import 'entities.dart';

/// One goods-receipt line held for inspection (BUY-9): pending until somebody
/// passes or rejects the quantity, done afterwards with the split recorded.
class QualityInspection {
  const QualityInspection({
    required this.goodsReceiptId,
    required this.grnNumber,
    required this.receiptDate,
    required this.vendorName,
    required this.lineId,
    required this.lineNumber,
    required this.productCode,
    required this.productName,
    required this.batchNumber,
    required this.quantity,
    required this.status,
    this.passedQuantity = '',
    this.rejectedQuantity = '',
    this.rejectedAction = '',
    this.inspectedAt = '',
    this.remarks = '',
  });

  final String goodsReceiptId;
  final String grnNumber;
  final String receiptDate;
  final String vendorName;
  final String lineId;
  final int lineNumber;
  final String productCode;
  final String productName;
  final String batchNumber;
  final String quantity;

  /// `PENDING` or `DONE`.
  final String status;
  final String passedQuantity;
  final String rejectedQuantity;

  /// `WRITE_OFF`, `RETURN`, or empty when nothing was rejected.
  final String rejectedAction;
  final String inspectedAt;
  final String remarks;

  bool get isPending => status == 'PENDING';

  /// The row's own identity: a receipt can hold several lines.
  String get key => '$goodsReceiptId/$lineId';

  factory QualityInspection.fromJson(Json json) => QualityInspection(
        goodsReceiptId: stringValue(json['goods_receipt_id']),
        grnNumber: stringValue(json['grn_number']),
        receiptDate: stringValue(json['receipt_date']),
        vendorName: stringValue(json['vendor_name']),
        lineId: stringValue(json['line_id']),
        lineNumber: (json['line_number'] as num?)?.toInt() ?? 0,
        productCode: stringValue(json['product_code']),
        productName: stringValue(json['product_name']),
        batchNumber: stringValue(json['batch_number']),
        quantity: stringValue(json['quantity']),
        status: stringValue(json['status']),
        passedQuantity: stringValue(json['passed_quantity']),
        rejectedQuantity: stringValue(json['rejected_quantity']),
        rejectedAction: stringValue(json['rejected_action']),
        inspectedAt: stringValue(json['inspected_at']),
        remarks: stringValue(json['remarks']),
      );
}
