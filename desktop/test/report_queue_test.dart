import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/diagnostics/crash_reporter.dart';
import 'package:agency_desktop/core/diagnostics/report_queue.dart';
import 'package:agency_desktop/core/logging/app_log.dart';
import 'package:flutter_test/flutter_test.dart';

/// Reports are queued to disk rather than posted as they happen, because the
/// failures most worth having occur before login, offline, or as the process
/// dies -- none of which can finish an HTTP request. These pin that a failed
/// upload loses nothing and that the queue cannot grow without limit.

Directory _tempDir() {
  final Directory directory = Directory(
    '${Directory.systemTemp.path}${Platform.pathSeparator}'
    'agency_queue_${DateTime.now().microsecondsSinceEpoch}',
  );
  directory.createSync(recursive: true);
  addTearDown(() {
    if (directory.existsSync()) directory.deleteSync(recursive: true);
  });
  return directory;
}

Map<String, Object?> _report(String fingerprint) => <String, Object?>{
      'fingerprint': fingerprint,
      'error_type': 'StateError',
      'message': 'boom',
      'breadcrumbs': const <String>[],
    };

void main() {
  setUp(() {
    CrashReporter.resetForTest();
    AppLog.resetForTest();
  });

  test('a report survives on disk until it is accepted', () async {
    final Directory directory = _tempDir();
    final ReportQueue queue = ReportQueue(directory: directory);
    queue.enqueue(_report('one'));

    // The server refuses it -- a flaky network must not destroy the evidence.
    int attempts = 0;
    await queue.flush((batch) async {
      attempts++;
      return false;
    });

    expect(attempts, 1);
    expect(queue.pending(), hasLength(1));

    await queue.flush((batch) async => true);
    expect(queue.pending(), isEmpty);
  });

  test('accepted reports are deleted, and the batch carries the payload',
      () async {
    final Directory directory = _tempDir();
    final ReportQueue queue = ReportQueue(directory: directory)
      ..enqueue(_report('one'))
      ..enqueue(_report('two'));

    List<Map<String, Object?>> received = const [];
    final int sent = await queue.flush((batch) async {
      received = batch;
      return true;
    });

    expect(sent, 2);
    expect(
      received.map((report) => report['fingerprint']),
      containsAll(<String>['one', 'two']),
    );
    expect(queue.pending(), isEmpty);
  });

  test('the queue is bounded and drops the oldest first', () {
    final Directory directory = _tempDir();
    final ReportQueue queue = ReportQueue(directory: directory, maxEntries: 3);

    for (int index = 0; index < 10; index++) {
      queue.enqueue(_report('report-$index'));
    }

    // A client that cannot reach its server for a month must not fill the disk.
    expect(queue.pending(), hasLength(3));
  });

  test('a corrupt entry is dropped rather than blocking the queue', () async {
    final Directory directory = _tempDir();
    final ReportQueue queue = ReportQueue(directory: directory);
    queue.enqueue(_report('good'));
    File('${directory.path}${Platform.pathSeparator}00000000000000000001.json')
        .writeAsStringSync('not json at all');

    List<Map<String, Object?>> received = const [];
    await queue.flush((batch) async {
      received = batch;
      return true;
    });

    expect(received.map((report) => report['fingerprint']), ['good']);
    expect(queue.pending(), isEmpty);
  });

  test('an unexpected termination is queued for the next sign-in', () {
    final Directory logs = _tempDir();
    final Directory queueDir = _tempDir();
    AppLog.initialize(directory: logs);

    // First run starts and is killed; the second notices.
    CrashReporter.beginSession(directory: logs);
    CrashReporter.resetForTest();
    CrashReporter.beginSession(directory: logs);

    final ReportQueue queue = ReportQueue(directory: queueDir)
      ..enqueueSession(appVersion: '1.0.0', buildNumber: '128');

    final List<File> pending = queue.pending();
    expect(pending, hasLength(1));
    final Map<String, dynamic> report =
        jsonDecode(pending.single.readAsStringSync()) as Map<String, dynamic>;
    expect(report['error_type'], 'UnexpectedTermination');
    expect(report['app_version'], '1.0.0');
    expect(report['build_number'], '128');
    expect(report['message'], contains('without a clean exit'));
  });

  test('a clean previous session queues nothing', () {
    final Directory logs = _tempDir();
    final Directory queueDir = _tempDir();
    AppLog.initialize(directory: logs);

    CrashReporter.beginSession(directory: logs);
    CrashReporter.endSessionCleanly();
    CrashReporter.resetForTest();
    CrashReporter.beginSession(directory: logs);

    ReportQueue(directory: queueDir)
        .enqueueSession(appVersion: '1.0.0', buildNumber: '128');

    expect(ReportQueue(directory: queueDir).pending(), isEmpty);
  });

  test('captured errors are queued with their fingerprint', () {
    final Directory logs = _tempDir();
    final Directory queueDir = _tempDir();
    AppLog.initialize(directory: logs);
    CrashReporter.beginSession(directory: logs);
    CrashReporter.recordError('Saving product', StateError('boom'));

    ReportQueue(directory: queueDir)
        .enqueueSession(appVersion: '1.0.0', buildNumber: '128');

    final Map<String, dynamic> report = jsonDecode(
      ReportQueue(directory: queueDir).pending().single.readAsStringSync(),
    ) as Map<String, dynamic>;
    expect(report['message'], contains('boom'));
    expect(report['fingerprint'], isNotEmpty);
  });
}
