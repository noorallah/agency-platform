import 'batch_serial.dart';
import 'entities.dart';
import 'line_tax_rule.dart';

/// Where a sales return can be raised from.
///
/// The goods physically left on a delivery note and the money was billed on a
/// sales invoice, so either is a starting point: a customer who sends goods
/// back before being invoiced has only the first.
enum SalesReturnSource {
  deliveryNote('DELIVERY_NOTE', 'Delivery note'),
  salesInvoice('SALES_INVOICE', 'Sales invoice');

  const SalesReturnSource(this.code, this.label);

  final String code;
  final String label;

  static SalesReturnSource fromCode(String code) =>
      SalesReturnSource.values.firstWhere(
        (value) => value.code == code,
        orElse: () => SalesReturnSource.deliveryNote,
      );
}

/// One line of a customer return.
class SalesReturnLine {
  const SalesReturnLine({
    required this.id,
    required this.lineNumber,
    required this.sourceType,
    required this.sourceDocumentNumber,
    required this.sourceDocumentLineNumber,
    required this.productId,
    required this.description,
    required this.dispatchedQuantity,
    required this.alreadyReturnedQuantity,
    required this.currentReturnQuantity,
    this.freeQuantity = '0',
    required this.restockQuantity,
    required this.damagedQuantity,
    required this.scrapQuantity,
    required this.reasonCode,
    required this.unitPrice,
    required this.taxAmount,
    required this.netAmount,
    required this.batchNumber,
    required this.remarks,
    this.enteredQuantity = '',
    this.returnUomId = '',
    this.serials = const [],
    this.taxRuleCode,
    this.taxRuleVersion,
  });

  final String id;
  final int lineNumber;
  final SalesReturnSource sourceType;
  final String sourceDocumentNumber;
  final int sourceDocumentLineNumber;
  final String productId;

  /// What the source document called it. Shown instead of the product id: a
  /// reader wants the goods named, not a UUID.
  final String description;
  final String dispatchedQuantity;
  final String alreadyReturnedQuantity;
  final String currentReturnQuantity;

  /// What was typed, in [returnUomId], where the line was typed in another
  /// unit than the source line's (D-PRC-37); empty otherwise.
  /// [currentReturnQuantity] is then the same goods in the source line's
  /// unit (0.5833 of a box for 7 pieces).
  final String enteredQuantity;
  final String returnUomId;

  /// The quantity the line's own unit counts.
  String get shownQuantity =>
      enteredQuantity.isEmpty ? currentReturnQuantity : enteredQuantity;

  /// The free goods among [currentReturnQuantity], credited nothing
  /// (D-PRC-8).
  final String freeQuantity;

  /// How much of it can be sold again. The rest came back damaged or as scrap:
  /// still owned and still worth what it cost, but not on the shelf.
  final String restockQuantity;
  final String damagedQuantity;
  final String scrapQuantity;
  final String reasonCode;
  final String unitPrice;
  final String taxAmount;
  final String netAmount;
  final String batchNumber;
  final String remarks;

  /// The serialised units this line brings back -- named when it was raised,
  /// back on the shelf once it completes.
  final List<PickedSerial> serials;

  /// What is still returnable against the source line after this one.
  String get pendingQuantity {
    final double dispatched = double.tryParse(dispatchedQuantity) ?? 0;
    final double already = double.tryParse(alreadyReturnedQuantity) ?? 0;
    final double current = double.tryParse(currentReturnQuantity) ?? 0;
    final double pending = dispatched - already - current;
    return (pending < 0 ? 0 : pending).toStringAsFixed(4);
  }

  /// The tax rule that decided this line's tax; null when none matched.
  final String? taxRuleCode;
  final int? taxRuleVersion;

  factory SalesReturnLine.fromJson(Json json) => SalesReturnLine(
        id: stringValue(json['id']),
        lineNumber: (json['line_number'] as num?)?.toInt() ?? 0,
        sourceType:
            SalesReturnSource.fromCode(stringValue(json['source_document_type'])),
        sourceDocumentNumber: stringValue(json['source_document_number']),
        sourceDocumentLineNumber:
            (json['source_document_line_number'] as num?)?.toInt() ?? 0,
        productId: stringValue(json['product_id']),
        description: stringValue(json['description']),
        dispatchedQuantity: stringValue(json['dispatched_quantity']),
        alreadyReturnedQuantity: stringValue(json['already_returned_quantity']),
        currentReturnQuantity: stringValue(json['current_return_quantity']),
        freeQuantity: json['free_quantity'] == null
            ? '0'
            : stringValue(json['free_quantity']),
        restockQuantity: stringValue(json['restock_quantity']),
        damagedQuantity: stringValue(json['damaged_quantity']),
        scrapQuantity: stringValue(json['scrap_quantity']),
        reasonCode: stringValue(json['reason_code']),
        unitPrice: stringValue(json['unit_price']),
        taxAmount: stringValue(json['tax_amount']),
        netAmount: stringValue(json['net_amount']),
        batchNumber: stringValue(json['batch_number']),
        remarks: stringValue(json['remarks']),
        enteredQuantity: stringValue(json['entered_quantity']),
        returnUomId: stringValue(json['return_uom_id']),
        serials: PickedSerial.listFrom(json['serials']),
        taxRuleCode: LineTaxRule.fromJson(json).code,
        taxRuleVersion: LineTaxRule.fromJson(json).version,
      );
}

