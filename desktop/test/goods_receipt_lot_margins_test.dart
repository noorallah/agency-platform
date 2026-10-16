// Row L3 step 5: a firm costing by lot keeps a retail and a wholesale margin
// on each lot. The receipt line offers both beside the two prices, blank
// taking the product's; the saved line's worked prices and any MRP warning
// are shown in place. A firm on Average sends no margins.

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/business/business_features.dart';
import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/goods_receipt.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/models/purchase.dart';
import 'package:agency_desktop/ui/goods_receipts/goods_receipt_editor_dialog.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

PurchaseOrder _order() => PurchaseOrder.fromJson({
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
          'description': 'Amoxicillin 500mg',
          'ordered_quantity': '10',
          'unit_price': '100',
        },
      ],
    });

class _ReceiptApi extends ApiClient {
  _ReceiptApi({this.mrpWarning})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  /// What the saved line warns of, if anything.
  final String? mrpWarning;
  Json? sent;

  @override
  Future<GoodsReceiptRecord> updateGoodsReceipt(
    String id,
    Json data, {
    int? expectedVersion,
  }) =>
      createGoodsReceipt(data);

  @override
  Future<PagedResult<GoodsReceiptRecord>> goodsReceipts({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    Map<String, String> filters = const {},
  }) async =>
      const PagedResult<GoodsReceiptRecord>(items: [], total: 0);

  @override
  Future<GoodsReceiptRecord> createGoodsReceipt(Json data) async {
    sent = data;
    return GoodsReceiptRecord.fromJson({
      'id': 'grn-2',
      'grn_number': 'GRN-2',
      'status': 'DRAFT',
      'lines': [
        {
          'id': 'grn-line-1',
          'line_number': 1,
          'purchase_order_line_id': 'po-line-1',
          'current_receipt_quantity': '10',
          'ptr': '125.00',
          'pts': '110.00',
          'retail_margin_percent': '25.0000',
          'wholesale_margin_percent': '10.0000',
          'mrp_warning': mrpWarning,
        },
      ],
    });
  }
}

