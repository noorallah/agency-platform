// Approval is a step of its own, per purchase document (backlog 120, M2).
//
// A firm may decide that a purchase order, a goods receipt or a supplier bill
// is complete once it is saved. Then the window offers one *Save*, which
// saves the draft and at once runs the rest -- order: send for approval, then
// approve; receipt: complete; bill: the approve step, with every question it
// already asks -- and whoever raised an order or a bill may approve it without
// the approve code, because the server stamped `approval_step: false` on it.
// These pin the windows' buttons and the list's Approve on both sides.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/document_preview.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/goods_receipt.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/models/purchase.dart';
import 'package:agency_desktop/models/vendor.dart';
import 'package:agency_desktop/ui/document_framework/document_steps.dart';
import 'package:agency_desktop/ui/goods_receipts/goods_receipt_editor_dialog.dart';
import 'package:agency_desktop/ui/goods_receipts/goods_receipt_steps.dart';
import 'package:agency_desktop/ui/purchase_invoices/purchase_invoice_editor_dialog.dart';
import 'package:agency_desktop/ui/purchase_invoices/purchase_invoice_steps.dart';
import 'package:agency_desktop/ui/purchases/purchase_management_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/new_purchase_order.dart';

/// Someone who may raise buying documents and may not approve them.
PermissionService _raiser() => PermissionService()
  ..applyAccessToken(
    'header.${base64Url.encode(utf8.encode(jsonEncode(<String, dynamic>{
          'sub': 'u-me',
          'roles': <String>['user'],
          'permissions': <String>[
            'PURCHASE_VIEW',
            'PURCHASE_CREATE',
            'PURCHASE_UPDATE',
            'PURCHASE_RECEIVE',
          ],
        }))).replaceAll('=', '')}.sig',
  );

class _Api extends ApiClient {
  _Api({required this.approvalStep, this.refuseApprove = false})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  /// What the firm's settings say of every document kind.
  final bool approvalStep;

  /// Answer the order's approve with a refusal.
  final bool refuseApprove;
  final List<String> calls = <String>[];

  Json _order(String status) => <String, dynamic>{
        'id': 'po-1',
        'firm_id': 'firm-1',
        'branch_id': 'branch-1',
        'warehouse_id': 'warehouse-1',
        'vendor_id': 'vendor-1',
        'po_number': 'PO-0001',
        'purchase_date': '2026-10-01',
        'status': status,
        'grand_total': '100.00',
        'approval_step': approvalStep,
        'created_by': 'u-me',
        'version': 1,
        'lines': <Json>[
          <String, dynamic>{
            'id': 'pol-1',
            'line_number': 1,
            'product_id': 'product-1',
            'ordered_quantity': '1',
            'unit_price': '100',
            'net_amount': '100.00',
          },
        ],
      };

  @override
  Future<PurchaseWorkflowSettings> purchaseWorkflowSettings() async =>
      PurchaseWorkflowSettings.fromJson(<String, dynamic>{
        'purchase_order_stage': true,
        'goods_receipt_stage': true,
        'is_configured': true,
        'purchase_order_approval': approvalStep,
        'goods_receipt_approval': approvalStep,
        'purchase_invoice_approval': approvalStep,
      });

  @override
  Future<GoodsReceiptRecord> createGoodsReceipt(Json data) async {
    calls.add('POST /goods-receipts');
    return GoodsReceiptRecord.fromJson(_receipt('DRAFT'));
  }

  @override
  Future<GoodsReceiptRecord> completeGoodsReceipt(String id) async {
    calls.add('POST /goods-receipts/$id/complete');
    return GoodsReceiptRecord.fromJson(_receipt('COMPLETED'));
  }

  Json _receipt(String status) => <String, dynamic>{
        'id': 'grn-9',
        'grn_number': 'GRN-9',
        'purchase_order_id': 'po-1',
        'purchase_order_number': 'PO-0001',
        'status': status,
        'version': 1,
        'approval_step': approvalStep,
        'created_by': 'u-me',
        'lines': <Json>[
          <String, dynamic>{
            'id': 'grn-line-1',
            'purchase_order_line_id': 'pol-1',
            'line_number': 1,
            'product_id': 'product-1',
            'current_receipt_quantity': '1',
          },
        ],
      };

