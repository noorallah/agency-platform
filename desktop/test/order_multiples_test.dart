// BUY-5: a supplier's minimum order quantity and order multiple.
//
// 1. The catalogue dialog sends `order_multiple`.
// 2. The buying settings dialog sends `order_quantity_policy`.
// 3. The order editor shows the server's quantity hint for a line, and
//    "Use N" sets that line's quantity and prices the order again.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/document_preview.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/models/purchase.dart';
import 'package:agency_desktop/models/vendor.dart';
import 'package:agency_desktop/ui/purchases/purchase_management_page.dart';
import 'package:agency_desktop/ui/purchases/purchase_workflow_settings_dialog.dart';
import 'package:agency_desktop/ui/vendors/supplier_catalogue_section.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/new_purchase_order.dart';

PermissionService _permissions(List<String> codes) {
  final String payload = base64Url
      .encode(utf8.encode(jsonEncode(<String, dynamic>{
        'roles': <String>['user'],
        'permissions': codes,
      })))
      .replaceAll('=', '');
  return PermissionService()..applyAccessToken('header.$payload.sig');
}

// 1. Catalogue ---------------------------------------------------------------

class _CatalogueApi extends ApiClient {
  _CatalogueApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  Json? lastBody;

  @override
  Future<PagedResult<Product>> products({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    ProductQuery filters = const ProductQuery(),
  }) async =>
      PagedResult<Product>(items: [
        Product.fromJson(<String, dynamic>{
          'id': 'p-1',
          'code': 'P001',
          'name': 'Widget',
        }),
      ], total: 1);

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
    if (method == 'GET') {
      return <String, dynamic>{
        'data': <Json>[
          <String, dynamic>{
            'id': 'r-1',
            'vendor_id': 'v-1',
            'product_id': 'p-1',
            'product_code': 'P001',
            'product_name': 'Widget',
            'minimum_order_quantity': '100',
            'order_multiple': '20',
            'effective_from': '2026-09-01',
            'is_current': true,
          },
        ],
      };
    }
    lastBody = body;
    return <String, dynamic>{
      'data': <String, dynamic>{'id': 'r-new', 'product_id': 'p-1'},
    };
  }
}

// 2. Settings ----------------------------------------------------------------

class _SettingsApi extends ApiClient {
  _SettingsApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Json> saved = <Json>[];

  @override
  Future<PurchaseWorkflowSettings> purchaseWorkflowSettings() async =>
      PurchaseWorkflowSettings.fromJson(<String, dynamic>{
        'purchase_order_stage': true,
        'goods_receipt_stage': true,
        'is_configured': true,
        'order_quantity_policy': 'WARN',
      });

  @override
  Future<PurchaseWorkflowSettings> updatePurchaseWorkflowSettings(
    PurchaseWorkflowSettings settings,
  ) async {
    saved.add(settings.toJson());
    return settings;
  }
}

// 3. Order editor -------------------------------------------------------------

class _OrderApi extends ApiClient {
  _OrderApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Json> previews = <Json>[];

  @override
  Future<PurchaseOrderPreviewRecord> previewPurchaseOrder(
    PurchaseOrder order,
  ) async {
    previews.add(order.toCreateJson());
    final PurchaseOrderLine line = order.lines.first;
    final Json priced = order.toCreateJson()
      ..['po_number'] = 'PO-0002'
      ..['subtotal'] = '0'
      ..['line_discount_total'] = '0'
      ..['tax_total'] = '0'
      ..['grand_total'] = '0'
      ..['lines'] = [
        {
          ...line.toWriteJson(),
          'line_number': 1,
          'gross_amount': '0',
          'discount_amount': '0',
          'tax_amount': '0',
          'net_amount': '0',
        },
      ];
    final bool fine = line.orderedQuantity == '120';
    return PurchaseOrderPreviewRecord.fromJson(<String, dynamic>{
      'order': priced,
      'interstate': false,
      'lines': <Json>[],
      'quantity_hints': fine
          ? <Json>[]
          : <Json>[
              <String, dynamic>{
                'line_number': 1,
                'product_id': 'product-1',
                'quantity': line.orderedQuantity,
                'minimum_order_quantity': '100',
                'order_multiple': '20',
                'suggested_quantity': '120.0000',
                'message': 'Supplier terms: minimum 100, multiples of 20 '
                    '— 120 would do',
              },
            ],
    });
  }
}

void main() {
  testWidgets('the catalogue dialog sends the order multiple', (tester) async {
    tester.view.physicalSize = const Size(1366, 768);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final _CatalogueApi api = _CatalogueApi();
    await tester.pumpWidget(MaterialApp(
      builder: (context, child) => Phase2Scope(child: child!),
      home: Scaffold(
        body: SingleChildScrollView(
          child: SupplierCatalogueSection(
            api: api,
            vendorId: 'v-1',
            canManage: true,
          ),
        ),
      ),
    ));
    await tester.pumpAndSettle();
    expect(find.text('Multiple'), findsOneWidget);
    expect(find.text('20'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('catalogue-add')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('catalogue-product')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('P001 Widget').last);
    await tester.pumpAndSettle();
    await tester.enterText(
        find.byKey(const ValueKey('catalogue-multiple')), '20');
    await tester.tap(find.byKey(const ValueKey('catalogue-save')));
    await tester.pumpAndSettle();
    expect(api.lastBody?['order_multiple'], '20');
  });

  testWidgets('the settings dialog sends the order quantity policy',
      (tester) async {
    tester.view.physicalSize = const Size(1366, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final _SettingsApi api = _SettingsApi();
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: PurchaseWorkflowSettingsDialog(
          api: api,
          permissions:
              _permissions(['PURCHASE_VIEW', 'PURCHASE_MANAGE_SETTINGS']),
        ),
      ),
    ));
    await tester.pumpAndSettle();
    final Finder choice = find.byKey(const ValueKey('order-quantity-policy'));
    await tester.ensureVisible(choice);
    await tester.tap(choice);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Refuse').last);
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();
    expect(api.saved.single['order_quantity_policy'], 'REFUSE');
  });

  testWidgets('a quantity hint shows and "Use 120" sets the quantity',
      (tester) async {
    tester.view.physicalSize = const Size(1600, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final _OrderApi api = _OrderApi();
    final Json vendor = <String, dynamic>{
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
    };
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Phase2Scope(
          child: PurchaseOrderEditorDialog(
            api: api,
            permissions: _permissions(['PURCHASE_VIEW', 'PURCHASE_CREATE']),
            mode: PurchaseDialogMode.create,
            order: null,
            vendors: <Vendor>[Vendor.fromJson(vendor)],
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
            products: <Product>[
              Product.fromJson(<String, dynamic>{
                'id': 'product-1',
                'firm_id': 'firm-1',
                'code': 'MED-001',
                'name': 'Pain Relief',
                'unit': 'BOX',
                'purchase_price': '100',
                'status': 'ACTIVE',
              }),
            ],
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
    await fillNewPurchaseOrder(
      tester,
      vendor: 'Northwind',
      product: 'Pain Relief',
    );

    expect(find.textContaining('120 would do'), findsOneWidget);
    await tester.tap(find.text('Use 120'));
    await tester.pump(const Duration(milliseconds: 400));
    await tester.pumpAndSettle();

    final Json line = api.previews.last['lines'][0] as Json;
    expect(line['ordered_quantity'], '120');
    expect(find.textContaining('120 would do'), findsNothing);
    expect(tester.takeException(), isNull);
  });
}
