import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/security/permission_service.dart';
import '../../models/sales_analysis.dart';
import 'desktop_framework.dart';
import 'reason_prompt.dart';

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

/// One choice offered by a filter picker.
class AnalysisOption {
  const AnalysisOption({required this.id, required this.label});

  final String id;
  final String label;
}

/// The extra controls of the analysis: basis, filters, last-year comparison,
/// margin and saved layouts. A screen that passes none of it (the purchase
/// analysis, for now) gets the plain pivot.
class AnalysisAdvanced {
  const AnalysisAdvanced({
    required this.reportCode,
    required this.fetch,
    required this.pickers,
    required this.options,
    required this.listLayouts,
    required this.saveLayout,
    required this.deleteLayout,
  });

  /// The `report_code` saved layouts are filed under.
  final String reportCode;

  final Future<SalesAnalysis> Function({
    required String rows,
    String? columns,
    required String fromDate,
    required String toDate,
    required bool netOfReturns,
    required Map<String, String> filters,
    required String basis,
    required bool comparePreviousYear,
  }) fetch;

  /// Filter parameter -> the label of its picker, in menu order.
  final Map<String, String> pickers;

  /// What a picker offers for a typed search.
  final Future<List<AnalysisOption>> Function(String parameter, String search)
      options;

  final Future<List<ReportLayout>> Function() listLayouts;
  final Future<void> Function(String name, Map<String, dynamic> settings)
      saveLayout;
  final Future<void> Function(String id) deleteLayout;
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
    this.advanced,
  });

  /// Null leaves the screen as the plain pivot.
  final AnalysisAdvanced? advanced;

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
    this.saveExportOverride,
  });

  /// Where an export goes in a test, which cannot open a save dialog.
  final SaveExportOverride? saveExportOverride;

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
  // The entity filters the analysis is narrowed by; drill-down composes on
  // top of whatever is here. Labels are kept for the chips only.
  final Map<String, String> _filters = {};
  final Map<String, String> _filterLabels = {};
  String _basis = 'billed';
  bool _compare = false;
  bool _chart = false;
  SalesAnalysis _analysis = SalesAnalysis.empty;
  bool _loading = false;
  bool _loaded = false;
  String? _error;

  DateTime get _today => widget.today ?? DateTime.now();

  AnalysisAdvanced? get _advanced => widget.config.advanced;

  bool get _ordered => _advanced != null && _basis == 'ordered';

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
      final AnalysisAdvanced? advanced = _advanced;
      final SalesAnalysis analysis = advanced == null
          ? await widget.config.fetch(
              rows: _rows,
              columns: _columns,
              fromDate: _from.text.trim(),
              toDate: _to.text.trim(),
              netOfReturns: _netOfReturns,
              filters: _filters,
            )
          : await advanced.fetch(
              rows: _rows,
              columns: _columns,
              fromDate: _from.text.trim(),
              toDate: _to.text.trim(),
              netOfReturns: _netOfReturns,
              filters: _filters,
              basis: _basis,
              comparePreviousYear: _compare,
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
      case 'quantity':
        final double q = figures.quantity;
        return q == q.roundToDouble() ? q.toStringAsFixed(0) : q.toString();
      case 'invoices':
        return figures.invoices.toString();
      default:
        return _value(figures)?.toStringAsFixed(2) ?? '';
    }
  }

  /// The chosen figure as a number; null where it has none.
  double? _value(AnalysisFigures? figures) {
    if (figures == null) return null;
    switch (_figure) {
      case 'taxable':
        return figures.taxable;
      case 'tax':
        return figures.tax;
      case 'quantity':
        return figures.quantity;
      case 'invoices':
        return figures.invoices.toDouble();
      case 'average_bill':
        return figures.averageBill;
      default:
        return figures.net;
    }
  }

  /// Whether cost, margin and margin % are on offer: the server sends them
  /// only to someone who may see cost, on the billed basis.
  bool get _hasMargin => _analysis.grandTotal.margin != null;

  bool get _hasCompare => _compare && _analysis.previous != null;

  List<String> _extraHeaders() => [
        if (_hasMargin) ...const ['Cost', 'Margin', 'Margin %'],
        if (_hasCompare) ...const ['Last year', 'Change %'],
      ];

  String _money(double? value) => value?.toStringAsFixed(2) ?? '';

  /// What follows the Total column for one row: margin figures, then the
  /// year-before figure and the change against it.
  List<String> _extraTexts(AnalysisFigures? current, AnalysisFigures? before) {
    String change() {
      final double? now = _value(current);
      final double? then = _value(before);
      if (now == null || then == null || then == 0) return '';
      final double pct = (now - then) / then.abs() * 100;
      return '${pct >= 0 ? '+' : ''}${pct.toStringAsFixed(1)}%';
    }

    return [
      if (_hasMargin) ...[
        _money(current?.cost),
        _money(current?.margin),
        current?.marginPercent == null
            ? ''
            : '${current!.marginPercent!.toStringAsFixed(1)}%',
      ],
      if (_hasCompare) ...[
        _show(before ?? const AnalysisFigures()),
        change(),
      ],
    ];
  }

  // ---- filters, layouts, export -----------------------------------------

  Future<void> _addFilter(String parameter) async {
    final AnalysisAdvanced? advanced = _advanced;
    if (advanced == null) return;
    final AnalysisOption? picked = await showDialog<AnalysisOption>(
      context: context,
      builder: (context) => _OptionPickerDialog(
        title: advanced.pickers[parameter] ?? parameter,
        search: (text) => advanced.options(parameter, text),
      ),
    );
    if (picked == null || !mounted) return;
    setState(() {
      _filters[parameter] = picked.id;
      _filterLabels[parameter] = picked.label;
    });
    unawaited(_load());
  }

  void _removeFilter(String parameter) {
    setState(() {
      _filters.remove(parameter);
      _filterLabels.remove(parameter);
    });
    unawaited(_load());
  }

  Map<String, dynamic> _settings() => {
        'rows': _rows,
        'columns': _columns,
        'basis': _basis,
        'net_of_returns': _netOfReturns,
        'compare_previous_year': _compare,
        'filters': {..._filters},
        'filter_labels': {..._filterLabels},
        'from_date': _from.text.trim(),
        'to_date': _to.text.trim(),
      };

  void _applyLayout(ReportLayout layout) {
    final Map<String, dynamic> s = layout.settings;
    final String columnsText = (s['columns'] ?? '').toString();
    final String? columns = columnsText.isEmpty ? null : columnsText;
    final Map<String, String> filters = {
      if (s['filters'] is Map)
        for (final MapEntry<dynamic, dynamic> e
            in (s['filters'] as Map).entries)
          e.key.toString(): e.value.toString(),
    };
    final Map<String, dynamic> labels = s['filter_labels'] is Map
        ? Map<String, dynamic>.from(s['filter_labels'] as Map)
        : const {};
    final String from = (s['from_date'] ?? '').toString();
    final String to = (s['to_date'] ?? '').toString();
    setState(() {
      _rows = widget.config.dimensions.containsKey(s['rows'])
          ? s['rows'].toString()
          : widget.config.defaultRows;
      _columns = widget.config.dimensions.containsKey(columns) ? columns : null;
      _basis = s['basis'] == 'ordered' ? 'ordered' : 'billed';
      _netOfReturns = s['net_of_returns'] != false;
      _compare = s['compare_previous_year'] == true;
      _filters
        ..clear()
        ..addAll(filters);
      _filterLabels
        ..clear()
        ..addAll({
          for (final String key in filters.keys)
            key: labels[key]?.toString() ?? filters[key]!,
        });
      if (_isoDate.hasMatch(from)) _from.text = from;
      if (_isoDate.hasMatch(to)) _to.text = to;
    });
    unawaited(_load());
  }

  Future<void> _openLayouts() async {
    final AnalysisAdvanced? advanced = _advanced;
    if (advanced == null) return;
    final ReportLayout? chosen = await showDialog<ReportLayout>(
      context: context,
      builder: (context) => _LayoutsDialog(
        list: advanced.listLayouts,
        save: (name) => advanced.saveLayout(name, _settings()),
        delete: advanced.deleteLayout,
      ),
    );
    if (chosen != null && mounted) _applyLayout(chosen);
  }

  Future<void> _export() async {
    final String content = analysisCsv(_gridHeaders(), _gridRows());
    final ScaffoldMessengerState messenger = ScaffoldMessenger.of(context);
    final String name =
        widget.config.title.toLowerCase().replaceAll(' ', '-');
    try {
      final String? path = await saveExportedText(
        suggestedName: '$name.csv',
        content: content,
        override: widget.saveExportOverride,
      );
      messenger.showSnackBar(SnackBar(
        content: Text(
            path == null ? exportCancelledMessage : exportSavedMessage(path)),
      ));
    } on Object catch (error) {
      messenger.showSnackBar(SnackBar(content: Text('Export failed: $error')));
    }
  }

  List<String> _gridHeaders() => [
        widget.config.dimensions[_rows] ?? _rows,
        if (_columns != null)
          for (final AnalysisHeading c in _analysis.columns)
            c.label.isEmpty ? '(none)' : c.label,
        'Total',
        ..._extraHeaders(),
      ];

  List<List<String>> _gridRows() => [
        for (final AnalysisHeading row in _analysis.rows)
          [
            row.label.isEmpty ? '(none)' : row.label,
            if (_columns != null)
              for (final AnalysisHeading c in _analysis.columns)
                _show(_analysis.cell(row.key, c.key)),
            _show(_analysis.rowTotals[row.key]),
            ..._extraTexts(_analysis.rowTotals[row.key],
                _analysis.previous?.rowTotals[row.key]),
          ],
        [
          'Total',
          if (_columns != null)
            for (final AnalysisHeading c in _analysis.columns)
              _show(_analysis.columnTotals[c.key]),
          _show(_analysis.grandTotal),
          ..._extraTexts(_analysis.grandTotal, _analysis.previous?.grandTotal),
        ],
      ];

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
          if (_filters.isNotEmpty)
            Padding(
              padding: const EdgeInsets.fromLTRB(
                  AppSpacing.lg, 0, AppSpacing.lg, AppSpacing.sm),
              child: _filterChips(),
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
        if (_advanced != null)
          dropdown<String>(
            label: 'Basis',
            width: 170,
            value: _basis,
            options: const {'billed': 'Billed', 'ordered': 'Orders booked'},
            onChanged: (value) {
              if (value == null) return;
              setState(() => _basis = value);
              unawaited(_load());
            },
          ),
        if (_advanced != null)
          FilterChip(
            label: const Text('Compare with last year'),
            selected: _compare,
            onSelected: (value) {
              setState(() => _compare = value);
              unawaited(_load());
            },
          ),
        if (_advanced != null)
          PopupMenuButton<String>(
            tooltip: 'Add a filter',
            onSelected: (parameter) => unawaited(_addFilter(parameter)),
            itemBuilder: (context) => [
              for (final MapEntry<String, String> e
                  in _advanced!.pickers.entries)
                PopupMenuItem<String>(value: e.key, child: Text(e.value)),
            ],
            child: const Chip(
              avatar: Icon(Icons.filter_alt_outlined, size: 18),
              label: Text('Add filter'),
            ),
          ),
        if (_advanced != null)
          IconButton(
            tooltip: _chart ? 'Show the table' : 'Show a chart',
            onPressed: () => setState(() => _chart = !_chart),
            icon: Icon(_chart ? Icons.table_rows_outlined : Icons.bar_chart),
          ),
        if (_advanced != null)
          IconButton(
            tooltip: 'Export to CSV',
            onPressed: _analysis.isEmpty ? null : () => unawaited(_export()),
            icon: const Icon(Icons.download),
          ),
        if (_advanced != null)
          TextButton.icon(
            onPressed: () => unawaited(_openLayouts()),
            icon: const Icon(Icons.view_list_outlined),
            label: const Text('Layouts'),
          ),
        IconButton(
          tooltip: 'Refresh',
          onPressed: _loading ? null : () => unawaited(_load()),
          icon: const Icon(Icons.refresh),
        ),
      ],
    );
  }

  Widget _filterChips() => Wrap(
        spacing: AppSpacing.sm,
        runSpacing: AppSpacing.xs,
        children: [
          for (final MapEntry<String, String> e in _filters.entries)
            InputChip(
              label: Text('${_advanced?.pickers[e.key] ?? e.key}: '
                  '${_filterLabels[e.key] ?? e.value}'),
              onDeleted: () => _removeFilter(e.key),
            ),
        ],
      );

  Widget _body(BuildContext context) {
    if (_analysis.isEmpty) {
      if (!_loaded) return const SizedBox.shrink();
      return StandardEmptyState(
        type: EmptyStateType.noRecords,
        title: widget.config.emptyTitle,
        message: 'No ${widget.config.noun} was '
            '${_ordered ? 'booked' : 'billed'} between these dates for '
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
          !_ordered &&
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

    if (_chart && _advanced != null) return _chartView(context);
    final List<DataRow> rows = [
      for (final AnalysisHeading row in _analysis.rows)
        DataRow(cells: [
          DataCell(Text(row.label.isEmpty ? '(none)' : row.label)),
          if (hasColumns)
            for (final AnalysisHeading column in columns)
              figureCell(_analysis.cell(row.key, column.key), row, column),
          figureCell(_analysis.rowTotals[row.key], row, null, style: bold),
          for (final String text in _extraTexts(_analysis.rowTotals[row.key],
              _analysis.previous?.rowTotals[row.key]))
            DataCell(Text(text)),
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
          for (final String text in _extraTexts(
              _analysis.grandTotal, _analysis.previous?.grandTotal))
            DataCell(Text(text, style: bold)),
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
            for (final String header in _extraHeaders())
              DataColumn(label: Text(header), numeric: true),
          ],
          rows: rows,
        ),
      ),
    );
  }

  /// The row totals of the chosen figure as horizontal bars, largest first,
  /// top fifteen. Last year's figure rides beneath each bar when compared.
  Widget _chartView(BuildContext context) {
    final ColorScheme scheme = Theme.of(context).colorScheme;
    final TextTheme text = Theme.of(context).textTheme;
    final List<({String label, double now, double? before})> bars = [
      for (final AnalysisHeading row in _analysis.rows)
        (
          label: row.label.isEmpty ? '(none)' : row.label,
          now: _value(_analysis.rowTotals[row.key]) ?? 0,
          before: _hasCompare
              ? (_value(_analysis.previous?.rowTotals[row.key]) ?? 0)
              : null,
        ),
    ]..sort((a, b) => b.now.compareTo(a.now));
    final List<({String label, double now, double? before})> top =
        bars.take(15).toList();
    double most = 0;
    for (final item in top) {
      if (item.now > most) most = item.now;
      if ((item.before ?? 0) > most) most = item.before!;
    }
    Widget bar(double value, Color color) => LayoutBuilder(
          builder: (context, box) => Align(
            alignment: Alignment.centerLeft,
            child: Container(
              height: 12,
              width: most <= 0
                  ? 0
                  : box.maxWidth * (value < 0 ? 0 : value) / most,
              color: color,
            ),
          ),
        );
    return ListView(
      key: const ValueKey('analysis-chart'),
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg),
      children: [
        for (final item in top)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: AppSpacing.xs),
            child: Row(
              children: [
                SizedBox(
                  width: 180,
                  child: Text(item.label, overflow: TextOverflow.ellipsis),
                ),
                Expanded(
                  child: Column(
                    children: [
                      bar(item.now, scheme.primary),
                      if (item.before != null) ...[
                        const SizedBox(height: 2),
                        bar(item.before!, scheme.outline),
                      ],
                    ],
                  ),
                ),
                SizedBox(
                  width: 110,
                  child: Text(
                    item.now.toStringAsFixed(2),
                    textAlign: TextAlign.right,
                    style: text.bodySmall,
                  ),
                ),
              ],
            ),
          ),
      ],
    );
  }
}