/// Goods coming back from a customer.
class SalesReturn {
  const SalesReturn({
    required this.id,
    required this.customerId,
    this.customerName = '',
    this.customerCode = '',
    required this.branchId,
    required this.warehouseId,
    required this.returnNumber,
    required this.returnDate,
    this.createdAt = '',
    this.attachedFileCount = 0,
    required this.customerReturnNumber,
    required this.returnReason,
    required this.status,
    required this.totalCurrentReturnQuantity,
    required this.totalRestockQuantity,
    required this.subtotal,
    required this.taxTotal,
    required this.grandTotal,
    required this.journalEntryId,
    required this.costJournalEntryId,
    required this.cancelReason,
    required this.remarks,
    required this.lines,
    this.timeLimitWarning = '',
  });

  final String id;
  final String customerId;

  /// Whose return it is, for the list; empty for a removed customer.
  final String customerName;
  final String customerCode;
  final String branchId;
  final String warehouseId;
  final String returnNumber;
  final String returnDate;
  final String createdAt;

  /// How many files are kept with it (SG-6).
  final int attachedFileCount;
  final String customerReturnNumber;
  final String returnReason;
  final String status;
  final String totalCurrentReturnQuantity;
  final String totalRestockQuantity;
  final String subtotal;
  final String taxTotal;

  /// What the customer is credited, tax included.
  final String grandTotal;

  /// The journal that credited the customer, and the one that put the cost of
  /// the goods back into stock. Two, because they answer two questions: the
  /// credit is at the selling price, the stock returns at what it cost.
  final String journalEntryId;
  final String costJournalEntryId;
  final String cancelReason;
  final String remarks;
  final List<SalesReturnLine> lines;

  /// Set when the return is dated past 30 November after the year of an
  /// invoice it credits, so it can no longer reduce tax (s.34(2), GST-1).
  final String timeLimitWarning;

  bool get isDraft => status == 'DRAFT';
  bool get isApproved => status == 'APPROVED';
  bool get isCompleted => status == 'COMPLETED';
  bool get isCancelled => status == 'CANCELLED';
  bool get isClosed => status == 'CLOSED';

  /// Whether the goods are actually back and the customer actually credited.
  /// A draft or an approved return has moved nothing yet.
  bool get hasMoved => isCompleted || isClosed;

  factory SalesReturn.fromJson(Json json) => SalesReturn(
        id: stringValue(json['id']),
        customerId: stringValue(json['customer_id']),
        customerName: stringValue(json['customer_name']),
        customerCode: stringValue(json['customer_code']),
        branchId: stringValue(json['branch_id']),
        warehouseId: stringValue(json['warehouse_id']),
        returnNumber: stringValue(json['return_number']),
        returnDate: stringValue(json['return_date']),
        createdAt: stringValue(json['created_at']),
        attachedFileCount:
            int.tryParse(stringValue(json['attached_file_count'])) ?? 0,
        customerReturnNumber: stringValue(json['customer_return_number']),
        returnReason: stringValue(json['return_reason']),
        status: stringValue(json['status']),
        totalCurrentReturnQuantity:
            stringValue(json['total_current_return_quantity']),
        totalRestockQuantity: stringValue(json['total_restock_quantity']),
        subtotal: stringValue(json['subtotal']),
        taxTotal: stringValue(json['tax_total']),
        grandTotal: stringValue(json['grand_total']),
        journalEntryId: stringValue(json['journal_entry_id']),
        costJournalEntryId: stringValue(json['cost_journal_entry_id']),
        cancelReason: stringValue(json['cancel_reason']),
        remarks: stringValue(json['remarks']),
        lines: [
          for (final dynamic line in json['lines'] is List ? json['lines'] : const [])
            if (line is Map) SalesReturnLine.fromJson(Map<String, dynamic>.from(line)),
        ],
        timeLimitWarning: stringValue(json['time_limit_warning']),
      );
}

