// SEL-3: a "combo price" offer. The benefit sends exactly action_type,
// amount and combo_items, refuses fewer than two products, and an edited
// offer loads its items and price back into the form.

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
    if (method == 'GET' && path.contains('products')) {
      return <String, dynamic>{
        'data': [
          for (final String n in ['1', '2'])
            <String, dynamic>{
              'id': 'prod-$n',
              'code': 'P$n',
              'name': 'Item $n',
            },
        ],
        'pagination': <String, dynamic>{
          'page': 1,
          'page_size': 20,
          'total_records': 2,
          'total_pages': 1,
        },
      };
    }
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

Future<void> _chooseCombo(WidgetTester tester) async {
  await tester.enterText(find.widgetWithText(TextFormField, 'Code'), 'COMBO');
  await tester.enterText(find.widgetWithText(TextFormField, 'Name'), 'Pair');
  await tester.tap(find.text('Percent off each line'));
  await tester.pumpAndSettle();
  await tester.tap(find.text('Combo price').last);
  await tester.pumpAndSettle();
}

Future<void> _addProduct(WidgetTester tester, String code) async {
  await tester.enterText(
      find.widgetWithText(TextFormField, 'Add a product to the set'), code);
  await tester.pumpAndSettle();
  await tester.tap(find.textContaining('$code —').last);
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('sends the price and the items for the new benefit',
      (tester) async {
    final _Api api = _Api();
    await _open(tester, api);
    await _chooseCombo(tester);
    await _addProduct(tester, 'P1');
    await _addProduct(tester, 'P2');
    await tester.enterText(
        find.byKey(const ValueKey('promotion-combo-qty-0-1')), '2');
    await tester.enterText(
        find.byKey(const ValueKey('promotion-combo-price-0')), '120');
    await tester.ensureVisible(find.text('Save'));
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();

    final Map action = (api.sentBody!['actions'] as List).first as Map;
    expect(action['action_type'], 'COMBO_PRICE');
    expect(action['amount'], '120');
    expect(action['combo_items'], [
      {'product_id': 'prod-1', 'quantity': '1'},
      {'product_id': 'prod-2', 'quantity': '2'},
    ]);
    expect(action.containsKey('percent'), isFalse);
    expect(action.containsKey('buy_quantity'), isFalse);
  });

  testWidgets('one product is refused before anything is sent',
      (tester) async {
    final _Api api = _Api();
    await _open(tester, api);
    await _chooseCombo(tester);
    await _addProduct(tester, 'P1');
    await tester.enterText(
        find.byKey(const ValueKey('promotion-combo-price-0')), '120');
    await tester.ensureVisible(find.text('Save'));
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();
    expect(api.sentBody, isNull);
    expect(find.text('A combo needs at least two different products.'),
        findsOneWidget);
  });

  testWidgets('a missing price is refused', (tester) async {
    final _Api api = _Api();
    await _open(tester, api);
    await _chooseCombo(tester);
    await _addProduct(tester, 'P1');
    await _addProduct(tester, 'P2');
    await tester.ensureVisible(find.text('Save'));
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();
    expect(api.sentBody, isNull);
    expect(find.text('Enter the price of one set.'), findsOneWidget);
  });

  testWidgets('an edited offer loads its items and price', (tester) async {
    final _Api api = _Api();
    await _open(tester, api, existing: <String, dynamic>{
      'id': 'p-9',
      'code': 'COMBO',
      'name': 'Pair',
      'actions': [
        {
          'action_type': 'COMBO_PRICE',
          'parameters': {
            'price': '120.00',
            'items': [
              {'product_id': 'prod-1', 'quantity': '1'},
              {'product_id': 'prod-2', 'quantity': '3'},
            ],
          },
        },
      ],
    });
    expect(find.text('Product chosen earlier'), findsNWidgets(2));
    expect(find.widgetWithText(TextFormField, '120.00'), findsOneWidget);
    expect(find.widgetWithText(TextFormField, '3'), findsOneWidget);

    await tester.ensureVisible(find.text('Save'));
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();
    final Map action = (api.sentBody!['actions'] as List).first as Map;
    expect(action['amount'], '120.00');
    expect((action['combo_items'] as List).last,
        {'product_id': 'prod-2', 'quantity': '3'});
  });

  test('the summary reads 2 products for 120.00', () {
    final PromotionActionRecord record = PromotionActionRecord.fromJson(
      <String, dynamic>{
        'action_type': 'COMBO_PRICE',
        'parameters': <String, dynamic>{
          'price': '120.00',
          'items': [
            {'product_id': 'a', 'quantity': '1'},
            {'product_id': 'b', 'quantity': '1'},
          ],
        },
      },
    );
    expect(comboPriceLabel(record.comboItems.length, record.amount),
        '2 products for 120.00');
  });
}
