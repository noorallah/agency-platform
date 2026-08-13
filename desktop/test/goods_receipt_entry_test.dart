import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/goods_receipt.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/models/purchase.dart';
import 'package:agency_desktop/ui/goods_receipts/goods_receipt_editor_dialog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// A purchase order for ten units of one product, four of them already
/// received on an earlier completed receipt.
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
          'unit_price': '25',
          'purchase_uom_id': 'uom-box',
          'inventory_uom_id': 'uom-strip',
          'batch_required': true,
        },
      ],
    });

class _ReceiptApi extends ApiClient {
  _ReceiptApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  Json? sent;

  @override
  Future<PagedResult<GoodsReceiptRecord>> goodsReceipts({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    Map<String, String> filters = const {},
  }) async =>
      PagedResult<GoodsReceiptRecord>(
        items: [
          GoodsReceiptRecord.fromJson({
            'id': 'grn-1',
            'grn_number': 'GRN-1',
            'status': 'COMPLETED',
            'lines': [
              {
                'id': 'grn-line-1',
                'purchase_order_line_id': 'po-line-1',
                'current_receipt_quantity': '4',
              },
            ],
          }),
        ],
        total: 1,
      );

  @override
  Future<GoodsReceiptRecord> createGoodsReceipt(Json data) async {
    sent = data;
    return GoodsReceiptRecord.fromJson({
      'id': 'grn-2',
      'grn_number': 'GRN-2',
      'status': 'DRAFT',
    });
  }
}

Future<void> _openEditor(WidgetTester tester, _ReceiptApi api) async {
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: GoodsReceiptEditorDialog(
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
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('a receipt line defaults to what is still outstanding', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(1600, 1000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final _ReceiptApi api = _ReceiptApi();
    await _openEditor(tester, api);

    await tester.tap(find.byType(DropdownButtonFormField<String>).first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('PO-2026-000001 • 2026-08-01').last);
    await tester.pumpAndSettle();

    // Ten ordered, four already received, so six is what is left to receive.
    // Defaulting to the full ten would be refused on save for over-receipt,
    // which reads as a bug to the person typing it.
    expect(find.text('Ordered 10 · already received 4'), findsOneWidget);
    final TextFormField accepted = tester.widget<TextFormField>(
      find.ancestor(
        of: find.text('Accepted *'),
        matching: find.byType(TextFormField),
      ),
    );
    expect(accepted.initialValue, '6');
  });

  testWidgets('the batch number typed off the carton reaches the payload', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(1600, 1000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final _ReceiptApi api = _ReceiptApi();
    await _openEditor(tester, api);

    await tester.tap(find.byType(DropdownButtonFormField<String>).first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('PO-2026-000001 • 2026-08-01').last);
    await tester.pumpAndSettle();

    await tester.enterText(
      find.ancestor(
        of: find.text('Batch Number *'),
        matching: find.byType(TextFormField),
      ),
      'B-2026-07',
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('Save Receipt'));
    await tester.pumpAndSettle();

    expect(api.sent, isNotNull);
    final Json payload = api.sent!;
    expect(payload['purchase_order_id'], 'po-1');
    final List<dynamic> lines = payload['lines'] as List<dynamic>;
    expect(lines, hasLength(1));
    final Json line = lines.first as Json;
    expect(line['purchase_order_line_id'], 'po-line-1');
    expect(line['line_number'], 1);
    expect(line['current_receipt_quantity'], '6');
    expect(
      line['batch_number'],
      'B-2026-07',
      reason: 'the batch is what makes the receipt traceable',
    );
    expect(line['warehouse_id'], 'wh-1');
  });

  testWidgets('a product that needs a batch cannot be saved without one', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(1600, 1000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final _ReceiptApi api = _ReceiptApi();
    await _openEditor(tester, api);

    await tester.tap(find.byType(DropdownButtonFormField<String>).first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('PO-2026-000001 • 2026-08-01').last);
    await tester.pumpAndSettle();

    await tester.tap(find.text('Save Receipt'));
    await tester.pumpAndSettle();

    // The server refuses this too, and its refusal is the authority. Saying so
    // before the round trip saves the storeman retyping the whole receipt.
    expect(
      find.textContaining('must be received with a batch number'),
      findsOneWidget,
    );
    expect(api.sent, isNull);
  });
}
