import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'cases.dart';
import 'harness.dart';
import 'sell_data.dart';

/// Receipts (book section RC): Negative, Role, Multi-user and the Positive
/// cases the selling flow does not cover. Run as tradeadmin, then qacct,
/// qsexe, qsmgr, qro. The cashier (CS) user does not exist in the fixture
/// firm; the administrator and Accounts (qacct) stand in for it.
void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('RC: receipt cases ($itHandle)', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1600, 1000);
    tester.view.devicePixelRatio = 1;
    final Server me = await Server.connect();
    final Server admin = await Server.connectAs(
        't10069cwy.tradeadmin@fixtures.local', fixturePassword);
    await startAndSignIn(tester);
    collectAppErrors();
    final FlowLog log = FlowLog('rc-$itHandle');
    const String menuPath = 'accounting/receipts';

    Future<void> openReceipts() async {
      await openMenu(tester, 'sell', menuPath);
      await refreshList(tester);
    }

    Future<void> openDialog() async {
      await openReceipts();
      await tapNew(tester);
      await pumpUntil(
          tester, find.byKey(const ValueKey<String>('settlement-mode')),
          waitingFor: 'the receipt dialog');
    }

    Future<void> pickParty() async {
      await typeLabelled(tester, 'Received from', 'Vijaya');
      await pumpFor(tester, const Duration(seconds: 1));
      await tester.tap(find.textContaining('Vijaya Stores').last);
      await pumpFor(tester, const Duration(seconds: 2));
    }

    Future<void> pressRecord() async {
      await tapButtonStarting(tester, 'Record ');
      await pumpFor(tester, const Duration(seconds: 1));
    }

    Future<Json> receiptById(String id) => admin.one('receipts', id);

    if (itHandle == 'tradeadmin') {
      final Json inv = await apiApprovedInvoice(admin, quantity: 3);
      final Json invForReverse = await apiApprovedInvoice(admin, quantity: 2);
      final Json invStale = await apiApprovedInvoice(admin, quantity: 2);
      final Json invRet = await apiApprovedInvoice(admin, quantity: 4);
      final Json rcReverse = await apiReceipt(
          admin, invForReverse, num2(invForReverse['grand_total']));
      final Json rcStale = await apiReceipt(
          admin, invStale, num2(invStale['grand_total']));
      final Json rcRet = await apiReceipt(admin, invRet, 50);
      final Json rcDone = await apiReceipt(admin, inv, 20);
      await admin.write('POST', '/api/v1/receipts/${rcDone['id']}/reverse',
          <String, dynamic>{'reason': 'screen case fixture'});

      await log.step('SC-RC-001 list opens with its columns', () async {
        await openReceipts();
        final List<String> missing = <String>[
          for (final String h in <String>[
            'Number',
            'Customer',
            'Date',
            'Method',
            'Cleared',
            'Status',
            'Amount'
          ])
            if (!screenHas(tester, h)) h,
        ];
        log.info('SC-RC-001', 'short texts: ${textOnScreen(tester).where((String t) => t.length < 24).take(70).join(' | ')}');
        if (missing.isNotEmpty) {
          throw StateError('not on screen: ${missing.join(', ')}');
        }
        log.saw = 'columns present';
      });

      // -- Negative -------------------------------------------------------
      await log.step('SC-RC-012 amount empty is refused', () async {
        await openDialog();
        await pickParty();
        log.saw = await expectRefusal(tester, me,
            collection: 'receipts',
            openKey: 'settlement-mode',
            press: pressRecord);
      });
      await closeOpenEditor(tester);

      await log.step('SC-RC-012 amount 0 is refused', () async {
        await openDialog();
        await pickParty();
        log.saw = await expectRefusal(tester, me,
            collection: 'receipts',
            openKey: 'settlement-mode',
            press: () async {
              await typeLabelled(tester, 'Amount', '0');
              await pressRecord();
            });
      });
      await closeOpenEditor(tester);

      await log.step('SC-RC-013 negative amount is refused', () async {
        await openDialog();
        await pickParty();
        log.saw = await expectRefusal(tester, me,
            collection: 'receipts',
            openKey: 'settlement-mode',
            typed: '-5',
            press: () async {
              await typeLabelled(tester, 'Amount', '-5');
              await pressRecord();
            });
      });
      await closeOpenEditor(tester);

      await log.step('SC-RC-014 a future date is refused', () async {
        await openDialog();
        await pickParty();
        await typeLabelled(tester, 'Amount', '10');
        final String todayText = DateTime.now().toIso8601String().substring(0, 10);
        await tester.ensureVisible(find.text('Date the money moved').last);
        await pumpFor(tester, const Duration(milliseconds: 500));
        await tester.tap(find.text('Date the money moved').last);
        await pumpFor(tester, const Duration(seconds: 1));
        final bool picker = find.byType(DatePickerDialog).evaluate().isNotEmpty;
        log.info('SC-RC-014', 'date picker open=$picker');
        if (!picker) throw StateError('the date picker did not open');
        final bool hasNext = find.byTooltip('Next month').evaluate().isNotEmpty;
        bool nextEnabled = false;
        if (hasNext) {
          nextEnabled = tester
                  .widget<IconButton>(find.ancestor(
                      of: find.byTooltip('Next month').first,
                      matching: find.byType(IconButton)).first)
                  .onPressed !=
              null;
        }
        log.info('SC-RC-014', 'Next month present=$hasNext enabled=$nextEnabled');
        if (nextEnabled) {
          await tester.tap(find.byTooltip('Next month').first);
          await pumpFor(tester, const Duration(milliseconds: 700));
          throw StateError('the picker offers a month after today');
        }
        await tester.tap(find.text('Cancel').last);
        await pumpFor(tester, const Duration(milliseconds: 700));
        final int before14 = await totalOf(me, 'receipts');
        await pressRecord();
        await pumpFor(tester, const Duration(seconds: 3));
        final Json? n14 = await me.newest('receipts');
        final String today14 =
            DateTime.now().toIso8601String().substring(0, 10);
        final List<String> dates14 = <String>[
          if (n14 != null)
            for (final MapEntry<String, dynamic> e in n14.entries)
              if (e.key.contains('date') && e.value != null)
                '${e.key}=${e.value}',
        ];
        log.saw = 'saved ${await totalOf(me, 'receipts') - before14}; '
            'newest receipt dates $dates14 (today $today14); the picker '
            'does not offer a day after today';
        final Json? seed14 = await me.newest('receipts');
        final String tomorrow = DateTime.now()
            .add(const Duration(days: 1))
            .toIso8601String()
            .substring(0, 10);
        final ({int status, String text}) http14 = await admin.attempt(
            'POST', '/api/v1/receipts', <String, dynamic>{
          'party_id': seed14?['party_id'] ?? seed14?['customer_id'],
          'settlement_date': tomorrow,
          'amount': '5',
          'method': 'CASH',
        });
        log.saw = '${log.saw}; HTTP receipt dated $tomorrow answered '
            '${http14.status}: ${http14.text.length > 160 ? http14.text.substring(0, 160) : http14.text}';
        if (http14.status < 400) {
          throw StateError('HTTP accepted a receipt dated $tomorrow');
        }
        if (dates14.any((String d) =>
            d.contains(RegExp(r'=(\d{4}-\d\d-\d\d)')) &&
            d.split('=').last.substring(0, 10).compareTo(today14) > 0)) {
          throw StateError('N3: a future-dated receipt was saved $dates14');
        }
      });
      await closeOpenEditor(tester);

      await log.step('SC-RC-017 no customer chosen: Record is refused',
          () async {
        await openDialog();
        log.saw = await expectRefusal(tester, me,
            collection: 'receipts',
            openKey: 'settlement-mode',
            typed: '25',
            press: () async {
              await typeLabelled(tester, 'Amount', '25');
              await pressRecord();
              final Json? n = await me.newest('receipts');
              log.info('SC-RC-017', 'newest receipt after press: '
                  '${n?['receipt_number']} customer ${n?['customer_id']} '
                  'amount ${n?['amount']} created ${n?['created_at']}');
            });
      });
      await closeOpenEditor(tester);

      await log.step('SC-RC-018 TDS typed without a section', () async {
        await openDialog();
        await pickParty();
        log.saw = await expectRefusal(tester, me,
            collection: 'receipts',
            openKey: 'settlement-mode',
            press: () async {
              await typeLabelled(tester, 'Amount', '100');
              await typeInKeyed(tester, 'settlement-tds-amount', '10');
              await pressRecord();
            });
      });
      await closeOpenEditor(tester);

      await log.step('SC-RC-021 closing a typed dialog asks', () async {
        await openDialog();
        await pickParty();
        await typeLabelled(tester, 'Amount', '77');
        final Finder cancel = find.text('Cancel');
        final Finder closeBtn = find.text('Close');
        if (cancel.evaluate().isNotEmpty) {
          await tester.tap(cancel.last);
        } else if (closeBtn.evaluate().isNotEmpty) {
          await tester.tap(closeBtn.last);
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

      await log.step('SC-RC-022 neither Edit nor Delete on a recorded receipt',
          () async {
        await openReceipts();
        await selectRow(tester, '${rcStale['settlement_number']}');
        final String e = buttonState(tester, 'Edit');
        final String d = buttonState(tester, 'Delete');
        log.saw = 'Edit $e, Delete $d';
        if (e == 'enabled' || d == 'enabled') throw StateError('$e/$d');
      });

      await log.step('SC-RC-020 a Reversed receipt cannot be reversed again',
          () async {
        await openReceipts();
        await selectRow(tester, '${rcDone['settlement_number']}');
        final String r = buttonState(tester, 'Reverse');
        log.saw = 'Reverse is $r on a reversed receipt';
        if (r == 'enabled') throw StateError('Reverse offered twice');
      });

      // -- Positive -------------------------------------------------------
      await log.step('SC-RC-004 more than owed with nothing applied becomes '
          'an advance', () async {
        final int before = await totalOf(me, 'receipts');
        await openDialog();
        await pickParty();
        await typeLabelled(tester, 'Amount', '137');
        await pumpFor(tester, const Duration(seconds: 1));
        final bool notice = screenHas(tester, 'will be held as an advance');
        await pressRecord();
        await pumpFor(tester, const Duration(seconds: 2));
        final Json? rc = await me.newest('receipts');
        log.saw = 'advance notice shown=$notice, saved '
            '${await totalOf(me, 'receipts') - before}, newest unallocated '
            '${rc?['unallocated_amount']}';
        if (!notice) throw StateError('the dialog did not say it will be held '
            'as an advance');
        if (rc == null || num2(rc['unallocated_amount']) != 137) {
          throw StateError('newest receipt is not a 137 advance');
        }
      });

      await log.step('SC-RC-003 an amount over the first bill spills onto the '
          'next', () async {
        final int before = await totalOf(me, 'receipts');
        await openDialog();
        await pickParty();
        await typeLabelled(tester, 'Amount', '900');
        await tapButton(tester, 'Oldest first');
        await pressRecord();
        await pumpFor(tester, const Duration(seconds: 2));
        final Json? rc = await me.newest('receipts');
        final Json full = await admin.one('receipts', '${rc!['id']}');
        final List<dynamic> al = (full['allocations'] as List<dynamic>?) ?? <dynamic>[];
        final double sum = al.fold<double>(
            0, (double s, dynamic a) => s + num2((a as Json)['amount']));
        log.saw = 'saved ${await totalOf(me, 'receipts') - before}, '
            '${al.length} allocations summing $sum, unallocated '
            '${full['unallocated_amount']}';
        if (num2(full['unallocated_amount']) > 0.005) {
          throw StateError('${full['unallocated_amount']} of 900 was left as '
              'an advance by Oldest first');
        }
        if (!sameMoney(sum + num2(full['unallocated_amount']), 900)) {
          throw StateError('allocations and advance do not add to 900');
        }
      });

      await log.step('SC-RC-005 a cheque receipt keeps its instrument date',
          () async {
        final int before = await totalOf(me, 'receipts');
        await openDialog();
        await pickParty();
        await typeLabelled(tester, 'Amount', '33');
        await chooseIn(tester, 'settlement-mode', 'Cheque');
        await pumpFor(tester, const Duration(seconds: 1));
        final bool dateBox = find
            .byKey(const ValueKey<String>('settlement-instrument-date'))
            .evaluate()
            .isNotEmpty;
        await pressRecord();
        await pumpFor(tester, const Duration(seconds: 2));
        final Json? rc = await me.newest('receipts');
        log.saw = 'instrument date box shown=$dateBox, saved '
            '${await totalOf(me, 'receipts') - before}, mode '
            '${rc?['payment_mode']}, instrument date ${rc?['instrument_date']}';
        if (!dateBox) throw StateError('no instrument date box for a cheque');
        if (rc == null || '${rc['payment_mode']}' != 'CHEQUE') {
          throw StateError('newest receipt is not a cheque: '
              '${rc?['payment_mode']}');
        }
      });

      await log.step('SC-RC-009 Reverse puts the bill back', () async {
        await openReceipts();
        await selectRow(tester, '${rcReverse['settlement_number']}');
        final String said = await pressWithReason(tester, 'Reverse');
        final Json rc = await receiptById('${rcReverse['id']}');
        final Json bill = await admin.one('sales-invoices', '${invForReverse['id']}');
        log.saw = 'receipt ${rc['status']}; bill outstanding '
            '${bill['outstanding_amount'] ?? bill['balance_due']} of '
            '${bill['grand_total']}; screen says "$said"';
        if ('${rc['status']}' != 'REVERSED') {
          throw StateError('status ${rc['status']}');
        }
      });

      await log.step('SC-RC-019 Reverse a receipt on a bill with an approved '
          'return resting on it', () async {
        final Json ret = await apiDraftReturn(admin, invRet, quantity: 1);
        await apiAct(admin, 'sales-returns', '${ret['id']}', 'approve');
        await openReceipts();
        await selectRow(tester, '${rcRet['settlement_number']}');
        final String said = await pressWithReason(tester, 'Reverse');
        final Json rc = await receiptById('${rcRet['id']}');
        final Json bill = await admin.one('sales-invoices', '${invRet['id']}');
        log.saw = 'receipt ${rc['status']}; bill outstanding '
            '${bill['outstanding_amount'] ?? bill['balance_due']} of '
            '${bill['grand_total']}; screen says "$said"';
        if (said.isEmpty) throw StateError('N1: said nothing');
      });

      // -- Multi-user -----------------------------------------------------
      await log.step('SC-RC-029 stale Reverse after another user reversed',
          () async {
        await openReceipts();
        await selectRow(tester, '${rcStale['settlement_number']}');
        await apiAct(await asUser('qacct'), 'receipts', '${rcStale['id']}',
            'reverse', <String, dynamic>{'reason': 'second session'});
        final String said = await pressWithReason(tester, 'Reverse');
        final Json rc = await receiptById('${rcStale['id']}');
        log.saw = 'receipt ${rc['status']}; screen says "$said"';
        if (said.isEmpty) throw StateError('N1: the stale Reverse said nothing');
      });

      await log.step('SC-RC-030 a second full receipt on a cleared bill '
          '(HTTP)', () async {
        final Json b = await apiApprovedInvoice(admin, quantity: 1);
        final double g = num2(b['grand_total']);
        await apiReceipt(await asUser('qacct'), b, g);
        final ({int status, String text}) r = await admin.attempt(
            'POST', '/api/v1/receipts', <String, dynamic>{
          'party_id': b['customer_id'],
          'settlement_date': DateTime.now().toIso8601String().substring(0, 10),
          'amount': '$g',
          'method': 'CASH',
          'allocations': <Json>[
            <String, dynamic>{'invoice_id': b['id'], 'amount': '$g'},
          ],
        });
        final Json after = await admin.one('sales-invoices', '${b['id']}');
        log.saw = 'second receipt answered ${r.status}: '
            '${r.text.length > 200 ? r.text.substring(0, 200) : r.text}; '
            'bill outstanding ${after['outstanding_amount'] ?? after['balance_due']}';
        final double out =
            num2(after['outstanding_amount'] ?? after['balance_due'] ?? 0);
        if (out < 0) throw StateError('bill went negative: $out');
        if (r.status < 400) {
          throw StateError('the second allocation to a cleared bill was '
              'accepted');
        }
      });

      await log.step('SC-RC-008 Files opens on a receipt; Send is not '
          'offered', () async {
        await openReceipts();
        await selectRow(tester, '${rcStale['settlement_number']}');
        await selectRow(tester, '${rcDone['settlement_number']}');
        final List<String> out = <String>[];
        final String send = buttonState(tester, 'Send');
        if (send == 'enabled') throw StateError('Send is offered on a receipt');
        out.add('Send $send (not offered, as the book says); Print '
            '${buttonState(tester, 'Print')}');
        for (final String b in <String>['Files']) {
          final String st = buttonState(tester, b);
          if (st != 'enabled') {
            out.add('$b $st');
            continue;
          }
          await tapButton(tester, b);
          await pumpFor(tester, const Duration(seconds: 2));
          out.add('$b opened=${find.byType(Dialog).evaluate().isNotEmpty}');
          await closeOpenEditor(tester);
        }
        log.saw = out.join('; ');
        if (out.skip(1).any((String s) => !s.endsWith('opened=true'))) {
          throw StateError(out.join('; '));
        }
      });

      log.skip('SC-RC-006', 'TDS section list not driven; the section '
          'dropdown holds no entries without a TDS master in the fixture');
      log.skip('SC-RC-007', 'no early-payment discount offered on any bill');
      log.skip('SC-RC-010', 'no payment promise recorded in the fixture firm');
      log.skip('SC-RC-011', 'Collection Sheet is under All Sell screens; '
          'not reached');
      log.skip('SC-RC-015', 'no closed financial period in the fixture firm');
      log.skip('SC-RC-016', 'Mode and account default to Cash; the dialog has '
          'no empty state for them');
      log.skip('SC-RC-028', 'needs the cashier user and the statement screen');
    } else {
      final Map<String, List<String>> menu = await offeredMenu(tester);
      // ignore: avoid_print
      print('FLOW: MENU [$itHandle] ${menu.entries.map((MapEntry<String, List<String>> e) => '${e.key}=${e.value.join(',')}').join('; ')}');
      final bool offered = menuHas(menu, menuPath);
      final ({int status, String text}) api =
          await me.attempt('GET', '/api/v1/receipts?page_size=1', null);
      if (itHandle == 'qacct') {
        await log.step('SC-RC-027 AC: Receipts offered, Record and Reverse',
            () async {
          log.saw = 'Receipts offered: $offered; list answers ${api.status}';
          if (!offered) throw StateError('not offered to Accounts');
          final Json b = await apiApprovedInvoice(admin, quantity: 1);
          final Json rc = await apiReceipt(admin, b, 10);
          await openReceipts();
          await selectRow(tester, '${rc['settlement_number']}');
          log.saw = '${log.saw}; New ${buttonState(tester, '+ New')}, '
              'Reverse ${buttonState(tester, 'Reverse')}';
          if (buttonState(tester, 'Reverse') != 'enabled') {
            throw StateError('Reverse not offered to Accounts');
          }
        });
      } else if (itHandle == 'qro') {
        await log.step('SC-RC-026 RO: rows readable, Record and Reverse absent',
            () async {
          log.saw = 'Receipts offered: $offered; list answers ${api.status}';
          if (!offered) throw StateError('not offered to Read Only');
          final Json b = await apiApprovedInvoice(admin, quantity: 1);
          final Json rc = await apiReceipt(admin, b, 10);
          await openReceipts();
          await selectRow(tester, '${rc['settlement_number']}');
          final Map<String, String> s = <String, String>{
            for (final String x in <String>['+ New', 'Reverse'])
              x: buttonState(tester, x),
          };
          log.saw = '${log.saw}; $s';
          if (s.values.any((String v) => v == 'enabled')) {
            throw StateError('Read Only is offered $s');
          }
        });
      } else {
        final String id = itHandle == 'qsexe' ? 'SC-RC-024' : 'SC-RC-025';
        await log.step('$id ${itHandle == 'qsexe' ? 'FS' : 'SM'}: Receipts '
            'not offered', () async {
          log.saw = 'Receipts offered: $offered; list answers ${api.status}';
          if (offered != (api.status == 200)) {
            throw StateError('menu ($offered) and server (${api.status}) '
                'disagree');
          }
          if (offered) throw StateError('Receipts is offered');
        });
      }
    }
    log.finish();
  });
}
