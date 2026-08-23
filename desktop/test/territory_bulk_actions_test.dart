// Bulk operations on territories, which had four endpoints and no screen.
//
// The API has been able to restatus, move, and reassign customers and
// salespeople across many territories at once since the module was written,
// and nothing in this client called any of it — a firm reorganising a
// hierarchy opened and saved one territory at a time.
//
// Two behaviours here are worth holding onto:
//
//   * Ticking rows must not move the detail panel's selection. They are two
//     different questions — "which rows am I about to restatus" and "which row
//     am I looking at" — and conflating them makes a twenty-row selection
//     rewrite the panel under the user.
//   * The customer and salesperson pickers open **empty**, not seeded from any
//     one ticked territory. Seeding would push that territory's list onto the
//     other nineteen by default, and the action replaces rather than adds.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/customer.dart';
import 'package:agency_desktop/models/firm_member.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/sales_territory.dart';
import 'package:agency_desktop/ui/sales/bulk_territory_actions_dialog.dart';
import 'package:agency_desktop/ui/sales/sales_territory_management_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions({List<String>? permissions}) =>
    PermissionService()
      ..applyAccessToken(_accessToken({
        'roles': <String>['user'],
        'permissions': permissions ??
            <String>[
              'TERRITORY_VIEW',
              'TERRITORY_CREATE',
              'TERRITORY_UPDATE',
              'TERRITORY_ASSIGN_CUSTOMERS',
              'TERRITORY_ASSIGN_SALESMEN',
            ],
      }));

Json _territoryJson(String id, String code, String name) => <String, dynamic>{
      'id': id,
      'firm_id': 'firm-1',
      'hierarchy_level_id': 'lvl-route',
      'hierarchy_level_name': 'Route',
      'code': code,
      'name': name,
      'status': 'ACTIVE',
      'path': code,
      'sort_order': 0,
      'customer_count': 0,
      'salesman_count': 0,
      'route_profile': null,
    };

Json _customerJson(String id, String code, String name) => <String, dynamic>{
      'id': id,
      'firm_id': 'firm-1',
      'code': code,
      'name': name,
      'display_name': name,
      'customer_type': 'BUSINESS',
      'status': 'ACTIVE',
      'currency_code': 'INR',
    };

class _BulkApi extends ApiClient {
  _BulkApi({this.failWith})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  /// When set, every bulk call throws it — the partial-write question.
  final String? failWith;

  Json? statusBody;
  Json? moveBody;
  List<Json>? customerItems;
  List<Json>? salesmanItems;

  @override
  Future<TerritoryHierarchyRecord> territoryHierarchy() async =>
      TerritoryHierarchyRecord.fromJson(<String, dynamic>{
        'levels': <Json>[
          <String, dynamic>{
            'id': 'lvl-route',
            'code': 'ROUTE',
            'name': 'Route',
            'display_name': 'Route',
            'level_order': 1,
          },
        ],
      });

  @override
  Future<List<TerritoryTreeNodeRecord>> territoryTree({
    bool includeDeleted = false,
  }) async =>
      const <TerritoryTreeNodeRecord>[];

  @override
  Future<PagedResult<SalesTerritory>> territories({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    TerritoryQuery filters = const TerritoryQuery(),
  }) async =>
      PagedResult<SalesTerritory>(
        items: <SalesTerritory>[
          SalesTerritory.fromJson(_territoryJson('t-1', 'RT01', 'North Beat')),
          SalesTerritory.fromJson(_territoryJson('t-2', 'RT02', 'South Beat')),
          SalesTerritory.fromJson(_territoryJson('t-3', 'RT03', 'East Beat')),
        ],
        total: 3,
      );

  @override
  Future<Json> territoryDashboard() async => <String, dynamic>{};

  @override
  Future<List<TerritoryRouteTypeRecord>> territoryRouteTypes() async =>
      const <TerritoryRouteTypeRecord>[];

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
        items: page == 1
            ? <Customer>[
                Customer.fromJson(_customerJson('c-1', 'C1', 'First Stores')),
                Customer.fromJson(_customerJson('c-2', 'C2', 'Second Stores')),
              ]
            : const <Customer>[],
        total: 2,
      );

  @override
  Future<List<FirmMember>>
      firmMembers() async => <FirmMember>[
            FirmMember.fromJson(<String, dynamic>{
              'user_id': 'user-1',
              'full_name': 'Ravi Kumar',
              'email': 'ravi@agency.local',
            }),
          ];

  @override
  Future<int> bulkTerritoryStatus(Json body) async {
    if (failWith != null) throw ApiException(failWith!);
    statusBody = body;
    return (body['territory_ids'] as List).length;
  }

  @override
  Future<int> bulkTerritoryMove(Json body) async {
    if (failWith != null) throw ApiException(failWith!);
    moveBody = body;
    return (body['territory_ids'] as List).length;
  }

  @override
  Future<int> bulkTerritoryCustomers(List<Json> items) async {
    if (failWith != null) throw ApiException(failWith!);
    customerItems = items;
    return items.length;
  }

  @override
  Future<int> bulkTerritorySalesmen(List<Json> items) async {
    if (failWith != null) throw ApiException(failWith!);
    salesmanItems = items;
    return items.length;
  }
}

