/// The palette a server reported, or the one implied by an older server.
///
/// A server that predates the palette/mode split sends only `preferred_theme`.
/// "blue" and "green" were palettes there and stay palettes here; "dark" and
/// "light" were modes and imply no palette at all.
String? _legacyPalette(Map<String, dynamic> json) {
  final Object? current = json['preferred_palette'];
  if (current is String && current.isNotEmpty) return current;
  return switch (json['preferred_theme']) {
    'blue' => 'blue',
    'green' => 'green',
    _ => null,
  };
}

/// The mode a server reported, or the one implied by an older server.
///
/// Returns null rather than "light" when the old value carries no opinion, so
/// the client falls through to following the operating system.
String? _legacyThemeMode(Map<String, dynamic> json) {
  final Object? current = json['preferred_theme_mode'];
  if (current is String && current.isNotEmpty) return current;
  return switch (json['preferred_theme']) {
    'dark' || 'high_contrast' => 'dark',
    'light' => 'light',
    _ => null,
  };
}

class UserPreferences {
  const UserPreferences({
    required this.preferencesVersion,
    required this.preferredTheme,
    this.preferredPalette,
    this.preferredThemeMode,
    this.preferredHighContrast,
    required this.language,
    required this.dateFormat,
    required this.timeFormat,
    required this.numberFormat,
    required this.currencyFormat,
    required this.defaultFirmId,
    required this.defaultLandingPage,
    required this.rowsPerPage,
    required this.notificationPreferences,
    required this.dashboardLayout,
  });

  final int preferencesVersion;
  /// Retained for older servers, which stored palette and mode in one
  /// string. New clients read the three fields below and only fall back to
  /// deriving from this when a server has not been upgraded.
  final String preferredTheme;
  final String? preferredPalette;
  final String? preferredThemeMode;
  final bool? preferredHighContrast;
  final String language;
  final String dateFormat;
  final String timeFormat;
  final String numberFormat;
  final String currencyFormat;
  final String? defaultFirmId;
  final String defaultLandingPage;
  final int rowsPerPage;
  final Map<String, dynamic> notificationPreferences;
  final Map<String, dynamic> dashboardLayout;

  factory UserPreferences.fromJson(Map<String, dynamic> json) {
    String requiredString(String key) {
      final dynamic value = json[key];
      if (value is! String || value.isEmpty) {
        throw FormatException('Preference "$key" must be a non-empty string.');
      }
      return value;
    }

    Map<String, dynamic> object(String key) {
      final dynamic value = json[key];
      if (value is! Map) {
        throw FormatException('Preference "$key" must be an object.');
      }
      return Map<String, dynamic>.from(value);
    }

    final int version = (json['preferences_version'] as num?)?.toInt() ?? 0;
    final int rows = (json['rows_per_page'] as num?)?.toInt() ?? 0;
    if (version < 1 || rows < 1) {
      throw const FormatException(
          'Preference version or rows per page is invalid.');
    }
    final dynamic defaultFirm = json['default_firm_id'];
    if (defaultFirm != null && defaultFirm is! String) {
      throw const FormatException(
          'Preference "default_firm_id" must be a string.');
    }
    return UserPreferences(
      preferencesVersion: version,
      preferredTheme: requiredString('preferred_theme'),
      preferredPalette: _legacyPalette(json),
      preferredThemeMode: _legacyThemeMode(json),
      preferredHighContrast: json['preferred_high_contrast'] is bool
          ? json['preferred_high_contrast'] as bool
          : json['preferred_theme'] == 'high_contrast',
      language: requiredString('language'),
      dateFormat: requiredString('date_format'),
      timeFormat: requiredString('time_format'),
      numberFormat: requiredString('number_format'),
      currencyFormat: requiredString('currency_format'),
      defaultFirmId: defaultFirm as String?,
      defaultLandingPage: requiredString('default_landing_page'),
      rowsPerPage: rows,
      notificationPreferences: object('notification_preferences'),
      dashboardLayout: object('dashboard_layout'),
    );
  }

  Map<String, dynamic> toJson() => {
        'preferences_version': preferencesVersion,
        'preferred_theme': preferredTheme,
        if (preferredPalette != null) 'preferred_palette': preferredPalette,
        if (preferredThemeMode != null)
          'preferred_theme_mode': preferredThemeMode,
        if (preferredHighContrast != null)
          'preferred_high_contrast': preferredHighContrast,
        'language': language,
        'date_format': dateFormat,
        'time_format': timeFormat,
        'number_format': numberFormat,
        'currency_format': currencyFormat,
        'default_firm_id': defaultFirmId,
        'default_landing_page': defaultLandingPage,
        'rows_per_page': rowsPerPage,
        'notification_preferences': notificationPreferences,
        'dashboard_layout': dashboardLayout,
      };
}
