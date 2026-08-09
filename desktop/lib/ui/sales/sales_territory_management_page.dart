import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/dialogs/app_dialogs.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/entities.dart';
import '../../models/sales_territory.dart';
import '../workspace/desktop_framework.dart';

class SalesTerritoryManagementPage extends StatefulWidget {
  const SalesTerritoryManagementPage({
    super.key,
    required this.api,
    required this.permissions,
  });

  final ApiClient api;
  final PermissionService permissions;

  @override
  State<SalesTerritoryManagementPage> createState() =>
      _SalesTerritoryManagementPageState();
}

class _SalesTerritoryManagementPageState
    extends State<SalesTerritoryManagementPage> {
  static const int _rowsPerPage = 20;
  final TextEditingController _search = TextEditingController();
  final FocusNode _searchFocus = FocusNode();

  TerritoryHierarchyRecord? _hierarchy;
  List<TerritoryTreeNodeRecord> _tree = const [];
  List<SalesTerritory> _items = const [];
  SalesTerritory? _selected;
  bool _loading = false;
  String? _error;
  int _page = 1;
  int _total = 0;
  String _sortBy = 'created_at';
  bool _descending = true;
  bool _includeDeleted = false;
  String? _status;
  String? _selectedParentId;
  Json _dashboard = const {};
  bool _expandTree = false;
  int _treeEpoch = 0;

  bool get _canView => widget.permissions.hasPermission('TERRITORY_VIEW');
  bool get _canCreate => widget.permissions.hasPermission('TERRITORY_CREATE');
  bool get _canEdit => widget.permissions.hasPermission('TERRITORY_UPDATE');
  bool get _canDelete => widget.permissions.hasPermission('TERRITORY_DELETE');
  bool get _canRestore => widget.permissions.hasPermission('TERRITORY_RESTORE');
  bool get _canExport => widget.permissions.hasPermission('TERRITORY_EXPORT');
  bool get _canAssignCustomers =>
      widget.permissions.hasPermission('TERRITORY_ASSIGN_CUSTOMERS');
  bool get _canAssignSalesmen =>
      widget.permissions.hasPermission('TERRITORY_ASSIGN_SALESMEN');

  @override
  void initState() {
    super.initState();
    _loadAll();
  }

  @override
  void dispose() {
    _search.dispose();
    _searchFocus.dispose();
    super.dispose();
  }

  Future<void> _loadAll({int? requestedPage}) async {
    if (!_canView) return;
    setState(() {
      _loading = true;
      _error = null;
      _page = requestedPage ?? _page;
    });
    try {
      final hierarchy = await widget.api.territoryHierarchy();
      final tree = await widget.api.territoryTree(
        includeDeleted: _includeDeleted,
      );
      final page = await widget.api.territories(
        page: _page,
        search: _search.text.trim(),
        sortBy: _sortBy,
        descending: _descending,
        filters: TerritoryQuery(
          parentId: _selectedParentId,
          status: _status,
          includeDeleted: _includeDeleted,
        ),
      );
      final dashboard = await widget.api.territoryDashboard();
      if (!mounted) return;
      setState(() {
        _hierarchy = hierarchy;
        _tree = tree;
        _items = page.items;
        _total = page.total;
        final selectedId = _selected?.id;
        _selected = selectedId == null
            ? null
            : _items.where((item) => item.id == selectedId).isEmpty
                ? null
                : _items.firstWhere((item) => item.id == selectedId);
        _dashboard = dashboard;
      });
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() => _error = exception.message);
    } finally {
      if (mounted) {
        setState(() => _loading = false);
      }
    }
  }

  Future<void> _openEditor({SalesTerritory? current, String? parentId}) async {
    if (!_canCreate && current == null) return;
    if (!_canEdit && current != null) return;
    final result = await showDialog<Json>(
      context: context,
      builder: (context) => _TerritoryEditorDialog(
        territory: current,
        hierarchy: _hierarchy,
        items: _items,
        initialParentId: parentId,
      ),
    );
    if (!mounted || result == null) return;
    try {
      if (current == null) {
        await widget.api.createTerritory(result);
      } else {
        await widget.api.updateTerritory(current.id, result);
      }
      await _loadAll();
    } on ApiException catch (exception) {
      if (!mounted) return;
      NotificationService.show(
        context,
        exception.message,
        kind: AppNotificationKind.error,
      );
    }
  }

  Future<void> _delete(SalesTerritory territory) async {
    if (!_canDelete || territory.isDeleted) return;
    final bool confirmed = await showWorkspaceConfirmDialog(
      context,
      title: 'Delete territory?',
      message: 'This territory will be soft deleted.',
      confirmLabel: 'Delete',
      type: ConfirmationType.delete,
    );
    if (!confirmed || !mounted) return;
    try {
      await widget.api.deleteTerritory(territory.id);
      await _loadAll();
    } on ApiException catch (exception) {
      if (!mounted) return;
      NotificationService.show(
        context,
        exception.message,
        kind: AppNotificationKind.error,
      );
    }
  }

  Future<void> _restore(SalesTerritory territory) async {
    if (!_canRestore || !territory.isDeleted) return;
    try {
      await widget.api.restoreTerritory(territory.id);
      await _loadAll();
    } on ApiException catch (exception) {
      if (!mounted) return;
      NotificationService.show(
        context,
        exception.message,
        kind: AppNotificationKind.error,
      );
    }
  }

  Future<void> _assignCustomers(SalesTerritory territory) async {
    if (!_canAssignCustomers) return;
    final TextEditingController input = TextEditingController(
      text: (await widget.api.territoryCustomers(territory.id)).join(','),
    );
    if (!mounted) return;
    final bool? submitted = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('Assign customers to ${territory.name}'),
        content: TextField(
          controller: input,
          maxLines: 4,
          decoration: const InputDecoration(
            labelText: 'Customer IDs (comma separated)',
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Save'),
          ),
        ],
      ),
    );
    if (submitted != true || !mounted) return;
    final ids = input.text
        .split(',')
        .map((value) => value.trim())
        .where((value) => value.isNotEmpty)
        .toList();
    try {
      await widget.api.setTerritoryCustomers(territory.id, ids);
      await _loadAll();
    } on ApiException catch (exception) {
      if (!mounted) return;
      NotificationService.show(
        context,
        exception.message,
        kind: AppNotificationKind.error,
      );
    } finally {
      input.dispose();
    }
  }

  Future<void> _assignSalesmen(SalesTerritory territory) async {
    if (!_canAssignSalesmen) return;
    final TextEditingController input = TextEditingController(
      text: (await widget.api.territorySalesmen(territory.id))
          .map((value) => value['user_id'].toString())
          .join(','),
    );
    if (!mounted) return;
    final bool? submitted = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('Assign salesmen to ${territory.name}'),
        content: TextField(
          controller: input,
          maxLines: 4,
          decoration: const InputDecoration(
            labelText: 'User IDs (comma separated)',
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Save'),
          ),
        ],
      ),
    );
    if (submitted != true || !mounted) return;
    final assignments = input.text
        .split(',')
        .map((value) => value.trim())
        .where((value) => value.isNotEmpty)
        .map((id) => {
              'user_id': id,
              'include_children': false,
              'is_primary': false,
            })
        .toList();
    try {
      await widget.api.setTerritorySalesmen(territory.id, assignments);
      await _loadAll();
    } on ApiException catch (exception) {
      if (!mounted) return;
      NotificationService.show(
        context,
        exception.message,
        kind: AppNotificationKind.error,
      );
    } finally {
      input.dispose();
    }
  }

  Future<void> _export() async {
    if (!_canExport) return;
    try {
      final csv =
          await widget.api.exportTerritories(search: _search.text.trim());
      if (!mounted) return;
      NotificationService.show(
        context,
        'Export generated (${csv.length} bytes).',
        kind: AppNotificationKind.success,
      );
    } on ApiException catch (exception) {
      if (!mounted) return;
      NotificationService.show(
        context,
        exception.message,
        kind: AppNotificationKind.error,
      );
    }
  }

  Future<void> _copyHierarchy(SalesTerritory territory) async {
    final TextEditingController code = TextEditingController(
      text: '${territory.code}_COPY',
    );
    final TextEditingController name = TextEditingController(
      text: '${territory.name} Copy',
    );
    final bool? submitted = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Copy hierarchy'),
        content: SizedBox(
          width: 420,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: code,
                decoration: const InputDecoration(labelText: 'New root code'),
              ),
              const SizedBox(height: 8),
              TextField(
                controller: name,
                decoration: const InputDecoration(labelText: 'New root name'),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Copy'),
          ),
        ],
      ),
    );
    if (submitted != true || !mounted) {
      code.dispose();
      name.dispose();
      return;
    }
    try {
      await widget.api.copyTerritory(territory.id, {
        'new_root_code': code.text.trim(),
        'new_root_name': name.text.trim(),
        'target_parent_id':
            territory.parentId.isEmpty ? null : territory.parentId,
        'include_assignments': true,
      });
      await _loadAll();
    } on ApiException catch (exception) {
      if (!mounted) return;
      NotificationService.show(
        context,
        exception.message,
        kind: AppNotificationKind.error,
      );
    } finally {
      code.dispose();
      name.dispose();
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!_canView) {
      return const WorkspaceEmptyState(
        title: 'No territory access',
        message:
            'Your account is missing TERRITORY_VIEW permission for this workspace.',
      );
    }

    final toolbar = WorkspaceToolbar(
      actions: const [
        ToolbarAction.newItem,
        ToolbarAction.edit,
        ToolbarAction.delete,
        ToolbarAction.refresh,
        ToolbarAction.export,
      ],
      isVisible: (action) => switch (action) {
        ToolbarAction.newItem => _canCreate,
        ToolbarAction.edit => _canEdit,
        ToolbarAction.delete => _canDelete || _canRestore,
        ToolbarAction.export => _canExport,
        _ => true,
      },
      isEnabled: (action) =>
          !_loading &&
          switch (action) {
            ToolbarAction.newItem => _canCreate,
            ToolbarAction.edit => _selected != null,
            ToolbarAction.delete => _selected != null,
            ToolbarAction.refresh => true,
            ToolbarAction.export => _items.isNotEmpty,
            _ => false,
          },
      onAction: (action) {
        switch (action) {
          case ToolbarAction.newItem:
            _openEditor();
            break;
          case ToolbarAction.edit:
            if (_selected != null) _openEditor(current: _selected);
            break;
          case ToolbarAction.delete:
            final selected = _selected;
            if (selected != null) {
              if (selected.isDeleted) {
                _restore(selected);
              } else {
                _delete(selected);
              }
            }
            break;
          case ToolbarAction.refresh:
            _loadAll();
            break;
          case ToolbarAction.export:
            _export();
            break;
          case ToolbarAction.view:
          case ToolbarAction.import:
          case ToolbarAction.print:
          case ToolbarAction.settings:
            break;
        }
      },
    );

    final searchPanel = SearchFilterPanel(
      controller: _search,
      focusNode: _searchFocus,
      hintText: 'Search code, name, hierarchy path',
      onSearch: (_) => _loadAll(requestedPage: 1),
      filters: [
        SizedBox(
          width: 180,
          child: DropdownButtonFormField<String>(
            initialValue: _status,
            decoration: const InputDecoration(labelText: 'Status'),
            items: const [
              DropdownMenuItem(value: 'DRAFT', child: Text('Draft')),
              DropdownMenuItem(value: 'ACTIVE', child: Text('Active')),
              DropdownMenuItem(value: 'INACTIVE', child: Text('Inactive')),
              DropdownMenuItem(value: 'ARCHIVED', child: Text('Archived')),
            ],
            onChanged: (value) {
              setState(() => _status = value);
              _loadAll(requestedPage: 1);
            },
          ),
        ),
        FilterChip(
          label: const Text('Include deleted'),
          selected: _includeDeleted,
          onSelected: (value) {
            setState(() => _includeDeleted = value);
            _loadAll(requestedPage: 1);
          },
        ),
      ],
    );

    final primaryContent = _error != null
        ? WorkspaceErrorState(message: _error!, onRetry: _loadAll)
        : _loading && _items.isEmpty
            ? const TableLoadingSkeleton()
            : _items.isEmpty
                ? const StandardEmptyState(type: EmptyStateType.noRecords)
                : LoadingOverlay(
                    loading: _loading,
                    child: EnterpriseDataGrid<SalesTerritory>(
                      items: _items,
                      total: _total,
                      pageOffset: (_page - 1) * _rowsPerPage,
                      rowsPerPage: _rowsPerPage,
                      columns: [
                        _column('Code', 'code'),
                        _column('Name', 'name'),
                        const GridColumn(key: 'level', label: 'Level'),
                        const GridColumn(key: 'route', label: 'Route type'),
                        const GridColumn(key: 'path', label: 'Hierarchy'),
                        _column('Status', 'status'),
                        const GridColumn(key: 'frequency', label: 'Frequency'),
                        const GridColumn(key: 'customers', label: 'Customers'),
                        const GridColumn(key: 'salesmen', label: 'Salesmen'),
                      ],
                      id: (item) => item.id,
                      cells: (item) => [
                        item.code,
                        item.name,
                        item.hierarchyLevelName,
                        item.routeProfile?.routeTypeName.isNotEmpty == true
                            ? item.routeProfile!.routeTypeName
                            : '-',
                        item.path,
                        item.isDeleted ? 'DELETED' : item.status,
                        item.routeProfile?.visitFrequency.isNotEmpty == true
                            ? item.routeProfile!.visitFrequency
                            : '-',
                        item.customerCount.toString(),
                        item.salesmanCount.toString(),
                      ],
                      selectedId: _selected?.id,
                      onSelect: (item) => setState(() => _selected = item),
                      onOpen: (item) => _openEditor(current: item),
                      onPageChanged: (offset) =>
                          _loadAll(requestedPage: offset ~/ _rowsPerPage + 1),
                    ),
                  );

    return WorkspaceShortcuts(
      bindings: WorkspaceShortcutBindings(
        create: _canCreate ? () => _openEditor() : null,
        focusSearch: _searchFocus.requestFocus,
        refresh: _loadAll,
        delete:
            _selected != null && _canDelete ? () => _delete(_selected!) : null,
      ),
      child: ManagementWorkspaceLayout(
        toolbar: toolbar,
        searchPanel: searchPanel,
        primaryContent: primaryContent,
        detailsPanel: _selected == null ? null : _detailsPanel(),
        statusBar: WorkspaceStatusBar(
          total: _total,
          selected: _selected != null,
          message: _loading ? 'Refreshing territories...' : 'Ready',
        ),
      ),
    );
  }

  GridColumn _column(String label, String sortBy) => GridColumn(
        key: sortBy,
        label: label,
        onSort: (ascending) {
          _sortBy = sortBy;
          _descending = !ascending;
          _loadAll(requestedPage: 1);
        },
      );

  Widget _detailsPanel() => Card(
        clipBehavior: Clip.antiAlias,
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.all(12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    _selected == null ? 'Territory tree' : _selected!.name,
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                  const SizedBox(height: 8),
                  if (_selected != null) ...[
                    Text('Code: ${_selected!.code}'),
                    Text('Level: ${_selected!.hierarchyLevelName}'),
                    Text(
                        'Status: ${_selected!.isDeleted ? 'DELETED' : _selected!.status}'),
                    Text('Customers: ${_selected!.customerCount}'),
                    Text('Salesmen: ${_selected!.salesmanCount}'),
                    Text(
                      'Coverage: A:${_selected!.activeCustomerCount} / I:${_selected!.inactiveCustomerCount} / N:${_selected!.newCustomerCount} / P:${_selected!.potentialCustomerCount}',
                    ),
                  ],
                  const SizedBox(height: 8),
                  Text(
                    'Dashboard • Territories ${_dashboard['total_territories'] ?? 0} • Routes ${_dashboard['total_routes'] ?? 0} • Customers w/o route ${_dashboard['customers_without_route'] ?? 0}',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              child: Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  OutlinedButton.icon(
                    onPressed: () => setState(() {
                      _expandTree = true;
                      _treeEpoch++;
                    }),
                    icon: const Icon(Icons.unfold_more),
                    label: const Text('Expand all'),
                  ),
                  OutlinedButton.icon(
                    onPressed: () => setState(() {
                      _expandTree = false;
                      _treeEpoch++;
                    }),
                    icon: const Icon(Icons.unfold_less),
                    label: const Text('Collapse all'),
                  ),
                  if (_selected != null && _canCreate)
                    OutlinedButton.icon(
                      onPressed: () => _openEditor(parentId: _selected!.id),
                      icon: const Icon(Icons.add),
                      label: const Text('Quick create child'),
                    ),
                  if (_selected != null && _canCreate)
                    OutlinedButton.icon(
                      onPressed: () => _copyHierarchy(_selected!),
                      icon: const Icon(Icons.copy_all_outlined),
                      label: const Text('Copy hierarchy'),
                    ),
                ],
              ),
            ),
            const Divider(height: 1),
            Expanded(
              child: ListView(
                padding: const EdgeInsets.all(8),
                children: [for (final node in _tree) _treeNode(node)],
              ),
            ),
            if (_selected != null &&
                (_canAssignCustomers || _canAssignSalesmen))
              Padding(
                padding: const EdgeInsets.all(12),
                child: Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    if (_canAssignCustomers)
                      OutlinedButton.icon(
                        onPressed: () => _assignCustomers(_selected!),
                        icon: const Icon(Icons.groups_2_outlined),
                        label: const Text('Assign customers'),
                      ),
                    if (_canAssignSalesmen)
                      OutlinedButton.icon(
                        onPressed: () => _assignSalesmen(_selected!),
                        icon: const Icon(Icons.badge_outlined),
                        label: const Text('Assign salesmen'),
                      ),
                  ],
                ),
              ),
          ],
        ),
      );

  Widget _treeNode(TerritoryTreeNodeRecord node) => ExpansionTile(
        key: ValueKey('tree-${node.id}-$_treeEpoch'),
        title: Text('${node.name} (${node.hierarchyLevelName})'),
        subtitle: Text(node.code),
        initiallyExpanded: _expandTree,
        children: [
          ListTile(
            dense: true,
            title: Text(node.path),
            trailing: PopupMenuButton<String>(
              onSelected: (value) {
                if (value == 'filter') {
                  setState(() => _selectedParentId = node.id);
                  _loadAll(requestedPage: 1);
                } else if (value == 'create') {
                  _openEditor(parentId: node.id);
                } else if (value == 'clear-filter') {
                  setState(() => _selectedParentId = null);
                  _loadAll(requestedPage: 1);
                }
              },
              itemBuilder: (context) => [
                const PopupMenuItem(
                    value: 'filter', child: Text('Filter list')),
                if (_canCreate)
                  const PopupMenuItem(
                    value: 'create',
                    child: Text('Quick create child'),
                  ),
                if (_selectedParentId != null)
                  const PopupMenuItem(
                    value: 'clear-filter',
                    child: Text('Clear parent filter'),
                  ),
              ],
            ),
          ),
          for (final child in node.children) _treeNode(child),
        ],
      );
}

