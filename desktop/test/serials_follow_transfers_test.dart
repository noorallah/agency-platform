// D-STK-40, the desktop half: a serial-numbered product's units are named when
// stock moves between warehouses, and may be typed on an opening stock line.
//
//   * a transfer document sends `serial_ids` for a serial-tracked line and
//     nothing of the kind for an ordinary one;
//   * receiving names the short and the damaged units of a tracked line;
//   * the one-step transfer sends `serial_ids`;
//   * the opening stock editor sends `serial_numbers`, and a reopened draft
//     resends the ones it carried.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/batch_serial.dart';
import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/inventory.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/models/stock_transfer.dart';
import 'package:agency_desktop/ui/inventory/inventory_management_page.dart';
import 'package:agency_desktop/ui/inventory/stock_action_dialog.dart';
import 'package:agency_desktop/ui/inventory/stock_transfer_steps_dialogs.dart';
import 'package:agency_desktop/ui/inventory/stock_transfers_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions(List<String> codes) => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': codes,
  }));

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

Product _product(String id, String code, String name, {bool serial = false}) =>
    Product(
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
      trackSerial: serial,
    );

SerialRecord _serial(String id, String number) => SerialRecord.fromJson({
      'id': id,
      'product_id': 'p-tv',
      'serial_number': number,
      'status': 'AVAILABLE',
    });

const Map<String, dynamic> _inTransit = {
  'id': 'st-9',
  'transfer_number': 'STF-0009',
  'transfer_date': '2026-10-02',
  'from_warehouse_id': 'wh-1',
  'from_warehouse_name': 'Central Warehouse',
  'to_warehouse_id': 'wh-2',
  'to_warehouse_name': 'City Godown',
  'status': 'DISPATCHED',
  'version': 2,
  'lines': [
    {
      'line_number': 1,
      'product_id': 'p-tv',
      'product_code': 'TV',
      'product_name': 'Television',
      'quantity': '3.0000',
      'serial_tracked': true,
      'serials': [
        {'serial_id': 's1', 'serial_number': 'TV-001', 'status': 'IN_TRANSIT'},
        {'serial_id': 's2', 'serial_number': 'TV-002', 'status': 'IN_TRANSIT'},
        {'serial_id': 's3', 'serial_number': 'TV-003', 'status': 'IN_TRANSIT'},
      ],
    },
  ],
};

class _TransferApi extends ApiClient {
  _TransferApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  Json? created;
  Json? receiveBody;

  @override
  Future<List<StockTransferRecord>> stockTransfers({String? status}) async =>
      [StockTransferRecord.fromJson(_inTransit)];

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
        items: [
          _product('p-sack', 'SACK', 'Rice sack'),
          _product('p-tv', 'TV', 'Television', serial: true),
        ],
        total: 2,
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
  Future<PagedResult<SerialRecord>> serials({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    SerialQuery filters = const SerialQuery(),
  }) async =>
      PagedResult<SerialRecord>(
        items: [
          _serial('s1', 'TV-001'),
          _serial('s2', 'TV-002'),
          _serial('s3', 'TV-003'),
        ],
        total: 3,
      );

  @override
  Future<StockTransferRecord> createStockTransfer(Json data) async {
    created = data;
    return StockTransferRecord.fromJson(_inTransit);
  }

  @override
  Future<StockTransferRecord> receiveStockTransfer(
      String id, Json data) async {
    receiveBody = data;
    return StockTransferRecord.fromJson(_inTransit);
  }
}

Future<void> _pumpTransfers(WidgetTester tester, _TransferApi api) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: StockTransfersPage(
        api: api,
        permissions: _permissions(['INVENTORY_VIEW', 'INVENTORY_ADJUST']),
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
  await tester.pumpAndSettle();
}

Future<void> _tap(WidgetTester tester, String key) async {
  final Finder target = find.byKey(ValueKey<String>(key));
  await tester.ensureVisible(target);
  await tester.tap(target);
  await tester.pumpAndSettle();
}

// The opening stock side: a draft that already carries serial numbers.
Json _paged(List<Json> rows) => {
      'data': rows,
      'pagination': {
        'page': 1,
        'page_size': 20,
        'total_records': rows.length,
        'total_pages': 1,
      },
    };

