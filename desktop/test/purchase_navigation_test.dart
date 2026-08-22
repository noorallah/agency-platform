// Purchase order statuses are views of one screen, not modules of their own.
//
// Purchases declared eleven sidebar entries for six destinations. Draft, Open,
// Cancelled and Closed Orders each opened this same workspace with a `status`
// preset, and History opened it with a different sort — five menu items leading
// to one screen, grouped under a node labelled "Orders", which says nothing
// about whose orders in an application that also sells.
//
// These pin the shape that replaced it: four entries and a status bar inside
// Purchase Orders that drives the existing filter. It was five until
// 2026-08-22, when the Sourcing group went: its two children, RFQs and Vendor
// Quotations, had no backend of any kind behind them.

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
import 'package:agency_desktop/ui/workspace/desktop_framework.dart';
import 'package:agency_desktop/ui/workspace/module_catalog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(List<String> permissions) {
  final String claims = base64Url
      .encode(utf8.encode(jsonEncode(<String, dynamic>{
        'roles': <String>['user'],
        'permissions': permissions,
      })))
      .replaceAll('=', '');
  return 'header.$claims.sig';
}

/// One row, so the grid renders instead of the empty state.
///
/// `StandardEmptyState` animates, and `pumpAndSettle` waits for animations to
/// stop — an empty list hangs the test rather than failing it.
final PurchaseOrder _order = PurchaseOrder.fromJson(<String, dynamic>{
  'id': 'po-1',
  'firm_id': 'firm-1',
  'po_number': 'PO-0001',
  'purchase_date': '2026-08-02',
  'status': 'DRAFT',
  'currency_code': 'INR',
  'grand_total': '590.00',
  'lines': <Json>[],
});

/// Every tab id Purchases still declares, plus the retired ones.
Set<String> _tabIds() =>
    ModuleCatalog.byId(AppModule.purchases).tabs.map((tab) => tab.id).toSet();

/// Flatten the sidebar tree so a leaf can be found at any depth.
Iterable<WorkspaceNavigationNode> _flatten(
  List<WorkspaceNavigationNode> nodes,
) sync* {
  for (final WorkspaceNavigationNode node in nodes) {
    yield node;
    yield* _flatten(node.children);
  }
}

class _RecordingApi extends ApiClient {
  _RecordingApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  /// Every list request, so a segment can be checked against what it asked for.
  final List<({String? status, String sortBy})> requests =
      <({String? status, String sortBy})>[];

  /// Counted so "selecting a row costs nothing" can be asserted rather than
  /// assumed.
  int historyCalls = 0;

  @override
  Future<PurchaseSummaryRecord> purchaseSummary() async =>
      const PurchaseSummaryRecord(
        total: 0,
        draft: 0,
        open: 0,
        cancelled: 0,
        closed: 0,
        totalValue: '0',
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
  }) async {
    requests.add((status: filters.status, sortBy: sortBy));
    return PagedResult<PurchaseOrder>(items: <PurchaseOrder>[_order], total: 1);
  }

  @override
  Future<PurchaseOrder> purchaseOrder(
    String id, {
    bool includeDeleted = false,
  }) async =>
      _order;

  @override
  Future<List<PurchaseOrderHistoryRecord>> purchaseOrderHistory(
    String id,
  ) async {
    historyCalls += 1;
    return const <PurchaseOrderHistoryRecord>[];
  }

  // The workspace loads six lookups before its first list. Unstubbed they
  // reach for a real server and the test hangs on `pumpAndSettle` rather than
  // failing, so every one of them answers empty here.
  @override
  Future<PagedResult<Vendor>> vendors({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    VendorQuery filters = const VendorQuery(),
  }) async =>
      const PagedResult<Vendor>(items: <Vendor>[], total: 0);

  @override
  Future<PagedResult<BranchRecord>> branches({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    BranchQuery filters = const BranchQuery(),
  }) async =>
      const PagedResult<BranchRecord>(items: <BranchRecord>[], total: 0);

  @override
  Future<PagedResult<WarehouseRecord>> warehouses({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    WarehouseQuery filters = const WarehouseQuery(),
  }) async =>
      const PagedResult<WarehouseRecord>(items: <WarehouseRecord>[], total: 0);

  @override
  Future<PagedResult<Product>> products({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    ProductQuery filters = const ProductQuery(),
  }) async =>
      const PagedResult<Product>(items: <Product>[], total: 0);

  @override
  Future<PagedResult<PlatformUser>> users({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
  }) async =>
      const PagedResult<PlatformUser>(items: <PlatformUser>[], total: 0);

  @override
  Future<PagedResult<TaxProfileRecord>> taxProfiles({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    String? taxSystemId,
  }) async =>
      const PagedResult<TaxProfileRecord>(
          items: <TaxProfileRecord>[], total: 0);
}

