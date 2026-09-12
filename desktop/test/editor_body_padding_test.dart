import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/customer.dart';
import 'package:agency_desktop/models/product.dart';
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
  });
}
