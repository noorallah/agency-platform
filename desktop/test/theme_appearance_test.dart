import 'dart:io';

import 'package:agency_desktop/core/design/design_tokens.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/theme/theme_manager.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Appearance is two independent choices, and the default defers to Windows.
///
/// The previous model was one enum of five values mixing palette with
/// brightness, and light was hardcoded as the default at five separate layers.
/// A user running Windows in dark mode was greeted with a white screen every
/// time, which is the most likely single cause of the eye strain this work was
/// asked to address. These tests pin the new behaviour so it cannot quietly
/// regress to a hardcoded default again.

DesktopPreferencesService _preferences() {
  final Directory directory =
      Directory.systemTemp.createTempSync('appearance-test');
  addTearDown(() => directory.deleteSync(recursive: true));
  return DesktopPreferencesService(directory: directory);
}

void main() {
  _densityTests();

  test('a user who has never chosen follows the operating system', () {
    expect(ThemeManager(_preferences()).mode, ThemeMode.system);
  });

  test('the app supplies both brightnesses so the OS choice can be honoured', () {
    // Supplying only `theme:` is why the old build could not follow Windows: a
    // single ThemeData leaves Flutter nothing to switch to.
    final ThemeManager manager = ThemeManager(_preferences());

    expect(manager.lightTheme.colorScheme.brightness, Brightness.light);
    expect(manager.darkTheme.colorScheme.brightness, Brightness.dark);
  });

  test('choosing a mode is remembered and does not disturb the accent', () async {
    final DesktopPreferencesService preferences = _preferences();
    final ThemeManager manager = ThemeManager(preferences);
    await manager.selectPalette(AppPalette.green);

    await manager.selectMode(ThemeMode.dark);

    expect(manager.mode, ThemeMode.dark);
    expect(manager.palette, AppPalette.green, reason: 'accent is a separate axis');
    expect(ThemeManager(preferences).mode, ThemeMode.dark, reason: 'persisted');
  });

  test('every accent exists in both brightnesses', () async {
    // "Blue" and "Green" used to be light-only, so choosing an accent silently
    // threw away a dark-mode preference.
    for (final AppPalette palette in AppPalette.values) {
      final DesktopPreferencesService preferences = _preferences();
      final ThemeManager manager = ThemeManager(preferences);
      await manager.selectPalette(palette);

      expect(manager.lightTheme.colorScheme.brightness, Brightness.light);
      expect(manager.darkTheme.colorScheme.brightness, Brightness.dark);
    }
  });

  test('higher contrast applies to whichever mode is in use', () async {
    // It used to be a yellow-seeded dark theme, so asking for readable contrast
    // forced both a dark screen and an accent nobody chose.
    final ThemeManager manager = ThemeManager(_preferences());
    await manager.selectMode(ThemeMode.light);
    final Color before = manager.lightTheme.colorScheme.onSurface;

    await manager.setHighContrast(true);

    expect(manager.mode, ThemeMode.light, reason: 'contrast is not a mode');
    expect(manager.palette, AppPalette.neutral, reason: 'nor an accent');
    expect(manager.lightTheme.colorScheme.onSurface, isNot(before));
  });

  test('an older stored choice is carried across, once', () {
    // The previous release stored one string. A deliberate "Blue" stays blue;
    // "Dark" was a mode and becomes one; the old hardcoded "light" default was
    // never a choice anyone made, so it becomes "follow the system".
    DesktopPreferences read(String legacy) =>
        DesktopPreferences.fromJson({'cached_theme': legacy});

    expect(read('blue').cachedPalette, 'blue');
    expect(read('blue').cachedThemeMode, 'system');
    expect(read('dark').cachedThemeMode, 'dark');
    expect(read('light').cachedThemeMode, 'system');
    expect(read('high_contrast').cachedHighContrast, isTrue);
    expect(read('high_contrast').cachedThemeMode, 'dark');
  });

  test('neither ground is pure white or pure black', () {
    // A full-white page is the biggest source of glare over a long shift, and
    // pure black makes light text shimmer against it.
    final ThemeManager manager = ThemeManager(_preferences());

    expect(manager.lightTheme.colorScheme.surface, isNot(const Color(0xffffffff)));
    expect(manager.darkTheme.colorScheme.surface, isNot(const Color(0xff000000)));
  });

  testWidgets('the rendered surface actually follows the platform', (tester) async {
    // The unit tests above prove both halves are built. This proves Flutter
    // uses them: flip the platform brightness and the surface must change.
    // Nothing in the previous build could pass this, because it supplied one
    // ThemeData and no themeMode.
    final ThemeManager manager = ThemeManager(_preferences());

    Future<Color> surfaceUnder(Brightness platform) async {
      tester.platformDispatcher.platformBrightnessTestValue = platform;
      late Color surface;
      await tester.pumpWidget(
        MaterialApp(
          theme: manager.lightTheme,
          darkTheme: manager.darkTheme,
          themeMode: manager.mode,
          home: Builder(
            builder: (context) {
              surface = Theme.of(context).colorScheme.surface;
              return const SizedBox();
            },
          ),
        ),
      );
      await tester.pumpAndSettle();
      return surface;
    }

    final Color light = await surfaceUnder(Brightness.light);
    final Color dark = await surfaceUnder(Brightness.dark);

    expect(light, isNot(dark));
    expect(light.computeLuminance(), greaterThan(dark.computeLuminance()));
  });
}

/// Density used to be a preference nothing read.
///
/// `GridDensity` has existed since the beginning with a `saveGridDensity()`
/// nobody called and a value nobody consumed. The single place it was honoured
/// changed rows-per-page rather than row height, which is the opposite of what
/// the word means. These pin that it now changes real measurements, applied
/// through the theme so every grid inherits it without a call site changing.
void _densityTests() {
  test('each density produces a different row height', () async {
    final ThemeManager manager = ThemeManager(_preferences());
    final Map<GridDensity, double> heights = {};

    for (final GridDensity density in GridDensity.values) {
      await manager.selectDensity(density);
      heights[density] =
          manager.lightTheme.dataTableTheme.dataRowMinHeight ?? -1;
    }

    expect(heights.values.toSet(), hasLength(GridDensity.values.length));
    expect(
      heights[GridDensity.compact]!,
      lessThan(heights[GridDensity.spacious]!),
      reason: 'compact must fit more rows, which is the point of it',
    );
  });

  test('density is persisted and reaches the theme extension', () async {
    final DesktopPreferencesService preferences = _preferences();
    await ThemeManager(preferences).selectDensity(GridDensity.compact);

    final ThemeManager reopened = ThemeManager(preferences);

    expect(reopened.density, GridDensity.compact);
    expect(
      reopened.lightTheme.extension<AppDensityTokens>()!.rowHeight,
      AppDensityTokens.compact.rowHeight,
    );
  });

  test('compact reclaims real vertical space against spacious', () async {
    final ThemeManager manager = ThemeManager(_preferences());
    await manager.selectDensity(GridDensity.spacious);
    final double spacious =
        manager.lightTheme.dataTableTheme.dataRowMinHeight ?? 0;
    await manager.selectDensity(GridDensity.compact);
    final double compact =
        manager.lightTheme.dataTableTheme.dataRowMinHeight ?? 0;

    // Over a 500px grid that is several extra rows on the smallest screen.
    expect(spacious - compact, greaterThanOrEqualTo(12));
  });
}