Future<void> _openEditor(
  WidgetTester tester,
  _ReceiptApi api, {
  required bool byLot,
  Set<String> features = const {},
  GoodsReceiptRecord? existing,
}) async {
  tester.view.physicalSize = const Size(1600, 1800);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: Phase2Scope(
          child: GoodsReceiptEditorDialog(
            api: api,
            purchaseOrders: [_order()],
            warehouses: [
              WarehouseRecord.fromJson({
                'id': 'wh-1',
                'code': 'MAIN',
                'name': 'Main Warehouse',
              }),
            ],
            products: [
              Product.fromJson({
                'id': 'prod-1',
                'code': 'SKU-1',
                'name': 'Amoxicillin 500mg',
              }),
            ],
            features: BusinessFeatures(features),
            costsByLot: byLot,
            existing: existing,
          ),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
  if (existing != null) return;
  await tester.tap(find.byKey(const ValueKey('goods-receipt-order')));
  await tester.pumpAndSettle();
  await tester.tap(find.textContaining('PO-2026-000001').last);
  await tester.pumpAndSettle();
}

Json _sentLine(_ReceiptApi api) =>
    (api.sent!['lines'] as List<dynamic>).single as Json;

const ValueKey<String> _retail =
    ValueKey<String>('goods-receipt-retail-margin-po-1-0');
const ValueKey<String> _wholesale =
    ValueKey<String>('goods-receipt-wholesale-margin-po-1-0');

void main() {
  testWidgets('by lot: margins start blank and travel with no batch number',
      (tester) async {
    final _ReceiptApi api = _ReceiptApi();
    await _openEditor(tester, api, byLot: true);

    // Never prefilled: blank is the product's margin, and says so.
    expect(tester.widget<TextFormField>(find.byKey(_retail)).initialValue, '');
    expect(
        tester.widget<TextFormField>(find.byKey(_wholesale)).initialValue, '');
    expect(find.text("Blank takes the product's margin"), findsNWidgets(2));
    // Without BATCH_PTR_PTS the prices are plain retail and wholesale.
    expect(find.text('Retail price per unit, before tax'), findsOneWidget);
    expect(find.text('Wholesale price per unit, before tax'), findsOneWidget);

    await tester.enterText(find.byKey(_retail), '25');
    await tester.enterText(
      find.byKey(const ValueKey<String>('goods-receipt-pts-po-1-0')),
      '110',
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('goods-receipt-save')));
    await tester.pumpAndSettle();

    final Json line = _sentLine(api);
    expect(line['retail_margin_percent'], '25');
    expect(line.containsKey('wholesale_margin_percent'), isFalse);
    expect(line['pts'], '110');
    expect(line.containsKey('ptr'), isFalse);
    expect(line.containsKey('batch_number'), isFalse);
  });

  testWidgets('by lot: a price above the MRP keeps the window open to warn',
      (tester) async {
    final _ReceiptApi api = _ReceiptApi(
      mrpWarning: 'The retail price 125.00 with GST is above the MRP 130.00.',
    );
    await _openEditor(tester, api, byLot: true);
    await tester.tap(find.byKey(const ValueKey('goods-receipt-save')));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);

    // Saved, and still on screen with the warning, not an error banner.
    expect(find.byKey(const ValueKey('goods-receipt-mrp-warnings')),
        findsOneWidget);
    expect(find.textContaining('Line 1: The retail price 125.00'),
        findsOneWidget);
    expect(find.byKey(const ValueKey('goods-receipt-mrp-warning-0')),
        findsOneWidget);
    expect(find.byType(MaterialBanner), findsNothing);
    // The worked prices as the server saved them.
    expect(find.byKey(const ValueKey('goods-receipt-saved-ptr-0')),
        findsOneWidget);
    expect(find.byKey(const ValueKey('goods-receipt-saved-pts-0')),
        findsOneWidget);
    expect(find.text('Retail price as saved'), findsOneWidget);
    expect(find.text('25%'), findsOneWidget);
    expect(find.text('Close'), findsOneWidget);
  });

  testWidgets('by lot with BATCH_PTR_PTS: the prices say PTR and PTS',
      (tester) async {
    final _ReceiptApi api = _ReceiptApi();
    await _openEditor(tester, api,
        byLot: true, features: const {'BATCH_PTR_PTS'});
    expect(find.text('Retail price (PTR) per unit, before tax'),
        findsOneWidget);
    expect(find.text('Wholesale price (PTS) per unit, before tax'),
        findsOneWidget);
    expect(find.text('Retail margin %'), findsOneWidget);
    expect(find.text('Wholesale margin %'), findsOneWidget);
    // The Average-firm PTR box is not shown twice.
    expect(find.text('PTR per unit (retailer)'), findsNothing);
  });

  testWidgets('by lot: a margin typed on a draft re-works the saved price',
      (tester) async {
    final _ReceiptApi api = _ReceiptApi();
    final GoodsReceiptRecord draft = GoodsReceiptRecord.fromJson({
      'id': 'grn-2',
      'grn_number': 'GRN-2',
      'status': 'DRAFT',
      'purchase_order_id': 'po-1',
      'version': 1,
      'lines': [
        {
          'id': 'grn-line-1',
          'line_number': 1,
          'purchase_order_line_id': 'po-line-1',
          'current_receipt_quantity': '10',
          'warehouse_id': 'wh-1',
          'ptr': '125.00',
          'pts': '110.00',
          'retail_margin_percent': '25.0000',
          'wholesale_margin_percent': '10.0000',
        },
      ],
    });
    await _openEditor(tester, api, byLot: true, existing: draft);
    // The saved margins are not put into the boxes.
    expect(tester.widget<TextFormField>(find.byKey(_retail)).initialValue, '');

    await tester.enterText(find.byKey(_retail), '30');
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('goods-receipt-save')));
    await tester.pumpAndSettle();

    final Json line = _sentLine(api);
    expect(line['retail_margin_percent'], '30');
    // The price carried in would win over the margin, so it is cleared.
    expect(line.containsKey('ptr'), isFalse);
    // The wholesale price nobody touched is kept.
    expect(line['pts'], '110.00');
  });

  testWidgets(
      'by lot: a price typed, then a margin, keeps the typed price (D-UI-109)',
      (tester) async {
    final _ReceiptApi api = _ReceiptApi();
    await _openEditor(tester, api, byLot: true);

    // The boxes' own order, left to right: the price, then its margin.
    await tester.enterText(
      find.byKey(const ValueKey<String>('goods-receipt-ptr-po-1-0')),
      '104',
    );
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(_retail), '40');
    await tester.pumpAndSettle();
    // The price box still holds what was typed.
    expect(find.byKey(const ValueKey<String>('goods-receipt-ptr-po-1-0')),
        findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('goods-receipt-save')));
    await tester.pumpAndSettle();

    final Json line = _sentLine(api);
    // A typed price wins over the margin; the server works the margin back.
    expect(line['ptr'], '104');
    expect(line['retail_margin_percent'], '40');
  });

  testWidgets('on Average no margin is offered or sent', (tester) async {
    final _ReceiptApi api = _ReceiptApi();
    await _openEditor(tester, api, byLot: false);
    expect(find.byKey(_retail), findsNothing);
    expect(find.byKey(_wholesale), findsNothing);
    expect(find.text('Retail margin %'), findsNothing);

    await tester.enterText(
      find.byKey(const ValueKey<String>('goods-receipt-batch-po-1-0')),
      'B-1',
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('goods-receipt-save')));
    await tester.pumpAndSettle();
    final Json line = _sentLine(api);
    expect(line.containsKey('retail_margin_percent'), isFalse);
    expect(line.containsKey('wholesale_margin_percent'), isFalse);
  });
}
