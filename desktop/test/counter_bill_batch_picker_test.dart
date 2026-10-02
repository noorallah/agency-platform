// Backlog 79 row 2: a counter bill -- a sales invoice with no source document
// for a firm that types no delivery note -- chooses the batches its own note
// ships, with the delivery note's own picker, and sends them as `batches`.

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/batch_serial.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/sales/sales_invoice_editor_dialog.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

BatchAvailabilityRecord _batch(
  String id, {
  required String expiry,
  required int days,
  required double fefo,
  String? mrp,
  String? sellingPrice,
}) =>
    BatchAvailabilityRecord.fromJson(<String, dynamic>{
      'batch_id': id,
      'batch_number': 'BN-$id',
      'expiry_date': expiry,
      'days_to_expiry': days,
      'on_hand': '20',
      'reserved': '0',
      'available': '20',
      'available_to_line': '20',
      'expired': false,
      'near_expiry': false,
      'fefo': fefo.toString(),
      'mrp': mrp,
      'selling_price': sellingPrice,
    });

class _CounterApi extends ApiClient {
  _CounterApi({
    this.existing,
    this.defaultWarehouse = 'wh-main',
    this.priceFromBatch = false,
  })
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final Json? existing;
  final String? defaultWarehouse;
  final bool priceFromBatch;
  Json? created;
  Json? updated;
  final List<Json> previews = <Json>[];
  Map<String, Object?>? asked;

  @override
  Future<List<BatchAvailabilityRecord>> batchAvailability({
    required String productId,
    required String warehouseId,
    String? storageNodeId,
    String? asOf,
    num? quantity,
    String? salesOrderLineId,
    String? customerId,
  }) async {
    asked = {
      'product_id': productId,
      'warehouse_id': warehouseId,
      'as_of': asOf,
      'quantity': quantity,
      'customer_id': customerId,
    };
    if (priceFromBatch) {
      // One batch takes the whole quantity, and carries a price.
      return [
        _batch('old',
            expiry: '2026-12-01',
            days: 20,
            fefo: 10,
            mrp: '120',
            sellingPrice: '95.5'),
      ];
    }
    return [
      _batch('old', expiry: '2026-12-01', days: 20, fefo: 6),
      _batch('new', expiry: '2027-06-01', days: 200, fefo: 4),
    ];
  }

  @override
  Future<Json> request(
    String method,
    String path, {
    Json? body,
    Map<String, String>? query,
    bool authenticated = true,
    bool retrying = false,
    int? expectedVersion,
  }) async {
    if (path.contains('workflow-settings')) {
      return <String, dynamic>{
        'data': <String, dynamic>{
          'quotation_stage': false,
          'sales_order_stage': false,
          'delivery_note_stage': false,
          if (defaultWarehouse != null) 'default_warehouse_id': defaultWarehouse,
          'is_configured': true,
        },
      };
    }
    if (path.endsWith('/batch-serial/sale-settings')) {
      return <String, dynamic>{
        'data': <String, dynamic>{'price_from_batch': priceFromBatch},
      };
    }
    if (path.contains('billable')) return <String, dynamic>{'data': <Json>[]};
    if (method == 'GET' && path.startsWith('/api/v1/customers')) {
      return <String, dynamic>{
        'data': <Json>[
          <String, dynamic>{
            'id': 'cust-1',
            'code': 'C-1',
            'name': 'Walk-in Customer',
            'display_name': 'Walk-in Customer',
          },
        ],
      };
    }
    if (method == 'GET' && path.startsWith('/api/v1/products')) {
      return <String, dynamic>{
        'data': <Json>[
          <String, dynamic>{
            'id': 'prod-1',
            'code': 'P-1',
            'name': 'Paracetamol',
            'track_batch': true,
          },
        ],
      };
    }
    if (method == 'POST' && path == '/api/v1/sales-invoices/preview') {
      previews.add(body!);
      return <String, dynamic>{
        'data': <String, dynamic>{
          'interstate': false,
          'invoice': <String, dynamic>{
            'invoice_number': 'SI-1',
            'subtotal': '0',
            'tax_total': '0',
            'grand_total': '0',
            'lines': const <Json>[],
          },
          'lines': const <Json>[],
        },
      };
    }
    if (method == 'GET' && path.startsWith('/api/v1/sales-invoices/')) {
      return <String, dynamic>{'data': existing};
    }
    if (method == 'PUT' && path.startsWith('/api/v1/sales-invoices/')) {
      updated = body;
      return <String, dynamic>{'data': existing};
    }
    if (method == 'POST' && path.endsWith('/sales-invoices')) {
      created = body;
      return <String, dynamic>{
        'data': <String, dynamic>{'id': 'inv-1', 'invoice_number': 'SI-1'},
      };
    }
    return <String, dynamic>{'data': const <Json>[]};
  }
}

