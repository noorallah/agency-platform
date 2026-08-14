import 'package:agency_desktop/core/branding/branding_config.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/preferences/user_preferences.dart';
import 'package:agency_desktop/core/theme/theme_manager.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('branding parsing honors deployer-provided values', () {
    final BrandingConfig config = BrandingConfig.fromJson({
      'app_name': 'Ledger Desk',
      'window_name': 'Ledger Desk Window',
      'product_name': 'Ledger Desk',
      'company_name': 'Example Co',
      'logo_path': 'logo.png',
      'splash_path': 'splash.png',
      'version': '2.0.0',
      'support_email': 'support@example.test',
      'support_website': 'https://example.test/support',
      'copyright': '© Example Co',
      'login_background_color': '#F0F0F0',
      'login_accent_color': '#001122',
    });

    expect(config.appName, 'Ledger Desk');
    expect(config.loginAccentColor.toARGB32(), 0xff001122);
  });

  test('desktop preferences retain local options without credentials', () {
    final DesktopPreferences preferences = DesktopPreferences.fromJson({
      'remember_username': true,
      'remember_me': true,
      'cached_username': 'person@example.test',
      'server_url': 'https://api.example.test',
      'recent_servers': ['https://api.example.test'],
      'cached_theme': 'green',
      'window_state': {'maximized': true},
      'last_workspace': 'audit',
    });

    expect(preferences.cachedUsername, 'person@example.test');
    expect(preferences.toJson().containsKey('password'), isFalse);
    expect(preferences.cachedPalette, 'green');
  });

  test('public server URLs require HTTPS while the local network permits HTTP', () {
    expect(
      normalizeServerUrl('https://api.example.test/'),
      'https://api.example.test',
    );
    expect(normalizeServerUrl('http://localhost:8000'), contains('localhost'));
    // The client and the backend are routinely on two machines in one
    // building, which is what plain HTTP over the LAN is for. The full rule
    // and its boundaries live in `server_url_rule_test.dart`.
    expect(normalizeServerUrl('http://192.168.1.20:8000'), contains('192.168'));
    expect(
      () => normalizeServerUrl('http://api.example.test'),
      throwsFormatException,
    );
  });

  test('user preference response parses versioned server preferences', () {
    final UserPreferences preferences = UserPreferences.fromJson({
      'preferences_version': 1,
      'preferred_theme': 'high_contrast',
      'language': 'en',
      'date_format': 'yyyy-MM-dd',
      'time_format': '24h',
      'number_format': '1,234.56',
      'currency_format': 'symbol',
      'default_firm_id': null,
      'default_landing_page': 'dashboard',
      'rows_per_page': 20,
      'notification_preferences': {},
      'dashboard_layout': {},
    });

    expect(preferences.preferredTheme, 'high_contrast');
    expect(preferences.preferredHighContrast, isTrue);
    expect(preferences.rowsPerPage, 20);
  });

  test('every palette is built in both brightnesses', () {
    // The old model had five entries mixing palette and mode, so "Blue" only
    // ever existed in light. Each palette must now render in both.
    for (final AppPalette palette in AppPalette.values) {
      for (final Brightness brightness in Brightness.values) {
        final ThemeData theme = ThemeRegistry.themeFor(
          palette: palette,
          brightness: brightness,
        );
        expect(theme.colorScheme.brightness, brightness);
      }
    }
    expect(AppPaletteDetails.fromWireName('green'), AppPalette.green);
  });

  test('an unrecognised appearance follows the operating system', () {
    // The old fallback was light, which is how a machine running Windows in
    // dark mode was greeted with a white screen.
    expect(AppThemeModeDetails.fromWireName(null), ThemeMode.system);
    expect(AppThemeModeDetails.fromWireName(''), ThemeMode.system);
    expect(AppThemeModeDetails.fromWireName('nonsense'), ThemeMode.system);
    expect(AppThemeModeDetails.fromWireName('dark'), ThemeMode.dark);
  });

  test('desktop preferences retain framework display preferences', () {
    final DesktopPreferences preferences = DesktopPreferences.fromJson({
      'sidebar_collapsed': true,
      'grid_density': 'compact',
      'default_landing_page': 'reports',
    });

    expect(preferences.sidebarCollapsed, isTrue);
    expect(preferences.gridDensity, GridDensity.compact);
    expect(preferences.defaultLandingPage, 'reports');
    expect(preferences.toJson(), containsPair('grid_density', 'compact'));
  });
}
