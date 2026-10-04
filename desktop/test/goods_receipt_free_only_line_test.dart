import 'package:agency_desktop/core/api/api_client.dart';
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

/// D-BUY-33: a free product of its own -- buy ten soap, get a bucket -- is an
/// order line with nothing to pay and only free goods. The receipt started
/// that line at nothing and, given a free quantity alone, left it out of the
/// save, so the bucket never reached the shelf.

/// Ten soap to pay for, and a bucket free.
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
          'product_id': 'soap',
          'description': 'Soap',
          'ordered_quantity': '10',
          'unit_price': '100',
        },
        {
          'id': 'po-line-2',
          'line_number': 2,
          'product_id': 'bucket',
          'description': 'Bucket',
          'ordered_quantity': '0',
          'free_quantity': '1',
          'unit_price': '0',
        },
      ],
    });

/// No receipts yet; records what the receipt sends.
class _Api extends ApiClient {
  _Api()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Json> sent = [];

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
  Future<GoodsReceiptRecord> createGoodsReceipt(Json body) async {
    sent.add(body);
    return GoodsReceiptRecord.fromJson({
      'id': 'grn-1',
      'grn_number': 'GRN-1',
      'purchase_order_id': 'po-1',
      'status': 'DRAFT',
      'lines': const [],
    });
  }
}

void main() {
  testWidgets('a free-only line starts at its free goods and is saved', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(1600, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final _Api api = _Api();
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
                Product.fromJson({'id': 'soap', 'code': 'S', 'name': 'Soap'}),
                Product.fromJson(
                    {'id': 'bucket', 'code': 'B', 'name': 'Bucket'}),
              ],
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('goods-receipt-order')));
    await tester.pumpAndSettle();
    await tester.tap(find.textContaining('PO-2026-000001').last);
    await tester.pumpAndSettle();

    expect(
      tester
          .widget<TextFormField>(
            find.byKey(const ValueKey<String>('goods-receipt-free-po-1-1')),
          )
          .initialValue,
      '1',
    );

    await tester.tap(find.byKey(const ValueKey('goods-receipt-save')));
    await tester.pumpAndSettle();

    expect(api.sent, hasLength(1));
    final List<dynamic> lines = api.sent.single['lines'] as List<dynamic>;
    expect(lines, hasLength(2), reason: 'the bucket line is not dropped');
    final Map<dynamic, dynamic> bucket = lines.firstWhere(
      (line) => (line as Map)['purchase_order_line_id'] == 'po-line-2',
    ) as Map<dynamic, dynamic>;
    expect(bucket['free_quantity'], '1');
  });
}
