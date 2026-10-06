// Landed cost vouchers (BUY-16): the grid and details pane read a voucher, a
// new voucher is posted with exactly the declared keys, and a posted voucher
// is cancelled with a reason.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/goods_receipt.dart';
import 'package:agency_desktop/models/vendor.dart';
import 'package:agency_desktop/ui/purchases/landed_costs_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions({bool manage = true}) => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': <String>[
      'PURCHASE_VIEW',
      if (manage) 'PURCHASE_APPROVE',
    ],
  }));

Json _voucher({String id = 'lc-1', String status = 'POSTED'}) =>
    <String, dynamic>{
      'id': id,
      'voucher_number': 'LC-$id',
      'voucher_date': '2026-10-03',
      'basis': 'VALUE',
      'total_amount': '1200.00',
      'inventory_amount': '900.00',
      'cogs_amount': '300.00',
      'status': status,
      'remarks': null,
      'cancel_reason': null,
      'version': 1,
      'charges': [
        {
          'line_number': 1,
          'description': 'Inbound freight',
          'amount': '1200.00',
          'vendor_id': null,
          'vendor_name': null,
          'bill_reference': 'TR-77',
        },
      ],
      'allocations': [
        {
          'goods_receipt_id': 'grn-1',
          'grn_number': 'GRN-0001',
          'goods_receipt_line_id': 'gl-1',
          'product_id': 'p-1',
          'product_name': 'Glucose 500g',
          'quantity': '40',
          'basis_measure': '4000',
          'amount': '1200.00',
          'inventory_amount': '900.00',
          'cogs_amount': '300.00',
        },
      ],
    };

GoodsReceiptRecord _receipt() => GoodsReceiptRecord.fromJson({
      'id': 'grn-1',
      'grn_number': 'GRN-0001',
      'receipt_date': '2026-09-20',
      'status': 'COMPLETED',
      'vendor_id': 'vendor-1',
      'vendor_name': 'Medico Distributors',
      'branch_id': 'branch-1',
      'lines': const <Json>[],
    });

class _Api extends ApiClient {
  _Api({this.vouchers = const []})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Json> vouchers;
  final List<String> requested = <String>[];
  Json? posted;
  Json? cancelled;

  @override
  Future<PagedResult<GoodsReceiptRecord>> goodsReceipts({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    Map<String, String> filters = const {},
  }) async {
    requested.add('receipts ${filters['status']}');
    return PagedResult<GoodsReceiptRecord>(items: [_receipt()], total: 1);
  }

  @override
  Future<PagedResult<Vendor>> vendors({
    int page = 1,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    VendorQuery filters = const VendorQuery(),
  }) async =>
      const PagedResult<Vendor>(items: [], total: 0);

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
    requested.add('$method $path');
    if (method == 'POST' && path == '/api/v1/landed-costs') {
      posted = body;
      return <String, dynamic>{'data': _voucher(id: 'lc-new')};
    }
    if (method == 'POST' && path.endsWith('/cancel')) {
      cancelled = body;
      return <String, dynamic>{'data': _voucher(status: 'CANCELLED')};
    }
    if (method == 'GET' && path.startsWith('/api/v1/landed-costs/')) {
      final String id = path.split('/').last;
      return <String, dynamic>{
        'data': vouchers.where((row) => row['id'] == id).firstOrNull ??
            _voucher(id: id),
      };
    }
    if (method == 'GET' && path == '/api/v1/landed-costs') {
      return <String, dynamic>{'data': vouchers};
    }
    return <String, dynamic>{'data': const <Json>[]};
  }
}

DesktopPreferencesService _preferences() => DesktopPreferencesService(
      directory: Directory.systemTemp.createTempSync('landed-costs'),
    );

Future<void> _pump(WidgetTester tester, _Api api, {bool manage = true}) async {
  tester.view.physicalSize = const Size(1600, 1000);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    builder: (context, child) => Phase2Scope(child: child!),
    home: Scaffold(
      body: LandedCostsPage(
        api: api,
        preferences: _preferences(),
        permissions: _permissions(manage: manage),
        hasActiveFirm: true,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('the grid lists a voucher and the details show where it went',
      (tester) async {
    final _Api api = _Api(vouchers: [_voucher()]);
    await _pump(tester, api);
    expect(find.text('LC-lc-1'), findsOneWidget);
    expect(find.text('By value'), findsOneWidget);

    await tester.tap(find.text('LC-lc-1').first);
    await tester.pump(const Duration(milliseconds: 500));
    await tester.pumpAndSettle();
    expect(api.requested, contains('GET /api/v1/landed-costs/lc-1'));
    expect(find.byKey(const ValueKey('landed-cost-details')), findsOneWidget);
    expect(find.text('Inbound freight'), findsOneWidget);
    expect(find.text('TR-77'), findsOneWidget);
    expect(find.text('GRN-0001'), findsOneWidget);
    expect(find.text('Glucose 500g'), findsOneWidget);
  });

  testWidgets('a new voucher is posted with exactly the declared keys',
      (tester) async {
    final _Api api = _Api();
    await _pump(tester, api, manage: true);
    await tester.tap(find.byKey(const ValueKey('toolbar-new')));
    await tester.pumpAndSettle();
    expect(api.requested, contains('receipts COMPLETED'));
    expect(find.textContaining('Expenses Included in Valuation'),
        findsOneWidget);

    // Nothing is posted until a receipt and a charge are given.
    await tester.tap(find.byKey(const ValueKey('landed-save')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('landed-problem')), findsOneWidget);
    expect(api.posted, isNull);

    await tester.tap(find.byKey(const ValueKey('landed-receipt-grn-1')));
    await tester.pumpAndSettle();
    await tester.enterText(
        find.byKey(const ValueKey('landed-charge-description-0')),
        'Inbound freight');
    await tester.enterText(
        find.byKey(const ValueKey('landed-charge-amount-0')), '1200');
    await tester.enterText(
        find.byKey(const ValueKey('landed-charge-bill-0')), 'TR-77');
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('landed-add-charge')));
    await tester.pumpAndSettle();
    await tester.enterText(
        find.byKey(const ValueKey('landed-charge-description-1')), 'Clearing');
    await tester.enterText(
        find.byKey(const ValueKey('landed-charge-amount-1')), '300');
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('landed-basis')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('By weight').last);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('landed-save')));
    await tester.pumpAndSettle();

    final Json body = api.posted!;
    expect(body.keys.toSet(), {
      'voucher_date',
      'basis',
      'goods_receipt_ids',
      'charges',
      'remarks',
    });
    expect(body['basis'], 'WEIGHT');
    expect(body['goods_receipt_ids'], ['grn-1']);
    final List<dynamic> charges = body['charges'] as List<dynamic>;
    expect(charges, hasLength(2));
    for (final dynamic charge in charges) {
      expect((charge as Json).keys.toSet(),
          {'description', 'amount', 'vendor_id', 'bill_reference'});
    }
    expect((charges.first as Json)['bill_reference'], 'TR-77');
    expect((charges.last as Json)['bill_reference'], isNull);
  });

  testWidgets('a posted voucher is cancelled with the reason given',
      (tester) async {
    final _Api api = _Api(vouchers: [_voucher()]);
    await _pump(tester, api);
    await tester.tap(find.text('LC-lc-1').first);
    await tester.pump(const Duration(milliseconds: 500));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('selection-cancel')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).last, 'Wrong receipt');
    await tester.pump();
    await tester.tap(find.text('Cancel voucher'));
    await tester.pumpAndSettle();
    expect(api.cancelled, {'reason': 'Wrong receipt'});
  });
}
