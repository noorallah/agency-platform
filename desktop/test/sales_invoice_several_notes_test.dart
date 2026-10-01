// One sales invoice bills several delivery notes (D-SELL-39, 2026-09-30).
//
// The server always accepted it -- every invoice line names its own source and
// the sources are checked against each other -- but the phase 2 editor offered
// a single "Bill this delivery note" picker, so a customer with three notes in
// a week was billed three times. These pin the "Also bill" control: only notes
// of the same customer and branch are offered, both notes' lines go in one
// payload numbered 1..n, and a draft made of two notes opens with both.

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/sales/sales_invoice_editor_dialog.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Json _note(
  String id,
  String number, {
  String customer = 'cust-1',
  String customerName = 'Anand Agencies',
  String branch = 'branch-1',
}) =>
    <String, dynamic>{
      'source_document_type': 'DELIVERY_NOTE',
      'source_document_id': id,
      'source_document_number': number,
      'document_date': '2026-08-04',
      'customer_id': customer,
      'customer_name': customerName,
      'branch_id': branch,
      'lines': <Json>[
        <String, dynamic>{
          'source_document_line_id': '$id-l1',
          'line_number': 1,
          'product_id': 'p-1',
          'description': 'Shampoo Bottle 180ml',
          'source_quantity': '4',
          'already_invoiced_quantity': '0',
          'remaining_quantity': '4',
          'unit_price': '100',
          'discount_percent': '0',
          'free_quantity': '0',
        },
        <String, dynamic>{
          'source_document_line_id': '$id-l2',
          'line_number': 2,
          'product_id': 'p-2',
          'description': 'Soap Bar 75g',
          'source_quantity': '10',
          'already_invoiced_quantity': '0',
          'remaining_quantity': '10',
          'unit_price': '20',
          'discount_percent': '0',
          'free_quantity': '0',
        },
      ],
    };

class _Api extends ApiClient {
  _Api({required this.billable})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Json> billable;
  Json? existing;
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
          'quotation_stage': true,
          'sales_order_stage': true,
          'delivery_note_stage': true,
          'is_configured': true,
        },
      };
    }
    if (path.contains('billable')) {
      return <String, dynamic>{'data': billable};
    }
    if (method == 'POST' && path == '/api/v1/sales-invoices/preview') {
      double subtotal = 0;
      final List<Json> priced = <Json>[];
      for (final dynamic raw in body!['lines'] as List<dynamic>) {
        final Json line = raw as Json;
        final double net = double.parse('${line['current_invoice_quantity']}') *
            double.parse('${line['unit_price']}');
        subtotal += net;
        priced.add(<String, dynamic>{
          'line_number': line['line_number'],
          'product_id': 'p-1',
          'source_document_line_id': line['source_document_line_id'],
          'discount_percent': '0',
          'discount_source': 'none',
          'net_amount': net.toStringAsFixed(4),
          'tax_amount': (net * .18).toStringAsFixed(4),
        });
      }
      return <String, dynamic>{
        'data': <String, dynamic>{
          'interstate': true,
          'invoice': <String, dynamic>{
            'invoice_number': 'SI-2026-2027-000014',
            'place_of_supply': '29-Karnataka',
            'subtotal': subtotal.toStringAsFixed(4),
            'tax_total': (subtotal * .18).toStringAsFixed(4),
            'grand_total': (subtotal * 1.18).toStringAsFixed(4),
            'lines': priced,
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
  _Api api, {
  String? invoiceId,
}) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Phase2Scope(
        child: SalesInvoiceEditorDialog(
          api: api,
          today: DateTime(2026, 8, 14),
          invoiceId: invoiceId,
        ),
      ),
    ),
  ));
  await tester.pumpAndSettle();
  await tester.pump(const Duration(milliseconds: 400));
  await tester.pumpAndSettle();
}

