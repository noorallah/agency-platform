import 'package:flutter/material.dart';

import '../design/design_tokens.dart';
import '../preferences/desktop_preferences_service.dart';

/// The accent identity of the application, independent of light or dark.
///
/// This used to be one enum mixing both ideas -- `{light, dark, blue, green,
/// highContrast}` -- which is why "Blue" and "Green" were light-only, why
/// "Dark" was a mode pretending to be a palette, and why "follow the system"
/// had nowhere to live. Palette and mode are orthogonal: every palette is
/// built in both brightnesses, and the mode decides which one is shown.
enum AppPalette { neutral, blue, green }

extension AppPaletteDetails on AppPalette {
  String get wireName => switch (this) {
        AppPalette.neutral => 'neutral',
        AppPalette.blue => 'blue',
        AppPalette.green => 'green',
      };

  String get label => switch (this) {
        AppPalette.neutral => 'Default',
        AppPalette.blue => 'Blue',
        AppPalette.green => 'Green',
      };

  /// The hue each palette is built from, chosen to stay legible on both grounds.
  Color get seed => switch (this) {
        AppPalette.neutral => const Color(0xff155eef),
        AppPalette.blue => const Color(0xff0067b8),
        AppPalette.green => const Color(0xff147d45),
      };

  static AppPalette fromWireName(String? value) => AppPalette.values.firstWhere(
        (palette) => palette.wireName == value,
        orElse: () => AppPalette.neutral,
      );
}

extension AppThemeModeDetails on ThemeMode {
  String get wireName => switch (this) {
        ThemeMode.system => 'system',
        ThemeMode.light => 'light',
        ThemeMode.dark => 'dark',
      };

  String get label => switch (this) {
        ThemeMode.system => 'Match Windows',
        ThemeMode.light => 'Light',
        ThemeMode.dark => 'Dark',
      };

  /// Falls back to following the operating system.
  ///
  /// The old fallback was `light`, which is how a user running Windows in dark
  /// mode ended up with a white screen on first run. Deferring to the system
  /// is the only defensible default for a value nobody has chosen.
  static ThemeMode fromWireName(String? value) => switch (value) {
        'light' => ThemeMode.light,
        'dark' => ThemeMode.dark,
        _ => ThemeMode.system,
      };
}

/// Holds the user's appearance choices and rebuilds the app when they change.
class ThemeManager extends ChangeNotifier {
  ThemeManager(this._preferences)
      : _palette = AppPaletteDetails.fromWireName(
          _preferences.current.cachedPalette,
        ),
        _mode = AppThemeModeDetails.fromWireName(
          _preferences.current.cachedThemeMode,
        ),
        _highContrast = _preferences.current.cachedHighContrast,
        _density = _preferences.current.gridDensity;

  final DesktopPreferencesService _preferences;
  AppPalette _palette;
  ThemeMode _mode;
  bool _highContrast;
  GridDensity _density;
  Future<void> Function(String palette, String mode, bool highContrast)?
      _serverSync;

  AppPalette get palette => _palette;
  ThemeMode get mode => _mode;
  bool get highContrast => _highContrast;
  GridDensity get density => _density;

  /// The light half of the pair. `MaterialApp.theme`.
  ThemeData get lightTheme => ThemeRegistry.themeFor(
        palette: _palette,
        brightness: Brightness.light,
        highContrast: _highContrast,
        density: _density,
      );

  /// The dark half of the pair. `MaterialApp.darkTheme`.
  ///
  /// Both halves are always built; `themeMode` decides which one Flutter uses,
  /// and only Flutter can see the operating system's setting.
  ThemeData get darkTheme => ThemeRegistry.themeFor(
        palette: _palette,
        brightness: Brightness.dark,
        highContrast: _highContrast,
        density: _density,
      );

  void bindServerSync(
    Future<void> Function(String palette, String mode, bool highContrast)
        serverSync,
  ) {
    _serverSync = serverSync;
  }

  Future<void> selectPalette(AppPalette palette) =>
      _apply(palette: palette, mode: _mode, highContrast: _highContrast);

  Future<void> selectMode(ThemeMode mode) =>
      _apply(palette: _palette, mode: mode, highContrast: _highContrast);

  Future<void> setHighContrast(bool enabled) =>
      _apply(palette: _palette, mode: _mode, highContrast: enabled);

  /// Change how tightly the interface packs.
  ///
  /// Stored through the setter that has existed unused since the beginning.
  Future<void> selectDensity(GridDensity density) async {
    if (density == _density) return;
    _density = density;
    notifyListeners();
    await _preferences.saveGridDensity(density);
  }

  /// Adopt the appearance stored on the server without echoing it back.
  Future<void> applyServerAppearance({
    String? palette,
    String? mode,
    bool? highContrast,
  }) =>
      _apply(
        palette: AppPaletteDetails.fromWireName(palette),
        mode: AppThemeModeDetails.fromWireName(mode),
        highContrast: highContrast ?? _highContrast,
        synchronize: false,
      );

