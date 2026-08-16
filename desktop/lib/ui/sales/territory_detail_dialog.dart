import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/entities.dart';
import '../../models/sales_territory.dart';
import '../workspace/desktop_framework.dart';

/// Everything about one territory, with room to work in.
///
/// The right-hand card on Geography was doing three jobs in 300 pixels: a
/// summary of the selected node, the controls for the tree, and the tree
/// itself. The summary moves here, where a route's details, its outlets and its
/// salespeople each get a tab.
///
/// The point of the Customers tab is that a round is **drawn**, not assembled
/// and then sorted. Clicking an outlet appends it as the next stop — first is
/// START, last is END — so the order is the act of choosing rather than a
/// second dialog you can forget to open.
class TerritoryDetailDialog extends StatefulWidget {
  const TerritoryDetailDialog({
    super.key,
    required this.api,
    required this.permissions,
    required this.territory,
  });

  final ApiClient api;
  final PermissionService permissions;
  final SalesTerritory territory;

  @override
  State<TerritoryDetailDialog> createState() => _TerritoryDetailDialogState();
}

class _TerritoryDetailDialogState extends State<TerritoryDetailDialog> {
  final TextEditingController _search = TextEditingController();

  int _tab = 0;
  bool _loading = false;
  bool _saving = false;
  String? _error;

  List<AssignableCustomerRecord> _outlets = const [];

  /// The round in the order it is walked. Position is the stop number.
  final List<AssignableCustomerRecord> _path = <AssignableCustomerRecord>[];

  /// The territory whose round `_path` actually holds.
  ///
  /// Saving **replaces** the whole list, so the pane has to be the truth about
  /// this territory or the save destroys it. Tracked rather than assumed: a
  /// read that failed leaves this null and Save refused, instead of an empty
  /// path that looks like a round waiting to be filled.
  String? _loadedFor;

  bool get _pathIsLoaded => _loadedFor == widget.territory.id;

  List<Json> _salesmen = const [];
  Set<String> _chosenSalesmen = <String>{};
  List<TerritorySalesmanCandidate> _candidates = const [];
  bool _salesmenLoaded = false;

  bool get _canAssignCustomers =>
      widget.permissions.hasPermission('TERRITORY_ASSIGN_CUSTOMERS');
  bool get _canAssignSalesmen =>
      widget.permissions.hasPermission('TERRITORY_ASSIGN_SALESMEN');

