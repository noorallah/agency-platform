// Input credit eligibility on the desktop (backlog 78 row 1, decision A36):
// the product's setting, the bill line's choice, the bill view's badge and
// the two new GSTR-3B rows.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/document_framework.dart';
import 'package:agency_desktop/models/document_preview.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/goods_receipt.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/ui/document_framework/document_framework_widgets.dart';
import 'package:agency_desktop/ui/products/product_management_page.dart';
import 'package:agency_desktop/ui/purchase_invoices/purchase_invoice_editor_dialog.dart';
import 'package:agency_desktop/ui/sales/gst_return_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

const ProductMetadataRecord _metadata = ProductMetadataRecord(
  profileCode: 'WHOLESALE',
  features: [],
  categories: [],
  taxProfiles: [],
  requiredAttributeDefinitionIds: [],
  optionalAttributeDefinitionIds: [],
);

Product _product({String? itc}) => Product.fromJson({
      'id': 'product-1',
      'code': 'PROD-001',
      'name': 'Pain Relief',
      'product_type': 'STOCK_ITEM',
      'status': 'ACTIVE',
      'unit': 'BOX',
      if (itc != null) 'itc_eligibility': itc,
    });

Future<Json?> _saveProduct(
  WidgetTester tester, {
  required bool canManageTax,
  required Product product,
  String? pick,
  void Function(DropdownButtonFormField<String> box)? beforeSave,
}) async {
  tester.view.physicalSize = const Size(1600, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  Json? sent;
  await tester.pumpWidget(MaterialApp(
    builder: (context, child) => Phase2Scope(child: child!),
    home: Scaffold(
      body: ProductWorkspaceDialog(
        mode: ProductDialogMode.edit,
        product: product,
        categories: const [],
        uoms: const [],
        definitions: const [],
        metadata: _metadata,
        initialTab: 'general',
        canManageTax: canManageTax,
        onMetadataForCategory: (_) async => _metadata,
        onSave: (payload) async {
          sent = payload;
          return product;
        },
        onTabChanged: (_) {},
      ),
    ),
  ));
  await tester.pumpAndSettle();
  final Finder box = find.byKey(const ValueKey('product-itc-eligibility'));
  await tester.ensureVisible(box);
  if (pick != null) {
    await tester.tap(box);
    await tester.pumpAndSettle();
    await tester.tap(find.text(pick).last);
    await tester.pumpAndSettle();
  }
  beforeSave?.call(tester.widget<DropdownButtonFormField<String>>(box));
  await tester.tap(find.byKey(const ValueKey('product-save')));
  await tester.pumpAndSettle();
  return sent;
}

GoodsReceiptRecord _receipt() => GoodsReceiptRecord.fromJson({
      'id': 'grn-1',
      'grn_number': 'GRN-2026-000001',
      'receipt_date': '2026-08-10',
      'status': 'COMPLETED',
      'vendor_id': 'vendor-1',
      'vendor_name': 'Medico Distributors',
      'branch_id': 'branch-1',
      'lines': [
        {
          'id': 'grn-line-1',
          'line_number': 1,
          'product_id': 'prod-1',
          'description': 'Amoxicillin 500mg',
          'accepted_quantity': '20',
          'unit_price': '25',
          'purchase_uom_id': 'uom-box',
          'warehouse_id': 'wh-1',
          'tax_profile_id': 'tax-1',
        },
      ],
    });

class _BillApi extends ApiClient {
  _BillApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  Json? sent;

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
      {'data': <Json>[]};

  @override
  Future<PurchaseInvoicePreviewRecord> previewPurchaseInvoice(
    Json data,
  ) async =>
      PurchaseInvoicePreviewRecord.fromJson({
        'invoice': {
          'invoice_number': 'PI-2026-000009',
          'subtotal': '500.00',
          'tax_total': '90.00',
          'grand_total': '590.00',
          'lines': [
            {
              'line_number': 1,
              'source_document_line_id': 'grn-line-1',
              'gross_amount': '500.00',
              'discount_amount': '0',
              'tax_amount': '90.00',
            },
          ],
        },
        'interstate': false,
        'lines': [
          {'line_number': 1, 'product_id': 'prod-1'},
        ],
      });

  @override
  Future<Json> createPurchaseInvoice(Json body) async {
    sent = body;
    return {
      'data': {'id': 'pi-1', 'invoice_number': 'PI-1', 'status': 'DRAFT'}
    };
  }
}

Future<_BillApi> _openBill(WidgetTester tester) async {
  tester.view.physicalSize = const Size(1600, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final _BillApi api = _BillApi();
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Phase2Scope(
        child: PurchaseInvoiceEditorDialog(
          api: api,
          receipts: [_receipt()],
          products: [
            Product.fromJson(
                {'id': 'prod-1', 'code': 'SKU-1', 'name': 'Amoxicillin'}),
          ],
        ),
      ),
    ),
  ));
  await tester.pumpAndSettle();
  await tester.tap(
        find.byKey(const ValueKey('purchase-invoice-receipt-supplier')));
  await tester.pumpAndSettle();
  await tester.tap(find.text('Medico Distributors').last);
  await tester.pumpAndSettle();
  await tester.pump(const Duration(milliseconds: 400));
  await tester.pumpAndSettle();
  await tester.enterText(
    find.byKey(const ValueKey<String>('purchase-invoice-supplier-number-0')),
    'SUP-5',
  );
  await tester.pumpAndSettle();
  return api;
}

