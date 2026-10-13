import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/contra_voucher.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/expense.dart';
import 'package:agency_desktop/models/settlement.dart';
import 'package:agency_desktop/models/settlement_direction.dart';
import 'package:agency_desktop/ui/finance/expenses_page.dart';
import 'package:agency_desktop/ui/finance/settlements_page.dart';
import 'package:agency_desktop/ui/workspace/cheque_print_dialog.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Cheque printing (ACC-12): the payee override, who is offered the command,
/// the layout dialog, and a refusal staying in the dialog.
class _ChequeApi extends ApiClient {
  _ChequeApi({this.rows = const []})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Settlement> rows;
  final List<Expense> expenseRows = [];
  String? refuse;
  final List<String> pdfCalls = [];
  final List<String?> chequeCalls = [];
  final List<Map<String, Object?>> saves = [];
  final List<String> tests = [];
  final List<String> order = [];

  @override
  Future<PagedResult<Settlement>> settlements({
    required SettlementDirection direction,
    int page = 1,
    int pageSize = 20,
    String search = '',
    String? partyId,
    String? settlementFrom,
    String? settlementTo,
  }) async =>
      PagedResult<Settlement>(items: rows, total: rows.length);

  @override
  Future<PagedResult<Expense>> expenses({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String? status,
    String? expenseFrom,
    String? expenseTo,
  }) async =>
      PagedResult<Expense>(items: expenseRows, total: expenseRows.length);

  @override
  Future<List<int>> refundChequePdf(String refundId, {String? payee}) async {
    pdfCalls.add('refund $refundId $payee');
    return const [37, 80, 68, 70];
  }

  @override
  Future<List<int>> expenseChequePdf(String expenseId, {String? payee}) async {
    pdfCalls.add('expense $expenseId $payee');
    return const [37, 80, 68, 70];
  }

  @override
  Future<List<int>> paymentChequePdf(String paymentId, {String? payee}) async {
    if (refuse != null) throw ApiException(refuse!, statusCode: 422);
    chequeCalls.add(payee);
    return const [37, 80, 68, 70];
  }

  @override
  Future<List<MoneyAccount>> contraMoneyAccounts() async => const [
        MoneyAccount(id: 'cash-1', code: '1001', name: 'Cash', kind: 'CASH'),
        MoneyAccount(id: 'bank-1', code: '1002', name: 'HDFC', kind: 'BANK'),
      ];

  @override
  Future<ChequeLayout> chequeLayout(String ledgerAccountId) async =>
      ChequeLayout(
        ledgerAccountId: ledgerAccountId,
        offsetXMm: '2.0',
        offsetYMm: '-1.5',
      );

  @override
  Future<ChequeLayout> saveChequeLayout(
    String ledgerAccountId, {
    required String offsetXMm,
    required String offsetYMm,
    required bool printAcPayee,
  }) async {
    if (refuse != null) throw ApiException(refuse!, statusCode: 403);
    order.add('save');
    saves.add({
      'id': ledgerAccountId,
      'x': offsetXMm,
      'y': offsetYMm,
      'acPayee': printAcPayee,
    });
    return ChequeLayout(
      ledgerAccountId: ledgerAccountId,
      offsetXMm: offsetXMm,
      offsetYMm: offsetYMm,
      printAcPayee: printAcPayee,
      version: 1,
    );
  }

  @override
  Future<List<int>> chequeTestPdf(String ledgerAccountId) async {
    order.add('test');
    tests.add(ledgerAccountId);
    return const [37, 80, 68, 70];
  }
}

Settlement _payment({
  String id = 'py-1',
  String method = 'BANK',
  String mode = 'CHEQUE',
  String status = 'POSTED',
  String direction = 'PAYMENT',
}) =>
    Settlement(
      id: id,
      direction: direction,
      partyId: 'v-1',
      partyCode: 'V1',
      partyName: 'Acme Traders',
      settlementNumber: 'PY-0001',
      settlementDate: '2026-10-01',
      amount: '5000.00',
      allocatedAmount: '0.00',
      unallocatedAmount: '0.00',
      method: method,
      ledgerAccountName: 'HDFC',
      instrumentReference: '',
      narration: '',
      status: status,
      journalEntryId: 'j-1',
      reversalReason: '',
      allocations: const [],
      paymentMode: mode,
    );

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

void _window(WidgetTester tester, [Size size = const Size(800, 600)]) {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
}

Finder _key(String key) => find.byKey(ValueKey<String>(key));

Future<void> _openDialog(
  WidgetTester tester,
  Widget Function(BuildContext) dialog,
) async {
  _window(tester);
  await tester.pumpWidget(MaterialApp(
    home: Builder(
      builder: (context) => TextButton(
        onPressed: () => showDialog<Object>(context: context, builder: dialog),
        child: const Text('open'),
      ),
    ),
  ));
  await tester.tap(find.text('open'));
  await tester.pumpAndSettle();
}

