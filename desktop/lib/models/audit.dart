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
    this.actorName = '',
    this.actorEmail = '',
    this.entityLabel = '',
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

  /// Who did it, in words. An audit trail's first question is "who", and an
  /// id answers it with a UUID -- the screen showed what changed, when, and
  /// from which address, and nothing about the person. Empty where the actor
  /// has since been deleted, or where nobody did it.
  final String actorName;
  final String actorEmail;

  /// Who it was done **to**, where the subject is a person. Empty for every
  /// other entity type, and the screen then says nothing rather than falling
  /// back to the id.
  final String entityLabel;

  /// The actor as somebody would name them, falling back through what is
  /// known. Never the raw id: an id on screen is what this exists to replace.
  String get actorLabel {
    if (actorName.isNotEmpty && actorEmail.isNotEmpty) {
      return '$actorName · $actorEmail';
    }
    if (actorName.isNotEmpty) return actorName;
    if (actorEmail.isNotEmpty) return actorEmail;
    return actorId.isEmpty ? 'the system' : 'a deleted user';
  }
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
      actorName: stringValue(json['actor_name']),
      actorEmail: stringValue(json['actor_email']),
      entityLabel: stringValue(json['entity_label']),
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
