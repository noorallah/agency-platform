// Claims on principals (SEL-11): the grid and details pane read a claim, a new
// claim is previewed and then raised with exactly the declared keys, a payment
// is recorded with the right body and can be reversed, and settling by the
// principal's credit note drafts a PRINCIPAL_CLAIM party adjustment.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/contra_voucher.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/ui/purchases/principal_claims_page.dart';
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

Json _line(String kind, String number, String amount) => <String, dynamic>{
      'line_number': 1,
      'kind': kind,
      'source_id': 'src-$number',
      'source_number': number,
      'source_date': '2026-05-01',
      'product_id': 'p-1',
      'product_name': 'Glucose 500g',
      'quantity': '10',
      'description': '',
      'amount': amount,
    };

Json _claim({
  String id = 'c-1',
  String status = 'RAISED',
  String outstanding = '3000.00',
  String vendorId = 'v-1',
  List<Json> receipts = const <Json>[],
}) =>
    <String, dynamic>{
      'id': id,
      'claim_number': 'PC-$id',
      'claim_date': '2026-10-01',
      'principal_id': 'pr-1',
      'principal_name': 'Hindustan Foods',
      'vendor_id': vendorId.isEmpty ? null : vendorId,
      'period_from': '2026-04-01',
      'period_to': '2026-09-30',
      'scheme_amount': '2000.00',
      'expiry_amount': '1000.00',
      'breakage_amount': '0.00',
      'total_amount': '3000.00',
      'settled_by_credit_note': '0.00',
      'settled_by_payment': '0.00',
      'outstanding': outstanding,
      'status': status,
      'remarks': null,
      'cancel_reason': null,
      'version': 1,
      'lines': [
        _line('SCHEME', 'INV-0042', '2000.00'),
        _line('EXPIRY', 'BATCH-77', '1000.00'),
      ],
      'receipts': receipts,
    };

Json _receipt(String id, {String status = 'POSTED'}) => <String, dynamic>{
      'id': id,
      'received_on': '2026-10-02',
      'amount': '1000.00',
      'money_account_id': 'm-1',
      'reference': 'UTR123',
      'status': status,
    };

class _Api extends ApiClient {
  _Api({this.claims = const []})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Json> claims;
  final List<String> requested = <String>[];
  Json? previewBody;
  Json? raiseBody;
  Json? receiptBody;
  Json? settlement;

  @override
  Future<List<PrincipalRecord>> principals() async => <PrincipalRecord>[
        PrincipalRecord.fromJson(const <String, dynamic>{
          'id': 'pr-1',
          'code': 'HUL',
          'name': 'Hindustan Foods',
          'vendor_id': 'v-1',
        }),
      ];

  @override
  Future<List<MoneyAccount>> contraMoneyAccounts() async => const [
        MoneyAccount(id: 'm-1', code: 'BANK1', name: 'Current account', kind: 'BANK'),
      ];

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
              'invoice_total': '4000',
              'allocated_amount': '0',
              'outstanding_amount': '4000.00',
            },
          ],
          'customer_bills': const [],
          'supplier_outstanding': '5000.00',
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
          'kind': 'PRINCIPAL_CLAIM',
          'amount': '3000',
          'principal_claim_id': 'c-1',
        },
      };
    }
    if (method == 'POST' && path == '/api/v1/principal-claims/preview') {
      previewBody = body;
      return <String, dynamic>{
        'data': {
          'principal_id': 'pr-1',
          'period_from': body!['period_from'],
          'period_to': body['period_to'],
          'scheme_amount': '2000.00',
          'free_goods_amount': '500.00',
          'expiry_amount': '1000.00',
          'breakage_amount': '0.00',
          'total_amount': '3500.00',
          'lines': [
            _line('SCHEME', 'INV-0042', '2000.00'),
            _line('FREE_GOODS', 'DN-0009', '500.00'),
            _line('EXPIRY', 'BATCH-77', '1000.00'),
          ],
        },
      };
    }
    if (method == 'POST' && path == '/api/v1/principal-claims') {
      raiseBody = body;
      return <String, dynamic>{'data': _claim()};
    }
    if (method == 'POST' && path.endsWith('/receipts')) {
      receiptBody = body;
      return <String, dynamic>{
        'data': _claim(status: 'PART_SETTLED', receipts: [_receipt('r-1')]),
      };
    }
    if (method == 'POST' && path.endsWith('/reverse')) {
      return <String, dynamic>{
        'data': _claim(receipts: [_receipt('r-1', status: 'REVERSED')]),
      };
    }
    if (method == 'GET' && path.startsWith('/api/v1/principal-claims/')) {
      final String id = path.split('/').last;
      return <String, dynamic>{
        'data': claims.firstWhere((claim) => claim['id'] == id),
      };
    }
    if (method == 'GET' && path == '/api/v1/principal-claims') {
      return <String, dynamic>{'data': claims};
    }
    return <String, dynamic>{'data': const <Json>[]};
  }
}

