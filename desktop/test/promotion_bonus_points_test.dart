// SEL-4: a bonus-points offer. The benefit saves a LOYALTY_MULTIPLIER with a
// multiplier of more than 1 and at most 10, stands alone in its offer, reads
// back as it was saved, and is summarised as "2x loyalty points".

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/pricing.dart';
import 'package:agency_desktop/ui/pricing/promotion_dialog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

class _Api extends ApiClient {
  _Api()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  Json? sentBody;

  @override
  Future<Json> request(
    String method,
    String path, {
    Json? body,
    Map<String, String>? query,
    bool authenticated = true,
    bool retrying = false,
    int? expectedVersion,
  }) async {
    sentBody = body;
    return <String, dynamic>{
      'data': <String, dynamic>{'id': 'p-1', 'code': 'X', 'name': 'X'},
    };
  }
}

Json _bonusOffer() => <String, dynamic>{
      'id': 'p-1',
      'code': 'DIWALI',
      'name': 'Diwali points',
      'status': 'ACTIVE',
      'priority': 100,
      'version': 1,
      'conditions': <Json>[],
      'actions': <Json>[
        <String, dynamic>{
          'action_type': 'LOYALTY_MULTIPLIER',
          'sequence': 1,
          'parameters': <String, dynamic>{'multiplier': '2'},
        },
      ],
    };

Future<void> _open(WidgetTester tester, _Api api, {Json? existing}) async {
  tester.view.physicalSize = const Size(1600, 1400);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: PromotionDialog(
        api: api,
        existing: existing == null ? null : PromotionRecord.fromJson(existing),
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

Future<void> _fillNew(WidgetTester tester) async {
  await tester.enterText(find.widgetWithText(TextFormField, 'Code'), 'DIWALI');
  await tester.enterText(
      find.widgetWithText(TextFormField, 'Name'), 'Diwali points');
}

Future<void> _chooseBonus(WidgetTester tester) async {
  await tester.tap(find.text('Percent off each line'));
  await tester.pumpAndSettle();
  await tester.tap(find.text('Bonus loyalty points').last);
  await tester.pumpAndSettle();
}

Future<void> _save(WidgetTester tester) async {
  await tester.ensureVisible(find.text('Save'));
  await tester.tap(find.text('Save'));
  await tester.pumpAndSettle();
}

Future<void> _enterMultiplier(WidgetTester tester, String value) async {
  await tester.enterText(
      find.byKey(const ValueKey('promotion-action-multiplier-0')), value);
}

void main() {
  testWidgets('saves a LOYALTY_MULTIPLIER with the multiplier', (tester) async {
    final _Api api = _Api();
    await _open(tester, api);
    await _fillNew(tester);
    await _chooseBonus(tester);
    expect(find.text('Times the usual points'), findsOneWidget);
    await _enterMultiplier(tester, '2');
    await _save(tester);

    final List actions = api.sentBody!['actions'] as List;
    expect(actions, hasLength(1));
    expect(actions.first['action_type'], 'LOYALTY_MULTIPLIER');
    expect(actions.first['multiplier'], '2');
    expect(actions.first.containsKey('percent'), isFalse);
  });

  for (final (String, String) bad in <(String, String)>[
    ('1', 'More than 1 and at most 10, such as 2.'),
    ('11', 'More than 1 and at most 10, such as 2.'),
    ('', 'Say how many times the usual points, such as 2.'),
  ]) {
    testWidgets('multiplier "${bad.$1}" is refused', (tester) async {
      final _Api api = _Api();
      await _open(tester, api);
      await _fillNew(tester);
      await _chooseBonus(tester);
      await _enterMultiplier(tester, bad.$1);
      await _save(tester);
      expect(api.sentBody, isNull);
      expect(find.text(bad.$2), findsOneWidget);
    });
  }

  testWidgets('a bonus with a discount in the same offer is refused',
      (tester) async {
    final _Api api = _Api();
    await _open(tester, api);
    await _fillNew(tester);
    await _chooseBonus(tester);
    await _enterMultiplier(tester, '2');
    await tester.ensureVisible(find.text('Add benefit'));
    await tester.tap(find.text('Add benefit'));
    await tester.pumpAndSettle();
    await _save(tester);

    expect(api.sentBody, isNull);
    expect(
      find.text('A bonus-points offer gives nothing else; make the discount '
          'a separate offer.'),
      findsOneWidget,
    );
  });

  testWidgets('a saved bonus offer reads back and saves unchanged',
      (tester) async {
    final _Api api = _Api();
    await _open(tester, api, existing: _bonusOffer());

    expect(find.text('Bonus loyalty points'), findsOneWidget);
    expect(find.text('2'), findsOneWidget);

    await _save(tester);
    final List actions = api.sentBody!['actions'] as List;
    expect(actions.first['action_type'], 'LOYALTY_MULTIPLIER');
    expect(actions.first['multiplier'], '2');
  });

  test('the summary reads "2x loyalty points"', () {
    final PromotionRecord row = PromotionRecord.fromJson(_bonusOffer());
    expect(row.actions.first.multiplier, '2');
    expect(bonusPointsLabel(row.actions.first.multiplier), '2x loyalty points');
    expect(bonusPointsLabel('1.50'), '1.5x loyalty points');
  });
}
