import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/api/concurrency.dart';
import '../../core/dialogs/app_dialogs.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/entities.dart';
import '../../models/customer.dart';
import '../../models/geography.dart';
import '../../models/sales_territory.dart';
import 'assignment_picker_dialog.dart';
import 'bulk_territory_actions_dialog.dart';
import 'call_order_dialog.dart';
import 'territory_detail_dialog.dart';
import 'territory_import_dialog.dart';
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
  String? _filterCityId;
  List<GeoPlaceRecord> _filterCities = const [];
  String? _selectedParentId;
  Json _dashboard = const {};
  bool _expandTree = false;
  int _treeEpoch = 0;

  /// Rows ticked for a bulk action. Distinct from `_selected`, which is the one
  /// row the detail panel and the Edit button follow — ticking twenty rows to
  /// restatus them should not also change what the panel is describing.
  Set<String> _bulkIds = <String>{};

  bool get _canView => widget.permissions.hasPermission('TERRITORY_VIEW');
  bool get _canCreate => widget.permissions.hasPermission('TERRITORY_CREATE');
  bool get _canEdit => widget.permissions.hasPermission('TERRITORY_UPDATE');
  bool get _canDelete => widget.permissions.hasPermission('TERRITORY_DELETE');
  bool get _canRestore => widget.permissions.hasPermission('TERRITORY_RESTORE');
  bool get _canExport => widget.permissions.hasPermission('TERRITORY_EXPORT');
  bool get _canImport => widget.permissions.hasPermission('TERRITORY_IMPORT');
  bool get _canAssignCustomers =>
      widget.permissions.hasPermission('TERRITORY_ASSIGN_CUSTOMERS');
  bool get _canAssignSalesmen =>
      widget.permissions.hasPermission('TERRITORY_ASSIGN_SALESMEN');

  /// Whether any bulk operation is open to this user at all.
  ///
  /// The checkbox column only appears when it is: offering people rows to tick
  /// and then no action to take on them is worse than not offering it.
  bool get _canBulk => _canEdit || _canAssignCustomers || _canAssignSalesmen;

  @override
  void initState() {
    super.initState();
    _loadAll();
    _loadFilterCities();
  }

  /// The cities a round could be tagged with, for the area filter.
  ///
  /// Best effort: geography is shared reference data a platform administrator
  /// maintains, and a firm whose Places are empty gets no filter rather than a
  /// broken grid.
  Future<void> _loadFilterCities() async {
    if (!_canView) return;
    try {
      final List<GeoPlaceRecord> rows =
          await widget.api.geoPlaces(GeoLevel.city);
      if (!mounted) return;
      setState(() => _filterCities = rows);
    } on ApiException {
      // No filter is better than an error on a screen that works without it.
    }
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
          cityId: _filterCityId,
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
    // Fetched here rather than held on the page: the editor is the only
    // place that needs them, and a firm defines these once and rarely.
    final List<TerritoryRouteTypeRecord> routeTypes =
        await widget.api.territoryRouteTypes();
    if (!mounted) return;
    final result = await showDialog<Json>(
      context: context,
      builder: (context) => _TerritoryEditorDialog(
        api: widget.api,
        territory: current,
        hierarchy: _hierarchy,
        items: _items,
        initialParentId: parentId,
        routeTypes: routeTypes,
      ),
    );
    if (!mounted || result == null) return;
    try {
      if (current == null) {
        await widget.api.createTerritory(result);
      } else {
        await widget.api.updateTerritory(
          current.id,
          result,
          expectedVersion: preconditionFor(current.version),
        );
      }
      await _loadAll();
    } on ApiException catch (exception) {
      if (!mounted) return;
      NotificationService.show(
        context,
        saveFailureMessage(exception, 'territory', changesKept: false),
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

  /// The API caps a page at 100, and the picker needs the whole list: a
  /// customer on page three is one you can neither find nor take off a round.

  /// Reads every page of a list endpoint. Bounded so a firm with a very large
  /// book cannot turn opening a dialog into a hundred requests — the search
  /// box inside the picker is the answer beyond this, not more paging.
  Future<List<T>> _allPages<T>(
    Future<PagedResult<T>> Function(int page) fetch,
  ) =>
      fetchAllPages<T>(fetch);

  Future<void> _assignCustomers(SalesTerritory territory) async {
    if (!_canAssignCustomers) return;
    // Replaces a text box that asked for comma-separated customer UUIDs.
    // Nobody knows a customer's id, and pasting the wrong one assigns a
    // different customer with nothing on screen to notice it by.
    final List<TerritoryCustomerAssignmentRecord> current =
        await widget.api.territoryCustomers(territory.id);
    final List<Customer> customers = await _allPages<Customer>(
      (page) => widget.api.customers(page: page, pageSize: maxApiPageSize),
    );
    if (!mounted) return;
    final List<String>? chosen = await showDialog<List<String>>(
      context: context,
      builder: (context) => AssignmentPickerDialog(
        title: 'Customers on ${territory.name}',
        searchHint: 'Search customers by name or code',
        emptyMessage: 'This firm has no customers yet. Add one under '
            'Masters before putting anybody on a round.',
        selectedIds: {for (final row in current) row.customerId},
        options: [
          for (final Customer customer in customers)
            AssignableOption(
              id: customer.id,
              label: customer.displayName.isEmpty
                  ? customer.name
                  : customer.displayName,
              secondary: customer.code,
            ),
        ],
      ),
    );
    if (chosen == null || !mounted) return;
    try {
      // Carry each customer's existing place in the round through. The picker
      // adds and removes; it has no notion of order, and rebuilding the list
      // from bare ids would flatten a sequence somebody had set.
      final Map<String, TerritoryCustomerAssignmentRecord> existing = {
        for (final row in current) row.customerId: row,
      };
      await widget.api.setTerritoryCustomers(territory.id, [
        for (final String id in chosen)
          existing[id] ??
              TerritoryCustomerAssignmentRecord(
                customerId: id,
                isPrimary: true,
                visitSequence: null,
                isPotential: false,
              ),
      ]);
      await _loadAll();
      if (!mounted) return;
      NotificationService.show(
        context,
        '${chosen.length} customer(s) on ${territory.name}.',
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

  Future<void> _setCallOrder(SalesTerritory territory) async {
    if (!_canAssignCustomers) return;
    final List<TerritoryCustomerAssignmentRecord> current =
        await widget.api.territoryCustomers(territory.id);
    final List<Customer> customers = await _allPages<Customer>(
      (page) => widget.api.customers(page: page, pageSize: maxApiPageSize),
    );
    if (!mounted) return;
    final Map<String, Customer> byId = {
      for (final Customer customer in customers) customer.id: customer,
    };
    final List<TerritoryCustomerAssignmentRecord>? ordered =
        await showDialog<List<TerritoryCustomerAssignmentRecord>>(
      context: context,
      builder: (context) => CallOrderDialog(
        routeName: territory.name,
        assignments: current,
        nameFor: (id) {
          final Customer? customer = byId[id];
          if (customer == null) return id;
          return customer.displayName.isEmpty
              ? '${customer.code} — ${customer.name}'
              : '${customer.code} — ${customer.displayName}';
        },
      ),
    );
    if (ordered == null || !mounted) return;
    try {
      await widget.api.setTerritoryCustomers(territory.id, ordered);
      await _loadAll();
      if (!mounted) return;
      NotificationService.show(
        context,
        'Call order saved for ${territory.name}.',
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

  Future<void> _assignSalesmen(SalesTerritory territory) async {
    if (!_canAssignSalesmen) return;
    final List<Json> current = await widget.api.territorySalesmen(territory.id);
    final List<TerritorySalesmanCandidate> users =
        await widget.api.territorySalesmanCandidates();
    if (!mounted) return;
    // An existing assignment carries more than a user id. Re-sending only the
    // id would quietly clear whoever was the primary and whoever covered the
    // child territories, because the API replaces the whole list.
    final Map<String, Json> existing = <String, Json>{
      for (final Json entry in current) stringValue(entry['user_id']): entry,
    };
    final List<String>? chosen = await showDialog<List<String>>(
      context: context,
      builder: (context) => AssignmentPickerDialog(
        title: 'Salespeople on ${territory.name}',
        searchHint: 'Search people by name or email',
        emptyMessage: 'No users to assign. Add one under Administration.',
        selectedIds: {
          for (final Json entry in current) stringValue(entry['user_id']),
        }..removeWhere((id) => id.isEmpty),
        options: [
          for (final TerritorySalesmanCandidate user in users)
            AssignableOption(
              id: user.userId,
              label: user.fullName.isEmpty ? user.email : user.fullName,
              secondary: user.email,
            ),
        ],
      ),
    );
    if (chosen == null || !mounted) return;
    try {
      await widget.api.setTerritorySalesmen(
        territory.id,
        [
          for (final String userId in chosen)
            <String, dynamic>{
              'user_id': userId,
              'is_primary': existing[userId]?['is_primary'] == true,
              'include_children': existing[userId]?['include_children'] == true,
            },
        ],
      );
      await _loadAll();
      if (!mounted) return;
      NotificationService.show(
        context,
        '${chosen.length} salesperson(s) on ${territory.name}.',
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

  /// Run one operation over every ticked territory.
  ///
  /// Each of the four is a single request that the server applies in one
  /// transaction, so a batch refused on its fifth territory leaves the first
  /// four unchanged — which is what lets the failure message say nothing was
  /// applied without lying.
  Future<void> _bulkActions() async {
    final List<SalesTerritory> targets =
        _items.where((item) => _bulkIds.contains(item.id)).toList();
    if (targets.isEmpty || !_canBulk) return;
    final BulkTerritoryChoice? choice = await showDialog<BulkTerritoryChoice>(
      context: context,
      builder: (context) => BulkTerritoryActionsDialog(
        count: targets.length,
        canUpdate: _canEdit,
        canAssignCustomers: _canAssignCustomers,
        canAssignSalesmen: _canAssignSalesmen,
        parents: [
          for (final SalesTerritory item in _items)
            if (!_bulkIds.contains(item.id))
              BulkParentOption(id: item.id, label: '${item.code} - ${item.name}'),
        ],
      ),
    );
    if (choice == null || !mounted) return;

    // The two assignment actions need a second dialog to say *who*, and both
    // replace rather than extend, so they are confirmed before anything runs.
    List<String>? chosenIds;
    if (choice.action == BulkTerritoryAction.customers) {
      chosenIds = await _pickCustomersForBulk(targets.length);
    } else if (choice.action == BulkTerritoryAction.salesmen) {
      chosenIds = await _pickSalesmenForBulk(targets.length);
    }
    if (!mounted) return;
    if (choice.action == BulkTerritoryAction.customers ||
        choice.action == BulkTerritoryAction.salesmen) {
      if (chosenIds == null) return;
    }

    try {
      final int affected = switch (choice.action) {
        BulkTerritoryAction.status => await widget.api.bulkTerritoryStatus({
            'territory_ids': [for (final item in targets) item.id],
            'status': choice.status,
          }),
        BulkTerritoryAction.move => await widget.api.bulkTerritoryMove({
            'territory_ids': [for (final item in targets) item.id],
            if (choice.parentId?.isNotEmpty == true)
              'new_parent_id': choice.parentId,
          }),
        BulkTerritoryAction.customers =>
          await widget.api.bulkTerritoryCustomers([
            for (final item in targets)
              <String, dynamic>{
                'territory_id': item.id,
                'customer_ids': chosenIds ?? const <String>[],
              },
          ]),
        BulkTerritoryAction.salesmen =>
          await widget.api.bulkTerritorySalesmen([
            for (final item in targets)
              <String, dynamic>{
                'territory_id': item.id,
                'assignments': [
                  for (final String userId in chosenIds ?? const <String>[])
                    <String, dynamic>{'user_id': userId},
                ],
              },
          ]),
      };
      setState(() => _bulkIds = <String>{});
      await _loadAll();
      if (!mounted) return;
      NotificationService.show(
        context,
        '$affected territor${affected == 1 ? 'y' : 'ies'} updated.',
        kind: AppNotificationKind.success,
      );
    } on ApiException catch (exception) {
      if (!mounted) return;
      NotificationService.show(
        context,
        '${exception.message} Nothing was changed.',
        kind: AppNotificationKind.error,
      );
    }
  }

  Future<List<String>?> _pickCustomersForBulk(int count) async {
    final List<Customer> customers = await _allPages<Customer>(
      (page) => widget.api.customers(page: page, pageSize: maxApiPageSize),
    );
    if (!mounted) return null;
    return showDialog<List<String>>(
      context: context,
      builder: (context) => AssignmentPickerDialog(
        title: 'Customers for $count territories',
        searchHint: 'Search customers by name or code',
        emptyMessage: 'This firm has no customers yet.',
        // Deliberately empty rather than pre-ticked from any one territory:
        // the list applies to all of them, so seeding it from one would put
        // that territory's customers onto the other nineteen by default.
        selectedIds: const <String>{},
        options: [
          for (final Customer customer in customers)
            AssignableOption(
              id: customer.id,
              label: customer.displayName.isEmpty
                  ? customer.name
                  : customer.displayName,
              secondary: customer.code,
            ),
        ],
      ),
    );
  }

  Future<List<String>?> _pickSalesmenForBulk(int count) async {
    final List<TerritorySalesmanCandidate> users =
        await widget.api.territorySalesmanCandidates();
    if (!mounted) return null;
    return showDialog<List<String>>(
      context: context,
      builder: (context) => AssignmentPickerDialog(
        title: 'Salespeople for $count territories',
        searchHint: 'Search people by name or email',
        emptyMessage: 'No users to assign. Add one under Administration.',
        selectedIds: const <String>{},
        options: [
          for (final TerritorySalesmanCandidate user in users)
            AssignableOption(
              id: user.userId,
              label: user.fullName.isEmpty ? user.email : user.fullName,
              secondary: user.email,
            ),
        ],
      ),
    );
  }

  /// Show everything about one territory, full screen.
  ///
  /// The right-hand card had 300 pixels for a summary, the tree controls and
  /// the tree itself. This is where the summary went, and where a round's
  /// outlets are laid out in the order they are called.
  Future<void> _openDetail(SalesTerritory territory) async {
    final bool? saved = await showDialog<bool>(
      context: context,
      builder: (context) => TerritoryDetailDialog(
        api: widget.api,
        permissions: widget.permissions,
        territory: territory,
      ),
    );
    if (saved != true || !mounted) return;
    // Customer and salesman counts live on the grid row, so they go stale the
    // moment the dialog saves.
    await _loadAll();
  }

  /// Load a hierarchy from CSV. The whole file is one transaction server-side.
  Future<void> _import() async {
    if (!_canImport) return;
    final bool? imported = await showDialog<bool>(
      context: context,
      builder: (context) => TerritoryImportDialog(api: widget.api),
    );
    if (imported != true || !mounted) return;
    await _loadAll();
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
        ToolbarAction.view,
        ToolbarAction.edit,
        ToolbarAction.delete,
        ToolbarAction.refresh,
        ToolbarAction.import,
        ToolbarAction.export,
      ],
      isVisible: (action) => switch (action) {
        ToolbarAction.newItem => _canCreate,
        ToolbarAction.edit => _canEdit,
        ToolbarAction.delete => _canDelete || _canRestore,
        ToolbarAction.import => _canImport,
        ToolbarAction.export => _canExport,
        _ => true,
      },
      isEnabled: (action) =>
          !_loading &&
          switch (action) {
            ToolbarAction.newItem => _canCreate,
            ToolbarAction.view => _selected != null,
            ToolbarAction.edit => _selected != null,
            ToolbarAction.delete => _selected != null,
            ToolbarAction.refresh => true,
            ToolbarAction.import => _canImport,
            ToolbarAction.export => _items.isNotEmpty,
            _ => false,
          },
      onAction: (action) {
        switch (action) {
          case ToolbarAction.newItem:
            _openEditor();
            break;
          case ToolbarAction.view:
            if (_selected != null) _openDetail(_selected!);
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
          case ToolbarAction.import:
            _import();
            break;
          case ToolbarAction.export:
            _export();
            break;
          case ToolbarAction.print:
          case ToolbarAction.settings:
            break;
        }
      },
    );

    final Widget? bulkBar = _bulkIds.isEmpty
        ? null
        : Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            child: Wrap(
              spacing: 8,
              runSpacing: 8,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                Text('${_bulkIds.length} ticked'),
                FilledButton.icon(
                  onPressed: _bulkActions,
                  icon: const Icon(Icons.playlist_add_check),
                  label: const Text('Bulk actions'),
                ),
                TextButton(
                  onPressed: () => setState(() => _bulkIds = <String>{}),
                  child: const Text('Clear selection'),
                ),
              ],
            ),
          );

    final searchPanel = SearchFilterPanel(
      controller: _search,
      focusNode: _searchFocus,
      hintText: 'Search code, name, hierarchy path',
      onSearch: (_) => _loadAll(requestedPage: 1),
      filters: [
        // Matches through the route profile's city, which is why the editor
        // now lets a round say where it is: the server has always filtered on
        // this and nothing ever wrote the column.
        if (_filterCities.isNotEmpty)
          SizedBox(
            width: 200,
            child: DropdownButtonFormField<String>(
              isExpanded: true,
              initialValue: _filterCityId ?? '',
              decoration: const InputDecoration(labelText: 'Area (city)'),
              items: [
                const DropdownMenuItem<String>(
                    value: '', child: Text('Any area')),
                for (final GeoPlaceRecord city in _filterCities)
                  DropdownMenuItem<String>(
                    value: city.id,
                    child: Text(city.name),
                  ),
              ],
              onChanged: (value) {
                setState(() =>
                    _filterCityId = (value == null || value.isEmpty) ? null : value);
                _loadAll(requestedPage: 1);
              },
            ),
          ),
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
                      selectedIds: _bulkIds,
                      onSelectionChanged: _canBulk
                          ? (ids) => setState(() => _bulkIds = ids)
                          : null,
                      onSelect: (item) => setState(() => _selected = item),
                      onOpen: _openDetail,
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
        // Sits between the filters and the grid so the count and the action are
        // next to the rows they apply to, and vanishes when nothing is ticked.
        filterPanel: bulkBar,
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
                    'Territory tree',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                  const SizedBox(height: 8),
                  // The selected node's summary moved to the detail dialog,
                  // which has room for it. This panel is the tree.
                  if (_selected != null)
                    OutlinedButton.icon(
                      onPressed: () => _openDetail(_selected!),
                      icon: const Icon(Icons.open_in_full),
                      label: Text('Open ${_selected!.code}'),
                    ),
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
                    if (_canAssignCustomers)
                      OutlinedButton.icon(
                        onPressed: () => _setCallOrder(_selected!),
                        icon: const Icon(Icons.format_list_numbered),
                        label: const Text('Call order'),
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
    required this.api,
    required this.territory,
    required this.hierarchy,
    required this.items,
    required this.routeTypes,
    this.initialParentId,
  });

  /// Needed for the geography ladder, which is loaded a level at a time as the
  /// user picks: every postal code in the country is not a useful dropdown.
  final ApiClient api;
  final SalesTerritory? territory;
  final TerritoryHierarchyRecord? hierarchy;
  final List<SalesTerritory> items;
  final String? initialParentId;

  /// The kinds of round this firm runs. A territory that is not a round
  /// leaves these blank — the API takes no route profile then.
  final List<TerritoryRouteTypeRecord> routeTypes;

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

  /// Whether this node is a round a salesperson walks, rather than a region or
  /// a zone. Held as an explicit switch, not inferred from whether the fields
  /// below happen to be filled: the API deletes the route profile when the
  /// payload omits it, so a route whose type was never chosen would lose its
  /// frequency and working days the next time somebody renamed it.
  late bool _isRoute = widget.territory?.routeProfile != null;
  // Shown and editable now that the server reads them: a round is only called
  // between these dates, so a window nobody could see would silently stop a
  // route running.
  late String _effectiveFrom = widget.territory?.routeProfile?.effectiveFrom ?? '';
  late String _effectiveTo = widget.territory?.routeProfile?.effectiveTo ?? '';

  // The area a round covers. These three columns have existed on the route
  // profile from the first migration and no screen ever set one, so the
  // `city_id` and `locality_id` filters on the territory list -- both
  // implemented server-side -- could never match anything.
  late String _cityId = widget.territory?.routeProfile?.cityId ?? '';
  late String _postalCodeId = widget.territory?.routeProfile?.postalCodeId ?? '';
  late String _localityId = widget.territory?.routeProfile?.localityId ?? '';

  List<GeoPlaceRecord> _cities = const [];
  List<GeoPlaceRecord> _postalCodes = const [];
  List<GeoPlaceRecord> _localities = const [];
  late String? _routeTypeId = _initialRouteTypeId();
  late String _visitFrequency = _initialVisitFrequency();
  late final Set<int> _workingDays = <int>{
    ...?widget.territory?.routeProfile?.workingDays,
  };

  /// Only pre-select a type the list still offers — a removed one would leave
  /// the dropdown holding a value with no matching item, which asserts.
  String? _initialRouteTypeId() {
    final String existing = widget.territory?.routeProfile?.routeTypeId ?? '';
    return widget.routeTypes.any((type) => type.id == existing)
        ? existing
        : null;
  }

  String _initialVisitFrequency() {
    final String existing =
        widget.territory?.routeProfile?.visitFrequency ?? '';
    return _frequencies.contains(existing) ? existing : 'ON_DEMAND';
  }

  late String? _levelId = widget.territory?.hierarchyLevelId;
  late String? _parentId = widget.territory?.parentId.isEmpty == true
      ? (widget.initialParentId?.isEmpty == true
          ? null
          : widget.initialParentId)
      : widget.territory?.parentId;

  @override
  void initState() {
    super.initState();
    _loadArea();
  }

  /// Load the ladder down to whatever the route already names.
  ///
  /// Geography reads need `TERRITORY_VIEW`, which anyone opening this editor
  /// holds. A firm whose administrator has not populated Places gets empty
  /// dropdowns and a route that still saves -- the area is optional.
  Future<void> _loadArea() async {
    try {
      final List<GeoPlaceRecord> cities =
          await widget.api.geoPlaces(GeoLevel.city);
      final List<GeoPlaceRecord> postalCodes = _cityId.isEmpty
          ? const <GeoPlaceRecord>[]
          : await widget.api.geoPlaces(GeoLevel.postalCode, parentId: _cityId);
      final List<GeoPlaceRecord> localities = _postalCodeId.isEmpty
          ? const <GeoPlaceRecord>[]
          : await widget.api
              .geoPlaces(GeoLevel.locality, parentId: _postalCodeId);
      if (!mounted) return;
      setState(() {
        _cities = cities;
        _postalCodes = postalCodes;
        _localities = localities;
      });
    } on ApiException {
      // The area is optional and the route saves without it, so a geography
      // read that fails costs three dropdowns rather than the editor.
    }
  }

  /// Options for one rung of the area ladder.
  ///
  /// A stored id that is not in the loaded list gets an entry of its own.
  /// `DropdownButtonFormField` asserts when its value matches no item, so a
  /// route tagged with a city the reader cannot see — geography read failed,
  /// or the city was retired — would otherwise break the whole editor. Keeping
  /// it also means saving does not quietly clear a tag nobody could see.
  List<DropdownMenuItem<String>> _areaItems(
    List<GeoPlaceRecord> rows,
    String currentId, {
    bool useCode = false,
  }) =>
      <DropdownMenuItem<String>>[
        const DropdownMenuItem<String>(value: '', child: Text('None')),
        for (final GeoPlaceRecord row in rows)
          DropdownMenuItem<String>(
            value: row.id,
            child: Text(useCode ? row.code : row.name),
          ),
        if (currentId.isNotEmpty && !rows.any((row) => row.id == currentId))
          DropdownMenuItem<String>(
            value: currentId,
            child: const Text('Currently set (not listed)'),
          ),
      ];

  Future<void> _pickCity(String? value) async {
    setState(() {
      _cityId = value ?? '';
      _postalCodeId = '';
      _localityId = '';
      _postalCodes = const [];
      _localities = const [];
    });
    if (_cityId.isEmpty) return;
    try {
      final List<GeoPlaceRecord> rows =
          await widget.api.geoPlaces(GeoLevel.postalCode, parentId: _cityId);
      if (!mounted) return;
      setState(() => _postalCodes = rows);
    } on ApiException {
      // Same reasoning as `_loadArea`.
    }
  }

  Future<void> _pickPostalCode(String? value) async {
    setState(() {
      _postalCodeId = value ?? '';
      _localityId = '';
      _localities = const [];
    });
    if (_postalCodeId.isEmpty) return;
    try {
      final List<GeoPlaceRecord> rows =
          await widget.api.geoPlaces(GeoLevel.locality, parentId: _postalCodeId);
      if (!mounted) return;
      setState(() => _localities = rows);
    } on ApiException {
      // Same reasoning as `_loadArea`.
    }
  }

  @override
  void dispose() {
    _code.dispose();
    _name.dispose();
    _description.dispose();
    super.dispose();
  }

  static const List<String> _frequencies = <String>[
    'DAILY',
    'WEEKLY',
    'FORTNIGHTLY',
    'MONTHLY',
    'QUARTERLY',
    'ON_DEMAND',
  ];

  /// ISO weekday numbering, which is what the API validates against (1-7).
  static const List<String> _weekdayNames = <String>[
    'Mon',
    'Tue',
    'Wed',
    'Thu',
    'Fri',
    'Sat',
    'Sun',
  ];

  List<Widget> _routeFields(BuildContext context) => <Widget>[
        DropdownButtonFormField<String?>(
          isExpanded: true,
          initialValue: _routeTypeId,
          decoration: InputDecoration(
            labelText: 'Route type',
            // No screen creates route types yet — the API has a POST but
            // nothing in this client calls it — so the message says the route
            // still saves rather than pointing at a door that is not there.
            helperText: widget.routeTypes.isEmpty
                ? 'None defined for this firm — a route saves without one'
                : null,
          ),
          items: <DropdownMenuItem<String?>>[
            const DropdownMenuItem<String?>(value: null, child: Text('None')),
            for (final TerritoryRouteTypeRecord type in widget.routeTypes)
              DropdownMenuItem<String?>(
                value: type.id,
                child: Text('${type.code} - ${type.name}'),
              ),
          ],
          onChanged: (value) => setState(() => _routeTypeId = value),
        ),
        const SizedBox(height: 8),
        DropdownButtonFormField<String>(
          isExpanded: true,
          initialValue: _visitFrequency,
          decoration: const InputDecoration(labelText: 'Visit frequency'),
          items: <DropdownMenuItem<String>>[
            for (final String frequency in _frequencies)
              DropdownMenuItem<String>(
                value: frequency,
                child: Text(_titleCase(frequency)),
              ),
          ],
          onChanged: (value) =>
              setState(() => _visitFrequency = value ?? 'ON_DEMAND'),
        ),
        const SizedBox(height: 8),
        // Where the round is. Cascading, because a flat locality list would be
        // every locality in the country.
        DropdownButtonFormField<String>(
          isExpanded: true,
          initialValue: _cityId.isEmpty ? '' : _cityId,
          decoration: InputDecoration(
            labelText: 'City',
            helperText: _cities.isEmpty
                ? 'No cities defined — a platform administrator maintains these '
                    'under Places. The route saves without one.'
                : 'Lets this round be found by area on the grid.',
          ),
          items: _areaItems(_cities, _cityId),
          onChanged: _pickCity,
        ),
        const SizedBox(height: 8),
        Row(
          children: [
            Expanded(
              child: DropdownButtonFormField<String>(
                isExpanded: true,
                initialValue: _postalCodeId.isEmpty ? '' : _postalCodeId,
                decoration: const InputDecoration(labelText: 'Pin code'),
                items: _areaItems(_postalCodes, _postalCodeId, useCode: true),
                onChanged: _cityId.isEmpty ? null : _pickPostalCode,
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: DropdownButtonFormField<String>(
                isExpanded: true,
                initialValue: _localityId.isEmpty ? '' : _localityId,
                decoration: const InputDecoration(labelText: 'Locality'),
                items: _areaItems(_localities, _localityId),
                onChanged: _postalCodeId.isEmpty
                    ? null
                    : (value) => setState(() => _localityId = value ?? ''),
              ),
            ),
          ],
        ),
        const SizedBox(height: 8),
        Row(
          children: [
            Expanded(
              child: _DateField(
                label: 'Runs from',
                value: _effectiveFrom,
                helperText: 'Blank means it has always run.',
                onChanged: (value) => setState(() => _effectiveFrom = value),
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: _DateField(
                label: 'Runs until',
                value: _effectiveTo,
                helperText: 'Blank means it has no end.',
                onChanged: (value) => setState(() => _effectiveTo = value),
              ),
            ),
          ],
        ),
        const SizedBox(height: 12),
        Align(
          alignment: Alignment.centerLeft,
          child: Text(
            'Working days',
            style: Theme.of(context).textTheme.labelLarge,
          ),
        ),
        const SizedBox(height: 4),
        Wrap(
          spacing: 6,
          children: <Widget>[
            for (int weekday = 1; weekday <= 7; weekday++)
              FilterChip(
                label: Text(_weekdayNames[weekday - 1]),
                selected: _workingDays.contains(weekday),
                onSelected: (selected) => setState(() {
                  if (selected) {
                    _workingDays.add(weekday);
                  } else {
                    _workingDays.remove(weekday);
                  }
                }),
              ),
          ],
        ),
        const SizedBox(height: 4),
        Align(
          alignment: Alignment.centerLeft,
          child: Text(
            _workingDays.isEmpty
                ? 'No days chosen — the route runs on no fixed day.'
                : 'Runs on ${_workingDays.length} day(s) a week.',
            style: Theme.of(context).textTheme.bodySmall,
          ),
        ),
      ];

  /// The profile is replaced whole, so the fields this form does not show
  /// have to be carried back or they are cleared. Effective dates and the
  /// city/postal/locality links are set elsewhere and would otherwise be lost
  /// the first time somebody changed a route's working days.
  Json _routeProfilePayload() {
    return <String, dynamic>{
      'route_type_id': _routeTypeId,
      'visit_frequency': _visitFrequency,
      'working_days': _workingDays.toList()..sort(),
      'effective_from': _orNull(_effectiveFrom),
      'effective_to': _orNull(_effectiveTo),
      'city_id': _orNull(_cityId),
      'postal_code_id': _orNull(_postalCodeId),
      'locality_id': _orNull(_localityId),
    };
  }

  static String? _orNull(String? value) =>
      (value == null || value.isEmpty) ? null : value;

  static String _titleCase(String code) => code
      .split('_')
      .map((word) =>
          word.isEmpty ? word : '${word[0]}${word.substring(1).toLowerCase()}')
      .join(' ');

  @override
  Widget build(BuildContext context) => AlertDialog(
        title:
            Text(widget.territory == null ? 'New territory' : 'Edit territory'),
        content: SizedBox(
          width: 560,
          // Scrolls because the route fields push this past the height of a
          // 1366x768 screen once they are showing.
          height: 520,
          child: Form(
            key: _form,
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  TextFormField(
                    controller: _code,
                    decoration: const InputDecoration(labelText: 'Code'),
                    validator: (value) =>
                        (value == null || value.trim().isEmpty)
                            ? 'Code is required'
                            : null,
                  ),
                  const SizedBox(height: 8),
                  TextFormField(
                    controller: _name,
                    decoration: const InputDecoration(labelText: 'Name'),
                    validator: (value) =>
                        (value == null || value.trim().isEmpty)
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
                  const Divider(height: 32),
                  SwitchListTile(
                    contentPadding: EdgeInsets.zero,
                    value: _isRoute,
                    title: const Text('This is a route'),
                    subtitle: const Text(
                      'A round somebody walks — sales or collection. Regions and '
                      'zones leave this off.',
                    ),
                    onChanged: (value) => setState(() => _isRoute = value),
                  ),
                  if (_isRoute) ..._routeFields(context),
                ],
              ),
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
                  // Omitted for a region or a zone, which the API reads as
                  // "this is not a round" and retires any profile it had.
                  if (_isRoute) 'route_profile': _routeProfilePayload(),
                },
              );
            },
            child: const Text('Save'),
          ),
        ],
      );
}

/// One end of a route's effective window.
///
/// A plain read-only field with a picker rather than a text box: the API takes
/// an ISO date and a typo is refused with a validation error that names a
/// field, not a format.
class _DateField extends StatelessWidget {
  const _DateField({
    required this.label,
    required this.value,
    required this.onChanged,
    this.helperText,
  });

  final String label;
  final String value;
  final ValueChanged<String> onChanged;
  final String? helperText;

  @override
  Widget build(BuildContext context) => InkWell(
        onTap: () async {
          final DateTime initial =
              DateTime.tryParse(value) ?? DateTime.now();
          final DateTime? picked = await showDatePicker(
            context: context,
            initialDate: initial,
            firstDate: DateTime(initial.year - 5),
            lastDate: DateTime(initial.year + 5),
          );
          if (picked == null) return;
          onChanged(
            '${picked.year.toString().padLeft(4, '0')}-'
            '${picked.month.toString().padLeft(2, '0')}-'
            '${picked.day.toString().padLeft(2, '0')}',
          );
        },
        child: InputDecorator(
          decoration: InputDecoration(
            labelText: label,
            helperText: helperText,
            suffixIcon: value.isEmpty
                ? const Icon(Icons.event, size: 18)
                : IconButton(
                    tooltip: 'Clear',
                    icon: const Icon(Icons.close, size: 18),
                    onPressed: () => onChanged(''),
                  ),
          ),
          child: Text(value.isEmpty ? 'Any date' : value),
        ),
      );
}
