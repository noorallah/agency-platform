import 'dart:async';

import 'package:flutter/material.dart';

import '../core/api/api_client.dart';
import '../core/design/design_tokens.dart';
import '../models/backup.dart';
import '../ui/workspace/desktop_framework.dart';

/// Admin > System > Backups in the phase 2 app: the backups the server has
/// taken, and a button to take one now.
///
/// For the platform tier only (`SYSTEM_BACKUP`); the menu offers it on that
/// code and the server enforces it. A backup runs on the server and takes a
/// while, so "Back up now" returns at once and this page polls until the run
/// is done rather than holding a request open.
class BackupsPage extends StatefulWidget {
  const BackupsPage({
    super.key,
    required this.api,
    this.pollInterval = const Duration(seconds: 3),
  });

  final ApiClient api;

  /// How often to ask again while a backup is running.
  final Duration pollInterval;

  @override
  State<BackupsPage> createState() => _BackupsPageState();
}

class _BackupsPageState extends State<BackupsPage> {
  BackupOverview? _overview;
  bool _loading = true;
  bool _starting = false;
  String? _error;
  String? _selectedPath;
  Timer? _poll;

  /// The run that finished while this page was watching it, kept until the
  /// next one starts so its message cannot flash past unread.
  BackupRun? _finished;
  bool _watchedRun = false;

  bool get _running => _overview?.run.running ?? false;

