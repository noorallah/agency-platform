// A sales order line may pin the batch the customer asked for (backlog 79
// row 4), in the phase 2 editor. Blank is "earliest expiry" and is sent as
// null; a chosen batch is sent as `pinned_batch_id`; reopening a draft keeps
// the pin, even when the batch no longer appears in the availability list.

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/sales/sales_order_editor_dialog.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Json _batch(String id, String number, String expiry, String available,
        {bool expired = false}) =>
    <String, dynamic>{
      'batch_id': id,
      'batch_number': number,
      'manufacturing_date': '2026-01-01',
      'expiry_date': expiry,
      'days_to_expiry': 100,
      'on_hand': available,
      'reserved': '0',
      'available': available,
      'available_to_line': available,
      'expired': expired,
      'near_expiry': false,
      'fefo': '0',
    };

Json _draft({String? pinned}) => <String, dynamic>{
      'id': 'so-1',
      'version': 3,
      'order_number': 'SO-1',
      'order_date': '2026-08-11',
      'status': 'DRAFT',
      'customer_id': 'c1',
      'branch_id': 'b1',
      'warehouse_id': 'w1',
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
          'pinned_batch_id': pinned,
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
  Json? created;
  Json? updated;
  Map<String, String>? availabilityQuery;

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
      return _paged(<Json>[
        <String, dynamic>{
          'id': 'c1',
          'code': 'C1',
          'name': 'Anand Agencies',
          'display_name': 'Anand Agencies',
          'customer_type': 'BUSINESS',
          'currency_code': 'INR',
          'default_discount_percent': '0',
          'payment_terms_days': 30,
          'status': 'ACTIVE',
          'addresses': const <Json>[],
        },
      ]);
    }
    if (path == '/api/v1/products') {
      return _paged(<Json>[
        <String, dynamic>{
          'id': 'p1',
          'code': 'P1',
          'name': 'Syrup 100ml',
          'selling_price': '100',
          'mrp': '120',
          'status': 'ACTIVE',
          'track_batch': true,
        },
      ]);
    }
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
    if (path == '/api/v1/batch-serial/batches/availability') {
      availabilityQuery = query;
      return <String, dynamic>{
        'data': <Json>[
          _batch('b-old', 'B-OLD', '2026-09-30', '40', expired: true),
          _batch('b-a', 'B-A', '2027-03-31', '25'),
          _batch('b-b', 'B-B', '2027-06-30', '10'),
        ],
      };
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
      return <String, dynamic>{
        'data': <String, dynamic>{
          'interstate': false,
          'order': <String, dynamic>{
            'order_number': 'SO-2',
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

const ValueKey<String> _batchKey = ValueKey('sales-order-line-batch-0');

void main() {
  group('pinning a batch (backlog 79 row 4)', () {
    testWidgets('left on earliest expiry sends null', (tester) async {
      final _OrderApi api = _OrderApi();
      await _open(tester, api);
      await _pickCustomer(tester);
      expect(find.byKey(_batchKey), findsOneWidget);
      expect(find.text('Earliest expiry'), findsOneWidget);
      expect(api.availabilityQuery!['product_id'], 'p1');
      expect(api.availabilityQuery!['warehouse_id'], 'w1');
      await _save(tester);
      final List<dynamic> lines = api.created!['lines'] as List<dynamic>;
      expect((lines.first as Json).containsKey('pinned_batch_id'), isTrue);
      expect((lines.first as Json)['pinned_batch_id'], isNull);
    });

    testWidgets('a chosen batch is sent; an expired one cannot be chosen',
        (tester) async {
      final _OrderApi api = _OrderApi();
      await _open(tester, api);
      await _pickCustomer(tester);
      await tester.tap(find.byKey(_batchKey));
      await tester.pumpAndSettle();
      // The expired batch is listed but refuses the tap.
      await tester.tap(find.textContaining('B-OLD').last);
      await tester.pumpAndSettle();
      expect(find.textContaining('B-A'), findsOneWidget);
      await tester.tap(find.textContaining('B-B').last);
      await tester.pumpAndSettle();
      await _save(tester);
      final List<dynamic> lines = api.created!['lines'] as List<dynamic>;
      expect((lines.first as Json)['pinned_batch_id'], 'b-b');
    });

    testWidgets('reopening preselects the pin and sends it back',
        (tester) async {
      final _OrderApi api = _OrderApi(existing: _draft(pinned: 'b-a'));
      await _open(tester, api, id: 'so-1');
      expect(find.textContaining('B-A'), findsOneWidget);
      await _save(tester);
      final List<dynamic> lines = api.updated!['lines'] as List<dynamic>;
      expect((lines.first as Json)['pinned_batch_id'], 'b-a');
    });

    testWidgets('a pin on a batch no longer listed is kept', (tester) async {
      final _OrderApi api = _OrderApi(existing: _draft(pinned: 'b-gone'));
      await _open(tester, api, id: 'so-1');
      expect(find.text('Pinned batch'), findsOneWidget);
      await _save(tester);
      final List<dynamic> lines = api.updated!['lines'] as List<dynamic>;
      expect((lines.first as Json)['pinned_batch_id'], 'b-gone');
    });
  });
}
