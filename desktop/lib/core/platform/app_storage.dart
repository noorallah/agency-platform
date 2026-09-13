import 'dart:io';

import 'package:path_provider/path_provider.dart';

/// Where the app keeps its own files, on every platform it builds for.
///
/// Desktop has always read `APPDATA`, `XDG_CONFIG_HOME` or `HOME`. An Android
/// process has none of them, and falling back to the working directory there
/// means `/`, which the app cannot write -- so preferences, logs and crash
/// reports failed on the first launch of a phone build. On a phone the root is
/// the app's own support directory, resolved once at startup by [initialize].
class AppStorage {
  const AppStorage._();

  static String? _mobileRoot;

  /// True on the platforms the client was designed for.
  static bool get isDesktop =>
      Platform.isWindows || Platform.isLinux || Platform.isMacOS;

  /// Resolve the phone's directory. A no-op on desktop; call before anything
  /// writes a file.
  static Future<void> initialize() async {
    if (isDesktop) return;
    _mobileRoot = (await getApplicationSupportDirectory()).path;
  }

  /// The directory `.agency_platform` lives in.
  static String get root {
    final String? mobile = _mobileRoot;
    if (mobile != null) return mobile;
    return Platform.environment['APPDATA'] ??
        Platform.environment['XDG_CONFIG_HOME'] ??
        Platform.environment['HOME'] ??
        Directory.current.path;
  }
}
