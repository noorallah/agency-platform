// Supplier rates (BUY-3): what a supplier charges is agreed once and read by
// every purchase order.
//
// Three screens carry it, and each has a way to go quietly wrong:
//
// 1. The supplier record sends its standing discount, or the server never
//    hears of it.
// 2. A supplier's price list names the supplier -- and only the supplier --
//    because the server refuses a list that also names a customer.
// 3. A purchase order line sends **nothing** for a rate or a discount nobody
//    typed, because a figure the screen made up is a figure that overrides
//    the supplier's list. A typed zero is an answer and is sent.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/document_preview.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/geography.dart';
import 'package:agency_desktop/models/pricing.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/models/purchase.dart';
import 'package:agency_desktop/models/vendor.dart';
import 'package:agency_desktop/ui/pricing/price_list_dialog.dart';
import 'package:agency_desktop/ui/purchases/purchase_management_page.dart';
import 'package:agency_desktop/ui/vendors/vendor_management_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions(List<String> codes) => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': codes,
  }));

Json _vendorJson({String discount = '2.5'}) => <String, dynamic>{
      'id': 'vendor-1',
      'firm_id': 'firm-1',
      'code': 'V001',
      'name': 'Northwind Supplies',
      'display_name': 'Northwind Supplies',
      'status': 'ACTIVE',
      'standing_discount_percent': discount,
      'addresses': <Json>[],
      'contacts': <Json>[],
      'bank_accounts': <Json>[],
      'tax_details': <Json>[],
      'notes': <Json>[],
    };

// ---------------------------------------------------------------------------
// 1. The supplier record
// ---------------------------------------------------------------------------

class _VendorApi extends ApiClient {
  _VendorApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  Json? saved;

  @override
  Future<PagedResult<Vendor>> vendors({
    int page = 1,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    VendorQuery filters = const VendorQuery(),
  }) async =>
      PagedResult<Vendor>(
        items: <Vendor>[Vendor.fromJson(_vendorJson())],
        total: 1,
      );

  @override
  Future<List<GeoPlaceRecord>> geoPlaces(
    GeoLevel level, {
    String parentId = '',
  }) async =>
      const <GeoPlaceRecord>[];

  @override
  Future<Vendor> updateVendor(
    String id,
    Json data, {
    int? expectedVersion,
  }) async {
    saved = data;
    return Vendor.fromJson(_vendorJson());
  }
}

// ---------------------------------------------------------------------------
// 2. The price list
// ---------------------------------------------------------------------------

class _ListApi extends ApiClient {
  _ListApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  Json? saved;

  @override
  Future<PriceListRecord> createPriceList(Json body) async {
    saved = body;
    return PriceListRecord.fromJson(<String, dynamic>{
      'id': 'pl-1',
      'code': 'SUP1',
      'name': 'Northwind rates',
      'effective_from': '2026-10-01',
    });
  }
}

// ---------------------------------------------------------------------------
// 3. The purchase order
// ---------------------------------------------------------------------------

class _OrderApi extends ApiClient {
  _OrderApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Json> previews = <Json>[];
  PurchaseOrder? created;

  @override
  Future<PurchaseOrderPreviewRecord> previewPurchaseOrder(
    PurchaseOrder order,
  ) async {
    previews.add(order.toCreateJson());
    final PurchaseOrderLine line = order.lines.first;
    // The server fills what was left blank.
    final String rate = line.unitPrice.isEmpty ? '100' : line.unitPrice;
    final double gross = (double.tryParse(line.orderedQuantity) ?? 0) *
        (double.tryParse(rate) ?? 0);
    final Json priced = order.toCreateJson()
      ..['po_number'] = 'PO-0002'
      ..['subtotal'] = gross.toStringAsFixed(2)
      ..['line_discount_total'] = '0'
      ..['tax_total'] = '0'
      ..['grand_total'] = gross.toStringAsFixed(2)
      ..['lines'] = [
        {
          ...line.toWriteJson(),
          'unit_price': rate,
          'discount_percent':
              line.discountPercent.isEmpty ? '2.5' : line.discountPercent,
          'line_number': 1,
          'gross_amount': gross.toStringAsFixed(2),
          'discount_amount': '0',
          'tax_amount': '0',
          'net_amount': gross.toStringAsFixed(2),
        },
      ];
    return PurchaseOrderPreviewRecord(
      order: PurchaseOrder.fromJson(priced),
      interstate: false,
      lines: const <DocumentPreviewLine>[],
    );
  }

  @override
  Future<List<PurchaseOrderHistoryRecord>> purchaseOrderHistory(
    String id,
  ) async =>
      const <PurchaseOrderHistoryRecord>[];

  @override
  Future<PurchaseOrder> createPurchaseOrder(PurchaseOrder order) async {
    created = order;
    return order.copyWith(id: 'po-2', poNumber: 'PO-0002');
  }
}

