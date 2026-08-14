import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/business/business_features.dart';
import '../../core/design/design_tokens.dart';
import '../../models/branch_warehouse.dart';
import '../../models/entities.dart';
import '../../models/inventory.dart';
import '../../models/product.dart';
import '../workspace/desktop_framework.dart';

/// One batch a line is expected to draw from, and how much of it.
class BatchDraw {
  const BatchDraw({
    required this.batchNumber,
    required this.expiryDate,
    required this.quantity,
  });

  /// Empty where the stock is not batch-tracked.
  final String batchNumber;
  final String expiryDate;
  final double quantity;

  String get label {
    final String name = batchNumber.isEmpty ? 'untracked stock' : batchNumber;
    final String when = expiryDate.isEmpty ? '' : ' (expires $expiryDate)';
    return '$name$when: ${_trim(quantity)}';
  }
}

String _trim(double value) =>
    value == value.roundToDouble() ? value.toStringAsFixed(0) : '$value';

/// Work out which batches a quantity will come off, earliest expiry first.
///
/// This mirrors `InventoryService.allocate_for_dispatch`, which is what
/// actually decides at dispatch: a batch with no expiry is not urgent so it
/// goes last, ties break on the batch number, and the walk stops when the
/// quantity is met. It is a **preview** and says so on screen -- the server
/// allocates when the note is dispatched, and stock can move in between.
List<BatchDraw> previewAllocation(List<InventoryRecord> stock, double quantity) {
  final List<InventoryRecord> candidates = [...stock]
    ..sort((a, b) {
      final bool aNone = a.batchExpiryDate.isEmpty;
      final bool bNone = b.batchExpiryDate.isEmpty;
      if (aNone != bNone) return aNone ? 1 : -1;
      final int byExpiry = a.batchExpiryDate.compareTo(b.batchExpiryDate);
      if (byExpiry != 0) return byExpiry;
      return a.batchNumber.compareTo(b.batchNumber);
    });
  final List<BatchDraw> draws = [];
  double outstanding = quantity;
  for (final InventoryRecord row in candidates) {
    if (outstanding <= 0) break;
    final double available = double.tryParse(row.availableQuantity) ?? 0;
    if (available <= 0) continue;
    final double take = available < outstanding ? available : outstanding;
    draws.add(BatchDraw(
      batchNumber: row.batchNumber,
      expiryDate: row.batchExpiryDate,
      quantity: take,
    ));
    outstanding -= take;
  }
  return draws;
}

/// One line being dispatched, as the person packing it is editing it.
class DeliveryDraftLine {
  DeliveryDraftLine({
    required this.salesOrderLineId,
    required this.lineNumber,
    required this.productId,
    required this.description,
    required this.orderedQuantity,
    required this.reservedQuantity,
    required this.alreadyDelivered,
    required this.unitPrice,
    required this.salesUomId,
    required this.inventoryUomId,
    required this.taxProfileId,
    required this.deliveryQuantity,
    this.freeQuantity = '0',
    this.damagedQuantity = '0',
    this.warehouseId = '',
    this.remarks = '',
  });

  final String salesOrderLineId;
  final int lineNumber;
  final String productId;
  final String description;
  final String orderedQuantity;
  final String reservedQuantity;
  final String alreadyDelivered;
  final String unitPrice;
  final String salesUomId;
  final String inventoryUomId;
  final String taxProfileId;

  String deliveryQuantity;
  String freeQuantity;
  String damagedQuantity;
  String warehouseId;
  String remarks;

  double get outstanding {
    final double ordered = double.tryParse(orderedQuantity) ?? 0;
    final double delivered = double.tryParse(alreadyDelivered) ?? 0;
    final double left = ordered - delivered;
    return left < 0 ? 0 : left;
  }

  double get reserved => double.tryParse(reservedQuantity) ?? 0;

  /// What the line can actually ship without the dispatch being refused.
  ///
  /// Stock is committed when the order is approved and released when the note
  /// is dispatched, so the reservation is the ceiling -- dispatching more than
  /// is reserved is refused unless the note allows over-delivery. Defaulting
  /// to the outstanding quantity would look right and fail at dispatch.
  double get deliverable => reserved < outstanding ? reserved : outstanding;

