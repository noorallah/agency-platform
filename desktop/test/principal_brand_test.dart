// MST-1: principals and brands are masters, a product can be filed under a
// brand, and sales can be analysed by either.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/ui/desktop_shell.dart';
import 'package:agency_desktop/ui/products/product_management_page.dart';
import 'package:agency_desktop/ui/sales/sales_analysis_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

ApiClient _api() => ApiClient(
      baseUrl: 'http://localhost:8000',
      accessToken: () => null,
      refreshAccessToken: () async => false,
      activeFirmId: () => 'firm-1',
    );

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _salesViewer() => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': <String>['SALES_VIEW'],
  }));

const ProductMetadataRecord _metadata = ProductMetadataRecord(
  profileCode: 'WHOLESALE',
  features: [],
  categories: [],
  taxProfiles: [],
  requiredAttributeDefinitionIds: [],
  optionalAttributeDefinitionIds: [],
);

void main() {
  test('a principal is written with its code, name and supplier', () {
    final definition = principalDefinition(_api(), PermissionService());
    final Map<String, dynamic> body = definition.payload(
      {
        'code': 'HUL',
        'name': 'Hindustan Unilever',
        'vendor_id': 'vendor-1',
        'is_active': true,
      },
      true,
    );
    expect(body, {
      'code': 'HUL',
      'name': 'Hindustan Unilever',
      'vendor_id': 'vendor-1',
      'is_active': true,
    });
    expect(definition.resource, 'products/principals');
    final Map<String, dynamic> noSupplier = definition.payload(
      {'code': 'X', 'name': 'X', 'vendor_id': '', 'is_active': true},
      true,
    );
    expect(noSupplier['vendor_id'], isNull);
  });

  test('a brand is written with its name and principal', () {
    final definition = brandDefinition(_api(), PermissionService());
    final Map<String, dynamic> body = definition.payload(
      {'name': 'Surf Excel', 'principal_id': 'p-1', 'is_active': true},
      true,
    );
    expect(body, {
      'name': 'Surf Excel',
      'principal_id': 'p-1',
      'is_active': true,
    });
    expect(definition.resource, 'products/brands');
    expect(
      definition.cells(BrandRecord.fromJson(const {
        'id': 'b-1',
        'name': 'Surf Excel',
        'principal_id': 'p-1',
        'principal_name': 'Hindustan Unilever',
        'is_active': true,
      })),
      ['Surf Excel', 'Hindustan Unilever', 'Yes'],
    );
  });

  testWidgets('a product filed under a brand sends brand_id', (tester) async {
    tester.view.physicalSize = const Size(1600, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    Json? sent;
    final Product product = Product.fromJson(const {
      'id': 'product-1',
      'code': 'PROD-001',
      'name': 'Detergent',
      'product_type': 'STOCK_ITEM',
      'status': 'ACTIVE',
      'unit': 'BOX',
      'brand': 'Old text',
    });
    await tester.pumpWidget(MaterialApp(
      builder: (context, child) => Phase2Scope(child: child!),
      home: Scaffold(
        body: ProductWorkspaceDialog(
          mode: ProductDialogMode.edit,
          product: product,
          categories: const [],
          uoms: const [],
          brands: const [
            BrandRecord(
              id: 'b-1',
              name: 'Surf Excel',
              principalId: 'p-1',
              principalName: 'Hindustan Unilever',
              isActive: true,
            ),
          ],
          definitions: const [],
          metadata: _metadata,
          initialTab: 'general',
          onMetadataForCategory: (_) async => _metadata,
          onSave: (payload) async {
            sent = payload;
            return product;
          },
          onTabChanged: (_) {},
        ),
      ),
    ));
    await tester.pumpAndSettle();
    expect(find.text('Free text: Old text'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('product-brand')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Surf Excel (Hindustan Unilever)').last);
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const ValueKey('product-save')));
    await tester.pumpAndSettle();
    expect(sent?['brand_id'], 'b-1');
    expect(sent?['brand'], 'Surf Excel');
  });

  testWidgets('without the brand list no brand_id is sent', (tester) async {
    tester.view.physicalSize = const Size(1600, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    Json? sent;
    final Product product = Product.fromJson(const {
      'id': 'product-1',
      'code': 'PROD-001',
      'name': 'Detergent',
      'product_type': 'STOCK_ITEM',
      'status': 'ACTIVE',
      'unit': 'BOX',
      'brand_id': 'b-1',
      'brand': 'Surf Excel',
    });
    await tester.pumpWidget(MaterialApp(
      builder: (context, child) => Phase2Scope(child: child!),
      home: Scaffold(
        body: ProductWorkspaceDialog(
          mode: ProductDialogMode.edit,
          product: product,
          categories: const [],
          uoms: const [],
          definitions: const [],
          metadata: _metadata,
          initialTab: 'general',
          onMetadataForCategory: (_) async => _metadata,
          onSave: (payload) async {
            sent = payload;
            return product;
          },
          onTabChanged: (_) {},
        ),
      ),
    ));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('product-save')));
    await tester.pumpAndSettle();
    expect(sent?.containsKey('brand_id'), isFalse);
  });

  testWidgets('sales analysis offers Brand and Principal', (tester) async {
    tester.view.physicalSize = const Size(1366, 768);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final _EmptyApi api = _EmptyApi();
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: SalesAnalysisPage(
          api: api,
          permissions: _salesViewer(),
          hasActiveFirm: true,
          today: DateTime(2026, 10, 15),
        ),
      ),
    ));
    await tester.pumpAndSettle();
    await tester
        .tap(find.widgetWithText(DropdownButtonFormField<String>, 'Rows'));
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(
      find.text('Brand'),
      100,
      scrollable: find.byType(Scrollable).last,
    );
    expect(find.text('Brand'), findsWidgets);
    await tester.scrollUntilVisible(
      find.text('Principal'),
      100,
      scrollable: find.byType(Scrollable).last,
    );
    await tester.tap(find.text('Principal').last);
    await tester.pumpAndSettle();
    expect(api.queries.last['rows'], 'principal');
  });
}

class _EmptyApi extends ApiClient {
  _EmptyApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Map<String, String>> queries = [];

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
    queries.add(query ?? {});
    return {
      'data': {
        'rows': [],
        'columns': [],
        'cells': [],
        'row_totals': <String, dynamic>{},
        'column_totals': <String, dynamic>{},
        'grand_total': {
          'quantity': 0,
          'taxable': 0,
          'tax': 0,
          'net': 0,
          'invoices': 0,
          'average_bill': null,
        },
      },
    };
  }
}
