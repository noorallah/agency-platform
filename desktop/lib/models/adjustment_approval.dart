import 'entities.dart';

/// The largest stock adjustment or write-off a role may post directly
/// (STK-8). Above it the movement goes to someone with a higher limit.
class RoleAdjustmentLimit {
  const RoleAdjustmentLimit({required this.roleCode, required this.maxValue});

  final String roleCode;

  /// An amount, as the server states it.
  final String maxValue;

  factory RoleAdjustmentLimit.fromJson(Json json) => RoleAdjustmentLimit(
        roleCode: stringValue(json['role_code']),
        maxValue: stringValue(json['max_value']),
      );

  Json toJson() => <String, dynamic>{
        'role_code': roleCode,
        'max_value': maxValue,
      };
}

/// A large adjustment or write-off waiting for somebody with a high enough
/// limit (STK-8). Nothing has moved until it is approved.
class AdjustmentRequestRecord {
  const AdjustmentRequestRecord({
    required this.id,
    required this.kind,
    required this.productId,
    required this.warehouseId,
    required this.quantity,
    required this.estimatedValue,
    required this.status,
    required this.requestedAt,
    this.decisionRemarks = '',
    this.version = 0,
  });

  factory AdjustmentRequestRecord.fromJson(Json json) =>
      AdjustmentRequestRecord(
        id: stringValue(json['id']),
        kind: stringValue(json['kind']),
        productId: stringValue(json['product_id']),
        warehouseId: stringValue(json['warehouse_id']),
        quantity: stringValue(json['quantity']),
        estimatedValue: stringValue(json['estimated_value']),
        status: stringValue(json['status']),
        requestedAt: stringValue(json['requested_at']),
        decisionRemarks: stringValue(json['decision_remarks']),
        version: (json['version'] as num?)?.toInt() ?? 0,
      );

  final String id;

  /// `ADJUSTMENT` or `WRITE_OFF`.
  final String kind;
  final String productId;
  final String warehouseId;
  final String quantity;
  final String estimatedValue;

  /// `PENDING`, `APPROVED` or `REJECTED`.
  final String status;
  final String requestedAt;
  final String decisionRemarks;
  final int version;

  bool get isPending => status == 'PENDING';
  String get kindLabel => kind == 'WRITE_OFF' ? 'Write-off' : 'Adjustment';
}
