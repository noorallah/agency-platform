import 'dart:io';

import '../logging/app_log.dart';

/// Removes anything that must never leave a customer's machine.
///
/// An allowlist would be safer still, but a report is mostly free text — log
/// lines and stack traces — so what matters is that the few things with real
/// value to an attacker cannot survive it. Applied to every message, stack and
/// log line that reaches a report.
abstract final class DiagnosticsRedaction {
  // Dart's RegExp is ECMAScript: inline `(?i)` is not a flag it understands,
  // and `\-` inside a class is an invalid identity escape. Case-insensitivity
  // is a constructor argument, and `-` goes last in a class instead.
  static final RegExp _jwt = RegExp(
    r'eyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]*',
  );
  static final RegExp _bearer = RegExp(
    r'\bBearer\s+[A-Za-z0-9._-]+',
    caseSensitive: false,
  );
  static final RegExp _namedSecret = RegExp(
    r'"?(password|refresh_token|access_token|secret|api[_-]?key)"?'
    r'\s*[:=]\s*"?[^",}\s]+',
    caseSensitive: false,
  );

  static String scrub(String value) => value
      .replaceAll(_jwt, '<redacted-jwt>')
      .replaceAll(_bearer, 'Bearer <redacted>')
      .replaceAllMapped(
        _namedSecret,
        (match) => '${match.group(1)}: <redacted>',
      );
}

/// One failure, kept for the session report.
class CapturedError {
  CapturedError({
    required this.at,
    required this.source,
    required this.message,
    required this.fingerprint,
    this.stack,
  });

  final DateTime at;
  final String source;
  final String message;
  final String fingerprint;
  final String? stack;

  Map<String, Object?> toJson() => <String, Object?>{
        'occurred_at': at.toUtc().toIso8601String(),
        'source': source,
        'message': message,
        'fingerprint': fingerprint,
        'stack_trace': stack,
      };
}

/// Notices that the application did not get to say goodbye, and turns a
/// session's failures into one file a customer can send.
///
/// A Dart handler cannot observe a native crash — by the time the process is
/// gone there is nothing left to run. What it *can* do is notice, on the next
/// launch, that the previous run never recorded a clean exit. That inference is
/// the only evidence available for the class of close being investigated here.
abstract final class CrashReporter {
  /// An error loop must not fill a disk or a report.
  static const int _maxSessionErrors = 20;
  static const int _logTailLines = 300;

  static File? _marker;
  static bool _previousSessionUnclean = false;
  static String? _previousSessionStartedAt;
  static final List<CapturedError> _errors = <CapturedError>[];
  static int _suppressed = 0;

  /// Whether the previous run ended without recording a clean exit.
  static bool get previousSessionEndedUnexpectedly => _previousSessionUnclean;

  static String? get previousSessionStartedAt => _previousSessionStartedAt;

  static List<CapturedError> get errors => List<CapturedError>.unmodifiable(
        _errors,
      );

  /// Reads the previous session's verdict, then claims the marker for this one.
  static void beginSession({Directory? directory}) {
    try {
      final Directory target = directory ?? AppLog.defaultDirectory();
      target.createSync(recursive: true);
      final File marker = File(
        '${target.path}${Platform.pathSeparator}session_active',
      );
      if (marker.existsSync()) {
        _previousSessionUnclean = true;
        _previousSessionStartedAt = marker.readAsStringSync().trim();
        AppLog.warn(
          'Previous session started at ${_previousSessionStartedAt ?? 'unknown'} '
          'ended without a clean exit. The application was terminated rather '
          'than closed.',
        );
      }
      marker.writeAsStringSync(
        DateTime.now().toUtc().toIso8601String(),
        flush: true,
      );
      _marker = marker;
    } on Object catch (error) {
      // Never let the crash reporter become the crash.
      AppLog.warn('Session marker unavailable: $error');
    }
  }

  /// Clears the marker, so the next launch knows this one ended on purpose.
  static void endSessionCleanly() {
    try {
      final File? marker = _marker;
      if (marker != null && marker.existsSync()) {
        marker.deleteSync();
      }
    } on Object {
      // A marker that will not delete only costs a false "unexpected" verdict.
    }
  }

