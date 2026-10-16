// What the click round of the offers on the bill line found (L7 step 8,
// `docs/qa/SCREEN_FLOW_CHECK_OFFERS_LINE_2026-10-16.md`), one test each.

import 'package:agency_desktop/models/offer_candidate.dart';
import 'package:agency_desktop/ui/workspace/offer_choice_block.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

OfferCandidate _candidate(
  String key, {
  String source = 'promotion',
  String? percent,
  String? free,
  String worth = '0',
  bool applied = false,
  bool available = true,
  String? reason,
  String? needsMore,
  String? thenGives,
}) =>
    OfferCandidate.fromJson(<String, dynamic>{
      'key': key,
      'source': source,
      'code': key.toUpperCase(),
      'name': key,
      'gives': <String, dynamic>{
        'kind': percent != null ? 'PERCENT' : 'FREE_GOODS',
        'percent': percent,
        'free_quantity': free,
        'sentence': '',
      },
      'worth': worth,
      'applied': applied,
      'available': available,
      'reason': reason,
      'needs_more': needsMore,
      'then_gives': thenGives,
    });

/// The worked example at 11: TEA-5 55.00 and TEA-11 1 free applied, CITY
/// and the standing rate beside them.
List<OfferCandidate> _atEleven() => <OfferCandidate>[
      _candidate('tea5', percent: '5', worth: '55.0000', applied: true),
      _candidate('tea11', free: '1', worth: '100.0000', applied: true),
      _candidate('city', source: 'price_list', percent: '4', worth: '44.0000'),
      _candidate('CUSTOMER', source: 'customer', percent: '2', worth: '22.0000'),
    ];

void main() {
  test(
      'ticking a price list over an applied discount offer sends the list '
      'and the free goods, not the discount offer (D-UI-115)', () {
    final List<OfferCandidate> all = _atEleven();
    final LineOfferChoice line = LineOfferChoice();
    line.toggle(all, all[2]);
    // The server refuses TEA-5 beside CITY ("Choose one of them"), so the
    // tick never took on the screen.
    expect(line.choice!.toJson(), <String, dynamic>{
      'discount_from': 'city',
      'offers': <String>['tea11'],
      'part_share': null,
    });
    expect(line.isTicked(all[0]), isFalse);
    expect(line.isTicked(all[1]), isTrue);
    expect(line.isTicked(all[2]), isTrue);
    // Ticking TEA-5 again moves the discount back to the offers.
    line.toggle(all, all[0]);
    expect(line.choice!.discountFrom, 'offers');
    expect(line.choice!.offers, unorderedEquals(<String>['tea11', 'tea5']));
    expect(line.isTicked(all[2]), isFalse);
  });

  testWidgets(
      'an offer that gives the line nothing shows no Gives figure '
      '(D-UI-116)', (WidgetTester tester) async {
    final List<OfferCandidate> atNine = <OfferCandidate>[
      _candidate('tea5', percent: '5', worth: '45.0000', applied: true),
      // Short of its first round: tickable, but earns nothing yet.
      _candidate('tea11',
          free: '1',
          reason: 'Nothing earned on this line yet.',
          needsMore: '2.0000',
          thenGives: '1 free'),
      // Out of reach: a hint row.
      _candidate('tea24',
          free: '3',
          available: false,
          needsMore: '13.0000',
          thenGives: '3 free'),
    ];
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: SizedBox(
          width: 360,
          child: OfferChoiceBlock(
            candidates: atNine,
            choice: LineOfferChoice(),
            mayChoose: true,
            onChanged: () {},
          ),
        ),
      ),
    ));
    expect(find.text('Nothing earned on this line yet.'), findsOneWidget);
    expect(find.text('13 more to get 3 free'), findsOneWidget);
    expect(find.text('1 free'), findsNothing);
    expect(find.text('3 free'), findsNothing);
    expect(
        find.descendant(
            of: find.byKey(const ValueKey<String>('offer-choice-tea5')),
            matching: find.textContaining('45.00')),
        findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  /// A saved line of 11 with CITY and TEA-11 chosen, TEA-5 passed over, as
  /// the server reads it back.
  List<Map<String, dynamic>> savedRows({bool partShare = false}) =>
      <Map<String, dynamic>>[
        <String, dynamic>{
          'sequence': 1,
          'source': 'promotion',
          'promotion_group_id': 'tea11',
          'price_list_id': null,
          'code': 'TEA-11',
          'state': 'APPLIED',
          'chosen': true,
          'discount_amount': '0.0000',
          'free_quantity': partShare ? '0.5000' : '1.0000',
          'part_share': partShare,
        },
        <String, dynamic>{
          'sequence': 2,
          'source': 'price_list',
          'promotion_group_id': null,
          'price_list_id': 'city',
          'code': 'CITY',
          'state': 'APPLIED',
          'chosen': true,
          'discount_amount': '44.0000',
          'free_quantity': '0.0000',
          'part_share': false,
        },
        <String, dynamic>{
          'sequence': 3,
          'source': 'promotion',
          'promotion_group_id': 'tea5',
          'price_list_id': null,
          'code': 'TEA-5',
          'state': 'REFUSED',
          'chosen': false,
          'discount_amount': '55.0000',
          'free_quantity': '0.0000',
          'part_share': false,
        },
      ];

  test(
      'a reopened draft is priced with the choice it was saved with, not '
      'from the start (D-UI-117)', () {
    final LineOfferChoice line = LineOfferChoice()..hold(savedRows());
    expect(line.payload, <String, dynamic>{
      'offer_choice': <String, dynamic>{
        'discount_from': 'city',
        'offers': <String>['tea11'],
        'part_share': null,
      },
    });
    final List<OfferCandidate> all = _atEleven();
    // The block shows CITY and TEA-11 ticked, TEA-5 not, as saved.
    expect(<bool>[for (final OfferCandidate c in all) line.isTicked(c)],
        <bool>[false, true, true, false]);

    final LineOfferChoice share = LineOfferChoice()
      ..hold(savedRows(partShare: true));
    expect(share.choice!.partShare, 'tea11');
    expect(share.partShareNote, '0.5 free from TEA-11');

    // A line nobody chose for follows the server: nothing is sent.
    final LineOfferChoice start = LineOfferChoice()
      ..hold(<Map<String, dynamic>>[
        for (final Map<String, dynamic> row in savedRows())
          <String, dynamic>{...row, 'chosen': false},
      ]);
    expect(start.payload, isEmpty);
    expect(LineOfferChoice()..hold(null), isA<LineOfferChoice>());
  });

  test(
      'a document\'s view says what each line was priced with and who chose '
      'it (D-UI-118)', () {
    final String said = savedOffersLine(savedRows());
    expect(said, startsWith('Offers: TEA-11 · 1 free · chosen by a person; '));
    expect(said, contains('Price list CITY · '));
    expect(said, contains('44.00 off · chosen by a person'));
    expect(said, endsWith('; TEA-5 · passed over'));
    expect(savedOffersLine(const <dynamic>[]), isEmpty);
    expect(savedOffersLine(null), isEmpty);
  });
}
