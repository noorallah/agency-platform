import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/entities.dart';
import '../../models/price_floor.dart';
import '../workspace/save_in_dialog.dart';

/// The most each role may discount by hand (backlog 64 row 3).
///
/// Reading needs only `SALES_VIEW`; changing the list needs
/// `SALES_MANAGE_SETTINGS`, which sales roles do not hold -- the limits exist
/// to constrain them. Saving replaces the whole list.
class DiscountLimitsDialog extends StatefulWidget {
  const DiscountLimitsDialog({
    super.key,
    required this.api,
    required this.permissions,
  });

  final ApiClient api;
  final PermissionService permissions;

  @override
  State<DiscountLimitsDialog> createState() => _DiscountLimitsDialogState();
}

class _LimitRow {
  _LimitRow(String role, String percent)
      : role = TextEditingController(text: role),
        percent = TextEditingController(text: percent);

  final TextEditingController role;
  final TextEditingController percent;
}

class _DiscountLimitsDialogState extends State<DiscountLimitsDialog>
    with SaveInDialog<DiscountLimitsDialog> {
  final List<_LimitRow> _rows = <_LimitRow>[];

  /// Role code to display name; empty when the caller may not list roles, in
  /// which case the code is typed.
  final Map<String, String> _roleNames = <String, String>{};
  bool _loading = true;
  String? _loadError;

  bool get _mayManage =>
      widget.permissions.hasPermission('SALES_MANAGE_SETTINGS');

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    for (final _LimitRow row in _rows) {
      row.role.dispose();
      row.percent.dispose();
    }
    super.dispose();
  }

  Future<void> _load() async {
    // Role names are a convenience: a sales manager may not hold the right to
    // list roles, and then the code is typed instead.
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
      final List<RoleDiscountLimit> limits = await widget.api.discountLimits();
      if (!mounted) return;
      setState(() {
        for (final RoleDiscountLimit limit in limits) {
          _rows.add(_LimitRow(limit.roleCode, limit.maxDiscountPercent));
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
        final List<RoleDiscountLimit> limits = <RoleDiscountLimit>[];
        for (final _LimitRow row in _rows) {
          final String role = row.role.text.trim();
          final String percent = row.percent.text.trim();
          final double? value = double.tryParse(percent);
          if (role.isEmpty) {
            throw ApiException('Choose a role for every limit.');
          }
          if (value == null || value < 0 || value > 100) {
            throw ApiException(
              'The limit for $role must be a percent from 0 to 100.',
            );
          }
          limits.add(
            RoleDiscountLimit(roleCode: role, maxDiscountPercent: percent),
          );
        }
        await widget.api.updateDiscountLimits(limits);
        if (mounted) {
          // Announce before the pop: the notification reads the theme off
          // this context.
          NotificationService.show(
            context,
            'Discount limits saved.',
            kind: AppNotificationKind.success,
          );
        }
        return true;
      });

  Widget _roleField(int index, bool editable) {
    final _LimitRow row = _rows[index];
    if (_roleNames.isEmpty) {
      return TextField(
        key: ValueKey('discount-limit-role-$index'),
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
      key: ValueKey('discount-limit-role-$index'),
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
      icon: const Icon(Icons.percent_outlined),
      title: const Text('Discount limits'),
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
                    "A person's limit is the largest among their roles that "
                    'have a row here. Nobody is limited until a row exists. '
                    'Only a discount typed by hand counts, not one that came '
                    "from a price list, a promotion or the customer's rate. "
                    'Above the limit the order or bill still saves, but '
                    'approving it is refused until someone with a higher '
                    'limit approves; the timeline records who.',
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
                        key: const ValueKey('discount-limits-empty'),
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
                              width: 130,
                              child: TextField(
                                key: ValueKey('discount-limit-percent-$i'),
                                controller: _rows[i].percent,
                                enabled: editable && !saving,
                                keyboardType:
                                    const TextInputType.numberWithOptions(
                                  decimal: true,
                                ),
                                decoration: const InputDecoration(
                                  labelText: 'Max discount',
                                  suffixText: '%',
                                ),
                              ),
                            ),
                            IconButton(
                              key: ValueKey('discount-limit-remove-$i'),
                              tooltip: 'Remove',
                              icon: const Icon(Icons.close),
                              onPressed: editable && !saving
                                  ? () => setState(() {
                                        final _LimitRow gone =
                                            _rows.removeAt(i);
                                        gone.role.dispose();
                                        gone.percent.dispose();
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
                        key: const ValueKey('discount-limit-add'),
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
                      'Changing discount limits needs the manage sales '
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
          key: const ValueKey('discount-limits-save'),
          onPressed: editable && !saving ? _save : null,
          child: Text(saving ? 'Saving…' : 'Save'),
        ),
      ],
    );
  }
}
