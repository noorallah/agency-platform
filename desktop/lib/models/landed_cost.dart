import 'entities.dart';

/// One freight or clearing bill on a landed cost voucher (BUY-16).
class LandedCostCharge {
  const LandedCostCharge({
    required this.description,
    required this.amount,
    this.lineNumber = 0,
    this.vendorId = '',
    this.vendorName = '',
    this.billReference = '',
  });

  final int lineNumber;
  final String description;
  final String amount;
  final String vendorId;
  final String vendorName;
  final String billReference;

  factory LandedCostCharge.fromJson(Json json) => LandedCostCharge(
        lineNumber: (json['line_number'] as num?)?.toInt() ?? 0,
        description: stringValue(json['description']),
        amount: _orZero(json['amount']),
        vendorId: stringValue(json['vendor_id']),
        vendorName: stringValue(json['vendor_name']),
        billReference: stringValue(json['bill_reference']),
      );
}

/// What one receipt line took of the charges: [amount] in all, split into the
/// part added to stock on hand and the part for goods already sold.
class LandedCostAllocation {
  const LandedCostAllocation({
    required this.grnNumber,
    required this.productName,
    this.goodsReceiptId = '',
    this.goodsReceiptLineId = '',
    this.productId = '',
    this.quantity = '0',
    this.basisMeasure = '0',
    this.amount = '0',
    this.inventoryAmount = '0',
    this.cogsAmount = '0',
  });

  final String goodsReceiptId;
  final String grnNumber;
  final String goodsReceiptLineId;
  final String productId;
  final String productName;
  final String quantity;
  final String basisMeasure;
  final String amount;
  final String inventoryAmount;
  final String cogsAmount;

  factory LandedCostAllocation.fromJson(Json json) => LandedCostAllocation(
        goodsReceiptId: stringValue(json['goods_receipt_id']),
        grnNumber: stringValue(json['grn_number']),
        goodsReceiptLineId: stringValue(json['goods_receipt_line_id']),
        productId: stringValue(json['product_id']),
        productName: stringValue(json['product_name']),
        quantity: _orZero(json['quantity']),
        basisMeasure: _orZero(json['basis_measure']),
        amount: _orZero(json['amount']),
        inventoryAmount: _orZero(json['inventory_amount']),
        cogsAmount: _orZero(json['cogs_amount']),
      );
}

/// A landed cost voucher: charges spread over received goods (BUY-16).
class LandedCost {
  const LandedCost({
    required this.id,
    required this.voucherNumber,
    required this.voucherDate,
    required this.basis,
    required this.status,
    this.totalAmount = '0',
    this.inventoryAmount = '0',
    this.cogsAmount = '0',
    this.remarks = '',
    this.cancelReason = '',
    this.version = 0,
    this.charges = const <LandedCostCharge>[],
    this.allocations = const <LandedCostAllocation>[],
  });

  final String id;
  final String voucherNumber;
  final String voucherDate;

  /// `VALUE`, `QUANTITY` or `WEIGHT`.
  final String basis;

  /// `POSTED` or `CANCELLED`.
  final String status;
  final String totalAmount;

  /// The share added to stock on hand.
  final String inventoryAmount;

  /// The share for goods already sold.
  final String cogsAmount;
  final String remarks;
  final String cancelReason;
  final int version;
  final List<LandedCostCharge> charges;
  final List<LandedCostAllocation> allocations;

  bool get isPosted => status == 'POSTED';
  bool get isCancelled => status == 'CANCELLED';

  factory LandedCost.fromJson(Json json) => LandedCost(
        id: stringValue(json['id']),
        voucherNumber: stringValue(json['voucher_number']),
        voucherDate: stringValue(json['voucher_date']),
        basis: stringValue(json['basis']),
        status: stringValue(json['status']),
        totalAmount: _orZero(json['total_amount']),
        inventoryAmount: _orZero(json['inventory_amount']),
        cogsAmount: _orZero(json['cogs_amount']),
        remarks: stringValue(json['remarks']),
        cancelReason: stringValue(json['cancel_reason']),
        version: (json['version'] as num?)?.toInt() ?? 0,
        charges: [
          for (final dynamic row
              in json['charges'] is List ? json['charges'] as List : const [])
            if (row is Map)
              LandedCostCharge.fromJson(Map<String, dynamic>.from(row)),
        ],
        allocations: [
          for (final dynamic row in json['allocations'] is List
              ? json['allocations'] as List
              : const [])
            if (row is Map)
              LandedCostAllocation.fromJson(Map<String, dynamic>.from(row)),
        ],
      );
}

String _orZero(dynamic value) {
  final String text = stringValue(value);
  return text.isEmpty ? '0' : text;
}
