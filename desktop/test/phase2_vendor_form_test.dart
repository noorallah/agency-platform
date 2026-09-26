// The vendor record in the phase 2 app (2026-09-26): a full-page tab with
// every section in one scroll, as the customer record the owner approved.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/geography.dart';
import 'package:agency_desktop/models/vendor.dart';
import 'package:agency_desktop/ui/vendors/vendor_management_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions() => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': <String>['VENDOR_VIEW', 'VENDOR_CREATE', 'VENDOR_UPDATE'],
  }));

Json _vendorJson({
  List<Json> addresses = const <Json>[],
  List<Json> contacts = const <Json>[],
  List<Json> bankAccounts = const <Json>[],
  List<Json> taxDetails = const <Json>[],
  List<Json> notes = const <Json>[],
}) =>
    <String, dynamic>{
      'id': 'v-1',
      'firm_id': 'firm-1',
      'code': 'V001',
      'name': 'Supplier One',
      'display_name': 'Supplier One',
      'status': 'ACTIVE',
      'addresses': addresses,
      'contacts': contacts,
      'bank_accounts': bankAccounts,
      'tax_details': taxDetails,
      'notes': notes,
    };

class _VendorApi extends ApiClient {
  _VendorApi({this.rows = const <Json>[]})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Json> rows;
  Json? saved;

  @override
  Future<PagedResult<Vendor>> vendors({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    VendorQuery filters = const VendorQuery(),
  }) async =>
      PagedResult<Vendor>(
        items: <Vendor>[for (final Json row in rows) Vendor.fromJson(row)],
        total: rows.length,
      );

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
  Future<Vendor> updateVendor(
    String id,
    Json data, {
    int? expectedVersion,
  }) async {
    saved = data;
    return Vendor.fromJson(_vendorJson());
  }
}

void main() {
  testWidgets('phase 2 shows the whole vendor on one page and saves it',
      (tester) async {
    tester.view.physicalSize = const Size(1600, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final _VendorApi api = _VendorApi(rows: <Json>[
      _vendorJson(
        bankAccounts: <Json>[
          <String, dynamic>{
            'id': 'bk-1',
            'bank_name': 'State Bank',
            'account_name': 'Supplier One',
            'account_number': '000123456789',
            'ifsc': 'SBIN0001234',
            'is_primary': true,
          },
        ],
      ),
    ]);
    await tester.pumpWidget(MaterialApp(
      builder: (context, child) => Phase2Scope(child: child!),
      home: Scaffold(
        body: VendorManagementPage(
          api: api,
          permissions: _permissions(),
          hasActiveFirm: true,
        ),
      ),
    ));
    await tester.pumpAndSettle();
    await tester.tap(find.text('V001').first);
    await tester.pump(const Duration(milliseconds: 400));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Edit').first);
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);

    // No tabs: the bank account sits on the same page as the name.
    expect(find.text('Vendor Name'), findsOneWidget);
    expect(find.text('Account number'), findsOneWidget);
    // The side panel says where they are paid.
    expect(find.text('State Bank · SBIN0001234'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('vendor-save')));
    await tester.pumpAndSettle();
    expect(api.saved?['code'], 'V001');
    expect(api.saved?['banking'], hasLength(1));
  });
}
