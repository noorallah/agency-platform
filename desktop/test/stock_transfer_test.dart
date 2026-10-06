// STK-1, the desktop half: stock transfer as a document.
//
//   * the Stock Transfers screen lists drafts, transfers in transit and
//     received ones, and offers each only the step that is next;
//   * a new draft sends exactly the keys the server declares;
//   * a refusal keeps the dialog open with the server's message;
//   * dispatch, receive, cancel and print call the right methods;
//   * receiving shows the shortage as the quantity sent less received;
//   * writing needs INVENTORY_ADJUST.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/batch_serial.dart';
import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/models/stock_transfer.dart';
import 'package:agency_desktop/ui/inventory/stock_transfer_dialog.dart';
import 'package:agency_desktop/ui/inventory/stock_transfer_steps_dialogs.dart';
import 'package:agency_desktop/ui/inventory/stock_transfers_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions(List<String> codes) => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': codes,
  }));

const Map<String, dynamic> _draft = {
  'id': 'st-1',
  'transfer_number': 'STF-0001',
  'transfer_date': '2026-10-01',
  'from_warehouse_id': 'wh-1',
  'from_warehouse_name': 'Central Warehouse',
  'to_warehouse_id': 'wh-2',
  'to_warehouse_name': 'City Godown',
  'status': 'DRAFT',
  'dispatched_value': '0.00',
  'shortage_value': '0.00',
  'version': 1,
  'lines': [
    {
      'line_number': 1,
      'product_id': 'p-sack',
      'product_code': 'SACK',
      'product_name': 'Rice sack',
      'quantity': '10.0000',
    },
  ],
};

const Map<String, dynamic> _transit = {
  'id': 'st-2',
  'transfer_number': 'STF-0002',
  'transfer_date': '2026-10-02',
  'from_warehouse_id': 'wh-1',
  'from_warehouse_name': 'Central Warehouse',
  'to_warehouse_id': 'wh-2',
  'to_warehouse_name': 'City Godown',
  'status': 'DISPATCHED',
  'dispatched_on': '2026-10-02',
  'vehicle_number': 'KA01AB1234',
  'dispatched_value': '1000.00',
  'shortage_value': '0.00',
  'version': 2,
  'lines': [
    {
      'line_number': 1,
      'product_id': 'p-sack',
      'product_code': 'SACK',
      'product_name': 'Rice sack',
      'quantity': '10.0000',
      'unit_cost': '100.00',
    },
  ],
};

WarehouseRecord _warehouse(String id, String code, String name) =>
    WarehouseRecord(
      id: id,
      firmId: 'firm-1',
      branchId: 'branch-1',
      code: code,
      name: name,
      displayName: name,
      warehouseTypeId: 'type-1',
      businessProfileId: 'profile-1',
      capacity: '0',
      capacityUnit: 'EA',
      status: 'ACTIVE',
      isDefault: false,
      temperatureControlled: false,
      coldStorage: false,
      hazardousStorage: false,
      isDeleted: false,
      createdAt: '2026-08-01T00:00:00Z',
    );

Product _product(String id, String code, String name) => Product(
      id: id,
      firmId: 'firm-1',
      code: code,
      barcode: '',
      qrCode: '',
      name: name,
      shortName: name,
      description: '',
      productType: 'FINISHED_GOOD',
      categoryId: 'cat-1',
      subCategoryId: '',
      unit: 'EA',
      brand: '',
      model: '',
      hsnSac: '',
      taxProfileId: '',
      purchasePrice: '0',
      sellingPrice: '0',
      mrp: '0',
      status: 'ACTIVE',
      remarks: '',
      isDeleted: false,
      createdAt: '2026-08-01T00:00:00Z',
      updatedAt: '2026-08-01T00:00:00Z',
      attributes: const [],
      media: const [],
    );

class _Api extends ApiClient {
  _Api({this.refuse})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  String? refuse;
  Json? created;
  int createCalls = 0;
  String? dispatchedId;
  Json? dispatchBody;
  String? receivedId;
  Json? receiveBody;
  String? cancelledId;
  String? cancelReason;
  String? challanId;
  String? fetchedId;

