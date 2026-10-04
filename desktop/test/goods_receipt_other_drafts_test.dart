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

/// D-BUY-23: a draft receipt reserves nothing and Complete refuses more than
/// was ordered, so a new receipt names the other drafts already holding its
/// lines and starts at what they leave -- rather than offering the whole
/// order again and letting two people each draft all of it.

/// Twenty ordered on one line.
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
          'ordered_quantity': '20',
          'unit_price': '25',
        },
      ],
    });

GoodsReceiptRecord _receipt(String id, String status, String quantity) =>
    GoodsReceiptRecord.fromJson({
      'id': id,
      'grn_number': id.toUpperCase(),
      'purchase_order_id': 'po-1',
      'status': status,
      'lines': [
        {
          'id': '$id-line',
          'purchase_order_line_id': 'po-line-1',
          'current_receipt_quantity': quantity,
        },
      ],
    });

/// Four received on a completed receipt; drafts of 4 and 6 open.
class _Api extends ApiClient {
  _Api({this.drafts})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<GoodsReceiptRecord>? drafts;
  final List<Map<String, String>> asked = [];

  @override
  Future<PagedResult<GoodsReceiptRecord>> goodsReceipts({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    Map<String, String> filters = const {},
  }) async {
    asked.add(filters);
    final List<GoodsReceiptRecord> rows = filters['status'] == 'DRAFT'
        ? drafts ??
            [_receipt('grn-7', 'DRAFT', '4'), _receipt('grn-8', 'DRAFT', '6')]
        : [_receipt('grn-1', 'COMPLETED', '4')];
    return PagedResult<GoodsReceiptRecord>(items: rows, total: rows.length);
  }
}

Future<void> _open(
  WidgetTester tester,
  _Api api, {
  GoodsReceiptRecord? existing,
}) async {
  tester.view.physicalSize = const Size(1600, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: Phase2Scope(
          child: GoodsReceiptEditorDialog(
            api: api,
            existing: existing,
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
    ),
  );
  await tester.pumpAndSettle();
  if (existing == null) {
    await tester.tap(find.byKey(const ValueKey('goods-receipt-order')));
    await tester.pumpAndSettle();
    await tester.tap(find.textContaining('PO-2026-000001').last);
    await tester.pumpAndSettle();
  }
}

String? _accepted(WidgetTester tester) => tester
    .widget<TextFormField>(
      find.byKey(const ValueKey<String>('goods-receipt-accepted-po-1-0')),
    )
    .initialValue;

void main() {
  testWidgets('a new receipt names the drafts holding its line and starts '
      'at what they leave', (tester) async {
    final _Api api = _Api();
    await _open(tester, api);
    expect(tester.takeException(), isNull);

    // The drafts were asked for once, by order and status, of the server.
    expect(
      api.asked,
      contains(equals({'purchase_order_id': 'po-1', 'status': 'DRAFT'})),
    );
    expect(
      find.text('other draft receipts hold 10 of this line (GRN-7, GRN-8)'),
      findsOneWidget,
    );
    // Twenty ordered, four in, ten held by drafts: six is what is left.
    expect(_accepted(tester), '6');
    expect(find.text('Held by other drafts'), findsOneWidget);
  });

  testWidgets('Due and the red box allow for the other drafts', (
    tester,
  ) async {
    // Seen in purchasing round 2: the note named the draft while Due said
    // the whole line and only more than that turned red.
    final _Api api = _Api();
    await _open(tester, api);
    final Finder box =
        find.byKey(const ValueKey<String>('goods-receipt-accepted-po-1-0'));
    Color? colour() => tester
        .widget<EditableText>(
          find.descendant(of: box, matching: find.byType(EditableText)),
        )
        .style
        .color;
    final Color error =
        Theme.of(tester.element(box)).colorScheme.error;

    // Sixteen still due on the order, ten of it held by drafts.
    expect(find.text('16'), findsNothing);
    expect(colour(), isNot(error));
    await tester.enterText(box, '7');
    await tester.pump();
    expect(colour(), error);
    expect(find.text('Over what is due by'), findsOneWidget);
  });

  testWidgets('drafts holding more than is due start the line at zero', (
    tester,
  ) async {
    final _Api api = _Api(drafts: [_receipt('grn-7', 'DRAFT', '18')]);
    await _open(tester, api);

    expect(
      find.text('another draft receipt holds 18 of this line (GRN-7)'),
      findsOneWidget,
    );
    expect(_accepted(tester), '0');
  });

  testWidgets('a draft being corrected is not counted as another', (
    tester,
  ) async {
    final _Api api = _Api();
    await _open(tester, api, existing: _receipt('grn-7', 'DRAFT', '4'));

    expect(
      find.text('another draft receipt holds 6 of this line (GRN-8)'),
      findsOneWidget,
    );
    // Its own saved quantity stands.
    expect(_accepted(tester), '4');
  });

  testWidgets('no other drafts, no note', (tester) async {
    final _Api api = _Api(drafts: const []);
    await _open(tester, api);

    expect(find.textContaining('of this line'), findsNothing);
    expect(_accepted(tester), '16');
  });
}
