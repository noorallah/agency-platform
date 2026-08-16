import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/entities.dart';
import '../../models/sales_territory.dart';
import '../workspace/desktop_framework.dart';

/// Build a round the way a supervisor actually builds one: walk a pin code,
/// tick the shops on it, then put them in the order they get called.
///
/// The customer picker on Geography answers "which of my customers is this",
/// by name. That is the wrong question for laying out a beat — a beat follows
/// a street, and the person building it knows the area, not the account codes.
/// It also could not tell you which outlets were on no round at all, which is
/// exactly the gap you are trying to close.
///
/// Assign and order are one screen rather than two dialogs because they are
/// one act: the shops you just picked have no place in the round until you say
/// where they go, and a separate ordering step is one you can forget.
class RouteBuilderPage extends StatefulWidget {
  const RouteBuilderPage({
    super.key,
    required this.api,
    required this.permissions,
  });

  final ApiClient api;
  final PermissionService permissions;

  @override
  State<RouteBuilderPage> createState() => _RouteBuilderPageState();
}

class _RouteBuilderPageState extends State<RouteBuilderPage> {
  final TextEditingController _search = TextEditingController();
  final TextEditingController _postalCode = TextEditingController();
  final TextEditingController _area = TextEditingController();
  final FocusNode _searchFocus = FocusNode();

  List<SalesTerritory> _routes = const [];
  String? _routeId;
  bool _unassignedOnly = false;

  List<AssignableCustomerRecord> _found = const [];
  int _total = 0;
  int _page = 1;
  static const int _rowsPerPage = 50;

  /// The round as it will be saved: order is position in this list.
  final List<AssignableCustomerRecord> _round = <AssignableCustomerRecord>[];

  /// The route whose membership `_round` actually holds.
  ///
  /// Saving **replaces** the round with this panel, so the panel has to be the
  /// truth about the selected route or the save destroys it. Tracked rather
  /// than assumed: if the load fails, this stays behind `_routeId` and Save is
  /// refused, instead of writing the previous route's shops onto this one.
  String? _loadedRouteId;

  bool get _roundIsLoaded => _loadedRouteId != null && _loadedRouteId == _routeId;

  bool _loading = false;
  bool _saving = false;
  String? _error;

  bool get _canView => widget.permissions.hasPermission('TERRITORY_VIEW');
  bool get _canAssign =>
      widget.permissions.hasPermission('TERRITORY_ASSIGN_CUSTOMERS');

  SalesTerritory? get _route =>
      _routes.where((item) => item.id == _routeId).firstOrNull;

  @override
  void initState() {
    super.initState();
    _loadRoutes();
  }

  @override
  void dispose() {
    _search.dispose();
    _postalCode.dispose();
    _area.dispose();
    _searchFocus.dispose();
    super.dispose();
  }