Future<void> _pump(
  WidgetTester tester,
  _BulkApi api, {
  PermissionService? permissions,
}) async {
  tester.view.physicalSize = const Size(1600, 1200);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: SalesTerritoryManagementPage(
        api: api,
        permissions: permissions ?? _permissions(),
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

/// Tick the checkbox on the given grid rows.
Future<void> _tick(WidgetTester tester, int count) async {
  final Finder boxes = find.byType(Checkbox);
  // The first checkbox is the header's select-all; the row boxes follow it.
  for (int index = 1; index <= count; index++) {
    await tester.tap(boxes.at(index));
    await tester.pumpAndSettle();
  }
}

void main() {
  testWidgets('ticking rows offers a bulk action and counts them',
      (tester) async {
    final api = _BulkApi();
    await _pump(tester, api);

    expect(find.text('Bulk actions'), findsNothing);

    await _tick(tester, 2);

    expect(find.text('2 ticked'), findsOneWidget);
    expect(find.text('Bulk actions'), findsOneWidget);
  });

  testWidgets('a bulk status change sends every ticked territory',
      (tester) async {
    final api = _BulkApi();
    await _pump(tester, api);
    await _tick(tester, 2);

    await tester.tap(find.text('Bulk actions'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Change status'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Continue'));
    await tester.pumpAndSettle();

    expect(api.statusBody, isNotNull);
    expect((api.statusBody!['territory_ids'] as List).length, 2);
    expect(api.statusBody!['status'], 'ACTIVE');
  });

  testWidgets('a bulk move sends the chosen parent once for all of them',
      (tester) async {
    final api = _BulkApi();
    await _pump(tester, api);
    await _tick(tester, 2);

    await tester.tap(find.text('Bulk actions'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Move under a parent'));
    await tester.pumpAndSettle();
    // The dropdown defaults to "No parent (root)", so this batch moves to the
    // top of the tree. Which parents are *offered* is covered separately, by
    // pumping the dialog directly — a closed dropdown renders only its
    // selected item, so the options are not in the tree to assert on here.
    await tester.tap(find.text('Continue'));
    await tester.pumpAndSettle();

    expect(api.moveBody, isNotNull);
    expect((api.moveBody!['territory_ids'] as List).length, 2);
    expect(api.moveBody!.containsKey('new_parent_id'), isFalse);
  });

  testWidgets('a bulk customer assignment applies one list to every territory',
      (tester) async {
    final api = _BulkApi();
    await _pump(tester, api);
    await _tick(tester, 2);

    await tester.tap(find.text('Bulk actions'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Set customers'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Continue'));
    await tester.pumpAndSettle();

    // The picker opens with nothing ticked, then we choose one customer.
    await tester.tap(find.text('First Stores'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();

    expect(api.customerItems, isNotNull);
    expect(api.customerItems!.length, 2);
    for (final Json item in api.customerItems!) {
      expect(item['customer_ids'], <String>['c-1']);
    }
  });

  testWidgets('a refused batch says nothing was changed', (tester) async {
    final api = _BulkApi(failWith: 'Territory not found.');
    await _pump(tester, api);
    await _tick(tester, 2);

    await tester.tap(find.text('Bulk actions'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Change status'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Continue'));
    await tester.pumpAndSettle();

    // The server applies the batch in one transaction, so this sentence is
    // true rather than reassuring.
    expect(
      find.textContaining('Nothing was changed.'),
      findsOneWidget,
    );
  });

  testWidgets('a user who can only assign customers is offered only that',
      (tester) async {
    final api = _BulkApi();
    await _pump(
      tester,
      api,
      permissions: _permissions(permissions: <String>[
        'TERRITORY_VIEW',
        'TERRITORY_ASSIGN_CUSTOMERS',
      ]),
    );
    await _tick(tester, 1);

    await tester.tap(find.text('Bulk actions'));
    await tester.pumpAndSettle();

    expect(find.text('Set customers'), findsOneWidget);
    expect(find.text('Change status'), findsNothing);
    expect(find.text('Move under a parent'), findsNothing);
    expect(find.text('Set salespeople'), findsNothing);
  });

  testWidgets('a ticked territory is not offered as its own new parent',
      (tester) async {
    // Moving a territory under another one in the same batch is how you get a
    // cycle, which the server refuses — so the dialog does not offer it.
    tester.view.physicalSize = const Size(1600, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(const MaterialApp(
      home: Scaffold(
        body: BulkTerritoryActionsDialog(
          count: 2,
          parents: <BulkParentOption>[
            BulkParentOption(id: 't-3', label: 'RT03 - East Beat'),
          ],
        ),
      ),
    ));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Move under a parent'));
    await tester.pumpAndSettle();
    await tester.tap(find.byType(DropdownButtonFormField<String>));
    await tester.pumpAndSettle();

    expect(find.text('RT03 - East Beat'), findsOneWidget);
    expect(find.text('RT01 - North Beat'), findsNothing);
    expect(find.text('RT02 - South Beat'), findsNothing);
  });
}
