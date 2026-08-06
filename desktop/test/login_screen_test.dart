import 'dart:async';
import 'dart:io';

import 'package:agency_desktop/core/auth/refresh_token_store.dart';
import 'package:agency_desktop/core/auth/session_controller.dart';
import 'package:agency_desktop/core/branding/branding_config.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/theme/theme_manager.dart';
import 'package:agency_desktop/ui/auth_screens.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

class _MemoryTokenStore implements RefreshTokenStore {
  String? token;

  @override
  Future<void> clear() async => token = null;

  @override
  Future<String?> read() async => token;

  @override
  Future<void> write(String value) async => token = value;
}

class _FakePreferencesService extends DesktopPreferencesService {
  _FakePreferencesService(Directory directory)
      : _current = const DesktopPreferences(),
        super(directory: directory);

  DesktopPreferences _current;

  @override
  DesktopPreferences get current => _current;

  @override
  bool get hasStoredPreferences => true;

  @override
  Future<void> saveLoginOptions({
    required bool rememberUsername,
    required bool rememberMe,
    required String username,
  }) async {
    _current = _current.copyWith(
      rememberUsername: rememberUsername,
      rememberMe: rememberMe,
      cachedUsername: username,
      clearCachedUsername: !rememberUsername,
    );
  }

  @override
  Future<void> saveTheme(String theme) async {
    _current = _current.copyWith(cachedTheme: theme);
  }

  @override
  Future<void> saveServerUrl(String url) async {
    _current = _current.copyWith(serverUrl: url);
  }
}

class _FakeSessionController extends SessionController {
  _FakeSessionController({required this.preferences})
      : super(
          baseUrl: 'https://api.example.test',
          preferences: preferences,
          tokenStore: _MemoryTokenStore(),
        );

  final _FakePreferencesService preferences;
  SessionStatus _status = SessionStatus.signedOut;
  String? _error;
  String? _notice;
  String? _attemptedUsername;
  String? submittedUsername;
  String? submittedPassword;
  int loginCalls = 0;
  bool loginShouldFail = false;
  Completer<void>? pendingLogin;
  String _baseUrl = 'https://api.example.test';

  @override
  SessionStatus get status => _status;

  @override
  String? get error => _error;

  @override
  String? get notice => _notice;

  @override
  String? get attemptedUsername => _attemptedUsername;

  @override
  String get baseUrl => _baseUrl;

  @override
  Future<void> login(
    String email,
    String password, {
    required bool rememberUsername,
    required bool rememberMe,
  }) async {
    if (_status == SessionStatus.authenticating) {
      return;
    }
    loginCalls++;
    submittedUsername = email;
    submittedPassword = password;
    _attemptedUsername = email;
    _error = null;
    _notice = null;
    _status = SessionStatus.authenticating;
    notifyListeners();
    await preferences.saveLoginOptions(
      rememberUsername: rememberUsername,
      rememberMe: rememberMe,
      username: email,
    );
    if (pendingLogin != null) {
      await pendingLogin!.future;
    }
    if (loginShouldFail) {
      _error = 'Invalid email or password.';
      _status = SessionStatus.error;
    } else {
      _status = SessionStatus.authenticated;
    }
    notifyListeners();
  }

  @override
  Future<void> updateServerUrl(String value) async {
    _baseUrl = value.trim();
    await preferences.saveServerUrl(_baseUrl);
  }
}

class _TestHarness extends StatelessWidget {
  const _TestHarness({
    required this.session,
    required this.preferences,
    required this.themes,
    this.capsLockEnabled,
  });

  final _FakeSessionController session;
  final _FakePreferencesService preferences;
  final ThemeManager themes;
  final bool Function()? capsLockEnabled;

  @override
  Widget build(BuildContext context) => AnimatedBuilder(
        animation: themes,
        builder: (context, _) => AnimatedBuilder(
          animation: session,
          builder: (context, _) => MaterialApp(
            theme: themes.theme,
            home: LoginScreen(
              session: session,
              preferences: preferences,
              branding: BrandingConfig.defaults,
              themes: themes,
              error: session.status == SessionStatus.error ? session.error : null,
              notice: session.notice,
              capsLockEnabled: capsLockEnabled,
            ),
          ),
        ),
      );
}

Future<_FakePreferencesService> _preferences() async {
  final Directory directory = Directory(
    '${Directory.systemTemp.path}\\agency_login_test_${DateTime.now().microsecondsSinceEpoch}',
  );
  if (!directory.existsSync()) {
    directory.createSync(recursive: true);
  }
  addTearDown(() async {
    if (await directory.exists()) {
      await directory.delete(recursive: true);
    }
  });
  return _FakePreferencesService(directory);
}

Future<_FakeSessionController> _session(_FakePreferencesService preferences) async =>
    _FakeSessionController(preferences: preferences);

Future<ThemeManager> _themes(_FakePreferencesService preferences) async =>
    ThemeManager(preferences);

Future<void> _useDesktopViewport(WidgetTester tester) async {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = const Size(1920, 1080);
  addTearDown(() {
    tester.view.resetPhysicalSize();
    tester.view.resetDevicePixelRatio();
  });
}

