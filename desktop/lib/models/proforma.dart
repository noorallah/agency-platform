// A statement of what an order will be charged, issued before the bill.

import 'entities.dart';

/// One line of a proforma, as it was snapshotted from the order.
class ProformaLine {
  const ProformaLine({
    required this.lineNumber,
    required this.productName,
    required this.description,
    required this.quantity,
    required this.freeQuantity,
    required this.unitPrice,
    required this.discountAmount,
    required this.taxAmount,
    required this.netAmount,
  });

  factory ProformaLine.fromJson(Json json) => ProformaLine(
        lineNumber: (json['line_number'] as num?)?.toInt() ?? 0,
        productName: stringValue(json['product_name']),
        description: stringValue(json['description']),
        quantity: _decimal(json['quantity']),
        freeQuantity: _decimal(json['free_quantity']),
        unitPrice: _decimal(json['unit_price']),
        discountAmount: _decimal(json['discount_amount']),
        taxAmount: _decimal(json['tax_amount']),
        netAmount: _decimal(json['net_amount']),
      );

  final int lineNumber;
  final String productName;
  final String description;
  final double quantity;

  /// Goods stated at nil value. Outside the gross and outside the tax, and a
  /// document that dropped them would understate what is being shipped.
  final double freeQuantity;
  final double unitPrice;
  final double discountAmount;
  final double taxAmount;
  final double netAmount;
}

/// One proforma, and everything it states.
class ProformaRecord {
  const ProformaRecord({
    required this.id,
    required this.proformaNumber,
    required this.proformaDate,
    required this.validUntil,
    required this.status,
    required this.customerName,
    required this.salesOrderNumber,
    required this.paymentTerms,
    required this.deliveryTerms,
    required this.remarks,
    required this.subtotal,
    required this.taxTotal,
    required this.grandTotal,
    required this.isTaxInvoice,
    required this.supersedesId,
    required this.lines,
    required this.version,
  });

  factory ProformaRecord.fromJson(Json json) => ProformaRecord(
        id: stringValue(json['id']),
        proformaNumber: stringValue(json['proforma_number']),
        proformaDate: stringValue(json['proforma_date']),
        validUntil: stringValue(json['valid_until']),
        status: stringValue(json['status']),
        customerName: stringValue(json['customer_name']),
        salesOrderNumber: stringValue(json['sales_order_number']),
        paymentTerms: stringValue(json['payment_terms']),
        deliveryTerms: stringValue(json['delivery_terms']),
        remarks: stringValue(json['remarks']),
        subtotal: _decimal(json['subtotal']),
        taxTotal: _decimal(json['tax_total']),
        grandTotal: _decimal(json['grand_total']),
        // Defaults to false rather than true: a document wrongly presented as
        // a tax invoice is the one mistake this screen exists to prevent.
        isTaxInvoice: json['is_tax_invoice'] == true,
        supersedesId: stringValue(json['supersedes_id']),
        lines: (json['lines'] as List<dynamic>? ?? const [])
            .whereType<Map>()
            .map((item) => ProformaLine.fromJson(Map<String, dynamic>.from(item)))
            .toList(),
        version: (json['version'] as num?)?.toInt() ?? 0,
      );

  final String id;
  final String proformaNumber;
  final String proformaDate;
  final String validUntil;
  final String status;
  final String customerName;
  final String salesOrderNumber;
  final String paymentTerms;
  final String deliveryTerms;
  final String remarks;
  final double subtotal;
  final double taxTotal;
  final double grandTotal;
  final bool isTaxInvoice;
  final String supersedesId;
  final List<ProformaLine> lines;
  final int version;

  bool get isDraft => status == 'DRAFT';
  bool get isIssued => status == 'ISSUED';
  bool get isCancelled => status == 'CANCELLED';
}

double _decimal(Object? value) => double.tryParse('${value ?? 0}') ?? 0;
