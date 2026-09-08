import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/auth/refresh_token_store.dart';
import 'package:agency_desktop/core/auth/session_controller.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/preferences/user_preferences.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/identity/primary_firm_dialog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// The user menu knows who is signed in, and where they start.
///
/// Until `GET /me` existed the menu showed the address typed at the login
/// form, and after a restored session the word "User". And the primary firm
/// -- the one a sign-in lands in -- was an administrator's to set and lost to
/// the last-used firm anyway, because the landing rule read the last firm
/// first. Switching is for the session; the primary is for next time.
AssignedFirm _firm(String id, {bool primary = false}) => AssignedFirm(
      id: id,
      code: id.toUpperCase(),
      name: 'Firm $id',
      isPrimary: primary,
    );

Map<String, dynamic> _me({String? primary}) => {
      'id': 'u-1',
      'email': 'asha@example.com',
      'full_name': 'Asha Rao',
      'is_platform_admin': false,
      'primary_firm_id': primary,
    };

Map<String, dynamic> _serverDocument() => {
      'preferences_version': 1,
      'preferred_theme': 'light',
      'preferred_palette': 'neutral',
      'preferred_theme_mode': 'system',
      'preferred_high_contrast': false,
      'language': 'en',
      'date_format': 'yyyy-MM-dd',
      'time_format': '24h',
      'number_format': '1,234.56',
      'currency_format': 'symbol',
      'default_firm_id': 'c',
      'default_landing_page': 'dashboard',
      'rows_per_page': 20,
      'notification_preferences': <String, dynamic>{},
      'dashboard_layout': <String, dynamic>{},
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
  _Api({required this.assigned})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => null,
        );

  /// The firms this person belongs to, as `/me/firms` would list them.
  List<AssignedFirm> assigned;
  String? primary;
  final List<String> primaryPuts = [];

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
  Future<UserPreferences> updateUserPreferences(Json changes) async =>
      UserPreferences.fromJson(_serverDocument());

  @override
  Future<List<AssignedFirm>> myFirms() async => assigned;

  @override
  Future<CurrentUser> me() async => CurrentUser.fromJson(_me(primary: primary));

  @override
  Future<CurrentUser> setPrimaryFirm(String firmId) async {
    primaryPuts.add(firmId);
    primary = firmId;
    assigned = [
      for (final AssignedFirm firm in assigned)
        _firm(firm.id, primary: firm.id == firmId),
    ];
    return CurrentUser.fromJson(_me(primary: primary));
  }
}

Future<(SessionController, _Api)> _signIn(List<AssignedFirm> firms) async {
  final Directory directory =
      Directory.systemTemp.createTempSync('primary-firm-test');
  addTearDown(() => directory.deleteSync(recursive: true));
  final DesktopPreferencesService preferences =
      DesktopPreferencesService(directory: directory);
  await preferences.load();
  final SessionController session = SessionController(
    baseUrl: 'http://localhost:8000',
    tokenStore: _MemoryTokenStore(),
    preferences: preferences,
  );
  final _Api api = _Api(assigned: firms)
    ..primary = firms.where((f) => f.isPrimary).map((f) => f.id).firstOrNull;
  session.api = api;
  await session.login('asha@example.com', 'pw',
      rememberUsername: false, rememberMe: false);
  return (session, api);
}

void main() {
  group('where a sign-in lands', () {
    final List<AssignedFirm> firms = [
      _firm('a'),
      _firm('b', primary: true),
      _firm('c'),
    ];

    test('the primary firm, over the one last used', () {
      // The whole point of letting a person choose one. Read the other way
      // round, the primary flag meant nothing to anybody who ever switched.
      expect(
        SessionController.resolveLandingFirm(firms, 'c', isPlatformAdmin: false)
            ?.id,
        'b',
      );
    });

    test('the last used firm when no primary is set', () {
      final List<AssignedFirm> unmarked = [_firm('a'), _firm('b'), _firm('c')];
      expect(
        SessionController.resolveLandingFirm(unmarked, 'c',
                isPlatformAdmin: false)
            ?.id,
        'c',
      );
    });

    test('and through the real sign-in', () async {
      final (SessionController session, _) = await _signIn(firms);

      expect(session.currentFirm?.id, 'b',
          reason: 'default_firm_id says c; the primary says b');
    });
  });

  group('who is signed in', () {
    test('the menu can name the person, not the login form', () async {
      final (SessionController session, _) = await _signIn([_firm('a')]);

      expect(session.currentUser?.fullName, 'Asha Rao');
      expect(session.currentUser?.email, 'asha@example.com');
      expect(session.userLabel, 'Asha Rao');
    });

    test('a person with no name is called by their address', () async {
      final SessionController session = SessionController(
        baseUrl: 'http://localhost:8000',
        tokenStore: _MemoryTokenStore(),
      );
      expect(session.userLabel, isNull, reason: 'nothing known yet');
    });
  });

  group('choosing the primary firm', () {
    test('goes to the server and re-reads the firm list', () async {
      final (SessionController session, _Api api) =
          await _signIn([_firm('a', primary: true), _firm('b')]);

      await session.setPrimaryFirm('b');

      expect(api.primaryPuts, ['b']);
      expect(session.firms.singleWhere((f) => f.isPrimary).id, 'b');
      expect(session.currentUser?.primaryFirmId, 'b');
      // Nothing about the current session moved: switching is for now.
      expect(session.currentFirm?.id, 'a');
    });

    testWidgets('the dialog starts on the current primary and returns the '
        'new one', (tester) async {
      String? chosen;
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: Builder(
            builder: (context) => TextButton(
              onPressed: () async => chosen = await choosePrimaryFirm(
                context,
                firms: [_firm('a', primary: true), _firm('b')],
              ),
              child: const Text('open'),
            ),
          ),
        ),
      ));
      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();

      final FilledButton save =
          tester.widget<FilledButton>(find.widgetWithText(FilledButton, 'Save'));
      expect(save.onPressed, isNull,
          reason: 'saving the answer already in force changes nothing');

      await tester.tap(find.text('Firm b'));
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(FilledButton, 'Save'));
      await tester.pumpAndSettle();

      expect(chosen, 'b');
    });

    testWidgets('a dismissal chooses nothing', (tester) async {
      String? chosen = 'untouched';
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: Builder(
            builder: (context) => TextButton(
              onPressed: () async => chosen = await choosePrimaryFirm(
                context,
                firms: [_firm('a', primary: true), _firm('b')],
              ),
              child: const Text('open'),
            ),
          ),
        ),
      ));
      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Cancel'));
      await tester.pumpAndSettle();

      expect(chosen, isNull);
    });
  });
}
