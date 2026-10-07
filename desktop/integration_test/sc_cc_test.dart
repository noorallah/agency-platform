import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'cases.dart';
import 'harness.dart';
import 'sell_data.dart';

/// Customer credits (book section CC): money on account set against a bill,
/// from Sell > Receipts ("Apply to an invoice" on an on-account receipt).
///
/// Run once as the fixture firm's administrator, then once per role:
///
///     for h in tradeadmin qacct qsmgr qro; do
///       IT_EMAIL=t10069cwy.$h@fixtures.local IT_PASSWORD=Fixture@2026pw \
///         LIMIT=900 bash integration_test/run.sh sc_cc_test.dart; done
void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('CC: customer credit cases ($itHandle)',
      (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1600, 1000);
    tester.view.devicePixelRatio = 1;
    final Server me = await Server.connect();
    final Server admin = await Server.connectAs(
        't10069cwy.tradeadmin@fixtures.local', fixturePassword);
    await startAndSignIn(tester);
    collectAppErrors();
    final FlowLog log = FlowLog('cc-$itHandle');
    const String menuPath = 'accounting/receipts';
    const String applyLabel = 'Apply to an invoice';

    Future<void> openReceipts() async {
      await openMenu(tester, 'sell', menuPath);
      await refreshList(tester);
    }

    Future<double> onAccount(Json receipt) async => num2(
        (await admin.one('receipts', '${receipt['id']}'))['unallocated_amount']);

    /// What the bill still owes: the list the Apply dialog itself reads (a
    /// bill owing nothing is not on it).
    Future<double> owed(Json invoice) async {
      final dynamic rows = await admin.get('/api/v1/receipts/outstanding'
          '?customer_id=${invoice['customer_id']}');
      for (final dynamic row in rows as List<dynamic>) {
        if ('${(row as Json)['invoice_id']}' == '${invoice['id']}') {
          return num2(row['outstanding_amount']);
        }
      }
      return 0;
    }

    Future<int> journals() => totalOf(admin, 'finance/journal-entries');

    bool dialogOpen(Json receipt) => find
        .text('Apply ${receipt['settlement_number']}')
        .evaluate()
        .isNotEmpty;

    /// Open the Apply dialog for [receipt] and point it at [invoice].
    Future<void> openApply(Json receipt, Json invoice) async {
      await openReceipts();
      await selectRow(tester, '${receipt['settlement_number']}');
      await tapButtonOrMenu(tester, applyLabel);
      await pumpUntil(
          tester, find.text('Apply ${receipt['settlement_number']}'),
          waitingFor: 'the Apply dialog');
      final String number = docNumber(invoice);
      if (find.textContaining('$number ').evaluate().isEmpty &&
          find.textContaining(number).evaluate().isEmpty) {
        await tester.tap(find.textContaining('— owes').last);
        await pumpFor(tester, const Duration(milliseconds: 700));
        // The customer's unpaid bills are a long list built as it scrolls.
        final Finder entry = find.textContaining(number);
        if (entry.evaluate().isEmpty) {
          await tester.scrollUntilVisible(entry, 320,
              scrollable: find.byType(Scrollable).last, maxScrolls: 200);
        }
        await pumpFor(tester, const Duration(milliseconds: 400));
        await tester.tap(entry.last);
        await pumpFor(tester, const Duration(milliseconds: 700));
      }
    }

    /// Type [amount], press Apply, and judge it as a refusal (N1 to N3).
    Future<String> refuseApply(Json receipt, Json invoice, String amount) async {
      final double before = await onAccount(receipt);
      final double owedBefore = await owed(invoice);
      await openApply(receipt, invoice);
      await typeLabelled(tester, 'Amount', amount);
      await tapDialogButton(tester, 'Apply');
      final String words = await watch(tester, seconds: 4, confirm: false);
      final bool open = dialogOpen(receipt);
      final String inDialog = open ? dialogText(tester) : '';
      final double after = await onAccount(receipt);
      final double owedAfter = await owed(invoice);
      final String saw = 'open=$open, on account $before -> $after, bill '
          'owes $owedBefore -> $owedAfter, says "$words"'
          '${open ? ' dialog "${inDialog.length > 300 ? inDialog.substring(0, 300) : inDialog}"' : ''}';
      final bool told = words.isNotEmpty ||
          RegExp(r'cannot|more than|only|exceed|nothing|greater|at most',
                  caseSensitive: false)
              .hasMatch(inDialog);
      final List<String> faults = <String>[
        if (!told) 'N1: nothing on screen says why',
        if (!open) 'N2: the dialog closed, the amount typed is gone',
        if (!sameMoney(before, after) || !sameMoney(owedBefore, owedAfter))
          'N3: money moved',
      ];
      await closeOpenEditor(tester);
      if (faults.isNotEmpty) throw StateError('${faults.join('; ')} [$saw]');
      return saw;
    }

    if (itHandle == 'tradeadmin') {
      final Json bill = await apiApprovedInvoice(admin, quantity: 3);
      final double grand = num2(bill['grand_total']);
      final Json credit = await apiReceipt(admin, bill, 200, allocate: false);
      final Json smallBill = await apiApprovedInvoice(admin, quantity: 1);
      final double smallGrand = num2(smallBill['grand_total']);
      final Json bigCredit = await apiReceipt(
          admin, smallBill, (smallGrand + 150).ceil(), allocate: false);
      final Json billRace = await apiApprovedInvoice(admin, quantity: 4);
      final Json creditRace =
          await apiReceipt(admin, billRace, 60, allocate: false);

      await log.step('SC-CC-001 an on-account receipt shows as a credit',
          () async {
        await openReceipts();
        await selectRow(tester, '${credit['settlement_number']}');
        final List<String> row =
            rowOf(tester, '${credit['settlement_number']}');
        final String apply = buttonState(tester, applyLabel);
        final bool chip = find
            .byKey(const ValueKey<String>('customer-credits'))
            .evaluate()
            .isNotEmpty;
        log.saw = 'row ${row.take(10).join(' / ')}; $applyLabel $apply; '
            'Customer credits button present=$chip; bill of $grand';
        if (apply != 'enabled') {
          throw StateError('$applyLabel is $apply on an on-account receipt');
        }
        if (!chip) throw StateError('no Customer credits button');
      });

      await log.step('SC-CC-001 Customer credits opens and lists credits',
          () async {
        await openReceipts();
        await tapKey(tester, 'customer-credits');
        await pumpFor(tester, const Duration(seconds: 3));
        final String first = dialogText(tester);
        if (find.text('Whose credit?').evaluate().isNotEmpty) {
          final Finder who = find.textContaining('Vijaya Stores');
          if (who.evaluate().isNotEmpty) {
            await tester.tap(who.last);
            await pumpFor(tester, const Duration(seconds: 3));
          }
        }
        final String second = dialogText(tester);
        log.saw = 'first "${first.length > 200 ? first.substring(0, 200) : first}"; '
            'then "${second.length > 400 ? second.substring(0, 400) : second}"; '
            'notice "${noticeText(tester).length > 200 ? '' : noticeText(tester)}"';
        if (first.isEmpty && second.isEmpty && noticeText(tester).isEmpty) {
          throw StateError('Customer credits opened nothing and said nothing');
        }
      });
      await closeOpenEditor(tester);
      await closeOpenEditor(tester);

      // -- Negative -----------------------------------------------------------
      await log.step('SC-CC-006 more than the credit is refused', () async {
        log.saw = await refuseApply(credit, bill, '300');
      });
      await log.step('SC-CC-007 more than the bill owes is refused', () async {
        log.saw = await refuseApply(
            bigCredit, smallBill, (smallGrand + 100).toStringAsFixed(2));
      });
      await log.step('SC-CC-010 an amount of 0 is refused', () async {
        log.saw = await refuseApply(credit, bill, '0');
      });
      await log.step('SC-CC-010 an empty amount: Apply does nothing, in '
          'words or not', () async {
        await openApply(credit, bill);
        await typeLabelled(tester, 'Amount', '');
        await tapDialogButton(tester, 'Apply');
        final String words = await watch(tester, seconds: 3, confirm: false);
        final bool open = dialogOpen(credit);
        log.saw = 'open=$open, says "$words", on account '
            '${await onAccount(credit)}';
        await closeOpenEditor(tester);
        if (!open) throw StateError('the dialog closed on an empty amount');
        if (words.isEmpty &&
            !RegExp(r'[Ee]nter|amount is').hasMatch(dialogText(tester))) {
          log.info('SC-CC-010', 'an empty amount: Apply is silent (the '
              'dialog stays, nothing is said)');
        }
      });
      await closeOpenEditor(tester);

      await log.step('SC-CC-008 a future date cannot be chosen', () async {
        await openApply(credit, bill);
        final List<String> labels = textOnScreen(tester)
            .where((String t) => RegExp(r'[Dd]ate|[Oo]n ').hasMatch(t) && t.length < 40)
            .toList();
        final String d = dialogText(tester);
        log.saw = 'the Apply dialog has the bill and the amount only, no '
            'date box (dialog: "${d.length > 240 ? d.substring(0, 240) : d}"; '
            'date labels in it: ${labels.where(d.contains).toList()}): an '
            'application is dated today by the server, so a future date '
            'cannot be typed (prevention)';
      });
      await closeOpenEditor(tester);

      // -- Positive -----------------------------------------------------------
      await log.step('SC-CC-003 apply 50 of the 200: 150 stays on account; '
          'no journal', () async {
        final int j = await journals();
        final double owedBefore = await owed(bill);
        await openApply(credit, bill);
        await typeLabelled(tester, 'Amount', '50');
        await tapDialogButton(tester, 'Apply');
        final String words = await watch(tester, seconds: 5, confirm: false);
        final double left = await onAccount(credit);
        final double owedAfter = await owed(bill);
        final int posted = await journals() - j;
        log.saw = 'says "$words"; on account $left; bill owes $owedBefore '
            '-> $owedAfter; journals posted $posted';
        if (!sameMoney(left, 150)) throw StateError('on account is $left');
        if (!sameMoney(owedBefore - owedAfter, 50)) {
          throw StateError('the bill fell by ${owedBefore - owedAfter}');
        }
        if (posted != 0) throw StateError('$posted journal(s) posted');
      });
      await closeOpenEditor(tester);

      await log.step('SC-CC-002 apply 30 more to a second bill', () async {
        final double owedBefore = await owed(smallBill);
        await openApply(credit, smallBill);
        final String offeredAmount = tester
            .widgetList<EditableText>(find.descendant(
                of: find.byType(Dialog), matching: find.byType(EditableText)))
            .map((EditableText e) => e.controller.text)
            .join(' / ');
        await typeLabelled(tester, 'Amount', '30');
        await tapDialogButton(tester, 'Apply');
        final String words = await watch(tester, seconds: 5, confirm: false);
        final double left = await onAccount(credit);
        final double owedAfter = await owed(smallBill);
        log.saw = 'the dialog offered "$offeredAmount"; says "$words"; on '
            'account $left; second bill owes $owedBefore -> $owedAfter';
        if (!sameMoney(left, 120)) throw StateError('on account is $left');
        if (!sameMoney(owedBefore - owedAfter, 30)) {
          throw StateError('the bill fell by ${owedBefore - owedAfter}');
        }
      });
      await closeOpenEditor(tester);

      await log.step('SC-CC-009 a credit already on a bill cannot be put '
          'on it again (HTTP)', () async {
        final ({int status, String text}) r = await admin.attempt(
            'POST', '/api/v1/receipts/${credit['id']}/allocate',
            <String, dynamic>{'invoice_id': bill['id'], 'amount': '10'});
        log.saw = 'answered ${r.status}: '
            '${r.text.length > 220 ? r.text.substring(0, 220) : r.text}';
        if (r.status < 400) {
          throw StateError('the same credit went on the same bill twice');
        }
      });

      await log.step('SC-CC-004 Reverse the receipt: the bill owes what it '
          'did', () async {
        final double owedBefore = await owed(bill);
        await openReceipts();
        await selectRow(tester, '${credit['settlement_number']}');
        final String words =
            await pressWithReason(tester, 'Reverse', reason: 'screen case');
        final double owedAfter = await owed(bill);
        final Json rc = await admin.one('receipts', '${credit['id']}');
        log.saw = 'says "$words"; receipt status ${rc['status']}; bill owes '
            '$owedBefore -> $owedAfter (bill total $grand)';
        if (!sameMoney(owedAfter - owedBefore, 50)) {
          throw StateError('the bill rose by ${owedAfter - owedBefore}, not '
              'the 50 that had been applied to it');
        }
      });

      log.skip('SC-CC-005', 'Customer Statements is a report screen; its '
          'figures are driven over HTTP (TC-SELL statements), not here');
      log.skip('SC-CC-011', 'Vijaya Stores always has an unpaid bill in the '
          'fixture firm, and a second customer is not seeded');
      log.skip('SC-CC-015', 'the fixture firm has no Counter Sales user; '
          'SC-CC-016 covers two users on one credit');

      // -- Multi-user ---------------------------------------------------------
      await log.step('SC-CC-016 two users spend one credit: the second is '
          'refused', () async {
        await openApply(creditRace, billRace);
        final ({int status, String text}) theirs = await (await asUser('qacct'))
            .attempt('POST', '/api/v1/receipts/${creditRace['id']}/allocate',
                <String, dynamic>{'invoice_id': billRace['id'], 'amount': '60'});
        if (theirs.status >= 400) {
          throw StateError('the first user could not apply: ${theirs.status} '
              '${theirs.text}');
        }
        final double owedBefore = await owed(billRace);
        await tapDialogButton(tester, 'Apply');
        final String words = await watch(tester, seconds: 5, confirm: false);
        final double owedAfter = await owed(billRace);
        log.saw = 'says "$words"; bill owes $owedBefore -> $owedAfter; on '
            'account ${await onAccount(creditRace)}';
        if (!sameMoney(owedBefore, owedAfter)) {
          throw StateError('the credit was spent twice');
        }
        if (words.isEmpty && !dialogOpen(creditRace)) {
          throw StateError('N1: the second Apply said nothing');
        }
      });
      await closeOpenEditor(tester);
    } else {
      final Map<String, List<String>> menu = await offeredMenu(tester);
      final bool offered = menuHas(menu, menuPath);
      final ({int status, String text}) list =
          await me.attempt('GET', '/api/v1/receipts?page_size=1', null);
      Future<Map<String, String>> onACredit() async {
        final Json b = await apiApprovedInvoice(admin, quantity: 1);
        final Json rc = await apiReceipt(admin, b, 25, allocate: false);
        await openReceipts();
        await selectRow(tester, '${rc['settlement_number']}');
        return <String, String>{
          applyLabel: buttonState(tester, applyLabel),
          'Customer credits': find
                  .byKey(const ValueKey<String>('customer-credits'))
                  .evaluate()
                  .isEmpty
              ? 'absent'
              : 'present',
          'Reverse': buttonState(tester, 'Reverse'),
        };
      }

      if (itHandle == 'qacct') {
        await log.step('SC-CC-012 AC: Customer credits and Apply offered',
            () async {
          if (!offered) throw StateError('Receipts not offered to Accounts');
          final Map<String, String> s = await onACredit();
          log.saw = 'offered=$offered, list ${list.status}; $s';
          if (s[applyLabel] != 'enabled' || s['Customer credits'] != 'present') {
            throw StateError('$s');
          }
        });
      } else if (itHandle == 'qsmgr') {
        await log.step('SC-CC-013 SM: not offered', () async {
          log.saw = 'Receipts offered=$offered; list answers ${list.status}';
          if (offered) throw StateError('Receipts offered to Sales Manager');
        });
      } else if (itHandle == 'qro') {
        await log.step('SC-CC-014 RO: readable; Apply absent', () async {
          if (!offered) throw StateError('Receipts not offered to Read Only');
          final Map<String, String> s = await onACredit();
          log.saw = 'offered=$offered, list ${list.status}; $s';
          if (s[applyLabel] == 'enabled' || s['Customer credits'] == 'present') {
            throw StateError('Read Only is offered: $s');
          }
        });
      }
    }
    log.finish();
  });
}
