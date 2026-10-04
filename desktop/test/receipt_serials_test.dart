import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/batch_serial.dart';
import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/document_preview.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/goods_receipt.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/models/purchase.dart';
import 'package:agency_desktop/ui/goods_receipts/goods_receipt_editor_dialog.dart';
import 'package:agency_desktop/ui/goods_receipts/goods_receipt_view_dialog.dart';
import 'package:agency_desktop/ui/purchase_returns/purchase_return_editor_dialog.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// An order for two products: a phone that carries a serial per unit (3 of
/// them) and a charger that does not.
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
          'product_id': 'prod-phone',
          'description': 'Phone',
          'ordered_quantity': '3',
          'unit_price': '100',
        },
        {
          'id': 'po-line-2',
          'line_number': 2,
          'product_id': 'prod-charger',
          'description': 'Charger',
          'ordered_quantity': '2',
          'unit_price': '10',
        },
      ],
    });

final List<Product> _products = [
  Product.fromJson({
    'id': 'prod-phone',
    'code': 'PH',
    'name': 'Phone',
    'track_serial': true,
  }),
  Product.fromJson({'id': 'prod-charger', 'code': 'CH', 'name': 'Charger'}),
];

class _Api extends ApiClient {
  _Api()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  Json? sent;
  final List<Json> expanded = <Json>[];
  final List<String> trailed = <String>[];

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
    });
  }

  @override
  Future<List<String>> expandSerials({
    required String prefix,
    required int start,
    required int count,
    int width = 0,
  }) async {
    expanded.add({
      'prefix': prefix,
      'start': start,
      'count': count,
      'width': width,
    });
    return [
      for (int i = 0; i < count; i++)
        '$prefix${(start + i).toString().padLeft(width, '0')}',
    ];
  }

  @override
  Future<PagedResult<SerialRecord>> serials({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    SerialQuery filters = const SerialQuery(),
  }) async =>
      PagedResult<SerialRecord>(
        items: [
          SerialRecord.fromJson({
            'id': 'serial-1',
            'serial_number': search,
            'product_id': 'prod-phone',
          }),
        ],
        total: 1,
      );

  @override
  Future<List<SerialTrailEvent>> serialTrail(String serialId) async {
    trailed.add(serialId);
    return [
      SerialTrailEvent.fromJson({
        'document_type': 'GOODS_RECEIPT',
        'document_number': 'GRN-9',
        'document_date': '2026-08-02',
        'party_name': 'Acme Supplies',
        'line_number': 1,
      }),
    ];
  }

  // The return editor.
  Json? sentReturn;

  @override
  Future<Json> documentPage(
    String resource, {
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    Map<String, String> additionalQuery = const {},
  }) async =>
      {'data': const <Json>[]};

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
  Future<PurchaseReturnPreviewRecord> previewPurchaseReturn(Json data) async =>
      PurchaseReturnPreviewRecord.fromJson({
        'purchase_return': {
          'subtotal': '0',
          'tax_total': '0',
          'grand_total': '0',
          'lines': <Json>[],
        },
        'interstate': false,
        'lines': <Json>[],
      });

  @override
  Future<Json> create(String resource, Json body) async {
    sentReturn = body;
    return {
      'data': {'id': 'pr-1', 'return_number': 'PR-1', 'status': 'DRAFT'}
    };
  }
}

Future<void> _size(WidgetTester tester, Size size) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
}

