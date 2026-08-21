import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/security/permission_service.dart';
import '../../models/diagnostics.dart';
import '../../models/entities.dart';
import '../workspace/desktop_framework.dart';

/// What failed, how often, and on which build.
///
/// The desktop has queued crash reports to disk and flushed them to
/// `/api/v1/diagnostics/client-errors` since the crash reporter was written,
/// and the server records its own failures beside them -- with nothing able to
/// read a single one back. Faults were being collected and nobody could look
/// at them.
///
/// Reports live in the **platform** store rather than per firm, unlike the
/// audit trail: a crash is telemetry for whoever maintains the product, and a
/// fault split across firm stores could not be counted or ranked. So this
/// screen shows every firm's faults at once, which is the opposite of the
/// audit page and worth saying on screen.
class DiagnosticsPage extends StatefulWidget {
  const DiagnosticsPage({
    super.key,
    required this.api,
    required this.permissions,
  });

  final ApiClient api;
  final PermissionService permissions;

  @override
  State<DiagnosticsPage> createState() => _DiagnosticsPageState();
}

class _DiagnosticsPageState extends State<DiagnosticsPage> {
  static const int _rowsPerPage = 20;
  final TextEditingController _search = TextEditingController();
  List<ErrorReportGroup> _groups = const [];
  ErrorReportGroup? _selected;
  List<ErrorReport> _occurrences = const [];
  String? _source;
  int _page = 1;
  int _total = 0;
  bool _loading = false;
  bool _loadingOccurrences = false;
  String? _error;

  /// The fault whose occurrences are on screen.
  ///
  /// Tracked separately from [_selected] so a slow response for one fault
  /// cannot land under another the user has since clicked.
  String? _shownFingerprint;

  bool get _canView => widget.permissions.hasPermission('DIAGNOSTICS_VIEW');

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

