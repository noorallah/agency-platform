import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../models/entities.dart';
import '../../models/goods_receipt.dart';
import '../../models/product.dart';
import '../../models/purchase.dart';
import '../../models/vendor.dart';
import '../../models/document_preview.dart';
import '../../phase2/document_page.dart';
import '../../phase2/indian_format.dart';
import '../workspace/desktop_framework.dart';

part 'purchase_invoice_editor_phase2.dart';

/// One line of a supplier bill, as it is being typed.
///
/// A bill line continues a receipt line -- or, for a firm that types no
/// receipts, an order line, whose receipt the bill raises -- so lines are
/// seeded from the document being billed rather than typed. What the clerk
/// supplies is how much of it this bill covers and, where the supplier's
/// price differs from the order's, the price on the paper.
class PurchaseInvoiceDraftLine {
  PurchaseInvoiceDraftLine({
    this.sourceDocumentType = 'GOODS_RECEIPT',
    required this.sourceDocumentId,
    required this.sourceDocumentLineId,
    required this.lineNumber,
    required this.productId,
    required this.description,
    required this.receivedQuantity,
    required this.alreadyInvoiced,
    required this.receiptUnitPrice,
    required this.purchaseUomId,
    required this.taxProfileId,
    required this.warehouseId,
    required this.batchNumber,
    required this.invoiceQuantity,
    this.expiryDate = '',
    this.unitPrice = '',
    this.remarks = '',
  });

  /// `GOODS_RECEIPT`, or `PURCHASE_ORDER` for a firm whose bill receives the
  /// goods itself.
  final String sourceDocumentType;
  final String sourceDocumentId;
  final String sourceDocumentLineId;
  final int lineNumber;
  final String productId;
  final String description;
  final String receivedQuantity;
  final String alreadyInvoiced;

  /// What the receipt recorded, which is what a blank price box takes.
  final String receiptUnitPrice;
  final String purchaseUomId;
  final String taxProfileId;
  final String warehouseId;

  /// The receipt's batch and expiry, typed on the bill only where the bill
  /// raises the receipt -- nobody else will see the goods arrive.
  String batchNumber;
  String expiryDate;

  String invoiceQuantity;
  String unitPrice;
  String remarks;

  bool get billsAnOrder => sourceDocumentType == 'PURCHASE_ORDER';

  /// What the receipt (or the order) still has to be billed for.
  double get outstanding {
    final double received = double.tryParse(receivedQuantity) ?? 0;
    final double invoiced = double.tryParse(alreadyInvoiced) ?? 0;
    final double left = received - invoiced;
    return left < 0 ? 0 : left;
  }

  Json toJson() => {
        'source_document_type': sourceDocumentType,
        'source_document_id': sourceDocumentId,
        'source_document_line_id': sourceDocumentLineId,
        'line_number': lineNumber,
        // No description: the server derives it from the receipt line, and
        // PurchaseInvoiceLineWrite forbids the key -- the same refusal every
        // purchase return met before its editor stopped sending one.
        'current_invoice_quantity':
            invoiceQuantity.trim().isEmpty ? '0' : invoiceQuantity.trim(),
        // A blank price is left out rather than sent as '0'. Absent means the
        // server takes the receipt line's price; zero means the supplier
        // charged nothing, which is a different statement.
        if (unitPrice.trim().isNotEmpty) 'unit_price': unitPrice.trim(),
        // No discount either way: silence takes the rate the receipt line
        // carries, and a literal zero would refuse it.
        if (taxProfileId.isNotEmpty) 'tax_profile_id': taxProfileId,
        if (purchaseUomId.isNotEmpty) 'purchase_uom_id': purchaseUomId,
        if (purchaseUomId.isNotEmpty) 'invoice_uom_id': purchaseUomId,
        if (warehouseId.isNotEmpty) 'warehouse_id': warehouseId,
        if (batchNumber.trim().isNotEmpty) 'batch_number': batchNumber.trim(),
        if (billsAnOrder && expiryDate.trim().isNotEmpty)
          'expiry_date': expiryDate.trim(),
        if (remarks.trim().isNotEmpty) 'remarks': remarks.trim(),
      };
}