Future<void> _openPayments(WidgetTester tester, _ChequeApi api) async {
  _window(tester, const Size(1600, 1100));
  final Directory temp = Directory.systemTemp.createTempSync('cheque');
  addTearDown(() => temp.deleteSync(recursive: true));
  await tester.pumpWidget(MaterialApp(
    builder: (context, child) => Phase2Scope(child: child!),
    home: Scaffold(
      body: SettlementsPage(
        api: api,
        preferences: DesktopPreferencesService(directory: temp),
        permissions: PermissionService()
          ..applyAccessToken(_accessToken({
            'roles': <String>['user'],
            'permissions': <String>['PAYMENT_VIEW', 'PAYMENT_CREATE'],
          })),
        hasActiveFirm: true,
        direction: SettlementDirection.payment,
      ),
    ),
  ));
  await tester.pumpAndSettle();
  await tester.tap(find.text('PY-0001').first);
  await tester.pump(const Duration(milliseconds: 500));
  await tester.pumpAndSettle();
}

Future<void> _openRefunds(
  WidgetTester tester,
  _ChequeApi api,
  List<String> printed,
) async {
  _window(tester, const Size(1600, 1100));
  final Directory temp = Directory.systemTemp.createTempSync('cheque');
  addTearDown(() => temp.deleteSync(recursive: true));
  await tester.pumpWidget(MaterialApp(
    builder: (context, child) => Phase2Scope(child: child!),
    home: Scaffold(
      body: SettlementsPage(
        api: api,
        preferences: DesktopPreferencesService(directory: temp),
        permissions: PermissionService()
          ..applyAccessToken(_accessToken({
            'roles': <String>['user'],
            'permissions': <String>['PAYMENT_VIEW', 'PAYMENT_CREATE'],
          })),
        hasActiveFirm: true,
        direction: SettlementDirection.refund,
        openPdfOverride: (name, bytes) async =>
            printed.add('$name:${bytes.length}'),
      ),
    ),
  ));
  await tester.pumpAndSettle();
  await tester.tap(find.text('PY-0001').first);
  await tester.pump(const Duration(milliseconds: 500));
  await tester.pumpAndSettle();
}

