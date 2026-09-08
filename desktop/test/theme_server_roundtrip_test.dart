import 'dart:io';

import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/preferences/user_preferences.dart';
import 'package:agency_desktop/core/theme/theme_manager.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// An appearance choice survives a sign-out because the server keeps it.
///
/// The sign-in path adopts whatever the server returns and writes it over the
/// local file. That is right when the server holds the user's choice and
/// destructive when it holds defaults -- which it did for a month, because the
/// desktop sent a field the server refused and so no choice was ever stored.
/// The contract itself is checked from the backend suite; this file pins the
/// client's half: what the server sends back is read, and applied, in full.
Directory _scratch() {
  final Directory directory =
      Directory.systemTemp.createTempSync('roundtrip-test');
  addTearDown(() => directory.deleteSync(recursive: true));
  return directory;
}

DesktopPreferencesService _preferences([Directory? directory]) =>
    DesktopPreferencesService(directory: directory ?? _scratch());

Map<String, dynamic> _serverDocument({
  String palette = 'blue',
  String mode = 'dark',
  bool highContrast = true,
}) =>
    {
      'preferences_version': 1,
      'preferred_theme': 'dark',
      'preferred_palette': palette,
      'preferred_theme_mode': mode,
      'preferred_high_contrast': highContrast,
      'language': 'en',
      'date_format': 'yyyy-MM-dd',
      'time_format': '24h',
      'number_format': '1,234.56',
      'currency_format': 'symbol',
      'default_firm_id': null,
      'default_landing_page': 'dashboard',
      'rows_per_page': 20,
      'notification_preferences': <String, dynamic>{},
      'dashboard_layout': <String, dynamic>{},
    };

void main() {
  test('the palette the server stores is read as itself', () {
    // Not derived from the legacy `preferred_theme`, which collapses blue and
    // green to "dark" whenever the mode is dark.
    final UserPreferences preferences =
        UserPreferences.fromJson(_serverDocument());

    expect(preferences.preferredPalette, 'blue');
    expect(preferences.preferredThemeMode, 'dark');
    expect(preferences.preferredHighContrast, isTrue);
  });

  test('an older server without the field still implies one', () {
    final Map<String, dynamic> legacy = _serverDocument()
      ..remove('preferred_palette')
      ..['preferred_theme'] = 'green';

    expect(UserPreferences.fromJson(legacy).preferredPalette, 'green');
  });

  test('what the server sends back is what the next launch starts from',
      () async {
    // The sign-in path: adopt the server's answer, write it locally, and a
    // fresh manager built from that file starts on the same appearance.
    final Directory directory = _scratch();
    final DesktopPreferencesService preferences = _preferences(directory);
    await preferences.load();
    final UserPreferences server = UserPreferences.fromJson(_serverDocument());

    await ThemeManager(preferences).applyServerAppearance(
      palette: server.preferredPalette,
      mode: server.preferredThemeMode,
      highContrast: server.preferredHighContrast,
    );

    final DesktopPreferencesService reloaded = _preferences(directory);
    await reloaded.load();
    final ThemeManager next = ThemeManager(reloaded);
    expect(next.palette, AppPalette.blue);
    expect(next.mode, ThemeMode.dark);
    expect(next.highContrast, isTrue);
  });

  test('a choice is echoed to the server as the three fields it declares',
      () async {
    // The other half of the round trip. Whatever the manager sends is what
    // the server must accept; the backend guard checks the names, this
    // checks the values are the wire names and not the enum's own.
    final DesktopPreferencesService preferences = _preferences();
    await preferences.load();
    final ThemeManager manager = ThemeManager(preferences);
    final List<(String, String, bool)> sent = [];
    manager.bindServerSync((palette, mode, highContrast) async {
      sent.add((palette, mode, highContrast));
    });

    await manager.selectPalette(AppPalette.green);
    await manager.selectMode(ThemeMode.dark);

    expect(sent.last, ('green', 'dark', false));
  });
}
