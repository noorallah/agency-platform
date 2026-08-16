// The shared geography ladder, which had six endpoints and no screen at all.
//
// Country > state > district > city > postal code > locality is what every
// address, branch, warehouse and route profile hangs off, and the only places
// that existed were the ones a seeder made — the API could list and create and
// nothing else.
//
// The behaviour worth protecting here is the permission split. Geography is
// reference data shared by every firm, so writing it is platform-admin only,
// while any firm user has to be able to *read* it in order to pick a city for
// a route. A screen that hid itself from firm users would take that away; one
// that offered them buttons would be lying about what the server will accept.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/geography.dart';
import 'package:agency_desktop/ui/sales/geography_master_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions({bool platformAdmin = false}) =>
    PermissionService()
      ..applyAccessToken(_accessToken({
        'roles': <String>[if (platformAdmin) 'platform_admin' else 'user'],
        'permissions': <String>['TERRITORY_VIEW'],
      }));

class _GeoApi extends ApiClient {
  _GeoApi({this.deleteError})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  /// When set, the delete call throws it — the in-use refusal.
  final String? deleteError;

  final List<String> requested = <String>[];
  Json? created;
  Json? updated;
  String? deleted;

  @override
  Future<List<GeoPlaceRecord>> geoPlaces(
    GeoLevel level, {
    String parentId = '',
  }) async {
    requested.add('${level.path}:$parentId');
    return switch (level) {
      GeoLevel.country => <GeoPlaceRecord>[
          GeoPlaceRecord.fromJson(level, <String, dynamic>{
            'id': 'c-in',
            'code': 'IN',
            'name': 'India',
            'iso2': 'IN',
            'iso3': 'IND',
            'phone_code': '91',
            'is_active': true,
          }),
        ],
      GeoLevel.state => <GeoPlaceRecord>[
          GeoPlaceRecord.fromJson(level, <String, dynamic>{
            'id': 's-tn',
            'country_id': 'c-in',
            'code': 'TN',
            'name': 'Tamil Nadu',
            'is_active': true,
          }),
        ],
      _ => const <GeoPlaceRecord>[],
    };
  }

  @override
  Future<GeoPlaceRecord> createGeoPlace(GeoLevel level, Json body) async {
    created = <String, dynamic>{'level': level.path, ...body};
    return GeoPlaceRecord.fromJson(level, <String, dynamic>{
      'id': 'new',
      ...body,
    });
  }

  @override
  Future<GeoPlaceRecord> updateGeoPlace(
    GeoLevel level,
    String id,
    Json body,
  ) async {
    updated = <String, dynamic>{'level': level.path, 'id': id, ...body};
    return GeoPlaceRecord.fromJson(level, <String, dynamic>{'id': id, ...body});
  }

  @override
  Future<void> deleteGeoPlace(GeoLevel level, String id) async {
    if (deleteError != null) throw ApiException(deleteError!);
    deleted = '${level.path}/$id';
  }
}

Future<void> _pump(
  WidgetTester tester,
  _GeoApi api, {
  bool platformAdmin = false,
}) async {
  tester.view.physicalSize = const Size(1600, 1200);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: GeographyMasterPage(
        api: api,
        permissions: _permissions(platformAdmin: platformAdmin),
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('the browser opens on countries', (tester) async {
    final api = _GeoApi();
    await _pump(tester, api);

    expect(find.text('India'), findsOneWidget);
    expect(api.requested.single, 'countries:');
  });

  testWidgets('opening a country asks for that country\'s states',
      (tester) async {
    final api = _GeoApi();
    await _pump(tester, api, platformAdmin: true);

    // The grid opens a row on double-click, which is how you walk down the
    // ladder.
    final Finder row = find.text('India').first;
    await tester.tap(row);
    await tester.pump(const Duration(milliseconds: 40));
    await tester.tap(row);
    await tester.pumpAndSettle();

    // The parent id travels with the request: a state list is only meaningful
    // under one country.
    expect(api.requested.last, 'states:c-in');
    expect(find.text('Tamil Nadu'), findsOneWidget);
  });

  testWidgets('a firm user sees the places and none of the buttons',
      (tester) async {
    final api = _GeoApi();
    await _pump(tester, api);

    // Geography is shared reference data — a firm admin reads it to pick a
    // city for a route, and a platform administrator maintains it.
    expect(find.text('India'), findsOneWidget);
    expect(find.textContaining('platform'), findsWidgets);
    expect(find.byTooltip('New'), findsNothing);
  });

  testWidgets('a platform administrator can add a country', (tester) async {
    final api = _GeoApi();
    await _pump(tester, api, platformAdmin: true);

    await tester.tap(find.byTooltip('New'));
    await tester.pumpAndSettle();
    await tester.enterText(find.widgetWithText(TextFormField, 'Code'), 'lk');
    await tester.enterText(
      find.widgetWithText(TextFormField, 'Name'),
      'Sri Lanka',
    );
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();

    expect(api.created, isNotNull);
    expect(api.created!['level'], 'countries');
    // Upper-cased client-side, matching what the API stores.
    expect(api.created!['code'], 'LK');
    expect(api.created!['name'], 'Sri Lanka');
  });

  testWidgets('a place still in use reports why it cannot be deleted',
      (tester) async {
    final api = _GeoApi(
      deleteError: '3 record(s) still use this country. '
          'Reassign them before deleting it.',
    );
    await _pump(tester, api, platformAdmin: true);

    await tester.tap(find.text('India').first);
    // The row tap schedules the selection through an ink response, so the
    // toolbar only re-enables on the next frame.
    await tester.pump(const Duration(milliseconds: 400));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Delete'));
    await tester.pumpAndSettle();
    expect(find.text('Delete India?'), findsOneWidget);
    await tester.tap(find.widgetWithText(FilledButton, 'Delete').last);
    await tester.pumpAndSettle();

    expect(find.textContaining('still use this country'), findsOneWidget);
  });
}
