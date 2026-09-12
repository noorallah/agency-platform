import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/customer.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/models/quotation.dart';
import 'package:agency_desktop/ui/quotations/quotation_editor_dialog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// A form inside a workspace dialog keeps room between itself and the frame.
///
/// Found on the 2026-09-13 manual pass (plan item 9.1): the New quotation
/// form sat flush against the dialog's edge, so the first row's floating
/// labels were cut off at the top and text touched the frame on every side.
/// The workspace dialog places its body unpadded; the editors that looked
/// right padded themselves, and four did not.
void main() {
  testWidgets('the quotation form is inset from the dialog on every side',
      (tester) async {
    tester.view.physicalSize = const Size(1366, 768);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: QuotationEditorDialog(
            customers: [
              Customer.fromJson({
                'id': 'c1',
                'code': 'WHOLE01C01',
                'name': 'Vijaya Super Stores',
                'display_name': 'Vijaya Super Stores',
              }),
            ],
            products: [
              Product.fromJson({
                'id': 'p1',
                'code': 'DETER1K',
                'name': 'Detergent Powder 1kg',
              }),
            ],
            branches: [
              BranchRecord.fromJson({'id': 'b1', 'code': 'WHL_HO', 'name': 'HO'}),
            ],
            warehouses: [
              WarehouseRecord.fromJson({
                'id': 'w1',
                'code': 'WHL_DC',
                'name': 'Bulk Goods Warehouse',
                'branch_id': 'b1',
              }),
            ],
            today: DateTime(2026, 9, 13),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);

    final Rect form = tester.getRect(find.byType(Form));
    final Rect customer =
        tester.getRect(find.byType(DropdownButtonFormField<String>).first);
    expect(customer.left - form.left, greaterThanOrEqualTo(16));
    expect(customer.top - form.top, greaterThanOrEqualTo(16));
    expect(form.right - customer.right, greaterThanOrEqualTo(16));

    // And a customer is offered by code and name, the way every other
    // picker names its rows: the plan says WHOLE01C01, the list said only
    // "Vijaya Super Stores" (plan item 9.1).
    await tester.tap(find.text('Customer'));
    await tester.pumpAndSettle();
    expect(find.text('WHOLE01C01 - Vijaya Super Stores'), findsWidgets);
  });

  testWidgets('a revision keeps a typed rate and re-prices a resolved one',
      (tester) async {
    // Found on the 2026-09-13 manual pass (plan item 9.2): reopening a
    // quotation refilled every Discount % box from the stored rate and sent
    // it back as typed, so a line moved from 12 to 18 units kept the 2% of
    // the ladder's first step instead of taking the 6.75% of its third.
    tester.view.physicalSize = const Size(1366, 768);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: QuotationEditorDialog(
            customers: [
              Customer.fromJson({
                'id': 'c1',
                'code': 'WHOLE01C01',
                'name': 'Vijaya Super Stores',
                'display_name': 'Vijaya Super Stores',
              }),
            ],
            products: [
              Product.fromJson({
                'id': 'p1',
                'code': 'DETER1K',
                'name': 'Detergent Powder 1kg',
              }),
            ],
            branches: [
              BranchRecord.fromJson({'id': 'b1', 'code': 'WHL_HO', 'name': 'HO'}),
            ],
            warehouses: [
              WarehouseRecord.fromJson({
                'id': 'w1',
                'code': 'WHL_DC',
                'name': 'Bulk Goods Warehouse',
                'branch_id': 'b1',
              }),
            ],
            today: DateTime(2026, 9, 13),
            existing: Quotation.fromJson({
              'id': 'q1',
              'customer_id': 'c1',
              'branch_id': 'b1',
              'warehouse_id': 'w1',
              'quotation_number': 'QT-2026-2027-000006',
              'quotation_date': '2026-09-13',
              'valid_until': '2026-10-13',
              'status': 'DRAFT',
              'lines': [
                {
                  'id': 'l1',
                  'line_number': 1,
                  'product_id': 'p1',
                  'quantity': '18.0000',
                  'unit_price': '84.0000',
                  'discount_percent': '2.0000',
                  'discount_source': 'price_list',
                },
                {
                  'id': 'l2',
                  'line_number': 2,
                  'product_id': 'p1',
                  'quantity': '3.0000',
                  'unit_price': '84.0000',
                  'discount_percent': '4.0000',
                  'discount_source': 'percent',
                },
              ],
            }),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    final List<TextFormField> boxes = tester
        .widgetList<TextFormField>(find.widgetWithText(TextFormField, 'Discount %'))
        .toList();
    expect(boxes, hasLength(2));
    // The resolved rate is not re-sent: its box is blank and says why.
    expect(boxes[0].controller?.text, isEmpty);
    expect(
      find.text('Last priced at 2% by the price list. Blank prices it afresh.'),
      findsOneWidget,
    );
    // The typed rate is what was agreed and stays.
    expect(boxes[1].controller?.text, '4.0000');
  });
}
