import 'dart:convert';
import 'dart:io';

import '../logging/app_log.dart';
import 'crash_reporter.dart';

/// Holds error reports on disk until the client can sign in and send them.
///
/// Reporting is deliberately **queued rather than posted immediately**. The
/// failures most worth having are the ones that happen before login, while the
/// network is down, or as the process dies — none of which can complete an HTTP
/// request. Writing to disk first is the only way those survive; the upload is
/// the easy half.
///
/// The queue is bounded and drops the oldest first. A client that cannot reach
/// its server for a month must not fill the disk with its complaints.
class ReportQueue {
  ReportQueue({Directory? directory, this.maxEntries = 50})
      : _directory = directory;

  final Directory? _directory;

  /// Oldest are dropped past this. Fifty distinct failures is already more than
  /// anyone will read; the rest is landfill.
  final int maxEntries;

  Directory get directory =>
      _directory ??
      Directory(
        '${AppLog.defaultDirectory().parent.path}'
        '${Platform.pathSeparator}crash_queue',
      );

  /// Writes one report. Never throws — a queue that fails must not become the
  /// failure it was recording.
  void enqueue(Map<String, Object?> report) {
    try {
      final Directory target = directory..createSync(recursive: true);
      final String stamp = DateTime.now().toUtc().microsecondsSinceEpoch
          .toString()
          .padLeft(20, '0');
      File('${target.path}${Platform.pathSeparator}$stamp.json')
          .writeAsStringSync(jsonEncode(report), flush: true);
      _trim();
    } on Object catch (error) {
      AppLog.warn('Could not queue an error report: $error');
    }
  }

  /// Queues the session's captured failures, plus the previous session's
  /// verdict when it was killed rather than closed.
  void enqueueSession({
    required String appVersion,
    required String buildNumber,
    String? contextLabel,
  }) {
    final String platformInfo =
        '${Platform.operatingSystem} ${Platform.operatingSystemVersion}';
    if (CrashReporter.previousSessionEndedUnexpectedly) {
      enqueue(<String, Object?>{
        'fingerprint': CrashReporter.fingerprintOf('UnexpectedTermination', null),
        'error_type': 'UnexpectedTermination',
        'message': 'The previous session ended without a clean exit, having '
            'started at ${CrashReporter.previousSessionStartedAt ?? 'unknown'}.',
        'stack_trace': null,
        'app_version': appVersion,
        'build_number': buildNumber,
        'platform_info': platformInfo,
        'context_label': contextLabel,
        'breadcrumbs': AppLog.recent.take(100).toList(),
      });
    }
    for (final CapturedError error in CrashReporter.errors) {
      enqueue(<String, Object?>{
        'fingerprint': error.fingerprint,
        'error_type': error.source,
        'message': error.message,
        'stack_trace': error.stack,
        'app_version': appVersion,
        'build_number': buildNumber,
        'platform_info': platformInfo,
        'context_label': contextLabel,
        'occurred_at': error.at.toIso8601String(),
        'breadcrumbs': const <String>[],
      });
    }
  }

  List<File> pending() {
    try {
      if (!directory.existsSync()) return const <File>[];
      final List<File> files = directory
          .listSync()
          .whereType<File>()
          .where((file) => file.path.endsWith('.json'))
          .toList()
        ..sort((a, b) => a.path.compareTo(b.path));
      return files;
    } on Object {
      return const <File>[];
    }
  }

  /// Sends everything queued, oldest first, and deletes what was accepted.
  ///
  /// [send] is given a batch and returns whether the server took it. A report
  /// is only deleted once it has been accepted — a failed upload leaves the
  /// queue exactly as it was, so nothing is lost to a flaky network.
  Future<int> flush(
    Future<bool> Function(List<Map<String, Object?>> batch) send, {
    int batchSize = 25,
  }) async {
    final List<File> files = pending();
    if (files.isEmpty) return 0;
    int sent = 0;
    for (int start = 0; start < files.length; start += batchSize) {
      final List<File> chunk =
          files.sublist(start, (start + batchSize).clamp(0, files.length));
      final List<Map<String, Object?>> batch = <Map<String, Object?>>[];
      final List<File> readable = <File>[];
      for (final File file in chunk) {
        try {
          final Object? decoded = jsonDecode(file.readAsStringSync());
          if (decoded is Map<String, dynamic>) {
            batch.add(decoded);
            readable.add(file);
          } else {
            file.deleteSync();
          }
        } on Object {
          // A corrupt entry would block the queue forever. Drop it.
          try {
            file.deleteSync();
          } on Object {
            // Nothing further to try.
          }
        }
      }
      if (batch.isEmpty) continue;
      final bool accepted = await send(batch);
      if (!accepted) {
        AppLog.warn('Error reports could not be sent; keeping them queued.');
        break;
      }
      for (final File file in readable) {
        try {
          file.deleteSync();
        } on Object {
          // Leaving it means one duplicate report, not a lost one.
        }
      }
      sent += batch.length;
    }
    if (sent > 0) AppLog.info('Sent $sent queued error report(s).');
    return sent;
  }

  void _trim() {
    final List<File> files = pending();
    if (files.length <= maxEntries) return;
    for (final File file in files.take(files.length - maxEntries)) {
      try {
        file.deleteSync();
      } on Object {
        // Nothing further to try.
      }
    }
  }
}
