import 'dart:async';

import 'package:flutter/foundation.dart';

import '../api/api_client.dart';
import '../diagnostics/report_queue.dart';
import '../logging/app_log.dart';
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
    ReportQueue? reportQueue,
    bool Function()? isPlatformAdmin,
  })  : _isPlatformAdmin = isPlatformAdmin ?? _neverAPlatformAdmin,
        _tokenStore = tokenStore ?? MigratingRefreshTokenStore(),
        _reportQueue = reportQueue ?? ReportQueue(),
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
  final ReportQueue _reportQueue;
  final DesktopPreferencesService _preferences;
  final Future<void> Function(UserPreferences preferences)?
      _onPreferencesSynchronized;
  final void Function(String? accessToken)? _onAccessTokenChanged;
  final Duration _sessionTimeout;

  /// Whether the signed-in user carries the platform designation.
  ///
  /// Read through a callback rather than decoded here: `PermissionService`
  /// already owns the token's claims, and a second decoder is a second thing
  /// to get wrong. It is read *after* `_applyTokens`, which pushes the new
  /// token into that service, so it is current by the time it is asked.
  final bool Function() _isPlatformAdmin;

  static bool _neverAPlatformAdmin() => false;

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
  /// Where the shell opens: the screen this **user** was last on.
  ///
  /// The server's `default_landing_page` first, because it is the user's and
  /// travels with them; the local file is one per Windows account, so on a
  /// shared machine it holds whoever signed in last, and used to be the only
  /// answer -- user B landed on user A's screen. The local copy is still the
  /// fallback for a session whose preferences could not be read.
  String? get lastWorkspace =>
      _serverPreferences?.defaultLandingPage ??
      _preferences.current.lastWorkspace ??
      _preferences.current.defaultLandingPage;

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
    if (_status == SessionStatus.authenticating) {
      return;
    }
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
      // The first moment reports can be sent: they were queued on disk because
      // the failures worth having happen before login, offline, or as the
      // process dies. Unawaited -- a report must never delay signing in.
      unawaited(flushQueuedErrorReports());
    } on ApiException catch (exception) {
      _error = exception.message;
      _setStatus(SessionStatus.error);
    }
  }

  /// Sends anything the crash queue is holding. Failures are left queued.
  Future<void> flushQueuedErrorReports() async {
    try {
      await _reportQueue.flush(api.reportClientErrors);
    } on Object catch (error) {
      AppLog.warn('Flushing queued error reports failed: $error');
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
    await _preferences.saveServerUrl(normalizeServerUrl(value));
    _baseUrl = _preferences.current.serverUrl;
    _createApiClient();
    if (_accessToken != null || _refreshToken != null) {
      await _clearSession();
      _setStatus(SessionStatus.signedOut);
    }
  }

  /// Persist the user's appearance choices to the server.
  ///
  /// `preferred_theme` is still sent so an older server keeps working: it gets
  /// the closest single value it understands, while a current server reads the
  /// three explicit fields and ignores it.
  ///
  /// Every key here must be one the server declares -- it forbids unknown
  /// fields, so one stray key fails the whole request, and for a month
  /// `preferred_palette` was exactly that key: no appearance choice reached
  /// the server, and every sign-in restored its defaults over the local copy.
  /// `backend/tests/unit/test_desktop_preference_payloads_are_accepted.py`
  /// reads this method and asks the schema.
  Future<void> updatePreferredAppearance({
    required String palette,
    required String themeMode,
    required bool highContrast,
  }) async {
    final UserPreferences updated = await api.updateUserPreferences({
      'preferred_palette': palette,
      'preferred_theme_mode': themeMode,
      'preferred_high_contrast': highContrast,
      'preferred_theme': _legacyThemeValue(palette, themeMode, highContrast),
    });
    await _applyServerPreferences(updated);
  }

  /// Collapse the three values into the one an older server accepts.
  static String _legacyThemeValue(
    String palette,
    String themeMode,
    bool highContrast,
  ) {
    if (highContrast) return 'high_contrast';
    if (themeMode == 'dark') return 'dark';
    if (palette == 'blue' || palette == 'green') return palette;
    return 'light';
  }

  /// Re-read the firms this user may work in.
  ///
  /// The list is otherwise fetched once, at sign-in, by
  /// `_synchronizePreferences` -- so a platform administrator who created a
  /// firm could not select it until they signed out and back in. Creating one
  /// and then being unable to reach it is the whole of setting a firm up.
  ///
  /// The current selection is kept if it is still in the list, and dropped if
  /// it is not: a firm that has been retired underneath the session is not one
  /// to go on sending `X-Firm-ID` for.
  Future<void> refreshFirms() async {
    final List<AssignedFirm> firms = await api.myFirms();
    _firms = firms;
    final String? currentId = _currentFirm?.id;
    if (currentId != null && !firms.any((firm) => firm.id == currentId)) {
      _currentFirm = null;
      _firmContextVersion++;
    }
    notifyListeners();
  }

  /// Whether this session may work with no firm selected.
  ///
  /// Only a platform administrator can: for anybody else a null firm means an
  /// empty sidebar and an application that does nothing, which is a bug rather
  /// than a mode.
  bool get canWorkWithoutAFirm => _isPlatformAdmin();

  /// Select a firm, or pass null for platform mode.
  Future<void> switchFirm(String? firmId) async {
    if (firmId == null) {
      if (!canWorkWithoutAFirm) {
        throw const ApiException('Select a firm to continue.');
      }
      if (_currentFirm == null) return;
      _currentFirm = null;
      _firmContextVersion++;
      registerActivity();
      notifyListeners();
      return;
    }
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

  /// Remember the screen the user is on, here and on the server.
  ///
  /// Locally first, so it is kept even when the server is unreachable; then
  /// as the user's own `default_landing_page`, which is what [lastWorkspace]
  /// reads back at the next sign-in on any machine. A refusal is logged and
  /// not shown: nothing the user did has failed, and the local copy stands.
  Future<void> saveLastWorkspace(String location) async {
    await _preferences.saveLastWorkspace(location);
    if (_accessToken == null) return;
    if (_serverPreferences?.defaultLandingPage == location) return;
    try {
      final UserPreferences updated =
          await api.updateUserPreferences({'default_landing_page': location});
      _serverPreferences = updated;
      await _preferences.cacheServerPreferences(updated.toJson());
    } on ApiException catch (error) {
      AppLog.warn('Last screen not saved on the server: ${error.message}');
    } on FormatException catch (error) {
      AppLog.warn('Last screen not saved on the server: ${error.message}');
    }
  }

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
  ) =>
      resolveLandingFirm(
        firms,
        preferredFirmId,
        isPlatformAdmin: _isPlatformAdmin(),
      );

  /// Which firm a fresh session lands on, if any.
  ///
  /// A platform administrator lands on **none**, every time, whatever they
  /// were last working in. Their designation reaches every firm's books, so
  /// restoring a firm would drop them straight into somebody's ledgers on a
  /// screen that looks like their own. The stored `default_firm_id` is left
  /// untouched rather than cleared, so nothing is lost by it -- and the
  /// caller skips the write-back when this answers null, which is what keeps
  /// it that way.
  ///
  /// Static and public because it is the rule rather than a step: the
  /// controller builds its own `ApiClient`, so `_synchronizePreferences`
  /// cannot be driven from a test, and a private answer inside it would be
  /// one nothing could interrogate.
  static AssignedFirm? resolveLandingFirm(
    List<AssignedFirm> firms,
    String? preferredFirmId, {
    required bool isPlatformAdmin,
  }) {
    if (firms.isEmpty || isPlatformAdmin) return null;
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