  Json toJson() => {
        'sales_order_line_id': salesOrderLineId,
        'line_number': lineNumber,
        if (description.isNotEmpty) 'description': description,
        'current_delivery_quantity': deliveryQuantity.trim().isEmpty
            ? '0'
            : deliveryQuantity.trim(),
        'free_quantity':
            freeQuantity.trim().isEmpty ? '0' : freeQuantity.trim(),
        'damaged_quantity':
            damagedQuantity.trim().isEmpty ? '0' : damagedQuantity.trim(),
        'unit_price': unitPrice.isEmpty ? '0' : unitPrice,
        if (taxProfileId.isNotEmpty) 'tax_profile_id': taxProfileId,
        if (salesUomId.isNotEmpty) 'sales_uom_id': salesUomId,
        if (inventoryUomId.isNotEmpty) 'inventory_uom_id': inventoryUomId,
        if (warehouseId.isNotEmpty) 'warehouse_id': warehouseId,
        if (remarks.trim().isNotEmpty) 'remarks': remarks.trim(),
      };
}

/// Raise a delivery note against a sales order.
///
/// Unlike a goods receipt, nobody types a batch here. Goods leaving are
/// allocated by the server at dispatch, earliest expiry first, so the editor's
/// job is to show which batches a line is expected to come off rather than to
/// ask for one.
class DeliveryNoteEditorDialog extends StatefulWidget {
  const DeliveryNoteEditorDialog({
    super.key,
    required this.api,
    required this.salesOrders,
    required this.warehouses,
    required this.products,
    this.features = const BusinessFeatures.unknown(),
  });

  final ApiClient api;

  /// Approved orders, as returned by `/api/v1/sales-orders`.
  final List<Json> salesOrders;
  final List<WarehouseRecord> warehouses;
  final List<Product> products;

  /// Which optional fields this firm's profile turns on. Unknown means shown:
  /// a configuration gap is not a decision.
  final BusinessFeatures features;

  @override
  State<DeliveryNoteEditorDialog> createState() =>
      _DeliveryNoteEditorDialogState();
}

class _DeliveryNoteEditorDialogState extends State<DeliveryNoteEditorDialog> {
  Json? _order;
  List<DeliveryDraftLine> _lines = const [];
  // Stock available per product in the chosen warehouse, one row per batch.
  Map<String, List<InventoryRecord>> _stockByProduct = const {};
  String _deliveryDate = _today();
  String _vehicle = '';
  String _driver = '';
  String _remarks = '';
  bool _saving = false;
  bool _loadingLines = false;
  String? _error;

  static String _today() => DateTime.now().toIso8601String().split('T').first;

  String get _orderNumber => stringValue(_order?['order_number']);

  String _productLabel(String productId) {
    for (final Product product in widget.products) {
      if (product.id == productId) return '${product.code} — ${product.name}';
    }
    return productId;
  }

  Future<void> _selectOrder(Json order) async {
    setState(() {
      _order = order;
      _loadingLines = true;
      _error = null;
    });
    final List<Json> orderLines = [
      for (final dynamic line in (order['lines'] as List<dynamic>? ?? const []))
        if (line is Map) Map<String, dynamic>.from(line),
    ];
    final Map<String, double> delivered = await _deliveredByLine(order);
    final String defaultWarehouse = stringValue(order['warehouse_id']);
    final List<DeliveryDraftLine> lines = [
      for (int index = 0; index < orderLines.length; index++)
        _draftLine(
          orderLines[index],
          index + 1,
          delivered[stringValue(orderLines[index]['id'])] ?? 0,
          defaultWarehouse,
        ),
    ];
    final Map<String, List<InventoryRecord>> stock =
        await _stockFor(lines, defaultWarehouse);
    if (!mounted) return;
    setState(() {
      _lines = lines;
      _stockByProduct = stock;
      _loadingLines = false;
    });
  }

  /// Sum what earlier notes already took off each order line.
  Future<Map<String, double>> _deliveredByLine(Json order) async {
    final Map<String, double> delivered = <String, double>{};
    try {
      final Json page = await widget.api.documentPage(
        'delivery-notes',
        page: 1,
        pageSize: 100,
        additionalQuery: {'sales_order_id': stringValue(order['id'])},
      );
      final dynamic data = page['data'];
      for (final dynamic note in data is List ? data : const []) {
        if (note is! Map) continue;
        final String status =
            stringValue(note['status']).trim().toUpperCase();
        // A cancelled note put its stock back, and a draft never took any.
        if (status == 'CANCELLED' || status == 'DRAFT') continue;
        for (final dynamic line in (note['lines'] as List<dynamic>? ?? const [])) {
          if (line is! Map) continue;
          final String id = stringValue(line['sales_order_line_id']);
          if (id.isEmpty) continue;
          delivered[id] = (delivered[id] ?? 0) +
              (double.tryParse(stringValue(line['current_delivery_quantity'])) ??
                  0);
        }
      }
    } on ApiException catch (exception) {
      _error = 'Could not read earlier notes for this order: '
          '${exception.message}. Quantities default to the reservation.';
    }
    return delivered;
  }

