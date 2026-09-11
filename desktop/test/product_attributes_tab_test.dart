// The Attributes tab of the product form shows the custom fields of the
// product's category. Those fields hang off `category_attribute_rules`, so the
// server answers a metadata read that names no category with no attribute at
// all -- and the metadata the workspace hands the dialog is exactly that
// firm-wide read. Only a category *changed* in the form fetched the right
// list, so an existing product opened with its category never showed the tab,
// in view or in edit. Found by manual test 5.5 on 2026-09-11.
//
// The rule this pins: opening a product asks for its own category's fields.

import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/ui/products/product_management_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

const ProductMetadataRecord _firmWide = ProductMetadataRecord(
  profileCode: 'WHOLESALE',
  features: [],
  categories: [],
  taxProfiles: [],
  requiredAttributeDefinitionIds: [],
  optionalAttributeDefinitionIds: [],
);

const ProductMetadataRecord _forCoreProducts = ProductMetadataRecord(
  profileCode: 'WHOLESALE',
  features: [],
  categories: [],
  taxProfiles: [],
  requiredAttributeDefinitionIds: [],
  optionalAttributeDefinitionIds: ['attr-origin'],
);

final AttributeDefinitionRecord _origin = AttributeDefinitionRecord.fromJson({
  'id': 'attr-origin',
  'code': 'COUNTRY_OF_ORIGIN',
  'name': 'Country of Origin',
  'data_type': 'TEXT',
  'entity_type': 'PRODUCT',
  'mandatory': false,
  'is_active': true,
  'applicable_category': 'CORE_PRODUCTS',
});

final Product _detergent = Product.fromJson(const {
  'id': 'product-1',
  'code': 'DETER1K',
  'name': 'Detergent 1kg',
  'product_type': 'STOCK_ITEM',
  'status': 'ACTIVE',
  'category_id': 'cat-core',
});

Future<List<String>> _open(
  WidgetTester tester, {
  required ProductDialogMode mode,
  Product? product,
}) async {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = const Size(1366, 768);
  addTearDown(() {
    tester.view.resetPhysicalSize();
    tester.view.resetDevicePixelRatio();
  });
  final List<String> asked = [];
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: ProductWorkspaceDialog(
          mode: mode,
          product: product,
          categories: const [],
          uoms: const [],
          definitions: [_origin],
          metadata: _firmWide,
          // Not General: its fixed-width dropdowns overflow under the test
          // font, and the tab strip under test is the same on every tab.
          initialTab: 'pricing',
          onMetadataForCategory: (String categoryId) async {
            asked.add(categoryId);
            return categoryId == 'cat-core' ? _forCoreProducts : _firmWide;
          },
          onSave: (_) async => _detergent,
          onTabChanged: (_) {},
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
  return asked;
}

void main() {
  testWidgets('an existing product opens with its category\'s attributes',
      (tester) async {
    final List<String> asked =
        await _open(tester, mode: ProductDialogMode.edit, product: _detergent);
    expect(asked, ['cat-core'],
        reason: 'the dialog must ask for the product\'s own category');
    expect(find.text('Attributes'), findsOneWidget);
  });

  testWidgets('the read-only view shows the tab too', (tester) async {
    await _open(tester, mode: ProductDialogMode.view, product: _detergent);
    expect(find.text('Attributes'), findsOneWidget);
  });

  testWidgets('a new product with no category yet has no attributes to show',
      (tester) async {
    final List<String> asked =
        await _open(tester, mode: ProductDialogMode.create);
    expect(asked, isEmpty);
    expect(find.text('Attributes'), findsNothing);
  });
}
