// What a firm has agreed to charge, and to whom.
//
// A price list holds rates off the product's price, scoped to one customer, to
// everyone on a round, or to the whole firm. Three things about that shape are
// easy to get wrong on screen and cost real money when they are:
//
// 1. The rates are **replaced** by what is saved, not merged, so an edit that
//    loses a race silently discards every rate somebody else just entered.
//    The version the row was read at has to ride along as the precondition.
// 2. The scope is **one key or none** — the server refuses a list scoped to a
//    customer and a territory at once — so moving an arrangement from one shop
//    to everybody must clear the shop, not leave the id behind.
// 3. Every figure is a **percentage**, so a blank one is a refusal rather than
//    a row quietly dropped from the payload.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/customer.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/pricing.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/ui/pricing/price_list_dialog.dart';
import 'package:agency_desktop/ui/pricing/price_list_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions({bool manage = true}) => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': <String>[
      'PRICE_LIST_VIEW',
      if (manage) 'PRICE_LIST_MANAGE',
    ],
  }));

Customer _customer(String id, String name) =>
    Customer.fromJson(<String, dynamic>{
      'id': id,
      'code': id.toUpperCase(),
      'name': name,
      'display_name': name,
      'customer_type': 'BUSINESS',
      'currency_code': 'INR',
      'status': 'ACTIVE',
    });

Product _product(String id, String code, String name) =>
    Product.fromJson(<String, dynamic>{
      'id': id,
      'code': code,
      'name': name,
      'status': 'ACTIVE',
    });

PriceListRecord _list({
  String id = 'pl-1',
  String code = 'PL001',
  String name = 'Monsoon rates',
  int version = 3,
  String customerId = '',
  String customerName = '',
  List<PriceListItemRecord> items = const <PriceListItemRecord>[],
}) =>
    PriceListRecord(
      id: id,
      code: code,
      name: name,
      version: version,
      customerId: customerId,
      customerName: customerName,
      effectiveFrom: '2026-06-01',
      items: items,
    );

class _PricingApi extends ApiClient {
  _PricingApi({this.rows = const <PriceListRecord>[]})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<PriceListRecord> rows;

  Json? savedBody;
  int? sentVersion;
  String? updatedId;

  @override
  Future<PagedResult<PriceListRecord>> priceLists({
    int page = 1,
    int pageSize = 20,
    String search = '',
  }) async =>
      PagedResult<PriceListRecord>(items: rows, total: rows.length);

  @override
  Future<PagedResult<Customer>> customers({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    CustomerQuery filters = const CustomerQuery(),
  }) async =>
      PagedResult<Customer>(
        items: [_customer('cus-1', 'Shop One')],
        total: 1,
      );

  @override
  Future<PagedResult<Product>> products({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    ProductQuery filters = const ProductQuery(),
  }) async =>
      PagedResult<Product>(
        items: [_product('prd-1', 'P001', 'Rice 25kg')],
        total: 1,
      );

  @override
  Future<PriceListRecord> createPriceList(Json body) async {
    savedBody = body;
    return _list();
  }

  @override
  Future<PriceListRecord> updatePriceList(
    String id,
    Json body, {
    int? expectedVersion,
  }) async {
    updatedId = id;
    savedBody = body;
    sentVersion = expectedVersion;
    return _list();
  }
}

Future<void> _pumpDialog(
  WidgetTester tester,
  _PricingApi api, {
  PriceListRecord? existing,
}) async {
  tester.view.physicalSize = const Size(1700, 1400);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: PriceListDialog(
        api: api,
        customers: [_customer('cus-1', 'Shop One')],
        products: [_product('prd-1', 'P001', 'Rice 25kg')],
        existing: existing,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('the grid says who each arrangement is with', (tester) async {
    tester.view.physicalSize = const Size(1700, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final _PricingApi api = _PricingApi(rows: [
      _list(),
      _list(
        id: 'pl-2',
        code: 'PL002',
        name: 'Shop One rates',
        customerId: 'cus-1',
        customerName: 'Shop One',
      ),
    ]);
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: PriceListPage(
          api: api,
          permissions: _permissions(),
          hasActiveFirm: true,
        ),
      ),
    ));
    await tester.pumpAndSettle();

    // A list with no scope belongs to the whole firm, and saying "Everyone"
    // is the difference between a blank cell and a fact.
    expect(find.text('Everyone'), findsOneWidget);
    expect(find.text('Shop One'), findsOneWidget);
  });

  testWidgets('an edit sends the version it read as the precondition',
      (tester) async {
    final _PricingApi api = _PricingApi();
    await _pumpDialog(
      tester,
      api,
      existing: _list(version: 7, items: const [
        PriceListItemRecord(productId: 'prd-1', discountPercent: '5'),
      ]),
    );

    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    expect(api.updatedId, 'pl-1');
    // The rates are replaced by what is sent, so without this a save that
    // lost a race would overwrite rates it never showed the user.
    expect(api.sentVersion, 7);
  });

  testWidgets('moving an arrangement to everybody clears the customer',
      (tester) async {
    final _PricingApi api = _PricingApi();
    await _pumpDialog(
      tester,
      api,
      existing: _list(
        customerId: 'cus-1',
        customerName: 'Shop One',
        items: const [
          PriceListItemRecord(productId: 'prd-1', discountPercent: '5'),
        ],
      ),
    );

    await tester.tap(find.text('Everyone'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    // Leaving the id behind would file the arrangement against a shop the
    // user has just taken it off.
    expect(api.savedBody!['customer_id'], isNull);
    expect(api.savedBody!['territory_id'], isNull);
  });

  testWidgets('a rate left blank is refused rather than dropped',
      (tester) async {
    final _PricingApi api = _PricingApi();
    await _pumpDialog(tester, api);

    await tester.enterText(find.widgetWithText(TextFormField, 'Code'), 'PL009');
    await tester.enterText(
        find.widgetWithText(TextFormField, 'Name'), 'New rates');
    await tester.tap(find.widgetWithText(TextButton, 'Add product'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    expect(find.text('Enter a rate.'), findsOneWidget);
    // Silently dropping the row would save a list that changes nothing while
    // reporting success.
    expect(api.savedBody, isNull);
  });
}
