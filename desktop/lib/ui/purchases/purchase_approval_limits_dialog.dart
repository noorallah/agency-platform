import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/entities.dart';
import '../../models/purchase.dart';
import '../workspace/save_in_dialog.dart';

/// The largest purchase order each role may approve (backlog 68 row 4).
///
/// Reading needs only `PURCHASE_VIEW`; changing the list needs
/// `PURCHASE_MANAGE_SETTINGS`, which the purchase manager does not hold -- the
/// limits exist to constrain the people who approve. Saving replaces the
/// whole list. The same shape as the discount limits under Selling.
class PurchaseApprovalLimitsDialog extends StatefulWidget {
  const PurchaseApprovalLimitsDialog({
    super.key,
    required this.api,
    required this.permissions,
  });

  final ApiClient api;
  final PermissionService permissions;

  @override
  State<PurchaseApprovalLimitsDialog> createState() =>
      _PurchaseApprovalLimitsDialogState();
}

class _LimitRow {
  _LimitRow(String role, String amount)
      : role = TextEditingController(text: role),
        amount = TextEditingController(text: amount);

  final TextEditingController role;
  final TextEditingController amount;
}

class _PurchaseApprovalLimitsDialogState
    extends State<PurchaseApprovalLimitsDialog>
    with SaveInDialog<PurchaseApprovalLimitsDialog> {
  final List<_LimitRow> _rows = <_LimitRow>[];

  /// Role code to display name; empty when the caller may not list roles, in
  /// which case the code is typed.
  final Map<String, String> _roleNames = <String, String>{};
  bool _loading = true;
  String? _loadError;

  bool get _mayManage =>
      widget.permissions.hasPermission('PURCHASE_MANAGE_SETTINGS');

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    for (final _LimitRow row in _rows) {
      row.role.dispose();
      row.amount.dispose();
    }
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final PagedResult<Role> roles = await widget.api.roles(
        pageSize: 100,
        sortBy: 'name',
        descending: false,
      );
      for (final Role role in roles.items) {
        if (role.isActive) _roleNames[role.code] = role.name;
      }
    } on ApiException {
      // Fall back to typing the code.
    }
    try {
      final List<RolePurchaseApprovalLimit> limits =
          await widget.api.purchaseApprovalLimits();
      if (!mounted) return;
      setState(() {
        for (final RolePurchaseApprovalLimit limit in limits) {
          _rows.add(_LimitRow(limit.roleCode, limit.maxOrderAmount));
        }
        _loading = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _loadError = error.message;
        _loading = false;
      });
    }
  }

  Future<void> _save() => saveAndClose<bool>(() async {
        final List<RolePurchaseApprovalLimit> limits =
            <RolePurchaseApprovalLimit>[];
        for (final _LimitRow row in _rows) {
          final String role = row.role.text.trim();
          final String amount = row.amount.text.trim();
          final double? value = double.tryParse(amount);
          if (role.isEmpty) {
            throw ApiException('Choose a role for every limit.');
          }
          if (value == null || value < 0) {
            throw ApiException(
              'The limit for $role must be an amount of zero or more.',
            );
          }
          limits.add(
            RolePurchaseApprovalLimit(roleCode: role, maxOrderAmount: amount),
          );
        }
        await widget.api.updatePurchaseApprovalLimits(limits);
        if (mounted) {
          NotificationService.show(
            context,
            'Approval limits saved.',
            kind: AppNotificationKind.success,
          );
        }
        return true;
      });

  Widget _roleField(int index, bool editable) {
    final _LimitRow row = _rows[index];
    if (_roleNames.isEmpty) {
      return TextField(
        key: ValueKey('approval-limit-role-$index'),
        controller: row.role,
        enabled: editable && !saving,
        decoration: const InputDecoration(labelText: 'Role code'),
      );
    }
    final String current = row.role.text;
    final Set<String> codes = <String>{
      ..._roleNames.keys,
      if (current.isNotEmpty) current,
    };
    return DropdownButtonFormField<String>(
      key: ValueKey('approval-limit-role-$index'),
      isExpanded: true,
      initialValue: current.isEmpty ? null : current,
      decoration: const InputDecoration(labelText: 'Role'),
      items: [
        for (final String code in codes)
          DropdownMenuItem(
            value: code,
            child: Text(
              _roleNames[code] ?? code,
              overflow: TextOverflow.ellipsis,
            ),
          ),
      ],
      onChanged: editable && !saving
          ? (value) => setState(() => row.role.text = value ?? '')
          : null,
    );
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final bool editable = _mayManage && !_loading && _loadError == null;
    return AlertDialog(
      scrollable: true,
      icon: const Icon(Icons.approval_outlined),
      title: const Text('Purchase approval limits'),
      content: SizedBox(
        width: 520,
        child: _loading
            ? const Padding(
                padding: EdgeInsets.all(AppSpacing.xl),
                child: Center(child: CircularProgressIndicator()),
              )
            : Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(
                    'The largest purchase order each role may approve, '
                    'judged on the order total including tax. A person\'s '
                    'limit is the largest among their roles that have a row '
                    'here; nobody is limited until a row exists. Above the '
                    'limit the order stays submitted and approving it is '
                    'refused until someone with a higher limit approves; the '
                    'timeline records who, with both amounts.',
                    style: theme.textTheme.bodySmall,
                  ),
                  const SizedBox(height: AppSpacing.lg),
                  if (_loadError != null)
                    Text(
                      _loadError!,
                      style: theme.textTheme.bodySmall
                          ?.copyWith(color: theme.colorScheme.error),
                    )
                  else ...[
                    saveErrorBanner(),
                    if (_rows.isEmpty)
                      Text(
                        'No limits set. Nobody is limited.',
                        key: const ValueKey('approval-limits-empty'),
                        style: theme.textTheme.bodySmall,
                      ),
                    for (int i = 0; i < _rows.length; i++)
                      Padding(
                        key: ObjectKey(_rows[i]),
                        padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                        child: Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Expanded(child: _roleField(i, editable)),
                            const SizedBox(width: AppSpacing.md),
                            SizedBox(
                              width: 160,
                              child: TextField(
                                key: ValueKey('approval-limit-amount-$i'),
                                controller: _rows[i].amount,
                                enabled: editable && !saving,
                                keyboardType:
                                    const TextInputType.numberWithOptions(
                                  decimal: true,
                                ),
                                decoration: const InputDecoration(
                                  labelText: 'Max order total',
                                ),
                              ),
                            ),
                            IconButton(
                              key: ValueKey('approval-limit-remove-$i'),
                              tooltip: 'Remove',
                              icon: const Icon(Icons.close),
                              onPressed: editable && !saving
                                  ? () => setState(() {
                                        final _LimitRow gone =
                                            _rows.removeAt(i);
                                        gone.role.dispose();
                                        gone.amount.dispose();
                                      })
                                  : null,
                            ),
                          ],
                        ),
                      ),
                    const SizedBox(height: AppSpacing.sm),
                    Align(
                      alignment: Alignment.centerLeft,
                      child: OutlinedButton.icon(
                        key: const ValueKey('approval-limit-add'),
                        icon: const Icon(Icons.add),
                        label: const Text('Add role'),
                        onPressed: editable && !saving
                            ? () => setState(() => _rows.add(_LimitRow('', '')))
                            : null,
                      ),
                    ),
                  ],
                  if (!_mayManage) ...[
                    const SizedBox(height: AppSpacing.lg),
                    Text(
                      'Changing approval limits needs the manage purchase '
                      'settings permission.',
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                    ),
                  ],
                ],
              ),
      ),
      actions: [
        TextButton(
          onPressed: saving ? null : () => Navigator.of(context).pop(false),
          child: const Text('Close'),
        ),
        FilledButton(
          key: const ValueKey('approval-limits-save'),
          onPressed: editable && !saving ? _save : null,
          child: Text(saving ? 'Saving…' : 'Save'),
        ),
      ],
    );
  }
}
