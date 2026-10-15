import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../models/entities.dart';
import '../../models/fixed_asset.dart';
import '../../models/goods_receipt.dart';
import '../../models/product.dart';
import '../../models/purchase.dart';
import '../../models/vendor.dart';
import '../../models/document_preview.dart';
import '../../models/line_tax_rule.dart';
import '../../phase2/document_page.dart';
import '../vendors/vendor_management_page.dart' show addSupplierInPlace;
import '../../phase2/indian_format.dart';
import '../../phase2/source_tick_dialog.dart';
import '../document_framework/document_steps.dart';
import '../workspace/custom_fields_section.dart';
import '../workspace/box_piece_cells.dart';
import '../workspace/desktop_framework.dart';
import '../../models/document_file.dart';
import '../purchases/document_attachments_dialog.dart';
import '../workspace/party_place.dart';
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
    this.packSize = '',
  });

  /// L5: the pack the line it bills is held at, where that line is counted
  /// in the stock unit; '' otherwise, and then it is billed in its own unit.
  final String packSize;

  /// L5: the Box and Pcs cells of Billing, used while the bill is typed in
  /// boxes and pieces; [invoiceQuantity] stays the figure sent, in pieces.
  /// [boxStamp] is what they were last filled for.
  final BoxPieceEntry boxes = BoxPieceEntry();
  String boxStamp = '';

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

  /// PG-13: a capital-goods line raises a fixed asset when the bill is
  /// approved. Both keys are sent only when ticked.
  bool capitalGoods = false;
  String assetClassId = '';

  /// D-BUY-40: the receipt line was received as capital goods, so this line
  /// is capital goods and the tick cannot be cleared; the server refuses a
  /// bill that says otherwise.
  bool capitalFromReceipt = false;

  bool get billsAnOrder => sourceDocumentType == 'PURCHASE_ORDER';

  /// D-UI-39: what the saved bill line holds that this screen has no box
  /// for -- a charge on the line, a discount somebody typed, an expiry --
  /// sent back as held, because the server replaces the line with what it
  /// is sent and an edit of the quantity would otherwise wipe them. Every
  /// key is one `PurchaseInvoiceLineWrite` declares.
  Json echo = const {};

  /// D-UI-39: the line as the bill being edited holds it, and what the
  /// boxes read when it was opened. While the two agree the line's figures
  /// are the server's own, as saved.
  Json? saved;
  String savedAs = '';

  String get typedAs => '${invoiceQuantity.trim()}|${unitPrice.trim()}';

  /// Whether the line differs from the bill as saved: retyped, or added.
  bool get changedSinceSaved => saved == null
      ? (double.tryParse(invoiceQuantity) ?? 0) > 0
      : typedAs != savedAs;

  /// What the receipt (or the order) still has to be billed for.
  double get outstanding {
    final double received = double.tryParse(receivedQuantity) ?? 0;
    final double invoiced = double.tryParse(alreadyInvoiced) ?? 0;
    final double returned = double.tryParse(returnedBeforeBilling) ?? 0;
    final double left = received - invoiced - returned;
    return left < 0 ? 0 : left;
  }

  /// [boxes] is a bill typed as boxes and pieces (L5): a line with a pack
  /// then names the pack its cells were added up at.
  Json toJson({bool boxes = false}) => {
        // First, so anything typed below replaces what the bill held.
        ...echo,
        'source_document_type': sourceDocumentType,
        'source_document_id': sourceDocumentId,
        'source_document_line_id': sourceDocumentLineId,
        'line_number': lineNumber,
        // No description: the server derives it from the receipt line, and
        // PurchaseInvoiceLineWrite forbids the key -- the same refusal every
        // purchase return met before its editor stopped sending one.
        'current_invoice_quantity':
            invoiceQuantity.trim().isEmpty ? '0' : invoiceQuantity.trim(),
        if (boxes && packOf(packSize) != null) 'pack_size': packSize,
        // A blank price is left out rather than sent as '0'. Absent means the
        // server takes the receipt line's price; zero means the supplier
        // charged nothing, which is a different statement.
        if (unitPrice.trim().isNotEmpty) 'unit_price': unitPrice.trim(),
        // No discount either way: silence takes the rate the receipt line
        // carries, and a literal zero would refuse it.
        if (taxProfileId.isNotEmpty) 'tax_profile_id': taxProfileId,
        if (itcEligibility.isNotEmpty) 'itc_eligibility': itcEligibility,
        if (capitalGoods) 'is_capital_goods': true,
        if (capitalGoods) 'asset_class_id': assetClassId,
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

  /// PG-13: ticked, the line raises a fixed asset of the chosen class.
  bool capitalGoods = false;
  String assetClassId = '';

  /// Bumped when a value is filled in for the user, so its box re-reads it.
  int epoch = 0;

  /// L5: the pack the saved line was written at; dropped when the product
  /// changes, and then the item's buying pack is the line's.
  String heldPack = '';

  /// L5: the four cells, used while the bill is typed in boxes and pieces;
  /// [quantity] and [freeQuantity] stay the figures sent, in pieces.
  final BoxPieceEntry boxes = BoxPieceEntry();
  String boxStamp = '';

  double get quantityValue => double.tryParse(quantity.trim()) ?? 0;

  bool get sendable => (productId ?? '').isNotEmpty && quantityValue > 0;

  /// D-UI-39: what the saved bill line holds that this screen has no box
  /// for, sent back as held; and the line as saved, with what the boxes
  /// read when it was opened (see [PurchaseInvoiceDraftLine.echo]).
  Json echo = const {};
  Json? saved;
  String savedAs = '';

  String get typedAs => '${productId ?? ''}|${quantity.trim()}|'
      '${freeQuantity.trim()}|${unitPrice.trim()}|${discountPercent.trim()}';

  bool get changedSinceSaved =>
      saved == null ? sendable : typedAs != savedAs;

  /// [packSize] is the pack the cells were added up at, on a line typed as
  /// boxes and pieces (L5); '' otherwise.
  Json toJson(int lineNumber, {String packSize = ''}) => {
        for (final MapEntry<String, dynamic> held in echo.entries)
          // A discount typed in the box replaces an amount the bill held:
          // sent beside it, the amount would win.
          if (held.key != 'discount_amount' || discountPercent.trim().isEmpty)
            held.key: held.value,
        'product_id': productId,
        'line_number': lineNumber,
        'current_invoice_quantity': quantity.trim(),
        if (packSize.isNotEmpty) 'pack_size': packSize,
        // Blank is left out, never sent as zero: silence takes the product's
        // purchase price, zero says the supplier charged nothing.
        if (unitPrice.trim().isNotEmpty) 'unit_price': unitPrice.trim(),
        if (discountPercent.trim().isNotEmpty)
          'discount_percent': discountPercent.trim(),
        if (itcEligibility.isNotEmpty) 'itc_eligibility': itcEligibility,
        if (capitalGoods) 'is_capital_goods': true,
        if (capitalGoods) 'asset_class_id': assetClassId,
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
    this.canAddVendor = false,
    this.onVendorAdded,
    this.existing,
  });

  /// D-UI-39: the Draft bill being edited, as `GET /purchase-invoices/{id}`
  /// answered it; null raises a new one. A Draft had no Edit, so a wrong
  /// quantity could only be put right by cancelling the bill and typing it
  /// again. The window opens holding the draft and saves it with a `PUT`
  /// carrying the version read here.
  final Json? existing;

  /// Whether **New supplier** is offered beside the supplier box of a bill
  /// typed directly (backlog 128): the user holds `VENDOR_CREATE`.
  final bool canAddVendor;

  /// Told of a supplier added from this bill, so the list behind it knows
  /// the name too.
  final ValueChanged<Vendor>? onVendorAdded;

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
  /// box. Until then the bill takes its order's, or its supplier's where it
  /// names no order, which the server also does when none is sent. Blank is
  /// rupees.
  String _currency = '';
  bool _currencyTouched = false;

  /// The rupees one unit of a foreign currency was worth on the bill's date,
  /// once typed. Until the box is touched the bill takes its order's rate.
  String _exchangeRate = '';
  bool _rateTouched = false;
  bool _saving = false;
  bool _loadingLines = false;
  String? _error;

  /// The bill this window saved itself, where *Save & approve* saved it and
  /// the approval did not happen. The window then holds that draft: it
  /// cannot raise a second bill, and its steps act on the one saved.
  Json? _saved;

  // ---- editing a Draft (D-UI-39) ------------------------------------------

  bool get _editing => widget.existing != null;

  /// One field of the bill being edited, as text; blank when it holds none.
  String _held(String key) => stringValue(widget.existing?[key]).trim();

  static double _amountOf(Object? value) =>
      double.tryParse(stringValue(value).trim()) ?? 0;

  /// A stored figure without the store's trailing zeros, as a box shows it.
  static String _plain(Object? value) =>
      documentQuantity(stringValue(value).trim());

  /// What the bill being edited is typed against, decided from the bill
  /// itself once the receipts it names were read -- never from the firm's
  /// stages alone, which may have changed since the bill was raised.
  PurchaseBillMode? _editMode;

  /// The bill raised the receipt its lines name, against an order somebody
  /// typed. The server keeps that receipt as it is on an edit, so the
  /// quantities and batches it holds cannot be changed from the bill.
  bool _ownReceipt = false;
  String _ownOrderNumber = '';

  /// The bill's receipts are still being read.
  bool _loadingEdit = false;

  /// Why this draft cannot be edited from here, said in place of its lines.
  String? _editBlock;

  /// The receipts on the bill being edited, which the list behind the
  /// window may not hold: one the bill raised itself is a draft.
  List<GoodsReceiptRecord> _editReceipts = const [];

  /// [_preview] holds the bill as saved, not a pricing of what is typed.
  bool _savedFigures = false;
  bool? _savedInterstate;
  int _savedLineCount = 0;
  bool _tcsTouched = false;

  bool get _editHeld => _loadingEdit || _editBlock != null;

  /// The currency the bill was saved in; blank is rupees.
  String get _savedCurrency {
    final String code = _held('currency_code').toUpperCase();
    return code == 'INR' ? '' : code;
  }

  bool get _hadTcs =>
      _held('tcs_rate_percent').isNotEmpty ||
      _amountOf(widget.existing?['tcs_amount']) > 0;

  /// Whether something that decides the whole bill's figures was changed.
  bool get _headerChangedSinceSaved =>
      _invoiceDate.trim() != _held('invoice_date') ||
      _tcsTouched ||
      _currencyTouched ||
      _rateTouched;

  bool get _changedSinceSaved {
    if (_headerChangedSinceSaved) return true;
    if (_direct) {
      return _directLines.where((line) => line.saved != null).length !=
              _savedLineCount ||
          _directLines.any((line) => line.changedSinceSaved);
    }
    return _lines.where((line) => line.saved != null).length !=
            _savedLineCount ||
        _lines.any((line) => line.changedSinceSaved);
  }

  /// A bill of receipts cannot be priced again while it is edited: the
  /// preview prices a new bill, which would count this draft's own quantity
  /// as billed by another and refuse it. So a changed bill says its tax and
  /// total follow on saving rather than showing figures nobody worked out.
  bool get _figuresOwed => _editing && !_direct && _changedSinceSaved;

  /// How the tax splits: the server's answer for what is typed, or what the
  /// saved bill's own tax lines say. Null when neither says.
  bool? get _interstate =>
      _savedFigures ? _savedInterstate : _preview?.interstate;

  /// Fill the header from the bill being edited. Its own dates, not today.
  void _holdHeader() {
    _invoiceDate = _held('invoice_date');
    _supplierInvoiceNumber = _held('supplier_invoice_number');
    _supplierInvoiceDate = _held('supplier_invoice_date');
    _supplierIrn = _held('supplier_irn');
    _remarks = _held('remarks');
    _tcsRate = _plain(_held('tcs_rate_percent'));
    // The amount is in its box only where somebody typed it. One the rate
    // gave is left blank, as it was typed, so it follows a new total.
    final double amount = _amountOf(_held('tcs_amount'));
    final double worked =
        _amountOf(_held('grand_total')) * _amountOf(_tcsRate) / 100;
    _tcsAmount =
        amount > 0 && (_tcsRate.isEmpty || (amount - worked).abs() > 0.005)
            ? _plain(_held('tcs_amount'))
            : '';
  }

  /// Read what the bill being edited charges for and fill its lines.
  ///
  /// The mode comes from the bill. A receipt it names that is still a draft
  /// can only be one the bill raised itself -- the server lets nobody else
  /// bill a draft receipt -- so the firm typed either products or an order.
  /// Which of the two the server does not publish, so the order is read: one
  /// the bill raised carries the supplier's invoice number as its reference
  /// and the bill's date as its own. Only then, and only while the firm
  /// still types neither stage, are the lines sent again as products, which
  /// is what makes the server withdraw that order and receipt and raise
  /// them again.
  Future<void> _loadEditing() async {
    final Json bill = widget.existing!;
    final List<Json> held = [
      for (final dynamic raw in bill['lines'] as List? ?? const [])
        if (raw is Map) Map<String, dynamic>.from(raw),
    ]..sort((a, b) => ((a['line_number'] as num?) ?? 0)
        .compareTo((b['line_number'] as num?) ?? 0));
    String? block;
    PurchaseBillMode mode = PurchaseBillMode.receipt;
    bool own = false;
    final List<GoodsReceiptRecord> receipts = <GoodsReceiptRecord>[];
    Map<String, double> invoiced = const <String, double>{};
    try {
      final List<String> ids = <String>[];
      for (final dynamic raw in [
        ...bill['sources'] as List? ?? const [],
        ...held,
      ]) {
        if (raw is! Map) continue;
        final String id = stringValue(raw['source_document_id']);
        if (stringValue(raw['source_document_type']) == 'GOODS_RECEIPT' &&
            id.isNotEmpty &&
            !ids.contains(id)) {
          ids.add(id);
        }
      }
      for (final String id in ids) {
        GoodsReceiptRecord? known;
        for (final GoodsReceiptRecord item in widget.receipts) {
          if (item.id == id) known = item;
        }
        receipts.add(known ?? await widget.api.goodsReceipt(id));
      }
      if (receipts.isEmpty) {
        block = '${_held('invoice_number')} names no goods receipt, so it '
            'cannot be changed from this screen. Cancel it and enter the '
            'bill again.';
      } else if (held
          .any((line) => stringValue(line['entered_quantity']).isNotEmpty)) {
        // The row keeps the quantity in the receipt's unit and the price of
        // one of it; what was typed cannot be put back in the boxes exactly.
        block = '${_held('invoice_number')} has a line typed in another '
            "unit than its goods receipt's, which this screen cannot show "
            'yet. Cancel it and enter the bill again to change it.';
      } else {
        own = receipts.any((item) => item.status == 'DRAFT');
        if (!own) {
          invoiced = await _invoicedByLine();
        } else if (!widget.stages.goodsReceiptStage &&
            !widget.stages.purchaseOrderStage &&
            receipts.length == 1 &&
            await _orderIsTheBills(receipts.first)) {
          mode = PurchaseBillMode.products;
        }
      }
    } on ApiException catch (exception) {
      block = 'Could not read what ${_held('invoice_number')} bills: '
          '${refusalMessage(exception)} Close this window and open the bill '
          'again.';
    }
    if (!mounted) return;
    setState(() {
      _loadingEdit = false;
      _editBlock = block;
      _editMode = mode;
      _editReceipts = receipts;
      if (block != null) return;
      _ownReceipt = own && mode == PurchaseBillMode.receipt;
      _ownOrderNumber = own ? receipts.first.purchaseOrderNumber : '';
      _savedLineCount = held.length;
      if (mode == PurchaseBillMode.products) {
        _vendorId = _held('vendor_id');
        final Map<String, GoodsReceiptLine> raised = {
          for (final GoodsReceiptLine line in receipts.first.lines)
            line.id: line,
        };
        _directLines
          ..clear()
          ..addAll([
            for (final Json line in held)
              _heldDirectLine(
                line,
                raised[stringValue(line['source_document_line_id'])],
              ),
          ]);
        if (_directLines.isEmpty) _directLines.add(PurchaseDirectLine());
      } else {
        _billVendorId = receipts.first.vendorId;
        _receipt = receipts.first;
        _extraReceipts = receipts.skip(1).toList();
        _lines = _heldLines(held, receipts, invoiced);
      }
      // Until something is changed the figures shown are the bill's own,
      // as the server saved them.
      _preview = PurchaseInvoicePreviewRecord(
        invoice: Map<String, dynamic>.from(bill),
        interstate: false,
        lines: const [],
      );
      _savedFigures = true;
      _savedInterstate = _heldInterstate(held);
    });
  }

  /// Whether the order behind a receipt the bill raised was raised by the
  /// bill too: a bill of products. An order that cannot be read is taken as
  /// somebody's own, which is the reading that withdraws nothing.
  Future<bool> _orderIsTheBills(GoodsReceiptRecord receipt) async {
    if (receipt.purchaseOrderId.isEmpty) return false;
    try {
      final PurchaseOrder order =
          await widget.api.purchaseOrder(receipt.purchaseOrderId);
      return order.referenceNumber.trim() ==
              _held('supplier_invoice_number') &&
          order.purchaseDate.trim() == _held('invoice_date');
    } on ApiException {
      return false;
    }
  }

  /// IGST or CGST and SGST, read off the tax lines the bill kept; null
  /// where their codes name neither.
  bool? _heldInterstate(List<Json> held) {
    for (final Json line in held) {
      for (final dynamic tax in line['taxes'] as List? ?? const []) {
        if (tax is! Map) continue;
        final String code =
            '${tax['component_code']} ${tax['component_label']}'.toUpperCase();
        if (code.contains('IGST')) return true;
        if (code.contains('CGST') || code.contains('SGST')) return false;
      }
    }
    return null;
  }

  /// What a saved line holds that neither kind of line has a box for.
  Json _heldLineExtras(Json was) => {
        if (_amountOf(was['charges_amount']) > 0)
          'charges_amount': stringValue(was['charges_amount']),
        for (final String key in const [
          'packaging_type_id',
          'storage_node_id',
          'manufacturing_date',
        ])
          if (stringValue(was[key]).isNotEmpty) key: stringValue(was[key]),
      };

  /// The input credit choice somebody made on a saved line, or blank.
  ///
  /// The row keeps what was resolved, not who decided it. Where it is what
  /// the product itself says and no tax rule decided the line, the box
  /// stays on *From product*: leaving it there resolves to the same answer.
  /// Anywhere else it is sent back as held, which is the reading under
  /// which saving an unchanged bill changes nothing.
  String _typedItc(Json was) {
    final String held = stringValue(was['itc_eligibility']);
    if (!const ['ELIGIBLE', 'BLOCKED', 'INELIGIBLE'].contains(held)) return '';
    final Product? product = _productById(stringValue(was['product_id']));
    if (product != null &&
        product.itcEligibility == held &&
        stringValue(was['tax_rule_code']).isEmpty) {
      return '';
    }
    return held;
  }

  /// The discount key to send back for a saved line that bills a receipt
  /// line, or nothing.
  ///
  /// The screen has no discount box here and a new bill sends none, so the
  /// receipt line's arrangement carries over; sending one back would turn
  /// that arrangement into an override. Nothing is sent where the saved
  /// discount is what the receipt line gives -- its rate on this line's
  /// worth, or its amount by the share billed. Only a discount that is
  /// neither, typed through another route, is sent back as held.
  Json _typedDiscount(Json was, GoodsReceiptLine source) {
    final double amount = _amountOf(was['discount_amount']);
    final double percent = _amountOf(was['discount_percent']);
    final double gross = _amountOf(was['gross_amount']);
    final double sourceRate = _amountOf(source.discountPercent);
    final double sourceAmount = _amountOf(source.discountAmount);
    final double sourceGross = _amountOf(source.grossAmount);
    final bool byRate = sourceAmount <= 0 ||
        (sourceRate > 0 &&
            (sourceGross * sourceRate / 100 - sourceAmount).abs() < 0.00006);
    final double whole = _amountOf(source.acceptedQuantity);
    final double share = whole > 0
        ? sourceAmount * _amountOf(was['current_invoice_quantity']) / whole
        : 0;
    final double inherited =
        byRate ? gross * sourceRate / 100 : (share > gross ? gross : share);
    // A rate is exact to the store's four places; a share is cut at the
    // paisa and the last part takes the rounding.
    if ((amount - inherited).abs() < (byRate ? 0.00006 : 0.011)) {
      return const {};
    }
    return (gross * percent / 100 - amount).abs() < 0.00006
        ? {'discount_percent': _plain(was['discount_percent'])}
        : {'discount_amount': _plain(was['discount_amount'])};
  }

  /// The lines of the receipts on the bill being edited: each at what the
  /// bill holds for it, and a receipt line the bill does not charge for at
  /// nothing -- a new bill would start it at what is left.
  List<PurchaseInvoiceDraftLine> _heldLines(
    List<Json> held,
    List<GoodsReceiptRecord> receipts,
    Map<String, double> invoiced,
  ) {
    final Map<String, Json> byLine = <String, Json>{};
    final Map<String, double> quantity = <String, double>{};
    for (final Json line in held) {
      final String id = stringValue(line['source_document_line_id']);
      byLine.putIfAbsent(id, () => line);
      quantity[id] =
          (quantity[id] ?? 0) + _amountOf(line['current_invoice_quantity']);
    }
    final List<PurchaseInvoiceDraftLine> lines = <PurchaseInvoiceDraftLine>[];
    for (final GoodsReceiptRecord receipt in receipts) {
      for (final GoodsReceiptLine source in receipt.lines) {
        final PurchaseInvoiceDraftLine draft = _draftLine(
          receipt,
          source,
          lines.length + 1,
          invoiced[source.id] ?? 0,
        );
        final Json? was = byLine[source.id];
        if (was == null) {
          draft.invoiceQuantity = '0';
        } else {
          draft.invoiceQuantity = _trim(quantity[source.id] ?? 0);
          draft.batchNumber = stringValue(was['batch_number']);
          draft.remarks = stringValue(was['remarks']);
          // A rate is in the box only where somebody typed one: the saved
          // price differs from the receipt line's. Left blank it takes the
          // receipt's again, which is the price it has.
          if ((_amountOf(was['unit_price']) - _amountOf(source.unitPrice))
                  .abs() >
              0.00005) {
            draft.unitPrice = _plain(was['unit_price']);
          }
          draft.itcEligibility = _typedItc(was);
          draft.capitalGoods =
              was['is_capital_goods'] == true || source.isCapitalGoods;
          draft.assetClassId =
              draft.capitalGoods ? stringValue(was['asset_class_id']) : '';
          draft.echo = {
            ..._heldLineExtras(was),
            ..._typedDiscount(was, source),
            if (stringValue(was['expiry_date']).isNotEmpty)
              'expiry_date': stringValue(was['expiry_date']),
          };
          draft.saved = was;
          draft.savedAs = draft.typedAs;
        }
        lines.add(draft);
      }
    }
    return lines;
  }

  /// One saved line of a bill of products, back in its boxes.
  ///
  /// Nothing is inherited on such a line: the order behind it was raised
  /// from the bill, at the rate and the discount the bill gave. So the rate
  /// is put back as held -- blank would take the product's price as it is
  /// today, which may no longer be the bill's -- and a discount on the row
  /// is one somebody typed. [raised] is the receipt line the bill raised,
  /// which is where its free goods are kept.
  PurchaseDirectLine _heldDirectLine(Json was, GoodsReceiptLine? raised) {
    final PurchaseDirectLine line = PurchaseDirectLine()
      ..heldPack = stringValue(was['pack_size'])
      ..productId = stringValue(was['product_id'])
      ..quantity = _plain(was['current_invoice_quantity'])
      ..freeQuantity = raised != null && _amountOf(raised.freeQuantity) > 0
          ? _plain(raised.freeQuantity)
          : ''
      ..unitPrice = _plain(was['unit_price'])
      ..batchNumber = stringValue(was['batch_number'])
      ..expiryDate = stringValue(was['expiry_date'])
      ..remarks = stringValue(was['remarks'])
      ..itcEligibility = _typedItc(was)
      ..capitalGoods = was['is_capital_goods'] == true;
    line.assetClassId =
        line.capitalGoods ? stringValue(was['asset_class_id']) : '';
    final double amount = _amountOf(was['discount_amount']);
    final bool asRate = (_amountOf(was['gross_amount']) *
                    _amountOf(was['discount_percent']) /
                    100 -
                amount)
            .abs() <
        0.00006;
    if (amount > 0 && asRate) {
      line.discountPercent = _plain(was['discount_percent']);
    }
    line.echo = {
      ..._heldLineExtras(was),
      // An amount no rate gives back has no box; it is sent back as held.
      if (amount > 0 && !asRate)
        'discount_amount': _plain(was['discount_amount']),
      // The unit and the place the line was raised in, so the order raised
      // again counts and receives it as before.
      for (final String key in const ['invoice_uom_id', 'warehouse_id'])
        if (stringValue(was[key]).isNotEmpty) key: stringValue(was[key]),
    };
    line.saved = was;
    line.savedAs = line.typedAs;
    return line;
  }

  /// What the bill holds in its header that this screen has no box for,
  /// sent back as held. The server writes each of these from the request
  /// even when it is absent, so leaving one out would clear it.
  Json _heldHeader({required bool pricing}) {
    final Json bill = widget.existing!;
    List<Json> rows(String key, List<String> fields) => [
          for (final dynamic raw in bill[key] as List? ?? const [])
            if (raw is Map)
              {
                for (final String field in fields)
                  if (raw[field] != null) field: raw[field],
              },
        ];
    final List<Json> notes = rows('notes', const ['note_type', 'note']);
    final List<Json> attachments = rows('attachments', const [
      'file_name',
      'mime_type',
      'file_path',
      'attachment_kind',
    ]);
    return {
      for (final String key in const [
        'payment_terms',
        'reference_number',
        'business_profile_id',
      ])
        if (_held(key).isNotEmpty) key: _held(key),
      // The due date follows the bill's date by the supplier's terms unless
      // one is sent, so it is sent back only while the date is the bill's
      // own: a bill moved to another day takes its due date again.
      if (_held('due_date').isNotEmpty &&
          _invoiceDate.trim() == _held('invoice_date'))
        'due_date': _held('due_date'),
      for (final String key in const ['additional_charges', 'round_off'])
        if (_amountOf(bill[key]) != 0) key: _held(key),
      // A bill of products is received at the firm's default branch unless
      // it names one; a bill of receipts takes its receipts' branch.
      if (_direct && _held('branch_id').isNotEmpty)
        'branch_id': _held('branch_id'),
      // A bill in the name of another office of the receipts' supplier.
      if (!_direct &&
          _held('vendor_id').isNotEmpty &&
          _held('vendor_id') != _receipt?.vendorId)
        'vendor_id': _held('vendor_id'),
      // Rebuilt from the request on every save. Not while merely pricing.
      if (!pricing && notes.isNotEmpty) 'notes': notes,
      if (!pricing && attachments.isNotEmpty) 'attachments': attachments,
    };
  }

  /// Phase 2: the bill as the server priced it last, and the line the side
  /// panel follows.
  PurchaseInvoicePreviewRecord? _preview;
  int _current = 0;
  Timer? _previewTimer;
  int _previewSerial = 0;
  bool _phase2 = false;

  /// L5: the boxes-and-pieces toggle as moved by hand; null until it is,
  /// and then the layout follows the bill (see `_boxAndPieces`).
  bool? _boxesChoice;

  /// Bumped when the supplier's number is filled in for the user, so its
  /// box re-reads it.
  int _supplierNumberEpoch = 0;

  void _setState(VoidCallback change) => setState(change);

  /// Suppliers added from this bill (backlog 128), offered after the ones
  /// the bill was opened with.
  final List<Vendor> _addedVendors = <Vendor>[];

  List<Vendor> get _vendorChoices => _addedVendors.isEmpty
      ? widget.vendors
      : [...widget.vendors, ..._addedVendors];

  /// Open the supplier form over the bill and choose the supplier it saved.
  Future<void> _addVendor() async {
    final Vendor? added = await addSupplierInPlace(context, api: widget.api);
    if (added == null || !mounted) return;
    widget.onVendorAdded?.call(added);
    setState(() {
      _addedVendors.add(added);
      _vendorId = added.id;
    });
    _schedulePreview();
  }

  /// PG-13: the asset classes, read the first time a line is ticked as
  /// capital goods so a bill with none costs no call.
  List<AssetClass> _assetClasses = const [];
  bool _assetClassesAsked = false;

  Future<void> _loadAssetClasses() async {
    if (_assetClassesAsked) return;
    _assetClassesAsked = true;
    try {
      final PagedResult<AssetClass> page =
          await widget.api.assetClasses(pageSize: 100);
      if (!mounted) return;
      setState(() => _assetClasses = [
            for (final AssetClass c in page.items)
              if (c.isActive) c
          ]);
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() {
        _assetClassesAsked = false;
        _error = refusalMessage(exception);
      });
    }
  }

  /// The supplier the bill is for, whichever way it was chosen.
  String? get _billSupplierId =>
      _vendorId ??
      _receipt?.vendorId ??
      _billedById ??
      _order?.vendorId ??
      _billVendorId;

  /// Backlog 140, a bill raised against an order: the supplier company the
  /// order is on, where it has a main office or branches. Null for a
  /// supplier on its own, which shows no *Billed by* box.
  VendorFamily? _orderFamily;

  /// The office the bill is from, where it is not the order's own supplier;
  /// null takes the order's, as a bill always did.
  String? _billedById;

  /// Bumped when a branch is added from here, so the *Billed by* box is
  /// built again and shows it chosen.
  int _officesEpoch = 0;

  /// *Billed by*: the offices of the order's supplier company. Null when the
  /// supplier has no branches and no main office.
  List<VendorFamilyMember>? get _orderOffices {
    final VendorFamily? family = _orderFamily;
    return family == null || family.members.length < 2 ? null : family.members;
  }

  /// Whether **New branch** is offered: the bill names an order and the
  /// person may add suppliers.
  bool get _offersNewBranch =>
      _mode == PurchaseBillMode.order && _order != null && widget.canAddVendor;

  /// Read the offices of the order's supplier, once per order chosen and
  /// only where the supplier list says it has a main office or branches: a
  /// supplier on its own makes no call.
  Future<void> _loadOrderFamily(PurchaseOrder order) async {
    final Vendor? supplier = _vendor(order.vendorId);
    if (supplier != null &&
        supplier.parentVendorId == null &&
        supplier.branchCount == 0) {
      return;
    }
    try {
      final VendorFamily family = await widget.api.vendorFamily(order.vendorId);
      if (!mounted || _order?.id != order.id) return;
      setState(() => _orderFamily = family);
    } on Object {
      // A family that cannot be read costs the choice, not the bill: it is
      // taken as from the order's supplier.
    }
  }

  void _chooseBilledBy(String? officeId) {
    setState(() {
      _billedById =
          officeId == null || officeId == _order?.vendorId ? null : officeId;
    });
    _schedulePreview();
  }

  /// Open the supplier form over the bill, set as a branch of the company
  /// the order is on, and put the bill in the name of the branch it saved
  /// (backlog 140). What was typed on the bill is kept.
  Future<void> _addBranch() async {
    final PurchaseOrder? order = _order;
    if (order == null) return;
    VendorFamily? family = _orderFamily;
    if (family == null) {
      final Vendor? supplier = _vendor(order.vendorId);
      if (supplier != null && supplier.parentVendorId == null) {
        // On its own until now: it becomes the main office.
        family = VendorFamily(
          parentId: supplier.id,
          members: [officeFrom(supplier, isParent: true)],
          totalBalance: '0.00',
        );
      } else {
        try {
          family = await widget.api.vendorFamily(order.vendorId);
        } on ApiException catch (exception) {
          if (!mounted) return;
          setState(() => _error = refusalMessage(exception));
          return;
        }
        if (!mounted || _order?.id != order.id) return;
      }
    }
    final VendorFamilyMember main = mainOfficeOf(family);
    final Vendor? added =
        await addSupplierInPlace(context, api: widget.api, branchOf: main);
    if (added == null || !mounted || _order?.id != order.id) return;
    widget.onVendorAdded?.call(added);
    if (added.parentVendorId != main.id) {
      // Taken out from under the main office in the form: it was saved, and
      // it is no office of this order's supplier.
      setState(() {
        _addedVendors.add(added);
        _error = '${added.displayName} was saved, but not as a branch of '
            '${main.name}, so this bill cannot be in its name.';
      });
      return;
    }
    setState(() {
      _addedVendors.add(added);
      _orderFamily = familyWithBranch(family!, added);
      _billedById = added.id;
      _officesEpoch += 1;
      _error = null;
    });
    _schedulePreview();
  }

  /// The currency of the supplier's account; blank is rupees.
  String get _supplierCurrency {
    for (final Vendor item in _vendorChoices) {
      if (item.id == _billSupplierId) return item.currencyCode;
    }
    return '';
  }

  /// The currency and rate of the order the bill's goods came on, which the
  /// server puts ahead of the supplier's own (D-BUY-39): the receipt says
  /// its order's, an order billed directly its own. Null for a bill that
  /// names neither; blank is rupees.
  (String, String)? get _orderCurrency {
    final GoodsReceiptRecord? receipt = _receipt;
    if (receipt != null) return (receipt.currencyCode, receipt.exchangeRate);
    final PurchaseOrder? order = _order;
    if (order != null) return (order.currencyCode, order.exchangeRate);
    return null;
  }

  /// What the bill starts in while nobody has typed a currency (D-BUY-42).
  /// A bill being edited starts in the currency it was saved in (D-UI-39).
  String get _startingCurrency =>
      _editing ? _savedCurrency : _orderCurrency?.$1 ?? _supplierCurrency;

  /// The bill's currency: what was typed, else its order's, else the
  /// supplier's. Blank and INR are both rupees and read as blank here.
  String get _billCurrency {
    final String code =
        (_currencyTouched ? _currency : _startingCurrency).trim().toUpperCase();
    return code == 'INR' ? '' : code;
  }

  /// The bill's rate: what was typed, else its order's while the bill is in
  /// the order's currency -- the rate the goods were received at.
  String get _billRate {
    if (_rateTouched) return _exchangeRate.trim();
    if (_editing) {
      // The rate the bill was saved at, while it stays in that currency.
      return _billCurrency == _savedCurrency
          ? _plain(_held('exchange_rate'))
          : '';
    }
    final (String, String)? order = _orderCurrency;
    if (order == null || order.$1.trim().toUpperCase() != _billCurrency) {
      return '';
    }
    return order.$2.trim();
  }

  bool get _foreign => _billCurrency.isNotEmpty;

  /// Receipts on is the whole chain; the server refuses receipts on with
  /// orders off, so the two switches name exactly three modes.
  ///
  /// A bill being edited is typed the way the bill itself says (D-UI-39),
  /// decided in [_loadEditing].
  PurchaseBillMode get _mode =>
      _editMode ??
      (widget.stages.goodsReceiptStage
          ? PurchaseBillMode.receipt
          : widget.stages.purchaseOrderStage
              ? PurchaseBillMode.order
              : PurchaseBillMode.products);

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
    // D-UI-39: an edit sends the fields whole, so they start at what the
    // bill holds; started empty, saving would clear them.
    stored: [
      for (final dynamic raw
          in widget.existing?['attributes'] as List? ?? const [])
        if (raw is Map)
          ProductAttributeValueRecord.fromJson(Map<String, dynamic>.from(raw)),
    ],
  );

  @override
  void initState() {
    super.initState();
    unawaited(_customFields.start());
    if (_editing) {
      _holdHeader();
      _loadingEdit = true;
      unawaited(_loadEditing());
    }
  }

  @override
  void dispose() {
    _previewTimer?.cancel();
    _customFields.dispose();
    for (final PurchaseInvoiceDraftLine line in _lines) {
      line.boxes.dispose();
    }
    for (final PurchaseDirectLine line in _directLines) {
      line.boxes.dispose();
    }
    super.dispose();
  }

  /// Price the bill again once the typing pauses; only the latest answer
  /// lands. A bill with no receipt or nothing being billed is not sent.
  void _schedulePreview() {
    if (!_phase2) return;
    // D-UI-39: a bill of receipts being edited is not priced again here;
    // see [_figuresOwed].
    if (_editing && (_editHeld || !_direct)) return;
    _previewTimer?.cancel();
    _previewTimer = Timer(const Duration(milliseconds: 350), () async {
      if (!_hasSource || !_hasSomethingToBill) return;
      final int serial = ++_previewSerial;
      try {
        final PurchaseInvoicePreviewRecord priced =
            await widget.api.previewPurchaseInvoice(_payload(pricing: true));
        if (!mounted || serial != _previewSerial) return;
        setState(() {
          _preview = priced;
          _savedFigures = false;
        });
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
    final Set<String> listed = {
      for (final GoodsReceiptRecord item in widget.receipts) item.id,
    };
    // D-UI-39: a receipt already on the bill being edited is offered
    // whatever is left of it, or unticking it could not be undone.
    final Set<String> on = {
      for (final GoodsReceiptRecord item in _editReceipts) item.id,
    };
    return [
      for (final GoodsReceiptRecord item in [
        ...widget.receipts,
        for (final GoodsReceiptRecord read in _editReceipts)
          if (!listed.contains(read.id)) read,
      ])
        if (item.vendorId == vendor &&
            (item.hasLeftToBill || on.contains(item.id)))
          item,
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
      // Another order is another supplier's offices.
      _orderFamily = null;
      _billedById = null;
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
      packSize: _stockPack(
        line.packSize,
        line.purchaseUomId,
        line.inventoryUomId,
      ),
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
        // D-UI-39: the bill being edited is not "another bill". Counting its
        // own quantity left a draft for the whole receipt reading nothing
        // left to bill, and refused the quantity it already holds.
        if (_editing && stringValue(row['id']) == _held('id')) continue;
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
      packSize: _stockPack(
        line.packSize,
        line.purchaseUomId,
        line.inventoryUomId,
      ),
    );
    draft.invoiceQuantity = _trim(draft.outstanding);
    draft.capitalFromReceipt = line.isCapitalGoods;
    draft.capitalGoods = line.isCapitalGoods;
    return draft;
  }

  static String _trim(double value) =>
      value == value.roundToDouble() ? value.toStringAsFixed(0) : '$value';

  /// L5: a source line's pack, only where the line is counted in the stock
  /// unit -- a line typed as boxes and pieces is in pieces.
  static String _stockPack(String pack, String unit, String stock) =>
      unit.isEmpty || unit == stock ? pack : '';

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
    if (_loadingEdit) return 'The bill is still being read.';
    if (_editBlock != null) return _editBlock;
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
    if (_foreign && (double.tryParse(_billRate) ?? 0) <= 0) {
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
      if (line.capitalGoods && line.assetClassId.isEmpty) {
        return 'Line ${line.lineNumber}: choose the asset class of the '
            'capital goods.';
      }
    }
    return null;
  }

  String? _directValidation() {
    if (_sendableDirect().isEmpty) return 'Add a product with a quantity.';
    for (int index = 0; index < _directLines.length; index++) {
      final PurchaseDirectLine line = _directLines[index];
      if (!line.sendable) continue;
      if (line.capitalGoods && line.assetClassId.isEmpty) {
        return 'Line ${index + 1}: choose the asset class of the capital '
            'goods.';
      }
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
    final bool editing = _editing;
    return {
      // D-UI-39: first, so what is typed below replaces what the bill held.
      if (editing) ..._heldHeader(pricing: pricing),
      if (_direct) 'vendor_id': _vendorId,
      // Backlog 140: only where another office of the order's supplier is
      // billing; the server checks it is one, and receives the goods from it.
      if (_mode == PurchaseBillMode.order && _billedById != null)
        'vendor_id': _billedById,
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
      if (!editing || pricing) ...{
        if (!_foreign && _tcsFigure(_tcsRate) != null)
          'tcs_rate_percent': _tcsRate.trim(),
        if (!_foreign && _tcsFigure(_tcsAmount) != null)
          'tcs_amount': _tcsAmount.trim(),
      } else if (_foreign ? _hadTcs : _tcsTouched) ...{
        // D-UI-39: an edit that leaves both boxes alone sends neither, and
        // the server keeps the bill's TCS -- an amount the rate gave follows
        // the new total, one that was typed stays. Once either is touched
        // both are sent, a blank one as null, because absent would keep it.
        // A bill moved to another currency gives its TCS up.
        'tcs_rate_percent':
            _foreign || _tcsFigure(_tcsRate) == null ? null : _tcsRate.trim(),
        'tcs_amount': _foreign || _tcsFigure(_tcsAmount) == null
            ? null
            : _tcsAmount.trim(),
      },
      // PG-12: sent once the person has chosen a currency (blank or INR is
      // rupees); until then the server starts the bill in its order's, or
      // its supplier's. The rate is sent only for a foreign bill: what was
      // typed, else the order's.
      // An edit that leaves the box alone sends none and keeps the bill's;
      // pricing it is a new bill to the server, so it is told.
      if (_currencyTouched || (editing && pricing))
        'currency_code': _foreign ? _billCurrency : 'INR',
      if (_foreign && (double.tryParse(_billRate) ?? 0) > 0)
        'exchange_rate': _billRate,
      // Only once the definitions arrived, and never while merely pricing:
      // absent leaves the stored values alone.
      if (!pricing && _customFields.hasFields)
        'attributes': _customFields.payload(),
      // L5: only where the toggle is offered; absent takes a receipt's on a
      // new bill and keeps the bill's own on an edit.
      if (_offersBoxes) 'box_and_piece_entry': _boxAndPieces,
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
            direct[index].toJson(
              index + 1,
              packSize: _boxAndPieces && _directPack(direct[index]) != null
                  ? _directPackSize(direct[index])
                  : '',
            )
        else
          for (int index = 0; index < sending.length; index++)
            {
              ...sending[index].toJson(boxes: _boxAndPieces),
              'line_number': index + 1,
            },
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
      // D-UI-39: a draft being edited is replaced, with the version it was
      // read at, so a save over somebody else's newer one is refused.
      final Json response = _editing
          ? await widget.api.updatePurchaseInvoice(
              _held('id'),
              _payload(),
              expectedVersion: (widget.existing!['version'] as num?)?.toInt(),
            )
          : await widget.api.createPurchaseInvoice(_payload());
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