  BackupEntry? get _selected => _overview?.backups
      .where((backup) => backup.path == _selectedPath)
      .firstOrNull;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  @override
  void dispose() {
    _poll?.cancel();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      _accept(await widget.api.getBackups());
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.message;
        _loading = false;
      });
    }
  }

  /// Takes a fresh overview, and keeps polling while a run is going.
  void _accept(BackupOverview overview) {
    if (!mounted) return;
    _poll?.cancel();
    final bool wasRunning = _watchedRun;
    setState(() {
      _overview = overview;
      _loading = false;
      if (_selected == null) _selectedPath = null;
      if (overview.run.running) {
        _watchedRun = true;
        _finished = null;
      } else {
        _watchedRun = false;
        if (wasRunning) _finished = overview.run;
      }
    });
    if (overview.run.running) {
      _poll = Timer(widget.pollInterval, () => unawaited(_refreshQuietly()));
    }
  }

  Future<void> _refreshQuietly() async {
    try {
      _accept(await widget.api.getBackups());
    } on ApiException catch (error) {
      if (!mounted) return;
      // Keep watching: one failed poll is not the end of the backup.
      setState(() => _error = error.message);
      _poll = Timer(widget.pollInterval, () => unawaited(_refreshQuietly()));
    }
  }

  Future<void> _start() async {
    setState(() {
      _starting = true;
      _error = null;
    });
    try {
      final BackupOverview overview = await widget.api.startBackup();
      if (!mounted) return;
      _watchedRun = true;
      setState(() => _starting = false);
      _accept(overview);
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _starting = false;
        _error = error.message;
      });
      // A 409 is "one is already running": say so, and pick it up.
      if (error.statusCode == 409) await _refreshQuietly();
    }
  }

  static String _kind(String kind) => switch (kind) {
        'manual' => 'By hand',
        'daily' => 'Nightly',
        'pre-upgrade' => 'Before upgrade',
        _ => kind,
      };

  static String _status(bool? complete) => switch (complete) {
        true => 'Complete',
        false => 'Unfinished',
        null => 'Not readable by the server',
      };

  /// 28.4 MB, not 29782016.
  static String size(int? bytes) {
    if (bytes == null) return '-';
    const List<String> units = ['B', 'KB', 'MB', 'GB', 'TB'];
    double value = bytes.toDouble();
    int unit = 0;
    while (value >= 1024 && unit < units.length - 1) {
      value /= 1024;
      unit++;
    }
    if (unit == 0) return '$bytes B';
    return '${value.toStringAsFixed(1)} ${units[unit]}';
  }

  Widget _info(BuildContext context) {
    final BackupOverview? overview = _overview;
    final String kept =
        overview == null ? '' : '; the last ${overview.keepManual} of those '
            'are kept';
    final String where =
        overview == null ? 'the backup folder' : overview.backupDirectory;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surfaceContainerLow,
        borderRadius: BorderRadius.circular(AppSpacing.xs),
      ),
      child: Text(
        'This server backs itself up every night at 02:00 and keeps those '
        'for 7 days. "Back up now" takes one immediately$kept. Backups are '
        'in $where on the server PC -- copy them off this PC (a USB drive '
        'or the cloud) regularly. Restoring is done by an administrator on '
        'the server PC, following section 6 of the Install Guide.',
        style: Theme.of(context).textTheme.bodySmall,
      ),
    );
  }

  Widget _runStatus(BuildContext context) {
    final BackupOverview? overview = _overview;
    if (overview == null) return const SizedBox.shrink();
    final BackupRun run = overview.run;
    final ColorScheme scheme = Theme.of(context).colorScheme;
    final TextTheme text = Theme.of(context).textTheme;
    if (run.running) {
      final String who = run.requestedBy == null ? '' : ' by ${run.requestedBy}';
      final String when = createdStamp(run.startedAt);
      return Padding(
        padding: const EdgeInsets.only(top: AppSpacing.md),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              'Backing up... started$who${when.isEmpty ? '' : ' at $when'}',
              key: const ValueKey('backup-running'),
              style: text.bodyMedium,
            ),
            const SizedBox(height: AppSpacing.xs),
            const LinearProgressIndicator(minHeight: 3),
          ],
        ),
      );
    }
    final BackupRun done = _finished ?? run;
    if (done.message == null || done.status == 'idle') {
      return const SizedBox.shrink();
    }
    final bool failed = done.status == 'failed';
    return Padding(
      padding: const EdgeInsets.only(top: AppSpacing.md),
      child: Row(children: [
        Icon(
          failed ? Icons.error_outline : Icons.check_circle_outline,
          size: 18,
          color: failed ? scheme.error : context.semanticColors.success,
        ),
        const SizedBox(width: AppSpacing.sm),
        Expanded(
          child: Text(
            done.message!,
            key: const ValueKey('backup-result'),
            style: text.bodyMedium?.copyWith(
              color: failed ? scheme.error : null,
            ),
          ),
        ),
      ]),
    );
  }

  Widget _detail(BuildContext context, BackupEntry backup) {
    final TextTheme text = Theme.of(context).textTheme;
    return Container(
      key: const ValueKey('backup-detail'),
      constraints: const BoxConstraints(maxHeight: 200),
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        border: Border(
          top: BorderSide(color: Theme.of(context).dividerColor),
        ),
      ),
      child: SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(children: [
              Expanded(child: SelectableText(backup.path, style: text.bodySmall)),
              IconButton(
                key: const ValueKey('backup-copy-path'),
                tooltip: 'Copy the folder path',
                icon: const Icon(Icons.copy, size: 18),
                onPressed: () => unawaited(copyTextToClipboard(backup.path)),
              ),
            ]),
            if (backup.applicationVersion != null)
              Text('Application version ${backup.applicationVersion}',
                  style: text.bodySmall),
            if (backup.stores.isEmpty)
              Padding(
                padding: const EdgeInsets.only(top: AppSpacing.xs),
                child: Text('No per-store detail is recorded for this backup.',
                    style: text.bodySmall),
              )
            else
              Padding(
                padding: const EdgeInsets.only(top: AppSpacing.sm),
                child: Table(
                  columnWidths: const {
                    0: FlexColumnWidth(2),
                    1: FlexColumnWidth(),
                    2: FlexColumnWidth(),
                    3: FlexColumnWidth(),
                    4: FlexColumnWidth(3),
                  },
                  children: [
                    TableRow(children: [
                      for (final String head in const [
                        'Store',
                        'Tables',
                        'Size',
                        'Outcome',
                        'Detail',
                      ])
                        Text(head,
                            style: text.labelMedium
                                ?.copyWith(fontWeight: FontWeight.w600)),
                    ]),
                    for (final BackupStore store in backup.stores)
                      TableRow(children: [
                        Text(store.label, style: text.bodySmall),
                        Text('${store.tables}', style: text.bodySmall),
                        Text(size(store.sizeBytes), style: text.bodySmall),
                        Text(store.outcome, style: text.bodySmall),
                        Text(store.detail ?? '', style: text.bodySmall),
                      ]),
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final BackupOverview? overview = _overview;
    final List<BackupEntry> backups = overview?.backups ?? const [];
    final BackupEntry? selected = _selected;
    final Widget grid = overview == null && _error != null
        ? WorkspaceEmptyState(
            title: 'Backups could not be read',
            message: _error!,
          )
        : overview != null && backups.isEmpty
            ? const WorkspaceEmptyState(
                title: 'No backups yet',
                message: 'The first nightly backup is taken at 02:00. Use '
                    '"Back up now" to take one straight away.',
              )
            : EnterpriseDataGrid<BackupEntry>(
                items: backups,
                total: backups.length,
                pageOffset: 0,
                rowsPerPage: backups.isEmpty ? 1 : backups.length,
                columns: const [
                  GridColumn(key: 'taken', label: 'Taken'),
                  GridColumn(key: 'kind', label: 'Kind'),
                  GridColumn(key: 'status', label: 'Status'),
                  GridColumn(key: 'size', label: 'Size', numeric: true),
                  GridColumn(key: 'files', label: 'Stores', numeric: true),
                  GridColumn(key: 'by', label: 'Taken by'),
                ],
                id: (backup) => backup.path,
                cells: (backup) {
                  final String taken = createdStamp(backup.createdAt);
                  return [
                    taken.isEmpty ? backup.name : taken,
                    _kind(backup.kind),
                    _status(backup.complete),
                    size(backup.sizeBytes),
                    backup.files == null ? '-' : '${backup.files}',
                    backup.requestedBy ?? '—',
                  ];
                },
                selectedId: _selectedPath,
                onSelect: (backup) =>
                    setState(() => _selectedPath = backup.path),
                contextActions: const [WorkspaceContextAction.refresh],
                onContextAction: (action, backup) => unawaited(_load()),
                onPageChanged: (_) {},
              );
    return phase2Frame(
      title: 'Backups',
      description: "Copies of every firm's data, kept on the server PC.",
      actions: [
        IconButton(
          key: const ValueKey('backups-refresh'),
          tooltip: 'Refresh',
          icon: const Icon(Icons.refresh),
          onPressed: _loading ? null : () => unawaited(_load()),
        ),
        const SizedBox(width: AppSpacing.sm),
        FilledButton.icon(
          key: const ValueKey('backup-now'),
          onPressed: _running || _starting || overview == null
              ? null
              : () => unawaited(_start()),
          icon: const Icon(Icons.backup_outlined),
          label: const Text('Back up now'),
        ),
      ],
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            _info(context),
            _runStatus(context),
            if (_error != null && overview != null)
              Padding(
                padding: const EdgeInsets.only(top: AppSpacing.md),
                child: Text(
                  _error!,
                  key: const ValueKey('backup-error'),
                  style: Theme.of(context)
                      .textTheme
                      .bodyMedium
                      ?.copyWith(color: Theme.of(context).colorScheme.error),
                ),
              ),
            if (_loading) const LinearProgressIndicator(minHeight: 2),
            const SizedBox(height: AppSpacing.md),
            Expanded(child: grid),
            if (selected != null) _detail(context, selected),
          ],
        ),
      ),
    );
  }
}
