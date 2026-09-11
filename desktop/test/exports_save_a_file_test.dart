// Export writes a file, and says where.
//
// Raised from manual testing (plan item 5.9): "export says success but no
// idea where file downloaded or no file downloaded". Four Export actions
// fetched the CSV from the server, dropped it, and reported success --
// branches and warehouses said "Export completed.", territories reported the
// byte count, vendors the row count. The server log showed each request
// answered 200; no file existed anywhere. Every one now goes through
// `saveExportedText`, which asks where to save and names the path.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/geography.dart';
import 'package:agency_desktop/models/sales_territory.dart';
import 'package:agency_desktop/models/vendor.dart';
import 'package:agency_desktop/ui/branches/branch_warehouse_management_page.dart';
import 'package:agency_desktop/ui/sales/sales_territory_management_page.dart';
import 'package:agency_desktop/ui/vendors/vendor_management_page.dart';
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

/// What the page handed to the save step, captured instead of written.
class _Saved {
  String? name;
  String? content;
  int calls = 0;

  /// The path a real save dialog would have answered with.
  final String path = r'D:\exports\out.csv';

  Future<String?> save(String suggestedName, String text) async {
    calls++;
    name = suggestedName;
    content = text;
    return path;
  }

  Future<String?> cancel(String suggestedName, String text) async {
    calls++;
    return null;
  }
}

const String _csv = 'Code,Name,Status\r\nX1,One,ACTIVE\r\n';

class _BranchApi extends ApiClient {
  _BranchApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  @override
  Future<PagedResult<BranchRecord>> branches({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    BranchQuery filters = const BranchQuery(),
  }) async =>
      PagedResult<BranchRecord>(
        items: <BranchRecord>[
          BranchRecord.fromJson(<String, dynamic>{
            'id': 'b-1',
            'firm_id': 'firm-1',
            'code': 'HO',
            'name': 'Head Office',
            'display_name': 'Head Office',
            'currency_code': 'INR',
            'status': 'ACTIVE',
            'is_default': true,
            'warehouse_count': 0,
          }),
        ],
        total: 1,
      );

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
        items: <WarehouseRecord>[
          WarehouseRecord.fromJson(<String, dynamic>{
            'id': 'w-1',
            'firm_id': 'firm-1',
            'branch_id': 'b-1',
            'code': 'WH1',
            'name': 'Main Store',
            'display_name': 'Main Store',
            'status': 'ACTIVE',
            'is_default': true,
          }),
        ],
        total: 1,
      );

  @override
  Future<List<TypeRecord>> branchTypes({bool includeDeleted = false}) async =>
      const <TypeRecord>[];

  @override
  Future<List<TypeRecord>> warehouseTypes({bool includeDeleted = false}) async =>
      const <TypeRecord>[];

  @override
  Future<List<GeoPlaceRecord>> geoPlaces(
    GeoLevel level, {
    String parentId = '',
  }) async =>
      const <GeoPlaceRecord>[];

  @override
  Future<String> exportBranches({String search = ''}) async => _csv;

  @override
  Future<String> exportWarehouses({String search = ''}) async => _csv;
}

class _TerritoryApi extends ApiClient {
  _TerritoryApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  @override
  Future<TerritoryHierarchyRecord> territoryHierarchy() async =>
      TerritoryHierarchyRecord.fromJson(<String, dynamic>{
        'levels': <Json>[
          <String, dynamic>{
            'id': 'lvl-route',
            'code': 'ROUTE',
            'name': 'Route',
            'display_name': 'Route',
            'level_order': 3,
          },
        ],
      });

  @override
  Future<List<TerritoryTreeNodeRecord>> territoryTree({
    bool includeDeleted = false,
  }) async =>
      const <TerritoryTreeNodeRecord>[];

  @override
  Future<PagedResult<SalesTerritory>> territories({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    TerritoryQuery filters = const TerritoryQuery(),
  }) async =>
      PagedResult<SalesTerritory>(
        items: <SalesTerritory>[
          SalesTerritory.fromJson(<String, dynamic>{
            'id': 't-1',
            'version': 1,
            'firm_id': 'firm-1',
            'hierarchy_level_id': 'lvl-route',
            'hierarchy_level_name': 'Route',
            'code': 'RT01',
            'name': 'North',
            'status': 'ACTIVE',
            'path': 'North',
            'sort_order': 0,
            'customer_count': 0,
            'salesman_count': 0,
          }),
        ],
        total: 1,
      );

  @override
  Future<Json> territoryDashboard() async => <String, dynamic>{};

  @override
  Future<List<GeoPlaceRecord>> geoPlaces(
    GeoLevel level, {
    String parentId = '',
  }) async =>
      const <GeoPlaceRecord>[];

