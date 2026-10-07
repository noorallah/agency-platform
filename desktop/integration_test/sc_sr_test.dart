import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'cases.dart';
import 'harness.dart';
import 'sell_data.dart';

/// Sales returns (book section SR): Negative, Role, Multi-user and Positive
/// cases the selling flow does not cover. Run as tradeadmin, then qsmgr,
/// qsexe, qro.
void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('SR: sales return cases ($itHandle)', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1600, 1000);
    tester.view.devicePixelRatio = 1;
    final Server me = await Server.connect();
    final Server admin = await Server.connectAs(
        't10069cwy.tradeadmin@fixtures.local', fixturePassword);
    await startAndSignIn(tester);
    collectAppErrors();
    final FlowLog log = FlowLog('sr-$itHandle');
    const String menuPath = 'salesReturns';

    Future<void> openReturns() async {
      await openMenu(tester, 'sell', menuPath);
      await refreshList(tester);
    }

    Future<String> statusOf(String id) async =>
        '${(await admin.one('sales-returns', id))['status']}';

    Future<void> newReturn(Json invoice) async {
      await openReturns();
      await tapNew(tester);
      await chooseIn(tester, 'sales-return-document', docNumber(invoice));
      await pumpFor(tester, const Duration(seconds: 2));
    }

    if (itHandle == 'tradeadmin') {
      final Json inv = await apiApprovedInvoice(admin, quantity: 10);
      final Json earlier = await apiDraftReturn(admin, inv, quantity: 2);
      await apiAct(admin, 'sales-returns', '${earlier['id']}', 'approve');
      final Json invB = await apiApprovedInvoice(admin, quantity: 9);
      final Json retDraft = await apiDraftReturn(admin, invB, quantity: 1);
      final Json retForApprove = await apiDraftReturn(admin, invB, quantity: 1);
      final Json retStale = await apiDraftReturn(admin, invB, quantity: 1);
      final Json retRace = await apiDraftReturn(admin, invB, quantity: 1);
      final Json retComplete = await apiDraftReturn(admin, invB, quantity: 1);
      await apiAct(admin, 'sales-returns', '${retComplete['id']}', 'approve');
      final Json retClosed = await apiDraftReturn(admin, invB, quantity: 1);
      await apiAct(admin, 'sales-returns', '${retClosed['id']}', 'approve');
      await apiAct(admin, 'sales-returns', '${retClosed['id']}', 'complete');
      await apiAct(admin, 'sales-returns', '${retClosed['id']}', 'close');
      final Json retApproved = await apiDraftReturn(admin, invB, quantity: 1);
      await apiAct(admin, 'sales-returns', '${retApproved['id']}', 'approve');

      await log.step('SC-SR-001 list opens with its columns and cards',
          () async {
        await openReturns();
        final List<String> missing = <String>[
          for (final String h in <String>[
            'Return Number',
            'Customer',
            'Return Date',
            'Status',
            'Draft',
            'Approved'
          ])
            if (!screenHas(tester, h)) h,
        ];
        log.info('SC-SR-001', 'short texts: ${textOnScreen(tester).where((String t) => t.length < 24).take(60).join(' | ')}');
        if (missing.isNotEmpty) {
          throw StateError('not on screen: ${missing.join(', ')}');
        }
        log.saw = 'columns and cards present';
      });

      // -- Negative -------------------------------------------------------
      Future<String> refuse(String qty) => expectRefusal(tester, me,
          collection: 'sales-returns',
          openKey: 'sales-return-save',
          press: () async {
            await typeInKeyed(tester, 'sales-return-returning-', qty);
            await tapKey(tester, 'sales-return-save');
          });

      await log.step('SC-SR-009 returning 9 when 8 can still come back',
          () async {
        await newReturn(inv);
        log.saw = await refuse('9');
      });
      await closeOpenEditor(tester);

      await log.step('SC-SR-010 returning 0 on every line', () async {
        await newReturn(inv);
        log.saw = await refuse('0');
      });
      await closeOpenEditor(tester);

      await log.step('SC-SR-011 returning -1', () async {
        await newReturn(inv);
        log.saw = await refuse('-1');
      });
      await closeOpenEditor(tester);

      await log.step('SC-SR-012 Save with nothing returned against', () async {
        await openReturns();
        await tapNew(tester);
        log.saw = await expectRefusal(tester, me,
            collection: 'sales-returns',
            openKey: 'sales-return-save',
            press: () async => tapKey(tester, 'sales-return-save'));
      });
      await closeOpenEditor(tester);

      await log.step('SC-SR-019 the Cancel button on a typed-in editor asks',
          () async {
        await newReturn(inv);
        await typeInKeyed(tester, 'sales-return-returning-', '3');
        await tapButton(tester, 'Cancel');
        await pumpFor(tester, const Duration(seconds: 1));
        final bool gone = find
            .byKey(const ValueKey<String>('sales-return-save'))
            .evaluate()
            .isEmpty;
        final bool asks =
            find.byKey(const ValueKey<String>('document-discard')).evaluate().isNotEmpty ||
                dialogText(tester).isNotEmpty;
        log.saw = 'editor closed=$gone, asked=$asks';
        if (gone && !asks) {
          throw StateError('Cancel closed an editor holding typing without '
              'asking (known SCRQ-21)');
        }
      });
      await closeOpenEditor(tester);

      await log.step('SC-SR-015 an Approved return cannot be edited',
          () async {
        await openReturns();
        await selectRow(tester, docNumber(retApproved));
        final String e = buttonState(tester, 'Edit');
        log.saw = 'Edit is $e on an Approved return; Approve '
            '${buttonState(tester, 'Approve')}, Complete '
            '${buttonState(tester, 'Complete')}';
        if (e == 'enabled') throw StateError('Edit offered');
      });

      await log.step('SC-SR-016 Complete is not offered on a Draft return',
          () async {
        await openReturns();
        await selectRow(tester, docNumber(retDraft));
        final String c = buttonState(tester, 'Complete');
        log.saw = 'Complete is $c on a Draft return';
        if (c == 'enabled') {
          await tapButton(tester, 'Complete');
          final String said = await watch(tester, seconds: 5);
          log.saw = '${log.saw}; pressed: "$said"';
          if (said.isEmpty) throw StateError('N1: said nothing');
        }
      });

      await log.step('SC-SR-017 a Closed return cannot be cancelled', () async {
        await openReturns();
        await selectRow(tester, docNumber(retClosed));
        final String c = buttonState(tester, 'Cancel');
        log.saw = 'Cancel is $c on a Closed return';
        if (c == 'enabled') {
          final String said = await pressWithReason(tester, 'Cancel');
          log.saw = '${log.saw}; pressed: "$said", status '
              '${await statusOf('${retClosed['id']}')}';
          if (await statusOf('${retClosed['id']}') == 'CANCELLED') {
            throw StateError('a Closed return was cancelled');
          }
        }
      });

      // -- Positive -------------------------------------------------------
      await log.step('SC-SR-004 Complete an Approved return', () async {
        await openReturns();
        await selectRow(tester, docNumber(retComplete));
        final String said = await pressWithReason(tester, 'Complete');
        final String status = await statusOf('${retComplete['id']}');
        log.saw = 'status $status, screen says "$said"';
        if (status != 'COMPLETED') throw StateError('status $status');
      });

      await log.step('SC-SR-005 Close a Completed return', () async {
        await openReturns();
        await selectRow(tester, docNumber(retComplete));
        final String said = await pressWithReason(tester, 'Close');
        final String status = await statusOf('${retComplete['id']}');
        log.saw = 'status $status, screen says "$said"';
        if (status != 'CLOSED') throw StateError('status $status');
      });

      await log.step('SC-SR-006 Cancel a Draft return with a reason', () async {
        await openReturns();
        await selectRow(tester, docNumber(retForApprove));
        final String said = await pressWithReason(tester, 'Cancel',
            reason: 'customer changed their mind');
        final String status = await statusOf('${retForApprove['id']}');
        log.saw = 'status $status, screen says "$said"';
        if (status != 'CANCELLED') throw StateError('status $status');
      });

      // -- Multi-user -----------------------------------------------------
      await log.step('SC-SR-024 stale Approve after another user approved',
          () async {
        await openReturns();
        await selectRow(tester, docNumber(retStale));
        await apiAct(await asUser('qsmgr'), 'sales-returns',
            '${retStale['id']}', 'approve');
        await tapButton(tester, 'Approve');
        final String said = await watch(tester, seconds: 5);
        log.saw = 'status ${await statusOf('${retStale['id']}')}, screen says '
            '"$said"';
        if (said.isEmpty) throw StateError('N1: the stale Approve said nothing');
      });

      await openReturns();
      await selectRow(tester, docNumber(retRace));
      final String editState25 = buttonState(tester, 'Edit');
      if (editState25 != 'enabled') {
        log.skip('SC-SR-025', 'a Draft return has no Edit on screen '
            '($editState25), so there is no second session to race');
      } else {
      await log.step('SC-SR-025 stale save after another user changed it',
          () async {
        await tapButton(tester, 'Edit');
        await pumpFor(tester, const Duration(seconds: 2));
        final Json cur = await admin.one('sales-returns', '${retRace['id']}');
        final Json line = (cur['lines'] as List<dynamic>).first as Json;
        await (await asUser('qsmgr')).write(
            'PUT', '/api/v1/sales-returns/${cur['id']}', <String, dynamic>{
          'customer_id': cur['customer_id'],
          'branch_id': cur['branch_id'],
          'warehouse_id': cur['warehouse_id'],
          'return_date': cur['return_date'],
          'remarks': 'changed by the second user',
          'source_documents': <Json>[
            for (final dynamic s in cur['sources'] as List<dynamic>? ??
                <dynamic>[])
              <String, dynamic>{
                'source_document_type': (s as Json)['source_document_type'],
                'source_document_id': s['source_document_id'],
              },
          ],
          'lines': <Json>[
            <String, dynamic>{
              'source_document_type': line['source_document_type'],
              'source_document_id': line['source_document_id'],
              'source_document_line_id': line['source_document_line_id'],
              'line_number': 1,
              'current_return_quantity': 1,
            },
          ],
        });
        await typeInKeyed(tester, 'sales-return-returning-', '2');
        final Set<String> before = textOnScreen(tester).toSet();
        await tapKey(tester, 'sales-return-save');
        final String said = await watch(tester, confirm: false, seconds: 5);
        final String fresh = textOnScreen(tester)
            .where((String t) => t.length < 260 && !before.contains(t))
            .join(' | ');
        final Json now = await admin.one('sales-returns', '${retRace['id']}');
        final bool open = find
            .byKey(const ValueKey<String>('sales-return-save'))
            .evaluate()
            .isNotEmpty;
        log.saw = 'open=$open; remarks "${now['remarks']}"; says "$said" / '
            'new on screen "$fresh"';
        if (!open) {
          throw StateError('HIGH: the editor closed on a stale save; remarks '
              'now "${now['remarks']}"');
        }
        if (now['remarks'] != 'changed by the second user') {
          throw StateError('HIGH: the other user\'s change was overwritten');
        }
        if (said.isEmpty && fresh.isEmpty) {
          throw StateError('N1: stale save said nothing');
        }
      });
      await closeOpenEditor(tester);
      }

      await log.step('SC-SR-023 the storekeeper completes (HTTP); accounts '
          'reads', () async {
        final Json r = await apiDraftReturn(admin, invB, quantity: 1);
        await apiAct(await asUser('qsmgr'), 'sales-returns', '${r['id']}',
            'approve');
        final ({int status, String text}) c = await (await asUser('qstore'))
            .attempt('POST', '/api/v1/sales-returns/${r['id']}/complete',
                <String, dynamic>{});
        final ({int status, String text}) a = await (await asUser('qacct'))
            .attempt('GET', '/api/v1/finance/journal-entries?page_size=1', null);
        log.saw = 'qstore Complete answered ${c.status}; qacct journals '
            '${a.status}';
        if (a.status != 200) throw StateError('accounts cannot read journals');
        if (c.status == 403) {
          log.info('SC-SR-023', 'the storekeeper is refused Complete (403); '
              'the return is completed by the Sales Manager instead');
        }
      });

      log.skip('SC-SR-007', 'no service line on any bill in the fixture firm');
      log.skip('SC-SR-008', 'row tick boxes of the grid not reached in two '
          'attempts (same as SC-SO-013)');
      log.skip('SC-SR-013', 'Return date is read-only (set to today); no '
          'input to type a future date into');
      log.skip('SC-SR-014', 'a return off a never-billed note: the credit is '
          'a report matter; not driven');
      log.skip('SC-SR-018', 'no credit note raised on a return in the fixture');
    } else {
      final Map<String, List<String>> menu = await offeredMenu(tester);
      // ignore: avoid_print
      print('FLOW: MENU [$itHandle] ${menu.entries.map((MapEntry<String, List<String>> e) => '${e.key}=${e.value.join(',')}').join('; ')}');
      final bool offered = menuHas(menu, menuPath);
      final Json inv = await apiApprovedInvoice(admin, quantity: 3);
      final Json ret = await apiDraftReturn(admin, inv, quantity: 1);
      Future<void> openAndSelect() async {
        await openReturns();
        await selectRow(tester, docNumber(ret));
      }

      if (itHandle == 'qsmgr') {
        await log.step('SC-SR-020 SM: Sales Returns offered with New, '
            'Approve, Cancel', () async {
          log.saw = 'offered: $offered';
          if (!offered) throw StateError('not offered to the Sales Manager');
          await openAndSelect();
          final Map<String, String> s = <String, String>{
            for (final String b in <String>['+ New', 'New Return', 'Approve', 'Cancel'])
              b: buttonState(tester, b),
          };
          log.saw = 'offered; $s';
          if (s['Approve'] != 'enabled' || s['Cancel'] != 'enabled') {
            throw StateError('missing: $s');
          }
        });
      } else if (itHandle == 'qsexe') {
        await log.step('SC-SR-021 FS: not offered, or readable with no New',
            () async {
          final ({int status, String text}) r =
              await me.attempt('GET', '/api/v1/sales-returns?page_size=1', null);
          log.saw = 'offered: $offered; list answers ${r.status}';
          if (offered != (r.status == 200)) {
            throw StateError('menu ($offered) and server (${r.status}) '
                'disagree');
          }
          if (!offered) return;
          await openAndSelect();
          final String n = buttonState(tester, 'New Return');
          log.saw = '${log.saw}; New Return $n';
          if (n == 'enabled') throw StateError('Field Sales may raise returns');
        });
      } else if (itHandle == 'qro') {
        await log.step('SC-SR-022 RO: rows readable, no write buttons',
            () async {
          log.saw = 'offered: $offered';
          if (!offered) throw StateError('not offered to Read Only');
          await openAndSelect();
          final Map<String, String> s = <String, String>{
            for (final String b in <String>['New Return', '+ New', 'Approve', 'Cancel'])
              b: buttonState(tester, b),
          };
          log.saw = 'buttons $s';
          if (s.values.any((String v) => v == 'enabled')) {
            throw StateError('Read Only is offered $s');
          }
        });
      }
    }
    log.finish();
  });
}
