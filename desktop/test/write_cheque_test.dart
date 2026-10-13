// Write a cheque (F13): the firm's own cheque to a supplier, a customer being
// refunded, an expense or any other account, and the issued register that
// follows it.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/post_dated_cheque.dart';
import 'package:agency_desktop/models/settlement.dart';
import 'package:agency_desktop/models/settlement_direction.dart';
import 'package:agency_desktop/ui/finance/post_dated_cheque_page.dart';
import 'package:agency_desktop/ui/finance/write_cheque_dialog.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions(List<String> perms) => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': perms,
  }));

const List<String> _all = [
  'PAYMENT_VIEW',
  'PAYMENT_CREATE',
  'EXPENSE_CREATE',
  'JOURNAL_POST',
];

Json _issued(
  String id,
  String number,
  String status, {
  String kind = 'EXPENSE',
  String? expenseNumber,
}) =>
    <String, dynamic>{
      'id': id,
      'direction': 'ISSUED',
      'party_id': 'a-1',
      'party_code': '5100',
      'party_name': 'Office rent',
      'paid_to_kind': kind,
      'payee_name': 'Mr Rao',
      'bank_account_id': 'bank-1',
      'bank_account_name': 'HDFC current',
      'cheque_number': number,
      'cheque_date': '2026-10-01',
      'amount': '7000.0000',
      'received_on': '2026-10-01',
      'status': status,
      'is_due': false,
      'expense_number': expenseNumber,
      'version': 1,
    };

class _Api extends ApiClient {
  _Api({this.rows = const [], this.banks = 2})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Json> rows;
  final int banks;
  final List<String> requested = <String>[];
  Json? written;
  String? refuse;
  int supplierReads = 0;
  int customerReads = 0;

  @override
  Future<List<PartyOption>> settlementParties({
    required SettlementDirection direction,
    String search = '',
  }) async {
    if (direction == SettlementDirection.payment) {
      supplierReads++;
      return const [PartyOption(id: 's-1', code: 'S1', name: 'Acme Traders')];
    }
    customerReads++;
    return const [PartyOption(id: 'c-1', code: 'C1', name: 'Mehta Traders')];
  }

  @override
  Future<List<int>> downloadBytes(
    String path, {
    Map<String, String>? query,
    String method = 'GET',
    Json? body,
    bool retrying = false,
  }) async {
    requested.add('GET $path');
    return const [37, 80, 68, 70];
  }

  @override
  Future<Json> request(
    String method,
    String path, {
    Json? body,
    Map<String, String>? query,
    bool authenticated = true,
    bool retrying = false,
    int? expectedVersion,
  }) async {
    requested.add('$method $path');
    if (path.endsWith('/issued/accounts')) {
      return <String, dynamic>{
        'data': <String, dynamic>{
          'bank_accounts': [
            for (int i = 1; i <= banks; i++)
              {'id': 'bank-$i', 'code': '100$i', 'name': 'Bank $i'},
          ],
          'expense_accounts': [
            {'id': 'e-1', 'code': '5100', 'name': 'Office rent'},
          ],
          'other_accounts': [
            {'id': 'o-1', 'code': '3100', 'name': 'Loan from partner'},
          ],
        },
      };
    }
    if (method == 'POST' && path.endsWith('/issued/write')) {
      if (refuse != null) throw ApiException(refuse!, statusCode: 422);
      written = body;
      final bool held = DateTime.parse(body!['cheque_date'] as String)
          .isAfter(DateTime.now());
      return <String, dynamic>{
        'data': _issued('n-1', body['cheque_number'] as String,
            held ? 'HELD' : 'DEPOSITED',
            expenseNumber: held ? null : 'EXP-0001'),
      };
    }
    if (method == 'GET' && path.contains('/post-dated-cheques/issued')) {
      return <String, dynamic>{
        'data': rows,
        'pagination': <String, dynamic>{'total_records': rows.length},
      };
    }
    return <String, dynamic>{'data': const <Json>[]};
  }
}

