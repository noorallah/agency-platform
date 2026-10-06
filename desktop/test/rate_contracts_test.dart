// Rate contracts (PG-9): the list, the create body (a blank discount is left
// out, never sent as 0), approve and cancel, the releases list, the purchase
// order's rate-contract label and over-draw banner, and no overflow at the two
// sizes the desktop is held to.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/models/purchase.dart';
import 'package:agency_desktop/models/vendor.dart';
import 'package:agency_desktop/ui/purchases/purchase_management_page.dart';
import 'package:agency_desktop/ui/purchases/rate_contract_page.dart';
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

Json _contract(String id, String status) => {
      'id': id,
      'contract_number': 'RC-$id',
      'vendor_id': 'v-1',
      'vendor_code': 'SG',
      'vendor_name': 'Sri Ganesh Traders',
      'valid_from': '2026-10-01',
      'valid_to': '2027-03-31',
      'reference': null,
      'notes': null,
      'status': status,
      'approved_at': null,
      'closed_at': null,
      'cancel_reason': null,
      'version': 2,
      'lines': [
        {
          'id': 'cl-1',
          'line_number': 1,
          'product_id': 'p-1',
          'product_code': 'RICE',
          'product_name': 'Basmati rice',
          'uom_id': null,
          'rate': '92.0000',
          'discount_percent': '0.0000',
          'contracted_quantity': '100.0000',
          'drawn_quantity': '40.0000',
          'remaining_quantity': '60.0000',
          'notes': null,
        },
      ],
    };

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
  final Map<String, Map<String, String>?> queries =
      <String, Map<String, String>?>{};

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
    queries[call] = query;
    switch (call) {
      case 'GET /api/v1/rate-contracts':
        return {
          'data': [
            _contract('1', 'DRAFT'),
            _contract('2', 'ACTIVE'),
            _contract('3', 'EXPIRED'),
          ],
          'pagination': {'total_records': 3},
        };
      case 'GET /api/v1/rate-contracts/1':
        return {'data': _contract('1', 'DRAFT')};
      case 'GET /api/v1/rate-contracts/2':
        return {'data': _contract('2', 'ACTIVE')};
      case 'POST /api/v1/rate-contracts':
        return {'data': _contract('9', 'DRAFT')};
      case 'POST /api/v1/rate-contracts/1/approve':
        return {'data': _contract('1', 'ACTIVE')};
      case 'POST /api/v1/rate-contracts/2/cancel':
        return {'data': _contract('2', 'CANCELLED')};
      case 'GET /api/v1/rate-contracts/2/releases':
        return {
          'data': [
            {
              'purchase_order_id': 'po-1',
              'po_number': 'PO-0042',
              'purchase_date': '2026-10-06',
              'order_status': 'APPROVED',
              'counts_as_drawn': true,
              'purchase_order_line_id': 'pl-1',
              'line_number': 1,
              'rate_contract_line_id': 'cl-1',
              'product_id': 'p-1',
              'ordered_quantity': '40.0000',
              'unit_price': '92.0000',
            },
          ],
        };
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

const List<String> _all = [
  'RATE_CONTRACT_VIEW',
  'RATE_CONTRACT_MANAGE',
  'PURCHASE_APPROVE',
];

Future<void> _pump(
  WidgetTester tester,
  _Api api, {
  Size size = const Size(1366, 768),
  List<String> perms = _all,
}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final DesktopPreferencesService preferences = DesktopPreferencesService(
    directory: Directory.systemTemp.createTempSync('rate-contracts'),
  );
  await tester.pumpWidget(MaterialApp(
    builder: (context, child) => Phase2Scope(child: child!),
    home: Scaffold(
      body: RateContractPage(
        api: api,
        preferences: preferences,
        permissions: _permissions(perms),
        hasActiveFirm: true,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

Future<void> _select(WidgetTester tester, String number) async {
  await tester.tap(find.text(number).first);
  await tester.pump(const Duration(milliseconds: 500));
  await tester.pumpAndSettle();
}

Future<void> _command(WidgetTester tester, String id) async {
  await tester.tap(find.byKey(ValueKey('selection-$id')));
  await tester.pumpAndSettle();
}

PurchaseOrder _order({String? warning, String? source}) =>
    PurchaseOrder.fromJson({
      'id': 'po-1',
      'po_number': 'PO-0042',
      'status': 'APPROVED',
      'vendor_id': 'vendor-1',
      'branch_id': 'branch-1',
      'warehouse_id': 'warehouse-1',
      'rate_contract_warning': warning,
      'lines': [
        {
          'id': 'pl-1',
          'line_number': 1,
          'product_id': 'product-1',
          'ordered_quantity': '150',
          'unit_price': '92',
          'rate_source': source,
          'rate_contract_line_id': source == null ? null : 'cl-1',
        },
      ],
    });

Future<void> _pumpOrder(WidgetTester tester, PurchaseOrder order,
    {Size size = const Size(1600, 900)}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    builder: (context, child) => Phase2Scope(child: child!),
    home: Scaffold(
      body: PurchaseOrderEditorDialog(
        api: _Api(),
        permissions: _permissions(const ['PURCHASE_VIEW']),
        mode: PurchaseDialogMode.view,
        order: order,
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
        canSubmit: false,
        canApprove: false,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('the list shows number, supplier, window, status and lines',
      (tester) async {
    final _Api api = _Api();
    await _pump(tester, api);

    expect(find.text('RC-1'), findsOneWidget);
    expect(find.text('RC-3'), findsOneWidget);
    expect(find.text('Sri Ganesh Traders'), findsWidgets);
    expect(find.text('2027-03-31'), findsWidgets);
    expect(find.text('Draft'), findsOneWidget);
    expect(find.text('Active'), findsOneWidget);
    expect(find.text('Expired'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('the status and supplier filters reach the query',
      (tester) async {
    final _Api api = _Api();
    await _pump(tester, api);

    await tester.tap(find.byKey(const ValueKey('rc-status-filter')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Active').last);
    await tester.pumpAndSettle();
    expect(api.queries['GET /api/v1/rate-contracts']!['status'], 'ACTIVE');

    await tester.tap(find.byKey(const ValueKey('rc-vendor-filter')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Sri Ganesh Traders').last);
    await tester.pumpAndSettle();
    expect(api.queries['GET /api/v1/rate-contracts']!['vendor_id'], 'v-1');
  });

  testWidgets('creating sends the declared fields and omits a blank discount',
      (tester) async {
    final _Api api = _Api();
    await _pump(tester, api);

    await tester.tap(find.byKey(const ValueKey('toolbar-new')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('rc-vendor')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Sri Ganesh Traders').last);
    await tester.pumpAndSettle();
    // The window's end is a date pick; accept the dialog's default day.
    await tester.tap(find.byKey(const ValueKey('rc-valid-to')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('OK'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const ValueKey('rc-product-0')), 'Rice');
    await tester.pumpAndSettle();
    await tester.tap(find.text('RICE · Basmati rice').last);
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const ValueKey('rc-rate-0')), '92');
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('rc-save')));
    await tester.pumpAndSettle();

    final Json sent = api.bodies['POST /api/v1/rate-contracts']!;
    expect(
        sent.keys.toSet(),
        <String>{
          'vendor_id',
          'valid_from',
          'valid_to',
          'lines',
        });
    final Json line = (sent['lines'] as List<dynamic>).single as Json;
    expect(line['product_id'], 'p-1');
    expect(line['rate'], '92');
    expect(line.containsKey('discount_percent'), isFalse);
    expect(line.containsKey('contracted_quantity'), isFalse);
    expect(find.byType(RateContractDialog), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('an active contract opens read-only with drawn and remaining',
      (tester) async {
    await _pump(tester, _Api());

    await _select(tester, 'RC-2');
    await tester.tap(find.byKey(const ValueKey('selection-edit')));
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('rc-read-only')), findsOneWidget);
    expect(find.byKey(const ValueKey('rc-save')), findsNothing);
    expect(find.text('40.0000'), findsOneWidget);
    expect(find.text('60.0000'), findsOneWidget);
  });

  testWidgets('approve calls the api; cancel asks for a reason and sends it',
      (tester) async {
    final _Api api = _Api();
    await _pump(tester, api);

    await _select(tester, 'RC-1');
    await _command(tester, 'approve');
    expect(api.calls, contains('POST /api/v1/rate-contracts/1/approve'));

    await _select(tester, 'RC-2');
    await _command(tester, 'cancel');
    await tester.enterText(find.byType(TextField).last, 'Prices revised');
    await tester.pump();
    await tester.tap(find.text('Cancel contract'));
    await tester.pumpAndSettle();
    expect(api.calls, contains('POST /api/v1/rate-contracts/2/cancel'));
    expect(api.bodies['POST /api/v1/rate-contracts/2/cancel'],
        {'reason': 'Prices revised'});
  });

  testWidgets('a draft can be deleted', (tester) async {
    final _Api api = _Api();
    await _pump(tester, api);

    await _select(tester, 'RC-1');
    await _command(tester, 'delete');
    await tester.tap(find.byKey(const ValueKey('rc-delete-confirm')));
    await tester.pumpAndSettle();
    expect(api.calls, contains('DELETE /api/v1/rate-contracts/1'));
  });

  testWidgets('releases lists the purchase order lines that drew',
      (tester) async {
    await _pump(tester, _Api());

    await _select(tester, 'RC-2');
    await _command(tester, 'releases');

    expect(find.byType(RateContractReleasesDialog), findsOneWidget);
    expect(find.textContaining('PO-0042'), findsOneWidget);
    expect(find.text('Basmati rice'), findsOneWidget);
    expect(find.textContaining('40.0000 @ 92.0000'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('without the view permission the list is locked',
      (tester) async {
    final _Api api = _Api();
    await _pump(tester, api, perms: const ['PURCHASE_VIEW']);
    expect(find.text('You cannot see rate contracts'), findsOneWidget);
    expect(api.calls, isNot(contains('GET /api/v1/rate-contracts')));
  });

  testWidgets('a purchase order shows the over-draw warning and the source',
      (tester) async {
    await _pumpOrder(
      tester,
      _order(
        warning: 'This order takes RICE 50 over the contracted quantity.',
        source: 'RATE_CONTRACT',
      ),
    );
    expect(find.byKey(const ValueKey('rate-contract-warning')), findsOneWidget);
    expect(find.textContaining('over the contracted quantity'), findsOneWidget);
    expect(find.byKey(const ValueKey('po-rate-contract-0')), findsOneWidget);
    expect(find.textContaining('Rate contract: from the rate agreed'),
        findsOneWidget);
  });

  testWidgets('a purchase order with no warning or contract shows neither',
      (tester) async {
    await _pumpOrder(tester, _order(source: 'TYPED'));
    expect(find.byKey(const ValueKey('rate-contract-warning')), findsNothing);
    expect(find.byKey(const ValueKey('po-rate-contract-0')), findsNothing);
  });

  testWidgets('the purchase order with a warning does not overflow at 1366x768',
      (tester) async {
    await _pumpOrder(
      tester,
      _order(warning: 'Over the contracted quantity.', source: 'RATE_CONTRACT'),
      size: const Size(1366, 768),
    );
    expect(tester.takeException(), isNull);
  });

  for (final Size size in const [Size(1366, 768), Size(800, 600)]) {
    testWidgets('no overflow at ${size.width.toInt()}x${size.height.toInt()}',
        (tester) async {
      final _Api api = _Api();
      await _pump(tester, api, size: size);
      expect(tester.takeException(), isNull);

      await tester.tap(find.byKey(const ValueKey('toolbar-new')));
      await tester.pumpAndSettle();
      expect(find.byType(RateContractDialog), findsOneWidget);
      expect(tester.takeException(), isNull);
      await tester.tap(find.text('Cancel'));
      await tester.pumpAndSettle();

      await _select(tester, 'RC-2');
      await tester.tap(find.byKey(const ValueKey('selection-edit')));
      await tester.pumpAndSettle();
      expect(find.byType(RateContractDialog), findsOneWidget);
      expect(tester.takeException(), isNull);
      await tester.tap(find.descendant(
          of: find.byType(RateContractDialog), matching: find.text('Close')));
      await tester.pumpAndSettle();

      await _command(tester, 'releases');
      expect(find.byType(RateContractReleasesDialog), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

  }
}
