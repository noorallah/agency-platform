import 'dart:convert';
import 'dart:io';

String normalizeServerUrl(String value) {
  final Uri uri = Uri.parse(value.trim());
  final bool loopback =
      uri.host == 'localhost' || uri.host == '127.0.0.1' || uri.host == '::1';
  if (!uri.hasAuthority ||
      (uri.scheme != 'https' && !(uri.scheme == 'http' && loopback)) ||
      uri.userInfo.isNotEmpty ||
      uri.query.isNotEmpty ||
      uri.fragment.isNotEmpty) {
    throw const FormatException(
      'Use an HTTPS server URL. HTTP is allowed only for localhost.',
    );
  }
  return uri.toString().replaceFirst(RegExp(r'/$'), '');
}

enum GridDensity { compact, comfortable, spacious }

extension GridDensityDetails on GridDensity {
  String get wireName => name;

  static GridDensity fromWireName(String? value) =>
      GridDensity.values.firstWhere(
        (density) => density.wireName == value,
        orElse: () => GridDensity.comfortable,
      );
}

/// Read the palette, honouring what an older build stored.
///
/// The previous release kept one `cached_theme` string mixing palette and
/// mode. A user who had chosen "Blue" should still get blue; one who had
/// chosen "Dark" was choosing a mode, not a palette, and keeps the default
/// accent.
String _paletteFrom(Map<String, dynamic> json) {
  final Object? current = json['cached_palette'];
  if (current is String && current.isNotEmpty) return current;
  return switch (json['cached_theme']) {
    'blue' => 'blue',
    'green' => 'green',
    _ => 'neutral',
  };
}

/// Read the mode, honouring what an older build stored.
///
/// Only an explicit past choice of light or dark carries over. Anything else --
/// including the old hardcoded `light` default that nobody actually chose --
/// becomes `system`, which is the point of the change.
String _themeModeFrom(Map<String, dynamic> json) {
  final Object? current = json['cached_theme_mode'];
  if (current is String && current.isNotEmpty) return current;
  return switch (json['cached_theme']) {
    'dark' || 'high_contrast' => 'dark',
    _ => 'system',
  };
}

class DesktopPreferences {
  const DesktopPreferences({
    this.version = 1,
    this.rememberUsername = false,
    this.rememberMe = false,
    this.cachedUsername,
    this.recentUsernames = const [],
    this.serverUrl = 'http://localhost:8000',
    this.recentServers = const [],
    this.cachedPalette = 'neutral',
    this.cachedThemeMode = 'system',
    this.cachedHighContrast = false,
    this.windowState = const {},
    this.lastWorkspace,
    this.serverPreferences = const {},
    this.sidebarCollapsed = false,
    this.gridDensity = GridDensity.comfortable,
    this.defaultLandingPage = 'dashboard',
  });

  final int version;
  final bool rememberUsername;
  final bool rememberMe;
  final String? cachedUsername;
  final List<String> recentUsernames;
  final String serverUrl;
  final List<String> recentServers;
  final String cachedPalette;

  /// Defaults to `system`, so a machine running Windows in dark mode is
  /// not greeted with a white screen on first run.
  final String cachedThemeMode;
  final bool cachedHighContrast;
  final Map<String, dynamic> windowState;
  final String? lastWorkspace;
  final Map<String, dynamic> serverPreferences;
  final bool sidebarCollapsed;
  final GridDensity gridDensity;
  final String defaultLandingPage;

