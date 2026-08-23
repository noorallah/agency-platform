// A product's packaging hierarchy, and what a scanned code turns out to be.
//
// The four packaging-level endpoints have existed since the UOM module was
// written and nothing in the desktop called them, so no firm could record a
// level at all. Worse, nothing in the *backend* read the barcodes those levels
// carry either — the framework doc's claim that they let "a scanner read a
// carton label and know it holds 120 pieces" had no implementation behind it.
//
// So this screen is only worth having alongside the lookup, and the tests are
// written that way: the hierarchy can be recorded, and a code recorded here
// resolves to a product and a quantity.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/uom/packaging_levels_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions({List<String> perms = const [
  'UOM_VIEW',
  'PACKAGING_MANAGE',
]}) =>
    PermissionService()
      ..applyAccessToken(_accessToken({
        'roles': <String>['user'],
        'permissions': perms,
      }));

class _PackagingApi extends ApiClient {
  _PackagingApi({this.levels = const [], this.lookup})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  /// What `GET .../packaging-levels` answers with.
  final List<Json> levels;

  /// What the lookup answers with, or null to answer as the server does when
  /// nothing carries the code.
  final Json? lookup;

  final List<String> requested = <String>[];
  Json? created;
  String? deleted;

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
    requested.add('$method $path');
    if (path.contains('barcode-lookup')) {
      if (lookup == null) {
        throw ApiException(
          'Nothing in this firm carries the code 8901234567906.',
          statusCode: 404,
        );
      }
      return <String, dynamic>{'data': lookup};
    }
    if (path.contains('packaging-levels')) {
      if (method == 'POST') {
        created = body;
        return <String, dynamic>{'data': _level()};
      }
      if (method == 'DELETE') {
        deleted = path;
        return <String, dynamic>{'data': null};
      }
      return <String, dynamic>{'data': levels};
    }
    if (path.contains('/products')) {
      return <String, dynamic>{
        'data': <Json>[
          <String, dynamic>{
            'id': 'p-1',
            'code': 'EXT5M',
            'name': 'Extension Board 5 Meter',
            'status': 'ACTIVE',
          },
        ],
        'pagination': <String, dynamic>{'total_records': 1},
      };
    }
    if (path.contains('/uoms')) {
      return <String, dynamic>{
        'data': <Json>[
          <String, dynamic>{
            'id': 'u-1',
            'code': 'PCS',
            'name': 'Pieces',
            'status': 'ACTIVE',
          },
        ],
      };
    }
    return <String, dynamic>{'data': const <Json>[]};
  }
}

Json _level() => <String, dynamic>{
      'id': 'lvl-1',
      'product_id': 'p-1',
      'level_name': 'CARTON',
      'conversion_to_base_factor': '120',
      'uom_id': 'u-1',
      'barcode': '8901234567906',
      'status': 'ACTIVE',
      'version': 3,
    };

