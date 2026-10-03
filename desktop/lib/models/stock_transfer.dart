import 'entities.dart';

/// One line of a stock transfer (STK-1): what was sent, what arrived and what
/// of that arrived damaged.
class StockTransferLineRecord {
  const StockTransferLineRecord({
    required this.lineNumber,
    required this.productId,
    this.productCode = '',
    this.productName = '',
    this.batchId = '',
    this.batchNumber = '',
    this.quantity = '',
    this.receivedQuantity = '',
    this.damagedQuantity = '',
    this.shortQuantity = '',
    this.unitCost = '',
    this.remarks = '',
  });

  final int lineNumber;
  final String productId;
  final String productCode;
  final String productName;
  final String batchId;
  final String batchNumber;
  final String quantity;
  final String receivedQuantity;
  final String damagedQuantity;
  final String shortQuantity;
  final String unitCost;
  final String remarks;

  String get productLabel =>
      productCode.isEmpty ? productName : '$productCode - $productName';

  factory StockTransferLineRecord.fromJson(Json json) =>
      StockTransferLineRecord(
        lineNumber: (json['line_number'] as num?)?.toInt() ?? 0,
        productId: stringValue(json['product_id']),
        productCode: stringValue(json['product_code']),
        productName: stringValue(json['product_name']),
        batchId: stringValue(json['batch_id']),
        batchNumber: stringValue(json['batch_number']),
        quantity: stringValue(json['quantity']),
        receivedQuantity: stringValue(json['received_quantity']),
        damagedQuantity: stringValue(json['damaged_quantity']),
        shortQuantity: stringValue(json['short_quantity']),
        unitCost: stringValue(json['unit_cost']),
        remarks: stringValue(json['remarks']),
      );
}

/// A stock transfer between two warehouses (STK-1): draft, dispatched,
/// received or cancelled.
class StockTransferRecord {
  const StockTransferRecord({
    required this.id,
    required this.transferNumber,
    required this.transferDate,
    this.fromBranchId = '',
    this.fromWarehouseId = '',
    this.fromWarehouseName = '',
    this.toBranchId = '',
    this.toWarehouseId = '',
    this.toWarehouseName = '',
    this.status = 'DRAFT',
    this.dispatchedOn = '',
    this.receivedOn = '',
    this.vehicleNumber = '',
    this.transporterName = '',
    this.dispatchedValue = '',
    this.shortageValue = '',
    this.remarks = '',
    this.receiptRemarks = '',
    this.cancelReason = '',
    this.version = 0,
    this.lines = const [],
  });

  final String id;
  final String transferNumber;
  final String transferDate;
  final String fromBranchId;
  final String fromWarehouseId;
  final String fromWarehouseName;
  final String toBranchId;
  final String toWarehouseId;
  final String toWarehouseName;

  /// `DRAFT`, `DISPATCHED`, `RECEIVED` or `CANCELLED`.
  final String status;
  final String dispatchedOn;
  final String receivedOn;
  final String vehicleNumber;
  final String transporterName;
  final String dispatchedValue;
  final String shortageValue;
  final String remarks;
  final String receiptRemarks;
  final String cancelReason;
  final int version;
  final List<StockTransferLineRecord> lines;

  bool get isDraft => status == 'DRAFT';
  bool get isDispatched => status == 'DISPATCHED';
  bool get isReceived => status == 'RECEIVED';
  bool get isCancelled => status == 'CANCELLED';

  /// A challan exists once the goods have left.
  bool get hasChallan => isDispatched || isReceived;

  String get statusLabel => switch (status) {
        'DRAFT' => 'Draft',
        'DISPATCHED' => 'In transit',
        'RECEIVED' => 'Received',
        'CANCELLED' => 'Cancelled',
        _ => status,
      };

  factory StockTransferRecord.fromJson(Json json) => StockTransferRecord(
        id: stringValue(json['id']),
        transferNumber: stringValue(json['transfer_number']),
        transferDate: stringValue(json['transfer_date']),
        fromBranchId: stringValue(json['from_branch_id']),
        fromWarehouseId: stringValue(json['from_warehouse_id']),
        fromWarehouseName: stringValue(json['from_warehouse_name']),
        toBranchId: stringValue(json['to_branch_id']),
        toWarehouseId: stringValue(json['to_warehouse_id']),
        toWarehouseName: stringValue(json['to_warehouse_name']),
        status: stringValue(json['status']),
        dispatchedOn: stringValue(json['dispatched_on']),
        receivedOn: stringValue(json['received_on']),
        vehicleNumber: stringValue(json['vehicle_number']),
        transporterName: stringValue(json['transporter_name']),
        dispatchedValue: stringValue(json['dispatched_value']),
        shortageValue: stringValue(json['shortage_value']),
        remarks: stringValue(json['remarks']),
        receiptRemarks: stringValue(json['receipt_remarks']),
        cancelReason: stringValue(json['cancel_reason']),
        version: (json['version'] as num?)?.toInt() ?? 0,
        lines: [
          for (final dynamic line in json['lines'] as List<dynamic>? ?? [])
            StockTransferLineRecord.fromJson(line as Json),
        ],
      );
}