  @override
  Future<StockTransferRecord> stockTransfer(String id) async {
    fetchedId = id;
    return StockTransferRecord.fromJson(_draft);
  }

  @override
  Future<List<StockTransferRecord>> stockTransfers({String? status}) async => [
        StockTransferRecord.fromJson(_draft),
        StockTransferRecord.fromJson(_transit),
      ];

  @override
  Future<PagedResult<WarehouseRecord>> warehouses({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    WarehouseQuery filters = const WarehouseQuery(),
  }) async =>
      PagedResult<WarehouseRecord>(
        items: [
          _warehouse('wh-1', 'WH-001', 'Central Warehouse'),
          _warehouse('wh-2', 'WH-002', 'City Godown'),
        ],
        total: 2,
      );

  @override
  Future<PagedResult<Product>> products({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    ProductQuery filters = const ProductQuery(),
  }) async =>
      PagedResult<Product>(
        items: [_product('p-sack', 'SACK', 'Rice sack')],
        total: 1,
      );

  @override
  Future<PagedResult<BatchRecord>> batches({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    BatchQuery filters = const BatchQuery(),
  }) async =>
      const PagedResult<BatchRecord>(items: [], total: 0);

  @override
  Future<StockTransferRecord> createStockTransfer(Json data) async {
    createCalls++;
    final String? message = refuse;
    if (message != null) throw ApiException(message, statusCode: 422);
    created = data;
    return StockTransferRecord.fromJson(_draft);
  }

  @override
  Future<StockTransferRecord> dispatchStockTransfer(
      String id, Json data) async {
    dispatchedId = id;
    dispatchBody = data;
    return StockTransferRecord.fromJson(_transit);
  }

  @override
  Future<StockTransferRecord> receiveStockTransfer(
      String id, Json data) async {
    receivedId = id;
    receiveBody = data;
    return StockTransferRecord.fromJson(_transit);
  }

  @override
  Future<StockTransferRecord> cancelStockTransfer(
      String id, String reason) async {
    cancelledId = id;
    cancelReason = reason;
    return StockTransferRecord.fromJson(_draft);
  }

  @override
  Future<List<int>> stockTransferChallan(String id) async {
    challanId = id;
    return const [1, 2, 3];
  }
}

