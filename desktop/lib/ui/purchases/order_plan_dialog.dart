import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../models/branch_warehouse.dart';
import '../../models/entities.dart';
import '../../models/product.dart';
import '../../models/vendor.dart';
import '../workspace/paged_fetch.dart';
import '../workspace/report_workbook.dart';
import '../workspace/save_in_dialog.dart';

/// Plan an order by company from average sales (backlog 130).
///
/// Choose a warehouse, optionally a company and a supplier, and how many days
/// of sales to average and how many days of stock to want, then **Show**. Every
/// active stocked product of the choice is listed with what was sold, what is
/// needed, what is in hand and on order, and the quantity to order. Tick rows,
/// adjust a quantity if wanted, and **Raise draft orders**: the server raises
/// one DRAFT per supplier through the order's own save path, all or none.
///
/// Nothing is listed until Show is pressed: a firm with thousands of products
/// should choose a company first. The rows are raised with the choices that
/// produced them, kept when Show was pressed, not with whatever the boxes say
/// afterwards.
///
/// The sales read start at **the last six months** (backlog 142), with one
/// month, three months and a year one click away and the box still typed.
/// **Raise all by %** puts every suggested quantity up by a percentage at
/// once, rounded up to a whole unit and to the supplier's minimum and pack;
/// a line typed afterwards stays as typed.
class OrderPlanDialog extends StatefulWidget {
  const OrderPlanDialog({super.key, required this.api});

  final ApiClient api;

  @override
  State<OrderPlanDialog> createState() => _OrderPlanDialogState();
}

