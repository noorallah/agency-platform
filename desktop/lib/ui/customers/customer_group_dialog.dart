import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/customer.dart';
import '../../models/entities.dart';

/// The segments a firm sells to, and what each is normally given.
///
/// Not the same question as a customer's *type*, which is INDIVIDUAL or
/// BUSINESS — a legal classification, and the wrong thing to hang a price on.
/// This is the firm's own grouping: Retailer, Wholesaler, Institution.
///
/// A segment's rate is the **last** thing consulted when a line is priced. A
/// rate agreed with one shop is more specific than one agreed with a whole
/// segment of them, so the customer's own standing rate wins.
class CustomerGroupDialog extends StatefulWidget {
  const CustomerGroupDialog({
    super.key,
    required this.api,
    required this.permissions,
  });

  final ApiClient api;
  final PermissionService permissions;

  @override
  State<CustomerGroupDialog> createState() => _CustomerGroupDialogState();
}

class _CustomerGroupDialogState extends State<CustomerGroupDialog> {
  List<CustomerGroup> _groups = const [];
  bool _loading = true;
  bool _saving = false;
  String? _error;

  final TextEditingController _code = TextEditingController();
  final TextEditingController _name = TextEditingController();
  final TextEditingController _rate = TextEditingController();
  String? _editingId;
  int _editingVersion = 0;

  bool get _mayManage =>
      widget.permissions.hasPermission('CUSTOMER_MANAGE_SETTINGS');

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _code.dispose();
    _name.dispose();
    _rate.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final PagedResult<CustomerGroup> result =
          await widget.api.customerGroups();
      if (!mounted) return;
      setState(() {
        _groups = result.items;
        _loading = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.message;
        _loading = false;
      });
    }
  }

  void _edit(CustomerGroup group) {
    setState(() {
      _editingId = group.id;
      _editingVersion = group.version;
      _code.text = group.code;
      _name.text = group.name;
      _rate.text = _trim(group.defaultDiscountPercent);
      _error = null;
    });
  }

  void _clear() {
    setState(() {
      _editingId = null;
      _editingVersion = 0;
      _code.clear();
      _name.clear();
      _rate.clear();
      _error = null;
    });
  }

  /// Render `5.0000` as `5` — the server stores a scale nobody types.
  static String _trim(String value) {
    if (!value.contains('.')) return value;
    final String trimmed =
        value.replaceAll(RegExp(r'0+$'), '').replaceAll(RegExp(r'\.$'), '');
    return trimmed.isEmpty ? '0' : trimmed;
  }

  Future<void> _save() async {
    if (_code.text.trim().isEmpty || _name.text.trim().isEmpty) {
      setState(() => _error = 'A group needs a code and a name.');
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    final Json body = <String, dynamic>{
      'code': _code.text.trim().toUpperCase(),
      'name': _name.text.trim(),
      'default_discount_percent':
          _rate.text.trim().isEmpty ? '0' : _rate.text.trim(),
      'is_active': true,
    };
    try {
      final String? id = _editingId;
      if (id == null) {
        await widget.api.createCustomerGroup(body);
      } else {
        await widget.api.updateCustomerGroup(
          id,
          body,
          expectedVersion: _editingVersion,
        );
      }
      if (!mounted) return;
      _clear();
      await _load();
      if (!mounted) return;
      setState(() => _saving = false);
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        // The dialog stays open, so the typing survives the refusal.
        _error = error.message;
        _saving = false;
      });
    }
  }

  Future<void> _delete(CustomerGroup group) async {
    try {
      await widget.api.deleteCustomerGroup(group.id);
      if (!mounted) return;
      await _load();
    } on ApiException catch (error) {
      if (!mounted) return;
      // The server refuses a group somebody is still in, and says how many.
      NotificationService.show(
        context,
        error.message,
        kind: AppNotificationKind.error,
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return AlertDialog(
      icon: const Icon(Icons.groups_outlined),
      title: const Text('Customer groups'),
      content: SizedBox(
        width: 560,
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
                    'How this firm segments the shops it sells to — not the '
                    'same thing as a customer’s legal type. A group’s rate is '
                    'the last one consulted: whatever the shop itself is on '
                    'wins.',
                    style: theme.textTheme.bodySmall,
                  ),
                  const SizedBox(height: AppSpacing.lg),
                  if (_groups.isEmpty)
                    Padding(
                      padding: const EdgeInsets.only(bottom: AppSpacing.md),
                      child: Text(
                        'No groups yet. Without one, a customer is priced by '
                        'their own rate and the price lists alone.',
                        style: theme.textTheme.bodySmall,
                      ),
                    ),
                  for (final CustomerGroup group in _groups)
                    ListTile(
                      contentPadding: EdgeInsets.zero,
                      dense: true,
                      title: Text('${group.code} · ${group.name}'),
                      subtitle: Text(
                        _trim(group.defaultDiscountPercent) == '0'
                            ? 'No standing rate'
                            : '${_trim(group.defaultDiscountPercent)}% off',
                        style: theme.textTheme.bodySmall,
                      ),
                      trailing: !_mayManage
                          ? null
                          : Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                IconButton(
                                  tooltip: 'Edit',
                                  icon: const Icon(Icons.edit_outlined, size: 18),
                                  onPressed: () => _edit(group),
                                ),
                                IconButton(
                                  tooltip: 'Remove',
                                  icon: const Icon(Icons.close, size: 18),
                                  onPressed: () => _delete(group),
                                ),
                              ],
                            ),
                    ),
                  if (_mayManage) ...[
                    const Divider(),
                    Row(
                      children: [
                        Expanded(
                          child: TextField(
                            controller: _code,
                            enabled: !_saving,
                            decoration: const InputDecoration(labelText: 'Code'),
                            textCapitalization: TextCapitalization.characters,
                          ),
                        ),
                        const SizedBox(width: AppSpacing.md),
                        Expanded(
                          flex: 2,
                          child: TextField(
                            controller: _name,
                            enabled: !_saving,
                            decoration: const InputDecoration(labelText: 'Name'),
                          ),
                        ),
                        const SizedBox(width: AppSpacing.md),
                        Expanded(
                          child: TextField(
                            controller: _rate,
                            enabled: !_saving,
                            decoration: const InputDecoration(
                              labelText: 'Rate',
                              suffixText: '%',
                              helperText: 'Blank is none',
                            ),
                            keyboardType: TextInputType.number,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: AppSpacing.md),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.end,
                      children: [
                        if (_editingId != null)
                          TextButton(
                            onPressed: _saving ? null : _clear,
                            child: const Text('Cancel edit'),
                          ),
                        const SizedBox(width: AppSpacing.sm),
                        FilledButton(
                          onPressed: _saving ? null : _save,
                          child: Text(
                            _editingId == null ? 'Add group' : 'Save group',
                          ),
                        ),
                      ],
                    ),
                  ],
                  if (_error != null) ...[
                    const SizedBox(height: AppSpacing.md),
                    Text(
                      _error!,
                      style: theme.textTheme.bodySmall
                          ?.copyWith(color: theme.colorScheme.error),
                    ),
                  ],
                ],
              ),
      ),
      actions: [
        TextButton(
          onPressed: _saving ? null : () => Navigator.of(context).pop(true),
          child: const Text('Close'),
        ),
      ],
    );
  }
}
