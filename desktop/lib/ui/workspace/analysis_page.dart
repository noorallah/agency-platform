import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/security/permission_service.dart';
import '../../models/sales_analysis.dart';
import 'desktop_framework.dart';

/// One document behind a cell of the pivot: an invoice or a bill.
class AnalysisDocument {
  const AnalysisDocument({
    required this.id,
    required this.number,
    required this.date,
    required this.net,
  });

  final String id;
  final String number;
  final String date;
  final double net;
}

/// Everything that differs between the sales and the purchase analysis. The
/// page itself is one widget, so a fix to the pivot lands in both.
class AnalysisConfig {
  const AnalysisConfig({
    required this.title,
    required this.noun,
    required this.nounPlural,
    required this.netLabel,
    required this.countLabel,
    required this.averageLabel,
    required this.emptyTitle,
    required this.permissionCodes,
    required this.defaultRows,
    required this.dimensions,
    required this.filterParameters,
    required this.fetch,
    required this.fetchDocuments,
  });

  /// Heading of the refusal states, e.g. "Sales analysis".
  final String title;

  /// "invoice" / "bill", singular and plural, for dialog and empty texts.
  final String noun;
  final String nounPlural;

  /// Labels of the figures that are named differently: net, count, average.
  final String netLabel;
  final String countLabel;
  final String averageLabel;
  final String emptyTitle;

  /// Any one of these opens the page.
  final List<String> permissionCodes;
  final String defaultRows;

  /// Dimension code -> label, in the order the dropdowns offer them.
  final Map<String, String> dimensions;

  /// Entity dimension -> the filter parameter that narrows to one of it. A
  /// time dimension is absent here and narrows the dates instead.
  final Map<String, String> filterParameters;

  final Future<SalesAnalysis> Function({
    required String rows,
    String? columns,
    required String fromDate,
    required String toDate,
    required bool netOfReturns,
    required Map<String, String> filters,
  }) fetch;

  final Future<List<AnalysisDocument>> Function({
    required String fromDate,
    required String toDate,
    required Map<String, String> filters,
  }) fetchDocuments;
}

/// Billed documents pivoted by one or two dimensions, with drill-down.
///
/// Nothing is stored: the server derives every figure from the documents (net
/// of returns unless asked otherwise) on each read, so the page only chooses
/// the shape and the period.
class AnalysisPage extends StatefulWidget {
  const AnalysisPage({
    super.key,
    required this.config,
    required this.permissions,
    required this.hasActiveFirm,
    this.today,
  });

  final AnalysisConfig config;
  final PermissionService permissions;
  final bool hasActiveFirm;

  /// Overridable so a test is not at the mercy of the calendar.
  final DateTime? today;

  @override
  State<AnalysisPage> createState() => _AnalysisPageState();
}

const Set<String> _timeDimensions = {'day', 'week', 'month', 'quarter', 'year'};

String _iso(DateTime date) =>
    '${date.year.toString().padLeft(4, '0')}-'
    '${date.month.toString().padLeft(2, '0')}-'
    '${date.day.toString().padLeft(2, '0')}';

final RegExp _isoDate = RegExp(r'^\d{4}-\d{2}-\d{2}$');

class _AnalysisPageState extends State<AnalysisPage> {
  final TextEditingController _from = TextEditingController();
  final TextEditingController _to = TextEditingController();
  late String _rows = widget.config.defaultRows;
  String? _columns;
  String _figure = 'net';
  bool _netOfReturns = true;
  // The entity filters the analysis is narrowed by. The page offers no
  // control for them yet, but drill-down composes on top of whatever is here.
  final Map<String, String> _filters = {};
  SalesAnalysis _analysis = SalesAnalysis.empty;
  bool _loading = false;
  bool _loaded = false;
  String? _error;

  DateTime get _today => widget.today ?? DateTime.now();

  bool get _canView =>
      widget.permissions.hasAnyPermission(widget.config.permissionCodes);

  @override
  void initState() {
    super.initState();
    final DateTime today = _today;
    _from.text = _iso(DateTime(today.year, today.month, 1));
    _to.text = _iso(today);
    if (widget.hasActiveFirm && _canView) unawaited(_load());
  }

