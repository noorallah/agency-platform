import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Choose the supplier and the first line's product, and type its quantity.
///
/// A new purchase order opens empty (D-UI-40): no supplier, no product and no
/// quantity. A test that is about something else takes what the order used to
/// be given by asking for it here. The product box is keyed with the line
/// epoch, so it is found by its prefix.
Future<void> fillNewPurchaseOrder(
  WidgetTester tester, {
  required String vendor,
  required String product,
  String quantity = '1',
}) async {
  await tester.tap(find.byKey(const ValueKey<String>('purchase-order-vendor')));
  await tester.pumpAndSettle();
  await tester.tap(find.textContaining(vendor).last);
  await tester.pumpAndSettle();
  await tester.tap(_keyedWith('purchase-order-line-product-').first);
  await tester.pumpAndSettle();
  await tester.tap(find.textContaining(product).last);
  await tester.pumpAndSettle();
  await tester.enterText(_keyedWith('purchase-order-qty-').first, quantity);
  await tester.pump(const Duration(milliseconds: 400));
  await tester.pumpAndSettle();
}

Finder _keyedWith(String prefix) => find.byWidgetPredicate((Widget w) =>
    w.key is ValueKey<String> &&
    (w.key! as ValueKey<String>).value.startsWith(prefix));
