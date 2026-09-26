// The phase 2 sales return screen (2026-09-26): every line of the source
// document in one table, so one return can bring back several products, and
// the credit priced as it is typed by `POST /sales-returns/preview`.

import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/document_preview.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/sales_return.dart';
import 'package:agency_desktop/ui/sales_returns/sales_return_editor_dialog.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// A dispatched note of two lines: 5 toothpaste at 50, 3 soap at 30.
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
        {
          'id': 'dn-line-2',
          'line_number': 2,
          'product_id': 'prod-2',
          'product_name': 'Soap 100g',
          'current_delivery_quantity': '3',
          'unit_price': '30',
        },
      ],
    });

/// Prices each draft at 18% within the state, the way the server would.
Future<SalesReturnPreviewRecord> _price(
  Json draft,
  List<Json> asked,
) async {
  asked.add(draft);
  const Map<String, double> prices = {'dn-line-1': 50, 'dn-line-2': 30};
  double subtotal = 0;
  final List<Json> lines = [];
  for (final dynamic raw in draft['lines'] as List<dynamic>) {
    final Json line = raw as Json;
    final double gross = double.parse('${line['current_return_quantity']}') *
        prices['${line['source_document_line_id']}']!;
    subtotal += gross;
    lines.add({
      'line_number': line['line_number'],
      'source_document_line_id': line['source_document_line_id'],
      'gross_amount': gross.toStringAsFixed(2),
      'discount_amount': '0',
      'bill_discount_amount': '0',
      'tax_amount': (gross * .18).toStringAsFixed(2),
    });
  }
  return SalesReturnPreviewRecord.fromJson({
    'sales_return': {
      'return_number': 'SR-2026-000003',
      'subtotal': subtotal.toStringAsFixed(2),
      'tax_total': (subtotal * .18).toStringAsFixed(2),
      'grand_total': (subtotal * 1.18).toStringAsFixed(2),
      'lines': lines,
    },
    'interstate': false,
    'lines': const [],
  });
}

void main() {
  testWidgets('phase 2 returns several lines at once, priced as typed',
      (tester) async {
    tester.view.physicalSize = const Size(1600, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final List<Json> asked = <Json>[];
    Json? saved;
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Builder(
          builder: (context) => TextButton(
            onPressed: () async {
              saved = await Navigator.of(context).push<Json>(
                MaterialPageRoute<Json>(
                  builder: (_) => Scaffold(
                    body: Phase2Scope(
                      child: SalesReturnEditorDialog(
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
                        preview: (draft) => _price(draft, asked),
                      ),
                    ),
                  ),
                ),
              );
            },
            child: const Text('open'),
          ),
        ),
      ),
    ));
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);

    // Both lines are on screen and nothing is coming back yet.
    expect(find.text('Toothpaste 150g'), findsOneWidget);
    expect(find.text('Soap 100g'), findsOneWidget);
    expect(asked, isEmpty);

    await tester.enterText(
      find.byKey(const ValueKey<String>('sales-return-returning-dn-1-0')),
      '2',
    );
    await tester.enterText(
      find.byKey(const ValueKey<String>('sales-return-returning-dn-1-1')),
      '1',
    );
    await tester.pump(const Duration(milliseconds: 400));
    await tester.pumpAndSettle();

    // 2 x 50 + 1 x 30 = 130, and 18% of it: 153.40.
    expect(asked.last['lines'], hasLength(2));
    expect(find.textContaining('153.40', findRichText: true), findsWidgets);
    expect(find.text('SR-2026-000003 (new)'), findsOneWidget);

    // More than went out is refused on the form.
    await tester.enterText(
      find.byKey(const ValueKey<String>('sales-return-returning-dn-1-1')),
      '4',
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('sales-return-save')));
    await tester.pumpAndSettle();
    expect(find.textContaining('only 3 went out'), findsOneWidget);
    expect(saved, isNull);

    await tester.enterText(
      find.byKey(const ValueKey<String>('sales-return-returning-dn-1-1')),
      '1',
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('sales-return-save')));
    await tester.pumpAndSettle();
    final List<dynamic> lines = saved!['lines'] as List<dynamic>;
    expect(lines, hasLength(2));
    expect((lines[1] as Json)['source_document_line_id'], 'dn-line-2');
    expect((lines[1] as Json)['line_number'], 2);
    expect(saved!['warehouse_id'], 'wh-1');
  });
}