Future<void> _pump(
  WidgetTester tester,
  _Api api,
  List<String> codes, {
  Future<void> Function(String, List<int>)? openPdf,
}) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: StockTransfersPage(
        api: api,
        permissions: _permissions(codes),
        openPdfOverride: openPdf,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

Future<void> _pick(WidgetTester tester, String key, String label) async {
  final Finder dropdown = find.byKey(ValueKey<String>(key));
  await tester.ensureVisible(dropdown);
  await tester.tap(dropdown);
  await tester.pumpAndSettle();
  await tester.tap(find.text(label).last);
  await tester.pumpAndSettle();
}

Future<void> _enter(WidgetTester tester, String key, String text) async {
  final Finder field = find.byKey(ValueKey<String>(key));
  await tester.ensureVisible(field);
  await tester.enterText(field, text);
}

Future<void> _fillDialog(WidgetTester tester) async {
  await tester.tap(find.byKey(const ValueKey('transfer-new')));
  await tester.pumpAndSettle();
  await _pick(tester, 'transfer-from', 'WH-001 - Central Warehouse');
  await _pick(tester, 'transfer-to', 'WH-002 - City Godown');
  await _enter(tester, 'transfer-vehicle', 'KA01AB1234');
  await _pick(tester, 'transfer-product-0', 'SACK - Rice sack');
  await _enter(tester, 'transfer-quantity-0', '10');
}

Future<void> _select(WidgetTester tester, String number) async {
  await tester.tap(find.text(number));
  await tester.pumpAndSettle();
}

bool _enabled(WidgetTester tester, String key) =>
    tester
        .widget<OutlinedButton>(find.byKey(ValueKey<String>(key)))
        .onPressed !=
    null;

void main() {
  group('the Stock Transfers screen', () {
    testWidgets('lists transfers and offers only the next step',
        (tester) async {
      await _pump(tester, _Api(), ['INVENTORY_VIEW', 'INVENTORY_ADJUST']);

      expect(find.text('STF-0001'), findsOneWidget);
      expect(find.text('STF-0002'), findsOneWidget);
      expect(find.text('Draft'), findsOneWidget);
      expect(find.text('In transit'), findsOneWidget);

      await _select(tester, 'STF-0001');
      expect(find.byKey(const ValueKey('transfer-details')), findsOneWidget);
      expect(_enabled(tester, 'transfer-edit'), isTrue);
      expect(_enabled(tester, 'transfer-dispatch'), isTrue);
      expect(_enabled(tester, 'transfer-receive'), isFalse);
      expect(_enabled(tester, 'transfer-challan'), isFalse);
      expect(_enabled(tester, 'transfer-cancel'), isTrue);

      await _select(tester, 'STF-0002');
      expect(_enabled(tester, 'transfer-edit'), isFalse);
      expect(_enabled(tester, 'transfer-dispatch'), isFalse);
      expect(_enabled(tester, 'transfer-receive'), isTrue);
      expect(_enabled(tester, 'transfer-challan'), isTrue);
      expect(_enabled(tester, 'transfer-cancel'), isTrue);
      expect(tester.takeException(), isNull);
    });

    testWidgets('Edit re-reads the draft before opening it', (tester) async {
      final api = _Api();
      await _pump(tester, api, ['INVENTORY_VIEW', 'INVENTORY_ADJUST']);
      await _select(tester, 'STF-0001');
      await tester.tap(find.byKey(const ValueKey('transfer-edit')));
      await tester.pumpAndSettle();

      expect(api.fetchedId, StockTransferRecord.fromJson(_draft).id);
      expect(tester.takeException(), isNull);
    });

    testWidgets('a viewer cannot write', (tester) async {
      await _pump(tester, _Api(), ['INVENTORY_VIEW']);
      await _select(tester, 'STF-0001');

      expect(
        tester
            .widget<FilledButton>(find.byKey(const ValueKey('transfer-new')))
            .onPressed,
        isNull,
      );
      expect(_enabled(tester, 'transfer-dispatch'), isFalse);
      expect(_enabled(tester, 'transfer-cancel'), isFalse);
    });

    testWidgets('a new draft sends exactly the declared keys', (tester) async {
      final _Api api = _Api();
      await _pump(tester, api, ['INVENTORY_VIEW', 'INVENTORY_ADJUST']);
      await _fillDialog(tester);

      await tester.tap(find.byKey(const ValueKey('transfer-save')));
      await tester.pumpAndSettle();

      final Json body = api.created!;
      expect(
        body.keys.toSet(),
        {
          'transfer_date',
          'from_warehouse_id',
          'to_warehouse_id',
          'vehicle_number',
          'lines',
        },
      );
      expect(body['from_warehouse_id'], 'wh-1');
      expect(body['to_warehouse_id'], 'wh-2');
      expect(body['vehicle_number'], 'KA01AB1234');
      expect(body['lines'], [
        {'product_id': 'p-sack', 'quantity': '10'},
      ]);
      expect(find.byType(StockTransferDialog), findsNothing);
      expect(tester.takeException(), isNull);
    });

    testWidgets('a refusal keeps the dialog open with the message',
        (tester) async {
      final _Api api = _Api(refuse: 'Choose two different warehouses.');
      await _pump(tester, api, ['INVENTORY_VIEW', 'INVENTORY_ADJUST']);
      await _fillDialog(tester);

      await tester.tap(find.byKey(const ValueKey('transfer-save')));
      await tester.pumpAndSettle();

      expect(api.createCalls, 1);
      expect(find.byType(StockTransferDialog), findsOneWidget);
      expect(find.text('Choose two different warehouses.'), findsOneWidget);
      expect(find.text('10'), findsOneWidget);
    });

    testWidgets('the same warehouse twice is not sent', (tester) async {
      final _Api api = _Api();
      await _pump(tester, api, ['INVENTORY_VIEW', 'INVENTORY_ADJUST']);
      await tester.tap(find.byKey(const ValueKey('transfer-new')));
      await tester.pumpAndSettle();
      await _pick(tester, 'transfer-from', 'WH-001 - Central Warehouse');
      await _pick(tester, 'transfer-to', 'WH-001 - Central Warehouse');

      await tester.tap(find.byKey(const ValueKey('transfer-save')));
      await tester.pumpAndSettle();

      expect(api.createCalls, 0);
      expect(find.text('The two warehouses must be different.'),
          findsOneWidget);
    });

    testWidgets('dispatch sends the vehicle typed', (tester) async {
      final _Api api = _Api();
      await _pump(tester, api, ['INVENTORY_VIEW', 'INVENTORY_ADJUST']);
      await _select(tester, 'STF-0001');

      await tester.tap(find.byKey(const ValueKey('transfer-dispatch')));
      await tester.pumpAndSettle();
      expect(find.byType(DispatchTransferDialog), findsOneWidget);
      await _enter(tester, 'dispatch-vehicle', 'MH12XY9999');
      await tester.tap(find.byKey(const ValueKey('dispatch-save')));
      await tester.pumpAndSettle();

      expect(api.dispatchedId, 'st-1');
      expect(api.dispatchBody!['vehicle_number'], 'MH12XY9999');
      expect(find.byType(DispatchTransferDialog), findsNothing);
    });

    testWidgets('receiving shows the shortage and sends what arrived',
        (tester) async {
      final _Api api = _Api();
      await _pump(tester, api, ['INVENTORY_VIEW', 'INVENTORY_ADJUST']);
      await _select(tester, 'STF-0002');

      await tester.tap(find.byKey(const ValueKey('transfer-receive')));
      await tester.pumpAndSettle();
      expect(find.byType(ReceiveTransferDialog), findsOneWidget);
      expect(find.text('Short 0'), findsOneWidget);

      await _enter(tester, 'receive-received-0', '8');
      await _enter(tester, 'receive-damaged-0', '1');
      await tester.pumpAndSettle();
      expect(find.text('Short 2'), findsOneWidget);

      await tester.tap(find.byKey(const ValueKey('receive-save')));
      await tester.pumpAndSettle();

      expect(api.receivedId, 'st-2');
      expect(api.receiveBody!['lines'], [
        {'line_number': 1, 'received_quantity': '8', 'damaged_quantity': '1'},
      ]);
      expect(find.byType(ReceiveTransferDialog), findsNothing);
      expect(tester.takeException(), isNull);
    });

    testWidgets('more received than sent is not sent', (tester) async {
      final _Api api = _Api();
      await _pump(tester, api, ['INVENTORY_VIEW', 'INVENTORY_ADJUST']);
      await _select(tester, 'STF-0002');
      await tester.tap(find.byKey(const ValueKey('transfer-receive')));
      await tester.pumpAndSettle();

      await _enter(tester, 'receive-received-0', '12');
      await tester.tap(find.byKey(const ValueKey('receive-save')));
      await tester.pumpAndSettle();

      expect(api.receivedId, isNull);
      expect(
        find.text('More of SACK - Rice sack was received than was sent.'),
        findsOneWidget,
      );
    });

    testWidgets('cancelling posts the reason typed', (tester) async {
      final _Api api = _Api();
      await _pump(tester, api, ['INVENTORY_VIEW', 'INVENTORY_ADJUST']);
      await _select(tester, 'STF-0002');

      await tester.tap(find.byKey(const ValueKey('transfer-cancel')));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField).last, 'Truck broke down');
      await tester.pump();
      await tester
          .tap(find.widgetWithText(FilledButton, 'Cancel transfer').last);
      await tester.pumpAndSettle();

      expect(api.cancelledId, 'st-2');
      expect(api.cancelReason, 'Truck broke down');
      expect(tester.takeException(), isNull);
    });

    testWidgets('print challan fetches the PDF', (tester) async {
      final _Api api = _Api();
      String? opened;
      await _pump(
        tester,
        api,
        ['INVENTORY_VIEW'],
        openPdf: (name, bytes) async => opened = name,
      );
      await _select(tester, 'STF-0002');

      await tester.tap(find.byKey(const ValueKey('transfer-challan')));
      await tester.pumpAndSettle();

      expect(api.challanId, 'st-2');
      expect(opened, 'Challan STF-0002');
    });
  });
}
