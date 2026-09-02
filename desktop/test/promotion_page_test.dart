// The offers a firm is running, and the two things about them that surprise
// people.
//
// A promotion is not a price list. Several apply to one order, in priority
// order, and each says whether it lets the ones behind it apply too. So the
// screen has to say, in words:
//
// 1. Percentages **compound on what is left** — two ten percent offers take
//    nineteen percent, not twenty. A firm that configures "10 + 10" and is
//    billed 19 will otherwise raise a ticket nobody can answer.
// 2. A promotion that does not stack **ends the stack**, rather than merely
//    being the last one somebody happened to write.
//
// And the save has to carry the version it read, because a live promotion is
// superseded rather than edited: a lost race produces a revision built on a
// promotion somebody else already replaced.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/pricing.dart';
import 'package:agency_desktop/ui/pricing/promotion_dialog.dart';
import 'package:agency_desktop/ui/pricing/promotion_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions({bool manage = true}) => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': <String>[
      'PROMOTION_VIEW',
      if (manage) 'PROMOTION_MANAGE',
    ],
  }));

PromotionRecord _promotion({
  String id = 'promo-1',
  String code = 'TEN',
  String name = 'Ten percent off',
  int version = 4,
  int priority = 10,
  bool allowStacking = true,
  List<PromotionActionRecord> actions = const <PromotionActionRecord>[
    PromotionActionRecord(actionType: 'LINE_DISCOUNT_PERCENT', percent: '10'),
  ],
}) =>
    PromotionRecord(
      id: id,
      code: code,
      name: name,
      version: version,
      priority: priority,
      status: 'ACTIVE',
      allowStacking: allowStacking,
      actions: actions,
    );

class _PromotionApi extends ApiClient {
  _PromotionApi({this.rows = const <PromotionRecord>[]})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<PromotionRecord> rows;
  List<PromotionCouponRecord> coupons = const <PromotionCouponRecord>[];

  Json? savedBody;
  int? sentVersion;
  String? updatedId;

  @override
  Future<PagedResult<PromotionRecord>> promotions({
    int page = 1,
    int pageSize = 20,
    String search = '',
  }) async =>
      PagedResult<PromotionRecord>(items: rows, total: rows.length);

  @override
  Future<PagedResult<PromotionCouponRecord>> promotionCoupons({
    int page = 1,
    int pageSize = 20,
    String search = '',
  }) async =>
      PagedResult<PromotionCouponRecord>(
        items: coupons,
        total: coupons.length,
      );

  @override
  Future<PromotionRecord> createPromotion(Json body) async {
    savedBody = body;
    return _promotion();
  }

  @override
  Future<PromotionRecord> updatePromotion(
    String id,
    Json body, {
    int? expectedVersion,
  }) async {
    updatedId = id;
    savedBody = body;
    sentVersion = expectedVersion;
    return _promotion();
  }
}

Future<void> _pumpPage(
  WidgetTester tester,
  _PromotionApi api, {
  bool manage = true,
}) async {
  tester.view.physicalSize = const Size(1600, 1200);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: PromotionPage(
        api: api,
        permissions: _permissions(manage: manage),
        hasActiveFirm: true,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

Future<void> _pumpDialog(
  WidgetTester tester,
  _PromotionApi api, {
  PromotionRecord? existing,
}) async {
  tester.view.physicalSize = const Size(1600, 1400);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Builder(
        builder: (context) => TextButton(
          onPressed: () => showDialog<bool>(
            context: context,
            builder: (_) => PromotionDialog(api: api, existing: existing),
          ),
          child: const Text('open'),
        ),
      ),
    ),
  ));
  await tester.tap(find.text('open'));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('the list says what each offer gives and where it applies',
      (tester) async {
    await _pumpPage(tester, _PromotionApi(rows: <PromotionRecord>[_promotion()]));

    expect(find.text('TEN'), findsOneWidget);
    // The benefit is spelled out rather than shown as an action code: nobody
    // reading this screen knows what LINE_DISCOUNT_PERCENT means.
    expect(find.textContaining('10% off the line'), findsWidgets);
  });

  testWidgets('a promotion that does not stack says it ends the stack',
      (tester) async {
    await _pumpPage(
      tester,
      _PromotionApi(rows: <PromotionRecord>[_promotion(allowStacking: false)]),
    );

    expect(find.text('Ends here'), findsOneWidget);
  });

  testWidgets('the compounding rule is stated, not left to be discovered',
      (tester) async {
    await _pumpDialog(tester, _PromotionApi());

    expect(
      find.textContaining('nineteen percent, not twenty'),
      findsOneWidget,
      reason: 'a firm configuring 10 + 10 and billed 19 must be told why',
    );
  });

  testWidgets('an edit sends the version it read', (tester) async {
    final _PromotionApi api = _PromotionApi();
    await _pumpDialog(tester, api, existing: _promotion(version: 4));

    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    expect(api.updatedId, 'promo-1');
    expect(
      api.sentVersion,
      4,
      reason: 'a live promotion is superseded, so a lost race would build a '
          'revision on one somebody else already replaced',
    );
  });

  testWidgets('a benefit with no figure is refused before it is sent',
      (tester) async {
    final _PromotionApi api = _PromotionApi();
    await _pumpDialog(tester, api);

    await tester.enterText(find.widgetWithText(TextFormField, 'Code'), 'NEW');
    await tester.enterText(find.widgetWithText(TextFormField, 'Name'), 'New offer');
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    expect(api.savedBody, isNull);
    expect(find.text('A benefit needs a figure.'), findsOneWidget);
  });

  testWidgets('without the manage permission there is nothing to press',
      (tester) async {
    await _pumpPage(
      tester,
      _PromotionApi(rows: <PromotionRecord>[_promotion()]),
      manage: false,
    );

    expect(find.widgetWithText(FilledButton, 'New promotion'), findsNothing);
  });

  testWidgets('the coupon list says how much of each is left', (tester) async {
    final _PromotionApi api = _PromotionApi(rows: <PromotionRecord>[_promotion()])
      ..coupons = const <PromotionCouponRecord>[
        PromotionCouponRecord(
          id: 'c-1',
          promotionId: 'promo-1',
          promotionCode: 'TEN',
          code: 'SAVE10',
          maxRedemptions: 100,
          redemptionCount: 37,
        ),
      ];
    await _pumpPage(tester, api);

    await tester.tap(find.text('Coupons'));
    await tester.pumpAndSettle();

    expect(find.text('SAVE10'), findsOneWidget);
    // What is left, not only what was allowed -- a limit on its own does not
    // tell somebody whether the campaign is nearly spent.
    expect(find.text('37 of 100 used'), findsOneWidget);
  });

  testWidgets('an unlimited coupon says so rather than showing a blank',
      (tester) async {
    final _PromotionApi api = _PromotionApi()
      ..coupons = const <PromotionCouponRecord>[
        PromotionCouponRecord(
          id: 'c-2',
          promotionId: 'promo-1',
          promotionCode: 'TEN',
          code: 'OPEN',
          redemptionCount: 5,
        ),
      ];
    await _pumpPage(tester, api);

    await tester.tap(find.text('Coupons'));
    await tester.pumpAndSettle();

    expect(find.text('5 used'), findsOneWidget);
    expect(find.text('No limit'), findsOneWidget);
  });
}
