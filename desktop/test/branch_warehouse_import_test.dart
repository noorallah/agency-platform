import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/branches/branch_warehouse_import_dialog.dart';
import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// The server writes an import batch in one transaction, so the dialog can
/// promise that a refused import left nothing behind. These pin the two halves
/// of that promise: nothing is sent until every row is usable, and a refusal
/// says plainly that nothing was written.

class _ImportApi extends ApiClient {
  _ImportApi({this.fails = false})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final bool fails;
  final List<Json> sent = <Json>[];

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
    if (fails) {
      throw const ApiException(
        'Branch code already exists in this firm.',
        statusCode: 409,
      );
    }
    sent.add(Map<String, dynamic>.from(body ?? const <String, dynamic>{}));
    final List<dynamic> records =
        (body?['records'] as List<dynamic>?) ?? const <dynamic>[];
    return <String, dynamic>{
      'success': true,
      'data': [
        for (final dynamic record in records)
          <String, dynamic>{
            'id': 'id-${records.indexOf(record)}',
            'code': (record as Json)['code'],
            'name': record['name'],
          },
      ],
    };
  }
}

/// A real file on disk: ``XFile.fromData`` leaves ``name`` and ``path``
/// empty, and the parser picks its format from the extension.
XFile _csv(String content) {
  final Directory dir = Directory.systemTemp.createTempSync('branch-import');
  final File file = File('${dir.path}/branches.csv')..writeAsStringSync(content);
  return XFile(file.path);
}

Future<void> _open(
  WidgetTester tester,
  _ImportApi api,
  String csv, {
  BranchImportTarget target = BranchImportTarget.branches,
}) async {
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: BranchWarehouseImportDialog(
          api: api,
          target: target,
          pickFileOverride: () async => _csv(csv),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
  // Reading the file is real I/O, which only runs inside runAsync -- outside
  // it, pumpAndSettle returns before the picker's future completes.
  await tester.runAsync(() async {
    await tester.tap(find.widgetWithText(OutlinedButton, 'Choose file'));
  });
  // Then wait for the parse to land rather than for a fixed 50ms. That sleep
  // was long enough on an idle machine and not on a loaded one: this test
  // failed three times on 2026-08-22 while another suite was running, each
  // time passing on its own, which reads exactly like a real regression until
  // you re-run it.
  await _waitForParse(tester);
}

/// Pump until the dialog has counted the rows it just read.
///
/// A parsed file renders one of two sentences -- "N rows ready." or "X of N
/// rows are usable." -- so the word they share is the signal. Polling for
/// "it parsed" rather than for a particular outcome keeps this helper shared:
/// which sentence, and which row errors, is what each test asserts.
Future<void> _waitForParse(
  WidgetTester tester, {
  Duration limit = const Duration(seconds: 10),
}) async {
  bool parsed() =>
      find.textContaining('rows ').evaluate().isNotEmpty ||
      find.textContaining('could not be read').evaluate().isNotEmpty;

  final Stopwatch elapsed = Stopwatch()..start();
  while (!parsed() && elapsed.elapsed < limit) {
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 10)),
    );
    await tester.pumpAndSettle();
  }
}

void main() {
  testWidgets('a clean file reports its rows and sends them as one batch',
      (tester) async {
    final _ImportApi api = _ImportApi();

    await _open(
      tester,
      api,
      'code,name\nBR-001,Head Office\nBR-002,Depot\n',
    );
    expect(find.text('2 rows ready.'), findsOneWidget);

    await tester.tap(find.widgetWithText(FilledButton, 'Import'));
    await tester.pumpAndSettle();

    expect(api.sent, hasLength(1), reason: 'one request, not one per row');
    expect((api.sent.single['records'] as List).length, 2);
    expect(find.text('Imported 2 branches.'), findsOneWidget);
  });

  testWidgets('a file with a bad row is not sent at all', (tester) async {
    final _ImportApi api = _ImportApi();

    await _open(
      tester,
      api,
      'code,name\nBR-001,Head Office\n,Missing code\n',
    );

    expect(find.textContaining('Row 3: code is required'), findsOneWidget);
    final FilledButton button = tester.widget<FilledButton>(
      find.widgetWithText(FilledButton, 'Import'),
    );
    expect(
      button.onPressed,
      isNull,
      reason: 'a batch is all or nothing, so one bad row blocks the send',
    );
    expect(api.sent, isEmpty);
  });

  testWidgets('a code the server would reject is caught before sending',
      (tester) async {
    final _ImportApi api = _ImportApi();

    await _open(
      tester,
      api,
      'code,name\nbr 001,Head Office\n',
    );

    expect(find.textContaining('upper-case'), findsOneWidget);
    expect(api.sent, isEmpty);
  });

  testWidgets('a refused import says plainly that nothing was written',
      (tester) async {
    final _ImportApi api = _ImportApi(fails: true);

    await _open(tester, api, 'code,name\nBR-001,Head Office\n');
    await tester.tap(find.widgetWithText(FilledButton, 'Import'));
    await tester.pumpAndSettle();

    expect(
      find.textContaining('Nothing was imported'),
      findsOneWidget,
      reason: "the user's first question is whether half of it went in",
    );
  });

  testWidgets('warehouses ask for the branch each one belongs to',
      (tester) async {
    final _ImportApi api = _ImportApi();

    await _open(
      tester,
      api,
      'code,name\nWH-001,Central\n',
      target: BranchImportTarget.warehouses,
    );

    expect(find.textContaining('Row 2: branch_id is required'), findsOneWidget);
    expect(api.sent, isEmpty);
  });
}
