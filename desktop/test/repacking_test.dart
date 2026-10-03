// STK-4, the desktop half: repacking and bulk breaking.
//
//   * the Repacking screen lists the firm's repacks and shows what a
//     selected one consumed, wasted and carried into each produced line;
//   * a new repack posts consume and produce lines with the wastage;
//   * a refusal keeps the dialog open with the server's message;
//   * cancelling posts the reason typed;
//   * posting and cancelling need INVENTORY_ADJUST.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/models/repack.dart';
import 'package:agency_desktop/ui/inventory/repack_dialog.dart';
import 'package:agency_desktop/ui/inventory/repacking_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions(List<String> codes) => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': codes,
  }));

const Map<String, dynamic> _posted = {
  'id': 'rp-1',
  'repack_number': 'RPK-0001',
  'repack_date': '2026-10-01',
  'branch_id': 'branch-1',
  'warehouse_id': 'warehouse-1',
  'wastage_percent': '2.0000',
  'consumed_value': '1000.00',
  'wastage_value': '20.00',
  'status': 'POSTED',
  'remarks': 'Sack to packets',
  'version': 1,
  'lines': [
    {
      'line_number': 1,
      'kind': 'CONSUME',
      'product_id': 'p-sack',
      'product_code': 'SACK',
      'product_name': 'Rice sack',
      'quantity': '10.0000',
      'value': '1000.00',
    },
    {
      'line_number': 2,
      'kind': 'PRODUCE',
      'product_id': 'p-pkt',
      'product_code': 'PKT',
      'product_name': 'Rice packet',
      'quantity': '490.0000',
      'value': '980.00',
    },
  ],
};

const BranchRecord _branch = BranchRecord(
  id: 'branch-1',
  firmId: 'firm-1',
  code: 'BR-001',
  name: 'Main Branch',
  displayName: 'Main Branch',
  description: '',
  branchTypeId: 'type-1',
  branchManagerId: '',
  businessProfileId: 'profile-1',
  email: '',
  phone: '',
  mobile: '',
  cityId: '',
  stateId: '',
  countryId: '',
  currencyCode: 'INR',
  status: 'ACTIVE',
  isDefault: true,
  isDeleted: false,
  warehouseCount: 1,
  createdAt: '2026-08-01T00:00:00Z',
);

const WarehouseRecord _warehouse = WarehouseRecord(
  id: 'warehouse-1',
  firmId: 'firm-1',
  branchId: 'branch-1',
  code: 'WH-001',
  name: 'Central Warehouse',
  displayName: 'Central Warehouse',
  warehouseTypeId: 'type-1',
  businessProfileId: 'profile-1',
  capacity: '0',
  capacityUnit: 'EA',
  status: 'ACTIVE',
  isDefault: true,
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

  /// When set, posting is refused with this message.
  String? refuse;
  Json? created;
  int createCalls = 0;
  String? cancelledId;
  String? cancelReason;

  @override
  Future<List<RepackRecord>> repacks() async => [RepackRecord.fromJson(_posted)];

  @override
  Future<PagedResult<BranchRecord>> branches({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    BranchQuery filters = const BranchQuery(),
  }) async =>
      const PagedResult<BranchRecord>(items: [_branch], total: 1);

  @override
  Future<PagedResult<WarehouseRecord>> warehouses({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    WarehouseQuery filters = const WarehouseQuery(),
  }) async =>
      const PagedResult<WarehouseRecord>(items: [_warehouse], total: 1);

  @override
  Future<PagedResult<Product>> products({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    ProductQuery filters = const ProductQuery(),
  }) async {
    final List<Product> items = [
      _product('p-sack', 'SACK', 'Rice sack'),
      _product('p-pkt', 'PKT', 'Rice packet'),
    ];
    return PagedResult<Product>(items: items, total: items.length);
  }

  @override
  Future<RepackRecord> createRepack(Json data) async {
    createCalls++;
    final String? message = refuse;
    if (message != null) throw ApiException(message, statusCode: 422);
    created = data;
    return RepackRecord.fromJson(_posted);
  }

  @override
  Future<RepackRecord> cancelRepack(String id, String reason) async {
    cancelledId = id;
    cancelReason = reason;
    return RepackRecord.fromJson(_posted);
  }
}

Future<void> _pump(WidgetTester tester, _Api api, List<String> codes) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: RepackingPage(api: api, permissions: _permissions(codes)),
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

