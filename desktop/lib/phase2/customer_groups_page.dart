import 'dart:async';

import 'package:flutter/material.dart';

import '../core/api/api_client.dart';
import '../core/api/concurrency.dart';
import '../core/design/design_tokens.dart';
import '../core/dialogs/app_dialogs.dart';
import '../core/notifications/notification_service.dart';
import '../core/security/permission_service.dart';
import '../models/customer.dart';
import '../models/entities.dart';
import '../ui/workspace/desktop_framework.dart';

/// Masters > Parties > Customer Groups in the phase 2 app: a list screen like
/// every other -- the page line, a grid, "+ New" -- rather than the phase 1
/// dialog stretched into a page (owner, 2026-09-26).
///
/// A group is how the firm segments the shops it sells to, and its rate is
/// the last one consulted when a line is priced: whatever the shop itself is
/// on wins. The same four calls the phase 1 dialog makes, the same body, the
/// same version check on update.
class CustomerGroupsPage extends StatefulWidget {
  const CustomerGroupsPage({
    super.key,
    required this.api,
    required this.permissions,
  });

  final ApiClient api;
  final PermissionService permissions;

  @override
  State<CustomerGroupsPage> createState() => _CustomerGroupsPageState();
}

class _CustomerGroupsPageState extends State<CustomerGroupsPage> {
  final TextEditingController _search = TextEditingController();
  List<CustomerGroup> _groups = const [];
  bool _loading = true;
  String? _error;
  String? _selectedId;

  bool get _mayManage =>
      widget.permissions.hasPermission('CUSTOMER_MANAGE_SETTINGS');

  CustomerGroup? get _selected =>
      _groups.where((group) => group.id == _selectedId).firstOrNull;

  /// The groups the search matches, by code or name.
  List<CustomerGroup> get _shown {
    final String q = _search.text.trim().toLowerCase();
    if (q.isEmpty) return _groups;
    return [
      for (final CustomerGroup group in _groups)
        if (group.code.toLowerCase().contains(q) ||
            group.name.toLowerCase().contains(q))
          group,
    ];
  }

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final PagedResult<CustomerGroup> result =
          await widget.api.customerGroups();
      if (!mounted) return;
      setState(() {
        _groups = result.items;
        _loading = false;
        if (_selected == null) _selectedId = null;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.message;
        _loading = false;
      });
    }
  }

  Future<void> _edit([CustomerGroup? group]) async {
    if (!_mayManage) return;
    final bool? saved = await showDialog<bool>(
      context: context,
      builder: (_) => _GroupEditor(api: widget.api, group: group),
    );
    if (saved == true) await _load();
  }

  Future<void> _delete(CustomerGroup group) async {
    if (!_mayManage) return;
    final bool sure = await AppDialogs.confirm(
      context,
      title: 'Remove ${group.name}?',
      message: 'Customers in this group keep their own rates; the group\'s '
          'rate stops applying to them. A group somebody is still in cannot '
          'be removed.',
      confirmLabel: 'Remove',
    );
    if (!sure || !mounted) return;
    try {
      await widget.api.deleteCustomerGroup(group.id);
      if (!mounted) return;
      setState(() => _selectedId = null);
      await _load();
    } on ApiException catch (error) {
      if (!mounted) return;
      // The server refuses a group somebody is still in, and says how many.
      NotificationService.show(context, error.message,
          kind: AppNotificationKind.error);
    }
  }

  static String _rate(String value) {
    if (!value.contains('.')) return value;
    final String trimmed =
        value.replaceAll(RegExp(r'0+$'), '').replaceAll(RegExp(r'\.$'), '');
    return trimmed.isEmpty ? '0' : trimmed;
  }

  @override
  Widget build(BuildContext context) {
    final List<CustomerGroup> shown = _shown;
    final CustomerGroup? selected = _selected;
    final int withRate =
        _groups.where((group) => _rate(group.defaultDiscountPercent) != '0').length;
    final Widget grid = _error != null
        ? WorkspaceEmptyState(title: 'Groups could not be read', message: _error!)
        : !_loading && _groups.isEmpty
            ? const WorkspaceEmptyState(
                title: 'No groups yet',
                message: 'Without one, a customer is priced by their own rate '
                    'and the price lists alone.',
              )
            : EnterpriseDataGrid<CustomerGroup>(
                items: shown,
                total: shown.length,
                pageOffset: 0,
                rowsPerPage: shown.isEmpty ? 1 : shown.length,
                columns: const [
                  GridColumn(key: 'code', label: 'Code'),
                  GridColumn(key: 'name', label: 'Name'),
                  GridColumn(key: 'rate', label: 'Rate %', numeric: true),
                  GridColumn(key: 'status', label: 'Status'),
                ],
                id: (group) => group.id,
                cells: (group) => [
                  group.code,
                  group.name,
                  _rate(group.defaultDiscountPercent),
                  group.isActive ? 'Active' : 'Inactive',
                ],
                selectedId: _selectedId,
                onSelect: (group) => setState(() => _selectedId = group.id),
                onOpen: _mayManage ? _edit : null,
                contextActions: [
                  if (_mayManage) WorkspaceContextAction.edit,
                  if (_mayManage) WorkspaceContextAction.delete,
                  WorkspaceContextAction.refresh,
                ],
                onContextAction: (action, group) => switch (action) {
                  WorkspaceContextAction.edit => unawaited(_edit(group)),
                  WorkspaceContextAction.delete => unawaited(_delete(group)),
                  _ => unawaited(_load()),
                },
                onPageChanged: (_) {},
              );
    return phase2Frame(
      title: 'Customer Groups',
      description: 'How this firm segments the shops it sells to -- not a '
          "customer's legal type. A group's rate is the last one consulted: "
          'whatever the shop itself is on wins.',
      child: ManagementWorkspaceLayout(
        searchPanel: SearchFilterPanel(
          controller: _search,
          hintText: 'Search code or name',
          onSearch: (_) => setState(() {}),
          onChanged: (_) => setState(() {}),
        ),
        toolbar: WorkspaceToolbar(
          actions: const [
            ToolbarAction.newItem,
            ToolbarAction.edit,
            ToolbarAction.delete,
            ToolbarAction.refresh,
          ],
          isVisible: (action) => switch (action) {
            ToolbarAction.newItem ||
            ToolbarAction.edit ||
            ToolbarAction.delete =>
              _mayManage,
            _ => true,
          },
          isEnabled: (action) => switch (action) {
            ToolbarAction.edit || ToolbarAction.delete => selected != null,
            _ => !_loading,
          },
          onAction: (action) => switch (action) {
            ToolbarAction.newItem => unawaited(_edit()),
            ToolbarAction.edit => unawaited(_edit(selected)),
            ToolbarAction.delete =>
              selected == null ? null : unawaited(_delete(selected)),
            _ => unawaited(_load()),
          },
        ),
        primaryContent: Column(children: [
          SummaryCards(children: [
            SummaryCount(label: 'Groups', value: '${_groups.length}'),
            SummaryCount(label: 'With a rate', value: '$withRate'),
          ]),
          if (_loading) const LinearProgressIndicator(minHeight: 2),
          Expanded(child: grid),
        ]),
        statusBar: WorkspaceStatusBar(
          total: shown.length,
          selected: selected != null,
          message: _loading ? 'Refreshing...' : 'Ready',
        ),
      ),
    );
  }
}