  @override
  void dispose() {
    _from.dispose();
    _to.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    if (!_isoDate.hasMatch(_from.text.trim()) ||
        !_isoDate.hasMatch(_to.text.trim())) {
      setState(() => _error = 'Dates are written YYYY-MM-DD.');
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final SalesAnalysis analysis = await widget.config.fetch(
        rows: _rows,
        columns: _columns,
        fromDate: _from.text.trim(),
        toDate: _to.text.trim(),
        netOfReturns: _netOfReturns,
        filters: _filters,
      );
      if (!mounted) return;
      setState(() {
        _analysis = analysis;
        _loaded = true;
      });
    } on ApiException catch (exception) {
      if (!mounted) return;
      // Clear the pane: figures from another shape must not sit under an
      // error that says the new one failed.
      setState(() {
        _error = exception.message;
        _analysis = SalesAnalysis.empty;
      });
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _preset(DateTime from, DateTime to) {
    _from.text = _iso(from);
    _to.text = _iso(to);
    unawaited(_load());
  }

  void _thisMonth() {
    final DateTime t = _today;
    _preset(DateTime(t.year, t.month, 1), t);
  }

  void _lastMonth() {
    final DateTime t = _today;
    _preset(DateTime(t.year, t.month - 1, 1), DateTime(t.year, t.month, 0));
  }

  void _thisFinancialYear() {
    final DateTime t = _today;
    final int year = t.month >= 4 ? t.year : t.year - 1;
    _preset(DateTime(year, 4, 1), t);
  }

  // ---- drill-down -------------------------------------------------------

  /// The query for the documents behind a cell: the page's own filters, plus
  /// the row's and column's values. An entity heading becomes the filter
  /// parameter its dimension maps to; a time heading narrows the dates,
  /// intersected with the page's period. Null when a heading has no key (the
  /// "(none)" bucket), which no filter can express.
  ({String from, String to, Map<String, String> filters})? _drillQuery(
    AnalysisHeading? row,
    AnalysisHeading? column,
  ) {
    String from = _from.text.trim();
    String to = _to.text.trim();
    final Map<String, String> filters = {..._filters};
    bool apply(String? dimension, AnalysisHeading? heading) {
      if (dimension == null || heading == null) return true;
      if (_timeDimensions.contains(dimension)) {
        final String? f = heading.fromDate;
        final String? t = heading.toDate;
        if (f != null && f.compareTo(from) > 0) from = f;
        if (t != null && t.compareTo(to) < 0) to = t;
        return true;
      }
      if (heading.key.isEmpty) return false;
      final String? parameter = widget.config.filterParameters[dimension];
      if (parameter == null) return false;
      filters[parameter] = heading.key;
      return true;
    }

    if (!apply(_rows, row)) return null;
    if (!apply(_columns, column)) return null;
    return (from: from, to: to, filters: filters);
  }

  Future<void> _openDocuments(
    String title,
    AnalysisHeading? row,
    AnalysisHeading? column,
  ) async {
    final query = _drillQuery(row, column);
    if (query == null) return;
    await showDialog<void>(
      context: context,
      builder: (context) => _DocumentsDialog(
        title: title,
        nounPlural: widget.config.nounPlural,
        load: () => widget.config.fetchDocuments(
          fromDate: query.from,
          toDate: query.to,
          filters: query.filters,
        ),
      ),
    );
  }

  // ---- figures ----------------------------------------------------------

  String _show(AnalysisFigures? figures) {
    if (figures == null) return '';
    switch (_figure) {
      case 'taxable':
        return figures.taxable.toStringAsFixed(2);
      case 'tax':
        return figures.tax.toStringAsFixed(2);
      case 'quantity':
        final double q = figures.quantity;
        return q == q.roundToDouble() ? q.toStringAsFixed(0) : q.toString();
      case 'invoices':
        return figures.invoices.toString();
      case 'average_bill':
        return figures.averageBill?.toStringAsFixed(2) ?? '';
      default:
        return figures.net.toStringAsFixed(2);
    }
  }

  // ---- build ------------------------------------------------------------

  @override
  Widget build(BuildContext context) {
    final String title = widget.config.title;
    if (!_canView) {
      return StandardEmptyState(
        type: EmptyStateType.noPermissions,
        title: title,
        message: 'You do not have permission to view ${title.toLowerCase()}.',
      );
    }
    if (!widget.hasActiveFirm) {
      return StandardEmptyState(
        type: EmptyStateType.noFirmSelected,
        title: title,
        message: 'Choose a firm to use ${title.toLowerCase()}.',
      );
    }
    return LoadingOverlay(
      loading: _loading,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.all(AppSpacing.lg),
            child: _controls(),
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
          Expanded(child: _body(context)),
        ],
      ),
    );
  }