/// One product line of a bill typed directly, by a firm that types neither
/// orders nor receipts: the server raises both behind the bill.
class PurchaseDirectLine {
  String? productId;
  String quantity = '';
  String freeQuantity = '';
  String unitPrice = '';
  String discountPercent = '';
  String batchNumber = '';
  String expiryDate = '';
  String remarks = '';

  /// Bumped when a value is filled in for the user, so its box re-reads it.
  int epoch = 0;

  double get quantityValue => double.tryParse(quantity.trim()) ?? 0;

  bool get sendable => (productId ?? '').isNotEmpty && quantityValue > 0;

  Json toJson(int lineNumber) => {
        'product_id': productId,
        'line_number': lineNumber,
        'current_invoice_quantity': quantity.trim(),
        // Blank is left out, never sent as zero: silence takes the product's
        // purchase price, zero says the supplier charged nothing.
        if (unitPrice.trim().isNotEmpty) 'unit_price': unitPrice.trim(),
        if (discountPercent.trim().isNotEmpty)
          'discount_percent': discountPercent.trim(),
        if (freeQuantity.trim().isNotEmpty)
          'free_quantity': freeQuantity.trim(),
        if (batchNumber.trim().isNotEmpty) 'batch_number': batchNumber.trim(),
        if (expiryDate.trim().isNotEmpty) 'expiry_date': expiryDate.trim(),
        if (remarks.trim().isNotEmpty) 'remarks': remarks.trim(),
      };
}

/// What a bill is typed against, decided by the firm's buying stages.
enum PurchaseBillMode {
  /// The whole chain: a bill charges for a completed goods receipt.
  receipt,

  /// Orders typed, receipts not: the bill names an approved order and
  /// receives what it charges for.
  order,

  /// Neither typed: the bill names products and raises both documents.
  products,
}

/// Record the supplier's bill for goods a receipt brought in.
///
/// The twin of the purchase return editor: both pick a completed goods
/// receipt and seed their lines from it, because the server refuses a line
/// that names no receipt line. What differs is the question each line asks --
/// a return asks how much is going back, a bill asks how much of what arrived
/// this piece of paper charges for -- and the header, which here is the
/// supplier's own invoice number and date, since that is what the payment
/// will be matched to.
class PurchaseInvoiceEditorDialog extends StatefulWidget {
  const PurchaseInvoiceEditorDialog({
    super.key,
    required this.api,
    required this.receipts,
    required this.products,
    this.stages = PurchaseWorkflowSettings.wholeChain,
    this.orders = const [],
    this.vendors = const [],
  });

  final ApiClient api;

  /// Completed goods receipts, which are what can be billed.
  final List<GoodsReceiptRecord> receipts;
  final List<Product> products;

  /// Which buying stages this firm types, deciding what a bill names.
  final PurchaseWorkflowSettings stages;

  /// Approved orders still to be received, for a firm that types no
  /// receipts.
  final List<PurchaseOrder> orders;

  /// Suppliers, for a bill typed directly.
  final List<Vendor> vendors;

  @override
  State<PurchaseInvoiceEditorDialog> createState() =>
      _PurchaseInvoiceEditorDialogState();
}

