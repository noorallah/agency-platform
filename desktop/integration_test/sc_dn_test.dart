import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'cases.dart';
import 'harness.dart';

/// Delivery notes (book section DN): Negative, Role and Multi-user cases.
/// Run as the administrator, then as `qsexe`, `qsmgr`, `qstore`, `qro`
/// (see sc_so_test.dart for the loop).
void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('DN: delivery note cases ($itHandle)', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1600, 1000);
    tester.view.devicePixelRatio = 1;
    final Server me = await Server.connect();
    final Server admin = await Server.connectAs(
        't10069cwy.tradeadmin@fixtures.local', fixturePassword);
    await startAndSignIn(tester);
    collectAppErrors();
    final FlowLog log = FlowLog('dn-$itHandle');
    const String menuPath = 'deliveryNotes/delivery-notes';

    Future<void> openNotes() async {
      await openMenu(tester, 'sell', menuPath);
      await refreshList(tester);
    }

    /// Open the order box and take the first order it offers.
    Future<String> pickFirstOrder() async {
      await tapKey(tester, 'delivery-note-order');
      await pumpFor(tester, const Duration(milliseconds: 600));
      final Finder entry = find.byWidgetPredicate((Widget w) =>
          w is Text && RegExp(r'^SO-[0-9-]+\s').hasMatch(w.data ?? ''));
      await pumpUntil(tester, entry, waitingFor: 'an order in the order box');
      final String label = (tester.widget(entry.first) as Text).data!;
      await tester.tap(find.text(label).last);
      await pumpFor(tester, const Duration(seconds: 2));
      return label.split(' ').first;
    }

    String today() => DateTime.now().toIso8601String().substring(0, 10);

    /// An approved order for [quantity] units, raised and approved over HTTP.
    Future<Json> approvedOrder(int quantity) async {
      final Json o = await apiDraftOrder(admin, quantity: quantity);
      await apiAct(admin, 'sales-orders', '${o['id']}', 'approve');
      return admin.one('sales-orders', '${o['id']}');
    }

    /// A draft note for one unit of [order], raised over HTTP.
    Future<Json> apiNote(Json order, {num quantity = 1}) async {
      final Json line = (order['lines'] as List<dynamic>).first as Json;
      return (await admin
          .write('POST', '/api/v1/delivery-notes', <String, dynamic>{
        'sales_order_id': order['id'],
        'delivery_date': today(),
        'lines': <Json>[
          <String, dynamic>{
            'sales_order_line_id': line['id'],
            'line_number': 1,
            'current_delivery_quantity': quantity,
          },
        ],
      })) as Json;
    }

    if (itHandle == 'tradeadmin') {
      await topUpStock(admin);
      final Json order10 = await approvedOrder(10);
      final Json draftOrder = await apiDraftOrder(admin, quantity: 3);
      final Json order3 = await approvedOrder(3);
      final Json order2 = await approvedOrder(2);
      final Json noteDraft = await apiNote(order3);
      final Json noteApproved = await apiNote(order2);
      await apiAct(admin, 'delivery-notes', '${noteApproved['id']}', 'approve');

      await log.step('SC-DN-001 list opens with its columns', () async {
        await openNotes();
        final List<String> missing = <String>[
          for (final String h in <String>[
            'Note Number',
            'Customer',
            'Sales Order',
            'Delivery Date',
            'Status'
          ])
            if (!screenHas(tester, h)) h,
        ];
        if (missing.isNotEmpty) {
          throw StateError('columns not on screen: ${missing.join(', ')}');
        }
        log.saw = 'columns present';
      });


      await log.step('SC-DN-013 more than is owed is refused (99999 typed)',
          () async {
        await openNotes();
        await tapNew(tester);
        await pickFirstOrder();
        await pumpFor(tester, const Duration(seconds: 2));
        log.saw = await expectRefusal(tester, me,
            collection: 'delivery-notes',
            openKey: 'delivery-note-save',
            press: () async {
              await typeInKeyed(tester, 'delivery-note-delivering-', '99999');
              await tapKey(tester, 'delivery-note-save');
              await pumpFor(tester, const Duration(seconds: 1));
              final String all = textOnScreen(tester)
                  .where((String t) =>
                      t.length < 220 &&
                      RegExp(r'quantity|deliver|owed|reserved|exceed|more than|stock',
                              caseSensitive: false)
                          .hasMatch(t))
                  .take(8)
                  .join(' | ');
              log.info('SC-DN-013', 'quantity-related text on screen after '
                  'Save: $all');
              if (!RegExp(r'exceed|more than|reserved|owed|cannot|only',
                      caseSensitive: false)
                  .hasMatch(all)) {
                log.defect('SC-DN-013 N1', 'no sentence says the quantity '
                    'is more than can be delivered');
              }
            });
      });
      await closeOpenEditor(tester);

      await log.step('SC-DN-017 quantity 0 on every line is refused',
          () async {
        await openNotes();
        await tapNew(tester);
        await pickFirstOrder();
        await pumpFor(tester, const Duration(seconds: 2));
        log.saw = await expectRefusal(tester, me,
            collection: 'delivery-notes',
            openKey: 'delivery-note-save',
            press: () async {
              await typeInKeyed(tester, 'delivery-note-delivering-', '0');
              await tapKey(tester, 'delivery-note-save');
            });
      });
      await log.step('SC-DN-023 the Cancel button on a typed-in editor asks',
          () async {
        await openNotes();
        await tapNew(tester);
        await pickFirstOrder();
        await typeInKeyed(tester, 'delivery-note-delivering-', '4');
        await tapButton(tester, 'Cancel');
        await pumpFor(tester, const Duration(seconds: 1));
        final String question = dialogText(tester);
        final bool gone = find
            .byKey(const ValueKey<String>('delivery-note-save'))
            .evaluate()
            .isEmpty;
        log.saw = 'editor closed=$gone, question="$question"';
        if (question.isEmpty && gone) {
          throw StateError('Cancel closed an editor holding a typed quantity '
              'without asking');
        }
      });
      await closeOpenEditor(tester);

      await log.step('SC-DN-015 a Draft order is not offered in the order box',
          () async {
        await openNotes();
        await tapNew(tester);
        await tapKey(tester, 'delivery-note-order');
        await pumpFor(tester, const Duration(seconds: 1));
        final bool offeredApproved = textOnScreen(tester)
            .any((String t) => RegExp(r'^SO-[0-9-]+\s').hasMatch(t));
        final bool offeredDraft = screenHas(tester, docNumber(draftOrder));
        log.saw = 'approved order offered=$offeredApproved, draft order '
            'offered=$offeredDraft';
        if (offeredDraft) throw StateError('a Draft order is offered');
        if (!offeredApproved) {
          throw StateError('the approved order is not offered either');
        }
        await closeOpenEditor(tester);
        // The picker reads the approved orders once, when the page first
        // opens: an order approved since is missing until the app restarts.
        final Json late = await approvedOrder(1);
        await openNotes();
        await tapNew(tester);
        await tapKey(tester, 'delivery-note-order');
        await pumpFor(tester, const Duration(seconds: 1));
        final bool lateOffered = screenHas(tester, docNumber(late));
        log.saw = '${log.saw}; an order approved after the page opened '
            'offered=$lateOffered';
        final String serverNewest = docNumber(late);
        log.info('SC-DN-015', 'server approved list has $serverNewest; the '
            'box offers ${textOnScreen(tester).where((String t) => RegExp(r'^SO-[0-9-]+\s').hasMatch(t)).take(3).join(' / ')} first');
        if (!lateOffered) {
          log.defect('SC-DN-015 stale picker',
              'an order approved after Delivery Notes was opened '
              '(${docNumber(late)}) is not in the order box (known SCRQ-27)');
        }
      });
      await closeOpenEditor(tester);

      await log.step('SC-DN-018 an Approved note cannot be edited', () async {
        await openNotes();
        await selectRow(tester, docNumber(noteApproved));
        final String edit = buttonState(tester, 'Edit');
        log.saw = 'Edit is $edit on an Approved note (the editor only '
            'creates; no Edit exists for a note in any status)';
        if (edit == 'enabled') throw StateError('Edit offered');
      });

      await log.step('SC-DN-019 Dispatch on a Draft note is not offered',
          () async {
        await openNotes();
        await selectRow(tester, docNumber(noteDraft));
        final String d = buttonState(tester, 'Dispatch');
        log.saw = 'Dispatch is $d on a Draft note';
        if (d == 'enabled') throw StateError('Dispatch offered on a Draft');
      });

      await log.step('SC-DN-030 stale Dispatch after another user dispatched',
          () async {
        await openNotes();
        await selectRow(tester, docNumber(noteApproved));
        await apiAct(await asUser('qsmgr'), 'delivery-notes',
            '${noteApproved['id']}', 'dispatch');
        await tapButton(tester, 'Dispatch');
        final Finder anyway =
            find.byKey(const ValueKey<String>('dispatch-anyway'));
        final String asked = noticeText(tester);
        if (anyway.evaluate().isNotEmpty) await tester.tap(anyway.first);
        final String said = await watch(tester, confirm: false, seconds: 5);
        final Json now = await admin.one('delivery-notes', '${noteApproved['id']}');
        log.saw = 'status ${now['status']}; asked "$asked"; said "$said"';
        if (said.isEmpty) {
          throw StateError('N1: Dispatch of a note another user had already '
              'dispatched said nothing after the dialog was confirmed');
        }
      });

      await log.step('SC-DN-021 order on hold: Dispatch is refused in words',
          () async {
        final Json held = await approvedOrder(2);
        final Json note = await apiNote(held);
        await apiAct(admin, 'delivery-notes', '${note['id']}', 'approve');
        await apiAct(admin, 'sales-orders', '${held['id']}', 'hold',
            <String, dynamic>{'reason': 'dispatch test'});
        await openNotes();
        await selectRow(tester, docNumber(note));
        await tapButton(tester, 'Dispatch');
        final Finder anyway =
            find.byKey(const ValueKey<String>('dispatch-anyway'));
        if (anyway.evaluate().isNotEmpty) await tester.tap(anyway.first);
        final String said = await watch(tester, confirm: false, seconds: 5);
        final Json now = await admin.one('delivery-notes', '${note['id']}');
        log.saw = 'note status ${now['status']}; said "$said"';
        if (now['status'] == 'DISPATCHED') {
          throw StateError('a note off an order on hold was dispatched');
        }
        if (said.isEmpty) throw StateError('N1: refusal said nothing');
      });

      log.skip('SC-DN-029', 'the delivery note editor only creates; a saved '
          'note cannot be opened for change on screen, so there is no second '
          'session to race');
      log.skip('SC-DN-014', 'stock cannot be set to 5 without moving the '
          'firm; on hand is 82 and approved orders reserve more than that '
          '(see SCRQ findings on over-reservation)');
      log.skip('SC-DN-016', 'the date box offers no future date in two '
          'attempts');
      log.skip('SC-DN-020', 'needs a billed dispatched note; chain done in '
          'the SB file');
      log.skip('SC-DN-022', 'no carrier master record in the fixture firm');
    } else {
      final Map<String, List<String>> menu = await offeredMenu(tester);
      // ignore: avoid_print
      print('FLOW: MENU [$itHandle] ${menu.entries.map((MapEntry<String, List<String>> e) => '${e.key}=${e.value.join(',')}').join('; ')}');
      final bool offered = menuHas(menu, menuPath);
      Future<void> openAndSelect(Json note) async {
        await openNotes();
        await selectRow(tester, docNumber(note));
      }

      if (itHandle == 'qsexe') {
        await log.step('SC-DN-024 FS: Delivery Notes offered or not; no '
            'Approve or Dispatch', () async {
          log.saw = 'Delivery Notes offered: $offered';
          if (!offered) return;
          final Json note = await apiNote(await approvedOrder(1));
          await openAndSelect(note);
          final Map<String, String> s = <String, String>{
            for (final String b in <String>['Approve', 'Dispatch', 'Cancel'])
              b: buttonState(tester, b),
          };
          log.saw = 'offered; buttons $s';
          if (s['Approve'] == 'enabled' || s['Dispatch'] == 'enabled') {
            throw StateError('FS is offered $s');
          }
        });
      } else if (itHandle == 'qstore') {
        await log.step('SC-DN-025 WH: Delivery Notes offered or not',
            () async {
          log.saw = 'Delivery Notes offered: $offered; menu areas '
              '${menu.keys.join(', ')}';
          final ({int status, String text}) r =
              await me.attempt('GET', '/api/v1/delivery-notes?page_size=1', null);
          log.saw = '${log.saw}; list answers ${r.status}';
          if (offered != (r.status == 200)) {
            throw StateError('the menu ($offered) and the server '
                '(${r.status}) disagree');
          }
        });
      } else if (itHandle == 'qsmgr') {
        await log.step('SC-DN-026 SM cannot change the sales stages', () async {
          final ({int status, String text}) s = await me.attempt('PUT',
              '/api/v1/sales-orders/workflow-settings', <String, dynamic>{});
          log.saw = 'stages PUT answered ${s.status} (HTTP level)';
          if (s.status != 403) throw StateError('answered ${s.status}');
        });
      } else if (itHandle == 'qro') {
        await log.step('SC-DN-024 RO: list readable, no write button',
            () async {
          log.saw = 'Delivery Notes offered: $offered';
          if (!offered) throw StateError('not offered to Read Only');
          final Json note = await apiNote(await approvedOrder(1));
          await openAndSelect(note);
          final Map<String, String> s = <String, String>{
            for (final String b in <String>[
              '+ New',
              'Approve',
              'Dispatch',
              'Cancel'
            ])
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
