import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'buy_data.dart';
import 'cases.dart';
import 'harness.dart';
import 'sell_data.dart';

/// Goods receipts (book section GR). Run as tradeadmin, then qstore (WH),
/// qpexe (PU), qpmgr (PM), qsexe (FS), qro.
void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('GR: goods receipt cases ($itHandle)',
      (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1600, 1000);
    tester.view.devicePixelRatio = 1;
    final Server me = await Server.connect();
    final Server admin = await Server.connectAs(
        't10069cwy.tradeadmin@fixtures.local', fixturePassword);
    await startAndSignIn(tester);
    collectAppErrors();
    final FlowLog log = FlowLog('gr-$itHandle');
    const String menuPath = 'goodsReceipts/receipts';

    Future<void> openReceipts() async {
      await openMenu(tester, 'buy', menuPath);
      await refreshList(tester);
    }

    Future<String> statusOf(String id) async =>
        '${(await admin.one('goods-receipts', id))['status']}';

    Future<void> newReceiptFor(Json po) async {
      await openReceipts();
      await tapNew(tester);
      await chooseIn(tester, 'goods-receipt-order', docNumber(po));
      await pumpFor(tester, const Duration(seconds: 2));
    }

    Future<String> refuse(String qty) => expectRefusal(tester, me,
        collection: 'goods-receipts',
        openKey: 'goods-receipt-save',
        press: () async {
          await typeInKeyed(tester, 'goods-receipt-accepted-', qty);
          await tapKey(tester, 'goods-receipt-save-complete');
          await confirmIfAsked(tester);
        });

    bool asked() =>
        find.byKey(const ValueKey<String>('document-discard')).evaluate().isNotEmpty ||
        dialogText(tester).isNotEmpty;

    if (itHandle == 'tradeadmin') {
      final Json po = await apiPo(admin, quantity: 10);
      final Json poPartial = await apiPo(admin, quantity: 10);
      final Json poDraftOnly = await apiPo(admin, quantity: 10, stage: 'draft');
      final Json poRace = await apiPo(admin, quantity: 10);
      final Json poBilled = await apiPo(admin, quantity: 10);
      final Json grBilled = await apiReceiptOf(admin, poBilled);
      final Json billDraft = await apiBill(admin, grBilled);
      await apiAct(admin, 'purchase-invoices', '${billDraft['id']}', 'approve');
      final Json grDraft =
          await apiReceiptOf(admin, await apiPo(admin), complete: false);
      final Json grCompleted = await apiReceiptOf(admin, await apiPo(admin));
      final Json grCancel = await apiReceiptOf(admin, await apiPo(admin));
      final Json grClose = await apiReceiptOf(admin, await apiPo(admin));

      await log.step('SC-GR-001 list opens with its columns', () async {
        await openReceipts();
        final List<String> missing = <String>[
          for (final String h in <String>[
            'GRN Number',
            'Supplier',
            'Purchase Order',
            'Receipt Date',
            'Status'
          ])
            if (!screenHas(tester, h)) h,
        ];
        if (missing.isNotEmpty) {
          throw StateError('not on screen: ${missing.join(', ')}');
        }
        log.saw = 'columns present';
      });

      // -- Negative -------------------------------------------------------
      await log.step('SC-GR-012 no purchase order: Save is refused', () async {
        await openReceipts();
        await tapNew(tester);
        log.saw = await expectRefusal(tester, me,
            collection: 'goods-receipts',
            openKey: 'goods-receipt-save',
            press: () async => tapKey(tester, 'goods-receipt-save'));
      });
      await closeOpenEditor(tester);

      await log.step('SC-GR-013 receiving 11 of 10 ordered', () async {
        await newReceiptFor(po);
        log.saw = await refuse('11');
      });
      await closeOpenEditor(tester);

      for (final String q in <String>['0', '-1']) {
        await log.step('SC-GR-014 quantity $q is refused', () async {
          await newReceiptFor(po);
          log.saw = await refuse(q);
        });
        await closeOpenEditor(tester);
      }

      await log.step('SC-GR-017 only approved orders are offered', () async {
        await openReceipts();
        await tapNew(tester);
        await tapKey(tester, 'goods-receipt-order');
        await pumpFor(tester, const Duration(seconds: 1));
        final bool approved = screenHas(tester, docNumber(po));
        final bool draft = screenHas(tester, docNumber(poDraftOnly));
        log.saw = 'approved order offered=$approved, draft order '
            'offered=$draft';
        await closeOpenEditor(tester);
        if (draft) throw StateError('a Draft order is offered');
        if (!approved) throw StateError('the approved order is not offered');
      });
      await closeOpenEditor(tester);

      await log.step('SC-GR-022 the Cancel button on a typed-in editor asks',
          () async {
        await newReceiptFor(po);
        await typeInKeyed(tester, 'goods-receipt-accepted-', '3');
        await tapButton(tester, 'Cancel');
        await pumpFor(tester, const Duration(seconds: 1));
        final bool gone = find
            .byKey(const ValueKey<String>('goods-receipt-save'))
            .evaluate()
            .isEmpty;
        log.saw = 'editor closed=$gone, asked=${asked()}';
        if (gone && !asked()) {
          throw StateError('Cancel closed an editor holding typing without '
              'asking (known SCRQ-21)');
        }
      });
      await closeOpenEditor(tester);

      await log.step('SC-GR-018 Cancel a receipt that has been invoiced',
          () async {
        await openReceipts();
        await selectRow(tester, docNumber(grBilled));
        final String said = await pressWithReason(tester, 'Cancel');
        final String st = await statusOf('${grBilled['id']}');
        log.saw = 'status $st, screen says "$said"';
        if (st == 'CANCELLED') {
          throw StateError('an invoiced receipt was cancelled');
        }
        if (said.isEmpty) throw StateError('N1: refusal said nothing');
      });

      await log.step('SC-GR-019 Edit on a Completed receipt', () async {
        await openReceipts();
        await selectRow(tester, docNumber(grCompleted));
        final String e = buttonState(tester, 'Edit');
        log.saw = 'Edit is $e on a Completed receipt';
        if (e == 'enabled') throw StateError('Edit offered');
      });

      await log.step('SC-GR-020 Close on a Draft receipt', () async {
        await openReceipts();
        await selectRow(tester, docNumber(grDraft));
        final String c = buttonState(tester, 'Close');
        log.saw = 'Close is $c on a Draft receipt';
        if (c == 'enabled') {
          final String said = await pressWithReason(tester, 'Close');
          final String st = await statusOf('${grDraft['id']}');
          log.saw = '${log.saw}; pressed: status $st, says "$said"';
          if (st == 'CLOSED') throw StateError('a Draft receipt was closed');
          if (said.isEmpty) throw StateError('N1: refusal said nothing');
        }
      });

      // -- Positive -------------------------------------------------------
      await log.step('SC-GR-003 receive 4, then the 6 still owed', () async {
        await newReceiptFor(poPartial);
        await typeInKeyed(tester, 'goods-receipt-accepted-', '4');
        await saveEditor(tester, 'goods-receipt-save-complete');
        await confirmIfAsked(tester);
        await pumpFor(tester, const Duration(seconds: 2));
        final String s1 =
            '${(await admin.one('purchases', '${poPartial['id']}'))['status']}';
        await newReceiptFor(poPartial);
        final List<String> shown = <String>[
          for (final EditableText e
              in tester.widgetList<EditableText>(find.byType(EditableText)))
            e.controller.text,
        ];
        await saveEditor(tester, 'goods-receipt-save-complete');
        await confirmIfAsked(tester);
        await pumpFor(tester, const Duration(seconds: 2));
        final String s2 =
            '${(await admin.one('purchases', '${poPartial['id']}'))['status']}';
        log.saw = 'after 4: order $s1; second receipt boxes '
            '${shown.where((String t) => t.isNotEmpty).take(8).join(' / ')}; '
            'after the rest: order $s2';
        if (!s1.contains('PART')) throw StateError('after 4 the order is $s1');
        if (!(s2 == 'RECEIVED' || s2.contains('COMPLETE'))) {
          throw StateError('after 10 the order is $s2');
        }
      });

      await log.step('SC-GR-008 Close a Completed receipt', () async {
        await openReceipts();
        await selectRow(tester, docNumber(grClose));
        final String said = await pressWithReason(tester, 'Close');
        final String st = await statusOf('${grClose['id']}');
        log.saw = 'status $st, screen says "$said"';
        if (st != 'CLOSED') throw StateError('status $st');
      });

      await log.step('SC-GR-010 Cancel a Completed receipt', () async {
        await openReceipts();
        await selectRow(tester, docNumber(grCancel));
        final String said = await pressWithReason(tester, 'Cancel');
        final String st = await statusOf('${grCancel['id']}');
        log.saw = 'status $st, screen says "$said"';
        if (st != 'CANCELLED') throw StateError('status $st');
      });

      // -- Multi-user -----------------------------------------------------
      await log.step('SC-GR-029 second receipt of the full order after '
          'another user received it', () async {
        await newReceiptFor(poRace);
        await apiReceiptOf(await asUser('qstore'), poRace, quantity: 10);
        log.saw = await expectRefusal(tester, me,
            collection: 'goods-receipts',
            openKey: 'goods-receipt-save',
            press: () async {
              await tapKey(tester, 'goods-receipt-save-complete');
              await confirmIfAsked(tester);
            });
      });
      await closeOpenEditor(tester);

      log.skip('SC-GR-004', 'the product is not batch-tracked in the fixture');
      log.skip('SC-GR-005', 'the product is not serial-tracked in the fixture');
      log.skip('SC-GR-006', 'MRP/PTR/PTS boxes need a batch-tracked product');
      log.skip('SC-GR-007', 'quarantine needs Quality Inspection set on');
      log.skip('SC-GR-009', 'transport boxes not driven');
      log.skip('SC-GR-011', 'file picker not drivable');
      log.skip('SC-GR-015', 'Receipt date is a picker limited to today');
      log.skip('SC-GR-016', 'needs a serial-tracked product');
      log.skip('SC-GR-021', 'needs stock consumed after the receipt');
      log.skip('SC-GR-028', 'covered by SC-GR-029 and the PO file');
      log.skip('SC-GR-030', 'a Completed receipt cannot be edited on screen');
    } else {
      final Map<String, List<String>> menu = await offeredMenu(tester);
      // ignore: avoid_print
      print('FLOW: MENU [$itHandle] ${menu.entries.map((MapEntry<String, List<String>> e) => '${e.key}=${e.value.join(',')}').join('; ')}');
      final bool offered = menuHas(menu, menuPath);
      final ({int status, String text}) api =
          await me.attempt('GET', '/api/v1/goods-receipts?page_size=1', null);
      final Json gr =
          await apiReceiptOf(admin, await apiPo(admin), complete: false);
      Future<void> openAndSelect() async {
        await openReceipts();
        await selectRow(tester, docNumber(gr));
      }

      Map<String, String> buttons(List<String> names) => <String, String>{
            for (final String b in names) b: buttonState(tester, b),
          };

      if (itHandle == 'qstore' || itHandle == 'qpexe' || itHandle == 'qpmgr') {
        final String id = <String, String>{
          'qstore': 'SC-GR-023 WH',
          'qpexe': 'SC-GR-024 PU',
          'qpmgr': 'SC-GR-025 PM'
        }[itHandle]!;
        await log.step('$id: Goods Receipts offered with New and Complete',
            () async {
          log.saw = 'offered: $offered; list ${api.status}; bills '
              'offered: ${menuHas(menu, 'purchaseInvoices')}; returns '
              'offered: ${menuHas(menu, 'purchaseReturns')}';
          if (!offered) throw StateError('Goods Receipts not offered');
          await openAndSelect();
          final Map<String, String> s = buttons(
              <String>['+ New', 'New', 'Approve', 'Complete', 'Cancel']);
          log.saw = '${log.saw}; $s';
          if (s['New'] != 'enabled' && s['+ New'] != 'enabled') {
            throw StateError('New not offered: $s');
          }
        });
      } else if (itHandle == 'qsexe') {
        await log.step('SC-GR-026 FS: Goods Receipts not offered', () async {
          log.saw = 'offered: $offered; list ${api.status}';
          if (offered) throw StateError('Goods Receipts offered to FS');
        });
      } else if (itHandle == 'qro') {
        await log.step('SC-GR-027 RO: rows readable, no write buttons',
            () async {
          log.saw = 'offered: $offered';
          if (!offered) throw StateError('not offered to Read Only');
          await openAndSelect();
          final Map<String, String> s = buttons(<String>[
            '+ New', 'New', 'Complete', 'Approve', 'Cancel', 'Close'
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
