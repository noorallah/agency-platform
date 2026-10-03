// Export to Tally (MSG-5): the export sends the chosen dates and saves the
// bytes, the mapping table renders, and Save sends the edited rows with the
// declared keys.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart' show Json;
import 'package:agency_desktop/ui/finance/tally_export_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions() => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': <String>['LEDGER_VIEW', 'JOURNAL_POST'],
  }));

class _Api extends ApiClient {
  _Api()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Map<String, String>?> exportQueries = [];
  Json? saved;

  @override
  Future<List<int>> downloadBytes(
    String path, {
    Map<String, String>? query,
    String method = 'GET',
    Json? body,
    bool retrying = false,
  }) async {
    expect(path, '/api/v1/finance/tally/export');
    exportQueries.add(query);
    return utf8.encode('<ENVELOPE/>');
  }

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
    if (method == 'PUT' && path == '/api/v1/finance/tally/mappings') {
      saved = body;
      return <String, dynamic>{'data': const <Json>[]};
    }
    if (path == '/api/v1/finance/tally/mappings') {
      return <String, dynamic>{
        'data': [
          {
            'ledger_account_id': 'a-1',
            'account_code': '1100',
            'account_name': 'Cash in hand',
            'tally_name': 'Cash',
            'tally_parent': 'Cash-in-Hand',
            'mapped': true,
          },
          {
            'ledger_account_id': 'a-2',
            'account_code': '4000',
            'account_name': 'Sales',
            'tally_name': 'Sales',
            'tally_parent': 'Sales Accounts',
            'mapped': false,
          },
          {
            'ledger_account_id': 'a-3',
            'account_code': '5000',
            'account_name': 'Rent',
            'tally_name': 'Rent',
            'tally_parent': 'Indirect Expenses',
            'mapped': false,
          },
        ],
      };
    }
    return <String, dynamic>{'data': const <Json>[]};
  }
}

DesktopPreferencesService _preferences() => DesktopPreferencesService(
      directory: Directory.systemTemp.createTempSync('tally-export'),
    );

Future<void> _pump(
  WidgetTester tester,
  _Api api, {
  Future<void> Function(String, List<int>)? save,
}) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    builder: (context, child) => Phase2Scope(child: child!),
    home: Scaffold(
      body: TallyExportPage(
        api: api,
        preferences: _preferences(),
        permissions: _permissions(),
        hasActiveFirm: true,
        saveBytesOverride: save,
        today: DateTime(2026, 10, 3),
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('export sends the last full month and saves the bytes',
      (tester) async {
    final _Api api = _Api();
    String? name;
    List<int>? bytes;
    await _pump(tester, api, save: (n, b) async {
      name = n;
      bytes = b;
    });
    expect(find.text('From 2026-09-01'), findsOneWidget);
    expect(find.text('To 2026-09-30'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('tally-export')));
    await tester.pumpAndSettle();

    expect(api.exportQueries.single,
        {'from_date': '2026-09-01', 'to_date': '2026-09-30'});
    expect(name, 'tally-20260901-20260930.xml');
    expect(utf8.decode(bytes!), '<ENVELOPE/>');
    expect(find.textContaining('The Tally file was saved'), findsOneWidget);
  });

  testWidgets('the mapping table lists every account with its Tally names',
      (tester) async {
    await _pump(tester, _Api());
    expect(find.text('Ledger names in Tally'), findsOneWidget);
    expect(find.text('Cash in hand'), findsOneWidget);
    expect(find.text('1100'), findsOneWidget);
    expect(find.widgetWithText(TextField, 'Cash'), findsOneWidget);
    expect(find.widgetWithText(TextField, 'Sales Accounts'), findsOneWidget);
    expect(find.textContaining('Gateway > Import > Masters'), findsOneWidget);
  });

  testWidgets('save sends mapped and edited rows with the declared keys',
      (tester) async {
    final _Api api = _Api();
    await _pump(tester, api);
    await tester.enterText(
        find.byKey(const ValueKey('tally-name-a-3')), 'Office Rent');
    await tester.tap(find.byKey(const ValueKey('tally-save')));
    await tester.pumpAndSettle();

    final List<dynamic> sent = api.saved!['mappings'] as List<dynamic>;
    expect(sent, hasLength(2));
    expect(sent[0], {
      'ledger_account_id': 'a-1',
      'tally_name': 'Cash',
      'tally_parent': 'Cash-in-Hand',
    });
    expect(sent[1], {
      'ledger_account_id': 'a-3',
      'tally_name': 'Office Rent',
      'tally_parent': 'Indirect Expenses',
    });
  });
}
