import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/preferences/desktop_preferences_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/finance.dart';
import '../../models/settlement_direction.dart';
import '../resource_management_page.dart';
import '../workspace/desktop_framework.dart';
import '../workspace/module_catalog.dart';
import 'balance_sheet_page.dart';
import 'control_accounts_page.dart';
import 'journal_entries_page.dart';
import 'ledger_statement_page.dart';
import 'profit_loss_page.dart';
import 'settlements_page.dart';
import 'trial_balance_page.dart';

/// The chart of accounts, as a plain REST resource.
///
/// Account groups come from the catalogue rather than a text box: an account
/// must hang off a group, and typing a UUID is not a thing to ask of an
/// accountant.
ResourceDefinition<LedgerAccount> ledgerAccountDefinition(
  ApiClient api,
  PermissionService permissions, {
  bool showFrame = true,
}) =>
    ResourceDefinition<LedgerAccount>(
      title: 'Chart of Accounts',
      resource: 'finance/ledger-accounts',
      showFrame: showFrame,
      description: 'The accounts every posting lands in.',
      headers: const ['Code', 'Account', 'Type', 'Status'],
      sortFields: const ['code', 'name', 'account_type', null],
      cells: (account) => [
        account.code,
        account.name,
        account.accountType,
        account.isActive ? 'Active' : 'Inactive',
      ],
      id: (account) => account.id,
      load: ({
        int page = 1,
        String search = '',
        String sortBy = 'created_at',
        bool descending = true,
      }) =>
          api.ledgerAccounts(),
      searchHint: 'Search accounts by code or name',
      canUseAction: (action, _) => switch (action) {
        ToolbarAction.newItem ||
        ToolbarAction.edit =>
          permissions.hasPermission('ACCOUNT_MANAGE'),
        // The API has no delete for a ledger account, and it should not: an
        // account with postings against it cannot go without taking its
        // history with it. Deactivating is the way, which is the `is_active`
        // field on the form.
        ToolbarAction.delete => false,
        _ => permissions.hasPermission('ACCOUNT_VIEW'),
      },
      // PATCH, not PUT: the endpoint takes a partial update.
      partialUpdate: true,
      fields: [
        const FieldSpec(
          key: 'account_group_id',
          label: 'Account Group',
          requiredOnCreate: true,
          readOnlyWhenEditing: true,
          optionsResource: 'finance/account-groups',
          singleSelection: true,
        ),
        const FieldSpec(key: 'code', label: 'Code', requiredOnCreate: true),
        const FieldSpec(key: 'name', label: 'Name', required: true),
        const FieldSpec(
          key: 'account_type',
          label: 'Account Type',
          requiredOnCreate: true,
          readOnlyWhenEditing: true,
          choices: ['ASSET', 'LIABILITY', 'EQUITY', 'INCOME', 'EXPENSE'],
        ),
        const FieldSpec(key: 'description', label: 'Description', multiline: true),
        // A line on the account must name a centre; the engine refuses it
        // otherwise. Set here, offered on the journal line, satisfied on
        // Cost Centres / Profit Centres.
        const FieldSpec(
          key: 'requires_cost_center',
          label: 'Requires a cost centre',
          boolean: true,
        ),
        const FieldSpec(
          key: 'requires_profit_center',
          label: 'Requires a profit centre',
          boolean: true,
        ),
        const FieldSpec(key: 'is_active', label: 'Active', boolean: true),
      ],
      initialValues: (account) => {
        'account_group_id': account?.accountGroupId ?? '',
        'code': account?.code ?? '',
        'name': account?.name ?? '',
        'account_type': account?.accountType ?? 'ASSET',
        'description': account?.description ?? '',
        'requires_cost_center': account?.requiresCostCenter ?? false,
        'requires_profit_center': account?.requiresProfitCenter ?? false,
        'is_active': account?.isActive ?? true,
      },
      payload: (values, isCreating) => {
        if (isCreating)
          'account_group_id': values['account_group_id'].toString(),
        if (isCreating) 'code': values['code'],
        'name': values['name'],
        if (isCreating) 'account_type': values['account_type'],
        if ('${values['description'] ?? ''}'.isNotEmpty)
          'description': values['description'],
        'requires_cost_center': values['requires_cost_center'] ?? false,
        'requires_profit_center': values['requires_profit_center'] ?? false,
        'is_active': values['is_active'] ?? true,
      },
      details: (account) => [
        DetailLine('Code', account.code),
        DetailLine('Name', account.name),
        DetailLine('Type', account.accountType),
        DetailLine('Balance sheet', account.isBalanceSheet ? 'Yes' : 'No'),
        DetailLine('Profit and loss', account.isProfitLoss ? 'Yes' : 'No'),
        if (account.requiresCostCenter) const DetailLine('Cost centre', 'Required'),
        if (account.requiresProfitCenter)
          const DetailLine('Profit centre', 'Required'),
        DetailLine('Status', account.isActive ? 'Active' : 'Inactive'),
      ],
    );

