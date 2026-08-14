import 'dart:convert';
import 'dart:io';

/// Whether an address is one the traffic to it cannot leave the local network.
///
/// Loopback, the private IPv4 ranges, IPv4 link-local, and the IPv6 equivalents
/// -- unique-local `fc00::/7` and link-local `fe80::/10`. A name is treated as
/// local when it cannot resolve on the public internet: a single label with no
/// dots (`server01`), or one of the suffixes reserved for local naming.
///
/// This decides where plain HTTP is allowed, so it errs towards saying no. An
/// address it cannot classify is not local.
bool isPrivateNetworkHost(String host) {
  final String name = host.toLowerCase().replaceAll(RegExp(r'^\[|\]$'), '');
  if (name.isEmpty) return false;
  if (name == 'localhost' || name == '::1') return true;

  final List<String> octets = name.split('.');
  if (octets.length == 4 && octets.every((part) => int.tryParse(part) != null)) {
    final List<int> parts = octets.map(int.parse).toList();
    if (parts.any((part) => part < 0 || part > 255)) return false;
    if (parts[0] == 127) return true; // loopback
    if (parts[0] == 10) return true; // 10/8
    if (parts[0] == 172 && parts[1] >= 16 && parts[1] <= 31) return true;
    if (parts[0] == 192 && parts[1] == 168) return true;
    if (parts[0] == 169 && parts[1] == 254) return true; // link-local
    return false; // any other literal address is public
  }

  if (name.contains(':')) {
    // IPv6 literal. fc00::/7 is unique-local, fe80::/10 link-local.
    final String head = name.split(':').first;
    if (head.length >= 2) {
      final int? leading = int.tryParse(head.substring(0, 2), radix: 16);
      if (leading != null && leading >= 0xfc && leading <= 0xfd) return true;
      if (leading != null && leading >= 0xfe && leading <= 0xfe) {
        return head.length >= 3 &&
            (head[2] == '8' || head[2] == '9' || head[2] == 'a' || head[2] == 'b');
      }
    }
    return false;
  }

  if (!name.contains('.')) return true; // a bare hostname is a LAN name
  return const ['.local', '.lan', '.internal', '.home.arpa']
      .any((suffix) => name.endsWith(suffix));
}

/// Validate and tidy a server address the user typed.
///
/// **HTTPS is accepted anywhere. Plain HTTP is accepted on the local network
/// only** -- loopback, the private ranges, and names that cannot resolve
/// publicly.
///
/// The product is deployed as a client on one machine and a backend on another
/// in the same building, and requiring HTTPS everywhere made that deployment
/// impossible without an installer that puts a certificate in every client's
/// trust store. So plain HTTP over the LAN is a supported choice, made
/// deliberately: on that network the credentials and business data are readable
/// by anything else on the wire, which is a trade a firm running its own switch
/// can reasonably make and a firm on a shared network should not.
///
/// What stays refused is HTTP to a public address, because that is the same
/// data crossing the internet in clear text, and no deployment of this product
/// needs it. Use HTTPS there.
String normalizeServerUrl(String value) {
  final Uri uri = Uri.parse(value.trim());
  final bool localNetwork = isPrivateNetworkHost(uri.host);
  if (!uri.hasAuthority ||
      (uri.scheme != 'https' && !(uri.scheme == 'http' && localNetwork)) ||
      uri.userInfo.isNotEmpty ||
      uri.query.isNotEmpty ||
      uri.fragment.isNotEmpty) {
    throw const FormatException(
      'Use https://, or http:// with an address on your own network '
      '(localhost, 10.x, 172.16-31.x, 192.168.x, or a name with no dots). '
      'Plain HTTP to a public address would send passwords in clear text.',
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
