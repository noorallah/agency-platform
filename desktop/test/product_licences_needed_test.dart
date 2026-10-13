// P3: a product, and a product category, may need several trade licences.
// The buyer must hold every one. These pin the "Licences needed" control on
// the product form (chips, add, remove, clear -> []) and the category
// editor's multi-choice sending `required_licence_type_ids` as a list.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/models/trade_licence.dart';
import 'package:agency_desktop/ui/desktop_shell.dart'
    show productCategoryDefinition;
import 'package:agency_desktop/ui/products/product_management_page.dart';
import 'package:agency_desktop/ui/resource_management_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) {
  final String payload =
      base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '');
  return 'header.$payload.signature';
}

TradeLicenceTypeRecord _type(String id, String code, String name) =>
    TradeLicenceTypeRecord(
      id: id,
      version: 1,
      code: code,
      name: name,
      formNumbers: '',
      expires: true,
      isActive: true,
      description: '',
    );

const ProductMetadataRecord _metadata = ProductMetadataRecord(
  profileCode: '',
  features: [],
  categories: [],
  taxProfiles: [],
  requiredAttributeDefinitionIds: [],
  optionalAttributeDefinitionIds: [],
);

Product _product(List<String> licences) => Product.fromJson({
      'id': 'product-1',
      'code': 'PARA',
      'name': 'Paracetamol',
      'brand': 'Calpol',
      'product_type': 'STOCK_ITEM',
      'status': 'ACTIVE',
      'required_licence_type_ids': licences,
    });

Future<List<Json>> _pumpProduct(
  WidgetTester tester,
  List<String> licences,
) async {
  tester.view.physicalSize = const Size(1600, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final List<Json> sent = <Json>[];
  final Product product = _product(licences);
  await tester.pumpWidget(MaterialApp(
    builder: (context, child) => Phase2Scope(child: child!),
    home: Scaffold(
      body: ProductWorkspaceDialog(
        mode: ProductDialogMode.edit,
        product: product,
        categories: const [],
        uoms: const [],
        licenceTypes: [
          _type('type-1', 'DRUG', 'Drug Licence'),
          _type('type-2', 'FSSAI', 'Food Licence'),
        ],
        definitions: const [],
        metadata: _metadata,
        initialTab: 'general',
        onMetadataForCategory: (_) async => _metadata,
        onSave: (payload) async {
          sent.add(payload);
          return product;
        },
        onTabChanged: (_) {},
      ),
    ),
  ));
  await tester.pumpAndSettle();
  return sent;
}

Future<void> _save(WidgetTester tester) async {
  await tester.tap(find.byKey(const ValueKey('product-save')));
  await tester.pumpAndSettle();
}

class _CategoryApi extends ApiClient {
  _CategoryApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<(String, Json)> writes = <(String, Json)>[];

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
    if (path == '/api/v1/trade-licences/types') {
      return {
        'data': [
          {'id': 'type-1', 'code': 'DRUG', 'name': 'Drug Licence'},
          {'id': 'type-2', 'code': 'FSSAI', 'name': 'Food Licence'},
        ].map((m) => {...m, 'is_active': true}).toList(),
      };
    }
    return {'data': const <dynamic>[]};
  }
}

void main() {
  testWidgets('a product with two licences opens with two chips',
      (tester) async {
    await _pumpProduct(tester, ['type-1', 'type-2']);

    expect(find.byType(InputChip), findsNWidgets(2));
    expect(find.text('Drug Licence'), findsOneWidget);
    expect(find.text('Food Licence'), findsOneWidget);
    expect(find.text('The buyer must hold every one of these.'),
        findsOneWidget);
  });

  testWidgets('removing one chip saves a list of one', (tester) async {
    final List<Json> sent = await _pumpProduct(tester, ['type-1', 'type-2']);

    await tester.tap(find.descendant(
      of: find.byKey(const ValueKey('product-licence-chip-type-2')),
      matching: find.byIcon(Icons.clear),
    ));
    await tester.pumpAndSettle();
    await _save(tester);

    expect(sent.single['required_licence_type_ids'], ['type-1']);
  });

  testWidgets('adding a licence sends both', (tester) async {
    final List<Json> sent = await _pumpProduct(tester, ['type-1']);

    await tester.tap(find.byKey(const ValueKey('product-licence-add')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Food Licence').last);
    await tester.pumpAndSettle();
    await _save(tester);

    expect(sent.single['required_licence_type_ids'], ['type-1', 'type-2']);
  });

  testWidgets('clearing every chip sends an empty list', (tester) async {
    final List<Json> sent = await _pumpProduct(tester, ['type-1', 'type-2']);

    for (final String id in ['type-1', 'type-2']) {
      await tester.tap(find.descendant(
        of: find.byKey(ValueKey('product-licence-chip-$id')),
        matching: find.byIcon(Icons.clear),
      ));
      await tester.pumpAndSettle();
    }
    expect(find.text("None named here: the category's licences apply."),
        findsOneWidget);
    await _save(tester);

    expect(sent.single['required_licence_type_ids'], <String>[]);
  });

  testWidgets('a retired licence type stays as a chip and is sent back',
      (tester) async {
    final List<Json> sent = await _pumpProduct(tester, ['type-gone']);

    expect(find.text('Inactive licence type'), findsOneWidget);
    await _save(tester);

    expect(sent.single['required_licence_type_ids'], ['type-gone']);
  });

  testWidgets('a category saved with two licences sends both ids',
      (tester) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(1600, 900);
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });
    final _CategoryApi api = _CategoryApi();
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: ResourceManagementPage<ProductCategoryRecord>(
          api: api,
          definition: productCategoryDefinition(
            api,
            PermissionService()
              ..applyAccessToken(_accessToken({
                'roles': <String>['user'],
                'permissions': ['PRODUCT_VIEW', 'PRODUCT_UPDATE'],
              })),
          ),
        ),
      ),
    ));
    await tester.pumpAndSettle();

    await tester.tap(find.widgetWithText(FilledButton, 'New').hitTestable());
    await tester.pumpAndSettle();
    await tester.enterText(
        find.widgetWithText(TextFormField, 'Category code'), 'MEDICINE');
    await tester.enterText(
        find.widgetWithText(TextFormField, 'Name'), 'Medicine');
    await tester.pump();
    await tester.tap(find.text('DRUG'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('FSSAI'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Save & Close'));
    await tester.pumpAndSettle();

    expect(api.writes, hasLength(1));
    final (String path, Json body) = api.writes.single;
    expect(path, '/api/v1/products/categories');
    expect(body['required_licence_type_ids'], ['type-1', 'type-2']);
  });
}
