// D-QA-6: the product form asks for a category, and the backend has always
// had the routes to create one, but no desktop screen called them -- a fresh
// firm's product form offered an empty list and only the API could fill it.
//
// These pin the screen that closes it: Masters declares it, the grid lists the
// tree inactive nodes included, and New sends the shape the endpoint takes.

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

class _CategoryApi extends ApiClient {
  _CategoryApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<(String, Json)> writes = <(String, Json)>[];
  Map<String, String>? listQuery;

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
      writes.add((path, Map<String, dynamic>.from(body ?? const {})));
      return {
        'data': {'id': 'cat-new', ...?body},
      };
    }
    if (path == '/api/v1/products/categories') {
      listQuery = query;
      return {
        'data': [
          {
            'id': 'cat-2',
            'code': 'SOAP',
            'name': 'Soap',
            'parent_id': 'cat-1',
            'level': 2,
            'path': 'PERSONAL/SOAP',
            'is_active': true,
          },
          {
            'id': 'cat-1',
            'code': 'PERSONAL',
            'name': 'Personal care',
            'parent_id': null,
            'level': 1,
            'path': 'PERSONAL',
            'is_active': false,
          },
        ],
      };
    }
    return {'data': const <dynamic>[]};
  }
}

PermissionService _permissions() {
  final String claims = base64Url
      .encode(utf8.encode(jsonEncode(<String, dynamic>{
        'roles': <String>['user'],
        'permissions': <String>['PRODUCT_VIEW', 'PRODUCT_UPDATE'],
      })))
      .replaceAll('=', '');
  return PermissionService()..applyAccessToken('header.$claims.sig');
}

Future<void> _pump(WidgetTester tester, _CategoryApi api) async {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = const Size(1600, 900);
  addTearDown(() {
    tester.view.resetPhysicalSize();
    tester.view.resetDevicePixelRatio();
  });
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: ResourceManagementPage<ProductCategoryRecord>(
        api: api,
        definition: productCategoryDefinition(api, _permissions()),
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

void main() {
  test('Masters declares the screen', () {
    final Set<String> ids =
        ModuleCatalog.byId(AppModule.masters).tabs.map((tab) => tab.id).toSet();
    expect(ids, contains('product-categories'));
  });

  testWidgets('the grid lists the whole tree in path order, inactive too',
      (tester) async {
    final _CategoryApi api = _CategoryApi();
    await _pump(tester, api);

    expect(api.listQuery?['include_inactive'], 'true');
    expect(find.text('PERSONAL/SOAP'), findsOneWidget);
    expect(
      tester.getTopLeft(find.text('PERSONAL').first).dy,
      lessThan(tester.getTopLeft(find.text('PERSONAL/SOAP')).dy),
      reason: 'a parent sorts before its children',
    );
  });

  testWidgets('New creates a category with the fields the endpoint takes',
      (tester) async {
    final _CategoryApi api = _CategoryApi();
    await _pump(tester, api);

    await tester.tap(find.widgetWithText(FilledButton, 'New').hitTestable());
    await tester.pumpAndSettle();
    await tester.enterText(
        find.widgetWithText(TextFormField, 'Category code'), 'DETERGENT');
    await tester.enterText(
        find.widgetWithText(TextFormField, 'Name'), 'Detergent');
    await tester.tap(find.text('Save & Close'));
    await tester.pumpAndSettle();

    expect(api.writes, hasLength(1));
    final (String path, Json body) = api.writes.single;
    expect(path, '/api/v1/products/categories');
    expect(body['code'], 'DETERGENT');
    expect(body['name'], 'Detergent');
    expect(body['parent_id'], isNull);
    expect(body['is_active'], isTrue);
  });
}
