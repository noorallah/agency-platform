// D-STK-15: a bill that ships its own goods names the units going out.
//
// With the delivery-note stage automatic the bill is the document that issues
// the stock, and since D-STK-4 the server refuses a serial-tracked line that
// does not name one serial per unit. The editor had no picker, so such a firm
// could not bill a mixer grinder from the desktop at all -- driven on the
// electronics fixture: the editor's own body was refused with "is
// serial-tracked: name the serial numbers going out on the bill line".

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/sales/sales_invoice_editor_dialog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

class _SerialApi extends ApiClient {
  _SerialApi({
    required this.salesOrderStage,
    this.billable = const [],
    this.existing,
  })
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final bool salesOrderStage;
  final List<Json> billable;
  final Json? existing;
  final List<Map<String, String>> serialQueries = <Map<String, String>>[];
  Json? created;
  Json? updated;

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
          'sales_order_stage': salesOrderStage,
          'delivery_note_stage': false,
          'default_warehouse_id': 'wh-main',
          'is_configured': true,
        },
      };
    }
    if (path.contains('billable')) return <String, dynamic>{'data': billable};
    if (method == 'GET' && path.startsWith('/api/v1/customers')) {
      return <String, dynamic>{
        'data': <Json>[
          <String, dynamic>{'id': 'cust-1', 'name': 'Walk-in Customer'},
        ],
      };
    }
    if (method == 'GET' && path.startsWith('/api/v1/products')) {
      return <String, dynamic>{
        'data': <Json>[
          <String, dynamic>{
            'id': 'mixer',
            'name': 'Mixer Grinder',
            'track_serial': true,
          },
        ],
      };
    }
    if (path.contains('batch-serial/serials')) {
      serialQueries.add(Map<String, String>.from(query ?? const {}));
      return <String, dynamic>{
        'data': <Json>[
          for (int n = 1; n <= 3; n++)
            <String, dynamic>{
              'id': 'serial-$n',
              'product_id': query?['product_id'] ?? '',
              'warehouse_id': query?['warehouse_id'] ?? '',
              'serial_number': 'MIX-000$n',
              'status': 'AVAILABLE',
            },
        ],
        'pagination': <String, dynamic>{'total_records': 3},
      };
    }
    if (method == 'GET' && path == '/api/v1/sales-invoices/inv-1') {
      return <String, dynamic>{'data': existing};
    }
    if (method == 'PUT' && path == '/api/v1/sales-invoices/inv-1') {
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

Future<void> _pump(WidgetTester tester, _SerialApi api,
    {String? invoiceId}) async {
  tester.view.physicalSize = const Size(1600, 1200);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Builder(
        builder: (context) => TextButton(
          onPressed: () => showDialog<bool>(
            context: context,
            builder: (_) => SalesInvoiceEditorDialog(
              api: api,
              today: DateTime(2026, 9, 19),
              invoiceId: invoiceId,
            ),
          ),
          child: const Text('open'),
        ),
      ),
    ),
  ));
  await tester.tap(find.text('open'));
  await tester.pumpAndSettle();
}

Json _orderToBill() => <String, dynamic>{
      'source_document_type': 'SALES_ORDER',
      'source_document_id': 'so-1',
      'source_document_number': 'SO-2026-2027-000001',
      'document_date': '2026-09-19',
      'customer_id': 'cust-1',
      'customer_name': 'Walk-in Customer',
      'branch_id': 'branch-1',
      'lines': <Json>[
        <String, dynamic>{
          'source_document_line_id': 'sol-1',
          'line_number': 1,
          'product_id': 'mixer',
          'description': 'Mixer Grinder',
          'source_quantity': '2',
          'already_invoiced_quantity': '0',
          'remaining_quantity': '2',
          'unit_price': '3000',
          'discount_percent': '0',
          'free_quantity': '0',
          'track_serial': true,
          'warehouse_id': 'wh-order',
        },
      ],
    };