  Widget _controls() {
    Widget dropdown<T>({
      required String label,
      required double width,
      required T? value,
      required Map<T, String> options,
      required void Function(T?) onChanged,
    }) =>
        SizedBox(
          width: width,
          child: DropdownButtonFormField<T>(
            initialValue: value,
            isExpanded: true,
            decoration: InputDecoration(labelText: label),
            items: [
              for (final MapEntry<T, String> e in options.entries)
                DropdownMenuItem<T>(value: e.key, child: Text(e.value)),
            ],
            onChanged: onChanged,
          ),
        );
    return Wrap(
      spacing: AppSpacing.md,
      runSpacing: AppSpacing.md,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        dropdown<String>(
          label: 'Rows',
          width: 170,
          value: _rows,
          options: widget.config.dimensions,
          onChanged: (value) {
            if (value == null) return;
            setState(() => _rows = value);
            unawaited(_load());
          },
        ),
        dropdown<String>(
          label: 'Columns',
          width: 170,
          value: _columns ?? '',
          options: {'': 'None', ...widget.config.dimensions},
          onChanged: (value) {
            setState(() => _columns = (value == null || value.isEmpty)
                ? null
                : value);
            unawaited(_load());
          },
        ),
        dropdown<String>(
          label: 'Figure',
          width: 160,
          value: _figure,
          options: {
            'net': widget.config.netLabel,
            'taxable': 'Taxable value',
            'tax': 'Tax',
            'quantity': 'Quantity',
            'invoices': widget.config.countLabel,
            'average_bill': widget.config.averageLabel,
          },
          onChanged: (value) {
            if (value != null) setState(() => _figure = value);
          },
        ),
        SizedBox(
          width: 130,
          child: TextField(
            controller: _from,
            decoration: const InputDecoration(
              labelText: 'From',
              hintText: 'YYYY-MM-DD',
            ),
            onSubmitted: (_) => unawaited(_load()),
          ),
        ),
        SizedBox(
          width: 130,
          child: TextField(
            controller: _to,
            decoration: const InputDecoration(
              labelText: 'To',
              hintText: 'YYYY-MM-DD',
            ),
            onSubmitted: (_) => unawaited(_load()),
          ),
        ),
        TextButton(onPressed: _thisMonth, child: const Text('This month')),
        TextButton(onPressed: _lastMonth, child: const Text('Last month')),
        TextButton(
          onPressed: _thisFinancialYear,
          child: const Text('This financial year'),
        ),
        Row(mainAxisSize: MainAxisSize.min, children: [
          Switch(
            value: _netOfReturns,
            onChanged: (value) {
              setState(() => _netOfReturns = value);
              unawaited(_load());
            },
          ),
          const Text('Net of returns'),
        ]),
        IconButton(
          tooltip: 'Refresh',
          onPressed: _loading ? null : () => unawaited(_load()),
          icon: const Icon(Icons.refresh),
        ),
      ],
    );
  }

  Widget _body(BuildContext context) {
    if (_analysis.isEmpty) {
      if (!_loaded) return const SizedBox.shrink();
      return StandardEmptyState(
        type: EmptyStateType.noRecords,
        title: widget.config.emptyTitle,
        message: 'No ${widget.config.noun} was billed between these dates for '
            'the filters chosen.',
      );
    }
    final TextStyle? bold = Theme.of(context).textTheme.titleSmall;
    final ColorScheme scheme = Theme.of(context).colorScheme;
    final bool hasColumns = _columns != null;
    final String rowLabel = widget.config.dimensions[_rows] ?? _rows;
    final List<AnalysisHeading> columns = _analysis.columns;

    DataCell figureCell(
      AnalysisFigures? figures,
      AnalysisHeading? row,
      AnalysisHeading? column, {
      TextStyle? style,
    }) {
      final bool drillable = row != null &&
          figures != null &&
          figures.invoices > 0 &&
          _drillQuery(row, column) != null;
      return DataCell(
        Text(_show(figures), style: style),
        onTap: drillable
            ? () => unawaited(_openDocuments(
                  '${row.label}'
                  '${column == null || !hasColumns ? '' : ' / ${column.label}'}',
                  row,
                  column,
                ))
            : null,
      );
    }

    final List<DataRow> rows = [
      for (final AnalysisHeading row in _analysis.rows)
        DataRow(cells: [
          DataCell(Text(row.label.isEmpty ? '(none)' : row.label)),
          if (hasColumns)
            for (final AnalysisHeading column in columns)
              figureCell(_analysis.cell(row.key, column.key), row, column),
          figureCell(_analysis.rowTotals[row.key], row, null, style: bold),
        ]),
      DataRow(
        color: WidgetStatePropertyAll(scheme.surfaceContainerHighest),
        cells: [
          DataCell(Text('Total', style: bold)),
          if (hasColumns)
            for (final AnalysisHeading column in columns)
              DataCell(Text(_show(_analysis.columnTotals[column.key]),
                  style: bold)),
          DataCell(Text(_show(_analysis.grandTotal), style: bold)),
        ],
      ),
    ];
    return SingleChildScrollView(
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg),
      child: Phase2WideTable(
        table: DataTable(
          columns: [
            DataColumn(label: Text(rowLabel)),
            if (hasColumns)
              for (final AnalysisHeading column in columns)
                DataColumn(
                  label: Text(column.label.isEmpty ? '(none)' : column.label),
                  numeric: true,
                ),
            const DataColumn(label: Text('Total'), numeric: true),
          ],
          rows: rows,
        ),
      ),
    );
  }
}

