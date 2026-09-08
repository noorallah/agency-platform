import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/geography.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/ui/branches/branch_warehouse_management_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// The branch and warehouse forms carry the firm's custom fields too, as a
/// section at the foot of each dialog, sent only once the definitions
/// arrived.

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
      'code': 'HO',
      'name': 'Head Office',
      'display_name': 'Head Office',
      'currency_code': 'INR',
      'status': 'ACTIVE',
      'is_default': true,
      'attributes': [
        {
          'id': 'v-1',
          'attribute_definition_id': 'def-fssai',
          'value_text': 'F-100',
        },
      ],
    };

Json _warehouseJson() => <String, dynamic>{
      'id': 'w-1',
      'branch_id': 'b-1',
      'code': 'WH1',
      'name': 'Main Store',
      'display_name': 'Main Store',
      'status': 'ACTIVE',
      'is_default': true,
    };

ApplicableAttributesRecord _applicable(String entityType, String id, String name,
        {String dataType = 'TEXT'}) =>
    ApplicableAttributesRecord.fromJson({
      'entity_type': entityType,
      'definitions': [
        {
          'id': id,
          'code': name.toUpperCase().replaceAll(' ', '_'),
          'name': name,
          'entity_type': entityType,
          'data_type': dataType,
          'mandatory': false,
          'is_active': true,
        },
      ],
      'mandatory_ids': const [],
    });

class _Api extends ApiClient {
  _Api()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  Json? saved;
  final List<String> asked = [];

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
      const <GeoPlaceRecord>[];

  @override
  Future<ApplicableAttributesRecord> applicableAttributeDefinitions(
    String entityType,
  ) async {
    asked.add(entityType);
    return entityType == 'BRANCH'
        ? _applicable('BRANCH', 'def-fssai', 'FSSAI licence')
        : _applicable('WAREHOUSE', 'def-bays', 'Dock bays', dataType: 'NUMBER');
  }

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
  _Api api,
  BranchWarehouseSection section,
  String rowCode,
) async {
  tester.view.physicalSize = const Size(1600, 1600);
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
  await tester.ensureVisible(find.widgetWithText(FilledButton, 'Save'));
  await tester.tap(find.widgetWithText(FilledButton, 'Save'));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('a branch shows its stored field and sends it back',
      (tester) async {
    final _Api api = _Api();
    await _open(tester, api, BranchWarehouseSection.branches, 'HO');

    expect(api.asked, ['BRANCH']);
    expect(find.text('Custom fields'), findsOneWidget);
    final TextField field =
        tester.widget(find.byKey(const ValueKey('attribute-def-fssai')));
    expect(field.controller!.text, 'F-100');

    await tester.ensureVisible(find.byKey(const ValueKey('attribute-def-fssai')));
    await tester.enterText(
        find.byKey(const ValueKey('attribute-def-fssai')), 'F-200');
    await _save(tester);

    expect(api.saved!['attributes'], [
      {'attribute_definition_id': 'def-fssai', 'value': 'F-200'},
    ]);
  });

  testWidgets('a warehouse asks for its own fields and sends a number',
      (tester) async {
    final _Api api = _Api();
    await _open(tester, api, BranchWarehouseSection.warehouses, 'WH1');

    expect(api.asked, ['WAREHOUSE']);
    await tester.ensureVisible(find.byKey(const ValueKey('attribute-def-bays')));
    await tester.enterText(find.byKey(const ValueKey('attribute-def-bays')), '4');
    await _save(tester);

    expect(api.saved!['attributes'], [
      {'attribute_definition_id': 'def-bays', 'value': '4'},
    ]);
  });
}
