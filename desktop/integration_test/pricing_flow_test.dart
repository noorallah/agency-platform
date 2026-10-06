import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'harness.dart';

/// The pricing screens, driven through the real phase 2 app against the live
/// server: a price list, an offer with a budget, a coupon, the loyalty
/// screen, a commission rule, the principal claim preview, and one sales
/// order that picks the offer up.
///
///     IT_EMAIL=... IT_PASSWORD=... bash integration_test/run.sh \
///         pricing_flow_test.dart
void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('pricing: lists, offers, coupons, loyalty, commission, claims',
      (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1600, 1000);
    tester.view.devicePixelRatio = 1;
    final Server server = await Server.connect();
    await startAndSignIn(tester);
    final FlowLog flow = FlowLog('pricing');
    final String stamp =
        DateTime.now().millisecondsSinceEpoch.toString().substring(7);
    final String listCode = 'FLPL$stamp';
    final String offerCode = 'FLOF$stamp';
    final String couponCode = 'FLCP$stamp';

    // -- Price list --------------------------------------------------------
    await flow.step('price list: new with a product price, save', () async {
      await openSetUp(tester, 'sales/price-lists');
      await tapButtonStarting(tester, 'New price list');
      await typeLabelled(tester, 'Code', listCode);
      await typeLabelled(tester, 'Name', 'Flow list $stamp');
      await tapButtonStarting(tester, 'Add product');
      await chooseInKeyed(tester, 'price-list-rate-product-', 'Detergent');
      await typeInKeyed(tester, 'price-list-rate-fixed-', '80');
      await tapButton(tester, 'Save');
      await pumpFor(tester, const Duration(seconds: 3));
      final dynamic rows = await server.get('/api/v1/price-lists?page_size=100');
      final Json? made = (rows as List<dynamic>)
          .cast<Json>()
          .where((Json r) => r['code'] == listCode)
          .firstOrNull;
      if (made == null) throw StateError('price list $listCode not saved');
      final Json full = await server.one('price-lists', '${made['id']}');
      final dynamic items = full['items'] ?? full['lines'] ?? full['rates'];
      if (items is! List || items.isEmpty) {
        throw StateError('saved list has no product price '
            '(keys: ${full.keys.join(',')})');
      }
      final Json first = items.first as Json;
      final double rate =
          num2(first['fixed_price'] ?? first['rate'] ?? first['price']);
      if (rate != 80) throw StateError('product price saved as $rate, typed 80');
      if (!screenHas(tester, listCode)) {
        flow.defect('price list: grid', '$listCode is not on the list screen');
      }
    });

    // -- Offer with a budget ----------------------------------------------
    await flow.step('offer: new with a budget, save, reopen', () async {
      await openSetUp(tester, 'sales/promotions');
      await tapButtonStarting(tester, 'New promotion');
      await typeLabelled(tester, 'Code', offerCode);
      await typeLabelled(tester, 'Name', 'Flow offer $stamp');
      await typeLabelled(tester, 'Percent', '5');
      await typeLabelled(tester, 'Budget (value)', '5000');
      await tapButton(tester, 'Save');
      await pumpFor(tester, const Duration(seconds: 3));
      final dynamic rows = await server.get('/api/v1/promotions?page_size=100');
      final Json? made = (rows as List<dynamic>)
          .cast<Json>()
          .where((Json r) => r['code'] == offerCode)
          .firstOrNull;
      if (made == null) throw StateError('offer $offerCode not saved');
      final double budget = num2(made['max_benefit_amount'] ??
          made['max_benefit'] ??
          made['budget_value']);
      if (budget != 5000) {
        throw StateError('budget saved as $budget, typed 5000 '
            '(keys: ${made.keys.join(',')})');
      }
      // Reopen: a double click on its row opens the read-only view.
      final Finder row = find.text(offerCode);
      await pumpUntil(tester, row, waitingFor: 'the offer row');
      await tester.tap(row.first);
      await tester.pump(const Duration(milliseconds: 60));
      await tester.tap(row.first);
      await pumpFor(tester, const Duration(seconds: 2));
      if (!screenHas(tester, 'Budget')) {
        flow.defect('offer: reopen', 'the offer view shows no Budget section');
      } else if (!screenHas(tester, '5,000')) {
        flow.defect('offer: reopen',
            'the Budget section does not show 5,000: '
            '${textOnScreen(tester).where((String t) => t.contains('udget')).join(' | ')}');
      }
      await tapButton(tester, 'Close');
    });

    // -- Coupon ------------------------------------------------------------
    await flow.step('coupon: new for the offer, save', () async {
      await tester.tap(find.text('Coupons').first);
      await pumpFor(tester, const Duration(seconds: 2));
      await tapButtonStarting(tester, 'New coupon');
      await tester.tap(find.text('Offer').last);
      await pumpFor(tester, const Duration(milliseconds: 600));
      await tester.tap(find.textContaining(offerCode).last);
      await pumpFor(tester, const Duration(milliseconds: 600));
      await typeLabelled(tester, 'Code', couponCode);
      await tapButton(tester, 'Save');
      await pumpFor(tester, const Duration(seconds: 3));
      final dynamic rows =
          await server.get('/api/v1/promotions/coupons?page_size=100');
      final bool found = (rows as List<dynamic>)
          .cast<Json>()
          .any((Json r) => r['code'] == couponCode);
      if (!found) throw StateError('coupon $couponCode not saved');
      if (!screenHas(tester, couponCode)) {
        flow.defect('coupon: grid', '$couponCode is not on the coupons grid');
      }
    });

    // -- Loyalty -----------------------------------------------------------
    await flow.step('loyalty: opens and shows a customer\'s points', () async {
      await openSetUp(tester, 'masters/loyalty');
      await tapKey(tester, 'loyalty-customer');
      await pumpFor(tester, const Duration(milliseconds: 600));
      await tester.tap(find.textContaining('Vijaya Stores').last);
      await pumpFor(tester, const Duration(seconds: 3));
      if (!screenHas(tester, 'Points')) {
        throw StateError('no Points figure after choosing the customer');
      }
      // ignore: avoid_print
      print('FLOW: INFO [pricing] loyalty screen: '
          '${textOnScreen(tester).take(40).join(' | ')}');
    });

    // -- Commission rule ---------------------------------------------------
    await flow.step('commission: new rule, save', () async {
      await openMenu(tester, 'sell', 'sales/commission');
      await tapButton(tester, 'Add rule');
      await typeLabelled(tester, 'Rate', '3');
      await tapButton(tester, 'Save');
      await pumpFor(tester, const Duration(seconds: 3));
      final dynamic rows =
          await server.get('/api/v1/commission/rules?page_size=100');
      final bool found = (rows as List<dynamic>)
          .cast<Json>()
          .any((Json r) => num2(r['percentage'] ?? r['rate']) == 3);
      if (!found) throw StateError('no 3% commission rule on the server');
    });

    // -- Principal claim ---------------------------------------------------
    await flow.step('principal claim: open, price cut claim preview',
        () async {
      await openMenu(tester, 'buy', 'purchases/principal-claims');
      await tapKey(tester, 'claim-new-price-cut');
      await pumpFor(tester, const Duration(seconds: 2));
      if (!screenHas(tester, 'Preview') && !screenHas(tester, 'Show')) {
        // ignore: avoid_print
        print('FLOW: INFO [pricing] claim dialog: '
            '${textOnScreen(tester).take(40).join(' | ')}');
      }
      await tapButtonStarting(tester, 'Preview');
      await pumpFor(tester, const Duration(seconds: 3));
      final bool shown =
          find.byKey(const ValueKey<String>('claim-preview-result'))
              .evaluate()
              .isNotEmpty;
      final bool refused = screenHas(tester, 'Choose') ||
          screenHas(tester, 'needs') ||
          screenHas(tester, 'must');
      if (!shown && !refused) {
        throw StateError('preview answered nothing on screen');
      }
      await tapButton(tester, 'Cancel');
    });

    // -- An order that picks the offer up ----------------------------------
    await flow.step('order: picks up the offer, shows its discount', () async {
      await openMenu(tester, 'sell', 'salesOrders');
      await tapButtonStarting(tester, 'New Order');
      await chooseIn(tester, 'sales-order-customer', 'Vijaya Stores');
      await chooseIn(tester, 'sales-order-line-product-0', 'Detergent');
      await typeIn(tester, 'sales-order-line-0', 1, '10');
      await pumpFor(tester, const Duration(seconds: 4));
      final bool offerOnScreen = screenHas(tester, 'Flow offer') ||
          screenHas(tester, offerCode) ||
          screenHas(tester, '5%');
      await tapKey(tester, 'sales-order-save');
      await pumpFor(tester, const Duration(seconds: 3));
      final Json? order = await server.newest('sales-orders');
      if (order == null) throw StateError('nothing was saved');
      final Json full = await server.one('sales-orders', '${order['id']}');
      final Json line = (full['lines'] as List<dynamic>).first as Json;
      final double percent = num2(line['discount_percent']);
      final String source = '${line['discount_source']}';
      if (percent != 5 || !source.toUpperCase().contains('PROMOTION')) {
        throw StateError('line discount is $percent from "$source", '
            'the offer gives 5 from a promotion');
      }
      if (!offerOnScreen) {
        flow.defect('order: offer on screen',
            'the editor did not name the offer or its 5% while typing');
      }
      final String? fault = arithmeticFault(full, quantity: 10);
      if (fault != null) throw StateError(fault);
      final double unit = num2(line['unit_price']);
      final double expected = unit * 10 * 0.95;
      if (!sameMoney(figuresOf(full).sub, expected)) {
        throw StateError('taxable ${figuresOf(full).sub}, expected '
            '$expected (10 x $unit less 5%)');
      }
      if (!screenShowsMoney(tester, figuresOf(full).grand)) {
        flow.defect('order: list total',
            'grand ${figuresOf(full).grand} is not on the list screen');
      }
    });

    flow.finish();
  });
}