Future<void> _pump(
  WidgetTester tester,
  _CounterApi api, {
  String? invoiceId,
}) async {
  tester.view.physicalSize = const Size(1600, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Builder(
        builder: (context) => TextButton(
          onPressed: () => Navigator.of(context).push<bool>(
            MaterialPageRoute<bool>(
              builder: (_) => Scaffold(
                body: Phase2Scope(
                  child: SalesInvoiceEditorDialog(
                    api: api,
                    invoiceId: invoiceId,
                    today: DateTime(2026, 8, 14),
                  ),
                ),
              ),
            ),
          ),
          child: const Text('open'),
        ),
      ),
    ),
  ));
  await tester.tap(find.text('open'));
  await tester.pumpAndSettle();
  await tester.pump(const Duration(milliseconds: 400));
  await tester.pumpAndSettle();
}

Future<void> _fillCounterBill(WidgetTester tester, {String? rate = '40'}) async {
  await tester.tap(find.byKey(const ValueKey('sales-invoice-customer')));
  await tester.pumpAndSettle();
  await tester.tap(find.textContaining('Walk-in Customer').last);
  await tester.pumpAndSettle();
  await tester.tap(
      find.byKey(const ValueKey<String>('sales-invoice-direct-product-0')));
  await tester.pumpAndSettle();
  await tester.tap(find.textContaining('Paracetamol').last);
  await tester.pumpAndSettle();
  final Finder cells = find.descendant(
    of: find.byKey(const ValueKey<String>('sales-invoice-direct-0')),
    matching: find.byType(EditableText),
  );
  await tester.enterText(cells.at(1), '10');
  if (rate != null) await tester.enterText(cells.at(2), rate);
  await tester.pump(const Duration(milliseconds: 400));
  await tester.pumpAndSettle();
}

Json _draft() => <String, dynamic>{
      'id': 'inv-1',
      'status': 'DRAFT',
      'invoice_date': '2026-08-14',
      'customer_id': 'cust-1',
      'customer_name': 'Walk-in Customer',
      'branch_id': 'branch-1',
      'version': 1,
      'lines': <Json>[
        <String, dynamic>{
          'line_number': 1,
          'source_document_type': 'DELIVERY_NOTE',
          'source_document_id': 'dn-own',
          'source_document_number': 'DN-1',
          'source_document_line_id': 'dnl-1',
          'product_id': 'prod-1',
          'warehouse_id': 'wh-note',
          'description': 'Paracetamol',
          'delivered_quantity': '10',
          'current_invoice_quantity': '10',
          'unit_price': '40',
          'discount_percent': '0',
          'batches': <Json>[
            <String, dynamic>{'batch_id': 'old', 'quantity': '3'},
            <String, dynamic>{'batch_id': 'new', 'quantity': '7'},
          ],
        },
      ],
    };