/// A grid as CSV: a header line, then one line per row, quoted where a cell
/// holds a comma, a quote or a line break.
String analysisCsv(List<String> headers, List<List<String>> rows) {
  String cell(String value) => value.contains(RegExp(r'[",\n\r]'))
      ? '"${value.replaceAll('"', '""')}"'
      : value;
  return [
    for (final List<String> line in [headers, ...rows])
      line.map(cell).join(','),
  ].join('\r\n');
}

/// Search and choose one record for a filter. Lookups are asked as the person
/// types; a refusal is shown in the dialog rather than lost.
class _OptionPickerDialog extends StatefulWidget {
  const _OptionPickerDialog({required this.title, required this.search});

  final String title;
  final Future<List<AnalysisOption>> Function(String search) search;

  @override
  State<_OptionPickerDialog> createState() => _OptionPickerDialogState();
}

class _OptionPickerDialogState extends State<_OptionPickerDialog> {
  final TextEditingController _query = TextEditingController();
  List<AnalysisOption>? _options;
  String? _error;
  int _ticket = 0;

  @override
  void initState() {
    super.initState();
    unawaited(_run(''));
  }

  @override
  void dispose() {
    _query.dispose();
    super.dispose();
  }

  Future<void> _run(String text) async {
    final int ticket = ++_ticket;
    try {
      final List<AnalysisOption> options = await widget.search(text.trim());
      if (!mounted || ticket != _ticket) return;
      setState(() {
        _options = options;
        _error = null;
      });
    } on ApiException catch (exception) {
      if (!mounted || ticket != _ticket) return;
      setState(() => _error = exception.message);
    }
  }

