// Backlog 89, unit sets: a NEW product can fill its units from a named set in
// one choice. Nothing is pre-filled without a choice; every box stays
// editable after a set is applied; the create body carries `unit_set_id` and
// `unit_conversion_factor`, an update carries neither.

import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/models/uom_packaging.dart';
import 'package:agency_desktop/ui/products/product_management_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

UomRecord _unit(String id, String name) => UomRecord(
      id: id,
      code: name.toUpperCase(),
      name: name,
      symbol: name.toLowerCase(),
      dimension: 'COUNT',
      status: 'ACTIVE',
      isDecimalAllowed: true,
    );

final List<UomRecord> _units = [
  _unit('uom-strip', 'Strip'),
  _unit('uom-box', 'Box'),
  _unit('uom-pc', 'Piece'),
  _unit('uom-litre', 'Litre'),
];

const List<ProductUnitSetOption> _sets = [
  ProductUnitSetOption(
    id: 'us-pharma',
    name: 'Pharma box of strips',
    baseUomId: 'uom-strip',
    inventoryUomId: 'uom-strip',
    purchaseUomId: 'uom-box',
    salesUomId: 'uom-strip',
    allowDecimal: false,
    conversionFactor: '10.000000',
    goodsTypeIds: ['gt-med'],
  ),
  ProductUnitSetOption(
    id: 'us-pieces',
    name: 'Plain pieces',
    baseUomId: 'uom-pc',
    allowDecimal: true,
  ),
  ProductUnitSetOption(
    id: 'us-paint',
    name: 'Litre tins',
    baseUomId: 'uom-litre',
    goodsTypeIds: ['gt-paint'],
  ),
];

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
    id: 'cat-gen',
    code: 'GEN',
    name: 'Sundries',
    parentId: '',
    level: 1,
    path: 'Sundries',
    isActive: true,
  ),
];

ProductMetadataRecord _metadataFor(String categoryId) => ProductMetadataRecord(
      profileCode: 'WHOLESALE',
      features: const [],
      categories: const [],
      taxProfiles: const [],
      requiredAttributeDefinitionIds: const [],
      optionalAttributeDefinitionIds: const [],
      goodsTypes: const [
        ProductGoodsTypeOption(
            id: 'gt-med', code: 'MEDICINE', name: 'Medicine'),
        ProductGoodsTypeOption(id: 'gt-paint', code: 'PAINT', name: 'Paint'),
      ],
      goodsTypeId: categoryId == 'cat-med' ? 'gt-med' : '',
      unitSets: _sets,
    );

final Product _stored = Product.fromJson(const {
  'id': 'product-9',
  'code': 'P-9',
  'name': 'Stored',
  'product_type': 'STOCK_ITEM',
  'status': 'ACTIVE',
});

