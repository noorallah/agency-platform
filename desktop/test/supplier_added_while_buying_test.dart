// Backlog 128 (M10): a supplier who is not in the list yet is added from the
// buying document being typed. The supplier form opens over the document,
// saves through the same create call as the Suppliers screen, and the
// document comes back with the new supplier chosen and what was typed kept.
// Offered only to somebody holding `VENDOR_CREATE`, and a firm with no
// supplier at all can start its first order this way.

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/models/purchase.dart';
import 'package:agency_desktop/models/vendor.dart';
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

  final List<String> calls = <String>[];
  final Map<String, Json?> bodies = <String, Json?>{};

  /// Answer the create with the server's refusal.
  bool refuseVendor = false;

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
    if (call == 'POST /api/v1/vendors') {
      if (refuseVendor) {
        throw const ApiException(
          'A vendor with this code already exists.',
          statusCode: 409,
        );
      }
      return {
        'data': _vendorJson('vendor-2', 'V002', '${body!['name']}'),
      };
    }
    if (call == 'POST /api/v1/purchases') {
      return {
        'data': {
          'id': 'po-1',
          'firm_id': 'firm-1',
          'branch_id': 'branch-1',
          'warehouse_id': 'warehouse-1',
          'vendor_id': '${body!['vendor_id']}',
          'po_number': 'PO-0001',
          'purchase_date': '2026-10-01',
          'status': 'DRAFT',
          'lines': <Json>[],
        },
      };
    }
    if (call == 'POST /api/v1/purchases/preview') {
      return {
        'data': {
          'order': {
            'id': 'po-1',
            'po_number': 'PO-0001',
            'status': 'DRAFT',
            'vendor_id': '${body!['vendor_id'] ?? ''}',
            'branch_id': 'branch-1',
            'warehouse_id': 'warehouse-1',
            'lines': <Json>[],
          },
          'interstate': false,
          'lines': <Json>[],
        },
      };
    }
    return {'data': const <dynamic>[]};
  }
}

Json _vendorJson(String id, String code, String name) => <String, dynamic>{
      'id': id,
      'firm_id': 'firm-1',
      'code': code,
      'name': name,
      'display_name': name,
      'status': 'ACTIVE',
      'addresses': <Json>[],
      'contacts': <Json>[],
      'bank_accounts': <Json>[],
      'tax_details': <Json>[],
      'notes': <Json>[],
    };

final Product _product = Product.fromJson(<String, dynamic>{
  'id': 'product-1',
  'firm_id': 'firm-1',
  'code': 'MED-001',
  'name': 'Pain Relief',
  'unit': 'BOX',
  'purchase_price': '100',
  'status': 'ACTIVE',
});

