// A retired tax record could not be brought back.
//
// `restoreTaxSystem`, `restoreTaxComponent` and `restoreTaxProfile` each had a
// route and a client method and nothing that called them, and the three lists
// never asked for deleted rows -- `include_deleted` defaults to false and the
// client did not send it. So a retired system, component or profile vanished
// from every list with no way to see it or bring it back: from the desktop, a
// soft delete behaved like a permanent one.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/tax/tax_management_page.dart';
import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions(List<String> codes) => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': codes,
  }));

class _Api extends ApiClient {
  _Api({this.rows = const <Json>[]})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Json> rows;

  /// Every query the page issued, so a test can say what it asked for rather
  /// than only what it rendered.
  final List<Map<String, String>> queries = <Map<String, String>>[];
  final List<String> posted = <String>[];

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
    if (method == 'POST') {
      posted.add(path);
      return <String, dynamic>{'data': rows.isEmpty ? null : rows.first};
    }
    if (query != null) queries.add(query);
    if (path.contains('/systems')) {
      return <String, dynamic>{
        'data': rows,
        'pagination': <String, dynamic>{'total_records': rows.length},
      };
    }
    return <String, dynamic>{
      'data': const <Json>[],
      'pagination': <String, dynamic>{'total_records': 0},
    };
  }
}

Json _system({required String id, required bool retired}) => <String, dynamic>{
      'id': id,
      'code': 'GST',
      'name': 'Goods and Services Tax',
      'display_name': 'Goods and Services Tax',
      'status': 'ACTIVE',
      'is_deleted': retired,
      'effective_from': '2026-04-01',
      'effective_to': '2027-03-31',
      'version': 1,
    };

Future<void> _open(WidgetTester tester, _Api api, List<String> codes) async {
  tester.view.physicalSize = const Size(1600, 1100);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: TaxManagementPage(
        api: api,
        permissions: _permissions(codes),
        hasActiveFirm: true,
        section: TaxManagementSection.systems,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

const List<String> _manager = <String>[
  'TAX_VIEW',
  'TAX_CREATE',
  'TAX_UPDATE',
  'TAX_DELETE',
  // Its own permission server-side, so its own permission here.
  'TAX_RESTORE',
];

void main() {
  testWidgets('retired rows are hidden until they are asked for',
      (tester) async {
    final _Api api = _Api(rows: <Json>[_system(id: 's-1', retired: false)]);
    await _open(tester, api, _manager);

    // A list of live tax systems is what somebody configuring tax wants, so
    // the flag is off by default and the query says so by its absence.
    expect(
      api.queries.every((q) => !q.containsKey('include_deleted')),
      isTrue,
    );

    await tester.tap(find.widgetWithText(FilterChip, 'Show retired'));
    await tester.pumpAndSettle();

    expect(
      api.queries.any((q) => q['include_deleted'] == 'true'),
      isTrue,
    );
  });

  testWidgets('a retired system can be brought back', (tester) async {
    final _Api api = _Api(rows: <Json>[_system(id: 's-1', retired: true)]);
    await _open(tester, api, _manager);

    await tester.tap(find.text('GST'), warnIfMissed: false);
    await tester.pumpAndSettle();

    // The restore lives on the row: it applies to one retired record, and
    // `ToolbarAction` is a framework enum shared by every workspace.
    final Finder row = find.text('GST');
    await tester.tapAt(tester.getCenter(row), buttons: kSecondaryButton);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Restore'));
    await tester.pumpAndSettle();

    expect(api.posted.single, contains('/systems/s-1/restore'));
  });

  testWidgets('a live row carries no restore, which would do nothing to it',
      (tester) async {
    final _Api api = _Api(rows: <Json>[_system(id: 's-1', retired: false)]);
    await _open(tester, api, _manager);

    final Finder row = find.text('GST');
    await tester.tapAt(tester.getCenter(row), buttons: kSecondaryButton);
    await tester.pumpAndSettle();

    expect(find.text('Restore'), findsNothing);
  });

  testWidgets('reading the framework is not authority to bring one back',
      (tester) async {
    final _Api api = _Api(rows: <Json>[_system(id: 's-1', retired: true)]);
    await _open(tester, api, const <String>['TAX_VIEW', 'TAX_DELETE']);

    final Finder row = find.text('GST');
    await tester.tapAt(tester.getCenter(row), buttons: kSecondaryButton);
    await tester.pumpAndSettle();

    expect(find.text('Restore'), findsNothing);
  });
}
