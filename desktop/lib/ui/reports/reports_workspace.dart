import 'dart:async';
import 'dart:io';

import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/entities.dart';
import '../../models/report.dart';
import '../workspace/desktop_framework.dart';
import '../workspace/module_catalog.dart';
import 'report_catalog.dart';

/// How a downloaded report file is written to disk. Tests inject one,
/// because a widget test cannot open a native save dialog. Answers the path
/// written, or null when the person cancelled.
typedef SaveReportFile = Future<String?> Function(
  String suggestedName,
  List<int> bytes,
);

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
    this.saveFile,
  });

  final ApiClient api;
  final PermissionService permissions;
  final bool hasActiveFirm;
  final String tabId;

  /// Where a downloaded file goes; null asks with the native save dialog.
  final SaveReportFile? saveFile;

  @override
  State<ReportsWorkspace> createState() => _ReportsWorkspaceState();
}

class _ReportsWorkspaceState extends State<ReportsWorkspace> {
  ReportDefinition? _selected;
  List<Json> _rows = const [];

  /// A dated report is paged a hundred rows at a time (D-RPT-18): the page
  /// on screen, and how many rows the window holds in all.
  static const int _pageSize = 100;
  int _page = 1;
  int _total = 0;
  bool _loading = false;
  String? _error;

  /// Shared by the sideways scroll view and its always-visible bar. A report
  /// wider than the window had neither a bar nor any other sign that columns
  /// lay off the right edge, and on a mouse the table could not be moved
  /// sideways at all without knowing Shift+wheel (plan item 10.8,
  /// 2026-09-13).
  final ScrollController _horizontal = ScrollController();

  // The period a report that requires one is asked for, opening on the
  // current month.
  final TextEditingController _from = TextEditingController();
  final TextEditingController _to = TextEditingController();

  // The return quarter a quarterly report is asked for (53.1), opening on the
  // last quarter that has ended -- the one a return is due for.
  final TextEditingController _financialYear = TextEditingController();
  int _quarter = 1;

  @override
  void dispose() {
    _horizontal.dispose();
    _from.dispose();
    _to.dispose();
    _financialYear.dispose();
    super.dispose();
  }

  /// A dated or quarterly report is paged; a snapshot is not.
  static bool _paged(ReportDefinition report) =>
      report.needsPeriod || report.quarterly;

  static String _iso(DateTime value) =>
      value.toIso8601String().split('T').first;

  /// `REPORT_VIEW` opens every report; a module's own view code opens that
  /// module's (D-RPT-4).
  bool _canRead(ReportDefinition report) =>
      (report.openToReportView &&
          widget.permissions.hasPermission('REPORT_VIEW')) ||
      widget.permissions.hasPermission(report.permission);

  bool get _canView => reportCatalog.any(_canRead);

  ReportArea get _area => widget.tabId == 'financial'
      ? ReportArea.financial
      : ReportArea.operational;

  List<ReportDefinition> get _reports => reportsFor(_area, canRead: _canRead);

  @override
  void initState() {
    super.initState();
    final DateTime now = DateTime.now();
    _from.text = _iso(DateTime(now.year, now.month, 1));
    _to.text = _iso(DateTime(now.year, now.month + 1, 0));
    final (String year, int quarter) = lastEndedReturnQuarter(now);
    _financialYear.text = year;
    _quarter = quarter;
    if (_reports.isNotEmpty) {
      _selected = _reports.first;
      unawaited(_load());
    }
  }

