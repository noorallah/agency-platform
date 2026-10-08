// Backlog 89: a product category carries a goods type, and a new product
// starts on its category's type. The form shows the type as a read-only line,
// fills the nine tracking switches, HSN and tax group for a NEW product only,
// and offers just the tracking the type has.

import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/ui/products/product_management_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

const ProductGoodsTypeOption _medicine = ProductGoodsTypeOption(
  id: 'gt-med',
  code: 'MEDICINE',
  name: 'Medicine',
  switches: {
    'track_batch': true,
    'track_expiry': true,
    'track_manufacturing_date': true,
    'track_serial': false,
    'track_warranty': false,
    'require_batch_on_receipt': true,
    'require_batch_on_issue': true,
    'require_serial_on_receipt': false,
    'require_serial_on_issue': false,
  },
  defaultHsnSac: '3004',
  defaultTaxProfileGroupCode: 'GST12',
);

const ProductGoodsTypeOption _paint = ProductGoodsTypeOption(
  id: 'gt-paint',
  code: 'PAINT',
  name: 'Paint',
  switches: {'track_batch': true},
  defaultHsnSac: '3208',
);

const List<ProductCategoryRecord> _categories = [
  ProductCategoryRecord(
    id: 'cat-med',
    code: 'MED',
    name: 'Medicines',
    parentId: '',
    level: 1,
    path: 'Medicines',
    isActive: true,
    goodsTypeId: 'gt-med',
  ),
  ProductCategoryRecord(
    id: 'cat-paint',
    code: 'PNT',
    name: 'Paints',
    parentId: '',
    level: 1,
    path: 'Paints',
    isActive: true,
    goodsTypeId: 'gt-paint',
  ),
  ProductCategoryRecord(
    id: 'cat-gen',
    code: 'GEN',
    name: 'Sundries',
    parentId: '',
    level: 1,
    path: 'Sundries',
    isActive: true,
  ),
];

const List<ProductTaxProfileRecord> _taxProfiles = [
  ProductTaxProfileRecord(
    id: 'tp-12',
    code: 'GST12',
    groupCode: 'GST12',
    label: 'GST 12%',
    taxSystemId: 'gst',
  ),
];

ProductMetadataRecord _metadataFor(String categoryId) {
  const List<ProductGoodsTypeOption> types = [_medicine, _paint];
  final String typeId = switch (categoryId) {
    'cat-med' => 'gt-med',
    'cat-paint' => 'gt-paint',
    _ => '',
  };
  return ProductMetadataRecord(
    profileCode: 'WHOLESALE',
    features: const [],
    categories: const [],
    taxProfiles: _taxProfiles,
    requiredAttributeDefinitionIds: const [],
    optionalAttributeDefinitionIds: const [],
    goodsTypes: types,
    goodsTypeId: typeId,
  );
}

class _Harness {
  final List<Json> sent = <Json>[];
  final List<String> metadataCalls = <String>[];
}