final Json _openingDraft = {
  'id': 'batch-1',
  'version': 1,
  'firm_id': 'firm-1',
  'branch_id': 'branch-1',
  'branch_code': 'HO',
  'branch_name': 'Head Office',
  'warehouse_id': 'wh-1',
  'warehouse_code': 'MAIN',
  'warehouse_name': 'Main Store',
  'reference_number': 'OPEN-009',
  'posting_date': '2026-09-25',
  'source_format': 'MANUAL',
  'status': 'DRAFT',
  'lines': [
    {
      'id': 'line-1',
      'line_number': 1,
      'product_id': 'prod-tv',
      'product_code': 'TV',
      'product_name': 'Television',
      'quantity': '2.0000',
      'unit_cost': '5000.00',
      'serial_tracked': true,
      'serial_numbers': ['SN-A', 'SN-B'],
    },
  ],
  'created_at': '2026-09-25T00:00:00Z',
  'updated_at': '2026-09-25T00:00:00Z',
};

class _OpeningApi extends ApiClient {
  _OpeningApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Json> created = <Json>[];
  final List<Json> updated = <Json>[];

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
    if (method == 'POST' && path == '/api/v1/inventory/opening-stock') {
      created.add(body!);
      return {'data': _openingDraft};
    }
    if (method == 'PUT' && path == '/api/v1/inventory/opening-stock/batch-1') {
      updated.add(body!);
      return {'data': _openingDraft};
    }
    if (method == 'GET' && path == '/api/v1/inventory/opening-stock') {
      return _paged([_openingDraft]);
    }
    if (path == '/api/v1/products') {
      return _paged([
        {
          'id': 'prod-tv',
          'code': 'TV',
          'name': 'Television',
          'purchase_price': '5000.00',
          'status': 'ACTIVE',
          'track_serial': true,
        },
        {
          'id': 'prod-sack',
          'code': 'SACK',
          'name': 'Rice sack',
          'purchase_price': '80.00',
          'status': 'ACTIVE',
        },
      ]);
    }
    if (path == '/api/v1/branches') {
      return _paged([
        {'id': 'branch-1', 'code': 'HO', 'name': 'Head Office'},
      ]);
    }
    if (path == '/api/v1/warehouses') {
      return _paged([
        {
          'id': 'wh-1',
          'code': 'MAIN',
          'name': 'Main Store',
          'branch_id': 'branch-1',
        },
      ]);
    }
    return _paged(const []);
  }
}

