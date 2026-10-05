// Customer turnover rebates (SG-9): the grid shows progress up the ladder,
// create names exactly one party and sends its slabs, a refusal keeps the
// dialog open with the server's message, accrue waits for the period to end,
// reverse is only for an accrued agreement, the statement shows the breakdown
// and the GST note, and settle drafts a CUSTOMER_REBATE party adjustment that
// carries the agreement.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/customer.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/sales/customer_rebates_page.dart';
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
      'SALES_VIEW',
      if (manage) 'SALES_APPROVE',
    ],
  }));

Json _rebate(
  String status, {
  String id = 'r-1',
  String toSettle = '0',
  String periodTo = '2026-09-30',
  bool group = false,
}) =>
    <String, dynamic>{
      'id': id,
      'version': 3,
      'customer_id': group ? null : 'c-1',
      'customer_name': group ? null : 'Mehta Stores',
      'customer_group_id': group ? 'g-1' : null,
      'customer_group_name': group ? 'Modern trade' : null,
      'code': 'CR-$id',
      'name': 'Festival turnover',
      'period_from': '2026-04-01',
      'period_to': periodTo,
      'status': status,
      'agreed_before_sale': false,
      'slabs': [
        {'id': 's1', 'line_number': 1, 'threshold': '100000', 'rate_percent': '2'},
        {'id': 's2', 'line_number': 2, 'threshold': '200000', 'rate_percent': '3'},
      ],
      'turnover': '150000.00',
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
  Future<PagedResult<Customer>> customers({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    CustomerQuery filters = const CustomerQuery(),
  }) async =>
      PagedResult<Customer>(items: [
        Customer.fromJson(<String, dynamic>{
          'id': 'c-1',
          'code': 'C1',
          'name': 'Mehta Stores',
          'display_name': 'Mehta Stores',
        }),
      ], total: 1);

  @override
  Future<PagedResult<CustomerGroup>> customerGroups({
    int page = 1,
    int pageSize = 100,
    String search = '',
  }) async =>
      PagedResult<CustomerGroup>(items: [
        CustomerGroup.fromJson(<String, dynamic>{
          'id': 'g-1',
          'code': 'MT',
          'name': 'Modern trade',
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
          'customer_bills': [
            {
              'invoice_id': 'b-1',
              'invoice_number': 'SI-001',
              'invoice_date': '2026-05-01',
              'invoice_total': '1000',
              'allocated_amount': '0',
              'outstanding_amount': '1000.00',
            },
          ],
          'supplier_bills': const [],
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
          'kind': 'CUSTOMER_REBATE',
          'amount': '1500',
          'customer_rebate_agreement_id': 'r-1',
        },
      };
    }
    if (method == 'POST' && path == '/api/v1/customer-rebates') {
      created = body;
      return <String, dynamic>{'data': _rebate('ACTIVE')};
    }
    if (path.endsWith('/statement')) {
      return <String, dynamic>{
        'data': {
          'agreement': _rebate('ACCRUED', toSettle: '3000.00', group: true),
          'customers': [
            {
              'customer_id': 'c-1',
              'customer_name': 'Mehta Stores',
              'invoiced': '160000',
              'returned': '10000',
              'credit_notes': '5000',
              'debit_notes': '5000',
              'turnover': '150000',
            },
          ],
          'invoiced': '160000',
          'returned': '10000',
          'credit_notes': '5000',
          'debit_notes': '5000',
          'turnover_today': '150000',
          'settlements': [
            {
              'id': 'pa-9',
              'adjustment_number': 'PA-0009',
              'adjustment_date': '2026-10-01',
              'customer_id': 'c-1',
              'customer_name': 'Mehta Stores',
              'amount': '500',
              'status': 'APPROVED',
            },
          ],
          'gst_note': 'Ask your CA about a GST credit note.',
        },
      };
    }
    if (path.endsWith('/accrue')) {
      accrueBody = body;
      if (accrueRefusal != null) {
        throw ApiException(accrueRefusal!, statusCode: 422);
      }
      return <String, dynamic>{'data': _rebate('ACCRUED', toSettle: '3000')};
    }
    if (method == 'GET' && path == '/api/v1/customer-rebates') {
      return <String, dynamic>{
        'data': rebates,
        'pagination': {
          'page': 1,
          'page_size': 100,
          'total_records': rebates.length,
          'total_pages': 1,
        },
      };
    }
    return <String, dynamic>{'data': const <Json>[]};
  }
}

DesktopPreferencesService _preferences() => DesktopPreferencesService(
      directory: Directory.systemTemp.createTempSync('customer-rebates'),
    );

