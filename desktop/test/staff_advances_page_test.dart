import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/staff_advance.dart';
import 'package:agency_desktop/ui/finance/staff_advances_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Accounts -> Staff Advances: what each employee owes, and the dialogs that
/// give an advance, record a recovery and take an entry back.
PermissionService _permissionsFor(List<String> perms) {
  final String payload = base64Url.encode(
    utf8.encode(jsonEncode({'permissions': perms})),
  );
  return PermissionService()..applyAccessToken('h.$payload.s');
}

StaffEmployee _employee(
  String id,
  String name, {
  String advanced = '5000.00',
  String recovered = '1000.00',
  String owes = '4000.00',
  bool active = true,
}) =>
    StaffEmployee.fromJson({
      'account_id': id,
      'code': 'SA-$id',
      'name': name,
      'is_active': active,
      'advanced': advanced,
      'recovered': recovered,
      'owes': owes,
    });

StaffAdvanceEntry _entry({String status = 'POSTED', String kind = 'ADVANCE'}) =>
    StaffAdvanceEntry.fromJson({
      'id': 'en-1',
      'entry_number': 'SAD-2026-2027-000001',
      'entry_date': '2026-09-01',
      'kind': kind,
      'employee_account_id': 'emp-1',
      'employee_name': 'Ravi',
      'other_account_id': 'a-cash',
      'other_account_code': '1000',
      'other_account_name': 'Cash',
      'other_side': 'MONEY',
      'amount': '2000.00',
      'narration': null,
      'status': status,
      'journal_entry_id': 'j-1',
      'version': 3,
    });

class _StaffApi extends ApiClient {
  _StaffApi({List<StaffEmployee>? employees})
      : employees = employees ??
            [
              _employee('emp-1', 'Ravi'),
              _employee('emp-2', 'Sunil',
                  advanced: '3000.00', recovered: '0.00', owes: '3000.00'),
              _employee('emp-3', 'Old Hand',
                  advanced: '0.00',
                  recovered: '0.00',
                  owes: '0.00',
                  active: false),
            ],
        super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<StaffEmployee> employees;
  int employeeReads = 0;
  int choiceReads = 0;
  String? added;
  Json? recorded;
  int saves = 0;
  bool asksAboutCash = false;
  String? cancelId;
  String? cancelReason;
  int? cancelVersion;
  String? entriesFor;

  @override
  Future<List<StaffEmployee>> staffEmployees() async {
    employeeReads++;
    return employees;
  }

  @override
  Future<StaffEmployee> addStaffEmployee(String name) async {
    added = name;
    final StaffEmployee made = _employee('emp-9', name,
        advanced: '0.00', recovered: '0.00', owes: '0.00');
    employees.add(made);
    return made;
  }

  @override
  Future<StaffAdvanceAccountChoices> staffAdvanceAccountChoices() async {
    choiceReads++;
    return StaffAdvanceAccountChoices.fromJson({
      'money_accounts': [
        {'id': 'a-bank', 'code': '1010', 'name': 'Bank', 'kind': 'BANK'},
        {'id': 'a-cash', 'code': '1000', 'name': 'Cash', 'kind': 'CASH'},
      ],
      'salary_accounts': [
        {'id': 'a-rent', 'code': '6000', 'name': 'Rent', 'kind': null},
        {'id': 'a-salary', 'code': '6100', 'name': 'Salaries', 'kind': null},
      ],
    });
  }

  @override
  Future<StaffAdvanceEntry> recordStaffAdvance(Json data) async {
    recorded = data;
    saves++;
    if (asksAboutCash && data['cash_below_zero_confirmed'] != true) {
      throw const ApiException(
        'Cash holds 500.00 and this pays 800.00 out of it. Save anyway?',
        statusCode: 409,
        details: <String, dynamic>{'reason': 'cash_below_zero'},
      );
    }
    return _entry(kind: data['kind'] as String);
  }

  @override
  Future<PagedResult<StaffAdvanceEntry>> staffAdvances({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String? employeeAccountId,
    String? status,
    String? entryFrom,
    String? entryTo,
  }) async {
    entriesFor = employeeAccountId;
    return PagedResult<StaffAdvanceEntry>(items: [_entry()], total: 1);
  }

  @override
  Future<StaffAdvanceEntry> cancelStaffAdvance(
    String id, {
    required String reason,
    int? version,
  }) async {
    cancelId = id;
    cancelReason = reason;
    cancelVersion = version;
    return _entry(status: 'CANCELLED');
  }
}

