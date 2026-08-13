import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../models/branch_warehouse.dart';
import '../../models/entities.dart';
import '../../models/goods_receipt.dart';
import '../../models/product.dart';
import '../../models/purchase.dart';
import '../workspace/desktop_framework.dart';

/// One line being received, as the storeman is editing it.
///
/// A goods receipt line always belongs to a purchase order line -- the backend
/// requires `purchase_order_line_id` and refuses anything else -- so the lines
/// are seeded from the order and never added by hand. What the storeman
/// supplies is what actually came off the lorry: how much of it, how much was
/// rejected or damaged, which bay it went to, and the batch number on the
/// carton.
class GoodsReceiptDraftLine {
  GoodsReceiptDraftLine({
    required this.purchaseOrderLineId,
    required this.lineNumber,
    required this.productId,
    required this.description,
    required this.orderedQuantity,
    required this.alreadyReceived,
    required this.unitPrice,
    required this.purchaseUomId,
    required this.inventoryUomId,
    required this.taxProfileId,
    required this.batchRequired,
    required this.expiryRequired,
    required this.receiptQuantity,
    this.freeQuantity = '0',
    this.rejectedQuantity = '0',
    this.damagedQuantity = '0',
    this.warehouseId = '',
    this.batchNumber = '',
    this.expiryDate = '',
    this.manufacturingDate = '',
    this.remarks = '',
  });

  final String purchaseOrderLineId;
  final int lineNumber;
  final String productId;
  final String description;
  final String orderedQuantity;
  final String alreadyReceived;
  final String unitPrice;
  final String purchaseUomId;
  final String inventoryUomId;
  final String taxProfileId;
  final bool batchRequired;
  final bool expiryRequired;

  String receiptQuantity;
  String freeQuantity;
  String rejectedQuantity;
  String damagedQuantity;
  String warehouseId;
  String batchNumber;
  String expiryDate;
  String manufacturingDate;
  String remarks;

  /// What is still outstanding on the order line, never below zero.
  double get outstanding {
    final double ordered = double.tryParse(orderedQuantity) ?? 0;
    final double received = double.tryParse(alreadyReceived) ?? 0;
    final double left = ordered - received;
    return left < 0 ? 0 : left;
  }

  Json toJson() => {
        'purchase_order_line_id': purchaseOrderLineId,
        'line_number': lineNumber,
        if (description.isNotEmpty) 'description': description,
        'current_receipt_quantity': receiptQuantity.trim().ifEmpty('0'),
        'rejected_quantity': rejectedQuantity.trim().ifEmpty('0'),
        'damaged_quantity': damagedQuantity.trim().ifEmpty('0'),
        'free_quantity': freeQuantity.trim().ifEmpty('0'),
        'unit_price': unitPrice.ifEmpty('0'),
        if (taxProfileId.isNotEmpty) 'tax_profile_id': taxProfileId,
        if (purchaseUomId.isNotEmpty) 'purchase_uom_id': purchaseUomId,
        if (inventoryUomId.isNotEmpty) 'inventory_uom_id': inventoryUomId,
        if (warehouseId.isNotEmpty) 'warehouse_id': warehouseId,
        if (batchNumber.trim().isNotEmpty) 'batch_number': batchNumber.trim(),
        if (expiryDate.trim().isNotEmpty) 'expiry_date': expiryDate.trim(),
        if (manufacturingDate.trim().isNotEmpty)
          'manufacturing_date': manufacturingDate.trim(),
        if (remarks.trim().isNotEmpty) 'remarks': remarks.trim(),
      };
}

extension _EmptyString on String {
  String ifEmpty(String fallback) => trim().isEmpty ? fallback : this;
}

/// Raise a goods receipt against a purchase order.
///
/// This is the first document the desktop can create. Until it existed the
/// batch work behind it was unreachable by a user: the backend resolves a
/// batch from the number on a receipt line, and nothing in the client could
/// send one.
class GoodsReceiptEditorDialog extends StatefulWidget {
  const GoodsReceiptEditorDialog({
    super.key,
    required this.api,
    required this.purchaseOrders,
    required this.warehouses,
    required this.products,
  });

  final ApiClient api;

  /// Orders that can still be received against.
  final List<PurchaseOrder> purchaseOrders;
  final List<WarehouseRecord> warehouses;
  final List<Product> products;

  @override
  State<GoodsReceiptEditorDialog> createState() =>
      _GoodsReceiptEditorDialogState();
}

class _GoodsReceiptEditorDialogState extends State<GoodsReceiptEditorDialog> {
  PurchaseOrder? _order;
  List<GoodsReceiptDraftLine> _lines = const [];
  String _receiptDate = _today();
  String _invoiceReference = '';
  String _transportDetails = '';
  String _vehicleNumber = '';
  String _remarks = '';
  bool _saving = false;
  bool _loadingLines = false;
  String? _error;

  static String _today() => DateTime.now().toIso8601String().split('T').first;