  @override
  void initState() {
    super.initState();
    _loadOutlets();
  }

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  Future<void> _loadOutlets() async {
    setState(() {
      // Dropped before the request, not after it succeeds.
      _path.clear();
      _loadedFor = null;
      _loading = true;
      _error = null;
    });
    try {
      final PagedResult<AssignableCustomerRecord> page =
          await widget.api.assignableCustomers(
        page: 1,
        pageSize: 500,
        territoryId: widget.territory.id,
      );
      if (!mounted) return;
      final List<AssignableCustomerRecord> current =
          page.items.where((row) => row.onThisRoute).toList()
            ..sort((a, b) => (a.visitSequence ?? 1 << 30)
                .compareTo(b.visitSequence ?? 1 << 30));
      setState(() {
        _outlets = page.items;
        _path
          ..clear()
          ..addAll(current);
        _loadedFor = widget.territory.id;
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

  Future<void> _loadSalesmen() async {
    if (_salesmenLoaded) return;
    setState(() => _loading = true);
    try {
      final List<Json> current =
          await widget.api.territorySalesmen(widget.territory.id);
      final List<TerritorySalesmanCandidate> candidates =
          await widget.api.territorySalesmanCandidates();
      if (!mounted) return;
      setState(() {
        _salesmen = current;
        _candidates = candidates;
        _chosenSalesmen = {
          for (final Json row in current) stringValue(row['user_id']),
        }..removeWhere((id) => id.isEmpty);
        _salesmenLoaded = true;
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

  /// Append an outlet as the next stop, or take it off and close the gap.
  void _toggleStop(AssignableCustomerRecord row) {
    if (!_canAssignCustomers) return;
    setState(() {
      final int at =
          _path.indexWhere((item) => item.customerId == row.customerId);
      if (at >= 0) {
        _path.removeAt(at);
      } else {
        _path.add(row);
      }
    });
  }

  int? _stopNumber(String customerId) {
    final int at = _path.indexWhere((item) => item.customerId == customerId);
    return at < 0 ? null : at + 1;
  }

  List<AssignableCustomerRecord> get _visibleOutlets {
    final String term = _search.text.trim().toLowerCase();
    if (term.isEmpty) return _outlets;
    return _outlets
        .where((row) =>
            row.name.toLowerCase().contains(term) ||
            row.code.toLowerCase().contains(term) ||
            row.area.toLowerCase().contains(term) ||
            row.postalCode.toLowerCase().contains(term))
        .toList();
  }

  Future<void> _save() async {
    if (_saving) return;
    if (_tab == 1) {
      if (!_canAssignCustomers || !_pathIsLoaded) return;
      await _saveCustomers();
    } else if (_tab == 2) {
      if (!_canAssignSalesmen || !_salesmenLoaded) return;
      await _saveSalesmen();
    }
  }

  Future<void> _saveCustomers() async {
    setState(() => _saving = true);
    try {
      // Membership and order in one request: the API replaces the whole list
      // and `visit_sequence` is position in it, so they cannot be sent apart.
      await widget.api.setTerritoryCustomers(widget.territory.id, [
        for (int index = 0; index < _path.length; index++)
          TerritoryCustomerAssignmentRecord(
            customerId: _path[index].customerId,
            isPrimary: true,
            visitSequence: index + 1,
            isPotential: false,
          ),
      ]);
      if (!mounted) return;
      setState(() => _saving = false);
      NotificationService.show(
        context,
        '${_path.length} stop(s) on ${widget.territory.name}, in order.',
        kind: AppNotificationKind.success,
      );
      Navigator.pop(context, true);
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

  Future<void> _saveSalesmen() async {
    setState(() => _saving = true);
    try {
      // The API replaces the whole list, so an existing assignment's flags are
      // carried back. Sending only ids silently demotes the primary and drops
      // whoever covered the child territories.
      final Map<String, Json> existing = <String, Json>{
        for (final Json row in _salesmen) stringValue(row['user_id']): row,
      };
      await widget.api.setTerritorySalesmen(widget.territory.id, [
        for (final String userId in _chosenSalesmen)
          <String, dynamic>{
            'user_id': userId,
            'is_primary': existing[userId]?['is_primary'] == true,
            'include_children': existing[userId]?['include_children'] == true,
          },
      ]);
      if (!mounted) return;
      setState(() => _saving = false);
      NotificationService.show(
        context,
        '${_chosenSalesmen.length} salesperson(s) on ${widget.territory.name}.',
        kind: AppNotificationKind.success,
      );
      Navigator.pop(context, true);
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

  bool get _canSaveCurrentTab => switch (_tab) {
        1 => _canAssignCustomers && _pathIsLoaded,
        2 => _canAssignSalesmen && _salesmenLoaded,
        _ => false,
      };

  @override
  Widget build(BuildContext context) {
    final SalesTerritory territory = widget.territory;
    return WorkspaceDialog(
      title: '${territory.code} — ${territory.name}',
      subtitle: territory.path,
      icon: Icons.travel_explore_outlined,
      loading: _loading || _saving,
      selectedTab: _tab,
      onTabChanged: (index) {
        setState(() => _tab = index);
        if (index == 2) _loadSalesmen();
      },
      tabs: [
        WorkspaceDialogTab(label: 'Details', child: _detailsTab(context)),
        WorkspaceDialogTab(label: 'Customers', child: _customersTab(context)),
        WorkspaceDialogTab(label: 'Salespeople', child: _salespeopleTab()),
      ],
      body: const SizedBox.shrink(),
      onClose: () => Navigator.pop(context),
      // The Details tab records nothing, so it offers no save rather than a
      // button that would do nothing when pressed.
      onSave: _canSaveCurrentTab ? _save : null,
      saveLabel: _tab == 1 ? 'Save round and order' : 'Save salespeople',
    );
  }

  Widget _detailsTab(BuildContext context) {
    final SalesTerritory territory = widget.territory;
    final TerritoryRouteProfileRecord? profile = territory.routeProfile;
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _section(context, 'Territory'),
          _row('Code', territory.code),
          _row('Name', territory.name),
          _row('Level', territory.hierarchyLevelName),
          _row('Status', territory.isDeleted ? 'DELETED' : territory.status),
          _row('Hierarchy', territory.path),
          if (territory.description.isNotEmpty)
            _row('Description', territory.description),
          const SizedBox(height: 16),
          _section(context, 'Coverage'),
          _row('Customers', '${territory.customerCount}'),
          _row('Active', '${territory.activeCustomerCount}'),
          _row('Inactive', '${territory.inactiveCustomerCount}'),
          _row('New', '${territory.newCustomerCount}'),
          _row('Potential', '${territory.potentialCustomerCount}'),
          _row('Salespeople', '${territory.salesmanCount}'),
          const SizedBox(height: 16),
          _section(context, 'Route'),
          if (profile == null)
            const Text(
              'This is not a route. Turn on "This is a route" in the editor to '
              'give it a type, a frequency and working days.',
            )
          else ...[
            _row(
              'Route type',
              profile.routeTypeName.isEmpty ? 'None' : profile.routeTypeName,
            ),
            _row('Visit frequency', _titleCase(profile.visitFrequency)),
            _row(
              'Working days',
              profile.workingDays.isEmpty
                  ? 'Not set'
                  : (profile.workingDays.toList()..sort())
                      .map((day) => _weekdays[day - 1])
                      .join(', '),
            ),
            // The window decides whether a beat plan calls this round at all,
            // so it belongs on the summary rather than only in the editor.
            _row(
              'Runs from',
              profile.effectiveFrom.isEmpty ? 'Always' : profile.effectiveFrom,
            ),
            _row(
              'Runs until',
              profile.effectiveTo.isEmpty ? 'No end' : profile.effectiveTo,
            ),
          ],
        ],
      ),
    );
  }

  Widget _customersTab(BuildContext context) {
    if (_error != null) {
      return WorkspaceErrorState(message: _error!, onRetry: _loadOutlets);
    }
    return Row(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Expanded(flex: 3, child: _outletList(context)),
        const VerticalDivider(width: 1),
        SizedBox(width: 380, child: _pathPane(context)),
      ],
    );
  }

  Widget _outletList(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.all(12),
            child: TextField(
              controller: _search,
              decoration: const InputDecoration(
                labelText: 'Search outlets by name, code, street or pin code',
                isDense: true,
                prefixIcon: Icon(Icons.search),
              ),
              onChanged: (_) => setState(() {}),
            ),
          ),
          const Divider(height: 1),
          Expanded(
            child: _visibleOutlets.isEmpty
                ? const StandardEmptyState(
                    type: EmptyStateType.noRecords,
                    title: 'No outlets',
                    message: 'This firm has no customers matching that search.',
                  )
                : ListView.builder(
                    itemCount: _visibleOutlets.length,
                    itemBuilder: (context, index) {
                      final AssignableCustomerRecord row =
                          _visibleOutlets[index];
                      final int? stop = _stopNumber(row.customerId);
                      return ListTile(
                        dense: true,
                        onTap: () => _toggleStop(row),
                        leading: CircleAvatar(
                          radius: 14,
                          backgroundColor: stop == null
                              ? Theme.of(context)
                                  .colorScheme
                                  .surfaceContainerHighest
                              : Theme.of(context).colorScheme.primaryContainer,
                          child: stop == null
                              ? const Icon(Icons.add, size: 15)
                              : Text(
                                  '$stop',
                                  style:
                                      Theme.of(context).textTheme.labelSmall,
                                ),
                        ),
                        title: Text(row.name),
                        subtitle: Text(
                          <String>[
                            row.code,
                            if (row.area.isNotEmpty) row.area,
                            if (row.postalCode.isNotEmpty) row.postalCode,
                          ].join(' · '),
                        ),
                        // Which other rounds already call this shop. A
                        // distributor visiting one outlet on a sales beat and
                        // a collection round is ordinary, so this informs
                        // rather than warns.
                        trailing: row.otherRoutes.isEmpty
                            ? null
                            : Text(
                                row.otherRoutes.join(', '),
                                style: Theme.of(context).textTheme.bodySmall,
                              ),
                      );
                    },
                  ),
          ),
        ],
      );

  Widget _pathPane(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    if (!_pathIsLoaded) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(16),
          child: Text(
            'This round could not be read, so it cannot be saved over. '
            'Close and reopen to try again.',
            textAlign: TextAlign.center,
          ),
        ),
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Padding(
          padding: const EdgeInsets.all(12),
          child: Row(
            children: [
              Expanded(
                child: Text(
                  'The path — ${_path.length} stop(s)',
                  style: theme.textTheme.titleSmall,
                ),
              ),
              if (_path.isNotEmpty && _canAssignCustomers)
                TextButton(
                  onPressed: () => setState(_path.clear),
                  child: const Text('Clear path'),
                ),
            ],
          ),
        ),
        const Divider(height: 1),
        Expanded(
          child: _path.isEmpty
              ? const Center(
                  child: Padding(
                    padding: EdgeInsets.all(16),
                    child: Text(
                      'Click an outlet on the left to make it the first stop, '
                      'then keep clicking to lay out the round in the order '
                      'it is called.',
                      textAlign: TextAlign.center,
                    ),
                  ),
                )
              : ReorderableListView.builder(
                  buildDefaultDragHandles: false,
                  itemCount: _path.length,
                  // `onReorderItem`, not `onReorder`: the older callback reports
                  // the target index in the list as it stood before the item
                  // was lifted out, so every caller has to decrement it by hand.
                  onReorderItem: (oldIndex, newIndex) => setState(() {
                    _path.insert(newIndex, _path.removeAt(oldIndex));
                  }),
                  itemBuilder: (context, index) {
                    final AssignableCustomerRecord row = _path[index];
                    final String? marker = index == 0
                        ? 'START'
                        : index == _path.length - 1
                            ? 'END'
                            : null;
                    return ListTile(
                      key: ValueKey<String>('path-${row.customerId}'),
                      dense: true,
                      leading: CircleAvatar(
                        radius: 14,
                        child: Text(
                          '${index + 1}',
                          style: theme.textTheme.labelSmall,
                        ),
                      ),
                      title: Text(row.name, overflow: TextOverflow.ellipsis),
                      subtitle: Text(
                        marker == null
                            ? '${row.area} · ${row.postalCode}'
                            : '$marker · ${row.area}',
                      ),
                      trailing: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          IconButton(
                            tooltip: 'Remove from path',
                            icon: const Icon(Icons.close, size: 18),
                            onPressed: _canAssignCustomers
                                ? () => _toggleStop(row)
                                : null,
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
        if (!_canAssignCustomers)
          const Padding(
            padding: EdgeInsets.all(12),
            child: Text('Read-only — you cannot assign customers to a route.'),
          ),
      ],
    );
  }

  Widget _salespeopleTab() {
    if (!_salesmenLoaded) {
      return const Center(child: Text('Loading salespeople...'));
    }
    if (_candidates.isEmpty) {
      return const StandardEmptyState(
        type: EmptyStateType.noRecords,
        title: 'Nobody to assign',
        message: 'Add a user under Administration and give them access to '
            'this firm.',
      );
    }
    return ListView(
      children: [
        for (final TerritorySalesmanCandidate person in _candidates)
          CheckboxListTile(
            value: _chosenSalesmen.contains(person.userId),
            title: Text(
              person.fullName.isEmpty ? person.email : person.fullName,
            ),
            subtitle: Text(person.email),
            onChanged: _canAssignSalesmen
                ? (value) => setState(() {
                      if (value == true) {
                        _chosenSalesmen.add(person.userId);
                      } else {
                        _chosenSalesmen.remove(person.userId);
                      }
                    })
                : null,
          ),
      ],
    );
  }

  Widget _section(BuildContext context, String label) => Padding(
        padding: const EdgeInsets.only(bottom: 8),
        child: Text(label, style: Theme.of(context).textTheme.titleSmall),
      );

  Widget _row(String label, String value) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 3),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SizedBox(width: 150, child: Text(label)),
            Expanded(child: Text(value.isEmpty ? '-' : value)),
          ],
        ),
      );

  static const List<String> _weekdays = <String>[
    'Mon',
    'Tue',
    'Wed',
    'Thu',
    'Fri',
    'Sat',
    'Sun',
  ];

  static String _titleCase(String code) => code
      .split('_')
      .map((word) => word.isEmpty
          ? word
          : word[0].toUpperCase() + word.substring(1).toLowerCase())
      .join(' ');
}
