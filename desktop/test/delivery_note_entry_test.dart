import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/inventory.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/ui/delivery_notes/delivery_note_editor_dialog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

InventoryRecord _stock({
  required String batchNumber,
  required String expiry,
  required String available,
}) =>
    InventoryRecord.fromJson({
      'id': 'inv-$batchNumber',
      'product_id': 'prod-1',
      'batch_id': 'batch-$batchNumber',
      'batch_number': batchNumber,
      'batch_expiry_date': expiry,
      'available_quantity': available,
      'current_quantity': available,
    });

/// A sales order for ten units with ten reserved.
Json _order({String reserved = '10'}) => {
      'id': 'so-1',
      'order_number': 'SO-2026-000001',
      'order_date': '2026-08-01',
      'warehouse_id': 'wh-1',
      'status': 'APPROVED',
      'lines': [
        {
          'id': 'so-line-1',
          'line_number': 1,
          'product_id': 'prod-1',
          'description': 'Amoxicillin 500mg',
          'quantity': '10',
          'reserved_quantity': reserved,
          'unit_price': '40',
          'sales_uom_id': 'uom-box',
          'warehouse_id': 'wh-1',
        },
      ],
    };

class _DeliveryApi extends ApiClient {
  _DeliveryApi({this.stock = const []})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<InventoryRecord> stock;
  Json? sent;

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
      // No earlier notes against this order.
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
      PagedResult<InventoryRecord>(items: stock, total: stock.length);

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

Future<void> _openEditor(
  WidgetTester tester,
  _DeliveryApi api, {
  Json? order,
}) async {
  tester.view.physicalSize = const Size(1600, 1200);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: DeliveryNoteEditorDialog(
          api: api,
          salesOrders: [order ?? _order()],
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
  );
  await tester.pumpAndSettle();
  await tester.tap(find.byType(DropdownButtonFormField<String>).first);
  await tester.pumpAndSettle();
  await tester.tap(find.text('SO-2026-000001 • 2026-08-01').last);
  await tester.pumpAndSettle();
}

void main() {
  group('the allocation preview', () {
    test('spends the earliest expiry first and stops when covered', () {
      final List<BatchDraw> draws = previewAllocation(
        [
          _stock(batchNumber: 'JUNE', expiry: '2027-06-30', available: '60'),
          _stock(batchNumber: 'MARCH', expiry: '2027-03-31', available: '40'),
        ],
        50,
      );

      expect(draws, hasLength(2));
      expect(draws.first.batchNumber, 'MARCH');
      expect(draws.first.quantity, 40);
      expect(draws.last.batchNumber, 'JUNE');
      expect(draws.last.quantity, 10, reason: 'only the shortfall is taken');
    });

    test('a batch with no expiry goes last, not first', () {
      // PostgreSQL sorts NULLs first in ASC and SQLite last, which is why the
      // server ranks this explicitly. A batch without an expiry is not urgent.
      final List<BatchDraw> draws = previewAllocation(
        [
          _stock(batchNumber: 'NOEXPIRY', expiry: '', available: '100'),
          _stock(batchNumber: 'MARCH', expiry: '2027-03-31', available: '10'),
        ],
        20,
      );

      expect(draws.first.batchNumber, 'MARCH');
      expect(draws.last.batchNumber, 'NOEXPIRY');
    });

    test('reports what it could not cover', () {
      final List<BatchDraw> draws = previewAllocation(
        [_stock(batchNumber: 'MARCH', expiry: '2027-03-31', available: '5')],
        20,
      );

      final double covered =
          draws.fold<double>(0, (total, draw) => total + draw.quantity);
      expect(covered, 5);
    });
  });

  testWidgets('a line defaults to what is reserved, not what was ordered', (
    tester,
  ) async {
    // Stock is committed when the order is approved and released at dispatch,
    // so dispatching more than is reserved is refused. Defaulting to the
    // ordered quantity would look right and fail at dispatch.
    final _DeliveryApi api = _DeliveryApi();
    await _openEditor(tester, api, order: _order(reserved: '6'));

    expect(
      find.text('Ordered 10 · reserved 6 · already delivered 0'),
      findsOneWidget,
    );
    final TextFormField delivering = tester.widget<TextFormField>(
      find.ancestor(
        of: find.text('Delivering *'),
        matching: find.byType(TextFormField),
      ),
    );
    expect(delivering.initialValue, '6');
  });

  testWidgets('a line with nothing reserved says why it cannot ship', (
    tester,
  ) async {
    final _DeliveryApi api = _DeliveryApi();
    await _openEditor(tester, api, order: _order(reserved: '0'));

    expect(find.textContaining('Nothing is reserved'), findsOneWidget);

    await tester.tap(find.text('Save Delivery Note'));
    await tester.pumpAndSettle();

    expect(api.sent, isNull, reason: 'a note with no shippable line is not sent');
  });

  testWidgets('a fully delivered line says so instead of blaming approval', (
    tester,
  ) async {
    // Nothing reserved has two causes: an order nobody approved, and one whose
    // reservation was released on the way out. Telling someone to approve an
    // order that is already delivered sends them after a button that will not
    // help — every seeded order in the demo store is in exactly this state.
    final _DeliveryApi api = _DeliveryApi();
    final Json order = _order(reserved: '0');
    (order['lines'] as List<dynamic>).first['quantity'] = '0';
    await _openEditor(tester, api, order: order);

    expect(find.textContaining('already been delivered in full'), findsOneWidget);
    expect(find.textContaining('Nothing is reserved'), findsNothing);
  });

  testWidgets('the note names no batch — the server chooses at dispatch', (
    tester,
  ) async {
    final _DeliveryApi api = _DeliveryApi(stock: [
      _stock(batchNumber: 'MARCH', expiry: '2027-03-31', available: '40'),
    ]);
    await _openEditor(tester, api);

    // The preview tells the packer which cartons to pick...
    expect(find.textContaining('MARCH'), findsWidgets);

    await tester.tap(find.text('Save Delivery Note'));
    await tester.pumpAndSettle();

    expect(api.sent, isNotNull);
    final List<dynamic> lines = api.sent!['lines'] as List<dynamic>;
    expect(lines, hasLength(1));
    final Json line = lines.first as Json;
    expect(line['sales_order_line_id'], 'so-line-1');
    expect(line['current_delivery_quantity'], '10');
    // ...but the payload carries no batch. Allocation is the server's, decided
    // when the note is dispatched, so sending one here would be a guess the
    // client is in no position to make.
    expect(line.containsKey('batch_number'), isFalse);
  });
}