Future<void> _pumpOpening(WidgetTester tester, _OpeningApi api) async {
  await tester.binding.setSurfaceSize(const Size(1600, 1000));
  addTearDown(() => tester.binding.setSurfaceSize(null));
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: InventoryManagementPage(
        api: api,
        preferences: DesktopPreferencesService(),
        permissions: _permissions([
          'INVENTORY_VIEW',
          'OPENING_STOCK_CREATE',
          'OPENING_STOCK_UPDATE',
        ]),
        hasActiveFirm: true,
        section: InventorySection.openingStock,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

void main() {
  group('the stock transfer document', () {
    testWidgets('names the units of a serial-tracked line, and only those',
        (tester) async {
      final _TransferApi api = _TransferApi();
      await _pumpTransfers(tester, api);
      await tester.tap(find.byKey(const ValueKey('transfer-new')));
      await tester.pumpAndSettle();
      await _pick(tester, 'transfer-from', 'WH-001 - Central Warehouse');
      await _pick(tester, 'transfer-to', 'WH-002 - City Godown');

      await _pick(tester, 'transfer-product-0', 'TV - Television');
      await _enter(tester, 'transfer-quantity-0', '2');
      expect(find.textContaining('0 of 2 picked'), findsOneWidget);
      await _tap(tester, 'serial-pick-s1');
      await _tap(tester, 'serial-pick-s3');
      expect(find.textContaining('2 of 2 picked'), findsOneWidget);

      await _tap(tester, 'transfer-line-add');
      await _pick(tester, 'transfer-product-1', 'SACK - Rice sack');
      await _enter(tester, 'transfer-quantity-1', '5');
      // An ordinary product offers no picker.
      expect(find.textContaining('Pick the units'), findsOneWidget);

      await _tap(tester, 'transfer-save');

      final List<dynamic> lines = api.created!['lines'] as List<dynamic>;
      expect(lines, [
        {
          'product_id': 'p-tv',
          'quantity': '2',
          'serial_ids': ['s1', 's3'],
        },
        {'product_id': 'p-sack', 'quantity': '5'},
      ]);
      expect(tester.takeException(), isNull);
    });

    testWidgets('a saved transfer shows its serial numbers', (tester) async {
      await _pumpTransfers(tester, _TransferApi());
      await tester.tap(find.text('STF-0009'));
      await tester.pumpAndSettle();

      final Finder serials = find.byKey(const ValueKey('transfer-serials-1'));
      expect(serials, findsOneWidget);
      expect(
        (tester.widget<Text>(serials)).data,
        contains('TV-001 (in transit), TV-002 (in transit)'),
      );
    });

    testWidgets('receiving names which units are short and which damaged',
        (tester) async {
      final _TransferApi api = _TransferApi();
      await _pumpTransfers(tester, api);
      await tester.tap(find.text('STF-0009'));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('transfer-receive')));
      await tester.pumpAndSettle();
      expect(find.byType(ReceiveTransferDialog), findsOneWidget);
      // Everything arrived whole: nothing to name.
      expect(find.textContaining('Which units'), findsNothing);

      await _enter(tester, 'receive-received-0', '1');
      await _enter(tester, 'receive-damaged-0', '1');
      expect(find.textContaining('Which units did not arrive - 0 of 2'),
          findsOneWidget);
      expect(find.textContaining('Which units arrived damaged - 0 of 1'),
          findsOneWidget);

      // Saving before naming them is refused here, not sent.
      await _tap(tester, 'receive-save');
      expect(api.receiveBody, isNull);
      expect(find.textContaining('did not arrive'), findsWidgets);

      await _tap(tester, 'receive-short-pick-0-s1');
      await _tap(tester, 'receive-short-pick-0-s2');
      await _tap(tester, 'receive-damaged-pick-0-s3');
      await _tap(tester, 'receive-save');

      expect(api.receiveBody!['lines'], [
        {
          'line_number': 1,
          'received_quantity': '1',
          'damaged_quantity': '1',
          'short_serial_ids': ['s1', 's2'],
          'damaged_serial_ids': ['s3'],
        },
      ]);
      expect(tester.takeException(), isNull);
    });
  });

  group('the one-step transfer', () {
    Future<Json?> run(
      WidgetTester tester, {
      required bool serial,
      required List<String> pick,
    }) async {
      tester.view.physicalSize = const Size(1366, 768);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      Json? sent;
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: Builder(
            builder: (context) => TextButton(
              onPressed: () => showDialog<Json>(
                context: context,
                builder: (_) => StockActionDialog(
                  action: StockAction.transfer,
                  productLabel: 'TV - Television',
                  warehouseLabel: 'Central',
                  sourceWarehouseId: 'wh-1',
                  available: 10,
                  quarantined: 0,
                  trackSerial: serial,
                  loadSerials: () async => const [
                    PickedSerial(id: 's1', serialNumber: 'TV-001'),
                    PickedSerial(id: 's2', serialNumber: 'TV-002'),
                  ],
                  warehouses: const [
                    WarehouseOption(id: 'wh-1', name: 'Central'),
                    WarehouseOption(id: 'wh-2', name: 'City'),
                  ],
                  onSave: (Json draft) async => sent = draft,
                ),
              ),
              child: const Text('open'),
            ),
          ),
        ),
      ));
      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();
      await tester.enterText(find.widgetWithText(TextField, 'Quantity'), '2');
      await tester.tap(find.widgetWithText(
          DropdownButtonFormField<String>, 'Move it to'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('City').last);
      await tester.pumpAndSettle();
      for (final String id in pick) {
        await tester.tap(find.byKey(ValueKey<String>('serial-pick-$id')));
        await tester.pumpAndSettle();
      }
      await tester.tap(find.widgetWithText(FilledButton, 'Transfer'));
      await tester.pumpAndSettle();
      return sent;
    }

    testWidgets('sends the units picked', (tester) async {
      final Json? sent = await run(tester, serial: true, pick: ['s1', 's2']);
      expect(sent, isNotNull);
      expect(sent!['serial_ids'], ['s1', 's2']);
      expect(sent['to_warehouse_id'], 'wh-2');
      // The page builds the request body from this draft; the key survives it.
      expect(
        stockActionBody(
          action: StockAction.transfer,
          draft: sent,
          branchId: 'b',
          warehouseId: 'wh-1',
          productId: 'p-tv',
        )['serial_ids'],
        ['s1', 's2'],
      );
    });

    testWidgets('is not sent with too few units picked', (tester) async {
      final Json? sent = await run(tester, serial: true, pick: ['s1']);
      expect(sent, isNull);
      expect(find.textContaining('2 needed, 1 picked'), findsOneWidget);
    });

    testWidgets('an ordinary product offers no picker and sends none',
        (tester) async {
      final Json? sent = await run(tester, serial: false, pick: const []);
      expect(sent, isNotNull);
      expect(sent!.containsKey('serial_ids'), isFalse);
    });
  });

  group('opening stock', () {
    testWidgets('a serial-tracked line sends the numbers typed',
        (tester) async {
      final _OpeningApi api = _OpeningApi();
      await _pumpOpening(tester, api);
      await tester.tap(find.text('New opening stock'));
      await tester.pumpAndSettle();
      await tester
          .tap(find.widgetWithText(DropdownButtonFormField<String>, 'Product'));
      await tester.pumpAndSettle();
      // An ordinary product has no serial box.
      await tester.tap(find.text('SACK - Rice sack').last);
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('opening-serials-0')), findsNothing);

      await tester
          .tap(find.widgetWithText(DropdownButtonFormField<String>, 'Product'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('TV - Television').last);
      await tester.pumpAndSettle();
      await tester.enterText(find.widgetWithText(TextField, 'Quantity'), '2');
      await tester.enterText(
          find.widgetWithText(TextField, 'Reference'), 'OPEN-010');
      await tester.enterText(
          find.byKey(const ValueKey('opening-serials-0')), 'SN-1\n SN-2 \n');
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.widgetWithText(FilledButton, 'Save'));
      await tester.tap(find.widgetWithText(FilledButton, 'Save'));
      await tester.pumpAndSettle();

      expect(api.created, hasLength(1));
      final Json line = (api.created.single['lines'] as List).single as Json;
      expect(line['serial_numbers'], ['SN-1', 'SN-2']);
    });

    testWidgets('a reopened draft resends the numbers it carried',
        (tester) async {
      final _OpeningApi api = _OpeningApi();
      await _pumpOpening(tester, api);
      // Pick the draft the way the grid does when its row is clicked.
      final EnterpriseDataGrid<OpeningStockBatchRecord> grid = tester.widget(
          find.byType(EnterpriseDataGrid<OpeningStockBatchRecord>));
      grid.onSelect(grid.items.single);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Edit draft'));
      await tester.pumpAndSettle();

      final TextField box = tester
          .widget<TextField>(find.byKey(const ValueKey('opening-serials-0')));
      expect(box.controller!.text, 'SN-A\nSN-B');
      await tester.ensureVisible(find.widgetWithText(FilledButton, 'Update'));
      await tester.tap(find.widgetWithText(FilledButton, 'Update'));
      await tester.pumpAndSettle();

      expect(api.updated, hasLength(1));
      final Json line = (api.updated.single['lines'] as List).single as Json;
      expect(line['serial_numbers'], ['SN-A', 'SN-B']);
    });

    test('a line reads its serial fields, absent meaning none', () {
      final OpeningStockLineRecord with_ = OpeningStockLineRecord.fromJson({
        'id': 'l',
        'serial_tracked': true,
        'serial_numbers': ['A', 'B'],
      });
      expect(with_.serialTracked, isTrue);
      expect(with_.serialNumbers, ['A', 'B']);
      final OpeningStockLineRecord without =
          OpeningStockLineRecord.fromJson({'id': 'l'});
      expect(without.serialTracked, isFalse);
      expect(without.serialNumbers, isEmpty);
    });
  });
}
