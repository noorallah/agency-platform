import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'cases.dart';
import 'harness.dart';
import 'sell_data.dart';

/// Proforma (book section PF).
///
/// Run once as the fixture firm's administrator, then once per role:
///
///     for h in tradeadmin qsmgr qsexe qro; do
///       IT_EMAIL=t10069cwy.$h@fixtures.local IT_PASSWORD=Fixture@2026pw \
///         LIMIT=900 bash integration_test/run.sh sc_pf_test.dart; done
void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('PF: proforma cases ($itHandle)', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1600, 1000);
    tester.view.devicePixelRatio = 1;
    final Server me = await Server.connect();
    final Server admin = await Server.connectAs(
        't10069cwy.tradeadmin@fixtures.local', fixturePassword);
    await startAndSignIn(tester);
    collectAppErrors();
    final FlowLog log = FlowLog('pf-$itHandle');
    const String menuPath = 'sales/proforma-invoices';
    const String api = 'proforma-invoices';
    String day(int offset) => DateTime.now()
        .add(Duration(days: offset))
        .toIso8601String()
        .substring(0, 10);

    final Map<String, List<String>> menu = await offeredMenu(tester);
    final bool offered = menuHas(menu, menuPath);

    Future<void> openProformas() async {
      await openMenu(tester, 'sell', menuPath);
      await refreshList(tester);
    }

    Future<Json> one(String id) => admin.one(api, id);
    Future<String> statusOf(String id) async => '${(await one(id))['status']}';
    Future<int> journals() => totalOf(admin, 'finance/journal-entries');

    Future<Json> approvedOrder() async {
      final Json order = await apiDraftOrder(admin, quantity: 2);
      await apiAct(admin, 'sales-orders', '${order['id']}', 'approve');
      return admin.one('sales-orders', '${order['id']}');
    }

    Future<Json> apiProforma(Json order, {bool issued = false}) async {
      final Json p = (await admin.write('POST', '/api/v1/$api',
          <String, dynamic>{
        'sales_order_id': order['id'],
        'proforma_date': day(0),
      })) as Json;
      if (issued) await apiAct(admin, api, '${p['id']}', 'issue');
      return one('${p['id']}');
    }

    Map<String, String> buttons() => <String, String>{
          for (final String b in <String>['+ New', 'New', 'Issue', 'Withdraw'])
            b: buttonState(tester, b),
        };

    bool editorOpen() => find
        .byKey(const ValueKey<String>('proforma-raise'))
        .evaluate()
        .isNotEmpty;

    if (itHandle == 'tradeadmin') {
      final Json orderA = await approvedOrder();
      final Json orderB = await approvedOrder();
      final Json draftOrder = await apiDraftOrder(admin, quantity: 1);
      final Json cancelledOrder = await apiDraftOrder(admin, quantity: 1);
      await apiAct(admin, 'sales-orders', '${cancelledOrder['id']}', 'cancel');
      final Json forIssue = await apiProforma(orderB);
      final Json forWithdraw = await apiProforma(orderB, issued: true);
      final Json forStale = await apiProforma(orderB);

      await log.step('SC-PF-002 list opens with its columns', () async {
        await openProformas();
        final List<String> missing = <String>[
          for (final String h in <String>[
            'Number', 'Customer', 'Date', 'Valid Until', 'Sales Order',
            'Status', 'Taxable Value', 'Tax', 'Grand Total',
          ])
            if (!screenHas(tester, h)) h,
        ];
        log.saw = 'missing $missing; header '
            '${rowOf(tester, 'Sales Order').take(12).join(' / ')}; ${buttons()}';
        if (missing.isNotEmpty) {
          throw StateError('not on screen: ${missing.join(', ')}');
        }
      });

      // -- Negative -----------------------------------------------------------
      await log.step('SC-PF-010 Raise with no order chosen', () async {
        await openProformas();
        final int before = await totalOf(admin, api);
        await tapNew(tester);
        await pumpUntil(
            tester, find.byKey(const ValueKey<String>('proforma-raise')),
            waitingFor: 'the proforma editor');
        final String chosen = boxesIn(tester, 'proforma-order');
        await tapKey(tester, 'proforma-raise');
        final String words = await watch(tester, seconds: 5, confirm: false);
        final int saved = await totalOf(admin, api) - before;
        log.saw = 'the editor opened with the order box reading "$chosen"; '
            'Raise pressed with nothing touched: saved=$saved, editor open='
            '${editorOpen()}, says "$words"';
        if (saved != 0) {
          throw StateError('N3: a proforma was raised for an order nobody '
              'chose (the box opened on "$chosen"); said "$words"');
        }
      });
      await closeOpenEditor(tester);

      await log.step('SC-PF-008 a Draft order is not offered', () async {
        final ({int status, String text}) r = await admin.attempt(
            'POST', '/api/v1/$api', <String, dynamic>{
          'sales_order_id': draftOrder['id'],
          'proforma_date': day(0),
        });
        await openProformas();
        await tapNew(tester);
        await pumpUntil(
            tester, find.byKey(const ValueKey<String>('proforma-raise')),
            waitingFor: 'the proforma editor');
        final Finder box = find.descendant(
            of: find.byKey(const ValueKey<String>('proforma-order')),
            matching: find.byType(EditableText));
        await tester.tap(box.first);
        await tester.enterText(box.first, docNumber(draftOrder));
        await pumpFor(tester, const Duration(seconds: 1));
        // The typed text itself is one match; an entry would be a second.
        final int shown =
            find.textContaining(docNumber(draftOrder)).evaluate().length;
        log.saw = 'picker entries naming the Draft order '
            '${docNumber(draftOrder)}: ${shown > 1 ? shown - 1 : 0}; over '
            'HTTP the raise answered ${r.status}: '
            '${r.text.length > 220 ? r.text.substring(0, 220) : r.text}';
        if (r.status < 400) throw StateError('a Draft order was stated');
        if (shown > 1) throw StateError('the Draft order is offered');
      });
      await closeOpenEditor(tester);

      await log.step('SC-PF-009 a cancelled order is refused in words',
          () async {
        final ({int status, String text}) r = await admin.attempt(
            'POST', '/api/v1/$api', <String, dynamic>{
          'sales_order_id': cancelledOrder['id'],
          'proforma_date': day(0),
        });
        log.saw = 'HTTP ${r.status}: '
            '${r.text.length > 240 ? r.text.substring(0, 240) : r.text} '
            '(the picker lists approved orders only, as in SC-PF-008)';
        if (r.status < 400) throw StateError('a cancelled order was stated');
      });

      await log.step('SC-PF-011 Valid until before today', () async {
        final ({int status, String text}) r = await admin.attempt(
            'POST', '/api/v1/$api', <String, dynamic>{
          'sales_order_id': orderA['id'],
          'proforma_date': day(0),
          'valid_until': day(-3),
        });
        await openProformas();
        await tapNew(tester);
        await pumpUntil(
            tester, find.byKey(const ValueKey<String>('proforma-raise')),
            waitingFor: 'the proforma editor');
        await tapKey(tester, 'proforma-valid-until');
        await pumpFor(tester, const Duration(seconds: 1));
        final bool picker =
            find.byType(DatePickerDialog).evaluate().isNotEmpty;
        if (picker) await tapDialogButton(tester, 'Cancel');
        log.saw = 'the box is a date picker (opened=$picker); over HTTP a '
            'proforma valid until three days ago answered ${r.status}: '
            '${r.text.length > 200 ? r.text.substring(0, 200) : r.text}';
        if (r.status < 400) {
          throw StateError('the server accepted a proforma whose prices '
              'stood until three days before its own date');
        }
      });
      await closeOpenEditor(tester);

      // -- Positive -----------------------------------------------------------
      await log.step('SC-PF-001 raise against an approved order; nothing '
          'posts', () async {
        final int jBefore = await journals();
        final int before = await totalOf(admin, api);
        await openProformas();
        await tapNew(tester);
        await pumpUntil(
            tester, find.byKey(const ValueKey<String>('proforma-raise')),
            waitingFor: 'the proforma editor');
        await chooseFiltered(tester, 'proforma-order', docNumber(orderA));
        await pumpFor(tester, const Duration(seconds: 1));
        await tapKey(tester, 'proforma-raise');
        final String words = await watch(tester, seconds: 5, confirm: false);
        final int saved = await totalOf(admin, api) - before;
        final Json? newest = await admin.newest(api);
        final int posted = await journals() - jBefore;
        log.saw = 'saved=$saved; says "$words"; newest '
            '${newest?['proforma_number']} for ${newest?['sales_order_number']} '
            'status ${newest?['status']}; journals posted $posted';
        if (saved != 1) throw StateError('saved $saved proformas');
        if ('${newest?['sales_order_id']}' != '${orderA['id']}') {
          throw StateError('the proforma states another order');
        }
        if ('${newest?['proforma_number']}'.startsWith('SI')) {
          throw StateError('the number is from the tax invoice series');
        }
        if (posted != 0) throw StateError('$posted journal(s) were posted');
      });
      await closeOpenEditor(tester);

      await log.step('SC-PF-003 Issue a Draft; still no journal', () async {
        final int jBefore = await journals();
        await openProformas();
        await selectRow(tester, '${forIssue['proforma_number']}');
        await tapButton(tester, 'Issue');
        final String words = await watch(tester, seconds: 5);
        final String st = await statusOf('${forIssue['id']}');
        final int posted = await journals() - jBefore;
        log.saw = 'status $st; says "$words"; journals posted $posted';
        if (st != 'ISSUED') throw StateError('status $st after Issue');
        if (posted != 0) throw StateError('$posted journal(s) were posted');
      });

      await log.step('SC-PF-004 Withdraw an Issued proforma; the order is '
          'untouched', () async {
        final String orderBefore =
            '${(await admin.one('sales-orders', '${orderB['id']}'))['status']}';
        await openProformas();
        await selectRow(tester, '${forWithdraw['proforma_number']}');
        final String words = await pressWithReason(tester, 'Withdraw',
            reason: 'customer changed the order');
        final String st = await statusOf('${forWithdraw['id']}');
        final String orderAfter =
            '${(await admin.one('sales-orders', '${orderB['id']}'))['status']}';
        log.saw = 'status $st; says "$words"; order $orderBefore -> '
            '$orderAfter';
        if (st != 'CANCELLED' && st != 'WITHDRAWN') {
          throw StateError('status $st after Withdraw');
        }
        if (orderBefore != orderAfter) throw StateError('the order moved');
      });

      await log.step('SC-PF-012 a Withdrawn proforma cannot be issued',
          () async {
        await openProformas();
        await selectRow(tester, '${forWithdraw['proforma_number']}');
        final Map<String, String> s = buttons();
        final ({int status, String text}) r = await admin.attempt(
            'POST', '/api/v1/$api/${forWithdraw['id']}/issue', null);
        log.saw = '$s; over HTTP Issue answered ${r.status}: '
            '${r.text.length > 160 ? r.text.substring(0, 160) : r.text}';
        if (s['Issue'] == 'enabled') {
          throw StateError('Issue is offered on a Withdrawn proforma');
        }
        if (r.status < 400) throw StateError('a withdrawn one was issued');
      });

      await log.step('SC-PF-004 Withdraw with no reason is refused in words',
          () async {
        await openProformas();
        await selectRow(tester, '${forIssue['proforma_number']}');
        await tapButton(tester, 'Withdraw');
        await pumpFor(tester, const Duration(seconds: 1));
        await tapDialogButton(tester, 'Withdraw');
        final String words = await watch(tester, seconds: 3, confirm: false);
        final bool open = find.byType(Dialog).evaluate().isNotEmpty;
        final String st = await statusOf('${forIssue['id']}');
        log.saw = 'dialog open=$open; status $st; says "$words"';
        if (st != 'ISSUED') throw StateError('withdrawn without a reason');
        if (!open) {
          throw StateError('the dialog closed with nothing said and nothing '
              'done (same family as SCRQ-23)');
        }
      });
      await closeOpenEditor(tester);

      await log.step('SC-PF-013 a proforma carries no receipt or journal '
          'link', () async {
        final Json p = await one('${forIssue['id']}');
        final List<String> links = <String>[
          for (final String k in p.keys)
            if (RegExp(r'journal|receivable|receipt|settlement').hasMatch(k)) k,
        ];
        await openProformas();
        await selectRow(tester, '${forIssue['proforma_number']}');
        final Map<String, String> pay = <String, String>{
          for (final String b in <String>[
            'Record a receipt', 'Receipt', 'Post', 'Journal', 'Approve'
          ])
            b: buttonState(tester, b),
        };
        log.saw = 'fields naming money or the ledger on the record: $links; '
            'buttons $pay';
        if (links.isNotEmpty) throw StateError('record carries $links');
        if (pay.values.any((String v) => v == 'enabled')) {
          throw StateError('a money or ledger button is offered: $pay');
        }
      });

      await log.step('SC-PF-007 Search narrows the grid', () async {
        await openProformas();
        final String wanted = '${forIssue['proforma_number']}';
        final String other = '${forWithdraw['proforma_number']}';
        final Finder box = find.ancestor(
            of: find.text('Search number or customer'),
            matching: find.byType(TextField));
        await pumpUntil(tester, box, waitingFor: 'the search box');
        await tester.enterText(box.first, wanted);
        await tester.testTextInput.receiveAction(TextInputAction.search);
        await pumpFor(tester, const Duration(seconds: 3));
        final bool has = find.text(wanted).evaluate().isNotEmpty;
        final bool hasOther = find.text(other).evaluate().isNotEmpty;
        final Finder typed = find.byWidgetPredicate((Widget w) =>
            w is EditableText && w.controller.text == wanted);
        await tester.enterText(typed.first, '');
        await tester.testTextInput.receiveAction(TextInputAction.search);
        await pumpFor(tester, const Duration(seconds: 3));
        final bool back = find.text(other).evaluate().isNotEmpty;
        log.saw = 'searched $wanted: shown=$has, $other shown=$hasOther; '
            'after clearing $other is back=$back';
        if (!has || hasOther) throw StateError('search did not narrow');
        if (!back) throw StateError('clearing left the grid narrowed');
      });

      log.skip('SC-PF-005', 'an approved order cannot be edited on screen, '
          'so the order cannot be changed under its proforma in one run');
      await log.step('SC-PF-006 Print and Send on a proforma', () async {
        await openProformas();
        await selectRow(tester, '${forIssue['proforma_number']}');
        final Map<String, String> s = <String, String>{
          for (final String b in <String>['Print', 'Send', 'Open', 'View'])
            b: buttonState(tester, b),
        };
        log.saw = '$s (Print not pressed: the system print preview never '
            'returns to a test run)';
        if (s['Print'] == 'absent' && s['Send'] == 'absent') {
          throw StateError('neither Print nor Send is offered on an Issued '
              'proforma: $s');
        }
      });

      // -- Multi-user ---------------------------------------------------------
      await log.step('SC-PF-018 Issue from a stale list after another user '
          'issued it', () async {
        await openProformas();
        await selectRow(tester, '${forStale['proforma_number']}');
        await apiAct(await asUser('qsmgr'), api, '${forStale['id']}', 'issue');
        await tapButton(tester, 'Issue');
        final String words = await watch(tester, seconds: 5);
        log.saw = 'says "$words"; status ${await statusOf('${forStale['id']}')}';
        if (words.isEmpty) throw StateError('N1: stale Issue said nothing');
      });
    } else {
      final ({int status, String text}) list =
          await me.attempt('GET', '/api/v1/$api?page_size=1', null);
      if (itHandle == 'qsmgr') {
        await log.step('SC-PF-014 SM: offered with New, Issue, Withdraw',
            () async {
          if (!offered) throw StateError('Proforma not offered to SM');
          final Json p = await apiProforma(await approvedOrder());
          await openProformas();
          await selectRow(tester, '${p['proforma_number']}');
          final Map<String, String> s = buttons();
          log.saw = 'offered=$offered, list ${list.status}; on a Draft: $s';
          final List<String> wrong = <String>[
            if (s['+ New'] != 'enabled' && s['New'] != 'enabled')
              'New not offered',
            for (final String b in <String>['Issue', 'Withdraw'])
              if (s[b] != 'enabled') '$b ${s[b]}',
          ];
          if (wrong.isNotEmpty) throw StateError(wrong.join(', '));
        });
      } else if (itHandle == 'qsexe') {
        await log.step('SC-PF-015 FS: Proforma not offered', () async {
          log.saw = 'offered=$offered; list answers ${list.status}';
          if (offered) throw StateError('Proforma is offered to Field Sales');
        });
        await log.step('SC-PF-017 FS cannot raise a proforma (HTTP)',
            () async {
          final Json order = await approvedOrder();
          final ({int status, String text}) r = await me.attempt(
              'POST', '/api/v1/$api', <String, dynamic>{
            'sales_order_id': order['id'],
            'proforma_date': day(0),
          });
          final String orderNow =
              '${(await admin.one('sales-orders', '${order['id']}'))['status']}';
          log.saw = 'raise answered ${r.status}; the order still reads '
              '$orderNow';
          if (r.status != 403) {
            throw StateError('expected 403, got ${r.status}: ${r.text}');
          }
        });
      } else if (itHandle == 'qro') {
        await log.step('SC-PF-016 RO: readable, no New, Issue, Withdraw',
            () async {
          if (!offered) throw StateError('Proforma not offered to RO');
          final Json p = await apiProforma(await approvedOrder());
          await openProformas();
          await selectRow(tester, '${p['proforma_number']}');
          final Map<String, String> s = buttons();
          log.saw = 'offered=$offered, list ${list.status}; $s';
          final List<String> on = <String>[
            for (final MapEntry<String, String> e in s.entries)
              if (e.value == 'enabled') e.key,
          ];
          if (on.isNotEmpty) throw StateError('Read Only is offered: $on');
        });
      }
    }
    log.finish();
  });
}