void main() {
  group('a refund and an expense on the leaf (F13)', () {
    test('a posted bank refund can be printed, a cash one cannot', () {
      expect(canPrintCheque(_payment(direction: 'REFUND')), isTrue);
      expect(
        canPrintCheque(_payment(direction: 'REFUND', method: 'CASH', mode: 'CASH')),
        isFalse,
      );
    });

    testWidgets('the Refunds screen prints from /refunds/{id}/cheque',
        (tester) async {
      final _ChequeApi api =
          _ChequeApi(rows: [_payment(id: 'rf-1', direction: 'REFUND')]);
      final List<String> printed = [];
      await _openRefunds(tester, api, printed);

      await tester.tap(find.text('Print cheque').first);
      await tester.pumpAndSettle();
      expect(find.text("Blank prints the customer's name"), findsOneWidget);
      await tester.tap(_key('cheque-print'));
      await tester.pumpAndSettle();

      expect(api.pdfCalls, ['refund rf-1 null']);
      expect(printed, ['Cheque PY-0001:4']);
    });

    testWidgets('a cash refund is offered no Print cheque', (tester) async {
      final _ChequeApi api = _ChequeApi(rows: [
        _payment(direction: 'REFUND', method: 'CASH', mode: 'CASH'),
      ]);
      await _openRefunds(tester, api, []);
      expect(find.byKey(const ValueKey('selection-bar')), findsOneWidget);
      expect(find.text('Print cheque'), findsNothing);
    });

    testWidgets('the Expenses screen prints from /expenses/{id}/cheque',
        (tester) async {
      final _ChequeApi api = _ChequeApi();
      api.expenseRows.add(Expense.fromJson({
        'id': 'e-1',
        'expense_number': 'EXP-0001',
        'expense_date': '2026-09-01',
        'expense_account_code': '6000',
        'expense_account_name': 'Rent',
        'paid_from_account_name': 'HDFC',
        'amount': '25000.00',
        'payee': 'Sharma Estates',
        'status': 'POSTED',
        'journal_entry_id': 'j-1',
        'version': 1,
      }));
      final List<String> printed = [];
      _window(tester, const Size(1600, 1100));
      final Directory temp = Directory.systemTemp.createTempSync('cheque');
      addTearDown(() => temp.deleteSync(recursive: true));
      await tester.pumpWidget(MaterialApp(
        builder: (context, child) => Phase2Scope(child: child!),
        home: Scaffold(
          body: ExpensesPage(
            api: api,
            preferences: DesktopPreferencesService(directory: temp),
            permissions: PermissionService()
              ..applyAccessToken(_accessToken({
                'roles': <String>['user'],
                'permissions': <String>['EXPENSE_VIEW', 'EXPENSE_CREATE'],
              })),
            hasActiveFirm: true,
            openPdfOverride: (name, bytes) async =>
                printed.add('$name:${bytes.length}'),
          ),
        ),
      ));
      await tester.pumpAndSettle();
      await tester.tap(find.text('EXP-0001').first);
      await tester.pump(const Duration(milliseconds: 500));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Print cheque').first);
      await tester.pumpAndSettle();
      expect(find.text('Pay Sharma Estates'), findsOneWidget);
      expect(find.text('Blank prints the payee kept on the expense'),
          findsOneWidget);
      await tester.tap(_key('cheque-print'));
      await tester.pumpAndSettle();

      expect(api.pdfCalls, ['expense e-1 null']);
      expect(printed, ['Cheque EXP-0001:4']);
    });
  });

  group('print cheque dialog', () {
    Future<void> open(
      WidgetTester tester,
      _ChequeApi api,
      List<String> printed,
    ) =>
        _openDialog(
          tester,
          (_) => ChequePrintDialog(
            api: api,
            paymentId: 'py-1',
            number: 'PY-0001',
            partyName: 'Acme Traders',
            amount: '5000.00',
            openPdfOverride: (name, bytes) async =>
                printed.add('$name:${bytes.length}'),
          ),
        );

    testWidgets('sends the payee typed, and prints the PDF', (tester) async {
      final _ChequeApi api = _ChequeApi();
      final List<String> printed = [];
      await open(tester, api, printed);

      expect(find.text("Blank prints the supplier's legal name"),
          findsOneWidget);
      expect(find.text('Pay Acme Traders'), findsOneWidget);
      expect(find.text('Amount 5000.00'), findsOneWidget);
      await tester.enterText(_key('cheque-payee'), 'Acme Trading Co');
      await tester.tap(_key('cheque-print'));
      await tester.pumpAndSettle();

      expect(api.chequeCalls, ['Acme Trading Co']);
      expect(printed, ['Cheque PY-0001:4']);
      expect(find.byType(ChequePrintDialog), findsNothing);
    });

    testWidgets('sends no payee when the box is blank', (tester) async {
      final _ChequeApi api = _ChequeApi();
      await open(tester, api, []);
      await tester.tap(_key('cheque-print'));
      await tester.pumpAndSettle();

      expect(api.chequeCalls, [null]);
    });

    testWidgets("the server's refusal stays in the dialog", (tester) async {
      final _ChequeApi api = _ChequeApi()
        ..refuse = 'A reversed payment cannot be printed.';
      final List<String> printed = [];
      await open(tester, api, printed);
      await tester.enterText(_key('cheque-payee'), 'Acme Trading Co');
      await tester.tap(_key('cheque-print'));
      await tester.pumpAndSettle();

      expect(find.text('A reversed payment cannot be printed.'),
          findsOneWidget);
      expect(find.byType(ChequePrintDialog), findsOneWidget);
      expect(find.text('Acme Trading Co'), findsOneWidget);
      expect(printed, isEmpty);
    });
  });

  group('who is offered the command', () {
    test('only a posted bank cheque payment', () {
      expect(canPrintCheque(_payment()), isTrue);
      expect(canPrintCheque(_payment(mode: '')), isTrue);
      expect(canPrintCheque(_payment(method: 'CASH', mode: 'CASH')), isFalse);
      expect(canPrintCheque(_payment(mode: 'UPI')), isFalse);
      expect(canPrintCheque(_payment(status: 'REVERSED')), isFalse);
      expect(canPrintCheque(_payment(direction: 'RECEIPT')), isFalse);
    });

    testWidgets('the Payments screen offers it for a cheque payment',
        (tester) async {
      final _ChequeApi api = _ChequeApi(rows: [_payment()]);
      await _openPayments(tester, api);

      await tester.tap(find.text('Print cheque').first);
      await tester.pumpAndSettle();
      expect(find.byType(ChequePrintDialog), findsOneWidget);
    });

    for (final Settlement row in [
      _payment(method: 'CASH', mode: 'CASH'),
      _payment(mode: 'UPI'),
      _payment(status: 'REVERSED'),
    ]) {
      testWidgets('not for ${row.method} ${row.paymentMode} ${row.status}',
          (tester) async {
        await _openPayments(tester, _ChequeApi(rows: [row]));
        expect(find.byKey(const ValueKey('selection-bar')), findsOneWidget);
        expect(find.text('Print cheque'), findsNothing);
      });
    }
  });

  group('cheque layout dialog', () {
    Future<void> open(
      WidgetTester tester,
      _ChequeApi api,
      List<String> printed,
    ) =>
        _openDialog(
          tester,
          (_) => ChequeLayoutDialog(
            api: api,
            openPdfOverride: (name, bytes) async =>
                printed.add('$name:${bytes.length}'),
          ),
        );

    Future<void> pickBank(WidgetTester tester) async {
      await tester.tap(_key('cheque-account'));
      await tester.pumpAndSettle();
      // Only the bank is offered, not the cash account.
      expect(find.textContaining('Cash'), findsNothing);
      await tester.tap(find.textContaining('HDFC').last);
      await tester.pumpAndSettle();
    }

    testWidgets('loads the layout, saves it and test prints', (tester) async {
      final _ChequeApi api = _ChequeApi();
      final List<String> printed = [];
      await open(tester, api, printed);
      await pickBank(tester);

      expect(find.text('2.0'), findsOneWidget);
      expect(find.text('-1.5'), findsOneWidget);

      await tester.enterText(_key('cheque-offset-x'), '3.5');
      await tester.enterText(_key('cheque-offset-y'), '-4');
      await tester.tap(_key('cheque-ac-payee'));
      await tester.pump();
      await tester.tap(_key('cheque-layout-save'));
      await tester.pumpAndSettle();

      expect(api.saves, [
        {'id': 'bank-1', 'x': '3.5', 'y': '-4.0', 'acPayee': false},
      ]);
      expect(find.text('Layout saved.'), findsOneWidget);

      await tester.tap(_key('cheque-test-print'));
      await tester.pumpAndSettle();
      // Nothing changed since the save, so it does not save again.
      expect(api.order, ['save', 'test']);
      expect(printed, ['Cheque test:4']);
      expect(find.byType(ChequeLayoutDialog), findsOneWidget);
    });

    testWidgets('test print saves a changed layout first', (tester) async {
      final _ChequeApi api = _ChequeApi();
      await open(tester, api, []);
      await pickBank(tester);

      await tester.enterText(_key('cheque-offset-x'), '5');
      await tester.pump();
      await tester.tap(_key('cheque-test-print'));
      await tester.pumpAndSettle();

      expect(api.order, ['save', 'test']);
      expect(api.saves.single['x'], '5.0');
    });

    testWidgets('a move past 30 mm is refused before any call', (tester) async {
      final _ChequeApi api = _ChequeApi();
      await open(tester, api, []);
      await pickBank(tester);

      await tester.enterText(_key('cheque-offset-x'), '31');
      await tester.tap(_key('cheque-layout-save'));
      await tester.pumpAndSettle();

      expect(_key('cheque-field-error'), findsOneWidget);
      expect(api.saves, isEmpty);
    });

    testWidgets("the server's refusal stays in the dialog", (tester) async {
      final _ChequeApi api = _ChequeApi();
      await open(tester, api, []);
      await pickBank(tester);
      api.refuse = 'You may not set up cheques.';

      await tester.enterText(_key('cheque-offset-x'), '4');
      await tester.tap(_key('cheque-layout-save'));
      await tester.pumpAndSettle();

      expect(find.text('You may not set up cheques.'), findsOneWidget);
      expect(find.byType(ChequeLayoutDialog), findsOneWidget);
      expect(find.text('4'), findsOneWidget);
    });

    testWidgets('the Payments screen opens it with nothing selected',
        (tester) async {
      final _ChequeApi api = _ChequeApi(rows: [_payment()]);
      _window(tester, const Size(1600, 1100));
      final Directory temp = Directory.systemTemp.createTempSync('cheque');
      addTearDown(() => temp.deleteSync(recursive: true));
      await tester.pumpWidget(MaterialApp(
        builder: (context, child) => Phase2Scope(child: child!),
        home: Scaffold(
          body: SettlementsPage(
            api: api,
            preferences: DesktopPreferencesService(directory: temp),
            permissions: PermissionService()
              ..applyAccessToken(_accessToken({
                'roles': <String>['user'],
                'permissions': <String>['PAYMENT_VIEW', 'PAYMENT_CREATE'],
              })),
            hasActiveFirm: true,
            direction: SettlementDirection.payment,
          ),
        ),
      ));
      await tester.pumpAndSettle();

      await tester.tap(_key('toolbar-more'));
      await tester.pumpAndSettle();
      await tester.tap(_key('toolbar-command-cheque-layout-menu'));
      await tester.pumpAndSettle();
      expect(find.byType(ChequeLayoutDialog), findsOneWidget);
    });
  });
}
