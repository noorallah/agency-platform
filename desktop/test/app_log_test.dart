import 'dart:io';

import 'package:agency_desktop/core/logging/app_log.dart';
import 'package:flutter_test/flutter_test.dart';

/// The client ships to machines nobody here can reach, so the log is the only
/// account of what happened. These pin the properties that make it worth
/// having: it survives the process, it keeps older generations instead of
/// discarding half the story, and the operations that matter are recorded even
/// when the level is turned up.

Directory _tempDir() {
  final Directory directory = Directory(
    '${Directory.systemTemp.path}${Platform.pathSeparator}'
    'agency_log_${DateTime.now().microsecondsSinceEpoch}',
  );
  directory.createSync(recursive: true);
  addTearDown(() {
    if (directory.existsSync()) directory.deleteSync(recursive: true);
  });
  return directory;
}

/// The day every test runs on, unless it moves the clock itself.
DateTime _now = DateTime(2026, 9, 24, 10);

File _logIn(Directory directory, [String day = '2026-09-24']) =>
    File('${directory.path}${Platform.pathSeparator}client-$day.log');

void main() {
  setUp(() {
    AppLog.resetForTest();
    _now = DateTime(2026, 9, 24, 10);
    AppLog.clock = () => _now;
  });

  test('a line reaches the file immediately, not on some later flush', () {
    final Directory directory = _tempDir();
    AppLog.initialize(directory: directory);

    AppLog.error('the database went away');

    // Read with nothing awaited: a crash a millisecond later must not take the
    // line that explains it.
    expect(
      _logIn(directory).readAsStringSync(),
      contains('[ERROR] the database went away'),
    );
  });

  test('the level decides what is written', () {
    final Directory directory = _tempDir();
    AppLog.initialize(directory: directory, level: LogLevel.warning);

    AppLog.debug('noise');
    AppLog.info('also noise');
    AppLog.warn('worth keeping');

    final String contents = _logIn(directory).readAsStringSync();
    expect(contents, isNot(contains('noise')));
    expect(contents, contains('[WARN] worth keeping'));
  });

  test('a critical operation survives a raised level', () {
    // "Did the invoice post?" has to be answerable on a customer machine that
    // has info and debug turned off.
    final Directory directory = _tempDir();
    AppLog.initialize(directory: directory, level: LogLevel.critical);

    AppLog.info('routine');
    AppLog.operation(
      'sales_invoice.approve',
      outcome: 'succeeded',
      details: const {'document': 'INV-001', 'firm': 'WHOLE01'},
    );

    final String contents = _logIn(directory).readAsStringSync();
    expect(contents, isNot(contains('routine')));
    expect(
      contents,
      contains(
        '[CRITICAL] operation=sales_invoice.approve outcome=succeeded '
        'document=INV-001 firm=WHOLE01',
      ),
    );
  });

  test('rotation keeps older generations instead of discarding them', () {
    final Directory directory = _tempDir();
    AppLog.initialize(directory: directory, maxBytes: 2048, backupCount: 3);

    for (int index = 0; index < 400; index++) {
      AppLog.info('line $index padded out to force the file over the limit');
    }

    final File live = _logIn(directory);
    expect(live.existsSync(), isTrue);
    expect(live.lengthSync(), lessThan(4096));
    // The previous generation is still readable -- the whole point of rotating
    // rather than truncating.
    expect(File('${live.path}.1').existsSync(), isTrue);
    // And it never keeps more than it was told to.
    expect(File('${live.path}.4').existsSync(), isFalse);
  });

  test('logs live in a logs folder, not loose beside preferences', () {
    expect(AppLog.defaultDirectory().path, endsWith('logs'));
  });

  test('a new day starts a new file, named for the day', () {
    final Directory directory = _tempDir();
    AppLog.initialize(directory: directory);

    AppLog.info('before midnight');
    _now = DateTime(2026, 9, 25, 0, 5);
    AppLog.info('after midnight');

    expect(_logIn(directory).readAsStringSync(), contains('before midnight'));
    expect(
      _logIn(directory, '2026-09-25').readAsStringSync(),
      contains('after midnight'),
    );
    expect(AppLog.filePath, endsWith('client-2026-09-25.log'));
  });

  test('fourteen days are kept and older ones deleted, generations too', () {
    final Directory directory = _tempDir();
    String path(String name) =>
        '${directory.path}${Platform.pathSeparator}$name';
    // Today is 2026-09-24: the 11th is the oldest of the fourteen days kept.
    File(path('client-2026-09-11.log')).writeAsStringSync('kept');
    File(path('client-2026-09-10.log')).writeAsStringSync('expired');
    File(path('client-2026-09-10.log.1')).writeAsStringSync('expired');
    File(path('notes.txt')).writeAsStringSync('not ours');

    AppLog.initialize(directory: directory);

    expect(File(path('client-2026-09-11.log')).existsSync(), isTrue);
    expect(File(path('client-2026-09-10.log')).existsSync(), isFalse);
    expect(File(path('client-2026-09-10.log.1')).existsSync(), isFalse);
    expect(File(path('notes.txt')).existsSync(), isTrue);
  });

  test('the shared location is ProgramData, per Windows user', () {
    final Directory? shared = AppLog.sharedClientDirectory(
      environment: const {
        'ProgramData': r'C:\ProgramData',
        'USERNAME': 'clerk',
      },
    );
    expect(
      shared?.path,
      r'C:\ProgramData\Agency Platform\logs\client\clerk',
    );
    // No user name, no shared folder: the per-user one is used instead.
    expect(
      AppLog.sharedClientDirectory(
        environment: const {'ProgramData': r'C:\ProgramData'},
      ),
      isNull,
    );
  });

  test('timestamps are UTC so they line up with the backend', () {
    final Directory directory = _tempDir();
    AppLog.initialize(directory: directory);

    AppLog.info('marker');

    expect(_logIn(directory).readAsStringSync(), contains('Z ['));
  });

  test('an unwritable location degrades instead of throwing', () {
    // Logging must never become the fault it exists to report.
    AppLog.initialize(directory: Directory(' :/definitely/not/a/path'));

    expect(() => AppLog.info('still fine'), returnsNormally);
    expect(AppLog.recent.last, contains('still fine'));
  });

  test('the recent buffer keeps the tail for the diagnostics report', () {
    final Directory directory = _tempDir();
    AppLog.initialize(directory: directory);

    AppLog.info('first');
    AppLog.warn('second');

    expect(AppLog.recent.last, contains('[WARN] second'));
    expect(AppLog.recent.any((line) => line.contains('[INFO] first')), isTrue);
  });
}
