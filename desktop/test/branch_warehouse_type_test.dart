// A branch or warehouse must be able to say what type it is.
//
// The API has accepted `branch_type_id` and `warehouse_type_id` since the
// module was written, and the Branch Types and Warehouse Types screens let you
// curate the lists — but neither dialog offered the field, so nothing could
// ever point at one. Every branch and warehouse in the seeded demo carried
// `(none)`, and the two type screens were lists you could edit and never
// apply.
//
// Raised from manual testing: "on new branch form there is no branch type then
// how it will be mapped".

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/branches/branch_warehouse_management_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions() => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': <String>[
      'BRANCH_VIEW',
      'BRANCH_CREATE',
      'BRANCH_UPDATE',
      'WAREHOUSE_VIEW',
      'WAREHOUSE_CREATE',
      'WAREHOUSE_UPDATE',
    ],
  }));

class _TypesApi extends ApiClient {
  _TypesApi({this.types = const []})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<TypeRecord> types;
  Json? created;

  @override
  Future<List<TypeRecord>> branchTypes({bool includeDeleted = false}) async =>
      types;

  @override
  Future<List<TypeRecord>> warehouseTypes({bool includeDeleted = false}) async =>
      types;

  @override
  Future<PagedResult<BranchRecord>> branches({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    BranchQuery filters = const BranchQuery(),
  }) async =>
      PagedResult<BranchRecord>(items: <BranchRecord>[_branch()], total: 1);

  @override
  Future<PagedResult<WarehouseRecord>> warehouses({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    WarehouseQuery filters = const WarehouseQuery(),
  }) async =>
      PagedResult<WarehouseRecord>(items: <WarehouseRecord>[], total: 0);

  @override
  Future<BranchRecord> createBranch(Json data) async {
    created = data;
    return _branch();
  }
}

TypeRecord _type(String id, String code, String name) =>
    TypeRecord.fromJson(<String, dynamic>{
      'id': id,
      'code': code,
      'name': name,
    });

BranchRecord _branch() => BranchRecord.fromJson(<String, dynamic>{
      'id': 'branch-1',
      'code': 'WHL_HO',
      'name': 'Head Office',
      'display_name': 'Head Office',
      'status': 'ACTIVE',
      'currency_code': 'INR',
    });

Future<void> _pump(WidgetTester tester, _TypesApi api) async {
  tester.view.physicalSize = const Size(1600, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: BranchWarehouseManagementPage(
        api: api,
        permissions: _permissions(),
        hasActiveFirm: true,
        section: BranchWarehouseSection.branches,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('the new branch form offers the firm\'s branch types',
      (tester) async {
    final _TypesApi api = _TypesApi(types: <TypeRecord>[
      _type('t-1', 'DISTRIBUTOR', 'Distributor'),
      _type('t-2', 'RETAIL', 'Retail Outlet'),
    ]);
    await _pump(tester, api);

    await tester.tap(find.widgetWithText(FilledButton, 'New'));
    await tester.pumpAndSettle();

    expect(find.text('Branch Type'), findsOneWidget,
        reason: 'the field the API has always accepted was not on the form');

    await tester.tap(find.byType(DropdownButtonFormField<String?>));
    await tester.pumpAndSettle();
    expect(find.textContaining('DISTRIBUTOR'), findsWidgets);
    expect(find.textContaining('RETAIL'), findsWidgets);
    // "None" is offered because a type is optional — a firm that classifies
    // nothing must still be able to save.
    expect(find.text('None'), findsWidgets);
  });

  testWidgets('choosing a type sends it with the branch', (tester) async {
    final _TypesApi api = _TypesApi(types: <TypeRecord>[
      _type('t-1', 'DISTRIBUTOR', 'Distributor'),
    ]);
    await _pump(tester, api);
    await tester.tap(find.widgetWithText(FilledButton, 'New'));
    await tester.pumpAndSettle();

    await tester.enterText(
        find.widgetWithText(TextField, 'Branch Code'), 'BR-NEW');
    await tester.enterText(
        find.widgetWithText(TextField, 'Branch Name'), 'New Branch');
    await tester.tap(find.byType(DropdownButtonFormField<String?>));
    await tester.pumpAndSettle();
    await tester.tap(find.textContaining('DISTRIBUTOR').last);
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    expect(api.created?['branch_type_id'], 't-1');
  });

  testWidgets('with no types defined the form still saves', (tester) async {
    // The field is optional and a firm may never define a type. Blocking the
    // save, or hiding the field entirely, would both be wrong — the helper
    // text says where to add one instead.
    final _TypesApi api = _TypesApi();
    await _pump(tester, api);
    await tester.tap(find.widgetWithText(FilledButton, 'New'));
    await tester.pumpAndSettle();

    expect(find.textContaining('None defined'), findsOneWidget);

    await tester.enterText(
        find.widgetWithText(TextField, 'Branch Code'), 'BR-NEW');
    await tester.enterText(
        find.widgetWithText(TextField, 'Branch Name'), 'New Branch');
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    // Null rather than absent: on an edit that is what clears a type the
    // record used to have.
    expect(api.created, isNotNull);
    expect(api.created!.containsKey('branch_type_id'), isTrue);
    expect(api.created!['branch_type_id'], isNull);
  });
}
