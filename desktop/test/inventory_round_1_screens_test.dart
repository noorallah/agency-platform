// Inventory round 1 (2026-10-08): the screen findings S4-S7 and S10-S12.
//
//   * S4  the adjustment dialog names the batch of a batch-held product;
//   * S5  Transactions shows the sign of a movement that took stock out;
//   * S6  a serial's warranty end before its start is refused by name;
//   * S7  the Expiry Monitor keeps its own six counters on the page line;
//   * S10 the Adjustment Limits refusal names the role as the row shows it;
//   * S11 Transactions' Type column uses the words of its own filter;
//   * S12 the opening stock reference is not prefilled.

import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/batch_serial.dart';
import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/adjustment_approval.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/ui/inventory/adjustment_limits_dialog.dart';
import 'package:agency_desktop/ui/inventory/batch_management_page.dart';
import 'package:agency_desktop/ui/inventory/inventory_management_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/access_token.dart';

Json _paged(List<Json> rows) => {
      'data': rows,
      'pagination': {
        'page': 1,
        'page_size': 20,
        'total_records': rows.length,
        'total_pages': 1,
      },
    };

BatchRecord _batch(String number) => BatchRecord.fromJson(<String, dynamic>{
      'id': 'batch-$number',
      'firm_id': 'firm-1',
      'product_id': 'p-1',
      'product_code': 'P1',
      'product_name': 'Detergent',
      'warehouse_id': 'w-1',
      'warehouse_code': 'WH',
      'warehouse_name': 'North',
      'branch_id': 'b-1',
      'batch_number': number,
      'expiry_date': '2026-12-31',
      'status': 'ACTIVE',
      'quantity': '20',
      'available_quantity': '20',
    });

class _Api extends ApiClient {
  _Api({this.batchRows = const []})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<BatchRecord> batchRows;
  List<Json> transactionRows = const [];

  @override
  Future<List<StorageNodeRecord>> storageNodes(
    String warehouseId, {
    bool includeDeleted = false,
  }) async =>
      const [];

  @override
  Future<PagedResult<BatchRecord>> batches({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    BatchQuery filters = const BatchQuery(),
  }) async =>
      PagedResult<BatchRecord>(items: batchRows, total: batchRows.length);

  @override
  Future<BatchSummaryRecord> batchSummary() async => const BatchSummaryRecord(
        totalBatches: 2,
        nearExpiry: 1,
        expired: 0,
        quarantine: 0,
      );

  @override
  Future<ExpiryDashboardRecord> expiryDashboard() async =>
      const ExpiryDashboardRecord(
        expiredToday: 0,
        expireIn7Days: 1,
        expireIn30Days: 2,
        totalExpired: 0,
        quarantine: 0,
        recalled: 0,
      );

  @override
  Future<PagedResult<SerialRecord>> serials({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    SerialQuery filters = const SerialQuery(),
  }) async =>
      const PagedResult<SerialRecord>(items: [], total: 0);

  @override
  Future<PagedResult<Role>> roles({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
  }) async =>
      PagedResult<Role>(items: [
        Role.fromJson(const {
          'id': 'r-1',
          'code': 'SALES_MANAGER',
          'name': 'Sales Manager',
          'is_active': true,
        }),
      ], total: 1);

  @override
  Future<List<RoleAdjustmentLimit>> adjustmentLimits() async => const [
        RoleAdjustmentLimit(roleCode: 'SALES_MANAGER', maxValue: '100'),
      ];

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
    if (path == '/api/v1/inventory/transactions') {
      return _paged(transactionRows);
    }
    return _paged(const []);
  }
}

void _viewport(WidgetTester tester, [Size size = const Size(1366, 768)]) {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
}

Json _transaction(String type, String quantity, String currentDelta) => {
      'id': 'txn-$type',
      'transaction_id': 'txn-$type',
      'product_code': 'P1',
      'product_name': 'Detergent',
      'warehouse_code': 'WH',
      'transaction_type': type,
      'reference_number': 'REF-$type',
      'transaction_date': '2026-10-08',
      'quantity': quantity,
      'current_quantity_delta': currentDelta,
      'new_current_quantity': '50',
    };