class _OrderPlanDialogState extends State<OrderPlanDialog>
    with SaveInDialog<OrderPlanDialog> {
  List<WarehouseRecord> _warehouses = const [];
  List<PrincipalRecord> _companies = const [];
  List<Vendor> _suppliers = const [];
  String? _warehouseId;
  String _companyId = '';
  String _supplierId = '';

  /// The periods offered beside the typed days, in days.
  static const List<(int, String)> _periods = <(int, String)>[
    (30, '1 month'),
    (90, '3 months'),
    (180, '6 months'),
    (365, '1 year'),
  ];

  final TextEditingController _salesDays = TextEditingController(text: '180');
  final TextEditingController _coverDays = TextEditingController(text: '30');
  final TextEditingController _raisePercent = TextEditingController();

  /// The percentage the shown quantities were last raised by; null until
  /// Apply is pressed, and again after the next Show.
  double? _raisedBy;

  bool _choicesLoading = true;
  String? _choicesError;

  /// Null until Show is pressed.
  List<Json>? _rows;
  bool _showing = false;
  String? _showError;

  /// The choices the shown rows were computed with.
  Json _kept = const <String, dynamic>{};
  final Set<int> _ticked = <int>{};

  /// One box per row, owned here (CLAUDE.md: a dialog owns its controllers).
  final List<TextEditingController> _quantities = <TextEditingController>[];

  @override
  void initState() {
    super.initState();
    _loadChoices();
  }

  @override
  void dispose() {
    _salesDays.dispose();
    _coverDays.dispose();
    _raisePercent.dispose();
    for (final TextEditingController controller in _quantities) {
      controller.dispose();
    }
    super.dispose();
  }

  Future<void> _loadChoices() async {
    try {
      final List<WarehouseRecord> warehouses = await fetchAllPages(
          (page) => widget.api.warehouses(page: page, pageSize: 100));
      List<PrincipalRecord> companies = const [];
      List<Vendor> suppliers = const [];
      // Companies and suppliers narrow the plan; not being able to read them
      // leaves the plan whole rather than refusing it.
      try {
        companies = (await widget.api.principals())
            .where((company) => company.isActive)
            .toList();
      } on ApiException {
        companies = const [];
      }
      try {
        suppliers = (await fetchAllPages((page) => widget.api.vendors(page: page)))
            .where((vendor) => !vendor.isDeleted)
            .toList();
      } on ApiException {
        suppliers = const [];
      }
      // The sales read start at six months whatever the firm's reorder alert
      // reads; the days of stock wanted start at the firm's own, and a
      // refusal keeps 30.
      try {
        final Json planning = await widget.api.reorderPlanning();
        final int? cover = int.tryParse(stringValue(planning['cover_days']));
        if (cover != null && cover >= 1 && cover <= 365) {
          _coverDays.text = '$cover';
        }
      } on ApiException {
        // Keep the defaults.
      }
      if (!mounted) return;
      setState(() {
        _warehouses = warehouses;
        _companies = companies;
        _suppliers = suppliers;
        _warehouseId = warehouses.isEmpty ? null : warehouses.first.id;
        _choicesLoading = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _choicesError = error.message;
        _choicesLoading = false;
      });
    }
  }

  int? get _salesValue => _days(_salesDays.text, 7);

  int? get _coverValue => _days(_coverDays.text, 1);

  static int? _days(String text, int least) {
    final int? value = int.tryParse(text.trim());
    return value != null && value >= least && value <= 365 ? value : null;
  }

  bool get _canShow =>
      !_choicesLoading &&
      !_showing &&
      !saving &&
      _warehouseId != null &&
      _salesValue != null &&
      _coverValue != null;

  static bool _positive(String text) => (double.tryParse(text.trim()) ?? 0) > 0;

  static bool _orderable(Json row) => stringValue(row['supplier_id']).isNotEmpty;

  /// The percentage typed, 0 to 500; null when it is not one.
  double? get _percentValue {
    final double? value = double.tryParse(_raisePercent.text.trim());
    return value != null && value >= 0 && value <= 500 ? value : null;
  }

  /// A suggested quantity put up by [percent]: rounded up to a whole unit,
  /// then to the supplier's minimum and pack as the server rounds its own.
  static double _raised(Json row, double percent) {
    final double suggested =
        double.tryParse(stringValue(row['suggested_quantity'])) ?? 0;
    // The hair taken off keeps 250 + 10% at 275 rather than 276.
    double quantity =
        (suggested * (100 + percent) / 100 - 1e-9).ceilToDouble();
    final double minimum =
        double.tryParse(stringValue(row['minimum_order_quantity'])) ?? 0;
    final double multiple =
        double.tryParse(stringValue(row['order_multiple'])) ?? 0;
    if (minimum > 0 && quantity < minimum) quantity = minimum;
    if (multiple > 0) {
      quantity = (quantity / multiple - 1e-9).ceilToDouble() * multiple;
    }
    return quantity;
  }

  /// Puts every suggested quantity up by the percentage typed. It starts
  /// from the suggestion each time, so 10 then 20 is plus 20 and 0 puts the
  /// suggestions back; a row with nothing suggested is left as it is.
  void _raiseAll() {
    final double? percent = _percentValue;
    final List<Json>? rows = _rows;
    if (percent == null || rows == null) return;
    for (int i = 0; i < rows.length; i++) {
      if (!_positive(stringValue(rows[i]['suggested_quantity']))) continue;
      _quantities[i].text = _plain(_raised(rows[i], percent));
    }
    setState(() => _raisedBy = percent);
  }

  /// A quantity as the server sent it, without trailing zeros.
  static String _plain(dynamic value) {
    final double? number = double.tryParse(stringValue(value));
    if (number == null) return stringValue(value);
    return number == number.roundToDouble()
        ? number.toStringAsFixed(0)
        : number.toString();
  }

  Future<void> _show() async {
    final String? warehouseId = _warehouseId;
    final int? sales = _salesValue;
    final int? cover = _coverValue;
    if (warehouseId == null || sales == null || cover == null) return;
    setState(() {
      _showing = true;
      _showError = null;
      saveError = null;
    });
    final String company = _companyId;
    final String supplier = _supplierId;
    try {
      final List<Json> rows = await widget.api.orderPlan(
        warehouseId: warehouseId,
        companyId: company.isEmpty ? null : company,
        vendorId: supplier.isEmpty ? null : supplier,
        salesDays: sales,
        coverDays: cover,
      );
      if (!mounted) return;
      for (final TextEditingController controller in _quantities) {
        controller.dispose();
      }
      _quantities
        ..clear()
        ..addAll([
          for (final Json row in rows)
            TextEditingController(
              text: _positive(stringValue(row['suggested_quantity']))
                  ? _plain(row['suggested_quantity'])
                  : '',
            ),
        ]);
      setState(() {
        _kept = <String, dynamic>{
          'warehouse_id': warehouseId,
          'company_id': company.isEmpty ? null : company,
          'brand_ids': <String>[],
          'vendor_id': supplier.isEmpty ? null : supplier,
          'sales_days': sales,
          'cover_days': cover,
        };
        _rows = rows;
        _raisedBy = null;
        _ticked
          ..clear()
          ..addAll([
            for (int i = 0; i < rows.length; i++)
              if (_orderable(rows[i]) && _positive(_quantities[i].text)) i,
          ]);
        _showing = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _showError = error.message;
        _showing = false;
      });
    }
  }

  Future<void> _raise() async {
    final List<Json> items = [
      for (final int index in _ticked.toList()..sort())
        <String, dynamic>{
          'product_id': _rows![index]['product_id'],
          'quantity': _quantities[index].text.trim(),
        },
    ];
    final Json body = <String, dynamic>{..._kept, 'items': items};
    await saveAndClose<Json>(() => widget.api.raiseOrderPlanDrafts(body));
  }

  Future<void> _download() async {
    final List<Json> rows = _rows ?? const [];
    final WarehouseRecord? warehouse = _warehouses
        .where((record) => record.id == stringValue(_kept['warehouse_id']))
        .firstOrNull;
    await downloadWorkbook(
      context,
      fileName: workbookFileName(['order-plan', warehouse?.code ?? '']),
      sheet: () => WorkbookSheet(
        title: 'Order plan',
        notes: [
          'Warehouse: ${warehouse?.name ?? ''}',
          'Sales of the last ${_kept['sales_days']} days; '
              'stock for ${_kept['cover_days']} days',
          if ((_raisedBy ?? 0) > 0)
            'Suggested quantities raised by ${_plain(_raisedBy)}%',
        ],
        headers: const [
          'Code',
          'Product',
          'Brand',
          'Sold',
          'Avg/day',
          'Needed',
          'In hand',
          'On order',
          'Order',
          'Supplier',
        ],
        numeric: const {3, 4, 5, 6, 7, 8},
        rows: [
          for (int i = 0; i < rows.length; i++)
            [
              stringValue(rows[i]['product_code']),
              stringValue(rows[i]['product_name']),
              stringValue(rows[i]['brand_name']),
              stringValue(rows[i]['sold_quantity']),
              stringValue(rows[i]['average_daily_sales']),
              stringValue(rows[i]['required_quantity']),
              stringValue(rows[i]['available_quantity']),
              stringValue(rows[i]['on_order_quantity']),
              _quantities[i].text.trim(),
              stringValue(rows[i]['supplier_name']),
            ],
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final bool canRaise = !_showing &&
        !saving &&
        _ticked.isNotEmpty &&
        _ticked.every((index) => _positive(_quantities[index].text));
    final double height =
        (MediaQuery.sizeOf(context).height - 260).clamp(240.0, 460.0);
    return AlertDialog(
      icon: const Icon(Icons.shopping_cart_checkout_outlined),
      title: const Text('Plan an order'),
      content: SizedBox(
        width: 900,
        height: height,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // A short window scrolls the choices rather than squeezing the
            // rows out from under them.
            if (!_choicesLoading)
              ConstrainedBox(
                constraints: BoxConstraints(maxHeight: height - 170),
                child: SingleChildScrollView(child: _choices()),
              ),
            const SizedBox(height: AppSpacing.xs),
            Text(
              'To order = sold in the period ÷ its days × days of stock '
              'wanted, less stock in hand and what is already on order, '
              'rounded up.',
              style: theme.textTheme.bodySmall,
            ),
            const SizedBox(height: AppSpacing.sm),
            saveErrorBanner(),
            Expanded(child: _body(theme)),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: saving ? null : () => Navigator.pop(context),
          child: const Text('Close'),
        ),
        TextButton.icon(
          key: const ValueKey('order-plan-download'),
          onPressed:
              (_rows ?? const []).isNotEmpty && !saving ? _download : null,
          icon: const Icon(Icons.download_outlined, size: 16),
          label: const Text('Download'),
        ),
        FilledButton(
          key: const ValueKey('order-plan-raise'),
          onPressed: canRaise ? _raise : null,
          child: Text(saving
              ? 'Raising…'
              : 'Raise draft orders (${_ticked.length})'),
        ),
      ],
    );
  }

  Widget _choices() {
    return Wrap(
      spacing: AppSpacing.md,
      runSpacing: AppSpacing.sm,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        SizedBox(
          width: 190,
          child: DropdownButtonFormField<String>(
            key: const ValueKey('order-plan-warehouse'),
            initialValue: _warehouseId,
            isExpanded: true,
            decoration: const InputDecoration(
                labelText: 'Warehouse', isDense: true),
            items: [
              for (final WarehouseRecord warehouse in _warehouses)
                DropdownMenuItem(
                  value: warehouse.id,
                  child: Text(
                    warehouse.name.isEmpty ? warehouse.code : warehouse.name,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
            ],
            onChanged: saving
                ? null
                : (value) => setState(() => _warehouseId = value),
          ),
        ),
        SizedBox(
          width: 190,
          child: DropdownButtonFormField<String>(
            key: const ValueKey('order-plan-company'),
            initialValue: _companyId,
            isExpanded: true,
            decoration:
                const InputDecoration(labelText: 'Company', isDense: true),
            items: [
              const DropdownMenuItem(value: '', child: Text('All companies')),
              for (final PrincipalRecord company in _companies)
                DropdownMenuItem(
                  value: company.id,
                  child: Text(company.name, overflow: TextOverflow.ellipsis),
                ),
            ],
            onChanged: saving
                ? null
                : (value) => setState(() => _companyId = value ?? ''),
          ),
        ),
        SizedBox(
          width: 220,
          child: DropdownButtonFormField<String>(
            key: const ValueKey('order-plan-supplier'),
            initialValue: _supplierId,
            isExpanded: true,
            decoration:
                const InputDecoration(labelText: 'Supplier', isDense: true),
            items: [
              const DropdownMenuItem(
                  value: '', child: Text("Each product's own supplier")),
              for (final Vendor vendor in _suppliers)
                DropdownMenuItem(
                  value: vendor.id,
                  child: Text(
                    vendor.displayName.isEmpty ? vendor.name : vendor.displayName,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
            ],
            onChanged: saving
                ? null
                : (value) => setState(() => _supplierId = value ?? ''),
          ),
        ),
        _daysBox(
          key: 'order-plan-sales-days',
          before: 'Sales of the last',
          controller: _salesDays,
        ),
        Wrap(
          spacing: AppSpacing.xs,
          children: [
            for (final (int days, String label) in _periods)
              ChoiceChip(
                key: ValueKey('order-plan-period-$days'),
                label: Text(label),
                visualDensity: VisualDensity.compact,
                selected: _salesValue == days,
                onSelected: saving
                    ? null
                    : (_) => setState(() => _salesDays.text = '$days'),
              ),
          ],
        ),
        _daysBox(
          key: 'order-plan-cover-days',
          before: 'Stock for',
          controller: _coverDays,
        ),
        FilledButton.tonal(
          key: const ValueKey('order-plan-show'),
          onPressed: _canShow ? _show : null,
          child: Text(_showing ? 'Reading…' : 'Show'),
        ),
        _raiseAllRow(Theme.of(context)),
      ],
    );
  }

  Widget _daysBox({
    required String key,
    required String before,
    required TextEditingController controller,
  }) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(before, style: Theme.of(context).textTheme.bodySmall),
        const SizedBox(width: AppSpacing.xs),
        SizedBox(
          width: 56,
          child: TextField(
            key: ValueKey(key),
            controller: controller,
            enabled: !saving,
            keyboardType: TextInputType.number,
            decoration: const InputDecoration(isDense: true),
            onChanged: (_) => setState(() {}),
          ),
        ),
        const SizedBox(width: AppSpacing.xs),
        Text('days', style: Theme.of(context).textTheme.bodySmall),
      ],
    );
  }

  Widget _body(ThemeData theme) {
    if (_choicesLoading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_choicesError != null) {
      return Center(
        child: Text(
          'The warehouses could not be read: $_choicesError',
          style: theme.textTheme.bodySmall
              ?.copyWith(color: theme.colorScheme.error),
        ),
      );
    }
    if (_showError != null) {
      return Center(
        child: Text(
          'The plan could not be read: $_showError',
          style: theme.textTheme.bodySmall
              ?.copyWith(color: theme.colorScheme.error),
        ),
      );
    }
    final List<Json>? rows = _rows;
    if (_showing) {
      return const Center(child: CircularProgressIndicator());
    }
    if (rows == null) {
      return Center(
        child: Text(
          'Choose a warehouse and a company, then press Show.',
          style: theme.textTheme.bodyMedium,
        ),
      );
    }
    if (rows.isEmpty) {
      return Center(
        child: Text(
          'No stocked product matches these choices.',
          style: theme.textTheme.bodyMedium,
        ),
      );
    }
    final TextStyle? head = theme.textTheme.labelSmall;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(children: [
          const SizedBox(width: 40),
          Expanded(flex: 4, child: Text('Product', style: head)),
          Expanded(flex: 2, child: Text('Brand', style: head)),
          Expanded(flex: 2, child: Text('Sold', style: head)),
          Expanded(flex: 2, child: Text('Avg/day', style: head)),
          Expanded(flex: 2, child: Text('Needed', style: head)),
          Expanded(flex: 2, child: Text('In hand', style: head)),
          Expanded(flex: 2, child: Text('On order', style: head)),
          Expanded(flex: 2, child: Text('Order', style: head)),
          Expanded(flex: 4, child: Text('Supplier', style: head)),
        ]),
        const Divider(height: 8),
        Expanded(
          child: ListView.builder(
            itemCount: rows.length,
            itemBuilder: (context, index) => _row(theme, rows[index], index),
          ),
        ),
      ],
    );
  }

  Widget _raiseAllRow(ThemeData theme) {
    final double? raisedBy = _raisedBy;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          raisedBy != null && raisedBy > 0
              ? 'Raised by ${_plain(raisedBy)}%. Raise all by'
              : 'Raise all by',
          key: const ValueKey('order-plan-raised-note'),
          style: theme.textTheme.bodySmall,
        ),
        const SizedBox(width: AppSpacing.xs),
        SizedBox(
          width: 56,
          child: TextField(
            key: const ValueKey('order-plan-raise-percent'),
            controller: _raisePercent,
            enabled: !saving,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            decoration: const InputDecoration(isDense: true),
            onChanged: (_) => setState(() {}),
          ),
        ),
        const SizedBox(width: AppSpacing.xs),
        Text('%', style: theme.textTheme.bodySmall),
        const SizedBox(width: AppSpacing.sm),
        OutlinedButton(
          key: const ValueKey('order-plan-raise-apply'),
          onPressed: !saving &&
                  !_showing &&
                  (_rows ?? const []).isNotEmpty &&
                  _percentValue != null
              ? _raiseAll
              : null,
          child: const Text('Apply'),
        ),
      ],
    );
  }

  Widget _row(ThemeData theme, Json row, int index) {
    final bool orderable = _orderable(row);
    final TextStyle? cell = theme.textTheme.bodySmall;
    return Row(
      key: ValueKey('order-plan-row-$index'),
      children: [
        SizedBox(
          width: 40,
          child: Checkbox(
            key: ValueKey('order-plan-tick-$index'),
            value: _ticked.contains(index),
            onChanged: orderable && !saving
                ? (value) => setState(() => value == true
                    ? _ticked.add(index)
                    : _ticked.remove(index))
                : null,
          ),
        ),
        Expanded(
          flex: 4,
          child: Text(
            '${stringValue(row['product_code'])} · '
            '${stringValue(row['product_name'])}',
            style: cell,
            overflow: TextOverflow.ellipsis,
          ),
        ),
        Expanded(
          flex: 2,
          child: Text(stringValue(row['brand_name']),
              style: cell, overflow: TextOverflow.ellipsis),
        ),
        Expanded(
            flex: 2, child: Text(_plain(row['sold_quantity']), style: cell)),
        Expanded(
            flex: 2,
            child: Text(_plain(row['average_daily_sales']), style: cell)),
        Expanded(
            flex: 2,
            child: Text(_plain(row['required_quantity']), style: cell)),
        Expanded(
            flex: 2,
            child: Text(_plain(row['available_quantity']), style: cell)),
        Expanded(
            flex: 2,
            child: Text(_plain(row['on_order_quantity']), style: cell)),
        Expanded(
          flex: 2,
          child: Padding(
            padding: const EdgeInsets.only(right: AppSpacing.sm),
            child: TextField(
              key: ValueKey('order-plan-quantity-$index'),
              controller: _quantities[index],
              enabled: orderable && !saving,
              keyboardType:
                  const TextInputType.numberWithOptions(decimal: true),
              style: cell,
              decoration: const InputDecoration(isDense: true),
              onChanged: (_) => setState(() {}),
            ),
          ),
        ),
        Expanded(
          flex: 4,
          child: Text(
            orderable
                ? stringValue(row['supplier_name'])
                : 'No supplier known',
            style: orderable
                ? cell
                : cell?.copyWith(color: theme.colorScheme.onSurfaceVariant),
            overflow: TextOverflow.ellipsis,
          ),
        ),
      ],
    );
  }
}
