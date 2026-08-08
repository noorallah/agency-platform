import 'package:flutter/material.dart';

import '../design/design_tokens.dart';
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
    final BorderSide borderSide = BorderSide(color: scheme.outlineVariant, width: 1);
    final BorderSide focusedBorderSide = BorderSide(color: scheme.primary, width: 1.6);
    final BorderSide errorBorderSide = BorderSide(color: scheme.error, width: 1.4);

    return ThemeData(
      colorScheme: scheme,
      useMaterial3: true,
      extensions: [AppSemanticColors.forScheme(scheme)],
      textTheme: brightness == Brightness.dark
          ? Typography.material2021().white.copyWith(
              bodyMedium:
                  Typography.material2021().white.bodyMedium?.copyWith(fontSize: 14),
            )
          : Typography.material2021().black.copyWith(
              bodyMedium:
                  Typography.material2021().black.bodyMedium?.copyWith(fontSize: 14),
            ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: scheme.surfaceContainerHighest.withValues(alpha: 0.38),
        contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
        hintStyle: TextStyle(
          fontSize: 14,
          color: scheme.onSurfaceVariant,
        ),
        labelStyle: TextStyle(
          fontSize: 14,
          color: scheme.onSurfaceVariant,
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: borderSide,
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: focusedBorderSide,
        ),
        errorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: errorBorderSide,
        ),
        focusedErrorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: scheme.error, width: 1.8),
        ),
      ),
    );
  }
}
