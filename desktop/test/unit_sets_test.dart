// Backlog 89, unit sets: a named template of units that fills a new product
// in one choice. The shared catalogue is read-only to a firm; the firm's own
// sets are edited like any master. The same tab replaces Industry Templates.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/uom_packaging.dart';
import 'package:agency_desktop/ui/desktop_shell.dart';
import 'package:agency_desktop/ui/resource_management_page.dart';
import 'package:agency_desktop/ui/workspace/module_catalog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

class _Write {
  _Write(this.method, this.path, this.body);

  final String method;
  final String path;
  final Json body;
}

class _SetsApi extends ApiClient {
  _SetsApi({this.refuseWith})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final String? refuseWith;
  final List<_Write> writes = <_Write>[];

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
    if (method != 'GET') {
      writes.add(_Write(method, path,
          Map<String, dynamic>.from(body ?? const <String, dynamic>{})));
      if (refuseWith != null && method == 'POST') {
        throw ApiException(refuseWith!, statusCode: 422);
      }
      return {
        'data': <String, dynamic>{...?body, 'id': 'new-1'},
      };
    }
    if (path.endsWith('/uom-framework/unit-sets')) {
      return {
        'data': [
          {
            'id': 'us-shared',
            'firm_id': null,
            'name': 'Pharma box of strips',
            'base_uom_id': 'uom-strip',
            'inventory_uom_id': 'uom-strip',
            'purchase_uom_id': 'uom-box',
            'sales_uom_id': 'uom-strip',
            'allow_decimal': false,
            'conversion_factor': '10.000000',
            'is_active': true,
            'goods_type_ids': ['gt-med'],
            'version': 1,
          },
          {
            'id': 'us-own',
            'firm_id': 'firm-1',
            'name': 'Loose pieces',
            'base_uom_id': 'uom-pc',
            'allow_decimal': true,
            'conversion_factor': null,
            'is_active': true,
            'goods_type_ids': <String>[],
            'version': 3,
          },
        ],
      };
    }
    if (path.endsWith('/uom-framework/uoms')) {
      return {
        'data': [
          for (final (String id, String name) in const [
            ('uom-strip', 'Strip'),
            ('uom-box', 'Box'),
            ('uom-pc', 'Piece'),
          ])
            {
              'id': id,
              'code': name.toUpperCase(),
              'name': name,
              'symbol': name.toLowerCase(),
              'dimension': 'COUNT',
              'status': 'ACTIVE',
              'is_decimal_allowed': true,
            },
        ],
      };
    }
    if (path.endsWith('/products/goods-types')) {
      return {
        'data': [
          {
            'id': 'gt-med',
            'firm_id': null,
            'code': 'MEDICINE',
            'name': 'Medicine',
            'track_batch': true,
            'is_active': true,
            'in_use': true,
            'version': 1,
          },
        ],
      };
    }
    return {'data': const <dynamic>[], 'pagination': {'total_records': 0}};
  }
}

PermissionService _permissions(List<String> codes) {
  final String claims = base64Url
      .encode(utf8.encode(jsonEncode(<String, dynamic>{
        'roles': <String>['user'],
        'permissions': codes,
      })))
      .replaceAll('=', '');
  return PermissionService()..applyAccessToken('header.$claims.sig');
}

