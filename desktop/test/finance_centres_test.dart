import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/finance.dart';
import 'package:agency_desktop/ui/finance/finance_workspace.dart';
import 'package:agency_desktop/ui/finance/journal_entry_dialog.dart';
import 'package:agency_desktop/ui/resource_management_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart';
import 'package:agency_desktop/ui/workspace/module_catalog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Cost and profit centres reach a screen, and a journal line can name one.
///
/// Both tables existed in finance with a `requires_cost_center` flag no
/// account set and no screen to write either. A line on an account that
/// requires a centre is refused by the engine without one -- so the picker
/// appears on exactly that line, and on no other.

PermissionService _permissions(List<String> codes) {
  final String payload =
      base64Url.encode(utf8.encode(jsonEncode({'permissions': codes})));
  return PermissionService()..applyAccessToken('h.$payload.s');
}

FinanceCentre _centre(String id, String code) => FinanceCentre.fromJson({
      'id': id,
      'code': code,
      'name': '$code centre',
      'is_active': true,
    });

LedgerAccount _account(String id, String code,
        {bool cost = false, bool profit = false}) =>
    LedgerAccount.fromJson({
      'id': id,
      'firm_id': 'firm-1',
      'account_group_id': 'g-1',
      'code': code,
      'name': 'Account $code',
      'account_type': 'EXPENSE',
      'is_active': true,
      'requires_cost_center': cost,
      'requires_profit_center': profit,
    });

class _Api extends ApiClient {
  _Api()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  Json? created;

  @override
  Future<PagedResult<FinanceCentre>> costCenters() async =>
      PagedResult(items: [_centre('cc-1', 'SALES')], total: 1);

  @override
  Future<PagedResult<FinanceCentre>> profitCenters() async =>
      PagedResult(items: [_centre('pc-1', 'NORTH')], total: 1);

  @override
  Future<Json> create(String resource, Json data) async {
    created = {'resource': resource, ...data};
    return {'data': {'id': 'new-1', ...data}};
  }
}

void main() {
  test('both centres are tabs of Finance behind the chart\'s view code', () {
    final ModuleDefinition finance = ModuleCatalog.byId(AppModule.accounting);
    for (final String id in ['cost-centers', 'profit-centers']) {
      final ModuleTabDefinition tab =
          finance.tabs.firstWhere((tab) => tab.id == id);
      expect(tab.requiredPermissions, ['ACCOUNT_VIEW'], reason: id);
    }
  });

  test('the definition writes through the finance routes and never deletes',
      () {
    final _Api api = _Api();
    final ResourceDefinition<FinanceCentre> cost = financeCentreDefinition(
      api,
      _permissions(const ['ACCOUNT_VIEW', 'ACCOUNT_MANAGE']),
      profit: false,
    );
    final ResourceDefinition<FinanceCentre> profit = financeCentreDefinition(
      api,
      _permissions(const ['ACCOUNT_VIEW']),
      profit: true,
    );
    expect(cost.resource, 'finance/cost-centers');
    expect(profit.resource, 'finance/profit-centers');
    expect(cost.partialUpdate, isTrue, reason: 'the endpoint is a PATCH');
    expect(cost.canUseAction!(ToolbarAction.delete, null), isFalse);
    expect(cost.canUseAction!(ToolbarAction.newItem, null), isTrue);
    expect(profit.canUseAction!(ToolbarAction.newItem, null), isFalse,
        reason: 'ACCOUNT_VIEW reads and does not write');

    final Json payload = cost.payload(
      {'code': 'SALES', 'name': 'Sales', 'description': '', 'is_active': true},
      true,
    );
    expect(payload, {'code': 'SALES', 'name': 'Sales', 'is_active': true});
    // The code is read-only after creation and is not sent on an update.
    expect(
      cost.payload({'code': 'SALES', 'name': 'Sales (r)', 'is_active': false},
          false),
      {'name': 'Sales (r)', 'is_active': false},
    );
  });

  testWidgets('the picker appears on the line whose account requires it',
      (tester) async {
    tester.view.physicalSize = const Size(1600, 1000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: JournalEntryDialog(
          api: _Api(),
          accounts: [
            _account('a-cash', '1000'),
            _account('a-purch', '5000', cost: true),
          ],
          periods: const [],
          journalTypes: const [],
          voucherTypes: const [],
          costCenters: [_centre('cc-1', 'SALES')],
          profitCenters: [_centre('pc-1', 'NORTH')],
        ),
      ),
    ));
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('cost-centre-0')), findsNothing);

    // Choose the account that requires a cost centre on line 1.
    await tester.tap(find.text('Account 1').first);
    await tester.pumpAndSettle();
    await tester.tap(find.textContaining('5000').last);
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('cost-centre-0')), findsOneWidget);
    expect(find.byKey(const ValueKey('profit-centre-0')), findsNothing,
        reason: 'the account requires a cost centre and not a profit centre');
    expect(find.byKey(const ValueKey('cost-centre-1')), findsNothing,
        reason: 'line 2 has no account yet');
  });

  test('a line carries its centres in the payload only when set', () {
    final JournalDraftLine bare =
        JournalDraftLine(ledgerAccountId: 'a-1', debit: '10');
    expect(bare.toJson().containsKey('cost_center_id'), isFalse);
    final JournalDraftLine placed = JournalDraftLine(
      ledgerAccountId: 'a-1',
      debit: '10',
      costCenterId: 'cc-1',
      profitCenterId: 'pc-1',
    );
    expect(placed.toJson()['cost_center_id'], 'cc-1');
    expect(placed.toJson()['profit_center_id'], 'pc-1');
  });
}