Future<void> _choosePrimary(WidgetTester tester, String number) async {
  await tester.tap(find.byKey(const ValueKey('sales-invoice-source')));
  await tester.pumpAndSettle();
  await tester.tap(find.textContaining(number).last);
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('a second note of the same customer is added to the bill',
      (tester) async {
    final _Api api = _Api(billable: <Json>[
      _note('dn-1', 'DN-000001'),
      _note('dn-2', 'DN-000002'),
      _note('dn-3', 'DN-000003',
          customer: 'cust-2', customerName: 'Bharat Traders'),
      _note('dn-4', 'DN-000004', branch: 'branch-2'),
    ]);
    await _pump(tester, api);
    expect(find.byKey(const ValueKey('sales-invoice-also-bill')), findsNothing);

    await _choosePrimary(tester, 'DN-000001');
    expect(tester.takeException(), isNull);
    expect(
        find.byKey(const ValueKey('sales-invoice-also-bill')), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('sales-invoice-also-bill')));
    await tester.pumpAndSettle();
    // Only the note of the same customer and branch is offered: not another
    // customer's, not another branch's, and not the one already chosen.
    expect(
        find.byKey(const ValueKey('sales-invoice-add-dn-2')), findsOneWidget);
    expect(find.byKey(const ValueKey('sales-invoice-add-dn-3')), findsNothing);
    expect(find.byKey(const ValueKey('sales-invoice-add-dn-4')), findsNothing);
    expect(find.byKey(const ValueKey('sales-invoice-add-dn-1')), findsNothing);
    await tester.tap(find.byKey(const ValueKey('sales-invoice-add-dn-2')));
    await tester.pumpAndSettle();
    await tester.pump(const Duration(milliseconds: 400));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);

    // Four rows now, each saying which note it is from.
    for (int i = 0; i < 4; i++) {
      expect(find.byKey(ValueKey<String>('sales-invoice-line-$i')),
          findsOneWidget);
    }
    expect(find.textContaining('DN-000002  ·  dispatched'), findsWidgets);
    expect(
        find.byKey(const ValueKey('sales-invoice-extra-dn-2')), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('sales-invoice-save')));
    await tester.pumpAndSettle();

    final List<dynamic> lines = api.created!['lines'] as List<dynamic>;
    expect(lines.length, 4);
    expect(
      [for (final dynamic l in lines) (l as Json)['source_document_id']],
      ['dn-1', 'dn-1', 'dn-2', 'dn-2'],
    );
    expect(
      [for (final dynamic l in lines) (l as Json)['line_number']],
      [1, 2, 3, 4],
    );
    expect(
      [for (final dynamic l in lines) (l as Json)['source_document_line_id']],
      ['dn-1-l1', 'dn-1-l2', 'dn-2-l1', 'dn-2-l2'],
    );
  });

  testWidgets('an added note comes off again with its lines', (tester) async {
    final _Api api = _Api(billable: <Json>[
      _note('dn-1', 'DN-000001'),
      _note('dn-2', 'DN-000002'),
    ]);
    await _pump(tester, api);
    await _choosePrimary(tester, 'DN-000001');
    await tester.tap(find.byKey(const ValueKey('sales-invoice-also-bill')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('sales-invoice-add-dn-2')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('sales-invoice-line-3')), findsOneWidget);

    await tester.tap(find.descendant(
      of: find.byKey(const ValueKey('sales-invoice-extra-dn-2')),
      matching: find.byType(Icon),
    ));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('sales-invoice-line-2')), findsNothing);

    await tester.tap(find.byKey(const ValueKey('sales-invoice-save')));
    await tester.pumpAndSettle();
    final List<dynamic> lines = api.created!['lines'] as List<dynamic>;
    expect(lines.length, 2);
    expect(
      {for (final dynamic l in lines) (l as Json)['source_document_id']},
      {'dn-1'},
    );
  });

  testWidgets('a draft made of two notes opens with both', (tester) async {
    Json line(String note, String lineId, String number, int no) =>
        <String, dynamic>{
          'source_document_type': 'DELIVERY_NOTE',
          'source_document_id': note,
          'source_document_number': number,
          'source_document_line_id': lineId,
          'line_number': no,
          'product_id': 'p-1',
          'description': 'Shampoo Bottle 180ml',
          'current_invoice_quantity': '2',
          'unit_price': '100',
          'discount_percent': '0',
        };
    final _Api api = _Api(billable: <Json>[])
      ..existing = <String, dynamic>{
        'id': 'inv-1',
        'invoice_number': 'SI-1',
        'invoice_date': '2026-08-10',
        'customer_id': 'cust-1',
        'customer_name': 'Anand Agencies',
        'branch_id': 'branch-1',
        'status': 'DRAFT',
        'version': 3,
        'bill_discount_percent': '0',
        'lines': <Json>[
          line('dn-1', 'dn-1-l1', 'DN-000001', 1),
          line('dn-2', 'dn-2-l1', 'DN-000002', 2),
        ],
      };
    await _pump(tester, api, invoiceId: 'inv-1');
    expect(tester.takeException(), isNull);
    expect(find.byKey(const ValueKey('sales-invoice-line-0')), findsOneWidget);
    expect(find.byKey(const ValueKey('sales-invoice-line-1')), findsOneWidget);
    expect(
        find.byKey(const ValueKey('sales-invoice-extra-dn-2')), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('sales-invoice-save')));
    await tester.pumpAndSettle();
    final List<dynamic> lines = api.updated!['lines'] as List<dynamic>;
    expect(
      [for (final dynamic l in lines) (l as Json)['source_document_id']],
      ['dn-1', 'dn-2'],
    );
    expect(
      [for (final dynamic l in lines) (l as Json)['line_number']],
      [1, 2],
    );
  });
}
