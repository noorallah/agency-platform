import 'entities.dart';

/// One line of a purchase requisition (BUY-7): what is wanted, and optionally
/// who should supply it.
class RequisitionLine {
  const RequisitionLine({
    this.id = '',
    required this.productId,
    this.productCode = '',
    this.productName = '',
    required this.quantity,
    this.vendorId = '',
    this.remarks = '',
    this.purchaseOrderId = '',
  });

  factory RequisitionLine.fromJson(Json json) => RequisitionLine(
        id: stringValue(json['id']),
        productId: stringValue(json['product_id']),
        productCode: stringValue(json['product_code']),
        productName: stringValue(json['product_name']),
        quantity: stringValue(json['quantity']),
        vendorId: stringValue(json['vendor_id']),
        remarks: stringValue(json['remarks']),
        purchaseOrderId: stringValue(json['purchase_order_id']),
      );

  final String id;
  final String productId;
  final String productCode;
  final String productName;
  final String quantity;
  final String vendorId;
  final String remarks;

  /// The draft order this line was converted into, once it has been.
  final String purchaseOrderId;
}

/// A request to buy, raised by whoever sees the need and approved before it
/// becomes purchase orders.
class PurchaseRequisition {
  const PurchaseRequisition({
    required this.id,
    required this.branchId,
    required this.warehouseId,
    required this.number,
    required this.date,
    this.neededBy = '',
    required this.status,
    this.remarks = '',
    this.cancelReason = '',
    this.version = 0,
    this.lines = const [],
  });

  factory PurchaseRequisition.fromJson(Json json) => PurchaseRequisition(
        id: stringValue(json['id']),
        branchId: stringValue(json['branch_id']),
        warehouseId: stringValue(json['warehouse_id']),
        number: stringValue(json['requisition_number']),
        date: stringValue(json['requisition_date']),
        neededBy: stringValue(json['needed_by']),
        status: stringValue(json['status']),
        remarks: stringValue(json['remarks']),
        cancelReason: stringValue(json['cancel_reason']),
        version: json['version'] is int ? json['version'] as int : 0,
        lines: [
          for (final dynamic line
              in json['lines'] is List ? json['lines'] as List : const [])
            if (line is Map)
              RequisitionLine.fromJson(Map<String, dynamic>.from(line)),
        ],
      );

  final String id;
  final String branchId;
  final String warehouseId;
  final String number;
  final String date;
  final String neededBy;

  /// `DRAFT`, `SUBMITTED`, `APPROVED`, `ORDERED` or `CANCELLED`.
  final String status;
  final String remarks;
  final String cancelReason;
  final int version;
  final List<RequisitionLine> lines;

  bool get isEditable => status == 'DRAFT' || status == 'SUBMITTED';
}
