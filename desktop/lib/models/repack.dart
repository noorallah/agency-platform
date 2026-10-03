import 'entities.dart';

/// One line of a repack (STK-4): stock consumed, or stock produced with the
/// value it carries.
class RepackLineRecord {
  const RepackLineRecord({
    required this.lineNumber,
    required this.kind,
    required this.productId,
    this.productCode = '',
    this.productName = '',
    this.batchId = '',
    this.quantity = '',
    this.value = '',
  });

  final int lineNumber;

  /// `CONSUME` or `PRODUCE`.
  final String kind;
  final String productId;
  final String productCode;
  final String productName;
  final String batchId;
  final String quantity;
  final String value;

  bool get isProduce => kind == 'PRODUCE';

  String get productLabel =>
      productCode.isEmpty ? productName : '$productCode - $productName';

  factory RepackLineRecord.fromJson(Json json) => RepackLineRecord(
        lineNumber: (json['line_number'] as num?)?.toInt() ?? 0,
        kind: stringValue(json['kind']),
        productId: stringValue(json['product_id']),
        productCode: stringValue(json['product_code']),
        productName: stringValue(json['product_name']),
        batchId: stringValue(json['batch_id']),
        quantity: stringValue(json['quantity']),
        value: stringValue(json['value']),
      );
}

/// A posted repack or bulk-breaking document (STK-4).
class RepackRecord {
  const RepackRecord({
    required this.id,
    required this.repackNumber,
    required this.repackDate,
    this.branchId = '',
    this.warehouseId = '',
    this.wastagePercent = '',
    this.consumedValue = '',
    this.wastageValue = '',
    this.status = 'POSTED',
    this.remarks = '',
    this.cancelReason = '',
    this.version = 0,
    this.lines = const [],
  });

  final String id;
  final String repackNumber;
  final String repackDate;
  final String branchId;
  final String warehouseId;
  final String wastagePercent;
  final String consumedValue;
  final String wastageValue;
  final String status;
  final String remarks;
  final String cancelReason;
  final int version;
  final List<RepackLineRecord> lines;

  bool get isCancelled => status == 'CANCELLED';

  Iterable<RepackLineRecord> get consumed =>
      lines.where((line) => !line.isProduce);

  Iterable<RepackLineRecord> get produced =>
      lines.where((line) => line.isProduce);

  factory RepackRecord.fromJson(Json json) => RepackRecord(
        id: stringValue(json['id']),
        repackNumber: stringValue(json['repack_number']),
        repackDate: stringValue(json['repack_date']),
        branchId: stringValue(json['branch_id']),
        warehouseId: stringValue(json['warehouse_id']),
        wastagePercent: stringValue(json['wastage_percent']),
        consumedValue: stringValue(json['consumed_value']),
        wastageValue: stringValue(json['wastage_value']),
        status: stringValue(json['status']),
        remarks: stringValue(json['remarks']),
        cancelReason: stringValue(json['cancel_reason']),
        version: (json['version'] as num?)?.toInt() ?? 0,
        lines: [
          for (final dynamic line in json['lines'] as List<dynamic>? ?? [])
            RepackLineRecord.fromJson(line as Json),
        ],
      );
}
