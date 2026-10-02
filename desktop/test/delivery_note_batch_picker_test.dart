// The batch picker on the phase 2 delivery note (backlog 79, decision A38):
// every batch of the line's product with what it can give, earliest expiry
// first as the default, and the person's own split sent as `batches`.

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/batch_serial.dart';
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

Json _order() => <String, dynamic>{
      'id': 'so-1',
      'order_number': 'SO-2026-000001',
      'order_date': '2026-08-01',
      'customer_id': 'c1',
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
          'warehouse_id': 'wh-1',
        },
      ],
    };

BatchAvailabilityRecord _batch(
  String id, {
  required String expiry,
  required int days,
  required double fefo,
  bool expired = false,
  bool near = false,
  bool shortForCustomer = false,
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
      'expired': expired,
      'near_expiry': near,
      'short_for_customer': shortForCustomer,
      'fefo': fefo.toString(),
    });

class _NoteApi extends ApiClient {
  _NoteApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  Json? sent;
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
      'sales_order_line_id': salesOrderLineId,
      'customer_id': customerId,
    };
    return [
      _batch('old', expiry: '2026-12-01', days: 20, fefo: 6, near: true),
      _batch('new', expiry: '2027-06-01', days: 200, fefo: 4),
      _batch('short', expiry: '2026-11-01', days: 30, fefo: 0,
          shortForCustomer: true),
      _batch('gone', expiry: '2026-01-01', days: -90, fefo: 0, expired: true),
    ];
  }

  @override
  Future<Customer> customer(String id) async => Customer.fromJson(
        <String, dynamic>{
          'id': 'c1',
          'code': 'C1',
          'name': 'Anand Agencies',
          'display_name': 'Anand Agencies',
          'customer_type': 'BUSINESS',
          'status': 'ACTIVE',
          'addresses': <Json>[],
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
      'data': {'id': 'dn-1', 'delivery_note_number': 'DN-1', 'status': 'DRAFT'}
    };
  }
}

Future<void> _open(WidgetTester tester, _NoteApi api) async {
  tester.view.physicalSize = const Size(1366, 768);
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
  // The batches are asked for a moment after the line settles.
  await tester.pump(const Duration(milliseconds: 400));
  await tester.pumpAndSettle();
}

Future<void> _save(WidgetTester tester) async {
  await tester.tap(find.byKey(const ValueKey('delivery-note-save')));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('shows every batch, earliest expiry pre-filled, expired locked',
      (tester) async {
    final _NoteApi api = _NoteApi();
    await _open(tester, api);

    expect(find.byKey(const ValueKey('delivery-note-batch-picker')),
        findsOneWidget);
    expect(find.text('BN-old'), findsOneWidget);
    expect(find.text('BN-gone'), findsOneWidget);
    expect(find.text('Near expiry'), findsOneWidget);
    expect(find.text('Expired'), findsOneWidget);
    expect(api.asked!['sales_order_line_id'], 'so-line-1');
    expect(api.asked!['quantity'], 10);
    expect(api.asked!['warehouse_id'], 'wh-1');
    expect(api.asked!['customer_id'], 'c1');
    // Flagged, never pre-filled.
    expect(find.text('Too short for customer'), findsOneWidget);
    expect(
        tester
            .widget<TextField>(find.descendant(
                of: find.byKey(const ValueKey<String>('batch-pick-so-line-1-short')),
                matching: find.byType(TextField)))
            .controller!
            .text,
        '0');

    TextField box(String id) => tester.widget<TextField>(find.descendant(
        of: find.byKey(ValueKey<String>('batch-pick-so-line-1-$id')),
        matching: find.byType(TextField)));
    expect(box('old').controller!.text, '6');
    expect(box('new').controller!.text, '4');
    expect(box('gone').enabled, isFalse);
    expect(find.textContaining('Chosen 10 of 10'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('an edited box is sent as the line\'s batches', (tester) async {
    final _NoteApi api = _NoteApi();
    await _open(tester, api);

    await tester.enterText(
        find.byKey(const ValueKey<String>('batch-pick-so-line-1-old')), '3');
    await tester.pump();
    await tester.enterText(
        find.byKey(const ValueKey<String>('batch-pick-so-line-1-new')), '7');
    await tester.pump();
    expect(find.textContaining('Chosen 10 of 10'), findsOneWidget);
    expect(find.byKey(const ValueKey('delivery-note-batch-reset')),
        findsOneWidget);

    await _save(tester);
    final List<dynamic> lines = api.sent!['lines'] as List<dynamic>;
    final Map<String, dynamic> line = lines.single as Map<String, dynamic>;
    final List<dynamic> batches = line['batches'] as List<dynamic>;
    expect(batches, hasLength(2));
    expect(batches[0]['batch_id'], 'old');
    expect(num.parse('${batches[0]['quantity']}'), 3);
    expect(batches[1]['batch_id'], 'new');
    expect(num.parse('${batches[1]['quantity']}'), 7);
  });

  testWidgets('a total that does not match the line is flagged',
      (tester) async {
    final _NoteApi api = _NoteApi();
    await _open(tester, api);
    await tester.enterText(
        find.byKey(const ValueKey<String>('batch-pick-so-line-1-old')), '1');
    await tester.pump();
    expect(find.textContaining('Chosen 5 of 10'), findsOneWidget);
    expect(find.textContaining('do not add up'), findsOneWidget);
  });

  testWidgets('"Use earliest expiry" sends an empty list', (tester) async {
    final _NoteApi api = _NoteApi();
    await _open(tester, api);
    await tester.enterText(
        find.byKey(const ValueKey<String>('batch-pick-so-line-1-old')), '3');
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('delivery-note-batch-reset')));
    await tester.pumpAndSettle();
    expect(find.textContaining('Chosen 10 of 10'), findsOneWidget);
    await _save(tester);
    final Map<String, dynamic> line =
        (api.sent!['lines'] as List<dynamic>).single as Map<String, dynamic>;
    expect(line['batches'], isEmpty);
  });

  testWidgets('with nothing edited the line sends no batches', (tester) async {
    final _NoteApi api = _NoteApi();
    await _open(tester, api);
    await _save(tester);
    final Map<String, dynamic> line =
        (api.sent!['lines'] as List<dynamic>).single as Map<String, dynamic>;
    expect(line['batches'], isNull);
    expect(line.containsKey('batches'), isFalse);
  });
}
