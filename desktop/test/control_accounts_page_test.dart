import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/finance.dart';
import 'package:agency_desktop/ui/finance/control_accounts_page.dart';
import 'package:agency_desktop/ui/workspace/module_catalog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Which account each posting purpose lands in, on a screen.
///
/// The mapping had no endpoint and no screen: opening the books wrote all 24
/// and re-pointing one was SQL. A purpose with lines already posted to its
/// account is held -- the row shows the count and offers no picker -- because
/// re-pointing it would leave two accounts each holding part of one story.

PermissionService _permissions(List<String> codes) {
  final String payload =
      base64Url.encode(utf8.encode(jsonEncode({'permissions': codes})));
  return PermissionService()..applyAccessToken('h.$payload.s');
}

ControlAccountMapping _row(
  String purpose,
  String label, {
  String? accountId,
  String code = '',
  String name = '',
  int posted = 0,
  List<String> types = const ['ASSET'],
}) =>
    ControlAccountMapping.fromJson({
      'purpose': purpose,
      'label': label,
      'expected_types': types,
      'ledger_account_id': accountId,
      'account_code': code,
      'account_name': name,
      'posted_lines': posted,
    });

LedgerAccount _account(String id, String code, String name, String type) =>
    LedgerAccount.fromJson({
      'id': id,
      'firm_id': 'firm-1',
      'account_group_id': 'g-1',
      'code': code,
      'name': name,
      'account_type': type,
      'is_active': true,
    });

class _Api extends ApiClient {
  _Api({required this.rows, this.refuse})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  List<ControlAccountMapping> rows;
  final String? refuse;
  final List<(String, String)> assigned = [];

  @override
  Future<List<ControlAccountMapping>> controlAccounts() async => rows;

  @override
  Future<PagedResult<LedgerAccount>> ledgerAccounts({
    String? accountGroupId,
    bool? isActive,
  }) async =>
      PagedResult(items: [
        _account('a-1200', '1200', 'Inventory', 'ASSET'),
        _account('a-1250', '1250', 'Stock in hand', 'ASSET'),
        _account('a-4000', '4000', 'Sales', 'INCOME'),
      ], total: 3);

  @override
  Future<String> assignControlAccount(
    String purpose,
    String ledgerAccountId,
  ) async {
    if (refuse != null) throw ApiException(refuse!, statusCode: 422);
    assigned.add((purpose, ledgerAccountId));
    rows = [
      for (final ControlAccountMapping row in rows)
        if (row.purpose == purpose)
          _row(purpose, row.label,
              accountId: ledgerAccountId, code: '1250', name: 'Stock in hand')
        else
          row,
    ];
    return 'Inventory posts to 1250 Stock in hand.';
  }
}

Future<void> _pump(
  WidgetTester tester,
  _Api api, {
  List<String> perms = const ['ACCOUNT_VIEW', 'ACCOUNT_MANAGE'],
  bool hasActiveFirm = true,
}) async {
  tester.view.physicalSize = const Size(1400, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: ControlAccountsPage(
        api: api,
        permissions: _permissions(perms),
        hasActiveFirm: hasActiveFirm,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

void main() {
  final List<ControlAccountMapping> rows = [
    _row('ACCOUNTS_RECEIVABLE', 'Accounts receivable',
        accountId: 'a-1100', code: '1100', name: 'Trade Receivables', posted: 3),
    _row('INVENTORY', 'Inventory',
        accountId: 'a-1200', code: '1200', name: 'Inventory'),
    _row('ROUNDING', 'Rounding', types: ['EXPENSE', 'INCOME']),
  ];

  testWidgets('lists every purpose with its account, gaps and holds',
      (tester) async {
    await _pump(tester, _Api(rows: rows));

    expect(find.text('Accounts receivable'), findsOneWidget);
    expect(find.text('1100 Trade Receivables'), findsOneWidget);
    expect(find.text('1200 Inventory'), findsOneWidget);
    expect(find.text('Not mapped'), findsOneWidget);
    expect(find.textContaining('1 of 3 purposes have no account'), findsOneWidget);
    // A held purpose says how many lines hold it and offers no picker.
    expect(find.text('3 posted'), findsOneWidget);
    expect(find.byKey(const ValueKey('control-account-edit-ACCOUNTS_RECEIVABLE')),
        findsNothing);
    expect(find.byKey(const ValueKey('control-account-edit-INVENTORY')),
        findsOneWidget);
    expect(find.text('Map'), findsOneWidget, reason: 'the gap');
    expect(find.text('Change'), findsOneWidget, reason: 'the free one');
  });

  testWidgets('re-points a purpose through the picker, filtered by type',
      (tester) async {
    final _Api api = _Api(rows: rows);
    await _pump(tester, api);

    await tester.tap(find.byKey(const ValueKey('control-account-edit-INVENTORY')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('control-account-INVENTORY')));
    await tester.pumpAndSettle();
    // Only asset accounts are offered for an asset purpose.
    expect(find.text('4000 Sales'), findsNothing);
    await tester.tap(find.text('1250 Stock in hand').last);
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    expect(api.assigned, [('INVENTORY', 'a-1250')]);
    expect(find.text('1250 Stock in hand'), findsOneWidget);
    expect(find.byKey(const ValueKey('control-account-INVENTORY')), findsNothing);
  });

  testWidgets('a refusal is shown and the mapping stays', (tester) async {
    final _Api api = _Api(
      rows: rows,
      refuse: 'Inventory has 5 posted lines on 1200 Inventory. Re-pointing '
          'it would leave two accounts each holding part of one story.',
    );
    await _pump(tester, api);

    await tester.tap(find.byKey(const ValueKey('control-account-edit-INVENTORY')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('control-account-INVENTORY')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('1250 Stock in hand').last);
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    expect(find.textContaining('5 posted lines'), findsOneWidget);
    expect(api.assigned, isEmpty);
  });

  testWidgets('a viewer sees the mapping and cannot change it', (tester) async {
    await _pump(tester, _Api(rows: rows), perms: const ['ACCOUNT_VIEW']);

    expect(find.text('1200 Inventory'), findsOneWidget);
    expect(find.text('Change'), findsNothing);
    expect(find.text('Map'), findsNothing);
  });

  testWidgets('needs a firm', (tester) async {
    await _pump(tester, _Api(rows: rows), hasActiveFirm: false);
    expect(find.text('Select a firm'), findsOneWidget);
  });

  test('is a tab of Finance, read with the chart\'s own code', () {
    final ModuleDefinition finance = ModuleCatalog.byId(AppModule.accounting);
    final ModuleTabDefinition tab =
        finance.tabs.firstWhere((tab) => tab.id == 'control-accounts');
    expect(tab.label, 'Control Accounts');
    expect(tab.requiredPermissions, ['ACCOUNT_VIEW']);
  });
}
