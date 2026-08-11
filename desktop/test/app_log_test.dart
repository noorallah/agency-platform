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

File _logIn(Directory directory) =>
    File('${directory.path}${Platform.pathSeparator}agency_desktop.log');

void main() {
  setUp(AppLog.resetForTest);

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
