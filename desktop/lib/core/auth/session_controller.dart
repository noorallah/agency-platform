import 'package:flutter/foundation.dart';

import '../api/api_client.dart';
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
  }) : _tokenStore = tokenStore ?? FileRefreshTokenStore() {
    api = ApiClient(
      baseUrl: baseUrl,
      accessToken: () => _accessToken,
      refreshAccessToken: refreshAccessToken,
    );
  }

  late final ApiClient api;
  final RefreshTokenStore _tokenStore;
  String? _accessToken;
  String? _refreshToken;
  SessionStatus _status = SessionStatus.restoring;
  String? _error;
  String? _notice;
  Future<bool>? _refreshOperation;

  SessionStatus get status => _status;
  String? get error => _error;
  String? get notice => _notice;

  Future<void> restore() async {
    _setStatus(SessionStatus.restoring);
    _refreshToken = await _tokenStore.read();
    if (_refreshToken == null) {
      _setStatus(SessionStatus.signedOut);
      return;
    }
    if (!await refreshAccessToken()) {
      await _tokenStore.clear();
      _refreshToken = null;
      _setStatus(SessionStatus.signedOut);
    }
  }

  Future<void> login(String email, String password) async {
    _notice = null;
    _error = null;
    _setStatus(SessionStatus.authenticating);
    try {
      final AuthTokens tokens = await api.login(email, password);
      await _applyTokens(tokens);
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
      // The backend revokes existing refresh sessions after a password change.
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

  Future<void> _clearSession() async {
    _accessToken = null;
    _refreshToken = null;
    await _tokenStore.clear();
  }

  Future<void> _applyTokens(AuthTokens tokens) async {
    _accessToken = tokens.accessToken;
    _refreshToken = tokens.refreshToken;
    await _tokenStore.write(tokens.refreshToken);
  }

  void _setStatus(SessionStatus value) {
    _status = value;
    notifyListeners();
  }
}
