// What a sales order says about where the goods go and on what terms
// (backlog 67 rows 3 and 4), in the phase 2 editor.
//
// Both are decisions the order records, so both are sent from the editor
// rather than left to the server's silence once the editor knows enough to
// say them: the ship-to address is preselected with the customer's default,
// and the credit terms are left blank unless somebody types them -- the
// customer's own days are shown beside the box, never filled into it.

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/sales/sales_order_editor_dialog.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/first_line.dart';

Json _address(
  String id,
  String type,
  String line1,
  String city, {
  bool shipping = false,
}) =>
    <String, dynamic>{
      'id': id,
      'address_type': type,
      'address_line1': line1,
      'address_line2': '',
      'area': '',
      'city': city,
      'district': '',
      'state': 'Maharashtra',
      'country': 'India',
      'postal_code': '411001',
      'is_default_billing': type == 'BILLING',
      'is_default_shipping': shipping,
    };

Json _customer(String id, String name, {int days = 0}) => <String, dynamic>{
      'id': id,
      'code': id.toUpperCase(),
      'name': name,
      'display_name': name,
      'customer_type': 'BUSINESS',
      'currency_code': 'INR',
      'default_discount_percent': '0',
      'payment_terms_days': days,
      'status': 'ACTIVE',
      'addresses': <Json>[
        _address('a-bill', 'BILLING', '1 Head Road', 'Mumbai'),
        _address('a-ship1', 'SHIPPING', '9 Depot Lane', 'Pune'),
        _address('a-ship2', 'SHIPPING', '4 Dock Street', 'Nashik',
            shipping: true),
      ],
    };

Json _product() => <String, dynamic>{
      'id': 'p1',
      'code': 'P1',
      'name': 'Shampoo 180ml',
      'selling_price': '100',
      'mrp': '120',
      'status': 'ACTIVE',
    };

/// A draft as `GET /api/v1/sales-orders/{id}` answers with it.
Json _draft({
  String? shippingAddressId,
  String? terms,
  int? termsDays,
}) =>
    <String, dynamic>{
      'id': 'so-1',
      'version': 6,
      'order_number': 'SO-2026-2027-000012',
      'order_date': '2026-08-11',
      'status': 'DRAFT',
      'customer_id': 'c1',
      'branch_id': 'b1',
      'warehouse_id': 'w1',
      'shipping_address_id': shippingAddressId,
      'payment_terms': terms,
      'payment_terms_days': termsDays,
      'bill_discount_percent': '0',
      'bill_discount_amount': '0',
      'lines': <Json>[
        <String, dynamic>{
          'line_number': 1,
          'product_id': 'p1',
          'quantity': '3',
          'free_quantity': '0',
          'unit_price': '95',
          'discount_percent': '0',
          'discount_source': 'percent',
          'discount_amount': '0',
        },
      ],
    };

class _OrderApi extends ApiClient {
  _OrderApi({this.existing})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final Json? existing;
  final List<Json> previews = <Json>[];
  Json? created;
  Json? updated;

  Json _paged(List<Json> rows) => <String, dynamic>{
        'data': rows,
        'pagination': <String, dynamic>{'total_records': rows.length},
      };

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
    if (path == '/api/v1/customers') {
      return _paged(<Json>[_customer('c1', 'Anand Agencies', days: 30)]);
    }
    if (path == '/api/v1/products') return _paged(<Json>[_product()]);
    if (path == '/api/v1/branches') {
      return _paged(<Json>[
        <String, dynamic>{
          'id': 'b1',
          'code': 'HO',
          'name': 'Head Office',
          'display_name': 'Head Office',
          'is_default': true,
        },
      ]);
    }
    if (path == '/api/v1/warehouses') {
      return _paged(<Json>[
        <String, dynamic>{
          'id': 'w1',
          'code': 'WH1',
          'name': 'Main Store',
          'display_name': 'Main Store',
          'is_default': true,
          'branch_id': 'b1',
        },
      ]);
    }
    if (path == '/api/v1/firm-members') {
      return <String, dynamic>{'data': const <Json>[]};
    }
    if (method == 'GET' && path.startsWith('/api/v1/sales-orders/')) {
      return <String, dynamic>{'data': existing};
    }
    if (method == 'PUT' && path.startsWith('/api/v1/sales-orders/')) {
      updated = body;
      return <String, dynamic>{'data': existing};
    }
    if (method == 'POST' && path == '/api/v1/sales-orders') {
      created = body;
      return <String, dynamic>{
        'data': <String, dynamic>{'id': 'so-1', 'order_number': 'SO-1'},
      };
    }
    if (method == 'POST' && path == '/api/v1/sales-orders/preview') {
      previews.add(body!);
      return <String, dynamic>{
        'data': <String, dynamic>{
          'interstate': false,
          'order': <String, dynamic>{
            'order_number': 'SO-2026-2027-000025',
            'subtotal': '100.0000',
            'tax_total': '18.0000',
            'grand_total': '118.0000',
            'lines': const <Json>[],
          },
          'lines': const <Json>[],
        },
      };
    }
    return <String, dynamic>{'data': const <Json>[]};
  }
}