Future<void> _pumpOrder(
  WidgetTester tester,
  _OrderApi api, {
  PurchaseOrder? order,
  PurchaseDialogMode mode = PurchaseDialogMode.create,
}) async {
  tester.view.physicalSize = const Size(1600, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Phase2Scope(
        child: PurchaseOrderEditorDialog(
          api: api,
          permissions: _permissions(['PURCHASE_VIEW', 'PURCHASE_CREATE']),
          mode: mode,
          order: order,
          vendors: <Vendor>[Vendor.fromJson(_vendorJson())],
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
}

void main() {
  testWidgets('the supplier record sends its standing discount',
      (tester) async {
    tester.view.physicalSize = const Size(1600, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final _VendorApi api = _VendorApi();
    await tester.pumpWidget(MaterialApp(
      builder: (context, child) => Phase2Scope(child: child!),
      home: Scaffold(
        body: VendorManagementPage(
          api: api,
          permissions:
              _permissions(['VENDOR_VIEW', 'VENDOR_CREATE', 'VENDOR_UPDATE']),
          hasActiveFirm: true,
        ),
      ),
    ));
    await tester.pumpAndSettle();
    await tester.tap(find.text('V001').first);
    await tester.pump(const Duration(milliseconds: 400));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Edit').first);
    await tester.pumpAndSettle();

    expect(find.text('Standing discount %'), findsOneWidget);
    expect(
      find.text('Taken off every purchase line that names no discount of '
          'its own'),
      findsOneWidget,
    );

    final Finder box = find.widgetWithText(TextField, 'Standing discount %');
    await tester.ensureVisible(box);
    await tester.enterText(box, '4');
    await tester.tap(find.byKey(const ValueKey('vendor-save')));
    await tester.pumpAndSettle();
    expect(api.saved?['standing_discount_percent'], 4);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a supplier-scoped price list sends the supplier and no other',
      (tester) async {
    tester.view.physicalSize = const Size(1700, 1400);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final _ListApi api = _ListApi();
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: PriceListDialog(
          api: api,
          customers: const [],
          products: const [],
          vendors: <Vendor>[Vendor.fromJson(_vendorJson())],
        ),
      ),
    ));
    await tester.pumpAndSettle();
    await tester.enterText(find.widgetWithText(TextFormField, 'Code'), 'SUP1');
    await tester.enterText(
        find.widgetWithText(TextFormField, 'Name'), 'Northwind rates');
    await tester.tap(find.text('One supplier'));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('price-list-supplier')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Northwind Supplies').last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();

    expect(api.saved?['vendor_id'], 'vendor-1');
    expect(api.saved?['customer_id'], isNull);
    expect(api.saved?['territory_id'], isNull);
    expect(tester.takeException(), isNull);
  });

  testWidgets('an untouched rate and discount are not sent', (tester) async {
    final _OrderApi api = _OrderApi();
    await _pumpOrder(tester, api);
    expect(tester.takeException(), isNull);

    // Nothing typed: the server is asked to fill both.
    expect(api.previews, isNotEmpty);
    final Json untouched = api.previews.last['lines'][0] as Json;
    expect(untouched.containsKey('unit_price'), isTrue);
    expect(untouched['unit_price'], isNull);
    expect(untouched['discount_percent'], isNull);

    // What a blank box takes is said under it.
    expect(
      find.text("Blank: the supplier's list price, else the product's "
          'purchase price'),
      findsOneWidget,
    );
    expect(
      find.text("Blank: the supplier's list rate, else its standing "
          'discount; 0 means none'),
      findsOneWidget,
    );

    await tester.tap(find.byKey(const ValueKey('purchase-order-save')));
    await tester.pumpAndSettle();
    final Json saved = api.created!.toCreateJson()['lines'][0] as Json;
    expect(saved['unit_price'], isNull);
    expect(saved['discount_percent'], isNull);
  });

  testWidgets('a discount typed as 0 is sent as 0', (tester) async {
    final _OrderApi api = _OrderApi();
    await _pumpOrder(tester, api);

    final Finder discount = find.byWidgetPredicate((Widget w) {
      final Key? key = w.key;
      return w is TextFormField &&
          key is ValueKey<String> &&
          key.value.startsWith('purchase-order-disc-') &&
          !key.value.startsWith('purchase-order-disc-amt');
    });
    await tester.enterText(discount.first, '0');
    await tester.pump(const Duration(milliseconds: 400));
    await tester.pumpAndSettle();
    final Json typed = api.previews.last['lines'][0] as Json;
    expect(typed['discount_percent'], '0');
    expect(typed['unit_price'], isNull);
  });

  testWidgets('a line remark is sent and shown again on reopen (D-BUY-21)',
      (tester) async {
    final _OrderApi api = _OrderApi();
    await _pumpOrder(tester, api);

    final Finder remark = find.byWidgetPredicate((Widget w) {
      final Key? key = w.key;
      return w is TextFormField &&
          key is ValueKey<String> &&
          key.value.startsWith('purchase-order-remarks-');
    });
    expect(remark, findsOneWidget);
    await tester.enterText(remark, 'Deliver to back gate');
    await tester.pump(const Duration(milliseconds: 400));
    await tester.pumpAndSettle();
    expect(
      (api.previews.last['lines'][0] as Json)['remarks'],
      'Deliver to back gate',
    );

    await tester.tap(find.byKey(const ValueKey('purchase-order-save')));
    await tester.pumpAndSettle();
    final Json saved = api.created!.toCreateJson()['lines'][0] as Json;
    expect(saved['remarks'], 'Deliver to back gate');

    // The saved order, opened again, shows the remark in its line.
    final PurchaseOrder reopened = PurchaseOrder.fromJson(<String, dynamic>{
      ...api.created!.toCreateJson(),
      'id': 'po-2',
      'po_number': 'PO-0002',
      'status': 'DRAFT',
    });
    await tester.pumpWidget(const SizedBox());
    final _OrderApi second = _OrderApi();
    await _pumpOrder(
      tester,
      second,
      order: reopened,
      mode: PurchaseDialogMode.edit,
    );
    expect(find.text('Deliver to back gate'), findsOneWidget);
  });
}
