import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Choose a product and type a quantity on the first line of a new document.
///
/// A new sales order or quotation used to open with the first product and a
/// quantity of 1 already on line 1 (D-UI-22). It starts empty now, so a test
/// that is about something else (a discount, a delivery charge, a price)
/// takes the line it used to be given by asking for it here. [document] is
/// the key prefix: `sales-order` or `quotation`.
Future<void> fillFirstLine(
  WidgetTester tester, {
  required String document,
  required String product,
  String quantity = '1',
}) async {
  await tester.tap(find.byKey(ValueKey<String>('$document-line-product-0')));
  await tester.pumpAndSettle();
  await tester.tap(find.textContaining(product).last);
  await tester.pumpAndSettle();
  // Phase 1 labels its quantity box; phase 2's is the second box in the row
  // (the product picker is the first).
  final Finder labelled = find.widgetWithText(TextFormField, 'Quantity');
  final Finder box = labelled.evaluate().isNotEmpty
      ? labelled.first
      : find
          .descendant(
            of: find.byKey(ValueKey<String>('$document-line-0')),
            matching: find.byType(EditableText),
          )
          .at(1);
  await tester.enterText(box, quantity);
  await tester.pump();
}
