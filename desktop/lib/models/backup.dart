import 'entities.dart';

/// One store's file inside a backup (`GET /api/v1/backups`).
class BackupStore {
  const BackupStore({
    required this.label,
    required this.database,
    required this.schemaName,
    required this.file,
    required this.sizeBytes,
    required this.tables,
    required this.revision,
    required this.outcome,
    required this.detail,
  });

  final String label, database, schemaName, revision;

  /// `ok`, `skipped` or `failed`.
  final String outcome;
  final String? file, detail;
  final int sizeBytes, tables;

  factory BackupStore.fromJson(Json json) => BackupStore(
        label: stringValue(json['label']),
        database: stringValue(json['database']),
        schemaName: stringValue(json['schema_name']),
        file: json['file'] as String?,
        sizeBytes: _intOr(json['size_bytes']) ?? 0,
        tables: _intOr(json['tables']) ?? 0,
        revision: stringValue(json['revision']),
        outcome: stringValue(json['outcome']),
        detail: json['detail'] as String?,
      );
}

/// A backup folder on the server's disk.
class BackupEntry {
  const BackupEntry({
    required this.kind,
    required this.name,
    required this.path,
    required this.createdAt,
    required this.complete,
    required this.sizeBytes,
    required this.files,
    required this.applicationVersion,
    required this.requestedBy,
    required this.stores,
  });

  /// `manual`, `daily` or `pre-upgrade`.
  final String kind;
  final String name, path;
  final String? createdAt, applicationVersion, requestedBy;

  /// Null when the server cannot read the folder.
  final bool? complete;
  final int? sizeBytes, files;
  final List<BackupStore> stores;

  factory BackupEntry.fromJson(Json json) => BackupEntry(
        kind: stringValue(json['kind']),
        name: stringValue(json['name']),
        path: stringValue(json['path']),
        createdAt: json['created_at'] as String?,
        complete: json['complete'] as bool?,
        sizeBytes: _intOr(json['size_bytes']),
        files: _intOr(json['files']),
        applicationVersion: json['application_version'] as String?,
        requestedBy: json['requested_by'] as String?,
        stores: _stores(json['stores']),
      );
}

/// The backup being taken, or the last one that was.
class BackupRun {
  const BackupRun({
    required this.status,
    required this.requestedBy,
    required this.startedAt,
    required this.finishedAt,
    required this.folder,
    required this.message,
    required this.stores,
  });

  /// `idle`, `running`, `succeeded` or `failed`.
  final String status;
  final String? requestedBy, startedAt, finishedAt, folder, message;
  final List<BackupStore> stores;

  bool get running => status == 'running';

  factory BackupRun.fromJson(Json json) => BackupRun(
        status: stringValue(json['status']),
        requestedBy: json['requested_by'] as String?,
        startedAt: json['started_at'] as String?,
        finishedAt: json['finished_at'] as String?,
        folder: json['folder'] as String?,
        message: json['message'] as String?,
        stores: _stores(json['stores']),
      );
}

/// What `GET` and `POST /api/v1/backups` answer.
class BackupOverview {
  const BackupOverview({
    required this.backupDirectory,
    required this.keepManual,
    required this.run,
    required this.backups,
  });

  final String backupDirectory;
  final int keepManual;
  final BackupRun run;

  /// Newest first.
  final List<BackupEntry> backups;

  factory BackupOverview.fromJson(Json json) => BackupOverview(
        backupDirectory: stringValue(json['backup_directory']),
        keepManual: _intOr(json['keep_manual']) ?? 0,
        run: BackupRun.fromJson(
          json['run'] is Map
              ? Map<String, dynamic>.from(json['run'] as Map)
              : const <String, dynamic>{},
        ),
        backups: [
          if (json['backups'] is List)
            for (final dynamic row in json['backups'] as List)
              if (row is Map)
                BackupEntry.fromJson(Map<String, dynamic>.from(row)),
        ],
      );
}

List<BackupStore> _stores(dynamic value) => [
      if (value is List)
        for (final dynamic row in value)
          if (row is Map) BackupStore.fromJson(Map<String, dynamic>.from(row)),
    ];

int? _intOr(dynamic value) => value is num ? value.toInt() : null;
