// Decision B6: the India Post places pack ships with the server, and a
// platform administrator loads it from the geography screen.
//
// Loading writes reference data every firm reads, so the action is offered to
// a platform administrator only, and a refusal stays inside the dialog.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/geography.dart';
import 'package:agency_desktop/ui/sales/geography_master_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions({required bool platformAdmin}) =>
    PermissionService()
      ..applyAccessToken(_accessToken({
        'roles': const <String>['user'],
        'platform_admin': platformAdmin,
        'permissions': <String>['TERRITORY_VIEW'],
      }));

class _PackApi extends ApiClient {
  _PackApi({this.refusal})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  String? refusal;
  List<String>? loaded;

  @override
  Future<List<GeoPlaceRecord>> geoPlaces(
    GeoLevel level, {
    String parentId = '',
  }) async =>
      const <GeoPlaceRecord>[];

  @override
  Future<List<PlacesPackState>> placesPack() async => <PlacesPackState>[
        PlacesPackState.fromJson(<String, dynamic>{
          'code': 'TN',
          'name': 'Tamil Nadu',
          'available': true,
          'post_offices': 12000,
          'postal_codes': 2500,
          'districts': 38,
          'districts_held': 5,
          'default': true,
        }),
        PlacesPackState.fromJson(<String, dynamic>{
          'code': 'MH',
          'name': 'Maharashtra',
          'available': true,
          'post_offices': 100,
          'postal_codes': 90,
          'districts': 36,
          'districts_held': 0,
          'default': false,
        }),
        PlacesPackState.fromJson(<String, dynamic>{
          'code': 'GA',
          'name': 'Goa',
          'available': false,
          'post_offices': 10,
          'postal_codes': 9,
          'districts': 2,
          'districts_held': 0,
          'default': false,
        }),
      ];

  @override
  Future<List<PlacesPackResult>> loadPlacesPack(List<String> states) async {
    final String? message = refusal;
    if (message != null) {
      refusal = null;
      throw ApiException(message, statusCode: 403);
    }
    loaded = states;
    return <PlacesPackResult>[
      PlacesPackResult.fromJson(<String, dynamic>{
        'code': 'TN',
        'name': 'Tamil Nadu',
        'districts': 33,
        'cities': 40,
        'postal_codes': 2400,
        'localities': 11000,
        'skipped': 3,
        'note': 'Some rows had no district.',
      }),
    ];
  }
}

Future<void> _pump(
  WidgetTester tester,
  _PackApi api, {
  required bool platformAdmin,
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

Future<void> _open(WidgetTester tester) async {
  await tester.tap(find.text('Load places from India Post...'));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('the states are listed with the south pre-ticked',
      (tester) async {
    await _pump(tester, _PackApi(), platformAdmin: true);
    await _open(tester);

    expect(find.text('2500 PIN codes, 12000 post offices, 5 districts '
        'already held'), findsOneWidget);
    expect(find.text('not in this store'), findsOneWidget);
    expect(find.textContaining('data.gov.in'), findsOneWidget);

    CheckboxListTile tile(String code) => tester.widget<CheckboxListTile>(
        find.byKey(ValueKey<String>('places-pack-state-$code')));
    expect(tile('TN').value, isTrue);
    expect(tile('MH').value, isFalse);
    expect(tile('GA').onChanged, isNull);
  });

  testWidgets('Load sends the ticked codes and then shows the results',
      (tester) async {
    final api = _PackApi();
    await _pump(tester, api, platformAdmin: true);
    await _open(tester);

    await tester.tap(find.byKey(const ValueKey<String>('places-pack-state-MH')));
    await tester.pump();
    await tester.tap(find.text('Load'));
    await tester.pumpAndSettle();

    expect(api.loaded, <String>['TN', 'MH']);
    expect(find.textContaining('Added 33 districts, 40 towns'), findsOneWidget);
    expect(find.text('Some rows had no district.'), findsOneWidget);
    expect(find.text('Close'), findsOneWidget);
  });

  testWidgets('a refusal stays inside the dialog', (tester) async {
    final api = _PackApi(refusal: 'Only a platform administrator may load.');
    await _pump(tester, api, platformAdmin: true);
    await _open(tester);

    await tester.tap(find.text('Load'));
    await tester.pumpAndSettle();

    expect(find.text('Only a platform administrator may load.'),
        findsOneWidget);
    expect(find.text('Load places from India Post'), findsOneWidget);
    expect(api.loaded, isNull);
    // Still pickable, so the user can try again.
    await tester.tap(find.text('Load'));
    await tester.pumpAndSettle();
    expect(api.loaded, <String>['TN']);
  });

  testWidgets('a firm user is not offered the load', (tester) async {
    await _pump(tester, _PackApi(), platformAdmin: false);

    expect(find.text('Load places from India Post...'), findsNothing);
  });
}
