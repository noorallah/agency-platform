import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/expense.dart';
import 'package:agency_desktop/ui/finance/expenses_page.dart';
import 'package:agency_desktop/ui/finance/record_expense_dialog.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Accounts -> Expenses: rent, fuel and salaries recorded without the journal
/// screen, the journal written and posted by the server as each is saved.
PermissionService _permissionsFor(List<String> perms) {
  final String payload = base64Url.encode(
    utf8.encode(jsonEncode({'permissions': perms})),
  );
  return PermissionService()..applyAccessToken('h.$payload.s');
}

Expense _expense({String status = 'POSTED'}) => Expense.fromJson({
      'id': 'e-1',
      'expense_number': 'EXP-2026-2027-000001',
      'expense_date': '2026-09-01',
      'expense_account_code': '6000',
      'expense_account_name': 'Rent',
      'paid_from_account_name': 'Bank',
      'amount': '25000.00',
      'payee': 'Sharma Estates',
      'reference': 'RENT-SEP-26',
      'narration': 'Godown rent for September',
      'status': status,
      'journal_entry_id': 'j-1',
      'cancel_reason': null,
      'version': 1,
    });

class _ExpenseApi extends ApiClient {
  _ExpenseApi({this.rows = const []})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Expense> rows;
  Json? recorded;
  String? cancelledId;
  String? cancelReason;
  int? cancelVersion;
  String? refusal;

  @override
  Future<PagedResult<Expense>> expenses({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String? status,
    String? expenseFrom,
    String? expenseTo,
  }) async =>
      PagedResult<Expense>(items: rows, total: rows.length);

  @override
  Future<Expense> expense(String id) async => rows.first;

  @override
  Future<ExpenseAccountChoices> expenseAccountChoices() async =>
      ExpenseAccountChoices.fromJson({
        'expense_accounts': [
          {'id': 'a-rent', 'code': '6000', 'name': 'Rent'},
          {'id': 'a-fuel', 'code': '6400', 'name': 'Travel and Conveyance'},
        ],
        'paid_from_accounts': [
          {'id': 'a-cash', 'code': '1000', 'name': 'Cash'},
          {'id': 'a-bank', 'code': '1010', 'name': 'Bank'},
        ],
      });

  @override
  Future<Expense> recordExpense(Json data) async {
    recorded = data;
    if (refusal != null) {
      throw ApiException(refusal!, statusCode: 422);
    }
    return _expense();
  }

  @override
  Future<Expense> cancelExpense({
    required String id,
    required String reason,
    int? expectedVersion,
  }) async {
    cancelledId = id;
    cancelReason = reason;
    cancelVersion = expectedVersion;
    return _expense(status: 'CANCELLED');
  }
}

