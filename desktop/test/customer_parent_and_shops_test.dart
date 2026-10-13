// A chain is one parent customer with one customer per shop under it
// (backlog 125). The GST number is typed once, on the parent; a shop that
// sends none takes the parent's, and one in another state types its own.
//
// What the form owes: a "Shop of" field that sends only `parent_customer_id`,
// a GST box that opens empty for a number the server copied, a Shops panel
// fed by one family call -- and no call at all for a customer without family.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/customer.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/customers/customer_management_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Json _customerJson({
  String id = 'cust-1',
  String code = 'CUS-001',
  String name = 'Anand Agencies',
  String gst = '',
  String? parentId,
  String? parentCode,
  String? parentName,
  bool fromParent = false,
  int shops = 0,
}) =>
    <String, dynamic>{
      'id': id,
      'version': 4,
      'firm_id': 'firm-1',
      'code': code,
      'customer_type': 'BUSINESS',
      'name': name,
      'display_name': name,
      'gst_number': gst,
      'currency_code': 'INR',
      'status': 'ACTIVE',
      'addresses': <dynamic>[],
      'contacts': <dynamic>[],
      'parent_customer_id': parentId,
      'parent_code': parentCode,
      'parent_name': parentName,
      'gst_number_from_parent': fromParent,
      'shop_count': shops,
    };

final CustomerFamily _family = CustomerFamily.fromJson(<String, dynamic>{
  'parent_id': 'dm-1',
  'members': <Json>[
    <String, dynamic>{
      'id': 'dm-1',
      'code': 'DM-HQ',
      'name': 'DMart',
      'is_parent': true,
      'gst_number': '33AAAAA0000A1Z5',
      'gst_number_from_parent': false,
      'status': 'ACTIVE',
      'place': null,
      'current_outstanding': '100.00',
      'unapplied_advance_balance': '0.00',
    },
    <String, dynamic>{
      'id': 'dm-2',
      'code': 'DM-ADY',
      'name': 'DMart Adyar',
      'is_parent': false,
      'gst_number': '33AAAAA0000A1Z5',
      'gst_number_from_parent': true,
      'status': 'ACTIVE',
      'place': 'Adyar, Chennai',
      'current_outstanding': '150.50',
      'unapplied_advance_balance': '0.00',
    },
  ],
  'total_outstanding': '250.50',
  'total_unapplied_advance': '0.00',
});

Customer _parent() => Customer.fromJson(_customerJson(
      id: 'dm-1',
      code: 'DM-HQ',
      name: 'DMart',
      gst: '33AAAAA0000A1Z5',
    ));

class _Pumped {
  _Pumped(this.sent, this.familyCalls);
  final List<Json> sent;
  final List<int> familyCalls;
}

Future<_Pumped> _pump(
  WidgetTester tester, {
  Customer? customer,
  List<Customer> found = const [],
  CustomerDialogMode? mode,
}) async {
  tester.view.physicalSize = const Size(1600, 1100);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final List<Json> sent = <Json>[];
  final List<int> familyCalls = <int>[];
  await tester.pumpWidget(MaterialApp(
    builder: (context, child) => Phase2Scope(child: child!),
    home: Scaffold(
      body: CustomerWorkspaceDialog(
        mode: mode ??
            (customer == null
                ? CustomerDialogMode.create
                : CustomerDialogMode.edit),
        customer: customer,
        onSave: (payload) async {
          sent.add(payload);
          return Customer.fromJson(_customerJson());
        },
        loadPlaces: (level, {parentId = ''}) async => const [],
        searchParents: (text) async => found,
        loadFamily: customer == null
            ? null
            : () async {
                familyCalls.add(1);
                return _family;
              },
      ),
    ),
  ));
  await tester.pumpAndSettle();
  return _Pumped(sent, familyCalls);
}

Future<void> _save(WidgetTester tester) async {
  await tester.tap(find.byKey(const ValueKey('customer-save')));
  await tester.pumpAndSettle();
}

Future<void> _chooseParent(WidgetTester tester) async {
  await tester.enterText(find.byKey(const ValueKey('customer-parent-box')), 'DM');
  await tester.pumpAndSettle();
  await tester.tap(find.textContaining('DM-HQ - DMart').last);
  await tester.pumpAndSettle();
}

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

class _ListApi extends ApiClient {
  _ListApi(this.rows)
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Customer> rows;

  @override
  Future<PagedResult<Customer>> customers({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    CustomerQuery filters = const CustomerQuery(),
  }) async =>
      PagedResult(items: rows, total: rows.length);

  @override
  Future<Json> documentSummary(String resource,
          {String path = 'summary'}) async =>
      <String, dynamic>{
        'data': <String, dynamic>{'active': rows.length},
      };
}