  @override
  Future<PurchaseInvoicePreviewRecord> previewPurchaseInvoice(Json data) async =>
      PurchaseInvoicePreviewRecord.fromJson(<String, dynamic>{
        'invoice': <String, dynamic>{
          'invoice_number': 'PI-9',
          'subtotal': '100.00',
          'tax_total': '0.00',
          'grand_total': '100.00',
          'lines': <Json>[],
        },
        'interstate': false,
        'lines': <Json>[],
      });

  @override
  Future<Json> purchaseInvoiceTdsProposal(String id) async =>
      <String, dynamic>{};

  @override
  Future<Json> createPurchaseInvoice(Json body) async {
    calls.add('POST /purchase-invoices');
    return <String, dynamic>{
      'data': <String, dynamic>{
        'id': 'pi-1',
        'invoice_number': 'PI-1',
        'status': 'DRAFT',
        'approval_step': approvalStep,
        'created_by': 'u-me',
      },
    };
  }

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
    if (method != 'GET' && !path.endsWith('/preview')) {
      calls.add('$method $path');
    }
    if (method == 'POST' && path == '/api/v1/purchases/preview') {
      return <String, dynamic>{
        'data': <String, dynamic>{
          'order': _order('DRAFT')..['lines'] = <Json>[],
          'interstate': false,
          'lines': <Json>[],
        },
      };
    }
    if (method == 'POST' && path == '/api/v1/purchases') {
      return <String, dynamic>{'data': _order('DRAFT')};
    }
    if (method == 'POST' && path == '/api/v1/purchases/po-1/submit') {
      return <String, dynamic>{'data': _order('SUBMITTED')};
    }
    if (method == 'POST' && path == '/api/v1/purchases/po-1/approve') {
      if (refuseApprove) {
        throw ApiException('Over the purchase budget.', statusCode: 422);
      }
      return <String, dynamic>{'data': _order('APPROVED')};
    }
    if (method == 'POST' && path.endsWith('/approve')) {
      return <String, dynamic>{'data': <String, dynamic>{}};
    }
    return <String, dynamic>{'data': const <dynamic>[]};
  }
}

Vendor _vendor() => Vendor.fromJson(<String, dynamic>{
      'id': 'vendor-1',
      'firm_id': 'firm-1',
      'code': 'V001',
      'name': 'Northwind Supplies',
      'display_name': 'Northwind Supplies',
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
      'code': 'P-1',
      'name': 'Pain Relief',
      'unit': 'BOX',
      'purchase_price': '100',
      'status': 'ACTIVE',
    });

PurchaseOrder _approvedOrder() => PurchaseOrder.fromJson(<String, dynamic>{
      'id': 'po-1',
      'po_number': 'PO-0001',
      'purchase_date': '2026-10-01',
      'warehouse_id': 'warehouse-1',
      'status': 'APPROVED',
      'lines': <Json>[
        <String, dynamic>{
          'id': 'pol-1',
          'line_number': 1,
          'product_id': 'product-1',
          'description': 'Pain Relief',
          'ordered_quantity': '1',
          'unit_price': '100',
        },
      ],
    });

Future<void> _show(WidgetTester tester, Widget window) async {
  tester.view.physicalSize = const Size(1600, 1000);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(body: Phase2Scope(child: window)),
  ));
  await tester.pumpAndSettle();
  await tester.pump(const Duration(milliseconds: 400));
  await tester.pumpAndSettle();
}

