import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/security/permission_service.dart';
import '../../models/sales_analysis.dart';
import '../workspace/analysis_page.dart';
import '../workspace/desktop_framework.dart';

/// What one product was bought at, bill by bill: a line over time, the
/// points behind it, and the lowest, highest, last and how far the last has
/// moved from the first. Nothing is stored; the server derives it per read.
class PurchaseRateTrendPage extends StatefulWidget {
  const PurchaseRateTrendPage({
    super.key,
    required this.api,
    required this.permissions,
    required this.hasActiveFirm,
  });

  final ApiClient api;
  final PermissionService permissions;
  final bool hasActiveFirm;

  @override
  State<PurchaseRateTrendPage> createState() => _PurchaseRateTrendPageState();
}

final RegExp _isoDate = RegExp(r'^\d{4}-\d{2}-\d{2}$');

class _PurchaseRateTrendPageState extends State<PurchaseRateTrendPage> {
  final TextEditingController _from = TextEditingController();
  final TextEditingController _to = TextEditingController();
  AnalysisOption? _product;
  AnalysisOption? _supplier;
  List<RateTrendPoint> _points = const [];
  bool _loading = false;
  bool _loaded = false;
  String? _error;

  bool get _canView => widget.permissions
      .hasAnyPermission(const ['PURCHASE_VIEW', 'REPORT_VIEW']);

  @override
  void dispose() {
    _from.dispose();
    _to.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    final AnalysisOption? product = _product;
    if (product == null) return;
    final String from = _from.text.trim();
    final String to = _to.text.trim();
    if ((from.isNotEmpty && !_isoDate.hasMatch(from)) ||
        (to.isNotEmpty && !_isoDate.hasMatch(to))) {
      setState(() => _error = 'Dates are written YYYY-MM-DD.');
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final List<RateTrendPoint> points = await widget.api.purchaseRateTrend(
        productId: product.id,
        supplierId: _supplier?.id,
        fromDate: from,
        toDate: to,
      );
      if (!mounted) return;
      setState(() {
        _points = points;
        _loaded = true;
      });
    } on ApiException catch (exception) {
      if (!mounted) return;
      // Clear the pane: a line from another product must not sit under an
      // error that says this one failed.
      setState(() {
        _error = exception.message;
        _points = const [];
      });
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<List<AnalysisOption>> _search(bool product, String text) async =>
      product
          ? [
              for (final p
                  in (await widget.api.products(search: text, pageSize: 50))
                      .items)
                AnalysisOption(id: p.id, label: p.name),
            ]
          : [
              for (final v in (await widget.api.vendors(search: text)).items)
                AnalysisOption(id: v.id, label: v.name),
            ];

  Future<void> _choose({required bool product}) async {
    final AnalysisOption? picked = await showDialog<AnalysisOption>(
      context: context,
      builder: (context) => AnalysisOptionPickerDialog(
        title: product ? 'Choose a product' : 'Choose a supplier',
        search: (text) => _search(product, text),
      ),
    );
    if (picked == null) return;
    setState(() => product ? _product = picked : _supplier = picked);
    unawaited(_load());
  }

  Widget _picker({
    required Key key,
    required String label,
    required String hint,
    required AnalysisOption? value,
    required bool product,
  }) =>
      SizedBox(
        width: 240,
        child: InkWell(
          key: key,
          onTap: () => unawaited(_choose(product: product)),
          child: InputDecorator(
            decoration: InputDecoration(
              labelText: label,
              suffixIcon: !product && value != null
                  ? IconButton(
                      tooltip: 'Any supplier',
                      icon: const Icon(Icons.close, size: 16),
                      onPressed: () {
                        setState(() => _supplier = null);
                        unawaited(_load());
                      },
                    )
                  : const Icon(Icons.search, size: 16),
            ),
            child: Text(
              value?.label ?? hint,
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ),
      );

  Widget _box(String label, TextEditingController controller) => SizedBox(
        width: 130,
        child: TextField(
          controller: controller,
          decoration: InputDecoration(
            labelText: label,
            hintText: 'YYYY-MM-DD',
          ),
          onSubmitted: (_) => unawaited(_load()),
        ),
      );

  @override
  Widget build(BuildContext context) {
    const String title = 'Rate trend';
    if (!_canView) {
      return const StandardEmptyState(
        type: EmptyStateType.noPermissions,
        title: title,
        message: 'You do not have permission to view the rate trend.',
      );
    }
    if (!widget.hasActiveFirm) {
      return const StandardEmptyState(
        type: EmptyStateType.noFirmSelected,
        title: title,
        message: 'Choose a firm to use the rate trend.',
      );
    }
    return LoadingOverlay(
      loading: _loading,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.all(AppSpacing.lg),
            child: Wrap(
              spacing: AppSpacing.md,
              runSpacing: AppSpacing.md,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                _picker(
                  key: const ValueKey('rate-trend-product'),
                  label: 'Product',
                  hint: 'Choose a product',
                  value: _product,
                  product: true,
                ),
                _picker(
                  key: const ValueKey('rate-trend-supplier'),
                  label: 'Supplier',
                  hint: 'Any supplier',
                  value: _supplier,
                  product: false,
                ),
                _box('From', _from),
                _box('To', _to),
                FilledButton(
                  onPressed: _product == null ? null : () => unawaited(_load()),
                  child: const Text('Refresh'),
                ),
                Text(
                  'Blank dates read the last twelve months.',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ],
            ),
          ),
          if (_error != null)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg),
              child: Text(
                _error!,
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
            ),
          Expanded(child: _body(context)),
        ],
      ),
    );
  }

