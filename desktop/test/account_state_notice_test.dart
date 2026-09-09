// A refusal that names the account's state reaches the person.
//
// The server answers one message for every credential failure, so nothing
// about an address is disclosed -- and until 2026-09-09 it answered the same
// message for a locked, inactive or expired account, which left somebody
// holding the right password with no way to tell a lockout from a typo
// (docs/BACKLOG.md 18.1, 18.2). Those three refusals now carry their own
// error code and message. On the login screen the message is shown as the
// server sent it, which needed no client change; this file pins the other
// door, the token refresh, where the client used to discard the reason and
// drop the person on the sign-in screen with nothing said -- and the moment
// a lockout lifts, which the sign-in screen counts down to.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/auth/refresh_token_store.dart';
import 'package:agency_desktop/core/auth/session_controller.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:flutter_test/flutter_test.dart';

const String _inactiveMessage =
    'This account is inactive. Ask an administrator to reactivate it.';

class _MemoryTokenStore implements RefreshTokenStore {
  _MemoryTokenStore([this._token]);
  String? _token;
  @override
  Future<String?> read() async => _token;
  @override
  Future<void> write(String token) async => _token = token;
  @override
  Future<void> clear() async => _token = null;
}

/// An API whose refresh is refused the way the server refuses it.
class _RefusingApi extends ApiClient {
  _RefusingApi(this.refusal)
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => null,
        );

  final ApiException refusal;

  @override
  Future<AuthTokens> refresh(String refreshToken) async => throw refusal;

  @override
  Future<AuthTokens> login(String email, String password) async =>
      throw refusal;
}

Future<SessionController> _signedInAgainst(ApiException refusal) async {
  final Directory directory =
      Directory.systemTemp.createTempSync('account-state-lock');
  addTearDown(() => directory.deleteSync(recursive: true));
  final DesktopPreferencesService preferences =
      DesktopPreferencesService(directory: directory);
  await preferences.load();
  final SessionController session = SessionController(
    baseUrl: 'http://localhost:8000',
    tokenStore: _MemoryTokenStore(),
    preferences: preferences,
  )..api = _RefusingApi(refusal);
  await session.login('a@example.com', 'pw',
      rememberUsername: false, rememberMe: false);
  return session;
}

Future<SessionController> _restoredAgainst(ApiException refusal) async {
  final Directory directory =
      Directory.systemTemp.createTempSync('account-state-notice');
  addTearDown(() => directory.deleteSync(recursive: true));
  final DesktopPreferencesService preferences =
      DesktopPreferencesService(directory: directory);
  await preferences.load();
  final SessionController session = SessionController(
    baseUrl: 'http://localhost:8000',
    tokenStore: _MemoryTokenStore('r'),
    preferences: preferences,
  )..api = _RefusingApi(refusal);
  await session.restore();
  return session;
}

/// A loopback server answering the error envelope the backend sends.
Future<ApiClient> _serverRefusingWith(Map<String, dynamic> error) async {
  final HttpServer server =
      await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
  server.listen((HttpRequest request) async {
    request.response
      ..statusCode = HttpStatus.unauthorized
      ..headers.contentType = ContentType.json
      ..write(jsonEncode(<String, dynamic>{'success': false, 'error': error}));
    await request.response.close();
  });
  addTearDown(() => server.close(force: true));
  return ApiClient(
    baseUrl: 'http://127.0.0.1:${server.port}',
    accessToken: () => null,
    refreshAccessToken: () async => false,
    activeFirmId: () => null,
  );
}