  String _productLabel(String productId) {
    for (final Product product in widget.products) {
      if (product.id == productId) return '${product.code} — ${product.name}';
    }
    return productId;
  }

  /// Seed the lines from the order, defaulting each to what is outstanding.
  ///
  /// The already-received figure is summed from the order's completed
  /// receipts. Without it a second receipt against a partly-received order
  /// would default to the full ordered quantity and be refused on save for
  /// over-receipt, which reads as a bug to the person typing it.
  Future<void> _selectOrder(PurchaseOrder order) async {
    setState(() {
      _order = order;
      _loadingLines = true;
      _error = null;
    });
    final Map<String, double> received = <String, double>{};
    try {
      final PagedResult<GoodsReceiptRecord> existing =
          await widget.api.goodsReceipts(
        page: 1,
        pageSize: 100,
        filters: {'purchase_order_id': order.id, 'status': 'COMPLETED'},
      );
      for (final GoodsReceiptRecord receipt in existing.items) {
        for (final GoodsReceiptLine line in receipt.lines) {
          received[line.purchaseOrderLineId] =
              (received[line.purchaseOrderLineId] ?? 0) +
                  (double.tryParse(line.currentReceiptQuantity) ?? 0);
        }
      }
    } on ApiException catch (exception) {
      // A receipt can still be raised without this; the server enforces the
      // over-receipt rule either way. Say so rather than blocking.
      _error = 'Could not read earlier receipts for this order: '
          '${exception.message}. Quantities default to the full order.';
    }
    if (!mounted) return;
    final String defaultWarehouse =
        order.warehouseId.isNotEmpty ? order.warehouseId : '';
    setState(() {
      _lines = [
        for (int index = 0; index < order.lines.length; index++)
          _draftLine(
            order.lines[index],
            index + 1,
            received[order.lines[index].id] ?? 0,
            defaultWarehouse,
          ),
      ];
      _loadingLines = false;
    });
  }

  GoodsReceiptDraftLine _draftLine(
    PurchaseOrderLine line,
    int lineNumber,
    double alreadyReceived,
    String defaultWarehouse,
  ) {
    final GoodsReceiptDraftLine draft = GoodsReceiptDraftLine(
      purchaseOrderLineId: line.id,
      lineNumber: lineNumber,
      productId: line.productId,
      description: line.description,
      orderedQuantity: line.orderedQuantity,
      alreadyReceived: _trim(alreadyReceived),
      unitPrice: line.unitPrice,
      purchaseUomId: line.purchaseUomId,
      inventoryUomId: line.inventoryUomId,
      taxProfileId: line.taxProfileId,
      batchRequired: line.batchRequired,
      expiryRequired: line.expiryRequired,
      receiptQuantity: '0',
      warehouseId: defaultWarehouse,
    );
    draft.receiptQuantity = _trim(draft.outstanding);
    return draft;
  }

  static String _trim(double value) =>
      value == value.roundToDouble() ? value.toStringAsFixed(0) : '$value';

  /// Lines with nothing on them are not sent; the rest must add up.
  String? _validation() {
    if (_order == null) return 'Choose the purchase order being received.';
    final List<GoodsReceiptDraftLine> sending = _sendableLines();
    if (sending.isEmpty) {
      return 'Enter a received quantity on at least one line.';
    }
    for (final GoodsReceiptDraftLine line in sending) {
      if (line.warehouseId.isEmpty) {
        return 'Line ${line.lineNumber}: choose the warehouse the goods went to.';
      }
      if (line.batchRequired && line.batchNumber.trim().isEmpty) {
        return 'Line ${line.lineNumber}: this product must be received with a '
            'batch number.';
      }
    }
    return null;
  }

