import 'package:flutter/material.dart';

import 'core/auth/session_controller.dart';
import 'core/branding/branding_config.dart';
import 'core/preferences/desktop_preferences_service.dart';
import 'core/preferences/user_preferences.dart';
import 'core/security/permission_service.dart';
import 'core/theme/theme_manager.dart';
import 'ui/auth_screens.dart';
import 'ui/desktop_shell.dart';

const String _configuredApiUrl = String.fromEnvironment('API_BASE_URL',
    defaultValue: 'http://localhost:8000');

class AgencyApp extends StatefulWidget {
  const AgencyApp({
    super.key,
    this.session,
    this.preferences,
    this.branding,
    this.permissions,
  });

  final SessionController? session;
  final DesktopPreferencesService? preferences;
  final BrandingConfig? branding;
  final PermissionService? permissions;

  @override
  State<AgencyApp> createState() => _AgencyAppState();
}

class _AgencyAppState extends State<AgencyApp> {
  late final DesktopPreferencesService _preferences =
      widget.preferences ?? DesktopPreferencesService();
  late final BrandingConfig _branding =
      widget.branding ?? BrandingConfig.defaults;
  late final ThemeManager _themes = ThemeManager(_preferences);
  late final PermissionService _permissions =
      widget.permissions ?? PermissionService();
  late final SessionController _session = widget.session ??
      SessionController(
        baseUrl: _preferences.current.serverUrl.isEmpty ||
                _preferences.current.serverUrl == 'http://localhost:8000'
            ? _configuredApiUrl
            : _preferences.current.serverUrl,
        preferences: _preferences,
        onPreferencesSynchronized: _applyServerPreferences,
        onAccessTokenChanged: _permissions.applyAccessToken,
      );

  @override
  void initState() {
    super.initState();
    _session.addListener(_synchronizePermissions);
    _synchronizePermissions();
    _themes.bindServerSync((theme) {
      if (_session.status == SessionStatus.authenticated ||
          _session.status == SessionStatus.requiresPasswordChange) {
        return _session.updatePreferredTheme(theme);
      }
      return Future.value();
    });
    _session.restore();
  }

  Future<void> _applyServerPreferences(UserPreferences preferences) =>
      _themes.applyServerTheme(preferences.preferredTheme);

  void _synchronizePermissions() =>
      _permissions.applyAccessToken(_session.accessToken);

  @override
  void dispose() {
    _themes.dispose();
    _session.removeListener(_synchronizePermissions);
    _session.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AnimatedBuilder(
        animation: _themes,
        builder: (context, _) => MaterialApp(
          title: _branding.windowName,
          debugShowCheckedModeBanner: false,
          theme: _themes.theme,
          home: AnimatedBuilder(
            animation: _session,
            builder: (context, _) {
              switch (_session.status) {
                case SessionStatus.restoring:
                case SessionStatus.authenticating:
                  return _StatusPage(
                    message: 'Connecting to ${_branding.productName}…',
                    loading: true,
                    branding: _branding,
                  );
                case SessionStatus.signedOut:
                case SessionStatus.error:
                  return LoginScreen(
                    session: _session,
                    preferences: _preferences,
                    branding: _branding,
                    themes: _themes,
                    error: _session.status == SessionStatus.error
                        ? _session.error
                        : null,
                    notice: _session.notice,
                  );
                case SessionStatus.requiresPasswordChange:
                  return ChangeInitialPasswordScreen(
                    session: _session,
                    branding: _branding,
                  );
                case SessionStatus.authenticated:
                  return DesktopShell(
                    session: _session,
                    preferences: _preferences,
                    branding: _branding,
                    themes: _themes,
                    permissions: _permissions,
                  );
              }
            },
          ),
        ),
      );
}

class _StatusPage extends StatelessWidget {
  const _StatusPage({
    required this.message,
    required this.loading,
    required this.branding,
  });
  final String message;
  final bool loading;
  final BrandingConfig branding;
  @override
  Widget build(BuildContext context) => Scaffold(
        body: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (branding.splashFile != null)
                Image.file(branding.splashFile!,
                    height: 96, fit: BoxFit.contain),
              if (branding.splashFile != null) const SizedBox(height: 16),
              if (loading) const CircularProgressIndicator(),
              const SizedBox(height: 16),
              Text(message),
            ],
          ),
        ),
      );
}
