import 'dart:io';

import 'package:flutter/foundation.dart';
import '../platform/app_storage.dart';

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
/// One file per day, `client-YYYY-MM-DD.log`, kept for [retentionDays]. On an
/// installed Windows copy they live beside the server's, under
/// `C:\ProgramData\Agency Platform\logs\client\<windows user>`, so whoever
/// supports the machine finds every log in one folder; anywhere that is not
/// writable they fall back to the per-user [defaultDirectory].
///
/// Within a day a file that passes [maxBytes] is rotated to `.1`, `.2` and so
/// on, keeping whole generations rather than discarding the older half of the
/// story exactly when it got long enough to matter.
///
/// Every line is written **synchronously and flushed**, because the reason this
/// exists is a client that disappears: an unflushed buffer dies with it.
abstract final class AppLog {
  static const String _prefix = 'client-';
  static const int _recentLimit = 300;

  /// Debug builds keep everything; a shipped client would otherwise spend its
  /// time writing lines nobody reads.
  static LogLevel minimumLevel = kReleaseMode ? LogLevel.info : LogLevel.debug;

  static int maxBytes = 2 * 1024 * 1024;
  static int backupCount = 5;

  /// Days of daily files kept, today's included.
  static int retentionDays = 14;

  /// Test seam: the local time the file name is taken from.
  static DateTime Function() clock = DateTime.now;

  static Directory? _directory;
  static File? _file;
  static String? _fileDay;
  static final List<String> _recent = <String>[];

  static String? get filePath => _file?.path;

  static Directory? get directory => _directory;

  /// The tail of this session, for the diagnostics report.
  static List<String> get recent => List<String>.unmodifiable(_recent);

  /// `%APPDATA%\.agency_platform\logs` on Windows, the equivalent elsewhere.
  ///
  /// Per user and always writable. The crash marker and the report queue live
  /// here whatever happens to the log files, because they are one user's state
  /// rather than something to read beside the server's logs.
  static Directory defaultDirectory() {
    final String root = AppStorage.root;
    return Directory(
      '$root${Platform.pathSeparator}.agency_platform'
      '${Platform.pathSeparator}logs',
    );
  }

  /// `C:\ProgramData\Agency Platform\logs\client\<user>`, or null where there
  /// is no such thing: not Windows, or no ProgramData, or no user name.
  static Directory? sharedClientDirectory({Map<String, String>? environment}) {
    final Map<String, String> env = environment ?? Platform.environment;
    if (environment == null && !Platform.isWindows) return null;
    final String? programData = env['ProgramData'] ?? env['PROGRAMDATA'];
    final String? user = env['USERNAME'];
    if (programData == null || programData.isEmpty) return null;
    if (user == null || user.isEmpty) return null;
    return Directory(
      '$programData\\Agency Platform\\logs\\client\\$user',
    );
  }

  /// The logs folder as a whole: what "Open logs folder" shows.
  ///
  /// The shared one when this machine has it -- it holds the server's logs too
  /// on a server PC -- otherwise the folder this client is writing to.
  static Directory logsFolder() {
    final Directory? shared = sharedClientDirectory();
    if (shared != null && shared.parent.parent.existsSync()) {
      return shared.parent.parent;
    }
    return _directory ?? defaultDirectory();
  }

  /// Opens the log. Never throws — logging must not become the fault it exists
  /// to report.
  static void initialize({
    Directory? directory,
    LogLevel? level,
    int? maxBytes,
    int? backupCount,
    int? retentionDays,
  }) {
    if (level != null) minimumLevel = level;
    if (maxBytes != null) AppLog.maxBytes = maxBytes;
    if (backupCount != null) AppLog.backupCount = backupCount;
    if (retentionDays != null) AppLog.retentionDays = retentionDays;
    _file = null;
    _fileDay = null;
    final Directory? shared = sharedClientDirectory();
    final List<Directory> candidates = directory != null
        ? <Directory>[directory]
        : <Directory>[if (shared != null) shared, defaultDirectory()];
    _directory = null;
    for (final Directory candidate in candidates) {
      if (_usable(candidate)) {
        _directory = candidate;
        break;
      }
    }
    if (_directory != null) _openToday();
  }

  /// Whether a line can actually be written there. Creating the folder is not
  /// proof: ProgramData lets a standard user create a folder it then cannot
  /// write a file in, when the installer did not grant it.
  static bool _usable(Directory candidate) {
    try {
      candidate.createSync(recursive: true);
      final File probe = File(
        '${candidate.path}${Platform.pathSeparator}.write-test',
      );
      probe.writeAsStringSync('', flush: true);
      probe.deleteSync();
      return true;
    } on Object {
      return false;
    }
  }

  static String _day(DateTime moment) =>
      '${moment.year.toString().padLeft(4, '0')}-'
      '${moment.month.toString().padLeft(2, '0')}-'
      '${moment.day.toString().padLeft(2, '0')}';

  /// Points the log at today's file, and prunes what has aged out.
  static void _openToday() {
    final Directory? target = _directory;
    if (target == null) return;
    final String today = _day(clock());
    _fileDay = today;
    _file = File('${target.path}${Platform.pathSeparator}$_prefix$today.log');
    _prune(target, clock());
  }

  /// Deletes daily files, and their rotated generations, older than
  /// [retentionDays]. Only files this class names: anything else a person put
  /// in the folder is left alone.
  static void _prune(Directory target, DateTime now) {
    final DateTime today = DateTime(now.year, now.month, now.day);
    final DateTime oldestKept = today.subtract(Duration(days: retentionDays - 1));
    final RegExp name = RegExp(r'^client-(\d{4})-(\d{2})-(\d{2})\.log(\.\d+)?$');
    try {
      for (final FileSystemEntity entity in target.listSync()) {
        if (entity is! File) continue;
        final String base = entity.uri.pathSegments.last;
        final RegExpMatch? match = name.firstMatch(base);
        if (match == null) continue;
        final DateTime day = DateTime(
          int.parse(match.group(1)!),
          int.parse(match.group(2)!),
          int.parse(match.group(3)!),
        );
        if (day.isBefore(oldestKept)) entity.deleteSync();
      }
    } on Object {
      // Housekeeping must never cost a log line.
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
    if (_directory != null && _fileDay != _day(clock())) _openToday();
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
    _fileDay = null;
    _directory = null;
    minimumLevel = LogLevel.debug;
    maxBytes = 2 * 1024 * 1024;
    backupCount = 5;
    retentionDays = 14;
    clock = DateTime.now;
  }
}
