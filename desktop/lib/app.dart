import 'package:flutter/material.dart';

import 'core/auth/session_controller.dart';
import 'core/branding/branding_config.dart';
import 'core/diagnostics/diagnostics_share.dart';
import 'core/preferences/desktop_preferences_service.dart';
import 'core/preferences/user_preferences.dart';
import 'core/security/permission_service.dart';
import 'core/theme/theme_manager.dart';
import 'ui/auth_screens.dart';
import 'ui/desktop_shell.dart';
import 'ui/server_connection_gate.dart';

const String _configuredApiUrl = String.fromEnvironment('API_BASE_URL',
    defaultValue: 'http://localhost:8000');

/// The preferences file's own default, which means "never chosen".
const String _unchosenServerUrl = 'http://localhost:8000';

/// Which server the app talks to, in order of who decided it: the user, in
/// Application Settings; then Setup, in `config/branding.json`; then the build.
///
/// The preferences default is indistinguishable from a choice of it, so it
/// counts as no choice -- as it always has.
String resolveServerUrl({
  required String saved,
  required String installed,
  required String compiled,
}) {
  if (saved.isNotEmpty && saved != _unchosenServerUrl) return saved;
  if (installed.isNotEmpty) return installed;
  return compiled;
}

class AgencyApp extends StatefulWidget {
  const AgencyApp({
    super.key,
    this.session,
    this.preferences,
    this.branding,
    this.permissions,
    this.waitForServer = false,
    this.serverProbe,
    this.phase2 = false,
  });

  /// Open the phase 2 frame after sign-in (`lib/main_phase2.dart`).
  final bool phase2;

  final SessionController? session;
  final DesktopPreferencesService? preferences;
  final BrandingConfig? branding;
  final PermissionService? permissions;

  /// Show [ServerConnectionGate] until the server answers `/health`, before
  /// the session is restored or the sign-in screen shown. `main` turns it on;
  /// tests that drive the sign-in screen leave it off.
  final bool waitForServer;

  /// Replaces the gate's `/health` call, for tests.
  final Future<bool> Function()? serverProbe;

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
        baseUrl: resolveServerUrl(
          saved: _preferences.current.serverUrl,
          installed: _branding.serverUrl,
          compiled: _configuredApiUrl,
        ),
        preferences: _preferences,
        onPreferencesSynchronized: _applyServerPreferences,
        onAccessTokenChanged: _permissions.applyAccessToken,
        // Late-bound on purpose: the permission service is the one
        // decoder of the token's claims, and it is refreshed by the
        // callback above before this is ever asked.
        isPlatformAdmin: () => _permissions.isPlatformAdmin,
      );

  @override
  void initState() {
    super.initState();
    _session.addListener(_synchronizePermissions);
    _synchronizePermissions();
    _themes.bindServerSync((palette, mode, highContrast) {
      if (_session.status == SessionStatus.authenticated ||
          _session.status == SessionStatus.requiresPasswordChange) {
        return _session.updatePreferredAppearance(
          palette: palette,
          themeMode: mode,
          highContrast: highContrast,
        );
      }
      return Future.value();
    });
    if (_serverReady) _session.restore();
  }

  /// Whether the gate has let the app through. Restoring the session asks the
  /// server for a token, so it waits for the same answer the gate does.
  late bool _serverReady = !widget.waitForServer;

  void _passGate() {
    if (_serverReady) return;
    setState(() => _serverReady = true);
    _session.restore();
  }

  Future<void> _applyServerPreferences(UserPreferences preferences) =>
      _themes.applyServerAppearance(
        palette: preferences.preferredPalette,
        mode: preferences.preferredThemeMode,
        highContrast: preferences.preferredHighContrast,
      );

  /// Re-resolve grants whenever the token or the selected firm changes.
  ///
  /// switchFirm notifies without issuing a new token, so the active firm has to
  /// be passed through here or the UI would keep the previous firm's grants.
  void _synchronizePermissions() => _permissions.applyAccessToken(
        _session.accessToken,
        activeFirmId: _session.currentFirm?.id,
      );

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
          // Both halves are always supplied; themeMode decides which one is
          // used, and only Flutter can see the operating system's setting.
          theme: _themes.lightTheme,
          darkTheme: _themes.darkTheme,
          themeMode: _themes.mode,
          // Flutter's `Text` is not selectable, which is the opposite of the
          // web and of every other desktop application: nothing on screen could
          // be highlighted or copied unless somebody had happened to build that
          // particular label as a `SelectableText`. In an ERP the values people
          // most need to copy -- a document number, a code, an id in an error
          // message -- were the ones they had to retype by hand.
          //
          // It goes here rather than in `builder`, which is inserted *above*
          // the Navigator: `SelectableRegion` requires an `Overlay` ancestor,
          // and the Navigator is what provides one, so wrapping there throws
          // and takes the whole screen with it. Inside `home` the route is
          // already within the overlay.
          //
          // Dialogs are separate routes, so this does not reach them, and the
          // claim that it cost nothing -- because their values sit in editable
          // text fields -- was wrong: a form's labels, helper text, validation
          // messages and read-only values are plain `Text`, and those are
          // exactly what a user needs to quote back. The two dialog shells
          // wrap themselves; see `WorkspaceDialog` and `CrudWorkspaceDialog`.
          home: !_serverReady
              ? ServerConnectionGate(
                  probe: widget.serverProbe ?? _session.api.backendReachable,
                  serverUrl: _session.baseUrl,
                  onConnected: _passGate,
                  onContinueAnyway: _passGate,
                  onOpenLogs: DiagnosticsShare.openLogsFolder,
                )
              : SelectionArea(
            child: AnimatedBuilder(
              animation: _session,
              builder: (context, _) {
                switch (_session.status) {
                  case SessionStatus.restoring:
                    return _StatusPage(
                      message: 'Connecting to ${_branding.productName}…',
                      loading: true,
                      branding: _branding,
                    );
                  case SessionStatus.authenticating:
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
                      lockedUntil: _session.status == SessionStatus.error
                          ? _session.lockedUntil
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
                      phase2: widget.phase2,
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