/// The documents behind one cell. Loads on open so a refusal is shown inside
/// the dialog rather than lost.
class _DocumentsDialog extends StatefulWidget {
  const _DocumentsDialog({
    required this.title,
    required this.nounPlural,
    required this.load,
  });

  final String title;
  final String nounPlural;
  final Future<List<AnalysisDocument>> Function() load;

  @override
  State<_DocumentsDialog> createState() => _DocumentsDialogState();
}

class _DocumentsDialogState extends State<_DocumentsDialog> {
  List<AnalysisDocument>? _documents;
  String? _error;

  @override
  void initState() {
    super.initState();
    unawaited(_fetch());
  }

  Future<void> _fetch() async {
    try {
      final List<AnalysisDocument> documents = await widget.load();
      if (mounted) setState(() => _documents = documents);
    } on ApiException catch (exception) {
      if (mounted) setState(() => _error = exception.message);
    }
  }

  @override
  Widget build(BuildContext context) {
    final List<AnalysisDocument>? documents = _documents;
    Widget content;
    if (_error != null) {
      content = Text(_error!);
    } else if (documents == null) {
      content = const Center(child: CircularProgressIndicator());
    } else if (documents.isEmpty) {
      content = Text('No ${widget.nounPlural}.');
    } else {
      content = ListView(
        shrinkWrap: true,
        children: [
          for (final AnalysisDocument document in documents)
            ListTile(
              dense: true,
              title: Text(document.number),
              subtitle: Text(document.date),
              trailing: Text(document.net.toStringAsFixed(2)),
            ),
        ],
      );
    }
    return AlertDialog(
      title: Text(widget.title.isEmpty ? 'Documents' : widget.title),
      content: SizedBox(width: 420, height: 360, child: content),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Close'),
        ),
      ],
    );
  }
}
