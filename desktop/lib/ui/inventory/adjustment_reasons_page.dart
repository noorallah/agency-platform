import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/security/permission_service.dart';
import '../../models/adjustment_reason.dart';
import '../../models/entities.dart';
import '../../models/finance.dart';
import '../resource_management_page.dart';
import '../workspace/desktop_framework.dart';

/// The reasons a firm gives for writing stock off (STK-7), each with the
/// ledger account its value is booked to.
///
/// Expressed as a `ResourceDefinition`: a flat list with a short form. The
/// ledger account is a dropdown whose choices are the account ids, labelled
/// "code - name", so the definition can stay a plain value.
ResourceDefinition<AdjustmentReasonRecord> adjustmentReasonDefinition(
  ApiClient api,
  PermissionService permissions,
  List<LedgerAccount> accounts, {
  bool showFrame = true,
}) {
  final Map<String, String> accountLabels = {
    for (final LedgerAccount account in accounts)
      account.id: '${account.code} - ${account.name}',
  };
  return ResourceDefinition<AdjustmentReasonRecord>(
    title: 'Adjustment Reasons',
    // Builds `/api/v1/inventory/adjustment-reasons[/{id}]` through the
    // generic helpers.
    resource: 'inventory/adjustment-reasons',
    showFrame: showFrame,
    description: 'Why stock leaves the books, and where the value goes.',
    searchHint: 'Search reasons by code or name',
    headers: const ['Code', 'Name', 'Ledger account', 'System', 'Status'],
    cells: (reason) => [
      reason.code,
      reason.name,
      reason.ledgerAccountName.isEmpty
          ? 'Default adjustment account'
          : reason.ledgerAccountName,
      reason.isSystem ? 'Yes' : '',
      reason.isActive ? 'Active' : 'Inactive',
    ],
    id: (reason) => reason.id,
    load: ({
      int page = 1,
      String search = '',
      String sortBy = 'created_at',
      bool descending = true,
    }) async {
      // A plain list; filtered here so no `search` is sent that the server
      // would ignore.
      final List<AdjustmentReasonRecord> all = await api.adjustmentReasons();
      final String term = search.trim().toLowerCase();
      final List<AdjustmentReasonRecord> matching = term.isEmpty
          ? all
          : all
              .where((reason) =>
                  reason.code.toLowerCase().contains(term) ||
                  reason.name.toLowerCase().contains(term))
              .toList();
      return PagedResult<AdjustmentReasonRecord>(
        items: matching,
        total: matching.length,
      );
    },
    canUseAction: (action, selected) {
      final bool canManage =
          permissions.hasPermission('INVENTORY_MANAGE_REASONS');
      return switch (action) {
        ToolbarAction.newItem || ToolbarAction.edit => canManage,
        // The server refuses a system reason too; not offering it says so
        // before the round trip.
        ToolbarAction.delete => canManage && !(selected?.isSystem ?? false),
        _ => true,
      };
    },
    fields: [
      const FieldSpec(
        key: 'code',
        label: 'Code',
        requiredOnCreate: true,
        // A reason's code is what documents carry, so it is fixed once saved.
        readOnlyWhenEditing: true,
        helperText: 'Letters, digits, _ and - only. Stored in upper case.',
      ),
      const FieldSpec(key: 'name', label: 'Name', requiredOnCreate: true),
      FieldSpec(
        key: 'ledger_account_id',
        label: 'Ledger account',
        choices: ['', ...accountLabels.keys],
        choiceLabels: {'': 'Default adjustment account', ...accountLabels},
        helperText: 'Where the value is booked when stock is written off '
            'under this reason.',
      ),
      const FieldSpec(
        key: 'is_active',
        label: 'Active',
        boolean: true,
        helperText: 'An inactive reason is no longer offered on a write-off.',
      ),
    ],
    initialValues: (reason) => <String, dynamic>{
      'code': reason?.code ?? '',
      'name': reason?.name ?? '',
      'ledger_account_id': reason?.ledgerAccountId ?? '',
      'is_active': reason?.isActive ?? true,
    },
    payload: (values, isCreating) {
      final String account =
          (values['ledger_account_id'] as String? ?? '').trim();
      return <String, dynamic>{
        'code': (values['code'] as String? ?? '').trim().toUpperCase(),
        'name': (values['name'] as String? ?? '').trim(),
        // Null clears the account, which is what "Default" means.
        'ledger_account_id': account.isEmpty ? null : account,
        'is_active': values['is_active'] == true,
      };
    },
  );
}

/// The Adjustment Reasons tab.
class AdjustmentReasonsPage extends StatefulWidget {
  const AdjustmentReasonsPage({
    super.key,
    required this.api,
    required this.permissions,
  });

  final ApiClient api;
  final PermissionService permissions;

  @override
  State<AdjustmentReasonsPage> createState() => _AdjustmentReasonsPageState();
}

class _AdjustmentReasonsPageState extends State<AdjustmentReasonsPage> {
  List<LedgerAccount>? _accounts;

  @override
  void initState() {
    super.initState();
    _loadAccounts();
  }

  /// The accounts a reason can point at. A read that fails leaves the list
  /// empty, so the reasons still show and "Default" stays choosable.
  Future<void> _loadAccounts() async {
    List<LedgerAccount> accounts = const [];
    try {
      accounts = (await widget.api.ledgerAccounts()).items;
    } on ApiException {
      accounts = const [];
    }
    if (!mounted) return;
    setState(() => _accounts = accounts);
  }

  @override
  Widget build(BuildContext context) {
    final List<LedgerAccount>? accounts = _accounts;
    if (accounts == null) {
      return const Center(child: CircularProgressIndicator());
    }
    return ResourceManagementPage<AdjustmentReasonRecord>(
      api: widget.api,
      definition: adjustmentReasonDefinition(
        widget.api,
        widget.permissions,
        accounts,
        showFrame: false,
      ),
    );
  }
}
