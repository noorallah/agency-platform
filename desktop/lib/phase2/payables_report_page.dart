import 'dart:async';

import 'package:flutter/material.dart';

import '../core/api/api_client.dart';
import '../core/design/design_tokens.dart';
import '../models/entities.dart' show Json;
import 'indian_format.dart';

/// Buy > Money > Payables by Month (PG-2, backlog 85): what each supplier is
/// owed (or was paid) month by month, a total row, a line saying whether the
/// grid agrees with control account 2100, and a stacked chart of the top five
/// suppliers.
///
/// Everything is read from one server report; the page adds up nothing the
/// server did not already say, so the grid and the books check cannot differ.
class PayablesReportPage extends StatefulWidget {
  const PayablesReportPage({
    super.key,
    required this.api,
    required this.onOpenBills,
  });

  final ApiClient api;

  /// Opens the Purchase Invoices list, where a supplier's bills are.
  final VoidCallback onOpenBills;

  @override
  State<PayablesReportPage> createState() => _PayablesReportPageState();
}

class _PayablesReportPageState extends State<PayablesReportPage> {
  DateTime _asOf = DateTime.now();
  String _basis = 'invoice';
  int _months = 6;
  String _view = 'owed';
  String? _vendorId;
  String? _branchId;
  List<MapEntry<String, String>> _vendors = const [];
  List<MapEntry<String, String>> _branches = const [];
  Json? _data;
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    unawaited(_loadChoices());
    unawaited(_load());
  }

  Future<void> _loadChoices() async {
    try {
      final vendors = await widget.api.vendors();
      final branches = await widget.api.branches(pageSize: 100);
      if (!mounted) return;
      setState(() {
        _vendors = [for (final v in vendors.items) MapEntry(v.id, v.name)];
        _branches = [for (final b in branches.items) MapEntry(b.id, b.name)];
      });
    } on Object {
      // The filters stay at "All"; the report itself still loads.
    }
  }

  String _iso(DateTime d) => '${d.year.toString().padLeft(4, '0')}-'
      '${d.month.toString().padLeft(2, '0')}-'
      '${d.day.toString().padLeft(2, '0')}';

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final Json data = await widget.api.purchasePayables(
        asOf: _iso(_asOf),
        basis: _basis,
        months: _months,
        view: _view,
        vendorId: _vendorId,
        branchId: _view == 'paid' ? null : _branchId,
      );
      if (!mounted) return;
      setState(() {
        _data = data;
        _loading = false;
      });
    } on Object catch (error) {
      if (!mounted) return;
      setState(() {
        _error = '$error';
        _loading = false;
      });
    }
  }

  void _change(VoidCallback change) {
    setState(change);
    unawaited(_load());
  }

  Future<void> _pickDate() async {
    final DateTime? picked = await showDatePicker(
      context: context,
      initialDate: _asOf,
      firstDate: DateTime(2000),
      lastDate: DateTime(2100),
    );
    if (picked != null) _change(() => _asOf = picked);
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Payables by month', style: theme.textTheme.titleLarge),
            const SizedBox(height: AppSpacing.md),
            _filters(),
            const SizedBox(height: AppSpacing.md),
            if (_loading) const LinearProgressIndicator(),
            if (_error != null)
              Text(_error!,
                  key: const ValueKey('payables-error'),
                  style: TextStyle(color: theme.colorScheme.error)),
            if (_data != null) ...[
              _booksCheck(theme),
              const SizedBox(height: AppSpacing.md),
              _chart(theme),
              const SizedBox(height: AppSpacing.md),
              _grid(theme),
            ],
          ],
        ),
      ),
    );
  }

  Widget _filters() {
    return Wrap(
      spacing: AppSpacing.md,
      runSpacing: AppSpacing.sm,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        SegmentedButton<String>(
          key: const ValueKey('payables-view'),
          segments: const [
            ButtonSegment(value: 'owed', label: Text('Owed')),
            ButtonSegment(value: 'paid', label: Text('Paid')),
          ],
          selected: {_view},
          onSelectionChanged: (s) => _change(() => _view = s.first),
        ),
        OutlinedButton.icon(
          key: const ValueKey('payables-as-of'),
          onPressed: _pickDate,
          icon: const Icon(Icons.event, size: 18),
          label: Text('As of ${_iso(_asOf)}'),
        ),
        SegmentedButton<String>(
          key: const ValueKey('payables-basis'),
          segments: const [
            ButtonSegment(value: 'invoice', label: Text('By invoice date')),
            ButtonSegment(value: 'due', label: Text('By due date')),
          ],
          selected: {_basis},
          onSelectionChanged: (s) => _change(() => _basis = s.first),
        ),
        DropdownButton<int>(
          key: const ValueKey('payables-months'),
          value: _months,
          items: [
            for (final int m in const [3, 6, 9, 12, 18, 24])
              DropdownMenuItem(value: m, child: Text('$m months')),
          ],
          onChanged: (m) => _change(() => _months = m ?? 6),
        ),
        _choice('payables-supplier', 'All suppliers', _vendors, _vendorId,
            (v) => _change(() => _vendorId = v), true),
        _choice('payables-branch', 'All branches', _branches, _branchId,
            (v) => _change(() => _branchId = v), _view == 'owed'),
      ],
    );
  }

  Widget _choice(String key, String all, List<MapEntry<String, String>> items,
      String? value, ValueChanged<String?> onChanged, bool enabled) {
    return ConstrainedBox(
      constraints: const BoxConstraints(maxWidth: 220, minWidth: 140),
      child: DropdownButton<String?>(
        key: ValueKey(key),
        isExpanded: true,
        value: items.any((e) => e.key == value) ? value : null,
        items: [
          DropdownMenuItem<String?>(value: null, child: Text(all)),
          for (final e in items)
            DropdownMenuItem<String?>(
              value: e.key,
              child: Text(e.value, overflow: TextOverflow.ellipsis),
            ),
        ],
        onChanged: enabled ? onChanged : null,
      ),
    );
  }

  double _n(Object? v) => double.tryParse('${v ?? 0}') ?? 0;

  Widget _booksCheck(ThemeData theme) {
    final Object? check = _data?['books_check'];
    if (check is! Map) return const SizedBox.shrink();
    final bool compared = check['difference'] != null;
    final bool off = compared && _n(check['difference']).abs() >= 0.005;
    final String note = '${check['note'] ?? ''}';
    final String ledger = indianAmount(_n(check['ledger_balance']), full: true);
    final String diff = indianAmount(_n(check['difference']), full: true);
    final String text = !compared
        ? (note.isEmpty ? 'No comparison with the books for this view.' : note)
        : off
            ? 'Does not agree with the books: control account 2100 holds '
                '$ledger, difference $diff. $note'
            : 'Agrees with the books: control account 2100 holds $ledger.';
    final Color color =
        off ? theme.colorScheme.error : theme.colorScheme.onSurfaceVariant;
    return Row(
      key: const ValueKey('payables-books-check'),
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(off ? Icons.warning_amber : Icons.check_circle_outline,
            size: 18, color: color),
        const SizedBox(width: AppSpacing.sm),
        Expanded(child: Text(text, style: TextStyle(color: color))),
      ],
    );
  }

  List<Map> get _rows => [
        for (final Object? r in (_data?['rows'] as List? ?? const []))
          if (r is Map) r,
      ];

  List<String> get _monthKeys => [
        for (final Object? m in (_data?['months'] as List? ?? const [])) '$m',
      ];

  List<double> _amounts(Object? v, int n) {
    final List<double> out = List.filled(n, 0);
    if (v is List) {
      for (int i = 0; i < n && i < v.length; i++) {
        out[i] = _n(v[i]);
      }
    }
    return out;
  }

  double _sum(Object? v, int n) =>
      _amounts(v, n).fold(0, (a, b) => a + b);

  Widget _chart(ThemeData theme) {
    final List<String> months = _monthKeys;
    final int n = months.length;
    final List<Map> rows = [..._rows]..sort((a, b) =>
        _sum(b['amounts'], n).abs().compareTo(_sum(a['amounts'], n).abs()));
    if (n == 0 || rows.isEmpty) return const SizedBox.shrink();
    final ColorScheme scheme = theme.colorScheme;
    final List<Color> palette = [
      scheme.primary,
      scheme.secondary,
      scheme.tertiary,
      scheme.error,
      scheme.primaryContainer,
    ];
    final List<_Series> series = [];
    for (int i = 0; i < rows.length && i < 5; i++) {
      series.add(_Series(
          '${rows[i]['vendor_name']}', palette[i], _amounts(rows[i]['amounts'], n)));
    }
    if (rows.length > 5) {
      final List<double> others = List.filled(n, 0);
      for (final Map r in rows.skip(5)) {
        final List<double> a = _amounts(r['amounts'], n);
        for (int m = 0; m < n; m++) {
          others[m] += a[m];
        }
      }
      series.add(_Series('Others', scheme.outline, others));
    }
    return Column(
      key: const ValueKey('payables-chart'),
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          height: 160,
          width: double.infinity,
          child: CustomPaint(
            painter: _StackedBars(
                series, months, scheme.outlineVariant, scheme.onSurfaceVariant),
          ),
        ),
        const SizedBox(height: AppSpacing.sm),
        Wrap(spacing: AppSpacing.md, runSpacing: AppSpacing.xs, children: [
          for (final _Series s in series)
            Row(mainAxisSize: MainAxisSize.min, children: [
              Container(width: 10, height: 10, color: s.color),
              const SizedBox(width: AppSpacing.xs),
              Text(s.label, style: theme.textTheme.bodySmall),
            ]),
        ]),
      ],
    );
  }

  Widget _grid(ThemeData theme) {
    final List<String> months = _monthKeys;
    final bool owed = _view == 'owed';
    final Object? total = _data?['total'];
    final List<Map> rows = _rows;

    TableRow row(Map r, {bool bold = false}) {
      final TextStyle? style = bold
          ? theme.textTheme.bodyMedium?.copyWith(fontWeight: FontWeight.w700)
          : theme.textTheme.bodyMedium;
      Widget cell(double v) => Padding(
            padding: const EdgeInsets.symmetric(
                horizontal: AppSpacing.sm, vertical: AppSpacing.xs),
            child: Text(indianAmount(v, full: true),
                style: style, textAlign: TextAlign.right),
          );
      final List<double> a = _amounts(r['amounts'], months.length);
      final bool isTotal = r['vendor_id'] == null;
      return TableRow(children: [
        Padding(
          key: isTotal ? const ValueKey('payables-total-row') : null,
          padding: const EdgeInsets.symmetric(horizontal: AppSpacing.sm),
          child: isTotal
              ? Text('${r['vendor_name']}', style: style)
              : TextButton(
                  key: ValueKey('payables-open-${r['vendor_id']}'),
                  onPressed: widget.onOpenBills,
                  child: Align(
                    alignment: Alignment.centerLeft,
                    child: Text('${r['vendor_name']}',
                        overflow: TextOverflow.ellipsis),
                  ),
                ),
        ),
        if (owed) cell(_n(r['older'])),
        for (final double v in a) cell(v),
        if (owed) cell(_n(r['later'])),
        if (owed) cell(_n(r['credits'])),
        cell(_n(r['total'])),
      ]);
    }

    Widget head(String t) => Padding(
          padding: const EdgeInsets.symmetric(
              horizontal: AppSpacing.sm, vertical: AppSpacing.xs),
          child: Text(t,
              textAlign: TextAlign.right,
              style: theme.textTheme.labelLarge
                  ?.copyWith(fontWeight: FontWeight.w700)),
        );

    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: Table(
        key: const ValueKey('payables-grid'),
        defaultColumnWidth: const FixedColumnWidth(112),
        columnWidths: const {0: FixedColumnWidth(200)},
        border: TableBorder(
          horizontalInside: BorderSide(color: theme.dividerColor),
        ),
        defaultVerticalAlignment: TableCellVerticalAlignment.middle,
        children: [
          TableRow(
            decoration:
                BoxDecoration(color: theme.colorScheme.surfaceContainerHigh),
            children: [
              Padding(
                padding: const EdgeInsets.all(AppSpacing.sm),
                child: Text('Supplier',
                    style: theme.textTheme.labelLarge
                        ?.copyWith(fontWeight: FontWeight.w700)),
              ),
              if (owed) head('Older'),
              for (final String m in months) head(m),
              if (owed) head('Later'),
              if (owed) head('Credits'),
              head(owed ? 'Outstanding' : 'Paid'),
            ],
          ),
          for (final Map r in rows) row(r),
          if (total is Map)
            TableRow(
              decoration:
                  BoxDecoration(color: theme.colorScheme.surfaceContainer),
              children: row(total, bold: true).children,
            ),
        ],
      ),
    );
  }
}

