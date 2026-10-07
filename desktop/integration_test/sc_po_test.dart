import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'buy_data.dart';
import 'cases.dart';
import 'harness.dart';
import 'sell_data.dart';

/// Purchase orders (book section PO). Run as tradeadmin, then qpexe (PU),
/// qpmgr (PM), qstore (WH), qsexe (FS), qro. Where a case names PU or PM the
/// administrator runs it (the cases are about the refusal, not the right);
/// the second user of a two-user case works over HTTP.
void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('PO: purchase order cases ($itHandle)',
      (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1600, 1000);
    tester.view.devicePixelRatio = 1;
    final Server me = await Server.connect();
    final Server admin = await Server.connectAs(
        't10069cwy.tradeadmin@fixtures.local', fixturePassword);
    await startAndSignIn(tester);
    collectAppErrors();
    final FlowLog log = FlowLog('po-$itHandle');
    const String menuPath = 'purchases/purchase-orders';

    Future<void> openOrders() async {
      await openMenu(tester, 'buy', menuPath);
      await refreshList(tester);
    }

    Future<String> statusOf(String id) async =>
        '${(await admin.one('purchases', id))['status']}';

    Future<void> newOrderWithVendor() async {
      await openOrders();
      await tapNew(tester);
      await chooseIn(tester, 'purchase-order-vendor', 'Principal supplier');
    }

    Future<String> refuse(Future<void> Function() typing) => expectRefusal(
        tester, me,
        collection: 'purchases',
        openKey: 'purchase-order-save',
        press: () async {
          await typing();
          await tapKey(tester, 'purchase-order-save');
        });

    if (itHandle == 'tradeadmin') {
      final Json draft = await apiPo(admin, stage: 'draft');
      final Json forAmend = await apiPo(admin);
      final Json forEdit = await apiPo(admin);
      final Json forClose = await apiPo(admin);
      final Json forCancel = await apiPo(admin);
      final Json forDup = await apiPo(admin, stage: 'draft');
      final Json forSent = await apiPo(admin);
      final Json forStale = await apiPo(admin, stage: 'submitted');
      final Json forRace = await apiPo(admin, stage: 'draft');
      final Json forList = await apiPo(admin, stage: 'submitted');
      final Json received = await apiPo(admin);
      await apiReceiptOf(admin, received, quantity: 10);
      final Json billedPo = await apiPo(admin);
      await apiApprovedBillFrom(admin, billedPo);

      await log.step('SC-PO-001 list opens with its columns and cards',
          () async {
        await openOrders();
        final List<String> missing = <String>[
          for (final String h in <String>[
            'Draft Orders',
            'Open Orders',
            'Orders Today',
            'Pending Delivery',
            'Cancelled',
            'Closed',
            'Purchase Value',
            'Status'
          ])
            if (!screenHas(tester, h)) h,
        ];
        log.info('SC-PO-001', 'short texts: ${textOnScreen(tester).where((String t) => t.length < 28).take(70).join(' | ')}');
        if (missing.isNotEmpty) {
          throw StateError('not on screen: ${missing.join(', ')}');
        }
        log.saw = 'columns and cards present';
      });

      // -- Negative -------------------------------------------------------
      await log.step('SC-PO-018 no vendor: Save is refused', () async {
        await openOrders();
        await tapNew(tester);
        try {
          log.saw = await refuse(() async {});
        } finally {
          final Json? n = await me.newest('purchases');
          log.info('SC-PO-018', 'newest order: ${n?['po_number']} '
              'vendor ${n?['vendor_id']} lines '
              '${(n?['lines'] as List<dynamic>?)?.length} '
              'status ${n?['status']}');
        }
      });
      await closeOpenEditor(tester);

      await log.step('SC-PO-019 vendor but no product: Save is refused',
          () async {
        await newOrderWithVendor();
        log.saw = await refuse(() async {});
      });
      await closeOpenEditor(tester);

      for (final String q in <String>['0', '-4']) {
        await log.step('SC-PO-020 quantity $q is refused', () async {
          await newOrderWithVendor();
          log.saw = await refuse(() async {
            await chooseInKeyed(
                tester, 'purchase-order-line-product-', 'Detergent');
            await typeInKeyed(tester, 'purchase-order-qty-', q);
          });
        });
        await closeOpenEditor(tester);
      }

      await log.step('SC-PO-031 the Cancel button on a typed-in editor asks',
          () async {
        await newOrderWithVendor();
        await chooseInKeyed(tester, 'purchase-order-line-product-', 'Detergent');
        await typeInKeyed(tester, 'purchase-order-qty-', '7');
        await tapButton(tester, 'Cancel');
        await pumpFor(tester, const Duration(seconds: 1));
        final bool gone = find
            .byKey(const ValueKey<String>('purchase-order-save'))
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

      await log.step('SC-PO-024 Approve on a Draft order (Submit skipped)',
          () async {
        await openOrders();
        await selectRow(tester, docNumber(draft));
        final String a = buttonState(tester, 'Approve');
        log.saw = 'Approve is $a on a Draft';
        if (a == 'enabled') {
          await tapButton(tester, 'Approve');
          final String said = await watch(tester, seconds: 5);
          final String st = await statusOf('${draft['id']}');
          log.saw = '${log.saw}; pressed: status $st, screen says "$said"';
          if (st == 'APPROVED') throw StateError('a Draft was approved');
          if (said.isEmpty) throw StateError('N1: refusal said nothing');
        }
      });

      await log.step('SC-PO-027 Cancel with goods received against the order',
          () async {
        await openOrders();
        await selectRow(tester, docNumber(received));
        final String said = await pressWithReason(tester, 'Cancel');
        final String st = await statusOf('${received['id']}');
        log.saw = 'status $st, screen says "$said"';
        if (st == 'CANCELLED') {
          throw StateError('an order with goods received was cancelled');
        }
        if (said.isEmpty) throw StateError('N1: refusal said nothing');
      });

      await log.step('SC-PO-028 Cancel with a bill raised on the order',
          () async {
        await openOrders();
        await selectRow(tester, docNumber(billedPo));
        final String said = await pressWithReason(tester, 'Cancel');
        final String st = await statusOf('${billedPo['id']}');
        log.saw = 'status $st, screen says "$said"';
        if (st == 'CANCELLED') {
          throw StateError('an order with a bill on it was cancelled');
        }
        if (said.isEmpty) throw StateError('N1: refusal said nothing');
      });

      await log.step('SC-PO-029 editing an Approved order withdraws approval',
          () async {
        await openOrders();
        await selectRow(tester, docNumber(forEdit));
        await tapButton(tester, 'Edit');
        await pumpFor(tester, const Duration(seconds: 2));
        log.info('SC-PO-029', 'after Edit: dialogs ${find.byType(Dialog).evaluate().length}, '
            'save box ${find.byKey(const ValueKey<String>('purchase-order-save')).evaluate().length}, '
            'text "${dialogText(tester)}"; fresh: ${textOnScreen(tester).where((String t) => t.contains('ithdraw') || t.contains('mend')).join(' | ')}');
        final bool warned = screenHas(tester, 'withdraws');
        if (find.text('Edit anyway').evaluate().isNotEmpty) {
          await tester.tap(find.text('Edit anyway').last);
          await pumpFor(tester, const Duration(seconds: 2));
        }
        await typeInKeyed(tester, 'purchase-order-qty-', '11');
        await saveEditor(tester, 'purchase-order-save');
        await pumpFor(tester, const Duration(seconds: 2));
        final String st = await statusOf('${forEdit['id']}');
        log.saw = 'warning shown=$warned; status after save $st';
        if (!warned) throw StateError('no "withdraws the approval" warning');
        if (st == 'APPROVED') throw StateError('still Approved after the edit');
      });

      // -- Positive -------------------------------------------------------
      await log.step('SC-PO-009 Amend an Approved order', () async {
        await openOrders();
        await selectRow(tester, docNumber(forAmend));
        final String said = await pressWithReason(tester, 'Amend');
        final bool editor = find
            .byKey(const ValueKey<String>('purchase-order-save'))
            .evaluate()
            .isNotEmpty;
        final String st = await statusOf('${forAmend['id']}');
        log.saw = 'status $st, amend editor open=$editor, screen says "$said"';
        if (!editor && st == 'APPROVED') {
          throw StateError('Amend neither opened an editor nor withdrew the '
              'approval');
        }
      });
      await closeOpenEditor(tester);

      await log.step('SC-PO-010 Mark as sent', () async {
        await openOrders();
        await selectRow(tester, docNumber(forSent));
        await tapButtonOrMenu(tester, 'Mark as sent');
        await pumpFor(tester, const Duration(milliseconds: 800));
        final String asked = dialogText(tester);
        await tester.tap(find.text('Printed and handed over').last);
        final String said = await watch(tester, confirm: false, seconds: 5);
        final Json now = await admin.one('purchases', '${forSent['id']}');
        log.saw = 'asked "$asked"; sent_at ${now['sent_at']}, '
            'status ${now['status']}, screen says "$said"';
        if (now['sent_at'] == null) throw StateError('not marked as sent');
      });
      await closeOpenEditor(tester);

      await log.step('SC-PO-011 Duplicate makes a new Draft', () async {
        final int before = await totalOf(me, 'purchases');
        await openOrders();
        await selectRow(tester, docNumber(forDup));
        await tapButtonOrMenu(tester, 'Duplicate');
        await pumpFor(tester, const Duration(seconds: 2));
        final bool editor = find
            .byKey(const ValueKey<String>('purchase-order-save'))
            .evaluate()
            .isNotEmpty;
        final int after = await totalOf(me, 'purchases');
        log.saw = 'editor open=$editor, records ${after - before} more';
        if (!editor && after == before) {
          throw StateError('Duplicate opened nothing and saved nothing');
        }
      });
      await closeOpenEditor(tester);

      await log.step('SC-PO-012 Close an Approved order', () async {
        await openOrders();
        await selectRow(tester, docNumber(forClose));
        final String said = await pressWithReason(tester, 'Close');
        final String st = await statusOf('${forClose['id']}');
        log.saw = 'status $st, screen says "$said"';
        if (st != 'CLOSED') throw StateError('status $st');
      });

      await log.step('SC-PO-013 Cancel', () async {
        await openOrders();
        await selectRow(tester, docNumber(forCancel));
        final String said = await pressWithReason(tester, 'Cancel');
        final String st = await statusOf('${forCancel['id']}');
        log.saw = 'Cancel: status $st, says "$said"';
        if (st != 'CANCELLED') throw StateError('status $st after Cancel');
        await selectRow(tester, docNumber(forCancel));
        log.saw = '${log.saw}; Restore on the Cancelled row is '
            '${buttonState(tester, 'Restore')} (it is for deleted orders)';
      });
      log.skip('SC-PO-014', 'Restore brings back a deleted order, not a '
          'Cancelled one; there is no way back from Cancelled on screen');

      await log.step('SC-PO-016 Below reorder level opens a dialog', () async {
        await openOrders();
        await tapButtonOrMenu(tester, 'Below reorder level…');
        await pumpFor(tester, const Duration(seconds: 2));
        final bool dialog = find.byType(Dialog).evaluate().isNotEmpty;
        log.saw = 'dialog open=$dialog: ${dialogText(tester)}';
        await closeOpenEditor(tester);
        if (!dialog) throw StateError('nothing opened');
      });

      // -- Multi-user -----------------------------------------------------
      await log.step('SC-PO-039 stale Approve after another user approved',
          () async {
        await openOrders();
        await selectRow(tester, docNumber(forStale));
        await apiAct(await asUser('qpmgr'), 'purchases', '${forStale['id']}',
            'approve');
        await tapButton(tester, 'Approve');
        final String said = await watch(tester, seconds: 5);
        log.saw = 'status ${await statusOf('${forStale['id']}')}, screen '
            'says "$said"';
        if (said.isEmpty) throw StateError('N1: stale Approve said nothing');
      });

      await log.step('SC-PO-040 another user approves; Refresh shows it',
          () async {
        await openOrders();
        await apiAct(await asUser('qpmgr'), 'purchases', '${forList['id']}',
            'approve');
        await refreshList(tester);
        final List<String> texts = rowOf(tester, docNumber(forList));
        log.saw = 'row reads: ${texts.join(' | ')}';
        if (!texts.any((String t) => t.toLowerCase().startsWith('approved'))) {
          throw StateError('row did not show Approved: ${texts.join(' | ')}');
        }
      });

      await log.step('SC-PO-038 stale save after another user submitted',
          () async {
        await openOrders();
        await selectRow(tester, docNumber(forRace));
        await tapButton(tester, 'Edit');
        await pumpFor(tester, const Duration(seconds: 2));
        await apiAct(await asUser('qpmgr'), 'purchases', '${forRace['id']}',
            'submit');
        await typeInKeyed(tester, 'purchase-order-qty-', '13');
        final Set<String> before = textOnScreen(tester).toSet();
        await tapKey(tester, 'purchase-order-save');
        final String said = await watch(tester, confirm: false, seconds: 5);
        final String fresh = textOnScreen(tester)
            .where((String t) => t.length < 260 && !before.contains(t))
            .join(' | ');
        final bool open = find
            .byKey(const ValueKey<String>('purchase-order-save'))
            .evaluate()
            .isNotEmpty;
        final Json now = await admin.one('purchases', '${forRace['id']}');
        final double qty = num2(
            ((now['lines'] as List<dynamic>).first as Json)['ordered_quantity']);
        log.saw = 'editor open=$open; status ${now['status']}; quantity '
            '$qty; says "$said" / "$fresh"';
        if (!open && qty == 13) {
          throw StateError('HIGH: a save from a stale copy went through over '
              'the other user\'s submit (status ${now['status']})');
        }
        if (said.isEmpty && fresh.isEmpty) {
          throw StateError('N1: the stale save said nothing');
        }
      });
      await closeOpenEditor(tester);

      log.skip('SC-PO-006', 'no rate contract in the fixture firm');
      log.skip('SC-PO-007', 'no supplier scheme in the fixture firm');
      log.skip('SC-PO-008', 'no foreign currency supplier');
      log.skip('SC-PO-015', 'grid tick boxes not reached (same as SC-SO-013)');
      log.skip('SC-PO-017', 'saved searches not driven');
      log.skip('SC-PO-021', 'Expected by is a date picker limited to future '
          'days; not driven');
      log.skip('SC-PO-022', 'no inactive supplier in the fixture firm');
      log.skip('SC-PO-025', 'no budget set in the fixture firm');
      log.skip('SC-PO-026', 'no approval limits set in the fixture firm');
      log.skip('SC-PO-030', 'no rate contract in the fixture firm');
      log.skip('SC-PO-037', 'covered by SC-PO-039/040 and the GR file');
    } else {
      final Map<String, List<String>> menu = await offeredMenu(tester);
      // ignore: avoid_print
      print('FLOW: MENU [$itHandle] ${menu.entries.map((MapEntry<String, List<String>> e) => '${e.key}=${e.value.join(',')}').join('; ')}');
      final bool offered = menuHas(menu, menuPath);
      final ({int status, String text}) api =
          await me.attempt('GET', '/api/v1/purchases?page_size=1', null);
      final Json sub = await apiPo(admin, stage: 'submitted');
      Future<void> openAndSelect() async {
        await openOrders();
        await selectRow(tester, docNumber(sub));
      }

      Map<String, String> buttons(List<String> names) => <String, String>{
            for (final String b in names) b: buttonState(tester, b),
          };

      if (itHandle == 'qpexe') {
        await log.step('SC-PO-032 PU: New and Submit offered, Approve not',
            () async {
          log.saw = 'offered: $offered; list ${api.status}';
          if (!offered) throw StateError('Purchase Orders not offered to PU');
          await openAndSelect();
          final Map<String, String> s =
              buttons(<String>['+ New', 'New', 'Submit', 'Approve', 'Cancel']);
          log.saw = '${log.saw}; $s';
          if (s['Approve'] == 'enabled') {
            throw StateError('PU is offered Approve (SC-PO-023): $s');
          }
        });
      } else if (itHandle == 'qpmgr') {
        await log.step('SC-PO-033 PM: Approve, Amend, Close offered', () async {
          log.saw = 'offered: $offered';
          if (!offered) throw StateError('not offered to PM');
          await openAndSelect();
          final Map<String, String> s =
              buttons(<String>['Approve', 'Amend', 'Close', 'Cancel']);
          log.saw = '${log.saw}; $s';
          if (s['Approve'] != 'enabled') {
            throw StateError('Approve not offered to PM on a Submitted order');
          }
        });
      } else if (itHandle == 'qstore') {
        await log.step('SC-PO-034 WH: Purchase Orders offered or not',
            () async {
          log.saw = 'offered: $offered; list answers ${api.status}';
          if (offered != (api.status == 200)) {
            throw StateError('menu ($offered) and server (${api.status}) '
                'disagree');
          }
        });
      } else if (itHandle == 'qsexe') {
        await log.step('SC-PO-035 FS: nothing offered in Buy', () async {
          log.saw = 'Purchase Orders offered: $offered; buy menu '
              '${menu['buy']}; list answers ${api.status}';
          if (offered) throw StateError('Purchase Orders offered to FS');
        });
      } else if (itHandle == 'qro') {
        await log.step('SC-PO-036 RO: rows readable, no write buttons',
            () async {
          log.saw = 'offered: $offered';
          if (!offered) throw StateError('not offered to Read Only');
          await openAndSelect();
          final Map<String, String> s = buttons(<String>[
            '+ New', 'New', 'Submit', 'Approve', 'Edit', 'Cancel', 'Close'
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

/// A completed receipt and an approved bill on [po], so it has a bill on it.
Future<Json> apiApprovedBillFrom(Server server, Json po) async {
  final Json gr = await apiReceiptOf(server, po, quantity: 10);
  final Json draft = await apiBill(server, gr);
  await apiAct(server, 'purchase-invoices', '${draft['id']}', 'approve');
  return server.one('purchase-invoices', '${draft['id']}');
}
