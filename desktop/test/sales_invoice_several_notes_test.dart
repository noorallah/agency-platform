// One sales invoice bills several delivery notes (D-SELL-39, 2026-09-30;
// SEL-1, 2026-10-03).
//
// The server always accepted it -- every invoice line names its own source and
// the sources are checked against each other. The screen now asks for the
// customer first and offers that customer's notes as a tick list, refusing on
// screen a note of another branch, salesman, territory or route and naming
// the note it clashes with. These pin the tick list, the payload of several
// notes numbered 1..n, and a draft of two notes opening with both.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/document_framework/document_steps.dart';
import 'package:agency_desktop/ui/sales/sales_document_steps.dart';
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
  String salesman = '',
  String salesmanName = '',
}) =>
    <String, dynamic>{
      'sales_order_number': 'SO-$number',
      'salesman_id': salesman.isEmpty ? null : salesman,
      'salesman_name': salesmanName,
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
  Size size = const Size(1366, 768),
  List<DocumentStep<Json>> steps = const [],
}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Phase2Scope(
        child: SalesInvoiceEditorDialog(
          api: api,
          today: DateTime(2026, 8, 14),
          invoiceId: invoiceId,
          steps: steps,
        ),
      ),
    ),
  ));
  await tester.pumpAndSettle();
  await tester.pump(const Duration(milliseconds: 400));
  await tester.pumpAndSettle();
}

Future<void> _chooseCustomer(WidgetTester tester, String name) async {
  await tester.tap(find.byKey(const ValueKey('sales-invoice-bill-customer')));
  await tester.pumpAndSettle();
  await tester.tap(find.text(name).last);
  await tester.pumpAndSettle();
}

Future<void> _tick(WidgetTester tester, String id) async {
  await tester.tap(find.byKey(ValueKey<String>('sales-invoice-tick-$id')));
  await tester.pumpAndSettle();
}

Future<void> _done(WidgetTester tester) async {
  await tester.tap(find.byKey(const ValueKey('sales-invoice-tick-done')));
  await tester.pumpAndSettle();
  await tester.pump(const Duration(milliseconds: 400));
  await tester.pumpAndSettle();
}

Checkbox _box(WidgetTester tester, String id) => tester
    .widget<Checkbox>(find.byKey(ValueKey<String>('sales-invoice-tick-$id')));

