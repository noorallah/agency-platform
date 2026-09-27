import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/security/permission_service.dart';
import '../../models/audit.dart';
import '../../models/entities.dart';
import '../workspace/desktop_framework.dart';

/// Who changed what, and what it was before.
///
/// The trail is per store rather than central: platform administration is
/// recorded in the platform trail, and every firm-owned change in that firm's
/// own. That is deliberate -- a firm with its own database has to hold its own
/// history for the isolation and per-firm restore guarantees to mean anything
/// -- and it means this screen shows **one** trail, the one the current firm
/// context selects. The caption says so, because a reader who takes it for
/// everything will conclude that something they cannot see never happened.
class AuditLogPage extends StatefulWidget {
  const AuditLogPage({
    super.key,
    required this.api,
    required this.permissions,
    required this.firmLabel,
  });

  final ApiClient api;
  final PermissionService permissions;

  /// The firm whose trail this is, or null for the platform trail.
  final String? firmLabel;

  @override
  State<AuditLogPage> createState() => _AuditLogPageState();
}

class _AuditLogPageState extends State<AuditLogPage> {
  static const int _rowsPerPage = 20;
  final TextEditingController _action = TextEditingController();
  final TextEditingController _entityType = TextEditingController();
  List<AuditLogEntry> _rows = const [];

  /// Phase 2's Period over the trail (review, 2026-09-27).
  DatePeriod _period = const DatePeriod.all();
  AuditLogEntry? _selected;
  int _page = 1;
  int _total = 0;
  bool _loading = false;
  String? _error;

  bool get _canView => widget.permissions.hasPermission('AUDIT_LOG_VIEW');

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  @override
  void dispose() {
    _action.dispose();
    _entityType.dispose();
    super.dispose();
  }