  /// The last "open showing that" request applied -- Home's "Invoices
  /// overdue" opens this screen on the overdue report.
  int _request = 0;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final ListViewRequest? request =
        ListViewRequestScope.of(context, 'reports/${widget.tabId}');
    if (request == null || request.serial == _request) return;
    _request = request.serial;
    final ReportDefinition? report =
        _reports.where((report) => report.id == request.view).firstOrNull;
    // A report this user may not read is not opened by asking for it; the
    // screen stays on its first report, as the menu would have opened it.
    if (report == null || report == _selected) return;
    _selected = report;
    _rows = const [];
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) unawaited(_load());
    });
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

  /// Which load is the latest: opened on a report for a reason, the screen
  /// asks for its first report and then for the one it was opened for, and
  /// the first answer must not land on top of the second.
  int _loads = 0;

  Future<void> _load({int page = 1}) async {
    final ReportDefinition? report = _selected;
    if (report == null || !widget.hasActiveFirm || !_canRead(report)) return;
    final int load = ++_loads;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final ReportPage result = await widget.api.reportRows(
        report.path,
        query: report.quarterly
            ? {
                'financial_year': _financialYear.text.trim(),
                'quarter': 'Q$_quarter',
                'page': '$page',
                'page_size': '$_pageSize',
              }
            : report.needsPeriod
                ? {
                    'from_date': _from.text.trim(),
                    'to_date': _to.text.trim(),
                    'page': '$page',
                    'page_size': '$_pageSize',
                  }
                : null,
        rowsKey: report.rowsKey,
      );
      if (!mounted || load != _loads) return;
      setState(() {
        _rows = result.rows;
        _total = result.total;
        _page = page;
      });
    } on ApiException catch (exception) {
      if (!mounted || load != _loads) return;
      setState(() {
        _error = exception.message;
        _rows = const [];
      });
    } finally {
      if (mounted && load == _loads) setState(() => _loading = false);
    }
  }

  bool _downloading = false;

  /// Download the report's file and save it where the person says.
  Future<void> _download(ReportDefinition report) async {
    final ReportFile? file = report.file;
    if (file == null || _downloading) return;
    setState(() => _downloading = true);
    try {
      final String year = _financialYear.text.trim();
      final (String name, List<int> bytes) = switch (file) {
        ReportFile.tds26q => (
            '26Q-$year-Q$_quarter.xlsx',
            await widget.api.tds26qFile(
              financialYear: year,
              quarter: 'Q$_quarter',
            ),
          ),
      };
      final String? path = await (widget.saveFile ?? _saveToDisk)(name, bytes);
      if (!mounted) return;
      NotificationService.show(
        context,
        path == null ? exportCancelledMessage : exportSavedMessage(path),
        kind: path == null
            ? AppNotificationKind.information
            : AppNotificationKind.success,
      );
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() => _error = exception.message);
    } finally {
      if (mounted) setState(() => _downloading = false);
    }
  }

  static Future<String?> _saveToDisk(String name, List<int> bytes) async {
    final FileSaveLocation? location = await getSaveLocation(
      suggestedName: name,
      acceptedTypeGroups: const [
        XTypeGroup(label: 'Excel workbook', extensions: ['xlsx']),
      ],
    );
    if (location == null) return null;
    await File(location.path).writeAsBytes(bytes, flush: true);
    return location.path;
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

  /// "1–100 of 2,340" with Previous and Next, for a dated report. The whole
  /// history used to arrive at once into a `DataTable` that is not
  /// virtualised (D-RPT-18); a hundred rows a page is what the server caps
  /// at, and the window above narrows it further.
  List<Widget> _pager(BuildContext context) {
    final int first = _total == 0 ? 0 : (_page - 1) * _pageSize + 1;
    final int last = (_page - 1) * _pageSize + _rows.length;
    final bool hasNext = last < _total;
    return [
      Text('$first–$last of $_total',
          style: Theme.of(context).textTheme.bodySmall),
      IconButton(
        tooltip: 'Previous page',
        onPressed: _loading || _page <= 1
            ? null
            : () => unawaited(_load(page: _page - 1)),
        icon: const Icon(Icons.chevron_left),
      ),
      IconButton(
        tooltip: 'Next page',
        onPressed: _loading || !hasNext
            ? null
            : () => unawaited(_load(page: _page + 1)),
        icon: const Icon(Icons.chevron_right),
      ),
    ];
  }

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
    if (Phase2Scope.of(context)) return _phase2Report(context, report, columns);
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
            if (report.needsPeriod) ...[
              if (!report.asOnDate) ...[
                SizedBox(
                  width: 130,
                  child: TextField(
                    key: const ValueKey<String>('report-from'),
                    controller: _from,
                    decoration: const InputDecoration(labelText: 'From'),
                    onSubmitted: (_) => unawaited(_load()),
                  ),
                ),
                const SizedBox(width: AppSpacing.sm),
              ],
              SizedBox(
                width: 130,
                child: TextField(
                  key: const ValueKey<String>('report-to'),
                  controller: _to,
                  decoration: InputDecoration(
                      labelText: report.asOnDate ? 'As on' : 'To'),
                  onSubmitted: (_) => unawaited(_load()),
                ),
              ),
              const SizedBox(width: AppSpacing.md),
            ],
            if (_paged(report)) ..._pager(context) else
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
              // Sideways outside, up-and-down inside: the horizontal bar then
              // sits at the bottom of the screen rather than under the last
              // row, where a long report would hide it.
              : Padding(
                  padding:
                      const EdgeInsets.symmetric(horizontal: AppSpacing.lg),
                  child: Scrollbar(
                    key: const ValueKey<String>('report-horizontal-scrollbar'),
                    controller: _horizontal,
                    thumbVisibility: true,
                    trackVisibility: true,
                    child: SingleChildScrollView(
                      controller: _horizontal,
                      scrollDirection: Axis.horizontal,
                      padding: const EdgeInsets.only(bottom: AppSpacing.md),
                      child: SingleChildScrollView(
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
                ),
        ),
      ],
    );
  }

  /// Phase 2: the report as every list is drawn (4.7) -- a compact line with
  /// its name, the dates and Refresh; the lists' grid, with status in words,
  /// Yes / No for true / false, figures right-aligned in Indian digits and
  /// the least important columns dropping first on a narrow window; the
  /// pager at the foot, as on a list.
  Widget _phase2Report(
    BuildContext context,
    ReportDefinition report,
    List<ReportColumn> columns,
  ) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
    Widget dateBox(String hint, Key key, TextEditingController controller) =>
        SizedBox(
          width: 150,
          height: 32,
          child: TextField(
            key: key,
            controller: controller,
            style: theme.textTheme.bodyMedium?.copyWith(fontSize: 13),
            decoration: InputDecoration(
              isDense: true,
              prefixText: '$hint  ',
              prefixStyle: theme.textTheme.bodySmall
                  ?.copyWith(color: scheme.onSurfaceVariant),
              contentPadding:
                  const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(5),
                borderSide: BorderSide(color: scheme.outlineVariant),
              ),
              enabledBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(5),
                borderSide: BorderSide(color: scheme.outlineVariant),
              ),
            ),
            onSubmitted: (_) => unawaited(_load()),
          ),
        );
    String shown(Json row, ReportColumn column) {
      final dynamic value = row[column.key];
      if (value is bool) return value ? 'Yes' : 'No';
      return cellValue(row, column.key);
    }

    final int rowsPerPage = _paged(report)
        ? _pageSize
        : (_rows.isEmpty ? 1 : _rows.length);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        // On the page's one line (4.5): which report, its dates, Refresh.
        Phase2LineTools(children: [
          Text(
            report.label,
            style: theme.textTheme.bodyMedium
                ?.copyWith(fontSize: 13, fontWeight: FontWeight.w600),
          ),
          // What question it answers, behind (i) as every title's.
          Tooltip(
            message: report.description,
            child: Icon(Icons.info_outline,
                size: 16, color: scheme.onSurfaceVariant),
          ),
          if (report.needsPeriod) ...[
            dateBox('From', const ValueKey<String>('report-from'), _from),
            dateBox('To', const ValueKey<String>('report-to'), _to),
          ],
          // One return quarter (53.1): the year it falls in, and which.
          if (report.quarterly) ...[
            dateBox('Year', const ValueKey<String>('report-financial-year'),
                _financialYear),
            SizedBox(
              height: 32,
              child: DropdownButton<int>(
                key: const ValueKey<String>('report-quarter'),
                value: _quarter,
                isDense: true,
                underline: const SizedBox.shrink(),
                style: theme.textTheme.bodyMedium?.copyWith(fontSize: 13),
                items: const [
                  DropdownMenuItem(value: 1, child: Text('Q1 Apr-Jun')),
                  DropdownMenuItem(value: 2, child: Text('Q2 Jul-Sep')),
                  DropdownMenuItem(value: 3, child: Text('Q3 Oct-Dec')),
                  DropdownMenuItem(value: 4, child: Text('Q4 Jan-Mar')),
                ],
                onChanged: (value) {
                  if (value == null) return;
                  setState(() => _quarter = value);
                  unawaited(_load());
                },
              ),
            ),
          ],
          if (report.file != null)
            TextButton.icon(
              key: const ValueKey<String>('report-download'),
              onPressed: _loading || _downloading
                  ? null
                  : () => unawaited(_download(report)),
              icon: const Icon(Icons.download_outlined, size: 16),
              label: const Text('Download'),
            ),
          Phase2Refresh(
            onPressed: _loading ? null : () => unawaited(_load()),
            child: const SizedBox.shrink(),
          ),
        ]),
        if (_error != null)
          Padding(
            padding: const EdgeInsets.all(AppSpacing.md),
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
              : EnterpriseDataGrid<Json>(
                  key: ValueKey<String>('report-grid-${report.id}'),
                  items: _rows,
                  total: _paged(report) ? _total : _rows.length,
                  pageOffset: _paged(report) ? (_page - 1) * _pageSize : 0,
                  rowsPerPage: rowsPerPage,
                  columns: [
                    for (final ReportColumn column in columns)
                      GridColumn(
                        key: column.key,
                        label: column.label,
                        numeric: column.numeric,
                      ),
                  ],
                  id: (row) => '${identityHashCode(row)}',
                  cells: (row) => [
                    for (final ReportColumn column in columns)
                      shown(row, column),
                  ],
                  onSelect: (_) {},
                  onPageChanged: (offset) => unawaited(
                    _load(page: offset ~/ _pageSize + 1),
                  ),
                ),
        ),
      ],
    );
  }
}

/// The last return quarter that has ended on [today]: the financial year as
/// `2026-27` and the quarter 1 to 4, April to June being 1. A TDS return is
/// filed after its quarter ends, so that is the one a screen opens on.
(String, int) lastEndedReturnQuarter(DateTime today) {
  final int startYear = today.month >= 4 ? today.year : today.year - 1;
  final int current = (today.month - 4) % 12 ~/ 3 + 1;
  final int year = current == 1 ? startYear - 1 : startYear;
  final int quarter = current == 1 ? 4 : current - 1;
  return ('$year-${((year + 1) % 100).toString().padLeft(2, '0')}', quarter);
}