  factory DesktopPreferences.fromJson(Map<String, dynamic> json) {
    List<String> strings(dynamic value) => value is List
        ? value.whereType<String>().where((entry) => entry.isNotEmpty).toList()
        : const [];
    Map<String, dynamic> object(dynamic value) =>
        value is Map ? Map<String, dynamic>.from(value) : const {};
    String? optionalString(dynamic value) => value is String ? value : null;
    final List<String> recentUsernames =
        strings(json['recent_usernames']).toList(growable: false);
    final String? cachedUsername = optionalString(json['cached_username']);
    return DesktopPreferences(
      version: (json['version'] as num?)?.toInt() ?? 1,
      rememberUsername: json['remember_username'] == true,
      rememberMe: json['remember_me'] == true,
      cachedUsername: cachedUsername,
      recentUsernames: recentUsernames.isNotEmpty
          ? recentUsernames
          : cachedUsername == null || cachedUsername.isEmpty
              ? const []
              : [cachedUsername],
      serverUrl: optionalString(json['server_url']) ?? 'http://localhost:8000',
      recentServers: strings(json['recent_servers']),
      cachedPalette: _paletteFrom(json),
      cachedThemeMode: _themeModeFrom(json),
      cachedHighContrast: json['cached_high_contrast'] == true ||
          optionalString(json['cached_theme']) == 'high_contrast',
      windowState: object(json['window_state']),
      lastWorkspace: optionalString(json['last_workspace']),
      serverPreferences: object(json['server_preferences']),
      sidebarCollapsed: json['sidebar_collapsed'] == true,
      gridDensity:
          GridDensityDetails.fromWireName(optionalString(json['grid_density'])),
      defaultLandingPage:
          optionalString(json['default_landing_page']) ?? 'dashboard',
    );
  }

  Map<String, dynamic> toJson() => {
        'version': version,
        'remember_username': rememberUsername,
        'remember_me': rememberMe,
        'cached_username': cachedUsername,
        'recent_usernames': recentUsernames,
        'server_url': serverUrl,
        'recent_servers': recentServers,
        'cached_palette': cachedPalette,
        'cached_theme_mode': cachedThemeMode,
        'cached_high_contrast': cachedHighContrast,
        'window_state': windowState,
        'last_workspace': lastWorkspace,
        'server_preferences': serverPreferences,
        'sidebar_collapsed': sidebarCollapsed,
        'grid_density': gridDensity.wireName,
        'default_landing_page': defaultLandingPage,
      };

  DesktopPreferences copyWith({
    bool? rememberUsername,
    bool? rememberMe,
    String? cachedUsername,
    bool clearCachedUsername = false,
    List<String>? recentUsernames,
    String? serverUrl,
    List<String>? recentServers,
    String? cachedPalette,
    String? cachedThemeMode,
    bool? cachedHighContrast,
    Map<String, dynamic>? windowState,
    String? lastWorkspace,
    bool clearLastWorkspace = false,
    Map<String, dynamic>? serverPreferences,
    bool? sidebarCollapsed,
    GridDensity? gridDensity,
    String? defaultLandingPage,
  }) =>
      DesktopPreferences(
        version: version,
        rememberUsername: rememberUsername ?? this.rememberUsername,
        rememberMe: rememberMe ?? this.rememberMe,
        cachedUsername:
            clearCachedUsername ? null : cachedUsername ?? this.cachedUsername,
        recentUsernames: recentUsernames ?? this.recentUsernames,
        serverUrl: serverUrl ?? this.serverUrl,
        recentServers: recentServers ?? this.recentServers,
        cachedPalette: cachedPalette ?? this.cachedPalette,
        cachedThemeMode: cachedThemeMode ?? this.cachedThemeMode,
        cachedHighContrast: cachedHighContrast ?? this.cachedHighContrast,
        windowState: windowState ?? this.windowState,
        lastWorkspace:
            clearLastWorkspace ? null : lastWorkspace ?? this.lastWorkspace,
        serverPreferences: serverPreferences ?? this.serverPreferences,
        sidebarCollapsed: sidebarCollapsed ?? this.sidebarCollapsed,
        gridDensity: gridDensity ?? this.gridDensity,
        defaultLandingPage: defaultLandingPage ?? this.defaultLandingPage,
      );
}

