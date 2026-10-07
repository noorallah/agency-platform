// Backlog 89: a goods type says how a line of goods is tracked. The shared
// catalogue is read-only to a firm, which takes a type into use and sets its
// own defaults; the firm's own types are edited like any master.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/product.dart';
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

class _TypesApi extends ApiClient {
  _TypesApi({this.refuseWith})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  /// When set, every create is refused with this message.
  final String? refuseWith;

  final List<_Write> writes = <_Write>[];
  int goodsTypeReads = 0;

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
    if (path.endsWith('/products/goods-types')) {
      goodsTypeReads++;
      return {
        'data': [
          {
            'id': 'gt-shared',
            'firm_id': null,
            'code': 'MEDICINE',
            'name': 'Medicine',
            'track_batch': true,
            'track_expiry': true,
            'track_manufacturing_date': true,
            'is_active': true,
            'in_use': false,
            'version': 1,
          },
          {
            'id': 'gt-own',
            'firm_id': 'firm-1',
            'code': 'COLD_CHAIN',
            'name': 'Cold chain',
            'track_batch': true,
            'is_active': true,
            'in_use': true,
            'default_hsn_sac': '3002',
            'version': 4,
          },
        ],
      };
    }
    if (path.endsWith('/products/categories')) {
      return {
        'data': [
          {
            'id': 'cat-1',
            'code': 'VACCINES',
            'name': 'Vaccines',
            'level': 0,
            'path': 'VACCINES',
            'is_active': true,
            'goods_type_id': 'gt-own',
          },
          {
            'id': 'cat-2',
            'code': 'STATIONERY',
            'name': 'Stationery',
            'level': 0,
            'path': 'STATIONERY',
            'is_active': true,
            'goods_type_id': null,
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

void _window(WidgetTester tester, Size size) {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = size;
  addTearDown(() {
    tester.view.resetPhysicalSize();
    tester.view.resetDevicePixelRatio();
  });
}

Future<void> _openTypes(
  WidgetTester tester,
  _TypesApi api,
  PermissionService permissions, {
  Size size = const Size(1600, 900),
}) async {
  _window(tester, size);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Builder(
        builder: (context) => ResourceManagementPage<GoodsTypeRecord>(
          api: api,
          definition: goodsTypeDefinition(api, permissions, context: context),
        ),
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

Future<void> _openCategories(
  WidgetTester tester,
  _TypesApi api,
  PermissionService permissions,
) async {
  _window(tester, const Size(1600, 900));
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: ResourceManagementPage<ProductCategoryRecord>(
        api: api,
        definition: productCategoryDefinition(api, permissions),
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

Future<void> _select(WidgetTester tester, String text) async {
  await tester.tap(find.text(text).first);
  // Rows carry a double-tap handler, so a single tap is held for its timeout.
  await tester.pump(const Duration(milliseconds: 500));
  await tester.pumpAndSettle();
}

void main() {
  const List<String> manage = ['PRODUCT_VIEW', 'CUSTOM_FIELD_MANAGE'];

  test('the tab sits beside Custom Fields and asks PRODUCT_VIEW', () {
    final tabs = ModuleCatalog.byId(AppModule.administration).tabs;
    final int goods = tabs.indexWhere((tab) => tab.id == 'goods-types');
    final int custom = tabs.indexWhere((tab) => tab.id == 'firm-custom-fields');
    expect(goods, greaterThanOrEqualTo(0));
    expect(goods, lessThan(custom));
    expect(tabs[goods].requiredPermissions, ['PRODUCT_VIEW']);
  });

  testWidgets('the list shows a shared row and an own row', (tester) async {
    await _openTypes(tester, _TypesApi(), _permissions(['PRODUCT_VIEW']));

    for (final String heading in [
      'Code',
      'Name',
      'Kind',
      'Tracks',
      'In use',
      'Default HSN',
      'Default tax group',
      'Active',
    ]) {
      expect(find.text(heading), findsWidgets);
    }
    expect(find.text('MEDICINE'), findsOneWidget);
    expect(find.text('COLD_CHAIN'), findsOneWidget);
    expect(find.text('Shared'), findsOneWidget);
    expect(find.text('Own'), findsOneWidget);
    expect(find.text('Batch, expiry, manufacturing date'), findsOneWidget);
    expect(find.text('Batch'), findsOneWidget);
  });

  testWidgets('adding an own type sends exactly the declared keys',
      (tester) async {
    final _TypesApi api = _TypesApi();
    await _openTypes(tester, api, _permissions(manage));

    await tester.tap(find.widgetWithText(FilledButton, 'New').hitTestable());
    await tester.pumpAndSettle();
    final Finder boxes = find.byType(TextFormField);
    await tester.enterText(boxes.at(0), 'PAINT_TINT');
    await tester.enterText(boxes.at(1), 'Tinted paint');
    await tester.pumpAndSettle();
    await tester.tap(find.text('Save & Close').hitTestable());
    await tester.pumpAndSettle();

    expect(api.writes, hasLength(1));
    expect(api.writes.single.method, 'POST');
    expect(api.writes.single.path, '/api/v1/products/goods-types');
    expect(api.writes.single.body, {
      'code': 'PAINT_TINT',
      'name': 'Tinted paint',
      'description': null,
      'track_batch': false,
      'track_expiry': false,
      'track_manufacturing_date': false,
      'track_serial': false,
      'track_warranty': false,
      'default_hsn_sac': null,
      'default_tax_profile_group_code': null,
      'is_active': true,
    });
  });

  testWidgets('a refused save keeps the dialog open with the message',
      (tester) async {
    final _TypesApi api =
        _TypesApi(refuseWith: 'A goods type with this code already exists.');
    await _openTypes(tester, api, _permissions(manage));

    await tester.tap(find.widgetWithText(FilledButton, 'New').hitTestable());
    await tester.pumpAndSettle();
    final Finder boxes = find.byType(TextFormField);
    await tester.enterText(boxes.at(0), 'COLD_CHAIN');
    await tester.enterText(boxes.at(1), 'Cold chain');
    await tester.pumpAndSettle();
    await tester.tap(find.text('Save & Close').hitTestable());
    await tester.pumpAndSettle();

    expect(find.textContaining('already exists'), findsWidgets);
    expect(find.byType(TextFormField), findsWidgets);
    expect(find.text('Save & Close'), findsOneWidget);
  });

  testWidgets('a shared row offers Use and not Edit or Delete',
      (tester) async {
    final _TypesApi api = _TypesApi();
    final PermissionService permissions = _permissions(manage);
    await _openTypes(tester, api, permissions);

    await _select(tester, 'MEDICINE');
    expect(find.text('Use in this firm'), findsOneWidget);
    expect(find.text('Stop using'), findsNothing);
    expect(find.text('Set defaults'), findsOneWidget);
    final GoodsTypeRecord shared = (await api.goodsTypes()).first;
    final definition = goodsTypeDefinition(
      api,
      permissions,
      context:
          tester.element(find.byType(ResourceManagementPage<GoodsTypeRecord>)),
    );
    expect(definition.canEdit!(shared), isFalse);
    expect(definition.editRefusal!(shared),
        contains('A shared goods type cannot be changed'));

    await tester.tap(find.text('Use in this firm'));
    await tester.pumpAndSettle();
    expect(api.writes, hasLength(1));
    expect(api.writes.single.method, 'PUT');
    expect(api.writes.single.path,
        '/api/v1/products/goods-types/gt-shared/use');
    expect(api.writes.single.body, {'in_use': true});
  });

  testWidgets('a type in use offers Stop using', (tester) async {
    final _TypesApi api = _TypesApi();
    await _openTypes(tester, api, _permissions(manage));

    await _select(tester, 'COLD_CHAIN');
    expect(find.text('Stop using'), findsOneWidget);
    expect(find.text('Use in this firm'), findsNothing);

    await tester.tap(find.text('Stop using'));
    await tester.pumpAndSettle();
    expect(api.writes.single.body, {'in_use': false});
  });

  testWidgets('Set defaults saves through the use route', (tester) async {
    final _TypesApi api = _TypesApi();
    await _openTypes(tester, api, _permissions(manage));

    await _select(tester, 'MEDICINE');
    await tester.tap(find.text('Set defaults'));
    await tester.pumpAndSettle();
    await tester.enterText(
        find.byKey(const ValueKey('goods-type-defaults-hsn')), '3004');
    await tester.tap(find.byKey(const ValueKey('goods-type-defaults-save')));
    await tester.pumpAndSettle();

    expect(api.writes.single.path,
        '/api/v1/products/goods-types/gt-shared/use');
    expect(api.writes.single.body, {
      'in_use': true,
      'default_hsn_sac': '3004',
      'default_tax_profile_group_code': null,
    });
  });

  testWidgets('without CUSTOM_FIELD_MANAGE no write action is offered',
      (tester) async {
    await _openTypes(tester, _TypesApi(), _permissions(['PRODUCT_VIEW']));

    await _select(tester, 'MEDICINE');
    expect(find.text('Use in this firm'), findsNothing);
    expect(find.text('Set defaults'), findsNothing);
    expect(find.widgetWithText(FilledButton, 'New'), findsNothing);
  });

  testWidgets('the screen fits the 800x600 window', (tester) async {
    await _openTypes(tester, _TypesApi(), _permissions(manage),
        size: const Size(800, 600));
    await _select(tester, 'COLD_CHAIN');
    expect(tester.takeException(), isNull);
  });

  testWidgets('the category form sends the goods type, or null for General',
      (tester) async {
    final _TypesApi api = _TypesApi();
    await _openCategories(
        tester, api, _permissions(['PRODUCT_VIEW', 'PRODUCT_UPDATE']));

    // The grid names the type, or General.
    expect(find.text('Cold chain'), findsOneWidget);
    expect(find.text('General'), findsOneWidget);

    await tester.tap(find.widgetWithText(FilledButton, 'New').hitTestable());
    await tester.pumpAndSettle();
    // Only a type in use is offered: the shared, unused Medicine is not.
    expect(find.textContaining('Cold chain'), findsWidgets);
    expect(find.textContaining('Medicine'), findsNothing);
    final Finder boxes = find.byType(TextFormField);
    await tester.enterText(boxes.at(0), 'COLD');
    await tester.enterText(boxes.at(1), 'Cold goods');
    await tester.tap(find.textContaining('Cold chain').last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Save & Close').hitTestable());
    await tester.pumpAndSettle();
    expect(api.writes.single.body['goods_type_id'], 'gt-own');

    api.writes.clear();
    await tester.tap(find.widgetWithText(FilledButton, 'New').hitTestable());
    await tester.pumpAndSettle();
    final Finder again = find.byType(TextFormField);
    await tester.enterText(again.at(0), 'PLAIN');
    await tester.enterText(again.at(1), 'Plain goods');
    await tester.tap(find.text('Save & Close').hitTestable());
    await tester.pumpAndSettle();
    expect(api.writes.single.body.containsKey('goods_type_id'), isTrue);
    expect(api.writes.single.body['goods_type_id'], isNull);
  });
}
