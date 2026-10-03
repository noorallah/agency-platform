import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/settlement_direction.dart';
import 'package:agency_desktop/ui/finance/ledger_files_dialog.dart';
import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Files kept with a journal entry, a receipt or a payment (ACC-10): the
/// calls are recorded at the `request` level so the paths and body keys the
/// server declares are what is checked.
class _Call {
  _Call(this.method, this.path, this.body);
  final String method;
  final String path;
  final Object? body;
}

class _FilesApi extends ApiClient {
  _FilesApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<_Call> calls = [];
  String? refuse;
  final List<Json> rows = [
    {
      'id': 'a-1',
      'journal_entry_id': 'j-1',
      'settlement_id': null,
      'file_name': 'voucher.pdf',
      'mime_type': 'application/pdf',
      'file_path': '/scans/voucher.pdf',
      'caption': 'Signed copy',
      'created_at': '2026-10-03T10:00:00Z',
      'created_by': 'u-1',
    },
  ];

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
    calls.add(_Call(method, path, body));
    if (method != 'GET' && refuse != null) throw ApiException(refuse!);
    if (method == 'DELETE') {
      rows.removeWhere((Json r) => path.endsWith('/${r['id']}'));
      return <String, dynamic>{};
    }
    if (method == 'POST') {
      final List<dynamic> items = (body!)['attachments'] as List;
      rows.add({
        'id': 'a-new',
        'file_name': (items.first as Json)['file_name'],
        'file_path': (items.first as Json)['file_path'],
        'created_at': '2026-10-03T11:00:00Z',
      });
    }
    return {'success': true, 'data': List<Json>.of(rows)};
  }
}

void _bigWindow(WidgetTester tester) {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
}

Future<void> _open(WidgetTester tester, Widget dialog) async {
  _bigWindow(tester);
  await tester.pumpWidget(MaterialApp(home: Scaffold(body: dialog)));
  await tester.pumpAndSettle();
}

Widget _journal(_FilesApi api, {bool canEdit = true, bool canView = true}) =>
    LedgerFilesDialog.journal(
      api: api,
      journalId: 'j-1',
      subtitle: 'JV-1',
      canEdit: canEdit,
      canView: canView,
      pickFiles: () async => [XFile('slip.pdf')],
    );

void main() {
  testWidgets('a journal lists its files with caption', (tester) async {
    final _FilesApi api = _FilesApi();
    await _open(tester, _journal(api));
    expect(api.calls.single.method, 'GET');
    expect(api.calls.single.path,
        '/api/v1/finance/journal-entries/j-1/attachments');
    expect(find.text('voucher.pdf'), findsOneWidget);
    expect(find.textContaining('Signed copy'), findsOneWidget);
  });

  testWidgets('a journal attach posts exactly the declared keys',
      (tester) async {
    final _FilesApi api = _FilesApi();
    await _open(tester, _journal(api));
    await tester.tap(find.text('Attach photo or document'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).first, 'Bank advice');
    await tester.pump();
    await tester.tap(find.text('Save files'));
    await tester.pumpAndSettle();
    final _Call post = api.calls.firstWhere((c) => c.method == 'POST');
    expect(post.path, '/api/v1/finance/journal-entries/j-1/attachments');
    final List<dynamic> items = (post.body! as Json)['attachments'] as List;
    expect((post.body! as Json).keys, ['attachments']);
    expect((items.single as Json).keys.toSet(),
        {'file_name', 'mime_type', 'file_path', 'caption'});
    expect((items.single as Json)['file_name'], 'slip.pdf');
    expect((items.single as Json)['mime_type'], 'application/pdf');
    expect((items.single as Json)['caption'], 'Bank advice');
    expect(find.text('slip.pdf'), findsOneWidget);
  });

  testWidgets('a journal remove asks, then calls DELETE on the right path',
      (tester) async {
    final _FilesApi api = _FilesApi();
    await _open(tester, _journal(api));
    await tester.tap(find.byTooltip('Remove').first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Remove').last);
    await tester.pumpAndSettle();
    final _Call del = api.calls.firstWhere((c) => c.method == 'DELETE');
    expect(del.path,
        '/api/v1/finance/journal-entries/j-1/attachments/a-1');
    expect(find.text('voucher.pdf'), findsNothing);
  });

  for (final SettlementDirection direction in [
    SettlementDirection.receipt,
    SettlementDirection.payment,
  ]) {
    testWidgets('a ${direction.noun} lists, attaches and removes',
        (tester) async {
      final _FilesApi api = _FilesApi();
      await _open(
        tester,
        LedgerFilesDialog(
          api: api,
          recordId: 's-9',
          direction: direction,
          subtitle: 'X-9',
          pickFiles: () async => [XFile('slip.pdf')],
        ),
      );
      final String base = '/api/v1/${direction.path}/s-9/attachments';
      expect(api.calls.first.path, base);
      await tester.tap(find.text('Attach photo or document'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Save files'));
      await tester.pumpAndSettle();
      expect(
          api.calls.any((c) => c.method == 'POST' && c.path == base), isTrue);
      await tester.tap(find.byTooltip('Remove').first);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Remove').last);
      await tester.pumpAndSettle();
      expect(
        api.calls.any(
            (c) => c.method == 'DELETE' && c.path == '$base/a-1'),
        isTrue,
      );
    });
  }

  testWidgets('a refusal is shown and the dialog keeps what was picked',
      (tester) async {
    final _FilesApi api = _FilesApi()..refuse = 'The period is closed.';
    await _open(tester, _journal(api));
    await tester.tap(find.text('Attach photo or document'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Save files'));
    await tester.pumpAndSettle();
    expect(find.text('The period is closed.'), findsOneWidget);
    expect(find.text('slip.pdf'), findsOneWidget);
  });

  testWidgets('a reader without the create permission cannot attach or remove',
      (tester) async {
    final _FilesApi api = _FilesApi();
    await _open(tester, _journal(api, canEdit: false));
    expect(find.text('voucher.pdf'), findsOneWidget);
    expect(find.byTooltip('Remove'), findsNothing);
    expect(find.text('Attach photo or document'), findsNothing);
    expect(find.text('Save files'), findsNothing);
  });

  testWidgets('without the view permission nothing is read', (tester) async {
    final _FilesApi api = _FilesApi();
    await _open(tester, _journal(api, canView: false));
    expect(api.calls, isEmpty);
    expect(find.text('voucher.pdf'), findsNothing);
  });

  testWidgets('fits the smallest window', (tester) async {
    final _FilesApi api = _FilesApi();
    tester.view.physicalSize = const Size(800, 600);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: _journal(api))));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
  });
}
