import 'purchase.dart';

/// One line's companions in a priced preview of any sales document: what this customer last paid
/// for the product, and the stock free to promise where the offer ships from.
class DocumentPreviewLine {
  const DocumentPreviewLine({
    required this.lineNumber,
    required this.productId,
    required this.lastPrice,
    required this.lastInvoiceNumber,
    required this.lastInvoiceDate,
    this.lastDiscountPercent = '',
    required this.availableQuantity,
    this.incomingQuantity = '0',
    this.outgoingQuantity = '0',
  });

  final int lineNumber;
  final String productId;

  /// Empty when the customer has never been billed for the product.
  final String lastPrice;
  final String lastInvoiceNumber;
  final String lastInvoiceDate;

  /// The discount rate on that bill's line (backlog 55 G6); empty with no bill.
  final String lastDiscountPercent;
  final String availableQuantity;

  /// On approved purchase orders for that warehouse, not yet received
  /// (STK-10).
  final String incomingQuantity;

  /// Promised there on open sales orders, not yet dispatched nor reserved.
  final String outgoingQuantity;

  factory DocumentPreviewLine.fromJson(Map<String, dynamic> json) =>
      DocumentPreviewLine(
        lineNumber: (json['line_number'] as num?)?.toInt() ?? 0,
        productId: '${json['product_id'] ?? ''}',
        lastPrice: json['last_price'] == null ? '' : '${json['last_price']}',
        lastInvoiceNumber: '${json['last_invoice_number'] ?? ''}',
        lastInvoiceDate: '${json['last_invoice_date'] ?? ''}',
        lastDiscountPercent: json['last_discount_percent'] == null
            ? ''
            : '${json['last_discount_percent']}',
        availableQuantity: '${json['available_quantity'] ?? '0'}',
        incomingQuantity: '${json['incoming_quantity'] ?? '0'}',
        outgoingQuantity: '${json['outgoing_quantity'] ?? '0'}',
      );
}

/// A sales order priced exactly as saving it would, from
/// `POST /api/v1/sales-orders/preview`: the order the save would store (as
/// the API answers it), how its tax splits, and each line's companions.
class SalesOrderPreviewRecord {
  const SalesOrderPreviewRecord({
    required this.order,
    required this.interstate,
    required this.lines,
  });

  final Map<String, dynamic> order;
  final bool interstate;
  final List<DocumentPreviewLine> lines;

  factory SalesOrderPreviewRecord.fromJson(Map<String, dynamic> json) =>
      SalesOrderPreviewRecord(
        order: Map<String, dynamic>.from(json['order'] as Map? ?? const {}),
        interstate: json['interstate'] == true,
        lines: _previewLines(json['lines']),
      );
}

/// A sales invoice priced exactly as saving it would, from
/// `POST /api/v1/sales-invoices/preview`.
class SalesInvoicePreviewRecord {
  const SalesInvoicePreviewRecord({
    required this.invoice,
    required this.interstate,
    required this.lines,
  });

  final Map<String, dynamic> invoice;
  final bool interstate;
  final List<DocumentPreviewLine> lines;

  factory SalesInvoicePreviewRecord.fromJson(Map<String, dynamic> json) =>
      SalesInvoicePreviewRecord(
        invoice: Map<String, dynamic>.from(json['invoice'] as Map? ?? const {}),
        interstate: json['interstate'] == true,
        lines: _previewLines(json['lines']),
      );
}

/// A purchase order priced exactly as saving it would, from
/// `POST /api/v1/purchases/preview`: the order as the save would store it,
/// how its tax splits, and each line's last price from this vendor and stock.
class PurchaseOrderPreviewRecord {
  const PurchaseOrderPreviewRecord({
    required this.order,
    required this.interstate,
    required this.lines,
    this.quantityHints = const <QuantityHint>[],
  });

  final PurchaseOrder order;
  final bool interstate;
  final List<DocumentPreviewLine> lines;

  /// Lines off the supplier's minimum or multiple (BUY-5).
  final List<QuantityHint> quantityHints;