  Future<void> _load({int? requestedPage}) async {
    if (!_canView) return;
    setState(() {
      _loading = true;
      _error = null;
      if (requestedPage != null) _page = requestedPage;
    });
    try {
      final PagedResult<ErrorReportGroup> result = await widget.api.errorGroups(
        page: _page,
        pageSize: _rowsPerPage,
        search: _search.text.trim(),
        source: _source,
      );
      if (!mounted) return;
      setState(() {
        _groups = result.items;
        _total = result.total;
      });
      await _select(result.items.isEmpty ? null : result.items.first);
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() {
        _error = exception.message;
        _groups = const [];
        _total = 0;
        _selected = null;
        _occurrences = const [];
        _shownFingerprint = null;
      });
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _select(ErrorReportGroup? group) async {
    setState(() {
      _selected = group;
      _occurrences = const [];
      _shownFingerprint = null;
      _loadingOccurrences = group != null;
    });
    if (group == null) return;
    try {
      final List<ErrorReport> rows =
          await widget.api.errorOccurrences(group.fingerprint);
      if (!mounted) return;
      // The user may have clicked another fault while this was in flight.
      if (_selected?.fingerprint != group.fingerprint) return;
      setState(() {
        _occurrences = rows;
        _shownFingerprint = group.fingerprint;
      });
    } on ApiException catch (exception) {
      if (!mounted) return;
      if (_selected?.fingerprint != group.fingerprint) return;
      setState(() => _error = exception.message);
    } finally {
      if (mounted && _selected?.fingerprint == group.fingerprint) {
        setState(() => _loadingOccurrences = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!_canView) {
      return const StandardEmptyState(
        type: EmptyStateType.noPermissions,
        title: 'Diagnostics',
        message: 'You do not have permission to read error reports.',
      );
    }
    return LoadingOverlay(
      loading: _loading,
      child: Column(children: [
        _filters(context),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg),
          child: Align(
            alignment: Alignment.centerLeft,
            child: Text(
              'Every firm at once. Error reports are kept in the platform '
              'store, so this is the whole product rather than one firm — '
              'unlike the audit trail beside it.',
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
          child: _groups.isEmpty
              ? const StandardEmptyState(
                  type: EmptyStateType.noRecords,
                  title: 'Nothing has failed',
                  message: 'No error report matches. Clients queue reports on '
                      'disk until they can sign in, so a fault may arrive '
                      'later than it happened.',
                )
              : Row(children: [
                  Expanded(flex: 3, child: _list(context)),
                  const VerticalDivider(width: 1),
                  Expanded(flex: 4, child: _detail(context)),
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

  Widget _filters(BuildContext context) => Padding(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Row(children: [
          SizedBox(
            width: 320,
            child: TextField(
              controller: _search,
              decoration: const InputDecoration(
                labelText: 'Search',
                hintText: 'Message or error type',
              ),
              onSubmitted: (_) => unawaited(_load(requestedPage: 1)),
            ),
          ),
          const SizedBox(width: AppSpacing.md),
          SizedBox(
            width: 180,
            child: DropdownButtonFormField<String>(
              // Null is "everything", which is what triage starts from.
              initialValue: _source,
              decoration: const InputDecoration(labelText: 'Source'),
              items: const [
                DropdownMenuItem<String>(value: null, child: Text('All')),
                DropdownMenuItem<String>(
                    value: 'CLIENT', child: Text('Desktop')),
                DropdownMenuItem<String>(
                    value: 'SERVER', child: Text('Server')),
              ],
              onChanged: (value) {
                setState(() => _source = value);
                unawaited(_load(requestedPage: 1));
              },
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
      );

  Widget _list(BuildContext context) => ListView.separated(
        itemCount: _groups.length,
        separatorBuilder: (_, __) => const Divider(height: 1),
        itemBuilder: (context, index) {
          final ErrorReportGroup group = _groups[index];
          return ListTile(
            selected: group.fingerprint == _selected?.fingerprint,
            title: Text(
              group.errorType,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
            subtitle: Text(
              group.message,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
            leading: StatusBadge(
              label: group.source == 'CLIENT' ? 'Desktop' : 'Server',
              tone: group.source == 'CLIENT'
                  ? StatusBadgeTone.warning
                  : StatusBadgeTone.danger,
            ),
            // The count is what ranks the work: one fault seen 400 times is
            // the one to fix first, and the list is ordered by recency.
            trailing: Text(
              '${group.occurrences}×',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            onTap: () => unawaited(_select(group)),
          );
        },
      );

  Widget _detail(BuildContext context) {
    final ErrorReportGroup? group = _selected;
    if (group == null) {
      return const Center(child: Text('Choose a fault.'));
    }
    final TextTheme text = Theme.of(context).textTheme;
    return SingleChildScrollView(
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(group.errorType, style: text.titleMedium),
          const SizedBox(height: AppSpacing.sm),
          SelectableText(group.message, style: text.bodyMedium),
          const SizedBox(height: AppSpacing.md),
          Wrap(
            spacing: AppSpacing.sm,
            runSpacing: AppSpacing.sm,
            children: [
              _fact(context, '${group.occurrences} occurrences'),
              _fact(context, 'First seen ${group.firstSeen}'),
              _fact(context, 'Last seen ${group.lastSeen}'),
              // A fault seen only on older builds may already be fixed; one
              // reaching the current build is still live.
              if (group.appVersions.isNotEmpty)
                _fact(context, 'Versions ${group.appVersions.join(', ')}'),
            ],
          ),
          const SizedBox(height: AppSpacing.lg),
          Text('Occurrences', style: text.titleSmall),
          const SizedBox(height: AppSpacing.sm),
          if (_loadingOccurrences)
            const Padding(
              padding: EdgeInsets.all(AppSpacing.lg),
              child: Center(child: CircularProgressIndicator()),
            )
          else if (_shownFingerprint != group.fingerprint)
            Text('Could not read the occurrences.', style: text.bodySmall)
          else if (_occurrences.isEmpty)
            Text(
              'The group is counted from rows that are no longer stored. '
              'Retention prunes reports; the count outlives them.',
              style: text.bodySmall,
            )
          else
            for (final ErrorReport row in _occurrences) _occurrence(context, row),
        ],
      ),
    );
  }

  Widget _fact(BuildContext context, String label) => Chip(
        label: Text(label),
        visualDensity: VisualDensity.compact,
      );

  Widget _occurrence(BuildContext context, ErrorReport row) {
    final TextTheme text = Theme.of(context).textTheme;
    return ExpansionTile(
      tilePadding: EdgeInsets.zero,
      childrenPadding: const EdgeInsets.only(bottom: AppSpacing.md),
      title: Text(
        row.occurredAt.isEmpty ? row.receivedAt : row.occurredAt,
        style: text.bodyMedium,
      ),
      subtitle: Text(
        [
          if (row.appVersion.isNotEmpty) 'v${row.appVersion}',
          if (row.buildNumber.isNotEmpty) 'build ${row.buildNumber}',
          if (row.platformInfo.isNotEmpty) row.platformInfo,
          if (row.contextLabel.isNotEmpty) row.contextLabel,
        ].join(' · '),
        style: text.bodySmall,
      ),
      children: [
        Align(
          alignment: Alignment.centerLeft,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (row.requestId.isNotEmpty)
                // The one field that ties a client crash to the server's own
                // logs for the same request.
                SelectableText('Request ${row.requestId}',
                    style: text.bodySmall),
              if (row.firmId.isNotEmpty)
                SelectableText('Firm ${row.firmId}', style: text.bodySmall),
              if (row.userId.isNotEmpty)
                SelectableText('User ${row.userId}', style: text.bodySmall),
              if (row.occurredAt.isNotEmpty &&
                  row.occurredAt != row.receivedAt)
                Text('Reported ${row.receivedAt}', style: text.bodySmall),
              if (row.breadcrumbs.isNotEmpty) ...[
                const SizedBox(height: AppSpacing.sm),
                Text('Leading up to it', style: text.labelMedium),
                for (final String crumb in row.breadcrumbs)
                  Text('• $crumb', style: text.bodySmall),
              ],
              if (row.stackTrace.isNotEmpty) ...[
                const SizedBox(height: AppSpacing.sm),
                Text('Stack trace', style: text.labelMedium),
                const SizedBox(height: AppSpacing.xs),
                // Horizontally scrollable in its own right: a stack frame is
                // long and the page itself must never scroll sideways.
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(AppSpacing.sm),
                  decoration: BoxDecoration(
                    color: Theme.of(context).colorScheme.surfaceContainerHighest,
                    borderRadius: AppRadius.small,
                  ),
                  child: SingleChildScrollView(
                    scrollDirection: Axis.horizontal,
                    child: SelectableText(
                      row.stackTrace,
                      style: text.bodySmall?.copyWith(fontFamily: 'monospace'),
                    ),
                  ),
                ),
              ],
            ],
          ),
        ),
      ],
    );
  }
}
