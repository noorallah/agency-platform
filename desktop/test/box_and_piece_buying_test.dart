// L5 step 10, buying side (BOX_AND_PIECE_LINE_DESIGN 4): the purchase
// order, the goods receipt, the supplier's bill and the purchase return
// typed as boxes and loose pieces.
//
// A new document follows its party where the firm's buying switch is on --
// the order and a bill of products the supplier's mark, a receipt, a bill
// of receipts and a return the document they continue -- and a saved one
// reopens as it was saved. The quantity sent stays one figure in pieces,
// beside the pack the two cells were added up at; read-only figures read
// "3 x 12 + 5"; an item with no pack has its box cells closed. The shared
// cells themselves are checked once, in box_and_piece_entry_test.dart.

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/batch_serial.dart';
import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/document_preview.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/goods_receipt.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/models/purchase.dart';
import 'package:agency_desktop/models/vendor.dart';
import 'package:agency_desktop/ui/goods_receipts/goods_receipt_editor_dialog.dart';
import 'package:agency_desktop/ui/purchase_invoices/purchase_invoice_editor_dialog.dart';
import 'package:agency_desktop/ui/purchase_returns/purchase_return_editor_dialog.dart';
import 'package:agency_desktop/ui/purchases/purchase_management_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// One API for all four editors: the firm's buying switch, and every save
/// and pricing kept to be read back.
class _Api extends ApiClient {
  _Api({this.switchOn = true})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  /// The firm's "Type quantities as boxes and pieces" for buying.
  final bool switchOn;
  final Map<String, Json?> bodies = <String, Json?>{};
  int settingsReads = 0;
  Json? sent;

  @override
  Future<Json> request(
    String method,
    String path, {
    Json? body,
    Map<String, String>? query,
    bool authenticated = true,
    bool retrying = false,
    int? expectedVersion,
  }) async {
    final String call = '$method $path';
    bodies[call] = body;
    if (call == 'GET /api/v1/purchases/workflow-settings') {
      settingsReads++;
      return {
        'data': {'box_and_piece_entry': switchOn},
      };
    }
    if (call == 'POST /api/v1/purchases' ||
        call == 'PUT /api/v1/purchases/po-1') {
      return {'data': _savedOrderJson()};
    }
    if (call == 'POST /api/v1/purchases/preview') {
      return {
        'data': {
          'order': {'id': '', 'status': 'DRAFT', 'lines': <Json>[]},
          'interstate': false,
          'lines': <Json>[],
        },
      };
    }
    return {'data': const <dynamic>[]};
  }

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
  Future<GoodsReceiptRecord> updateGoodsReceipt(
    String id,
    Json data, {
    int? expectedVersion,
  }) async {
    sent = data;
    return GoodsReceiptRecord.fromJson({
      'id': id,
      'grn_number': 'GRN-1',
      'status': 'DRAFT',
    });
  }

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

  final List<Json> previews = <Json>[];

  @override
  Future<PurchaseInvoicePreviewRecord> previewPurchaseInvoice(
    Json data, {
    String? replacing,
  }) async {
    previews.add(data);
    return PurchaseInvoicePreviewRecord.fromJson({
      'invoice': {'invoice_number': 'PI-9', 'lines': <Json>[]},
      'interstate': false,
      'lines': <Json>[],
    });
  }

  @override
  Future<Json> createPurchaseInvoice(Json body) async {
    sent = body;
    return {
      'data': {'id': 'pi-1', 'invoice_number': 'PI-1', 'status': 'DRAFT'}
    };
  }

  @override
  Future<PurchaseReturnPreviewRecord> previewPurchaseReturn(Json data) async {
    previews.add(data);
    return PurchaseReturnPreviewRecord.fromJson({
      'purchase_return': {'return_number': 'PR-9', 'lines': <Json>[]},
      'interstate': false,
      'lines': <Json>[],
    });
  }

  @override
  Future<Json> create(String resource, Json body) async {
    sent = body;
    return {
      'data': {'id': 'pr-1', 'return_number': 'PR-1', 'status': 'DRAFT'}
    };
  }
}

