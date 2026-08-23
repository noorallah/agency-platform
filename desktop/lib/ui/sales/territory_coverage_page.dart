import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/security/permission_service.dart';
import '../../models/sales_territory.dart';
import '../../models/firm_member.dart';
import '../workspace/desktop_framework.dart';

/// How much ground each salesperson covers.
///
/// `GET /coverage/salesmen` has answered this since the module was written and
/// nothing called it, so the one question a sales manager asks first — who is
/// carrying how much, and who is carrying nothing — had no screen.
///
/// Read-only. Coverage is a consequence of the assignments made on Geography,
/// not something to edit here.
class TerritoryCoveragePage extends StatefulWidget {
  const TerritoryCoveragePage({
    super.key,
    required this.api,
    required this.permissions,
  });

  final ApiClient api;
  final PermissionService permissions;

  @override
  State<TerritoryCoveragePage> createState() => _TerritoryCoveragePageState();
}

class _TerritoryCoveragePageState extends State<TerritoryCoveragePage> {
  final TextEditingController _search = TextEditingController();
  final FocusNode _searchFocus = FocusNode();

  List<TerritoryCoverageRecord> _rows = const [];
  Map<String, FirmMember> _people = const {};
  bool _loading = false;
  String? _error;

  bool get _canView => widget.permissions.hasPermission('TERRITORY_VIEW');

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _search.dispose();
    _searchFocus.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    if (!_canView) {
      setState(() => _error = 'You do not have permission to view routes.');
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final List<TerritoryCoverageRecord> rows =
          await widget.api.territoryCoverage();
      // The coverage rows carry user ids. Names come from the candidate list,
      // which reads `users` through the platform store — the tenant session
      // cannot see that table at all.
      final List<FirmMember> people =
          await widget.api.firmMembers();
      if (!mounted) return;
      setState(() {
        _rows = rows;
        _people = {for (final person in people) person.userId: person};
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

  String _name(String userId) {
    final FirmMember? person = _people[userId];
    if (person == null) return userId;
    return person.fullName.isEmpty ? person.email : person.fullName;
  }

  List<TerritoryCoverageRecord> get _visible {
    final String term = _search.text.trim().toLowerCase();
    if (term.isEmpty) return _rows;
    return _rows
        .where((row) => _name(row.userId).toLowerCase().contains(term))
        .toList();
  }

  @override
  Widget build(BuildContext context) {
    final List<TerritoryCoverageRecord> rows = _visible;
    final int uncovered = _rows.where((row) => row.assignedRoutes == 0).length;

    final Widget toolbar = WorkspaceToolbar(
      actions: const [ToolbarAction.refresh],
      isEnabled: (action) => action == ToolbarAction.refresh,
      onAction: (action) {
        if (action == ToolbarAction.refresh) _load();
      },
    );

    final Widget searchPanel = SearchFilterPanel(
      controller: _search,
      focusNode: _searchFocus,
      hintText: 'Search salespeople by name',
      onSearch: (_) => setState(() {}),
      onChanged: (_) => setState(() {}),
      onClear: () => setState(() {}),
    );

    final Widget content = _error != null
        ? WorkspaceErrorState(message: _error!, onRetry: _load)
        : _loading && _rows.isEmpty
            ? const TableLoadingSkeleton()
            : rows.isEmpty
                ? const StandardEmptyState(
                    type: EmptyStateType.noRecords,
                    title: 'Nobody is on a territory yet',
                    message: 'Assign salespeople to a route on Geography and '
                        'their coverage appears here.',
                  )
                : LoadingOverlay(
                    loading: _loading,
                    child: EnterpriseDataGrid<TerritoryCoverageRecord>(
                      items: rows,
                      total: rows.length,
                      pageOffset: 0,
                      rowsPerPage: rows.length,
                      columns: const [
                        GridColumn(key: 'name', label: 'Salesperson'),
                        GridColumn(key: 'territories', label: 'Territories'),
                        GridColumn(key: 'routes', label: 'Routes'),
                        GridColumn(key: 'customers', label: 'Customers'),
                        GridColumn(key: 'coverage', label: 'Coverage'),
                      ],
                      id: (row) => row.userId,
                      cells: (row) => [
                        _name(row.userId),
                        '${row.assignedTerritories}',
                        '${row.assignedRoutes}',
                        '${row.customerCount}',
                        '${row.coveragePercent.toStringAsFixed(1)}%',
                      ],
                      onSelect: (_) {},
                      onPageChanged: (_) {},
                    ),
                  );

    return ManagementWorkspaceLayout(
      toolbar: toolbar,
      searchPanel: searchPanel,
      primaryContent: content,
      statusBar: WorkspaceStatusBar(
        total: rows.length,
        selected: false,
        message: _loading
            ? 'Refreshing coverage...'
            : uncovered == 0
                ? 'Everyone assigned here carries at least one route.'
                : '$uncovered person(s) carry no route at all.',
      ),
    );
  }
}
