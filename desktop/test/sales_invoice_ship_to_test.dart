// Where a sales invoice says the goods went (backlog 67 row 3), in the
// phase 2 editor.
//
// A new bill leaves the box at "(as delivered)" and sends null, which is
// what lets the server take the address from the notes billed; naming one
// is an explicit choice. Reopening a draft shows the address it saved.

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/customer.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/sales/sales_invoice_editor_dialog.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Json _address(String id, String line1, String city, {bool shipping = false}) =>
    <String, dynamic>{
      'id': id,
      'address_type': 'SHIPPING',
      'address_line1': line1,
      'address_line2': '',
      'area': '',
      'city': city,
      'district': '',
      'state': 'Maharashtra',
      'country': 'India',
      'postal_code': '411001',
      'is_default_billing': false,
      'is_default_shipping': shipping,
    };

Json _billable() => <String, dynamic>{
      'source_document_type': 'DELIVERY_NOTE',
      'source_document_id': 'dn-1',
      'source_document_number': 'DN-2026-2027-000004',
      'document_date': '2026-08-04',
      'customer_id': 'c1',
      'customer_name': 'Anand Agencies',
      'branch_id': 'branch-1',
      'lines': <Json>[
        <String, dynamic>{
          'source_document_line_id': 'dnl-1',
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
      ],
    };

/// A draft bill of that note, saved with the Pune address.
Json _draft() => <String, dynamic>{
      'id': 'inv-1',
      'version': 2,
      'invoice_number': 'SI-2026-2027-000014',
      'status': 'DRAFT',
      'customer_id': 'c1',
      'shipping_address_id': 'a-pune',
      'lines': <Json>[
        <String, dynamic>{
          'source_document_type': 'DELIVERY_NOTE',
          'source_document_id': 'dn-1',
          'source_document_line_id': 'dnl-1',
          'line_number': 1,
          'product_id': 'p-1',
          'current_invoice_quantity': '4',
          'unit_price': '100',
        },
      ],
    };

class _InvoiceApi extends ApiClient {
  _InvoiceApi({this.existing})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final Json? existing;
  Json? created;
  Json? updated;

  @override
  Future<Customer> customer(String id) async =>
      Customer.fromJson(<String, dynamic>{
        'id': 'c1',
        'code': 'C1',
        'name': 'Anand Agencies',
        'display_name': 'Anand Agencies',
        'customer_type': 'BUSINESS',
        'status': 'ACTIVE',
        'addresses': <Json>[
          _address('a-pune', '9 Depot Lane', 'Pune'),
          _address('a-nashik', '4 Dock Street', 'Nashik', shipping: true),
        ],
      });

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
      return <String, dynamic>{'data': <Json>[_billable()]};
    }
    if (method == 'POST' && path == '/api/v1/sales-invoices/preview') {
      return <String, dynamic>{
        'data': <String, dynamic>{
          'interstate': false,
          'invoice': <String, dynamic>{
            'invoice_number': 'SI-2026-2027-000014',
            'subtotal': '400.0000',
            'tax_total': '72.0000',
            'grand_total': '472.0000',
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

Future<void> _open(WidgetTester tester, _InvoiceApi api, {String? id}) async {
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
                    invoiceId: id,
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

Future<void> _save(WidgetTester tester) async {
  await tester.tap(find.byKey(const ValueKey('sales-invoice-save')));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('a new bill is left "as delivered" and sends null',
      (tester) async {
    final _InvoiceApi api = _InvoiceApi();
    await _open(tester, api);
    expect(find.byKey(const ValueKey('sales-invoice-ship-to')), findsOneWidget);
    expect(find.text('(as delivered)'), findsOneWidget);
    await _save(tester);
    expect(api.created!.containsKey('shipping_address_id'), isTrue);
    expect(api.created!['shipping_address_id'], isNull);
  });

  testWidgets('naming an address sends it', (tester) async {
    final _InvoiceApi api = _InvoiceApi();
    await _open(tester, api);
    await tester.tap(find.byKey(const ValueKey('sales-invoice-ship-to')));
    await tester.pumpAndSettle();
    await tester.tap(find.textContaining('4 Dock Street, Nashik').last);
    await tester.pumpAndSettle();
    await _save(tester);
    expect(api.created!['shipping_address_id'], 'a-nashik');
  });

  testWidgets('reopening a draft shows the address it saved', (tester) async {
    final _InvoiceApi api = _InvoiceApi(existing: _draft());
    await _open(tester, api, id: 'inv-1');
    expect(find.textContaining('9 Depot Lane, Pune'), findsOneWidget);
    await _save(tester);
    expect(api.updated!['shipping_address_id'], 'a-pune');
  });
}
