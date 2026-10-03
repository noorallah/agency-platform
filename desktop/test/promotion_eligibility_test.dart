// SEL-6: customer eligibility conditions on offers. The two history fields
// are numeric, save field_key/operator/value_number as typed, and read in
// words ("First order only", "Not billed in 60 days").

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
  testWidgets('first order only saves customer_order_count EQUALS 0',
      (tester) async {
    final _Api api = _Api();
    await _open(tester, api);
    await _fillNew(tester);
    await _addCondition(tester, "Customer's approved orders so far");

    await tester.enterText(find.widgetWithText(TextFormField, 'Value'), '0');
    await _save(tester);

    final List conditions = api.sentBody!['conditions'] as List;
    expect(conditions, hasLength(1));
    expect(conditions.first['field_key'], 'customer_order_count');
    expect(conditions.first['operator'], 'EQUALS');
    expect(conditions.first['value_number'], '0');
  });

  testWidgets('not billed in N days saves GREATER_OR_EQUAL', (tester) async {
    final _Api api = _Api();
    await _open(tester, api);
    await _fillNew(tester);
    await _addCondition(tester, "Days since the customer's last order");

    await tester.tap(find.text('is'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('is at least').last);
    await tester.pumpAndSettle();
    await tester.enterText(find.widgetWithText(TextFormField, 'Value'), '60');
    await _save(tester);

    final List conditions = api.sentBody!['conditions'] as List;
    expect(conditions.first['field_key'], 'days_since_last_order');
    expect(conditions.first['operator'], 'GREATER_OR_EQUAL');
    expect(conditions.first['value_number'], '60');
  });

  test('eligibility conditions are summarised in words', () {
    expect(
      describePromotionCondition(const PromotionConditionRecord(
        fieldKey: 'customer_order_count',
        operator: 'EQUALS',
        valueNumber: '0.0000',
      )),
      'First order only',
    );
    expect(
      describePromotionCondition(const PromotionConditionRecord(
        fieldKey: 'days_since_last_order',
        operator: 'GREATER_OR_EQUAL',
        valueNumber: '60.0000',
      )),
      'Not billed in 60 days',
    );
    expect(
      describePromotionCondition(const PromotionConditionRecord(
        fieldKey: 'customer_order_count',
        operator: 'GREATER_OR_EQUAL',
        valueNumber: '3',
      )),
      "Customer's approved orders so far is at least 3",
    );
  });
}