Future<_Harness> _open(
  WidgetTester tester, {
  Product? product,
  Product? copyOf,
  ProductMetadataRecord? metadata,
}) async {
  tester.view.physicalSize = const Size(1600, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final _Harness harness = _Harness();
  await tester.pumpWidget(MaterialApp(
    builder: (context, child) => Phase2Scope(child: child!),
    home: Scaffold(
      body: ProductWorkspaceDialog(
        mode: product == null
            ? ProductDialogMode.create
            : ProductDialogMode.edit,
        product: product,
        copyOf: copyOf,
        categories: _categories,
        uoms: const [],
        definitions: const [],
        metadata: metadata ?? _metadataFor(''),
        initialTab: 'general',
        onMetadataForCategory: (id) async {
          harness.metadataCalls.add(id);
          return _metadataFor(id);
        },
        onSave: (payload) async {
          harness.sent.add(payload);
          return product ?? _stored;
        },
        onTabChanged: (_) {},
      ),
    ),
  ));
  await tester.pumpAndSettle();
  return harness;
}

final Product _stored = Product.fromJson(const {
  'id': 'product-9',
  'code': 'P-9',
  'name': 'Stored',
  'product_type': 'STOCK_ITEM',
  'status': 'ACTIVE',
});

Future<void> _pickCategory(WidgetTester tester, String name) async {
  final Finder box = find.widgetWithText(DropdownButtonFormField<String>,
      'Category');
  await tester.ensureVisible(box);
  await tester.tap(box);
  await tester.pumpAndSettle();
  await tester.tap(find.text(name).last);
  await tester.pumpAndSettle();
}

Future<void> _save(WidgetTester tester) async {
  await tester.enterText(
    find.widgetWithText(TextField, 'Product name *'),
    'Cough Syrup',
  );
  await tester.tap(find.byKey(const ValueKey('product-save')));
  await tester.pumpAndSettle();
}

String _line(WidgetTester tester) =>
    (tester.widget(find.byKey(const ValueKey('product-goods-type'))) as Text)
        .data!;

void main() {
  testWidgets('a medicine category fills a new product', (tester) async {
    final _Harness h = await _open(tester);
    expect(_line(tester), 'Goods type: General');

    await _pickCategory(tester, 'Medicines');
    expect(_line(tester), 'Goods type: Medicine');
    expect(find.text('Track batch'), findsOneWidget);
    expect(find.text('Track expiry'), findsOneWidget);
    expect(find.text('Track manufacturing date'), findsOneWidget);
    expect(find.text('Track serial'), findsNothing);
    expect(find.text('Require batch on receipt'), findsOneWidget);
    expect(find.text('Shelf life (days)'), findsOneWidget);

    await tester.ensureVisible(
        find.byKey(const ValueKey('product-show-all-tracking')));
    await tester.tap(find.byKey(const ValueKey('product-show-all-tracking')));
    await tester.pumpAndSettle();
    expect(find.text('Track serial'), findsOneWidget);
    // Serial is off, so its dependents stay hidden even with Show all.
    expect(find.text('Require serial on receipt'), findsNothing);

    await _save(tester);
    expect(h.sent, hasLength(1));
    final Json sent = h.sent.single;
    expect(sent['track_batch'], isTrue);
    expect(sent['track_expiry'], isTrue);
    expect(sent['track_manufacturing_date'], isTrue);
    expect(sent['track_serial'], isFalse);
    expect(sent['require_batch_on_receipt'], isTrue);
    expect(sent['require_batch_on_issue'], isTrue);
    expect(sent['hsn_sac'], '3004');
    expect(sent['tax_profile_group_code'], 'GST12');
    expect(sent.containsKey('goods_type_id'), isFalse);
  });

  testWidgets('a general category sets the switches off and says so',
      (tester) async {
    final _Harness h = await _open(tester);
    await _pickCategory(tester, 'Sundries');
    expect(_line(tester), 'Goods type: General');
    expect(find.byKey(const ValueKey('product-no-tracking-hint')),
        findsOneWidget);
    expect(find.text('Track batch'), findsNothing);
    expect(find.byKey(const ValueKey('product-show-all-tracking')),
        findsOneWidget);

    await _save(tester);
    final Json sent = h.sent.single;
    for (final String key in const [
      'track_batch',
      'track_expiry',
      'track_manufacturing_date',
      'track_serial',
      'track_warranty',
      'require_batch_on_receipt',
      'require_batch_on_issue',
    ]) {
      expect(sent[key], isFalse, reason: key);
    }
  });

  testWidgets('an HSN the type filled is replaced by the next type',
      (tester) async {
    final _Harness h = await _open(tester);
    await _pickCategory(tester, 'Medicines');
    // 3004 was filled by the type, so the next type replaces it.
    await _pickCategory(tester, 'Paints');
    await _save(tester);
    expect(h.sent.last['hsn_sac'], '3208');
    // The tax group the medicine type filled is not the paint type's.
    expect(h.sent.last['tax_profile_group_code'], isNull);
  });

  testWidgets('a typed HSN is never overwritten', (tester) async {
    final _Harness typed = await _open(tester);
    await tester.enterText(find.widgetWithText(TextField, 'HSN / SAC'), '9999');
    await _pickCategory(tester, 'Medicines');
    await _save(tester);
    expect(typed.sent.single['hsn_sac'], '9999');
  });

  testWidgets('expiry off hides shelf life; batch off hides the issue rule',
      (tester) async {
    final _Harness h = await _open(tester);
    await _pickCategory(tester, 'Medicines');
    expect(find.text('Shelf life (days)'), findsOneWidget);
    expect(find.byKey(const ValueKey('product-issue-rule')), findsOneWidget);

    await tester.tap(find.widgetWithText(SwitchListTile, 'Track expiry'));
    await tester.pumpAndSettle();
    expect(find.text('Shelf life (days)'), findsNothing);
    expect(find.byKey(const ValueKey('product-expiry-rules')), findsNothing);

    await tester.tap(find.widgetWithText(SwitchListTile, 'Track batch'));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('product-issue-rule')), findsNothing);
    expect(find.text('Require batch on receipt'), findsNothing);

    await _save(tester);
    expect(h.sent.single['require_batch_on_receipt'], isFalse);
    expect(h.sent.single['require_batch_on_issue'], isFalse);
  });

  testWidgets('an existing product keeps its own switches and stored type',
      (tester) async {
    final Product existing = Product.fromJson(const {
      'id': 'product-1',
      'code': 'PROD-001',
      'name': 'Pain Relief',
      'product_type': 'STOCK_ITEM',
      'status': 'ACTIVE',
      'goods_type_id': 'gt-med',
      'track_batch': false,
      'track_serial': true,
      'hsn_sac': '1111',
    });
    final _Harness h = await _open(
      tester,
      product: existing,
      metadata: _metadataFor('cat-med'),
    );
    expect(_line(tester), 'Goods type: Medicine');
    await tester.tap(find.byKey(const ValueKey('product-save')));
    await tester.pumpAndSettle();
    final Json sent = h.sent.single;
    expect(sent['track_batch'], isFalse);
    expect(sent['track_serial'], isTrue);
    expect(sent['track_expiry'], isFalse);
    expect(sent['hsn_sac'], '1111');
    expect(sent.containsKey('goods_type_id'), isFalse);
  });

  testWidgets('barcode and QR code are plain fields', (tester) async {
    await _open(tester);
    final Finder barcode = find.widgetWithText(TextField, 'Barcode');
    await tester.ensureVisible(barcode);
    expect(tester.widget<TextField>(barcode).readOnly, isFalse);
    expect(tester.widget<TextField>(barcode).enabled, isNot(false));
    expect(find.textContaining('Disabled by feature flag'), findsNothing);
  });

  testWidgets('opening asks the server for nothing; one category, one call',
      (tester) async {
    final _Harness h = await _open(tester);
    expect(h.metadataCalls, isEmpty);
    await _pickCategory(tester, 'Medicines');
    expect(h.metadataCalls, ['cat-med']);
  });
}