Future<void> _openReceipt(WidgetTester tester, _Api api) async {
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: Phase2Scope(
          child: GoodsReceiptEditorDialog(
            api: api,
            purchaseOrders: [_order()],
            warehouses: [
              WarehouseRecord.fromJson(
                  {'id': 'wh-1', 'code': 'MAIN', 'name': 'Main'}),
            ],
            products: _products,
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
}

GoodsReceiptRecord _receiptRecord() => GoodsReceiptRecord.fromJson({
      'id': 'grn-1',
      'grn_number': 'GRN-1',
      'receipt_date': '2026-08-10',
      'status': 'COMPLETED',
      'lines': [
        {
          'id': 'grn-line-1',
          'line_number': 1,
          'product_id': 'prod-phone',
          'description': 'Phone',
          'accepted_quantity': '3',
          'unit_price': '100',
          'serial_tracked': true,
          'serial_numbers': ['A1', 'A2', 'A3'],
        },
      ],
    });

Future<void> _openReturn(WidgetTester tester, _Api api) async {
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: Phase2Scope(
          child: PurchaseReturnEditorDialog(
            api: api,
            receipts: [_receiptRecord()],
            products: _products,
          ),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
  await tester.tap(find.byKey(const ValueKey('purchase-return-receipt')));
  await tester.pumpAndSettle();
  await tester.tap(find.textContaining('GRN-1').last);
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('the serials cell shows only for a tracked line', (tester) async {
    await _size(tester, const Size(1600, 1000));
    await _openReceipt(tester, _Api());

    expect(find.byKey(const ValueKey('goods-receipt-serials-0')), findsOneWidget);
    expect(find.byKey(const ValueKey('goods-receipt-serials-1')), findsNothing);
    expect(find.text('0 of 3'), findsOneWidget);
  });

  testWidgets('the dialog counts and flags a serial entered twice', (
    tester,
  ) async {
    await _size(tester, const Size(1600, 1000));
    await _openReceipt(tester, _Api());

    await tester.tap(find.byKey(const ValueKey('goods-receipt-serials-0')));
    await tester.pumpAndSettle();
    await tester.enterText(
        find.byKey(const ValueKey('serial-text')), 'A1\na2\nA2\n\nA3');
    await tester.pumpAndSettle();

    expect(find.text('4 of 3 entered'), findsOneWidget);
    expect(find.textContaining('Entered twice: A2'), findsOneWidget);
  });

  testWidgets('a range fill calls expand and appends', (tester) async {
    await _size(tester, const Size(1600, 1000));
    final _Api api = _Api();
    await _openReceipt(tester, api);

    await tester.tap(find.byKey(const ValueKey('goods-receipt-serials-0')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const ValueKey('serial-text')), 'X1');
    await tester.enterText(find.byKey(const ValueKey('serial-prefix')), 'SN');
    await tester.enterText(find.byKey(const ValueKey('serial-start')), '8');
    await tester.enterText(find.byKey(const ValueKey('serial-range-count')), '2');
    await tester.enterText(find.byKey(const ValueKey('serial-width')), '3');
    await tester.tap(find.byKey(const ValueKey('serial-fill')));
    await tester.pumpAndSettle();

    expect(api.expanded.single,
        {'prefix': 'SN', 'start': 8, 'count': 2, 'width': 3});
    expect(find.text('3 of 3 entered'), findsOneWidget);
    final TextField box =
        tester.widget<TextField>(find.byKey(const ValueKey('serial-text')));
    expect(box.controller!.text, 'X1\nSN008\nSN009');
  });

  testWidgets('save sends serial_numbers for the tracked line only', (
    tester,
  ) async {
    await _size(tester, const Size(1600, 1000));
    final _Api api = _Api();
    await _openReceipt(tester, api);

    await tester.tap(find.byKey(const ValueKey('goods-receipt-serials-0')));
    await tester.pumpAndSettle();
    await tester.enterText(
        find.byKey(const ValueKey('serial-text')), 'A1\nA2\nA3');
    await tester.tap(find.byKey(const ValueKey('serial-ok')));
    await tester.pumpAndSettle();
    expect(find.text('3 of 3'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('goods-receipt-save')));
    await tester.pumpAndSettle();

    final List<dynamic> lines = api.sent!['lines'] as List<dynamic>;
    expect((lines[0] as Json)['serial_numbers'], ['A1', 'A2', 'A3']);
    expect((lines[1] as Json).containsKey('serial_numbers'), isFalse);
  });

  testWidgets('an untouched tracked line sends no serial_numbers', (
    tester,
  ) async {
    await _size(tester, const Size(1600, 1000));
    final _Api api = _Api();
    await _openReceipt(tester, api);

    await tester.tap(find.byKey(const ValueKey('goods-receipt-save')));
    await tester.pumpAndSettle();

    final List<dynamic> lines = api.sent!['lines'] as List<dynamic>;
    expect((lines[0] as Json).containsKey('serial_numbers'), isFalse);
  });

  testWidgets('the return dialog sends the serials going back', (tester) async {
    await _size(tester, const Size(1600, 1000));
    final _Api api = _Api();
    await _openReturn(tester, api);

    await tester.tap(find.byKey(const ValueKey('purchase-return-serials-0')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const ValueKey('serial-text')), 'A2');
    await tester.tap(find.byKey(const ValueKey('serial-ok')));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const ValueKey('purchase-return-save')));
    await tester.pumpAndSettle();

    final List<dynamic> lines = api.sentReturn!['lines'] as List<dynamic>;
    expect((lines.first as Json)['serial_numbers'], ['A2']);
  });

  testWidgets('a completed receipt shows a serial trail on tap', (
    tester,
  ) async {
    await _size(tester, const Size(1600, 1000));
    final _Api api = _Api();
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: GoodsReceiptViewDialog(
            receipt: _receiptRecord(),
            history: const [],
            api: api,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('view-serials-1')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('serial-row-A2')));
    await tester.pumpAndSettle();

    expect(api.trailed, ['serial-1']);
    expect(find.textContaining('GRN-9'), findsOneWidget);
  });

  for (final Size size in const [Size(1366, 768), Size(800, 600)]) {
    testWidgets('the serial dialog does not overflow at $size', (
      tester,
    ) async {
      await _size(tester, size);
      await _openReceipt(tester, _Api());
      // The line table scrolls sideways when the window is narrow.
      await tester.ensureVisible(
          find.byKey(const ValueKey('goods-receipt-serials-0')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('goods-receipt-serials-0')));
      await tester.pumpAndSettle();
      await tester.enterText(
          find.byKey(const ValueKey('serial-text')), 'A1\nA1\nA2\nA3\nA4');
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
      expect(find.byKey(const ValueKey('serial-ok')), findsOneWidget);
    });
  }
}
