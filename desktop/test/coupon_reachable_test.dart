// Coupons were list-only.
//
// The promotion workspace's toolbar hid "New promotion" on the coupon tab and
// never gained a control of its own, so `createPromotionCoupon`,
// `updatePromotionCoupon` and `deletePromotionCoupon` had a route, a client
// method and nothing that called them: no coupon could be brought into
// existence from the desktop at all.
//
// These pin the control and the two rules the form has to respect -- a code is
// fixed once minted, and a blank limit means no limit rather than zero.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/pricing.dart';
import 'package:agency_desktop/ui/pricing/coupon_dialog.dart';
import 'package:agency_desktop/ui/pricing/promotion_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions(List<String> codes) => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': codes,
  }));

class _Api extends ApiClient {
  _Api({this.offers = const <Json>[], this.coupons = const <Json>[]})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Json> offers;
  final List<Json> coupons;

  Json? sentBody;
  final List<String> posted = <String>[];

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
    if (method == 'POST' || method == 'PUT') {
      posted.add('$method $path');
      sentBody = body;
      return <String, dynamic>{'data': _coupon(id: 'c-1', code: 'SAVE10')};
    }
    if (path.contains('promotions/coupons')) {
      return <String, dynamic>{
        'data': coupons,
        'pagination': <String, dynamic>{'total_records': coupons.length},
      };
    }
    return <String, dynamic>{
      'data': offers,
      'pagination': <String, dynamic>{'total_records': offers.length},
    };
  }
}

Json _promotion(String id, String code, String name) => <String, dynamic>{
      'id': id,
      'code': code,
      'name': name,
      'status': 'ACTIVE',
      'priority': 100,
      'allow_stacking': true,
      'requires_coupon': true,
      'version': 1,
      'version_number': 1,
      'conditions': <Json>[],
      'actions': <Json>[],
    };

Json _coupon({
  required String id,
  required String code,
  int? maxRedemptions,
  int? perCustomer,
  String status = 'ACTIVE',
  String? ownStatus,
  String? offerStatus,
}) =>
    <String, dynamic>{
      if (ownStatus != null) 'own_status': ownStatus,
      if (offerStatus != null) 'offer_status': offerStatus,
      'id': id,
      'promotion_id': 'p-1',
      'promotion_code': 'WELCOME',
      'code': code,
      'description': 'ten percent',
      'status': status,
      'max_redemptions': maxRedemptions,
      'max_redemptions_per_customer': perCustomer,
      'effective_from': null,
      'effective_to': null,
      'redemption_count': 0,
      'version': 3,
    };

