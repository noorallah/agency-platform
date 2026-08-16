// A vendor address can finally name its city — and a save keeps what the
// dialog does not edit.
//
// `vendor_addresses` has no text city, state or postal code at all: the
// geography masters are the only way to say where a vendor is, and no screen
// ever set those ids, so every seeded address was two street lines and nothing
// else. The API had accepted the ids since the module was written.
//
// The other half matters more. The dialog used to send all six child
// collections as empty lists, and the API replaces rather than merges — so
// correcting a phone number destroyed the vendor's addresses, contacts, bank
// accounts, tax details, attachments and notes.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/geography.dart';
import 'package:agency_desktop/models/vendor.dart';
import 'package:agency_desktop/ui/vendors/vendor_management_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions() => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': <String>['VENDOR_VIEW', 'VENDOR_CREATE', 'VENDOR_UPDATE'],
  }));

Json _vendorJson({List<Json> addresses = const <Json>[]}) => <String, dynamic>{
      'id': 'v-1',
      'firm_id': 'firm-1',
      'code': 'V001',
      'name': 'Supplier One',
      'display_name': 'Supplier One',
      'status': 'ACTIVE',
      'addresses': addresses,
      'contacts': const <Json>[],
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

Future<void> _open(WidgetTester tester, _VendorApi api) async {
  tester.view.physicalSize = const Size(1600, 1200);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
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
  // Two: the toolbar button and the grid's row-action column. The toolbar
  // comes first in the tree.
  await tester.tap(find.byTooltip('Edit').first);
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('a save no longer sends empty collections', (tester) async {
    // The defect: `contacts`, `banking`, `tax`, `attachments` and `notes` were
    // sent as `[]`, and the API replaces rather than merges.
    final api = _VendorApi(rows: <Json>[_vendorJson()]);
    await _open(tester, api);

    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    expect(api.saved, isNotNull);
    for (final String key in <String>[
      'contacts',
      'banking',
      'tax',
      'attachments',
      'notes',
    ]) {
      expect(api.saved!.containsKey(key), isFalse, reason: '$key must be absent');
    }
    // Addresses are edited here, so they are sent.
    expect(api.saved!.containsKey('addresses'), isTrue);
  });

  testWidgets('an existing address keeps its id and its place', (tester) async {
    final api = _VendorApi(rows: <Json>[
      _vendorJson(addresses: <Json>[
        <String, dynamic>{
          'id': 'a-1',
          'address_type': 'BILLING',
          'address_line1': '11 Supplier Street',
          'country_id': 'c-in',
          'is_primary': true,
        },
      ]),
    ]);
    await _open(tester, api);

    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    final List<dynamic> rows = api.saved!['addresses'] as List<dynamic>;
    expect(rows.length, 1);
    final Json row = rows.first as Json;
    // The id goes back so the server reconciles the row rather than replacing
    // it, which would lose its history.
    expect(row['id'], 'a-1');
    expect(row['address_line1'], '11 Supplier Street');
    expect(row['country_id'], 'c-in');
  });
}
