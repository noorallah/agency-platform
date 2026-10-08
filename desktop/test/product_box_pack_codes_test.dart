// Backlog 89, market gap 3: a document line's product box finds a product by
// a pack's code. The box filtered on the label alone -- name, code and the
// product's own barcode -- so a carton label scanned into it matched
// nothing, on every phase 2 document editor.

import 'dart:io';

import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Product _product(String id, String name, {List<String> packs = const []}) =>
    Product.fromJson(<String, dynamic>{
      'id': id,
      'code': id.toUpperCase(),
      'name': name,
      'barcode': '890$id',
      'pack_codes': packs,
    });

void main() {
  final List<Product> products = <Product>[
    _product('p1', 'Soap', packs: <String>['8901234567906', '5012345678900']),
    _product('p2', 'Tea'),
    _product('p3', 'Salt', packs: <String>['7700000000011']),
  ];
  final List<DropdownMenuEntry<String>> entries = <DropdownMenuEntry<String>>[
    for (final Product item in products)
      DropdownMenuEntry<String>(
        value: item.id,
        label: '${item.name}  ${item.code}  ${item.barcode}',
      ),
  ];

  test('a product row carries the codes of its packs', () {
    expect(products[0].packCodes, <String>['8901234567906', '5012345678900']);
    expect(products[1].packCodes, isEmpty);
  });

  test("a pack's code leaves its product, and Enter picks it", () {
    final List<DropdownMenuEntry<String>> found =
        productEntriesMatching(entries, '8901234567906', products);
    expect(found.map((e) => e.value), <String>['p1']);
    expect(productEntryToHighlight(found, '8901234567906'), 0);

    // The second code of the same pack, and another product's pack.
    expect(
        productEntriesMatching(entries, '5012345678900', products)
            .map((e) => e.value),
        <String>['p1']);
    expect(
        productEntriesMatching(entries, '7700000000011', products)
            .map((e) => e.value),
        <String>['p3']);
  });

  test('a name, a code and the own barcode match as they did', () {
    expect(productEntriesMatching(entries, 'tea', products).map((e) => e.value),
        <String>['p2']);
    expect(productEntriesMatching(entries, '890p3', products).map((e) => e.value),
        <String>['p3']);
    expect(productEntriesMatching(entries, '', products), entries);
    expect(productEntriesMatching(entries, 'nothing', products), isEmpty);

    final List<DropdownMenuEntry<String>> several =
        productEntriesMatching(entries, 's', products);
    expect(several.map((e) => e.value), <String>['p1', 'p3']);
    expect(productEntryToHighlight(several, 's'), 0);
    expect(productEntryToHighlight(entries, 'salt'), 2);
    expect(productEntryToHighlight(entries, ''), isNull);
    expect(productEntryToHighlight(const [], 'x'), isNull);
  });

  testWidgets('a carton label typed into a product box picks the product',
      (tester) async {
    String? picked;
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: DropdownMenu<String>(
          key: const ValueKey('box'),
          enableFilter: true,
          filterCallback: (entries, filter) =>
              productEntriesMatching(entries, filter, products),
          searchCallback: productEntryToHighlight,
          requestFocusOnTap: true,
          dropdownMenuEntries: entries,
          onSelected: (value) => picked = value,
        ),
      ),
    ));
    await tester.tap(find.byKey(const ValueKey('box')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), '8901234567906');
    await tester.pumpAndSettle();
    // A scanner ends the code with Enter.
    await tester.testTextInput.receiveAction(TextInputAction.done);
    await tester.pumpAndSettle();
    expect(picked, 'p1');
  });

  test('every phase 2 document editor uses the one filter', () {
    // The five product boxes were five copies of one menu; a sixth editor
    // that leaves the callbacks out finds nothing for a carton label.
    const List<String> editors = <String>[
      'lib/ui/sales/sales_invoice_editor_phase2.dart',
      'lib/ui/sales/sales_order_editor_phase2.dart',
      'lib/ui/quotations/quotation_editor_phase2.dart',
      'lib/ui/purchases/purchase_order_editor_phase2.dart',
      'lib/ui/purchase_invoices/purchase_invoice_editor_phase2.dart',
    ];
    for (final String path in editors) {
      final String source = File(path).readAsStringSync();
      expect(source.contains("'Product (code, name or barcode)'"), isTrue,
          reason: '$path no longer has a product column');
      expect(source.contains('productEntriesMatching('), isTrue,
          reason: '$path filters its product box on the label alone');
      expect(source.contains('searchCallback: productEntryToHighlight'), isTrue,
          reason: '$path does not highlight what a pack code found');
    }
    // An editor added later is caught by its column heading.
    final List<String> strays = <String>[
      for (final FileSystemEntity entity
          in Directory('lib').listSync(recursive: true))
        if (entity is File &&
            entity.path.endsWith('.dart') &&
            entity
                .readAsStringSync()
                .contains("'Product (code, name or barcode)'") &&
            !entity.readAsStringSync().contains('productEntriesMatching('))
          entity.path,
    ];
    expect(strays, isEmpty);
  });
}