  static void recordError(String source, Object error, [StackTrace? stack]) {
    AppLog.recordError(source, error, stack);
    if (_errors.length >= _maxSessionErrors) {
      _suppressed++;
      return;
    }
    final String message = DiagnosticsRedaction.scrub('$error');
    final String? trace =
        stack == null ? null : DiagnosticsRedaction.scrub(stack.toString());
    _errors.add(
      CapturedError(
        at: DateTime.now().toUtc(),
        source: source,
        message: message,
        fingerprint: fingerprintOf('$error', stack),
        stack: trace,
      ),
    );
  }

  /// A stable identity for "the same bug", so one fault groups instead of
  /// arriving a thousand times.
  ///
  /// Line numbers and absolute paths are stripped: they move with every build
  /// and every machine, and would give the same crash a new identity each time.
  static String fingerprintOf(String error, StackTrace? stack) {
    final String type = error.split(':').first.trim();
    final List<String> frames = (stack?.toString() ?? '')
        .split('\n')
        .where((line) => line.trim().isNotEmpty)
        .take(5)
        .map(
          (line) => line
              .replaceAll(RegExp(r'\(.*\)'), '')
              .replaceAll(RegExp(r'\d+'), '')
              .trim(),
        )
        .toList();
    return _stableHash('$type|${frames.join('|')}');
  }

  /// FNV-1a. `String.hashCode` is not guaranteed stable across runs or Dart
  /// versions, and a fingerprint that changes per launch groups nothing.
  static String _stableHash(String value) {
    int hash = 0xcbf29ce484222325;
    for (final int unit in value.codeUnits) {
      hash ^= unit;
      hash = (hash * 0x100000001b3) & 0xFFFFFFFFFFFFFFFF;
    }
    return hash.toRadixString(16).padLeft(16, '0');
  }

  /// Builds the report a customer sends to support.
  ///
  /// Plain text rather than an archive: mail clients and ticket systems block
  /// attachments they cannot see inside, and this has to be pasteable.
  static String buildReport({
    required String appName,
    required String version,
    required String buildNumber,
    String? firmCode,
    String? userId,
    String? serverUrl,
  }) {
    final StringBuffer report = StringBuffer()
      ..writeln('$appName diagnostics report')
      ..writeln('=' * 60)
      ..writeln('Generated        : ${DateTime.now().toUtc().toIso8601String()}')
      ..writeln('Application      : $version (build $buildNumber)')
      ..writeln(
        'Machine          : ${Platform.operatingSystem} '
        '${Platform.operatingSystemVersion}',
      )
      ..writeln('Firm             : ${firmCode ?? 'not signed in'}')
      // Identifier only. A support report is not a reason to move somebody's
      // name and email address onto a third machine.
      ..writeln('User             : ${userId ?? 'not signed in'}')
      ..writeln('Server           : ${serverUrl ?? 'unknown'}');

    // The headline: whether the application was closed or killed.
    if (_previousSessionUnclean) {
      report
        ..writeln('Previous session : ENDED UNEXPECTEDLY')
        ..writeln(
          '                   started ${_previousSessionStartedAt ?? 'unknown'};'
          ' no clean exit was recorded.',
        );
    } else {
      report.writeln('Previous session : closed normally');
    }

    report
      ..writeln()
      ..writeln('--- Errors this session (${_errors.length}) ---');
    if (_errors.isEmpty) {
      report.writeln('None recorded.');
    }
    for (final CapturedError error in _errors) {
      report
        ..writeln()
        ..writeln('[${error.at.toIso8601String()}] ${error.source}')
        ..writeln('  ${error.message}')
        ..writeln('  fingerprint ${error.fingerprint}');
      final String? stack = error.stack;
      if (stack != null && stack.isNotEmpty) {
        for (final String line in stack.split('\n').take(12)) {
          report.writeln('  $line');
        }
      }
    }
    if (_suppressed > 0) {
      report.writeln('\n($_suppressed further errors were not recorded.)');
    }

    report
      ..writeln()
      ..writeln('--- Recent activity ---');
    final List<String> recent = AppLog.recent;
    for (final String line in recent.length > _logTailLines
        ? recent.sublist(recent.length - _logTailLines)
        : recent) {
      report.writeln(DiagnosticsRedaction.scrub(line));
    }
    if (AppLog.filePath != null) {
      report
        ..writeln()
        ..writeln('Full log: ${AppLog.filePath}');
    }
    return report.toString();
  }

  /// Test seam.
  static void resetForTest() {
    _marker = null;
    _previousSessionUnclean = false;
    _previousSessionStartedAt = null;
    _errors.clear();
    _suppressed = 0;
  }
}