class _Series {
  _Series(this.label, this.color, this.values);
  final String label;
  final Color color;
  final List<double> values;
}

/// Stacked bars, one per month, drawn from the report's own numbers.
class _StackedBars extends CustomPainter {
  _StackedBars(this.series, this.months, this.axis, this.text);

  final List<_Series> series;
  final List<String> months;
  final Color axis;
  final Color text;

  @override
  void paint(Canvas canvas, Size size) {
    const double labelH = 16;
    final double chartH = size.height - labelH;
    final int n = months.length;
    double top = 0;
    for (int m = 0; m < n; m++) {
      double t = 0;
      for (final _Series s in series) {
        if (s.values[m] > 0) t += s.values[m];
      }
      if (t > top) top = t;
    }
    canvas.drawLine(
        Offset(0, chartH), Offset(size.width, chartH), Paint()..color = axis);
    if (top <= 0 || n == 0) return;
    final double slot = size.width / n;
    final double barW = slot * .6;
    for (int m = 0; m < n; m++) {
      double y = chartH;
      final double x = m * slot + (slot - barW) / 2;
      for (final _Series s in series) {
        final double v = s.values[m];
        if (v <= 0) continue;
        final double h = chartH * v / top;
        canvas.drawRect(
            Rect.fromLTWH(x, y - h, barW, h), Paint()..color = s.color);
        y -= h;
      }
      final TextPainter label = TextPainter(
        text: TextSpan(
            text: months[m],
            style: TextStyle(color: text, fontSize: slot < 60 ? 8 : 10)),
        textDirection: TextDirection.ltr,
        maxLines: 1,
      )..layout(maxWidth: slot);
      label.paint(
          canvas, Offset(m * slot + (slot - label.width) / 2, chartH + 2));
    }
  }

  @override
  bool shouldRepaint(_StackedBars old) =>
      old.series != series || old.months != months;
}
