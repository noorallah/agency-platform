// A branch edit must keep the address and the flags the form never showed.
//
// `branches` and `warehouses` carry the six geography keys and two street
// lines, and no screen ever set one. Worse, the server's update dumped the
// whole write model and assigned every field, so anything the form omitted was
// written back as null — and the form hardcoded `is_default: false`,
// `gst_registration: false`, a fixed 09:00–18:00 working day and, for a
// warehouse, all ten capability flags. One rename cleared the lot.
//
// These pin what the form now sends: a real address, a real place, and the
// flags as they were read rather than as constants.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/geography.dart';
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

Json _branchJson() => <String, dynamic>{
      'id': 'b-1',
      'firm_id': 'firm-1',
      'code': 'HO',
      'name': 'Head Office',
      'display_name': 'Head Office',
      'currency_code': 'INR',
      'status': 'ACTIVE',
      'address_line1': '9 Mount Road',
      'address_line2': 'Near Spencer Plaza',
      'country_id': 'c-in',
      'city_id': 'city-mad',
      'gst_registration': true,
      'is_default': true,
      'warehouse_count': 0,
    };

Json _warehouseJson() => <String, dynamic>{
      'id': 'w-1',
      'firm_id': 'firm-1',
      'branch_id': 'b-1',
      'code': 'WH1',
      'name': 'Main Store',
      'display_name': 'Main Store',
      'capacity': '500',
      'capacity_unit': 'KG',
      'status': 'ACTIVE',
      'address_line1': '12 Dock Road',
      'country_id': 'c-in',
      'is_default': true,
      'cold_storage': true,
      'hazardous_storage': true,
      'has_loading_dock': true,
    };

class _BranchApi extends ApiClient {
  _BranchApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  Json? saved;

  @override
  Future<PagedResult<BranchRecord>> branches({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    BranchQuery filters = const BranchQuery(),
  }) async =>
      PagedResult<BranchRecord>(
        items: <BranchRecord>[BranchRecord.fromJson(_branchJson())],
        total: 1,
      );

  @override
  Future<PagedResult<WarehouseRecord>> warehouses({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    WarehouseQuery filters = const WarehouseQuery(),
  }) async =>
      PagedResult<WarehouseRecord>(
        items: <WarehouseRecord>[WarehouseRecord.fromJson(_warehouseJson())],
        total: 1,
      );

  @override
  Future<List<TypeRecord>> branchTypes({bool includeDeleted = false}) async =>
      const <TypeRecord>[];

  @override
  Future<List<TypeRecord>> warehouseTypes({bool includeDeleted = false}) async =>
      const <TypeRecord>[];

  @override
  Future<List<GeoPlaceRecord>> geoPlaces(
    GeoLevel level, {
    String parentId = '',
  }) async =>
      switch (level) {
        GeoLevel.country => <GeoPlaceRecord>[
            GeoPlaceRecord.fromJson(level, <String, dynamic>{
              'id': 'c-in',
              'code': 'IN',
              'name': 'India',
            }),
          ],
        _ => const <GeoPlaceRecord>[],
      };

  @override
  Future<BranchRecord> updateBranch(
    String id,
    Json data, {
    int? expectedVersion,
  }) async {
    saved = data;
    return BranchRecord.fromJson(_branchJson());
  }

  @override
  Future<WarehouseRecord> updateWarehouse(
    String id,
    Json data, {
    int? expectedVersion,
  }) async {
    saved = data;
    return WarehouseRecord.fromJson(_warehouseJson());
  }
}

Future<void> _open(
  WidgetTester tester,
  _BranchApi api,
  BranchWarehouseSection section,
  String rowCode,
) async {
  tester.view.physicalSize = const Size(1600, 1400);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: BranchWarehouseManagementPage(
        api: api,
        permissions: _permissions(),
        hasActiveFirm: true,
        section: section,
      ),
    ),
  ));
  await tester.pumpAndSettle();
  await tester.tap(find.text(rowCode).first);
  await tester.pump(const Duration(milliseconds: 400));
  await tester.pumpAndSettle();
  await tester.tap(find.byTooltip('Edit').first);
  await tester.pumpAndSettle();
}

Future<void> _save(WidgetTester tester) async {
  await tester.tap(find.widgetWithText(FilledButton, 'Save'));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('a branch rename keeps its address and its place',
      (tester) async {
    final _BranchApi api = _BranchApi();
    await _open(tester, api, BranchWarehouseSection.branches, 'HO');
    await _save(tester);

    expect(api.saved, isNotNull);
    expect(api.saved!['address_line1'], '9 Mount Road');
    expect(api.saved!['address_line2'], 'Near Spencer Plaza');
    expect(api.saved!['country_id'], 'c-in');
    expect(api.saved!['city_id'], 'city-mad');
  });

  testWidgets('a branch keeps the flags the form used to hardcode',
      (tester) async {
    final _BranchApi api = _BranchApi();
    await _open(tester, api, BranchWarehouseSection.branches, 'HO');
    await _save(tester);

    expect(api.saved!['is_default'], isTrue);
    expect(api.saved!['gst_registration'], isTrue);
    // The form does not edit working hours, so it must not send a fixed day
    // that overwrites whatever the firm set.
    expect(api.saved!.containsKey('working_hours'), isFalse);
  });

  testWidgets('clearing the address line sends null, not an empty string',
      (tester) async {
    final _BranchApi api = _BranchApi();
    await _open(tester, api, BranchWarehouseSection.branches, 'HO');

    await tester.enterText(
      find.widgetWithText(TextField, 'Address line 1'),
      '',
    );
    await tester.pumpAndSettle();
    await _save(tester);

    expect(api.saved!['address_line1'], isNull);
  });

  testWidgets('a warehouse rename keeps its ten capability flags',
      (tester) async {
    final _BranchApi api = _BranchApi();
    await _open(tester, api, BranchWarehouseSection.warehouses, 'WH1');
    await _save(tester);

    expect(api.saved!['address_line1'], '12 Dock Road');
    expect(api.saved!['is_default'], isTrue);
    expect(api.saved!['cold_storage'], isTrue);
    expect(api.saved!['hazardous_storage'], isTrue);
    expect(api.saved!['has_loading_dock'], isTrue);
    // Read from the record, not assumed: this one has neither.
    expect(api.saved!['has_receiving_area'], isFalse);
    expect(api.saved!['temperature_controlled'], isFalse);
  });
}
