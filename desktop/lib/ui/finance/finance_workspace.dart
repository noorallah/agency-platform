import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/preferences/desktop_preferences_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/finance.dart';
import '../resource_management_page.dart';
import '../workspace/desktop_framework.dart';
import '../workspace/module_catalog.dart';
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
        const FieldSpec(key: 'is_active', label: 'Active', boolean: true),
      ],
      initialValues: (account) => {
        'account_group_id': account?.accountGroupId ?? '',
        'code': account?.code ?? '',
        'name': account?.name ?? '',
        'account_type': account?.accountType ?? 'ASSET',
        'description': account?.description ?? '',
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

/// The accounting workspace: what the finance API has been recording all along.
///
/// The module rendered "Coming Soon" while thirty endpoints ran behind it and
/// every goods receipt, dispatch and invoice posted to the ledger. These two
/// tabs are the ones that make the rest legible -- the accounts postings land
/// in, and whether the result balances. Journal entries, receipts and payments
/// are still placeholders, and the catalog still says so.
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
