// D-UI-37: a refused sales return leaves the editor open with the server's
// sentence and everything typed; a saved one closes it.

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/entities.dart' show Json;
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
          'current_delivery_quantity': '9',
          'unit_price': '50',
        },
      ],
    });

Future<void> _open(
  WidgetTester tester, {
  required bool phase2,
  required Future<void> Function(Json payload) onSave,
}) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final Widget editor = SalesReturnEditorDialog(
    documents: [_note()],
    warehouses: [
      WarehouseRecord.fromJson({
        'id': 'wh-1',
        'code': 'MAIN',
        'name': 'Main',
        'is_default': true,
      }),
    ],
    today: DateTime(2026, 8, 20),
    onSave: onSave,
  );
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(body: phase2 ? Phase2Scope(child: editor) : editor),
  ));
  await tester.pumpAndSettle();
  await chooseReturnDocument(tester, 'DN-2026-000001');
}

void main() {
  testWidgets('a refusal keeps the editor open with the sentence and the '
      'typing', (tester) async {
    int calls = 0;
    await _open(tester, phase2: true, onSave: (Json payload) async {
      calls++;
      throw ApiException(
        'Return quantity exceeds what left on DN-2026-000001 (9 sent, 7 '
        'already returned).',
        statusCode: 422,
      );
    });
    await tester.enterText(
        find.byKey(const ValueKey<String>('sales-return-returning-dn-1-0')),
        '4');
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey<String>('sales-return-save')));
    await tester.pumpAndSettle();

    expect(calls, 1);
    expect(find.byType(SalesReturnEditorDialog), findsOneWidget);
    expect(find.textContaining('9 sent, 7 already returned'), findsOneWidget);
    expect(
      tester
          .widget<EditableText>(find.descendant(
            of: find.byKey(
                const ValueKey<String>('sales-return-returning-dn-1-0')),
            matching: find.byType(EditableText),
          ))
          .controller
          .text,
      '4',
    );
  });

  testWidgets('the same in the older layout', (tester) async {
    await _open(tester, phase2: false, onSave: (Json payload) async {
      throw ApiException('Return quantity exceeds what left.',
          statusCode: 422);
    });
    await tester.tap(find.text('Create draft'));
    await tester.pumpAndSettle();

    expect(find.byType(SalesReturnEditorDialog), findsOneWidget);
    expect(find.textContaining('Return quantity exceeds'), findsOneWidget);
  });

  testWidgets('an accepted save writes the return once',
      (tester) async {
    final List<Json> written = <Json>[];
    await _open(tester, phase2: true, onSave: (Json payload) async {
      written.add(payload);
    });
    await tester.enterText(
        find.byKey(const ValueKey<String>('sales-return-returning-dn-1-0')),
        '2');
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey<String>('sales-return-save')));
    await tester.pumpAndSettle();

    expect(written, hasLength(1));
    expect(tester.takeException(), isNull);
  });
}