/// A cost centre or a profit centre, as a plain REST resource.
///
/// One definition builder for both: the tables are the same shape and the
/// only differences are the noun and the route. `PATCH`, not `PUT`, because
/// the endpoints take a partial update; no delete, because a centre with
/// journal lines against it cannot go without taking history with it, and
/// the API offers none -- deactivating is the way.
ResourceDefinition<FinanceCentre> financeCentreDefinition(
  ApiClient api,
  PermissionService permissions, {
  required bool profit,
  bool showFrame = true,
}) {
  final String noun = profit ? 'Profit Centres' : 'Cost Centres';
  return ResourceDefinition<FinanceCentre>(
    title: noun,
    resource: profit ? 'finance/profit-centers' : 'finance/cost-centers',
    showFrame: showFrame,
    description: profit
        ? 'Where revenue is attributed. A journal line on an account that '
            'requires a profit centre is refused without one.'
        : 'Where cost is attributed. A journal line on an account that '
            'requires a cost centre is refused without one.',
    headers: const ['Code', 'Name', 'Description', 'Status'],
    sortFields: const ['code', 'name', null, null],
    cells: (centre) => [
      centre.code,
      centre.name,
      centre.description,
      centre.isActive ? 'Active' : 'Inactive',
    ],
    id: (centre) => centre.id,
    load: ({
      int page = 1,
      String search = '',
      String sortBy = 'created_at',
      bool descending = true,
    }) =>
        profit ? api.profitCenters() : api.costCenters(),
    searchHint: 'Search by code or name',
    canUseAction: (action, _) => switch (action) {
      ToolbarAction.newItem ||
      ToolbarAction.edit =>
        permissions.hasPermission('ACCOUNT_MANAGE'),
      ToolbarAction.delete => false,
      _ => permissions.hasPermission('ACCOUNT_VIEW'),
    },
    partialUpdate: true,
    fields: const [
      FieldSpec(
        key: 'code',
        label: 'Code',
        requiredOnCreate: true,
        readOnlyWhenEditing: true,
      ),
      FieldSpec(key: 'name', label: 'Name', required: true),
      FieldSpec(key: 'description', label: 'Description', multiline: true),
      FieldSpec(key: 'is_active', label: 'Active', boolean: true),
    ],
    initialValues: (centre) => {
      'code': centre?.code ?? '',
      'name': centre?.name ?? '',
      'description': centre?.description ?? '',
      'is_active': centre?.isActive ?? true,
    },
    payload: (values, isCreating) => {
      if (isCreating) 'code': values['code'],
      'name': values['name'],
      if ('${values['description'] ?? ''}'.isNotEmpty)
        'description': values['description'],
      'is_active': values['is_active'] ?? true,
    },
    details: (centre) => [
      DetailLine('Code', centre.code),
      DetailLine('Name', centre.name),
      DetailLine('Description', centre.description),
      DetailLine('Status', centre.isActive ? 'Active' : 'Inactive'),
    ],
  );
}

/// The accounting workspace: what the finance API has been recording all along.
///
/// The module rendered "Coming Soon" while thirty endpoints ran behind it and
/// every goods receipt, dispatch and invoice posted to the ledger. These tabs
/// are the ones that make the rest legible -- the accounts postings land in,
/// the postings themselves, one account's statement, and whether the result
/// balances. Receipts and payments have no endpoint at all and are still
/// placeholders.
class FinanceWorkspace extends StatefulWidget {
  const FinanceWorkspace({
    super.key,
    required this.api,
    required this.preferences,
    required this.permissions,
    required this.hasActiveFirm,
    required this.tabId,
  });

  final ApiClient api;
  final DesktopPreferencesService preferences;
  final PermissionService permissions;
  final bool hasActiveFirm;
  final String tabId;

  @override
  State<FinanceWorkspace> createState() => _FinanceWorkspaceState();
}

class _FinanceWorkspaceState extends State<FinanceWorkspace> {
  @override
  Widget build(BuildContext context) => ModuleWorkspaceFrame(
        title: ModuleCatalog.byId(AppModule.accounting).label,
        description: 'Accounts, and whether the books balance.',
        breadcrumbs: const ['Workspace', 'Finance'],
        child: switch (widget.tabId) {
          'cost-centers' => ResourceManagementPage<FinanceCentre>(
              api: widget.api,
              definition: financeCentreDefinition(
                widget.api,
                widget.permissions,
                profit: false,
                showFrame: false,
              ),
            ),
          'profit-centers' => ResourceManagementPage<FinanceCentre>(
              api: widget.api,
              definition: financeCentreDefinition(
                widget.api,
                widget.permissions,
                profit: true,
                showFrame: false,
              ),
            ),
          'control-accounts' => ControlAccountsPage(
              api: widget.api,
              permissions: widget.permissions,
              hasActiveFirm: widget.hasActiveFirm,
            ),
          'journal-entries' => JournalEntriesPage(
              api: widget.api,
              permissions: widget.permissions,
              hasActiveFirm: widget.hasActiveFirm,
            ),
          'ledgers' => LedgerStatementPage(
              api: widget.api,
              permissions: widget.permissions,
              hasActiveFirm: widget.hasActiveFirm,
            ),
          'receipts' => SettlementsPage(
              api: widget.api,
              permissions: widget.permissions,
              hasActiveFirm: widget.hasActiveFirm,
              direction: SettlementDirection.receipt,
            ),
          'payments' => SettlementsPage(
              api: widget.api,
              permissions: widget.permissions,
              hasActiveFirm: widget.hasActiveFirm,
              direction: SettlementDirection.payment,
            ),
          'refunds' => SettlementsPage(
              api: widget.api,
              permissions: widget.permissions,
              hasActiveFirm: widget.hasActiveFirm,
              direction: SettlementDirection.refund,
            ),
          'balance-sheet' => BalanceSheetPage(
              api: widget.api,
              permissions: widget.permissions,
              hasActiveFirm: widget.hasActiveFirm,
            ),
          'profit-loss' => ProfitLossPage(
              api: widget.api,
              permissions: widget.permissions,
              hasActiveFirm: widget.hasActiveFirm,
            ),
          'trial-balance' => TrialBalancePage(
              api: widget.api,
              permissions: widget.permissions,
              hasActiveFirm: widget.hasActiveFirm,
            ),
          _ => ResourceManagementPage<LedgerAccount>(
              api: widget.api,
              definition: ledgerAccountDefinition(
                widget.api,
                widget.permissions,
                showFrame: false,
              ),
            ),
        },
      );
}