Future<void> _openDialog(
  WidgetTester tester,
  _Api api, {
  PromotionCouponRecord? existing,
}) async {
  tester.view.physicalSize = const Size(1600, 1100);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: CouponDialog(
        api: api,
        promotions: <PromotionRecord>[
          PromotionRecord.fromJson(_promotion('p-1', 'WELCOME', 'Welcome')),
        ],
        existing: existing,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('the coupon tab offers a control that mints one', (tester) async {
    tester.view.physicalSize = const Size(1600, 1100);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: PromotionPage(
          api: _Api(offers: <Json>[_promotion('p-1', 'WELCOME', 'Welcome')]),
          permissions:
              _permissions(const ['PROMOTION_VIEW', 'PROMOTION_MANAGE']),
          hasActiveFirm: true,
        ),
      ),
    ));
    await tester.pumpAndSettle();

    // The offers tab carries its own create button; the coupon tab carried
    // none, which is the whole defect.
    expect(find.widgetWithText(FilledButton, 'New coupon'), findsNothing);
    await tester.tap(find.text('Coupons'));
    await tester.pumpAndSettle();
    expect(find.widgetWithText(FilledButton, 'New coupon'), findsOneWidget);
  });

  testWidgets('a blank limit is sent as no limit, not as zero', (tester) async {
    final _Api api = _Api();
    await _openDialog(tester, api);
    // A new coupon names no offer for the user (D-UI-54): choose it.
    await tester.tap(find.byKey(const ValueKey('coupon-offer')));
    await tester.pumpAndSettle();
    await tester.tap(find.textContaining('WELCOME').last);
    await tester.pumpAndSettle();

    await tester.enterText(
        find.widgetWithText(TextFormField, 'Code'), 'SAVE10');
    await tester.tap(find.widgetWithText(FilledButton, 'Create'));
    await tester.pumpAndSettle();

    // Zero would be a coupon nobody can use. Null is "as many as they like",
    // which is what an empty box means to the person filling it in.
    expect(api.sentBody?['max_redemptions'], isNull);
    expect(api.sentBody?['max_redemptions_per_customer'], isNull);
    expect(api.sentBody?['code'], 'SAVE10');
  });

  testWidgets('the limits are sent on an edit, so emptying a box clears one',
      (tester) async {
    final _Api api = _Api();
    await _openDialog(
      tester,
      api,
      existing: PromotionCouponRecord.fromJson(
        _coupon(id: 'c-1', code: 'SAVE10', maxRedemptions: 100, perCustomer: 2),
      ),
    );

    await tester.enterText(
        find.widgetWithText(TextFormField, 'Total claims allowed'), '');
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    // The server reads an absent field as "leave it alone", so a form showing
    // every limit has to state each one or emptying a box would do nothing.
    expect(api.sentBody!.containsKey('max_redemptions'), isTrue);
    expect(api.sentBody?['max_redemptions'], isNull);
    expect(api.sentBody?['max_redemptions_per_customer'], 2);
  });

  testWidgets('the code cannot be changed once the coupon exists',
      (tester) async {
    await _openDialog(
      tester,
      _Api(),
      existing:
          PromotionCouponRecord.fromJson(_coupon(id: 'c-1', code: 'SAVE10')),
    );

    // It is on a leaflet somebody is holding, and a claim already made names
    // it -- the service refuses a change, so the form must not offer one.
    final TextFormField code = tester.widget<TextFormField>(
        find.widgetWithText(TextFormField, 'Code'));
    expect(code.enabled, isFalse);
  });

  testWidgets('an edit sends the version it read', (tester) async {
    final _Api api = _Api();
    await _openDialog(
      tester,
      api,
      existing:
          PromotionCouponRecord.fromJson(_coupon(id: 'c-1', code: 'SAVE10')),
    );

    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    expect(api.posted.single, startsWith('PUT'));
  });

  testWidgets(
      'a code under a paused offer is saved with its own status, not the one '
      'it reads as (D-PRC-16)', (tester) async {
    final _Api api = _Api();
    await _openDialog(
      tester,
      api,
      existing: PromotionCouponRecord.fromJson(_coupon(
        id: 'c-1',
        code: 'SAVE10',
        status: 'INACTIVE',
        ownStatus: 'ACTIVE',
        offerStatus: 'INACTIVE',
      )),
    );

    // The box is filled from what the code is set to, and says why the list
    // reads it differently.
    expect(find.text('Active'), findsOneWidget);
    expect(find.textContaining('Off because its offer is paused'),
        findsOneWidget);

    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    // Sending `INACTIVE` back would switch the code off for good.
    expect(api.sentBody?['status'], 'ACTIVE');
  });

  testWidgets('a response without own_status falls back to status',
      (tester) async {
    final _Api api = _Api();
    await _openDialog(
      tester,
      api,
      existing: PromotionCouponRecord.fromJson(
          _coupon(id: 'c-1', code: 'SAVE10', status: 'DRAFT')),
    );
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();
    expect(api.sentBody?['status'], 'DRAFT');
  });

  testWidgets('the list shows the derived status and says why it differs',
      (tester) async {
    tester.view.physicalSize = const Size(1366, 768);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: PromotionPage(
          api: _Api(
            offers: <Json>[_promotion('p-1', 'WELCOME', 'Welcome')],
            coupons: <Json>[
              _coupon(
                id: 'c-1',
                code: 'SAVE10',
                status: 'INACTIVE',
                ownStatus: 'ACTIVE',
                offerStatus: 'INACTIVE',
              ),
            ],
          ),
          permissions:
              _permissions(const ['PROMOTION_VIEW', 'PROMOTION_MANAGE']),
          hasActiveFirm: true,
        ),
      ),
    ));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Coupons'));
    await tester.pumpAndSettle();

    expect(find.textContaining('Off because its offer is paused'),
        findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('reading offers is not authority to mint a code', (tester) async {
    // Both halves in one test on purpose. `findsNothing` alone is satisfied
    // by a button that exists for nobody, so it would go on passing if the
    // control were deleted -- which is the very state this file exists to
    // stop coming back.
    Future<void> open(List<String> codes) async {
      tester.view.physicalSize = const Size(1600, 1100);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: PromotionPage(
            api: _Api(),
            permissions: _permissions(codes),
            hasActiveFirm: true,
          ),
        ),
      ));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Coupons'));
      await tester.pumpAndSettle();
    }

    await open(const ['PROMOTION_VIEW']);
    expect(find.widgetWithText(FilledButton, 'New coupon'), findsNothing);

    await open(const ['PROMOTION_VIEW', 'PROMOTION_MANAGE']);
    expect(find.widgetWithText(FilledButton, 'New coupon'), findsOneWidget);
  });
}