  @override
  Widget build(BuildContext context) {
    final List<AnalysisOption>? options = _options;
    Widget list;
    if (_error != null) {
      list = Text(_error!);
    } else if (options == null) {
      list = const Center(child: CircularProgressIndicator());
    } else if (options.isEmpty) {
      list = const Text('Nothing matches.');
    } else {
      list = ListView(
        children: [
          for (final AnalysisOption option in options)
            ListTile(
              dense: true,
              title: Text(option.label),
              onTap: () => Navigator.of(context).pop(option),
            ),
        ],
      );
    }
    return AlertDialog(
      title: Text(widget.title),
      content: SizedBox(
        width: 420,
        height: 380,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            TextField(
              controller: _query,
              autofocus: true,
              decoration: const InputDecoration(labelText: 'Search'),
              onChanged: (value) => unawaited(_run(value)),
            ),
            const SizedBox(height: AppSpacing.md),
            Expanded(child: list),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
      ],
    );
  }
}

/// Saved layouts: open one, delete one, or save the screen as it is. The save
/// runs here, so a refusal stays on screen with what was typed.
class _LayoutsDialog extends StatefulWidget {
  const _LayoutsDialog({
    required this.list,
    required this.save,
    required this.delete,
  });

  final Future<List<ReportLayout>> Function() list;
  final Future<void> Function(String name) save;
  final Future<void> Function(String id) delete;

