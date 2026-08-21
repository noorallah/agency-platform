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
// accounts, tax details, attachments and notes. It then went the other way and
// sent none of them, which was safe and left four tabs showing a sentence
// where a form belonged: contacts, banking, tax and notes round-tripped
// through the API and could only be filled by import.
//
// Now five are edited and sent, and `attachments` is the one still absent --
// nothing in this client uploads a file. A collection that is sent must carry
// what was loaded, ids and all, or "replace" quietly means "delete".

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
  testWidgets('a save sends what it edits and omits what it cannot',
      (tester) async {
    // Attachments are the one collection with no form: nothing here uploads a
    // file, so sending `[]` for them would delete what an import put there.
    final api = _VendorApi(rows: <Json>[_vendorJson()]);
    await _open(tester, api);

    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    expect(api.saved, isNotNull);
    expect(api.saved!.containsKey('attachments'), isFalse,
        reason: 'attachments must be absent');
    for (final String key in <String>[
      'addresses',
      'contacts',
      'banking',
      'tax',
      'notes',
    ]) {
      expect(api.saved!.containsKey(key), isTrue, reason: '$key is edited');
    }
    // The write schema's names, not the response's `bank_accounts` /
    // `tax_details`. The schema forbids extra fields, so the response's names
    // would be a 422.
    expect(api.saved!.containsKey('bank_accounts'), isFalse);
    expect(api.saved!.containsKey('tax_details'), isFalse);
  });

  testWidgets('the collections it loaded come back unchanged', (tester) async {
    // The dialog sends the whole list, so a row it loaded and did not touch
    // has to survive the round trip -- with its id, or the server reconciles
    // it as a new row and the old one is deleted.
    final api = _VendorApi(rows: <Json>[
      _vendorJson(
        contacts: <Json>[
          <String, dynamic>{
            'id': 'ct-1',
            'name': 'Asha Rao',
            'designation': 'Owner',
            'mobile': '+919812345678',
            'is_primary': true,
            'status': 'ACTIVE',
          },
        ],
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
        taxDetails: <Json>[
          <String, dynamic>{
            'id': 'tx-1',
            'gstin': '29ABCDE1234F1Z5',
            'pan': 'ABCDE1234F',
            'is_primary': true,
          },
        ],
        notes: <Json>[
          <String, dynamic>{
            'id': 'nt-1',
            'note': 'Delivers on Tuesdays only.',
            'note_type': 'DELIVERY',
          },
        ],
      ),
    ]);
    await _open(tester, api);

    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    final Json saved = api.saved!;
    final Json contact = (saved['contacts'] as List).single as Json;
    expect(contact['id'], 'ct-1');
    expect(contact['name'], 'Asha Rao');
    expect(contact['is_primary'], isTrue);
    final Json bank = (saved['banking'] as List).single as Json;
    expect(bank['id'], 'bk-1');
    expect(bank['account_number'], '000123456789');
    expect(bank['ifsc'], 'SBIN0001234');
    final Json tax = (saved['tax'] as List).single as Json;
    expect(tax['id'], 'tx-1');
    expect(tax['gstin'], '29ABCDE1234F1Z5');
    final Json note = (saved['notes'] as List).single as Json;
    expect(note['id'], 'nt-1');
    expect(note['note_type'], 'DELIVERY');
  });

  testWidgets('a bank account can be typed in', (tester) async {
    // The tab used to read "Bank details are supported with primary flag" and
    // offer nothing to type one into.
    final api = _VendorApi(rows: <Json>[_vendorJson()]);
    await _open(tester, api);

    await tester.tap(find.widgetWithText(Tab, 'Banking'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(OutlinedButton, 'Add account(s)'));
    await tester.pumpAndSettle();
    await tester.enterText(
        find.widgetWithText(TextField, 'Bank'), 'Canara Bank');
    await tester.enterText(
        find.widgetWithText(TextField, 'Account name'), 'Supplier One');
    await tester.enterText(
        find.widgetWithText(TextField, 'Account number'), '55501234');
    // Lower case on the way in, upper on the way out: the server normalises
    // it, and the screen should not disagree with what was stored.
    await tester.enterText(
        find.widgetWithText(TextField, 'IFSC'), 'cnrb0005555');
    await tester.tap(find.widgetWithText(CheckboxListTile, 'Primary'));
    await tester.pumpAndSettle();

    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    final Json bank = (api.saved!['banking'] as List).single as Json;
    expect(bank.containsKey('id'), isFalse, reason: 'a new row has no id');
    expect(bank['bank_name'], 'Canara Bank');
    expect(bank['account_number'], '55501234');
    expect(bank['ifsc'], 'CNRB0005555');
    expect(bank['is_primary'], isTrue);
    // Blank optional fields go as null, not as empty strings.
    expect(bank['branch'], isNull);
    expect(bank['upi_id'], isNull);
  });

  testWidgets('choosing a primary contact demotes the other', (tester) async {
    // One primary per collection is the API's rule; the form applies it rather
    // than letting the save be refused for something it already knows.
    final api = _VendorApi(rows: <Json>[
      _vendorJson(contacts: <Json>[
        <String, dynamic>{
          'id': 'ct-1',
          'name': 'Asha Rao',
          'is_primary': true,
          'status': 'ACTIVE',
        },
        <String, dynamic>{
          'id': 'ct-2',
          'name': 'Bala Iyer',
          'is_primary': false,
          'status': 'ACTIVE',
        },
      ]),
    ]);
    await _open(tester, api);

    await tester.tap(find.widgetWithText(Tab, 'Contacts'));
    await tester.pumpAndSettle();
    // The second card sits below a 360px tab body, and a tap at coordinates
    // outside the dialog lands on the barrier and closes it.
    final Finder secondPrimary =
        find.widgetWithText(CheckboxListTile, 'Primary').last;
    await tester.ensureVisible(secondPrimary);
    await tester.pumpAndSettle();
    await tester.tap(secondPrimary);
    await tester.pumpAndSettle();

    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    final List<dynamic> contacts = api.saved!['contacts'] as List;
    expect(contacts.length, 2);
    expect((contacts[0] as Json)['is_primary'], isFalse);
    expect((contacts[1] as Json)['is_primary'], isTrue);
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