void main() {
  testWidgets('choosing a parent sends its id and no GST number',
      (tester) async {
    final _Pumped run = await _pump(tester, found: [_parent()]);
    expect(find.text('Shop of'), findsOneWidget);
    expect(
      find.text('The buyer this customer is a shop of. Leave blank for a '
          'buyer on its own.'),
      findsOneWidget,
    );

    await tester.enterText(
      find.widgetWithText(TextFormField, 'Customer name'),
      'DMart Adyar',
    );
    await _chooseParent(tester);
    expect(
      find.textContaining("Blank takes the parent's GST number "
          '(33AAAAA0000A1Z5).'),
      findsOneWidget,
    );
    await _save(tester);

    expect(run.sent.single['parent_customer_id'], 'dm-1');
    expect(run.sent.single['gst_number'], isNull);
    // Only the one new key is added; the derived fields are never written.
    for (final String key in const [
      'parent_code',
      'parent_name',
      'gst_number_from_parent',
      'shop_count',
    ]) {
      expect(run.sent.single.containsKey(key), isFalse);
    }
  });

  testWidgets('the one being edited, a shop and the walk-in are not offered',
      (tester) async {
    await _pump(
      tester,
      customer: Customer.fromJson(_customerJson()),
      found: [
        Customer.fromJson(_customerJson(id: 'cust-1', code: 'DM-SELF')),
        Customer.fromJson(_customerJson(
            id: 'x-2', code: 'DM-SHOP', parentId: 'dm-1', parentCode: 'DM-HQ')),
        Customer.fromJson(<String, dynamic>{
          ..._customerJson(id: 'x-3', code: 'DM-CASH'),
          'is_cash_sale': true,
        }),
        _parent(),
      ],
    );
    await tester.enterText(
        find.byKey(const ValueKey('customer-parent-box')), 'DM');
    await tester.pumpAndSettle();
    expect(find.textContaining('DM-HQ - DMart'), findsOneWidget);
    expect(find.textContaining('DM-SELF'), findsNothing);
    expect(find.textContaining('DM-SHOP'), findsNothing);
    expect(find.textContaining('DM-CASH'), findsNothing);
  });

  testWidgets('a number the server copied opens as an empty box with the helper',
      (tester) async {
    final _Pumped run = await _pump(
      tester,
      customer: Customer.fromJson(_customerJson(
        code: 'DM-ADY',
        gst: '33AAAAA0000A1Z5',
        parentId: 'dm-1',
        parentCode: 'DM-HQ',
        parentName: 'DMart',
        fromParent: true,
      )),
    );

    expect(
      tester
          .widget<TextFormField>(find.widgetWithText(TextFormField, 'GST number'))
          .controller!
          .text,
      '',
    );
    expect(
      find.textContaining("Blank takes the parent's GST number "
          '(33AAAAA0000A1Z5). Type one only for a shop registered in another '
          'state.'),
      findsOneWidget,
    );
    await _save(tester);
    expect(run.sent.single['gst_number'], isNull);
    expect(run.sent.single['parent_customer_id'], 'dm-1');
  });

  testWidgets('clearing the parent sends null', (tester) async {
    final _Pumped run = await _pump(
      tester,
      customer: Customer.fromJson(_customerJson(
        code: 'DM-ADY',
        parentId: 'dm-1',
        parentCode: 'DM-HQ',
        parentName: 'DMart',
      )),
    );
    expect(find.text('DM-HQ - DMart'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('customer-parent-clear')));
    await tester.pumpAndSettle();
    await _save(tester);

    expect(run.sent.single.containsKey('parent_customer_id'), isTrue);
    expect(run.sent.single['parent_customer_id'], isNull);
  });

  testWidgets('a parent with shops cannot become a shop', (tester) async {
    await _pump(
      tester,
      customer: Customer.fromJson(_customerJson(code: 'DM-HQ', shops: 2)),
    );
    expect(find.text('This customer is the parent of 2 shops.'), findsOneWidget);
    expect(find.byKey(const ValueKey('customer-parent-box')), findsNothing);
  });

  testWidgets('the Shops panel lists the family and the total, in one call',
      (tester) async {
    final _Pumped run = await _pump(
      tester,
      customer: Customer.fromJson(_customerJson(code: 'DM-HQ', shops: 1)),
    );

    expect(run.familyCalls, hasLength(1));
    expect(find.text('Shops'), findsOneWidget);
    expect(find.textContaining('DM-HQ  DMart  (parent)'), findsOneWidget);
    expect(find.textContaining('DM-ADY  DMart Adyar'), findsOneWidget);
    expect(find.textContaining("33AAAAA0000A1Z5 (parent's)"), findsOneWidget);
    expect(find.textContaining('Adyar, Chennai'), findsOneWidget);
    expect(find.text('Total outstanding'), findsOneWidget);
    expect(find.text('250.50'), findsOneWidget);
  });

  testWidgets('a customer with no parent and no shops makes no family call',
      (tester) async {
    final _Pumped run =
        await _pump(tester, customer: Customer.fromJson(_customerJson()));
    expect(run.familyCalls, isEmpty);
    expect(find.text('Shops'), findsNothing);
    expect(find.text('Total outstanding'), findsNothing);
  });

  testWidgets('the list says which rows are shops and which are parents',
      (tester) async {
    tester.view.physicalSize = const Size(1600, 1100);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final PermissionService permissions = PermissionService()
      ..applyAccessToken(_accessToken({
        'roles': <String>['user'],
        'permissions': <String>['CUSTOMER_VIEW'],
      }));
    final _ListApi api = _ListApi([
      Customer.fromJson(_customerJson(
          id: 'dm-1', code: 'DM-HQ', name: 'DMart', shops: 3)),
      Customer.fromJson(_customerJson(
          id: 'dm-2',
          code: 'DM-ADY',
          name: 'DMart Adyar',
          parentId: 'dm-1',
          parentCode: 'DM-HQ',
          parentName: 'DMart')),
      Customer.fromJson(_customerJson(id: 'z-1', code: 'ZZ', name: 'Alone')),
    ]);
    await tester.pumpWidget(Phase2Scope(
      child: MaterialApp(
        home: Scaffold(
          body: CustomerManagementPage(
            api: api,
            permissions: permissions,
            hasActiveFirm: true,
          ),
        ),
      ),
    ));
    await tester.pumpAndSettle();

    expect(find.text('3 shops'), findsOneWidget);
    expect(find.text('Shop of DM-HQ'), findsOneWidget);
  });
}