void main() {
  testWidgets('a batch-tracked line offers the picker, earliest expiry first',
      (tester) async {
    final _CounterApi api = _CounterApi();
    await _pump(tester, api);
    await _fillCounterBill(tester);

    expect(find.byKey(const ValueKey('sales-invoice-batch-picker')),
        findsOneWidget);
    expect(find.text('BN-old'), findsOneWidget);
    expect(api.asked!['warehouse_id'], 'wh-main');
    expect(api.asked!['as_of'], '2026-08-14');
    expect(api.asked!['quantity'], 10);
    expect(api.asked!['customer_id'], 'cust-1');
    expect(find.textContaining('Chosen 10 of 10'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('choosing another split sends it as the line\'s batches',
      (tester) async {
    final _CounterApi api = _CounterApi();
    await _pump(tester, api);
    await _fillCounterBill(tester);

    await tester.enterText(
        find.byKey(const ValueKey<String>('batch-pick-direct-0-old')), '0');
    await tester.pump();
    await tester.enterText(
        find.byKey(const ValueKey<String>('batch-pick-direct-0-new')), '10');
    await tester.pump();
    expect(find.textContaining('Chosen 10 of 10'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('sales-invoice-save')));
    await tester.pumpAndSettle();

    final Map<String, dynamic> line = Map<String, dynamic>.from(
        (api.created!['lines'] as List).single as Map);
    final List<dynamic> batches = line['batches'] as List<dynamic>;
    expect(batches, hasLength(1));
    expect(batches.single['batch_id'], 'new');
    expect(num.parse('${batches.single['quantity']}'), 10);
    // Pricing the bill never carries the choice.
    expect(api.previews.every((p) => !(p['lines'] as List).any(
        (l) => (l as Map).containsKey('batches'))), isTrue);
  });

  testWidgets('a line whose picker was never touched sends no batches',
      (tester) async {
    final _CounterApi api = _CounterApi();
    await _pump(tester, api);
    await _fillCounterBill(tester);

    await tester.tap(find.byKey(const ValueKey('sales-invoice-save')));
    await tester.pumpAndSettle();

    final Map<String, dynamic> line = Map<String, dynamic>.from(
        (api.created!['lines'] as List).single as Map);
    expect(line.containsKey('batches'), isFalse);
  });

  testWidgets('"Use earliest expiry" sends an empty list', (tester) async {
    final _CounterApi api = _CounterApi();
    await _pump(tester, api);
    await _fillCounterBill(tester);

    await tester.enterText(
        find.byKey(const ValueKey<String>('batch-pick-direct-0-old')), '2');
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('sales-invoice-batch-reset')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('sales-invoice-save')));
    await tester.pumpAndSettle();

    final Map<String, dynamic> line = Map<String, dynamic>.from(
        (api.created!['lines'] as List).single as Map);
    expect(line['batches'], isEmpty);
  });

  testWidgets('with no default warehouse the picker says so and sends nothing',
      (tester) async {
    final _CounterApi api = _CounterApi(defaultWarehouse: null);
    await _pump(tester, api);
    await _fillCounterBill(tester);

    expect(api.asked, isNull);
    expect(find.textContaining('names no default warehouse'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('sales-invoice-save')));
    await tester.pumpAndSettle();
    final Map<String, dynamic> line = Map<String, dynamic>.from(
        (api.created!['lines'] as List).single as Map);
    expect(line.containsKey('batches'), isFalse);
  });

  testWidgets('an edited draft pre-fills from the note and sends it back',
      (tester) async {
    final _CounterApi api = _CounterApi(existing: _draft());
    await _pump(tester, api, invoiceId: 'inv-1');

    // Asked of the warehouse the note line ships from.
    expect(api.asked!['warehouse_id'], 'wh-note');
    TextField box(String id) => tester.widget<TextField>(find.descendant(
        of: find.byKey(ValueKey<String>('batch-pick-dnl-1-$id')),
        matching: find.byType(TextField)));
    expect(box('old').controller!.text, '3');
    expect(box('new').controller!.text, '7');
    expect(find.textContaining('Chosen 10 of 10'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('sales-invoice-save')));
    await tester.pumpAndSettle();

    final Map<String, dynamic> line = Map<String, dynamic>.from(
        (api.updated!['lines'] as List).single as Map);
    final List<dynamic> batches = line['batches'] as List<dynamic>;
    expect(batches.map((b) => b['batch_id']), <String>['old', 'new']);
    expect(num.parse('${batches[0]['quantity']}'), 3);
    expect(num.parse('${batches[1]['quantity']}'), 7);
  });

  group('price from batch (backlog 79 row 7)', () {
    testWidgets('the picker shows each batch MRP and price',
        (tester) async {
      final _CounterApi api = _CounterApi(priceFromBatch: true);
      await _pump(tester, api);
      await _fillCounterBill(tester, rate: null);

      expect(find.textContaining('MRP 120.00'), findsOneWidget);
      expect(find.textContaining('price 95.50'), findsOneWidget);
    });

    testWidgets('a single batch with a price sets the rate when none typed',
        (tester) async {
      final _CounterApi api = _CounterApi(priceFromBatch: true);
      await _pump(tester, api);
      await _fillCounterBill(tester, rate: null);

      await tester.tap(find.byKey(const ValueKey('sales-invoice-save')));
      await tester.pumpAndSettle();
      final Map<String, dynamic> line = Map<String, dynamic>.from(
          (api.created!['lines'] as List).single as Map);
      expect(num.parse('${line['unit_price']}'), 95.5);
    });

    testWidgets('a rate the person typed is left alone', (tester) async {
      final _CounterApi api = _CounterApi(priceFromBatch: true);
      await _pump(tester, api);
      await _fillCounterBill(tester);

      await tester.tap(find.byKey(const ValueKey('sales-invoice-save')));
      await tester.pumpAndSettle();
      final Map<String, dynamic> line = Map<String, dynamic>.from(
          (api.created!['lines'] as List).single as Map);
      expect(num.parse('${line['unit_price']}'), 40);
    });

    testWidgets('with the rule off the batch price is not used',
        (tester) async {
      final _CounterApi api = _CounterApi();
      await _pump(tester, api);
      await _fillCounterBill(tester, rate: null);
      // Two batches there, and the rule is off: no rate was set.
      await tester.tap(find.byKey(const ValueKey('sales-invoice-save')));
      await tester.pumpAndSettle();
      final Map<String, dynamic> line = Map<String, dynamic>.from(
          (api.created!['lines'] as List).single as Map);
      expect(num.tryParse('${line['unit_price']}') ?? 0, 0);
    });
  });
}