Future<void> _open(WidgetTester tester, _OrderApi api, {String? id}) async {
  tester.view.physicalSize = const Size(1600, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Builder(
        builder: (BuildContext context) => TextButton(
          onPressed: () => Navigator.of(context).push<bool>(
            MaterialPageRoute<bool>(
              builder: (_) => Scaffold(
                body: Phase2Scope(
                  child: SalesOrderEditorDialog(
                    api: api,
                    today: DateTime(2026, 8, 14),
                    orderId: id,
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
  if (id == null) {
    await fillFirstLine(tester, document: 'sales-order', product: 'Shampoo');
  }
}

Future<void> _pickCustomer(WidgetTester tester) async {
  await tester.tap(find.byKey(const ValueKey('sales-order-customer')));
  await tester.pumpAndSettle();
  await tester.tap(find.textContaining('Anand Agencies').last);
  await tester.pumpAndSettle();
}

Future<void> _save(WidgetTester tester) async {
  await tester.tap(find.byKey(const ValueKey('sales-order-save')));
  await tester.pumpAndSettle();
}

void main() {
  group('payment terms (backlog 67 row 4)', () {
    testWidgets('blank boxes say what blank takes and send null',
        (tester) async {
      final _OrderApi api = _OrderApi();
      await _open(tester, api);
      await _pickCustomer(tester);
      expect(find.text("blank takes the customer's 30 days"), findsOneWidget);
      // Never prefilled: the box reads empty.
      final TextField days = tester.widget<TextField>(
        find.descendant(
          of: find.byKey(const ValueKey('sales-order-payment-days')),
          matching: find.byType(TextField),
        ),
      );
      expect(days.controller!.text, isEmpty);
      await _save(tester);
      expect(api.created!.containsKey('payment_terms'), isTrue);
      expect(api.created!['payment_terms'], isNull);
      expect(api.created!['payment_terms_days'], isNull);
    });

    testWidgets('typed terms and days are sent', (tester) async {
      final _OrderApi api = _OrderApi();
      await _open(tester, api);
      await _pickCustomer(tester);
      await tester.enterText(
          find.byKey(const ValueKey('sales-order-payment-terms')), 'Net 45');
      await tester.enterText(
          find.byKey(const ValueKey('sales-order-payment-days')), '45');
      await _save(tester);
      expect(api.created!['payment_terms'], 'Net 45');
      expect(api.created!['payment_terms_days'], 45);
    });

    testWidgets('reopening shows what was saved and sends it back',
        (tester) async {
      final _OrderApi api =
          _OrderApi(existing: _draft(terms: '50% advance', termsDays: 15));
      await _open(tester, api, id: 'so-1');
      expect(find.text('50% advance'), findsOneWidget);
      expect(find.text('15'), findsOneWidget);
      await _save(tester);
      expect(api.updated!['payment_terms'], '50% advance');
      expect(api.updated!['payment_terms_days'], 15);
    });
  });

  group('ship to (backlog 67 row 3)', () {
    testWidgets('a new order preselects the default shipping address',
        (tester) async {
      final _OrderApi api = _OrderApi();
      await _open(tester, api);
      expect(find.byKey(const ValueKey('sales-order-ship-to')), findsNothing);
      await _pickCustomer(tester);
      expect(find.byKey(const ValueKey('sales-order-ship-to')), findsOneWidget);
      // One line each, the default marked.
      expect(find.textContaining('4 Dock Street, Nashik'), findsOneWidget);
      await _save(tester);
      expect(api.created!['shipping_address_id'], 'a-ship2');
    });

    testWidgets('another of the customer\'s addresses can be chosen',
        (tester) async {
      final _OrderApi api = _OrderApi();
      await _open(tester, api);
      await _pickCustomer(tester);
      await tester.tap(find.byKey(const ValueKey('sales-order-ship-to')));
      await tester.pumpAndSettle();
      await tester.tap(find.textContaining('9 Depot Lane, Pune').last);
      await tester.pumpAndSettle();
      await _save(tester);
      expect(api.created!['shipping_address_id'], 'a-ship1');
    });

    testWidgets('reopening shows and keeps the order\'s own address',
        (tester) async {
      final _OrderApi api =
          _OrderApi(existing: _draft(shippingAddressId: 'a-ship1'));
      await _open(tester, api, id: 'so-1');
      expect(find.textContaining('9 Depot Lane, Pune'), findsOneWidget);
      await _save(tester);
      expect(api.updated!['shipping_address_id'], 'a-ship1');
    });
  });
}
