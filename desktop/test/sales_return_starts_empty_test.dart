// D-UI-22: a new sales return starts with no source document chosen.

import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/sales_return.dart';
import 'package:agency_desktop/ui/sales_returns/sales_return_editor_dialog.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'support/return_document.dart';

ReturnableDocument _note(String id, String number) =>
    ReturnableDocument.fromDeliveryNote({
      'id': id,
      'delivery_note_number': number,
      'delivery_date': '2026-08-10',
      'customer_name': 'Anand Agencies',
      'status': 'DISPATCHED',
      'lines': [
        {
          'id': '$id-line-1',
          'line_number': 1,
          'product_id': 'prod-1',
          'product_name': 'Toothpaste 150g',
          'current_delivery_quantity': '5',
          'unit_price': '50',
        },
      ],
    });

Future<List<Object?>> _open(WidgetTester tester, {required bool phase2}) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final List<Object?> saved = [];
  final Widget editor = SalesReturnEditorDialog(
    documents: [_note('dn-1', 'DN-1'), _note('dn-2', 'DN-2')],
    warehouses: [
      WarehouseRecord.fromJson({
        'id': 'wh-1',
        'code': 'MAIN',
        'name': 'Main',
        'is_default': true,
      }),
    ],
    today: DateTime(2026, 8, 20),
  );
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Builder(
        builder: (context) => TextButton(
          onPressed: () async {
            saved.add(await Navigator.of(context).push<Object?>(
              MaterialPageRoute<Object?>(
                builder: (_) => Scaffold(
                  body: phase2 ? Phase2Scope(child: editor) : editor,
                ),
              ),
            ));
          },
          child: const Text('open'),
        ),
      ),
    ),
  ));
  await tester.tap(find.text('open'));
  await tester.pumpAndSettle();
  return saved;
}

void main() {
  testWidgets('phase 1 opens with no document and Save says so',
      (tester) async {
    final List<Object?> saved = await _open(tester, phase2: false);
    expect(find.textContaining('DN-1'), findsNothing);
    await tester.tap(find.widgetWithText(FilledButton, 'Create draft'));
    await tester.pumpAndSettle();
    expect(find.text('Choose the document the goods went out on.'),
        findsOneWidget);
    expect(saved, isEmpty);

    await chooseReturnDocument(tester, 'DN-2');
    expect(find.textContaining('DN-2'), findsWidgets);
  });

  testWidgets('phase 2 opens with no document and Save says so',
      (tester) async {
    final List<Object?> saved = await _open(tester, phase2: true);
    expect(find.textContaining('against DN-'), findsNothing);
    await tester.tap(find.byKey(const ValueKey<String>('sales-return-save')));
    await tester.pumpAndSettle();
    expect(
      find.textContaining('Choose the delivery note or invoice'),
      findsOneWidget,
    );
    expect(saved, isEmpty);

    await chooseReturnDocument(tester, 'DN-2');
    expect(find.textContaining('against DN-2'), findsOneWidget);
  });
}
