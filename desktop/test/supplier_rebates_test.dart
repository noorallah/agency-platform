// Supplier volume rebates (BUY-13): the grid shows progress up the ladder,
// create posts exactly the declared keys with its slabs, accrue calls its
// route and shows a refusal inside the dialog, settle drafts a SUPPLIER_REBATE
// party adjustment against the supplier's bills, and settle is off for a row
// that is not yet accrued.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/vendor.dart';
import 'package:agency_desktop/ui/purchases/supplier_rebates_page.dart';
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

Json _rebate(String status, {String id = 'r-1', String toSettle = '0'}) =>
    <String, dynamic>{
      'id': id,
      'version': 3,
      'vendor_id': 'v-1',
      'vendor_name': 'Shah Foods',
      'code': 'RB-$id',
      'name': 'Festival volume',
      'period_from': '2026-04-01',
      'period_to': '2026-09-30',
      'status': status,
      'slabs': [
        {'id': 's1', 'line_number': 1, 'threshold': '100000', 'rate_percent': '2'},
        {'id': 's2', 'line_number': 2, 'threshold': '200000', 'rate_percent': '3'},
      ],
      'volume': '150000.00',
      'rate_percent': '2',
      'earned': '3000.00',
      'next_threshold': '200000.00',
      'next_rate_percent': '3',
      'to_next': '50000.00',
      if (status == 'ACCRUED') 'accrued_amount': '3000.00',
      'settled': '0',
      'to_settle': toSettle,
    };

class _Api extends ApiClient {
  _Api({this.rebates = const [], this.accrueRefusal})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Json> rebates;
  final String? accrueRefusal;
  final List<String> requested = <String>[];
  Json? created;
  Json? settlement;
  Json? accrueBody;

