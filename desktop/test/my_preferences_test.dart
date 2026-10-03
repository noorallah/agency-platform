import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/auth/refresh_token_store.dart';
import 'package:agency_desktop/core/auth/session_controller.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/preferences/user_preferences.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/phase2/display_dates.dart';
import 'package:agency_desktop/phase2/menu_layout.dart';
import 'package:agency_desktop/phase2/my_preferences_dialog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// My preferences (backlog 73), held to the owner's condition of 2026-10-04:
/// opening it asks the server nothing, and saving is one request carrying
/// only what changed -- none at all when nothing did.

Map<String, dynamic> _serverDocument() => {
      'preferences_version': 1,
      'preferred_theme': 'light',
      'preferred_palette': 'neutral',
      'preferred_theme_mode': 'system',
      'preferred_high_contrast': false,
      'language': 'en',
      'date_format': 'dd-MM-yyyy',
      'time_format': '24h',
      'number_format': '1,234.56',
      'currency_format': 'symbol',
      'default_firm_id': null,
      'default_landing_page': 'dashboard',
      'rows_per_page': 20,
      'notification_preferences': <String, dynamic>{},
      'dashboard_layout': <String, dynamic>{
        'favourites': ['home'],
      },
    };

class _MemoryTokenStore implements RefreshTokenStore {
  String? _token;
  @override
  Future<String?> read() async => _token;
  @override
  Future<void> write(String token) async => _token = token;
  @override
  Future<void> clear() async => _token = null;
}

class _Api extends ApiClient {
  _Api()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => null,
        );

  final List<Json> updates = [];

  @override
  Future<AuthTokens> login(String email, String password) async =>
      const AuthTokens(
        accessToken: 'h.e30.s',
        refreshToken: 'r',
        forcePasswordChange: false,
      );

  @override
  Future<UserPreferences> getUserPreferences() async =>
      UserPreferences.fromJson(_serverDocument());

  @override
  Future<UserPreferences> updateUserPreferences(Json changes) async {
    updates.add(changes);
    return UserPreferences.fromJson({..._serverDocument(), ...changes});
  }

  @override
  Future<List<AssignedFirm>> myFirms() async => const [];

  @override
  Future<CurrentUser> me() async => CurrentUser.fromJson(const {
        'id': 'u-1',
        'email': 'asha@example.com',
        'full_name': 'Asha Rao',
        'is_platform_admin': false,
        'primary_firm_id': null,
      });
}

Future<(SessionController, _Api)> _signIn() async {
  final Directory directory =
      Directory.systemTemp.createTempSync('my-preferences-test');
  addTearDown(() => directory.deleteSync(recursive: true));
  final DesktopPreferencesService preferences =
      DesktopPreferencesService(directory: directory);
  await preferences.load();
  final SessionController session = SessionController(
    baseUrl: 'http://localhost:8000',
    tokenStore: _MemoryTokenStore(),
    preferences: preferences,
  );
  final _Api api = _Api();
  session.api = api;
  await session.login('asha@example.com', 'pw',
      rememberUsername: false, rememberMe: false);
  api.updates.clear();
  return (session, api);
}

const MyPreferences _current = MyPreferences(
  startInFirmId: 'a',
  firstScreen: MyPreferences.lastScreen,
  themeMode: 'system',
  textSize: AppTextSize.standard,
  dateFormat: 'dd-MM-yyyy',
);

const List<AssignedFirm> _firms = [
  AssignedFirm(id: 'a', code: 'A', name: 'Firm A', isPrimary: true),
  AssignedFirm(id: 'b', code: 'B', name: 'Firm B', isPrimary: false),
];

Future<List<MyPreferencesChange>> _open(
  WidgetTester tester, {
  bool offerStartInFirm = true,
}) async {
  final List<MyPreferencesChange> saved = [];
  await tester.pumpWidget(MaterialApp(
    home: Builder(
      builder: (context) => TextButton(
        onPressed: () => showDialog<bool>(
          context: context,
          builder: (_) => MyPreferencesDialog(
            current: _current,
            firms: _firms,
            offerStartInFirm: offerStartInFirm,
            screens: const [(path: 'home', label: 'Home')],
            onSave: (change) async => saved.add(change),
          ),
        ),
        child: const Text('open'),
      ),
    ),
  ));
  await tester.tap(find.text('open'));
  await tester.pumpAndSettle();
  return saved;
}

Future<void> _choose(WidgetTester tester, String key, String option) async {
  await tester.tap(find.byKey(ValueKey(key)));
  await tester.pumpAndSettle();
  await tester.tap(find.text(option).last);
  await tester.pumpAndSettle();
}

