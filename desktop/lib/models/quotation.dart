import 'entities.dart';

/// One line of an offer.
class QuotationLine {
  const QuotationLine({
    required this.id,
    required this.lineNumber,
    required this.productId,
    required this.description,
    required this.quantity,
    required this.unitPrice,
    required this.discountAmount,
    required this.taxAmount,
    required this.netAmount,
    required this.remarks,
  });

  final String id;
  final int lineNumber;
  final String productId;

  /// What the goods are called. Shown instead of the product id: a customer
  /// reading a quotation wants the item named, not a UUID.
  final String description;
  final String quantity;
  final String unitPrice;
  final String discountAmount;
  final String taxAmount;
  final String netAmount;
  final String remarks;

  factory QuotationLine.fromJson(Json json) => QuotationLine(
        id: stringValue(json['id']),
        lineNumber: (json['line_number'] as num?)?.toInt() ?? 0,
        productId: stringValue(json['product_id']),
        description: stringValue(json['description']),
        quantity: stringValue(json['quantity']),
        unitPrice: stringValue(json['unit_price']),
        discountAmount: stringValue(json['discount_amount']),
        taxAmount: stringValue(json['tax_amount']),
        netAmount: stringValue(json['net_amount']),
        remarks: stringValue(json['remarks']),
      );
}

/// A price offered to a customer before anything is sold.
///
/// A quotation commits nothing: no stock is reserved, no balance moves, no
/// journal is written. All of that happens at conversion, on the order it
/// becomes, which is why the screen is careful never to imply otherwise.
class Quotation {
  const Quotation({
    required this.id,
    required this.customerId,
    required this.branchId,
    required this.warehouseId,
    required this.quotationNumber,
    required this.quotationDate,
    required this.validUntil,
    required this.customerReference,
    required this.paymentTerms,
    required this.deliveryTerms,
    required this.status,
    required this.subtotal,
    required this.taxTotal,
    required this.grandTotal,
    required this.convertedSalesOrderId,
    required this.convertedSalesOrderNumber,
    required this.declineReason,
    required this.cancelReason,
    required this.remarks,
    required this.isExpired,
    required this.canConvert,
    required this.lines,
  });

  final String id;
  final String customerId;
  final String branchId;
  final String warehouseId;
  final String quotationNumber;
  final String quotationDate;

  /// The last day the quoted prices stand.
  final String validUntil;
  final String customerReference;
  final String paymentTerms;
  final String deliveryTerms;
  final String status;
  final String subtotal;
  final String taxTotal;
  final String grandTotal;
  final String convertedSalesOrderId;
  final String convertedSalesOrderNumber;
  final String declineReason;
  final String cancelReason;
  final String remarks;

  /// Both answered by the server rather than worked out here, so the client
  /// cannot disagree with it about whether an offer still stands.
  final bool isExpired;
  final bool canConvert;

  final List<QuotationLine> lines;

  bool get isDraft => status == 'DRAFT';
  bool get isSent => status == 'SENT';
  bool get isAccepted => status == 'ACCEPTED';
  bool get isConverted => status == 'CONVERTED';
  bool get isDeclined => status == 'DECLINED';
  bool get isCancelled => status == 'CANCELLED';

  /// Whether the offer is still open — nobody has decided and it has not
  /// lapsed. This is what "how much business is on the table" counts.
  bool get isOpen => (isDraft || isSent) && !isExpired;

  factory Quotation.fromJson(Json json) => Quotation(
        id: stringValue(json['id']),
        customerId: stringValue(json['customer_id']),
        branchId: stringValue(json['branch_id']),
        warehouseId: stringValue(json['warehouse_id']),
        quotationNumber: stringValue(json['quotation_number']),
        quotationDate: stringValue(json['quotation_date']),
        validUntil: stringValue(json['valid_until']),
        customerReference: stringValue(json['customer_reference']),
        paymentTerms: stringValue(json['payment_terms']),
        deliveryTerms: stringValue(json['delivery_terms']),
        status: stringValue(json['status']),
        subtotal: stringValue(json['subtotal']),
        taxTotal: stringValue(json['tax_total']),
        grandTotal: stringValue(json['grand_total']),
        convertedSalesOrderId: stringValue(json['converted_sales_order_id']),
        convertedSalesOrderNumber:
            stringValue(json['converted_sales_order_number']),
        declineReason: stringValue(json['decline_reason']),
        cancelReason: stringValue(json['cancel_reason']),
        remarks: stringValue(json['remarks']),
        isExpired: boolValue(json['is_expired']),
        canConvert: boolValue(json['can_convert']),
        lines: [
          for (final dynamic line in json['lines'] is List ? json['lines'] : const [])
            if (line is Map) QuotationLine.fromJson(Map<String, dynamic>.from(line)),
        ],
      );
}

/// What a conversion produced: the quotation, and the order it became.
class QuotationConversion {
  const QuotationConversion({
    required this.quotation,
    required this.orderNumber,
  });

  final Quotation quotation;
  final String orderNumber;

  factory QuotationConversion.fromJson(Json json) {
    final dynamic order = json['order'];
    final dynamic data = json['data'];
    return QuotationConversion(
      quotation: Quotation.fromJson(
        data is Map ? Map<String, dynamic>.from(data) : const {},
      ),
      orderNumber: order is Map
          ? stringValue(Map<String, dynamic>.from(order)['order_number'])
          : '',
    );
  }
}