Future<List<Vendor>> _pumpOrder(
  WidgetTester tester,
  _Api api, {
  bool canAddVendor = true,
  bool withVendor = true,
}) async {
  tester.view.physicalSize = const Size(1600, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final List<Vendor> told = <Vendor>[];
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Phase2Scope(
        child: PurchaseOrderEditorDialog(
          api: api,
          permissions: PermissionService(),
          mode: PurchaseDialogMode.create,
          order: null,
          vendors: <Vendor>[
            if (withVendor)
              Vendor.fromJson(
                  _vendorJson('vendor-1', 'V001', 'Northwind Supplies')),
          ],
          canAddVendor: canAddVendor,
          onVendorAdded: told.add,
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
          products: <Product>[_product],
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
  return told;
}

Future<void> _pumpBill(
  WidgetTester tester,
  _Api api, {
  bool canAddVendor = true,
  PurchaseWorkflowSettings stages = const PurchaseWorkflowSettings(
    purchaseOrderStage: false,
    goodsReceiptStage: false,
    isConfigured: true,
  ),
}) async {
  tester.view.physicalSize = const Size(1600, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Phase2Scope(
        child: PurchaseInvoiceEditorDialog(
          api: api,
          receipts: const [],
          products: <Product>[_product],
          stages: stages,
          vendors: <Vendor>[
            Vendor.fromJson(
                _vendorJson('vendor-1', 'V001', 'Northwind Supplies')),
          ],
          canAddVendor: canAddVendor,
        ),
      ),
    ),
  ));
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
Future<void> _saveSupplier(WidgetTester tester, String name) async {
  await tester.enterText(find.widgetWithText(TextField, 'Vendor Name'), name);
  await tester.tap(find.byKey(const ValueKey('vendor-save')));
  await tester.pumpAndSettle();
  await tester.pump(const Duration(milliseconds: 400));
  await tester.pumpAndSettle();
}

const ValueKey<String> _orderButton = ValueKey('purchase-order-new-supplier');
const ValueKey<String> _billButton = ValueKey('purchase-invoice-new-supplier');

void main() {
  group('on a purchase order', () {
    testWidgets('a new supplier is saved and chosen, and the order kept',
        (tester) async {
      final _Api api = _Api();
      final List<Vendor> told = await _pumpOrder(tester, api);
      // Something typed on the order before the supplier is added.
      await tester.tap(_keyed('purchase-order-line-product-').first);
      await tester.pumpAndSettle();
      await tester.tap(find.textContaining('Pain Relief').last);
      await tester.pumpAndSettle();
      await tester.enterText(_keyed('purchase-order-qty-').first, '7');
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(_orderButton));
      await tester.pumpAndSettle();
      expect(find.widgetWithText(TextField, 'Vendor Name'), findsOneWidget);
      await _saveSupplier(tester, 'Coastal Traders');
      expect(tester.takeException(), isNull);

      // One create call, with the name typed.
      expect(
        api.calls.where((call) => call == 'POST /api/v1/vendors').length,
        1,
      );
      expect(api.bodies['POST /api/v1/vendors']!['name'], 'Coastal Traders');
      // The form is gone, the order is back, and the supplier box names him.
      expect(find.byKey(const ValueKey('vendor-save')), findsNothing);
      expect(find.byKey(_orderButton), findsOneWidget);
      expect(
        _text(tester, _keyed('purchase-order-vendor')),
        contains('Coastal Traders'),
      );
      expect(told.map((vendor) => vendor.id), <String>['vendor-2']);

      await tester.tap(find.byKey(const ValueKey('purchase-order-save')));
      await tester.pumpAndSettle();
      final Json saved = api.bodies['POST /api/v1/purchases']!;
      expect(saved['vendor_id'], 'vendor-2');
      final List<dynamic> lines = saved['lines'] as List<dynamic>;
      expect((lines.single as Json)['product_id'], 'product-1');
      expect(tester.takeException(), isNull);
    });

    testWidgets('closing the form without saving changes nothing',
        (tester) async {
      final _Api api = _Api();
      final List<Vendor> told = await _pumpOrder(tester, api);
      await tester.tap(find.byKey(_orderButton));
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(TextButton, 'Cancel'));
      await tester.pumpAndSettle();

      expect(api.calls, isNot(contains('POST /api/v1/vendors')));
      expect(find.byKey(_orderButton), findsOneWidget);
      expect(_text(tester, _keyed('purchase-order-vendor')), isEmpty);
      expect(told, isEmpty);
      expect(tester.takeException(), isNull);
    });

    testWidgets('a refusal stays in the form with the server message',
        (tester) async {
      final _Api api = _Api()..refuseVendor = true;
      final List<Vendor> told = await _pumpOrder(tester, api);
      await tester.tap(find.byKey(_orderButton));
      await tester.pumpAndSettle();
      await _saveSupplier(tester, 'Coastal Traders');

      expect(find.byKey(const ValueKey('vendor-save')), findsOneWidget);
      expect(
        find.textContaining('A vendor with this code already exists.'),
        findsWidgets,
      );
      expect(told, isEmpty);
      expect(tester.takeException(), isNull);
    });

    testWidgets('not offered without VENDOR_CREATE', (tester) async {
      await _pumpOrder(tester, _Api(), canAddVendor: false);
      expect(find.byKey(_orderButton), findsNothing);
      expect(find.byKey(const ValueKey('purchase-order-vendor')),
          findsOneWidget);
    });

    testWidgets('a firm with no supplier yet starts its first order',
        (tester) async {
      final _Api api = _Api();
      await _pumpOrder(tester, api, withVendor: false);
      expect(find.text('Nothing to order yet'), findsNothing);
      await tester.tap(find.byKey(_orderButton));
      await tester.pumpAndSettle();
      await _saveSupplier(tester, 'First Supplier');
      expect(
        _text(tester, _keyed('purchase-order-vendor')),
        contains('First Supplier'),
      );
      expect(tester.takeException(), isNull);
    });

    testWidgets('with no supplier and no right to add one, nothing to order',
        (tester) async {
      await _pumpOrder(tester, _Api(), withVendor: false, canAddVendor: false);
      expect(find.text('Nothing to order yet'), findsOneWidget);
    });
  });

  group('on a supplier bill typed directly', () {
    testWidgets('a new supplier is saved and chosen', (tester) async {
      final _Api api = _Api();
      await _pumpBill(tester, api);
      await tester.tap(find.byKey(_billButton));
      await tester.pumpAndSettle();
      await _saveSupplier(tester, 'Coastal Traders');

      expect(api.bodies['POST /api/v1/vendors']!['name'], 'Coastal Traders');
      expect(find.byKey(const ValueKey('vendor-save')), findsNothing);
      expect(
        _text(tester, _keyed('purchase-invoice-vendor')),
        contains('Coastal Traders'),
      );
      expect(tester.takeException(), isNull);
    });

    testWidgets('not offered without VENDOR_CREATE', (tester) async {
      await _pumpBill(tester, _Api(), canAddVendor: false);
      expect(find.byKey(_billButton), findsNothing);
      expect(find.byKey(const ValueKey('purchase-invoice-vendor')),
          findsOneWidget);
    });

    testWidgets('not offered on a bill that names a receipt', (tester) async {
      await _pumpBill(
        tester,
        _Api(),
        stages: PurchaseWorkflowSettings.wholeChain,
      );
      expect(find.byKey(_billButton), findsNothing);
    });
  });
}