  /// Only nodes carrying a route profile: a beat is laid out on a round, and
  /// the customers a plan calls are the ones assigned to one.
  Future<void> _loadRoutes() async {
    if (!_canView) {
      setState(() => _error = 'You do not have permission to view routes.');
      return;
    }
    try {
      final PagedResult<SalesTerritory> page =
          await widget.api.territories(page: 1, pageSize: 100);
      if (!mounted) return;
      setState(() {
        _routes = page.items
            .where((item) => item.routeProfile != null && !item.isDeleted)
            .toList();
      });
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() => _error = exception.message);
    }
  }

  /// Load the round's current members, in their saved call order.
  Future<void> _loadRound() async {
    final String? id = _routeId;
    if (id == null) return;
    setState(() {
      // Dropped before the request, not after it succeeds: a panel still
      // showing the last route's shops is the one thing Save must never see.
      _round.clear();
      _loadedRouteId = null;
      _loading = true;
    });
    try {
      // Paged, not one oversized request: the server refuses anything above
      // `maxApiPageSize`, so asking for 500 failed every time and left the
      // panel unloaded -- which the save guard then correctly refused to
      // write over.
      final List<AssignableCustomerRecord> rows =
          await fetchAllPages<AssignableCustomerRecord>(
        (page) => widget.api.assignableCustomers(
          page: page,
          pageSize: maxApiPageSize,
          territoryId: id,
        ),
      );
      if (!mounted) return;
      final List<AssignableCustomerRecord> current = rows
          .where((row) => row.onThisRoute)
          .toList()
        // The server orders unplaced customers last; within the placed ones the
        // sequence is what the round is walked in.
        ..sort((a, b) =>
            (a.visitSequence ?? 1 << 30).compareTo(b.visitSequence ?? 1 << 30));
      setState(() {
        _round
          ..clear()
          ..addAll(current);
        _loadedRouteId = id;
        _loading = false;
      });
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() {
        _error = exception.message;
        _loading = false;
      });
    }
  }

  Future<void> _find({int requestedPage = 1}) async {
    if (!_canView) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final PagedResult<AssignableCustomerRecord> page =
          await widget.api.assignableCustomers(
        page: requestedPage,
        pageSize: _rowsPerPage,
        territoryId: _routeId ?? '',
        search: _search.text.trim(),
        postalCode: _postalCode.text.trim(),
        area: _area.text.trim(),
        unassignedOnly: _unassignedOnly,
      );
      if (!mounted) return;
      setState(() {
        _found = page.items;
        _total = page.total;
        _page = requestedPage;
        _loading = false;
      });
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() {
        _error = exception.message;
        _loading = false;
      });
    }
  }

  void _addToRound(AssignableCustomerRecord row) {
    if (_round.any((item) => item.customerId == row.customerId)) return;
    setState(() => _round.add(row));
  }

  void _addAllFound() {
    setState(() {
      for (final AssignableCustomerRecord row in _found) {
        if (!_round.any((item) => item.customerId == row.customerId)) {
          _round.add(row);
        }
      }
    });
  }

  Future<void> _save() async {
    final String? id = _routeId;
    if (id == null || !_canAssign || !_roundIsLoaded) return;
    setState(() => _saving = true);
    try {
      // One request carries both the membership and the order: the API replaces
      // the whole list, and `visit_sequence` is position in that list. Saving
      // them separately would leave a window where the round exists with no
      // order at all.
      await widget.api.setTerritoryCustomers(id, [
        for (int index = 0; index < _round.length; index++)
          TerritoryCustomerAssignmentRecord(
            customerId: _round[index].customerId,
            isPrimary: true,
            visitSequence: index + 1,
            isPotential: false,
          ),
      ]);
      if (!mounted) return;
      setState(() => _saving = false);
      NotificationService.show(
        context,
        '${_round.length} outlet(s) on ${_route?.name ?? 'the route'}, in order.',
        kind: AppNotificationKind.success,
      );
      await _find(requestedPage: _page);
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() => _saving = false);
      NotificationService.show(
        context,
        exception.message,
        kind: AppNotificationKind.error,
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);

    final Widget toolbar = WorkspaceToolbar(
      actions: const [ToolbarAction.refresh],
      isEnabled: (action) => action == ToolbarAction.refresh,
      onAction: (action) {
        if (action == ToolbarAction.refresh) _find(requestedPage: _page);
      },
      trailing: [
        SizedBox(
          width: 280,
          child: DropdownButtonFormField<String>(
            initialValue: _routeId,
            isExpanded: true,
            decoration: const InputDecoration(
              labelText: 'Route being built',
              isDense: true,
            ),
            items: [
              for (final SalesTerritory route in _routes)
                DropdownMenuItem<String>(
                  value: route.id,
                  child: Text('${route.code} - ${route.name}'),
                ),
            ],
            onChanged: (value) {
              setState(() => _routeId = value);
              _loadRound();
              _find();
            },
          ),
        ),
      ],
    );

    final Widget searchPanel = SearchFilterPanel(
      controller: _search,
      focusNode: _searchFocus,
      hintText: 'Search outlets by name or code',
      onSearch: (_) => _find(),
      onClear: () => _find(),
      filters: [
        SizedBox(
          width: 150,
          child: TextField(
            controller: _postalCode,
            decoration: const InputDecoration(
              labelText: 'Pin code',
              isDense: true,
            ),
            onSubmitted: (_) => _find(),
          ),
        ),
        SizedBox(
          width: 200,
          child: TextField(
            controller: _area,
            decoration: const InputDecoration(
              labelText: 'Street / area',
              isDense: true,
            ),
            onSubmitted: (_) => _find(),
          ),
        ),
        FilterChip(
          label: const Text('On no route yet'),
          selected: _unassignedOnly,
          onSelected: (value) {
            setState(() => _unassignedOnly = value);
            _find();
          },
        ),
        FilledButton.icon(
          onPressed: () => _find(),
          icon: const Icon(Icons.search),
          label: const Text('Find'),
        ),
      ],
    );

    final Widget results = _error != null
        ? WorkspaceErrorState(message: _error!, onRetry: () => _find())
        : _found.isEmpty
            ? const StandardEmptyState(
                type: EmptyStateType.noRecords,
                title: 'No outlets found',
                message: 'Search by pin code or street to find the shops on a '
                    'round, then add them in the order you call them.',
              )
            : EnterpriseDataGrid<AssignableCustomerRecord>(
                items: _found,
                total: _total,
                pageOffset: (_page - 1) * _rowsPerPage,
                rowsPerPage: _rowsPerPage,
                columns: const [
                  GridColumn(key: 'code', label: 'Code'),
                  GridColumn(key: 'name', label: 'Outlet'),
                  GridColumn(key: 'address', label: 'Address'),
                  GridColumn(key: 'area', label: 'Street / area'),
                  GridColumn(key: 'pin', label: 'Pin code'),
                  GridColumn(key: 'routes', label: 'Already on'),
                ],
                id: (row) => row.customerId,
                cells: (row) => [
                  row.code,
                  row.name,
                  row.addressLine,
                  row.area,
                  row.postalCode,
                  row.onThisRoute
                      ? 'This route'
                      : row.otherRoutes.isEmpty
                          ? '-'
                          : row.otherRoutes.join(', '),
                ],
                onSelect: (_) {},
                // Double-click adds, which is the fastest way to walk a list.
                onOpen: _addToRound,
                onPageChanged: (offset) =>
                    _find(requestedPage: offset ~/ _rowsPerPage + 1),
              );

    final Widget roundPanel = Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Padding(
          padding: const EdgeInsets.all(12),
          child: Row(
            children: [
              Expanded(
                child: Text(
                  _route == null
                      ? 'Pick a route'
                      : '${_route!.code} — ${_round.length} stop(s)',
                  style: theme.textTheme.titleSmall,
                ),
              ),
              if (_found.isNotEmpty && _routeId != null)
                TextButton(
                  onPressed: _addAllFound,
                  child: const Text('Add all found'),
                ),
            ],
          ),
        ),
        const Divider(height: 1),
        Expanded(
          child: _routeId == null
              ? const Center(child: Text('Choose the route to build.'))
              : !_roundIsLoaded
                  ? const Center(
                      child: Padding(
                        padding: EdgeInsets.all(16),
                        child: Text(
                          'This round could not be read, so it cannot be '
                          'saved over. Refresh to try again.',
                          textAlign: TextAlign.center,
                        ),
                      ),
                    )
                  : _round.isEmpty
                  ? const Center(
                      child: Padding(
                        padding: EdgeInsets.all(16),
                        child: Text(
                          'Nobody on this round yet. Double-click an outlet on '
                          'the left to add it.',
                          textAlign: TextAlign.center,
                        ),
                      ),
                    )
                  : ReorderableListView.builder(
                      buildDefaultDragHandles: false,
                      itemCount: _round.length,
                      onReorderItem: (oldIndex, newIndex) => setState(() {
                        _round.insert(newIndex, _round.removeAt(oldIndex));
                      }),
                      itemBuilder: (context, index) {
                        final AssignableCustomerRecord row = _round[index];
                        return ListTile(
                          key: ValueKey<String>(row.customerId),
                          dense: true,
                          leading: CircleAvatar(
                            radius: 13,
                            child: Text(
                              '${index + 1}',
                              style: theme.textTheme.labelSmall,
                            ),
                          ),
                          title: Text(
                            row.name,
                            overflow: TextOverflow.ellipsis,
                          ),
                          subtitle: Text('${row.area} · ${row.postalCode}'),
                          trailing: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              IconButton(
                                tooltip: 'Remove from round',
                                icon: const Icon(Icons.close, size: 18),
                                onPressed: () =>
                                    setState(() => _round.removeAt(index)),
                              ),
                              ReorderableDragStartListener(
                                index: index,
                                child: const Icon(Icons.drag_handle),
                              ),
                            ],
                          ),
                        );
                      },
                    ),
        ),
        const Divider(height: 1),
        Padding(
          padding: const EdgeInsets.all(12),
          child: FilledButton.icon(
            onPressed: _saving || !_canAssign || !_roundIsLoaded ? null : _save,
            icon: const Icon(Icons.save_outlined),
            label: Text(_saving ? 'Saving...' : 'Save round and order'),
          ),
        ),
      ],
    );

    return ManagementWorkspaceLayout(
      toolbar: toolbar,
      searchPanel: searchPanel,
      primaryContent: LoadingOverlay(loading: _loading, child: results),
      detailsPanel: roundPanel,
      detailsWidth: 360,
      statusBar: WorkspaceStatusBar(
        total: _total,
        selected: _round.isNotEmpty,
        message: _canAssign
            ? 'Saving replaces the whole round with the list on the right.'
            : 'Read-only — you cannot assign customers to a route.',
      ),
    );
  }
}
