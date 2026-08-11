import 'dart:io';

import 'package:flutter/foundation.dart';

/// Severity, ordered. Anything below [AppLog.minimumLevel] is discarded before
/// it costs a file write.
enum LogLevel {
  debug('DEBUG'),
  info('INFO'),
  warning('WARN'),
  error('ERROR'),

  /// Reserved for operations whose failure is material to the business —
  /// posting, approving, provisioning, anything that moves money or stock.
  critical('CRITICAL');

  const LogLevel(this.label);

  final String label;

  bool operator >=(LogLevel other) => index >= other.index;
}

/// The desktop client's logging framework: levelled, rotated, on disk.
///
/// This replaces a single file that was trimmed by discarding its older half
/// once it passed a megabyte — which threw away the beginning of the story
/// exactly when the story got long enough to matter. Rotation keeps whole
/// generations instead, so the run *before* the interesting one is still there.
///
/// Every line is written **synchronously and flushed**, because the reason this
/// exists is a client that disappears: an unflushed buffer dies with it.
abstract final class AppLog {
  static const String _fileName = 'agency_desktop.log';
  static const int _recentLimit = 300;

  /// Debug builds keep everything; a shipped client would otherwise spend its
  /// time writing lines nobody reads.
  static LogLevel minimumLevel = kReleaseMode ? LogLevel.info : LogLevel.debug;

  static int maxBytes = 2 * 1024 * 1024;
  static int backupCount = 5;

  static Directory? _directory;
  static File? _file;
  static final List<String> _recent = <String>[];

  static String? get filePath => _file?.path;

  static Directory? get directory => _directory;

  /// The tail of this session, for the diagnostics report.
  static List<String> get recent => List<String>.unmodifiable(_recent);

  /// `%APPDATA%\.agency_platform\logs` on Windows, the equivalent elsewhere.
  static Directory defaultDirectory() {
    final String? configured = Platform.environment['APPDATA'] ??
        Platform.environment['XDG_CONFIG_HOME'] ??
        Platform.environment['HOME'];
    final String root = configured ?? Directory.current.path;
    return Directory(
      '$root${Platform.pathSeparator}.agency_platform'
      '${Platform.pathSeparator}logs',
    );
  }

  /// Opens the log. Never throws — logging must not become the fault it exists
  /// to report.
  static void initialize({
    Directory? directory,
    LogLevel? level,
    int? maxBytes,
    int? backupCount,
  }) {
    if (level != null) minimumLevel = level;
    if (maxBytes != null) AppLog.maxBytes = maxBytes;
    if (backupCount != null) AppLog.backupCount = backupCount;
    try {
      final Directory target = directory ?? defaultDirectory();
      target.createSync(recursive: true);
      _directory = target;
      _file = File('${target.path}${Platform.pathSeparator}$_fileName');
    } on Object {
      _directory = null;
      _file = null;
    }
  }

  static void debug(String message) => _write(LogLevel.debug, message);

  static void info(String message) => _write(LogLevel.info, message);

  static void warn(String message) => _write(LogLevel.warning, message);

  static void error(String message) => _write(LogLevel.error, message);

  /// Records a business-critical operation and its outcome.
  ///
  /// Logged at [LogLevel.critical] so it survives a raised minimum level on a
  /// customer machine: when someone asks "did the invoice post?", the answer
  /// has to be in the file even when debug and info were turned off.
  static void operation(
    String name, {
    String outcome = 'started',
    Map<String, Object?> details = const <String, Object?>{},
  }) {
    final String suffix = details.isEmpty
        ? ''
        : ' ${details.entries.map((e) => '${e.key}=${e.value}').join(' ')}';
    _write(LogLevel.critical, 'operation=$name outcome=$outcome$suffix');
  }

  static void recordError(String source, Object error, [StackTrace? stack]) {
    _write(LogLevel.error, '$source: $error');
    final String? trace = stack?.toString().trim();
    if (trace != null && trace.isNotEmpty) {
      _write(LogLevel.error, 'STACK $trace');
    }
  }

  static void _write(LogLevel level, String message) {
    if (!(level >= minimumLevel)) return;
    // UTC, so a client log lines up with the backend's without a timezone guess.
    final String line =
        '${DateTime.now().toUtc().toIso8601String()} [${level.label}] $message';
    _recent.add(line);
    if (_recent.length > _recentLimit) _recent.removeAt(0);
    if (!kReleaseMode) debugPrint(line);
    final File? file = _file;
    if (file == null) return;
    try {
      _rotateIfNeeded(file);
      file.writeAsStringSync('$line\n', mode: FileMode.append, flush: true);
    } on Object {
      // A log that cannot be written must not take the application with it.
    }
  }

  /// Renames generations outwards: `.4` is dropped, `.3` becomes `.4`, and the
  /// live file becomes `.1`.
  static void _rotateIfNeeded(File file) {
    if (!file.existsSync() || file.lengthSync() < maxBytes) return;
    final String base = file.path;
    try {
      final File oldest = File('$base.$backupCount');
      if (oldest.existsSync()) oldest.deleteSync();
      for (int index = backupCount - 1; index >= 1; index--) {
        final File source = File('$base.$index');
        if (source.existsSync()) source.renameSync('$base.${index + 1}');
      }
      file.renameSync('$base.1');
    } on Object {
      // If rotation fails, keep appending rather than losing the line.
    }
  }

  /// Test seam.
  static void resetForTest() {
    _recent.clear();
    _file = null;
    _directory = null;
    minimumLevel = LogLevel.debug;
    maxBytes = 2 * 1024 * 1024;
    backupCount = 5;
  }
}