DesktopPreferencesService _preferences() => DesktopPreferencesService(
      directory: Directory.systemTemp.createTempSync('principal-claims'),
    );

Future<void> _pump(WidgetTester tester, _Api api, {bool manage = true}) async {
  tester.view.physicalSize = const Size(1600, 1000);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    builder: (context, child) => Phase2Scope(child: child!),
    home: Scaffold(
      body: PrincipalClaimsPage(
        api: api,
        preferences: _preferences(),
        permissions: _permissions(manage: manage),
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

Future<void> _pickDay(WidgetTester tester, String key, String day) async {
  await tester.tap(find.byKey(ValueKey(key)));
  await tester.pumpAndSettle();
  await tester.tap(find.text(day).last);
  await tester.tap(find.text('OK'));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('a claim shows its free goods as a total and a group of lines',
      (tester) async {
    final Json claim = <String, dynamic>{
      ..._claim(),
      'free_goods_amount': '500.00',
      'total_amount': '3500.00',
      'lines': [
        _line('SCHEME', 'INV-0042', '2000.00'),
        _line('FREE_GOODS', 'DN-0009', '500.00'),
        _line('EXPIRY', 'BATCH-77', '1000.00'),
      ],
    };
    await _pump(tester, _Api(claims: [claim]));
    await _select(tester, 'PC-c-1');

    final Finder pane = find.byKey(const ValueKey('claim-details'));
    expect(
      find.descendant(of: pane, matching: find.text('Free goods')),
      findsNWidgets(2),
      reason: 'the total row and the group heading',
    );
    expect(find.textContaining('DN-0009 · Glucose 500g · × 10'),
        findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('the grid and the details pane read a claim', (tester) async {
    await _pump(tester, _Api(claims: [_claim()]));
    expect(find.text('PC-c-1'), findsOneWidget);
    expect(find.text('Hindustan Foods'), findsOneWidget);
    expect(find.text('Outstanding'), findsOneWidget);
    await _select(tester, 'PC-c-1');
    expect(find.byKey(const ValueKey('claim-details')), findsOneWidget);
    expect(find.textContaining('INV-0042'), findsOneWidget);
    expect(find.textContaining('BATCH-77'), findsOneWidget);
    expect(find.text('Expired stock'), findsWidgets);
  });

  testWidgets('a claim is previewed, then raised with the declared keys',
      (tester) async {
    final _Api api = _Api();
    await _pump(tester, api);
    await tester.tap(find.byKey(const ValueKey('toolbar-new')));
    await tester.pumpAndSettle();

    // Nothing can be raised before it has been previewed.
    expect(
        tester
            .widget<FilledButton>(find.byKey(const ValueKey('claim-raise')))
            .onPressed,
        isNull);

    await tester.tap(find.byKey(const ValueKey('claim-preview')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('claim-problem')), findsOneWidget);
    expect(api.previewBody, isNull);

    await tester.tap(find.byKey(const ValueKey('claim-principal')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Hindustan Foods').last);
    await tester.pumpAndSettle();
    await _pickDay(tester, 'claim-from', '1');
    await _pickDay(tester, 'claim-to', '28');
    await tester.tap(find.byKey(const ValueKey('claim-kind-BREAKAGE')));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const ValueKey('claim-preview')));
    await tester.pumpAndSettle();
    expect(api.previewBody, isNotNull);
    expect(find.byKey(const ValueKey('claim-preview-result')), findsOneWidget);
    expect(find.textContaining('INV-0042'), findsOneWidget);
    // Free goods are their own total and their own group of lines: the
    // delivery note, the product, the quantity and the value at cost.
    expect(find.text('Free goods'), findsWidgets);
    expect(find.text('500.00'), findsWidgets);
    expect(find.textContaining('DN-0009 · Glucose 500g · × 10'),
        findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('claim-raise')));
    await tester.pumpAndSettle();

    final Json body = api.raiseBody!;
    expect(body.keys.toSet(), {
      'principal_id',
      'period_from',
      'period_to',
      'claim_date',
      'kinds',
    });
    expect(body['principal_id'], 'pr-1');
    // Free goods is offered with the rest and claimed by default.
    expect(body['kinds'], ['SCHEME', 'FREE_GOODS', 'EXPIRY']);
    expect(api.previewBody!.keys.toSet(), body.keys.toSet());
  });

  testWidgets('recording a payment sends the right body', (tester) async {
    final _Api api = _Api(claims: [_claim()]);
    await _pump(tester, api);
    await _select(tester, 'PC-c-1');
    await tester.tap(find.byKey(const ValueKey('selection-record-payment')));
    await tester.pumpAndSettle();

    // Prefilled with what is outstanding; no account chosen yet.
    expect(
        tester
            .widget<TextField>(
                find.byKey(const ValueKey('claim-payment-amount')))
            .controller!
            .text,
        '3000.00');
    await tester.tap(find.byKey(const ValueKey('claim-payment-save')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('claim-payment-problem')), findsOneWidget);
    expect(api.receiptBody, isNull);

    await tester.tap(find.byKey(const ValueKey('claim-payment-account')));
    await tester.pumpAndSettle();
    await tester.tap(find.textContaining('Current account').last);
    await tester.pumpAndSettle();
    await tester.enterText(
        find.byKey(const ValueKey('claim-payment-amount')), '1000');
    await tester.enterText(
        find.byKey(const ValueKey('claim-payment-reference')), 'UTR123');
    await tester.tap(find.byKey(const ValueKey('claim-payment-save')));
    await tester.pumpAndSettle();

    final Json body = api.receiptBody!;
    expect(body.keys.toSet(),
        {'received_on', 'amount', 'money_account_id', 'reference'});
    expect(body['amount'], '1000');
    expect(body['money_account_id'], 'm-1');
    expect(body['reference'], 'UTR123');
    expect(api.requested, contains('POST /api/v1/principal-claims/c-1/receipts'));
  });

  testWidgets('a posted payment can be reversed', (tester) async {
    final _Api api = _Api(claims: [
      _claim(status: 'PART_SETTLED', receipts: [_receipt('r-1')]),
    ]);
    await _pump(tester, api);
    await _select(tester, 'PC-c-1');
    await tester.tap(find.byKey(const ValueKey('selection-reverse-payment')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('claim-reverse-r-1')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('claim-reverse-confirm')));
    await tester.pumpAndSettle();
    expect(api.requested,
        contains('POST /api/v1/principal-claims/c-1/receipts/r-1/reverse'));
  });

  testWidgets('settling by credit note drafts a PRINCIPAL_CLAIM adjustment',
      (tester) async {
    final _Api api = _Api(claims: [_claim()]);
    await _pump(tester, api);
    await _select(tester, 'PC-c-1');
    await tester.tap(find.byKey(const ValueKey('selection-settle-claim')));
    await tester.pumpAndSettle();

    // More than is outstanding on the claim is refused on the form.
    await tester.enterText(
        find.byKey(const ValueKey('settle-bill-b-1')), '1000');
    await tester.enterText(
        find.byKey(const ValueKey('settle-bill-b-2')), '2500');
    await tester.tap(find.byKey(const ValueKey('settle-save')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('settle-problem')), findsOneWidget);
    expect(api.settlement, isNull);

    await tester.enterText(
        find.byKey(const ValueKey('settle-bill-b-2')), '2000');
    await tester.tap(find.byKey(const ValueKey('settle-save')));
    await tester.pumpAndSettle();

    final Json body = api.settlement!;
    expect(body['kind'], 'PRINCIPAL_CLAIM');
    expect(body['vendor_id'], 'v-1');
    expect(body['principal_claim_id'], 'c-1');
    expect(body['amount'], '3000.00');
    expect(body.containsKey('customer_id'), isFalse);
    expect(body.containsKey('rebate_agreement_id'), isFalse);
    expect(body['allocations'], [
      {'side': 'SUPPLIER', 'bill_id': 'b-1', 'amount': '1000'},
      {'side': 'SUPPLIER', 'bill_id': 'b-2', 'amount': '2000'},
    ]);
  });

  testWidgets('credit-note settlement is off with no supplier or no balance',
      (tester) async {
    await _pump(
        tester,
        _Api(claims: [
          _claim(id: 'c-1', vendorId: ''),
        ]));
    await _select(tester, 'PC-c-1');
    expect(find.byKey(const ValueKey('selection-settle-claim')), findsNothing);
    expect(find.byKey(const ValueKey('selection-record-payment')),
        findsOneWidget);
    expect(find.byKey(const ValueKey('selection-cancel')), findsOneWidget);
  });

  testWidgets('without approve nothing can be changed', (tester) async {
    await _pump(tester, _Api(claims: [_claim()]), manage: false);
    expect(find.byKey(const ValueKey('toolbar-new')), findsNothing);
    expect(find.text('PC-c-1'), findsOneWidget);
    await _select(tester, 'PC-c-1');
    expect(find.byKey(const ValueKey('selection-record-payment')),
        findsNothing);
    expect(find.byKey(const ValueKey('selection-print-statement')),
        findsOneWidget);
  });
}
