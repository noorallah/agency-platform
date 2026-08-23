// A firm can raise an invoice from the desktop.
//
// Until 2026-08-23 it could not. There was no invoice editor, no "bill this
// delivery note" action, and no call that POSTed to `/api/v1/sales-invoices`
// anywhere in `desktop/lib` — so a firm using only the desktop could quote,
// order and dispatch, and then had no way to bill. The route had worked all
// along and `SALES_INVOICE_CREATE` was seeded with no screen checking it.
//
// Two behaviours carry the weight here. The picker offers only documents with
// something left to bill, because a client cannot know how much of a delivery
// line earlier invoices already took. And a quantity above what is left is
// refused before the round trip, with the remainder named.

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/sales/sales_invoice_editor_dialog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Json _billable({
  String remaining = '4',
  String alreadyInvoiced = '0',
  String discountPercent = '0',
}) =>
    <String, dynamic>{
      'source_document_type': 'DELIVERY_NOTE',
      'source_document_id': 'dn-1',
      'source_document_number': 'DN-2026-2027-000004',
      'document_date': '2026-08-04',
      'customer_id': 'cust-1',
      'customer_name': 'Anand Agencies',
      'branch_id': 'branch-1',
      'lines': <Json>[
        <String, dynamic>{
          'source_document_line_id': 'dnl-1',
          'line_number': 1,
          'product_id': 'p-1',
          'description': 'Shampoo Bottle 180ml',
          'source_quantity': '4',
          'already_invoiced_quantity': alreadyInvoiced,
          'remaining_quantity': remaining,
          'unit_price': '100',
          'discount_percent': discountPercent,
          'free_quantity': '0',
        },
      ],
    };

class _InvoiceApi extends ApiClient {
  _InvoiceApi({this.billable = const []})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Json> billable;

  /// The draft an edit reads back, when one is being corrected.
  Json? existing;

