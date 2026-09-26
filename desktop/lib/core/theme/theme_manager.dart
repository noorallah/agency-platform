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
  ThemeManager(this._preferences, {this.wireframe = false})
      : _palette = AppPaletteDetails.fromWireName(
          _preferences.current.cachedPalette,
        ),
        _mode = AppThemeModeDetails.fromWireName(
          _preferences.current.cachedThemeMode,
        ),
        _highContrast = _preferences.current.cachedHighContrast,
        _density = _preferences.current.gridDensity;

  final DesktopPreferencesService _preferences;

  /// The phase 2 app: the light theme takes the wireframe's own greys and
  /// text (see [ThemeRegistry.themeFor]). Phase 1 keeps its colours.
  final bool wireframe;
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
        wireframe: wireframe,
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
    final bool changed =
        palette != _palette || mode != _mode || highContrast != _highContrast;
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
    bool wireframe = false,
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
    //
    // Text and borders are fixed too (UI_PHASE_2_DESIGN.md 4.14, the colour
    // mock-up the owner approved on 2026-09-26): dark-grey text rather than
    // near-black, and a control border that clears 3 : 1 -- the tonal
    // `outline` is fainter than that, which is how a field's edge or a hover
    // state ends up hard to see. `theme_contrast_test.dart` holds every pair
    // to the figures in 4.14. High contrast keeps the algorithm's text, which
    // is stronger still.
    final ColorScheme grounds = dark
        ? scheme.copyWith(
            surface: const Color(0xff14181b),
            surfaceContainerLowest: const Color(0xff1b2124),
            surfaceContainerLow: const Color(0xff1e2427),
            surfaceContainer: const Color(0xff20272b),
            surfaceContainerHigh: const Color(0xff242b2f),
            surfaceContainerHighest: const Color(0xff283034),
          )
        : scheme.copyWith(
            primary: palette.seed,
            onPrimary: Colors.white,
            surface: const Color(0xfff4f6f8),
            surfaceContainerLowest: const Color(0xfffbfcfd),
            surfaceContainerLow: const Color(0xfff1f4f7),
            surfaceContainer: const Color(0xffedf1f3),
            surfaceContainerHigh: const Color(0xffe7ecef),
            surfaceContainerHighest: const Color(0xffe1e7ea),
          );
    // Phase 2, light: the approved wireframe's own colours, which the owner
    // compared against the app on 2026-09-26 ("font little light", "background
    // not exactly matched") -- white where work is done (#ffffff), a neutral
    // grey for headings, bars and tabs (#f3f4f6, #e5e7eb) rather than the
    // bluish greys above, row lines #eaeef2, and text a shade darker than the
    // wireframe's #1f2328 because Flutter draws Segoe UI thinner than a
    // browser does.
    final ColorScheme? page = !(wireframe && !dark && !highContrast)
        ? null
        : scheme.copyWith(
            primary: palette.seed,
            onPrimary: Colors.white,
            surface: const Color(0xffffffff),
            surfaceContainerLowest: const Color(0xffffffff),
            surfaceContainerLow: const Color(0xfff3f4f6),
            surfaceContainer: const Color(0xffeef0f2),
            surfaceContainerHigh: const Color(0xffe5e7eb),
            surfaceContainerHighest: const Color(0xffeaeef2),
            onSurface: const Color(0xff16191d),
            onSurfaceVariant: const Color(0xff4d5761),
            outline: const Color(0xff6e7781),
            outlineVariant: const Color(0xffd0d7de),
          );
    final ColorScheme tuned = page ??
        (highContrast
            ? grounds
            : dark
                ? grounds.copyWith(
                    onSurface: const Color(0xffe3e7ea),
                    onSurfaceVariant: const Color(0xffa7b1ba),
                    outline: const Color(0xff77838d),
                    outlineVariant: const Color(0xff2c3439),
                  )
                : grounds.copyWith(
                    onSurface: const Color(0xff1f2933),
                    onSurfaceVariant: const Color(0xff52606d),
                    outline: const Color(0xff7b8794),
                    // The wireframe's line (#d0d7de): a box's edge you can see without
                    // it shouting -- the owner compared the two and preferred it.
                    outlineVariant: const Color(0xffd0d7de),
                  ));

    final TextTheme textTheme = AppTypography.textTheme(tuned);
    // Cards are separated by a quiet line; a control that can be typed into
    // needs an edge somebody can find (4.14, 3 : 1).
    final BorderSide borderSide =
        BorderSide(color: tuned.outlineVariant, width: 1);
    final BorderSide controlSide = BorderSide(color: tuned.outline, width: 1);

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
        // Flutter's default marks a selected row with primary at 8% opacity,
        // which is close to invisible on this light ground and disappears
        // entirely in high contrast -- and the row the toolbar is about to act
        // on is the one thing in the grid that must be unmistakable.
        dataRowColor: WidgetStateProperty.resolveWith((states) {
          if (states.contains(WidgetState.selected)) {
            return tuned.primary.withValues(alpha: dark ? 0.24 : 0.14);
          }
          if (states.contains(WidgetState.hovered)) {
            return tuned.onSurface.withValues(alpha: 0.05);
          }
          return null;
        }),
      ),
      listTileTheme: ListTileThemeData(
        minVerticalPadding: spacing.fieldGap / 2,
        dense: density == GridDensity.compact,
      ),
      textTheme: textTheme,
      // Every banner in the client bar one carries a refusal, and an
      // unstyled one reads as a plain paragraph -- "This location holds
      // 4, so 10 cannot be moved out of it" went unnoticed on 2026-09-12
      // (plan item 8.3). Styled once here rather than at ~20 sites; the one
      // informational banner overrides its colour where it is built.
      bannerTheme: MaterialBannerThemeData(
        backgroundColor: tuned.errorContainer,
        contentTextStyle:
            textTheme.bodyMedium?.copyWith(color: tuned.onErrorContainer),
        dividerColor: tuned.error,
      ),
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
        // **Helper and error text may wrap.**
        //
        // Flutter defaults both to a single line and clips the rest without a
        // word. Half this application's helpers are a sentence -- "Lower case,
        // digits, dots, dashes. Unique in this firm." needs **three** lines in
        // a two-column form at 360 wide, and was rendered in a 19-pixel box
        // showing one. That is the "showing half text" reported on 2026-09-15:
        // not a label, not a padding, not a density. A helper nobody can read
        // to the end is worse than none, because it looks like a rendering
        // fault rather than a truncation.
        //
        // `auth_screens.dart` had already passed `helperMaxLines: 2` by hand
        // for the same reason, which is the tell that this belonged in the
        // theme: one screen working around a default every other screen has.
        helperMaxLines: 3,
        errorMaxLines: 3,
        hintStyle:
            textTheme.bodyMedium?.copyWith(color: tuned.onSurfaceVariant),
        labelStyle:
            textTheme.bodyMedium?.copyWith(color: tuned.onSurfaceVariant),
        enabledBorder: OutlineInputBorder(
          borderRadius: AppRadius.medium,
          borderSide: controlSide,
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