/// Twelve pieces to the box it is bought in; counted in pieces.
Product _boxed() => Product.fromJson({
      'id': 'prod-1',
      'code': 'SKU-1',
      'name': 'Cough Syrup',
      'unit': 'PCS',
      'purchase_price': '10',
      'buying_pack_size': '12.0000',
      'buying_pack_unit_code': 'BOX',
      'status': 'ACTIVE',
    });

/// Bought and stocked loose: no pack at all.
Product _loose() => Product.fromJson({
      'id': 'prod-2',
      'code': 'SKU-2',
      'name': 'Loose Cotton',
      'unit': 'PCS',
      'purchase_price': '55',
      'status': 'ACTIVE',
    });

Vendor _vendor({bool marked = true}) => Vendor.fromJson({
      'id': 'vendor-1',
      'code': 'V-001',
      'name': 'Medico Distributors',
      'display_name': 'Medico Distributors',
      'status': 'ACTIVE',
      'box_and_piece_entry': marked,
    });

Finder _keyed(String prefix) => find.byWidgetPredicate((widget) =>
    widget.key is ValueKey<String> &&
    (widget.key! as ValueKey<String>).value.startsWith(prefix));

String _cell(WidgetTester tester, String key) => tester
    .widget<EditableText>(find.descendant(
      of: find.byKey(ValueKey<String>(key)),
      matching: find.byType(EditableText),
    ))
    .controller
    .text;

Future<void> _type(WidgetTester tester, String key, String value) async {
  await tester.enterText(find.byKey(ValueKey<String>(key)), value);
  await tester.pump();
}

Future<void> _settle(WidgetTester tester) async {
  await tester.pumpAndSettle();
  await tester.pump(const Duration(milliseconds: 400));
  await tester.pumpAndSettle();
}

Future<void> _choose(WidgetTester tester, Finder box, String text) async {
  await tester.tap(box);
  await tester.pumpAndSettle();
  await tester.tap(find.textContaining(text).last);
  await tester.pumpAndSettle();
}

void _size(WidgetTester tester, Size size) {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
}

// ---- the purchase order ---------------------------------------------------

Json _savedOrderJson({bool boxes = true, String pack = '12.0000'}) => {
      'id': 'po-1',
      'firm_id': 'firm-1',
      'branch_id': 'branch-1',
      'warehouse_id': 'warehouse-1',
      'vendor_id': 'vendor-1',
      'po_number': 'PO-0001',
      'purchase_date': '2026-10-01',
      'status': 'DRAFT',
      'box_and_piece_entry': boxes,
      'lines': [
        {
          'id': 'line-1',
          'line_number': 1,
          'product_id': 'prod-1',
          'ordered_quantity': '41.0000',
          'free_quantity': null,
          'unit_price': '10',
          'purchase_uom_id': 'uom-pcs',
          'inventory_uom_id': 'uom-pcs',
          'pack_size': pack,
        },
      ],
    };

Future<void> _pumpOrder(
  WidgetTester tester,
  _Api api, {
  PurchaseDialogMode mode = PurchaseDialogMode.create,
  PurchaseOrder? order,
  bool marked = true,
  Size size = const Size(1366, 768),
}) async {
  _size(tester, size);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Phase2Scope(
        child: PurchaseOrderEditorDialog(
          api: api,
          permissions: PermissionService(),
          mode: mode,
          order: order,
          vendors: <Vendor>[_vendor(marked: marked)],
          branches: <BranchRecord>[
            BranchRecord.fromJson(<String, dynamic>{
              'id': 'branch-1',
              'code': 'BR-001',
              'name': 'Main Branch',
              'status': 'ACTIVE',
              'is_default': true,
            }),
          ],
          warehouses: <WarehouseRecord>[
            WarehouseRecord.fromJson(<String, dynamic>{
              'id': 'warehouse-1',
              'branch_id': 'branch-1',
              'code': 'WH-001',
              'name': 'Main Warehouse',
              'status': 'ACTIVE',
              'is_default': true,
            }),
          ],
          products: <Product>[_boxed(), _loose()],
          buyers: const [],
          taxProfiles: const [],
          storageNodes: const [],
          canSubmit: true,
          canApprove: false,
        ),
      ),
    ),
  ));
  await _settle(tester);
}

