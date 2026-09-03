import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/models/purchase.dart';
import 'package:agency_desktop/models/tax_framework.dart';
import 'package:agency_desktop/models/vendor.dart';
import 'package:agency_desktop/ui/purchases/purchase_management_page.dart';
import 'package:agency_desktop/ui/workspace/module_catalog.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('module catalog exposes enterprise purchase workspace tabs', () {
    expect(
      ModuleCatalog.byId(AppModule.purchases).tabs.map((tab) => tab.label),
      containsAll([
        'Dashboard',
        'Purchase Orders',
        'Analytics',
        'Settings',
      ]),
    );
  });

  test('module catalog exposes goods receipt workspace tabs', () {
    // One, not eight. Pending, Partial and Completed Receipts, Rejected and
    // Damaged Items and History were menu entries onto this same workspace --
    // see `GoodsReceiptView` and `goods_receipt_navigation_test.dart`. Settings
    // was the last of them: the page takes a tab id and reads it nowhere, so
    // the entry rendered the receipts list.
    expect(
      ModuleCatalog.byId(AppModule.goodsReceipts).tabs.map((tab) => tab.label),
      <String>['Receipts'],
    );
  });

  testWidgets('purchase workspace loads grid and opens editor with Ctrl+N',
      (tester) async {
    _setDesktopSurface(tester);
    final Directory temp =
        Directory.systemTemp.createTempSync('purchase-workspace-test');
    final DesktopPreferencesService preferences =
        DesktopPreferencesService(directory: temp);
    final PermissionService permissions = PermissionService()
      ..applyAccessToken(_accessToken({
        'permissions': [
          'PURCHASE_VIEW',
          'PURCHASE_CREATE',
          'PURCHASE_UPDATE',
          'PURCHASE_DELETE',
          'PURCHASE_RESTORE',
          'PURCHASE_IMPORT',
          'PURCHASE_EXPORT',
          'PURCHASE_APPROVE',
          'PURCHASE_CANCEL',
        ],
      }));
    final _PurchaseApi api = _PurchaseApi();

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: PurchaseManagementPage(
            api: api,
            preferences: preferences,
            permissions: permissions,
            hasActiveFirm: true,
            section: PurchaseSection.purchaseOrders,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('PO-0001'), findsWidgets);

    await tester.sendKeyDownEvent(LogicalKeyboardKey.controlLeft);
    await tester.sendKeyEvent(LogicalKeyboardKey.keyN);
    await tester.sendKeyUpEvent(LogicalKeyboardKey.controlLeft);
    await tester.pumpAndSettle();

    expect(find.text('New Purchase Order'), findsOneWidget);
    expect(find.text('Document Header'), findsWidgets);
    expect(find.text('Line Items'), findsWidgets);
    expect(find.text('Delivery Information'), findsWidgets);
    expect(find.text('Charges and Taxes'), findsWidgets);
    expect(find.text('Attachments'), findsWidgets);
    expect(find.text('Notes'), findsWidgets);
    expect(find.text('History'), findsWidgets);
    expect(find.text('Approval'), findsWidgets);
  });

  testWidgets('purchase import wizard previews CSV and runs import',
      (tester) async {
    _setDesktopSurface(tester);
    final _PurchaseApi api = _PurchaseApi();
    var imported = false;

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: PurchaseImportWizard(
            api: api,
            requiredHeaders: const [
              'branchid',
              'warehouseid',
              'vendorid',
              'productid',
              'purchasedate',
              'orderedqty',
              'unitprice',
            ],
            initialFileName: 'purchase-import.csv',
            initialFileBytes: utf8.encode(
              'BranchId,WarehouseId,VendorId,ProductId,PurchaseDate,OrderedQty,UnitPrice\n'
              '${_branch.id},${_warehouse.id},${_vendor.id},${_product.id},2026-08-02,5,100\n',
            ),
            onImported: () async => imported = true,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Total Records'), findsOneWidget);
    expect(find.text('Valid Records'), findsOneWidget);
    expect(find.text('Start Import'), findsOneWidget);

    await tester.tap(find.text('Start Import'));
    await tester.pumpAndSettle();

    expect(imported, isTrue);
    expect(api.importFileCalls, 1);
  });

  test('an update payload no longer states a status', () {
    // The server owns the status through its lifecycle endpoints. Echoing the
    // one we last read is what let an approved order be edited to any amount
    // and stay approved.
    final Json body = _purchaseOrder.toUpdateJson();
    expect(body.containsKey('status'), isFalse);
    expect(_purchaseOrder.toCreateJson()['status'], 'DRAFT');
  });

  test('the model refuses the edits the server refuses', () {
    // Mirrors `PurchaseService._assert_order_editable`.
    expect(_purchaseOrder.isEditable, isTrue);
    for (final String status in ['PARTIALLY_RECEIVED', 'RECEIVED']) {
      final PurchaseOrder order = _purchaseOrder.copyWith(status: status);
      expect(order.isEditable, isFalse, reason: status);
      expect(order.editRefusal, contains('received'));
    }
    for (final String status in ['CANCELLED', 'CLOSED']) {
      final PurchaseOrder order = _purchaseOrder.copyWith(status: status);
      expect(order.isEditable, isFalse, reason: status);
      expect(order.editRefusal, isNotNull);
    }
    // Approved is editable -- it just costs the approval, which the workspace
    // asks about before opening the editor.
    expect(_purchaseOrder.copyWith(status: 'APPROVED').isEditable, isTrue);
    expect(_purchaseOrder.copyWith(status: 'APPROVED').editRefusal, isNull);
  });

  testWidgets('editing an approved order warns that approval is withdrawn',
      (tester) async {
    _setDesktopSurface(tester);
    final _PurchaseApi api = _PurchaseApi()..status = 'APPROVED';
    await _pumpWorkspace(tester, api: api);

    await tester.tap(find.text('PO-0001').first);
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithIcon(IconButton, Icons.edit_outlined).first);
    await tester.pumpAndSettle();

    expect(find.text('Editing withdraws the approval'), findsOneWidget);
    expect(find.textContaining('need submitting and approving again'),
        findsOneWidget);

    // Backing out leaves the editor closed.
    await tester.tap(find.widgetWithText(TextButton, 'Cancel'));
    await tester.pumpAndSettle();
    expect(find.text('Edit Purchase Order'), findsNothing);
  });

  testWidgets('a received order cannot be edited at all', (tester) async {
    _setDesktopSurface(tester);
    final _PurchaseApi api = _PurchaseApi()..status = 'RECEIVED';
    await _pumpWorkspace(tester, api: api);

    await tester.tap(find.text('PO-0001').first);
    await tester.pumpAndSettle();

    final Finder edit =
        find.widgetWithIcon(IconButton, Icons.edit_outlined).first;
    expect(tester.widget<IconButton>(edit).onPressed, isNull,
        reason: 'the server refuses this edit, so the button must not offer it');
  });

  testWidgets('open purchase order offers Submit, and moves without closing',
      (tester) async {
    _setDesktopSurface(tester);
    final _PurchaseApi api = _PurchaseApi();
    await _pumpWorkspace(tester, api: api);

    await _openOrder(tester);

    expect(find.text('Purchase Order'), findsWidgets);
    expect(find.text('Submit this draft to send it for approval.'),
        findsOneWidget);
    expect(_enabled(tester, 'Submit'), isTrue);
    // Present, so the person holding approval can see the step exists -- but
    // not pressable until the draft has been submitted.
    expect(_enabled(tester, 'Approve'), isFalse);

    await tester.tap(find.widgetWithText(OutlinedButton, 'Submit'));
    await tester.pumpAndSettle();

    expect(api.lifecycleCalls, ['submit:po-1']);
    // Still open, which is the whole point: you keep your place in the
    // document you were reading.
    expect(find.text('Purchase Order'), findsWidgets);
    expect(_enabled(tester, 'Submit'), isFalse);
    expect(_enabled(tester, 'Approve'), isTrue);
    expect(find.text('Approve this order to commit the firm to it.'),
        findsOneWidget);
  });

  testWidgets('approving from inside reloads the grid without claiming an edit',
      (tester) async {
    _setDesktopSurface(tester);
    final _PurchaseApi api = _PurchaseApi()..status = 'SUBMITTED';
    await _pumpWorkspace(tester, api: api);

    await _openOrder(tester);

    await tester.tap(find.widgetWithText(OutlinedButton, 'Approve'));
    await tester.pumpAndSettle();

    expect(api.lifecycleCalls, ['approve:po-1']);
    expect(_enabled(tester, 'Approve'), isFalse);

    // Two say Close -- the toolbar's and the footer's. Both call `_close`.
    await tester.tap(find.widgetWithText(OutlinedButton, 'Close').last);
    await tester.pumpAndSettle();

    // The grid is reloaded -- otherwise the row behind still reads SUBMITTED
    // -- but nothing was edited, so the workspace must not say it was.
    expect(find.text('Purchase order updated.'), findsNothing);
    expect(find.text('PO-0001'), findsWidgets);
  });

  testWidgets('without the permission the button is absent, not just disabled',
      (tester) async {
    _setDesktopSurface(tester);
    final _PurchaseApi api = _PurchaseApi()..status = 'SUBMITTED';
    await _pumpWorkspace(
      tester,
      api: api,
      // Enough to open a purchase order and nothing more.
      permissionCodes: const ['PURCHASE_VIEW'],
    );

    await _openOrder(tester);

    expect(find.widgetWithText(OutlinedButton, 'Approve'), findsNothing);
    expect(find.widgetWithText(OutlinedButton, 'Submit'), findsNothing);
    expect(find.text('Waiting for someone who holds purchase approval.'),
        findsOneWidget);
  });

  testWidgets('a new purchase order offers neither, having nothing to act on',
      (tester) async {
    _setDesktopSurface(tester);
    await _pumpWorkspace(tester, api: _PurchaseApi());

    await tester.sendKeyDownEvent(LogicalKeyboardKey.controlLeft);
    await tester.sendKeyEvent(LogicalKeyboardKey.keyN);
    await tester.sendKeyUpEvent(LogicalKeyboardKey.controlLeft);
    await tester.pumpAndSettle();

    expect(find.text('New Purchase Order'), findsOneWidget);
    expect(find.widgetWithText(OutlinedButton, 'Submit'), findsNothing);
    expect(find.widgetWithText(OutlinedButton, 'Approve'), findsNothing);
    expect(find.text('Save the order before it can be sent for approval.'),
        findsOneWidget);
  });
}

