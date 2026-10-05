// D-BUY-40 desktop: capital goods from the order line to the bill line.
//
// The order line carries the tick and sends it only when ticked. The receipt
// line starts at the order line's mark and sends `is_capital_goods` only when
// it differs, so silence keeps meaning "as ordered". A bill line made from a
// receipt line received as capital goods starts ticked, cannot be cleared,
// and needs its asset class before it saves.

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/document_preview.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/goods_receipt.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/models/purchase.dart';
import 'package:agency_desktop/models/vendor.dart';
import 'package:agency_desktop/ui/goods_receipts/goods_receipt_editor_dialog.dart';
import 'package:agency_desktop/ui/purchase_invoices/purchase_invoice_editor_dialog.dart';
import 'package:agency_desktop/ui/purchases/purchase_management_page.dart';
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

  final Map<String, Json?> bodies = <String, Json?>{};
  final List<String> calls = <String>[];
  Json? bill;

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
    calls.add(call);
    bodies[call] = body;
    switch (call) {
      case 'POST /api/v1/purchases':
        return {'data': _orderJson()};
      case 'PUT /api/v1/goods-receipts/gr-1':
        return {'data': _receiptJson()};
      case 'POST /api/v1/purchases/preview':
        return {
          'data': {
            'order': {
              'id': 'po-1',
              'po_number': 'PO-0001',
              'status': 'DRAFT',
              'lines': <Json>[],
            },
            'interstate': false,
            'lines': <Json>[],
          },
        };
      case 'GET /api/v1/fixed-assets/classes':
        return {
          'data': [
            {
              'id': 'c-1',
              'code': 'PLANT',
              'name': 'Plant and machinery',
              'depreciation_method': 'WDV',
              'rate_percent': '15.0000',
              'is_active': true,
              'version': 1,
            },
          ],
          'pagination': {'total_records': 1},
        };
    }
    if (path == '/api/v1/purchases/po-1') return {'data': _orderJson()};
    if (path == '/api/v1/goods-receipts') {
      return {
        'data': const <Json>[],
        'pagination': {'total_records': 0},
      };
    }
    return {'data': const <dynamic>[]};
  }

  @override
  Future<PurchaseInvoicePreviewRecord> previewPurchaseInvoice(Json data) async =>
      PurchaseInvoicePreviewRecord.fromJson({
        'invoice': {
          'invoice_number': 'PI-9',
          'subtotal': '1000.00',
          'tax_total': '0.00',
          'grand_total': '1000.00',
          'lines': <Json>[],
        },
        'interstate': false,
        'lines': <Json>[],
      });

  @override
  Future<Json> createPurchaseInvoice(Json body) async {
    bill = body;
    return {
      'data': {'id': 'pi-1', 'invoice_number': 'PI-1', 'status': 'DRAFT'}
    };
  }
}

Json _orderJson({bool capital = false}) => {
      'id': 'po-1',
      'firm_id': 'firm-1',
      'branch_id': 'branch-1',
      'warehouse_id': 'warehouse-1',
      'vendor_id': 'vendor-1',
      'po_number': 'PO-0001',
      'purchase_date': '2026-10-01',
      'status': 'APPROVED',
      'grand_total': '500.00',
      'lines': [
        {
          'id': 'pol-1',
          'line_number': 1,
          'product_id': 'product-1',
          'description': 'Packing machine',
          'ordered_quantity': '1',
          'unit_price': '100000',
          'discount_percent': '0',
          'net_amount': '100000.00',
          'is_capital_goods': capital,
        },
      ],
    };

