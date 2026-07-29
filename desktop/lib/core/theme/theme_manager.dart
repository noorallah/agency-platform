import 'package:flutter/material.dart';

import '../preferences/desktop_preferences_service.dart';

enum AppTheme { light, dark, blue, green, highContrast }

extension AppThemeDetails on AppTheme {
  String get wireName => switch (this) {
        AppTheme.light => 'light',
        AppTheme.dark => 'dark',
        AppTheme.blue => 'blue',
        AppTheme.green => 'green',
        AppTheme.highContrast => 'high_contrast',
      };

  String get label => switch (this) {
        AppTheme.light => 'Light',
        AppTheme.dark => 'Dark',
        AppTheme.blue => 'Blue',
        AppTheme.green => 'Green',
        AppTheme.highContrast => 'High Contrast',
      };

  static AppTheme fromWireName(String value) => AppTheme.values.firstWhere(
        (theme) => theme.wireName == value,
        orElse: () => AppTheme.light,
      );
}

class ThemeManager extends ChangeNotifier {
  ThemeManager(this._preferences)
      : _current =
            AppThemeDetails.fromWireName(_preferences.current.cachedTheme);

  final DesktopPreferencesService _preferences;
  AppTheme _current;
  Future<void> Function(String theme)? _serverSync;

  AppTheme get current => _current;
  ThemeData get theme => ThemeRegistry.themeFor(_current);

  void bindServerSync(Future<void> Function(String theme) serverSync) {
    _serverSync = serverSync;
  }

  Future<void> select(AppTheme theme, {bool synchronize = true}) async {
    if (_current != theme) {
      _current = theme;
      notifyListeners();
    }
    await _preferences.saveTheme(theme.wireName);
    if (synchronize && _serverSync != null) {
      await _serverSync!(theme.wireName);
    }
  }

  Future<void> applyServerTheme(String value) async {
    await select(AppThemeDetails.fromWireName(value), synchronize: false);
  }
}

class ThemeRegistry {
  static ThemeData themeFor(AppTheme theme) {
    final Brightness brightness = switch (theme) {
      AppTheme.dark || AppTheme.highContrast => Brightness.dark,
      _ => Brightness.light,
    };
    final Color seed = switch (theme) {
      AppTheme.light => const Color(0xff155eef),
      AppTheme.dark => const Color(0xff6ea8fe),
      AppTheme.blue => const Color(0xff0067b8),
      AppTheme.green => const Color(0xff147d45),
      AppTheme.highContrast => Colors.yellow,
    };
    final ColorScheme scheme = ColorScheme.fromSeed(
      seedColor: seed,
      brightness: brightness,
      contrastLevel: theme == AppTheme.highContrast ? 1 : 0,
    );
    return ThemeData(
      colorScheme: scheme,
      useMaterial3: true,
      inputDecorationTheme: const InputDecorationTheme(
        border: OutlineInputBorder(),
      ),
    );
  }
}
