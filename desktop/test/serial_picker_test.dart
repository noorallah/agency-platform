import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/batch_serial.dart';
import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/inventory.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/models/sales_return.dart';
import 'package:agency_desktop/ui/delivery_notes/delivery_note_editor_dialog.dart';
import 'package:agency_desktop/ui/sales_returns/sales_return_editor_dialog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// The storekeeper picks which serialised units go, and which come back.
///
/// A mixer grinder left on a delivery note and its serial stayed AVAILABLE for
/// ever, because nothing said which unit it was (D-STK-4). The owner's answer
/// is a picker: a line for a serial-tracked product names its units, one per
/// unit, and the server marks exactly those SOLD at dispatch -- and a return
/// names the ones coming back.

/// An approved order for two mixer grinders, reserved and in pieces.
Json _order({String productId = 'prod-mix'}) => {
      'id': 'so-1',
      'order_number': 'SO-2026-000001',
      'order_date': '2026-08-01',
      'warehouse_id': 'wh-1',
      'status': 'APPROVED',
      'lines': [
        {
          'id': 'so-line-1',
          'line_number': 1,
          'product_id': productId,
          'description': 'Mixer Grinder',
          'quantity': '2',
          'reserved_quantity': '2',
          'unit_price': '3000',
          'sales_uom_id': 'uom-piece',
          'inventory_uom_id': 'uom-piece',
          'warehouse_id': 'wh-1',
        },
      ],
    };

SerialRecord _serial(String id, String number) => SerialRecord.fromJson({
      'id': id,
      'product_id': 'prod-mix',
      'warehouse_id': 'wh-1',
      'serial_number': number,
      'status': 'AVAILABLE',
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
  SerialQuery? asked;

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
  Future<PagedResult<SerialRecord>> serials({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    SerialQuery filters = const SerialQuery(),
  }) async {
    asked = filters;
    final List<SerialRecord> shelf = [
      _serial('ser-1', 'MIX-0001'),
      _serial('ser-2', 'MIX-0002'),
      _serial('ser-3', 'MIX-0003'),
    ];
    return PagedResult<SerialRecord>(items: shelf, total: shelf.length);
  }

  @override
  Future<Json> create(String resource, Json body) async {
    sent = body;
    return {
      'data': {'id': 'dn-1', 'delivery_note_number': 'DN-1', 'status': 'DRAFT'}
    };
  }
}

Future<void> _openNoteEditor(
  WidgetTester tester,
  _NoteApi api, {
  bool serialised = true,
}) async {
  tester.view.physicalSize = const Size(1600, 1200);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: DeliveryNoteEditorDialog(
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
              'id': 'prod-mix',
              'code': 'MIX',
              'name': 'Mixer Grinder',
              'track_serial': serialised,
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

Map<String, dynamic> _onlyLine(Json? body) =>
    Map<String, dynamic>.from((body!['lines'] as List).single as Map);

/// A delivered line for two grinders, and a sales invoice the return names.
ReturnableDocument _note() => ReturnableDocument.fromDeliveryNote({
      'id': 'dn-1',
      'delivery_note_number': 'DN-2026-000001',
      'delivery_date': '2026-08-04',
      'customer_id': 'cust-1',
      'customer_name': 'Anand Electricals',
      'status': 'DISPATCHED',
      'lines': [
        {
          'id': 'dn-line-1',
          'line_number': 1,
          'product_id': 'prod-mix',
          'product_name': 'Mixer Grinder',
          'current_delivery_quantity': '2',
          'unit_price': '3000',
        },
      ],
    });

Future<Json?> _raiseReturn(
  WidgetTester tester, {
  required ReturnableSerials offered,
  List<String> pick = const [],
  List<String>? asked,
}) async {
  tester.view.physicalSize = const Size(1600, 1200);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  Json? payload;
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: Builder(
          builder: (context) => TextButton(
            onPressed: () async {
              payload = await showDialog<Json>(
                context: context,
                builder: (_) => SalesReturnEditorDialog(
                  documents: [_note()],
                  warehouses: [
                    WarehouseRecord.fromJson({
                      'id': 'wh-1',
                      'code': 'MAIN',
                      'name': 'Main',
                      'display_name': 'Main warehouse',
                    }),
                  ],
                  today: DateTime(2026, 8, 5),
                  loadSerials: (document, line) async {
                    asked?.add('${document.sourceType.code} ${line.id}');
                    return offered;
                  },
                ),
              );
            },
            child: const Text('open'),
          ),
        ),
      ),
    ),
  );
  await tester.tap(find.text('open'));
  await tester.pumpAndSettle();
  for (final String id in pick) {
    await tester.tap(find.byKey(ValueKey<String>('serial-back-$id')));
    await tester.pumpAndSettle();
  }
  await tester.tap(find.widgetWithText(FilledButton, 'Create draft'));
  await tester.pumpAndSettle();
  return payload;
}

