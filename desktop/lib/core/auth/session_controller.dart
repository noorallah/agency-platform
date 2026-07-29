import 'package:flutter/foundation.dart';

import '../api/api_client.dart';
import '../preferences/desktop_preferences_service.dart';
import '../preferences/user_preferences.dart';
import 'refresh_token_store.dart';

enum SessionStatus {
  restoring,
  signedOut,
  authenticating,
  requiresPasswordChange,
  authenticated,
  error,
}

class SessionController extends ChangeNotifier {
  SessionController({
    required String baseUrl,
    RefreshTokenStore? tokenStore,
    DesktopPreferencesService? preferences,
    Future<void> Function(UserPreferences preferences)?
        onPreferencesSynchronized,
  })  : _tokenStore = tokenStore ?? MigratingRefreshTokenStore(),
        _preferences = preferences ?? DesktopPreferencesService(),
        _baseUrl = baseUrl,
        _onPreferencesSynchronized = onPreferencesSynchronized {
    _rememberMe = _preferences.current.rememberMe;
    _createApiClient();
  }

  late ApiClient api;
  final RefreshTokenStore _tokenStore;
  final DesktopPreferencesService _preferences;
  final Future<void> Function(UserPreferences preferences)?
      _onPreferencesSynchronized;
  String _baseUrl;
  String? _accessToken;
  String? _refreshToken;
  bool _rememberMe = false;
  SessionStatus _status = SessionStatus.restoring;
  String? _error;
  String? _notice;
  Future<bool>? _refreshOperation;

  SessionStatus get status => _status;
  String? get error => _error;
  String? get notice => _notice;
  String get baseUrl => _baseUrl;

  Future<void> restore() async {
    _setStatus(SessionStatus.restoring);
    _rememberMe = _preferences.current.rememberMe;
    if (!_rememberMe && _preferences.hasStoredPreferences) {
      await _tokenStore.clear();
      _setStatus(SessionStatus.signedOut);
      return;
    }
    _refreshToken = await _tokenStore.read();
    if (_refreshToken == null) {
      _setStatus(SessionStatus.signedOut);
      return;
    }
    if (!_rememberMe) {
      _rememberMe = true;
      await _preferences.saveLoginOptions(
        rememberUsername: _preferences.current.rememberUsername,
        rememberMe: true,
        username: _preferences.current.cachedUsername ?? '',
      );
    }
    if (!await refreshAccessToken()) {
      await _tokenStore.clear();
      _refreshToken = null;
      _setStatus(SessionStatus.signedOut);
    }
  }

  Future<void> login(
    String email,
    String password, {
    required bool rememberUsername,
    required bool rememberMe,
  }) async {
    _notice = null;
    _error = null;
    _setStatus(SessionStatus.authenticating);
    try {
      final AuthTokens tokens = await api.login(email, password);
      _rememberMe = rememberMe;
      await _preferences.saveLoginOptions(
        rememberUsername: rememberUsername,
        rememberMe: rememberMe,
        username: email,
      );
      await _applyTokens(tokens);
      await _synchronizePreferences();
      _setStatus(tokens.forcePasswordChange
          ? SessionStatus.requiresPasswordChange
          : SessionStatus.authenticated);
    } on ApiException catch (exception) {
      _error = exception.message;
      _setStatus(SessionStatus.error);
    }
  }

  Future<void> completeInitialPasswordChange(
    String currentPassword,
    String newPassword,
  ) async {
    _error = null;
    _setStatus(SessionStatus.authenticating);
    try {
      await api.changePassword(currentPassword, newPassword);
      await _clearSession();
      _notice = 'Password updated. Sign in with your new password.';
      _setStatus(SessionStatus.signedOut);
    } on ApiException catch (exception) {
      _error = exception.message;
      _setStatus(SessionStatus.requiresPasswordChange);
    }
  }

  Future<bool> refreshAccessToken() {
    final Future<bool>? existing = _refreshOperation;
    if (existing != null) {
      return existing;
    }
    late final Future<bool> operation;
    operation = _refreshAccessToken().whenComplete(() {
      if (identical(_refreshOperation, operation)) {
        _refreshOperation = null;
      }
    });
    _refreshOperation = operation;
    return operation;
  }

  Future<bool> _refreshAccessToken() async {
    if (_refreshToken == null) {
      return false;
    }
    try {
      final AuthTokens tokens = await api.refresh(_refreshToken!);
      if (tokens.accessToken.isEmpty || tokens.refreshToken.isEmpty) {
        await _clearSession();
        _setStatus(SessionStatus.signedOut);
        return false;
      }
      await _applyTokens(tokens);
      await _synchronizePreferences();
      return true;
    } on ApiException {
      await _clearSession();
      _setStatus(SessionStatus.signedOut);
      return false;
    }
  }

  Future<void> logout() async {
    final String? refreshToken = _refreshToken;
    try {
      if (refreshToken != null) {
        await api.logout(refreshToken);
      }
    } on ApiException {
      // Local logout must succeed even if the network is unavailable.
    } finally {
      await _clearSession();
      _setStatus(SessionStatus.signedOut);
    }
  }

  Future<void> updateServerUrl(String value) async {
    final Uri parsed = Uri.parse(value.trim());
    if (!parsed.hasScheme || !parsed.hasAuthority) {
      throw const FormatException(
          'Enter a complete server URL, including https://.');
    }
    await _preferences.saveServerUrl(value);
    _baseUrl = _preferences.current.serverUrl;
    _createApiClient();
    if (_accessToken != null || _refreshToken != null) {
      await _clearSession();
      _setStatus(SessionStatus.signedOut);
    }
  }

  Future<void> updatePreferredTheme(String theme) async {
    final UserPreferences updated =
        await api.updateUserPreferences({'preferred_theme': theme});
    await _preferences.cacheServerPreferences(updated.toJson());
  }

  Future<void> _synchronizePreferences() async {
    try {
      final UserPreferences preferences = await api.getUserPreferences();
      await _preferences.cacheServerPreferences(preferences.toJson());
      if (_onPreferencesSynchronized != null) {
        await _onPreferencesSynchronized(preferences);
      }
    } on ApiException catch (exception) {
      _notice = 'Signed in, but preferences could not be synchronized: '
          '${exception.message}';
    } on FormatException catch (exception) {
      _notice = 'Signed in, but preferences could not be synchronized: '
          '${exception.message}';
    }
  }

  Future<void> _clearSession() async {
    _accessToken = null;
    _refreshToken = null;
    await _tokenStore.clear();
  }

  Future<void> _applyTokens(AuthTokens tokens) async {
    _accessToken = tokens.accessToken;
    _refreshToken = tokens.refreshToken;
    if (_rememberMe) {
      await _tokenStore.write(tokens.refreshToken);
    } else {
      await _tokenStore.clear();
    }
  }

  void _createApiClient() {
    api = ApiClient(
      baseUrl: _baseUrl,
      accessToken: () => _accessToken,
      refreshAccessToken: refreshAccessToken,
    );
  }

  void _setStatus(SessionStatus value) {
    _status = value;
    notifyListeners();
  }
}