PermissionService _permissions() => PermissionService()
  ..applyAccessToken(_accessToken(const <String>[
    'PURCHASE_VIEW',
    'PURCHASE_CREATE',
    'PURCHASE_UPDATE',
  ]));

Future<_RecordingApi> _openOrders(
  WidgetTester tester, {
  PurchaseOrderView initialView = PurchaseOrderView.all,
}) async {
  tester.view.physicalSize = const Size(1600, 1000);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final Directory temp =
      Directory.systemTemp.createTempSync('purchase-navigation-test');
  addTearDown(() => temp.deleteSync(recursive: true));
  final DesktopPreferencesService preferences =
      DesktopPreferencesService(directory: temp);
  final _RecordingApi api = _RecordingApi();

  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: PurchaseManagementPage(
        api: api,
        preferences: preferences,
        permissions: _permissions(),
        hasActiveFirm: true,
        section: PurchaseSection.purchaseOrders,
        initialView: initialView,
      ),
    ),
  ));
  await tester.pumpAndSettle();
  return api;
}

void main() {
  group('the navigation says what it means', () {
    test('a status is not a module', () {
      final Set<String> ids = _tabIds();
      for (final String retired in <String>[
        'draft-orders',
        'open-orders',
        'cancelled-orders',
        'closed-orders',
        'purchase-history',
      ]) {
        expect(
          ids,
          isNot(contains(retired)),
          reason: '$retired opened the same workspace with a filter preset',
        );
      }
      expect(ids, contains('purchase-orders'));
    });

    test('four entries, and no group called Orders', () {
      final List<WorkspaceNavigationNode> nodes =
          ModuleCatalog.navigationChildren(AppModule.purchases, _tabIds());

      expect(
        nodes.map((node) => node.label),
        <String>['Dashboard', 'Purchase Orders', 'Analytics', 'Settings'],
      );
      expect(
          _flatten(nodes).map((node) => node.label), isNot(contains('Orders')));
    });

    test('nothing in the menu opens a screen the backend cannot serve', () {
      // Sourcing held RFQs and Vendor Quotations, and the backend has neither
      // -- no model, no endpoint, no service. Both rendered a sentence saying
      // the API does not expose them yet, which is a menu entry that cannot do
      // anything. Removed on 2026-08-22; assert the shape rather than the two
      // names, so a third placeholder cannot be added quietly.
      final List<WorkspaceNavigationNode> nodes =
          ModuleCatalog.navigationChildren(AppModule.purchases, _tabIds());
      final List<String?> paths = <String?>[
        for (final WorkspaceNavigationNode node in nodes) ...<String?>[
          node.path,
          ...node.children.map((child) => child.path),
        ],
      ];

      expect(nodes.map((node) => node.label), isNot(contains('Sourcing')));
      expect(paths, isNot(contains('purchase-rfqs')));
      expect(paths, isNot(contains('vendor-quotations')));
      expect(nodes.map((node) => node.label), contains('Purchase Orders'));
    });

    test('a retired tab id still resolves somewhere real', () {
      // The last workspace is persisted, so an upgrade must not strand a user
      // who left the app on Draft Orders -- or, since 2026-08-22, on RFQs or
      // Vendor Quotations, which were removed for having no backend at all.
      for (final String retired in ModuleCatalog.purchaseTabAliases.keys) {
        expect(
          ModuleCatalog.purchaseTabAliases[retired],
          'purchase-orders',
          reason: '$retired must lead to the workspace that absorbed it',
        );
      }
    });
  });

  group('the status bar drives the existing filter', () {
    testWidgets('every segment is offered', (tester) async {
      await _openOrders(tester);

      for (final String label in <String>[
        'All',
        'Draft',
        'Open',
        'Cancelled',
        'Closed',
        'History',
      ]) {
        expect(find.widgetWithText(SegmentedButton<PurchaseOrderView>, label),
            findsOneWidget);
      }
    });

    testWidgets('choosing one asks the server for it', (tester) async {
      final _RecordingApi api = await _openOrders(tester);
      expect(api.requests.last.status, isNull, reason: 'All filters nothing');

      await tester.tap(find.text('Draft'));
      await tester.pumpAndSettle();
      expect(api.requests.last.status, 'DRAFT');

      await tester.tap(find.text('Cancelled'));
      await tester.pumpAndSettle();
      expect(api.requests.last.status, 'CANCELLED');
    });

    testWidgets('History is a sort, not a status', (tester) async {
      final _RecordingApi api = await _openOrders(tester);

      await tester.tap(find.text('History'));
      await tester.pumpAndSettle();

      // It narrows nothing — it reorders. That is what makes it worth a
      // segment beside All rather than a duplicate of it.
      expect(api.requests.last.status, isNull);
      expect(api.requests.last.sortBy, 'purchase_date');
    });

    testWidgets('a workspace restored on Draft opens on Draft', (tester) async {
      final _RecordingApi api =
          await _openOrders(tester, initialView: PurchaseOrderView.draft);

      expect(api.requests.first.status, 'DRAFT');
    });

    testWidgets('no other section shows the bar', (tester) async {
      // Taller than the others: the dashboard stacks seven metric cards, two
      // summary panels and an embedded grid.
      tester.view.physicalSize = const Size(1600, 1600);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      final Directory temp =
          Directory.systemTemp.createTempSync('purchase-navigation-dash');
      addTearDown(() => temp.deleteSync(recursive: true));
      final DesktopPreferencesService preferences =
          DesktopPreferencesService(directory: temp);

      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: PurchaseManagementPage(
            api: _RecordingApi(),
            preferences: preferences,
            permissions: _permissions(),
            hasActiveFirm: true,
            section: PurchaseSection.dashboard,
          ),
        ),
      ));
      await tester.pumpAndSettle();

      expect(find.byType(SegmentedButton<PurchaseOrderView>), findsNothing);
    });
  });

  group('what is not built stays not built', () {
    for (final (PurchaseSection section, String label)
        in <(PurchaseSection, String)>[
      (PurchaseSection.analytics, 'Analytics'),
    ]) {
      testWidgets('$label says so rather than inventing a screen',
          (tester) async {
        tester.view.physicalSize = const Size(1600, 1000);
        tester.view.devicePixelRatio = 1;
        addTearDown(tester.view.reset);
        final Directory temp =
            Directory.systemTemp.createTempSync('purchase-navigation-soon');
        addTearDown(() => temp.deleteSync(recursive: true));
        final DesktopPreferencesService preferences =
            DesktopPreferencesService(directory: temp);

        await tester.pumpWidget(MaterialApp(
          home: Scaffold(
            body: PurchaseManagementPage(
              api: _RecordingApi(),
              preferences: preferences,
              permissions: _permissions(),
              hasActiveFirm: true,
              section: section,
            ),
          ),
        ));
        await tester.pumpAndSettle();

        expect(find.textContaining(label), findsWidgets);
        expect(find.byType(SegmentedButton<PurchaseOrderView>), findsNothing);
      });
    }
  });

  group('the grid keeps its width', () {
    testWidgets('there is no details panel beside the table', (tester) async {
      // It repeated columns the grid already shows -- PO number, vendor,
      // branch, warehouse, buyer, date, status, priority, total -- and took a
      // third of the width to do it, squeezing a fifteen-column table.
      await _openOrders(tester);

      expect(find.byType(QuickSummaryPanel), findsNothing);
      expect(find.byType(DetailsPanel), findsNothing);
      expect(find.text('PO-0001'), findsWidgets);
    });

    testWidgets('double-clicking a row opens the document', (tester) async {
      final _RecordingApi api = await _openOrders(tester);

      final Finder row = find.text('PO-0001').first;
      await tester.tap(row);
      await tester.pump(const Duration(milliseconds: 50));
      await tester.tap(row);
      await tester.pumpAndSettle();

      // The full document, which is where everything the panel showed lives.
      expect(find.text('Document Header'), findsWidgets);
      expect(api.historyCalls, greaterThan(0),
          reason: 'the dialog loads its own history');
    });

    testWidgets('selecting a row costs no request', (tester) async {
      // Selecting used to fetch that order's whole history to fill one
      // "Latest Activity" line in the panel -- on every click.
      final _RecordingApi api = await _openOrders(tester);
      final int before = api.historyCalls;

      await tester.tap(find.text('PO-0001').first);
      await tester.pumpAndSettle();

      expect(api.historyCalls, before);
    });
  });
}