  Future<void> _load({int? requestedPage}) async {
    if (!_canView) return;
    setState(() {
      _loading = true;
      _error = null;
      if (requestedPage != null) _page = requestedPage;
    });
    try {
      final PagedResult<AuditLogEntry> result = await widget.api.auditLogs(
        page: _page,
        pageSize: _rowsPerPage,
        action: _action.text.trim(),
        entityType: _entityType.text.trim(),
        dateFrom: _period.from == null ? null : DatePeriod.iso(_period.from!),
        dateTo: _period.to == null ? null : DatePeriod.iso(_period.to!),
      );
      if (!mounted) return;
      // Phase 2 lists pick nothing until the user does; phase 1's side pane
      // wanted an entry to show. Read without a dependency: this runs from
      // initState too.
      final bool phase2 =
          context.getInheritedWidgetOfExactType<Phase2Scope>() != null;
      setState(() {
        _rows = result.items;
        _total = result.total;
        _selected = phase2
            ? result.items.where((row) => row.id == _selected?.id).firstOrNull
            : (result.items.isEmpty ? null : result.items.first);
      });
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() {
        _error = exception.message;
        _rows = const [];
        _total = 0;
      });
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!_canView) {
      return const StandardEmptyState(
        type: EmptyStateType.noPermissions,
        title: 'Audit log',
        message: 'You do not have permission to read the audit trail.',
      );
    }
    if (Phase2Scope.of(context)) return _phase2(context);
    return LoadingOverlay(
      loading: _loading,
      child: Column(children: [
        Padding(
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: Row(children: [
            SizedBox(
              width: 260,
              child: TextField(
                controller: _action,
                decoration: const InputDecoration(
                  labelText: 'Action',
                  hintText: 'customer.created',
                  helperText: 'Part of the name is enough',
                ),
                onSubmitted: (_) => _load(requestedPage: 1),
              ),
            ),
            const SizedBox(width: AppSpacing.md),
            SizedBox(
              width: 220,
              child: TextField(
                controller: _entityType,
                decoration: const InputDecoration(
                  labelText: 'Entity type',
                  hintText: 'customer',
                  helperText: 'Part of the name is enough',
                ),
                onSubmitted: (_) => _load(requestedPage: 1),
              ),
            ),
            const SizedBox(width: AppSpacing.md),
            FilledButton.tonalIcon(
              onPressed: () => unawaited(_load(requestedPage: 1)),
              icon: const Icon(Icons.search),
              label: const Text('Search'),
            ),
            const Spacer(),
            IconButton(
              tooltip: 'Refresh',
              onPressed: _loading ? null : () => unawaited(_load()),
              icon: const Icon(Icons.refresh),
            ),
          ]),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg),
          child: Align(
            alignment: Alignment.centerLeft,
            child: Text(
              widget.firmLabel == null
                  ? 'The platform trail: users, roles and firm administration. '
                      'Each firm keeps its own trading history in its own store.'
                  : 'The trail for ${widget.firmLabel}. Platform administration '
                      'and other firms keep their own, in their own stores.',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ),
        ),
        if (_error != null)
          Padding(
            padding: const EdgeInsets.all(AppSpacing.lg),
            child: MaterialBanner(
              content: Text(_error!),
              actions: [
                TextButton(
                  onPressed: () => setState(() => _error = null),
                  child: const Text('Dismiss'),
                ),
              ],
            ),
          ),
        Expanded(
          child: _rows.isEmpty
              ? const StandardEmptyState(
                  type: EmptyStateType.noRecords,
                  title: 'Nothing recorded',
                  message: 'No entry in this trail matches. Every mutation '
                      'writes one, so an empty result means it happened in a '
                      'different store or outside the filters.',
                )
              : Row(children: [
                  Expanded(flex: 3, child: _list(context)),
                  const VerticalDivider(width: 1),
                  Expanded(flex: 2, child: _detail(context)),
                ]),
        ),
        WorkspacePager(
          page: _page,
          pageSize: _rowsPerPage,
          total: _total,
          onPageChanged: (next) => unawaited(_load(requestedPage: next)),
        ),
      ]),
    );
  }

  /// Whose trail this is, in one sentence.
  String get _trailSentence => widget.firmLabel == null
      ? 'The platform trail: users, roles and firm administration. Each firm '
          'keeps its own trading history in its own store.'
      : 'The trail for ${widget.firmLabel}. Platform administration and other '
          'firms keep their own, in their own stores.';

  /// Phase 2 (review, 2026-09-27): a grid with the action as the line's
  /// search, the Period after it and the entity type under "+ filter"; the
  /// entry opens in a window instead of a pane beside the list.
  Widget _phase2(BuildContext context) {
    final AuditLogEntry? picked = _selected;
    return LoadingOverlay(
      loading: _loading,
      child: ManagementWorkspaceLayout(
        toolbar: WorkspaceToolbar(
          actions: const [ToolbarAction.view, ToolbarAction.refresh],
          isEnabled: (action) =>
              action == ToolbarAction.refresh ? !_loading : picked != null,
          onAction: (action) {
            if (action == ToolbarAction.view && picked != null) {
              unawaited(_open(picked));
            } else {
              unawaited(_load());
            }
          },
          trailing: [
            DateRangeFilter(
              value: _period,
              onChanged: (period) {
                setState(() => _period = period);
                unawaited(_load(requestedPage: 1));
              },
            ),
          ],
        ),
        searchPanel: SearchFilterPanel(
          controller: _action,
          hintText: 'Search action, e.g. customer.created',
          onSearch: (_) => unawaited(_load(requestedPage: 1)),
        ),
        filterPanel: FilterPanel(
          activeFilterCount: _entityType.text.trim().isEmpty ? 0 : 1,
          onApply: () => unawaited(_load(requestedPage: 1)),
          onClear: () {
            _entityType.clear();
            unawaited(_load(requestedPage: 1));
          },
          children: [
            SizedBox(
              width: 220,
              child: TextField(
                controller: _entityType,
                decoration: const InputDecoration(
                  labelText: 'Entity type',
                  hintText: 'customer',
                ),
              ),
            ),
          ],
        ),
        notice: _trailSentence,
        selectionBar: true,
        selection: picked == null
            ? null
            : SelectionSummary.record(
                name: picked.action,
                facts: [
                  picked.entityLabel.isEmpty
                      ? picked.entityType
                      : '${picked.entityType} ${picked.entityLabel}',
                  picked.actorLabel,
                  createdStamp(picked.createdAt),
                ],
                onClear: () => setState(() => _selected = null),
              ),
        primaryContent: Column(children: [
          if (_error != null)
            MaterialBanner(
              content: Text(_error!),
              actions: [
                TextButton(
                  onPressed: () => setState(() => _error = null),
                  child: const Text('Dismiss'),
                ),
              ],
            ),
          Expanded(
            child: _rows.isEmpty
                ? const StandardEmptyState(
                    type: EmptyStateType.noRecords,
                    title: 'Nothing recorded',
                    message: 'No entry in this trail matches. Every mutation '
                        'writes one, so an empty result means it happened in '
                        'a different store or outside the filters.',
                  )
                : EnterpriseDataGrid<AuditLogEntry>(
                    items: _rows,
                    total: _total,
                    pageOffset: (_page - 1) * _rowsPerPage,
                    rowsPerPage: _rowsPerPage,
                    selectedId: picked?.id,
                    columns: const [
                      GridColumn(key: 'when', label: 'When'),
                      GridColumn(key: 'action', label: 'Action', priority: 1),
                      GridColumn(key: 'entity', label: 'Entity'),
                      GridColumn(key: 'subject', label: 'Subject'),
                      GridColumn(key: 'by', label: 'By'),
                    ],
                    id: (row) => row.id,
                    cells: (row) => [
                      createdStamp(row.createdAt),
                      row.action,
                      row.entityType,
                      row.entityLabel.isEmpty ? row.entityId : row.entityLabel,
                      row.actorLabel,
                    ],
                    onSelect: (row) => setState(() => _selected = row),
                    onOpen: (row) => unawaited(_open(row)),
                    onPageChanged: (offset) => unawaited(
                      _load(requestedPage: offset ~/ _rowsPerPage + 1),
                    ),
                  ),
          ),
        ]),
        statusBar: WorkspaceStatusBar(
          total: _total,
          selected: picked != null,
          message: _loading ? 'Loading...' : null,
        ),
      ),
    );
  }

  /// Read one entry: what the side pane held, in a window.
  Future<void> _open(AuditLogEntry row) async {
    setState(() => _selected = row);
    await showDialog<void>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        content: SizedBox(width: 560, child: _detail(dialogContext)),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(),
            child: const Text('Close'),
          ),
        ],
      ),
    );
  }

  Widget _list(BuildContext context) => ListView.separated(
        itemCount: _rows.length,
        separatorBuilder: (_, __) => const Divider(height: 1),
        itemBuilder: (context, index) {
          final AuditLogEntry row = _rows[index];
          return ListTile(
            selected: row.id == _selected?.id,
            dense: true,
            title: Text('${row.action}  ·  ${row.entityType}'),
            // Who, then when. The list used to give neither -- an action and
            // an entity type, which is the same two words for every row a
            // busy day produces.
            subtitle: Text('${row.actorLabel}  ·  ${row.createdAt}'),
            onTap: () => setState(() => _selected = row),
          );
        },
      );

  Widget _detail(BuildContext context) {
    final AuditLogEntry? row = _selected;
    if (row == null) {
      return const Center(child: Text('Choose an entry.'));
    }
    final List<AuditFieldChange> changes = row.changes;
    return SingleChildScrollView(
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(row.action, style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: AppSpacing.sm),
          Text(
            // The subject named where it is a person, with the id kept
            // beside it: the id is what a support request quotes, and the
            // name is what makes the row readable. Every other entity type
            // has only the id, which is honest -- resolving them would mean
            // knowing what each `entity_type` points at.
            row.entityLabel.isEmpty
                ? '${row.entityType} · ${row.entityId}'
                : '${row.entityType} · ${row.entityLabel}',
            style: Theme.of(context).textTheme.bodySmall,
          ),
          if (row.entityLabel.isNotEmpty)
            Text(row.entityId, style: Theme.of(context).textTheme.bodySmall),
          Text('By ${row.actorLabel}',
              style: Theme.of(context).textTheme.bodySmall),
          Text(row.createdAt, style: Theme.of(context).textTheme.bodySmall),
          if (row.ipAddress.isNotEmpty)
            Text(
              'From ${row.ipAddress}',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          const SizedBox(height: AppSpacing.lg),
          if (changes.isEmpty)
            Text(
              row.hasBothSides
                  ? 'Recorded, with nothing different between the two sides.'
                  : row.afterData.isEmpty
                      ? 'A deletion. What it was is on the record.'
                      : 'A creation. There was no earlier version.',
              style: Theme.of(context).textTheme.bodyMedium,
            )
          else
            // Only the fields that moved. An audit row can carry a dozen
            // unchanged ones on both sides, and showing all of them buries the
            // one somebody is looking for.
            Phase2WideTable(
              table: DataTable(
                columnSpacing: AppSpacing.lg,
                columns: const [
                  DataColumn(label: Text('Field')),
                  DataColumn(label: Text('Was')),
                  DataColumn(label: Text('Became')),
                ],
                rows: [
                  for (final AuditFieldChange change in changes)
                    DataRow(cells: [
                      DataCell(Text(change.field)),
                      DataCell(Text(change.before.isEmpty ? '—' : change.before)),
                      DataCell(Text(change.after.isEmpty ? '—' : change.after)),
                    ]),
                ],
              ),
            ),
        ],
      ),
    );
  }
}