  @override
  State<_LayoutsDialog> createState() => _LayoutsDialogState();
}

class _LayoutsDialogState extends State<_LayoutsDialog> {
  List<ReportLayout>? _layouts;
  String? _error;

  @override
  void initState() {
    super.initState();
    unawaited(_refresh());
  }

  Future<void> _refresh() async {
    try {
      final List<ReportLayout> layouts = await widget.list();
      if (mounted) {
        setState(() {
          _layouts = layouts;
          _error = null;
        });
      }
    } on ApiException catch (exception) {
      if (mounted) setState(() => _error = exception.message);
    }
  }

  Future<void> _saveAs() async {
    final String? name = await askForReason(
      context,
      title: 'Save layout',
      explanation: 'Saves the rows, columns, basis, filters and period as '
          'they are now. A layout with the same name is replaced.',
      label: 'Name',
      confirmLabel: 'Save',
    );
    if (name == null) return;
    try {
      await widget.save(name);
      await _refresh();
    } on ApiException catch (exception) {
      if (mounted) setState(() => _error = exception.message);
    }
  }

  Future<void> _delete(ReportLayout layout) async {
    try {
      await widget.delete(layout.id);
      await _refresh();
    } on ApiException catch (exception) {
      if (mounted) setState(() => _error = exception.message);
    }
  }

  @override
  Widget build(BuildContext context) {
    final List<ReportLayout>? layouts = _layouts;
    Widget body;
    if (layouts == null) {
      body = _error != null
          ? Text(_error!)
          : const Center(child: CircularProgressIndicator());
    } else if (layouts.isEmpty) {
      body = const Text('No saved layouts yet.');
    } else {
      body = ListView(
        shrinkWrap: true,
        children: [
          for (final ReportLayout layout in layouts)
            ListTile(
              dense: true,
              title: Text(layout.name),
              onTap: () => Navigator.of(context).pop(layout),
              trailing: IconButton(
                tooltip: 'Delete ${layout.name}',
                icon: const Icon(Icons.delete_outline),
                onPressed: () => unawaited(_delete(layout)),
              ),
            ),
        ],
      );
    }
    return AlertDialog(
      title: const Text('Layouts'),
      content: SizedBox(
        width: 420,
        height: 320,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (_error != null && layouts != null)
              Padding(
                padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                child: Text(
                  _error!,
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
              ),
            Expanded(child: body),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => unawaited(_saveAs()),
          child: const Text('Save as...'),
        ),
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Close'),
        ),
      ],
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
