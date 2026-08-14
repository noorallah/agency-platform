import '../../core/api/api_client.dart';
import 'workspace_components.dart';

/// What the status bar knows about the server right now.
class HealthSnapshot {
  const HealthSnapshot({required this.backend, required this.database});

  final ConnectionStateIndicator backend;
  final ConnectionStateIndicator database;

  /// The state before the first answer has come back.
  static const HealthSnapshot checking = HealthSnapshot(
    backend: ConnectionStateIndicator.checking,
    database: ConnectionStateIndicator.checking,
  );
}

/// Turn two yes/no answers into the two lights the status bar shows.
///
/// Separated from the asking so the decision can be tested without a server.
/// The part worth pinning is the third state: when the backend is unreachable
/// the database is **unknown**, not offline. This client has no way to tell a
/// database that has gone from a database it simply cannot see past a dead
/// server, and a status bar that claims the difference is the same kind of
/// wrong as the literal `checking` it replaced.
HealthSnapshot resolveHealth({required bool backend, required bool database}) {
  if (!backend) {
    return const HealthSnapshot(
      backend: ConnectionStateIndicator.offline,
      database: ConnectionStateIndicator.unknown,
    );
  }
  return HealthSnapshot(
    backend: ConnectionStateIndicator.online,
    database: database
        ? ConnectionStateIndicator.online
        : ConnectionStateIndicator.offline,
  );
}

/// Ask the server whether it, and its database, are answering.
///
/// The database is only asked about when the server answered at all: otherwise
/// the second call just waits for the same timeout to report the same outage,
/// which doubles how long a disconnected client takes to notice.
Future<HealthSnapshot> probeHealth(ApiClient api) async {
  final bool backend = await api.backendReachable();
  final bool database = backend && await api.databaseReachable();
  return resolveHealth(backend: backend, database: database);
}