String _token(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

class _ReturnsApi extends ApiClient {
  _ReturnsApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

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
    Json heads(double igst) => {
          'integrated_tax': igst,
          'central_tax': 0.0,
          'state_tax': 0.0,
          'cess': 0.0,
        };
    if (path.endsWith('/gstr3b')) {
      return {
        'data': {
          'gstin': '29AABCU9603R1ZM',
          'outward_taxable_supplies': {
            'taxable_value': 0.0,
            ...heads(0),
          },
          'credit_notes_deducted': {'taxable_value': 0.0, 'tax': 0.0},
          'eligible_itc': heads(700),
          'itc_reversed_blocked': heads(123),
          'itc_ineligible': heads(45),
          'net_itc': heads(577),
        },
      };
    }
    return {
      'data': {'gstin': '29AABCU9603R1ZM', 'b2b': <Json>[]},
    };
  }
}

void main() {
  testWidgets('a product with a blocked credit sends it, and says what it is',
      (tester) async {
    final Json? sent = await _saveProduct(
      tester,
      canManageTax: true,
      product: _product(itc: 'ELIGIBLE'),
      pick: 'Blocked (s.17(5))',
      // Read before the save closes the page.
      beforeSave: (_) => expect(
          find.text('Cars, food and catering, personal use, gifts'),
          findsOneWidget),
    );
    expect(sent?['itc_eligibility'], 'BLOCKED');
  });

  testWidgets('without the tax permission the setting is shown, not editable',
      (tester) async {
    final Json? sent = await _saveProduct(
      tester,
      canManageTax: false,
      product: _product(itc: 'BLOCKED'),
      beforeSave: (box) => expect(box.onChanged, isNull),
    );
    // The stored value is echoed back unchanged, which the server accepts.
    expect(sent?['itc_eligibility'], 'BLOCKED');
  });

  testWidgets('a bill line sends no input credit unless one is chosen',
      (tester) async {
    final _BillApi api = await _openBill(tester);
    expect(find.text('From product'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('purchase-invoice-save')));
    await tester.pumpAndSettle();
    final Json line = (api.sent!['lines'] as List).first as Json;
    expect(line.containsKey('itc_eligibility'), isFalse);
  });

  testWidgets('a chosen input credit is sent on the line', (tester) async {
    final _BillApi api = await _openBill(tester);
    final Finder box =
        find.byKey(const ValueKey<String>('purchase-invoice-itc-grn-1-0'));
    await tester.ensureVisible(box);
    await tester.tap(box);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Blocked (s.17(5))').last);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('purchase-invoice-save')));
    await tester.pumpAndSettle();
    final Json line = (api.sent!['lines'] as List).first as Json;
    expect(line['itc_eligibility'], 'BLOCKED');
  });

  testWidgets('the bill view flags a line whose credit is not claimable',
      (tester) async {
    await tester.pumpWidget(const MaterialApp(
      home: Scaffold(
        body: SingleChildScrollView(
          child: EnterpriseDocumentLines(lines: [
            DocumentLineSnapshot(lineNumber: 1, itcEligibility: 'BLOCKED'),
            DocumentLineSnapshot(lineNumber: 2, itcEligibility: 'ELIGIBLE'),
            DocumentLineSnapshot(lineNumber: 3, itcEligibility: 'INELIGIBLE'),
          ]),
        ),
      ),
    ));
    await tester.pumpAndSettle();
    expect(find.text('Credit blocked'), findsOneWidget);
    expect(find.text('Credit ineligible'), findsOneWidget);
  });

  testWidgets('GSTR-3B shows blocked and ineligible credit in table 4',
      (tester) async {
    tester.view.physicalSize = const Size(1366, 768);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: GstReturnPage(
          api: _ReturnsApi(),
          permissions: PermissionService()
            ..applyAccessToken(_token({
              'roles': <String>['user'],
              'permissions': <String>['SALES_VIEW'],
            })),
          hasActiveFirm: true,
        ),
      ),
    ));
    await tester.pumpAndSettle();
    await tester.tap(find.text('GSTR-3B'));
    await tester.pumpAndSettle();
    expect(find.textContaining('4(B)(1) ITC reversed'), findsOneWidget);
    expect(find.textContaining('4(D)(2) Ineligible ITC'), findsOneWidget);
    expect(find.text('123.00'), findsOneWidget);
    expect(find.text('45.00'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
