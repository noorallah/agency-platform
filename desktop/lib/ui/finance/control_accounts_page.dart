import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/finance.dart';
import '../workspace/desktop_framework.dart';

/// Which ledger account each posting purpose lands in.
///
/// `firm_control_accounts` is what tells posting that Inventory is 1200 and
/// Trade Receivables is 1100. Opening the books maps all 24; until
/// 2026-09-08 changing one afterwards was an SQL statement, because the
/// mapping had no endpoint and no screen. A purpose with lines already posted
/// to its account is **held**: re-pointing it would leave two accounts each
/// holding part of one story, so the row shows the count and no picker.
class ControlAccountsPage extends StatefulWidget {
  const ControlAccountsPage({
    super.key,
    required this.api,
    required this.permissions,
    required this.hasActiveFirm,
  });

  final ApiClient api;
  final PermissionService permissions;
  final bool hasActiveFirm;

  @override
  State<ControlAccountsPage> createState() => _ControlAccountsPageState();
}

class _ControlAccountsPageState extends State<ControlAccountsPage> {
  List<ControlAccountMapping> _rows = const [];
  List<LedgerAccount> _accounts = const [];
  bool _loading = true;
  String? _error;

  /// The purpose whose picker is open, and the account chosen in it.
  String? _editing;
  String? _chosen;
  bool _saving = false;

  bool get _canManage => widget.permissions.hasPermission('ACCOUNT_MANAGE');

  @override
  void initState() {
    super.initState();
    if (widget.hasActiveFirm) _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final List<ControlAccountMapping> rows = await widget.api.controlAccounts();
      final List<LedgerAccount> accounts =
          (await widget.api.ledgerAccounts(isActive: true)).items;
      if (!mounted) return;
      setState(() {
        _rows = rows;
        _accounts = accounts;
        _loading = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = error.message;
      });
    }
  }

  Future<void> _save(ControlAccountMapping row) async {
    final String? accountId = _chosen;
    if (accountId == null) return;
    setState(() => _saving = true);
    try {
      final String message =
          await widget.api.assignControlAccount(row.purpose, accountId);
      if (!mounted) return;
      NotificationService.show(context, message,
          kind: AppNotificationKind.success);
      setState(() {
        _editing = null;
        _chosen = null;
      });
      await _load();
    } on ApiException catch (error) {
      if (!mounted) return;
      NotificationService.show(context, error.message,
          kind: AppNotificationKind.error);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  /// Accounts the purpose may post to, by classification. The server refuses
  /// the rest anyway; offering them would be offering a refusal.
  List<LedgerAccount> _candidates(ControlAccountMapping row) => _accounts
      .where((account) => row.expectedTypes.contains(account.accountType))
      .toList();

  Widget _accountCell(BuildContext context, ControlAccountMapping row) {
    final ThemeData theme = Theme.of(context);
    if (_editing == row.purpose) {
      final List<LedgerAccount> candidates = _candidates(row);
      return Row(
        children: [
          Expanded(
            child: DropdownButtonFormField<String>(
              isExpanded: true,
              key: ValueKey('control-account-${row.purpose}'),
              initialValue: _chosen,
              isDense: true,
              decoration: const InputDecoration(isDense: true),
              items: [
                for (final LedgerAccount account in candidates)
                  DropdownMenuItem(
                    value: account.id,
                    child: Text('${account.code} ${account.name}',
                        overflow: TextOverflow.ellipsis),
                  ),
              ],
              onChanged:
                  _saving ? null : (value) => setState(() => _chosen = value),
            ),
          ),
          const SizedBox(width: 8),
          FilledButton(
            onPressed: _saving || _chosen == null || _chosen == row.ledgerAccountId
                ? null
                : () => _save(row),
            child: const Text('Save'),
          ),
          TextButton(
            onPressed: _saving
                ? null
                : () => setState(() {
                      _editing = null;
                      _chosen = null;
                    }),
            child: const Text('Cancel'),
          ),
        ],
      );
    }
    final String label = row.isMapped
        ? '${row.accountCode} ${row.accountName}'
        : 'Not mapped';
    return Row(
      children: [
        Expanded(
          child: Text(
            label,
            style: row.isMapped
                ? null
                : theme.textTheme.bodyMedium
                    ?.copyWith(color: theme.colorScheme.error),
          ),
        ),
        if (row.isHeld)
          Tooltip(
            message: '${row.postedLines} posted line'
                '${row.postedLines == 1 ? '' : 's'} on this account. Re-pointing '
                'it would leave two accounts each holding part of one story; '
                'post a transfer entry and map a new account from the next '
                'period instead.',
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(Icons.lock_outline,
                    size: 16, color: theme.colorScheme.onSurfaceVariant),
                const SizedBox(width: 4),
                Text('${row.postedLines} posted',
                    style: theme.textTheme.labelSmall),
              ],
            ),
          )
        else if (_canManage)
          TextButton(
            key: ValueKey('control-account-edit-${row.purpose}'),
            onPressed: _saving
                ? null
                : () => setState(() {
                      _editing = row.purpose;
                      _chosen = row.ledgerAccountId;
                    }),
            child: Text(row.isMapped ? 'Change' : 'Map'),
          ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    if (!widget.hasActiveFirm) {
      return const StandardEmptyState(
        type: EmptyStateType.noFirmSelected,
        title: 'Select a firm',
        message: 'Control accounts belong to a firm. Choose one to see where '
            'its postings land.',
      );
    }
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_error != null) {
      return StandardEmptyState(
        type: EmptyStateType.noRecords,
        title: 'Could not load the mapping',
        message: _error!,
        action: FilledButton(onPressed: _load, child: const Text('Retry')),
      );
    }
    final int unmapped = _rows.where((row) => !row.isMapped).length;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
          child: Text(
            unmapped == 0
                ? 'Every posting purpose has an account. A purpose with lines '
                    'already posted to its account is held.'
                : '$unmapped of ${_rows.length} purposes have no account. A '
                    'document that reaches one is refused at approval.',
            style: theme.textTheme.bodySmall?.copyWith(
              color: unmapped == 0
                  ? theme.colorScheme.onSurfaceVariant
                  : theme.colorScheme.error,
            ),
          ),
        ),
        Expanded(
          child: SingleChildScrollView(
            padding: const EdgeInsets.fromLTRB(16, 4, 16, 16),
            child: Table(
              columnWidths: const {
                0: FlexColumnWidth(2.2),
                1: FlexColumnWidth(1.4),
                2: FlexColumnWidth(3),
              },
              defaultVerticalAlignment: TableCellVerticalAlignment.middle,
              children: [
                TableRow(
                  children: [
                    for (final String heading in [
                      'Purpose',
                      'Posts to',
                      'Account',
                    ])
                      Padding(
                        padding: const EdgeInsets.symmetric(vertical: 8),
                        child: Text(heading, style: theme.textTheme.labelLarge),
                      ),
                  ],
                ),
                for (final ControlAccountMapping row in _rows)
                  TableRow(
                    children: [
                      Padding(
                        padding: const EdgeInsets.symmetric(vertical: 6),
                        child: Text(row.label),
                      ),
                      Text(
                        row.expectedTypes.join(' or '),
                        style: theme.textTheme.bodySmall,
                      ),
                      Padding(
                        padding: const EdgeInsets.symmetric(vertical: 2),
                        child: _accountCell(context, row),
                      ),
                    ],
                  ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}
