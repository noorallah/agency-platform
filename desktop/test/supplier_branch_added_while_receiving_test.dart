// Backlog 140 (F9): the order is placed on the supplier company and the goods
// come from a branch nobody has entered yet. A **New branch** button beside
// *Received from* on the goods receipt, and beside *Billed by* on a bill
// raised against an order, opens the supplier form over the document already
// set as a branch of the company the order is on. Save returns with the new
// branch chosen and what was typed kept. Offered only to somebody holding
// `VENDOR_CREATE`.

import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/document_preview.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/goods_receipt.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/models/purchase.dart';
import 'package:agency_desktop/models/vendor.dart';
import 'package:agency_desktop/phase2/document_page.dart';
import 'package:agency_desktop/ui/goods_receipts/goods_receipt_editor_dialog.dart';
import 'package:agency_desktop/ui/purchase_invoices/purchase_invoice_editor_dialog.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Json _vendorJson(
  String id,
  String code,
  String name, {
  String? parentId,
  int branches = 0,
}) =>
    <String, dynamic>{
      'id': id,
      'firm_id': 'firm-1',
      'code': code,
      'name': name,
      'display_name': name,
      'status': 'ACTIVE',
      'parent_vendor_id': parentId,
      'branch_count': branches,
      'addresses': <Json>[],
      'contacts': <Json>[],
      'bank_accounts': <Json>[],
      'tax_details': <Json>[],
      'notes': <Json>[],
    };

Json _member(String id, String code, String name, {bool main = false}) =>
    <String, dynamic>{
      'id': id,
      'code': code,
      'name': name,
      'is_parent': main,
      'status': 'ACTIVE',
      'balance': '0.00',
    };

class _Api extends ApiClient {
  _Api({this.hasBranch = true})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  /// Whether the order's supplier already has a branch.
  final bool hasBranch;

  final List<String> calls = <String>[];
  final List<String> familyCalls = <String>[];
  Json? vendorSent;
  Json? receiptSent;
  Json? billSent;
  final List<Json> previews = <Json>[];

