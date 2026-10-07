// D-UI-15: returning more than went out says so on the screen.

import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/sales_return.dart';
import 'package:agency_desktop/ui/sales_returns/sales_return_editor_dialog.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'support/return_document.dart';

ReturnableDocument _note() => ReturnableDocument.fromDeliveryNote({
      'id': 'dn-1',
      'delivery_note_number': 'DN-2026-000001',
      'delivery_date': '2026-08-10',
      'customer_name': 'Anand Agencies',
      'status': 'DISPATCHED',
      'lines': [
        {
          'id': 'dn-line-1',
          'line_number': 1,
          'product_id': 'prod-1',
          'product_name': 'Toothpaste 150g',
          'current_delivery_quantity': '5',
          'unit_price': '50',
        },
      ],
    });

ReturnableDocument _bill() => ReturnableDocument.fromSalesInvoice({
      'id': 'si-1',
      'invoice_number': 'SI-26-27-000005',
      'invoice_date': '2026-08-10',
      'customer_name': 'Anand Agencies',
      'status': 'APPROVED',
      'lines': [
        {
          'id': 'si-line-1',
          'line_number': 1,
          'product_id': 'prod-1',
          'product_name': 'Toothpaste 150g',
          'current_invoice_quantity': '5',
          'unit_price': '50',
        },
      ],
    });

void main() {
  for (final MapEntry<String, ReturnableDocument> doc in {
    'a delivery note': _note(),
    'a bill': _bill(),
  }.entries)
  testWidgets('9999 against ${doc.key} line of 5 is refused in words',
      (tester) async {
    tester.view.physicalSize = const Size(1366, 768);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Phase2Scope(
          child: SalesReturnEditorDialog(
            documents: [doc.value],
            warehouses: [
              WarehouseRecord.fromJson({
                'id': 'wh-1',
                'code': 'MAIN',
                'name': 'Main',
                'is_default': true,
              }),
            ],
            today: DateTime(2026, 8, 20),
          ),
        ),
      ),
    ));
    await tester.pumpAndSettle();
    await chooseReturnDocument(tester, doc.value.number);
    await tester.enterText(
        find.byKey(ValueKey<String>('sales-return-returning-${doc.value.id}-0')),
        '9999');
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey<String>('sales-return-save')));
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey<String>('sales-return-save')),
        findsOneWidget);
    expect(find.textContaining('only 5 went out'), findsOneWidget);
  });
}
