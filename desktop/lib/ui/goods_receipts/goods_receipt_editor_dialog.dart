import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/api/api_client.dart';
import '../../core/business/business_features.dart';
import '../../core/design/design_tokens.dart';
import '../../models/branch_warehouse.dart';
import '../../models/entities.dart';
import '../../models/goods_receipt.dart';
import '../../models/product.dart';
import '../../models/purchase.dart';
import '../../phase2/document_page.dart';
import '../../phase2/indian_format.dart';
import '../document_framework/document_steps.dart';
import '../workspace/desktop_framework.dart';
import '../../models/document_file.dart';
import '../purchases/document_attachments_dialog.dart';
import 'goods_receipt_eway_dialog.dart';
import 'serial_entry_dialog.dart';

part 'goods_receipt_editor_phase2.dart';

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
    this.mrp = '',
    this.sellingPrice = '',
    this.ptr = '',
    this.pts = '',
    this.remarks = '',
    this.schemeName = '',
    this.serialTracked = false,
    this.orderedAsCapital = false,
    this.capitalGoods = false,
  });

  /// D-BUY-40: whether the order line was ordered as capital goods, and
  /// whether this line is received as such. The key travels only when they
  /// differ, so silence keeps meaning "as ordered".
  final bool orderedAsCapital;
  bool capitalGoods;

  /// Whether the product carries a serial per unit (PG-10).
  bool serialTracked;

  /// The serials typed for the line; sent only once the user has touched
  /// them, because absent leaves what the server holds.
  List<String> serials = [];
  bool serialsTouched = false;

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

  /// Per stock unit, tax included; goes on the batch the receipt creates.
  String mrp;

  /// Per stock unit, before tax.
  String sellingPrice;

  /// Retailer / stockist rates (BATCH_PTR_PTS); sent only when typed.
  String ptr;
  String pts;
  String remarks;

  /// The supplier's scheme the free goods came under (BUY-1); optional.
  String schemeName;

  /// What other draft receipts against the same order already hold of this
  /// line, and their numbers (D-BUY-23). A draft reserves nothing and the
  /// server refuses over-receipt only at Complete, so without this two
  /// people each draft the whole quantity and learn it there.
  double heldByOtherDrafts = 0;
  List<String> otherDraftNumbers = const [];

  /// What is due once the other drafts are completed, never below zero:
  /// what a new receipt starts at.
  double get dueAfterOtherDrafts {
    final double left = outstanding - heldByOtherDrafts;
    return left < 0 ? 0 : left;
  }

  /// What is still outstanding on the order line, never below zero.
  double get outstanding {
    final double ordered = double.tryParse(orderedQuantity) ?? 0;
    final double received = double.tryParse(alreadyReceived) ?? 0;
    final double left = ordered - received;
    return left < 0 ? 0 : left;
  }

  Json toJson({bool ptrPts = false}) => {
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
        // Only a line with a batch has one to put them on.
        if (batchNumber.trim().isNotEmpty && mrp.trim().isNotEmpty)
          'mrp': mrp.trim(),
        if (batchNumber.trim().isNotEmpty && sellingPrice.trim().isNotEmpty)
          'selling_price': sellingPrice.trim(),
        if (ptrPts && batchNumber.trim().isNotEmpty && ptr.trim().isNotEmpty)
          'ptr': ptr.trim(),
        if (ptrPts && batchNumber.trim().isNotEmpty && pts.trim().isNotEmpty)
          'pts': pts.trim(),
        if (remarks.trim().isNotEmpty) 'remarks': remarks.trim(),
        if (schemeName.trim().isNotEmpty) 'scheme_name': schemeName.trim(),
        if (serialTracked && serialsTouched) 'serial_numbers': serials,
        if (capitalGoods != orderedAsCapital) 'is_capital_goods': capitalGoods,
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
    this.existing,
    this.features = const BusinessFeatures.unknown(),
    this.steps = const [],
    this.canAttach = true,
  });

  final ApiClient api;

  /// Whether the user may add and delete files on the receipt
  /// (`PURCHASE_RECEIVE`); without it they can only look.
  final bool canAttach;

  /// Orders that can still be received against.
  final List<PurchaseOrder> purchaseOrders;
  final List<WarehouseRecord> warehouses;
  final List<Product> products;

  /// The draft being corrected, where one is.
  ///
  /// A receipt could be created, completed, cancelled and closed and never
  /// corrected, so a wrong quantity meant cancelling and re-keying every
  /// line -- and the service takes the edit precisely so it need not. Only a
  /// draft: once completed the lines are what stock was posted at.
  final GoodsReceiptRecord? existing;

  /// Which optional fields this firm's profile turns on. Unknown means shown:
  /// a configuration gap is not a decision.
  final BusinessFeatures features;

  /// The receipt's next steps, as the list toolbar offers them (D-BUY-22):
  /// *Save & complete* where the user may complete, and Cancel or Close on a
  /// draft already saved. Empty offers none.
  final List<DocumentStep<GoodsReceiptRecord>> steps;

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
  String _ewayBillNumber = '';
  String _ewayBillDate = '';
  String _remarks = '';
  bool _saving = false;
  bool _loadingLines = false;
  String? _error;

  /// Phase 2: the line the side panel follows.
  int _current = 0;

  void _setState(VoidCallback change) => setState(change);

  /// The draft this window has saved itself, where *Save & complete* saved
  /// it and the completing did not happen -- refused, or backed out of. The
  /// next save corrects it rather than raising a second receipt.
  GoodsReceiptRecord? _saved;

  /// The receipt as it stands on the server, where it is saved at all.
  GoodsReceiptRecord? get _record => _saved ?? widget.existing;

  bool get _isEditing => _record != null;

  @override
  void initState() {
    super.initState();
    final GoodsReceiptRecord? current = widget.existing;
    if (current != null) {
      _receiptDate = current.receiptDate;
      _invoiceReference = current.invoiceReference;
      _transportDetails = current.transportDetails;
      _vehicleNumber = current.vehicleNumber;
      _ewayBillNumber = current.ewayBillNumber;
      _ewayBillDate = current.ewayBillDate;
      _remarks = current.remarks;
      final PurchaseOrder? order = _orderOf(current.purchaseOrderId);
      if (order != null) {
        unawaited(_selectOrder(order));
      } else {
        unawaited(_fetchOrder(current.purchaseOrderId));
      }
    }
  }

  /// Read the draft's order when the list did not hand it over -- it had not
  /// finished loading, or the order has since left the receivable list. The
  /// draft's lines are that order's lines, so without it the editor would
  /// show a receipt against nothing.
  Future<void> _fetchOrder(String orderId) async {
    setState(() => _loadingLines = true);
    try {
      final PurchaseOrder order = await widget.api.purchaseOrder(orderId);
      if (!mounted) return;
      await _selectOrder(order);
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() {
        _loadingLines = false;
        _error = 'Could not read the purchase order this receipt was raised '
            'against: ${exception.message}';
      });
    }
  }

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
    // Free goods already in, per order line, so a new receipt starts at the
    // free goods still owed (D-BUY-33).
    final Map<String, double> receivedFree = <String, double>{};
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
          receivedFree[line.purchaseOrderLineId] =
              (receivedFree[line.purchaseOrderLineId] ?? 0) +
                  (double.tryParse(line.freeQuantity) ?? 0);
        }
      }
    } on ApiException catch (exception) {
      // A receipt can still be raised without this; the server enforces the
      // over-receipt rule either way. Say so rather than blocking.
      _error = 'Could not read earlier receipts for this order: '
          '${exception.message}. Quantities default to the full order.';
    }
    final Map<String, double> drafted = <String, double>{};
    final Map<String, List<String>> draftNumbers = <String, List<String>>{};
    try {
      // The other drafts against this order (D-BUY-23): one read, filtered
      // by the server. This receipt's own draft is not "another".
      final PagedResult<GoodsReceiptRecord> drafts =
          await widget.api.goodsReceipts(
        page: 1,
        pageSize: 100,
        filters: {'purchase_order_id': order.id, 'status': 'DRAFT'},
      );
      for (final GoodsReceiptRecord receipt in drafts.items) {
        if (receipt.status != 'DRAFT' || receipt.id == _record?.id) continue;
        for (final GoodsReceiptLine line in receipt.lines) {
          final double quantity =
              double.tryParse(line.currentReceiptQuantity) ?? 0;
          if (quantity <= 0) continue;
          final String key = line.purchaseOrderLineId;
          drafted[key] = (drafted[key] ?? 0) + quantity;
          final String number =
              receipt.grnNumber.isEmpty ? 'unnumbered' : receipt.grnNumber;
          final List<String> numbers = draftNumbers[key] ?? <String>[];
          if (!numbers.contains(number)) numbers.add(number);
          draftNumbers[key] = numbers;
        }
      }
    } on ApiException {
      // Only a warning is lost; the server still refuses over-receipt at
      // Complete.
    }
    if (!mounted) return;
    final String defaultWarehouse =
        order.warehouseId.isNotEmpty ? order.warehouseId : '';
    setState(() {
      _lines = _withSavedQuantities([
        for (int index = 0; index < order.lines.length; index++)
          _draftLine(
            order.lines[index],
            index + 1,
            received[order.lines[index].id] ?? 0,
            defaultWarehouse,
            freeReceived: receivedFree[order.lines[index].id] ?? 0,
            heldByOtherDrafts: drafted[order.lines[index].id] ?? 0,
            otherDraftNumbers: draftNumbers[order.lines[index].id] ?? const [],
          ),
      ]);
      _loadingLines = false;
    });
  }

  /// The order this receipt was raised against, if it is still in the list.
  PurchaseOrder? _orderOf(String orderId) {
    for (final PurchaseOrder order in widget.purchaseOrders) {
      if (order.id == orderId) return order;
    }
    return null;
  }

  /// Put the draft's own numbers back on the lines the order derived.
  ///
  /// The order gives each line its ordered quantity, units and tax profile;
  /// the receipt gives what was actually counted. Matched on
  /// `purchase_order_line_id`, which both carry -- the same key the payload
  /// is built on.
  List<GoodsReceiptDraftLine> _withSavedQuantities(
    List<GoodsReceiptDraftLine> drafts,
  ) {
    final GoodsReceiptRecord? current = widget.existing;
    if (current == null) return drafts;
    final Map<String, GoodsReceiptLine> saved = <String, GoodsReceiptLine>{
      for (final GoodsReceiptLine line in current.lines)
        line.purchaseOrderLineId: line,
    };
    for (final GoodsReceiptDraftLine draft in drafts) {
      final GoodsReceiptLine? line = saved[draft.purchaseOrderLineId];
      if (line == null) continue;
      draft.receiptQuantity = line.currentReceiptQuantity;
      draft.rejectedQuantity = line.rejectedQuantity;
      draft.damagedQuantity = line.damagedQuantity;
      draft.freeQuantity = line.freeQuantity;
      if (line.warehouseId.isNotEmpty) draft.warehouseId = line.warehouseId;
      draft.batchNumber = line.batchNumber;
      draft.expiryDate = line.expiryDate;
      draft.manufacturingDate = line.manufacturingDate;
      draft.mrp = line.mrp;
      draft.sellingPrice = line.sellingPrice;
      draft.ptr = line.ptr;
      draft.pts = line.pts;
      draft.remarks = line.remarks;
      draft.schemeName = line.schemeName;
      draft.serialTracked = draft.serialTracked || line.serialTracked;
      draft.serials = List<String>.of(line.serialNumbers);
      draft.capitalGoods = line.isCapitalGoods;
    }
    return drafts;
  }

  GoodsReceiptDraftLine _draftLine(
    PurchaseOrderLine line,
    int lineNumber,
    double alreadyReceived,
    String defaultWarehouse, {
    double freeReceived = 0,
    double heldByOtherDrafts = 0,
    List<String> otherDraftNumbers = const [],
  }) {
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
      orderedAsCapital: line.isCapitalGoods,
      capitalGoods: line.isCapitalGoods,
      serialTracked: widget.products
          .any((item) => item.id == line.productId && item.trackSerial),
    );
    draft
      ..heldByOtherDrafts = heldByOtherDrafts
      ..otherDraftNumbers = otherDraftNumbers;
    // Starts at what the other drafts leave (D-BUY-23), so two people
    // receiving the same order do not each start at the whole of it.
    draft.receiptQuantity = _trim(draft.dueAfterOtherDrafts);
    // The order's free goods still to come start on the line too: a free
    // product of its own (buy soap, get a bucket) is a line with nothing to
    // pay and only free goods, and it used to start at nothing (D-BUY-33).
    final double freeDue =
        (double.tryParse(line.freeQuantity) ?? 0) - freeReceived;
    draft.freeQuantity = _trim(freeDue > 0 ? freeDue : 0);
    return draft;
  }

  static String _trim(double value) =>
      value == value.roundToDouble() ? value.toStringAsFixed(0) : '$value';

  /// Lines with nothing on them are not sent; the rest must add up.
  String? _validation() {
    if (_order == null) return 'Choose the purchase order being received.';
    final String? ewayProblem = ewayBillProblem(_ewayBillNumber);
    if (ewayProblem != null) return ewayProblem;
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
      if (widget.features.isEnabled('BATCH_PTR_PTS')) {
        final String? rate = ptrPtsProblem(line);
        if (rate != null) return rate;
      }
    }
    return null;
  }

  /// A PTR or PTS above the line's MRP, said before the server has to.
  String? ptrPtsProblem(GoodsReceiptDraftLine line) {
    final double? mrp = double.tryParse(line.mrp.trim());
    if (mrp == null) return null;
    for (final MapEntry<String, String> rate in {
      'PTR': line.ptr,
      'PTS': line.pts,
    }.entries) {
      final double? value = double.tryParse(rate.value.trim());
      if (value != null && value > mrp) {
        return 'Line ${line.lineNumber}: ${rate.key} cannot be more than '
            'the MRP.';
      }
    }
    return null;
  }

  List<GoodsReceiptDraftLine> _sendableLines() => [
        for (final GoodsReceiptDraftLine line in _lines)
          if ((double.tryParse(line.receiptQuantity) ?? 0) > 0 ||
              // A line of free goods alone is goods received (D-BUY-33).
              (double.tryParse(line.freeQuantity) ?? 0) > 0 ||
              (double.tryParse(line.rejectedQuantity) ?? 0) > 0 ||
              (double.tryParse(line.damagedQuantity) ?? 0) > 0)
            line,
      ];

  /// Save and close with the saved receipt.
  Future<void> _save() async {
    final GoodsReceiptRecord? saved = await _persist();
    if (saved == null || !mounted) return;
    Navigator.pop(context, saved);
  }

  /// Save, then complete what was saved (D-BUY-22). A refused completion
  /// leaves the window open on the saved draft with the server's sentence.
  Future<void> _saveAndStep(DocumentStep<GoodsReceiptRecord> step) =>
      saveThenStep<GoodsReceiptRecord>(
        context,
        save: _persist,
        step: step,
        onStopped: (saved, refusal) => setState(() {
          _saved = saved;
          _saving = false;
          _error = refusal == null
              ? null
              : 'Saved as draft ${saved.grnNumber}, but not completed: '
                  '$refusal';
        }),
      );

  /// Write the receipt, returning it as saved; null when the save was
  /// refused, which [_error] then says.
  Future<GoodsReceiptRecord?> _persist() async {
    final String? problem = _validation();
    if (problem != null) {
      setState(() => _error = problem);
      return null;
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
        // Sent on an edit too: the editor shows what is on file, so what it
        // holds is what to keep. A blank number is null, which clears.
        'eway_bill_number':
            _ewayBillNumber.trim().isEmpty ? null : _ewayBillNumber.trim(),
        'eway_bill_date':
            _ewayBillNumber.trim().isEmpty || _ewayBillDate.trim().isEmpty
                ? null
                : _ewayBillDate.trim(),
        // Line numbers are renumbered from one over what is actually being
        // sent, so skipping a line that did not arrive cannot leave a gap the
        // document has to explain.
        'lines': [
          for (int index = 0; index < sending.length; index++)
            {
              ...sending[index].toJson(
                ptrPts: widget.features.isEnabled('BATCH_PTR_PTS'),
              ),
              'line_number': index + 1,
            },
        ],
      };
      final GoodsReceiptRecord? current = _record;
      final GoodsReceiptRecord saved =
          current != null
              ? await widget.api.updateGoodsReceipt(
                  current.id,
                  payload,
                  expectedVersion: current.version,
                )
              : await widget.api.createGoodsReceipt(payload);
      return saved;
    } on ApiException catch (exception) {
      if (!mounted) return null;
      setState(() {
        _error = refusalMessage(exception);
        _saving = false;
      });
      return null;
    }
  }

  @override
  Widget build(BuildContext context) => Phase2Scope.of(context)
      // Phase 2: the one-screen receipt (the documents' approved layout).
      ? _phase2Page(context)
      : WorkspaceDialog(
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
            width: AppDimensions.documentPickerWidth,
            child: DropdownButtonFormField<String>(
              initialValue: _order?.id,
              // A number that is still longer than the field truncates rather
              // than overflowing; the width is sized so a seeded one does not.
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
          if (widget.features.isEnabled('VEHICLE_TRACKING'))
            _text('Vehicle Number', _vehicleNumber,
                (value) => _vehicleNumber = value, null),
          _text('E-way Bill No.', _ewayBillNumber,
              (value) => _ewayBillNumber = value, '12 digits'),
          _text('E-way Bill Date', _ewayBillDate,
              (value) => _ewayBillDate = value, 'YYYY-MM-DD'),
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
                                // Code first, as every other picker reads:
                                // the plan and the grids name warehouses by
                                // code (plan item 9.12, 2026-09-13).
                                child: Text(
                                  '${warehouse.code} - ${warehouse.name}',
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
                      // Only offered where the firm's profile enables them.
                      // The server refuses a receipt carrying one otherwise --
                      // a 403 naming the feature, on save, after the whole
                      // document has been keyed.
                      if (widget.features.isEnabled('EXPIRY_TRACKING'))
                        _lineField(
                          line.expiryRequired ? 'Expiry Date *' : 'Expiry Date',
                          line.expiryDate,
                          (value) => line.expiryDate = value,
                          width: 180,
                          hint: 'YYYY-MM-DD',
                        ),
                      if (widget.features.isEnabled('MANUFACTURING_DATE'))
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