  /// What the create answers as the new supplier's main office; null is the
  /// one the form sent.
  bool dropParent = false;

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
    calls.add('$method $path');
    if (method == 'POST' && path == '/api/v1/vendors') {
      vendorSent = body;
      return {
        'data': _vendorJson(
          'v-new',
          'HQ-CBE',
          '${body!['name']}',
          parentId: dropParent ? null : body['parent_vendor_id'] as String?,
        ),
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
      PagedResult<GoodsReceiptRecord>(items: const [], total: 0);

  @override
  Future<VendorFamily> vendorFamily(String id) async {
    familyCalls.add(id);
    return VendorFamily.fromJson(<String, dynamic>{
      'parent_id': 'v-main',
      'members': <Json>[
        _member('v-main', 'HQ', 'Sundaram Pharma', main: true),
        if (hasBranch) _member('v-blr', 'HQ-BLR', 'Sundaram Pharma Bengaluru'),
      ],
      'total_balance': '0.00',
    });
  }

  @override
  Future<GoodsReceiptRecord> createGoodsReceipt(Json data) async {
    receiptSent = data;
    return GoodsReceiptRecord.fromJson({
      'id': 'grn-2',
      'grn_number': 'GRN-2',
      'status': 'DRAFT',
    });
  }

  @override
  Future<PurchaseInvoicePreviewRecord> previewPurchaseInvoice(
    Json data,
  ) async {
    previews.add(data);
    return PurchaseInvoicePreviewRecord.fromJson({
      'invoice': {
        'invoice_number': 'PI-2026-000009',
        'subtotal': '250.00',
        'tax_total': '0.00',
        'grand_total': '250.00',
        'lines': [
          {
            'line_number': 1,
            'gross_amount': '250.00',
            'discount_amount': '0',
            'tax_amount': '0.00',
            'net_amount': '250.00',
          },
        ],
      },
      'interstate': false,
      'lines': [
        {'line_number': 1, 'product_id': 'prod-1'},
      ],
    });
  }

  @override
  Future<Json> createPurchaseInvoice(Json body) async {
    billSent = body;
    return {
      'data': {'id': 'pi-1', 'invoice_number': 'PI-1', 'status': 'DRAFT'}
    };
  }
}

PurchaseOrder _order() => PurchaseOrder.fromJson({
      'id': 'po-1',
      'po_number': 'PO-2026-000001',
      'purchase_date': '2026-08-01',
      'warehouse_id': 'wh-1',
      'vendor_id': 'v-main',
      'status': 'APPROVED',
      'lines': [
        {
          'id': 'po-line-1',
          'line_number': 1,
          'product_id': 'prod-1',
          'description': 'Amoxicillin 500mg',
          'ordered_quantity': '10',
          'unit_price': '25',
        },
      ],
    });

final Product _product = Product.fromJson({
  'id': 'prod-1',
  'code': 'SKU-1',
  'name': 'Amoxicillin 500mg',
  'purchase_price': '25',
});

Future<void> _settle(WidgetTester tester) async {
  await tester.pumpAndSettle();
  await tester.pump(const Duration(milliseconds: 400));
  await tester.pumpAndSettle();
}

Future<void> _openReceipt(
  WidgetTester tester,
  _Api api, {
  bool canAddBranch = true,
}) async {
  tester.view.physicalSize = const Size(1600, 1100);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: Phase2Scope(
          child: GoodsReceiptEditorDialog(
            api: api,
            purchaseOrders: [_order()],
            warehouses: const [],
            products: const [],
            canAddBranch: canAddBranch,
          ),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

Future<void> _chooseOrder(WidgetTester tester, String key) async {
  await tester.tap(find.byKey(ValueKey<String>(key)));
  await tester.pumpAndSettle();
  await tester.tap(find.textContaining('PO-2026-000001').last);
  await _settle(tester);
}

Future<void> _openBill(
  WidgetTester tester,
  _Api api, {
  bool canAddVendor = true,
  bool supplierHasBranches = true,
  PurchaseWorkflowSettings stages = const PurchaseWorkflowSettings(
    purchaseOrderStage: true,
    goodsReceiptStage: false,
    isConfigured: true,
  ),
}) async {
  tester.view.physicalSize = const Size(1600, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: Phase2Scope(
          child: PurchaseInvoiceEditorDialog(
            api: api,
            receipts: const [],
            products: [_product],
            stages: stages,
            orders: [_order()],
            vendors: [
              Vendor.fromJson(_vendorJson(
                'v-main',
                'HQ',
                'Sundaram Pharma',
                branches: supplierHasBranches ? 1 : 0,
              )),
            ],
            canAddVendor: canAddVendor,
          ),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

Finder _keyed(String prefix) => find.byWidgetPredicate((widget) =>
    widget.key is ValueKey<String> &&
    (widget.key! as ValueKey<String>).value.startsWith(prefix));

String _text(WidgetTester tester, Finder box) => tester
    .widget<EditableText>(
      find.descendant(of: box, matching: find.byType(EditableText)).first,
    )
    .controller
    .text;

/// Type a name into the supplier form that is open and save it.
Future<void> _saveBranch(WidgetTester tester, String name) async {
  await tester.enterText(find.widgetWithText(TextField, 'Vendor Name'), name);
  await tester.tap(find.byKey(const ValueKey('vendor-save')));
  await _settle(tester);
}

const ValueKey<String> _receiptButton = ValueKey('goods-receipt-new-branch');
const ValueKey<String> _billButton = ValueKey('purchase-invoice-new-branch');

void main() {
  group('on a goods receipt', () {
    testWidgets('a new branch is saved under the main office and chosen, and '
        'the receipt kept', (tester) async {
      final _Api api = _Api();
      await _openReceipt(tester, api);
      // No order, nothing to be a branch of.
      expect(find.byKey(_receiptButton), findsNothing);
      await _chooseOrder(tester, 'goods-receipt-order');
      // Something typed on the receipt before the branch is added.
      await tester.enterText(
        find.descendant(
          of: find.ancestor(
            of: find.text("Supplier's invoice number"),
            matching: find.byType(DocumentField),
          ),
          matching: find.byType(TextFormField),
        ),
        'SUP-77',
      );
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(_receiptButton));
      await tester.pumpAndSettle();
      // The form opens as a branch of the company the order is on.
      expect(
        _text(tester, find.byKey(const ValueKey('vendor-parent-box'))),
        'HQ - Sundaram Pharma',
      );
      await _saveBranch(tester, 'Sundaram Pharma Coimbatore');
      expect(tester.takeException(), isNull);

      expect(api.vendorSent!['parent_vendor_id'], 'v-main');
      expect(api.vendorSent!['name'], 'Sundaram Pharma Coimbatore');
      // The form is gone and the receipt is back with the branch chosen.
      expect(find.byKey(const ValueKey('vendor-save')), findsNothing);
      expect(
        _text(tester, _keyed('goods-receipt-received-from')),
        contains('Sundaram Pharma Coimbatore'),
      );
      // One read of the family when the order was chosen, none after.
      expect(api.familyCalls, ['v-main']);

      await tester.tap(find.byKey(const ValueKey('goods-receipt-save')));
      await tester.pumpAndSettle();
      expect(api.receiptSent!['vendor_id'], 'v-new');
      expect(api.receiptSent!['invoice_reference'], 'SUP-77');
      expect(tester.takeException(), isNull);
    });

    testWidgets('a supplier on its own gets its first branch here',
        (tester) async {
      final _Api api = _Api(hasBranch: false);
      await _openReceipt(tester, api);
      await _chooseOrder(tester, 'goods-receipt-order');
      expect(find.text('Received from'), findsNothing);

      await tester.tap(find.byKey(_receiptButton));
      await tester.pumpAndSettle();
      await _saveBranch(tester, 'Sundaram Pharma Coimbatore');

      expect(api.vendorSent!['parent_vendor_id'], 'v-main');
      expect(find.text('Received from'), findsOneWidget);
      expect(
        _text(tester, _keyed('goods-receipt-received-from')),
        contains('Sundaram Pharma Coimbatore'),
      );
      await tester.tap(find.byKey(const ValueKey('goods-receipt-save')));
      await tester.pumpAndSettle();
      expect(api.receiptSent!['vendor_id'], 'v-new');
      expect(tester.takeException(), isNull);
    });

    testWidgets('closing the form without saving changes nothing',
        (tester) async {
      final _Api api = _Api();
      await _openReceipt(tester, api);
      await _chooseOrder(tester, 'goods-receipt-order');
      await tester.tap(find.byKey(_receiptButton));
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(TextButton, 'Cancel'));
      await tester.pumpAndSettle();

      expect(api.vendorSent, isNull);
      expect(
        _text(tester, _keyed('goods-receipt-received-from')),
        contains('Sundaram Pharma'),
      );
      await tester.tap(find.byKey(const ValueKey('goods-receipt-save')));
      await tester.pumpAndSettle();
      expect(api.receiptSent!['vendor_id'], 'v-main');
      expect(tester.takeException(), isNull);
    });

    testWidgets('a supplier saved outside the company is not chosen',
        (tester) async {
      final _Api api = _Api()..dropParent = true;
      await _openReceipt(tester, api);
      await _chooseOrder(tester, 'goods-receipt-order');
      await tester.tap(find.byKey(_receiptButton));
      await tester.pumpAndSettle();
      await _saveBranch(tester, 'Somebody Else');

      expect(find.textContaining('not as a branch of Sundaram Pharma'),
          findsOneWidget);
      await tester.tap(find.byKey(const ValueKey('goods-receipt-save')));
      await tester.pumpAndSettle();
      expect(api.receiptSent!['vendor_id'], 'v-main');
    });

    testWidgets('not offered without VENDOR_CREATE', (tester) async {
      final _Api api = _Api();
      await _openReceipt(tester, api, canAddBranch: false);
      await _chooseOrder(tester, 'goods-receipt-order');
      expect(find.byKey(_receiptButton), findsNothing);
      expect(find.text('Received from'), findsOneWidget);
    });
  });

  test('the Goods Receipts page offers it to a holder of VENDOR_CREATE', () {
    // The window is tried above with the flag handed to it; this is the one
    // line that hands it over, and nothing else would notice it gone.
    final String page = File(
      'lib/ui/goods_receipts/goods_receipt_management_page.dart',
    ).readAsStringSync();
    expect(
      page,
      contains("canAddBranch: widget.permissions.hasPermission('VENDOR_CREATE')"),
    );
  });

  group('on a supplier bill raised against an order', () {
    testWidgets('the offices are offered and a new branch bills the order',
        (tester) async {
      final _Api api = _Api();
      await _openBill(tester, api);
      expect(find.byKey(_billButton), findsNothing);
      await _chooseOrder(tester, 'purchase-invoice-order');

      expect(api.familyCalls, ['v-main']);
      expect(find.text('Billed by'), findsOneWidget);
      // Untouched, the bill is the order's supplier's and names nobody.
      expect(api.previews.last.containsKey('vendor_id'), isFalse);

      await tester.enterText(
        find.byKey(const ValueKey('purchase-invoice-supplier-number-0')),
        'SUP-900',
      );
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(_billButton));
      await tester.pumpAndSettle();
      expect(
        _text(tester, find.byKey(const ValueKey('vendor-parent-box'))),
        'HQ - Sundaram Pharma',
      );
      await _saveBranch(tester, 'Sundaram Pharma Coimbatore');
      expect(tester.takeException(), isNull);

      expect(api.vendorSent!['parent_vendor_id'], 'v-main');
      expect(
        _text(tester, _keyed('purchase-invoice-billed-by')),
        contains('Sundaram Pharma Coimbatore'),
      );
      // Priced again in the branch's name, and no second family read.
      expect(api.previews.last['vendor_id'], 'v-new');
      expect(api.familyCalls, ['v-main']);

      await tester.tap(find.byKey(const ValueKey('purchase-invoice-save')));
      await tester.pumpAndSettle();
      expect(api.billSent!['vendor_id'], 'v-new');
      expect(api.billSent!['supplier_invoice_number'], 'SUP-900');
      expect(tester.takeException(), isNull);
    });

    testWidgets('an office already there is chosen from Billed by',
        (tester) async {
      final _Api api = _Api();
      await _openBill(tester, api);
      await _chooseOrder(tester, 'purchase-invoice-order');
      await tester.tap(find.byKey(const ValueKey('purchase-invoice-billed-by')));
      await tester.pumpAndSettle();
      await tester.tap(
          find.textContaining('HQ-BLR  Sundaram Pharma Bengaluru').last);
      await _settle(tester);

      expect(api.previews.last['vendor_id'], 'v-blr');
      expect(tester.takeException(), isNull);
    });

    testWidgets('a supplier on its own costs no call and gets its first '
        'branch', (tester) async {
      final _Api api = _Api(hasBranch: false);
      await _openBill(tester, api, supplierHasBranches: false);
      await _chooseOrder(tester, 'purchase-invoice-order');
      expect(api.familyCalls, isEmpty);
      expect(find.text('Billed by'), findsNothing);

      await tester.tap(find.byKey(_billButton));
      await tester.pumpAndSettle();
      await _saveBranch(tester, 'Sundaram Pharma Coimbatore');

      expect(api.familyCalls, isEmpty);
      expect(api.vendorSent!['parent_vendor_id'], 'v-main');
      expect(find.text('Billed by'), findsOneWidget);
      expect(api.previews.last['vendor_id'], 'v-new');
      expect(tester.takeException(), isNull);
    });

    testWidgets('not offered without VENDOR_CREATE', (tester) async {
      final _Api api = _Api();
      await _openBill(tester, api, canAddVendor: false);
      await _chooseOrder(tester, 'purchase-invoice-order');
      expect(find.byKey(_billButton), findsNothing);
      expect(find.text('Billed by'), findsOneWidget);
    });

    testWidgets('not offered on a bill that names a receipt', (tester) async {
      await _openBill(
        tester,
        _Api(),
        stages: PurchaseWorkflowSettings.wholeChain,
      );
      expect(find.byKey(_billButton), findsNothing);
      expect(find.text('Billed by'), findsNothing);
    });
  });
}
