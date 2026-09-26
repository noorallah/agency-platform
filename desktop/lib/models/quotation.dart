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
    required this.discountPercent,
    this.discountSource = '',
    this.freeQuantity = '0',
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

  /// The rate that was quoted, which is what the editor puts back in the field.
  /// Only the resulting amount was parsed before, so revising a discounted
  /// line silently re-sent it at full price.
  final String discountPercent;

  /// `percent`/`amount` when typed, else where the server resolved it from;
  /// empty for a line stored before the source was recorded.
  final String discountSource;

  /// Thrown in with this line, charged for at nothing.
  final String freeQuantity;
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
        discountPercent: stringValue(json['discount_percent']),
        discountSource: stringValue(json['discount_source']),
        freeQuantity: stringValue(json['free_quantity']).isEmpty
            ? '0'
            : stringValue(json['free_quantity']),
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
    this.version = 0,
    required this.customerId,
    required this.branchId,
    required this.warehouseId,
    required this.quotationNumber,
    required this.quotationDate,
    required this.validUntil,
    this.createdAt = '',
    required this.customerReference,
    required this.paymentTerms,
    required this.deliveryTerms,
    required this.status,
    this.billDiscountPercent = '0',
    this.billDiscountSource = '',
    this.freightAmount = '0',
    this.freightWaivedAmount = '0',
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

  /// The optimistic-concurrency version this record was read at, sent back
  /// as `If-Match` on save so a concurrent edit is refused rather than
  /// silently overwritten. Zero means the server published none, and the
  /// save then carries no precondition.
  final int version;
  final String customerId;
  final String branchId;
  final String warehouseId;
  final String quotationNumber;
  final String quotationDate;

  /// The last day the quoted prices stand.
  final String validUntil;
  final String createdAt;
  final String customerReference;
  final String paymentTerms;
  final String deliveryTerms;
  final String status;
  /// What was taken off the whole offer, as a rate. Zero means none.
  final String billDiscountPercent;

  /// Where that came from: `typed`, `promotion` or `none`. Empty on an offer
  /// saved before the server recorded it, when it could only have been typed.
  final String billDiscountSource;

  /// What the customer is charged for delivery, after any free-shipping
  /// offer took its share off.
  final String freightAmount;

  /// What a free-shipping offer took off the delivery charge that was asked
  /// for. The charge asked is [freightAmount] plus this.
  final String freightWaivedAmount;

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
        version: (json['version'] as num?)?.toInt() ?? 0,
        customerId: stringValue(json['customer_id']),
        branchId: stringValue(json['branch_id']),
        warehouseId: stringValue(json['warehouse_id']),
        quotationNumber: stringValue(json['quotation_number']),
        quotationDate: stringValue(json['quotation_date']),
        validUntil: stringValue(json['valid_until']),
        createdAt: stringValue(json['created_at']),
        customerReference: stringValue(json['customer_reference']),
        paymentTerms: stringValue(json['payment_terms']),
        deliveryTerms: stringValue(json['delivery_terms']),
        status: stringValue(json['status']),
        billDiscountPercent:
            stringValue(json['bill_discount_percent']).isEmpty
                ? '0'
                : stringValue(json['bill_discount_percent']),
        billDiscountSource: stringValue(json['bill_discount_source']),
        freightAmount: stringValue(json['freight_amount']).isEmpty
            ? '0'
            : stringValue(json['freight_amount']),
        freightWaivedAmount: stringValue(json['freight_waived_amount']).isEmpty
            ? '0'
            : stringValue(json['freight_waived_amount']),
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

/// One line's companions in a priced preview: what this customer last paid
/// for the product, and the stock free to promise where the offer ships from.
class QuotationPreviewLine {
  const QuotationPreviewLine({
    required this.lineNumber,
    required this.productId,
    required this.lastPrice,
    required this.lastInvoiceNumber,
    required this.lastInvoiceDate,
    required this.availableQuantity,
  });

  final int lineNumber;
  final String productId;

  /// Empty when the customer has never been billed for the product.
  final String lastPrice;
  final String lastInvoiceNumber;
  final String lastInvoiceDate;
  final String availableQuantity;

  factory QuotationPreviewLine.fromJson(Map<String, dynamic> json) =>
      QuotationPreviewLine(
        lineNumber: (json['line_number'] as num?)?.toInt() ?? 0,
        productId: '${json['product_id'] ?? ''}',
        lastPrice: json['last_price'] == null ? '' : '${json['last_price']}',
        lastInvoiceNumber: '${json['last_invoice_number'] ?? ''}',
        lastInvoiceDate: '${json['last_invoice_date'] ?? ''}',
        availableQuantity: '${json['available_quantity'] ?? '0'}',
      );
}

/// An offer priced exactly as saving it would, from
/// `POST /api/v1/quotations/preview`: the draft the save would store (its
/// rates, discounts, tax and number), how its tax splits, and each line's
/// companions. Nothing is saved.
class QuotationPreviewRecord {
  const QuotationPreviewRecord({
    required this.quotation,
    required this.interstate,
    required this.lines,
  });

  final Quotation quotation;

  /// IGST across states; CGST and SGST within one.
  final bool interstate;
  final List<QuotationPreviewLine> lines;

  factory QuotationPreviewRecord.fromJson(Map<String, dynamic> json) =>
      QuotationPreviewRecord(
        quotation: Quotation.fromJson(
          Map<String, dynamic>.from(json['quotation'] as Map? ?? const {}),
        ),
        interstate: json['interstate'] == true,
        lines: [
          for (final dynamic line in json['lines'] as List? ?? const [])
            if (line is Map)
              QuotationPreviewLine.fromJson(Map<String, dynamic>.from(line)),
        ],
      );
}