class _PurchaseInvoiceEditorDialogState
    extends State<PurchaseInvoiceEditorDialog> {
  GoodsReceiptRecord? _receipt;
  PurchaseOrder? _order;
  String? _vendorId;
  final List<PurchaseDirectLine> _directLines = [PurchaseDirectLine()];
  List<PurchaseInvoiceDraftLine> _lines = const [];
  String _invoiceDate = _today();
  String _supplierInvoiceNumber = '';
  String _supplierInvoiceDate = _today();
  String _remarks = '';
  bool _saving = false;
  bool _loadingLines = false;
  String? _error;

  /// Phase 2: the bill as the server priced it last, and the line the side
  /// panel follows.
  PurchaseInvoicePreviewRecord? _preview;
  int _current = 0;
  Timer? _previewTimer;
  int _previewSerial = 0;
  bool _phase2 = false;

  /// Bumped when the supplier's number is filled in for the user, so its
  /// box re-reads it.
  int _supplierNumberEpoch = 0;

  void _setState(VoidCallback change) => setState(change);

  /// Receipts on is the whole chain; the server refuses receipts on with
  /// orders off, so the two switches name exactly three modes.
  PurchaseBillMode get _mode => widget.stages.goodsReceiptStage
      ? PurchaseBillMode.receipt
      : widget.stages.purchaseOrderStage
          ? PurchaseBillMode.order
          : PurchaseBillMode.products;

  bool get _direct => _mode == PurchaseBillMode.products;

  /// Whether the document being billed -- or, typed directly, the supplier
  /// -- has been chosen.
  bool get _hasSource => switch (_mode) {
        PurchaseBillMode.receipt => _receipt != null,
        PurchaseBillMode.order => _order != null,
        PurchaseBillMode.products => _vendorId != null,
      };

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _phase2 = Phase2Scope.of(context);
  }

  @override
  void dispose() {
    _previewTimer?.cancel();
    super.dispose();
  }

  /// Price the bill again once the typing pauses; only the latest answer
  /// lands. A bill with no receipt or nothing being billed is not sent.
  void _schedulePreview() {
    if (!_phase2) return;
    _previewTimer?.cancel();
    _previewTimer = Timer(const Duration(milliseconds: 350), () async {
      if (!_hasSource || !_hasSomethingToBill) return;
      final int serial = ++_previewSerial;
      try {
        final PurchaseInvoicePreviewRecord priced =
            await widget.api.previewPurchaseInvoice(_payload(pricing: true));
        if (!mounted || serial != _previewSerial) return;
        setState(() => _preview = priced);
      } on ApiException {
        // A bill the server refuses as it stands keeps the last figures;
        // saving it says why.
      }
    });
  }

  static String _today() => DateTime.now().toIso8601String().split('T').first;

  String _productLabel(String productId) {
    for (final Product product in widget.products) {
      if (product.id == productId) return '${product.code} — ${product.name}';
    }
    return productId;
  }

  Future<void> _selectReceipt(GoodsReceiptRecord receipt) async {
    setState(() {
      _receipt = receipt;
      _loadingLines = true;
      _error = null;
    });
    final Map<String, double> invoiced = await _invoicedByLine();
    if (!mounted) return;
    setState(() {
      _lines = [
        for (int index = 0; index < receipt.lines.length; index++)
          _draftLine(
            receipt,
            receipt.lines[index],
            index + 1,
            invoiced[receipt.lines[index].id] ?? 0,
          ),
      ];
      _loadingLines = false;
    });
  }

  /// Seed the lines from an approved order, at what is still to arrive.
  ///
  /// What has arrived is summed from the completed receipts against each
  /// order line; the server refuses a bill past the order either way.
  void _selectOrder(PurchaseOrder order) {
    final Map<String, double> received = <String, double>{};
    for (final GoodsReceiptRecord receipt in widget.receipts) {
      if (receipt.purchaseOrderId != order.id) continue;
      for (final GoodsReceiptLine line in receipt.lines) {
        received[line.purchaseOrderLineId] =
            (received[line.purchaseOrderLineId] ?? 0) +
                (double.tryParse(line.acceptedQuantity) ?? 0);
      }
    }
    setState(() {
      _order = order;
      _error = null;
      _lines = [
        for (int index = 0; index < order.lines.length; index++)
          _orderLine(
            order,
            order.lines[index],
            index + 1,
            received[order.lines[index].id] ?? 0,
          ),
      ];
    });
  }

  PurchaseInvoiceDraftLine _orderLine(
    PurchaseOrder order,
    PurchaseOrderLine line,
    int lineNumber,
    double received,
  ) {
    final PurchaseInvoiceDraftLine draft = PurchaseInvoiceDraftLine(
      sourceDocumentType: 'PURCHASE_ORDER',
      sourceDocumentId: order.id,
      sourceDocumentLineId: line.id,
      lineNumber: lineNumber,
      productId: line.productId,
      description: line.description,
      receivedQuantity: line.orderedQuantity,
      alreadyInvoiced: _trim(received),
      receiptUnitPrice: line.unitPrice,
      purchaseUomId: line.purchaseUomId,
      taxProfileId: line.taxProfileId,
      warehouseId: line.warehouseId,
      batchNumber: '',
      expiryDate: line.expiryDate,
      invoiceQuantity: '0',
    );
    draft.invoiceQuantity = _trim(draft.outstanding);
    return draft;
  }

  /// Sum what live bills already charge against each receipt line.
  ///
  /// The server enforces this too -- a bill past the received quantity is
  /// refused -- but it decides after the whole document is typed. Defaulting
  /// to what is left means the common case never meets that refusal. A
  /// cancelled bill charges nothing, so it is not counted.
  Future<Map<String, double>> _invoicedByLine() async {
    final Map<String, double> invoiced = <String, double>{};
    try {
      final List<Json> rows = await fetchAllPages<Json>((page) async {
        final Json response = await widget.api.documentPage(
          'purchase-invoices',
          page: page,
          pageSize: 100,
        );
        final dynamic data = response['data'];
        final List<Json> items = [
          for (final dynamic row in data is List ? data : const [])
            if (row is Map) Map<String, dynamic>.from(row),
        ];
        return PagedResult<Json>(
          items: items,
          total: pagedTotal(response, fallback: items.length),
        );
      });
      for (final Json row in rows) {
        if (stringValue(row['status']).trim().toUpperCase() == 'CANCELLED') {
          continue;
        }
        for (final dynamic line
            in (row['lines'] as List<dynamic>? ?? const [])) {
          if (line is! Map) continue;
          final String id = stringValue(line['source_document_line_id']);
          if (id.isEmpty) continue;
          invoiced[id] = (invoiced[id] ?? 0) +
              (double.tryParse(stringValue(line['current_invoice_quantity'])) ??
                  0);
        }
      }
    } on ApiException catch (exception) {
      _error = 'Could not read earlier bills: ${exception.message}. '
          'Quantities default to the full receipt.';
    }
    return invoiced;
  }

  PurchaseInvoiceDraftLine _draftLine(
    GoodsReceiptRecord receipt,
    GoodsReceiptLine line,
    int lineNumber,
    double alreadyInvoiced,
  ) {
    final PurchaseInvoiceDraftLine draft = PurchaseInvoiceDraftLine(
      sourceDocumentId: receipt.id,
      sourceDocumentLineId: line.id,
      lineNumber: lineNumber,
      productId: line.productId,
      description: line.description,
      receivedQuantity: line.acceptedQuantity,
      alreadyInvoiced: _trim(alreadyInvoiced),
      receiptUnitPrice: line.unitPrice,
      purchaseUomId: line.purchaseUomId,
      taxProfileId: line.taxProfileId,
      warehouseId: line.warehouseId,
      batchNumber: line.batchNumber,
      invoiceQuantity: '0',
    );
    draft.invoiceQuantity = _trim(draft.outstanding);
    return draft;
  }

  static String _trim(double value) =>
      value == value.roundToDouble() ? value.toStringAsFixed(0) : '$value';

  List<PurchaseInvoiceDraftLine> _sendableLines() => [
        for (final PurchaseInvoiceDraftLine line in _lines)
          if ((double.tryParse(line.invoiceQuantity) ?? 0) > 0) line,
      ];

  List<PurchaseDirectLine> _sendableDirect() => [
        for (final PurchaseDirectLine line in _directLines)
          if (line.sendable) line,
      ];

  bool get _hasSomethingToBill =>
      _direct ? _sendableDirect().isNotEmpty : _sendableLines().isNotEmpty;

  String? _validation() {
    if (!_hasSource) {
      return switch (_mode) {
        PurchaseBillMode.receipt => 'Choose the goods receipt being billed.',
        PurchaseBillMode.order => 'Choose the purchase order being billed.',
        PurchaseBillMode.products => 'Choose the supplier.',
      };
    }
    if (_supplierInvoiceNumber.trim().isEmpty) {
      return "Enter the supplier's invoice number.";
    }
    if (_supplierInvoiceDate.trim().isEmpty) {
      return "Enter the supplier's invoice date.";
    }
    if (_invoiceDate.trim().isEmpty) return 'Enter the invoice date.';
    if (_direct) return _directValidation();
    final List<PurchaseInvoiceDraftLine> sending = _sendableLines();
    if (sending.isEmpty) {
      return 'Enter a quantity on at least one line.';
    }
    for (final PurchaseInvoiceDraftLine line in sending) {
      final double billing = double.tryParse(line.invoiceQuantity) ?? 0;
      if (billing > line.outstanding) {
        return 'Line ${line.lineNumber}: quantity exceeds what the '
            '${line.billsAnOrder ? 'order still has to receive' : 'receipt still has to be billed for'}'
            ' (${_trim(line.outstanding)}).';
      }
      final String price = line.unitPrice.trim();
      if (price.isNotEmpty && (double.tryParse(price) ?? -1) < 0) {
        return 'Line ${line.lineNumber}: the unit price must be a number of '
            'zero or more, or blank to take the receipt price.';
      }
    }
    return null;
  }

  String? _directValidation() {
    if (_sendableDirect().isEmpty) return 'Add a product with a quantity.';
    for (int index = 0; index < _directLines.length; index++) {
      final PurchaseDirectLine line = _directLines[index];
      if (!line.sendable) continue;
      for (final (String name, String value) in [
        ('rate', line.unitPrice),
        ('free quantity', line.freeQuantity),
        ('discount', line.discountPercent),
      ]) {
        if (value.trim().isNotEmpty &&
            (double.tryParse(value.trim()) ?? -1) < 0) {
          return 'Line ${index + 1}: the $name must be a number of zero or '
              'more, or blank.';
        }
      }
      if ((double.tryParse(line.discountPercent.trim()) ?? 0) > 100) {
        return 'Line ${index + 1}: a discount cannot be more than 100%.';
      }
      final Product? product = _productById(line.productId);
      if (product != null &&
          product.trackBatch &&
          line.batchNumber.trim().isEmpty) {
        return 'Line ${index + 1}: ${product.name} is tracked by batch; '
            'enter the batch number from the bill.';
      }
      if (product != null &&
          product.trackExpiry &&
          line.expiryDate.trim().isEmpty) {
        return 'Line ${index + 1}: ${product.name} is tracked by expiry; '
            'enter the expiry date from the bill.';
      }
    }
    return null;
  }

  Product? _productById(String? id) {
    for (final Product item in widget.products) {
      if (item.id == id) return item;
    }
    return null;
  }

  /// The bill as the server is sent it. Priced before the supplier's number
  /// is typed, a placeholder stands in: the number changes no figure.
  Json _payload({bool pricing = false}) {
    final List<PurchaseInvoiceDraftLine> sending = _sendableLines();
    final String supplierNumber = _supplierInvoiceNumber.trim();
    final List<PurchaseDirectLine> direct = _sendableDirect();
    // No vendor or branch for a receipt or an order: the server takes both
    // from the document, and a copy sent from here is one more thing that can
    // disagree with it. A bill of products names its supplier; its branch is
    // the firm's default, as the stage settings say.
    return {
      if (_direct) 'vendor_id': _vendorId,
      'invoice_date': _invoiceDate.trim(),
      'supplier_invoice_number':
          pricing && supplierNumber.isEmpty ? '-' : supplierNumber,
      'supplier_invoice_date': _supplierInvoiceDate.trim(),
      if (_remarks.trim().isNotEmpty) 'remarks': _remarks.trim(),
      // An order or a list of products raises its own receipt, which the
      // server records as the source; only a typed receipt is named here.
      if (_mode == PurchaseBillMode.receipt)
        'source_documents': [
          {
            'source_document_type': 'GOODS_RECEIPT',
            'source_document_id': _receipt!.id,
          }
        ],
      'lines': [
        if (_direct)
          for (int index = 0; index < direct.length; index++)
            direct[index].toJson(index + 1)
        else
          for (int index = 0; index < sending.length; index++)
            {...sending[index].toJson(), 'line_number': index + 1},
      ],
    };
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
      final Json response = await widget.api.createPurchaseInvoice(_payload());
      if (!mounted) return;
      final dynamic data = response['data'];
      Navigator.pop(context, data is Json ? data : response);
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() {
        _error = refusalMessage(exception);
        _saving = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) => Phase2Scope.of(context)
      // Phase 2: the one-screen bill (the documents' approved layout).
      ? _phase2Page(context)
      : WorkspaceDialog(
          title: 'New Purchase Invoice',
          subtitle: _receipt == null
              ? 'Choose the goods receipt being billed'
              : 'Against ${_receipt!.grnNumber}',
          icon: Icons.request_quote_outlined,
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
                  label: const Text('Save Invoice'),
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
                  title: 'Supplier Bill',
                  description:
                      'Which delivery is being billed, and what the supplier '
                      'wrote on the bill.',
                ),
                const SizedBox(height: AppSpacing.md),
                _headerFields(),
                const SizedBox(height: AppSpacing.xl),
                SectionHeader(
                  title: 'Items Billed',
                  description: _receipt == null
                      ? 'Lines appear once a goods receipt is chosen.'
                      : 'Lines come from the receipt, at what it still has to '
                          'be billed for. A blank price takes the receipt '
                          'price; type one only where the bill differs.',
                ),
                const SizedBox(height: AppSpacing.md),
                if (_receipt == null)
                  const StandardEmptyState(
                    type: EmptyStateType.noRecords,
                    title: 'No goods receipt chosen',
                    message: 'A bill charges for what a receipt brought in, so '
                        'pick the receipt above.',
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
              initialValue: _receipt?.id,
              isExpanded: true,
              decoration: const InputDecoration(
                labelText: 'Goods Receipt *',
                helperText: 'Completed receipts only',
              ),
              items: [
                for (final GoodsReceiptRecord receipt in widget.receipts)
                  DropdownMenuItem<String>(
                    value: receipt.id,
                    child: Text(
                      '${receipt.grnNumber} • ${receipt.receiptDate}',
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
              ],
              onChanged: _saving
                  ? null
                  : (value) {
                      final Iterable<GoodsReceiptRecord> match =
                          widget.receipts.where((row) => row.id == value);
                      if (match.isNotEmpty) _selectReceipt(match.first);
                    },
            ),
          ),
          _text(
              'Supplier Invoice Number *',
              _supplierInvoiceNumber,
              (value) => _supplierInvoiceNumber = value,
              'As printed on the bill'),
          _text('Supplier Invoice Date *', _supplierInvoiceDate,
              (value) => _supplierInvoiceDate = value, 'YYYY-MM-DD'),
          _text('Invoice Date *', _invoiceDate, (value) => _invoiceDate = value,
              'YYYY-MM-DD'),
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
        for (final PurchaseInvoiceDraftLine line in _lines) ...[
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
                        'Received ${line.receivedQuantity} · already billed '
                        '${line.alreadyInvoiced}',
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
                        'Billing *',
                        line.invoiceQuantity,
                        (value) => line.invoiceQuantity = value,
                        width: 130,
                      ),
                      _lineField(
                        'Unit Price',
                        line.unitPrice,
                        (value) => line.unitPrice = value,
                        width: 180,
                        helper: line.receiptUnitPrice.isEmpty
                            ? 'Blank takes the receipt price'
                            : 'Blank takes ${line.receiptUnitPrice}',
                      ),
                      _lineField(
                        'Remarks',
                        line.remarks,
                        (value) => line.remarks = value,
                        width: 240,
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
    String? helper,
  }) =>
      SizedBox(
        width: width,
        child: TextFormField(
          initialValue: value,
          decoration: InputDecoration(labelText: label, helperText: helper),
          onChanged: (next) => setState(() => onChanged(next)),
        ),
      );
}
