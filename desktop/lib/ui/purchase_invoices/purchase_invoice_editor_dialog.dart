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
import '../../models/line_tax_rule.dart';
import '../../phase2/document_page.dart';
import '../../phase2/indian_format.dart';
import '../../phase2/source_tick_dialog.dart';
import '../document_framework/document_steps.dart';
import '../workspace/custom_fields_section.dart';
import '../workspace/desktop_framework.dart';
import '../../models/document_file.dart';
import '../purchases/document_attachments_dialog.dart';
import 'supplier_irn_dialog.dart';

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
    this.returnedBeforeBilling = '',
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

  /// What went back off the receipt line before any bill reached it: the
  /// supplier bills only what the firm kept (D-BUY-26).
  final String returnedBeforeBilling;

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

  /// Blank takes the product's input credit setting (backlog 78 row 1);
  /// otherwise ELIGIBLE, BLOCKED or INELIGIBLE. Never prefilled.
  String itcEligibility = '';

  bool get billsAnOrder => sourceDocumentType == 'PURCHASE_ORDER';

  /// What the receipt (or the order) still has to be billed for.
  double get outstanding {
    final double received = double.tryParse(receivedQuantity) ?? 0;
    final double invoiced = double.tryParse(alreadyInvoiced) ?? 0;
    final double returned = double.tryParse(returnedBeforeBilling) ?? 0;
    final double left = received - invoiced - returned;
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
        if (itcEligibility.isNotEmpty) 'itc_eligibility': itcEligibility,
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

  /// Blank takes the product's input credit setting; never prefilled.
  String itcEligibility = '';

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
        if (itcEligibility.isNotEmpty) 'itc_eligibility': itcEligibility,
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
    this.steps = const [],
    this.canAttach = true,
  });

  final ApiClient api;

  /// Whether the user may add and delete files on the bill
  /// (`PURCHASE_CREATE` or `PURCHASE_UPDATE`); without it they can only look.
  final bool canAttach;

  /// The bill's next steps, as the list toolbar offers them (D-BUY-22):
  /// *Save & approve* where the user may approve. Empty offers none.
  final List<DocumentStep<Json>> steps;

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

  /// Further receipts of the same supplier and branch billed on this one
  /// paper (D-BUY-18). [_receipt] stays the primary one; every line of every
  /// receipt is in [_lines].
  List<GoodsReceiptRecord> _extraReceipts = const [];

  /// Phase 2: the supplier chosen before any receipt is ticked (SEL-1).
  String? _billVendorId;
  PurchaseOrder? _order;
  String? _vendorId;
  final List<PurchaseDirectLine> _directLines = [PurchaseDirectLine()];
  List<PurchaseInvoiceDraftLine> _lines = const [];
  String _invoiceDate = _today();
  String _supplierInvoiceNumber = '';
  String _supplierInvoiceDate = _today();

  /// The IRN printed on the supplier's e-invoice; blank is none.
  String _supplierIrn = '';
  String _remarks = '';

  /// PG-6: TCS the supplier charged on the bill (206C(1H)). Both blank is
  /// none; a typed amount wins, and a rate alone is worked out on the grand
  /// total by the server.
  String _tcsRate = '';
  String _tcsAmount = '';

  /// PG-12: the currency typed by the person, once they have touched the
  /// box. Until then the bill takes its supplier's, which the server also
  /// does when none is sent. Blank is rupees.
  String _currency = '';
  bool _currencyTouched = false;

  /// The rupees one unit of a foreign currency was worth on the bill's date.
  String _exchangeRate = '';
  bool _saving = false;
  bool _loadingLines = false;
  String? _error;

  /// The bill this window saved itself, where *Save & approve* saved it and
  /// the approval did not happen. The window then holds that draft: it
  /// cannot raise a second bill, and its steps act on the one saved.
  Json? _saved;

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

  /// The supplier the bill is for, whichever way it was chosen.
  String? get _billSupplierId =>
      _vendorId ?? _receipt?.vendorId ?? _order?.vendorId ?? _billVendorId;

  /// The currency of the supplier's account; blank is rupees.
  String get _supplierCurrency {
    for (final Vendor item in widget.vendors) {
      if (item.id == _billSupplierId) return item.currencyCode;
    }
    return '';
  }

  /// The bill's currency: what was typed, else the supplier's. Blank and INR
  /// are both rupees and read as blank here.
  String get _billCurrency {
    final String code =
        (_currencyTouched ? _currency : _supplierCurrency).trim().toUpperCase();
    return code == 'INR' ? '' : code;
  }

  bool get _foreign => _billCurrency.isNotEmpty;

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

  /// The firm's own fields on a purchase invoice (MST-6), sent only once the
  /// definitions arrived.
  late final CustomFieldsController _customFields = CustomFieldsController(
    load: () => widget.api.applicableAttributeDefinitions('PURCHASE_INVOICE'),
  );

  @override
  void initState() {
    super.initState();
    unawaited(_customFields.start());
  }

  @override
  void dispose() {
    _previewTimer?.cancel();
    _customFields.dispose();
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
      // A different primary receipt is a different bill: the receipts added
      // beside the last one do not follow it.
      _extraReceipts = const [];
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

  /// The supplier whose receipts the tick list offers: the one chosen, or
  /// the one the bill's receipts belong to.
  String? get _tickVendorId => _receipt?.vendorId ?? _billVendorId;

  /// That supplier's receipts with something left to bill (D-BUY-27).
  List<GoodsReceiptRecord> get _vendorReceipts {
    final String? vendor = _tickVendorId;
    if (vendor == null) return const [];
    return [
      for (final GoodsReceiptRecord item in widget.receipts)
        if (item.vendorId == vendor && item.hasLeftToBill) item,
    ];
  }

  /// Why [candidate] cannot share a bill with [ticked], or null where it
  /// can. The server's rule, asked before the save: one supplier and one
  /// branch (SEL-1, backlog 58 item 4).
  String? _receiptClash(
    GoodsReceiptRecord candidate,
    List<GoodsReceiptRecord> ticked,
  ) {
    for (final GoodsReceiptRecord other in ticked) {
      if (candidate.branchId != other.branchId) {
        return 'Another branch from ${other.grnNumber}: a bill covers '
            'the receipts of one branch';
      }
    }
    return null;
  }

  /// Put exactly [picked] on the bill, in that order: the first is the
  /// primary receipt. Quantities already typed on a receipt that stays are
  /// kept; a receipt coming on starts at what it still has to be billed for.
  Future<void> _setReceipts(List<GoodsReceiptRecord> picked) async {
    final Set<String> had = {
      if (_receipt != null) _receipt!.id,
      for (final GoodsReceiptRecord item in _extraReceipts) item.id,
    };
    final bool adding = picked.any((item) => !had.contains(item.id));
    Map<String, double> invoiced = const <String, double>{};
    if (adding) {
      setState(() {
        _loadingLines = true;
        _error = null;
      });
      invoiced = await _invoicedByLine();
      if (!mounted) return;
    }
    setState(() {
      final Map<String, List<PurchaseInvoiceDraftLine>> kept =
          <String, List<PurchaseInvoiceDraftLine>>{};
      for (final PurchaseInvoiceDraftLine line in _lines) {
        kept
            .putIfAbsent(line.sourceDocumentId, () => <PurchaseInvoiceDraftLine>[])
            .add(line);
      }
      final List<PurchaseInvoiceDraftLine> lines = <PurchaseInvoiceDraftLine>[];
      for (final GoodsReceiptRecord receipt in picked) {
        final List<PurchaseInvoiceDraftLine>? own = kept[receipt.id];
        if (own != null) {
          lines.addAll(own);
          continue;
        }
        for (int index = 0; index < receipt.lines.length; index++) {
          lines.add(_draftLine(
            receipt,
            receipt.lines[index],
            lines.length + 1,
            invoiced[receipt.lines[index].id] ?? 0,
          ));
        }
      }
      _receipt = picked.isEmpty ? null : picked.first;
      _extraReceipts = picked.skip(1).toList();
      _lines = lines;
      _loadingLines = false;
      _current = 0;
      // The paper usually carries the number the storeman noted.
      final GoodsReceiptRecord? first = _receipt;
      if (first != null &&
          _supplierInvoiceNumber.trim().isEmpty &&
          first.invoiceReference.isNotEmpty) {
        _supplierInvoiceNumber = first.invoiceReference;
        _supplierNumberEpoch++;
      }
    });
  }

  /// The receipt number a line belongs to, for telling apart the lines of
  /// several receipts.
  String _grnOf(String receiptId) {
    if (_receipt?.id == receiptId) return _receipt!.grnNumber;
    for (final GoodsReceiptRecord item in _extraReceipts) {
      if (item.id == receiptId) return item.grnNumber;
    }
    return '';
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
      returnedBeforeBilling: line.returnedUnbilledQuantity,
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
    for (final (String name, String value) in [
      ('TCS rate', _tcsRate),
      ('TCS amount', _tcsAmount),
    ]) {
      if (value.trim().isNotEmpty && _tcsFigure(value) == null) {
        return 'The $name must be a number of zero or more, or blank.';
      }
    }
    if ((_tcsFigure(_tcsRate) ?? 0) > 100) {
      return 'The TCS rate cannot be more than 100%.';
    }
    if (_billCurrency.isNotEmpty &&
        !RegExp(r'^[A-Z]{3}$').hasMatch(_billCurrency)) {
      return 'The currency is a three-letter code, such as USD.';
    }
    if (_foreign && (double.tryParse(_exchangeRate.trim()) ?? 0) <= 0) {
      return 'Enter the exchange rate: the rupees one $_billCurrency was '
          "worth on the supplier's invoice date.";
    }
    final String? irnProblem = supplierIrnProblem(_supplierIrn);
    if (irnProblem != null) return irnProblem;
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

  /// A TCS box's figure, or null where it is blank or not a number of zero
  /// or more.
  double? _tcsFigure(String value) {
    final double? figure = double.tryParse(value.trim());
    return figure == null || figure < 0 ? null : figure;
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
      // Blank is none. Priced while typing, half an IRN is left out rather
      // than refused: the number changes no figure.
      'supplier_irn': _supplierIrn.trim().isEmpty ||
              (pricing && supplierIrnProblem(_supplierIrn) != null)
          ? null
          : _supplierIrn.trim(),
      if (_remarks.trim().isNotEmpty) 'remarks': _remarks.trim(),
      // PG-6: sent only when typed -- blank is no TCS. Priced while typing,
      // a box that is not yet a number is left out rather than refused.
      // A bill in another currency carries no TCS: the server refuses it.
      if (!_foreign && _tcsFigure(_tcsRate) != null)
        'tcs_rate_percent': _tcsRate.trim(),
      if (!_foreign && _tcsFigure(_tcsAmount) != null)
        'tcs_amount': _tcsAmount.trim(),
      // PG-12: sent once the person has chosen a currency (blank or INR is
      // rupees); until then the server starts the bill in its supplier's.
      // The rate is sent only for a foreign bill, and only once typed.
      if (_currencyTouched) 'currency_code': _foreign ? _billCurrency : 'INR',
      if (_foreign && (double.tryParse(_exchangeRate.trim()) ?? 0) > 0)
        'exchange_rate': _exchangeRate.trim(),
      // Only once the definitions arrived, and never while merely pricing:
      // absent leaves the stored values alone.
      if (!pricing && _customFields.hasFields)
        'attributes': _customFields.payload(),
      // An order or a list of products raises its own receipt, which the
      // server records as the source; only a typed receipt is named here.
      if (_mode == PurchaseBillMode.receipt)
        'source_documents': [
          for (final GoodsReceiptRecord item in [
            _receipt!,
            ..._extraReceipts,
          ])
            {
              'source_document_type': 'GOODS_RECEIPT',
              'source_document_id': item.id,
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

  /// Save and close with the saved bill.
  Future<void> _save() async {
    final Json? saved = await _persist();
    if (saved == null || !mounted) return;
    Navigator.pop(context, saved);
  }

  /// Save, then approve what was saved (D-BUY-22). A refused approval leaves
  /// the window open on the saved draft with the server's sentence.
  Future<void> _saveAndStep(DocumentStep<Json> step) => saveThenStep<Json>(
        context,
        save: _persist,
        step: step,
        onStopped: (saved, refusal) => setState(() {
          _saved = saved;
          _saving = false;
          _error = refusal == null
              ? null
              : 'Saved as draft ${stringValue(saved['invoice_number'])}, but '
                  'not approved: $refusal';
        }),
      );

  /// Write the bill, returning it as saved; null when the save was refused,
  /// which [_error] then says.
  Future<Json?> _persist() async {
    final String? problem = _validation() ?? _customFields.validate();
    if (problem != null) {
      setState(() => _error = problem);
      return null;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final Json response = await widget.api.createPurchaseInvoice(_payload());
      final dynamic data = response['data'];
      return data is Json ? data : response;
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
                AdditionalDetailsSection(
                  controller: _customFields,
                  noun: 'purchase invoices',
                ),
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