Json _receiptJson({bool capital = false}) => {
      'id': 'gr-1',
      'receipt_number': 'GRN-0001',
      'purchase_order_id': 'po-1',
      'purchase_order_number': 'PO-0001',
      'receipt_date': '2026-09-01',
      'status': 'DRAFT',
      'version': 4,
      'lines': [
        {
          'id': 'grl-1',
          'line_number': 1,
          'purchase_order_line_id': 'pol-1',
          'purchase_order_line_number': 1,
          'product_id': 'product-1',
          'description': 'Packing machine',
          'ordered_quantity': '1',
          'previously_received_quantity': '0',
          'current_receipt_quantity': '1',
          'rejected_quantity': '0',
          'damaged_quantity': '0',
          'free_quantity': '0',
          'warehouse_id': 'warehouse-1',
          'unit_price': '100000',
          'is_capital_goods': capital,
        },
      ],
    };

Vendor _vendor() => Vendor.fromJson({
      'id': 'vendor-1',
      'firm_id': 'firm-1',
      'code': 'V001',
      'name': 'Acme Machines',
      'display_name': 'Acme Machines',
      'status': 'ACTIVE',
      'addresses': <Json>[],
      'contacts': <Json>[],
      'bank_accounts': <Json>[],
      'tax_details': <Json>[],
      'notes': <Json>[],
    });

Product _product() => Product.fromJson(<String, dynamic>{
      'id': 'product-1',
      'firm_id': 'firm-1',
      'code': 'MAC-1',
      'name': 'Packing machine',
      'unit': 'NOS',
      'purchase_price': '100000',
      'status': 'ACTIVE',
    });

void _size(WidgetTester tester) {
  tester.view.physicalSize = const Size(1600, 1000);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
}

Future<void> _tap(WidgetTester tester, String key) async {
  final Finder f = find.byKey(ValueKey<String>(key));
  await tester.ensureVisible(f);
  await tester.tap(f);
  await tester.pumpAndSettle();
}

bool _ticked(WidgetTester tester, String key) =>
    tester.widget<Checkbox>(find.byKey(ValueKey<String>(key))).value ?? false;

bool _enabled(WidgetTester tester, String key) =>
    tester.widget<Checkbox>(find.byKey(ValueKey<String>(key))).onChanged !=
    null;

// The order editor ------------------------------------------------------

Future<void> _pumpOrder(
  WidgetTester tester,
  _Api api, {
  PurchaseDialogMode mode = PurchaseDialogMode.create,
  PurchaseOrder? order,
}) async {
  _size(tester);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Phase2Scope(
        child: PurchaseOrderEditorDialog(
          api: api,
          permissions: PermissionService(),
          mode: mode,
          order: order,
          vendors: <Vendor>[_vendor()],
          branches: <BranchRecord>[
            BranchRecord.fromJson(<String, dynamic>{
              'id': 'branch-1',
              'firm_id': 'firm-1',
              'code': 'BR-001',
              'name': 'Main Branch',
              'display_name': 'Main Branch',
              'status': 'ACTIVE',
              'is_default': true,
            }),
          ],
          warehouses: <WarehouseRecord>[
            WarehouseRecord.fromJson(<String, dynamic>{
              'id': 'warehouse-1',
              'firm_id': 'firm-1',
              'branch_id': 'branch-1',
              'code': 'WH-001',
              'name': 'Main Warehouse',
              'status': 'ACTIVE',
              'is_default': true,
            }),
          ],
          products: <Product>[_product()],
          buyers: const [],
          taxProfiles: const [],
          storageNodes: const [],
          canSubmit: true,
          canApprove: false,
        ),
      ),
    ),
  ));
  await tester.pumpAndSettle();
  await tester.pump(const Duration(milliseconds: 400));
  await tester.pumpAndSettle();
}

// The receipt editor ----------------------------------------------------

