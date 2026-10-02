// SEL-7: offers only on certain weekdays or hours. Seven chips save an `IN`
// of ISO day numbers, a From/Until window saves a `BETWEEN` whose end is the
// last minute (Until minus one), a saved condition reads back as it was
// entered, and a window that does not move forward is refused before sending.

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

Json _offer(List<Json> conditions) => <String, dynamic>{
      'id': 'p-1',
      'code': 'HAPPY',
      'name': 'Happy hour',
      'status': 'ACTIVE',
      'priority': 100,
      'version': 1,
      'conditions': conditions,
      'actions': <Json>[
        <String, dynamic>{
          'action_type': 'LINE_DISCOUNT_PERCENT',
          'sequence': 1,
          'parameters': <String, dynamic>{'percent': '10'},
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
  await tester.enterText(find.widgetWithText(TextFormField, 'Code'), 'HAPPY');
  await tester.enterText(
      find.widgetWithText(TextFormField, 'Name'), 'Happy hour');
  await tester.enterText(find.widgetWithText(TextFormField, 'Percent'), '10');
}

Future<void> _addCondition(WidgetTester tester, String field) async {
  await tester.ensureVisible(find.text('Add condition'));
  await tester.tap(find.text('Add condition'));
  await tester.pumpAndSettle();
  await tester.tap(find.text('Product category').first);
  await tester.pumpAndSettle();
  await tester.tap(find.text(field).last);
  await tester.pumpAndSettle();
}

Future<void> _save(WidgetTester tester) async {
  await tester.tap(find.text('Save'));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('weekday chips save an IN of day numbers', (tester) async {
    final _Api api = _Api();
    await _open(tester, api);
    await _fillNew(tester);
    await _addCondition(tester, 'Days of the week');

    await tester.tap(find.byKey(const ValueKey('promotion-weekday-7')));
    await tester.tap(find.byKey(const ValueKey('promotion-weekday-6')));
    await tester.pumpAndSettle();
    await _save(tester);

    final List conditions = api.sentBody!['conditions'] as List;
    expect(conditions, hasLength(1));
    expect(conditions.first['field_key'], 'weekday');
    expect(conditions.first['operator'], 'IN');
    expect(conditions.first['value_json'], <String>['6', '7']);
  });

  testWidgets('no day chosen is refused', (tester) async {
    final _Api api = _Api();
    await _open(tester, api);
    await _fillNew(tester);
    await _addCondition(tester, 'Days of the week');
    await _save(tester);

    expect(api.sentBody, isNull);
    expect(find.text('Choose at least one day of the week.'), findsOneWidget);
  });

  testWidgets('a time window saves a BETWEEN ending a minute early',
      (tester) async {
    final _Api api = _Api();
    await _open(tester, api);
    await _fillNew(tester);
    await _addCondition(tester, 'Time of day');

    await tester.enterText(
        find.byKey(const ValueKey('promotion-time-from')), '16:00');
    await tester.enterText(
        find.byKey(const ValueKey('promotion-time-until')), '18:00');
    await _save(tester);

    final List conditions = api.sentBody!['conditions'] as List;
    expect(conditions.first['field_key'], 'time_of_day');
    expect(conditions.first['operator'], 'BETWEEN');
    expect(conditions.first['value_json'], <num>[960, 1079]);
  });

  testWidgets('a window that does not move forward is refused',
      (tester) async {
    final _Api api = _Api();
    await _open(tester, api);
    await _fillNew(tester);
    await _addCondition(tester, 'Time of day');

    await tester.enterText(
        find.byKey(const ValueKey('promotion-time-from')), '18:00');
    await tester.enterText(
        find.byKey(const ValueKey('promotion-time-until')), '09:00');
    await _save(tester);

    expect(api.sentBody, isNull);
    expect(
      find.text('A window cannot cross midnight -- make it two offers'),
      findsOneWidget,
    );
  });

  testWidgets('saved conditions read back as chips and a closing time',
      (tester) async {
    final _Api api = _Api();
    await _open(
      tester,
      api,
      existing: _offer(<Json>[
        <String, dynamic>{
          'sequence': 1,
          'field_key': 'weekday',
          'operator': 'IN',
          'value_json': <int>[7, 6],
        },
        <String, dynamic>{
          'sequence': 2,
          'field_key': 'time_of_day',
          'operator': 'BETWEEN',
          'value_json': <int>[960, 1079],
        },
      ]),
    );

    expect(
      tester
          .widget<FilterChip>(find.byKey(const ValueKey('promotion-weekday-6')))
          .selected,
      isTrue,
    );
    expect(
      tester
          .widget<FilterChip>(find.byKey(const ValueKey('promotion-weekday-1')))
          .selected,
      isFalse,
    );
    expect(find.text('16:00'), findsOneWidget);
    expect(find.text('18:00'), findsOneWidget);

    await _save(tester);
    final List conditions = api.sentBody!['conditions'] as List;
    expect(conditions[0]['value_json'], <String>['6', '7']);
    expect(conditions[1]['value_json'], <num>[960, 1079]);
  });

  test('conditions are summarised in words', () {
    expect(
      describePromotionCondition(const PromotionConditionRecord(
        fieldKey: 'weekday',
        operator: 'IN',
        valueList: <String>['7', '6'],
      )),
      'Days: Sat, Sun',
    );
    expect(
      describePromotionCondition(const PromotionConditionRecord(
        fieldKey: 'time_of_day',
        operator: 'BETWEEN',
        valueList: <String>['960', '1079'],
      )),
      'Time: 16:00-18:00',
    );
  });
}
