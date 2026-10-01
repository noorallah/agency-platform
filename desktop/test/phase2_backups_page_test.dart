import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/phase2/backups_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Admin > System > Backups in the phase 2 app.
class _BackupsApi extends ApiClient {
  _BackupsApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => null,
        );

  List<Json> backups = [
    _backup('manual', '20261001-144700', by: 'admin@x'),
    _backup('daily', '20261001-020000'),
    _backup('pre-upgrade', '20260930-101500', complete: false),
    _backup('manual', '20260929-090000', complete: null, size: null),
  ];

  /// What the next GET answers as the run.
  Json run = _idle;

  /// What the next POST does.
  ApiException? refuse;
  int gets = 0;
  int posts = 0;

  @override
  Future<Json> request(
    String method,
    String path, {
    Json? body,
    Map<String, String>? query,
    bool authenticated = true,
    bool retrying = false,
    int? expectedVersion,
  }) async {
    expect(path, '/api/v1/backups');
    if (method == 'POST') {
      posts++;
      if (refuse != null) throw refuse!;
      run = {
        'status': 'running',
        'requested_by': 'admin@x',
        'started_at': '2026-10-01T09:00:00+00:00',
        'finished_at': null,
        'folder': null,
        'message': null,
        'stores': const [],
      };
    } else {
      gets++;
    }
    return {
      'data': {
        'backup_directory': r'C:\ProgramData\Agency Platform\backups',
        'keep_manual': 10,
        'run': run,
        'backups': backups,
      },
    };
  }
}

const Json _idle = {
  'status': 'idle',
  'requested_by': null,
  'started_at': null,
  'finished_at': null,
  'folder': null,
  'message': null,
  'stores': <Json>[],
};

Json _backup(
  String kind,
  String name, {
  String? by,
  bool? complete = true,
  int? size = 29782016,
}) =>
    {
      'kind': kind,
      'name': name,
      'path': 'C:\\backups\\$kind\\$name',
      'created_at': '2026-10-01T09:17:00+00:00',
      'complete': complete,
      'size_bytes': size,
      'files': size == null ? null : 2,
      'application_version': '1.1.0',
      'requested_by': by,
      'stores': kind == 'manual' && by != null
          ? [
              {
                'label': 'Platform',
                'database': 'agency',
                'schema_name': 'platform',
                'file': 'platform.dump',
                'size_bytes': 1048576,
                'tables': 40,
                'revision': '0161',
                'outcome': 'ok',
                'detail': null,
              },
            ]
          : <Json>[],
    };

Future<_BackupsApi> _pump(WidgetTester tester, {_BackupsApi? with_}) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final _BackupsApi api = with_ ?? _BackupsApi();
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Phase2Scope(
        child: BackupsPage(api: api, pollInterval: const Duration(seconds: 3)),
      ),
    ),
  ));
  await tester.pumpAndSettle();
  return api;
}

void main() {
  testWidgets('lists the backups with all three kinds and their status',
      (tester) async {
    await _pump(tester);
    expect(find.text('Backups'), findsWidgets);
    expect(find.text('By hand'), findsWidgets);
    expect(find.text('Nightly'), findsOneWidget);
    expect(find.text('Before upgrade'), findsOneWidget);
    expect(find.text('Complete'), findsNWidgets(2));
    expect(find.text('Unfinished'), findsOneWidget);
    expect(find.text('Not readable by the server'), findsOneWidget);
    expect(find.text('28.4 MB'), findsNWidgets(3));
    expect(find.text('admin@x'), findsOneWidget);
    expect(find.textContaining('every night at 02:00'), findsOneWidget);
    expect(find.textContaining(r'C:\ProgramData\Agency Platform\backups'),
        findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('selecting a row shows its folder and its stores',
      (tester) async {
    await _pump(tester);
    await tester.tap(find.text('admin@x'));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('backup-detail')), findsOneWidget);
    expect(find.text(r'C:\backups\manual\20261001-144700'), findsOneWidget);
    expect(find.text('Platform'), findsOneWidget);
    expect(find.text('40'), findsOneWidget);
    expect(find.byKey(const ValueKey('backup-copy-path')), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('Back up now runs, polls, and shows the result', (tester) async {
    final _BackupsApi api = await _pump(tester);
    await tester.tap(find.byKey(const ValueKey('backup-now')));
    await tester.pump();
    await tester.pump();
    expect(api.posts, 1);
    expect(find.byKey(const ValueKey('backup-running')), findsOneWidget);
    expect(find.textContaining('started by admin@x'), findsOneWidget);
    expect(find.byType(LinearProgressIndicator), findsWidgets);
    // The button waits for the run to finish.
    expect(
      tester
          .widget<FilledButton>(find.byKey(const ValueKey('backup-now')))
          .onPressed,
      isNull,
    );

    api.backups = [_backup('manual', '20261001-150000', by: 'admin@x'),
        ...api.backups];
    api.run = {
      'status': 'succeeded',
      'requested_by': 'admin@x',
      'started_at': '2026-10-01T09:00:00+00:00',
      'finished_at': '2026-10-01T09:01:00+00:00',
      'folder': r'C:\backups\manual\20261001-150000',
      'message': 'Backed up 2 stores (28.4 MB).',
      'stores': <Json>[],
    };
    await tester.pump(const Duration(seconds: 3));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('backup-running')), findsNothing);
    expect(find.text('Backed up 2 stores (28.4 MB).'), findsOneWidget);
    expect(find.text('By hand'), findsNWidgets(3));
    expect(
      tester
          .widget<FilledButton>(find.byKey(const ValueKey('backup-now')))
          .onPressed,
      isNotNull,
    );
    expect(tester.takeException(), isNull);
  });

  testWidgets('a failed run is shown in the error colour', (tester) async {
    final _BackupsApi api = await _pump(tester);
    await tester.tap(find.byKey(const ValueKey('backup-now')));
    await tester.pump();
    await tester.pump();
    api.run = {
      ..._idle,
      'status': 'failed',
      'message': 'The disk is full.',
    };
    await tester.pump(const Duration(seconds: 3));
    await tester.pumpAndSettle();
    final Text message =
        tester.widget<Text>(find.byKey(const ValueKey('backup-result')));
    expect(message.data, 'The disk is full.');
    expect(
      message.style?.color,
      Theme.of(tester.element(find.byType(BackupsPage))).colorScheme.error,
    );
  });

  testWidgets('a 409 shows the server message', (tester) async {
    final _BackupsApi api = _BackupsApi()
      ..refuse = const ApiException(
        'A backup is already running.',
        statusCode: 409,
      );
    await _pump(tester, with_: api);
    await tester.tap(find.byKey(const ValueKey('backup-now')));
    await tester.pumpAndSettle();
    expect(find.text('A backup is already running.'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('no backups yet is said plainly', (tester) async {
    final _BackupsApi api = _BackupsApi()..backups = [];
    await _pump(tester, with_: api);
    expect(find.text('No backups yet'), findsOneWidget);
    expect(find.byKey(const ValueKey('backup-now')), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