Future<List<Json>> _open(WidgetTester tester, {Product? product}) async {
  tester.view.physicalSize = const Size(1600, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final List<Json> sent = <Json>[];
  await tester.pumpWidget(MaterialApp(
    builder: (context, child) => Phase2Scope(child: child!),
    home: Scaffold(
      body: ProductWorkspaceDialog(
        mode: product == null
            ? ProductDialogMode.create
            : ProductDialogMode.edit,
        product: product,
        categories: _categories,
        uoms: _units,
        definitions: const [],
        metadata: _metadataFor(''),
        initialTab: 'general',
        onMetadataForCategory: (id) async => _metadataFor(id),
        onSave: (payload) async {
          sent.add(payload);
          return product ?? _stored;
        },
        onTabChanged: (_) {},
      ),
    ),
  ));
  await tester.pumpAndSettle();
  return sent;
}

Future<void> _pickCategory(WidgetTester tester, String name) async {
  final Finder box =
      find.widgetWithText(DropdownButtonFormField<String>, 'Category');
  await tester.ensureVisible(box);
  await tester.tap(box);
  await tester.pumpAndSettle();
  await tester.tap(find.text(name).last);
  await tester.pumpAndSettle();
}

Future<void> _openSetPicker(WidgetTester tester) async {
  final Finder box = find.byKey(const ValueKey('product-unit-set'));
  await tester.ensureVisible(box);
  await tester.tap(box);
  await tester.pumpAndSettle();
}

Future<void> _pickSet(WidgetTester tester, String name) async {
  await _openSetPicker(tester);
  await tester.tap(find.text(name).last);
  await tester.pumpAndSettle();
}

Future<void> _pickUnit(WidgetTester tester, String label, String unit) async {
  final Finder box =
      find.widgetWithText(DropdownButtonFormField<String>, label);
  await tester.ensureVisible(box);
  await tester.tap(box);
  await tester.pumpAndSettle();
  await tester.tap(find.textContaining(unit).last);
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

void main() {
  testWidgets('the picker is narrowed by the category goods type',
      (tester) async {
    await _open(tester);
    await _pickCategory(tester, 'Medicines');
    await _openSetPicker(tester);
    expect(find.text('None (choose the units below)'), findsWidgets);
    expect(find.text('Pharma box of strips'), findsWidgets);
    // A set with no goods type is offered to every product.
    expect(find.text('Plain pieces'), findsWidgets);
    expect(find.text('Litre tins'), findsNothing);
  });

  testWidgets('a General product is offered only the sets for every product',
      (tester) async {
    await _open(tester);
    await _openSetPicker(tester);
    expect(find.text('Plain pieces'), findsWidgets);
    expect(find.text('Pharma box of strips'), findsNothing);
    expect(find.text('Litre tins'), findsNothing);
  });

  testWidgets('Show all unit sets lists every set', (tester) async {
    await _open(tester);
    final Finder all =
        find.byKey(const ValueKey('product-show-all-unit-sets'));
    await tester.ensureVisible(all);
    await tester.tap(all);
    await tester.pumpAndSettle();
    await _openSetPicker(tester);
    expect(find.text('Pharma box of strips'), findsWidgets);
    expect(find.text('Litre tins'), findsWidgets);
    expect(find.text('Plain pieces'), findsWidgets);
  });

  testWidgets('picking a set fills the units, decimal switch and conversion',
      (tester) async {
    final List<Json> sent = await _open(tester);
    await _pickCategory(tester, 'Medicines');
    await _pickSet(tester, 'Pharma box of strips');

    final Finder factor =
        find.byKey(const ValueKey('product-unit-conversion-factor'));
    expect(factor, findsOneWidget);
    expect(tester.widget<TextFormField>(factor).controller!.text, '10');
    expect(find.text('1 Box = how many Strip'), findsOneWidget);

    await _save(tester);
    final Json body = sent.single;
    expect(body['unit_set_id'], 'us-pharma');
    expect(body['unit_conversion_factor'], '10');
    expect(body['base_uom_id'], 'uom-strip');
    expect(body['inventory_uom_id'], 'uom-strip');
    expect(body['purchase_uom_id'], 'uom-box');
    expect(body['sales_uom_id'], 'uom-strip');
    expect(body['allow_decimal'], isFalse);
  });

  testWidgets('what is changed after picking is what is sent', (tester) async {
    final List<Json> sent = await _open(tester);
    await _pickCategory(tester, 'Medicines');
    await _pickSet(tester, 'Pharma box of strips');
    await tester.enterText(
        find.byKey(const ValueKey('product-unit-conversion-factor')), '12');
    await _pickUnit(tester, 'Sales UOM', 'Piece');
    await _save(tester);
    final Json body = sent.single;
    expect(body['unit_conversion_factor'], '12');
    expect(body['sales_uom_id'], 'uom-pc');
    expect(body['unit_set_id'], 'us-pharma');
  });

  testWidgets('the choice survives a category that narrows it out',
      (tester) async {
    final List<Json> sent = await _open(tester);
    await _pickCategory(tester, 'Medicines');
    await _pickSet(tester, 'Pharma box of strips');
    await _pickCategory(tester, 'Sundries');
    await _save(tester);
    expect(sent.single['unit_set_id'], 'us-pharma');
  });

  testWidgets('no set means nothing pre-filled and no unit_set_id',
      (tester) async {
    final List<Json> sent = await _open(tester);
    expect(find.byKey(const ValueKey('product-unit-conversion-factor')),
        findsNothing);
    await _save(tester);
    final Json body = sent.single;
    expect(body.containsKey('unit_set_id'), isFalse);
    expect(body.containsKey('unit_conversion_factor'), isFalse);
    expect(body['base_uom_id'], isNull);
    expect(body['purchase_uom_id'], isNull);
  });

  testWidgets('the conversion box follows two different units, set or not',
      (tester) async {
    final List<Json> sent = await _open(tester);
    await _pickUnit(tester, 'Purchase UOM', 'Box');
    expect(find.byKey(const ValueKey('product-unit-conversion-factor')),
        findsNothing);
    await _pickUnit(tester, 'Base UOM', 'Strip');
    final Finder factor =
        find.byKey(const ValueKey('product-unit-conversion-factor'));
    expect(factor, findsOneWidget);
    await tester.enterText(factor, '5');
    await _save(tester);
    final Json body = sent.single;
    expect(body['unit_conversion_factor'], '5');
    expect(body.containsKey('unit_set_id'), isFalse);
  });

  testWidgets('a blank or zero conversion is not sent', (tester) async {
    final List<Json> sent = await _open(tester);
    await _pickUnit(tester, 'Purchase UOM', 'Box');
    await _pickUnit(tester, 'Base UOM', 'Strip');
    await tester.enterText(
        find.byKey(const ValueKey('product-unit-conversion-factor')), '0');
    await _save(tester);
    expect(sent.single.containsKey('unit_conversion_factor'), isFalse);
  });

  testWidgets('an existing product has no picker, no box, and sends neither',
      (tester) async {
    final Product existing = Product.fromJson(const {
      'id': 'product-1',
      'code': 'PROD-001',
      'name': 'Pain Relief',
      'product_type': 'STOCK_ITEM',
      'status': 'ACTIVE',
      'base_uom_id': 'uom-strip',
      'purchase_uom_id': 'uom-box',
      'unit_set_id': 'us-pharma',
    });
    final List<Json> sent = await _open(tester, product: existing);
    expect(find.byKey(const ValueKey('product-unit-set')), findsNothing);
    expect(
        find.byKey(const ValueKey('product-show-all-unit-sets')), findsNothing);
    expect(find.byKey(const ValueKey('product-unit-conversion-factor')),
        findsNothing);
    final Finder origin = find.byKey(const ValueKey('product-unit-set-origin'));
    await tester.ensureVisible(origin);
    expect((tester.widget(origin) as Text).data,
        'Units from: Pharma box of strips');

    await tester.tap(find.byKey(const ValueKey('product-save')));
    await tester.pumpAndSettle();
    final Json body = sent.single;
    expect(body.containsKey('unit_set_id'), isFalse);
    expect(body.containsKey('unit_conversion_factor'), isFalse);
    expect(body['purchase_uom_id'], 'uom-box');
  });

  testWidgets('a product from no set shows no origin line', (tester) async {
    await _open(tester, product: _stored);
    expect(
        find.byKey(const ValueKey('product-unit-set-origin')), findsNothing);
  });
}
