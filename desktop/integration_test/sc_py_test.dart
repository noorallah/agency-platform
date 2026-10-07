import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'buy_data.dart';
import 'cases.dart';
import 'harness.dart';
import 'sell_data.dart';

/// Payments (book section PY). Run as tradeadmin, then qacct (AC), qpexe
/// (PU), qpmgr (PM), qro. The cashier (CS) user does not exist in the fixture
/// firm.
void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('PY: payment cases ($itHandle)', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1600, 1000);
    tester.view.devicePixelRatio = 1;
    final Server me = await Server.connect();
    final Server admin = await Server.connectAs(
        't10069cwy.tradeadmin@fixtures.local', fixturePassword);
    await startAndSignIn(tester);
    collectAppErrors();
    final FlowLog log = FlowLog('py-$itHandle');
    const String menuPath = 'accounting/payments';

    Future<void> openPayments() async {
      await openMenu(tester, 'buy', menuPath);
      await refreshList(tester);
    }

    Future<void> openDialog() async {
      await openPayments();
      await tapNew(tester);
      await pumpUntil(
          tester, find.byKey(const ValueKey<String>('settlement-mode')),
          waitingFor: 'the payment dialog');
    }

    Future<void> pickSupplier() async {
      await typeLabelled(tester, 'Paid to', 'Principal');
      await pumpFor(tester, const Duration(seconds: 1));
      await tester.tap(find.textContaining('Principal supplier').last);
      await pumpFor(tester, const Duration(seconds: 2));
    }

    Future<void> pressRecord() async {
      await tapButtonStarting(tester, 'Record ');
      await pumpFor(tester, const Duration(seconds: 1));
    }

    Map<String, String> buttons(List<String> names) => <String, String>{
          for (final String b in names) b: buttonState(tester, b),
        };

    if (itHandle == 'tradeadmin') {
      final Json bill = await apiApprovedBill(admin);
      final Json billRev = await apiApprovedBill(admin);
      final Json payRev = await apiPayment(admin, billRev,
          num2(billRev['grand_total']));
      final Json billStale = await apiApprovedBill(admin);
      final Json payStale = await apiPayment(admin, billStale,
          num2(billStale['grand_total']));
      final Json billDone = await apiApprovedBill(admin);
      final Json payDone = await apiPayment(admin, billDone, 30);
      await admin.write('POST', '/api/v1/payments/${payDone['id']}/reverse',
          <String, dynamic>{'reason': 'screen case fixture'});

      await log.step('SC-PY-001 list opens with chips and columns', () async {
        await openPayments();
        final List<String> missing = <String>[
          for (final String h in <String>[
            'Number',
            'Supplier',
            'Date',
            'Method',
            'Status',
            'Amount',
            'Supplier credits',
            'Supplier refunds'
          ])
            if (!screenHas(tester, h)) h,
        ];
        log.info('SC-PY-001', 'short texts: ${textOnScreen(tester).where((String t) => t.length < 26).take(70).join(' | ')}');
        if (missing.isNotEmpty) {
          throw StateError('not on screen: ${missing.join(', ')}');
        }
        log.saw = 'columns and chips present';
      });

      // -- Negative -------------------------------------------------------
      for (final String amount in <String>['', '0', '-5']) {
        await log.step('SC-PY-011 amount "$amount" is refused', () async {
          await openDialog();
          await pickSupplier();
          log.saw = await expectRefusal(tester, me,
              collection: 'payments',
              openKey: 'settlement-mode',
              typed: amount.isEmpty ? null : amount,
              press: () async {
                if (amount.isNotEmpty) {
                  await typeLabelled(tester, 'Amount', amount);
                }
                await pressRecord();
              });
        });
        await closeOpenEditor(tester);
      }

      await log.step('SC-PY-015 no supplier chosen: Record is refused',
          () async {
        await openDialog();
        log.saw = await expectRefusal(tester, me,
            collection: 'payments',
            openKey: 'settlement-mode',
            typed: '25',
            press: () async {
              await typeLabelled(tester, 'Amount', '25');
              await pressRecord();
            });
      });
      await closeOpenEditor(tester);

      await log.step('SC-PY-019 closing a typed dialog asks', () async {
        await openDialog();
        await pickSupplier();
        await typeLabelled(tester, 'Amount', '77');
        final Finder cancel = find.text('Cancel');
        if (cancel.evaluate().isNotEmpty) {
          await tester.tap(cancel.last);
        } else {
          await tester.tap(find.byIcon(Icons.close).first);
        }
        await pumpFor(tester, const Duration(seconds: 1));
        final bool gone = find
            .byKey(const ValueKey<String>('settlement-mode'))
            .evaluate()
            .isEmpty;
        final bool asks = find.byType(AlertDialog).evaluate().isNotEmpty;
        log.saw = 'dialog closed=$gone, asked=$asks';
        if (gone && !asks) {
          throw StateError('the dialog closed holding typing without asking '
              '(same family as known SCRQ-21/29)');
        }
      });
      await closeOpenEditor(tester);

      await log.step('SC-PY-018 neither Edit nor Delete on a payment',
          () async {
        await openPayments();
        await selectRow(tester, '${payStale['settlement_number']}');
        final String e = buttonState(tester, 'Edit');
        final String d = buttonState(tester, 'Delete');
        log.saw = 'Edit $e, Delete $d';
        if (e == 'enabled' || d == 'enabled') throw StateError('$e/$d');
      });

      await log.step('SC-PY-017 a Reversed payment cannot be reversed again',
          () async {
        await openPayments();
        await selectRow(tester, '${payDone['settlement_number']}');
        final String r = buttonState(tester, 'Reverse');
        log.saw = 'Reverse is $r on a reversed payment';
        if (r == 'enabled') throw StateError('Reverse offered twice');
      });

      await log.step('SC-PY-012 an amount larger than anything owed, nothing '
          'applied', () async {
        final int before = await totalOf(me, 'payments');
        await openDialog();
        await pickSupplier();
        await typeLabelled(tester, 'Amount', '1234');
        await pumpFor(tester, const Duration(seconds: 1));
        final bool notice = screenHas(tester, 'will be held as an advance');
        await pressRecord();
        await pumpFor(tester, const Duration(seconds: 2));
        final int after = await totalOf(me, 'payments');
        final Json? p = await me.newest('payments');
        log.saw = 'advance notice shown=$notice; saved ${after - before}; '
            'newest unallocated ${p?['unallocated_amount']}';
        if (after > before && p != null) {
          // Undo what the case made.
          await admin.write('POST', '/api/v1/payments/${p['id']}/reverse',
              <String, dynamic>{'reason': 'screen case clean-up'});
        }
        log.info('SC-PY-012', 'the Payments screen accepts an amount with '
            'nothing applied as an advance to the supplier: '
            '${after > before}');
      });

      // -- Positive -------------------------------------------------------
      await log.step('SC-PY-003 pay 400 only against the oldest bills',
          () async {
        final int before = await totalOf(me, 'payments');
        await openDialog();
        await pickSupplier();
        await typeLabelled(tester, 'Amount', '400');
        await tapButton(tester, 'Oldest first');
        await pressRecord();
        await pumpFor(tester, const Duration(seconds: 2));
        final Json? p = await me.newest('payments');
        final Json full = await admin.one('payments', '${p!['id']}');
        final List<dynamic> al =
            (full['allocations'] as List<dynamic>?) ?? <dynamic>[];
        final double sum = al.fold<double>(
            0, (double s, dynamic a) => s + num2((a as Json)['amount']));
        log.saw = 'saved ${await totalOf(me, 'payments') - before}; amount '
            '${full['amount']}; allocated $sum over ${al.length} bills';
        if (!sameMoney(num2(full['amount']), 400)) {
          throw StateError('payment is ${full['amount']}, typed 400');
        }
        if (!sameMoney(sum + num2(full['unallocated_amount']), 400)) {
          throw StateError('allocations and advance do not add to 400');
        }
      });

      await log.step('SC-PY-008 Reverse puts the bill back', () async {
        await openPayments();
        await selectRow(tester, '${payRev['settlement_number']}');
        final String said = await pressWithReason(tester, 'Reverse');
        final Json p = await admin.one('payments', '${payRev['id']}');
        final Json b = await admin.one('purchase-invoices', '${billRev['id']}');
        log.saw = 'payment ${p['status']}; bill ${b['status']} outstanding '
            '${b['outstanding_amount'] ?? b['balance_due']}; screen says '
            '"$said"';
        if ('${p['status']}' != 'REVERSED') {
          throw StateError('status ${p['status']}');
        }
      });

      // -- Multi-user -----------------------------------------------------
      await log.step('SC-PY-027 stale Reverse after another user reversed',
          () async {
        await openPayments();
        await selectRow(tester, '${payStale['settlement_number']}');
        await apiAct(await asUser('qacct'), 'payments', '${payStale['id']}',
            'reverse', <String, dynamic>{'reason': 'second session'});
        final String said = await pressWithReason(tester, 'Reverse');
        final Json p = await admin.one('payments', '${payStale['id']}');
        log.saw = 'payment ${p['status']}; screen says "$said"';
        if (said.isEmpty) throw StateError('N1: the stale Reverse said nothing');
      });

      await log.step('SC-PY-026 a second full payment on a paid bill (HTTP)',
          () async {
        final double g = num2(bill['grand_total']);
        await apiPayment(await asUser('qacct'), bill, g);
        final ({int status, String text}) r = await admin.attempt(
            'POST', '/api/v1/payments', <String, dynamic>{
          'party_id': bill['vendor_id'],
          'settlement_date': DateTime.now().toIso8601String().substring(0, 10),
          'amount': '$g',
          'method': 'CASH',
          'allocations': <Json>[
            <String, dynamic>{'invoice_id': bill['id'], 'amount': '$g'},
          ],
        });
        final Json after = await admin.one('purchase-invoices', '${bill['id']}');
        log.saw = 'second payment answered ${r.status}: '
            '${r.text.length > 200 ? r.text.substring(0, 200) : r.text}; '
            'bill outstanding ${after['outstanding_amount'] ?? after['balance_due']}';
        final double out =
            num2(after['outstanding_amount'] ?? after['balance_due'] ?? 0);
        if (out < 0) throw StateError('bill went below zero: $out');
        if (r.status < 400) {
          throw StateError('a second allocation to a paid bill was accepted');
        }
      });

      log.skip('SC-PY-004', 'TDS section list not driven; no TDS master in '
          'the fixture');
      log.skip('SC-PY-005', 'cheque printing is a native print');
      log.skip('SC-PY-006', 'no foreign-currency bill in the fixture');
      log.skip('SC-PY-007', 'Payment Runs screen not reached');
      log.skip('SC-PY-009', 'Print is native; Send and Files as in Receipts');
      log.skip('SC-PY-010', 'Post-dated Cheques screen not reached');
      log.skip('SC-PY-013', 'future date not driven (see SC-RC-014)');
      log.skip('SC-PY-014', 'no closed period in the fixture firm');
      log.skip('SC-PY-016', 'no foreign bill in the fixture');
      log.skip('SC-PY-025', 'covered by the PB file multi-user cases');
    } else {
      final Map<String, List<String>> menu = await offeredMenu(tester);
      // ignore: avoid_print
      print('FLOW: MENU [$itHandle] ${menu.entries.map((MapEntry<String, List<String>> e) => '${e.key}=${e.value.join(',')}').join('; ')}');
      final bool offered = menuHas(menu, menuPath);
      final ({int status, String text}) api =
          await me.attempt('GET', '/api/v1/payments?page_size=1', null);
      if (itHandle == 'qacct' || itHandle == 'qro') {
        final Json b = await apiApprovedBill(admin);
        final Json p = await apiPayment(admin, b, 10);
        final String id = itHandle == 'qacct' ? 'SC-PY-020' : 'SC-PY-024';
        await log.step('$id ${itHandle == 'qacct' ? 'AC' : 'RO'}: Payments '
            'offered; buttons', () async {
          log.saw = 'offered: $offered; list ${api.status}';
          if (!offered) throw StateError('not offered');
          await openPayments();
          await selectRow(tester, '${p['settlement_number']}');
          final Map<String, String> s = buttons(<String>['+ New', 'Reverse']);
          log.saw = '${log.saw}; $s; Payment Runs offered: '
              '${menuHas(menu, 'accounting/payment-runs')}';
          if (itHandle == 'qacct' &&
              (s['+ New'] != 'enabled' || s['Reverse'] != 'enabled')) {
            throw StateError('Accounts is missing Record or Reverse: $s');
          }
          if (itHandle == 'qro' && s.values.any((String v) => v == 'enabled')) {
            throw StateError('Read Only is offered $s');
          }
        });
      } else {
        final String id = itHandle == 'qpexe' ? 'SC-PY-021 PU' : 'SC-PY-022 PM';
        await log.step('$id: Payments not offered', () async {
          log.saw = 'offered: $offered; list ${api.status}';
          if (offered != (api.status == 200)) {
            throw StateError('menu ($offered) and server (${api.status}) '
                'disagree');
          }
          if (offered) throw StateError('Payments is offered');
        });
      }
    }
    log.finish();
  });
}