Future<void> _orderSupplierAndItem(
  WidgetTester tester, {
  String item = 'Cough Syrup',
}) async {
  await _choose(
      tester, find.byKey(const ValueKey('purchase-order-vendor')), 'Medico');
  await _choose(tester, _keyed('purchase-order-line-product-').first, item);
}

// ---- the goods receipt ----------------------------------------------------

PurchaseOrder _receivableOrder({
  bool boxes = true,
  String unit = 'uom-pcs',
}) =>
    PurchaseOrder.fromJson({
      'id': 'po-1',
      'po_number': 'PO-2026-000001',
      'purchase_date': '2026-10-01',
      'vendor_id': 'vendor-1',
      'warehouse_id': 'wh-1',
      'status': 'APPROVED',
      'box_and_piece_entry': boxes,
      'lines': [
        {
          'id': 'po-line-1',
          'line_number': 1,
          'product_id': 'prod-1',
          'ordered_quantity': '41',
          'unit_price': '10',
          'purchase_uom_id': unit,
          'inventory_uom_id': 'uom-pcs',
          'pack_size': '12.0000',
        },
      ],
    });

Future<void> _pumpReceipt(
  WidgetTester tester,
  _Api api, {
  PurchaseOrder? order,
  GoodsReceiptRecord? existing,
  Size size = const Size(1600, 900),
}) async {
  _size(tester, size);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Phase2Scope(
        child: GoodsReceiptEditorDialog(
          api: api,
          purchaseOrders: [order ?? _receivableOrder()],
          warehouses: [
            WarehouseRecord.fromJson(
                {'id': 'wh-1', 'code': 'MAIN', 'name': 'Main Warehouse'}),
          ],
          products: [_boxed()],
          existing: existing,
        ),
      ),
    ),
  ));
  await _settle(tester);
}

// ---- the bill and the return ----------------------------------------------

GoodsReceiptRecord _completedReceipt({
  bool boxes = true,
  String pack = '12.0000',
  String unit = 'uom-pcs',
}) =>
    GoodsReceiptRecord.fromJson({
      'id': 'grn-1',
      'grn_number': 'GRN-2026-000001',
      'receipt_date': '2026-10-02',
      'status': 'COMPLETED',
      'vendor_id': 'vendor-1',
      'vendor_name': 'Medico Distributors',
      'branch_id': 'branch-1',
      'box_and_piece_entry': boxes,
      'lines': [
        {
          'id': 'grn-line-1',
          'line_number': 1,
          'product_id': 'prod-1',
          'description': 'Cough Syrup',
          'accepted_quantity': '41',
          'free_quantity': '0',
          'unit_price': '10',
          'purchase_uom_id': unit,
          'inventory_uom_id': 'uom-pcs',
          'warehouse_id': 'wh-1',
          'pack_size': pack,
        },
      ],
    });

Future<void> _pumpBill(
  WidgetTester tester,
  _Api api, {
  PurchaseWorkflowSettings stages = const PurchaseWorkflowSettings(
    purchaseOrderStage: true,
    goodsReceiptStage: true,
    isConfigured: true,
    boxAndPieceEntry: true,
  ),
  List<GoodsReceiptRecord> receipts = const [],
  bool marked = true,
  Size size = const Size(1600, 900),
}) async {
  _size(tester, size);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Phase2Scope(
        child: PurchaseInvoiceEditorDialog(
          api: api,
          receipts: receipts,
          products: [_boxed(), _loose()],
          stages: stages,
          vendors: [_vendor(marked: marked)],
        ),
      ),
    ),
  ));
  await _settle(tester);
}

const PurchaseWorkflowSettings _billOfProducts = PurchaseWorkflowSettings(
  purchaseOrderStage: false,
  goodsReceiptStage: false,
  isConfigured: true,
  boxAndPieceEntry: true,
);

