import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/auth/refresh_token_store.dart';
import 'package:agency_desktop/core/auth/session_controller.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/preferences/user_preferences.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:flutter_test/flutter_test.dart';

/// What a sign-in may and may not overwrite.
///
/// Two things went missing at every sign-in. Saved searches and the
/// inventory views kept their state inside the cached server document, which
/// the sign-in replaces wholesale, so they came back empty each morning. And
/// the last screen was one machine-wide file, so on a shared PC user B landed
/// on user A's screen -- and a user moving to another PC landed nowhere in
/// particular. The first now lives apart from the server cache; the second
/// lives on the server, as the user's own `default_landing_page`.
Directory _scratch() {
  final Directory directory =
      Directory.systemTemp.createTempSync('workspace-state-test');
  addTearDown(() => directory.deleteSync(recursive: true));
  return directory;
}

Map<String, dynamic> _serverDocument({String landing = 'dashboard'}) => {
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
      'default_firm_id': null,
      'default_landing_page': landing,
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

/// A server that signs anybody in and remembers what it was told.
class _Api extends ApiClient {
  _Api({required this.landing})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => null,
        );

  String landing;
  final List<Map<String, dynamic>> patches = [];

  @override
  Future<AuthTokens> login(String email, String password) async =>
      const AuthTokens(
        accessToken: 'h.e30.s',
        refreshToken: 'r',
        forcePasswordChange: false,
      );

  @override
  Future<UserPreferences> getUserPreferences() async =>
      UserPreferences.fromJson(_serverDocument(landing: landing));

  @override
  Future<List<AssignedFirm>> myFirms() async => const [];

  @override
  Future<UserPreferences> updateUserPreferences(Json changes) async {
    patches.add(changes);
    landing = (changes['default_landing_page'] as String?) ?? landing;
    return UserPreferences.fromJson(_serverDocument(landing: landing));
  }
}

void main() {
  group("a screen's own state survives a sign-in", () {
    test('replacing the server cache leaves workspace state alone', () async {
      final DesktopPreferencesService preferences =
          DesktopPreferencesService(directory: _scratch());
      await preferences.load();
      await preferences.saveWorkspaceState('workspace.global_search', {
        'saved_searches': ['overdue invoices'],
      });

      // What `_applyServerPreferences` does at every sign-in.
      await preferences.cacheServerPreferences(_serverDocument());

      expect(
        preferences.workspaceState('workspace.global_search')['saved_searches'],
        ['overdue invoices'],
      );
      expect(preferences.current.serverPreferences['workspace.global_search'],
          isNull,
          reason: 'the server cache holds the server document and nothing else');
    });

    test('state an older build kept inside the server cache is lifted once',
        () async {
      // The fix for losing saved searches must not itself lose them.
      final Directory directory = _scratch();
      File('${directory.path}${Platform.pathSeparator}desktop_preferences.json')
          .writeAsStringSync(jsonEncode({
        'version': 1,
        'server_preferences': {
          ..._serverDocument(),
          'workspace.global_search': {
            'recent_searches': ['ravi'],
          },
          'inventory_management': {'low_stock_only': true},
        },
      }));
      final DesktopPreferencesService preferences =
          DesktopPreferencesService(directory: directory);
      await preferences.load();

      expect(
        preferences.workspaceState('workspace.global_search')['recent_searches'],
        ['ravi'],
      );
      expect(
        preferences.workspaceState('inventory_management')['low_stock_only'],
        isTrue,
      );
      expect(preferences.workspaceState('nothing-here'), isEmpty);
    });
  });

  group('the last screen is the user\'s, not the machine\'s', () {
    Future<(SessionController, _Api)> signIn({
      required String serverLanding,
      String? localLast,
    }) async {
      final Directory directory = _scratch();
      if (localLast != null) {
        File('${directory.path}${Platform.pathSeparator}desktop_preferences.json')
            .writeAsStringSync(jsonEncode({
          'version': 1,
          'last_workspace': localLast,
        }));
      }
      final DesktopPreferencesService preferences =
          DesktopPreferencesService(directory: directory);
      await preferences.load();
      final SessionController session = SessionController(
        baseUrl: 'http://localhost:8000',
        tokenStore: _MemoryTokenStore(),
        preferences: preferences,
      );
      final _Api api = _Api(landing: serverLanding);
      session.api = api;
      await session.login('a@b.c', 'pw',
          rememberUsername: false, rememberMe: false);
      expect(session.status, SessionStatus.authenticated);
      return (session, api);
    }

    test('sign-in opens on the screen the server remembers for this user',
        () async {
      // Not the machine's last screen, which is whoever signed in last.
      final (SessionController session, _) = await signIn(
        serverLanding: 'salesOrders/sales-orders',
        localLast: 'inventory/stock',
      );

      expect(session.lastWorkspace, 'salesOrders/sales-orders');
    });

    test('moving to a screen is remembered on the server', () async {
      final (SessionController session, _Api api) =
          await signIn(serverLanding: 'dashboard');

      await session.saveLastWorkspace('goodsReceipts/goods-receipts');

      expect(api.patches.last, {
        'default_landing_page': 'goodsReceipts/goods-receipts',
      });
      expect(session.lastWorkspace, 'goodsReceipts/goods-receipts');
    });

    test('staying on the same screen sends nothing', () async {
      // The router persists on every change; the server is asked only when
      // the answer would differ.
      final (SessionController session, _Api api) =
          await signIn(serverLanding: 'inventory/stock');
      api.patches.clear();

      await session.saveLastWorkspace('inventory/stock');

      expect(api.patches, isEmpty);
    });

    test('a signed-out session keeps it locally and asks nobody', () async {
      final DesktopPreferencesService preferences =
          DesktopPreferencesService(directory: _scratch());
      await preferences.load();
      final SessionController session = SessionController(
        baseUrl: 'http://localhost:8000',
        tokenStore: _MemoryTokenStore(),
        preferences: preferences,
      );
      final _Api api = _Api(landing: 'dashboard');
      session.api = api;

      await session.saveLastWorkspace('reports/register');

      expect(api.patches, isEmpty);
      expect(preferences.current.lastWorkspace, 'reports/register');
      expect(session.lastWorkspace, 'reports/register',
          reason: 'with no server document, the local copy is the answer');
    });
  });
}