Future<void> _pumpReceipt(
  WidgetTester tester,
  _Api api, {
  required bool orderCapital,
  required bool receiptCapital,
}) async {
  _size(tester);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Phase2Scope(
        child: GoodsReceiptEditorDialog(
          api: api,
          purchaseOrders: <PurchaseOrder>[
            PurchaseOrder.fromJson(_orderJson(capital: orderCapital)),
          ],
          warehouses: const [],
          products: <Product>[_product()],
          existing: GoodsReceiptRecord.fromJson(
            _receiptJson(capital: receiptCapital),
          ),
        ),
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

// The bill editor -------------------------------------------------------

GoodsReceiptRecord _billedReceipt({required bool capital}) =>
    GoodsReceiptRecord.fromJson({
      'id': 'grn-1',
      'grn_number': 'GRN-2026-000001',
      'receipt_date': '2026-08-10',
      'status': 'COMPLETED',
      'vendor_id': 'vendor-1',
      'vendor_name': 'Acme Machines',
      'branch_id': 'branch-1',
      'lines': [
        {
          'id': 'grn-line-1',
          'line_number': 1,
          'product_id': 'product-1',
          'description': 'Packing machine',
          'accepted_quantity': '1',
          'unit_price': '100000',
          'purchase_uom_id': 'uom-box',
          'warehouse_id': 'wh-1',
          'tax_profile_id': 'tax-1',
          'is_capital_goods': capital,
        },
      ],
    });

Future<void> _pumpBill(
  WidgetTester tester,
  _Api api, {
  required bool capital,
}) async {
  _size(tester);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Phase2Scope(
        child: PurchaseInvoiceEditorDialog(
          api: api,
          receipts: [_billedReceipt(capital: capital)],
          vendors: [_vendor()],
          products: [_product()],
        ),
      ),
    ),
  ));
  await tester.pumpAndSettle();
  await tester
      .tap(find.byKey(const ValueKey('purchase-invoice-receipt-supplier')));
  await tester.pumpAndSettle();
  await tester.tap(find.text('Acme Machines').last);
  await tester.pumpAndSettle();
  await tester.pump(const Duration(milliseconds: 400));
  await tester.pumpAndSettle();
}

