import 'package:agency_desktop/core/branding/branding_config.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/preferences/user_preferences.dart';
import 'package:agency_desktop/core/theme/theme_manager.dart';
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
    expect(preferences.cachedTheme, 'green');
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

    expect(preferences.preferredTheme, AppTheme.highContrast.wireName);
    expect(preferences.rowsPerPage, 20);
  });

  test('theme registry exposes the five supported switchable themes', () {
    expect(AppTheme.values, hasLength(5));
    expect(ThemeRegistry.themeFor(AppTheme.dark).brightness, isNotNull);
    expect(AppThemeDetails.fromWireName('green'), AppTheme.green);
  });
}
