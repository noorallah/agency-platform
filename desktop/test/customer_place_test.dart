// A customer address can name a place, and the form shows what it will save.
//
// `customer_addresses` held city, area, district, state and postal code as
// plain strings with no link to the geography masters, so "Parrys" and
// "Parry's Corner" never grouped and a pin-code search was a string match.
// Vendors, branches and warehouses had the keys and no form; customers are the
// opposite, which is why they needed a migration and these two behaviours:
//
// 1. The chosen ids reach the payload.
// 2. The required free text is updated to match, because the server derives it
//    from the keys and a form must not show something different from what it
//    is about to send.

import 'package:agency_desktop/models/customer.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/geography.dart';
import 'package:agency_desktop/ui/customers/customer_management_page.dart';
import 'package:agency_desktop/ui/workspace/geo_area_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

GeoPlaceRecord _place(GeoLevel level, String id, String code, String name) =>
    GeoPlaceRecord.fromJson(level, <String, dynamic>{
      'id': id,
      'code': code,
      'name': name,
      'postal_code': code,
    });

Future<List<GeoPlaceRecord>> _loadPlaces(
  GeoLevel level, {
  String parentId = '',
}) async =>
    switch (level) {
      GeoLevel.country => <GeoPlaceRecord>[
          _place(level, 'c-in', 'IN', 'India'),
        ],
      GeoLevel.state => <GeoPlaceRecord>[
          _place(level, 's-tn', 'TN', 'Tamil Nadu'),
        ],
      GeoLevel.district => <GeoPlaceRecord>[
          _place(level, 'd-chn', 'CHN', 'Chennai'),
        ],
      GeoLevel.city => <GeoPlaceRecord>[
          _place(level, 'ct-chn', 'CHN', 'Chennai'),
        ],
      GeoLevel.postalCode => <GeoPlaceRecord>[
          _place(level, 'p-1', '600001', '600001'),
        ],
      GeoLevel.locality => <GeoPlaceRecord>[
          _place(level, 'l-parrys', 'PRY', 'Parrys'),
        ],
    };

Json _customerJson() => <String, dynamic>{
      'id': 'cust-1',
      'code': 'C001',
      'name': 'Shop One',
      'display_name': 'Shop One',
      'customer_type': 'BUSINESS',
      'currency_code': 'INR',
      'status': 'ACTIVE',
      'addresses': <Json>[
        <String, dynamic>{
          'id': 'addr-1',
          'address_type': 'BILLING',
          'address_line1': '21 Market Road',
          'area': 'Main Market',
          'city': 'typed city',
          'state': 'typed state',
          'country': 'IN',
          'postal_code': '000000',
          'is_default_billing': true,
        },
      ],
      'contacts': const <Json>[],
    };

Future<Json?> _openAndSave(
  WidgetTester tester, {
  required Future<void> Function(WidgetTester tester) act,
}) async {
  tester.view.physicalSize = const Size(1700, 1400);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  Json? saved;
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: CustomerWorkspaceDialog(
        mode: CustomerDialogMode.edit,
        customer: Customer.fromJson(_customerJson()),
        loadPlaces: _loadPlaces,
        onSave: (payload) async {
          saved = payload;
          return Customer.fromJson(_customerJson());
        },
      ),
    ),
  ));
  await tester.pumpAndSettle();
  await tester.tap(find.text('Address'));
  await tester.pumpAndSettle();
  await act(tester);
  await tester.tap(find.widgetWithText(FilledButton, 'Save'));
  await tester.pumpAndSettle();
  return saved;
}

/// Choose [name] on the picker's rung at [rung].
///
/// Found by position rather than by label: the address form already has a
/// free-text field labelled Country, State and City beside the ladder, so a
/// label finder matches two widgets and belongs to neither reliably.
Future<void> _choose(WidgetTester tester, int rung, String name) async {
  final Finder field = find
      .descendant(
        of: find.byType(GeoAreaPicker),
        matching: find.byType(DropdownButtonFormField<String>),
      )
      .at(rung);
  // No `ensureVisible`: it looks for a Scrollable ancestor and the tab body
  // is not one. The surface is sized large enough that the ladder is on
  // screen.
  await tester.tap(field);
  await tester.pumpAndSettle();
  await tester.tap(find.text(name).last);
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('a chosen place reaches the payload', (tester) async {
    final Json? saved = await _openAndSave(tester, act: (tester) async {
      await _choose(tester, 0, 'India');
      await _choose(tester, 1, 'Tamil Nadu');
    });

    final List<dynamic> rows = saved!['addresses'] as List<dynamic>;
    final Json address = rows.first as Json;
    expect(address['country_id'], 'c-in');
    expect(address['state_id'], 's-tn');
  });

  testWidgets('the required text is updated to what will be saved',
      (tester) async {
    // The server derives `state` from `state_id`, so a form still showing the
    // typed value would be showing something it is not about to save.
    final Json? saved = await _openAndSave(tester, act: (tester) async {
      await _choose(tester, 0, 'India');
      await _choose(tester, 1, 'Tamil Nadu');
    });

    final Json address =
        (saved!['addresses'] as List<dynamic>).first as Json;
    expect(address['state'], 'Tamil Nadu');
    // Not chosen, so left exactly as the user typed it.
    expect(address['city'], 'typed city');
  });

  testWidgets('an address with no place still saves its text', (tester) async {
    final Json? saved = await _openAndSave(tester, act: (tester) async {});

    final Json address =
        (saved!['addresses'] as List<dynamic>).first as Json;
    expect(address['city'], 'typed city');
    expect(address['country_id'], isNull);
    expect(address['state_id'], isNull);
  });
}