Future<void> _pumpReturn(
  WidgetTester tester,
  _Api api, {
  GoodsReceiptRecord? receipt,
  Size size = const Size(1600, 900),
}) async {
  _size(tester, size);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Phase2Scope(
        child: PurchaseReturnEditorDialog(
          api: api,
          receipts: [receipt ?? _completedReceipt()],
          products: [_boxed()],
        ),
      ),
    ),
  ));
  await _settle(tester);
  await _choose(tester, find.byKey(const ValueKey('purchase-return-receipt')),
      'GRN-2026-000001');
  await _settle(tester);
}

void main() {
  group('the purchase order', () {
    testWidgets(
        'opens in boxes for a marked supplier and sends 3 boxes + 5 pcs as '
        '41 at a pack of 12', (tester) async {
      final _Api api = _Api();
      await _pumpOrder(tester, api);
      expect(
          find.byKey(const ValueKey('purchase-order-box-and-pieces')),
          findsOneWidget);
      await _orderSupplierAndItem(tester);
      expect(find.byKey(const ValueKey('purchase-order-line-0-box')),
          findsOneWidget);
      expect(find.text('Qty'), findsNothing);

      await _type(tester, 'purchase-order-line-0-box', '3');
      await _type(tester, 'purchase-order-line-0-pcs', '5');
      await _settle(tester);
      expect(
          find.text('Box of 12. 3 boxes + 5 pcs = 41 pcs.'), findsOneWidget);
      await tester.tap(find.byKey(const ValueKey('purchase-order-save')));
      await _settle(tester);

      final Json sent = api.bodies['POST /api/v1/purchases']!;
      expect(sent['box_and_piece_entry'], isTrue);
      final Json line = (sent['lines'] as List<dynamic>).single as Json;
      expect(line['ordered_quantity'], '41');
      expect(line['pack_size'], '12.0000');
      // Counted in pieces: no buying unit is named.
      expect(line.containsKey('purchase_uom_id'), isFalse);
      // Blank free says nothing.
      expect(line['free_quantity'], isNull);
      expect(tester.takeException(), isNull);
    });

    testWidgets('an unmarked supplier opens in pieces; the toggle changes it',
        (tester) async {
      final _Api api = _Api();
      await _pumpOrder(tester, api, marked: false);
      await _orderSupplierAndItem(tester);
      expect(find.text('Qty'), findsOneWidget);
      expect(find.byKey(const ValueKey('purchase-order-line-0-box')),
          findsNothing);
      await tester.enterText(_keyed('purchase-order-qty-').first, '30');
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const ValueKey('box-piece-toggle-on')));
      await tester.pumpAndSettle();
      // The same 30, shown as two cells.
      expect(_cell(tester, 'purchase-order-line-0-box'), '2');
      expect(_cell(tester, 'purchase-order-line-0-pcs'), '6');
      await tester.tap(find.byKey(const ValueKey('purchase-order-save')));
      await _settle(tester);
      final Json line = ((api.bodies['POST /api/v1/purchases']!['lines']
              as List<dynamic>)
          .single as Json);
      expect(line['ordered_quantity'], '30');
      expect(line['pack_size'], '12.0000');
    });

    testWidgets('with the switch off there is no toggle and nothing is sent',
        (tester) async {
      final _Api api = _Api(switchOn: false);
      await _pumpOrder(tester, api);
      await _orderSupplierAndItem(tester);
      expect(find.byKey(const ValueKey('purchase-order-box-and-pieces')),
          findsNothing);
      await tester.enterText(_keyed('purchase-order-qty-').first, '5');
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('purchase-order-save')));
      await _settle(tester);
      final Json sent = api.bodies['POST /api/v1/purchases']!;
      expect(sent.containsKey('box_and_piece_entry'), isFalse);
      final Json line = (sent['lines'] as List<dynamic>).single as Json;
      expect(line.containsKey('pack_size'), isFalse);
    });

    testWidgets('a saved order reopens as it was saved, with no settings read',
        (tester) async {
      final _Api api = _Api(switchOn: false);
      await _pumpOrder(
        tester,
        api,
        mode: PurchaseDialogMode.edit,
        order: PurchaseOrder.fromJson(_savedOrderJson()),
        marked: false,
      );
      expect(api.settingsReads, 0);
      expect(_cell(tester, 'purchase-order-line-0-box'), '3');
      expect(_cell(tester, 'purchase-order-line-0-pcs'), '5');
    });

    testWidgets('an item with no pack has its box cells closed',
        (tester) async {
      final _Api api = _Api();
      await _pumpOrder(tester, api);
      await _orderSupplierAndItem(tester, item: 'Loose Cotton');
      expect(find.byKey(const ValueKey('purchase-order-line-0-box-closed')),
          findsOneWidget);
      expect(
          find.byKey(const ValueKey('purchase-order-line-0-free-box-closed')),
          findsOneWidget);
      await _type(tester, 'purchase-order-line-0-pcs', '7');
      await tester.tap(find.byKey(const ValueKey('purchase-order-save')));
      await _settle(tester);
      final Json line = ((api.bodies['POST /api/v1/purchases']!['lines']
              as List<dynamic>)
          .single as Json);
      expect(line['ordered_quantity'], '7');
      expect(line.containsKey('pack_size'), isFalse);
    });

    testWidgets('fits 800x600 in boxes', (tester) async {
      final _Api api = _Api();
      await _pumpOrder(
        tester,
        api,
        mode: PurchaseDialogMode.edit,
        order: PurchaseOrder.fromJson(_savedOrderJson()),
        size: const Size(800, 600),
      );
      expect(find.byKey(const ValueKey('purchase-order-line-0-box')),
          findsOneWidget);
      expect(tester.takeException(), isNull);
    });
  });

  group('the goods receipt', () {
    Future<void> chooseOrder(WidgetTester tester) async {
      await _choose(tester, find.byKey(const ValueKey('goods-receipt-order')),
          'PO-2026-000001');
      await _settle(tester);
    }

    testWidgets(
        'follows an order typed in boxes: the figures read 3 x 12 + 5 and '
        'Accepted is two boxes', (tester) async {
      final _Api api = _Api();
      await _pumpReceipt(tester, api);
      await chooseOrder(tester);
      expect(find.byKey(const ValueKey('goods-receipt-box-and-pieces')),
          findsOneWidget);
      final Text ordered = tester
          .widget<Text>(find.byKey(const ValueKey('goods-receipt-ordered-0')));
      expect(ordered.data, '3 x 12 + 5');
      final Text due =
          tester.widget<Text>(find.byKey(const ValueKey('goods-receipt-due-0')));
      expect(due.data, '3 x 12 + 5');
      expect(_cell(tester, 'goods-receipt-line-0-box'), '3');
      expect(_cell(tester, 'goods-receipt-line-0-pcs'), '5');

      await _type(tester, 'goods-receipt-line-0-box', '2');
      await _type(tester, 'goods-receipt-line-0-pcs', '0');
      await tester.tap(find.byKey(const ValueKey('goods-receipt-save')));
      await _settle(tester);
      final Json sent = api.sent!;
      expect(sent['box_and_piece_entry'], isTrue);
      final Json line = (sent['lines'] as List<dynamic>).single as Json;
      expect(line['current_receipt_quantity'], '24');
      expect(line['pack_size'], '12.0000');
      expect(tester.takeException(), isNull);
    });

    testWidgets('an order typed in pieces opens in pieces, the toggle offered',
        (tester) async {
      final _Api api = _Api();
      await _pumpReceipt(tester, api, order: _receivableOrder(boxes: false));
      await chooseOrder(tester);
      expect(find.byKey(const ValueKey('goods-receipt-box-and-pieces')),
          findsOneWidget);
      expect(find.byKey(const ValueKey('goods-receipt-line-0-box')),
          findsNothing);
      expect(
          tester
              .widget<Text>(
                  find.byKey(const ValueKey('goods-receipt-ordered-0')))
              .data,
          '41');
    });

    testWidgets('a saved receipt reopens as it was saved', (tester) async {
      final _Api api = _Api(switchOn: false);
      await _pumpReceipt(
        tester,
        api,
        order: _receivableOrder(boxes: false),
        existing: GoodsReceiptRecord.fromJson({
          'id': 'grn-1',
          'grn_number': 'GRN-1',
          'purchase_order_id': 'po-1',
          'status': 'DRAFT',
          'box_and_piece_entry': true,
          'lines': [
            {
              'id': 'grn-line-1',
              'purchase_order_line_id': 'po-line-1',
              'current_receipt_quantity': '26.0000',
              'free_quantity': '0',
            },
          ],
        }),
      );
      expect(api.settingsReads, 0);
      expect(_cell(tester, 'goods-receipt-line-0-box'), '2');
      expect(_cell(tester, 'goods-receipt-line-0-pcs'), '2');
    });

    testWidgets('an order line counted in boxes has its box cells closed',
        (tester) async {
      final _Api api = _Api();
      await _pumpReceipt(tester, api,
          order: _receivableOrder(unit: 'uom-box'));
      await chooseOrder(tester);
      expect(find.byKey(const ValueKey('goods-receipt-line-0-box-closed')),
          findsOneWidget);
      expect(_cell(tester, 'goods-receipt-line-0-pcs'), '41');
    });

    testWidgets('fits 800x600 in boxes', (tester) async {
      final _Api api = _Api();
      await _pumpReceipt(tester, api, size: const Size(800, 600));
      await chooseOrder(tester);
      expect(find.byKey(const ValueKey('goods-receipt-line-0-box')),
          findsOneWidget);
      expect(tester.takeException(), isNull);
    });
  });

  group("the supplier's bill", () {
    Future<void> chooseReceipt(WidgetTester tester) async {
      await _choose(
          tester,
          find.byKey(const ValueKey('purchase-invoice-receipt-supplier')),
          'Medico Distributors');
      await _settle(tester);
    }

    Future<void> save(WidgetTester tester) async {
      await tester.enterText(
        find.byKey(
            const ValueKey<String>('purchase-invoice-supplier-number-0')),
        'SUP-1',
      );
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('purchase-invoice-save')));
      await _settle(tester);
    }

    testWidgets(
        'a receipt typed in boxes is billed in boxes: Billing is two boxes '
        'and Received reads 3 x 12 + 5', (tester) async {
      final _Api api = _Api();
      await _pumpBill(tester, api, receipts: [_completedReceipt()]);
      await chooseReceipt(tester);
      expect(
          tester
              .widget<Text>(
                  find.byKey(const ValueKey('purchase-invoice-received-0')))
              .data,
          '3 x 12 + 5');
      expect(_cell(tester, 'purchase-invoice-line-0-box'), '3');
      expect(_cell(tester, 'purchase-invoice-line-0-pcs'), '5');
      // A bill line has no free cells.
      expect(find.byKey(const ValueKey('purchase-invoice-line-0-free-box')),
          findsNothing);

      await _type(tester, 'purchase-invoice-line-0-box', '2');
      await _type(tester, 'purchase-invoice-line-0-pcs', '0');
      await save(tester);
      final Json sent = api.sent!;
      expect(sent['box_and_piece_entry'], isTrue);
      final Json line = (sent['lines'] as List<dynamic>).single as Json;
      expect(line['current_invoice_quantity'], '24');
      expect(line['pack_size'], '12.0000');
      expect(tester.takeException(), isNull);
    });

    testWidgets(
        'a bill of products opens in boxes for a marked supplier and sends '
        '3 boxes + 5 pcs as 41', (tester) async {
      final _Api api = _Api();
      await _pumpBill(tester, api, stages: _billOfProducts);
      await _choose(tester,
          find.byKey(const ValueKey('purchase-invoice-vendor')), 'Medico');
      await _choose(
          tester,
          find.byKey(const ValueKey('purchase-invoice-direct-product-0')),
          'SKU-1');
      await _type(tester, 'purchase-invoice-direct-0-box', '3');
      await _type(tester, 'purchase-invoice-direct-0-pcs', '5');
      await save(tester);
      final Json line =
          (api.sent!['lines'] as List<dynamic>).single as Json;
      expect(line['current_invoice_quantity'], '41');
      expect(line['pack_size'], '12.0000');
      // Blank free says nothing: nothing is prefilled.
      expect(line.containsKey('free_quantity'), isFalse);
    });

    testWidgets('an unmarked supplier opens in pieces', (tester) async {
      final _Api api = _Api();
      await _pumpBill(tester, api, stages: _billOfProducts, marked: false);
      await _choose(tester,
          find.byKey(const ValueKey('purchase-invoice-vendor')), 'Medico');
      expect(find.byKey(const ValueKey('purchase-invoice-box-and-pieces')),
          findsOneWidget);
      expect(
          find.byKey(const ValueKey(
              'purchase-invoice-direct-quantity-direct-0')),
          findsOneWidget);
      expect(find.byKey(const ValueKey('purchase-invoice-direct-0-box')),
          findsNothing);
    });

    testWidgets('an item with no pack has its box cells closed',
        (tester) async {
      final _Api api = _Api();
      await _pumpBill(tester, api, stages: _billOfProducts);
      await _choose(tester,
          find.byKey(const ValueKey('purchase-invoice-vendor')), 'Medico');
      await _choose(
          tester,
          find.byKey(const ValueKey('purchase-invoice-direct-product-0')),
          'SKU-2');
      expect(
          find.byKey(const ValueKey('purchase-invoice-direct-0-box-closed')),
          findsOneWidget);
    });

    testWidgets('fits 800x600 in boxes', (tester) async {
      final _Api api = _Api();
      await _pumpBill(tester, api,
          receipts: [_completedReceipt()], size: const Size(800, 600));
      await chooseReceipt(tester);
      expect(find.byKey(const ValueKey('purchase-invoice-line-0-box')),
          findsOneWidget);
      expect(tester.takeException(), isNull);
    });
  });

  group('the purchase return', () {
    testWidgets(
        'a receipt typed in boxes goes back in boxes: Returning is two boxes, '
        'Received reads 3 x 12 + 5', (tester) async {
      final _Api api = _Api();
      await _pumpReturn(tester, api);
      expect(api.settingsReads, 1);
      expect(
          tester
              .widget<Text>(
                  find.byKey(const ValueKey('purchase-return-received-0')))
              .data,
          '3 x 12 + 5');
      expect(_cell(tester, 'purchase-return-line-0-box'), '3');
      expect(_cell(tester, 'purchase-return-line-0-pcs'), '5');

      await _type(tester, 'purchase-return-line-0-box', '1');
      await _type(tester, 'purchase-return-line-0-pcs', '0');
      await tester.tap(find.byKey(const ValueKey('purchase-return-save')));
      await _settle(tester);
      final Json sent = api.sent!;
      expect(sent['box_and_piece_entry'], isTrue);
      final Json line = (sent['lines'] as List<dynamic>).single as Json;
      expect(line['current_return_quantity'], '12');
      expect(line['pack_size'], '12.0000');
      expect(line.containsKey('free_quantity'), isFalse);
      expect(tester.takeException(), isNull);
    });

    testWidgets('a receipt typed in pieces opens in pieces, the toggle offered',
        (tester) async {
      final _Api api = _Api();
      await _pumpReturn(tester, api, receipt: _completedReceipt(boxes: false));
      expect(find.byKey(const ValueKey('purchase-return-box-and-pieces')),
          findsOneWidget);
      expect(find.byKey(const ValueKey('purchase-return-line-0-box')),
          findsNothing);
      await tester.tap(find.byKey(const ValueKey('box-piece-toggle-on')));
      await tester.pumpAndSettle();
      expect(_cell(tester, 'purchase-return-line-0-box'), '3');
    });

    testWidgets('an item with no pack has its box cells closed',
        (tester) async {
      final _Api api = _Api();
      await _pumpReturn(tester, api, receipt: _completedReceipt(pack: ''));
      expect(find.byKey(const ValueKey('purchase-return-line-0-box-closed')),
          findsOneWidget);
      expect(_cell(tester, 'purchase-return-line-0-pcs'), '41');
    });

    testWidgets('fits 800x600 in boxes', (tester) async {
      final _Api api = _Api();
      await _pumpReturn(tester, api, size: const Size(800, 600));
      expect(find.byKey(const ValueKey('purchase-return-line-0-box')),
          findsOneWidget);
      expect(tester.takeException(), isNull);
    });
  });
}
