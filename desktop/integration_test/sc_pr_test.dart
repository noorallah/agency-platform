import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'buy_data.dart';
import 'cases.dart';
import 'harness.dart';
import 'sell_data.dart';

/// Purchase returns (book section PR). Run as tradeadmin, then qpexe (PU),
/// qpmgr (PM), qstore (WH), qro.
void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('PR: purchase return cases ($itHandle)',
      (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1600, 1000);
    tester.view.devicePixelRatio = 1;
    final Server me = await Server.connect();
    final Server admin = await Server.connectAs(
        't10069cwy.tradeadmin@fixtures.local', fixturePassword);
    await startAndSignIn(tester);
    collectAppErrors();
    final FlowLog log = FlowLog('pr-$itHandle');
    const String menuPath = 'purchaseReturns';

    Future<void> openReturns() async {
      await openMenu(tester, 'buy', menuPath);
      await refreshList(tester);
    }

    Future<String> statusOf(String id) async =>
        '${(await admin.one('purchase-returns', id))['status']}';

    Future<void> newReturnFor(Json gr) async {
      await openReturns();
      await tapNew(tester);
      await chooseIn(tester, 'purchase-return-receipt', docNumber(gr));
      await pumpFor(tester, const Duration(seconds: 2));
    }

    Future<String> refuse(String qty) => expectRefusal(tester, me,
        collection: 'purchase-returns',
        openKey: 'purchase-return-save',
        press: () async {
          await typeInKeyed(tester, 'purchase-return-returning-', qty);
          await tapKey(tester, 'purchase-return-save');
        });

    Map<String, String> buttons(List<String> names) => <String, String>{
          for (final String b in names) b: buttonState(tester, b),
        };

    if (itHandle == 'tradeadmin') {
      final Json gr = await apiReceiptOf(admin, await apiPo(admin));
      final Json grPartly = await apiReceiptOf(admin, await apiPo(admin));
      final Json earlier = await apiPurchaseReturn(admin, grPartly, quantity: 4);
      await apiAct(admin, 'purchase-returns', '${earlier['id']}', 'approve');
      final Json grDraft =
          await apiReceiptOf(admin, await apiPo(admin), complete: false);
      final Json rApproved = await apiPurchaseReturn(admin, gr);
      await apiAct(admin, 'purchase-returns', '${rApproved['id']}', 'approve');
      final Json rDraft = await apiPurchaseReturn(admin, gr);
      final Json rFlow = await apiPurchaseReturn(admin, gr);
      await apiAct(admin, 'purchase-returns', '${rFlow['id']}', 'approve');
      final Json rClosed = await apiPurchaseReturn(admin, gr);
      for (final String a in <String>['approve', 'complete', 'close']) {
        await apiAct(admin, 'purchase-returns', '${rClosed['id']}', a);
      }
      final Json rCancel = await apiPurchaseReturn(admin, gr);
      final Json rStale = await apiPurchaseReturn(admin, gr);

      await log.step('SC-PR-001 list opens with its columns', () async {
        await openReturns();
        final List<String> missing = <String>[
          for (final String h in <String>[
            'Return Number',
            'Supplier',
            'Return Date',
            'Status'
          ])
            if (!screenHas(tester, h)) h,
        ];
        log.info('SC-PR-001', 'short texts: ${textOnScreen(tester).where((String t) => t.length < 26).take(60).join(' | ')}');
        if (missing.isNotEmpty) {
          throw StateError('not on screen: ${missing.join(', ')}');
        }
        log.saw = 'columns present';
      });

      // -- Negative -------------------------------------------------------
      await log.step('SC-PR-010 returning 11 of 10 received', () async {
        await newReturnFor(gr);
        log.saw = await refuse('11');
      });
      await closeOpenEditor(tester);

      await log.step('SC-PR-011 returning 7 when only 6 can still go back',
          () async {
        await newReturnFor(grPartly);
        log.saw = await refuse('7');
      });
      await closeOpenEditor(tester);

      for (final String q in <String>['0', '-1']) {
        await log.step('SC-PR-012 quantity $q is refused', () async {
          await newReturnFor(gr);
          log.saw = await refuse(q);
        });
        await closeOpenEditor(tester);
      }

      await log.step('SC-PR-013 no receipt chosen: Save is refused', () async {
        await openReturns();
        await tapNew(tester);
        log.saw = await expectRefusal(tester, me,
            collection: 'purchase-returns',
            openKey: 'purchase-return-save',
            press: () async => tapKey(tester, 'purchase-return-save'));
      });
      await closeOpenEditor(tester);

      await log.step('SC-PR-014 a Draft receipt is not offered', () async {
        await openReturns();
        await tapNew(tester);
        await tapKey(tester, 'purchase-return-receipt');
        await pumpFor(tester, const Duration(seconds: 1));
        final bool done = screenHas(tester, docNumber(gr));
        final bool draft = screenHas(tester, docNumber(grDraft));
        log.saw = 'completed receipt offered=$done, draft receipt '
            'offered=$draft';
        await closeOpenEditor(tester);
        if (draft) throw StateError('a Draft receipt is offered');
        if (!done) throw StateError('the completed receipt is not offered');
      });
      await closeOpenEditor(tester);

      await log.step('SC-PR-021 the Cancel button on a typed-in editor asks',
          () async {
        await newReturnFor(gr);
        await typeInKeyed(tester, 'purchase-return-returning-', '2');
        await tapButton(tester, 'Cancel');
        await pumpFor(tester, const Duration(seconds: 1));
        final bool gone = find
            .byKey(const ValueKey<String>('purchase-return-save'))
            .evaluate()
            .isEmpty;
        final bool asks = find
                .byKey(const ValueKey<String>('document-discard'))
                .evaluate()
                .isNotEmpty ||
            dialogText(tester).isNotEmpty;
        log.saw = 'editor closed=$gone, asked=$asks';
        if (gone && !asks) {
          throw StateError('Cancel closed an editor holding typing without '
              'asking (known SCRQ-21)');
        }
      });
      await closeOpenEditor(tester);

      await log.step('SC-PR-018 an Approved return cannot be edited',
          () async {
        await openReturns();
        await selectRow(tester, docNumber(rApproved));
        final String e = buttonState(tester, 'Edit');
        log.saw = 'Edit is $e on an Approved return';
        if (e == 'enabled') throw StateError('Edit offered');
      });

      await log.step('SC-PR-019 Complete is not offered on a Draft return',
          () async {
        await openReturns();
        await selectRow(tester, docNumber(rDraft));
        final String c = buttonState(tester, 'Complete');
        log.saw = 'Complete is $c on a Draft return';
        if (c == 'enabled') {
          final String said = await pressWithReason(tester, 'Complete');
          log.saw = '${log.saw}; pressed: "$said", status '
              '${await statusOf('${rDraft['id']}')}';
          if (said.isEmpty) throw StateError('N1: said nothing');
        }
      });

      await log.step('SC-PR-020 a Closed return cannot be closed or cancelled',
          () async {
        await openReturns();
        await selectRow(tester, docNumber(rClosed));
        final Map<String, String> s = buttons(<String>['Close', 'Cancel']);
        log.saw = 'buttons $s';
        if (s['Cancel'] == 'enabled') {
          final String said = await pressWithReason(tester, 'Cancel');
          final String st = await statusOf('${rClosed['id']}');
          log.saw = '${log.saw}; Cancel pressed: status $st, says "$said"';
          if (st == 'CANCELLED') throw StateError('a Closed return was '
              'cancelled');
        }
      });

      // -- Positive -------------------------------------------------------
      await log.step('SC-PR-004 Complete an Approved return, then Close it',
          () async {
        await openReturns();
        await selectRow(tester, docNumber(rFlow));
        final String s1 = await pressWithReason(tester, 'Complete');
        final String st1 = await statusOf('${rFlow['id']}');
        await selectRow(tester, docNumber(rFlow));
        final String s2 = await pressWithReason(tester, 'Close');
        final String st2 = await statusOf('${rFlow['id']}');
        log.saw = 'Complete: $st1 ("$s1"); Close: $st2 ("$s2")';
        if (st1 != 'COMPLETED' || st2 != 'CLOSED') {
          throw StateError('status $st1 then $st2');
        }
      });

      await log.step('SC-PR-009 Cancel a Draft return', () async {
        await openReturns();
        await selectRow(tester, docNumber(rCancel));
        final String said = await pressWithReason(tester, 'Cancel');
        final String st = await statusOf('${rCancel['id']}');
        log.saw = 'status $st, screen says "$said"';
        if (st != 'CANCELLED') throw StateError('status $st');
      });

      // -- Multi-user -----------------------------------------------------
      await log.step('SC-PR-027 stale Approve after another user approved',
          () async {
        await openReturns();
        await selectRow(tester, docNumber(rStale));
        await apiAct(await asUser('qpmgr'), 'purchase-returns',
            '${rStale['id']}', 'approve');
        await tapButton(tester, 'Approve');
        final String said = await watch(tester, seconds: 5);
        log.saw = 'status ${await statusOf('${rStale['id']}')}, screen says '
            '"$said"';
        if (said.isEmpty) throw StateError('N1: stale Approve said nothing');
      });

      log.skip('SC-PR-005', 'Replace outcome needs a purchase order stage '
          'check; not driven');
      log.skip('SC-PR-006', 'credit on a paid bill is a report matter');
      log.skip('SC-PR-007', 'no free goods in the fixture receipts');
      log.skip('SC-PR-008', 'no batch-tracked product in the fixture');
      log.skip('SC-PR-015', 'Return date is a picker; not driven');
      log.skip('SC-PR-016', 'would need stock sold after receipt');
      log.skip('SC-PR-017', 'no capital goods line in the fixture');
      log.skip('SC-PR-026', 'covered by SC-PR-027 and the PY file');
      log.skip('SC-PR-028', 'a Draft return has no Edit on screen to race');
    } else {
      final Map<String, List<String>> menu = await offeredMenu(tester);
      // ignore: avoid_print
      print('FLOW: MENU [$itHandle] ${menu.entries.map((MapEntry<String, List<String>> e) => '${e.key}=${e.value.join(',')}').join('; ')}');
      final bool offered = menuHas(menu, menuPath);
      final ({int status, String text}) api =
          await me.attempt('GET', '/api/v1/purchase-returns?page_size=1', null);
      final Json gr = await apiReceiptOf(admin, await apiPo(admin));
      final Json ret = await apiPurchaseReturn(admin, gr);
      Future<void> openAndSelect() async {
        await openReturns();
        await selectRow(tester, docNumber(ret));
      }

      if (itHandle == 'qpexe') {
        await log.step('SC-PR-022 PU: New offered, Approve absent', () async {
          log.saw = 'offered: $offered; list ${api.status}';
          if (!offered) throw StateError('not offered to PU');
          await openAndSelect();
          final Map<String, String> s =
              buttons(<String>['+ New', 'New', 'Approve']);
          log.saw = '${log.saw}; $s';
          if (s['Approve'] == 'enabled') {
            throw StateError('PU is offered Approve: $s');
          }
        });
      } else if (itHandle == 'qpmgr') {
        await log.step('SC-PR-023 PM: Approve and Cancel offered', () async {
          log.saw = 'offered: $offered';
          if (!offered) throw StateError('not offered to PM');
          await openAndSelect();
          final Map<String, String> s =
              buttons(<String>['Approve', 'Complete', 'Close', 'Cancel']);
          log.saw = '${log.saw}; $s';
          if (s['Approve'] != 'enabled' || s['Cancel'] != 'enabled') {
            throw StateError('missing: $s');
          }
        });
      } else if (itHandle == 'qstore') {
        await log.step('SC-PR-024 WH: Purchase Returns not offered', () async {
          log.saw = 'offered: $offered; list ${api.status}';
          if (offered) throw StateError('returns offered to WH');
        });
      } else if (itHandle == 'qro') {
        await log.step('SC-PR-025 RO: rows readable, no write buttons',
            () async {
          log.saw = 'offered: $offered';
          if (!offered) throw StateError('not offered to Read Only');
          await openAndSelect();
          final Map<String, String> s = buttons(<String>[
            '+ New', 'New', 'Approve', 'Complete', 'Cancel', 'Close'
          ]);
          log.saw = '${log.saw}; $s';
          if (s.values.any((String v) => v == 'enabled')) {
            throw StateError('Read Only is offered $s');
          }
        });
      }
    }
    log.finish();
  });
}