void main() {
  group('the order line', () {
    testWidgets('ticking it sends is_capital_goods on that line',
        (tester) async {
      final _Api api = _Api();
      await _pumpOrder(tester, api);
      expect(_ticked(tester, 'purchase-order-capital--0'), isFalse);
      expect(
        find.textContaining('A fixed asset, not stock'),
        findsOneWidget,
      );
      await _tap(tester, 'purchase-order-capital--0');
      expect(_ticked(tester, 'purchase-order-capital--0'), isTrue);

      await _tap(tester, 'purchase-order-save');
      final Json line =
          (api.bodies['POST /api/v1/purchases']!['lines'] as List).first
              as Json;
      expect(line['is_capital_goods'], true);
    });

    testWidgets('an unticked line sends no such key', (tester) async {
      final _Api api = _Api();
      await _pumpOrder(tester, api);
      await _tap(tester, 'purchase-order-save');
      final Json line =
          (api.bodies['POST /api/v1/purchases']!['lines'] as List).first
              as Json;
      expect(line.containsKey('is_capital_goods'), isFalse);
    });

    testWidgets('an existing order opens with its stored mark',
        (tester) async {
      final _Api api = _Api();
      await _pumpOrder(
        tester,
        api,
        mode: PurchaseDialogMode.edit,
        order: PurchaseOrder.fromJson(
          _orderJson(capital: true)..['status'] = 'DRAFT',
        ),
      );
      expect(_ticked(tester, 'purchase-order-capital-po-1-0'), isTrue);
    });
  });

  group('the receipt line', () {
    testWidgets(
        'a line of a capital-goods order line opens ticked and, untouched, '
        'sends no is_capital_goods', (tester) async {
      final _Api api = _Api();
      await _pumpReceipt(tester, api, orderCapital: true, receiptCapital: true);
      expect(_ticked(tester, 'goods-receipt-capital-po-1-0'), isTrue);
      expect(
        find.textContaining('Received without entering stock'),
        findsOneWidget,
      );

      await _tap(tester, 'goods-receipt-save');
      final Json line =
          (api.bodies['PUT /api/v1/goods-receipts/gr-1']!['lines'] as List)
              .first as Json;
      expect(line.containsKey('is_capital_goods'), isFalse);
    });

    testWidgets('ticking a line ordered as stock sends true', (tester) async {
      final _Api api = _Api();
      await _pumpReceipt(
          tester, api, orderCapital: false, receiptCapital: false);
      expect(_ticked(tester, 'goods-receipt-capital-po-1-0'), isFalse);
      await _tap(tester, 'goods-receipt-capital-po-1-0');

      await _tap(tester, 'goods-receipt-save');
      final Json line =
          (api.bodies['PUT /api/v1/goods-receipts/gr-1']!['lines'] as List)
              .first as Json;
      expect(line['is_capital_goods'], true);
    });

    testWidgets('unticking a line ordered as capital goods sends false',
        (tester) async {
      final _Api api = _Api();
      await _pumpReceipt(tester, api, orderCapital: true, receiptCapital: true);
      await _tap(tester, 'goods-receipt-capital-po-1-0');

      await _tap(tester, 'goods-receipt-save');
      final Json line =
          (api.bodies['PUT /api/v1/goods-receipts/gr-1']!['lines'] as List)
              .first as Json;
      expect(line['is_capital_goods'], false);
    });

    testWidgets('a line ordered and received as stock sends no key',
        (tester) async {
      final _Api api = _Api();
      await _pumpReceipt(
          tester, api, orderCapital: false, receiptCapital: false);
      await _tap(tester, 'goods-receipt-save');
      final Json line =
          (api.bodies['PUT /api/v1/goods-receipts/gr-1']!['lines'] as List)
              .first as Json;
      expect(line.containsKey('is_capital_goods'), isFalse);
    });
  });

  group('the bill line', () {
    testWidgets(
        'from a receipt line received as capital goods it is ticked, '
        'fixed, asks for its class and refuses to save without one',
        (tester) async {
      final _Api api = _Api();
      await _pumpBill(tester, api, capital: true);
      const String tick = 'purchase-invoice-capital-grn-1-0';
      expect(_ticked(tester, tick), isTrue);
      expect(_enabled(tester, tick), isFalse);
      expect(find.text('Received as capital goods.'), findsOneWidget);
      expect(
        find.byKey(const ValueKey('purchase-invoice-asset-class-grn-1-0')),
        findsOneWidget,
      );
      expect(api.calls, contains('GET /api/v1/fixed-assets/classes'));

      await tester.enterText(
        find.byKey(const ValueKey('purchase-invoice-supplier-number-0')),
        'AM-1',
      );
      await tester.pumpAndSettle();
      await _tap(tester, 'purchase-invoice-save');
      expect(api.bill, isNull);
      expect(find.textContaining('choose the asset class'), findsWidgets);

      await _tap(tester, 'purchase-invoice-asset-class-grn-1-0');
      await tester.tap(find.text('PLANT · Plant and machinery').last);
      await tester.pumpAndSettle();
      await _tap(tester, 'purchase-invoice-save');
      final Json line = (api.bill!['lines'] as List).first as Json;
      expect(line['is_capital_goods'], true);
      expect(line['asset_class_id'], 'c-1');
    });

    testWidgets('from an ordinary receipt line it behaves as before',
        (tester) async {
      final _Api api = _Api();
      await _pumpBill(tester, api, capital: false);
      const String tick = 'purchase-invoice-capital-grn-1-0';
      expect(_ticked(tester, tick), isFalse);
      expect(_enabled(tester, tick), isTrue);
      expect(find.text('Received as capital goods.'), findsNothing);
      expect(
        find.byKey(const ValueKey('purchase-invoice-asset-class-grn-1-0')),
        findsNothing,
      );
      expect(api.calls, isNot(contains('GET /api/v1/fixed-assets/classes')));
    });
  });
}