/// Double-click the seeded row, which is how the workspace opens a document.
Future<void> _openOrder(WidgetTester tester) async {
  final Finder row = find.text('PO-0001').first;
  await tester.tap(row);
  await tester.pump(const Duration(milliseconds: 50));
  await tester.tap(row);
  await tester.pumpAndSettle();
}

/// Whether the dialog toolbar button reading [label] can be pressed.
bool _enabled(WidgetTester tester, String label) {
  final Finder finder = find.widgetWithText(OutlinedButton, label);
  expect(finder, findsOneWidget, reason: 'no toolbar button reading $label');
  return tester.widget<OutlinedButton>(finder).onPressed != null;
}

/// Pump the purchase orders workspace with a full set of permissions.
Future<void> _pumpWorkspace(
  WidgetTester tester, {
  required _PurchaseApi api,
  List<String> permissionCodes = const [
    'PURCHASE_VIEW',
    'PURCHASE_CREATE',
    'PURCHASE_UPDATE',
    'PURCHASE_DELETE',
    'PURCHASE_RESTORE',
    'PURCHASE_IMPORT',
    'PURCHASE_EXPORT',
    'PURCHASE_APPROVE',
    'PURCHASE_CANCEL',
  ],
}) async {
  final Directory temp =
      Directory.systemTemp.createTempSync('purchase-dialog-test');
  addTearDown(() => temp.deleteSync(recursive: true));
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: PurchaseManagementPage(
          api: api,
          preferences: DesktopPreferencesService(directory: temp),
          permissions: PermissionService()
            ..applyAccessToken(_accessToken({'permissions': permissionCodes})),
          hasActiveFirm: true,
          section: PurchaseSection.purchaseOrders,
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

class _PurchaseApi extends ApiClient {
  _PurchaseApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  int importFileCalls = 0;

  /// Every lifecycle call this fake was asked to make, in order.
  final List<String> lifecycleCalls = <String>[];

  /// What `purchases()` and `purchaseOrder()` hand back. A test that wants an
  /// order awaiting approval sets this before pumping.
  String status = 'DRAFT';

  PurchaseOrder get order => _purchaseOrder.copyWith(status: status);

  @override
  Future<PurchaseOrder> submitPurchaseOrder(String id) async {
    lifecycleCalls.add('submit:$id');
    status = 'SUBMITTED';
    return order;
  }

  @override
  Future<PurchaseOrder> approvePurchaseOrder(String id) async {
    lifecycleCalls.add('approve:$id');
    status = 'APPROVED';
    return order;
  }

  @override
  Future<PurchaseSummaryRecord> purchaseSummary() async =>
      const PurchaseSummaryRecord(
        total: 1,
        draft: 1,
        open: 0,
        cancelled: 0,
        closed: 0,
        totalValue: '500.00',
        overdueDelivery: 0,
      );

  @override
  Future<PagedResult<PurchaseOrder>> purchases({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    PurchaseQuery filters = const PurchaseQuery(),
  }) async =>
      PagedResult(items: [order], total: 1);

  @override
  Future<PurchaseOrder> purchaseOrder(
    String id, {
    bool includeDeleted = false,
  }) async =>
      order;

  @override
  Future<List<PurchaseOrderHistoryRecord>> purchaseOrderHistory(
    String id,
  ) async =>
      const [
        PurchaseOrderHistoryRecord(
          id: 'history-1',
          action: 'CREATED',
          fromStatus: '',
          toStatus: 'DRAFT',
          remarks: 'Created',
          detailsJson: '',
          createdBy: 'user-1',
          createdAt: '2026-08-02T10:00:00Z',
        ),
      ];

  @override
  Future<PagedResult<Vendor>> vendors({
    int page = 1,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    VendorQuery filters = const VendorQuery(),
  }) async =>
      const PagedResult(items: [_vendor], total: 1);

  @override
  Future<PagedResult<BranchRecord>> branches({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    BranchQuery filters = const BranchQuery(),
  }) async =>
      const PagedResult(items: [_branch], total: 1);

  @override
  Future<PagedResult<WarehouseRecord>> warehouses({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    WarehouseQuery filters = const WarehouseQuery(),
  }) async =>
      const PagedResult(items: [_warehouse], total: 1);

  @override
  Future<List<StorageNodeRecord>> storageNodes(
    String warehouseId, {
    bool includeDeleted = false,
  }) async =>
      const [
        StorageNodeRecord(
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
        ),
      ];

  @override
  Future<PagedResult<Product>> products({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    ProductQuery filters = const ProductQuery(),
  }) async =>
      const PagedResult(items: [_product], total: 1);

  @override
  Future<PagedResult<PlatformUser>> users({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
  }) async =>
      const PagedResult(
        items: [
          PlatformUser(
            id: 'user-1',
            email: 'buyer@example.com',
            fullName: 'Buyer One',
            isActive: true,
            forcePasswordChange: false,
            expiresAt: '',
          ),
        ],
        total: 1,
      );

  @override
  Future<PagedResult<TaxProfileRecord>> taxProfiles({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    String? taxSystemId,
    bool includeDeleted = false,
  }) async =>
      const PagedResult(
        items: [
          TaxProfileRecord(
            id: 'tax-1',
            taxSystemId: 'tax-system-1',
            code: 'GST18',
            name: 'GST 18%',
            label: 'GST 18%',
            status: 'ACTIVE',
            isHistorical: false,
            isDeleted: false,
            components: [],
          ),
        ],
        total: 1,
      );

  @override
  Future<List<PurchaseOrder>> importPurchaseOrdersFile({
    required String format,
    required String fileName,
    required List<int> bytes,
  }) async {
    importFileCalls++;
    return [_purchaseOrder];
  }
}

const Vendor _vendor = Vendor(
  id: 'vendor-1',
  firmId: 'firm-1',
  code: 'V-001',
  name: 'Northwind Supplies',
  legalName: 'Northwind Supplies Pvt Ltd',
  displayName: 'Northwind Supplies',
  categoryId: '',
  typeId: '',
  status: 'ACTIVE',
  businessProfileId: '',
  gstRegistration: true,
  gstin: '',
  pan: '',
  licenseNumber: '',
  registrationNumber: '',
  website: '',
  email: '',
  phone: '',
  mobile: '',
  remarks: '',
  businessAttributes: {},
  createdAt: '',
  updatedAt: '',
  isDeleted: false,
  contacts: [],
  addresses: [],
);

const BranchRecord _branch = BranchRecord(
  id: 'branch-1',
  firmId: 'firm-1',
  code: 'BR-001',
  name: 'Main Branch',
  displayName: 'Main Branch',
  description: '',
  branchTypeId: '',
  branchManagerId: '',
  businessProfileId: '',
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
  createdAt: '',
);

const WarehouseRecord _warehouse = WarehouseRecord(
  id: 'warehouse-1',
  firmId: 'firm-1',
  branchId: 'branch-1',
  code: 'WH-001',
  name: 'Central Warehouse',
  displayName: 'Central Warehouse',
  warehouseTypeId: '',
  businessProfileId: '',
  capacity: '',
  capacityUnit: '',
  status: 'ACTIVE',
  isDefault: true,
  temperatureControlled: false,
  coldStorage: false,
  hazardousStorage: false,
  isDeleted: false,
  createdAt: '',
);

const Product _product = Product(
  id: 'product-1',
  firmId: 'firm-1',
  code: 'MED-001',
  barcode: '',
  qrCode: '',
  name: 'Pain Relief',
  shortName: 'Pain Relief',
  description: '',
  productType: 'GOODS',
  categoryId: '',
  subCategoryId: '',
  unit: 'BOX',
  brand: '',
  model: '',
  hsnSac: '',
  taxProfileId: 'tax-1',
  purchasePrice: '100',
  sellingPrice: '150',
  mrp: '180',
  status: 'ACTIVE',
  remarks: '',
  isDeleted: false,
  createdAt: '',
  updatedAt: '',
  attributes: [],
  media: [],
);

const PurchaseOrder _purchaseOrder = PurchaseOrder(
  id: 'po-1',
  firmId: 'firm-1',
  branchId: 'branch-1',
  warehouseId: 'warehouse-1',
  vendorId: 'vendor-1',
  buyerId: 'user-1',
  taxProfileId: 'tax-1',
  poNumber: 'PO-0001',
  vendorContact: '',
  vendorAddress: '',
  department: '',
  purchaseType: 'STANDARD_PURCHASE',
  purchaseCategory: '',
  purchaseDate: '2026-08-02',
  expectedDeliveryDate: '2026-08-05',
  paymentTerms: '',
  deliveryTerms: '',
  currencyCode: 'INR',
  exchangeRate: '',
  referenceNumber: 'REF-001',
  externalReference: '',
  priority: 'NORMAL',
  remarks: 'Initial order',
  status: 'DRAFT',
  subtotal: '500.00',
  lineDiscountTotal: '0.00',
  headerDiscountAmount: '0.00',
  taxTotal: '90.00',
  additionalCharges: '0.00',
  roundOff: '0.00',
  grandTotal: '590.00',
  closeReason: '',
  cancelReason: '',
  isDeleted: false,
  createdAt: '2026-08-02T10:00:00Z',
  updatedAt: '2026-08-02T10:00:00Z',
  lines: [
    PurchaseOrderLine(
      id: 'line-1',
      lineNumber: 1,
      productId: 'product-1',
      description: 'Pain Relief',
      vendorProductCode: '',
      purchaseUomId: '',
      inventoryUomId: '',
      conversionFactor: '1',
      conversionVersion: null,
      orderedQuantity: '5',
      freeQuantity: '0',
      baseQuantity: '5',
      unitPrice: '100',
      discountPercent: '0',
      discountAmount: '0',
      grossAmount: '500',
      taxProfileId: 'tax-1',
      taxAmount: '90',
      netAmount: '590',
      batchRequired: false,
      expiryRequired: false,
      serialRequired: false,
      manufacturingDate: '',
      expiryDate: '',
      warehouseId: 'warehouse-1',
      storageNodeId: 'storage-1',
      remarks: '',
      status: 'ACTIVE',
      createdAt: '',
      updatedAt: '',
    ),
  ],
  deliverySchedules: [],
  attachments: [],
  notes: [],
);

String _accessToken(Map<String, Object?> payload) {
  final String header =
      base64Url.encode(utf8.encode(jsonEncode({'alg': 'none', 'typ': 'JWT'})));
  final String body = base64Url.encode(utf8.encode(jsonEncode(payload)));
  return '$header.$body.signature';
}

void _setDesktopSurface(WidgetTester tester) {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = const Size(1600, 900);
  addTearDown(() {
    tester.view.resetPhysicalSize();
    tester.view.resetDevicePixelRatio();
  });
}