  Future<void> _apply({
    required AppPalette palette,
    required ThemeMode mode,
    required bool highContrast,
    bool synchronize = true,
  }) async {
    final bool changed = palette != _palette ||
        mode != _mode ||
        highContrast != _highContrast;
    if (changed) {
      _palette = palette;
      _mode = mode;
      _highContrast = highContrast;
      notifyListeners();
    }
    await _preferences.saveAppearance(
      palette: palette.wireName,
      themeMode: mode.wireName,
      highContrast: highContrast,
    );
    if (synchronize && _serverSync != null) {
      await _serverSync!(palette.wireName, mode.wireName, highContrast);
    }
  }
}

/// Builds the application theme for one palette in one brightness.
class ThemeRegistry {
  static ThemeData themeFor({
    required AppPalette palette,
    required Brightness brightness,
    bool highContrast = false,
    GridDensity density = GridDensity.comfortable,
  }) {
    final AppDensityTokens spacing = switch (density) {
      GridDensity.compact => AppDensityTokens.compact,
      GridDensity.comfortable => AppDensityTokens.comfortable,
      GridDensity.spacious => AppDensityTokens.spacious,
    };
    // High contrast is a modifier on whatever the user is already using, not a
    // theme of its own. It used to be a yellow-seeded dark theme, which is not
    // what anyone means by high contrast and forced a palette change to get it.
    final ColorScheme scheme = ColorScheme.fromSeed(
      seedColor: palette.seed,
      brightness: brightness,
      contrastLevel: highContrast ? 1.0 : 0.0,
    );
    final bool dark = brightness == Brightness.dark;

    // Designed grounds rather than whatever the tonal algorithm emits. Neither
    // is pure black or pure white: a full-white page is the single biggest
    // source of glare over a long shift, and pure black makes light text
    // shimmer against it.
    final ColorScheme tuned = dark
        ? scheme.copyWith(
            surface: const Color(0xff14181b),
            surfaceContainerLowest: const Color(0xff0f1315),
            surfaceContainerLow: const Color(0xff181d20),
            surfaceContainer: const Color(0xff1c2225),
            surfaceContainerHigh: const Color(0xff222829),
            surfaceContainerHighest: const Color(0xff272d2f),
          )
        : scheme.copyWith(
            surface: const Color(0xfff7f9fa),
            surfaceContainerLowest: Colors.white,
            surfaceContainerLow: const Color(0xfff2f5f7),
            surfaceContainer: const Color(0xffedf1f3),
            surfaceContainerHigh: const Color(0xffe7ecef),
            surfaceContainerHighest: const Color(0xffe1e7ea),
          );

    final TextTheme textTheme = AppTypography.textTheme(tuned);
    final BorderSide borderSide =
        BorderSide(color: tuned.outlineVariant, width: 1);

    return ThemeData(
      colorScheme: tuned,
      useMaterial3: true,
      scaffoldBackgroundColor: tuned.surface,
      visualDensity: spacing.visualDensity,
      extensions: [AppSemanticColors.forScheme(tuned), spacing],
      // Applied here rather than at ~20 grid call sites, which is the whole
      // reason density is a theme concern and not a widget parameter.
      dataTableTheme: DataTableThemeData(
        headingRowHeight: spacing.headerHeight,
        dataRowMinHeight: spacing.rowHeight,
        dataRowMaxHeight: spacing.rowHeight,
        headingTextStyle: textTheme.labelSmall,
        dataTextStyle: textTheme.bodyMedium,
      ),
      listTileTheme: ListTileThemeData(
        minVerticalPadding: spacing.fieldGap / 2,
        dense: density == GridDensity.compact,
      ),
      textTheme: textTheme,
      dividerTheme: DividerThemeData(color: tuned.outlineVariant, space: 1),
      cardTheme: CardThemeData(
        color: tuned.surfaceContainerLowest,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: AppRadius.medium,
          side: borderSide,
        ),
        margin: EdgeInsets.zero,
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: tuned.surfaceContainerLowest,
        contentPadding: EdgeInsets.symmetric(
          horizontal: AppSpacing.md,
          vertical: spacing.fieldGap,
        ),
        hintStyle: textTheme.bodyMedium?.copyWith(color: tuned.onSurfaceVariant),
        labelStyle: textTheme.bodyMedium?.copyWith(color: tuned.onSurfaceVariant),
        enabledBorder: OutlineInputBorder(
          borderRadius: AppRadius.medium,
          borderSide: borderSide,
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: AppRadius.medium,
          borderSide: BorderSide(color: tuned.primary, width: 1.6),
        ),
        errorBorder: OutlineInputBorder(
          borderRadius: AppRadius.medium,
          borderSide: BorderSide(color: tuned.error, width: 1.4),
        ),
        focusedErrorBorder: OutlineInputBorder(
          borderRadius: AppRadius.medium,
          borderSide: BorderSide(color: tuned.error, width: 1.8),
        ),
      ),
    );
  }
}