Finder _key(String key) => find.byKey(ValueKey<String>(key));

Future<void> _openDialog(
  WidgetTester tester,
  _Api api,
  List<String> perms,
) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Builder(
      builder: (context) => TextButton(
        onPressed: () => showDialog<PostDatedCheque>(
          context: context,
          builder: (_) =>
              WriteChequeDialog(api: api, permissions: _permissions(perms)),
        ),
        child: const Text('open'),
      ),
    ),
  ));
  await tester.tap(find.text('open'));
  await tester.pumpAndSettle();
}

Future<void> _pickBank(WidgetTester tester) async {
  await tester.tap(_key('cheque-bank'));
  await tester.pumpAndSettle();
  await tester.tap(find.textContaining('Bank 1').last);
  await tester.pumpAndSettle();
}

Future<void> _pickPays(WidgetTester tester, String words) async {
  await tester.tap(_key('cheque-pays'));
  await tester.pumpAndSettle();
  await tester.tap(find.text(words).last);
  await tester.pumpAndSettle();
}

Future<void> _pickPayee(
    WidgetTester tester, String typed, String optionLabel) async {
  await tester.enterText(_key('cheque-payee-account'), typed);
  await tester.pumpAndSettle();
  await tester.tap(find.text(optionLabel).last);
  await tester.pumpAndSettle();
}

