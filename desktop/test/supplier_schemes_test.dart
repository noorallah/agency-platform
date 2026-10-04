// Supplier free schemes (PG-11): the list and the create body; the purchase
// order sending null for a blank free box and 0 for a typed 0; a scheme
// suggestion adding one gift line (with its scheme_id) and never a second;
// a suggestion that names a line updating it instead; and a free-only line
// being priced live and saved.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/models/purchase.dart';
import 'package:agency_desktop/models/vendor.dart';
import 'package:agency_desktop/ui/purchases/purchase_management_page.dart';
import 'package:agency_desktop/ui/purchases/supplier_scheme_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions(List<String> perms) => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': perms,
  }));

Json _scheme(String id, {String? vendor = 'v-1', bool active = true}) => {
      'id': id,
      'vendor_id': vendor,
      'vendor_code': vendor == null ? null : 'SG',
      'vendor_name': vendor == null ? null : 'Sri Ganesh Traders',
      'product_id': 'p-1',
      'product_code': 'RICE',
      'product_name': 'Basmati rice',
      'buy_quantity': '10.0000',
      'free_quantity': '2.0000',
      'free_product_id': null,
      'free_product_code': null,
      'free_product_name': null,
      'valid_from': '2026-10-01',
      'valid_to': null,
      'is_active': active,
      'notes': null,
      'label': '10+2',
      'in_force': active,
      'version': 3,
    };

class _Api extends ApiClient {
  _Api({this.suggestions = const <Json>[]})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  /// What every preview answers in `scheme_suggestions`.
  final List<Json> suggestions;
  final List<Json> previews = <Json>[];
  final Map<String, Json?> bodies = <String, Json?>{};

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
    switch (call) {
      case 'GET /api/v1/supplier-schemes':
        return {
          'data': [
            _scheme('1'),
            _scheme('2', vendor: null),
            _scheme('3', active: false),
          ],
          'pagination': {'total_records': 3},
        };
      case 'POST /api/v1/supplier-schemes':
        return {'data': _scheme('9')};
      case 'POST /api/v1/purchases/preview':
        previews.add(body!);
        return {
          'data': {
            'order': {
              'id': 'po-1',
              'po_number': 'PO-0001',
              'status': 'DRAFT',
              'vendor_id': 'vendor-1',
              'branch_id': 'branch-1',
              'warehouse_id': 'warehouse-1',
              'lines': <Json>[],
            },
            'interstate': false,
            'lines': <Json>[],
            'scheme_suggestions': suggestions,
          },
        };
      case 'PUT /api/v1/purchases/po-1':
        return {'data': _orderJson()};
    }
    if (path == '/api/v1/vendors') {
      return {
        'data': [
          {'id': 'v-1', 'code': 'SG', 'name': 'Sri Ganesh Traders'},
        ],
        'pagination': {'total_records': 1},
      };
    }
    if (path == '/api/v1/products') {
      return {
        'data': [
          {'id': 'p-1', 'code': 'RICE', 'name': 'Basmati rice'},
        ],
        'pagination': {'total_records': 1},
      };
    }
    return {'data': const <dynamic>[]};
  }
}

Json _orderJson() => {
      'id': 'po-1',
      'firm_id': 'firm-1',
      'branch_id': 'branch-1',
      'warehouse_id': 'warehouse-1',
      'vendor_id': 'vendor-1',
      'po_number': 'PO-0001',
      'purchase_date': '2026-10-01',
      'status': 'DRAFT',
      'grand_total': '500.00',
      'lines': [
        {
          'id': 'line-1',
          'line_number': 1,
          'product_id': 'product-1',
          'ordered_quantity': '10',
          'free_quantity': null,
          'unit_price': '100',
          'discount_percent': '0',
          'net_amount': '1000.00',
        },
      ],
    };

Json _suggestion({int? existing, String product = 'product-2'}) => {
      'line_number': 1,
      'scheme_id': 's-1',
      'scheme_label': '10+2',
      'free_product_id': product,
      'free_product_code': 'MED-002',
      'free_product_name': 'Cough Syrup',
      'free_quantity': '2.0000',
      'existing_line_number': existing,
    };

