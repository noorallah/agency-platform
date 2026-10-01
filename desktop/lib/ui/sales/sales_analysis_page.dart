import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/security/permission_service.dart';
import '../../models/sales_analysis.dart';
import '../workspace/desktop_framework.dart';

/// Billed sales pivoted by one or two dimensions, with drill-down.
///
/// Nothing is stored: the server derives every figure from the invoices (net
/// of returns unless asked otherwise) on each read, so the page only chooses
/// the shape and the period.
class SalesAnalysisPage extends StatefulWidget {
  const SalesAnalysisPage({
    super.key,
    required this.api,
    required this.permissions,
    required this.hasActiveFirm,
    this.today,
  });

  final ApiClient api;
  final PermissionService permissions;
  final bool hasActiveFirm;

  /// Overridable so a test is not at the mercy of the calendar.
  final DateTime? today;

  @override
  State<SalesAnalysisPage> createState() => _SalesAnalysisPageState();
}

/// Dimension code -> label, in the order the dropdowns offer them.
const Map<String, String> _dimensions = {
  'day': 'Day',
  'week': 'Week',
  'month': 'Month',
  'quarter': 'Quarter',
  'year': 'Year',
  'product': 'Product',
  'category': 'Category',
  'customer': 'Customer',
  'customer_group': 'Customer group',
  'salesman': 'Salesman',
  'territory': 'Territory',
  'route': 'Route',
  'branch': 'Branch',
};

const Set<String> _timeDimensions = {'day', 'week', 'month', 'quarter', 'year'};

/// The one figure shown in each cell.
const Map<String, String> _figures = {
  'net': 'Net sales',
  'taxable': 'Taxable value',
  'tax': 'Tax',
  'quantity': 'Quantity',
  'invoices': 'Invoices',
  'average_bill': 'Average bill',
};

String _iso(DateTime date) =>
    '${date.year.toString().padLeft(4, '0')}-'
    '${date.month.toString().padLeft(2, '0')}-'
    '${date.day.toString().padLeft(2, '0')}';

final RegExp _isoDate = RegExp(r'^\d{4}-\d{2}-\d{2}$');

class _SalesAnalysisPageState extends State<SalesAnalysisPage> {
  final TextEditingController _from = TextEditingController();
  final TextEditingController _to = TextEditingController();
  String _rows = 'customer';
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
      widget.permissions.hasAnyPermission(['SALES_VIEW', 'REPORT_VIEW']);

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
      final SalesAnalysis analysis = await widget.api.salesAnalysis(
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

  /// The query for the invoices behind a cell: the page's own filters, plus
  /// the row's and column's values. An entity heading becomes `<dim>_id`; a
  /// time heading narrows the dates, intersected with the page's period.
  /// Null when a heading has no key (the "(none)" bucket), which no filter
  /// can express.
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
      filters['${dimension}_id'] = heading.key;
      return true;
    }

    if (!apply(_rows, row)) return null;
    if (!apply(_columns, column)) return null;
    return (from: from, to: to, filters: filters);
  }

  Future<void> _openInvoices(
    String title,
    AnalysisHeading? row,
    AnalysisHeading? column,
  ) async {
    final query = _drillQuery(row, column);
    if (query == null) return;
    await showDialog<void>(
      context: context,
      builder: (context) => _InvoicesDialog(
        title: title,
        load: () => widget.api.salesAnalysisInvoices(
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
    if (!_canView) {
      return const StandardEmptyState(
        type: EmptyStateType.noPermissions,
        title: 'Sales analysis',
        message: 'You do not have permission to view sales analysis.',
      );
    }
    if (!widget.hasActiveFirm) {
      return const StandardEmptyState(
        type: EmptyStateType.noFirmSelected,
        title: 'Sales analysis',
        message: 'Choose a firm to analyse its sales.',
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
          options: _dimensions,
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
          options: {'': 'None', ..._dimensions},
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
          options: _figures,
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
      return const StandardEmptyState(
        type: EmptyStateType.noRecords,
        title: 'Nothing sold in this period',
        message: 'No invoice was billed between these dates for the filters '
            'chosen.',
      );
    }
    final TextStyle? bold = Theme.of(context).textTheme.titleSmall;
    final ColorScheme scheme = Theme.of(context).colorScheme;
    final bool hasColumns = _columns != null;
    final String rowLabel = _dimensions[_rows] ?? _rows;
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
            ? () => unawaited(_openInvoices(
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

/// The invoices behind one cell. Loads on open so a refusal is shown inside
/// the dialog rather than lost.
class _InvoicesDialog extends StatefulWidget {
  const _InvoicesDialog({required this.title, required this.load});

  final String title;
  final Future<List<AnalysisInvoice>> Function() load;

  @override
  State<_InvoicesDialog> createState() => _InvoicesDialogState();
}

class _InvoicesDialogState extends State<_InvoicesDialog> {
  List<AnalysisInvoice>? _invoices;
  String? _error;

  @override
  void initState() {
    super.initState();
    unawaited(_fetch());
  }

  Future<void> _fetch() async {
    try {
      final List<AnalysisInvoice> invoices = await widget.load();
      if (mounted) setState(() => _invoices = invoices);
    } on ApiException catch (exception) {
      if (mounted) setState(() => _error = exception.message);
    }
  }

  @override
  Widget build(BuildContext context) {
    final List<AnalysisInvoice>? invoices = _invoices;
    Widget content;
    if (_error != null) {
      content = Text(_error!);
    } else if (invoices == null) {
      content = const Center(child: CircularProgressIndicator());
    } else if (invoices.isEmpty) {
      content = const Text('No invoices.');
    } else {
      content = ListView(
        shrinkWrap: true,
        children: [
          for (final AnalysisInvoice invoice in invoices)
            ListTile(
              dense: true,
              title: Text(invoice.invoiceNumber),
              subtitle: Text(invoice.invoiceDate),
              trailing: Text(invoice.net.toStringAsFixed(2)),
            ),
        ],
      );
    }
    return AlertDialog(
      title: Text(widget.title.isEmpty ? 'Invoices' : widget.title),
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
