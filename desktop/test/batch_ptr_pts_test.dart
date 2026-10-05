// Batch-wise PTR / PTS (PG-14, backlog 86 row 22): the customer's trade
// class, the rates typed on a goods receipt line, and the batch picker's
// columns -- all behind the BATCH_PTR_PTS feature.

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/business/business_features.dart';
import 'package:agency_desktop/models/batch_serial.dart';
import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/customer.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/goods_receipt.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/models/purchase.dart';
import 'package:agency_desktop/ui/customers/customer_management_page.dart';
import 'package:agency_desktop/ui/goods_receipts/goods_receipt_editor_dialog.dart';
import 'package:agency_desktop/ui/workspace/batch_picker_panel.dart';
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

  @override
  Future<GoodsReceiptRecord> createGoodsReceipt(Json data) async {
    sent = data;
    return GoodsReceiptRecord.fromJson(
        {'id': 'grn-2', 'grn_number': 'GRN-2', 'status': 'DRAFT'});
  }

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
  Future<List<BatchAvailabilityRecord>> batchAvailability({
    required String productId,
    required String warehouseId,
    String? storageNodeId,
    String? asOf,
    num? quantity,
    String? salesOrderLineId,
    String? customerId,
  }) async =>
      [
        BatchAvailabilityRecord.fromJson(<String, dynamic>{
          'batch_id': 'b1',
          'batch_number': 'BN-1',
          'expiry_date': '2027-06-01',
          'days_to_expiry': 200,
          'on_hand': '20',
          'reserved': '0',
          'available': '20',
          'available_to_line': '20',
          'fefo': '1',
          'mrp': '100',
          'ptr': '70.5',
          'pts': '60',
        }),
      ];
}

PurchaseOrder _order() => PurchaseOrder.fromJson({
      'id': 'po-1',
      'po_number': 'PO-1',
      'purchase_date': '2026-08-01',
      'warehouse_id': 'wh-1',
      'status': 'APPROVED',
      'lines': [
        {
          'id': 'po-line-1',
          'line_number': 1,
          'product_id': 'prod-1',
          'description': 'Tablet',
          'ordered_quantity': '3',
          'unit_price': '10',
        },
      ],
    });

Future<void> _openReceipt(
  WidgetTester tester,
  _Api api,
  BusinessFeatures features,
) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: Phase2Scope(
          child: GoodsReceiptEditorDialog(
            api: api,
            features: features,
            purchaseOrders: [_order()],
            warehouses: [
              WarehouseRecord.fromJson(
                  {'id': 'wh-1', 'code': 'MAIN', 'name': 'Main'}),
            ],
            products: [
              Product.fromJson(
                  {'id': 'prod-1', 'code': 'TB', 'name': 'Tablet'}),
            ],
          ),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
  await tester.tap(find.byKey(const ValueKey('goods-receipt-order')));
  await tester.pumpAndSettle();
  await tester.tap(find.textContaining('PO-1').last);
  await tester.pumpAndSettle();
  await tester.enterText(
      find.byKey(const ValueKey('goods-receipt-batch-po-1-0')), 'BN-9');
  await tester.pumpAndSettle();
}

Future<void> _save(WidgetTester tester) async {
  await tester.tap(find.byKey(const ValueKey('goods-receipt-save')));
  await tester.pumpAndSettle();
}

Json _customerJson(String? tradeClass) => <String, dynamic>{
      'id': 'cust-1',
      'code': 'C001',
      'name': 'Anand',
      'display_name': 'Anand',
      'customer_type': 'BUSINESS',
      'currency_code': 'INR',
      'status': 'ACTIVE',
      'credit_limit': '0',
      'default_discount_percent': '0',
      'trade_class': tradeClass,
      'addresses': const <Json>[],
      'contacts': const <Json>[],
    };

