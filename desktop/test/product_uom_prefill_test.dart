// A firm's business profile carries the units its industry trades in — a
// pharmacy in strips, a food distributor in packs. Those defaults are applied
// by pre-filling the create form rather than by filling them in on the server:
// a unit the user can see and change before saving is one they can disagree
// with, while a unit applied silently is noticed only when a conversion comes
// out wrong three documents later.
//
// The rules this pins: pre-fill a new product, never an existing one, and say
// where the values came from.

import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/models/uom_packaging.dart';
import 'package:agency_desktop/ui/products/product_management_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

const ProductMetadataRecord _metadata = ProductMetadataRecord(
  profileCode: 'PHARMACY',
  features: [],
  categories: [],
  taxProfiles: [],
  requiredAttributeDefinitionIds: [],
  optionalAttributeDefinitionIds: [],
);

const List<UomRecord> _units = [
  UomRecord(
    id: 'uom-strip',
    code: 'STRIP',
    name: 'Strip',
    symbol: 'strip',
    dimension: 'COUNT',
    status: 'ACTIVE',
    isDecimalAllowed: false,
  ),
  UomRecord(
    id: 'uom-box',
    code: 'BOX',
    name: 'Box',
    symbol: 'box',
    dimension: 'COUNT',
    status: 'ACTIVE',
    isDecimalAllowed: false,
  ),
];

const BusinessProfileUomDefaults _pharmacyDefaults = BusinessProfileUomDefaults(
  businessProfileId: 'profile-1',
  firmId: null,
  baseUomId: 'uom-strip',
  inventoryUomId: 'uom-strip',
  purchaseUomId: 'uom-box',
  salesUomId: 'uom-strip',
  allowFraction: false,
  allowDecimal: false,
);

Future<void> _open(
  WidgetTester tester, {
  required ProductDialogMode mode,
  Product? product,
  BusinessProfileUomDefaults? defaults,
}) async {
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
          mode: mode,
          product: product,
          categories: const [],
          uoms: _units,
          profileUomDefaults: defaults,
          definitions: const [],
          metadata: _metadata,
          initialTab: 'packaging',
          onMetadataForCategory: (_) async => _metadata,
          onSave: (_) async => _existingProduct,
          onTabChanged: (_) {},
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

final Product _existingProduct = Product.fromJson(const {
  'id': 'product-1',
  'code': 'PROD-001',
  'name': 'Pain Relief',
  'product_type': 'STOCK_ITEM',
  'status': 'ACTIVE',
  // Deliberately blank: someone cleared these, and reopening the product must
  // not quietly put the profile's units back.
  'base_uom_id': '',
  'inventory_uom_id': '',
  'purchase_uom_id': '',
  'sales_uom_id': '',
  'allow_fraction': false,
  'allow_decimal': true,
});

void main() {
  testWidgets('a new product starts on its profile units', (tester) async {
    await _open(
      tester,
      mode: ProductDialogMode.create,
      defaults: _pharmacyDefaults,
    );

    expect(find.text('Strip (STRIP)'), findsWidgets);
    expect(find.text('Box (BOX)'), findsWidgets);
  });

  testWidgets('the form says where the units came from', (tester) async {
    await _open(
      tester,
      mode: ProductDialogMode.create,
      defaults: _pharmacyDefaults,
    );

    expect(find.textContaining('business profile'), findsOneWidget);
  });

  testWidgets('an existing product keeps what it was saved with',
      (tester) async {
    await _open(
      tester,
      mode: ProductDialogMode.edit,
      product: _existingProduct,
      defaults: _pharmacyDefaults,
    );

    expect(
      find.text('Strip (STRIP)'),
      findsNothing,
      reason: 'defaulting an edit would rewrite units the user had cleared',
    );
    expect(find.textContaining('business profile'), findsNothing);
  });

  testWidgets('a firm with no profile defaults gets a blank form',
      (tester) async {
    await _open(tester, mode: ProductDialogMode.create, defaults: null);

    expect(find.text('Strip (STRIP)'), findsNothing);
    expect(find.textContaining('business profile'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a default naming a withdrawn unit does not break the form',
      (tester) async {
    await _open(
      tester,
      mode: ProductDialogMode.create,
      defaults: const BusinessProfileUomDefaults(
        businessProfileId: 'profile-1',
        firmId: null,
        baseUomId: 'uom-deactivated',
        inventoryUomId: null,
        purchaseUomId: null,
        salesUomId: null,
        allowFraction: false,
        allowDecimal: true,
      ),
    );

    // A dropdown throws when its value is absent from its items, so an
    // outdated default must be dropped rather than selected.
    expect(tester.takeException(), isNull);
    expect(find.textContaining('business profile'), findsNothing);
  });
}
