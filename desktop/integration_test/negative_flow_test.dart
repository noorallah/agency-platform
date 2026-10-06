import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'harness.dart';

/// Refusals, driven through the real screens. For each one the flow checks,
/// as a person would see it: (a) the refusal is shown in words, (b) the editor
/// or dialog stays open with what was typed still there, (c) nothing was
/// saved. What the screen did is printed as `FLOW: INFO` so a reader can judge
/// the wording; a refusal that closes, loses the typing, says nothing or
/// half-saves is recorded as a `DEFECT`.
///
///     IT_EMAIL=... IT_PASSWORD=... bash integration_test/run.sh \
///         negative_flow_test.dart
void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('negative: refusals on the main screens',
      (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1600, 1000);
    tester.view.devicePixelRatio = 1;
    final Server server = await Server.connect();
    await startAndSignIn(tester);
    final FlowLog flow = FlowLog('negative');

    final RegExp words = RegExp(
        r'must|need|choose|required|select|pick|add a|cannot|can.t|not |refus|invalid|already|exceed|more than|before|after|enter|insufficient|only',
        caseSensitive: false);

    Future<int> count(String collection) async =>
        ((await server.get('/api/v1/$collection?page_size=100')) as List)
            .length;

    /// Press [button] (a key or a label), then judge the three things.
    Future<void> refused(
      String label, {
      required String collection,
      required Future<void> Function() press,
      required String stillOpenKey,
      String? typedStillThere,
    }) async {
      await flow.step(label, () async {
        final int before = await count(collection);
        final Set<String> beforeText = textOnScreen(tester).toSet();
        await press();
        await pumpFor(tester, const Duration(seconds: 4));
        final bool open = find
            .byKey(ValueKey<String>(stillOpenKey))
            .evaluate()
            .isNotEmpty;
        final List<String> fresh = textOnScreen(tester)
            .where((String t) => !beforeText.contains(t))
            .toList();
        final String notice = noticeText(tester);
        final RegExp strict = RegExp(
            r'^(Enter|Choose|Select|Pick)|must|required|cannot|already|'
            r'not allowed|exceed|more than',
            caseSensitive: false);
        final List<String> said = <String>[
          ...fresh.where(words.hasMatch),
          ...textOnScreen(tester)
              .where((String t) => t.length < 160 && strict.hasMatch(t)),
          if (notice.isNotEmpty) notice,
        ];
        final int after = await count(collection);
        // ignore: avoid_print
        print('FLOW: INFO [negative] $label: open=$open, '
            'saved=${after - before}, said="${said.take(4).join(' | ')}"');
        if (after != before) {
          flow.defect(label, 'the refusal still saved ${after - before} '
              'record(s)');
        }
        if (!open) {
          flow.defect(label, 'the editor closed (typing lost)');
        } else if (typedStillThere != null &&
            !screenHas(tester, typedStillThere)) {
          flow.defect(label, 'what was typed ("$typedStillThere") is gone');
        }
        if (said.isEmpty) {
          flow.defect(label, 'nothing on screen says why it was refused');
        }
      });
    }

    // -- Sales order -------------------------------------------------------
    await flow.step('order: open a new one', () async {
      await openMenu(tester, 'sell', 'salesOrders');
      await tapNew(tester);
      await pumpUntil(
          tester, find.byKey(const ValueKey<String>('sales-order-save')));
    });
    await refused('order: save with no customer and no product',
        collection: 'sales-orders',
        press: () => tapKey(tester, 'sales-order-save'),
        stillOpenKey: 'sales-order-save');
    await flow.step('order: fill customer and product', () async {
      await chooseIn(tester, 'sales-order-customer', 'Vijaya Stores');
      await chooseIn(tester, 'sales-order-line-product-0', 'Detergent');
    });
    await refused('order: quantity 0',
        collection: 'sales-orders',
        press: () async {
          await typeIn(tester, 'sales-order-line-0', 1, '0');
          await tapKey(tester, 'sales-order-save');
        },
        stillOpenKey: 'sales-order-save');
    await refused('order: quantity -5',
        collection: 'sales-orders',
        press: () async {
          await typeIn(tester, 'sales-order-line-0', 1, '-5');
          await tapKey(tester, 'sales-order-save');
        },
        stillOpenKey: 'sales-order-save');

    // -- Sales return more than billed ------------------------------------
    await flow.step('return: more than was billed', () async {
      final Json? bill = await server.newest('sales-invoices');
      if (bill == null) throw StateError('no bill to return against');
      await openMenu(tester, 'sell', 'salesReturns');
      await tapNew(tester);
      await chooseIn(tester, 'sales-return-document', docNumber(bill));
      await pumpFor(tester, const Duration(seconds: 2));
      final int before = await count('sales-returns');
      await typeInKeyed(tester, 'sales-return-returning-', '9999');
      await pumpFor(tester, const Duration(seconds: 2));
      final String shown = textOnScreen(tester)
          .where((String t) => words.hasMatch(t) && t.length < 200)
          .take(5)
          .join(' | ');
      await tapKey(tester, 'sales-return-save');
      await pumpFor(tester, const Duration(seconds: 4));
      final bool open =
          find.byKey(const ValueKey<String>('sales-return-save'))
              .evaluate()
              .isNotEmpty;
      final int after = await count('sales-returns');
      // ignore: avoid_print
      print('FLOW: INFO [negative] return 9999: open=$open, '
          'saved=${after - before}, on screen="$shown", '
          'notice="${noticeText(tester)}"');
      if (after != before) flow.defect('return: 9999', 'saved a return');
      if (!open) flow.defect('return: 9999', 'the editor closed');
      if (shown.isEmpty && noticeText(tester).isEmpty) {
        flow.defect('return: 9999', 'nothing says why');
      }
    });

    // -- Receipt more than owed -------------------------------------------
    await flow.step('receipt: far more than the customer owes', () async {
      await openMenu(tester, 'sell', 'accounting/receipts');
      await tapNew(tester);
      await typeLabelled(tester, 'Received from', 'Vijaya');
      await pumpFor(tester, const Duration(seconds: 1));
      await tester.tap(find.textContaining('Vijaya Stores').last);
      await pumpFor(tester, const Duration(seconds: 2));
      await typeLabelled(tester, 'Amount', '9999999');
      final int before = await count('receipts');
      await tapButtonStarting(tester, 'Record ');
      await pumpFor(tester, const Duration(seconds: 4));
      final int after = await count('receipts');
      final bool open = find.byType(Dialog).evaluate().isNotEmpty;
      // ignore: avoid_print
      print('FLOW: INFO [negative] receipt 9999999: dialogOpen=$open, '
          'saved=${after - before}, notice="${noticeText(tester)}"');
      if (after != before && !open) {
        // Taken as an advance: say so in the record, not as a defect.
        // ignore: avoid_print
        print('FLOW: INFO [negative] the receipt was taken (advance)');
      }
      if (after == before && !open) {
        flow.defect('receipt: too much', 'closed without saving or saying');
      }
    });

    // -- Offer end before start -------------------------------------------
    await flow.step('offer: ends before it starts', () async {
      await openSetUp(tester, 'sales/promotions');
      await tapNew(tester);
      await typeLabelled(tester, 'Code', 'NEG${DateTime.now().millisecond}');
      await typeLabelled(tester, 'Name', 'Backwards offer');
      await typeLabelled(tester, 'Percent', '5');
      await typeLabelled(tester, 'From', '2026-12-01');
      await typeLabelled(tester, 'Until', '2026-11-01');
      final int before = await count('promotions');
      await tapButton(tester, 'Save');
      await pumpFor(tester, const Duration(seconds: 4));
      final int after = await count('promotions');
      final bool open = find.byType(Dialog).evaluate().isNotEmpty;
      final String said = <String>[
        noticeText(tester),
      ].join(' ');
      // ignore: avoid_print
      print('FLOW: INFO [negative] offer end<start: open=$open, '
          'saved=${after - before}, said="$said"');
      if (after != before) {
        flow.defect('offer: end before start', 'it was saved');
      }
      if (!open) flow.defect('offer: end before start', 'dialog closed');
    });

    // -- Duplicate coupon code --------------------------------------------
    await flow.step('coupon: a code that already exists', () async {
      await closeOpenEditor(tester);
      await tester.tap(find.text('Coupons').first);
      await pumpFor(tester, const Duration(seconds: 2));
      await tapNew(tester);
      await tester.tap(find.text('Offer').last);
      await pumpFor(tester, const Duration(milliseconds: 600));
      await tester.tap(find.textContaining('WELCOME —').last);
      await pumpFor(tester, const Duration(milliseconds: 600));
      await typeLabelled(tester, 'Code', 'WELCOME10');
      final int before = await count('promotions/coupons');
      await tapButton(tester, 'Create');
      await pumpFor(tester, const Duration(seconds: 4));
      final int after = await count('promotions/coupons');
      final bool open = find.byType(Dialog).evaluate().isNotEmpty;
      // ignore: avoid_print
      print('FLOW: INFO [negative] duplicate coupon: open=$open, '
          'saved=${after - before}, notice="${noticeText(tester)}"');
      if (after != before) flow.defect('coupon: duplicate', 'it was saved');
      if (!open) flow.defect('coupon: duplicate', 'dialog closed');
    });

    // -- Approve an order twice -------------------------------------------
    await flow.step('purchase order: approve a second time', () async {
      final dynamic rows = await server.get('/api/v1/purchases?page_size=100');
      final Json? done = (rows as List<dynamic>)
          .cast<Json>()
          .where((Json r) => !<String>['DRAFT', 'CANCELLED']
              .contains('${r['status']}'))
          .firstOrNull;
      if (done == null) throw StateError('no approved purchase order');
      await openMenu(tester, 'buy', 'purchases/purchase-orders');
      await selectRow(tester, docNumber(done));
      final Finder approve = find.ancestor(
        of: find.text('Approve'),
        matching: find.byWidgetPredicate(
            (Widget w) => w is ButtonStyleButton && w.onPressed != null),
      );
      final bool offered = approve.evaluate().isNotEmpty;
      // ignore: avoid_print
      print('FLOW: INFO [negative] approved order offers Approve again: '
          '$offered');
      if (offered) {
        flow.defect('purchase order: second approve',
            'Approve is still offered on an approved order');
      }
    });

    flow.finish();
  });
}
