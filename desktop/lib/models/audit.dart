import 'entities.dart';

/// One recorded mutation.
///
/// The trail is **per store**, not central: platform administration is written
/// to the platform trail, and every firm-owned change to that firm's own. No
/// single query answers "everything that happened", which is deliberate -- a
/// firm with a dedicated database has to hold its own history for the isolation
/// and per-firm restore guarantees to mean anything.
class AuditLogEntry {
  const AuditLogEntry({
    required this.id,
    required this.createdAt,
    required this.action,
    required this.entityType,
    required this.entityId,
    required this.actorId,
    required this.firmId,
    required this.beforeData,
    required this.afterData,
    required this.ipAddress,
    required this.applicationVersion,
  });

  final String id;
  final String createdAt;
  final String action;
  final String entityType;
  final String entityId;
  final String actorId;
  final String firmId;
  final Map<String, dynamic> beforeData;
  final Map<String, dynamic> afterData;
  final String ipAddress;
  final String applicationVersion;

  /// Whether this row records a change rather than a creation or deletion.
  bool get hasBothSides => beforeData.isNotEmpty && afterData.isNotEmpty;

  /// The fields that actually differ, which is what somebody is looking for.
  ///
  /// An audit row can carry a dozen unchanged fields on both sides; showing
  /// all of them buries the one that moved.
  List<AuditFieldChange> get changes {
    final Set<String> keys = {...beforeData.keys, ...afterData.keys};
    final List<AuditFieldChange> rows = [];
    for (final String key in keys.toList()..sort()) {
      final String before = '${beforeData[key] ?? ''}';
      final String after = '${afterData[key] ?? ''}';
      if (before == after) continue;
      rows.add(AuditFieldChange(field: key, before: before, after: after));
    }
    return rows;
  }

  factory AuditLogEntry.fromJson(Json json) {
    Map<String, dynamic> side(dynamic value) =>
        value is Map ? Map<String, dynamic>.from(value) : <String, dynamic>{};
    return AuditLogEntry(
      id: stringValue(json['id']),
      createdAt: stringValue(json['created_at']),
      action: stringValue(json['action']),
      entityType: stringValue(json['entity_type']),
      entityId: stringValue(json['entity_id']),
      actorId: stringValue(json['actor_id']),
      firmId: stringValue(json['firm_id']),
      beforeData: side(json['before_data']),
      afterData: side(json['after_data']),
      ipAddress: stringValue(json['ip_address']),
      applicationVersion: stringValue(json['application_version']),
    );
  }
}

/// One field that changed, and what it changed from and to.
class AuditFieldChange {
  const AuditFieldChange({
    required this.field,
    required this.before,
    required this.after,
  });

  final String field;
  final String before;
  final String after;
}
