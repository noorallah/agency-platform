import 'dart:io';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

abstract class RefreshTokenStore {
  Future<String?> read();
  Future<void> write(String token);
  Future<void> clear();
}

/// Store refresh tokens in the operating system credential vault.
class SecureRefreshTokenStore implements RefreshTokenStore {
  SecureRefreshTokenStore({FlutterSecureStorage? storage})
      : _storage = storage ?? const FlutterSecureStorage();

  static const _key = 'agency_platform.refresh_token';
  final FlutterSecureStorage _storage;

  @override
  Future<void> clear() => _storage.delete(key: _key);

  @override
  Future<String?> read() => _storage.read(key: _key);

  @override
  Future<void> write(String token) => _storage.write(key: _key, value: token);
}

/// Migrates refresh tokens from the pre-vault local file on first use.
class MigratingRefreshTokenStore implements RefreshTokenStore {
  MigratingRefreshTokenStore({
    SecureRefreshTokenStore? secureStore,
    FileRefreshTokenStore? legacyStore,
  })  : _secureStore = secureStore ?? SecureRefreshTokenStore(),
        _legacyStore = legacyStore ?? FileRefreshTokenStore();

  final SecureRefreshTokenStore _secureStore;
  final FileRefreshTokenStore _legacyStore;

  @override
  Future<void> clear() async {
    await _secureStore.clear();
    await _legacyStore.clear();
  }

  @override
  Future<String?> read() async {
    final String? secureToken = await _secureStore.read();
    if (secureToken != null && secureToken.isNotEmpty) {
      return secureToken;
    }
    final String? legacyToken = await _legacyStore.read();
    if (legacyToken == null || legacyToken.isEmpty) {
      return null;
    }
    await _secureStore.write(legacyToken);
    await _legacyStore.clear();
    return legacyToken;
  }

  @override
  Future<void> write(String token) async {
    await _secureStore.write(token);
    await _legacyStore.clear();
  }
}

/// File-backed test double for isolated desktop session tests.
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

  File get _file =>
      File('${_directory.path}${Platform.pathSeparator}refresh_token');

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
