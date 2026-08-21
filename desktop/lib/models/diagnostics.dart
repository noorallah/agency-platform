import 'entities.dart';

/// One fault, with every occurrence of it collapsed into a single row.
///
/// The list endpoint groups by fingerprint rather than returning raw reports:
/// a thousand copies of one crash is one problem, and a screen that shows it
/// as a thousand rows cannot be triaged. The count is what ranks the work.
class ErrorReportGroup {
  const ErrorReportGroup({
    required this.fingerprint,
    required this.source,
    required this.errorType,
    required this.message,
    required this.occurrences,
    required this.firstSeen,
    required this.lastSeen,
    required this.appVersions,
  });

  final String fingerprint;

  /// `CLIENT` for a desktop crash, `SERVER` for one the backend recorded.
  final String source;
  final String errorType;
  final String message;
  final int occurrences;
  final String firstSeen;
  final String lastSeen;

  /// Every application version this fault has been seen on.
  ///
  /// One version means it may already be fixed; a list ending at the current
  /// build means it is still live.
  final List<String> appVersions;

  factory ErrorReportGroup.fromJson(Json json) => ErrorReportGroup(
        fingerprint: stringValue(json['fingerprint']),
        source: stringValue(json['source']),
        errorType: stringValue(json['error_type']),
        message: stringValue(json['message']),
        occurrences: (json['occurrences'] as num?)?.toInt() ?? 0,
        firstSeen: stringValue(json['first_seen']),
        lastSeen: stringValue(json['last_seen']),
        appVersions: stringList(json['app_versions']),
      );
}

/// One stored occurrence of a fault.
class ErrorReport {
  const ErrorReport({
    required this.id,
    required this.source,
    required this.fingerprint,
    required this.errorType,
    required this.message,
    required this.stackTrace,
    required this.appVersion,
    required this.buildNumber,
    required this.platformInfo,
    required this.firmId,
    required this.userId,
    required this.requestId,
    required this.contextLabel,
    required this.breadcrumbs,
    required this.occurredAt,
    required this.receivedAt,
  });

  final String id;
  final String source;
  final String fingerprint;
  final String errorType;
  final String message;
  final String stackTrace;
  final String appVersion;
  final String buildNumber;
  final String platformInfo;
  final String firmId;
  final String userId;
  final String requestId;

  /// What the client was doing, as the reporter labelled it.
  final String contextLabel;

  /// The steps leading up to the failure, oldest first.
  final List<String> breadcrumbs;

  /// When it happened on the client, which can be well before it was reported:
  /// the desktop queues reports on disk until it can sign in and flush them.
  final String occurredAt;
  final String receivedAt;

  factory ErrorReport.fromJson(Json json) => ErrorReport(
        id: stringValue(json['id']),
        source: stringValue(json['source']),
        fingerprint: stringValue(json['fingerprint']),
        errorType: stringValue(json['error_type']),
        message: stringValue(json['message']),
        stackTrace: stringValue(json['stack_trace']),
        appVersion: stringValue(json['app_version']),
        buildNumber: stringValue(json['build_number']),
        platformInfo: stringValue(json['platform_info']),
        firmId: stringValue(json['firm_id']),
        userId: stringValue(json['user_id']),
        requestId: stringValue(json['request_id']),
        contextLabel: stringValue(json['context_label']),
        breadcrumbs: stringList(json['breadcrumbs']),
        occurredAt: stringValue(json['occurred_at']),
        receivedAt: stringValue(json['received_at']),
      );
}