  /// Read available stock for the products on these lines, one call per
  /// warehouse rather than one per line.
  Future<Map<String, List<InventoryRecord>>> _stockFor(
    List<DeliveryDraftLine> lines,
    String warehouseId,
  ) async {
    if (warehouseId.isEmpty) return const {};
    final Map<String, List<InventoryRecord>> byProduct = {};
    try {
      final PagedResult<InventoryRecord> rows = await widget.api.inventory(
        page: 1,
        pageSize: 100,
        filters: InventoryQuery(warehouseId: warehouseId),
      );
      final Set<String> wanted = {for (final line in lines) line.productId};
      for (final InventoryRecord row in rows.items) {
        if (!wanted.contains(row.productId)) continue;
        byProduct.putIfAbsent(row.productId, () => []).add(row);
      }
    } on ApiException {
      // The preview is a courtesy; losing it must not stop a dispatch being
      // recorded. The server allocates either way.
      return const {};
    }
    return byProduct;
  }

  DeliveryDraftLine _draftLine(
    Json line,
    int lineNumber,
    double alreadyDelivered,
    String defaultWarehouse,
  ) {
    final DeliveryDraftLine draft = DeliveryDraftLine(
      salesOrderLineId: stringValue(line['id']),
      lineNumber: lineNumber,
      productId: stringValue(line['product_id']),
      description: stringValue(line['description']),
      orderedQuantity: stringValue(line['quantity']),
      reservedQuantity: stringValue(line['reserved_quantity']),
      alreadyDelivered: _trim(alreadyDelivered),
      unitPrice: stringValue(line['unit_price']),
      salesUomId: stringValue(line['sales_uom_id']),
      inventoryUomId: stringValue(line['inventory_uom_id']),
      taxProfileId: stringValue(line['tax_profile_id']),
      deliveryQuantity: '0',
      warehouseId: stringValue(line['warehouse_id']).isNotEmpty
          ? stringValue(line['warehouse_id'])
          : defaultWarehouse,
    );
    draft.deliveryQuantity = _trim(draft.deliverable);
    return draft;
  }

  List<DeliveryDraftLine> _sendableLines() => [
        for (final DeliveryDraftLine line in _lines)
          if ((double.tryParse(line.deliveryQuantity) ?? 0) > 0 ||
              (double.tryParse(line.damagedQuantity) ?? 0) > 0)
            line,
      ];

  String? _validation() {
    if (_order == null) return 'Choose the sales order being delivered.';
    final List<DeliveryDraftLine> sending = _sendableLines();
    if (sending.isEmpty) {
      return 'Enter a delivery quantity on at least one line. A line with '
          'nothing reserved cannot be dispatched until the order is approved.';
    }
    for (final DeliveryDraftLine line in sending) {
      if (line.warehouseId.isEmpty) {
        return 'Line ${line.lineNumber}: choose the warehouse the goods leave '
            'from.';
      }
    }
    return null;
  }