  Widget _body(BuildContext context) {
    if (_product == null) {
      return const StandardEmptyState(
        type: EmptyStateType.noRecords,
        title: 'Choose a product',
        message: 'The rate trend is for one product at a time.',
      );
    }
    if (_points.isEmpty) {
      if (!_loaded) return const SizedBox.shrink();
      return const StandardEmptyState(
        type: EmptyStateType.noRecords,
        title: 'Not bought in this period',
        message: 'No bill carries this product between these dates.',
      );
    }
    final ThemeData theme = Theme.of(context);
    final List<double> rates = [for (final p in _points) p.rate];
    final double lowest = rates.reduce((a, b) => a < b ? a : b);
    final double highest = rates.reduce((a, b) => a > b ? a : b);
    final double first = rates.first;
    final double last = rates.last;
    final String change = first == 0
        ? '-'
        : '${last >= first ? '+' : ''}'
            '${((last - first) / first.abs() * 100).toStringAsFixed(1)}%';

    Widget stat(String label, String value) => Padding(
          padding: const EdgeInsets.only(right: AppSpacing.xl),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(label, style: theme.textTheme.bodySmall),
              Text(value, style: theme.textTheme.titleMedium),
            ],
          ),
        );

    return SingleChildScrollView(
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Wrap(runSpacing: AppSpacing.sm, children: [
            stat('Lowest', lowest.toStringAsFixed(2)),
            stat('Highest', highest.toStringAsFixed(2)),
            stat('Last', last.toStringAsFixed(2)),
            stat('Change since first', change),
          ]),
          const SizedBox(height: AppSpacing.md),
          SizedBox(
            height: 220,
            child: CustomPaint(
              key: const ValueKey('rate-trend-chart'),
              painter: _TrendPainter(
                rates: rates,
                line: theme.colorScheme.primary,
                grid: theme.colorScheme.outlineVariant,
                label: theme.colorScheme.onSurfaceVariant,
                style: theme.textTheme.bodySmall ?? const TextStyle(),
              ),
            ),
          ),
          const SizedBox(height: AppSpacing.md),
          Phase2WideTable(
            table: DataTable(
              columns: const [
                DataColumn(label: Text('Date')),
                DataColumn(label: Text('Bill')),
                DataColumn(label: Text('Supplier')),
                DataColumn(label: Text('Quantity'), numeric: true),
                DataColumn(label: Text('Rate'), numeric: true),
              ],
              rows: [
                for (final RateTrendPoint p in _points)
                  DataRow(cells: [
                    DataCell(Text(p.billDate)),
                    DataCell(Text(p.billNumber)),
                    DataCell(Text(p.supplierName)),
                    DataCell(Text(_quantity(p.quantity))),
                    DataCell(Text(p.rate.toStringAsFixed(2))),
                  ]),
              ],
            ),
          ),
          const SizedBox(height: AppSpacing.lg),
        ],
      ),
    );
  }

  String _quantity(double q) =>
      q == q.roundToDouble() ? q.toStringAsFixed(0) : q.toString();
}

/// A plain line through the rates in the order bought, with the lowest and
/// highest rate written against the axis. Colours come from the theme.
class _TrendPainter extends CustomPainter {
  _TrendPainter({
    required this.rates,
    required this.line,
    required this.grid,
    required this.label,
    required this.style,
  });

  final List<double> rates;
  final Color line;
  final Color grid;
  final Color label;
  final TextStyle style;

  static const double _left = 56;
  static const double _pad = 12;

  @override
  void paint(Canvas canvas, Size size) {
    final double low = rates.reduce((a, b) => a < b ? a : b);
    final double high = rates.reduce((a, b) => a > b ? a : b);
    final double span = high == low ? 1 : high - low;
    final double width = size.width - _left - _pad;
    final double height = size.height - 2 * _pad;
    Offset at(int i) => Offset(
          _left +
              (rates.length == 1 ? width / 2 : width * i / (rates.length - 1)),
          _pad + height * (1 - (rates[i] - low) / span),
        );

    final Paint gridPaint = Paint()
      ..color = grid
      ..strokeWidth = 1;
    for (final double v in [low, high]) {
      final double y = _pad + height * (1 - (v - low) / span);
      canvas.drawLine(
          Offset(_left, y), Offset(size.width - _pad, y), gridPaint);
      final TextPainter tp = TextPainter(
        text: TextSpan(
          text: v.toStringAsFixed(2),
          style: style.copyWith(color: label),
        ),
        textDirection: TextDirection.ltr,
      )..layout();
      tp.paint(canvas, Offset(_left - tp.width - 6, y - tp.height / 2));
    }

    final Paint linePaint = Paint()
      ..color = line
      ..strokeWidth = 2
      ..style = PaintingStyle.stroke;
    final Path path = Path()..moveTo(at(0).dx, at(0).dy);
    for (int i = 1; i < rates.length; i++) {
      path.lineTo(at(i).dx, at(i).dy);
    }
    canvas.drawPath(path, linePaint);
    final Paint dot = Paint()..color = line;
    for (int i = 0; i < rates.length; i++) {
      canvas.drawCircle(at(i), 3, dot);
    }
  }

  @override
  bool shouldRepaint(_TrendPainter old) =>
      old.rates != rates || old.line != line || old.grid != grid;
}