  @override
  Future<List<TerritoryRouteTypeRecord>> territoryRouteTypes() async =>
      const <TerritoryRouteTypeRecord>[];

  @override
  Future<String> exportTerritories({
    String search = '',
    String format = 'csv',
    String dataset = 'hierarchy',
  }) async =>
      _csv;
}

class _VendorApi extends ApiClient {
  _VendorApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  @override
  Future<PagedResult<Vendor>> vendors({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    VendorQuery filters = const VendorQuery(),
  }) async =>
      PagedResult<Vendor>(
        items: <Vendor>[
          Vendor.fromJson(<String, dynamic>{
            'id': 'v-1',
            'firm_id': 'firm-1',
            'code': 'V001',
            'name': 'Supplier One',
            'display_name': 'Supplier One',
            'status': 'ACTIVE',
            'addresses': <Json>[],
            'contacts': <Json>[],
            'bank_accounts': <Json>[],
            'tax_details': <Json>[],
            'notes': <Json>[],
          }),
        ],
        total: 1,
      );

  @override
  Future<List<GeoPlaceRecord>> geoPlaces(
    GeoLevel level, {
    String parentId = '',
  }) async =>
      const <GeoPlaceRecord>[];

  @override
  Future<String> exportVendors({String search = ''}) async => _csv;
}

Future<void> _pump(WidgetTester tester, Widget page) async {
  tester.view.physicalSize = const Size(1600, 1200);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(home: Scaffold(body: page)));
  await tester.pumpAndSettle();
}

Future<void> _tapExport(WidgetTester tester) async {
  await tester.tap(find.byTooltip('Export'));
  await tester.pumpAndSettle();
}

void main() {
  group('a saved export names its path', () {
    testWidgets('branches', (tester) async {
      final _Saved saved = _Saved();
      await _pump(
        tester,
        BranchWarehouseManagementPage(
          api: _BranchApi(),
          permissions: _permissions(['BRANCH_VIEW', 'BRANCH_WAREHOUSE_EXPORT']),
          hasActiveFirm: true,
          section: BranchWarehouseSection.branches,
          saveExportOverride: saved.save,
        ),
      );
      await _tapExport(tester);

      expect(saved.name, 'branches.csv');
      expect(saved.content, _csv, reason: 'the server\'s CSV, byte for byte');
      expect(find.text(exportSavedMessage(saved.path)), findsOneWidget);
    });

    testWidgets('warehouses', (tester) async {
      final _Saved saved = _Saved();
      await _pump(
        tester,
        BranchWarehouseManagementPage(
          api: _BranchApi(),
          permissions:
              _permissions(['WAREHOUSE_VIEW', 'BRANCH_WAREHOUSE_EXPORT']),
          hasActiveFirm: true,
          section: BranchWarehouseSection.warehouses,
          saveExportOverride: saved.save,
        ),
      );
      await _tapExport(tester);

      expect(saved.name, 'warehouses.csv');
      expect(saved.content, _csv);
      expect(find.text(exportSavedMessage(saved.path)), findsOneWidget);
    });

    testWidgets('territories', (tester) async {
      final _Saved saved = _Saved();
      await _pump(
        tester,
        SalesTerritoryManagementPage(
          api: _TerritoryApi(),
          permissions: _permissions(['TERRITORY_VIEW', 'TERRITORY_EXPORT']),
          saveExportOverride: saved.save,
        ),
      );
      await _tapExport(tester);

      expect(saved.name, 'territories.csv');
      expect(saved.content, _csv);
      expect(find.text(exportSavedMessage(saved.path)), findsOneWidget);
    });

    testWidgets('vendors', (tester) async {
      final _Saved saved = _Saved();
      await _pump(
        tester,
        VendorManagementPage(
          api: _VendorApi(),
          permissions: _permissions(['VENDOR_VIEW', 'VENDOR_EXPORT']),
          hasActiveFirm: true,
          saveExportOverride: saved.save,
        ),
      );
      await _tapExport(tester);

      expect(saved.name, 'vendors.csv');
      expect(saved.content, _csv);
      expect(find.text(exportSavedMessage(saved.path)), findsOneWidget);
    });
  });

  testWidgets('a dismissed save dialog is reported as no file, not success',
      (tester) async {
    final _Saved saved = _Saved();
    await _pump(
      tester,
      VendorManagementPage(
        api: _VendorApi(),
        permissions: _permissions(['VENDOR_VIEW', 'VENDOR_EXPORT']),
        hasActiveFirm: true,
        saveExportOverride: saved.cancel,
      ),
    );
    await _tapExport(tester);

    expect(saved.calls, 1);
    expect(find.text(exportCancelledMessage), findsOneWidget);
    expect(find.textContaining('saved to'), findsNothing);
  });
}