Future<void> _pump(WidgetTester tester, _PackagingApi api,
    {PermissionService? permissions}) async {
  tester.view.physicalSize = const Size(1700, 1200);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: PackagingLevelsPage(
        api: api,
        permissions: permissions ?? _permissions(),
        hasActiveFirm: true,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

Future<void> _chooseProduct(WidgetTester tester) async {
  await tester.tap(find.byType(DropdownButtonFormField<String>).first);
  await tester.pumpAndSettle();
  await tester.tap(find.text('EXT5M — Extension Board 5 Meter').last);
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('nothing is read until a product is chosen', (tester) async {
    // Levels are per product. A firm with four thousand products has no use
    // for one grid of all their cartons, so the screen asks first.
    final _PackagingApi api = _PackagingApi();
    await _pump(tester, api);

    expect(find.text('Choose a product'), findsOneWidget);
    expect(
      api.requested.where((call) => call.contains('packaging-levels')),
      isEmpty,
    );
  });

  testWidgets("a chosen product's hierarchy is read and shown", (tester) async {
    final _PackagingApi api = _PackagingApi(levels: <Json>[_level()]);
    await _pump(tester, api);

    await _chooseProduct(tester);

    expect(
      api.requested,
      contains('GET /api/v1/uom-framework/products/p-1/packaging-levels'),
    );
    expect(find.text('CARTON'), findsOneWidget);
    expect(find.text('120'), findsOneWidget);
    expect(find.text('8901234567906'), findsOneWidget);
  });

  testWidgets('a level is added with the codes printed on it', (tester) async {
    final _PackagingApi api = _PackagingApi();
    await _pump(tester, api);
    await _chooseProduct(tester);

    await tester.tap(find.widgetWithText(FilledButton, 'Add level'));
    await tester.pumpAndSettle();
    await tester.enterText(
        find.widgetWithText(TextFormField, 'Level name'), 'CARTON');
    await tester.enterText(
        find.widgetWithText(TextFormField, 'Base units'), '120');
    await tester.enterText(
        find.widgetWithText(TextFormField, 'Barcode'), '8901234567906');
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    expect(api.created!['level_name'], 'CARTON');
    expect(api.created!['conversion_to_base_factor'], '120');
    expect(api.created!['barcode'], '8901234567906');
    // Cleared codes are sent as null rather than omitted, so emptying one
    // clears it rather than leaving the old value standing.
    expect(api.created!.containsKey('gtin'), isTrue);
    expect(api.created!['gtin'], isNull);
  });

  testWidgets('a level holding nothing is refused', (tester) async {
    // A level that holds no base units cannot be scanned into a quantity,
    // which is the only reason to record one.
    final _PackagingApi api = _PackagingApi();
    await _pump(tester, api);
    await _chooseProduct(tester);

    await tester.tap(find.widgetWithText(FilledButton, 'Add level'));
    await tester.pumpAndSettle();
    await tester.enterText(
        find.widgetWithText(TextFormField, 'Level name'), 'CARTON');
    await tester.enterText(
        find.widgetWithText(TextFormField, 'Base units'), '0');
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    expect(find.text('Must be more than nothing.'), findsOneWidget);
    expect(api.created, isNull);
  });

  testWidgets('a scanned code says what it is and how much', (tester) async {
    final _PackagingApi api = _PackagingApi(lookup: <String, dynamic>{
      'code': '8901234567906',
      'product_id': 'p-1',
      'product_code': 'EXT5M',
      'product_name': 'Extension Board 5 Meter',
      'packaging_level_id': 'lvl-1',
      'level_name': 'CARTON',
      'base_quantity': '120',
      'matched_field': 'barcode',
    });
    await _pump(tester, api);

    await tester.enterText(
      find.widgetWithText(TextField, 'Scan or type a code'),
      '8901234567906',
    );
    await tester.tap(find.widgetWithText(FilledButton, 'Look up'));
    await tester.pumpAndSettle();

    expect(
      find.textContaining('one scan is 120 base units'),
      findsOneWidget,
    );
    expect(find.textContaining('EXT5M'), findsWidgets);
  });

  testWidgets("a code nobody carries shows the server's own sentence",
      (tester) async {
    // It names the code, or says how many things carry it -- more useful than
    // anything the client could invent, and the next thing anybody does is
    // re-scan.
    final _PackagingApi api = _PackagingApi();
    await _pump(tester, api);

    await tester.enterText(
      find.widgetWithText(TextField, 'Scan or type a code'),
      '8901234567906',
    );
    await tester.tap(find.widgetWithText(FilledButton, 'Look up'));
    await tester.pumpAndSettle();

    expect(
      find.text('Nothing in this firm carries the code 8901234567906.'),
      findsOneWidget,
    );
  });

  testWidgets('without PACKAGING_MANAGE nothing can be added', (tester) async {
    final _PackagingApi api = _PackagingApi(levels: <Json>[_level()]);
    await _pump(
      tester,
      api,
      permissions: _permissions(perms: const ['UOM_VIEW']),
    );
    await _chooseProduct(tester);

    expect(find.widgetWithText(FilledButton, 'Add level'), findsNothing);
    // The lookup is still there: reading what a code is needs no authority to
    // change anything.
    expect(find.widgetWithText(FilledButton, 'Look up'), findsOneWidget);
  });
}