  Future<void> _save() async {
    final String? problem = _validation();
    if (problem != null) {
      setState(() => _error = problem);
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final List<DeliveryDraftLine> sending = _sendableLines();
      final Json payload = {
        'sales_order_id': stringValue(_order!['id']),
        'delivery_date': _deliveryDate,
        if (_vehicle.trim().isNotEmpty) 'vehicle': _vehicle.trim(),
        if (_driver.trim().isNotEmpty) 'driver': _driver.trim(),
        if (_remarks.trim().isNotEmpty) 'remarks': _remarks.trim(),
        'lines': [
          for (int index = 0; index < sending.length; index++)
            {...sending[index].toJson(), 'line_number': index + 1},
        ],
      };
      final Json response = await widget.api.create('delivery-notes', payload);
      if (!mounted) return;
      final dynamic data = response['data'];
      Navigator.pop(context, data is Json ? data : response);
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() {
        _error = exception.message;
        _saving = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) => WorkspaceDialog(
        title: 'New Delivery Note',
        subtitle: _order == null
            ? 'Choose a sales order to deliver against'
            : 'Against $_orderNumber',
        icon: Icons.local_shipping_outlined,
        loading: _saving || _loadingLines,
        onClose: _saving ? null : () => Navigator.pop(context),
        onSave: _saving ? null : _save,
        footer: Padding(
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.end,
            children: [
              TextButton(
                onPressed: _saving ? null : () => Navigator.pop(context),
                child: const Text('Cancel'),
              ),
              const SizedBox(width: AppSpacing.md),
              FilledButton.icon(
                onPressed: _saving ? null : _save,
                icon: const Icon(Icons.save_outlined),
                label: const Text('Save Delivery Note'),
              ),
            ],
          ),
        ),
        body: SingleChildScrollView(
          padding: const EdgeInsets.all(AppSpacing.xl),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (_error != null) ...[
                MaterialBanner(
                  content: Text(_error!),
                  actions: [
                    TextButton(
                      onPressed: () => setState(() => _error = null),
                      child: const Text('Dismiss'),
                    ),
                  ],
                ),
                const SizedBox(height: AppSpacing.lg),
              ],
              const SectionHeader(
                title: 'Dispatch',
                description: 'Which order is going out, when, and on what.',
              ),
              const SizedBox(height: AppSpacing.md),
              _headerFields(),
              const SizedBox(height: AppSpacing.xl),
              SectionHeader(
                title: 'Items Going Out',
                description: _order == null
                    ? 'Lines appear once a sales order is chosen.'
                    : 'Lines come from the order and default to what is '
                        'reserved for it. Batches are chosen at dispatch, '
                        'earliest expiry first.',
              ),
              const SizedBox(height: AppSpacing.md),
              if (_order == null)
                const StandardEmptyState(
                  type: EmptyStateType.noRecords,
                  title: 'No sales order chosen',
                  message: 'A delivery note records what leaves against an '
                      'order, so pick one above.',
                )
              else
                ..._lineCards(),
            ],
          ),
        ),
      );

  Widget _headerFields() => Wrap(
        spacing: AppSpacing.lg,
        runSpacing: AppSpacing.lg,
        children: [
          SizedBox(
            width: 320,
            child: DropdownButtonFormField<String>(
              initialValue:
                  _order == null ? null : stringValue(_order!['id']),
              isExpanded: true,
              decoration: const InputDecoration(
                labelText: 'Sales Order *',
                helperText: 'Approved orders only',
              ),
              items: [
                for (final Json order in widget.salesOrders)
                  DropdownMenuItem<String>(
                    value: stringValue(order['id']),
                    child: Text(
                      '${stringValue(order['order_number'])} • '
                      '${stringValue(order['order_date'])}',
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
              ],
              onChanged: _saving
                  ? null
                  : (value) {
                      final Iterable<Json> match = widget.salesOrders
                          .where((order) => stringValue(order['id']) == value);
                      if (match.isNotEmpty) _selectOrder(match.first);
                    },
            ),
          ),
          _text('Delivery Date *', _deliveryDate,
              (value) => _deliveryDate = value, 'YYYY-MM-DD'),
          // Offered only where the firm's profile enables it. The server
          // refuses a dispatch carrying one otherwise -- a 403 naming the
          // feature, after the whole document has been keyed.
          if (widget.features.isEnabled('VEHICLE_TRACKING'))
            _text('Vehicle', _vehicle, (value) => _vehicle = value, null),
          _text('Driver', _driver, (value) => _driver = value, null),
          _text('Remarks', _remarks, (value) => _remarks = value, null),
        ],
      );

  Widget _text(
    String label,
    String value,
    ValueChanged<String> onChanged,
    String? hint, {
    double width = 220,
  }) =>
      SizedBox(
        width: width,
        child: TextFormField(
          initialValue: value,
          decoration: InputDecoration(labelText: label, hintText: hint),
          onChanged: (next) => setState(() => onChanged(next)),
        ),
      );

  List<Widget> _lineCards() => [
        for (final DeliveryDraftLine line in _lines) ...[
          Card(
            clipBehavior: Clip.antiAlias,
            child: Padding(
              padding: const EdgeInsets.all(AppSpacing.lg),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          'Line ${line.lineNumber} · '
                          '${_productLabel(line.productId)}',
                          style: Theme.of(context).textTheme.titleMedium,
                        ),
                      ),
                      Text(
                        'Ordered ${line.orderedQuantity} · reserved '
                        '${line.reservedQuantity} · already delivered '
                        '${line.alreadyDelivered}',
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                    ],
                  ),
                  // Nothing reserved has two causes and they need different
                  // answers: an order nobody approved has reserved nothing
                  // yet, while a fully delivered one released its reservation
                  // on the way out. Telling someone to approve an order that
                  // is already delivered sends them looking for a button that
                  // will not help.
                  if (line.outstanding <= 0) ...[
                    const SizedBox(height: AppSpacing.sm),
                    Text(
                      'This line has already been delivered in full.',
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ] else if (line.reserved <= 0) ...[
                    const SizedBox(height: AppSpacing.sm),
                    Text(
                      'Nothing is reserved for this line, so dispatching it '
                      'would be refused. Approve the sales order first.',
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                            color: Theme.of(context).colorScheme.error,
                          ),
                    ),
                  ],
                  const SizedBox(height: AppSpacing.md),
                  Wrap(
                    spacing: AppSpacing.lg,
                    runSpacing: AppSpacing.lg,
                    children: [
                      _lineField(
                        'Delivering *',
                        line.deliveryQuantity,
                        (value) => line.deliveryQuantity = value,
                        width: 130,
                      ),
                      _lineField(
                        'Free',
                        line.freeQuantity,
                        (value) => line.freeQuantity = value,
                        width: 110,
                      ),
                      _lineField(
                        'Damaged',
                        line.damagedQuantity,
                        (value) => line.damagedQuantity = value,
                        width: 110,
                      ),
                      SizedBox(
                        width: 240,
                        child: DropdownButtonFormField<String>(
                          initialValue: line.warehouseId.isEmpty
                              ? null
                              : line.warehouseId,
                          isExpanded: true,
                          decoration:
                              const InputDecoration(labelText: 'Warehouse *'),
                          items: [
                            for (final WarehouseRecord warehouse
                                in widget.warehouses)
                              DropdownMenuItem<String>(
                                value: warehouse.id,
                                child: Text(
                                  warehouse.name,
                                  overflow: TextOverflow.ellipsis,
                                ),
                              ),
                          ],
                          onChanged: (value) =>
                              setState(() => line.warehouseId = value ?? ''),
                        ),
                      ),
                      _lineField(
                        'Remarks',
                        line.remarks,
                        (value) => line.remarks = value,
                        width: 260,
                      ),
                    ],
                  ),
                  const SizedBox(height: AppSpacing.md),
                  _allocationPreview(line),
                ],
              ),
            ),
          ),
          const SizedBox(height: AppSpacing.md),
        ],
      ];

  /// Show which batches the line is expected to come off.
  ///
  /// Nobody types a batch on a delivery note -- the server allocates at
  /// dispatch, earliest expiry first. Showing the expected split is what lets
  /// the person packing the crate know which cartons to pick, and it is
  /// labelled as expected rather than decided because stock can move between
  /// saving the note and dispatching it.
  Widget _allocationPreview(DeliveryDraftLine line) {
    final List<InventoryRecord> stock = _stockByProduct[line.productId] ?? [];
    final double quantity = double.tryParse(line.deliveryQuantity) ?? 0;
    if (stock.isEmpty || quantity <= 0) {
      return Text(
        stock.isEmpty
            ? 'No stock of this product is on hand in the chosen warehouse.'
            : 'Enter a quantity to see which batches it would come from.',
        style: Theme.of(context).textTheme.bodySmall,
      );
    }
    final List<BatchDraw> draws = previewAllocation(stock, quantity);
    final double covered =
        draws.fold<double>(0, (total, draw) => total + draw.quantity);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Expected to ship from — earliest expiry first, decided at dispatch',
          style: Theme.of(context).textTheme.labelMedium,
        ),
        const SizedBox(height: AppSpacing.xs),
        for (final BatchDraw draw in draws)
          Text(draw.label, style: Theme.of(context).textTheme.bodySmall),
        if (covered < quantity)
          Text(
            'Short by ${_trim(quantity - covered)} — there is not enough '
            'available stock to cover this line.',
            style: Theme.of(context).textTheme.bodySmall?.copyWith(
                  color: Theme.of(context).colorScheme.error,
                ),
          ),
      ],
    );
  }

  Widget _lineField(
    String label,
    String value,
    ValueChanged<String> onChanged, {
    required double width,
  }) =>
      SizedBox(
        width: width,
        child: TextFormField(
          initialValue: value,
          decoration: InputDecoration(labelText: label),
          onChanged: (next) => setState(() => onChanged(next)),
        ),
      );
}