void main() {
  testWidgets('a direct bill of a serial-tracked product names its units',
      (tester) async {
    final _SerialApi api = _SerialApi(salesOrderStage: false);
    await _pump(tester, api);

    await tester.tap(find.byType(DropdownButtonFormField<String>).first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Walk-in Customer').last);
    await tester.pumpAndSettle();
    await tester.tap(find.byType(DropdownButtonFormField<String>).last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Mixer Grinder').last);
    await tester.pumpAndSettle();
    await tester.enterText(find.widgetWithText(TextFormField, 'Qty'), '2');
    await tester.enterText(find.widgetWithText(TextFormField, 'Price'), '3000');
    await tester.pumpAndSettle();

    // The units on the firm's default shelf are offered.
    expect(api.serialQueries.single['warehouse_id'], 'wh-main');
    expect(api.serialQueries.single['status'], 'AVAILABLE');
    expect(find.text('MIX-0001'), findsOneWidget);

    // Short of units, the save is refused here rather than by the server.
    await tester.tap(find.widgetWithText(FilledButton, 'Create draft'));
    await tester.pumpAndSettle();
    expect(api.created, isNull);
    expect(find.textContaining('2 needed, 0 picked'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey<String>('serial-pick-serial-1')));
    await tester.tap(find.byKey(const ValueKey<String>('serial-pick-serial-3')));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Create draft'));
    await tester.pumpAndSettle();

    final Map<String, dynamic> line = Map<String, dynamic>.from(
        (api.created!['lines'] as List).single as Map);
    expect(line['serial_ids'], <String>['serial-1', 'serial-3']);
  });

  testWidgets('billing an order that ships on the bill names its units too',
      (tester) async {
    final _SerialApi api =
        _SerialApi(salesOrderStage: true, billable: <Json>[_orderToBill()]);
    await _pump(tester, api);

    // Offered off the shelf the order ships from.
    expect(api.serialQueries.single['warehouse_id'], 'wh-order');
    await tester.tap(find.byKey(const ValueKey<String>('serial-pick-serial-2')));
    await tester.tap(find.byKey(const ValueKey<String>('serial-pick-serial-3')));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Create draft'));
    await tester.pumpAndSettle();

    final Map<String, dynamic> line = Map<String, dynamic>.from(
        (api.created!['lines'] as List).single as Map);
    expect(line['serial_ids'], <String>['serial-2', 'serial-3']);
  });

  testWidgets('a dispatched note is billed without naming units',
      (tester) async {
    // The note picked them when it shipped; the server refuses them again.
    final Json note = _orderToBill()
      ..['source_document_type'] = 'DELIVERY_NOTE'
      ..['source_document_id'] = 'dn-1';
    final _SerialApi api =
        _SerialApi(salesOrderStage: true, billable: <Json>[note]);
    await _pump(tester, api);

    expect(find.textContaining('Serial numbers going out'), findsNothing);
    await tester.tap(find.widgetWithText(FilledButton, 'Create draft'));
    await tester.pumpAndSettle();

    final Map<String, dynamic> line = Map<String, dynamic>.from(
        (api.created!['lines'] as List).single as Map);
    expect(line.containsKey('serial_ids'), isFalse);
  });

  testWidgets('editing a draft that ships its own note re-offers the picker',
      (tester) async {
    // D-SELL-33: the saved draft bills the note it raised, so the editor saw
    // a note line and offered no picker; the units could not be changed.
    final Json draft = <String, dynamic>{
      'id': 'inv-1',
      'status': 'DRAFT',
      'invoice_date': '2026-09-19',
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
          'product_id': 'mixer',
          'warehouse_id': 'wh-order',
          'description': 'Mixer Grinder',
          'delivered_quantity': '2',
          'current_invoice_quantity': '2',
          'unit_price': '3000',
          'discount_percent': '0',
          'picks_serials': true,
          'serials': <Json>[
            <String, dynamic>{
              'serial_id': 'serial-1',
              'serial_number': 'MIX-0001',
              'status': 'AVAILABLE',
            },
            <String, dynamic>{
              'serial_id': 'serial-3',
              'serial_number': 'MIX-0003',
              'status': 'AVAILABLE',
            },
          ],
        },
      ],
    };
    final _SerialApi api =
        _SerialApi(salesOrderStage: true, existing: draft);
    await _pump(tester, api, invoiceId: 'inv-1');

    expect(find.textContaining('Serial numbers going out'), findsOneWidget);
    expect(api.serialQueries.single['warehouse_id'], 'wh-order');
    // Swap one unit for another and save.
    await tester.tap(find.byKey(const ValueKey<String>('serial-pick-serial-1')));
    await tester.tap(find.byKey(const ValueKey<String>('serial-pick-serial-2')));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    final Map<String, dynamic> line = Map<String, dynamic>.from(
        (api.updated!['lines'] as List).single as Map);
    expect(line['serial_ids'], <String>['serial-3', 'serial-2']);
  });
}