/// A group's code, name and rate -- new, or one being corrected.
class _GroupEditor extends StatefulWidget {
  const _GroupEditor({required this.api, this.group});

  final ApiClient api;
  final CustomerGroup? group;

  @override
  State<_GroupEditor> createState() => _GroupEditorState();
}

class _GroupEditorState extends State<_GroupEditor> {
  late final TextEditingController _code =
      TextEditingController(text: widget.group?.code ?? '');
  late final TextEditingController _name =
      TextEditingController(text: widget.group?.name ?? '');
  late final TextEditingController _rate = TextEditingController(
    text: widget.group == null
        ? ''
        : _CustomerGroupsPageState._rate(widget.group!.defaultDiscountPercent),
  );
  bool _saving = false;
  String? _error;

  @override
  void dispose() {
    _code.dispose();
    _name.dispose();
    _rate.dispose();
    super.dispose();
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
      final CustomerGroup? group = widget.group;
      if (group == null) {
        await widget.api.createCustomerGroup(body);
      } else {
        await widget.api.updateCustomerGroup(
          group.id,
          body,
          expectedVersion: group.version,
        );
      }
      if (!mounted) return;
      Navigator.of(context).pop(true);
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        // The form stays open, so the typing survives the refusal.
        _error = saveFailureMessage(error, 'customer group', changesKept: true);
        _saving = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: Text(widget.group == null ? 'New customer group' : 'Edit group'),
        content: SizedBox(
          width: 420,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              TextField(
                controller: _code,
                enabled: !_saving,
                autofocus: true,
                decoration: const InputDecoration(labelText: 'Code'),
                textCapitalization: TextCapitalization.characters,
              ),
              const SizedBox(height: AppSpacing.md),
              TextField(
                controller: _name,
                enabled: !_saving,
                decoration: const InputDecoration(labelText: 'Name'),
              ),
              const SizedBox(height: AppSpacing.md),
              TextField(
                controller: _rate,
                enabled: !_saving,
                decoration: const InputDecoration(
                  labelText: 'Rate',
                  suffixText: '%',
                  helperText: 'Blank is none. Whatever the shop itself is on '
                      'wins over this.',
                ),
                keyboardType: TextInputType.number,
                onSubmitted: (_) => _save(),
              ),
              if (_error != null) ...[
                const SizedBox(height: AppSpacing.md),
                Text(
                  _error!,
                  style: Theme.of(context)
                      .textTheme
                      .bodySmall
                      ?.copyWith(color: Theme.of(context).colorScheme.error),
                ),
              ],
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: _saving ? null : () => Navigator.of(context).pop(false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: _saving ? null : _save,
            child: Text(widget.group == null ? 'Add group' : 'Save'),
          ),
        ],
      );
}