Future<void> _pump(
  WidgetTester tester,
  _StaffApi api, {
  List<String> perms = const [
    'EXPENSE_VIEW',
    'EXPENSE_CREATE',
    'EXPENSE_CANCEL',
  ],
}) async {
  tester.view.physicalSize = const Size(1400, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      builder: (context, child) => Phase2Scope(child: child!),
      home: Scaffold(
        body: StaffAdvancesPage(
          api: api,
          permissions: _permissionsFor(perms),
          hasActiveFirm: true,
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

Future<void> _select(WidgetTester tester, String name) async {
  await tester.tap(find.text(name).first);
  // Past the double-click window, which is when a click is a selection.
  await tester.pump(const Duration(milliseconds: 500));
  await tester.pumpAndSettle();
}

Future<void> _pick(WidgetTester tester, Key dropdown, String text) async {
  await tester.tap(find.byKey(dropdown));
  await tester.pumpAndSettle();
  await tester.tap(find.text(text).last);
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('the list shows what each owes and the total, in one request',
      (tester) async {
    final _StaffApi api = _StaffApi();
    await _pump(tester, api);

    expect(find.text('Ravi'), findsOneWidget);
    expect(find.text('Sunil'), findsOneWidget);
    expect(find.text('Old Hand (switched off)'), findsOneWidget);
    expect(find.text('Still owes'), findsOneWidget);
    expect(find.text('4,000.00'), findsOneWidget);
    expect(find.text('3,000.00'), findsWidgets);
    final Text total =
        tester.widget(find.byKey(const ValueKey('staff-total-owed')));
    expect(total.data, '7,000.00');
    expect(api.employeeReads, 1);
    expect(api.choiceReads, 0);
    expect(api.entriesFor, isNull);
  });

  testWidgets('an empty firm is told to add the first employee',
      (tester) async {
    await _pump(tester, _StaffApi(employees: []));
    expect(
      find.text('No employees yet. Add the first one to give an advance.'),
      findsOneWidget,
    );
  });

  testWidgets('Add employee posts the name and reads the list again',
      (tester) async {
    final _StaffApi api = _StaffApi();
    await _pump(tester, api);

    await tester.tap(find.text('Add employee').first);
    await tester.pumpAndSettle();
    await tester.enterText(
        find.byKey(const ValueKey('staff-employee-name')), 'Meena');
    await tester.tap(find.byKey(const ValueKey('staff-employee-save')));
    await tester.pumpAndSettle();

    expect(api.added, 'Meena');
    expect(api.employeeReads, 2);
    expect(find.text('Meena'), findsOneWidget);
    // The new row is the selected one.
    expect(find.byKey(const ValueKey('selection-bar')), findsOneWidget);
  });

  testWidgets('Give advance posts an ADVANCE from the chosen account',
      (tester) async {
    final _StaffApi api = _StaffApi();
    await _pump(tester, api);
    await _select(tester, 'Ravi');

    await tester.tap(find.text('Give advance').first);
    await tester.pumpAndSettle();
    expect(api.choiceReads, 1);
    expect(find.text('He owes 4,000.00 now.'), findsOneWidget);
    // Cash comes first and is chosen, though the server listed the bank first.
    expect(find.text('1000 Cash'), findsOneWidget);

    await _pick(tester, const ValueKey('staff-other-SALARY'), '1010 Bank');
    await tester.enterText(find.byKey(const ValueKey('staff-amount')), '2000');
    await tester.enterText(find.byKey(const ValueKey('staff-note')), 'Diwali');
    await tester.tap(find.byKey(const ValueKey('staff-save')));
    await tester.pumpAndSettle();

    expect(api.recorded?['kind'], 'ADVANCE');
    expect(api.recorded?['employee_account_id'], 'emp-1');
    expect(api.recorded?['other_account_id'], 'a-bank');
    expect(api.recorded?['amount'], '2000');
    expect(api.recorded?['narration'], 'Diwali');
    expect(api.recorded?.containsKey('cash_below_zero_confirmed'), isFalse);
    expect(api.employeeReads, 2);

    // The choices are kept: a second dialog does not read them again.
    await tester.tap(find.text('Record recovery').first);
    await tester.pumpAndSettle();
    expect(api.choiceReads, 1);
  });

  testWidgets('the cash question is asked and the resend is confirmed',
      (tester) async {
    final _StaffApi api = _StaffApi()..asksAboutCash = true;
    await _pump(tester, api);
    await _select(tester, 'Ravi');
    await tester.tap(find.text('Give advance').first);
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const ValueKey('staff-amount')), '800');
    await tester.tap(find.byKey(const ValueKey('staff-save')));
    await tester.pumpAndSettle();

    expect(find.text('Cash would go below zero'), findsOneWidget);
    await tester.tap(find.text('Go back'));
    await tester.pumpAndSettle();
    expect(api.saves, 1);
    expect(find.text('Give advance'), findsWidgets);

    await tester.tap(find.byKey(const ValueKey('staff-save')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Save anyway'));
    await tester.pumpAndSettle();

    expect(api.saves, 3);
    expect(api.recorded?['cash_below_zero_confirmed'], true);
    expect(api.recorded?['other_account_id'], 'a-cash');
    expect(api.employeeReads, 2);
  });

  testWidgets('a recovery above what is owed is refused on the screen',
      (tester) async {
    final _StaffApi api = _StaffApi();
    await _pump(tester, api);
    await _select(tester, 'Ravi');
    await tester.tap(find.text('Record recovery').first);
    await tester.pumpAndSettle();

    expect(find.text('He owes 4,000.00.'), findsOneWidget);
    await tester.enterText(find.byKey(const ValueKey('staff-amount')), '4500');
    await tester.tap(find.byKey(const ValueKey('staff-save')));
    await tester.pumpAndSettle();

    expect(find.text('He owes only 4,000.00.'), findsOneWidget);
    expect(api.saves, 0);
  });

  testWidgets('Taken from salary sends the salary account', (tester) async {
    final _StaffApi api = _StaffApi();
    await _pump(tester, api);
    await _select(tester, 'Ravi');
    await tester.tap(find.text('Record recovery').first);
    await tester.pumpAndSettle();

    expect(
      find.textContaining('The salary account is charged this amount.'),
      findsOneWidget,
    );
    // The account named for salary is chosen, not the first in the list.
    await tester.enterText(find.byKey(const ValueKey('staff-amount')), '1500');
    await tester.tap(find.byKey(const ValueKey('staff-save')));
    await tester.pumpAndSettle();

    expect(api.recorded?['kind'], 'RECOVERY');
    expect(api.recorded?['other_account_id'], 'a-salary');
    expect(api.recorded?['amount'], '1500');
  });

  testWidgets('Paid back sends the money account', (tester) async {
    final _StaffApi api = _StaffApi();
    await _pump(tester, api);
    await _select(tester, 'Ravi');
    await tester.tap(find.text('Record recovery').first);
    await tester.pumpAndSettle();

    await _pick(
        tester, const ValueKey('staff-side'), 'Paid back in cash or bank');
    expect(
      find.textContaining('The salary account is charged this amount.'),
      findsNothing,
    );
    await tester.enterText(find.byKey(const ValueKey('staff-amount')), '500');
    await tester.tap(find.byKey(const ValueKey('staff-save')));
    await tester.pumpAndSettle();

    expect(api.recorded?['kind'], 'RECOVERY');
    expect(api.recorded?['other_account_id'], 'a-cash');
  });

  testWidgets('Entries lists the employee\'s entries and Cancel sends the '
      'reason and the version', (tester) async {
    final _StaffApi api = _StaffApi();
    await _pump(tester, api);
    await _select(tester, 'Ravi');

    await tester.tap(find.text('Entries').first);
    await tester.pumpAndSettle();
    expect(api.entriesFor, 'emp-1');
    expect(find.text('SAD-2026-2027-000001'), findsOneWidget);
    expect(find.text('Advance'), findsOneWidget);
    expect(find.text('2,000.00'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('staff-cancel-en-1')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).last, 'Typed twice');
    await tester.pump();
    await tester.tap(find.text('Cancel entry'));
    await tester.pumpAndSettle();

    expect(api.cancelId, 'en-1');
    expect(api.cancelReason, 'Typed twice');
    expect(api.cancelVersion, 3);
    expect(api.employeeReads, 2);
  });

  testWidgets('without EXPENSE_CREATE there is no Add, Give or Record',
      (tester) async {
    final _StaffApi api = _StaffApi();
    await _pump(tester, api, perms: const ['EXPENSE_VIEW']);
    await _select(tester, 'Ravi');

    expect(find.text('Add employee'), findsNothing);
    expect(find.text('Give advance'), findsNothing);
    expect(find.text('Record recovery'), findsNothing);
    expect(find.text('Entries'), findsWidgets);
    expect(tester.takeException(), isNull);
  });
}
