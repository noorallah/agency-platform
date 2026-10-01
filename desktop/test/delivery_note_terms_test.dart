// What a delivery note says about where the goods go and how they travel
// (backlog 67 rows 3 and 5), in the phase 2 editor.

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/customer.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/inventory.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/ui/delivery_notes/delivery_note_editor_dialog.dart';
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

/// An approved order for ten units with ten reserved, shipping to the Pune
/// depot.
Json _order() => <String, dynamic>{
      'id': 'so-1',
      'order_number': 'SO-2026-000001',
      'order_date': '2026-08-01',
      'customer_id': 'c1',
      'shipping_address_id': 'a-pune',
      'warehouse_id': 'wh-1',
      'status': 'APPROVED',
      'lines': <Json>[
        <String, dynamic>{
          'id': 'so-line-1',
          'line_number': 1,
          'product_id': 'prod-1',
          'description': 'Amoxicillin 500mg',
          'quantity': '10',
          'reserved_quantity': '10',
          'unit_price': '40',
          'sales_uom_id': 'uom-box',
          'warehouse_id': 'wh-1',
        },
      ],
    };

class _NoteApi extends ApiClient {
  _NoteApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  Json? sent;

  @override
  Future<Customer> customer(String id) async => Customer.fromJson(
        <String, dynamic>{
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
        },
      );

  @override
  Future<Json> documentPage(
    String resource, {
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    Map<String, String> additionalQuery = const {},
  }) async =>
      const {'data': <dynamic>[]};

  @override
  Future<PagedResult<InventoryRecord>> inventory({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    InventoryQuery filters = const InventoryQuery(),
  }) async =>
      const PagedResult<InventoryRecord>(items: [], total: 0);

  @override
  Future<Json> create(String resource, Json body) async {
    sent = body;
    return {
      'data': {
        'id': 'dn-1',
        'delivery_note_number': 'DN-1',
        'status': 'DRAFT',
      }
    };
  }
}

Future<void> _open(WidgetTester tester, _NoteApi api) async {
  tester.view.physicalSize = const Size(1600, 1000);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: Phase2Scope(
          child: DeliveryNoteEditorDialog(
            api: api,
            salesOrders: [_order()],
            warehouses: [
              WarehouseRecord.fromJson({
                'id': 'wh-1',
                'code': 'MAIN',
                'name': 'Main Warehouse',
              }),
            ],
            products: [
              Product.fromJson({
                'id': 'prod-1',
                'code': 'SKU-1',
                'name': 'Amoxicillin 500mg',
              }),
            ],
          ),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
  await tester.tap(find.byKey(const ValueKey('delivery-note-order')));
  await tester.pumpAndSettle();
  await tester.tap(find.textContaining('SO-2026-000001').last);
  await tester.pumpAndSettle();
}

Future<void> _save(WidgetTester tester) async {
  await tester.tap(find.byKey(const ValueKey('delivery-note-save')));
  await tester.pumpAndSettle();
}

void main() {
  group('ship to (backlog 67 row 3)', () {
    testWidgets('is preselected with the order\'s own address',
        (tester) async {
      final _NoteApi api = _NoteApi();
      await _open(tester, api);
      expect(find.byKey(const ValueKey('delivery-note-ship-to')),
          findsOneWidget);
      expect(find.textContaining('9 Depot Lane, Pune'), findsOneWidget);
      await _save(tester);
      expect(api.sent!['shipping_address_id'], 'a-pune');
    });

    testWidgets('can be sent to another of the customer\'s addresses',
        (tester) async {
      final _NoteApi api = _NoteApi();
      await _open(tester, api);
      await tester.tap(find.byKey(const ValueKey('delivery-note-ship-to')));
      await tester.pumpAndSettle();
      await tester.tap(find.textContaining('4 Dock Street, Nashik').last);
      await tester.pumpAndSettle();
      await _save(tester);
      expect(api.sent!['shipping_address_id'], 'a-nashik');
    });
  });
}