  Json? created;
  Json? updated;
  int? sentVersion;
  String? refuseWith;

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
    if (path.contains('billable')) {
      return <String, dynamic>{'data': billable};
    }
    if (method == 'GET' && path.startsWith('/api/v1/sales-invoices/')) {
      return <String, dynamic>{'data': existing};
    }
    if (method == 'PUT' && path.startsWith('/api/v1/sales-invoices/')) {
      if (refuseWith != null) {
        throw ApiException(refuseWith!, statusCode: 409);
      }
      updated = body;
      sentVersion = expectedVersion;
      return <String, dynamic>{'data': existing};
    }
    if (method == 'POST' && path.endsWith('/sales-invoices')) {
      if (refuseWith != null) {
        throw ApiException(refuseWith!, statusCode: 422);
      }
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
  _InvoiceApi api, {
  String? invoiceId,
}) async {
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
              today: DateTime(2026, 8, 14),
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

void main() {
  testWidgets('a delivery note with something left to bill can be invoiced',
      (tester) async {
    final _InvoiceApi api = _InvoiceApi(billable: <Json>[_billable()]);
    await _pump(tester, api);

    // One document, so it is chosen for the user rather than made a step.
    expect(find.textContaining('DN-2026-2027-000004'), findsWidgets);
    expect(find.textContaining('Billed before tax: 400.00'), findsOneWidget);

    await tester.tap(find.widgetWithText(FilledButton, 'Create draft'));
    await tester.pumpAndSettle();

    final Json sent = api.created!;
    expect(sent['customer_id'], 'cust-1');
    expect(sent['invoice_date'], '2026-08-14');
    final Map<String, dynamic> line =
        Map<String, dynamic>.from((sent['lines'] as List).single as Map);
    expect(line['source_document_type'], 'DELIVERY_NOTE');
    expect(line['source_document_id'], 'dn-1');
    expect(line['source_document_line_id'], 'dnl-1');
    // Defaulted to what is left, which is the number the save accepts.
    expect(line['current_invoice_quantity'], '4');
    expect(line['unit_price'], '100');
  });

  testWidgets('a partly billed note offers only the remainder',
      (tester) async {
    final _InvoiceApi api = _InvoiceApi(
      billable: <Json>[_billable(remaining: '3', alreadyInvoiced: '1')],
    );
    await _pump(tester, api);

    expect(find.textContaining('already billed 1'), findsOneWidget);
    expect(find.textContaining('Billed before tax: 300.00'), findsOneWidget);
  });

  testWidgets('billing more than is left is refused before it is sent',
      (tester) async {
    // The goods left on somebody else's document; a bill claiming more than
    // went out is one the warehouse cannot reconcile.
    final _InvoiceApi api = _InvoiceApi(billable: <Json>[_billable()]);
    await _pump(tester, api);

    await tester.enterText(find.widgetWithText(TextFormField, 'Bill'), '9');
    await tester.tap(find.widgetWithText(FilledButton, 'Create draft'));
    await tester.pumpAndSettle();

    expect(find.text('Only 4.0 left to bill.'), findsOneWidget);
    expect(api.created, isNull);
  });

  testWidgets('a line billed at nothing is left off the invoice',
      (tester) async {
    // Sent as a zero the server would price and store it, and an invoice
    // carrying a line for nothing is one the customer queries.
    final _InvoiceApi api = _InvoiceApi(billable: <Json>[_billable()]);
    await _pump(tester, api);

    await tester.enterText(find.widgetWithText(TextFormField, 'Bill'), '0');
    await tester.tap(find.widgetWithText(FilledButton, 'Create draft'));
    await tester.pumpAndSettle();

    expect(api.created, isNull);
    expect(find.text('Bill at least one line.'), findsOneWidget);
  });

  testWidgets('a discount on the whole bill reaches the payload',
      (tester) async {
    final _InvoiceApi api = _InvoiceApi(billable: <Json>[_billable()]);
    await _pump(tester, api);

    await tester.enterText(
      find.widgetWithText(TextFormField, 'Discount on the whole bill %'),
      '10',
    );
    await tester.pumpAndSettle();
    expect(find.textContaining('Billed before tax: 360.00'), findsOneWidget);

    await tester.tap(find.widgetWithText(FilledButton, 'Create draft'));
    await tester.pumpAndSettle();

    expect(api.created!['bill_discount_percent'], '10');
  });

  testWidgets('no discount on the bill says nothing about one',
      (tester) async {
    final _InvoiceApi api = _InvoiceApi(billable: <Json>[_billable()]);
    await _pump(tester, api);

    await tester.tap(find.widgetWithText(FilledButton, 'Create draft'));
    await tester.pumpAndSettle();

    expect(api.created!.containsKey('bill_discount_percent'), isFalse);
  });

  testWidgets("the line's own discount is shown but not re-sent",
      (tester) async {
    // The invoice inherits it from the line it bills, so echoing it back
    // would turn an inherited rate into an explicit one — and an explicit
    // rate stops the customer's standing arrangement applying.
    final _InvoiceApi api = _InvoiceApi(
      billable: <Json>[_billable(discountPercent: '7.5')],
    );
    await _pump(tester, api);

    expect(find.textContaining('less 7.5%'), findsOneWidget);

    await tester.tap(find.widgetWithText(FilledButton, 'Create draft'));
    await tester.pumpAndSettle();

    final Map<String, dynamic> line =
        Map<String, dynamic>.from((api.created!['lines'] as List).single as Map);
    expect(line.containsKey('discount_percent'), isFalse);
  });

  testWidgets('nothing to bill explains itself rather than showing a form',
      (tester) async {
    final _InvoiceApi api = _InvoiceApi();
    await _pump(tester, api);

    expect(find.text('Nothing is waiting to be billed'), findsOneWidget);
    expect(
      tester
          .widget<FilledButton>(
              find.widgetWithText(FilledButton, 'Create draft'))
          .onPressed,
      isNull,
    );
  });


  group('correcting a draft', () {
    Json draft({String quantity = '2', int version = 5}) => <String, dynamic>{
          'id': 'inv-1',
          'invoice_number': 'SI-1',
          'invoice_date': '2026-08-10',
          'customer_id': 'cust-1',
          'branch_id': 'branch-1',
          'status': 'DRAFT',
          'version': version,
          'bill_discount_percent': '0',
          'lines': <Json>[
            <String, dynamic>{
              'source_document_type': 'DELIVERY_NOTE',
              'source_document_id': 'dn-1',
              'source_document_number': 'DN-2026-2027-000004',
              'source_document_line_id': 'dnl-1',
              'line_number': 1,
              'description': 'Shampoo Bottle 180ml',
              'current_invoice_quantity': quantity,
              'unit_price': '100',
              'discount_percent': '0',
            },
          ],
        };

    testWidgets('a draft opens on what it already bills', (tester) async {
      // Before this a mistyped draft could only be cancelled and re-raised:
      // `PUT /api/v1/sales-invoices/{id}` existed and nothing called it.
      final _InvoiceApi api = _InvoiceApi(
        billable: <Json>[_billable(remaining: '2', alreadyInvoiced: '2')],
      )..existing = draft();
      await _pump(tester, api, invoiceId: 'inv-1');

      expect(find.text('Edit draft invoice'), findsOneWidget);
      expect(find.widgetWithText(FilledButton, 'Save'), findsOneWidget);
      // Two billed, priced at a hundred.
      expect(find.textContaining('Billed before tax: 200.00'), findsOneWidget);
    });

    testWidgets('a correction is sent as a PUT carrying the version',
        (tester) async {
      final _InvoiceApi api = _InvoiceApi(
        billable: <Json>[_billable(remaining: '2', alreadyInvoiced: '2')],
      )..existing = draft();
      await _pump(tester, api, invoiceId: 'inv-1');

      await tester.enterText(find.widgetWithText(TextFormField, 'Bill'), '3');
      await tester.tap(find.widgetWithText(FilledButton, 'Save'));
      await tester.pumpAndSettle();

      expect(api.created, isNull);
      final Map<String, dynamic> line =
          Map<String, dynamic>.from((api.updated!['lines'] as List).single as Map);
      expect(line['current_invoice_quantity'], '3');
      // Echoed back as `If-Match`, so a concurrent edit is refused rather
      // than silently overwritten.
      expect(api.sentVersion, 5);
    });

    testWidgets('a draft may keep what it bills plus whatever is still free',
        (tester) async {
      // The draft's own quantity counts against the source line, so the
      // ceiling is its own two plus the two still unbilled -- not two.
      final _InvoiceApi api = _InvoiceApi(
        billable: <Json>[_billable(remaining: '2', alreadyInvoiced: '2')],
      )..existing = draft();
      await _pump(tester, api, invoiceId: 'inv-1');

      await tester.enterText(find.widgetWithText(TextFormField, 'Bill'), '4');
      await tester.tap(find.widgetWithText(FilledButton, 'Save'));
      await tester.pumpAndSettle();

      expect(api.updated, isNotNull);
    });

    testWidgets('above that ceiling is still refused', (tester) async {
      final _InvoiceApi api = _InvoiceApi(
        billable: <Json>[_billable(remaining: '2', alreadyInvoiced: '2')],
      )..existing = draft();
      await _pump(tester, api, invoiceId: 'inv-1');

      await tester.enterText(find.widgetWithText(TextFormField, 'Bill'), '9');
      await tester.tap(find.widgetWithText(FilledButton, 'Save'));
      await tester.pumpAndSettle();

      expect(find.text('Only 4.0 left to bill.'), findsOneWidget);
      expect(api.updated, isNull);
    });

    testWidgets('a stale version shows the concurrency refusal',
        (tester) async {
      final _InvoiceApi api = _InvoiceApi(
        billable: <Json>[_billable(remaining: '2', alreadyInvoiced: '2')],
      )
        ..existing = draft()
        ..refuseWith = 'This invoice was changed by somebody else.';
      await _pump(tester, api, invoiceId: 'inv-1');

      await tester.tap(find.widgetWithText(FilledButton, 'Save'));
      await tester.pumpAndSettle();

      expect(
        find.text('This invoice was changed by somebody else.'),
        findsOneWidget,
      );
    });

    testWidgets('a fully billed source can still have its draft edited',
        (tester) async {
      // It is absent from the billable list, so the dropdown needs the item
      // added back or it asserts on a value it cannot find.
      final _InvoiceApi api = _InvoiceApi()..existing = draft(quantity: '4');
      await _pump(tester, api, invoiceId: 'inv-1');

      expect(find.text('Edit draft invoice'), findsOneWidget);
      expect(find.textContaining('Billed before tax: 400.00'), findsOneWidget);
    });
  });

  testWidgets("a refusal from the server is shown in the server's words",
      (tester) async {
    final _InvoiceApi api = _InvoiceApi(billable: <Json>[_billable()])
      ..refuseWith = 'No open accounting period covers 2026-08-14.';
    await _pump(tester, api);

    await tester.tap(find.widgetWithText(FilledButton, 'Create draft'));
    await tester.pumpAndSettle();

    expect(
      find.text('No open accounting period covers 2026-08-14.'),
      findsOneWidget,
    );
  });
}
