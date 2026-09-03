// Credit a customer earns, and the one thing this screen must not misstate.
//
// Spending credit settles a bill; it does not discount one. The difference is
// what GST the firm collects, so the screen says it rather than leaving a
// reader to assume the familiar thing.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/customers/loyalty_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions({
  List<String> perms = const ['LOYALTY_VIEW'],
}) =>
    PermissionService()
      ..applyAccessToken(_accessToken({
        'roles': <String>['user'],
        'permissions': perms,
      }));

class _LoyaltyApi extends ApiClient {
  _LoyaltyApi({required this.settings, this.entries = const []})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final Json settings;
  final List<Json> entries;

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
    if (path.endsWith('/settings')) {
      return <String, dynamic>{'data': settings};
    }
    return <String, dynamic>{'data': entries};
  }
}

Json _settings({bool enabled = true, int? expiryMonths = 24}) =>
    <String, dynamic>{
      'is_enabled': enabled,
      'points_per_amount': '2',
      'amount_per_point': '1',
      'minimum_redemption_points': 50,
      'expiry_months': expiryMonths,
    };

Json _entry({String kind = 'EARNED', String points = '20.0000'}) =>
    <String, dynamic>{
      'id': 'le-1',
      'customer_id': 'c-1',
      'customer_name': 'Kumar Stores',
      'kind': kind,
      'points': points,
      'amount': '20.00',
      'sales_invoice_number': 'SI-2026-2027-000004',
      'earned_on': '2026-06-10',
      'expires_on': '2028-06-10',
    };

Future<void> _pump(
  WidgetTester tester,
  _LoyaltyApi api, {
  PermissionService? permissions,
}) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: LoyaltyPage(
        api: api,
        permissions: permissions ?? _permissions(),
        hasActiveFirm: true,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('the screen says spending settles rather than discounts',
      (tester) async {
    await _pump(tester, _LoyaltyApi(settings: _settings()));

    // The difference is what GST the firm collects, so it is not left to be
    // assumed.
    expect(
      find.textContaining('settles a bill; it does not discount it'),
      findsOneWidget,
    );
  });

  testWidgets('the scheme is spelled out, expiry included', (tester) async {
    await _pump(tester, _LoyaltyApi(settings: _settings()));

    expect(find.textContaining('2 points per 100'), findsOneWidget);
    expect(find.textContaining('expire after 24 months'), findsOneWidget);
  });

  testWidgets('points that never expire say so rather than showing a blank',
      (tester) async {
    // Null is a real choice here, not a missing value.
    await _pump(tester, _LoyaltyApi(settings: _settings(expiryMonths: null)));

    expect(find.textContaining('never expire'), findsOneWidget);
  });

  testWidgets('a firm with no scheme is told nobody is earning',
      (tester) async {
    await _pump(tester, _LoyaltyApi(settings: _settings(enabled: false)));

    expect(find.textContaining('nobody is earning'), findsOneWidget);
  });

  testWidgets('the ledger signs the points so the direction is visible',
      (tester) async {
    await _pump(
      tester,
      _LoyaltyApi(
        settings: _settings(),
        entries: <Json>[
          _entry(),
          _entry(kind: 'REDEEMED', points: '-10.0000'),
        ],
      ),
    );

    // A reader should see which way it went without decoding the kind first.
    expect(find.text('+20.00'), findsOneWidget);
    expect(find.text('-10.00'), findsOneWidget);
  });

  testWidgets('someone without the view permission sees nothing',
      (tester) async {
    await _pump(
      tester,
      _LoyaltyApi(settings: _settings(), entries: <Json>[_entry()]),
      permissions: _permissions(perms: const <String>['CUSTOMER_VIEW']),
    );

    expect(find.textContaining('view loyalty permission'), findsOneWidget);
    expect(find.textContaining('Kumar Stores'), findsNothing);
  });
}
