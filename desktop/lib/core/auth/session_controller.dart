import 'dart:async';

import 'package:flutter/foundation.dart';

import '../api/api_client.dart';
import '../preferences/desktop_preferences_service.dart';
import '../preferences/user_preferences.dart';
import '../../models/entities.dart';
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
    void Function(String? accessToken)? onAccessTokenChanged,
    Duration sessionTimeout = const Duration(minutes: 30),
  })  : _tokenStore = tokenStore ?? MigratingRefreshTokenStore(),
        _preferences = preferences ?? DesktopPreferencesService(),
        _baseUrl = baseUrl,
        _onPreferencesSynchronized = onPreferencesSynchronized,
        _onAccessTokenChanged = onAccessTokenChanged,
        _sessionTimeout = sessionTimeout {
    _rememberMe = _preferences.current.rememberMe;
    _createApiClient();
  }

  late ApiClient api;
  final RefreshTokenStore _tokenStore;
  final DesktopPreferencesService _preferences;
  final Future<void> Function(UserPreferences preferences)?
      _onPreferencesSynchronized;
  final void Function(String? accessToken)? _onAccessTokenChanged;
  final Duration _sessionTimeout;
  String _baseUrl;
  String? _accessToken;
  String? _refreshToken;
  bool _rememberMe = false;
  SessionStatus _status = SessionStatus.restoring;
  String? _error;
  String? _notice;
  String? _attemptedUsername;
  Future<bool>? _refreshOperation;
  Timer? _sessionTimer;
  UserPreferences? _serverPreferences;
  List<AssignedFirm> _firms = const [];
  AssignedFirm? _currentFirm;
  int _firmContextVersion = 0;

  SessionStatus get status => _status;
  String? get error => _error;
  String? get notice => _notice;
  String? get attemptedUsername => _attemptedUsername;
  String get baseUrl => _baseUrl;
  String? get accessToken => _accessToken;
  UserPreferences? get serverPreferences => _serverPreferences;
  List<AssignedFirm> get firms => List.unmodifiable(_firms);
  AssignedFirm? get currentFirm => _currentFirm;
  int get firmContextVersion => _firmContextVersion;
  String? get lastWorkspace => _preferences.current.lastWorkspace;

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
    _attemptedUsername = email;
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
      _setStatus(tokens.forcePasswordChange
          ? SessionStatus.requiresPasswordChange
          : SessionStatus.authenticated);
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
    await _applyServerPreferences(updated);
  }

  Future<void> switchFirm(String firmId) async {
    final AssignedFirm firm = _firms.firstWhere(
      (item) => item.id == firmId,
      orElse: () => throw const ApiException(
        'The selected firm is not assigned to this user.',
      ),
    );
    if (_currentFirm?.id == firm.id) return;
    final UserPreferences updated =
        await api.updateUserPreferences({'default_firm_id': firm.id});
    _currentFirm = firm;
    _firmContextVersion++;
    await _applyServerPreferences(updated);
    registerActivity();
    notifyListeners();
  }

  Future<void> saveLastWorkspace(String location) =>
      _preferences.saveLastWorkspace(location);

  void registerActivity() {
    if (_accessToken == null) return;
    _sessionTimer?.cancel();
    _sessionTimer = Timer(_sessionTimeout, _expireInactiveSession);
  }

  Future<void> _synchronizePreferences() async {
    try {
      final UserPreferences preferences = await api.getUserPreferences();
      final List<AssignedFirm> firms = await api.myFirms();
      _firms = firms;
      _currentFirm = _resolveCurrentFirm(firms, preferences.defaultFirmId);
      final UserPreferences synchronizedPreferences =
          _currentFirm != null && preferences.defaultFirmId != _currentFirm!.id
              ? await api.updateUserPreferences(
                  {'default_firm_id': _currentFirm!.id},
                )
              : preferences;
      await _applyServerPreferences(synchronizedPreferences);
      registerActivity();
      notifyListeners();
    } on ApiException catch (exception) {
      _notice = 'Signed in, but preferences could not be synchronized: '
          '${exception.message}';
    } on FormatException catch (exception) {
      _notice = 'Signed in, but preferences could not be synchronized: '
          '${exception.message}';
    }
  }

  Future<void> _clearSession() async {
    _sessionTimer?.cancel();
    _accessToken = null;
    _refreshToken = null;
    _serverPreferences = null;
    _firms = const [];
    _currentFirm = null;
    _firmContextVersion++;
    _onAccessTokenChanged?.call(null);
    await _tokenStore.clear();
  }

  Future<void> _applyTokens(AuthTokens tokens) async {
    _accessToken = tokens.accessToken;
    _refreshToken = tokens.refreshToken;
    _onAccessTokenChanged?.call(_accessToken);
    if (_rememberMe) {
      await _tokenStore.write(tokens.refreshToken);
    } else {
      await _tokenStore.clear();
    }
    registerActivity();
  }

  void _createApiClient() {
    api = ApiClient(
      baseUrl: _baseUrl,
      accessToken: () => _accessToken,
      refreshAccessToken: refreshAccessToken,
      activeFirmId: () => _currentFirm?.id,
      onRequest: registerActivity,
    );
  }

  Future<void> _applyServerPreferences(UserPreferences preferences) async {
    _serverPreferences = preferences;
    await _preferences.cacheServerPreferences(preferences.toJson());
    if (_onPreferencesSynchronized != null) {
      await _onPreferencesSynchronized(preferences);
    }
  }

  AssignedFirm? _resolveCurrentFirm(
    List<AssignedFirm> firms,
    String? preferredFirmId,
  ) {
    if (firms.isEmpty) return null;
    for (final AssignedFirm firm in firms) {
      if (firm.id == preferredFirmId) return firm;
    }
    for (final AssignedFirm firm in firms) {
      if (firm.isPrimary) return firm;
    }
    return firms.first;
  }

  Future<void> _expireInactiveSession() async {
    await _clearSession();
    _notice = 'Your session ended after a period of inactivity.';
    _setStatus(SessionStatus.signedOut);
  }

  void _setStatus(SessionStatus value) {
    _status = value;
    notifyListeners();
  }

  @override
  void dispose() {
    _sessionTimer?.cancel();
    super.dispose();
  }
}
