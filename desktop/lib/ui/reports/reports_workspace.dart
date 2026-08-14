import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/security/permission_service.dart';
import '../../models/entities.dart';
import '../../models/report.dart';
import '../workspace/desktop_framework.dart';
import '../workspace/module_catalog.dart';
import 'report_catalog.dart';

/// The reports the server has always been able to produce.
///
/// Thirty-four report endpoints existed across seven modules and nothing in the
/// client called one of them, while `REPORT_VIEW` was seeded and granted. This
/// is a list of reports and a grid: the reports are data, so a new one is a
/// catalogue entry rather than a screen.
class ReportsWorkspace extends StatefulWidget {
  const ReportsWorkspace({
    super.key,
    required this.api,
    required this.permissions,
    required this.hasActiveFirm,
    required this.tabId,
  });

  final ApiClient api;
  final PermissionService permissions;
  final bool hasActiveFirm;
  final String tabId;

  @override
  State<ReportsWorkspace> createState() => _ReportsWorkspaceState();
}

class _ReportsWorkspaceState extends State<ReportsWorkspace> {
  ReportDefinition? _selected;
  List<Json> _rows = const [];
  bool _loading = false;
  String? _error;

  bool get _canView => widget.permissions.hasPermission('REPORT_VIEW');

  ReportArea get _area => widget.tabId == 'financial'
      ? ReportArea.financial
      : ReportArea.operational;

  List<ReportDefinition> get _reports => reportsFor(_area);

  @override
  void initState() {
    super.initState();
    if (_reports.isNotEmpty) {
      _selected = _reports.first;
      unawaited(_load());
    }
  }

  @override
  void didUpdateWidget(ReportsWorkspace oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.tabId == widget.tabId) return;
    // A different tab is a different set of reports, so the one on screen is
    // not one of them any more.
    setState(() {
      _selected = _reports.isEmpty ? null : _reports.first;
      _rows = const [];
    });
    if (_selected != null) unawaited(_load());
  }

  Future<void> _load() async {
    final ReportDefinition? report = _selected;
    if (report == null || !widget.hasActiveFirm || !_canView) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final List<Json> rows = await widget.api.reportRows(report.path);
      if (!mounted) return;
      setState(() => _rows = rows);
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() {
        _error = exception.message;
        _rows = const [];
      });
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) => ModuleWorkspaceFrame(
        title: ModuleCatalog.byId(AppModule.reports).label,
        description: 'What the firm has been doing, and what it is owed.',
        breadcrumbs: const ['Workspace', 'Reports'],
        child: _content(context),
      );

  Widget _content(BuildContext context) {
    if (!_canView) {
      return const StandardEmptyState(
        type: EmptyStateType.noPermissions,
        title: 'Reports',
        message: 'You do not have permission to read reports.',
      );
    }
    if (!widget.hasActiveFirm) {
      return const StandardEmptyState(
        type: EmptyStateType.noFirmSelected,
        title: 'Reports',
        message: 'Choose a firm to see its reports.',
      );
    }
    return LoadingOverlay(
      loading: _loading,
      child: Row(children: [
        SizedBox(width: 300, child: _picker(context)),
        const VerticalDivider(width: 1),
        Expanded(child: _report(context)),
      ]),
    );
  }

  Widget _picker(BuildContext context) => ListView.separated(
        itemCount: _reports.length,
        separatorBuilder: (_, __) => const Divider(height: 1),
        itemBuilder: (context, index) {
          final ReportDefinition report = _reports[index];
          return ListTile(
            dense: true,
            selected: report.id == _selected?.id,
            title: Text(report.label),
            onTap: () {
              setState(() => _selected = report);
              unawaited(_load());
            },
          );
        },
      );

  Widget _report(BuildContext context) {
    final ReportDefinition? report = _selected;
    if (report == null) {
      return const StandardEmptyState(
        type: EmptyStateType.noRecords,
        title: 'Nothing here yet',
        message: 'No report is defined for this tab.',
      );
    }
    final List<ReportColumn> columns = columnsFor(report, _rows);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: Row(children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(report.label,
                      style: Theme.of(context).textTheme.titleMedium),
                  // What question it answers: "Reconciliation" tells nobody
                  // what is being reconciled.
                  Text(report.description,
                      style: Theme.of(context).textTheme.bodySmall),
                ],
              ),
            ),
            Text('${_rows.length} row(s)',
                style: Theme.of(context).textTheme.bodySmall),
            const SizedBox(width: AppSpacing.md),
            IconButton(
              tooltip: 'Refresh',
              onPressed: _loading ? null : () => unawaited(_load()),
              icon: const Icon(Icons.refresh),
            ),
          ]),
        ),
        if (_error != null)
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg),
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
                  title: 'Nothing to report',
                  message: 'This firm has nothing matching it yet.',
                )
              : SingleChildScrollView(
                  padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg),
                  child: SingleChildScrollView(
                    scrollDirection: Axis.horizontal,
                    child: DataTable(
                      columns: [
                        for (final ReportColumn column in columns)
                          DataColumn(
                            label: Text(column.label),
                            numeric: column.numeric,
                          ),
                      ],
                      rows: [
                        for (final Json row in _rows)
                          DataRow(cells: [
                            for (final ReportColumn column in columns)
                              DataCell(Text(cellValue(row, column.key))),
                          ]),
                      ],
                    ),
                  ),
                ),
        ),
      ],
    );
  }
}
