import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/security/permission_service.dart';
import '../../models/sales_territory.dart';
import '../workspace/desktop_framework.dart';

/// Who is called today.
///
/// The last thing missing from "prepare weekly daily sales on that route": a
/// route could be drawn, ordered and scheduled, and nothing anywhere answered
/// which outlets that adds up to on a given day.
///
/// The answer is computed by the server from the recurrence rule and the
/// assignment tables rather than stored, so this screen is never showing a
/// stale occurrence — and it says who *should* be called, never who was. There
/// is no visit execution behind it.
class CallListPage extends StatefulWidget {
  const CallListPage({
    super.key,
    required this.api,
    required this.permissions,
  });

  final ApiClient api;
  final PermissionService permissions;

  @override
  State<CallListPage> createState() => _CallListPageState();
}

class _CallListPageState extends State<CallListPage> {
  DateTime _date = DateTime.now();
  String _salesmanId = '';
  List<TerritorySalesmanCandidate> _salesmen = const [];
  CallListRecord? _result;
  bool _loading = false;
  String? _error;

  bool get _canView => widget.permissions.hasPermission('TERRITORY_VIEW');

  @override
  void initState() {
    super.initState();
    _loadSalesmen();
    _load();
  }

  /// Not `/api/v1/users`: that is guarded by `USER_VIEW`, a platform-admin
  /// permission the roles that run territories do not hold.
  Future<void> _loadSalesmen() async {
    if (!_canView) return;
    try {
      final List<TerritorySalesmanCandidate> rows =
          await widget.api.territorySalesmanCandidates();
      if (!mounted) return;
      setState(() => _salesmen = rows);
    } on ApiException {
      // A missing candidate list costs the filter, not the screen.
    }
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
      final CallListRecord result = await widget.api.callLists(
        date: _isoDate(_date),
        salesmanId: _salesmanId,
      );
      if (!mounted) return;
      setState(() {
        _result = result;
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

  static String _isoDate(DateTime value) =>
      '${value.year.toString().padLeft(4, '0')}-'
      '${value.month.toString().padLeft(2, '0')}-'
      '${value.day.toString().padLeft(2, '0')}';

  Future<void> _pickDate() async {
    final DateTime? picked = await showDatePicker(
      context: context,
      initialDate: _date,
      firstDate: DateTime(_date.year - 2),
      lastDate: DateTime(_date.year + 2),
    );
    if (picked == null) return;
    setState(() => _date = picked);
    await _load();
  }

  void _shiftDay(int days) {
    setState(() => _date = _date.add(Duration(days: days)));
    _load();
  }

  @override
  Widget build(BuildContext context) {
    final List<CallListEntryRecord> entries =
        _result?.entries ?? const <CallListEntryRecord>[];
    final List<CallListEntryRecord> running =
        entries.where((entry) => entry.occurs).toList();
    final int totalStops = running.fold(
      0,
      (count, entry) => count + entry.stops.length,
    );

    final Widget toolbar = WorkspaceToolbar(
      actions: const [ToolbarAction.refresh],
      isEnabled: (action) => action == ToolbarAction.refresh,
      onAction: (action) {
        if (action == ToolbarAction.refresh) _load();
      },
    );

    // The date and the salesperson are the only two things to narrow by, and
    // there is nothing to type — a call list is not searched, it is read for a
    // day. So the filter row carries them and there is no search box.
    final Widget filterPanel = Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      child: Wrap(
        spacing: 8,
        runSpacing: 8,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          IconButton(
            tooltip: 'Previous day',
            icon: const Icon(Icons.chevron_left),
            onPressed: () => _shiftDay(-1),
          ),
          TextButton.icon(
            onPressed: _pickDate,
            icon: const Icon(Icons.event),
            label: Text(_isoDate(_date)),
          ),
          IconButton(
            tooltip: 'Next day',
            icon: const Icon(Icons.chevron_right),
            onPressed: () => _shiftDay(1),
          ),
          TextButton(
            onPressed: () {
              setState(() => _date = DateTime.now());
              _load();
            },
            child: const Text('Today'),
          ),
          SizedBox(
            width: 240,
            child: DropdownButtonFormField<String>(
              initialValue: _salesmanId.isEmpty ? '' : _salesmanId,
              decoration: const InputDecoration(
                labelText: 'Salesperson',
                isDense: true,
              ),
              items: [
                const DropdownMenuItem<String>(
                  value: '',
                  child: Text('Everyone'),
                ),
                for (final candidate in _salesmen)
                  DropdownMenuItem<String>(
                    value: candidate.userId,
                    child: Text(candidate.fullName),
                  ),
              ],
              onChanged: (value) {
                setState(() => _salesmanId = value ?? '');
                _load();
              },
            ),
          ),
        ],
      ),
    );

    final Widget content = _error != null
        ? WorkspaceErrorState(message: _error!, onRetry: _load)
        : _loading && _result == null
            ? const TableLoadingSkeleton()
            : entries.isEmpty
                ? const StandardEmptyState(
                    type: EmptyStateType.noRecords,
                    title: 'No beat plans to call from',
                    message: 'A call list is built from active beat plans. '
                        'Create one under Beat Plans to schedule a round.',
                  )
                : LoadingOverlay(
                    loading: _loading,
                    child: ListView(
                      padding: const EdgeInsets.all(16),
                      children: [
                        for (final entry in entries) _EntryCard(entry: entry),
                      ],
                    ),
                  );

    return ManagementWorkspaceLayout(
      toolbar: toolbar,
      searchPanel: filterPanel,
      primaryContent: content,
      statusBar: WorkspaceStatusBar(
        total: totalStops,
        selected: false,
        message: _loading
            ? 'Refreshing call list...'
            : '${running.length} of ${entries.length} plan(s) run on '
                '${_isoDate(_date)}',
      ),
    );
  }
}

/// One plan's card: the round, who walks it, and the outlets in call order.
class _EntryCard extends StatelessWidget {
  const _EntryCard({required this.entry});