  @override
  Future<PagedResult<Vendor>> vendors({
    int page = 1,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    VendorQuery filters = const VendorQuery(),
  }) async =>
      PagedResult<Vendor>(items: [
        Vendor.fromJson(<String, dynamic>{
          'id': 'v-1',
          'code': 'V1',
          'name': 'Shah Foods',
          'display_name': 'Shah Foods',
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
    requested.add('$method $path');
    if (path == '/api/v1/party-adjustments/open-bills') {
      return <String, dynamic>{
        'data': {
          'supplier_bills': [
            {
              'invoice_id': 'b-1',
              'invoice_number': 'PI-001',
              'invoice_date': '2026-05-01',
              'invoice_total': '1000',
              'allocated_amount': '0',
              'outstanding_amount': '1000.00',
            },
            {
              'invoice_id': 'b-2',
              'invoice_number': 'PI-002',
              'invoice_date': '2026-06-01',
              'invoice_total': '2000',
              'allocated_amount': '0',
              'outstanding_amount': '2000.00',
            },
          ],
          'customer_bills': const [],
          'supplier_outstanding': '3000.00',
        },
      };
    }
    if (method == 'POST' && path == '/api/v1/party-adjustments') {
      settlement = body;
      return <String, dynamic>{
        'data': {
          'id': 'pa-1',
          'adjustment_number': 'PA-0001',
          'adjustment_date': '2026-10-03',
          'kind': 'SUPPLIER_REBATE',
          'amount': '1500',
          'rebate_agreement_id': 'r-1',
        },
      };
    }
    if (method == 'POST' && path == '/api/v1/supplier-rebates') {
      created = body;
      return <String, dynamic>{'data': _rebate('ACTIVE')};
    }
    if (path.endsWith('/accrue')) {
      accrueBody = body;
      if (accrueRefusal != null) {
        throw ApiException(accrueRefusal!, statusCode: 422);
      }
      return <String, dynamic>{'data': _rebate('ACCRUED', toSettle: '3000')};
    }
    if (method == 'GET' && path == '/api/v1/supplier-rebates') {
      return <String, dynamic>{'data': rebates};
    }
    return <String, dynamic>{'data': const <Json>[]};
  }
}

DesktopPreferencesService _preferences() => DesktopPreferencesService(
      directory: Directory.systemTemp.createTempSync('supplier-rebates'),
    );

Future<void> _pump(WidgetTester tester, _Api api, {bool manage = true}) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    builder: (context, child) => Phase2Scope(child: child!),
    home: Scaffold(
      body: SupplierRebatesPage(
        api: api,
        preferences: _preferences(),
        permissions: _permissions(manage: manage),
        hasActiveFirm: true,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

Future<void> _select(WidgetTester tester, String code) async {
  await tester.tap(find.text(code).first);
  await tester.pump(const Duration(milliseconds: 500));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('the grid shows progress up the ladder', (tester) async {
    await _pump(tester, _Api(rebates: [_rebate('ACTIVE')]));
    expect(find.text('RB-r-1'), findsOneWidget);
    expect(find.text('Shah Foods'), findsOneWidget);
    expect(find.text('Next slab / To next'), findsOneWidget);
    expect(find.textContaining('200000.00 at 3% (50000.00 to go)'),
        findsOneWidget);
    expect(find.text('Earned'), findsOneWidget);
    expect(find.text('To settle'), findsOneWidget);
  });

  testWidgets('create posts exactly the declared keys with its slabs',
      (tester) async {
    final _Api api = _Api();
    await _pump(tester, api);
    await tester.tap(find.byKey(const ValueKey('toolbar-new')));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const ValueKey('rebate-vendor')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Shah Foods').last);
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const ValueKey('rebate-code')), 'RB1');
    await tester.enterText(
        find.byKey(const ValueKey('rebate-name')), 'Festival volume');
    await tester.enterText(
        find.byKey(const ValueKey('rebate-slab-threshold-0')), '100000');
    await tester.enterText(
        find.byKey(const ValueKey('rebate-slab-rate-0')), '2');
    await tester.tap(find.byKey(const ValueKey('rebate-add-slab')));
    await tester.pumpAndSettle();
    await tester.enterText(
        find.byKey(const ValueKey('rebate-slab-threshold-1')), '200000');
    await tester.enterText(
        find.byKey(const ValueKey('rebate-slab-rate-1')), '3');

    // No period yet: the form refuses before the server is asked.
    await tester.tap(find.byKey(const ValueKey('rebate-save')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('rebate-problem')), findsOneWidget);
    expect(api.created, isNull);

    Future<void> pickDay(String key, String day) async {
      await tester.tap(find.byKey(ValueKey(key)));
      await tester.pumpAndSettle();
      await tester.tap(find.text(day).last);
      await tester.tap(find.text('OK'));
      await tester.pumpAndSettle();
    }

    await pickDay('rebate-from', '1');
    await pickDay('rebate-to', '28');
    await tester.tap(find.byKey(const ValueKey('rebate-save')));
    await tester.pumpAndSettle();

    final Json body = api.created!;
    expect(body.keys.toSet(), {
      'vendor_id',
      'code',
      'name',
      'period_from',
      'period_to',
      'slabs',
    });
    expect(body['vendor_id'], 'v-1');
    expect(body['code'], 'RB1');
    expect(body['slabs'], [
      {'threshold': '100000', 'rate_percent': '2'},
      {'threshold': '200000', 'rate_percent': '3'},
    ]);
  });

  testWidgets('accrue calls the route', (tester) async {
    final _Api api = _Api(rebates: [_rebate('ACTIVE')]);
    await _pump(tester, api);
    await _select(tester, 'RB-r-1');
    await tester.tap(find.byKey(const ValueKey('selection-accrue')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('rebate-action-confirm')));
    await tester.pumpAndSettle();
    expect(api.requested, contains('POST /api/v1/supplier-rebates/r-1/accrue'));
    expect(api.accrueBody, isEmpty);
  });

  testWidgets('a refused accrual shows the message and keeps the dialog',
      (tester) async {
    final _Api api = _Api(
      rebates: [_rebate('ACTIVE')],
      accrueRefusal: 'The period has not ended yet.',
    );
    await _pump(tester, api);
    await _select(tester, 'RB-r-1');
    await tester.tap(find.byKey(const ValueKey('selection-accrue')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('rebate-action-confirm')));
    await tester.pumpAndSettle();
    expect(find.text('The period has not ended yet.'), findsOneWidget);
    expect(find.byKey(const ValueKey('rebate-action-confirm')),
        findsOneWidget);
  });

  testWidgets('settle posts a SUPPLIER_REBATE adjustment with its bills',
      (tester) async {
    final _Api api =
        _Api(rebates: [_rebate('ACCRUED', toSettle: '3000.00')]);
    await _pump(tester, api);
    await _select(tester, 'RB-r-1');
    await tester.tap(find.byKey(const ValueKey('selection-settle-rebate')));
    await tester.pumpAndSettle();

    // More than is left to settle is refused on the form.
    await tester.enterText(
        find.byKey(const ValueKey('settle-bill-b-1')), '1000');
    await tester.enterText(
        find.byKey(const ValueKey('settle-bill-b-2')), '2500');
    await tester.tap(find.byKey(const ValueKey('settle-save')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('settle-problem')), findsOneWidget);
    expect(api.settlement, isNull);

    await tester.enterText(
        find.byKey(const ValueKey('settle-bill-b-2')), '500');
    await tester.tap(find.byKey(const ValueKey('settle-save')));
    await tester.pumpAndSettle();

    final Json body = api.settlement!;
    expect(body['kind'], 'SUPPLIER_REBATE');
    expect(body['vendor_id'], 'v-1');
    expect(body['rebate_agreement_id'], 'r-1');
    expect(body['amount'], '1500.00');
    expect(body['reason'], 'Supplier credit note for RB-r-1');
    expect(body['allocations'], [
      {'side': 'SUPPLIER', 'bill_id': 'b-1', 'amount': '1000'},
      {'side': 'SUPPLIER', 'bill_id': 'b-2', 'amount': '500'},
    ]);
    expect(body.containsKey('customer_id'), isFalse);
  });

  testWidgets('settle is off for a rebate that is not accrued',
      (tester) async {
    await _pump(tester, _Api(rebates: [_rebate('ACTIVE')]));
    await _select(tester, 'RB-r-1');
    // The selection bar offers only what the row can do.
    expect(find.byKey(const ValueKey('selection-settle-rebate')),
        findsNothing);
    expect(find.byKey(const ValueKey('selection-reverse')), findsNothing);
    expect(find.byKey(const ValueKey('selection-edit-rebate')),
        findsOneWidget);
    expect(find.byKey(const ValueKey('selection-cancel')), findsOneWidget);
    final OutlinedButton accrue = tester
        .widget<OutlinedButton>(find.byKey(const ValueKey('selection-accrue')));
    expect(accrue.onPressed, isNotNull);
  });

  testWidgets('without approve nothing can be changed', (tester) async {
    await _pump(tester, _Api(rebates: [_rebate('ACTIVE')]), manage: false);
    expect(find.byKey(const ValueKey('toolbar-new')), findsNothing);
    expect(find.text('RB-r-1'), findsOneWidget);
  });
}