  List<GoodsReceiptDraftLine> _sendableLines() => [
        for (final GoodsReceiptDraftLine line in _lines)
          if ((double.tryParse(line.receiptQuantity) ?? 0) > 0 ||
              (double.tryParse(line.rejectedQuantity) ?? 0) > 0 ||
              (double.tryParse(line.damagedQuantity) ?? 0) > 0)
            line,
      ];

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
      final List<GoodsReceiptDraftLine> sending = _sendableLines();
      final Json payload = {
        'purchase_order_id': _order!.id,
        'receipt_date': _receiptDate,
        if (_invoiceReference.trim().isNotEmpty)
          'invoice_reference': _invoiceReference.trim(),
        if (_transportDetails.trim().isNotEmpty)
          'transport_details': _transportDetails.trim(),
        if (_vehicleNumber.trim().isNotEmpty)
          'vehicle_number': _vehicleNumber.trim(),
        if (_remarks.trim().isNotEmpty) 'remarks': _remarks.trim(),
        // Line numbers are renumbered from one over what is actually being
        // sent, so skipping a line that did not arrive cannot leave a gap the
        // document has to explain.
        'lines': [
          for (int index = 0; index < sending.length; index++)
            {...sending[index].toJson(), 'line_number': index + 1},
        ],
      };
      final GoodsReceiptRecord saved =
          await widget.api.createGoodsReceipt(payload);
      if (!mounted) return;
      Navigator.pop(context, saved);
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
        title: 'New Goods Receipt',
        subtitle: _order == null
            ? 'Choose a purchase order to receive against'
            : 'Against ${_order!.poNumber}',
        icon: Icons.inventory_2_outlined,
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
                label: const Text('Save Receipt'),
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
                title: 'Delivery',
                description:
                    'Which order arrived, when, and what paperwork came with it.',
              ),
              const SizedBox(height: AppSpacing.md),
              _headerFields(),
              const SizedBox(height: AppSpacing.xl),
              SectionHeader(
                title: 'Received Items',
                description: _order == null
                    ? 'Lines appear once a purchase order is chosen.'
                    : 'Lines come from the order. Leave a quantity at zero for '
                        'anything that did not arrive.',
              ),
              const SizedBox(height: AppSpacing.md),
              if (_order == null)
                const StandardEmptyState(
                  type: EmptyStateType.noRecords,
                  title: 'No purchase order chosen',
                  message:
                      'A goods receipt always records what arrived against an '
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
              initialValue: _order?.id,
              // A document number and date is longer than the field on a
              // 1366-wide screen; without this the closed dropdown overflows
              // rather than truncating.
              isExpanded: true,
              decoration: const InputDecoration(
                labelText: 'Purchase Order *',
                helperText: 'Approved orders only',
              ),
              items: [
                for (final PurchaseOrder order in widget.purchaseOrders)
                  DropdownMenuItem<String>(
                    value: order.id,
                    child: Text(
                      '${order.poNumber} • ${order.purchaseDate}',
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
              ],
              onChanged: _saving
                  ? null
                  : (value) {
                      final Iterable<PurchaseOrder> match = widget.purchaseOrders
                          .where((order) => order.id == value);
                      if (match.isNotEmpty) _selectOrder(match.first);
                    },
            ),
          ),
          _text('Receipt Date *', _receiptDate,
              (value) => _receiptDate = value, 'YYYY-MM-DD'),
          _text('Supplier Invoice Reference', _invoiceReference,
              (value) => _invoiceReference = value, null),
          _text('Transport Details', _transportDetails,
              (value) => _transportDetails = value, null),
          _text('Vehicle Number', _vehicleNumber,
              (value) => _vehicleNumber = value, null),
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
        for (final GoodsReceiptDraftLine line in _lines) ...[
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
                          'Line ${line.lineNumber} · ${_productLabel(line.productId)}',
                          style: Theme.of(context).textTheme.titleMedium,
                        ),
                      ),
                      Text(
                        'Ordered ${line.orderedQuantity} · '
                        'already received ${line.alreadyReceived}',
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                    ],
                  ),
                  const SizedBox(height: AppSpacing.md),
                  Wrap(
                    spacing: AppSpacing.lg,
                    runSpacing: AppSpacing.lg,
                    children: [
                      _lineField(
                        'Accepted *',
                        line.receiptQuantity,
                        (value) => line.receiptQuantity = value,
                        width: 130,
                      ),
                      _lineField(
                        'Free',
                        line.freeQuantity,
                        (value) => line.freeQuantity = value,
                        width: 110,
                      ),
                      _lineField(
                        'Rejected',
                        line.rejectedQuantity,
                        (value) => line.rejectedQuantity = value,
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
                          initialValue:
                              line.warehouseId.isEmpty ? null : line.warehouseId,
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
                          onChanged: (value) => setState(
                              () => line.warehouseId = value ?? ''),
                        ),
                      ),
                      // The batch number is typed off the carton. The server
                      // resolves it to a real batch and refuses the line when
                      // the product requires one, so the asterisk here is a
                      // hint and not the rule.
                      _lineField(
                        line.batchRequired ? 'Batch Number *' : 'Batch Number',
                        line.batchNumber,
                        (value) => line.batchNumber = value,
                        width: 200,
                      ),
                      _lineField(
                        line.expiryRequired ? 'Expiry Date *' : 'Expiry Date',
                        line.expiryDate,
                        (value) => line.expiryDate = value,
                        width: 180,
                        hint: 'YYYY-MM-DD',
                      ),
                      _lineField(
                        'Manufacturing Date',
                        line.manufacturingDate,
                        (value) => line.manufacturingDate = value,
                        width: 180,
                        hint: 'YYYY-MM-DD',
                      ),
                      _lineField(
                        'Remarks',
                        line.remarks,
                        (value) => line.remarks = value,
                        width: 260,
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: AppSpacing.md),
        ],
      ];

  Widget _lineField(
    String label,
    String value,
    ValueChanged<String> onChanged, {
    required double width,
    String? hint,
  }) =>
      SizedBox(
        width: width,
        child: TextFormField(
          initialValue: value,
          decoration: InputDecoration(labelText: label, hintText: hint),
          onChanged: (next) => setState(() => onChanged(next)),
        ),
      );
}
