import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'cases.dart';
import 'harness.dart';
import 'sell_data.dart';

/// Quotations (book section QT): Negative, Role and Multi-user cases, and the
/// Positive ones the selling flow does not cover.
///
/// Run once as the fixture firm's administrator, then once per role:
///
///     for h in tradeadmin qsexe qsmgr qro; do
///       IT_EMAIL=t10069cwy.$h@fixtures.local IT_PASSWORD=Fixture@2026pw \
///         LIMIT=900 bash integration_test/run.sh sc_qt_test.dart; done
///
/// A refused lifecycle step on this screen is a banner over the grid, not a
/// toast, so [said] reads both.
void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('QT: quotation cases ($itHandle)', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1600, 1000);
    tester.view.devicePixelRatio = 1;
    final Server me = await Server.connect();
    final Server admin = await Server.connectAs(
        't10069cwy.tradeadmin@fixtures.local', fixturePassword);
    await startAndSignIn(tester);
    collectAppErrors();
    final FlowLog log = FlowLog('qt-$itHandle');
    final String stamp =
        DateTime.now().millisecondsSinceEpoch.toString().substring(6);
    String day(int offset) => DateTime.now()
        .add(Duration(days: offset))
        .toIso8601String()
        .substring(0, 10);

    Future<void> openQuotes() async {
      await openMenu(tester, 'sell', 'quotations');
      await refreshList(tester);
    }

    Future<Json> one(String id) => admin.one('quotations', id);
    Future<String> statusOf(String id) async => '${(await one(id))['status']}';

    /// The masters of the newest order: customer, branch, warehouse, product.
    final Json? seed = await admin.newest('sales-orders');
    final Json seedFull = await admin.one('sales-orders', '${seed!['id']}');
    final Json seedLine = (seedFull['lines'] as List<dynamic>).first as Json;

    Json quoteBody({num quantity = 2, int from = 0, int until = 15}) =>
        <String, dynamic>{
          'customer_id': seedFull['customer_id'],
          'branch_id': seedFull['branch_id'],
          'warehouse_id': seedFull['warehouse_id'],
          'quotation_date': day(from),
          'valid_until': day(until),
          'lines': <Json>[
            <String, dynamic>{
              'line_number': 1,
              'product_id': seedLine['product_id'],
              'quantity': quantity,
            },
          ],
        };

    /// A quotation raised over HTTP by [by] and taken to [stage]
    /// (draft, sent, accepted, converted).
    Future<Json> apiQuote(Server by, {String stage = 'draft'}) async {
      Json q = (await by.write('POST', '/api/v1/quotations', quoteBody()))
          as Json;
      const List<String> order = <String>['send', 'accept', 'convert'];
      final int upTo = <String, int>{
        'draft': 0,
        'sent': 1,
        'accepted': 2,
        'converted': 3,
      }[stage]!;
      for (final String action in order.take(upTo)) {
        await apiAct(admin, 'quotations', '${q['id']}', action);
      }
      q = await one('${q['id']}');
      return q;
    }

    /// What a banner, a toast or a dialog says over the next [seconds].
    Future<String> said({int seconds = 5}) async {
      final Set<String> seen = <String>{};
      final DateTime end = DateTime.now().add(Duration(seconds: seconds));
      while (DateTime.now().isBefore(end)) {
        await tester.pump(const Duration(milliseconds: 200));
        final String n = noticeText(tester);
        if (n.isNotEmpty) seen.add(n);
        for (final Text t in tester.widgetList<Text>(find.descendant(
            of: find.byType(MaterialBanner), matching: find.byType(Text)))) {
          final String d = t.data ?? '';
          if (d.isNotEmpty && d != 'Dismiss') seen.add(d);
        }
      }
      return seen.join(' || ');
    }

    Future<void> dismissBanner() async {
      final Finder d = find.text('Dismiss');
      if (d.evaluate().isNotEmpty) {
        await tester.tap(d.first);
        await pumpFor(tester, const Duration(milliseconds: 400));
      }
    }

    Map<String, String> buttons(List<String> names) => <String, String>{
          for (final String b in names) b: buttonState(tester, b),
        };

    const List<String> lifecycle = <String>[
      'Mark as sent',
      'Revise',
      'Customer accepted',
      'Customer declined',
      'Convert to order',
      'Withdraw',
    ];

    Future<void> newQuote({bool customer = true, bool product = true}) async {
      await openQuotes();
      await tapNew(tester);
      await pumpUntil(
          tester, find.byKey(const ValueKey<String>('quotation-save')),
          waitingFor: 'the quotation editor');
      if (customer) {
        await chooseIn(tester, 'quotation-customer', 'Vijaya Stores');
      }
      if (product) {
        await chooseIn(tester, 'quotation-line-product-0', 'Detergent');
      }
    }

    Future<String> refuse(Future<void> Function() typing, {String? typed}) =>
        expectRefusal(tester, me,
            collection: 'quotations',
            openKey: 'quotation-save',
            typed: typed,
            press: () async {
              await typing();
              await tapKey(tester, 'quotation-save');
            });

    if (itHandle == 'tradeadmin') {
      final Json draft = await apiQuote(admin);
      final Json forDecline = await apiQuote(admin, stage: 'sent');
      final Json forWithdraw = await apiQuote(admin);
      final Json converted = await apiQuote(admin, stage: 'converted');
      final Json forStale = await apiQuote(admin, stage: 'accepted');
      final Json forTwoUsers = await apiQuote(admin);

      await log.step('SC-QT-001 list opens with its columns', () async {
        await openQuotes();
        final List<String> missing = <String>[
          for (final String h in <String>[
            'Quotation Number',
            'Customer',
            'Quotation Date',
            'Valid Until',
            'Status',
            'Grand Total',
          ])
            if (!screenHas(tester, h)) h,
        ];
        log.saw = 'missing $missing; header '
            '${rowOf(tester, 'Quotation Number').take(12).join(' / ')}';
        if (missing.isNotEmpty) {
          throw StateError('not on screen: ${missing.join(', ')}');
        }
      });

      // -- Negative: the editor ----------------------------------------------
      await log.step('SC-QT-016 no customer: Save is refused', () async {
        await newQuote(customer: false);
        log.saw = await refuse(() async {
          await typeIn(tester, 'quotation-line-0', 1, '3');
        });
      });
      await closeOpenEditor(tester);

      await log.step('SC-QT-017 customer but no line: Save is refused',
          () async {
        await newQuote(product: false);
        log.saw = await refuse(() async {}, typed: 'Vijaya');
      });
      await closeOpenEditor(tester);

      for (final String q in <String>['0', '-5']) {
        await log.step(
            'SC-QT-0${q == '0' ? '18' : '19'} quantity $q is refused',
            () async {
          await newQuote();
          log.saw = await refuse(() async {
            await typeIn(tester, 'quotation-line-0', 1, q);
            log.info('SC-QT-0${q == '0' ? '18' : '19'}',
                'boxes: ${boxesIn(tester, 'quotation-line-0')}');
          }, typed: 'Vijaya');
        });
        await closeOpenEditor(tester);
      }

      await log.step('SC-QT-020 Valid until before the quotation date',
          () async {
        final ({int status, String text}) r = await admin.attempt(
            'POST', '/api/v1/quotations', quoteBody(from: 0, until: -1));
        await newQuote();
        await tapKey(tester, 'quotation-valid-until');
        await pumpFor(tester, const Duration(seconds: 1));
        final bool picker =
            find.byType(DatePickerDialog).evaluate().isNotEmpty;
        // Yesterday's number is greyed out in a picker that starts today.
        final String yesterday =
            '${DateTime.now().subtract(const Duration(days: 1)).day}';
        bool offered = false;
        if (picker && DateTime.now().day > 1) {
          final Finder cell = find.descendant(
              of: find.byType(DatePickerDialog),
              matching: find.text(yesterday));
          if (cell.evaluate().isNotEmpty) {
            await tester.tap(cell.first, warnIfMissed: false);
            await pumpFor(tester, const Duration(milliseconds: 500));
            await tapDialogButton(tester, 'OK');
            offered = !screenHas(tester,
                '${DateTime.now().add(const Duration(days: 15)).day}'.padLeft(2, '0'));
          }
        } else if (picker) {
          await tapDialogButton(tester, 'Cancel');
        }
        log.saw = 'picker opened=$picker; over HTTP a quotation valid until '
            'yesterday answered ${r.status}: '
            '${r.text.length > 160 ? r.text.substring(0, 160) : r.text}; '
            'the picker starts at the quotation date (prevention), a day '
            'before it changed the box=$offered';
        if (r.status < 400) {
          throw StateError('the server accepted a quotation valid until the '
              'day before its date');
        }
      });
      await closeOpenEditor(tester);

      await log.step('SC-QT-025 the Cancel button on a typed-in editor asks; '
          'Keep keeps; Discard saves nothing', () async {
        await newQuote();
        await typeIn(tester, 'quotation-line-0', 1, '6');
        final int before = await totalOf(me, 'quotations');
        await tapButton(tester, 'Cancel');
        await pumpFor(tester, const Duration(seconds: 1));
        final String question = dialogText(tester);
        if (question.isEmpty) {
          throw StateError('Cancel asked nothing (editor open='
              '${find.byKey(const ValueKey<String>('quotation-save')).evaluate().isNotEmpty})');
        }
        await tapKey(tester, 'document-keep-editing');
        final bool kept = screenHasTyped(tester, 'Vijaya');
        await tester.sendKeyEvent(LogicalKeyboardKey.escape);
        await pumpFor(tester, const Duration(seconds: 1));
        final String onEsc = dialogText(tester);
        if (onEsc.isNotEmpty) {
          await tapKey(tester, 'document-discard');
        } else {
          await tapButton(tester, 'Cancel');
          await tapKey(tester, 'document-discard');
        }
        await pumpFor(tester, const Duration(seconds: 1));
        final bool gone = find
            .byKey(const ValueKey<String>('quotation-save'))
            .evaluate()
            .isEmpty;
        final int saved = await totalOf(me, 'quotations') - before;
        log.saw = 'asked "$question"; Keep editing kept the typing=$kept; '
            'Esc after a click asked=${onEsc.isNotEmpty}; Discard closed='
            '$gone; saved=$saved';
        if (!kept) throw StateError('Keep editing lost the customer');
        if (onEsc.isEmpty) throw StateError('Esc did nothing in the editor');
        if (!gone || saved != 0) {
          throw StateError('Discard: closed=$gone, saved=$saved');
        }
      });
      await closeOpenEditor(tester);

      // -- Negative: the lifecycle -------------------------------------------
      await log.step('SC-QT-021 Convert to order is not offered on a Draft',
          () async {
        await openQuotes();
        await selectRow(tester, docNumber(draft));
        final Map<String, String> s = buttons(lifecycle);
        log.saw = '$s';
        if (s['Convert to order'] == 'enabled') {
          throw StateError('Convert to order is offered on a Draft');
        }
        if (s['Customer accepted'] == 'enabled') {
          throw StateError('Customer accepted is offered on a Draft');
        }
      });

      await log.step('SC-QT-022 a Converted quotation cannot be converted '
          'again', () async {
        await openQuotes();
        await selectRow(tester, docNumber(converted));
        final String c = buttonState(tester, 'Convert to order');
        log.saw = 'Convert to order is $c on a Converted quotation';
        if (c == 'enabled') throw StateError('Convert offered again');
      });

      await log.step('SC-QT-023 Revise, Withdraw and Customer declined on a '
          'Converted quotation', () async {
        await openQuotes();
        await selectRow(tester, docNumber(converted));
        final Map<String, String> s =
            buttons(<String>['Revise', 'Withdraw', 'Customer declined']);
        log.saw = '$s; status ${await statusOf('${converted['id']}')}';
        final List<String> on = <String>[
          for (final MapEntry<String, String> e in s.entries)
            if (e.value == 'enabled') e.key,
        ];
        if (on.isNotEmpty) throw StateError('offered: $on');
      });

      await log.step('SC-QT-022 stale Convert after another user converted',
          () async {
        await openQuotes();
        await selectRow(tester, docNumber(forStale));
        await apiAct(await asUser('qsmgr'), 'quotations',
            '${forStale['id']}', 'convert');
        final int before = await totalOf(admin, 'sales-orders');
        await tapButton(tester, 'Convert to order');
        final String words = await said();
        final int more = await totalOf(admin, 'sales-orders') - before;
        log.saw = 'screen says "$words"; orders raised by the second press: '
            '$more';
        await dismissBanner();
        if (more != 0) throw StateError('a second order was raised');
        if (words.isEmpty) throw StateError('N1: stale Convert said nothing');
      });

      await log.step('SC-QT-024 a quotation past its Valid Until', () async {
        final ({int status, String text}) r = await admin.attempt(
            'POST', '/api/v1/quotations', quoteBody(from: -20, until: -5));
        if (r.status >= 400) {
          log.saw = 'a quotation dated 20 days back and valid until 5 days '
              'back cannot be raised (${r.status}: '
              '${r.text.length > 200 ? r.text.substring(0, 200) : r.text}); '
              'no expired quotation can be made in one run';
          throw StateError('could not make an expired quotation: ${log.saw}');
        }
        final String number =
            RegExp(r'"quotation_number":\s*"([^"]+)').firstMatch(r.text)!.group(1)!;
        await openQuotes();
        await selectRow(tester, number);
        final bool badge = screenHas(tester, 'EXPIRED');
        final Map<String, String> s = buttons(lifecycle);
        String words = '';
        if (s['Mark as sent'] == 'enabled') {
          await tapButton(tester, 'Mark as sent');
          words = await said();
          await dismissBanner();
        }
        log.saw = '$number: EXPIRED badge=$badge; $s; Mark as sent says '
            '"$words"';
        if (!badge) throw StateError('no EXPIRED badge on the row');
        if (s['Convert to order'] == 'enabled') {
          throw StateError('Convert to order offered on an expired Draft');
        }
      });

      log.skip('SC-QT-026', 'no inactive customer in the fixture firm, and '
          'making one would change a master the other cases use');

      // -- Positive ----------------------------------------------------------
      await log.step('SC-QT-009 Customer declined on a Sent quotation',
          () async {
        await openQuotes();
        await selectRow(tester, docNumber(forDecline));
        final String words =
            await pressWithReason(tester, 'Customer declined', reason: 'price');
        final String st = await statusOf('${forDecline['id']}');
        await refreshList(tester);
        await selectRow(tester, docNumber(forDecline));
        final String c = buttonState(tester, 'Convert to order');
        log.saw = 'status $st; screen says "$words"; row '
            '${rowOf(tester, docNumber(forDecline)).take(9).join(' / ')}; '
            'Convert to order $c';
        if (st != 'DECLINED' && st != 'REJECTED') {
          throw StateError('status $st after Customer declined');
        }
        if (c == 'enabled') throw StateError('Convert offered after decline');
      });

      await log.step('SC-QT-010 Withdraw a Draft', () async {
        await openQuotes();
        await selectRow(tester, docNumber(forWithdraw));
        final String words =
            await pressWithReason(tester, 'Withdraw', reason: 'raised twice');
        final String st = await statusOf('${forWithdraw['id']}');
        await refreshList(tester);
        await selectRow(tester, docNumber(forWithdraw));
        final Map<String, String> s =
            buttons(<String>['Revise', 'Convert to order', 'Mark as sent']);
        log.saw = 'status $st; screen says "$words"; afterwards $s';
        if (st != 'CANCELLED' && st != 'WITHDRAWN') {
          throw StateError('status $st after Withdraw');
        }
        if (s.values.any((String v) => v == 'enabled')) {
          throw StateError('still offered after Withdraw: $s');
        }
      });

      await log.step('SC-QT-011 Send and Attachments open (Print not '
          'pressed)', () async {
        await openQuotes();
        await selectRow(tester, docNumber(draft));
        final List<String> out = <String>[
          'Print ${buttonState(tester, 'Print')} (not pressed: the system '
              'print preview never returns to a test run)',
        ];
        for (final String b in <String>['Send', 'Attachments']) {
          final String st = buttonState(tester, b);
          if (st != 'enabled') {
            out.add('$b $st');
            continue;
          }
          await tapButton(tester, b);
          await pumpFor(tester, const Duration(seconds: 2));
          final bool opened = find.byType(Dialog).evaluate().isNotEmpty;
          out.add('$b opened=$opened'
              '${opened ? ' ("${dialogText(tester).split(' | ').take(3).join(' / ')}")' : ' (says "${noticeText(tester)}")'}');
          await closeOpenEditor(tester);
        }
        log.saw = out.join('; ');
        if (out.skip(1).any((String s) => !s.contains('opened=true'))) {
          throw StateError(out.join('; '));
        }
      });

      await log.step('SC-QT-004 a blank discount box says what it takes',
          () async {
        await newQuote();
        await pumpFor(tester, const Duration(seconds: 3));
        final String boxes = boxesIn(tester, 'quotation-line-0');
        final List<String> hints = textOnScreen(tester)
            .where((String t) =>
                t.length < 160 &&
                RegExp(r'price list|standing|%|level|blank',
                        caseSensitive: false)
                    .hasMatch(t))
            .take(6)
            .toList();
        log.saw = 'line boxes "$boxes"; texts naming a rate: $hints';
        if (hints.isEmpty) {
          throw StateError('nothing under the line says which rate a blank '
              'discount takes (boxes "$boxes")');
        }
      });
      await closeOpenEditor(tester);

      await log.step('SC-QT-012 Rate includes GST: 118 is 100 plus 18',
          () async {
        await newQuote();
        final Finder tick =
            find.byKey(const ValueKey<String>('quotation-rate-includes-tax'));
        if (tick.evaluate().isEmpty) {
          throw StateError('the Rate includes GST switch is not on the '
              'editor in this firm');
        }
        final Finder boxes = find.descendant(
            of: find.byKey(const ValueKey<String>('quotation-line-0')),
            matching: find.byType(EditableText));
        int rateBox = -1;
        final List<EditableText> all =
            tester.widgetList<EditableText>(boxes).toList();
        for (int i = 2; i < all.length; i++) {
          final double? v = double.tryParse(all[i].controller.text);
          if (v != null && v > 1) {
            rateBox = i;
            break;
          }
        }
        if (rateBox < 0) {
          throw StateError('no rate box found on the line: '
              '${boxesIn(tester, 'quotation-line-0')}');
        }
        await tester.tap(tick.first);
        await pumpFor(tester, const Duration(milliseconds: 600));
        await typeIn(tester, 'quotation-line-0', 1, '1');
        await typeIn(tester, 'quotation-line-0', rateBox, '118');
        await pumpFor(tester, const Duration(seconds: 2));
        await saveEditor(tester, 'quotation-save');
        final Json q = (await admin.newest('quotations'))!;
        final Json full = await one('${q['id']}');
        final ({double sub, double tax, double grand}) f = figuresOf(full);
        final Json line = (full['lines'] as List<dynamic>).first as Json;
        log.saw = '${docNumber(full)}: taxable ${f.sub}, tax ${f.tax}, grand '
            '${f.grand}; line discount ${line['discount_percent']} percent '
            '(the customer\'s own arrangement comes off the 100), rate box '
            'was number $rateBox';
        if (!sameMoney(f.sub + f.tax, f.grand)) {
          throw StateError('grand ${f.grand} is not ${f.sub} + ${f.tax}');
        }
        final double gross = num2(line['unit_price']) *
            (1 + num2(line['tax_percent'] ?? line['gst_rate'] ?? 18) / 100);
        log.saw = '${log.saw}; stored rate ${line['unit_price']} '
            '(with tax ${gross.toStringAsFixed(2)})';
        if ((num2(line['unit_price']) - 100).abs() > 0.01) {
          throw StateError('the stored rate is ${line['unit_price']}, not '
              'the 100 before tax');
        }
      });
      await closeOpenEditor(tester);

      await log.step('SC-QT-013 a coupon nobody recognises: no discount, no '
          'refusal', () async {
        await newQuote();
        await typeIn(tester, 'quotation-line-0', 1, '2');
        await typeInKeyed(tester, 'quotation-coupon', 'NOSUCH$stamp');
        await pumpFor(tester, const Duration(seconds: 2));
        final String hint = textOnScreen(tester)
            .where((String t) =>
                t.length < 160 &&
                RegExp(r'coupon|code', caseSensitive: false).hasMatch(t))
            .take(4)
            .join(' | ');
        await saveEditor(tester, 'quotation-save');
        final Json q = (await admin.newest('quotations'))!;
        log.saw = 'saved ${docNumber(q)} with coupon ${q['coupon_code']}; '
            'the editor said of it: "$hint"';
        if ('${q['coupon_code']}' != 'NOSUCH$stamp') {
          throw StateError('the newest quotation is not the one typed');
        }
      });
      await closeOpenEditor(tester);
      log.info('SC-QT-013', 'the half with a real coupon (WELCOME10 lowering '
          'the line) is driven in the coupon file, SC-CP-012/013');

      await log.step('SC-QT-014 Search narrows the grid and clearing brings '
          'the rows back', () async {
        await openQuotes();
        final String wanted = docNumber(draft);
        final String other = docNumber(forTwoUsers);
        final Finder box = find.ancestor(
            of: find.text('Search number or customer'),
            matching: find.byType(TextField));
        await pumpUntil(tester, box, waitingFor: 'the search box');
        await tester.enterText(box.first, wanted);
        await tester.testTextInput.receiveAction(TextInputAction.search);
        await pumpFor(tester, const Duration(seconds: 3));
        final bool has = screenHas(tester, wanted);
        final bool hasOther = find.text(other).evaluate().isNotEmpty;
        final Finder typed = find.byWidgetPredicate((Widget w) =>
            w is EditableText && w.controller.text == wanted);
        await tester.enterText(typed.first, '');
        await tester.testTextInput.receiveAction(TextInputAction.search);
        await pumpFor(tester, const Duration(seconds: 3));
        final bool back = find.text(other).evaluate().isNotEmpty;
        log.saw = 'searched $wanted: shown=$has, another row ($other) '
            'shown=$hasOther; after clearing the other row is back=$back';
        if (!has || hasOther) throw StateError('search did not narrow');
        if (!back) {
          throw StateError('clearing the search left the grid narrowed');
        }
      });

      log.skip('SC-QT-015', 'no enquiry in the fixture firm');
      log.skip('SC-QT-030', 'no price floor or discount limit is set in the '
          'fixture firm');
      log.skip('SC-QT-029', 'the fixture firm has no Cashier or Billing '
          'Executive user');

      // -- Multi-user ---------------------------------------------------------
      await log.step('SC-QT-032 a save from a stale copy is refused and the '
          'typing kept', () async {
        await openQuotes();
        await selectRow(tester, docNumber(forTwoUsers));
        await tapButton(tester, 'Revise');
        await pumpUntil(
            tester, find.byKey(const ValueKey<String>('quotation-save')),
            waitingFor: 'the quotation editor');
        await pumpFor(tester, const Duration(seconds: 2));
        final Server other = await asUser('qsmgr');
        final ({int status, String text}) theirs = await other.attempt(
            'PUT',
            '/api/v1/quotations/${forTwoUsers['id']}',
            quoteBody(quantity: 9));
        if (theirs.status >= 400) {
          throw StateError('the second user could not save: '
              '${theirs.status} ${theirs.text}');
        }
        await typeIn(tester, 'quotation-line-0', 1, '4');
        await tapKey(tester, 'quotation-save');
        final String words = await said(seconds: 5);
        final bool open = find
            .byKey(const ValueKey<String>('quotation-save'))
            .evaluate()
            .isNotEmpty;
        final List<String> extra = textOnScreen(tester)
            .where((String t) =>
                t.length < 260 &&
                RegExp(r'changed|somebody|reload|since', caseSensitive: false)
                    .hasMatch(t))
            .take(2)
            .toList();
        final Json now = await one('${forTwoUsers['id']}');
        final double qty = num2(
            ((now['lines'] as List<dynamic>).first as Json)['quantity']);
        log.saw = 'editor open=$open; says "$words" $extra; the record now '
            'holds quantity $qty (the other user saved 9, this one typed 4)';
        if (qty == 4) {
          throw StateError('the stale save went through: the other user\'s '
              '9 was overwritten by 4 (open=$open, said "$words" $extra)');
        }
        if (!open) throw StateError('N2: the editor closed');
        if (words.isEmpty && extra.isEmpty) {
          throw StateError('N1: nothing says why the save did not happen');
        }
      });
      await closeOpenEditor(tester);
    } else {
      final Map<String, List<String>> menu = await offeredMenu(tester);
      final bool offered = menuHas(menu, 'quotations');
      final ({int status, String text}) api =
          await me.attempt('GET', '/api/v1/quotations?page_size=1', null);

      if (itHandle == 'qsexe') {
        await log.step('SC-QT-027 FS: Quotations offered with New and the '
            'steps of an offer', () async {
          if (!offered) throw StateError('Quotations not offered to FS');
          final Json mine = await apiQuote(me);
          await openQuotes();
          await selectRow(tester, docNumber(mine));
          final Map<String, String> s =
              buttons(<String>['+ New', 'New', ...lifecycle]);
          log.saw = 'offered=$offered, list ${api.status}; on a Draft of '
              'their own: $s';
          final List<String> wrong = <String>[
            if (s['+ New'] != 'enabled' && s['New'] != 'enabled')
              'New not offered',
            for (final String b in <String>['Revise', 'Mark as sent'])
              if (s[b] != 'enabled') '$b ${s[b]}',
          ];
          if (wrong.isNotEmpty) throw StateError(wrong.join(', '));
        });
      } else if (itHandle == 'qro') {
        await log.step('SC-QT-028 RO: rows readable, no write button',
            () async {
          if (!offered) throw StateError('Quotations not offered to RO');
          final Json theirs = await apiQuote(admin);
          await openQuotes();
          await selectRow(tester, docNumber(theirs));
          final Map<String, String> s =
              buttons(<String>['+ New', 'New', ...lifecycle]);
          log.saw = 'offered=$offered, list ${api.status}; $s';
          final List<String> on = <String>[
            for (final MapEntry<String, String> e in s.entries)
              if (e.value == 'enabled') e.key,
          ];
          if (on.isNotEmpty) throw StateError('Read Only is offered: $on');
        });
      } else if (itHandle == 'qsmgr') {
        await log.step('SC-QT-031 SM sees the quotation FS left, with the '
            'same number, total and status', () async {
          if (!offered) throw StateError('Quotations not offered to SM');
          final Json theirs = await apiQuote(await asUser('qsexe'));
          await openQuotes();
          await selectRow(tester, docNumber(theirs));
          final List<String> row = rowOf(tester, docNumber(theirs));
          final double grand = figuresOf(theirs).grand;
          log.saw = 'row ${row.take(10).join(' / ')}; server total $grand, '
              'status ${theirs['status']}';
          if (!screenShowsMoney(tester, grand)) {
            throw StateError('the total $grand is not on the row');
          }
          if (!row.any((String t) => t.toLowerCase() == 'draft')) {
            throw StateError('the row does not read Draft');
          }
        });
      }
    }
    log.finish();
  });
}
