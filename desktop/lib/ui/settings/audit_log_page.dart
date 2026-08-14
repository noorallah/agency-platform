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
      );
      if (!mounted) return;
      setState(() {
        _rows = result.items;
        _total = result.total;
        _selected = result.items.isEmpty ? null : result.items.first;
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

  Widget _list(BuildContext context) => ListView.separated(
        itemCount: _rows.length,
        separatorBuilder: (_, __) => const Divider(height: 1),
        itemBuilder: (context, index) {
          final AuditLogEntry row = _rows[index];
          return ListTile(
            selected: row.id == _selected?.id,
            dense: true,
            title: Text('${row.action}  ·  ${row.entityType}'),
            subtitle: Text(row.createdAt),
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
            '${row.entityType} · ${row.entityId}',
            style: Theme.of(context).textTheme.bodySmall,
          ),
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
            SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: DataTable(
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
