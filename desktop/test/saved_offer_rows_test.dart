// L7 step 9: a saved document's view shows, per line, what was applied and
// "chosen by" (`docs/design/OFFERS_ON_THE_BILL_LINE_DESIGN.md` section 4).
//
// The line's `offers` rows are the server's record of what the line was
// priced with: APPLIED rows say what they gave and whether a person chose
// them, REFUSED rows are offers the start would have applied that a
// person's choice passed over. They show in the side panel while no pricing
// lists the line's offers afresh.

import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/customer.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/models/quotation.dart';
import 'package:agency_desktop/models/sales_invoice.dart';
import 'package:agency_desktop/ui/quotations/quotation_editor_dialog.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:agency_desktop/ui/workspace/discount_source.dart';
import 'package:agency_desktop/ui/workspace/offer_choice_block.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Json _row(
  String code, {
  String source = 'promotion',
  String state = 'APPLIED',
  bool chosen = false,
  String discount = '0',
  String free = '0',
  bool partShare = false,
  int sequence = 1,
}) =>
    <String, dynamic>{
      'sequence': sequence,
      'source': source,
      'promotion_group_id': source == 'promotion' ? 'g-$code' : null,
      'price_list_id': source == 'price_list' ? 'pl-$code' : null,
      'code': code,
      'name': code,
      'state': state,
      'chosen': chosen,
      'discount_amount': discount,
      'free_quantity': free,
      'part_share': partShare,
    };

/// The saved line's rows: one offer applied by the start, one chosen by a
/// person with a part share, and one the choice passed over.
List<Json> _savedRows() => <Json>[
      _row('TEA-5', discount: '55.0000', sequence: 1),
      _row('TEA-11',
          free: '1.0000', chosen: true, partShare: true, sequence: 2),
      _row('TEA-24', state: 'REFUSED', sequence: 3),
    ];

void main() {
  group('the wording of a saved row', () {
    test('an applied discount says what came off', () {
      expect(savedOfferWords(_row('TEA-5', discount: '55.0000')),
          'TEA-5 · 55.00 off · applied');
    });

    test('a row a person chose says so', () {
      expect(
          savedOfferWords(_row('TEA-11', free: '1.0000', chosen: true)),
          'TEA-11 · 1 free · chosen by a person');
    });

    test('a part share is named', () {
      expect(
          savedOfferWords(_row('TEA-11',
              free: '0.4167', chosen: true, partShare: true)),
          'TEA-11 · 0.4167 free · part share · chosen by a person');
    });

    test('a refused row was passed over', () {
      expect(savedOfferWords(_row('TEA-11', state: 'REFUSED')),
          'TEA-11 · passed over');
    });

    test('a price list, a standing rate and a group rate', () {
      expect(
          savedOfferWords(
              _row('CITY', source: 'price_list', discount: '12.5')),
          'Price list CITY · 12.50 off · applied');
      expect(
          savedOfferWords(_row('C-0102', source: 'customer', discount: '4')),
          'Standing rate · 4.00 off · applied');
      expect(
          savedOfferWords(
              _row('RETAIL', source: 'customer_group', state: 'REFUSED')),
          'Group rate · passed over');
    });

    test('rows read in the order the server weighed them', () {
      final List<Map<String, dynamic>> rows = savedOfferRows(<Json>[
        _row('B', sequence: 2),
        _row('A', sequence: 1),
        <String, dynamic>{'state': 'SKIPPED', 'code': 'X'},
      ]);
      expect(rows.map((row) => row['code']), <String>['A', 'B']);
      expect(savedOfferRows(null), isEmpty);
    });

    test('a passed-over offer never names the discount source', () {
      expect(
          discountSourceNamed('promotion', <Json>[
            _row('TEA-5', discount: '55'),
            _row('TEA-24', state: 'REFUSED', discount: '30'),
          ]),
          'TEA-5');
    });

    test('a bill line reads the offers of the order line behind it', () {
      final BillableLine line = BillableLine.fromJson(<String, dynamic>{
        'source_document_line_id': 'dn-1',
        'line_number': 1,
        'offers': _savedRows(),
      });
      expect(line.offers, hasLength(3));
      expect(BillableLine.fromJson(const <String, dynamic>{}).offers,
          isEmpty);
    });
  });

  testWidgets('a saved quotation shows its line rows in the side panel',
      (tester) async {
    tester.view.physicalSize = const Size(1600, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final Quotation saved = Quotation.fromJson(<String, dynamic>{
      'id': 'q1',
      'version': 1,
      'customer_id': 'c1',
      'customer_name': 'Sri Murugan Stores',
      'branch_id': 'ho',
      'warehouse_id': 'w1',
      'quotation_number': 'QT-1',
      'quotation_date': '2026-09-26',
      'valid_until': '2026-10-26',
      'status': 'DRAFT',
      'lines': <Json>[
        <String, dynamic>{
          'id': 'l1',
          'line_number': 1,
          'product_id': 'p1',
          'quantity': '11',
          'unit_price': '100.00',
          'discount_percent': '5',
          'discount_source': 'promotion',
          'discount_amount': '55.00',
          'net_amount': '1045.00',
          'offers': _savedRows(),
        },
      ],
    });
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Phase2Scope(
          child: QuotationEditorDialog(
            customers: [
              Customer.fromJson({
                'id': 'c1',
                'code': 'C-0102',
                'name': 'Sri Murugan Stores',
                'display_name': 'Sri Murugan Stores',
              }),
            ],
            products: [
              Product.fromJson({
                'id': 'p1',
                'code': 'P-1002',
                'name': 'Tata Salt 1kg',
                'selling_price': '100.00',
              }),
            ],
            branches: [
              BranchRecord.fromJson({
                'id': 'ho',
                'code': 'HO',
                'name': 'Head office',
                'display_name': 'Head office',
                'is_default': true,
              }),
            ],
            warehouses: [
              WarehouseRecord.fromJson({
                'id': 'w1',
                'code': 'MAIN',
                'name': 'Main',
                'display_name': 'Main',
                'branch_id': 'ho',
                'is_default': true,
              }),
            ],
            today: DateTime(2026, 9, 26),
            existing: saved,
          ),
        ),
      ),
    ));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('quotation-offer-block')),
        findsOneWidget);
    expect(find.text('TEA-5 · 55.00 off · applied'), findsOneWidget);
    expect(find.text('TEA-11 · 1 free · part share · chosen by a person'),
        findsOneWidget);
    expect(find.text('TEA-24 · passed over'), findsOneWidget);
    expect(find.text('No offer or arrangement for this line.'), findsNothing);
    expect(tester.takeException(), isNull);
  });
}
