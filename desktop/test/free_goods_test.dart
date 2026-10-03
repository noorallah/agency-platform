// BUY-1: free goods. The product flag, the scheme on a receipt line, the
// write-off to a customer, and the report that ties them together.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/goods_receipt.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/models/purchase.dart';
import 'package:agency_desktop/models/report.dart';
import 'package:agency_desktop/ui/goods_receipts/goods_receipt_editor_dialog.dart';
import 'package:agency_desktop/ui/inventory/stock_action_dialog.dart';
import 'package:agency_desktop/ui/products/product_management_page.dart';
import 'package:agency_desktop/ui/reports/report_catalog.dart';
import 'package:agency_desktop/ui/reports/reports_workspace.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

class _Api extends ApiClient {
  _Api()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  Json? sent;
  final List<String> requested = [];

  @override
  Future<GoodsReceiptRecord> createGoodsReceipt(Json data) async {
    sent = data;
    return GoodsReceiptRecord.fromJson({'id': 'grn-2', 'status': 'DRAFT'});
  }

  @override
  Future<ReportPage> reportRows(
    String path, {
    Map<String, String>? query,
    String? rowsKey,
  }) async {
    requested.add(path);
    return const ReportPage(rows: [], total: 0);
  }
}

PermissionService _permissions() {
  final String payload = base64Url.encode(utf8.encode(jsonEncode({
    'permissions': ['REPORT_VIEW', 'INVENTORY_VIEW'],
  })));
  return PermissionService()..applyAccessToken('h.$payload.s');
}

void main() {
  testWidgets('a product marked for free issue only is saved so',
      (tester) async {
    tester.view.physicalSize = const Size(1600, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    Json? sent;
    final Product gift = Product.fromJson(const {
      'id': 'p-9',
      'code': 'GIFT-1',
      'name': 'Steel bowl',
      'product_type': 'STOCK_ITEM',
      'status': 'ACTIVE',
      'unit': 'NOS',
    });
    const ProductMetadataRecord metadata = ProductMetadataRecord(
      profileCode: 'WHOLESALE',
      features: [],
      categories: [],
      taxProfiles: [],
      requiredAttributeDefinitionIds: [],
      optionalAttributeDefinitionIds: [],
    );
    await tester.pumpWidget(MaterialApp(
      builder: (context, child) => Phase2Scope(child: child!),
      home: Scaffold(
        body: ProductWorkspaceDialog(
          mode: ProductDialogMode.edit,
          product: gift,
          categories: const [],
          uoms: const [],
          definitions: const [],
          metadata: metadata,
          initialTab: 'general',
          onMetadataForCategory: (_) async => metadata,
          onSave: (payload) async {
            sent = payload;
            return gift;
          },
          onTabChanged: (_) {},
        ),
      ),
    ));
    await tester.pumpAndSettle();
    expect(find.text('Promotional stock: given away, never sold at a price'),
        findsOneWidget);
    final Finder box = find.byKey(const ValueKey('product-free-issue-only'));
    await tester.ensureVisible(box);
    await tester.tap(box);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('product-save')));
    await tester.pumpAndSettle();
    expect(sent?['free_issue_only'], isTrue);
  });

  testWidgets('the scheme typed on a receipt line is sent', (tester) async {
    tester.view.physicalSize = const Size(1600, 1000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final _Api api = _Api();
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Phase2Scope(
          child: GoodsReceiptEditorDialog(
            api: api,
            purchaseOrders: [
              PurchaseOrder.fromJson({
                'id': 'po-1',
                'po_number': 'PO-2026-000001',
                'purchase_date': '2026-08-01',
                'warehouse_id': 'wh-1',
                'status': 'APPROVED',
                'lines': [
                  {
                    'id': 'po-line-1',
                    'line_number': 1,
                    'product_id': 'prod-1',
                    'description': 'Soap',
                    'ordered_quantity': '10',
                    'unit_price': '25',
                  },
                ],
              }),
            ],
            warehouses: [
              WarehouseRecord.fromJson(
                  {'id': 'wh-1', 'code': 'MAIN', 'name': 'Main'}),
            ],
            products: [
              Product.fromJson(
                  {'id': 'prod-1', 'code': 'SKU-1', 'name': 'Soap'}),
            ],
          ),
        ),
      ),
    ));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('goods-receipt-order')));
    await tester.pumpAndSettle();
    await tester.tap(find.textContaining('PO-2026-000001').last);
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(const ValueKey<String>('goods-receipt-scheme-po-1-0')),
      'Buy 10 get 1',
    );
    await tester.tap(find.byKey(const ValueKey('goods-receipt-save')));
    await tester.pumpAndSettle();
    final Json line = (api.sent!['lines'] as List<dynamic>).single as Json;
    expect(line['scheme_name'], 'Buy 10 get 1');
  });

  testWidgets('a free gift needs a customer and sends the one chosen',
      (tester) async {
    tester.view.physicalSize = const Size(1366, 768);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final List<Json> saved = [];
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: StockActionDialog(
          action: StockAction.writeOff,
          productLabel: 'Steel bowl',
          warehouseLabel: 'Main',
          sourceWarehouseId: 'wh-1',
          available: 20,
          quarantined: 0,
          warehouses: const [],
          reasons: const [
            StockReasonOption(code: 'DAMAGE', name: 'Damage'),
            StockReasonOption(
                code: 'FREE_TO_CUSTOMER', name: 'Given free to customer'),
            StockReasonOption(code: 'SAMPLE', name: 'Sample'),
          ],
          searchCustomers: (text) async => const [
            StockCustomerOption(id: 'c-1', label: 'C-001 - Asha Stores'),
          ],
          onSave: (draft) async => saved.add(draft),
        ),
      ),
    ));
    await tester.pumpAndSettle();
    await tester.enterText(find.widgetWithText(TextField, 'Quantity'), '2');
    await tester.tap(find.text('Damage'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Given free to customer').last);
    await tester.pumpAndSettle();

    await tester.tap(find.widgetWithText(FilledButton, 'Write off'));
    await tester.pumpAndSettle();
    expect(saved, isEmpty);
    expect(find.text('Choose the customer it was given to.'), findsOneWidget);

    await tester.enterText(
        find.byKey(const ValueKey('stock-write-off-customer')), 'Ash');
    await tester.pumpAndSettle();
    await tester.tap(find.text('C-001 - Asha Stores'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Write off'));
    await tester.pumpAndSettle();
    expect(saved.single['reason'], 'FREE_TO_CUSTOMER');
    expect(saved.single['customer_id'], 'c-1');
  });

  testWidgets('the free goods report asks for its own path', (tester) async {
    final ReportDefinition report =
        reportCatalog.firstWhere((entry) => entry.id == 'free-goods');
    expect(report.path, '/api/v1/inventory/reports/free-goods');
    expect(report.needsPeriod, isTrue);
    expect([for (final ReportColumn c in report.columns) c.label], [
      'Section',
      'Supplier / customer',
      'Scheme / reason',
      'Product',
      'Quantity',
      'Value',
    ]);

    tester.view.physicalSize = const Size(1600, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final _Api api = _Api();
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: ReportsWorkspace(
          api: api,
          permissions: _permissions(),
          hasActiveFirm: true,
          tabId: 'operational',
        ),
      ),
    ));
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.text('Free goods'), 200,
        scrollable: find.byType(Scrollable).first);
    await tester.ensureVisible(find.text('Free goods'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Free goods'));
    await tester.pumpAndSettle();
    expect(api.requested.last, '/api/v1/inventory/reports/free-goods');
  });
}
