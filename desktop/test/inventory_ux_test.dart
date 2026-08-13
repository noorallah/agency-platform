import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/batch_serial.dart';
import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/inventory.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/ui/inventory/batch_management_page.dart';
import 'package:agency_desktop/ui/inventory/inventory_import_wizard.dart';
import 'package:agency_desktop/ui/workspace/global_search.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('inventory import wizard validates CSV opening stock files',
      (tester) async {
    _setDesktopSurface(tester);
    final Directory temp = Directory.systemTemp.createTempSync('inventory-csv');
    final File file =
        File('${temp.path}${Platform.pathSeparator}opening-stock.csv')
          ..writeAsStringSync(
            'ProductCode,BranchCode,WarehouseCode,StorageCode,Quantity,ReferenceNumber,PostingDate\n'
            'MED-001,BR-001,WH-001,RACK-A,10,OPEN-001,2026-08-02\n',
          );
    final _InventoryImportApi api = _InventoryImportApi();
    final DesktopPreferencesService preferences =
        DesktopPreferencesService(directory: temp);
    final InventoryImportWizardController controller =
        InventoryImportWizardController();

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: InventoryImportWizard(
            api: api,
            preferences: preferences,
            branches: [_branch],
            warehouses: [_warehouse],
            products: [_product],
            initialType: InventoryImportType.inventoryAdjustment,
            controller: controller,
            onViewImportedRecords: (_) async {},
          ),
        ),
      ),
    );

    await tester.runAsync(
      () => controller.loadPreparedFile(
          'opening-stock.csv', file.readAsBytesSync()),
    );
    await tester.pumpAndSettle();

    expect(find.text('Total Records'), findsOneWidget);
    expect(find.text('Valid Records'), findsOneWidget);
    expect(find.text('Start Import'), findsOneWidget);
    expect(api.createOpeningStockCalls, 0);
  });

  test('inventory import file parser reads XLSX rows', () {
    final List<Map<String, String>> rows = InventoryImportFileParser.parseBytes(
      fileName: 'adjustments.xlsx',
      bytes: base64Decode(_xlsxFixtureBase64),
    );

    expect(rows, hasLength(1));
    expect(rows.single['productcode'], 'MED-001');
    expect(rows.single['branchcode'], 'BR-001');
    expect(rows.single['warehousecode'], 'WH-001');
    expect(rows.single['quantity'], '5');
    expect(rows.single['referencenumber'], 'ADJ-001');
    expect(rows.single['transactiondate'], '2026-08-02');
  });

  testWidgets('inventory import wizard shows cancel during adjustment import',
      (tester) async {
    _setDesktopSurface(tester);
    final Directory temp =
        Directory.systemTemp.createTempSync('inventory-retry');
    final File file =
        File('${temp.path}${Platform.pathSeparator}adjustments.csv')
          ..writeAsStringSync(
            'ProductCode,BranchCode,WarehouseCode,StorageCode,Quantity,ReferenceNumber,TransactionDate\n'
            'MED-001,BR-001,WH-001,RACK-A,3,ADJ-001,2026-08-02\n'
            'MED-001,BR-001,WH-001,RACK-A,2,ADJ-002,2026-08-02\n',
          );
    final DesktopPreferencesService preferences =
        DesktopPreferencesService(directory: temp);
    final InventoryImportWizardController controller =
        InventoryImportWizardController();
    final _InventoryImportApi api = _InventoryImportApi(
      adjustmentDelay: const Duration(milliseconds: 60),
    );

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: InventoryImportWizard(
            api: api,
            preferences: preferences,
            branches: [_branch],
            warehouses: [_warehouse],
            products: [_product],
            controller: controller,
            onViewImportedRecords: (_) async {},
          ),
        ),
      ),
    );

    await tester.runAsync(
      () => controller.loadPreparedFile(
          'adjustments.csv', file.readAsBytesSync()),
    );
    await tester.pumpAndSettle();
    expect(
      controller.canImport,
      isTrue,
      reason: controller.validationIssues.join(', '),
    );
    await tester.tap(find.text('Start Import'));
    await tester.pump(const Duration(milliseconds: 10));

    expect(find.text('Cancel'), findsOneWidget);

    controller.cancelImport();
    await tester.pump(const Duration(milliseconds: 120));
    await tester.pumpAndSettle();
  });

  testWidgets(
      'inventory import wizard shows retry after failed adjustment import',
      (tester) async {
    _setDesktopSurface(tester);
    final Directory temp =
        Directory.systemTemp.createTempSync('inventory-retry-fail');
    final File file =
        File('${temp.path}${Platform.pathSeparator}adjustments.csv')
          ..writeAsStringSync(
            'ProductCode,BranchCode,WarehouseCode,StorageCode,Quantity,ReferenceNumber,TransactionDate\n'
            'MED-001,BR-001,WH-001,RACK-A,3,ADJ-001,2026-08-02\n'
            'MED-001,BR-001,WH-001,RACK-A,2,ADJ-002,2026-08-02\n',
          );
    final DesktopPreferencesService preferences =
        DesktopPreferencesService(directory: temp);
    final InventoryImportWizardController controller =
        InventoryImportWizardController();
    final _InventoryImportApi api = _InventoryImportApi(
      failAdjustmentCalls: const {1},
    );

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: InventoryImportWizard(
            api: api,
            preferences: preferences,
            branches: [_branch],
            warehouses: [_warehouse],
            products: [_product],
            initialType: InventoryImportType.inventoryAdjustment,
            controller: controller,
            onViewImportedRecords: (_) async {},
          ),
        ),
      ),
    );

    await tester.runAsync(
      () => controller.loadPreparedFile(
          'adjustments.csv', file.readAsBytesSync()),
    );
    await tester.pumpAndSettle();

    expect(
      controller.canImport,
      isTrue,
      reason: controller.validationIssues.join(', '),
    );
    await tester.tap(find.text('Start Import'));
    await tester.pumpAndSettle();

    expect(find.text('Retry Import'), findsOneWidget);
    expect(api.adjustmentCalls, 2);
  });

  testWidgets('global search applies filters and opens inventory details',
      (tester) async {
    _setDesktopSurface(tester);
    GlobalSearchRequest? lastRequest;

    await tester.pumpWidget(
      MaterialApp(
        home: Builder(
          builder: (context) => Scaffold(
            body: Center(
              child: FilledButton(
                onPressed: () => showGlobalSearch(
                  context,
                  executor: (request) async {
                    lastRequest = request;
                    return GlobalSearchResponse(
                      message: '1 inventory result found.',
                      results: [
                        GlobalSearchResultItem(
                          id: 'inv-1',
                          title: 'Pain Relief',
                          subtitle: 'MED-001 • WH-001 • BR-001',
                          currentStock: '10',
                          availableStock: '8',
                          branch: 'Main Branch',
                          warehouse: 'Central Warehouse',
                          status: 'ACTIVE',
                          productCode: 'MED-001',
                          inventoryId: 'inv-1',
                          onOpen: () => showDialog<void>(
                            context: context,
                            builder: (context) => const AlertDialog(
                              content: Text('Inventory Details Dialog'),
                            ),
                          ),
                        ),
                      ],
                    );
                  },
                ),
                child: const Text('Open Search'),
              ),
            ),
          ),
        ),
      ),
    );

    await tester.tap(find.text('Open Search'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Branches'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).first, 'BR-001');
    await tester.tap(find.widgetWithText(FilledButton, 'Search'));
    await tester.pumpAndSettle();

    expect(lastRequest?.category, GlobalSearchCategory.branches);
    expect(find.text('Pain Relief'), findsOneWidget);

    await tester.tap(find.widgetWithText(FilledButton, 'Open Details'));
    await tester.pumpAndSettle();

    expect(find.text('Inventory Details Dialog'), findsOneWidget);
  });

  testWidgets('global search shows integration placeholder without executor',
      (tester) async {
    _setDesktopSurface(tester);

    await tester.pumpWidget(
      MaterialApp(
        home: Builder(
          builder: (context) => Scaffold(
            body: Center(
              child: FilledButton(
                onPressed: () => showGlobalSearch(context),
                child: const Text('Open Search'),
              ),
            ),
          ),
        ),
      ),
    );

    await tester.tap(find.text('Open Search'));
    await tester.pumpAndSettle();

    expect(
      find.text(
          'Search integration will be enabled when module APIs are available.'),
      findsOneWidget,
    );
  });

  testWidgets('batch management page shows empty state for batches section',
      (tester) async {
    _setDesktopSurface(tester);
    final _BatchSerialApi api = _BatchSerialApi();
    final Directory temp = Directory.systemTemp.createTempSync('batch-test');
    final DesktopPreferencesService preferences =
        DesktopPreferencesService(directory: temp);
    final PermissionService permissions = _permissionsFor([
      'BATCH_VIEW',
      'BATCH_CREATE',
      'BATCH_UPDATE',
      'BATCH_DELETE',
      'SERIAL_VIEW',
    ]);

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: BatchManagementPage(
            api: api,
            preferences: preferences,
            permissions: permissions,
            hasActiveFirm: true,
            section: BatchSerialSection.batches,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    // Empty state shown when no batches returned.
    expect(find.text('No records'), findsOneWidget);
  });

  testWidgets(
      'batch management page renders batch grid when batches are returned',
      (tester) async {
    _setDesktopSurface(tester);
    final _BatchSerialApi api = _BatchSerialApi(batchItems: [_batchRecord]);
    final Directory temp =
        Directory.systemTemp.createTempSync('batch-grid-test');
    final DesktopPreferencesService preferences =
        DesktopPreferencesService(directory: temp);
    final PermissionService permissions = _permissionsFor([
      'BATCH_VIEW',
      'BATCH_CREATE',
    ]);

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: BatchManagementPage(
            api: api,
            preferences: preferences,
            permissions: permissions,
            hasActiveFirm: true,
            section: BatchSerialSection.batches,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    // Batch number and product name appear in the grid.
    expect(find.text('BATCH-001'), findsAny);
    expect(find.text('MED-001 - Pain Relief'), findsAny);
  });

  testWidgets('serial management page shows empty state for serials section',
      (tester) async {
    _setDesktopSurface(tester);
    final _BatchSerialApi api = _BatchSerialApi();
    final Directory temp = Directory.systemTemp.createTempSync('serial-test');
    final DesktopPreferencesService preferences =
        DesktopPreferencesService(directory: temp);
    final PermissionService permissions = _permissionsFor([
      'SERIAL_VIEW',
      'SERIAL_CREATE',
    ]);

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: BatchManagementPage(
            api: api,
            preferences: preferences,
            permissions: permissions,
            hasActiveFirm: true,
            section: BatchSerialSection.serials,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('No records'), findsOneWidget);
  });

  testWidgets('expiry monitor builds dashboard cards without active batches',
      (tester) async {
    _setDesktopSurface(tester);
    final _BatchSerialApi api = _BatchSerialApi();
    final Directory temp = Directory.systemTemp.createTempSync('expiry-test');
    final DesktopPreferencesService preferences =
        DesktopPreferencesService(directory: temp);
    final PermissionService permissions = _permissionsFor(['BATCH_VIEW']);

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: BatchManagementPage(
            api: api,
            preferences: preferences,
            permissions: permissions,
            hasActiveFirm: true,
            section: BatchSerialSection.expiryMonitor,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    // Dashboard metric cards should appear.
    expect(find.text('Expired Today'), findsOneWidget);
    expect(find.text('Expire in 7 Days'), findsOneWidget);
    expect(find.text('Expire in 30 Days'), findsOneWidget);
    expect(find.text('Quarantine'), findsOneWidget);
  });
}

void _setDesktopSurface(WidgetTester tester) {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = const Size(1600, 1200);
  addTearDown(tester.view.resetDevicePixelRatio);
  addTearDown(tester.view.resetPhysicalSize);
}

/// Create a [PermissionService] pre-seeded with the given permission codes.
PermissionService _permissionsFor(List<String> perms) {
  final String payload = base64Url.encode(
    utf8.encode(jsonEncode({'permissions': perms})),
  );
  final String fakeToken = 'h.$payload.s';
  return PermissionService()..applyAccessToken(fakeToken);
}

class _InventoryImportApi extends ApiClient {
  _InventoryImportApi({
    this.adjustmentDelay = Duration.zero,
    this.failAdjustmentCalls = const <int>{},
  }) : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final Duration adjustmentDelay;
  // A seam the fake keeps for callers that want to observe retries; no
  // test supplies one today, so it is a field rather than a parameter.
  final void Function(int callNumber)? onAdjustmentCall = null;
  final Set<int> failAdjustmentCalls;
  int createOpeningStockCalls = 0;
  int postOpeningStockCalls = 0;
  int adjustmentCalls = 0;
  int updateCalls = 0;

  @override
  Future<PagedResult<InventoryRecord>> inventory({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'updated_at',
    bool descending = true,
    InventoryQuery filters = const InventoryQuery(),
  }) async {
    final bool matchesProduct =
        filters.productId == null || filters.productId == _inventory.productId;
    final bool matchesBranch =
        filters.branchId == null || filters.branchId == _inventory.branchId;
    final bool matchesWarehouse = filters.warehouseId == null ||
        filters.warehouseId == _inventory.warehouseId;
    if (!matchesProduct || !matchesBranch || !matchesWarehouse) {
      return const PagedResult(items: [], total: 0);
    }
    return const PagedResult(items: [_inventory], total: 1);
  }

  @override
  Future<List<StorageNodeRecord>> storageNodes(
    String warehouseId, {
    bool includeDeleted = false,
  }) async =>
      const [_storage];

  @override
  Future<OpeningStockBatchRecord> createOpeningStock(Json data) async {
    createOpeningStockCalls++;
    return _openingStockDraft;
  }

  @override
  Future<OpeningStockBatchRecord> postOpeningStock(String id) async {
    postOpeningStockCalls++;
    return _openingStockPosted;
  }

  @override
  Future<InventoryRecord> updateInventoryRecord(String id, Json data) async {
    updateCalls++;
    return _inventory;
  }

  @override
  Future<InventoryTransactionRecord> createInventoryAdjustment(
      Json data) async {
    adjustmentCalls++;
    onAdjustmentCall?.call(adjustmentCalls);
    if (failAdjustmentCalls.contains(adjustmentCalls)) {
      throw const ApiException('Simulated adjustment failure');
    }
    if (adjustmentDelay != Duration.zero) {
      await Future<void>.delayed(adjustmentDelay);
    }
    return _transaction;
  }
}

const String _xlsxFixtureBase64 =
    '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';

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

const StorageNodeRecord _storage = StorageNodeRecord(
  id: 'storage-1',
  warehouseId: 'warehouse-1',
  parentId: '',
  nodeType: 'RACK',
  code: 'RACK-A',
  name: 'Rack A',
  path: 'RACK-A',
  sortOrder: 1,
  isActive: true,
  isDeleted: false,
);

const Product _product = Product(
  id: 'product-1',
  firmId: 'firm-1',
  code: 'MED-001',
  barcode: '890100001',
  qrCode: '',
  name: 'Pain Relief',
  shortName: 'Pain Relief',
  description: '',
  productType: 'FINISHED_GOOD',
  categoryId: 'cat-1',
  subCategoryId: '',
  unit: 'EA',
  brand: 'Acme',
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
  attributes: [],
  media: [],
);

const InventoryRecord _inventory = InventoryRecord(
  id: 'inv-1',
  firmId: 'firm-1',
  branchId: 'branch-1',
  branchCode: 'BR-001',
  branchName: 'Main Branch',
  warehouseId: 'warehouse-1',
  warehouseCode: 'WH-001',
  warehouseName: 'Central Warehouse',
  storageNodeId: 'storage-1',
  storageNodeCode: 'RACK-A',
  storageNodeName: 'Rack A',
  productId: 'product-1',
  productCode: 'MED-001',
  productName: 'Pain Relief',
  batchId: 'batch-1',
  batchNumber: 'MARCH-01',
  batchExpiryDate: '2027-03-31',
  businessProfileId: 'profile-1',
  businessProfileCode: 'MEDICAL',
  currentQuantity: '10',
  reservedQuantity: '2',
  availableQuantity: '8',
  blockedQuantity: '0',
  damagedQuantity: '0',
  quarantineQuantity: '0',
  inTransitQuantity: '0',
  minimumLevel: '1',
  maximumLevel: '20',
  reorderLevel: '5',
  safetyStock: '2',
  lastTransactionAt: '2026-08-02',
  status: 'ACTIVE',
  isDeleted: false,
  createdAt: '2026-08-01T00:00:00Z',
  updatedAt: '2026-08-01T00:00:00Z',
);

const OpeningStockBatchRecord _openingStockDraft = OpeningStockBatchRecord(
  id: 'batch-1',
  firmId: 'firm-1',
  branchId: 'branch-1',
  branchCode: 'BR-001',
  branchName: 'Main Branch',
  warehouseId: 'warehouse-1',
  warehouseCode: 'WH-001',
  warehouseName: 'Central Warehouse',
  referenceNumber: 'OPEN-001',
  postingDate: '2026-08-02',
  sourceFormat: 'CSV',
  status: 'DRAFT',
  remarks: '',
  postedAt: '',
  lines: [],
  createdAt: '2026-08-01T00:00:00Z',
  updatedAt: '2026-08-01T00:00:00Z',
);

const OpeningStockBatchRecord _openingStockPosted = OpeningStockBatchRecord(
  id: 'batch-1',
  firmId: 'firm-1',
  branchId: 'branch-1',
  branchCode: 'BR-001',
  branchName: 'Main Branch',
  warehouseId: 'warehouse-1',
  warehouseCode: 'WH-001',
  warehouseName: 'Central Warehouse',
  referenceNumber: 'OPEN-001',
  postingDate: '2026-08-02',
  sourceFormat: 'CSV',
  status: 'POSTED',
  remarks: '',
  postedAt: '2026-08-02',
  lines: [],
  createdAt: '2026-08-01T00:00:00Z',
  updatedAt: '2026-08-01T00:00:00Z',
);

const InventoryTransactionRecord _transaction = InventoryTransactionRecord(
  id: 'txn-1',
  inventoryId: 'inv-1',
  firmId: 'firm-1',
  branchId: 'branch-1',
  branchCode: 'BR-001',
  branchName: 'Main Branch',
  warehouseId: 'warehouse-1',
  warehouseCode: 'WH-001',
  warehouseName: 'Central Warehouse',
  storageNodeId: 'storage-1',
  storageNodeCode: 'RACK-A',
  storageNodeName: 'Rack A',
  productId: 'product-1',
  productCode: 'MED-001',
  productName: 'Pain Relief',
  businessProfileId: 'profile-1',
  transactionType: 'ADJUSTMENT',
  referenceNumber: 'ADJ-001',
  referenceType: 'ADJUSTMENT',
  transactionDate: '2026-08-02',
  quantity: '1',
  currentQuantityDelta: '1',
  reservedQuantityDelta: '0',
  blockedQuantityDelta: '0',
  damagedQuantityDelta: '0',
  quarantineQuantityDelta: '0',
  inTransitQuantityDelta: '0',
  previousCurrentQuantity: '9',
  newCurrentQuantity: '10',
  previousReservedQuantity: '2',
  newReservedQuantity: '2',
  previousAvailableQuantity: '7',
  newAvailableQuantity: '8',
  previousBlockedQuantity: '0',
  newBlockedQuantity: '0',
  previousDamagedQuantity: '0',
  newDamagedQuantity: '0',
  previousQuarantineQuantity: '0',
  newQuarantineQuantity: '0',
  previousInTransitQuantity: '0',
  newInTransitQuantity: '0',
  remarks: '',
  createdAt: '2026-08-02T00:00:00Z',
  transactionId: 'txn-1',
);

class _BatchSerialApi extends ApiClient {
  _BatchSerialApi({
    this.batchItems = const [],
  }) : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<BatchRecord> batchItems;
  final List<LotRecord> lotItems = const [];
  final List<SerialRecord> serialItems = const [];

  @override
  Future<PagedResult<BatchRecord>> batches({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    BatchQuery filters = const BatchQuery(),
  }) async =>
      PagedResult(items: batchItems, total: batchItems.length);

  @override
  Future<BatchSummaryRecord> batchSummary() async => const BatchSummaryRecord(
        totalBatches: 0,
        nearExpiry: 0,
        expired: 0,
        quarantine: 0,
      );

  @override
  Future<ExpiryDashboardRecord> expiryDashboard() async =>
      const ExpiryDashboardRecord(
        expiredToday: 0,
        expireIn7Days: 0,
        expireIn30Days: 0,
        totalExpired: 0,
        quarantine: 0,
        recalled: 0,
      );

  @override
  Future<PagedResult<LotRecord>> lots({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    LotQuery filters = const LotQuery(),
  }) async =>
      PagedResult(items: lotItems, total: lotItems.length);

  @override
  Future<PagedResult<SerialRecord>> serials({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    SerialQuery filters = const SerialQuery(),
  }) async =>
      PagedResult(items: serialItems, total: serialItems.length);
}

const BatchRecord _batchRecord = BatchRecord(
  id: 'batch-record-1',
  firmId: 'firm-1',
  productId: 'product-1',
  productCode: 'MED-001',
  productName: 'Pain Relief',
  warehouseId: 'warehouse-1',
  warehouseCode: 'WH-001',
  warehouseName: 'Central Warehouse',
  branchId: 'branch-1',
  branchCode: 'BR-001',
  branchName: 'Main Branch',
  batchNumber: 'BATCH-001',
  supplierBatch: 'SUP-BATCH-001',
  internalBatch: '',
  manufacturingDate: '2026-01-01',
  expiryDate: '2027-01-01',
  bestBeforeDate: '',
  status: 'AVAILABLE',
  quantity: '100',
  availableQuantity: '95',
  reservedQuantity: '5',
  blockedQuantity: '0',
  damagedQuantity: '0',
  quarantineQuantity: '0',
  shelfLifeDays: 365,
  remarks: '',
  isDeleted: false,
  createdAt: '2026-08-01T00:00:00Z',
  updatedAt: '2026-08-01T00:00:00Z',
);