Future<void> _pumpList(WidgetTester tester, _Api api) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final DesktopPreferencesService preferences = DesktopPreferencesService(
    directory: Directory.systemTemp.createTempSync('supplier-schemes'),
  );
  await tester.pumpWidget(MaterialApp(
    builder: (context, child) => Phase2Scope(child: child!),
    home: Scaffold(
      body: SupplierSchemePage(
        api: api,
        preferences: preferences,
        permissions:
            _permissions(['SUPPLIER_SCHEME_VIEW', 'SUPPLIER_SCHEME_MANAGE']),
        hasActiveFirm: true,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

Product _product(String id, String code, String name) =>
    Product.fromJson(<String, dynamic>{
      'id': id,
      'firm_id': 'firm-1',
      'code': code,
      'name': name,
      'unit': 'BOX',
      'purchase_price': '100',
      'status': 'ACTIVE',
    });

Future<void> _pumpOrder(WidgetTester tester, _Api api) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Phase2Scope(
        child: PurchaseOrderEditorDialog(
          api: api,
          permissions: PermissionService(),
          mode: PurchaseDialogMode.edit,
          order: PurchaseOrder.fromJson(_orderJson()),
          vendors: <Vendor>[
            Vendor.fromJson(<String, dynamic>{
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
            }),
          ],
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
            _product('product-1', 'MED-001', 'Pain Relief'),
            _product('product-2', 'MED-002', 'Cough Syrup'),
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
  await _settlePreview(tester);
}

/// The preview waits for typing to pause; let it fire and land.
Future<void> _settlePreview(WidgetTester tester) async {
  await tester.pump(const Duration(milliseconds: 400));
  await tester.pumpAndSettle();
}

Finder _box(String name, int line) => find.byWidgetPredicate((widget) =>
    widget.key is ValueKey<String> &&
    RegExp('^purchase-order-$name-[0-9]+-$line-').hasMatch(
      (widget.key! as ValueKey<String>).value,
    ));

Finder _freeBox(int line) => _box('free', line);

Finder _qtyBox(int line) => _box('qty', line);

List<dynamic> _sentLines(Json body) => body['lines'] as List<dynamic>;

void main() {
  testWidgets('the list shows the label, supplier and status', (tester) async {
    await _pumpList(tester, _Api());

    expect(find.text('10+2'), findsWidgets);
    expect(find.text('Sri Ganesh Traders'), findsNWidgets(2));
    expect(find.text('All suppliers'), findsOneWidget);
    expect(find.text('Same product'), findsWidgets);
    expect(find.text('Open'), findsWidgets);
    expect(find.text('In force'), findsWidgets);
    expect(find.text('Switched off'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('creating sends exactly the declared fields', (tester) async {
    final _Api api = _Api();
    await _pumpList(tester, api);

    await tester.tap(find.byKey(const ValueKey('toolbar-new')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const ValueKey('ss-product')), 'Rice');
    await tester.pumpAndSettle();
    await tester.tap(find.text('RICE · Basmati rice').last);
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const ValueKey('ss-buy')), '10');
    await tester.enterText(find.byKey(const ValueKey('ss-free')), '2');
    await tester.tap(find.byKey(const ValueKey('ss-save')));
    await tester.pumpAndSettle();

    final Json sent = api.bodies['POST /api/v1/supplier-schemes']!;
    expect(
      sent.keys.toSet(),
      <String>{
        'vendor_id',
        'product_id',
        'buy_quantity',
        'free_quantity',
        'free_product_id',
        'valid_from',
        'valid_to',
        'is_active',
        'notes',
      },
    );
    expect(sent['vendor_id'], isNull);
    expect(sent['free_product_id'], isNull);
    expect(sent['valid_to'], isNull);
    expect(sent['product_id'], 'p-1');
    expect(sent['buy_quantity'], '10');
    expect(sent['free_quantity'], '2');
    expect(sent['is_active'], true);
    expect(find.byType(SupplierSchemeDialog), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a blank free box is sent as null and a typed 0 as 0',
      (tester) async {
    final _Api api = _Api();
    await _pumpOrder(tester, api);

    expect(api.previews, isNotEmpty);
    expect(_sentLines(api.previews.last).single['free_quantity'], isNull);

    await tester.enterText(_freeBox(0), '0');
    await _settlePreview(tester);

    expect(_sentLines(api.previews.last).single['free_quantity'], '0');
    expect(tester.takeException(), isNull);
  });

  testWidgets('a suggestion adds one gift line with its scheme, once',
      (tester) async {
    final _Api api = _Api(suggestions: [_suggestion()]);
    await _pumpOrder(tester, api);
    await _settlePreview(tester);

    final List<dynamic> lines = _sentLines(api.previews.last);
    expect(lines, hasLength(2));
    final Json gift = lines.last as Json;
    expect(gift['product_id'], 'product-2');
    expect(gift['ordered_quantity'], '0');
    expect(gift['free_quantity'], '2');
    expect(gift['scheme_id'], 's-1');
    // The paid line never names a scheme.
    expect((lines.first as Json).containsKey('scheme_id'), isFalse);
    expect(find.text('Line 2: Scheme 10+2 applied'), findsOneWidget);

    // Several more previews answer the same suggestion: still one gift line.
    await tester.enterText(_qtyBox(0), '20');
    await _settlePreview(tester);
    await _settlePreview(tester);
    expect(_sentLines(api.previews.last), hasLength(2));

    // And it is saved with the order.
    await tester.tap(find.byKey(const ValueKey('purchase-order-save')));
    await tester.pumpAndSettle();
    final List<dynamic> saved =
        _sentLines(api.bodies['PUT /api/v1/purchases/po-1']!);
    expect(saved, hasLength(2));
    expect((saved.last as Json)['scheme_id'], 's-1');
    expect((saved.last as Json)['ordered_quantity'], '0');
    expect(tester.takeException(), isNull);
  });

  testWidgets('a suggestion naming a line updates its free box',
      (tester) async {
    final _Api api =
        _Api(suggestions: [_suggestion(existing: 1, product: 'product-1')]);
    await _pumpOrder(tester, api);
    await _settlePreview(tester);

    final List<dynamic> lines = _sentLines(api.previews.last);
    expect(lines, hasLength(1));
    expect((lines.single as Json)['free_quantity'], '2');
    expect((lines.single as Json).containsKey('scheme_id'), isFalse);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a free-only line is priced live and kept', (tester) async {
    final _Api api = _Api();
    await _pumpOrder(tester, api);
    final int before = api.previews.length;

    await tester.enterText(_qtyBox(0), '0');
    await tester.enterText(_freeBox(0), '3');
    await _settlePreview(tester);

    expect(api.previews.length, greaterThan(before));
    final Json line = _sentLines(api.previews.last).single as Json;
    expect(line['ordered_quantity'], '0');
    expect(line['free_quantity'], '3');
    expect(tester.takeException(), isNull);
  });
}
