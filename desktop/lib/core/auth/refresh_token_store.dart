import 'dart:io';

abstract class RefreshTokenStore {
  Future<String?> read();
  Future<void> write(String token);
  Future<void> clear();
}

/// Desktop-only storage boundary. A platform credential-vault store can replace it
/// without changing authentication logic.
class FileRefreshTokenStore implements RefreshTokenStore {
  FileRefreshTokenStore({Directory? directory})
      : _directory = directory ?? _defaultDirectory();

  final Directory _directory;

  static Directory _defaultDirectory() {
    final String? configured = Platform.environment['APPDATA'] ??
        Platform.environment['XDG_CONFIG_HOME'] ??
        Platform.environment['HOME'];
    return Directory(
      '${configured ?? Directory.current.path}${Platform.pathSeparator}.agency_platform',
    );
  }

  File get _file => File('${_directory.path}${Platform.pathSeparator}refresh_token');

  @override
  Future<void> clear() async {
    if (await _file.exists()) {
      await _file.delete();
    }
  }

  @override
  Future<String?> read() async {
    if (!await _file.exists()) {
      return null;
    }
    final String token = (await _file.readAsString()).trim();
    return token.isEmpty ? null : token;
  }

  @override
  Future<void> write(String token) async {
    await _directory.create(recursive: true);
    await _file.writeAsString(token, flush: true);
  }
}