Future<Json?> _customerSave(
  WidgetTester tester, {
  String? stored,
  String? pick,
}) async {
  tester.view.physicalSize = const Size(1700, 1400);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  Json? saved;
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: CustomerWorkspaceDialog(
        mode: CustomerDialogMode.edit,
        customer: Customer.fromJson(_customerJson(stored)),
        loadPlaces: (level, {parentId = ''}) async => const [],
        onSave: (payload) async {
          saved = payload;
          return Customer.fromJson(_customerJson(stored));
        },
      ),
    ),
  ));
  await tester.pumpAndSettle();
  await tester.tap(find.text('Financial'));
  await tester.pumpAndSettle();
  if (pick != null) {
    await tester.tap(find.byKey(const ValueKey('customer-trade-class')));
    await tester.pumpAndSettle();
    await tester.tap(find.text(pick).last);
    await tester.pumpAndSettle();
  }
  await tester.tap(find.widgetWithText(FilledButton, 'Save'));
  await tester.pumpAndSettle();
  return saved;
}

Future<void> _picker(WidgetTester tester, bool show) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: SingleChildScrollView(
        child: BatchPickerPanel(
          api: _Api(),
          lineId: 'l1',
          productId: 'prod-1',
          warehouseId: 'wh-1',
          asOf: '2026-08-01',
          quantity: 5,
          picks: null,
          enabled: true,
          showPtrPts: show,
          onChanged: (_) {},
        ),
      ),
    ),
  ));
  await tester.pump(const Duration(milliseconds: 400));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('a picked trade class is sent; Not set is null', (tester) async {
    final Json? picked = await _customerSave(tester, pick: 'Stockist');
    expect(picked!['trade_class'], 'STOCKIST');
  });

  testWidgets('the stored trade class is kept on save', (tester) async {
    final Json? kept = await _customerSave(tester, stored: 'RETAILER');
    expect(kept!['trade_class'], 'RETAILER');
  });

  testWidgets('Not set goes as null', (tester) async {
    final Json? none = await _customerSave(tester);
    expect(none!.containsKey('trade_class'), isTrue);
    expect(none['trade_class'], isNull);
  });

  testWidgets('the receipt sends ptr and pts only when typed', (tester) async {
    final _Api api = _Api();
    await _openReceipt(tester, api, const BusinessFeatures({'BATCH_PTR_PTS'}));
    await tester.enterText(
        find.byKey(const ValueKey('goods-receipt-ptr-po-1-0')), '70');
    await _save(tester);
    final Json line = (api.sent!['lines'] as List).first as Json;
    expect(line['ptr'], '70');
    expect(line.containsKey('pts'), isFalse);
    expect(tester.takeException(), isNull);
  });

  testWidgets('without the feature the fields are absent and nothing is sent',
      (tester) async {
    final _Api api = _Api();
    await _openReceipt(tester, api, const BusinessFeatures(<String>{}));
    expect(find.byKey(const ValueKey('goods-receipt-ptr-po-1-0')),
        findsNothing);
    expect(find.byKey(const ValueKey('goods-receipt-pts-po-1-0')),
        findsNothing);
    await _save(tester);
    final Json line = (api.sent!['lines'] as List).first as Json;
    expect(line.containsKey('ptr'), isFalse);
    expect(line.containsKey('pts'), isFalse);
  });

  testWidgets('a rate above the MRP is refused before the server',
      (tester) async {
    final _Api api = _Api();
    await _openReceipt(tester, api, const BusinessFeatures({'BATCH_PTR_PTS'}));
    await tester.enterText(
        find.byKey(const ValueKey('goods-receipt-mrp-po-1-0')), '100');
    await tester.enterText(
        find.byKey(const ValueKey('goods-receipt-pts-po-1-0')), '120');
    await _save(tester);
    expect(find.textContaining('PTS cannot be more than the MRP'),
        findsOneWidget);
    expect(api.sent, isNull);
  });

  testWidgets('the picker shows PTR and PTS when the feature is on',
      (tester) async {
    await _picker(tester, true);
    expect(find.textContaining('PTR 70.50'), findsOneWidget);
    expect(find.textContaining('PTS 60.00'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('the picker hides them when the feature is off', (tester) async {
    await _picker(tester, false);
    expect(find.textContaining('MRP 100.00'), findsOneWidget);
    expect(find.textContaining('PTR'), findsNothing);
    expect(find.textContaining('PTS'), findsNothing);
  });
}