Future<void> _pump(
  WidgetTester tester,
  _Api api, {
  List<String> perms = _all,
}) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final List<String> printed = [];
  await tester.pumpWidget(MaterialApp(
    builder: (context, child) => Phase2Scope(child: child!),
    home: Scaffold(
      body: PostDatedChequePage(
        api: api,
        preferences: DesktopPreferencesService(
          directory: Directory.systemTemp.createTempSync('write-cheque'),
        ),
        permissions: _permissions(perms),
        hasActiveFirm: true,
        issued: true,
        openPdfOverride: (name, bytes) async =>
            printed.add('$name:${bytes.length}'),
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

Future<void> _select(WidgetTester tester, String number) async {
  await tester.tap(find.text(number).first);
  await tester.pump(const Duration(milliseconds: 500));
  await tester.pumpAndSettle();
}

void main() {
  group('the dialog', () {
    testWidgets('an expense account is sent as account_id, with only the '
        'declared keys', (tester) async {
      final _Api api = _Api();
      await _openDialog(tester, api, _all);
      await _pickBank(tester);
      await _pickPays(tester, 'Expense account');
      await _pickPayee(tester, 'rent', '5100  Office rent');
      await tester.enterText(_key('cheque-number'), '000321');
      await tester.enterText(_key('cheque-amount'), '7000');
      await tester.tap(_key('cheque-save'));
      await tester.pumpAndSettle();

      expect(api.requested, contains('POST /api/v1/post-dated-cheques/issued/write'));
      expect(api.written, <String, dynamic>{
        'bank_account_id': 'bank-1',
        'account_id': 'e-1',
        'payee_name': 'Office rent',
        'amount': '7000',
        'cheque_number': '000321',
        'cheque_date': api.written!['cheque_date'],
      });
      expect(tester.takeException(), isNull);
    });

    testWidgets('a supplier is sent as supplier_id, and the only bank is '
        'chosen already', (tester) async {
      final _Api api = _Api(banks: 1);
      await _openDialog(tester, api, _all);
      await _pickPayee(tester, 'acme', 'S1  Acme Traders');
      await tester.enterText(_key('cheque-number'), '000322');
      await tester.enterText(_key('cheque-amount'), '1500');
      await tester.enterText(_key('cheque-narration'), 'On account');
      await tester.tap(_key('cheque-save'));
      await tester.pumpAndSettle();

      expect(api.written!['bank_account_id'], 'bank-1');
      expect(api.written!['supplier_id'], 's-1');
      expect(api.written!.containsKey('customer_id'), isFalse);
      expect(api.written!.containsKey('account_id'), isFalse);
      expect(api.written!['narration'], 'On account');
    });

    testWidgets('suppliers and customers are read once, when first chosen',
        (tester) async {
      final _Api api = _Api();
      await _openDialog(tester, api, _all);
      expect(api.supplierReads, 1);
      expect(api.customerReads, 0);
      await _pickPays(tester, 'Customer (a refund)');
      await _pickPays(tester, 'Supplier');
      await _pickPays(tester, 'Customer (a refund)');
      expect(api.supplierReads, 1);
      expect(api.customerReads, 1);
    });

    testWidgets('the name on the cheque follows the account picked, and a '
        'typed name is kept and sent', (tester) async {
      final _Api api = _Api(banks: 1);
      await _openDialog(tester, api, _all);
      await _pickPayee(tester, 'acme', 'S1  Acme Traders');
      expect(find.text('Acme Traders'), findsOneWidget);

      await tester.enterText(_key('cheque-payee-name'), 'Acme Trading Co');
      await _pickPays(tester, 'Customer (a refund)');
      await _pickPayee(tester, 'mehta', 'C1  Mehta Traders');
      expect(find.text('Acme Trading Co'), findsOneWidget);

      await tester.enterText(_key('cheque-number'), '000323');
      await tester.enterText(_key('cheque-amount'), '90');
      await tester.tap(_key('cheque-save'));
      await tester.pumpAndSettle();

      expect(api.written!['payee_name'], 'Acme Trading Co');
      expect(api.written!['customer_id'], 'c-1');
    });

    testWidgets('the line under the date says held or recorded now',
        (tester) async {
      final _Api api = _Api();
      await _openDialog(tester, api, _all);
      expect(
        find.text('Dated today or before: it is recorded now as a payment '
            'to the supplier.'),
        findsOneWidget,
      );
      await _pickPays(tester, 'Expense account');
      expect(
        find.text('Dated today or before: it is recorded now as an expense.'),
        findsOneWidget,
      );

      await tester.tap(_key('cheque-date'));
      await tester.pumpAndSettle();
      // The picker opens on today; the next day is the ahead date.
      final DateTime next = DateTime.now().add(const Duration(days: 1));
      if (next.month != DateTime.now().month) {
        await tester.tap(find.byTooltip('Next month'));
        await tester.pumpAndSettle();
      }
      await tester.tap(find.text('${next.day}').last);
      await tester.tap(find.text('OK'));
      await tester.pumpAndSettle();
      expect(
        find.text('Dated ahead: it is held and posts nothing until you '
            'present it.'),
        findsOneWidget,
      );
    });

    testWidgets('a user with only the expense right is offered only that kind',
        (tester) async {
      final _Api api = _Api();
      await _openDialog(tester, api, const ['EXPENSE_CREATE']);
      await tester.tap(_key('cheque-pays'));
      await tester.pumpAndSettle();
      expect(find.text('Expense account'), findsWidgets);
      expect(find.text('Supplier'), findsNothing);
      expect(find.text('Customer (a refund)'), findsNothing);
      expect(find.text('Other account'), findsNothing);
    });

    testWidgets('a user with none of the rights cannot save', (tester) async {
      final _Api api = _Api();
      await _openDialog(tester, api, const []);
      expect(
        find.text('Writing a cheque needs the right to record a payment, an '
            'expense or a journal.'),
        findsOneWidget,
      );
      expect(
        tester.widget<FilledButton>(_key('cheque-save')).onPressed,
        isNull,
      );
    });

    testWidgets('a firm with no bank account is told so', (tester) async {
      final _Api api = _Api(banks: 0);
      await _openDialog(tester, api, _all);
      expect(find.text('The firm has no bank account to draw a cheque on.'),
          findsOneWidget);
    });

    testWidgets('an incomplete cheque is refused before the server',
        (tester) async {
      final _Api api = _Api();
      await _openDialog(tester, api, _all);
      await tester.tap(_key('cheque-save'));
      await tester.pumpAndSettle();
      expect(_key('cheque-problem'), findsOneWidget);
      expect(api.written, isNull);
    });

    testWidgets("the server's refusal keeps the dialog open", (tester) async {
      final _Api api = _Api(banks: 1)
        ..refuse = 'Cheque 000324 is already in use on this bank account.';
      await _openDialog(tester, api, _all);
      await _pickPayee(tester, 'acme', 'S1  Acme Traders');
      await tester.enterText(_key('cheque-number'), '000324');
      await tester.enterText(_key('cheque-amount'), '10');
      await tester.tap(_key('cheque-save'));
      await tester.pumpAndSettle();

      expect(find.text('Cheque 000324 is already in use on this bank account.'),
          findsOneWidget);
      expect(find.byType(WriteChequeDialog), findsOneWidget);
      expect(find.text('000324'), findsOneWidget);
    });

    testWidgets('the dialog fits the 800x600 window', (tester) async {
      final _Api api = _Api();
      await _openDialog(tester, api, _all);
      tester.view.physicalSize = const Size(800, 600);
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
    });
  });

  group('the issued register', () {
    testWidgets('shows Paid to, Pays and Recorded as for an expense cheque, '
        'and Print cheque asks for the cheque', (tester) async {
      final _Api api = _Api(rows: <Json>[
        _issued('d-1', '000400', 'DEPOSITED', expenseNumber: 'EXP-0007'),
      ]);
      await _pump(tester, api);

      expect(find.text('Paid to'), findsOneWidget);
      expect(find.text('Pays'), findsOneWidget);
      expect(find.text('Recorded as'), findsOneWidget);
      expect(find.text('Mr Rao'), findsOneWidget);
      expect(find.text('Expense'), findsOneWidget);
      expect(find.text('HDFC current'), findsOneWidget);
      expect(find.text('EXP-0007'), findsOneWidget);

      await _select(tester, '000400');
      await tester.tap(find.text('Print cheque').first);
      await tester.pumpAndSettle();
      await tester.tap(_key('cheque-print'));
      await tester.pumpAndSettle();
      expect(api.requested,
          contains('GET /api/v1/post-dated-cheques/issued/d-1/print'));
    });

    testWidgets('Print cheque is not offered for a cancelled cheque',
        (tester) async {
      final _Api api = _Api(rows: <Json>[_issued('x-1', '000401', 'CANCELLED')]);
      await _pump(tester, api);
      await _select(tester, '000401');
      expect(find.text('Print cheque'), findsNothing);
    });

    testWidgets('a user with none of the three rights sees no New button',
        (tester) async {
      final _Api api = _Api(rows: <Json>[_issued('d-1', '000400', 'HELD')]);
      await _pump(tester, api, perms: const ['PAYMENT_VIEW']);
      expect(find.byKey(const ValueKey('toolbar-new')), findsNothing);
    });

    testWidgets('writing a cheque selects it and offers to print',
        (tester) async {
      final _Api api = _Api(banks: 1);
      await _pump(tester, api);
      await tester.tap(find.byKey(const ValueKey('toolbar-new')));
      await tester.pumpAndSettle();
      await _pickPays(tester, 'Expense account');
      await _pickPayee(tester, 'rent', '5100  Office rent');
      await tester.enterText(_key('cheque-number'), '000500');
      await tester.enterText(_key('cheque-amount'), '7000');
      await tester.tap(_key('cheque-save'));
      await tester.pumpAndSettle();

      expect(api.written, isNotNull);
      expect(_key('cheque-print'), findsOneWidget);
      await tester.tap(_key('cheque-print'));
      await tester.pumpAndSettle();
      expect(api.requested,
          contains('GET /api/v1/post-dated-cheques/issued/n-1/print'));
    });
  });
}
