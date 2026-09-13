// Where the app keeps its files. Desktop reads the same environment variables
// it always did; a phone build resolves its own directory at startup instead,
// because an Android process has none of them and "/" is not writable.

import 'dart:io';

import 'package:agency_desktop/core/platform/app_storage.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('on desktop the root is what it always was', () async {
    await AppStorage.initialize();
    expect(AppStorage.isDesktop, isTrue);
    final String expected = Platform.environment['APPDATA'] ??
        Platform.environment['XDG_CONFIG_HOME'] ??
        Platform.environment['HOME'] ??
        Directory.current.path;
    expect(AppStorage.root, expected);
  });
}