  factory PurchaseOrderPreviewRecord.fromJson(Map<String, dynamic> json) =>
      PurchaseOrderPreviewRecord(
        order: PurchaseOrder.fromJson(
          Map<String, dynamic>.from(json['order'] as Map? ?? const {}),
        ),
        interstate: json['interstate'] == true,
        lines: _previewLines(json['lines']),
        quantityHints: <QuantityHint>[
          for (final dynamic item in json['quantity_hints'] as List? ?? const [])
            if (item is Map) QuantityHint.fromJson(Map<String, dynamic>.from(item)),
        ],
      );
}

/// What a supplier's minimum order quantity and order multiple say about one
/// order line (BUY-5), with the nearest quantity that satisfies them.
class QuantityHint {
  const QuantityHint({
    required this.lineNumber,
    required this.productId,
    required this.suggestedQuantity,
    required this.message,
  });

  final int lineNumber;
  final String productId;
  final String suggestedQuantity;
  final String message;

  factory QuantityHint.fromJson(Map<String, dynamic> json) => QuantityHint(
        lineNumber: int.tryParse('${json['line_number'] ?? ''}') ?? 0,
        productId: '${json['product_id'] ?? ''}',
        suggestedQuantity: _plainNumber('${json['suggested_quantity'] ?? ''}'),
        message: '${json['message'] ?? ''}',
      );
}

/// "120.0000" reads as "120"; anything else is left as the server wrote it.
String _plainNumber(String value) {
  final double? number = double.tryParse(value);
  if (number == null) return value;
  return number == number.roundToDouble()
      ? number.toStringAsFixed(0)
      : value.replaceFirst(RegExp(r'0+$'), '');
}

/// A supplier bill priced exactly as saving it would, from
/// `POST /api/v1/purchase-invoices/preview`: the bill as the save would store
/// it (with any duplicate-number warning), how its tax splits, and each
/// line's last price from this vendor and stock.
class PurchaseInvoicePreviewRecord {
  const PurchaseInvoicePreviewRecord({
    required this.invoice,
    required this.interstate,
    required this.lines,
  });

  final Map<String, dynamic> invoice;
  final bool interstate;
  final List<DocumentPreviewLine> lines;

  factory PurchaseInvoicePreviewRecord.fromJson(Map<String, dynamic> json) =>
      PurchaseInvoicePreviewRecord(
        invoice: Map<String, dynamic>.from(json['invoice'] as Map? ?? const {}),
        interstate: json['interstate'] == true,
        lines: _previewLines(json['lines']),
      );
}

/// A return to the supplier priced exactly as saving it would, from
/// `POST /api/v1/purchase-returns/preview`.
class PurchaseReturnPreviewRecord {
  const PurchaseReturnPreviewRecord({
    required this.purchaseReturn,
    required this.interstate,
    required this.lines,
  });

  final Map<String, dynamic> purchaseReturn;
  final bool interstate;
  final List<DocumentPreviewLine> lines;

  factory PurchaseReturnPreviewRecord.fromJson(Map<String, dynamic> json) =>
      PurchaseReturnPreviewRecord(
        purchaseReturn: Map<String, dynamic>.from(
          json['purchase_return'] as Map? ?? const {},
        ),
        interstate: json['interstate'] == true,
        lines: _previewLines(json['lines']),
      );
}

/// A sales return priced exactly as saving it would, from
/// `POST /api/v1/sales-returns/preview`: the credit the customer will be
/// given, how its tax splits, and each line's companions.
class SalesReturnPreviewRecord {
  const SalesReturnPreviewRecord({
    required this.salesReturn,
    required this.interstate,
    required this.lines,
  });

  final Map<String, dynamic> salesReturn;
  final bool interstate;
  final List<DocumentPreviewLine> lines;

  factory SalesReturnPreviewRecord.fromJson(Map<String, dynamic> json) =>
      SalesReturnPreviewRecord(
        salesReturn: Map<String, dynamic>.from(
          json['sales_return'] as Map? ?? const {},
        ),
        interstate: json['interstate'] == true,
        lines: _previewLines(json['lines']),
      );
}

List<DocumentPreviewLine> _previewLines(dynamic raw) => [
      for (final dynamic line in raw as List? ?? const [])
        if (line is Map)
          DocumentPreviewLine.fromJson(Map<String, dynamic>.from(line)),
    ];