void main() {
  testWidgets('renders the enterprise login layout and quick login panel',
      (tester) async {
    await _useDesktopViewport(tester);
    final prefs = await _preferences();
    final themes = await _themes(prefs);
    final session = await _session(prefs);

    await tester.pumpWidget(
      _TestHarness(session: session, preferences: prefs, themes: themes),
    );

    expect(find.text('Welcome Back'), findsOneWidget);
    expect(find.text('Sign in to continue.'), findsOneWidget);
    expect(find.text('Username / Email'), findsOneWidget);
    expect(find.text('Sign-in Options'), findsOneWidget);
    expect(find.text('Quick Login'), findsOneWidget);
    expect(find.text('Forgot password?'), findsOneWidget);
  });

  testWidgets('shows loading state and blocks duplicate submissions',
      (tester) async {
    await _useDesktopViewport(tester);
    final prefs = await _preferences();
    final themes = await _themes(prefs);
    final session = await _session(prefs);
    session.pendingLogin = Completer<void>();

    await tester.pumpWidget(
      _TestHarness(session: session, preferences: prefs, themes: themes),
    );

    await tester.enterText(find.byType(TextFormField).at(0), 'alice');
    await tester.enterText(find.byType(TextFormField).at(1), 'Password@123');
    await tester.tap(find.byType(FilledButton).first);
    await tester.pump();

    expect(find.text('Signing in...'), findsOneWidget);
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
    expect(session.loginCalls, 1);

    await tester.tap(find.byType(FilledButton).first);
    await tester.pump();
    expect(session.loginCalls, 1);

    session.pendingLogin!.complete();
    await tester.pump();
  });

  testWidgets('shows error state, focuses password, and dismisses with escape',
      (tester) async {
    await _useDesktopViewport(tester);
    final prefs = await _preferences();
    final themes = await _themes(prefs);
    final session = await _session(prefs);
    session.loginShouldFail = true;

    await tester.pumpWidget(
      _TestHarness(session: session, preferences: prefs, themes: themes),
    );

    await tester.enterText(find.byType(TextFormField).at(0), 'alice');
    await tester.enterText(find.byType(TextFormField).at(1), 'Password@123');
    await tester.tap(find.byType(FilledButton).first);
    await tester.pumpAndSettle();

    expect(find.textContaining('Unable to sign in.'), findsOneWidget);
    final EditableText passwordField =
        tester.widget(find.byType(EditableText).at(1));
    expect(passwordField.focusNode.hasFocus, isTrue);

    await tester.sendKeyEvent(LogicalKeyboardKey.escape);
    await tester.pump();
    expect(find.textContaining('Unable to sign in.'), findsNothing);
  });

  testWidgets('trims credentials and validates whitespace-only input',
      (tester) async {
    await _useDesktopViewport(tester);
    final prefs = await _preferences();
    final themes = await _themes(prefs);
    final session = await _session(prefs);

    await tester.pumpWidget(
      _TestHarness(session: session, preferences: prefs, themes: themes),
    );

    await tester.enterText(find.byType(TextFormField).at(0), '  alice  ');
    await tester.enterText(find.byType(TextFormField).at(1), '  Password@123  ');
    await tester.ensureVisible(find.text('Sign in'));
    await tester.tap(find.text('Sign in'));
    await tester.pumpAndSettle();

    expect(session.submittedUsername, 'alice');
    expect(session.submittedPassword, 'Password@123');

    await tester.enterText(find.byType(TextFormField).at(0), '   ');
    await tester.enterText(find.byType(TextFormField).at(1), '   ');
    await tester.tap(find.byType(FilledButton).first);
    await tester.pump();

    expect(find.text('Enter your username or email.'), findsOneWidget);
    expect(find.text('Enter your password.'), findsOneWidget);
  });

  testWidgets('shows caps lock warning and remember options', (tester) async {
    await _useDesktopViewport(tester);
    final prefs = await _preferences();
    final themes = await _themes(prefs);
    final session = await _session(prefs);

    await tester.pumpWidget(
      _TestHarness(
        session: session,
        preferences: prefs,
        themes: themes,
        capsLockEnabled: () => true,
      ),
    );

    await tester.ensureVisible(find.byType(TextFormField).at(1));
    await tester.tap(find.byType(TextFormField).at(1));
    await tester.pumpAndSettle();

    expect(find.text('Caps Lock is ON'), findsOneWidget);
    expect(find.text('Remember username'), findsOneWidget);
    expect(find.text('Remember me on this device'), findsOneWidget);
  });

  testWidgets('autofills credentials from quick login', (tester) async {
    await _useDesktopViewport(tester);
    final prefs = await _preferences();
    final themes = await _themes(prefs);
    final session = await _session(prefs);

    await tester.pumpWidget(
      _TestHarness(session: session, preferences: prefs, themes: themes),
    );

    await tester.ensureVisible(find.widgetWithText(OutlinedButton, 'Administrator'));
    await tester.tap(find.widgetWithText(OutlinedButton, 'Administrator'));
    await tester.pump();

    final TextFormField usernameField =
        tester.widget(find.byType(TextFormField).at(0));
    final TextFormField passwordField =
        tester.widget(find.byType(TextFormField).at(1));
    expect(usernameField.controller!.text, 'superadmin@agency.local');
    expect(passwordField.controller!.text, 'Password@123');
  });

  testWidgets('opens application settings and toggles theme', (tester) async {
    await _useDesktopViewport(tester);
    final prefs = await _preferences();
    final themes = await _themes(prefs);
    final session = await _session(prefs);

    await tester.pumpWidget(
      _TestHarness(session: session, preferences: prefs, themes: themes),
    );

    await tester.tap(find.byTooltip('Choose theme'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Dark').last);
    await tester.pumpAndSettle();

    expect(themes.current, AppTheme.dark);

    await tester.tap(find.byTooltip('Application Settings'));
    await tester.pumpAndSettle();

    expect(find.text('Application Settings'), findsOneWidget);
    expect(find.text('API URL'), findsOneWidget);
    expect(find.text('Language (future)'), findsOneWidget);
    expect(find.text('Font Size'), findsOneWidget);
    expect(find.text('About'), findsOneWidget);
  });
}
