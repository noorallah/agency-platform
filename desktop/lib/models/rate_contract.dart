import 'entities.dart';

List<T> _list<T>(dynamic raw, T Function(Json) parse) => [
      for (final dynamic item in raw is List ? raw : const [])
        if (item is Map) parse(Map<String, dynamic>.from(item)),
    ];

int _int(dynamic value) => value is num ? value.toInt() : 0;

/// One product on a supplier rate contract (PG-9).
class RateContractLine {
  const RateContractLine({
    this.id = '',
    this.lineNumber = 0,
    required this.productId,
    this.productCode = '',
    this.productName = '',
    this.uomId = '',
    this.rate = '',
    this.discountPercent = '',
    this.contractedQuantity = '',
    this.drawnQuantity = '',
    this.remainingQuantity = '',
    this.notes = '',
  });

  factory RateContractLine.fromJson(Json json) => RateContractLine(
        id: stringValue(json['id']),
        lineNumber: _int(json['line_number']),
        productId: stringValue(json['product_id']),
        productCode: stringValue(json['product_code']),
        productName: stringValue(json['product_name']),
        uomId: stringValue(json['uom_id']),
        rate: stringValue(json['rate']),
        discountPercent: stringValue(json['discount_percent']),
        contractedQuantity: stringValue(json['contracted_quantity']),
        drawnQuantity: stringValue(json['drawn_quantity']),
        remainingQuantity: stringValue(json['remaining_quantity']),
        notes: stringValue(json['notes']),
      );

  final String id;
  final int lineNumber;
  final String productId;
  final String productCode;
  final String productName;
  final String uomId;
  final String rate;
  final String discountPercent;

  /// Empty when the contract sets no quantity ceiling on this line.
  final String contractedQuantity;
  final String drawnQuantity;

  /// Empty when there is no contracted quantity.
  final String remainingQuantity;
  final String notes;
}

/// A rate agreed with a supplier for a window of dates.
class RateContract {
  const RateContract({
    required this.id,
    this.number = '',
    this.vendorId = '',
    this.vendorCode = '',
    this.vendorName = '',
    this.validFrom = '',
    this.validTo = '',
    this.reference = '',
    this.notes = '',
    required this.status,
    this.approvedAt = '',
    this.closedAt = '',
    this.cancelReason = '',
    this.version = 0,
    this.lines = const [],
  });

  factory RateContract.fromJson(Json json) => RateContract(
        id: stringValue(json['id']),
        number: stringValue(json['contract_number']),
        vendorId: stringValue(json['vendor_id']),
        vendorCode: stringValue(json['vendor_code']),
        vendorName: stringValue(json['vendor_name']),
        validFrom: stringValue(json['valid_from']),
        validTo: stringValue(json['valid_to']),
        reference: stringValue(json['reference']),
        notes: stringValue(json['notes']),
        status: stringValue(json['status']),
        approvedAt: stringValue(json['approved_at']),
        closedAt: stringValue(json['closed_at']),
        cancelReason: stringValue(json['cancel_reason']),
        version: _int(json['version']),
        lines: _list(json['lines'], RateContractLine.fromJson),
      );

  final String id;
  final String number;
  final String vendorId;
  final String vendorCode;
  final String vendorName;
  final String validFrom;
  final String validTo;
  final String reference;
  final String notes;
  final String status;
  final String approvedAt;
  final String closedAt;
  final String cancelReason;
  final int version;
  final List<RateContractLine> lines;

  bool get isDraft => status == 'DRAFT';
  bool get isActive => status == 'ACTIVE';
}

/// A purchase order line that draws on a contract line.
class RateContractRelease {
  const RateContractRelease({
    this.purchaseOrderId = '',
    this.poNumber = '',
    this.purchaseDate = '',
    this.orderStatus = '',
    this.countsAsDrawn = false,
    this.lineNumber = 0,
    this.productId = '',
    this.orderedQuantity = '',
    this.unitPrice = '',
  });

  factory RateContractRelease.fromJson(Json json) => RateContractRelease(
        purchaseOrderId: stringValue(json['purchase_order_id']),
        poNumber: stringValue(json['po_number']),
        purchaseDate: stringValue(json['purchase_date']),
        orderStatus: stringValue(json['order_status']),
        countsAsDrawn: json['counts_as_drawn'] == true,
        lineNumber: _int(json['line_number']),
        productId: stringValue(json['product_id']),
        orderedQuantity: stringValue(json['ordered_quantity']),
        unitPrice: stringValue(json['unit_price']),
      );

  final String purchaseOrderId;
  final String poNumber;
  final String purchaseDate;
  final String orderStatus;
  final bool countsAsDrawn;
  final int lineNumber;
  final String productId;
  final String orderedQuantity;
  final String unitPrice;
}