void main() {
  testWidgets('the customer comes first, then a tick list of their notes',
      (tester) async {
    final _Api api = _Api(billable: <Json>[
      _note('dn-1', 'DN-000001'),
      _note('dn-2', 'DN-000002'),
      _note('dn-3', 'DN-000003',
          customer: 'cust-2', customerName: 'Bharat Traders'),
      _note('dn-4', 'DN-000004', branch: 'branch-2'),
    ]);
    await _pump(tester, api);
    expect(
        find.byKey(const ValueKey('sales-invoice-choose-notes')), findsNothing);

    await _chooseCustomer(tester, 'Anand Agencies');
    expect(tester.takeException(), isNull);
    // The list opened by itself: the customer has more than one note. Another
    // customer's note is not in it.
    expect(
        find.byKey(const ValueKey('sales-invoice-tick-dn-1')), findsOneWidget);
    expect(find.byKey(const ValueKey('sales-invoice-tick-dn-3')), findsNothing);
    expect(find.text('SO-DN-000002'), findsOneWidget);
    // 4 x 100 + 10 x 20 left on each note.
    expect(find.textContaining('600.00'), findsNWidgets(3));

    await _tick(tester, 'dn-1');
    // Another branch's note cannot join, and says why.
    expect(_box(tester, 'dn-4').onChanged, isNull);
    expect(
      find.byKey(const ValueKey('sales-invoice-clash-dn-4')),
      findsOneWidget,
    );
    expect(find.textContaining('on DN-000001'), findsOneWidget);
    await _tick(tester, 'dn-2');
    await _done(tester);
    expect(tester.takeException(), isNull);

    for (int i = 0; i < 4; i++) {
      expect(find.byKey(ValueKey<String>('sales-invoice-line-$i')),
          findsOneWidget);
    }
    expect(find.textContaining('DN-000002  ·  dispatched'), findsWidgets);
    expect(
        find.byKey(const ValueKey('sales-invoice-note-dn-2')), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('sales-invoice-save')));
    await tester.pumpAndSettle();

    final List<dynamic> lines = api.created!['lines'] as List<dynamic>;
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

  testWidgets('a note of another salesman is refused on screen by name',
      (tester) async {
    final _Api api = _Api(billable: <Json>[
      _note('dn-1', 'DN-000001', salesman: 'u-1', salesmanName: 'Asha Rao'),
      _note('dn-2', 'DN-000002', salesman: 'u-2', salesmanName: 'Ravi Kumar'),
      _note('dn-5', 'DN-000005'),
    ]);
    await _pump(tester, api);
    await _chooseCustomer(tester, 'Anand Agencies');
    await _tick(tester, 'dn-1');

    expect(_box(tester, 'dn-2').onChanged, isNull);
    expect(
      find.text('Another salesman: Ravi Kumar here, Asha Rao on DN-000001'),
      findsOneWidget,
    );
    // A note naming no salesman may join either.
    expect(_box(tester, 'dn-5').onChanged, isNotNull);
    await _tick(tester, 'dn-5');
    await _done(tester);

    await tester.tap(find.byKey(const ValueKey('sales-invoice-save')));
    await tester.pumpAndSettle();
    final List<dynamic> lines = api.created!['lines'] as List<dynamic>;
    expect(
      {for (final dynamic l in lines) (l as Json)['source_document_id']},
      {'dn-1', 'dn-5'},
    );
  });

  testWidgets('unticking a note takes its lines off the bill', (tester) async {
    final _Api api = _Api(billable: <Json>[
      _note('dn-1', 'DN-000001'),
      _note('dn-2', 'DN-000002'),
    ]);
    await _pump(tester, api);
    await _chooseCustomer(tester, 'Anand Agencies');
    await _tick(tester, 'dn-1');
    await _tick(tester, 'dn-2');
    await _done(tester);
    expect(find.byKey(const ValueKey('sales-invoice-line-3')), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('sales-invoice-choose-notes')));
    await tester.pumpAndSettle();
    // The list reopens with what the bill holds ticked.
    expect(_box(tester, 'dn-2').value, isTrue);
    await _tick(tester, 'dn-1');
    await _done(tester);
    expect(find.byKey(const ValueKey('sales-invoice-line-2')), findsNothing);

    await tester.tap(find.byKey(const ValueKey('sales-invoice-save')));
    await tester.pumpAndSettle();
    final List<dynamic> lines = api.created!['lines'] as List<dynamic>;
    expect(
      {for (final dynamic l in lines) (l as Json)['source_document_id']},
      {'dn-2'},
    );
    expect(
      [for (final dynamic l in lines) (l as Json)['line_number']],
      [1, 2],
    );
  });

  // The delivery-note bill's band carries one more button than the counter
  // bill's (Save & print beside Save & print (F9)); with its own steps it
  // must still fit the 800x600 test window, and so must its line table.
  testWidgets('a bill from delivery notes fits 1366x768 and 800x600', (
    tester,
  ) async {
    for (final Size size in const <Size>[Size(1366, 768), Size(800, 600)]) {
      final _Api api = _Api(billable: <Json>[
        _note('dn-1', 'DN-000001'),
        _note('dn-2', 'DN-000002'),
      ]);
      final PermissionService approver = PermissionService()
        ..applyAccessToken(
          'header.${base64Url.encode(utf8.encode(jsonEncode({
                'roles': <String>['user'],
                'permissions': <String>['SALES_APPROVE', 'SALES_CANCEL'],
              }))).replaceAll('=', '')}.sig',
        );
      await _pump(
        tester,
        api,
        size: size,
        steps: salesInvoiceSteps(api, approver),
      );
      expect(
        find.byKey(const ValueKey('sales-invoice-save-print')),
        findsOneWidget,
      );
      expect(
        find.byKey(const ValueKey('sales-invoice-save-approve')),
        findsOneWidget,
      );
      await _chooseCustomer(tester, 'Anand Agencies');
      await _tick(tester, 'dn-1');
      await _tick(tester, 'dn-2');
      await _done(tester);
      expect(
        find.byKey(const ValueKey('sales-invoice-line-0')),
        findsOneWidget,
      );
      expect(tester.takeException(), isNull, reason: '$size');
      await tester.pumpWidget(const SizedBox());
    }
  });

  testWidgets("a customer's only note is ticked without asking",
      (tester) async {
    final _Api api = _Api(billable: <Json>[
      _note('dn-1', 'DN-000001'),
      _note('dn-3', 'DN-000003',
          customer: 'cust-2', customerName: 'Bharat Traders'),
    ]);
    await _pump(tester, api);
    await _chooseCustomer(tester, 'Bharat Traders');
    await tester.pump(const Duration(milliseconds: 400));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('sales-invoice-tick-done')), findsNothing);
    expect(
        find.byKey(const ValueKey('sales-invoice-note-dn-3')), findsOneWidget);
    expect(find.byKey(const ValueKey('sales-invoice-line-1')), findsOneWidget);
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
        find.byKey(const ValueKey('sales-invoice-note-dn-2')), findsOneWidget);
    // A draft keeps its notes: changing them is raising another bill.
    expect(
        find.byKey(const ValueKey('sales-invoice-choose-notes')), findsNothing);

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

  // D-UI-18: the "Choose the customer first" hint stays in the widget tree
  // after a choice, but a DropdownMenu hint is faded to nothing once the box
  // holds text. It is invisible, not a defect.
  testWidgets('the customer hint is not visible once a customer is chosen',
      (tester) async {
    final _Api api = _Api(billable: <Json>[
      _note('dn-1', 'DN-000001'),
      _note('dn-3', 'DN-000003',
          customer: 'cust-2', customerName: 'Bharat Traders'),
    ]);
    await _pump(tester, api);
    double hintOpacity() => find
        .ancestor(
          of: find.text('Choose the customer first'),
          matching: find.byType(AnimatedOpacity),
        )
        .evaluate()
        .map((e) => (e.widget as AnimatedOpacity).opacity)
        .first;

    expect(hintOpacity(), 1.0, reason: 'shown while the box is empty');
    await _chooseCustomer(tester, 'Anand Agencies');
    expect(hintOpacity(), 0.0, reason: 'faded out once a customer is chosen');
  });
}