void main() {
  group('the dialog', () {
    testWidgets('Save with nothing changed closes and saves nothing',
        (tester) async {
      final List<MyPreferencesChange> saved = await _open(tester);

      await tester.tap(find.byKey(const ValueKey('prefs-save')));
      await tester.pumpAndSettle();

      expect(saved, isEmpty);
      expect(find.text('My preferences'), findsNothing);
    });

    testWidgets('a changed theme is the only field sent', (tester) async {
      final List<MyPreferencesChange> saved = await _open(tester);

      await _choose(tester, 'prefs-theme', 'Dark');
      await tester.tap(find.byKey(const ValueKey('prefs-save')));
      await tester.pumpAndSettle();

      expect(saved, hasLength(1));
      expect(saved.single.themeMode, 'dark');
      expect(saved.single.startInFirmId, isNull);
      expect(saved.single.firstScreen, isNull);
      expect(saved.single.textSize, isNull);
      expect(saved.single.dateFormat, isNull);
    });

    testWidgets('start in firm and first screen are carried when changed',
        (tester) async {
      final List<MyPreferencesChange> saved = await _open(tester);

      await _choose(tester, 'prefs-start-in-firm', 'Firm B');
      await _choose(tester, 'prefs-first-screen', 'Home');
      await tester.tap(find.byKey(const ValueKey('prefs-save')));
      await tester.pumpAndSettle();

      expect(saved.single.startInFirmId, 'b');
      expect(saved.single.firstScreen, 'home');
      expect(saved.single.themeMode, isNull);
    });

    testWidgets('start in firm is hidden when there is no choice to make',
        (tester) async {
      await _open(tester, offerStartInFirm: false);

      expect(find.byKey(const ValueKey('prefs-start-in-firm')), findsNothing);
      expect(find.byKey(const ValueKey('prefs-first-screen')), findsOneWidget);
    });

    testWidgets('a refusal keeps the dialog open with the message',
        (tester) async {
      await tester.pumpWidget(MaterialApp(
        home: Builder(
          builder: (context) => TextButton(
            onPressed: () => showDialog<bool>(
              context: context,
              builder: (_) => MyPreferencesDialog(
                current: _current,
                firms: _firms,
                screens: const [],
                onSave: (_) async =>
                    throw const ApiException('Not a firm you belong to.'),
              ),
            ),
            child: const Text('open'),
          ),
        ),
      ));
      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();

      await _choose(tester, 'prefs-start-in-firm', 'Firm B');
      await tester.tap(find.byKey(const ValueKey('prefs-save')));
      await tester.pumpAndSettle();

      expect(find.text('My preferences'), findsOneWidget);
      expect(find.text('Not a firm you belong to.'), findsOneWidget);
    });
  });

  group('saving through the session', () {
    test('one request, carrying only the changed field', () async {
      final (SessionController session, _Api api) = await _signIn();

      await session.saveMyPreferences(dateFormat: 'yyyy-MM-dd');

      expect(api.updates, hasLength(1));
      expect(api.updates.single.keys, ['date_format']);
      expect(session.serverPreferences?.dateFormat, 'yyyy-MM-dd');
    });

    test('a theme goes with the legacy value an older server reads', () async {
      final (SessionController session, _Api api) = await _signIn();

      await session.saveMyPreferences(themeMode: 'dark');

      expect(api.updates.single, {
        'preferred_theme_mode': 'dark',
        'preferred_theme': 'dark',
      });
    });

    test('nothing changed is no request at all', () async {
      final (SessionController session, _Api api) = await _signIn();

      await session.saveMyPreferences();

      expect(api.updates, isEmpty);
    });
  });

  group('the first screen', () {
    test('is read from the layout, beside the favourites', () {
      expect(MyPreferences.firstScreenIn(null), MyPreferences.lastScreen);
      expect(
        MyPreferences.firstScreenIn({
          'favourites': ['home'],
          MyPreferences.layoutKey: 'salesInvoices',
        }),
        'salesInvoices',
      );
    });
  });

  group('dates', () {
    tearDown(() => DisplayDates.use(null));

    test('are written in the chosen format, dd-MM-yyyy by default', () {
      final DateTime day = DateTime(2026, 10, 4);
      expect(DisplayDates.write(day), '04-10-2026');
      DisplayDates.use('yyyy-MM-dd');
      expect(DisplayDates.write(day), '2026-10-04');
      DisplayDates.use('MM/dd/yyyy');
      expect(DisplayDates.write(day), '10/04/2026');
      DisplayDates.use('nonsense');
      expect(DisplayDates.write(day), '04-10-2026');
    });
  });

  group('Settings', () {
    test('offers My Preferences with no firm open', () {
      final MenuItemSpec item = MenuLayout.settings.items
          .firstWhere((item) => item.path == MenuLayout.myPreferencesRoute);
      expect(item.isSetting, isTrue);
      expect(item.needsFirm, isFalse);
    });
  });
}