class DesktopPreferencesService {
  DesktopPreferencesService({Directory? directory})
      : _directory = directory ?? _defaultDirectory();

  final Directory _directory;
  DesktopPreferences _preferences = const DesktopPreferences();
  bool _hasStoredPreferences = false;

  DesktopPreferences get current => _preferences;
  bool get hasStoredPreferences => _hasStoredPreferences;

  static Directory _defaultDirectory() {
    final String? configured = Platform.environment['APPDATA'] ??
        Platform.environment['XDG_CONFIG_HOME'] ??
        Platform.environment['HOME'];
    return Directory(
      '${configured ?? Directory.current.path}${Platform.pathSeparator}.agency_platform',
    );
  }

  File get _file => File(
      '${_directory.path}${Platform.pathSeparator}desktop_preferences.json');

  Future<void> load() async {
    if (!await _file.exists()) {
      return;
    }
    try {
      final dynamic value = jsonDecode(await _file.readAsString());
      if (value is! Map<String, dynamic>) {
        throw const FormatException(
            'Desktop preferences must be a JSON object.');
      }
      _preferences = DesktopPreferences.fromJson(value);
      _hasStoredPreferences = true;
    } on FileSystemException catch (error) {
      stderr.writeln('Unable to read desktop preferences: $error');
      _preferences = const DesktopPreferences();
    } on FormatException catch (error) {
      stderr.writeln('Invalid desktop preferences; using defaults: $error');
      _preferences = const DesktopPreferences();
    }
  }

  Future<void> saveLoginOptions({
    required bool rememberUsername,
    required bool rememberMe,
    required String username,
  }) {
    final List<String> recentUsernames = rememberUsername
        ? <String>[
            username,
            ..._preferences.recentUsernames.where((entry) => entry != username),
          ].take(8).toList()
        : _preferences.recentUsernames;
    return _save(
      _preferences.copyWith(
        rememberUsername: rememberUsername,
        rememberMe: rememberMe,
        cachedUsername: username,
        clearCachedUsername: !rememberUsername,
        recentUsernames: recentUsernames,
      ),
    );
  }

  Future<void> saveServerUrl(String url) {
    final String normalized = normalizeServerUrl(url);
    final List<String> recent = [
      normalized,
      ..._preferences.recentServers.where((entry) => entry != normalized),
    ].take(8).toList();
    return _save(
        _preferences.copyWith(serverUrl: normalized, recentServers: recent));
  }

  Future<void> saveAppearance({
    required String palette,
    required String themeMode,
    required bool highContrast,
  }) =>
      _save(
        _preferences.copyWith(
          cachedPalette: palette,
          cachedThemeMode: themeMode,
          cachedHighContrast: highContrast,
        ),
      );

  Future<void> saveWindowState(Map<String, dynamic> state) =>
      _save(_preferences.copyWith(windowState: state));

  Future<void> saveLastWorkspace(String? workspace) =>
      _save(_preferences.copyWith(
        lastWorkspace: workspace,
        clearLastWorkspace: workspace == null,
      ));

  Future<void> cacheServerPreferences(Map<String, dynamic> preferences) =>
      _save(_preferences.copyWith(serverPreferences: preferences));

  Future<void> saveSidebarCollapsed(bool collapsed) =>
      _save(_preferences.copyWith(sidebarCollapsed: collapsed));

  Future<void> saveGridDensity(GridDensity density) =>
      _save(_preferences.copyWith(gridDensity: density));

  Future<void> saveDefaultLandingPage(String page) =>
      _save(_preferences.copyWith(defaultLandingPage: page));

  Future<void> _save(DesktopPreferences preferences) async {
    _preferences = preferences;
    try {
      await _directory.create(recursive: true);
      await _file.writeAsString(jsonEncode(preferences.toJson()), flush: true);
      _hasStoredPreferences = true;
    } on FileSystemException catch (error) {
      stderr.writeln('Unable to save desktop preferences: $error');
    }
  }
}
