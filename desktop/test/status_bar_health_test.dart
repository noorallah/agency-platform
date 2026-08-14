import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/ui/workspace/health_probe.dart';
import 'package:agency_desktop/ui/workspace/workspace_components.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// The status bar's health lights.
///
/// They were passed `checking` and `unknown` as literals and nothing ever
/// probed them, so the bar reported "checking" for the life of the application.
/// A light that never changes is worse than no light, because it gets believed
/// once.
class _HealthApi extends ApiClient {
  _HealthApi({required this.backend, required this.database})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => null,
        );

  final bool backend;
  final bool database;
  int backendCalls = 0;
  int databaseCalls = 0;

  @override
  Future<bool> backendReachable() async {
    backendCalls++;
    return backend;
  }

  @override
  Future<bool> databaseReachable() async {
    databaseCalls++;
    return database;
  }
}

void main() {
  group('resolving the two lights', () {
    test('a healthy server and database are both online', () {
      final HealthSnapshot snapshot =
          resolveHealth(backend: true, database: true);
      expect(snapshot.backend, ConnectionStateIndicator.online);
      expect(snapshot.database, ConnectionStateIndicator.online);
    });

    test('a server whose database has gone shows exactly that', () {
      // The case the second light exists for. One light for both would hide it.
      final HealthSnapshot snapshot =
          resolveHealth(backend: true, database: false);
      expect(snapshot.backend, ConnectionStateIndicator.online);
      expect(snapshot.database, ConnectionStateIndicator.offline);
    });

    test('an unreachable server leaves the database unknown, not offline', () {
      // With no answer from the server, this client cannot tell a database that
      // has gone from one it simply cannot see past. Claiming "offline" would
      // be the same kind of wrong as the literal it replaced.
      final HealthSnapshot snapshot =
          resolveHealth(backend: false, database: false);
      expect(snapshot.backend, ConnectionStateIndicator.offline);
      expect(snapshot.database, ConnectionStateIndicator.unknown);
    });
  });

  group('asking the server', () {
    test('both are asked when the server answers', () async {
      final _HealthApi api = _HealthApi(backend: true, database: true);
      await probeHealth(api);
      expect(api.backendCalls, 1);
      expect(api.databaseCalls, 1);
    });

    test('the database is not asked when the server is unreachable', () async {
      // Otherwise a disconnected client waits out two timeouts to learn one
      // thing, which doubles how long it takes to notice.
      final _HealthApi api = _HealthApi(backend: false, database: false);
      final HealthSnapshot snapshot = await probeHealth(api);
      expect(api.backendCalls, 1);
      expect(api.databaseCalls, 0);
      expect(snapshot.database, ConnectionStateIndicator.unknown);
    });
  });

  testWidgets('the bar renders the state it is given', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: ApplicationStatusBar(
            stateText: 'Offline',
            backend: ConnectionStateIndicator.offline,
            database: ConnectionStateIndicator.unknown,
          ),
        ),
      ),
    );

    expect(find.text('API: offline'), findsOneWidget);
    expect(find.text('DB: unknown'), findsOneWidget);
    expect(find.text('Offline'), findsOneWidget);
    // The old literal must not survive anywhere in the rendered bar.
    expect(find.text('API: checking'), findsNothing);
  });
}
