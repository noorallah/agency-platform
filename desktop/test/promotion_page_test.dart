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
import 'package:agency_desktop/models/customer.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/firm_member.dart';
import 'package:agency_desktop/models/pricing.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/ui/pricing/promotion_dialog.dart';
import 'package:agency_desktop/ui/pricing/promotion_page.dart';
import 'package:agency_desktop/phase2/phase2_scope.dart';
import 'package:agency_desktop/ui/reports/report_catalog.dart';
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
  List<PromotionConditionRecord> conditions =
      const <PromotionConditionRecord>[],
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
      conditions: conditions,
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
  final List<String> deleted = <String>[];

  /// What the condition picker searches when it asks for products.
  List<Product> catalogue = const <Product>[];
  final List<String> productSearches = <String>[];

  @override
  Future<void> deletePromotion(String id) async => deleted.add(id);

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
  Future<PagedResult<Product>> products({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    ProductQuery filters = const ProductQuery(),
  }) async {
    productSearches.add(search);
    final List<Product> hits = catalogue
        .where((item) =>
            item.code.contains(search.toUpperCase()) ||
            item.name.toLowerCase().contains(search.toLowerCase()))
        .toList();
    return PagedResult<Product>(items: hits, total: hits.length);
  }

  @override
  Future<PagedResult<CustomerGroup>> customerGroups({
    int page = 1,
    int pageSize = 100,
    String search = '',
  }) async {
    final List<CustomerGroup> all = <CustomerGroup>[
      CustomerGroup.fromJson(const <String, dynamic>{
        'id': 'g-whole',
        'code': 'WHOLE',
        'name': 'Wholesale',
      }),
      CustomerGroup.fromJson(const <String, dynamic>{
        'id': 'g-retail',
        'code': 'RETAIL',
        'name': 'Retail',
      }),
    ];
    return PagedResult<CustomerGroup>(items: all, total: all.length);
  }

  @override
  Future<List<FirmMember>> firmMembers() async => const <FirmMember>[
        FirmMember(userId: 'u-asha', fullName: 'Asha Rao'),
      ];

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
  bool phase2 = false,
}) async {
  tester.view.physicalSize = const Size(1600, 1200);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    // Above the navigator, so a dialog the page opens is phase 2's too.
    builder: phase2 ? (context, child) => Phase2Scope(child: child!) : null,
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
    await _pumpPage(
        tester, _PromotionApi(rows: <PromotionRecord>[_promotion()]));

    expect(find.text('TEN'), findsOneWidget);
    // The benefit is spelled out rather than shown as an action code: nobody
    // reading this screen knows what LINE_DISCOUNT_PERCENT means.
    expect(find.textContaining('10% off the line'), findsWidgets);
  });

  testWidgets('a condition reads as a sentence, not a rule code',
      (tester) async {
    // `line_quantity GREATER_OR_EQUAL 25` was printed raw (BL-31.15).
    await _pumpPage(
      tester,
      _PromotionApi(rows: <PromotionRecord>[
        _promotion(conditions: const <PromotionConditionRecord>[
          PromotionConditionRecord(
            fieldKey: 'line_quantity',
            operator: 'GREATER_OR_EQUAL',
            valueNumber: '25.0000',
          ),
        ]),
      ]),
      // Read-only: with Edit on double-click a single tap waits on the
      // double-tap timer, and the pane is the same either way.
      manage: false,
    );
    await tester.tap(find.text('TEN'));
    await tester.pump(const Duration(milliseconds: 400));
    await tester.pumpAndSettle();

    expect(find.text('Quantity on the line is at least 25'), findsOneWidget);
    expect(find.textContaining('GREATER_OR_EQUAL'), findsNothing);
  });

  testWidgets('a condition on a product names the product, not its id',
      (tester) async {
    // A product condition was shown as a bare id (BL-31.15).
    await _pumpPage(
      tester,
      _PromotionApi(rows: <PromotionRecord>[
        _promotion(conditions: const <PromotionConditionRecord>[
          PromotionConditionRecord(
            fieldKey: 'product_id',
            operator: 'EQUALS',
            valueText: 'p-milk',
            valueLabel: 'MILK — Milk',
          ),
        ]),
      ]),
      manage: false,
    );
    await tester.tap(find.text('TEN'));
    await tester.pump(const Duration(milliseconds: 400));
    await tester.pumpAndSettle();

    expect(find.text('Product is MILK — Milk'), findsOneWidget);
    expect(find.textContaining('p-milk'), findsNothing);
  });

  testWidgets('a product is picked by name and sent by id', (tester) async {
    final _PromotionApi api = _PromotionApi()
      ..catalogue = <Product>[
        Product.fromJson(const <String, dynamic>{
          'id': 'p-milk',
          'code': 'MILK',
          'name': 'Milk'
        }),
        Product.fromJson(const <String, dynamic>{
          'id': 'p-tea',
          'code': 'TEA',
          'name': 'Tea'
        }),
      ];
    await _pumpDialog(
      tester,
      api,
      existing: _promotion(conditions: const <PromotionConditionRecord>[
        PromotionConditionRecord(
          fieldKey: 'product_id',
          operator: 'EQUALS',
          valueText: 'p-old',
          valueLabel: 'OLD — Old stock',
        ),
      ]),
    );

    // An existing condition opens with its name, not its id.
    final Finder picker = find.widgetWithText(TextFormField, 'OLD — Old stock');
    expect(picker, findsOneWidget);

    await tester.enterText(picker, 'mil');
    await tester.pumpAndSettle();
    expect(api.productSearches, contains('mil'));
    await tester.tap(find.text('MILK — Milk'));
    await tester.pumpAndSettle();

    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    final List<dynamic> conditions = api.savedBody!['conditions'] as List;
    expect((conditions.single as Map)['value_text'], 'p-milk');
  });

  testWidgets('a name typed but not picked is refused before it is sent',
      (tester) async {
    final _PromotionApi api = _PromotionApi();
    await _pumpDialog(
      tester,
      api,
      existing: _promotion(conditions: const <PromotionConditionRecord>[
        PromotionConditionRecord(
          fieldKey: 'product_id',
          operator: 'EQUALS',
          valueText: 'p-old',
          valueLabel: 'OLD — Old stock',
        ),
      ]),
    );

    await tester.enterText(
      find.widgetWithText(TextFormField, 'OLD — Old stock'),
      'nothing like it',
    );
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    expect(api.savedBody, isNull);
    expect(find.text('Pick one from the list.'), findsOneWidget);
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

  testWidgets('saving an active offer says a new revision was made',
      (tester) async {
    final _PromotionApi api =
        _PromotionApi(rows: <PromotionRecord>[_promotion(code: 'BULK5')]);
    await _pumpPage(tester, api);

    await tester.tap(find.text('BULK5'));
    await tester.pump(const Duration(milliseconds: 50));
    await tester.tap(find.text('BULK5'));
    await tester.pumpAndSettle();
    expect(find.byType(PromotionDialog), findsOneWidget);

    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    // An active offer is superseded rather than changed, and until the toast
    // the only sign was a second row after Refresh.
    expect(
      find.textContaining('saved as a new revision'),
      findsOneWidget,
    );
  });

  testWidgets('a benefit with no figure is refused before it is sent',
      (tester) async {
    final _PromotionApi api = _PromotionApi();
    await _pumpDialog(tester, api);

    await tester.enterText(find.widgetWithText(TextFormField, 'Code'), 'NEW');
    await tester.enterText(
        find.widgetWithText(TextFormField, 'Name'), 'New offer');
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
    final _PromotionApi api =
        _PromotionApi(rows: <PromotionRecord>[_promotion()])
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

  // D-QA-7: the dialog had no coupon-only switch, so an offer meant for
  // coupon holders applied to everyone, and every pricing case after it failed.
  testWidgets('an offer can be made coupon-only, with limits', (tester) async {
    final _PromotionApi api = _PromotionApi();
    await _pumpDialog(tester, api, existing: _promotion());

    await tester.tap(find.byKey(const ValueKey('promotion-requires-coupon')));
    await tester.enterText(
        find.byKey(const ValueKey('promotion-max-redemptions')), '100');
    await tester.enterText(
        find.byKey(const ValueKey('promotion-max-per-customer')), '1');
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    expect(api.savedBody?['requires_coupon'], isTrue);
    expect(api.savedBody?['max_redemptions'], 100);
    expect(api.savedBody?['max_redemptions_per_customer'], 1);
  });

  testWidgets('an edit keeps the coupon rule and limits it was read with',
      (tester) async {
    final _PromotionApi api = _PromotionApi();
    const PromotionRecord base = PromotionRecord(
      id: 'promo-1',
      code: 'CPN',
      name: 'Coupon offer',
      version: 2,
      status: 'ACTIVE',
      requiresCoupon: true,
      maxRedemptions: 50,
      actions: <PromotionActionRecord>[
        PromotionActionRecord(
            actionType: 'LINE_DISCOUNT_PERCENT', percent: '10'),
      ],
    );
    await _pumpDialog(tester, api, existing: base);

    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    // An update replaces the offer: a field left out would be cleared.
    expect(api.savedBody?['requires_coupon'], isTrue);
    expect(api.savedBody?['max_redemptions'], 50);
    expect(api.savedBody?['max_redemptions_per_customer'], isNull);
  });

  // SEL-11: the promotion write is a full replace, so both keys always go.
  testWidgets('an own offer sends no principal and a full share',
      (tester) async {
    final _PromotionApi api = _PromotionApi();
    await _pumpDialog(tester, api, existing: _promotion());

    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    expect(api.savedBody!.containsKey('principal_id'), isTrue);
    expect(api.savedBody!['principal_id'], isNull);
    expect(api.savedBody!['principal_share_percent'], '100');
  });

  testWidgets('a principal-funded offer sends the principal and its share',
      (tester) async {
    final _PromotionApi api = _PromotionApi();
    await _pumpDialog(tester, api, existing: _promotion());

    // Off until a principal is chosen.
    expect(
        tester
            .widget<TextFormField>(
                find.byKey(const ValueKey('promotion-principal-share')))
            .enabled,
        isFalse);
    await tester.ensureVisible(find.byKey(const ValueKey('promotion-principal')));
    await tester.tap(find.byKey(const ValueKey('promotion-principal')));
    await tester.pumpAndSettle();
    await tester.tap(find.textContaining('Hindustan Foods').last);
    await tester.pumpAndSettle();
    await tester.enterText(
        find.byKey(const ValueKey('promotion-principal-share')), '60');
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    expect(api.savedBody!['principal_id'], 'pr-1');
    expect(api.savedBody!['principal_share_percent'], '60');
  });

  testWidgets('a share above 100 is refused before it is sent',
      (tester) async {
    final _PromotionApi api = _PromotionApi();
    await _pumpDialog(tester, api, existing: _promotion());
    await tester.ensureVisible(find.byKey(const ValueKey('promotion-principal')));
    await tester.tap(find.byKey(const ValueKey('promotion-principal')));
    await tester.pumpAndSettle();
    await tester.tap(find.textContaining('Hindustan Foods').last);
    await tester.pumpAndSettle();
    await tester.enterText(
        find.byKey(const ValueKey('promotion-principal-share')), '120');
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    expect(api.savedBody, isNull);
    expect(find.text('Above 0 and up to 100'), findsOneWidget);
  });

  testWidgets('an edit keeps the principal it was read with', (tester) async {
    final _PromotionApi api = _PromotionApi();
    const PromotionRecord base = PromotionRecord(
      id: 'promo-1',
      code: 'FND',
      name: 'Funded offer',
      version: 2,
      status: 'ACTIVE',
      principalId: 'pr-1',
      principalSharePercent: '40',
      actions: <PromotionActionRecord>[
        PromotionActionRecord(
            actionType: 'LINE_DISCOUNT_PERCENT', percent: '10'),
      ],
    );
    await _pumpDialog(tester, api, existing: base);

    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    expect(api.savedBody!['principal_id'], 'pr-1');
    expect(api.savedBody!['principal_share_percent'], '40');
  });

  testWidgets('a limit of zero is refused before it is sent', (tester) async {
    final _PromotionApi api = _PromotionApi();
    await _pumpDialog(tester, api, existing: _promotion());

    await tester.enterText(
        find.byKey(const ValueKey('promotion-max-redemptions')), '0');
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    expect(api.savedBody, isNull);
    expect(find.text('A whole number of 1 or more, or blank'), findsOneWidget);
  });

  testWidgets('phase 2 names the picked offer on a bar and reads it in a window',
      (tester) async {
    // Option C (owner, 2026-09-27): no side pane; the bar names the offer
    // and carries Open, Edit and Delete.
    await _pumpPage(
      tester,
      _PromotionApi(rows: <PromotionRecord>[_promotion()]),
      phase2: true,
    );
    await tester.tap(find.text('TEN').first);
    await tester.pump(const Duration(milliseconds: 500));
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('selection-bar')), findsOneWidget);
    expect(find.byKey(const ValueKey('selection-edit')), findsOneWidget);
    expect(find.byKey(const ValueKey('selection-delete')), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('selection-view')));
    await tester.pumpAndSettle();
    expect(find.byType(AlertDialog), findsOneWidget);
  });

  testWidgets('retiring a promotion asks first (D-DLG-2)', (tester) async {
    final _PromotionApi api =
        _PromotionApi(rows: <PromotionRecord>[_promotion()]);
    await _pumpPage(tester, api, phase2: true);
    await tester.tap(find.text('TEN').first);
    await tester.pump(const Duration(milliseconds: 500));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('selection-delete')));
    await tester.pumpAndSettle();

    expect(find.byType(AlertDialog), findsOneWidget);
    expect(api.deleted, isEmpty);
    await tester.tap(find.widgetWithText(TextButton, 'Cancel'));
    await tester.pumpAndSettle();
    expect(api.deleted, isEmpty);

    await tester.tap(find.byKey(const ValueKey('selection-delete')));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Retire'));
    await tester.pumpAndSettle();
    expect(api.deleted, ['promo-1']);
  });

  // D-SELL-42: the screen offered only part of what the server supports.
  group('the promotion screen offers everything the server accepts', () {
    Future<void> pickFrom(
      WidgetTester tester,
      String label,
      String item, {
      int at = 0,
    }) async {
      final Finder box =
          find.widgetWithText(DropdownButtonFormField<String>, label);
      await tester.ensureVisible(box.at(at));
      await tester.tap(box.at(at));
      await tester.pumpAndSettle();
      await tester.tap(find.text(item).last);
      await tester.pumpAndSettle();
    }

    Future<void> addCondition(WidgetTester tester) async {
      await tester.ensureVisible(find.text('Add condition'));
      await tester.tap(find.text('Add condition'));
      await tester.pumpAndSettle();
    }

    Future<void> nameIt(WidgetTester tester) async {
      await tester.enterText(find.widgetWithText(TextFormField, 'Code'), 'NEW');
      await tester.enterText(
          find.widgetWithText(TextFormField, 'Name'), 'New offer');
    }

    Future<void> save(WidgetTester tester) async {
      await tester.tap(find.widgetWithText(FilledButton, 'Save'));
      await tester.pumpAndSettle();
    }

    testWidgets('free delivery takes no figure and is sent as such',
        (tester) async {
      final _PromotionApi api = _PromotionApi();
      await _pumpDialog(tester, api);
      await nameIt(tester);
      await pickFrom(tester, 'Benefit', 'Free delivery');
      expect(find.text('A benefit needs a figure.'), findsNothing);
      await save(tester);

      final Map<dynamic, dynamic> action =
          (api.savedBody!['actions'] as List).single as Map;
      expect(action, <String, dynamic>{
        'sequence': 1,
        'action_type': 'FREE_SHIPPING',
      });
    });

    testWidgets('a free product names the product and how many',
        (tester) async {
      final _PromotionApi api = _PromotionApi()
        ..catalogue = <Product>[
          Product.fromJson(const <String, dynamic>{
            'id': 'p-pen',
            'code': 'PEN',
            'name': 'Pen',
          }),
        ];
      await _pumpDialog(tester, api);
      await nameIt(tester);
      await pickFrom(tester, 'Benefit', 'A free product (buy X, get another)');

      // Refused until a product is chosen.
      await save(tester);
      expect(api.savedBody, isNull);
      expect(find.text('Pick the product to give away.'), findsOneWidget);

      await tester.enterText(
          find.widgetWithText(TextFormField, 'Product given away'), 'pen');
      await tester.pumpAndSettle();
      await tester.tap(find.text('PEN — Pen'));
      await tester.pumpAndSettle();
      await tester.enterText(find.widgetWithText(TextFormField, 'Buy'), '10');
      await tester.enterText(
          find.widgetWithText(TextFormField, 'Get free'), '2');
      await save(tester);

      final Map<dynamic, dynamic> action =
          (api.savedBody!['actions'] as List).single as Map;
      expect(action['action_type'], 'FREE_PRODUCT');
      expect(action['free_product_id'], 'p-pen');
      expect(action['buy_quantity'], '10');
      expect(action['free_quantity'], '2');
      expect(action.containsKey('percent'), isFalse);
    });

    testWidgets('a percentage with a cap sends the cap; without, none',
        (tester) async {
      // 60 item 1: "20% off, up to 500".
      final _PromotionApi api = _PromotionApi();
      await _pumpDialog(tester, api);
      await nameIt(tester);
      await tester.enterText(
          find.widgetWithText(TextFormField, 'Percent'), '20');
      await tester.enterText(
          find.byKey(const ValueKey('promotion-action-cap-0')), '500');
      await save(tester);

      final Map<dynamic, dynamic> action =
          (api.savedBody!['actions'] as List).single as Map;
      expect(action['percent'], '20');
      expect(action['max_amount'], '500');
    });

    testWidgets('the new fields and tests are all on offer', (tester) async {
      await _pumpDialog(tester, _PromotionApi());
      await addCondition(tester);
      await tester
          .tap(find.widgetWithText(DropdownButtonFormField<String>, 'When'));
      await tester.pumpAndSettle();
      for (final String label in <String>[
        'Customer group',
        'Branch',
        'Salesman',
        'Document type',
        'Document date',
      ]) {
        expect(find.text(label), findsWidgets, reason: label);
      }
      await tester.tap(find.text('Customer group').last);
      await tester.pumpAndSettle();
      await tester
          .tap(find.widgetWithText(DropdownButtonFormField<String>, 'Test'));
      await tester.pumpAndSettle();
      for (final String label in <String>[
        'is one of',
        'is none of',
        'is set',
        'is not set',
      ]) {
        expect(find.text(label), findsWidgets, reason: label);
      }
      expect(find.text('is between'), findsNothing,
          reason: 'BETWEEN reads numbers only');
    });

    testWidgets('one of several groups sends a list', (tester) async {
      final _PromotionApi api = _PromotionApi();
      await _pumpDialog(tester, api);
      await nameIt(tester);
      await tester.enterText(
          find.widgetWithText(TextFormField, 'Percent'), '5');
      await addCondition(tester);
      await pickFrom(tester, 'When', 'Customer group');
      await pickFrom(tester, 'Test', 'is one of');

      // Nothing chosen yet: said before it is sent.
      await save(tester);
      expect(api.savedBody, isNull);
      expect(find.textContaining('Add at least one value'), findsOneWidget);

      for (final String pick in <String>[
        'WHOLE — Wholesale',
        'RETAIL — Retail',
      ]) {
        await tester.tap(find.widgetWithText(TextFormField, 'Add one'));
        await tester.pumpAndSettle();
        await tester.tap(find.text(pick).last);
        await tester.pumpAndSettle();
      }
      expect(find.byType(InputChip), findsNWidgets(2));
      await save(tester);

      final Map<dynamic, dynamic> condition =
          (api.savedBody!['conditions'] as List).single as Map;
      expect(condition['field_key'], 'customer_group_id');
      expect(condition['operator'], 'IN');
      expect(condition['value_json'], <String>['g-whole', 'g-retail']);
      expect(condition.containsKey('value_text'), isFalse);
    });

    testWidgets('between two numbers sends both bounds', (tester) async {
      final _PromotionApi api = _PromotionApi();
      await _pumpDialog(tester, api);
      await nameIt(tester);
      await tester.enterText(
          find.widgetWithText(TextFormField, 'Percent'), '5');
      await addCondition(tester);
      await pickFrom(tester, 'When', 'Quantity on the line');
      await pickFrom(tester, 'Test', 'is between');
      await tester.enterText(find.widgetWithText(TextFormField, 'Min'), '10');
      await tester.enterText(find.widgetWithText(TextFormField, 'Max'), '50');
      await save(tester);

      final Map<dynamic, dynamic> condition =
          (api.savedBody!['conditions'] as List).single as Map;
      expect(condition['operator'], 'BETWEEN');
      expect(condition['value_json'], <num>[10, 50]);
    });

    testWidgets('is set sends no value at all', (tester) async {
      final _PromotionApi api = _PromotionApi();
      await _pumpDialog(tester, api);
      await nameIt(tester);
      await tester.enterText(
          find.widgetWithText(TextFormField, 'Percent'), '5');
      await addCondition(tester);
      await pickFrom(tester, 'When', 'Salesman');
      await pickFrom(tester, 'Test', 'is set');
      expect(find.text('Nothing to enter.'), findsOneWidget);
      await save(tester);

      expect((api.savedBody!['conditions'] as List).single, <String, dynamic>{
        'sequence': 1,
        'field_key': 'salesman_id',
        'operator': 'EXISTS',
      });
    });

    testWidgets('a document type and a date are chosen, not typed as ids',
        (tester) async {
      final _PromotionApi api = _PromotionApi();
      await _pumpDialog(tester, api);
      await nameIt(tester);
      await tester.enterText(
          find.widgetWithText(TextFormField, 'Percent'), '5');
      await addCondition(tester);
      await pickFrom(tester, 'When', 'Document type');
      await pickFrom(tester, 'Document', 'Quotation');
      await addCondition(tester);
      await pickFrom(tester, 'When', 'Document date', at: 1);
      await pickFrom(tester, 'Test', 'is at least', at: 1);
      await tester.enterText(
          find.widgetWithText(TextFormField, 'Date'), '2026-10-01');
      await save(tester);

      final List<dynamic> conditions = api.savedBody!['conditions'] as List;
      expect((conditions[0] as Map)['value_text'], 'SALES_QUOTATION');
      expect((conditions[1] as Map)['value_date'], '2026-10-01');
      expect((conditions[1] as Map).containsKey('value_text'), isFalse);
    });

    testWidgets('a saved list reads back with names and stays overflow-free',
        (tester) async {
      tester.view.physicalSize = const Size(1366, 768);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      final _PromotionApi api = _PromotionApi();
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: Builder(
            builder: (context) => TextButton(
              onPressed: () => showDialog<bool>(
                context: context,
                builder: (_) => PromotionDialog(
                  api: api,
                  existing: _promotion(
                    conditions: const <PromotionConditionRecord>[
                      PromotionConditionRecord(
                        fieldKey: 'customer_group_id',
                        operator: 'IN',
                        valueList: <String>['g-whole', 'g-retail'],
                      ),
                      PromotionConditionRecord(
                        fieldKey: 'line_quantity',
                        operator: 'BETWEEN',
                        valueList: <String>['10', '50'],
                      ),
                    ],
                  ),
                ),
              ),
              child: const Text('open'),
            ),
          ),
        ),
      ));
      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();

      expect(find.widgetWithText(InputChip, 'WHOLE — Wholesale'),
          findsOneWidget);
      expect(
          find.widgetWithText(InputChip, 'RETAIL — Retail'), findsOneWidget);
      expect(tester.takeException(), isNull);

      await tester.tap(find.widgetWithText(FilledButton, 'Save'));
      await tester.pumpAndSettle();
      final List<dynamic> conditions = api.savedBody!['conditions'] as List;
      expect((conditions[0] as Map)['value_json'],
          <String>['g-whole', 'g-retail']);
      expect((conditions[1] as Map)['value_json'], <num>[10, 50]);
    });
  });

  testWidgets('a condition reads as a sentence for the new tests',
      (tester) async {
    expect(
      describePromotionCondition(const PromotionConditionRecord(
          fieldKey: 'line_quantity',
          operator: 'BETWEEN',
          valueList: <String>['10.0000', '50'])),
      'Quantity on the line is between 10 and 50',
    );
    expect(
      describePromotionCondition(const PromotionConditionRecord(
          fieldKey: 'salesman_id', operator: 'EXISTS')),
      'Salesman is set',
    );
    expect(
      describePromotionCondition(const PromotionConditionRecord(
          fieldKey: 'transaction_type',
          operator: 'EQUALS',
          valueText: 'SALES_QUOTATION')),
      'Document type is Quotation',
    );
  });

  group('the scheme budgets', () {
    const PromotionRecord budgeted = PromotionRecord(
      id: 'promo-1',
      code: 'BUD',
      name: 'Budgeted offer',
      version: 2,
      status: 'ACTIVE',
      maxBenefitAmount: '5000.0000',
      benefitAmountClaimed: '1200.0000',
      remainingBenefitAmount: '3800.0000',
      maxFreeQuantity: '300.0000',
      freeQuantityClaimed: '40.0000',
      remainingFreeQuantity: '260.0000',
      actions: <PromotionActionRecord>[
        PromotionActionRecord(
            actionType: 'LINE_DISCOUNT_PERCENT', percent: '10'),
      ],
    );

    testWidgets('both boxes are sent when filled', (tester) async {
      final _PromotionApi api = _PromotionApi();
      await _pumpDialog(tester, api, existing: _promotion());
      expect(find.text('Budget (value)'), findsOneWidget);
      expect(find.text('Budget (free units)'), findsOneWidget);
      await tester.enterText(
          find.byKey(const ValueKey('promotion-max-benefit')), '5000');
      await tester.enterText(
          find.byKey(const ValueKey('promotion-max-free-units')), '300');
      await tester.tap(find.widgetWithText(FilledButton, 'Save'));
      await tester.pumpAndSettle();

      expect(api.savedBody?['max_benefit_amount'], '5000');
      expect(api.savedBody?['max_free_quantity'], '300');
    });

    testWidgets('a saved offer shows what is used and left, untouched sends '
        'its figure', (tester) async {
      final _PromotionApi api = _PromotionApi();
      await _pumpDialog(tester, api, existing: budgeted);
      expect(find.text('Used 1200, left 3800'), findsOneWidget);
      expect(find.text('Used 40, left 260'), findsOneWidget);
      await tester.tap(find.widgetWithText(FilledButton, 'Save'));
      await tester.pumpAndSettle();

      expect(api.savedBody?['max_benefit_amount'], '5000');
      expect(api.savedBody?['max_free_quantity'], '300');
    });

    testWidgets('a budget that was set and is emptied is sent as null',
        (tester) async {
      final _PromotionApi api = _PromotionApi();
      await _pumpDialog(tester, api, existing: budgeted);
      await tester.enterText(
          find.byKey(const ValueKey('promotion-max-benefit')), '');
      await tester.tap(find.widgetWithText(FilledButton, 'Save'));
      await tester.pumpAndSettle();

      expect(api.savedBody!.containsKey('max_benefit_amount'), isTrue);
      expect(api.savedBody!['max_benefit_amount'], isNull);
      expect(api.savedBody?['max_free_quantity'], '300');
    });

    testWidgets('an offer with no budget on file sends nothing when blank',
        (tester) async {
      final _PromotionApi api = _PromotionApi();
      await _pumpDialog(tester, api, existing: _promotion());
      await tester.tap(find.widgetWithText(FilledButton, 'Save'));
      await tester.pumpAndSettle();

      expect(api.savedBody!.containsKey('max_benefit_amount'), isFalse);
      expect(api.savedBody!.containsKey('max_free_quantity'), isFalse);
    });

    testWidgets('a budget of zero is refused before it is sent',
        (tester) async {
      final _PromotionApi api = _PromotionApi();
      await _pumpDialog(tester, api, existing: _promotion());
      await tester.enterText(
          find.byKey(const ValueKey('promotion-max-free-units')), '0');
      await tester.tap(find.widgetWithText(FilledButton, 'Save'));
      await tester.pumpAndSettle();

      expect(api.savedBody, isNull);
      expect(find.text('A number above 0, or blank'), findsOneWidget);
    });

    testWidgets('the editor fits 1366x768 without overflow', (tester) async {
      final _PromotionApi api = _PromotionApi();
      await _pumpDialog(tester, api, existing: budgeted);
      tester.view.physicalSize = const Size(1366, 768);
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
    });

    testWidgets('the offer window reads what is used and left',
        (tester) async {
      await _pumpPage(
        tester,
        _PromotionApi(rows: <PromotionRecord>[budgeted]),
        phase2: true,
      );
      await tester.tap(find.text('BUD').first);
      await tester.pump(const Duration(milliseconds: 500));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('selection-view')));
      await tester.pumpAndSettle();

      expect(find.byKey(const ValueKey('promotion-budget-value')),
          findsOneWidget);
      expect(find.textContaining('1200.0000 used, 3800.0000 left'),
          findsOneWidget);
      expect(find.textContaining('40.0000 used, 260.0000 left'),
          findsOneWidget);
    });

    test('the performance and claims reports name the free units and budgets',
        () {
      final Set<String> performance = reportCatalog
          .firstWhere((report) => report.id == 'promotion-performance')
          .columns
          .map((column) => column.key)
          .toSet();
      expect(
        performance,
        containsAll(<String>[
          'free_quantity',
          'max_benefit_amount',
          'remaining_benefit_amount',
          'max_free_quantity',
          'remaining_free_quantity',
        ]),
      );
      final Set<String> claims = reportCatalog
          .firstWhere((report) => report.id == 'promotion-redemptions')
          .columns
          .map((column) => column.key)
          .toSet();
      expect(claims, contains('free_quantity'));
    });

    test('all three offer reports have a Free units column', () {
      for (final String id in <String>[
        'promotion-performance',
        'promotion-redemptions',
        'promotion-coupons',
      ]) {
        final column = reportCatalog
            .firstWhere((report) => report.id == id)
            .columns
            .firstWhere((column) => column.key == 'free_quantity');
        expect(column.label, 'Free units', reason: id);
        expect(column.numeric, isTrue, reason: id);
      }
    });
  });
}
