// D-QA-12: the product form's Product type and Status dropdowns showed the
// stored codes -- STOCK_ITEM, FINISHED_GOODS, ACTIVE -- where people expect
// words. The value saved is still the code; only what is shown changes.

import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/ui/products/product_management_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

const ProductMetadataRecord _metadata = ProductMetadataRecord(
  profileCode: 'DISTRIBUTION',
  features: [],
  categories: [],
  taxProfiles: [],
  requiredAttributeDefinitionIds: [],
  optionalAttributeDefinitionIds: [],
);

void main() {
  test('a code reads as words, in sentence case', () {
    expect(productCodeLabel('STOCK_ITEM'), 'Stock item');
    expect(productCodeLabel('DIGITAL_PRODUCT'), 'Digital product');
    expect(productCodeLabel('ACTIVE'), 'Active');
    expect(productCodeLabel(''), '');
  });

  testWidgets('the new-product form offers words, not codes', (tester) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(1366, 768);
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ProductWorkspaceDialog(
            mode: ProductDialogMode.create,
            product: null,
            categories: const [],
            uoms: const [],
            definitions: const [],
            metadata: _metadata,
            initialTab: 'general',
            onMetadataForCategory: (_) async => _metadata,
            onSave: (_) async => throw UnimplementedError(),
            onTabChanged: (_) {},
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Stock item'), findsOneWidget);
    expect(find.text('Active'), findsOneWidget);
    expect(find.text('STOCK_ITEM'), findsNothing);
    expect(find.text('ACTIVE'), findsNothing);
  });
}
