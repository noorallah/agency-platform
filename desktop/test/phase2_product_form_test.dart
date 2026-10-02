// The product record in the phase 2 app (2026-09-26): a full-page tab with
// every section in one scroll and a side panel of prices, margin and stock,
// as the customer record the owner approved.

import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/ui/products/product_management_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

const ProductMetadataRecord _metadata = ProductMetadataRecord(
  profileCode: 'WHOLESALE',
  features: [],
  categories: [],
  taxProfiles: [],
  requiredAttributeDefinitionIds: [],
  optionalAttributeDefinitionIds: [],
);

final Product _product = Product.fromJson(const {
  'id': 'product-1',
  'code': 'PROD-001',
  'name': 'Pain Relief',
  'product_type': 'STOCK_ITEM',
  'status': 'ACTIVE',
  'unit': 'BOX',
  'purchase_price': '80',
  'selling_price': '100',
  'mrp': '120',
  'stock_on_hand': '42',
});

void main() {
  testWidgets('phase 2 shows the whole product on one page and saves it',
      (tester) async {
    tester.view.physicalSize = const Size(1600, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    Json? sent;
    await tester.pumpWidget(MaterialApp(
      builder: (context, child) => Phase2Scope(child: child!),
      home: Scaffold(
        body: ProductWorkspaceDialog(
          mode: ProductDialogMode.edit,
          product: _product,
          categories: const [],
          uoms: const [],
          definitions: const [],
          metadata: _metadata,
          initialTab: 'general',
          onMetadataForCategory: (_) async => _metadata,
          onSave: (payload) async {
            sent = payload;
            return _product;
          },
          onTabChanged: (_) {},
        ),
      ),
    ));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);

    // No tabs: the prices sit on the same page as the name.
    expect(find.text('Product name *'), findsOneWidget);
    expect(find.text('PRICING'), findsOneWidget);

    // The side panel works out the margin: 20 on 100, 20%.
    expect(find.byKey(const ValueKey('document-side-panel')), findsOneWidget);
    expect(find.text('20.00 · 20.0%'), findsOneWidget);
    expect(find.text('42 BOX'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('product-save')));
    await tester.pumpAndSettle();
    expect(sent?['code'], 'PROD-001');
    expect(sent?['name'], 'Pain Relief');
  });

  // STK-17: packing material is bought and stocked, never sold; a
  // discontinued product is sold until gone.
  testWidgets('a product marked not for sale says so, and the mark is saved',
      (tester) async {
    tester.view.physicalSize = const Size(1600, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    Json? sent;
    final Product carton = Product.fromJson(const {
      'id': 'product-2',
      'code': 'BOX-10',
      'name': 'Carton, 10 kg',
      'product_type': 'STOCK_ITEM',
      'status': 'DISCONTINUED',
      'unit': 'NOS',
      'not_for_sale': false,
    });
    await tester.pumpWidget(MaterialApp(
      builder: (context, child) => Phase2Scope(child: child!),
      home: Scaffold(
        body: ProductWorkspaceDialog(
          mode: ProductDialogMode.edit,
          product: carton,
          categories: const [],
          uoms: const [],
          definitions: const [],
          metadata: _metadata,
          initialTab: 'general',
          onMetadataForCategory: (_) async => _metadata,
          onSave: (payload) async {
            sent = payload;
            return carton;
          },
          onTabChanged: (_) {},
        ),
      ),
    ));
    await tester.pumpAndSettle();
    // A status the dropdown did not list would have thrown on build.
    expect(tester.takeException(), isNull);

    final Finder mark = find.byKey(const ValueKey('product-not-for-sale'));
    await tester.ensureVisible(mark);
    await tester.tap(mark);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('product-save')));
    await tester.pumpAndSettle();

    expect(sent?['not_for_sale'], isTrue);
    expect(sent?['status'], 'DISCONTINUED');
  });

  // STK-18: the shelf life a receipt fills each batch's expiry from.
  testWidgets('a shelf life typed in days is saved as a number',
      (tester) async {
    tester.view.physicalSize = const Size(1600, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    Json? sent;
    await tester.pumpWidget(MaterialApp(
      builder: (context, child) => Phase2Scope(child: child!),
      home: Scaffold(
        body: ProductWorkspaceDialog(
          mode: ProductDialogMode.edit,
          product: _product,
          categories: const [],
          uoms: const [],
          definitions: const [],
          metadata: _metadata,
          initialTab: 'general',
          onMetadataForCategory: (_) async => _metadata,
          onSave: (payload) async {
            sent = payload;
            return _product;
          },
          onTabChanged: (_) {},
        ),
      ),
    ));
    await tester.pumpAndSettle();

    final Finder field = find.widgetWithText(TextField, 'Shelf life (days)');
    await tester.ensureVisible(field);
    await tester.enterText(field, '180');
    await tester.tap(find.byKey(const ValueKey('product-save')));
    await tester.pumpAndSettle();

    expect(sent?['shelf_life_days'], 180);
    // STK-11: no rule chosen is earliest expiry, sent as null.
    expect(sent?['issue_rule'], isNull);
  });
}