Future<void> _pump(
  WidgetTester tester,
  _ExpenseApi api, {
  List<String> perms = const [
    'EXPENSE_VIEW',
    'EXPENSE_CREATE',
    'EXPENSE_CANCEL',
  ],
  Size size = const Size(1400, 900),
}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      // Above the navigator, so a dialog the page opens is phase 2's too.
      builder: (context, child) => Phase2Scope(child: child!),
      home: Scaffold(
        body: ExpensesPage(
          api: api,
          preferences: DesktopPreferencesService(
            directory: Directory.systemTemp.createTempSync('expenses'),
          ),
          permissions: _permissionsFor(perms),
          hasActiveFirm: true,
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

Future<void> _select(WidgetTester tester) async {
  await tester.tap(find.text('EXP-2026-2027-000001').first);
  // Past the double-click window, which is when a click is a selection.
  await tester.pump(const Duration(milliseconds: 500));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('the grid lists each expense with Period and Columns',
      (tester) async {
    await _pump(tester, _ExpenseApi(rows: [_expense()]));

    expect(find.byType(EnterpriseDataGrid<Expense>), findsOneWidget);
    expect(find.text('Rent'), findsOneWidget);
    expect(find.text('Sharma Estates'), findsOneWidget);
    expect(find.text('Paid from'), findsOneWidget);
    expect(find.byType(DateRangeFilter), findsOneWidget);
    expect(find.byType(ColumnsButton), findsOneWidget);
    // Nothing is picked until somebody picks it.
    expect(find.byKey(const ValueKey('selection-bar')), findsNothing);
  });

  testWidgets('the bar names the expense and cancels it with a reason',
      (tester) async {
    final _ExpenseApi api = _ExpenseApi(rows: [_expense()]);
    await _pump(tester, api);
    await _select(tester);

    expect(find.byKey(const ValueKey('selection-bar')), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('selection-cancel')));
    await tester.pumpAndSettle();
    expect(find.text('Cancel EXP-2026-2027-000001'), findsOneWidget);
    await tester.enterText(find.byType(TextField).last, 'Typed twice');
    await tester.tap(find.text('Cancel expense'));
    await tester.pumpAndSettle();

    expect(api.cancelledId, 'e-1');
    expect(api.cancelReason, 'Typed twice');
    expect(api.cancelVersion, 1);
  });

  testWidgets('Cancel is not offered without EXPENSE_CANCEL', (tester) async {
    await _pump(
      tester,
      _ExpenseApi(rows: [_expense()]),
      perms: const ['EXPENSE_VIEW', 'EXPENSE_CREATE'],
    );
    await _select(tester);

    expect(find.byKey(const ValueKey('selection-bar')), findsOneWidget);
    expect(find.byKey(const ValueKey('selection-cancel')), findsNothing);
  });

  testWidgets('New records the expense with the right payload', (tester) async {
    final _ExpenseApi api = _ExpenseApi();
    tester.view.physicalSize = const Size(1400, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    Expense? saved;
    await tester.pumpWidget(
      MaterialApp(
        builder: (context, child) => Phase2Scope(child: child!),
        home: Scaffold(
          body: Builder(
            builder: (context) => TextButton(
              onPressed: () async {
                saved = await showDialog<Expense>(
                  context: context,
                  builder: (_) => RecordExpenseDialog(
                    api: api,
                    today: DateTime(2026, 9, 1),
                  ),
                );
              },
              child: const Text('open'),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const ValueKey('expense-account')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('6000 Rent').last);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('expense-paid-from')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('1010 Bank').last);
    await tester.pumpAndSettle();
    await tester.enterText(
        find.byKey(const ValueKey('expense-amount')), '25000');
    await tester.enterText(
        find.byKey(const ValueKey('expense-payee')), 'Sharma Estates');
    await tester.enterText(
        find.byKey(const ValueKey('expense-reference')), 'RENT-SEP-26');
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();

    expect(api.recorded, {
      'expense_date': '2026-09-01',
      'expense_account_id': 'a-rent',
      'paid_from_account_id': 'a-bank',
      'amount': '25000',
      'payee': 'Sharma Estates',
      'reference': 'RENT-SEP-26',
    });
    expect(saved?.expenseNumber, 'EXP-2026-2027-000001');
  });

  testWidgets('a refusal is shown in the server\'s words', (tester) async {
    final _ExpenseApi api = _ExpenseApi()
      ..refusal = 'No open accounting period covers 2026-09-01.';
    tester.view.physicalSize = const Size(1400, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(
      MaterialApp(
        builder: (context, child) => Phase2Scope(child: child!),
        home: Scaffold(body: RecordExpenseDialog(api: api)),
      ),
    );
    await tester.pumpAndSettle();

    // Nothing chosen yet: refused before the server is asked.
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();
    expect(find.text('Choose what the money was spent on.'), findsOneWidget);
    expect(api.recorded, isNull);

    await tester.tap(find.byKey(const ValueKey('expense-account')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('6400 Travel and Conveyance').last);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('expense-paid-from')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('1000 Cash').last);
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const ValueKey('expense-amount')), '300');
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();

    expect(api.recorded, isNotNull);
    expect(
      find.text('No open accounting period covers 2026-09-01.'),
      findsOneWidget,
    );
  });

  testWidgets('it fits the smallest screen the app supports', (tester) async {
    await _pump(
      tester,
      _ExpenseApi(rows: [_expense(), _expense(status: 'CANCELLED')]),
      size: const Size(1366, 768),
    );
    await _select(tester);
    expect(tester.takeException(), isNull);
  });
}