Future<void> _pumpInventory(
  WidgetTester tester,
  _Api api,
  InventorySection section,
  List<String> codes,
) async {
  _viewport(tester, const Size(1600, 1000));
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: InventoryManagementPage(
        api: api,
        preferences: DesktopPreferencesService(),
        permissions: PermissionService()
          ..applyAccessToken(accessTokenFor(codes)),
        hasActiveFirm: true,
        section: section,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

Future<void> _pumpBatchPage(
  WidgetTester tester,
  BatchSerialSection section,
  List<String> codes, {
  bool phase2 = false,
}) async {
  _viewport(tester, const Size(1600, 1000));
  final Directory temp = Directory.systemTemp.createTempSync('round-1');
  addTearDown(() => temp.deleteSync(recursive: true));
  await tester.pumpWidget(MaterialApp(
    builder: phase2 ? (context, child) => Phase2Scope(child: child!) : null,
    home: Scaffold(
      body: BatchManagementPage(
        api: _Api(batchRows: [_batch('B-001'), _batch('B-002')]),
        preferences: DesktopPreferencesService(directory: temp),
        permissions: PermissionService()
          ..applyAccessToken(accessTokenFor(codes)),
        hasActiveFirm: true,
        section: section,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

Widget _adjustmentDialog(_Api api, List<Json> saved) {
  final BranchRecord branch = BranchRecord.fromJson(
      const {'id': 'b-1', 'code': 'BR', 'name': 'Main'});
  final WarehouseRecord warehouse = WarehouseRecord.fromJson(
      const {'id': 'w-1', 'branch_id': 'b-1', 'code': 'WH', 'name': 'North'});
  final Product product = Product.fromJson(const {
    'id': 'p-1',
    'code': 'P1',
    'name': 'Detergent',
    'product_type': 'STOCK_ITEM',
    'status': 'ACTIVE',
    'unit': 'BOX',
  });
  return MaterialApp(
    home: Scaffold(
      body: StockAdjustmentDialog(
        api: api,
        branches: [branch],
        warehouses: [warehouse],
        products: [product],
        onSave: (StockAdjustmentDraft draft) async =>
            saved.add(draft.toJson()),
      ),
    ),
  );
}

void main() {
  group('S4 the adjustment dialog and batches', () {
    testWidgets('a batch-held product offers a Batch box and sends batch_id',
        (tester) async {
      _viewport(tester);
      final List<Json> saved = [];
      await tester.pumpWidget(_adjustmentDialog(
          _Api(batchRows: [_batch('B-001'), _batch('B-002')]), saved));
      await tester.pumpAndSettle();

      final Finder box =
          find.widgetWithText(DropdownButtonFormField<String>, 'Batch');
      expect(box, findsOneWidget);
      await tester.ensureVisible(box);
      await tester.tap(box);
      await tester.pumpAndSettle();
      await tester.tap(find.textContaining('B-002').last);
      await tester.pumpAndSettle();
      await tester.enterText(
          find.widgetWithText(TextField, 'Quantity (+ or - value)'), '-3');
      await tester.tap(find.widgetWithText(FilledButton, 'Post adjustment'));
      await tester.pumpAndSettle();

      expect(saved.single['batch_id'], 'batch-B-002');
      expect(saved.single['quantity'], -3);
    });

    testWidgets('a product with no batches shows no Batch box and sends none',
        (tester) async {
      _viewport(tester);
      final List<Json> saved = [];
      await tester.pumpWidget(_adjustmentDialog(_Api(), saved));
      await tester.pumpAndSettle();

      expect(find.widgetWithText(DropdownButtonFormField<String>, 'Batch'),
          findsNothing);
      await tester.enterText(
          find.widgetWithText(TextField, 'Quantity (+ or - value)'), '-3');
      await tester.tap(find.widgetWithText(FilledButton, 'Post adjustment'));
      await tester.pumpAndSettle();

      expect(saved.single.containsKey('batch_id'), isFalse);
    });

    testWidgets('a negative adjustment with no batch chosen is refused first',
        (tester) async {
      _viewport(tester);
      final List<Json> saved = [];
      await tester.pumpWidget(
          _adjustmentDialog(_Api(batchRows: [_batch('B-001')]), saved));
      await tester.pumpAndSettle();

      await tester.enterText(
          find.widgetWithText(TextField, 'Quantity (+ or - value)'), '-3');
      await tester.tap(find.widgetWithText(FilledButton, 'Post adjustment'));
      await tester.pumpAndSettle();

      expect(saved, isEmpty);
      expect(find.textContaining('Choose the batch'), findsOneWidget);
    });
  });

  group('S5 and S11 the Transactions grid', () {
    testWidgets('shows the sign of stock taken out and the filter\'s words',
        (tester) async {
      final _Api api = _Api()
        ..transactionRows = [
          _transaction('ADJUSTMENT', '59', '-59'),
          _transaction('QUARANTINE_RELEASE', '4', '4'),
          _transaction('RESERVE', '7', '0'),
          _transaction('MYSTERY_TYPE', '1', '1'),
        ];
      await _pumpInventory(
          tester, api, InventorySection.transactions, ['INVENTORY_VIEW']);

      expect(find.text('-59'), findsOneWidget);
      expect(find.text('4'), findsOneWidget);
      expect(find.text('7'), findsOneWidget);
      expect(find.text('Adjustment / count'), findsWidgets);
      expect(find.text('Quarantine release'), findsOneWidget);
      expect(find.text('Reserved for an order'), findsOneWidget);
      expect(find.text('QUARANTINE_RELEASE'), findsNothing);
      // A code with no label shows as it is.
      expect(find.text('MYSTERY_TYPE'), findsOneWidget);
    });
  });

  group('S12 opening stock', () {
    testWidgets('the reference starts empty and is asked for', (tester) async {
      await _pumpInventory(tester, _Api(), InventorySection.openingStock,
          ['INVENTORY_VIEW', 'OPENING_STOCK_CREATE']);
      await tester.tap(find.text('New opening stock'));
      await tester.pumpAndSettle();

      final TextField reference = tester
          .widget<TextField>(find.widgetWithText(TextField, 'Reference'));
      expect(reference.controller!.text, isEmpty);

      await tester.ensureVisible(find.widgetWithText(FilledButton, 'Save'));
      await tester.tap(find.widgetWithText(FilledButton, 'Save'));
      await tester.pumpAndSettle();
      expect(find.text('Reference is required.'), findsOneWidget);
    });
  });

  group('S7 the Expiry Monitor counters', () {
    testWidgets('shows its own six, not the batches list\'s four',
        (tester) async {
      await _pumpBatchPage(
          tester, BatchSerialSection.expiryMonitor, ['BATCH_VIEW'],
          phase2: true);

      for (final String label in [
        'Expired today',
        'In 7 days',
        'In 30 days',
        'Recalled',
      ]) {
        expect(find.text(label), findsWidgets, reason: label);
      }
      expect(find.text('Near expiry'), findsNothing);
      expect(find.text('Batches'), findsNothing);
    });
  });

  group('S6 the serial form', () {
    testWidgets('a warranty end before the start is refused by name',
        (tester) async {
      await _pumpBatchPage(tester, BatchSerialSection.serials,
          ['BATCH_VIEW', 'SERIAL_VIEW', 'SERIAL_CREATE']);
      await tester.tap(find.text('Add Serial'));
      await tester.pumpAndSettle();

      await tester.enterText(
          find.widgetWithText(TextFormField, 'Serial Number *'), 'SN-1');
      await tester.enterText(
          find.widgetWithText(
              TextFormField, 'Warranty Start (YYYY-MM-DD)'),
          '2026-10-08');
      await tester.enterText(
          find.widgetWithText(TextFormField, 'Warranty End (YYYY-MM-DD)'),
          '2026-10-01');
      await tester.tap(find.widgetWithText(FilledButton, 'Create'));
      await tester.pumpAndSettle();

      expect(find.text('Warranty end cannot be before warranty start.'),
          findsOneWidget);
    });
  });

  group('S10 the Adjustment Limits refusal', () {
    testWidgets('names the role as the row shows it', (tester) async {
      _viewport(tester);
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: AdjustmentLimitsDialog(
            api: _Api(),
            permissions: PermissionService()
              ..applyAccessToken(accessTokenFor(
                  ['INVENTORY_VIEW', 'INVENTORY_MANAGE_SETTINGS'])),
          ),
        ),
      ));
      await tester.pumpAndSettle();

      await tester.enterText(
          find.byKey(const ValueKey('adjustment-limit-amount-0')), '-5');
      await tester.tap(find.byKey(const ValueKey('adjustment-limits-save')));
      await tester.pumpAndSettle();

      expect(find.textContaining('The limit for Sales Manager must be'),
          findsOneWidget);
      expect(find.textContaining('SALES_MANAGER must'), findsNothing);
    });
  });
}
