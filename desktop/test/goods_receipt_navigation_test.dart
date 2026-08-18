// A receipt's status is a view of the list, not a module.
//
// Goods Receipts declared eight menu entries for two destinations. Six of them
// sat under a group called "Reports" — Pending, Partial and Completed
// Receipts, Rejected and Damaged Items, History — and every one opened the
// same workspace. Worse than Purchases had it:
//
//   * `partial-receipts`, `rejected-items` and `damaged-items` filtered
//     **nothing at all** and showed the same list as Receipts;
//   * `grn-history` filtered `status = COMPLETED`, an exact duplicate of
//     Completed Receipts.
//
// The workspace itself put a 43%-wide `ListView` beside a 57%-wide document
// pane, so the list of receipts had less room than the preview of the one
// pointed at, and there was no table at all.

import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/document_framework.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/goods_receipt.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/models/purchase.dart';
import 'package:agency_desktop/ui/goods_receipts/goods_receipt_management_page.dart';
import 'package:agency_desktop/ui/document_framework/document_framework_widgets.dart';
import 'package:agency_desktop/ui/goods_receipts/goods_receipt_view_dialog.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart';
import 'package:agency_desktop/ui/workspace/module_catalog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/access_token.dart';

Json _receiptJson(String number, String status) => <String, dynamic>{
      'id': 'grn-$number',
      'firm_id': 'firm-1',
      'grn_number': number,
      'purchase_order_number': 'PO-0001',
      'receipt_date': '2026-08-02',
      'status': status,
      'grand_total': '590.00',
      'lines': <Json>[],
    };

class _ReceiptApi extends ApiClient {
  _ReceiptApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  /// Every list request, so a segment can be checked against what it asked
  /// for rather than against what the screen happens to show.
  final List<Map<String, String>> requests = <Map<String, String>>[];
  int historyCalls = 0;

  @override
  Future<Json> goodsReceiptSummary() async => const <String, dynamic>{
        'total': 2,
        'draft': 1,
        'completed': 1,
        'cancelled': 0,
        'closed': 0,
      };

  @override
  Future<PagedResult<GoodsReceiptRecord>> goodsReceipts({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    Map<String, String> filters = const <String, String>{},
  }) async {
    requests.add(Map<String, String>.from(filters));
    return PagedResult<GoodsReceiptRecord>(
      items: <GoodsReceiptRecord>[
        GoodsReceiptRecord.fromJson(_receiptJson('GRN-0001', 'DRAFT')),
        GoodsReceiptRecord.fromJson(_receiptJson('GRN-0002', 'COMPLETED')),
      ],
      total: 2,
    );
  }

  @override
  Future<List<DocumentTimelineSnapshot>> goodsReceiptHistory(String id) async {
    historyCalls += 1;
    return const <DocumentTimelineSnapshot>[];
  }

  @override
  Future<PagedResult<PurchaseOrder>> purchases({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    PurchaseQuery filters = const PurchaseQuery(),
  }) async =>
      const PagedResult<PurchaseOrder>(items: <PurchaseOrder>[], total: 0);

  @override
  Future<PagedResult<WarehouseRecord>> warehouses({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    WarehouseQuery filters = const WarehouseQuery(),
  }) async =>
      const PagedResult<WarehouseRecord>(
          items: <WarehouseRecord>[], total: 0);

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
}

Future<_ReceiptApi> _open(WidgetTester tester) async {
  tester.view.physicalSize = const Size(1600, 1200);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final Directory temp = Directory.systemTemp.createTempSync('grn-nav');
  addTearDown(() => temp.deleteSync(recursive: true));
  final _ReceiptApi api = _ReceiptApi();

  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: GoodsReceiptManagementPage(
        api: api,
        preferences: DesktopPreferencesService(directory: temp),
        permissions: PermissionService()
          ..applyAccessToken(accessTokenFor(
              const <String>['PURCHASE_VIEW', 'PURCHASE_CREATE'])),
        hasActiveFirm: true,
        tabId: 'receipts',
      ),
    ),
  ));
  await tester.pumpAndSettle();
  return api;
}

void main() {
  group('the navigation says what it means', () {
    test('a status is not a menu entry', () {
      final Set<String> ids = ModuleCatalog.byId(AppModule.goodsReceipts)
          .tabs
          .map((tab) => tab.id)
          .toSet();

      for (final String retired in ModuleCatalog.goodsReceiptTabAliases.keys) {
        expect(ids, isNot(contains(retired)), reason: '$retired was a view');
      }
      expect(ids, <String>{'receipts', 'grn-settings'});
    });

    test('two entries, and no group called Reports', () {
      final List<WorkspaceNavigationNode> nodes =
          ModuleCatalog.navigationChildren(
        AppModule.goodsReceipts,
        <String>{'receipts', 'grn-settings'},
      );

      expect(nodes.map((node) => node.label), <String>['Receipts', 'Settings']);
      expect(nodes.every((node) => node.isLeaf), isTrue);
    });

    test('a retired id still resolves to the workspace that absorbed it', () {
      for (final String path in ModuleCatalog.goodsReceiptTabAliases.values) {
        expect(path, 'receipts');
      }
    });
  });

  group('the status bar drives the query', () {
    testWidgets('every segment is offered', (tester) async {
      await _open(tester);

      for (final String label in <String>[
        'All',
        'Draft',
        'Completed',
        'Cancelled',
        'Closed',
      ]) {
        expect(
          find.widgetWithText(SegmentedButton<GoodsReceiptView>, label),
          findsOneWidget,
        );
      }
    });

    testWidgets('choosing one asks the server for it', (tester) async {
      final _ReceiptApi api = await _open(tester);
      expect(api.requests.last, isEmpty, reason: 'All filters nothing');

      // Scoped to the bar: the summary cards above carry the same words.
      Future<void> choose(String label) async {
        await tester.tap(find.descendant(
          of: find.byType(SegmentedButton<GoodsReceiptView>),
          matching: find.text(label),
        ));
        await tester.pumpAndSettle();
      }

      await choose('Completed');
      expect(api.requests.last, <String, String>{'status': 'COMPLETED'});

      await choose('Cancelled');
      expect(api.requests.last, <String, String>{'status': 'CANCELLED'});
    });
  });

  group('the table gets the width', () {
    testWidgets('a real grid, and no pinned document pane', (tester) async {
      await _open(tester);

      expect(find.byType(EnterpriseDataGrid<GoodsReceiptRecord>),
          findsOneWidget);
      // The pane held these; they belong in the dialog now.
      expect(find.byType(EnterpriseDocumentLines), findsNothing);
      expect(find.byType(EnterpriseTimeline), findsNothing);
      expect(find.text('GRN-0001'), findsWidgets);
    });

    testWidgets('double-clicking a row opens the document', (tester) async {
      final _ReceiptApi api = await _open(tester);

      final Finder row = find.text('GRN-0001').first;
      await tester.tap(row);
      await tester.pump(const Duration(milliseconds: 50));
      await tester.tap(row);
      await tester.pumpAndSettle();

      expect(find.byType(GoodsReceiptViewDialog), findsOneWidget);
      expect(api.historyCalls, greaterThan(0));
    });
  });

  group('the action that posts stock says so', () {
    testWidgets('the toolbar offers Complete, not Request approval',
        (tester) async {
      // `requestApproval` maps to `completeGoodsReceipt`, which is what moves
      // inventory. A receipt has no approval step, and naming the button after
      // one is how somebody completes a receipt without meaning to.
      await _open(tester);

      expect(find.text('Complete'), findsWidgets);
      expect(find.text('Request approval'), findsNothing);
    });
  });
}
