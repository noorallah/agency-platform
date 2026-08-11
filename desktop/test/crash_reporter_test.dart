import 'dart:io';

import 'package:agency_desktop/core/diagnostics/crash_reporter.dart';
import 'package:agency_desktop/core/logging/app_log.dart';
import 'package:flutter_test/flutter_test.dart';

/// A native crash cannot be observed by a Dart handler — by the time the
/// process is gone there is nothing left to run. The only evidence available is
/// the inference made on the *next* launch: the previous run never recorded a
/// clean exit. That is what these pin, along with the promise that a report a
/// customer emails carries no credentials.

Directory _tempDir() {
  final Directory directory = Directory(
    '${Directory.systemTemp.path}${Platform.pathSeparator}'
    'agency_crash_${DateTime.now().microsecondsSinceEpoch}',
  );
  directory.createSync(recursive: true);
  addTearDown(() {
    if (directory.existsSync()) directory.deleteSync(recursive: true);
  });
  return directory;
}

void main() {
  setUp(CrashReporter.resetForTest);

  group('session verdict', () {
    test('a session that exits cleanly is not reported as a crash', () {
      final Directory directory = _tempDir();
      AppLog.initialize(directory: directory);

      CrashReporter.beginSession(directory: directory);
      CrashReporter.endSessionCleanly();

      CrashReporter.resetForTest();
      CrashReporter.beginSession(directory: directory);

      expect(CrashReporter.previousSessionEndedUnexpectedly, isFalse);
    });

    test('a session that never exits is reported on the next launch', () {
      final Directory directory = _tempDir();
      AppLog.initialize(directory: directory);

      // First run: starts, and is killed -- no clean exit is ever recorded.
      CrashReporter.beginSession(directory: directory);

      // Second run.
      CrashReporter.resetForTest();
      CrashReporter.beginSession(directory: directory);

      expect(CrashReporter.previousSessionEndedUnexpectedly, isTrue);
      expect(CrashReporter.previousSessionStartedAt, isNotNull);
      expect(
        CrashReporter.buildReport(
          appName: 'Agency Platform',
          version: '1.0.0',
          buildNumber: '128',
        ),
        contains('Previous session : ENDED UNEXPECTEDLY'),
      );
    });

    test('the verdict survives into a third launch correctly', () {
      final Directory directory = _tempDir();
      AppLog.initialize(directory: directory);

      CrashReporter.beginSession(directory: directory); // killed
      CrashReporter.resetForTest();
      CrashReporter.beginSession(directory: directory); // notices, then claims
      CrashReporter.endSessionCleanly();
      CrashReporter.resetForTest();
      CrashReporter.beginSession(directory: directory);

      expect(CrashReporter.previousSessionEndedUnexpectedly, isFalse);
    });
  });

  group('capture', () {
    test('an error loop cannot flood the report', () {
      final Directory directory = _tempDir();
      AppLog.initialize(directory: directory);

      for (int index = 0; index < 100; index++) {
        CrashReporter.recordError('Loop', StateError('failure $index'));
      }

      expect(CrashReporter.errors.length, 20);
      expect(
        CrashReporter.buildReport(
          appName: 'Agency Platform',
          version: '1.0.0',
          buildNumber: '128',
        ),
        contains('80 further errors were not recorded'),
      );
    });

    test('the same fault gets the same fingerprint across runs', () {
      final StackTrace first = StackTrace.fromString(
        '#0 ProductPage.build (package:agency_desktop/ui/products.dart:120:11)\n'
        '#1 StatelessElement.build (package:flutter/src/widgets/framework.dart:1)',
      );
      // Same fault, different build: paths shift and line numbers move.
      final StackTrace second = StackTrace.fromString(
        '#0 ProductPage.build (package:agency_desktop/ui/products.dart:987:44)\n'
        '#1 StatelessElement.build (package:flutter/src/widgets/framework.dart:9)',
      );

      expect(
        CrashReporter.fingerprintOf('StateError: boom', first),
        CrashReporter.fingerprintOf('StateError: boom', second),
      );
      expect(
        CrashReporter.fingerprintOf('RangeError: boom', first),
        isNot(CrashReporter.fingerprintOf('StateError: boom', first)),
      );
    });
  });

  group('redaction', () {
    test('credentials never reach a report the customer emails', () {
      final Directory directory = _tempDir();
      AppLog.initialize(directory: directory);

      CrashReporter.recordError(
        'Request failed',
        'GET /api/v1/products failed. '
            'headers: {Authorization: Bearer abc.def.ghi123} '
            'body: {"password":"Hunter2!","refresh_token":"rt-secret-value"} '
            'token=eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.sIgNaTuRe',
      );

      final String report = CrashReporter.buildReport(
        appName: 'Agency Platform',
        version: '1.0.0',
        buildNumber: '128',
      );

      expect(report, isNot(contains('Hunter2!')));
      expect(report, isNot(contains('rt-secret-value')));
      expect(report, isNot(contains('abc.def.ghi123')));
      expect(report, isNot(contains('sIgNaTuRe')));
      expect(report, contains('<redacted'));
      // The useful part of the message survives.
      expect(report, contains('/api/v1/products'));
    });

    test('the report identifies the user by id, never by name', () {
      final Directory directory = _tempDir();
      AppLog.initialize(directory: directory);

      final String report = CrashReporter.buildReport(
        appName: 'Agency Platform',
        version: '1.0.0',
        buildNumber: '128',
        firmCode: 'WHOLE01',
        userId: '3f2a-91cc',
      );

      expect(report, contains('User             : 3f2a-91cc'));
      expect(report, contains('Firm             : WHOLE01'));
    });
  });

  test('the report leads with the answer, not with the log', () {
    final Directory directory = _tempDir();
    AppLog.initialize(directory: directory);
    AppLog.info('some earlier activity');

    final List<String> lines = CrashReporter.buildReport(
      appName: 'Agency Platform',
      version: '1.0.0',
      buildNumber: '128',
    ).split('\n');

    // Whoever opens this should not have to scroll to learn what happened.
    expect(lines.first, contains('Agency Platform diagnostics report'));
    expect(
      lines.take(12).where((line) => line.contains('Previous session')),
      isNotEmpty,
    );
    expect(lines.any((line) => line.contains('--- Recent activity ---')), isTrue);
  });
}
