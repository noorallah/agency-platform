import 'entities.dart';

/// A dispatched delivery note with something still left to bill.
///
/// The platform had no way to say which documents were already invoiced, so a
/// client could only offer all of them and let the save be refused. On a firm
/// with 58 delivery notes and 49 invoices that is a refusal nine times in ten,
/// which is why `GET /api/v1/sales-invoices/billable` exists.
class BillableDocument {
  const BillableDocument({
    required this.sourceDocumentType,
    required this.sourceDocumentId,
    required this.sourceDocumentNumber,
    required this.documentDate,
    required this.customerId,
    required this.customerName,
    required this.lines,
    this.branchId = '',
  });

  /// `DELIVERY_NOTE` or `SALES_ORDER`, sent back on every invoice line.
  final String sourceDocumentType;
  final String sourceDocumentId;
  final String sourceDocumentNumber;
  final String documentDate;
  final String customerId;
  final String customerName;
  final String branchId;
  final List<BillableLine> lines;

  String get label =>
      '$sourceDocumentNumber  ·  $documentDate  ·  $customerName';

  factory BillableDocument.fromJson(Json json) => BillableDocument(
        sourceDocumentType: stringValue(json['source_document_type']),
        sourceDocumentId: stringValue(json['source_document_id']),
        sourceDocumentNumber: stringValue(json['source_document_number']),
        documentDate: stringValue(json['document_date']),
        customerId: stringValue(json['customer_id']),
        customerName: stringValue(json['customer_name']),
        branchId: stringValue(json['branch_id']),
        lines: [
          for (final dynamic line
              in json['lines'] is List ? json['lines'] as List : const [])
            if (line is Map)
              BillableLine.fromJson(Map<String, dynamic>.from(line)),
        ],
      );
}

/// One line of such a document, and how much of it is still unbilled.
class BillableLine {
  const BillableLine({
    required this.sourceDocumentLineId,
    required this.lineNumber,
    required this.description,
    required this.sourceQuantity,
    required this.alreadyInvoicedQuantity,
    required this.remainingQuantity,
    required this.unitPrice,
    this.productId = '',
    this.discountPercent = '0',
    this.freeQuantity = '0',
  });

  final String sourceDocumentLineId;
  final int lineNumber;
  final String productId;
  final String description;

  /// What the source document committed — dispatched, on a delivery note.
  final String sourceQuantity;
  final String alreadyInvoicedQuantity;

  /// The difference, and what the invoice line defaults to. The server derives
  /// it the same way the save does, so the number offered is the number the
  /// save will accept.
  final String remainingQuantity;

  final String unitPrice;
  final String discountPercent;
  final String freeQuantity;

  String get label {
    final String name =
        description.isEmpty ? 'Line $lineNumber' : description;
    return '$lineNumber. $name';
  }

  factory BillableLine.fromJson(Json json) => BillableLine(
        sourceDocumentLineId: stringValue(json['source_document_line_id']),
        lineNumber: (json['line_number'] as num?)?.toInt() ?? 0,
        productId: stringValue(json['product_id']),
        description: stringValue(json['description']),
        sourceQuantity: stringValue(json['source_quantity']),
        alreadyInvoicedQuantity:
            stringValue(json['already_invoiced_quantity']),
        remainingQuantity: stringValue(json['remaining_quantity']),
        unitPrice: stringValue(json['unit_price']),
        discountPercent: stringValue(json['discount_percent']).isEmpty
            ? '0'
            : stringValue(json['discount_percent']),
        freeQuantity: stringValue(json['free_quantity']).isEmpty
            ? '0'
            : stringValue(json['free_quantity']),
      );
}

/// Which stages of a sale this firm fills in by hand.
///
/// The chain is quotation, sales order, delivery note, invoice. A stage that
/// is off is still raised -- by the server, as part of saving the bill -- so
/// this decides which screens a firm sees, never whether the documents exist.
class SalesWorkflowSettings {
  const SalesWorkflowSettings({
    required this.quotationStage,
    required this.salesOrderStage,
    required this.deliveryNoteStage,
    required this.isConfigured,
    this.defaultBranchId,
    this.defaultWarehouseId,
  });

  final bool quotationStage;
  final bool salesOrderStage;
  final bool deliveryNoteStage;
  final String? defaultBranchId;
  final String? defaultWarehouseId;

  /// False while the firm is still on the platform default: the whole chain.
  final bool isConfigured;

  /// What a firm gets before anybody configures anything, and what the client
  /// falls back to when the settings cannot be read. Failing open matters: an
  /// unreachable endpoint must not hide screens a firm depends on.
  static const SalesWorkflowSettings wholeChain = SalesWorkflowSettings(
    quotationStage: true,
    salesOrderStage: true,
    deliveryNoteStage: true,
    isConfigured: false,
  );

  /// True when the bill is the only document its user types.
  bool get billsDirectly => !salesOrderStage && !deliveryNoteStage;

  factory SalesWorkflowSettings.fromJson(Json json) => SalesWorkflowSettings(
        quotationStage: boolValue(json['quotation_stage']),
        salesOrderStage: boolValue(json['sales_order_stage']),
        deliveryNoteStage: boolValue(json['delivery_note_stage']),
        defaultBranchId: _orNull(json['default_branch_id']),
        defaultWarehouseId: _orNull(json['default_warehouse_id']),
        isConfigured: boolValue(json['is_configured']),
      );

  Json toJson() => <String, dynamic>{
        'quotation_stage': quotationStage,
        'sales_order_stage': salesOrderStage,
        'delivery_note_stage': deliveryNoteStage,
        'default_branch_id': defaultBranchId,
        'default_warehouse_id': defaultWarehouseId,
      };

  SalesWorkflowSettings copyWith({
    bool? quotationStage,
    bool? salesOrderStage,
    bool? deliveryNoteStage,
  }) =>
      SalesWorkflowSettings(
        quotationStage: quotationStage ?? this.quotationStage,
        salesOrderStage: salesOrderStage ?? this.salesOrderStage,
        deliveryNoteStage: deliveryNoteStage ?? this.deliveryNoteStage,
        defaultBranchId: defaultBranchId,
        defaultWarehouseId: defaultWarehouseId,
        isConfigured: isConfigured,
      );
}

/// An id the server may legitimately leave unset, rather than an empty string.
String? _orNull(dynamic value) {
  final String text = stringValue(value);
  return text.isEmpty ? null : text;
}