class _TerritoryEditorDialog extends StatefulWidget {
  const _TerritoryEditorDialog({
    required this.territory,
    required this.hierarchy,
    required this.items,
    this.initialParentId,
  });

  final SalesTerritory? territory;
  final TerritoryHierarchyRecord? hierarchy;
  final List<SalesTerritory> items;
  final String? initialParentId;

  @override
  State<_TerritoryEditorDialog> createState() => _TerritoryEditorDialogState();
}

class _TerritoryEditorDialogState extends State<_TerritoryEditorDialog> {
  final _form = GlobalKey<FormState>();
  late final TextEditingController _code =
      TextEditingController(text: widget.territory?.code ?? '');
  late final TextEditingController _name =
      TextEditingController(text: widget.territory?.name ?? '');
  late final TextEditingController _description =
      TextEditingController(text: widget.territory?.description ?? '');
  late String _status = widget.territory?.status ?? 'ACTIVE';
  late String? _levelId = widget.territory?.hierarchyLevelId;
  late String? _parentId = widget.territory?.parentId.isEmpty == true
      ? (widget.initialParentId?.isEmpty == true
          ? null
          : widget.initialParentId)
      : widget.territory?.parentId;

  @override
  void dispose() {
    _code.dispose();
    _name.dispose();
    _description.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title:
            Text(widget.territory == null ? 'New territory' : 'Edit territory'),
        content: SizedBox(
          width: 560,
          child: Form(
            key: _form,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextFormField(
                  controller: _code,
                  decoration: const InputDecoration(labelText: 'Code'),
                  validator: (value) => (value == null || value.trim().isEmpty)
                      ? 'Code is required'
                      : null,
                ),
                const SizedBox(height: 8),
                TextFormField(
                  controller: _name,
                  decoration: const InputDecoration(labelText: 'Name'),
                  validator: (value) => (value == null || value.trim().isEmpty)
                      ? 'Name is required'
                      : null,
                ),
                const SizedBox(height: 8),
                DropdownButtonFormField<String>(
                  initialValue: _levelId,
                  decoration:
                      const InputDecoration(labelText: 'Hierarchy level'),
                  items: (widget.hierarchy?.levels ?? const [])
                      .map(
                        (level) => DropdownMenuItem(
                          value: level.id,
                          child: Text(level.displayName),
                        ),
                      )
                      .toList(),
                  onChanged: (value) => setState(() => _levelId = value),
                  validator: (value) => value == null || value.isEmpty
                      ? 'Level is required'
                      : null,
                ),
                const SizedBox(height: 8),
                DropdownButtonFormField<String>(
                  initialValue: _parentId,
                  decoration: const InputDecoration(labelText: 'Parent'),
                  items: [
                    const DropdownMenuItem<String>(
                      value: '',
                      child: Text('No parent (root)'),
                    ),
                    ...widget.items.map(
                      (item) => DropdownMenuItem<String>(
                        value: item.id,
                        child: Text('${item.code} - ${item.name}'),
                      ),
                    ),
                  ],
                  onChanged: (value) => setState(
                    () => _parentId =
                        (value == null || value.isEmpty) ? null : value,
                  ),
                ),
                const SizedBox(height: 8),
                DropdownButtonFormField<String>(
                  initialValue: _status,
                  decoration: const InputDecoration(labelText: 'Status'),
                  items: const [
                    DropdownMenuItem(value: 'ACTIVE', child: Text('Active')),
                    DropdownMenuItem(
                        value: 'INACTIVE', child: Text('Inactive')),
                    DropdownMenuItem(
                        value: 'ARCHIVED', child: Text('Archived')),
                  ],
                  onChanged: (value) =>
                      setState(() => _status = value ?? 'ACTIVE'),
                ),
                const SizedBox(height: 8),
                TextFormField(
                  controller: _description,
                  maxLines: 3,
                  decoration: const InputDecoration(labelText: 'Description'),
                ),
              ],
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () {
              if (!(_form.currentState?.validate() ?? false)) return;
              Navigator.pop<Json>(
                context,
                {
                  'code': _code.text.trim().toUpperCase(),
                  'name': _name.text.trim(),
                  'hierarchy_level_id': _levelId,
                  'parent_id': _parentId,
                  'description': _description.text.trim().isEmpty
                      ? null
                      : _description.text.trim(),
                  'status': _status,
                  'sort_order': 0,
                },
              );
            },
            child: const Text('Save'),
          ),
        ],
      );
}