/// A document a return can be raised against, flattened for the picker.
///
/// Delivery notes and sales invoices are different resources with different
/// field names; the editor only needs what they have in common plus their
/// returnable lines.
class ReturnableDocument {
  const ReturnableDocument({
    required this.id,
    required this.sourceType,
    required this.number,
    required this.documentDate,
    required this.customerId,
    required this.lines,
    this.customerName = '',
    this.status = '',
  });

  final String id;
  final SalesReturnSource sourceType;
  final String number;
  final String documentDate;
  final String customerId;
  final String customerName;
  final List<ReturnableLine> lines;

  /// The document's own status.
  ///
  /// The list it comes from is unfiltered -- the 50 most recent of each kind
  /// -- so a cancelled invoice is offered like any other. A credit note may
  /// only correct a bill that was actually issued, so the picker filters on
  /// this rather than leaving somebody to choose one and find nothing to
  /// credit.
  final String status;

  /// Number, date and whose it is. The picker mixes every customer's notes
  /// and invoices, and with number and date alone a return was raised
  /// against another customer's note and credited them (plan item 9.22,
  /// 2026-09-13).
  String get label => customerName.isEmpty
      ? '$number  ·  $documentDate'
      : '$number  ·  $documentDate  ·  $customerName';

  /// Read a delivery note, whose dispatched quantity is what went out.
  factory ReturnableDocument.fromDeliveryNote(Json json) => ReturnableDocument(
        id: stringValue(json['id']),
        sourceType: SalesReturnSource.deliveryNote,
        number: stringValue(json['delivery_note_number']),
        documentDate: stringValue(json['delivery_date']),
        customerId: stringValue(json['customer_id']),
        customerName: stringValue(json['customer_name']),
        status: stringValue(json['status']),
        lines: _lines(json, 'current_delivery_quantity'),
      );

  /// Read a sales invoice, whose invoiced quantity is what was billed.
  factory ReturnableDocument.fromSalesInvoice(Json json) => ReturnableDocument(
        id: stringValue(json['id']),
        sourceType: SalesReturnSource.salesInvoice,
        number: stringValue(json['invoice_number']),
        documentDate: stringValue(json['invoice_date']),
        customerId: stringValue(json['customer_id']),
        customerName: stringValue(json['customer_name']),
        status: stringValue(json['status']),
        lines: _lines(json, 'current_invoice_quantity'),
      );

  static List<ReturnableLine> _lines(Json json, String quantityKey) => [
        for (final dynamic line in json['lines'] is List ? json['lines'] : const [])
          if (line is Map)
            ReturnableLine.fromJson(
              Map<String, dynamic>.from(line),
              quantityKey: quantityKey,
            ),
      ];
}

/// One line of a document that can be returned against.
class ReturnableLine {
  const ReturnableLine({
    required this.id,
    required this.lineNumber,
    required this.productId,
    required this.description,
    required this.quantity,
    required this.unitPrice,
    this.freeQuantity = '0',
  });

  final String id;
  final int lineNumber;
  final String productId;
  final String description;

  /// What this line charged the customer for. With [freeQuantity] it is the
  /// ceiling on the return: free goods can come back too (D-PRC-8).
  final String quantity;
  final String unitPrice;

  /// What the line sent free beside [quantity]; '0' when nothing was.
  final String freeQuantity;

  /// Whether the source line shipped any free goods.
  bool get shippedFree => (double.tryParse(freeQuantity) ?? 0) > 0;

  String get label {
    final String name = description.isEmpty ? 'Line $lineNumber' : description;
    return '$lineNumber. $name  ·  $quantity';
  }

  /// The product's name first, then the line's own text.
  ///
  /// `description` is nullable on every document line and the seeded
  /// documents leave it null, so reading it alone left both the credit-note
  /// and sales-return pickers offering "Line 1" and nothing else -- a choice
  /// nobody can make. `product_name` is what the server now sends beside it.
  /// "CODE  Name" from what the server sends beside a line, either part
  /// alone when only one is known, and empty when neither is -- the pickers
  /// then fall back to "Line N".
  static String _productLabel(Json json) {
    final String code = stringValue(json['product_code']);
    final String name = stringValue(json['product_name']);
    if (code.isEmpty) return name;
    return name.isEmpty ? code : '$code  $name';
  }

  factory ReturnableLine.fromJson(Json json, {required String quantityKey}) =>
      ReturnableLine(
        id: stringValue(json['id']),
        lineNumber: (json['line_number'] as num?)?.toInt() ?? 0,
        productId: stringValue(json['product_id']),
        description: stringValue(json['description']).isNotEmpty
            ? stringValue(json['description'])
            : _productLabel(json),
        quantity: stringValue(json[quantityKey]),
        unitPrice: stringValue(json['unit_price']),
        freeQuantity: json['free_quantity'] == null
            ? '0'
            : stringValue(json['free_quantity']),
      );
}
