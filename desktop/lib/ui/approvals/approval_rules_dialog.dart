import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/approval.dart';
import '../../models/entities.dart';
import '../workspace/save_in_dialog.dart';

/// Who signs a document, and from what amount (PLT-1): up to three levels per
/// document type, each naming the roles that may sign it.
///
/// Reading needs approving rights; changing a type's chain needs
/// `SALES_MANAGE_SETTINGS` for sales documents and
/// `PURCHASE_MANAGE_SETTINGS` for purchase ones. Saving replaces the type's
/// whole chain. Several rows at one level are alternatives; level 2 needs a
/// level 1, and so on, which the server enforces and names when it refuses.
class ApprovalRulesDialog extends StatefulWidget {
  const ApprovalRulesDialog({
    super.key,
    required this.api,
    required this.permissions,
  });

  final ApiClient api;
  final PermissionService permissions;

  @override
  State<ApprovalRulesDialog> createState() => _ApprovalRulesDialogState();
}

class _RuleRow {
  _RuleRow(this.level, String amount, String role)
      : amount = TextEditingController(text: amount),
        role = TextEditingController(text: role);

  int level;
  final TextEditingController amount;
  final TextEditingController role;

  void dispose() {
    amount.dispose();
    role.dispose();
  }
}

class _ApprovalRulesDialogState extends State<ApprovalRulesDialog>
    with SaveInDialog<ApprovalRulesDialog> {
  final Map<String, List<_RuleRow>> _byType = <String, List<_RuleRow>>{
    for (final (String code, String _) in approvalDocumentTypes)
      code: <_RuleRow>[],
  };

  /// Role code to display name; empty when the caller may not list roles, in
  /// which case the code is typed.
  final Map<String, String> _roleNames = <String, String>{};
  String _type = approvalDocumentTypes.first.$1;
  bool _loading = true;
  String? _loadError;

  bool _mayManage(String type) => widget.permissions.hasPermission(
        type.startsWith('SALES_')
            ? 'SALES_MANAGE_SETTINGS'
            : 'PURCHASE_MANAGE_SETTINGS',
      );

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    for (final List<_RuleRow> rows in _byType.values) {
      for (final _RuleRow row in rows) {
        row.dispose();
      }
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
      final List<ApprovalRule> rules = await widget.api.approvalRules();
      if (!mounted) return;
      setState(() {
        for (final ApprovalRule rule in rules) {
          _byType[rule.documentType]?.add(
            _RuleRow(rule.level, rule.minAmount, rule.roleCode),
          );
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
        final List<Json> rules = <Json>[];
        for (final _RuleRow row in _byType[_type]!) {
          final String role = row.role.text.trim();
          final String amount = row.amount.text.trim();
          final double? value = double.tryParse(amount);
          if (role.isEmpty) {
            throw ApiException('Choose a role for every level.');
          }
          if (value == null || value < 0) {
            throw ApiException(
              'The amount for level ${row.level} must be zero or more.',
            );
          }
          rules.add(<String, dynamic>{
            'level': row.level,
            'min_amount': amount,
            'role_code': role,
          });
        }
        await widget.api.replaceApprovalRules(
          _type,
          <String, dynamic>{'rules': rules},
        );
        if (mounted) {
          NotificationService.show(
            context,
            '${approvalTypeLabel(_type)} approval levels saved.',
            kind: AppNotificationKind.success,
          );
        }
        return true;
      });

  Widget _roleField(int index, _RuleRow row, bool editable) {
    if (_roleNames.isEmpty) {
      return TextField(
        key: ValueKey('approval-rule-role-$index'),
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
      key: ValueKey('approval-rule-role-$index'),
      isExpanded: true,
      initialValue: current.isEmpty ? null : current,
      decoration: const InputDecoration(labelText: 'Role'),
      items: [
        for (final String code in codes)
          DropdownMenuItem(
            value: code,
            child: Text(_roleNames[code] ?? code,
                overflow: TextOverflow.ellipsis),
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
    final bool mayManage = _mayManage(_type);
    final bool editable = mayManage && !_loading && _loadError == null;
    final List<_RuleRow> rows = _byType[_type]!;
    return AlertDialog(
      scrollable: true,
      icon: const Icon(Icons.approval_outlined),
      title: const Text('Approval levels'),
      content: SizedBox(
        width: 620,
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
                    'Up to three sign-offs by amount. A document of at least '
                    'the amount on a level needs that level signed by a '
                    'person holding one of its roles; roles on the same '
                    'level are alternatives. Level 2 needs a level 1, and '
                    'level 3 a level 2. The last sign-off approves the '
                    'document. A type with no rows is approved in one step.',
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
                    DropdownButtonFormField<String>(
                      key: const ValueKey('approval-rule-type'),
                      initialValue: _type,
                      decoration:
                          const InputDecoration(labelText: 'Document'),
                      items: [
                        for (final (String code, String label)
                            in approvalDocumentTypes)
                          DropdownMenuItem(value: code, child: Text(label)),
                      ],
                      onChanged: saving
                          ? null
                          : (value) =>
                              setState(() => _type = value ?? _type),
                    ),
                    const SizedBox(height: AppSpacing.md),
                    saveErrorBanner(),
                    if (rows.isEmpty)
                      Text(
                        'No levels set. One approval is enough.',
                        key: const ValueKey('approval-rules-empty'),
                        style: theme.textTheme.bodySmall,
                      ),
                    for (int i = 0; i < rows.length; i++)
                      Padding(
                        key: ObjectKey(rows[i]),
                        padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                        child: Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            SizedBox(
                              width: 90,
                              child: DropdownButtonFormField<int>(
                                key: ValueKey('approval-rule-level-$i'),
                                initialValue: rows[i].level,
                                decoration: const InputDecoration(
                                    labelText: 'Level'),
                                items: const [
                                  DropdownMenuItem(value: 1, child: Text('1')),
                                  DropdownMenuItem(value: 2, child: Text('2')),
                                  DropdownMenuItem(value: 3, child: Text('3')),
                                ],
                                onChanged: editable && !saving
                                    ? (value) => setState(
                                        () => rows[i].level = value ?? 1)
                                    : null,
                              ),
                            ),
                            const SizedBox(width: AppSpacing.md),
                            SizedBox(
                              width: 140,
                              child: TextField(
                                key: ValueKey('approval-rule-amount-$i'),
                                controller: rows[i].amount,
                                enabled: editable && !saving,
                                keyboardType:
                                    const TextInputType.numberWithOptions(
                                  decimal: true,
                                ),
                                decoration: const InputDecoration(
                                    labelText: 'From amount'),
                              ),
                            ),
                            const SizedBox(width: AppSpacing.md),
                            Expanded(child: _roleField(i, rows[i], editable)),
                            IconButton(
                              key: ValueKey('approval-rule-remove-$i'),
                              tooltip: 'Remove',
                              icon: const Icon(Icons.close),
                              onPressed: editable && !saving
                                  ? () => setState(
                                      () => rows.removeAt(i).dispose())
                                  : null,
                            ),
                          ],
                        ),
                      ),
                    const SizedBox(height: AppSpacing.sm),
                    Align(
                      alignment: Alignment.centerLeft,
                      child: OutlinedButton.icon(
                        key: const ValueKey('approval-rule-add'),
                        icon: const Icon(Icons.add),
                        label: const Text('Add level'),
                        onPressed: editable && !saving
                            ? () => setState(() => rows.add(_RuleRow(
                                  rows.isEmpty
                                      ? 1
                                      : (rows.last.level < 3
                                          ? rows.last.level + 1
                                          : 3),
                                  '',
                                  '',
                                )))
                            : null,
                      ),
                    ),
                  ],
                  if (!mayManage) ...[
                    const SizedBox(height: AppSpacing.lg),
                    Text(
                      _type.startsWith('SALES_')
                          ? 'Changing sales approval levels needs the manage '
                              'sales settings permission.'
                          : 'Changing purchase approval levels needs the '
                              'manage purchase settings permission.',
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
          key: const ValueKey('approval-rules-save'),
          onPressed: editable && !saving ? _save : null,
          child: Text(saving ? 'Saving…' : 'Save'),
        ),
      ],
    );
  }
}
