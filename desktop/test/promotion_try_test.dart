// Trying offers before they go live (backlog 60, item 13).
//
// The screen asks the server what a made-up document would earn and shows the
// reasons: which offers applied, which did not, and why. These tests pin that
// the request carries what was typed and that the answer is readable.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/customer.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/pricing.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/phase2/phase2_scope.dart';
import 'package:agency_desktop/ui/pricing/promotion_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

class _TryApi extends ApiClient {
  _TryApi({this.refuse = false})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final bool refuse;
  Json? sent;

  @override
  Future<PagedResult<PromotionRecord>> promotions({
    int page = 1,
    int pageSize = 20,
    String search = '',
  }) async =>
      const PagedResult<PromotionRecord>(items: <PromotionRecord>[], total: 0);

  @override
  Future<PagedResult<Product>> products({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    ProductQuery filters = const ProductQuery(),
  }) async {
    final List<Product> all = <Product>[
      Product.fromJson(const <String, dynamic>{
        'id': 'p-milk',
        'code': 'MILK',
        'name': 'Milk',
        'selling_price': '50',
      }),
    ];
    return PagedResult<Product>(items: all, total: all.length);
  }

  @override
  Future<PagedResult<Customer>> customers({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    CustomerQuery filters = const CustomerQuery(),
  }) async {
    final List<Customer> all = <Customer>[
      Customer.fromJson(const <String, dynamic>{
        'id': 'c-asha',
        'code': 'ASHA',
        'name': 'Asha Stores',
        'customer_group_id': 'g-whole',
      }),
    ];
    return PagedResult<Customer>(items: all, total: all.length);
  }

  @override
  Future<PromotionTryResult> simulatePromotions(Json body) async {
    sent = body;
    if (refuse) throw const ApiException('The date is outside any year.');
    return PromotionTryResult.fromJson(const <String, dynamic>{
      'lines': [
        {
          'line_number': 1,
          'discount_amount': '25.00',
          'free_quantity': '0',
          'applied_promotion_codes': ['TEN'],
        },
      ],
      'bill_discount_amount': '0',
      'freight_waived': '0',
      'applied_promotion_codes': ['TEN'],
      'applied': [
        {'promotion_id': 'x', 'code': 'TEN', 'benefit_amount': '25.00'},
      ],
      'gifts': [
        {'product_id': 'p-milk', 'quantity': '2', 'promotion_code': 'GIFT'},
      ],
      'decisions': [
        {
          'promotion_id': 'x',
          'code': 'TEN',
          'priority': 10,
          'matched': true,
          'reason': 'Every condition held.',
        },
        {
          'promotion_id': 'y',
          'code': 'FEST',
          'priority': 20,
          'matched': false,
          'reason': 'Needs a coupon code.',
        },
      ],
    });
  }
}

Future<void> _openTry(WidgetTester tester, _TryApi api) async {
  tester.view.physicalSize = const Size(800, 600);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final PermissionService permissions = PermissionService()
    ..applyAccessToken(_accessToken({
      'roles': <String>['user'],
      'permissions': <String>['PROMOTION_VIEW'],
    }));
  await tester.pumpWidget(MaterialApp(
    builder: (context, child) => Phase2Scope(child: child!),
    home: Scaffold(
      body: PromotionPage(
        api: api,
        permissions: permissions,
        hasActiveFirm: true,
      ),
    ),
  ));
  await tester.pumpAndSettle();
  // A command about the whole list lives behind "...", never on the line.
  await tester.tap(find.byKey(const ValueKey('toolbar-more')));
  await tester.pumpAndSettle();
  await tester
      .tap(find.byKey(const ValueKey('toolbar-command-try-offers-menu')));
  await tester.pumpAndSettle();
}

Future<void> _pick(WidgetTester tester, Finder field, String typed) async {
  await tester.tap(field);
  await tester.enterText(field, typed);
  await tester.pumpAndSettle();
  await tester.tap(find.textContaining(typed.toUpperCase()).last);
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('Try offers sends what was typed and shows the reasons',
      (tester) async {
    final _TryApi api = _TryApi();
    await _openTry(tester, api);

    expect(find.text('Try offers'), findsWidgets);
    await tester.enterText(find.byKey(const Key('try-date')), '2026-12-01');
    await _pick(
        tester,
        find.descendant(
            of: find.byKey(const Key('try-customer')),
            matching: find.byType(TextFormField)),
        'asha');
    await _pick(
        tester,
        find.descendant(
            of: find.byKey(const Key('try-product-0')),
            matching: find.byType(TextFormField)),
        'milk');
    await tester.pumpAndSettle();

    await tester.tap(find.widgetWithText(FilledButton, 'Try'));
    await tester.pumpAndSettle();

    final Json sent = api.sent!;
    expect(sent['transaction_date'], '2026-12-01');
    expect(sent['transaction_type'], 'SALES_ORDER');
    expect(sent['customer_id'], 'c-asha');
    expect(sent['customer_group_id'], 'g-whole');
    final Json line = (sent['lines'] as List).single as Json;
    expect(line['product_id'], 'p-milk');
    expect(line['quantity'], '1');
    expect(line['gross'], '50.00');

    final Finder result = find.byKey(const Key('try-result'));
    await tester.ensureVisible(result);
    expect(find.textContaining('discount 25.00'), findsOneWidget);
    expect(find.textContaining('2 x Milk (GIFT)'), findsOneWidget);
    expect(find.text('Total saved: 25.00'), findsOneWidget);
    expect(find.text('Every condition held.'), findsOneWidget);
    expect(find.text('Needs a coupon code.'), findsOneWidget);
    expect(find.text('Yes'), findsOneWidget);
    expect(find.text('No'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a refusal from the server is shown in the dialog',
      (tester) async {
    final _TryApi api = _TryApi(refuse: true);
    await _openTry(tester, api);
    await _pick(
        tester,
        find.descendant(
            of: find.byKey(const Key('try-product-0')),
            matching: find.byType(TextFormField)),
        'milk');

    await tester.tap(find.widgetWithText(FilledButton, 'Try'));
    await tester.pumpAndSettle();

    expect(find.text('The date is outside any year.'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a line needs a product before it is sent', (tester) async {
    final _TryApi api = _TryApi();
    await _openTry(tester, api);

    await tester.tap(find.widgetWithText(FilledButton, 'Try'));
    await tester.pumpAndSettle();

    expect(api.sent, isNull);
    expect(find.text('Pick a product for every line.'), findsOneWidget);
  });
}
