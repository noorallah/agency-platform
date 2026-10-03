import 'entities.dart';

/// One reason a firm gives for taking stock off the books (STK-7), and the
/// ledger account the value goes to.
///
/// The six the platform ships (damage, expiry, loss, internal use, staff,
/// display) are system rows: they can be re-pointed or switched off, but
/// neither renamed in code nor deleted.
class AdjustmentReasonRecord {
  const AdjustmentReasonRecord({
    required this.id,
    required this.code,
    required this.name,
    this.ledgerAccountId = '',
    this.ledgerAccountName = '',
    this.isSystem = false,
    this.isActive = true,
    this.version = 0,
  });

  final String id;
  final String code;
  final String name;

  /// Empty means the firm's default inventory adjustment account.
  final String ledgerAccountId;
  final String ledgerAccountName;
  final bool isSystem;
  final bool isActive;
  final int version;

  factory AdjustmentReasonRecord.fromJson(Json json) => AdjustmentReasonRecord(
        id: stringValue(json['id']),
        code: stringValue(json['code']),
        name: stringValue(json['name']),
        ledgerAccountId: stringValue(json['ledger_account_id']),
        ledgerAccountName: stringValue(json['ledger_account_name']),
        isSystem: json['is_system'] as bool? ?? false,
        isActive: json['is_active'] as bool? ?? true,
        version: (json['version'] as num?)?.toInt() ?? 0,
      );
}