void main() {
  group('the delivery note picker', () {
    testWidgets('offers the AVAILABLE units on the line\'s shelf',
        (tester) async {
      final _NoteApi api = _NoteApi();
      await _openNoteEditor(tester, api);

      expect(api.asked?.productId, 'prod-mix');
      expect(api.asked?.warehouseId, 'wh-1');
      expect(api.asked?.status, 'AVAILABLE');
      expect(find.text('MIX-0001'), findsOneWidget);
      expect(find.text('MIX-0003'), findsOneWidget);
      expect(
        find.text('Serial numbers going out — pick 2, 0 picked'),
        findsOneWidget,
      );
    });

    testWidgets('sends the picked units with the line', (tester) async {
      final _NoteApi api = _NoteApi();
      await _openNoteEditor(tester, api);

      await tester.tap(find.byKey(const ValueKey<String>('serial-pick-ser-1')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey<String>('serial-pick-ser-3')));
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(FilledButton, 'Save Delivery Note'));
      await tester.pumpAndSettle();

      expect(_onlyLine(api.sent)['serial_ids'], ['ser-1', 'ser-3']);
    });

    testWidgets('refuses to save a line short of units', (tester) async {
      // This editor only creates: a note saved one unit short could never be
      // dispatched, and nothing here could correct it.
      final _NoteApi api = _NoteApi();
      await _openNoteEditor(tester, api);

      await tester.tap(find.byKey(const ValueKey<String>('serial-pick-ser-2')));
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(FilledButton, 'Save Delivery Note'));
      await tester.pumpAndSettle();

      expect(api.sent, isNull);
      expect(
        find.textContaining('pick one serial number per unit going out'),
        findsOneWidget,
      );
    });

    testWidgets('a product nobody serialises has no picker and sends none',
        (tester) async {
      final _NoteApi api = _NoteApi();
      await _openNoteEditor(tester, api, serialised: false);

      expect(find.textContaining('Serial numbers going out'), findsNothing);
      expect(api.asked, isNull, reason: 'no serials were read');
      await tester.tap(find.widgetWithText(FilledButton, 'Save Delivery Note'));
      await tester.pumpAndSettle();

      expect(_onlyLine(api.sent).containsKey('serial_ids'), isFalse);
    });
  });

  group('the sales return picker', () {
    const ReturnableSerials sold = ReturnableSerials(
      serialTracked: true,
      serials: [
        PickedSerial(id: 'ser-1', serialNumber: 'MIX-0001', status: 'SOLD'),
        PickedSerial(id: 'ser-2', serialNumber: 'MIX-0002', status: 'SOLD'),
      ],
    );

    testWidgets('asks for the units sold on the chosen line', (tester) async {
      final List<String> asked = [];
      await _raiseReturn(tester, offered: sold, pick: ['ser-2'], asked: asked);

      expect(asked, ['DELIVERY_NOTE dn-line-1']);
    });

    testWidgets('sends the units coming back', (tester) async {
      final Json? payload =
          await _raiseReturn(tester, offered: sold, pick: ['ser-2']);

      expect(_onlyLine(payload)['serial_ids'], ['ser-2']);
    });

    testWidgets('refuses a return that names no unit', (tester) async {
      final Json? payload = await _raiseReturn(tester, offered: sold);

      expect(payload, isNull);
      expect(
        find.textContaining('Pick one serial number per unit coming back'),
        findsOneWidget,
      );
    });

    testWidgets('an untracked product sends no serials', (tester) async {
      final Json? payload = await _raiseReturn(
        tester,
        offered: ReturnableSerials.untracked,
      );

      expect(_onlyLine(payload).containsKey('serial_ids'), isFalse);
    });
  });
}
