import 'entities.dart';

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
    required this.restockQuantity,
    required this.damagedQuantity,
    required this.scrapQuantity,
    required this.reasonCode,
    required this.unitPrice,
    required this.taxAmount,
    required this.netAmount,
    required this.batchNumber,
    required this.remarks,
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

  /// What is still returnable against the source line after this one.
  String get pendingQuantity {
    final double dispatched = double.tryParse(dispatchedQuantity) ?? 0;
    final double already = double.tryParse(alreadyReturnedQuantity) ?? 0;
    final double current = double.tryParse(currentReturnQuantity) ?? 0;
    final double pending = dispatched - already - current;
    return (pending < 0 ? 0 : pending).toStringAsFixed(4);
  }

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
        restockQuantity: stringValue(json['restock_quantity']),
        damagedQuantity: stringValue(json['damaged_quantity']),
        scrapQuantity: stringValue(json['scrap_quantity']),
        reasonCode: stringValue(json['reason_code']),
        unitPrice: stringValue(json['unit_price']),
        taxAmount: stringValue(json['tax_amount']),
        netAmount: stringValue(json['net_amount']),
        batchNumber: stringValue(json['batch_number']),
        remarks: stringValue(json['remarks']),
      );
}

/// Goods coming back from a customer.
class SalesReturn {
  const SalesReturn({
    required this.id,
    required this.customerId,
    required this.branchId,
    required this.warehouseId,
    required this.returnNumber,
    required this.returnDate,
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
  });

  final String id;
  final String customerId;
  final String branchId;
  final String warehouseId;
  final String returnNumber;
  final String returnDate;
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
        branchId: stringValue(json['branch_id']),
        warehouseId: stringValue(json['warehouse_id']),
        returnNumber: stringValue(json['return_number']),
        returnDate: stringValue(json['return_date']),
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
  });

  final String id;
  final SalesReturnSource sourceType;
  final String number;
  final String documentDate;
  final String customerId;
  final List<ReturnableLine> lines;

  String get label => '$number  ·  $documentDate';

  /// Read a delivery note, whose dispatched quantity is what went out.
  factory ReturnableDocument.fromDeliveryNote(Json json) => ReturnableDocument(
        id: stringValue(json['id']),
        sourceType: SalesReturnSource.deliveryNote,
        number: stringValue(json['delivery_note_number']),
        documentDate: stringValue(json['delivery_date']),
        customerId: stringValue(json['customer_id']),
        lines: _lines(json, 'current_delivery_quantity'),
      );

  /// Read a sales invoice, whose invoiced quantity is what was billed.
  factory ReturnableDocument.fromSalesInvoice(Json json) => ReturnableDocument(
        id: stringValue(json['id']),
        sourceType: SalesReturnSource.salesInvoice,
        number: stringValue(json['invoice_number']),
        documentDate: stringValue(json['invoice_date']),
        customerId: stringValue(json['customer_id']),
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
  });

  final String id;
  final int lineNumber;
  final String productId;
  final String description;

  /// What this line sent the customer, which is the ceiling on the return.
  final String quantity;
  final String unitPrice;

  String get label {
    final String name = description.isEmpty ? 'Line $lineNumber' : description;
    return '$lineNumber. $name  ·  $quantity';
  }

  factory ReturnableLine.fromJson(Json json, {required String quantityKey}) =>
      ReturnableLine(
        id: stringValue(json['id']),
        lineNumber: (json['line_number'] as num?)?.toInt() ?? 0,
        productId: stringValue(json['product_id']),
        description: stringValue(json['description']),
        quantity: stringValue(json[quantityKey]),
        unitPrice: stringValue(json['unit_price']),
      );
}