/// Opens the dialog and fills a valid repack: 10 of the sack into 490 packets.
Future<void> _fillDialog(WidgetTester tester) async {
  await tester.tap(find.byKey(const ValueKey('repack-new')));
  await tester.pumpAndSettle();
  await _pick(tester, 'repack-branch', 'BR-001 - Main Branch');
  await _pick(tester, 'repack-warehouse-branch-1', 'WH-001 - Central Warehouse');
  await _enter(tester, 'repack-wastage', '2');
  await _pick(tester, 'repack-consume-product-0', 'SACK - Rice sack');
  await _enter(tester, 'repack-consume-quantity-0', '10');
  await _pick(tester, 'repack-produce-product-0', 'PKT - Rice packet');
  await _enter(tester, 'repack-produce-quantity-0', '490');
}

void main() {
  group('the Repacking screen', () {
    testWidgets('lists repacks and shows value, wastage and carried value',
        (tester) async {
      await _pump(tester, _Api(), ['INVENTORY_VIEW']);

      expect(find.text('RPK-0001'), findsOneWidget);
      expect(find.text('1000.00'), findsOneWidget);
      expect(find.text('Posted'), findsOneWidget);

      await tester.tap(find.text('RPK-0001'));
      await tester.pumpAndSettle();

      expect(find.byKey(const ValueKey('repack-details')), findsOneWidget);
      expect(find.text('Consumed value 1000.00'), findsOneWidget);
      expect(find.text('Wastage 20.00 (2.0000%)'), findsOneWidget);
      expect(find.text('SACK - Rice sack'), findsOneWidget);
      expect(find.text('PKT - Rice packet'), findsOneWidget);
      expect(find.text('Carried value 980.00'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('a viewer cannot post or cancel', (tester) async {
      await _pump(tester, _Api(), ['INVENTORY_VIEW']);
      await tester.tap(find.text('RPK-0001'));
      await tester.pumpAndSettle();

      expect(
        tester
            .widget<FilledButton>(find.byKey(const ValueKey('repack-new')))
            .onPressed,
        isNull,
      );
      expect(
        tester
            .widget<OutlinedButton>(find.byKey(const ValueKey('repack-cancel')))
            .onPressed,
        isNull,
      );
    });

    testWidgets('a new repack posts consume and produce lines with wastage',
        (tester) async {
      final _Api api = _Api();
      await _pump(tester, api, ['INVENTORY_VIEW', 'INVENTORY_ADJUST']);
      await _fillDialog(tester);

      await tester.tap(find.byKey(const ValueKey('repack-save')));
      await tester.pumpAndSettle();

      final Json body = api.created!;
      expect(body['branch_id'], 'branch-1');
      expect(body['warehouse_id'], 'warehouse-1');
      expect(body['wastage_percent'], '2');
      expect(body['lines'], [
        {'kind': 'CONSUME', 'product_id': 'p-sack', 'quantity': '10'},
        {'kind': 'PRODUCE', 'product_id': 'p-pkt', 'quantity': '490'},
      ]);
      expect(find.byType(RepackDialog), findsNothing);
      expect(tester.takeException(), isNull);
    });

    testWidgets('a refusal keeps the dialog open with the message',
        (tester) async {
      final _Api api = _Api(refuse: 'Only 4 of Rice sack is in stock.');
      await _pump(tester, api, ['INVENTORY_VIEW', 'INVENTORY_ADJUST']);
      await _fillDialog(tester);

      await tester.tap(find.byKey(const ValueKey('repack-save')));
      await tester.pumpAndSettle();

      expect(api.createCalls, 1);
      expect(find.byType(RepackDialog), findsOneWidget);
      expect(find.text('Only 4 of Rice sack is in stock.'), findsOneWidget);
      // Everything typed is still there.
      expect(find.text('490'), findsOneWidget);
    });

    testWidgets('nothing is sent until both sides have a line',
        (tester) async {
      final _Api api = _Api();
      await _pump(tester, api, ['INVENTORY_VIEW', 'INVENTORY_ADJUST']);
      await tester.tap(find.byKey(const ValueKey('repack-new')));
      await tester.pumpAndSettle();
      await _pick(tester, 'repack-branch', 'BR-001 - Main Branch');

      await tester.tap(find.byKey(const ValueKey('repack-save')));
      await tester.pumpAndSettle();

      expect(api.createCalls, 0);
      expect(find.text('Add at least one product to consume.'), findsOneWidget);
    });

    testWidgets('cancelling posts the reason typed', (tester) async {
      final _Api api = _Api();
      await _pump(tester, api, ['INVENTORY_VIEW', 'INVENTORY_ADJUST']);
      await tester.tap(find.text('RPK-0001'));
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const ValueKey('repack-cancel')));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField).last, 'Counted wrong');
      await tester.tap(find.widgetWithText(FilledButton, 'Cancel repack').last);
      await tester.pumpAndSettle();

      expect(api.cancelledId, 'rp-1');
      expect(api.cancelReason, 'Counted wrong');
      expect(tester.takeException(), isNull);
    });
  });
}
