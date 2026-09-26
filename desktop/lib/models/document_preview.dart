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
    required this.availableQuantity,
  });

  final int lineNumber;
  final String productId;

  /// Empty when the customer has never been billed for the product.
  final String lastPrice;
  final String lastInvoiceNumber;
  final String lastInvoiceDate;
  final String availableQuantity;

  factory DocumentPreviewLine.fromJson(Map<String, dynamic> json) =>
      DocumentPreviewLine(
        lineNumber: (json['line_number'] as num?)?.toInt() ?? 0,
        productId: '${json['product_id'] ?? ''}',
        lastPrice: json['last_price'] == null ? '' : '${json['last_price']}',
        lastInvoiceNumber: '${json['last_invoice_number'] ?? ''}',
        lastInvoiceDate: '${json['last_invoice_date'] ?? ''}',
        availableQuantity: '${json['available_quantity'] ?? '0'}',
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
  });

  final PurchaseOrder order;
  final bool interstate;
  final List<DocumentPreviewLine> lines;

  factory PurchaseOrderPreviewRecord.fromJson(Map<String, dynamic> json) =>
      PurchaseOrderPreviewRecord(
        order: PurchaseOrder.fromJson(
          Map<String, dynamic>.from(json['order'] as Map? ?? const {}),
        ),
        interstate: json['interstate'] == true,
        lines: _previewLines(json['lines']),
      );
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

List<DocumentPreviewLine> _previewLines(dynamic raw) => [
      for (final dynamic line in raw as List? ?? const [])
        if (line is Map)
          DocumentPreviewLine.fromJson(Map<String, dynamic>.from(line)),
    ];
