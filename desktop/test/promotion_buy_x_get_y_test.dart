// SEL-2: a "buy X, get Y at a discount" offer. The benefit sends exactly
// buy_quantity, free_quantity, percent and the optional max_amount, and its
// summary reads "Buy 1, get 1 at 50% off".

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

void main() {
  testWidgets('saves the four keys for the new benefit', (tester) async {
    final _Api api = _Api();
    await _open(tester, api);
    await tester.enterText(find.widgetWithText(TextFormField, 'Code'), 'BXGY');
    await tester.enterText(
        find.widgetWithText(TextFormField, 'Name'), 'Second at half');
    await tester.tap(find.text('Percent off each line'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Buy X, get Y at a discount').last);
    await tester.pumpAndSettle();
    await tester.enterText(
        find.byKey(const ValueKey('promotion-action-buy-0')), '1');
    await tester.enterText(
        find.byKey(const ValueKey('promotion-action-get-0')), '1');
    await tester.enterText(
        find.byKey(const ValueKey('promotion-action-off-0')), '50');
    await tester.enterText(
        find.byKey(const ValueKey('promotion-action-cap-0')), '200');
    await tester.ensureVisible(find.text('Save'));
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();

    final List actions = api.sentBody!['actions'] as List;
    expect(actions, hasLength(1));
    final Map action = actions.first as Map;
    expect(action['action_type'], 'BUY_X_GET_Y_DISCOUNT');
    expect(action['buy_quantity'], '1');
    expect(action['free_quantity'], '1');
    expect(action['percent'], '50');
    expect(action['max_amount'], '200');
    expect(action.containsKey('amount'), isFalse);
    expect(action.containsKey('multiplier'), isFalse);
  });

  testWidgets('a missing figure is refused before anything is sent',
      (tester) async {
    final _Api api = _Api();
    await _open(tester, api);
    await tester.enterText(find.widgetWithText(TextFormField, 'Code'), 'BXGY');
    await tester.enterText(
        find.widgetWithText(TextFormField, 'Name'), 'Second at half');
    await tester.tap(find.text('Percent off each line'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Buy X, get Y at a discount').last);
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Save'));
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();
    expect(api.sentBody, isNull);
    expect(find.text('Over 0, up to 100.'), findsOneWidget);
  });

  test('the summary reads Buy 1, get 1 at 50% off', () {
    final PromotionActionRecord record = PromotionActionRecord.fromJson(
      <String, dynamic>{
        'action_type': 'BUY_X_GET_Y_DISCOUNT',
        'parameters': <String, dynamic>{
          'buy_quantity': '1.0000',
          'free_quantity': '1',
          'percent': '50.00',
        },
      },
    );
    expect(
      buyXGetYDiscountLabel(
          record.buyQuantity, record.freeQuantity, record.percent),
      'Buy 1, get 1 at 50% off',
    );
  });
}