Future<void> _pump(WidgetTester tester, _Api api, {bool manage = true}) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    builder: (context, child) => Phase2Scope(child: child!),
    home: Scaffold(
      body: CustomerRebatesPage(
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
    expect(find.text('CR-r-1'), findsOneWidget);
    expect(find.text('Mehta Stores'), findsOneWidget);
    expect(find.text('Next slab / To next'), findsOneWidget);
    expect(find.textContaining('200000.00 at 3% (50000.00 to go)'),
        findsOneWidget);
    expect(find.text('Turnover'), findsOneWidget);
    expect(find.text('Earned'), findsOneWidget);
    expect(find.text('To settle'), findsOneWidget);
  });

  testWidgets('a group agreement is labelled as one', (tester) async {
    await _pump(tester, _Api(rebates: [_rebate('ACTIVE', group: true)]));
    expect(find.text('Modern trade (group)'), findsOneWidget);
  });

  testWidgets('create names exactly one customer and sends its slabs',
      (tester) async {
    final _Api api = _Api();
    await _pump(tester, api);
    await tester.tap(find.byKey(const ValueKey('toolbar-new')));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const ValueKey('rebate-customer')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Mehta Stores').last);
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const ValueKey('rebate-code')), 'CR1');
    await tester.enterText(
        find.byKey(const ValueKey('rebate-name')), 'Festival turnover');
    await tester.ensureVisible(
        find.byKey(const ValueKey('rebate-slab-threshold-0')));
    await tester.enterText(
        find.byKey(const ValueKey('rebate-slab-threshold-0')), '100000');
    await tester.enterText(
        find.byKey(const ValueKey('rebate-slab-rate-0')), '2');
    await tester.ensureVisible(find.byKey(const ValueKey('rebate-add-slab')));
    await tester.tap(find.byKey(const ValueKey('rebate-add-slab')));
    await tester.pumpAndSettle();
    await tester.enterText(
        find.byKey(const ValueKey('rebate-slab-threshold-1')), '200000');
    await tester.enterText(
        find.byKey(const ValueKey('rebate-slab-rate-1')), '3');
    await tester.ensureVisible(
        find.byKey(const ValueKey('rebate-agreed-before-sale')));
    expect(find.textContaining('Only informs your CA'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('rebate-agreed-before-sale')));
    await tester.pumpAndSettle();

    // No period yet: the form refuses before the server is asked.
    await tester.tap(find.byKey(const ValueKey('rebate-save')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('rebate-problem')), findsOneWidget);
    expect(api.created, isNull);

    Future<void> pickDay(String key, String day) async {
      await tester.ensureVisible(find.byKey(ValueKey(key)));
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
      'customer_id',
      'code',
      'name',
      'period_from',
      'period_to',
      'agreed_before_sale',
      'slabs',
    });
    expect(body['customer_id'], 'c-1');
    expect(body['agreed_before_sale'], isTrue);
    expect(body['slabs'], [
      {'threshold': '100000', 'rate_percent': '2'},
      {'threshold': '200000', 'rate_percent': '3'},
    ]);
  });

  testWidgets('create for a group sends the group id and no customer id',
      (tester) async {
    final _Api api = _Api();
    await _pump(tester, api);
    await tester.tap(find.byKey(const ValueKey('toolbar-new')));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Customer group'));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('rebate-group')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Modern trade').last);
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const ValueKey('rebate-code')), 'CR2');
    await tester.enterText(find.byKey(const ValueKey('rebate-name')), 'MT');
    await tester.ensureVisible(
        find.byKey(const ValueKey('rebate-slab-threshold-0')));
    await tester.enterText(
        find.byKey(const ValueKey('rebate-slab-threshold-0')), '100000');
    await tester.enterText(
        find.byKey(const ValueKey('rebate-slab-rate-0')), '2');
    Future<void> pickDay(String key, String day) async {
      await tester.ensureVisible(find.byKey(ValueKey(key)));
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
    expect(body['customer_group_id'], 'g-1');
    expect(body.containsKey('customer_id'), isFalse);
  });

  testWidgets('accrue is off until the period has ended', (tester) async {
    await _pump(tester,
        _Api(rebates: [_rebate('ACTIVE', periodTo: '2999-12-31')]));
    await _select(tester, 'CR-r-1');
    expect(find.byKey(const ValueKey('selection-accrue')), findsNothing);
    expect(find.byKey(const ValueKey('selection-edit-rebate')),
        findsOneWidget);
  });

  testWidgets('accrue calls the route once the period has ended',
      (tester) async {
    final _Api api = _Api(rebates: [_rebate('ACTIVE')]);
    await _pump(tester, api);
    await _select(tester, 'CR-r-1');
    await tester.tap(find.byKey(const ValueKey('selection-accrue')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('rebate-action-confirm')));
    await tester.pumpAndSettle();
    expect(
        api.requested, contains('POST /api/v1/customer-rebates/r-1/accrue'));
    expect(api.accrueBody, isEmpty);
  });

  testWidgets('a refused accrual shows the message and keeps the dialog',
      (tester) async {
    final _Api api = _Api(
      rebates: [_rebate('ACTIVE')],
      accrueRefusal: 'The period has not ended yet.',
    );
    await _pump(tester, api);
    await _select(tester, 'CR-r-1');
    await tester.tap(find.byKey(const ValueKey('selection-accrue')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('rebate-action-confirm')));
    await tester.pumpAndSettle();
    expect(find.text('The period has not ended yet.'), findsOneWidget);
    expect(find.byKey(const ValueKey('rebate-action-confirm')),
        findsOneWidget);
  });

  testWidgets('reverse is offered only for an accrued agreement',
      (tester) async {
    await _pump(tester, _Api(rebates: [_rebate('ACCRUED', toSettle: '3000')]));
    await _select(tester, 'CR-r-1');
    expect(find.byKey(const ValueKey('selection-reverse')), findsOneWidget);
    expect(find.byKey(const ValueKey('selection-accrue')), findsNothing);
    expect(find.byKey(const ValueKey('selection-cancel')), findsNothing);
    expect(find.byKey(const ValueKey('selection-edit-rebate')), findsNothing);
  });

  testWidgets('the statement shows the breakdown and the GST note',
      (tester) async {
    await _pump(tester, _Api(rebates: [_rebate('ACCRUED', toSettle: '3000')]));
    await _select(tester, 'CR-r-1');
    await tester.tap(find.byKey(const ValueKey('selection-rebate-statement')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('statement-turnover')), findsOneWidget);
    expect(find.text('Invoiced'), findsOneWidget);
    expect(find.text('Credit notes'), findsOneWidget);
    expect(find.text('160000.00'), findsWidgets);
    expect(find.textContaining('PA-0009'), findsOneWidget);
    expect(find.text('Ask your CA about a GST credit note.'), findsOneWidget);
  });

  testWidgets('settle posts a CUSTOMER_REBATE adjustment naming the agreement',
      (tester) async {
    final _Api api =
        _Api(rebates: [_rebate('ACCRUED', toSettle: '3000.00')]);
    await _pump(tester, api);
    await _select(tester, 'CR-r-1');
    await tester.tap(find.byKey(const ValueKey('selection-settle-rebate')));
    await tester.pumpAndSettle();

    // More than is left to settle is refused on the form.
    await tester.enterText(
        find.byKey(const ValueKey('settle-amount')), '3500');
    await tester.tap(find.byKey(const ValueKey('settle-save')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('settle-problem')), findsOneWidget);
    expect(api.settlement, isNull);

    await tester.enterText(
        find.byKey(const ValueKey('settle-amount')), '1500');
    await tester.enterText(
        find.byKey(const ValueKey('settle-bill-b-1')), '1000');
    await tester.tap(find.byKey(const ValueKey('settle-save')));
    await tester.pumpAndSettle();

    final Json body = api.settlement!;
    expect(body['kind'], 'CUSTOMER_REBATE');
    expect(body['customer_id'], 'c-1');
    expect(body['customer_rebate_agreement_id'], 'r-1');
    expect(body['amount'], '1500.00');
    expect(body['allocations'], [
      {'side': 'CUSTOMER', 'bill_id': 'b-1', 'amount': '1000'},
    ]);
    expect(body.containsKey('vendor_id'), isFalse);
    expect(body.containsKey('rebate_agreement_id'), isFalse);
  });

  testWidgets('settle is off for a rebate that is not accrued',
      (tester) async {
    await _pump(tester, _Api(rebates: [_rebate('ACTIVE')]));
    await _select(tester, 'CR-r-1');
    expect(find.byKey(const ValueKey('selection-settle-rebate')),
        findsNothing);
    expect(find.byKey(const ValueKey('selection-cancel')), findsOneWidget);
  });

  testWidgets('without approve nothing can be changed', (tester) async {
    await _pump(tester, _Api(rebates: [_rebate('ACTIVE')]), manage: false);
    expect(find.byKey(const ValueKey('toolbar-new')), findsNothing);
    expect(find.text('CR-r-1'), findsOneWidget);
  });
}
