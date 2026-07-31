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

class DesktopPreferences {
  const DesktopPreferences({
    this.version = 1,
    this.rememberUsername = false,
    this.rememberMe = false,
    this.cachedUsername,
    this.serverUrl = 'http://localhost:8000',
    this.recentServers = const [],
    this.cachedTheme = 'light',
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
  final String serverUrl;
  final List<String> recentServers;
  final String cachedTheme;
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
    return DesktopPreferences(
      version: (json['version'] as num?)?.toInt() ?? 1,
      rememberUsername: json['remember_username'] == true,
      rememberMe: json['remember_me'] == true,
      cachedUsername: optionalString(json['cached_username']),
      serverUrl: optionalString(json['server_url']) ?? 'http://localhost:8000',
      recentServers: strings(json['recent_servers']),
      cachedTheme: optionalString(json['cached_theme']) ?? 'light',
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
        'server_url': serverUrl,
        'recent_servers': recentServers,
        'cached_theme': cachedTheme,
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
    String? serverUrl,
    List<String>? recentServers,
    String? cachedTheme,
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
        serverUrl: serverUrl ?? this.serverUrl,
        recentServers: recentServers ?? this.recentServers,
        cachedTheme: cachedTheme ?? this.cachedTheme,
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
  }) =>
      _save(
        _preferences.copyWith(
          rememberUsername: rememberUsername,
          rememberMe: rememberMe,
          cachedUsername: username,
          clearCachedUsername: !rememberUsername,
        ),
      );

  Future<void> saveServerUrl(String url) {
    final String normalized = normalizeServerUrl(url);
    final List<String> recent = [
      normalized,
      ..._preferences.recentServers.where((entry) => entry != normalized),
    ].take(8).toList();
    return _save(
        _preferences.copyWith(serverUrl: normalized, recentServers: recent));
  }

  Future<void> saveTheme(String theme) =>
      _save(_preferences.copyWith(cachedTheme: theme));

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