Future<void> _pumpOrder(WidgetTester tester, _Api api) async {
  await _show(
    tester,
    PurchaseOrderEditorDialog(
      api: api,
      permissions: _raiser(),
      mode: PurchaseDialogMode.create,
      order: null,
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
  );
  await fillNewPurchaseOrder(
    tester,
    vendor: 'Northwind',
    product: 'Pain Relief',
  );
}

Future<void> _pumpReceipt(WidgetTester tester, _Api api) async {
  await _show(
    tester,
    GoodsReceiptEditorDialog(
      api: api,
      purchaseOrders: <PurchaseOrder>[_approvedOrder()],
      warehouses: <WarehouseRecord>[
        WarehouseRecord.fromJson(<String, dynamic>{
          'id': 'warehouse-1',
          'code': 'MAIN',
          'name': 'Main Warehouse',
        }),
      ],
      products: <Product>[_product()],
      steps: goodsReceiptSteps(api, _raiser()),
    ),
  );
  await tester.tap(find.byKey(const ValueKey('goods-receipt-order')));
  await tester.pumpAndSettle();
  await tester.tap(find.textContaining('PO-0001').last);
  await tester.pumpAndSettle();
}

Future<void> _pumpBill(WidgetTester tester, _Api api) async {
  final GoodsReceiptRecord receipt = GoodsReceiptRecord.fromJson(
    <String, dynamic>{
      'id': 'grn-1',
      'grn_number': 'GRN-2026-000001',
      'receipt_date': '2026-08-10',
      'status': 'COMPLETED',
      'vendor_id': 'vendor-1',
      'vendor_name': 'Northwind Supplies',
      'branch_id': 'branch-1',
      'lines': <Json>[
        <String, dynamic>{
          'id': 'grn-line-1',
          'line_number': 1,
          'product_id': 'product-1',
          'description': 'Pain Relief',
          'accepted_quantity': '1',
          'unit_price': '100',
          'purchase_uom_id': 'uom-box',
          'warehouse_id': 'warehouse-1',
          'tax_profile_id': 'tax-1',
        },
      ],
    },
  );
  await _show(
    tester,
    PurchaseInvoiceEditorDialog(
      api: api,
      receipts: <GoodsReceiptRecord>[receipt],
      vendors: <Vendor>[_vendor()],
      products: <Product>[_product()],
      stages: (await api.purchaseWorkflowSettings()),
      steps: <DocumentStep<Json>>[
        for (final DocumentStep<DocumentRef> step
            in purchaseInvoiceSteps(api, _raiser()))
          step.on<Json>(
            (Json json) =>
                DocumentRef.fromJson(json, numberKey: 'invoice_number'),
          ),
      ],
    ),
  );
  await tester
      .tap(find.byKey(const ValueKey('purchase-invoice-receipt-supplier')));
  await tester.pumpAndSettle();
  await tester.tap(find.text('Northwind Supplies').last);
  await tester.pumpAndSettle();
  await tester.pump(const Duration(milliseconds: 400));
  await tester.pumpAndSettle();
  await tester.enterText(
    find.byKey(const ValueKey('purchase-invoice-supplier-number-0')),
    'SUP-1',
  );
  await tester.pumpAndSettle();
}

String _label(WidgetTester tester, String key) => ((tester
        .widget<FilledButton>(find.byKey(ValueKey<String>(key)))
        .child) as Text)
    .data!;

void main() {
  group('a purchase order', () {
    testWidgets(
        'with approval off: one Save that saves, sends it and approves it',
        (tester) async {
      final _Api api = _Api(approvalStep: false);
      await _pumpOrder(tester, api);

      expect(_label(tester, 'purchase-order-save'), 'Save');
      await tester.tap(find.byKey(const ValueKey('purchase-order-save')));
      await tester.pumpAndSettle();

      expect(api.calls, <String>[
        'POST /api/v1/purchases',
        'POST /api/v1/purchases/po-1/submit',
        'POST /api/v1/purchases/po-1/approve',
      ]);
      expect(tester.takeException(), isNull);
    });

    testWidgets('a refused approval stops there and shows the server\'s words',
        (tester) async {
      final _Api api = _Api(approvalStep: false, refuseApprove: true);
      await _pumpOrder(tester, api);
      await tester.tap(find.byKey(const ValueKey('purchase-order-save')));
      await tester.pumpAndSettle();

      expect(api.calls.last, 'POST /api/v1/purchases/po-1/approve');
      expect(find.textContaining('Over the purchase budget.'), findsOneWidget);
      // The window holds the submitted order: Approve is still offered.
      expect(find.byKey(const ValueKey('purchase-order-approve')),
          findsOneWidget);
    });

    testWidgets('with approval a step: Save draft only, nothing submitted',
        (tester) async {
      final _Api api = _Api(approvalStep: true);
      await _pumpOrder(tester, api);

      expect(_label(tester, 'purchase-order-save'), 'Save draft');
      await tester.tap(find.byKey(const ValueKey('purchase-order-save')));
      await tester.pumpAndSettle();

      expect(api.calls, <String>['POST /api/v1/purchases']);
    });
  });

  group('a goods receipt', () {
    testWidgets('with completing off: one Save that completes',
        (tester) async {
      final _Api api = _Api(approvalStep: false);
      await _pumpReceipt(tester, api);

      expect(_label(tester, 'goods-receipt-save'), 'Save');
      expect(find.byKey(const ValueKey('goods-receipt-save-complete')),
          findsNothing);
      await tester.tap(find.byKey(const ValueKey('goods-receipt-save')));
      await tester.pumpAndSettle();

      expect(api.calls, <String>[
        'POST /goods-receipts',
        'POST /goods-receipts/grn-9/complete',
      ]);
      expect(tester.takeException(), isNull);
    });

    testWidgets('with completing a step: Save receipt and Save & complete',
        (tester) async {
      final _Api api = _Api(approvalStep: true);
      await _pumpReceipt(tester, api);

      expect(_label(tester, 'goods-receipt-save'), 'Save receipt');
      expect(find.byKey(const ValueKey('goods-receipt-save-complete')),
          findsOneWidget);
      await tester.tap(find.byKey(const ValueKey('goods-receipt-save')));
      await tester.pumpAndSettle();

      expect(api.calls, <String>['POST /goods-receipts']);
    });
  });

  group('a supplier bill', () {
    testWidgets('with approval off: one Save that asks the approve questions',
        (tester) async {
      final _Api api = _Api(approvalStep: false);
      await _pumpBill(tester, api);

      expect(_label(tester, 'purchase-invoice-save'), 'Save');
      expect(find.byKey(const ValueKey('purchase-invoice-save-approve')),
          findsNothing);
      await tester.tap(find.byKey(const ValueKey('purchase-invoice-save')));
      // The approve dialog may show a spinner while it reads, so pump.
      for (int i = 0; i < 10; i++) {
        await tester.pump(const Duration(milliseconds: 100));
      }

      // The same approve step as ever: its dialog, then the call.
      expect(api.calls, <String>['POST /purchase-invoices']);
      await tester.tap(find.byKey(const ValueKey('approve-bill-confirm')));
      for (int i = 0; i < 10; i++) {
        await tester.pump(const Duration(milliseconds: 100));
      }
      expect(api.calls.last, 'POST /api/v1/purchase-invoices/pi-1/approve');
    });

    testWidgets('with approval a step: Save bill, no approve call',
        (tester) async {
      final _Api api = _Api(approvalStep: true);
      await _pumpBill(tester, api);

      expect(_label(tester, 'purchase-invoice-save'), 'Save bill');
      await tester.tap(find.byKey(const ValueKey('purchase-invoice-save')));
      await tester.pumpAndSettle();

      expect(api.calls, <String>['POST /purchase-invoices']);
    });
  });

  group('the list offers Approve per row', () {
    PurchaseOrder order({required bool step, required String by}) =>
        PurchaseOrder.fromJson(<String, dynamic>{
          'id': 'po-1',
          'status': 'SUBMITTED',
          'approval_step': step,
          'created_by': by,
        });

    test('on an order, to the person who raised it', () {
      final PermissionService me = _raiser();
      expect(mayApprovePurchaseOrder(me, order(step: false, by: 'u-me')),
          isTrue);
      // Raised by someone else, or approval is a step: the code is needed.
      expect(mayApprovePurchaseOrder(me, order(step: false, by: 'u-other')),
          isFalse);
      expect(mayApprovePurchaseOrder(me, order(step: true, by: 'u-me')),
          isFalse);
    });

    test('on a bill, to the person who raised it', () {
      final _Api api = _Api(approvalStep: true);
      final DocumentStep<DocumentRef> approve =
          purchaseInvoiceSteps(api, _raiser())
              .firstWhere((step) => step.id == 'approve');
      DocumentRef row({required bool step, required String by}) => DocumentRef(
            id: 'r1',
            number: 'PI-1',
            status: 'DRAFT',
            approvalStep: step,
            createdBy: by,
          );
      expect(approve.enabledFor(row(step: false, by: 'u-me')), isTrue);
      expect(approve.enabledFor(row(step: false, by: 'u-other')), isFalse);
      expect(approve.enabledFor(row(step: true, by: 'u-me')), isFalse);
    });
  });
}
