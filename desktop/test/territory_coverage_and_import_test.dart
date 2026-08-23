// Two capabilities that were built and had no way to reach them.
//
// `GET /coverage/salesmen` has answered "who carries how much" since the
// module was written and nothing called it. `POST /import` has accepted a
// hierarchy CSV just as long, while the toolbar's Import action did nothing at
// all — and until it was made one transaction, wiring a button to it would
// have shipped a file that writes half of itself.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/firm_member.dart';
import 'package:agency_desktop/models/sales_territory.dart';
import 'package:agency_desktop/ui/sales/territory_coverage_page.dart';
import 'package:agency_desktop/ui/sales/territory_import_dialog.dart';
import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions() => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': <String>['TERRITORY_VIEW', 'TERRITORY_IMPORT'],
  }));

class _CoverageApi extends ApiClient {
  _CoverageApi({this.rows = const <Json>[], this.importError})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Json> rows;
  final String? importError;
  List<int>? importedBytes;

  @override
  Future<List<TerritoryCoverageRecord>> territoryCoverage() async =>
      <TerritoryCoverageRecord>[
        for (final Json row in rows) TerritoryCoverageRecord.fromJson(row),
      ];

  @override
  Future<List<FirmMember>>
      firmMembers() async => <FirmMember>[
            FirmMember.fromJson(<String, dynamic>{
              'user_id': 'user-1',
              'full_name': 'Ravi Kumar',
              'email': 'ravi@agency.local',
            }),
          ];

  @override
  Future<List<SalesTerritory>> importTerritories({
    required String fileName,
    required List<int> bytes,
  }) async {
    if (importError != null) throw ApiException(importError!);
    importedBytes = bytes;
    return const <SalesTerritory>[];
  }
}

void main() {
  testWidgets('coverage names the person and flags who carries nothing',
      (tester) async {
    tester.view.physicalSize = const Size(1600, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final api = _CoverageApi(rows: <Json>[
      <String, dynamic>{
        'user_id': 'user-1',
        'assigned_territories': 2,
        'assigned_routes': 0,
        'customer_count': 0,
        'coverage_percent': 0.0,
      },
    ]);

    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: TerritoryCoveragePage(api: api, permissions: _permissions()),
      ),
    ));
    await tester.pumpAndSettle();

    // The id is resolved through the candidate list — `users` lives only in
    // the platform store, so the coverage rows carry ids and nothing else.
    expect(find.text('Ravi Kumar'), findsOneWidget);
    expect(find.textContaining('carry no route at all'), findsOneWidget);
  });

  testWidgets('a refused import says nothing was written', (tester) async {
    tester.view.physicalSize = const Size(1600, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final api = _CoverageApi(importError: 'Unknown hierarchy level: Zone.');

    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: TerritoryImportDialog(
          api: api,
          pickFileOverride: () async => XFile.fromData(
            utf8.encode('Code,Name,Level\nRT01,North,Zone\n'),
            name: 'routes.csv',
            path: 'routes.csv',
          ),
        ),
      ),
    ));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Choose file'));
    await tester.pumpAndSettle();
    expect(find.textContaining('routes.csv'), findsOneWidget);

    await tester.tap(find.widgetWithText(FilledButton, 'Import'));
    await tester.pumpAndSettle();

    // The whole file is one transaction server-side, so this sentence is true
    // rather than reassuring.
    expect(find.textContaining('Nothing was imported.'), findsOneWidget);
  });

  testWidgets('a clean import sends the file', (tester) async {
    tester.view.physicalSize = const Size(1600, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final api = _CoverageApi();

    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: TerritoryImportDialog(
          api: api,
          pickFileOverride: () async => XFile.fromData(
            utf8.encode('Code,Name,Level\nRT01,North,Route\n'),
            name: 'routes.csv',
            path: 'routes.csv',
          ),
        ),
      ),
    ));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Choose file'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Import'));
    await tester.pumpAndSettle();

    expect(api.importedBytes, isNotNull);
    expect(find.textContaining('imported'), findsWidgets);
  });
}