  final CallListEntryRecord entry;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    '${entry.beatPlanCode} — ${entry.beatPlanName}',
                    style: theme.textTheme.titleMedium,
                  ),
                ),
                StatusBadge(
                  label: entry.occurs ? 'Runs today' : 'Not today',
                  tone: entry.occurs
                      ? StatusBadgeTone.success
                      : StatusBadgeTone.neutral,
                ),
              ],
            ),
            const SizedBox(height: 4),
            Text(
              '${entry.territoryCode} — ${entry.territoryName}',
              style: theme.textTheme.bodySmall,
            ),
            // A plan that cannot be computed says so. Showing an empty list
            // for both "nobody today" and "this cannot be worked out" would
            // misreport one of them every time.
            if (entry.reason.isNotEmpty) ...[
              const SizedBox(height: 8),
              Row(
                children: [
                  const Icon(Icons.info_outline, size: 16),
                  const SizedBox(width: 6),
                  Expanded(
                    child: Text(entry.reason, style: theme.textTheme.bodySmall),
                  ),
                ],
              ),
            ],
            if (entry.occurs) ...[
              const SizedBox(height: 12),
              if (entry.stops.isEmpty)
                Text(
                  'This round runs today but has no outlets on it yet.',
                  style: theme.textTheme.bodySmall,
                )
              else
                Column(
                  children: [
                    for (final stop in entry.stops)
                      ListTile(
                        dense: true,
                        contentPadding: EdgeInsets.zero,
                        leading: CircleAvatar(
                          radius: 14,
                          child: Text(
                            '${stop.stopOrder}',
                            style: theme.textTheme.labelSmall,
                          ),
                        ),
                        title: Text(stop.customerName),
                        subtitle: Text(stop.customerCode),
                        trailing: stop.plannedDurationMinutes == null
                            ? null
                            : Text('${stop.plannedDurationMinutes} min'),
                      ),
                  ],
                ),
            ],
          ],
        ),
      ),
    );
  }
}
