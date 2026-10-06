// The phase 2 sales return screen (2026-09-26): every line of the source
// document in one table, so one return can bring back several products, and
// the credit priced as it is typed by `POST /sales-returns/preview`.

import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/document_preview.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/sales_return.dart';
import 'package:agency_desktop/ui/reports/report_catalog.dart';
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

/// A note of 12 charged and 1 free toothpaste, and 3 soap with none free.
ReturnableDocument _noteWithFree() => ReturnableDocument.fromDeliveryNote({
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
          'current_delivery_quantity': '12',
          'free_quantity': '1',
          'unit_price': '50',
        },
        {
          'id': 'dn-line-2',
          'line_number': 2,
          'product_id': 'prod-2',
          'product_name': 'Soap 100g',
          'current_delivery_quantity': '3',
          'free_quantity': '0',
          'unit_price': '30',
        },
      ],
    });

/// Opens the phase 2 editor at 1366x768 and returns what Save popped.
Future<void> _openEditor(
  WidgetTester tester,
  ReturnableDocument note,
  List<Json?> saved,
) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Builder(
        builder: (context) => TextButton(
          onPressed: () async {
            saved.add(await Navigator.of(context).push<Json>(
              MaterialPageRoute<Json>(
                builder: (_) => Scaffold(
                  body: Phase2Scope(
                    child: SalesReturnEditorDialog(
                      documents: [note],
                      warehouses: [
                        WarehouseRecord.fromJson({
                          'id': 'wh-1',
                          'code': 'MAIN',
                          'name': 'Main',
                          'is_default': true,
                        }),
                      ],
                      today: DateTime(2026, 8, 20),
                      preview: (draft) => _price(draft, <Json>[]),
                    ),
                  ),
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
}

void main() {
  testWidgets('the free box is on a line that shipped free goods and only '
      'there (D-PRC-8)', (tester) async {
    await _openEditor(tester, _noteWithFree(), <Json?>[]);
    expect(
        find.byKey(const ValueKey<String>('sales-return-free-dn-1-0')),
        findsOneWidget);
    expect(
        find.byKey(const ValueKey<String>('sales-return-free-dn-1-1')),
        findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a blank free box sends no free_quantity, a typed one sends it, '
      'and 13 may come back against 12 sent and 1 free', (tester) async {
    final List<Json?> saved = <Json?>[];
    await _openEditor(tester, _noteWithFree(), saved);

    // 13 is more than the 12 charged, but the line sent one free as well.
    await tester.enterText(
        find.byKey(const ValueKey<String>('sales-return-returning-dn-1-0')),
        '13');
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('sales-return-save')));
    await tester.pumpAndSettle();
    expect(saved.single!['lines'], isNotNull);
    Json line = (saved.single!['lines'] as List).single as Json;
    expect(line['current_return_quantity'], '13');
    expect(line.containsKey('free_quantity'), isFalse);

    saved.clear();
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    await tester.enterText(
        find.byKey(const ValueKey<String>('sales-return-returning-dn-1-0')),
        '1');
    await tester.enterText(
        find.byKey(const ValueKey<String>('sales-return-free-dn-1-0')), '1');
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('sales-return-save')));
    await tester.pumpAndSettle();
    line = (saved.single!['lines'] as List).single as Json;
    expect(line['current_return_quantity'], '1');
    expect(line['free_quantity'], '1');
  });

  testWidgets('free units go back as free with a quantity of 0 (D-PRC-51)',
      (tester) async {
    final List<Json?> saved = <Json?>[];
    await _openEditor(tester, _noteWithFree(), saved);

    // Nothing typed anywhere: the line is left off and the form says so.
    await tester.tap(find.byKey(const ValueKey('sales-return-save')));
    await tester.pumpAndSettle();
    expect(saved, isEmpty);

    // The free box alone, the returning box untouched at 0.
    await tester.enterText(
        find.byKey(const ValueKey<String>('sales-return-free-dn-1-0')), '1');
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('sales-return-save')));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    final Json line = (saved.single!['lines'] as List).single as Json;
    expect(line['current_return_quantity'], '0');
    expect(line['free_quantity'], '1');
    expect(line['damaged_quantity'], '0');
    expect(line['scrap_quantity'], '0');
    // The server works the restock out, so none is sent to disagree with it.
    expect(line.containsKey('restock_quantity'), isFalse);
  });

  testWidgets('more free than was sent free, or than comes back, is refused '
      'on the form', (tester) async {
    final List<Json?> saved = <Json?>[];
    await _openEditor(tester, _noteWithFree(), saved);
    await tester.enterText(
        find.byKey(const ValueKey<String>('sales-return-returning-dn-1-0')),
        '3');
    await tester.enterText(
        find.byKey(const ValueKey<String>('sales-return-free-dn-1-0')), '2');
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('sales-return-save')));
    await tester.pumpAndSettle();
    expect(find.textContaining('1 free'), findsWidgets);
    expect(saved, isEmpty);
  });

  test('a saved return line carries its free goods', () {
    final SalesReturnLine line = SalesReturnLine.fromJson({
      'id': 'l-1',
      'free_quantity': '1.0000',
      'current_return_quantity': '13.0000',
    });
    expect(line.freeQuantity, '1.0000');
  });

  test('the by-product return report names its free units', () {
    final Set<String> keys = reportCatalog
        .firstWhere((report) => report.id == 'sales-return-by-product')
        .columns
        .map((column) => column.key)
        .toSet();
    expect(keys, containsAll(<String>['return_quantity', 'free_quantity']));
  });

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