Future<void> _open(
  WidgetTester tester,
  _SetsApi api,
  PermissionService permissions, {
  Size size = const Size(1600, 900),
}) async {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = size;
  addTearDown(() {
    tester.view.resetPhysicalSize();
    tester.view.resetDevicePixelRatio();
  });
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: ResourceManagementPage<UnitSet>(
        api: api,
        definition: unitSetDefinition(api, permissions),
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

Future<void> _fillAndSave(WidgetTester tester, {String name = 'Cartons'}) async {
  await tester.tap(find.widgetWithText(FilledButton, 'New').hitTestable());
  await tester.pumpAndSettle();
  await tester.enterText(find.byType(TextFormField).at(0), name);
  await tester.pumpAndSettle();
}

Future<void> _saveDialog(WidgetTester tester) async {
  await tester.ensureVisible(find.text('Save & Close').hitTestable());
  await tester.tap(find.text('Save & Close').hitTestable());
  await tester.pumpAndSettle();
}

void main() {
  const List<String> manage = ['UOM_VIEW', 'UOM_MANAGE'];

  test('the tab replaces Industry Templates in both menus', () {
    final tabs = ModuleCatalog.byId(AppModule.administration).tabs;
    expect(tabs.any((tab) => tab.id == 'unit-sets'), isTrue);
    expect(tabs.any((tab) => tab.id == 'industry-templates'), isFalse);
    expect(tabs.firstWhere((tab) => tab.id == 'unit-sets').label, 'Unit Sets');
    final String menu = File('lib/phase2/menu_layout.dart').readAsStringSync();
    expect(menu, contains("'unit-sets', 'Unit Sets'"));
    expect(menu, isNot(contains('industry-templates')));
  });

  testWidgets('the list shows the columns, conversion and shared or own',
      (tester) async {
    await _open(tester, _SetsApi(), _permissions(['UOM_VIEW']));

    for (final String heading in [
      'Name',
      'Stock unit',
      'Purchase unit',
      'Sales unit',
      'Conversion',
      'Goods types',
      'Active',
    ]) {
      expect(find.text(heading), findsWidgets);
    }
    expect(find.text('Pharma box of strips'), findsOneWidget);
    expect(find.text('1 Box = 10 Strip'), findsOneWidget);
    expect(find.text('none'), findsOneWidget);
    expect(find.text('Medicine'), findsOneWidget);
    expect(find.text('All goods'), findsOneWidget);
    expect(find.text('Shared'), findsOneWidget);
    expect(find.text('Own'), findsOneWidget);
  });

  testWidgets('a shared row cannot be edited or deleted and says why',
      (tester) async {
    final _SetsApi api = _SetsApi();
    final definition = unitSetDefinition(api, _permissions(manage));
    final List<UnitSet> rows = await api.unitSets();
    final UnitSet shared = rows.firstWhere((set) => set.isShared);
    final UnitSet own = rows.firstWhere((set) => !set.isShared);
    expect(definition.canEdit!(shared), isFalse);
    expect(definition.editRefusal!(shared), contains('shared unit set'));
    expect(definition.canEdit!(own), isTrue);
    expect(definition.editRefusal!(own), isNull);
  });

  testWidgets('adding a set sends exactly the declared keys', (tester) async {
    final _SetsApi api = _SetsApi();
    await _open(tester, api, _permissions(manage));
    await _fillAndSave(tester);

    // Units are chosen as chips: the base and purchase units differ from the
    // stock unit, so the conversion box appears.
    Future<void> chip(String section, String unit) async {
      final Finder chips = find.text('$unit · ${unit.toUpperCase()}');
      await tester.ensureVisible(chips.at(section == 'base' ? 0 : 2));
      await tester.tap(chips.at(section == 'base' ? 0 : 2));
      await tester.pumpAndSettle();
    }

    await chip('base', 'Strip');
    await chip('purchase', 'Box');
    final Finder factor = find.widgetWithText(
        TextFormField, 'Conversion: 1 purchase unit = ? stock units');
    expect(factor, findsOneWidget);
    await tester.enterText(factor, '10');
    await tester.pumpAndSettle();
    await _saveDialog(tester);

    expect(api.writes, hasLength(1));
    expect(api.writes.single.method, 'POST');
    expect(api.writes.single.path, '/api/v1/uom-framework/unit-sets');
    expect(api.writes.single.body, {
      'name': 'Cartons',
      'description': null,
      'base_uom_id': 'uom-strip',
      'inventory_uom_id': null,
      'purchase_uom_id': 'uom-box',
      'sales_uom_id': null,
      'minimum_sales_uom_id': null,
      'default_receiving_uom_id': null,
      'default_dispatch_uom_id': null,
      'allow_decimal': true,
      'conversion_factor': '10',
      'goods_type_ids': <String>[],
      'is_active': true,
    });
  });

  testWidgets('a set with no base unit is refused before anything is sent',
      (tester) async {
    final _SetsApi api = _SetsApi();
    await _open(tester, api, _permissions(manage));
    await _fillAndSave(tester);
    await _saveDialog(tester);
    expect(api.writes, isEmpty);
    expect(find.textContaining('Choose the base unit'), findsWidgets);
  });

  testWidgets('a refused save keeps the dialog open with the message',
      (tester) async {
    final _SetsApi api =
        _SetsApi(refuseWith: 'A unit set with this name already exists.');
    await _open(tester, api, _permissions(manage));
    await _fillAndSave(tester, name: 'Loose pieces');
    final Finder strip = find.text('Strip · STRIP').first;
    await tester.ensureVisible(strip);
    await tester.tap(strip);
    await tester.pumpAndSettle();
    await _saveDialog(tester);

    expect(find.textContaining('already exists'), findsWidgets);
    expect(find.text('Save & Close'), findsOneWidget);
    expect(api.writes, hasLength(1));
  });

  testWidgets('without UOM_MANAGE no write action is offered', (tester) async {
    await _open(tester, _SetsApi(), _permissions(['UOM_VIEW']));
    expect(find.widgetWithText(FilledButton, 'New'), findsNothing);
  });

  testWidgets('the screen fits the 800x600 window', (tester) async {
    await _open(tester, _SetsApi(), _permissions(manage),
        size: const Size(800, 600));
    expect(tester.takeException(), isNull);
  });
}
