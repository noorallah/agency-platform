// A18, desktop half: a product names the supplier reorder orders it from.
//
// These pin: the picker lists the firm's suppliers and choosing one sends
// `preferred_vendor_id`; choosing None sends null; an edit that never touches
// the picker sends back the id it loaded with; and a user who cannot list
// suppliers (null list) still saves the product with its value kept.

import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/models/vendor.dart';
import 'package:agency_desktop/ui/products/product_management_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

const ProductMetadataRecord _metadata = ProductMetadataRecord(
  profileCode: '',
  features: [],
  categories: [],
  taxProfiles: [],
  requiredAttributeDefinitionIds: [],
  optionalAttributeDefinitionIds: [],
);

Vendor _vendor(String id, String name) => Vendor.fromJson({
      'id': id,
      'name': name,
      'display_name': name,
      'status': 'ACTIVE',
    });

Product _product({String preferred = ''}) => Product.fromJson({
      'id': 'product-1',
      'version': 1,
      'code': 'PARA',
      'name': 'Paracetamol',
      'product_type': 'STOCK_ITEM',
      'status': 'ACTIVE',
      if (preferred.isNotEmpty) 'preferred_vendor_id': preferred,
    });

Future<void> _open(
  WidgetTester tester, {
  required ProductDialogMode mode,
  Product? product,
  List<Vendor>? suppliers,
  required void Function(Json) onSent,
}) async {
  tester.view.physicalSize = const Size(1600, 2600);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    builder: (context, child) => Phase2Scope(child: child!),
    home: Scaffold(
      body: ProductWorkspaceDialog(
        mode: mode,
        product: product,
        categories: const [],
        uoms: const [],
        suppliers: suppliers,
        definitions: const [],
        metadata: _metadata,
        initialTab: 'general',
        onMetadataForCategory: (_) async => _metadata,
        onSave: (payload) async {
          onSent(payload);
          return _product();
        },
        onTabChanged: (_) {},
      ),
    ),
  ));
  await tester.pumpAndSettle();
  if (mode == ProductDialogMode.create) {
    await tester.enterText(
      find.widgetWithText(TextField, 'Product code *'),
      'PARA',
    );
    await tester.enterText(
      find.widgetWithText(TextField, 'Product name *'),
      'Paracetamol',
    );
  }
}

Future<void> _save(WidgetTester tester) async {
  await tester.ensureVisible(find.byKey(const ValueKey('product-save')));
  await tester.tap(find.byKey(const ValueKey('product-save')));
  await tester.pumpAndSettle();
}

Future<void> _pick(WidgetTester tester, String label) async {
  final Finder picker = find.byKey(const ValueKey('product-preferred-supplier'));
  await tester.ensureVisible(picker);
  await tester.pumpAndSettle();
  await tester.tap(picker);
  await tester.pumpAndSettle();
  await tester.tap(find.text(label).last);
  await tester.pumpAndSettle();
}

void main() {
  final List<Vendor> suppliers = [
    _vendor('vendor-1', 'Sri Ganesh Traders'),
    _vendor('vendor-2', 'Lakshmi Agencies'),
  ];

  testWidgets('choosing a supplier sends preferred_vendor_id', (tester) async {
    Json? sent;
    await _open(tester,
        mode: ProductDialogMode.create,
        suppliers: suppliers,
        onSent: (p) => sent = p);
    await _pick(tester, 'Lakshmi Agencies');
    await _save(tester);
    expect(sent?['preferred_vendor_id'], 'vendor-2');
  });

  testWidgets('choosing None sends null', (tester) async {
    Json? sent;
    await _open(tester,
        mode: ProductDialogMode.edit,
        product: _product(preferred: 'vendor-1'),
        suppliers: suppliers,
        onSent: (p) => sent = p);
    expect(find.text('Sri Ganesh Traders'), findsOneWidget);
    await _pick(tester, 'None');
    await _save(tester);
    expect(sent, isNotNull);
    expect(sent!.containsKey('preferred_vendor_id'), isTrue);
    expect(sent!['preferred_vendor_id'], isNull);
  });

  testWidgets('an edit that leaves it alone sends back the loaded id',
      (tester) async {
    Json? sent;
    await _open(tester,
        mode: ProductDialogMode.edit,
        product: _product(preferred: 'vendor-1'),
        suppliers: suppliers,
        onSent: (p) => sent = p);
    await _save(tester);
    expect(sent?['preferred_vendor_id'], 'vendor-1');
  });

  testWidgets(
      'without a supplier list the picker is disabled and the value is kept',
      (tester) async {
    Json? sent;
    await _open(tester,
        mode: ProductDialogMode.edit,
        product: _product(preferred: 'vendor-1'),
        suppliers: null,
        onSent: (p) => sent = p);
    final DropdownButtonFormField<String> picker =
        tester.widget(find.byKey(const ValueKey('product-preferred-supplier')));
    expect(picker.onChanged, isNull);
    await _save(tester);
    expect(sent?['preferred_vendor_id'], 'vendor-1');
  });
}