void main() {
  group('the error code travels with the exception', () {
    test('a coded refusal is readable as one', () async {
      final ApiClient api = await _serverRefusingWith(<String, dynamic>{
        'code': 'account_inactive',
        'message': _inactiveMessage,
      });

      final ApiException refusal = await api
          .refresh('r')
          .then<ApiException>((_) => fail('the server refused this'))
          .catchError((Object e) => e as ApiException);

      expect(refusal.code, 'account_inactive');
      expect(refusal.message, _inactiveMessage);
      expect(refusal.namesAccountState, isTrue);
    });

    test('a credential refusal names no state', () async {
      final ApiClient api = await _serverRefusingWith(<String, dynamic>{
        'code': 'authentication_required',
        'message': 'Invalid email or password.',
      });

      final ApiException refusal = await api
          .login('a@example.com', 'pw')
          .then<ApiException>((_) => fail('the server refused this'))
          .catchError((Object e) => e as ApiException);

      expect(refusal.code, 'authentication_required');
      expect(refusal.namesAccountState, isFalse);
    });

    test('an envelope without a code leaves it null', () async {
      final ApiClient api = await _serverRefusingWith(<String, dynamic>{
        'message': 'Request refused.',
      });

      final ApiException refusal = await api
          .refresh('r')
          .then<ApiException>((_) => fail('the server refused this'))
          .catchError((Object e) => e as ApiException);

      expect(refusal.code, isNull);
      expect(refusal.namesAccountState, isFalse);
    });
  });

  group('a lockout says when it lifts', () {
    test('the seconds left become a moment the screen can count to',
        () async {
      final DateTime before = DateTime.now();
      final SessionController session = await _signedInAgainst(
        const ApiException(
          'This account is locked after too many failed sign-in attempts. '
          'Try again in 5 minutes.',
          statusCode: HttpStatus.unauthorized,
          code: 'account_locked',
          details: <String, dynamic>{'retry_after_seconds': 300},
        ),
      );

      expect(session.status, SessionStatus.error);
      expect(session.lockedUntil, isNotNull);
      final Duration left = session.lockedUntil!.difference(before);
      expect(left.inSeconds, inInclusiveRange(299, 300));
    });

    test('any other refusal names no moment', () async {
      final SessionController session = await _signedInAgainst(
        const ApiException(
          'Invalid email or password.',
          statusCode: HttpStatus.unauthorized,
          code: 'authentication_required',
        ),
      );

      expect(session.status, SessionStatus.error);
      expect(session.lockedUntil, isNull);
    });

    test('a lockout that did not say how long names no moment', () async {
      final SessionController session = await _signedInAgainst(
        const ApiException(
          'This account is locked.',
          statusCode: HttpStatus.unauthorized,
          code: 'account_locked',
        ),
      );

      expect(session.lockedUntil, isNull,
          reason: 'the message is still shown; only the countdown is absent');
    });
  });

  group('a session ended by the account state says why', () {
    test('an inactive account leaves its message on the sign-in screen',
        () async {
      final SessionController session = await _restoredAgainst(
        const ApiException(
          _inactiveMessage,
          statusCode: HttpStatus.unauthorized,
          code: 'account_inactive',
        ),
      );

      expect(session.status, SessionStatus.signedOut);
      expect(session.notice, _inactiveMessage);
      expect(session.error, isNull,
          reason: 'no login was attempted, so there is no login error');
    });

    test('an ordinary token expiry says nothing', () async {
      final SessionController session = await _restoredAgainst(
        const ApiException(
          'The refresh token is invalid or expired.',
          statusCode: HttpStatus.unauthorized,
          code: 'authentication_required',
        ),
      );

      expect(session.status, SessionStatus.signedOut);
      expect(session.notice, isNull,
          reason: 'a session ending the ordinary way is not news');
    });

    test('the next sign-in attempt clears the notice', () async {
      final SessionController session = await _restoredAgainst(
        const ApiException(
          _inactiveMessage,
          statusCode: HttpStatus.unauthorized,
          code: 'account_expired',
        ),
      );
      expect(session.notice, isNotNull);

      // The refusing API has no login of its own, so the attempt fails at
      // the network; what matters is that the old notice does not outlive it.
      await session.login('a@example.com', 'pw',
          rememberUsername: false, rememberMe: false);

      expect(session.notice, isNull);
    });
  });
}
