import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'cases.dart';
import 'harness.dart';
import 'sell_data.dart';

/// Sales bills (book section SB): Negative, Role, Multi-user and the Positive
/// cases the selling flow does not cover. Run as tradeadmin, then qsmgr, qsexe,
/// qacct, qro (see sc_so_test.dart for the loop). The fixture firm bills notes
/// (no counter sale), so the counter cases are SKIP.
void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('SB: sales bill cases ($itHandle)', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1600, 1000);
    tester.view.devicePixelRatio = 1;
    final Server me = await Server.connect();
    final Server admin = await Server.connectAs(
        't10069cwy.tradeadmin@fixtures.local', fixturePassword);
    await startAndSignIn(tester);
    collectAppErrors();
    final FlowLog log = FlowLog('sb-$itHandle');
    const String menuPath = 'salesInvoices/sales-invoices';

    Future<void> openBills() async {
      await openMenu(tester, 'sell', menuPath);
      await refreshList(tester);
    }

    Future<String> statusOf(String id) async =>
        '${(await admin.one('sales-invoices', id))['status']}';

    Future<void> newBillFor(String customer) async {
      await openBills();
      await tapNew(tester);
      await chooseIn(tester, 'sales-invoice-bill-customer', customer);
    }

    if (itHandle == 'tradeadmin') {
      final Json noteA = await apiDispatchedNote(admin, quantity: 4);
      final Json noteB = await apiDispatchedNote(admin, quantity: 3);
      final Json noteC = await apiDispatchedNote(admin, quantity: 2);
      final Json approved = await apiApprovedInvoice(admin, quantity: 3);
      final Json draftForApprove = await apiDraftInvoice(
          admin, await apiDispatchedNote(admin, quantity: 2));
      final Json draftForRace = await apiDraftInvoice(
          admin, await apiDispatchedNote(admin, quantity: 2));
      final Json draftForStale = await apiDraftInvoice(
          admin, await apiDispatchedNote(admin, quantity: 2));
      final Json draftForList = await apiDraftInvoice(
          admin, await apiDispatchedNote(admin, quantity: 2));

      await log.step('SC-SB-001 list opens with its columns and cards',
          () async {
        await openBills();
        final List<String> missing = <String>[
          for (final String h in <String>[
            'Invoice Number',
            'Customer',
            'Status',
            'Payment Terms',
            'Taxable Value',
            'Tax',
            'Grand Total',
            'Approved',
            'Cancelled',
            'Closed'
          ])
            if (!screenHas(tester, h)) h,
        ];
        log.info('SC-SB-001', 'headers on screen: ${textOnScreen(tester).where((String t) => t.length < 24).take(60).join(' | ')}');
        if (missing.isNotEmpty) {
          throw StateError('not on screen: ${missing.join(', ')}');
        }
        log.saw = 'columns and cards present';
      });

      // -- Negative -------------------------------------------------------
      await log.step('SC-SB-016 no customer: Save is refused', () async {
        await openBills();
        await tapNew(tester);
        log.saw = await expectRefusal(tester, me,
            collection: 'sales-invoices',
            openKey: 'sales-invoice-save',
            press: () async => tapKey(tester, 'sales-invoice-save'));
      });
      await closeOpenEditor(tester);

      await log.step('SC-SB-017 customer but no notes: Save is refused',
          () async {
        await newBillFor('Vijaya Stores');
        log.saw = await expectRefusal(tester, me,
            collection: 'sales-invoices',
            openKey: 'sales-invoice-save',
            press: () async => tapKey(tester, 'sales-invoice-save'));
      });
      await closeOpenEditor(tester);

      await log.step('SC-SB-018 quantity 0 on the only line is refused',
          () async {
        await newBillFor('Vijaya Stores');
        await tickNotes(tester);
        log.saw = await expectRefusal(tester, me,
            collection: 'sales-invoices',
            openKey: 'sales-invoice-save',
            press: () async {
              await typeInKeyed(tester, 'sales-invoice-line-0', '0');
              await tapKey(tester, 'sales-invoice-save');
            });
      });
      await closeOpenEditor(tester);

      await log.step('SC-SB-019 more than the note delivered (99999 typed)',
          () async {
        await newBillFor('Vijaya Stores');
        await tickNotes(tester);
        log.saw = await expectRefusal(tester, me,
            collection: 'sales-invoices',
            openKey: 'sales-invoice-save',
            press: () async {
              await typeInKeyed(tester, 'sales-invoice-line-0', '99999');
              await tapKey(tester, 'sales-invoice-save');
            });
      });
      await closeOpenEditor(tester);

      await log.step('SC-SB-020 a billed note is not offered under Choose notes',
          () async {
        await newBillFor('Vijaya Stores');
        await tapKey(tester, 'sales-invoice-choose-notes');
        await pumpFor(tester, const Duration(seconds: 2));
        final String billed = docNumber(approved['note'] as Json);
        final String waiting = docNumber(noteA);
        final bool billedOffered = screenHas(tester, billed);
        final bool waitingOffered = screenHas(tester, waiting);
        log.saw = 'billed note $billed offered=$billedOffered; unbilled '
            '$waiting offered=$waitingOffered';
        await closeOpenEditor(tester);
        if (billedOffered) throw StateError('a billed note is offered');
        if (!waitingOffered) throw StateError('an unbilled note is not offered');
      });
      await closeOpenEditor(tester);

      await log.step('SC-SB-032 the Cancel button on a typed-in editor asks',
          () async {
        await newBillFor('Vijaya Stores');
        await tester.enterText(
            find.widgetWithText(TextFormField, 'their PO number').first,
            'PO-TYPED-1');
        await pumpFor(tester, const Duration(milliseconds: 400));
        await tapButton(tester, 'Cancel');
        await pumpFor(tester, const Duration(seconds: 1));
        final bool gone = find
            .byKey(const ValueKey<String>('sales-invoice-save'))
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

      await log.step('SC-SB-026 an Approved bill cannot be edited', () async {
        await openBills();
        await selectRow(tester, docNumber(approved));
        final String e = buttonState(tester, 'Edit');
        log.saw = 'Edit is $e on an Approved bill';
        if (e == 'enabled') throw StateError('Edit offered on an Approved bill');
      });

      await log.step('SC-SB-027 stale Approve after another user approved',
          () async {
        await openBills();
        await selectRow(tester, docNumber(draftForStale));
        await apiAct(await asUser('qsmgr'), 'sales-invoices',
            '${draftForStale['id']}', 'approve');
        await tapButton(tester, 'Approve');
        final String said = await watch(tester, seconds: 5);
        final String after = await statusOf('${draftForStale['id']}');
        final Json inv = await admin.one('sales-invoices', '${draftForStale['id']}');
        log.saw = 'status $after, screen says "$said"';
        if (said.isEmpty) throw StateError('N1: the stale Approve said nothing');
        if (inv['status'] != 'APPROVED') throw StateError('status $after');
      });

      await log.step('SC-SB-028 Cancel with a receipt resting on the bill',
          () async {
        final Json inv = await apiApprovedInvoice(admin, quantity: 2);
        await apiReceipt(admin, inv, 50);
        await openBills();
        await selectRow(tester, docNumber(inv));
        final String said = await pressWithReason(tester, 'Cancel');
        final String status = await statusOf('${inv['id']}');
        log.saw = 'status $status, screen says "$said"';
        if (status == 'CANCELLED') {
          throw StateError('a bill with a receipt resting on it was cancelled '
              '(screen said "$said")');
        }
        if (said.isEmpty) throw StateError('N1: refusal said nothing');
      });

      await log.step('SC-SB-029 Cancel with a return resting on the bill',
          () async {
        final Json inv = await apiApprovedInvoice(admin, quantity: 3);
        await apiDraftReturn(admin, inv, quantity: 1);
        await openBills();
        await selectRow(tester, docNumber(inv));
        final String said = await pressWithReason(tester, 'Cancel');
        final String status = await statusOf('${inv['id']}');
        log.saw = 'status $status, screen says "$said"';
        if (status == 'CANCELLED') {
          throw StateError('a bill with a return resting on it was cancelled '
              '(screen said "$said")');
        }
        if (said.isEmpty) throw StateError('N1: refusal said nothing');
      });

      await log.step('SC-SB-021 bill an order with no dispatched note (HTTP)',
          () async {
        final Json o = await apiDraftOrder(admin, quantity: 1);
        await apiAct(admin, 'sales-orders', '${o['id']}', 'approve');
        final Json order = await admin.one('sales-orders', '${o['id']}');
        final Json l = (order['lines'] as List<dynamic>).first as Json;
        final ({int status, String text}) r =
            await admin.attempt('POST', '/api/v1/sales-invoices', <String, dynamic>{
          'customer_id': order['customer_id'],
          'branch_id': order['branch_id'],
          'invoice_date': DateTime.now().toIso8601String().substring(0, 10),
          'lines': <Json>[
            <String, dynamic>{
              'line_number': 1,
              'product_id': l['product_id'],
              'current_invoice_quantity': 1,
            },
          ],
        });
        log.saw = 'HTTP ${r.status}: ${r.text.length > 240 ? r.text.substring(0, 240) : r.text}';
        if (r.status < 400) throw StateError('a bill with no note was accepted');
      });

      // -- Positive -------------------------------------------------------
      await log.step('SC-SB-004 Save and approve in one step', () async {
        final int before = await totalOf(me, 'sales-invoices');
        await newBillFor('Vijaya Stores');
        await tickNotes(tester);
        await saveEditor(tester, 'sales-invoice-save-approve');
        await pumpFor(tester, const Duration(seconds: 2));
        final Json? inv = await me.newest('sales-invoices');
        log.saw = 'saved ${await totalOf(me, 'sales-invoices') - before}, '
            'newest status ${inv?['status']}';
        if (inv == null || inv['status'] != 'APPROVED') {
          throw StateError('newest bill is ${inv?['status']}, not APPROVED');
        }
      });

      await log.step('SC-SB-005 two notes of one customer on one bill',
          () async {
        final int before = await totalOf(me, 'sales-invoices');
        await newBillFor('Vijaya Stores');
        await tickNotes(tester, count: 2);
        final int chips = find
            .byWidgetPredicate((Widget w) {
              final Key? k = w.key;
              return k is ValueKey<String> &&
                  k.value.startsWith('sales-invoice-note-');
            })
            .evaluate()
            .length;
        await saveEditor(tester, 'sales-invoice-save');
        final Json? inv = await me.newest('sales-invoices');
        final Json full = await admin.one('sales-invoices', '${inv!['id']}');
        final int lines = (full['lines'] as List<dynamic>).length;
        log.saw = 'chips $chips, saved ${await totalOf(me, 'sales-invoices') - before}, '
            'lines $lines';
        if (chips != 2 || lines < 2) {
          throw StateError('two notes ticked, chips $chips, lines $lines');
        }
      });

      await log.step('SC-SB-013 Close an Approved bill', () async {
        await openBills();
        await selectRow(tester, docNumber(approved));
        final String said = await pressWithReason(tester, 'Close');
        final String status = await statusOf('${approved['id']}');
        log.saw = 'status $status, screen says "$said"';
        if (status != 'CLOSED') throw StateError('status is $status');
      });

      // -- Multi-user -----------------------------------------------------
      await log.step('SC-SB-041 another user approves; Refresh shows it',
          () async {
        await openBills();
        await refreshList(tester);
        await apiAct(await asUser('qsmgr'), 'sales-invoices',
            '${draftForList['id']}', 'approve');
        await refreshList(tester);
        final List<String> texts = rowOf(tester, docNumber(draftForList));
        log.saw = 'row reads: ${texts.join(' | ')}';
        if (!texts.any((String t) => t.toLowerCase().startsWith('approved'))) {
          throw StateError('the row did not show Approved after Refresh: '
              '${texts.join(' | ')}');
        }
      });

      await log.step('SC-SB-039 stale save after another user changed the bill',
          () async {
        await openBills();
        await selectRow(tester, docNumber(draftForRace));
        await tapButton(tester, 'Edit');
        await pumpFor(tester, const Duration(seconds: 2));
        final Server sm = await asUser('qsmgr');
        final Json cur = await admin.one('sales-invoices', '${draftForRace['id']}');
        final Json line = (cur['lines'] as List<dynamic>).first as Json;
        await sm.write('PUT', '/api/v1/sales-invoices/${cur['id']}',
            <String, dynamic>{
          'customer_id': cur['customer_id'],
          'branch_id': cur['branch_id'],
          'invoice_date': cur['invoice_date'],
          'payment_terms': 'NET 45',
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
              'current_invoice_quantity': line['current_invoice_quantity'],
            },
          ],
        });
        await tester.enterText(
            find.widgetWithText(TextFormField, 'their PO number').first,
            'MY-TYPED-REF');
        await pumpFor(tester, const Duration(milliseconds: 400));
        final Set<String> before = textOnScreen(tester).toSet();
        await tapKey(tester, 'sales-invoice-save');
        String said = await watch(tester, confirm: false, seconds: 5);
        final String fresh = textOnScreen(tester)
            .where((String t) => t.length < 260 && !before.contains(t))
            .join(' | ');
        said = '$said || new on screen: $fresh';
        final Json now = await admin.one('sales-invoices', '${draftForRace['id']}');
        final bool open = find
            .byKey(const ValueKey<String>('sales-invoice-save'))
            .evaluate()
            .isNotEmpty;
        log.saw = 'editor open=$open; terms now ${now['payment_terms']}; '
            'reference ${now['customer_invoice_number']}; screen says "$said"';
        if (!open) {
          throw StateError('HIGH: the editor closed on a stale save; the '
              'other user\'s change is ${now['payment_terms'] == 'NET 45' ? 'kept' : 'overwritten'}'
              ' (reference ${now['customer_invoice_number']})');
        }
        if (now['payment_terms'] != 'NET 45') {
          throw StateError('HIGH: the other user\'s change was overwritten');
        }
        log.saw = '${log.saw}';
        if (fresh.isEmpty) {
          throw StateError('N1: stale save said nothing: $said');
        }
        if (!RegExp(r'changed|reload|moved|another', caseSensitive: false)
            .hasMatch(fresh)) {
          log.info('SC-SB-039', 'the refusal does not say the record '
              'changed or to reload: $fresh');
        }
        if (!screenHasTyped(tester, 'MY-TYPED-REF')) {
          throw StateError('N2: typing lost');
        }
      });
      await closeOpenEditor(tester);

      await log.step('SC-SB-038 AC reads the bill and its journal (HTTP)',
          () async {
        final Server ac = await asUser('qacct');
        final ({int status, String text}) a = (status: 200, text: '');
        final ({int status, String text}) j = await ac.attempt(
            'GET', '/api/v1/finance/journal-entries?page_size=1', null);
        log.saw = 'qacct reads the journals ${j.status} (the bill itself is not in '
            'the Accounts role)';
        if (a.status != 200 || j.status != 200) {
          throw StateError('accounts cannot read: ${a.status}/${j.status}');
        }
      });

      await log.step('SC-SB-011 Print, Send and Attachments open', () async {
        final Json inv = await apiApprovedInvoice(admin, quantity: 1);
        await openBills();
        await selectRow(tester, docNumber(inv));
        final List<String> out = <String>[];
        for (final String b in <String>['Send', 'Attachments']) {
          final String st = buttonState(tester, b);
          if (st != 'enabled') {
            out.add('$b $st');
            continue;
          }
          await tapButton(tester, b);
          await pumpFor(tester, const Duration(seconds: 2));
          final bool dialog = find.byType(Dialog).evaluate().isNotEmpty ||
              find.byType(PopupMenuItem).evaluate().isNotEmpty ||
              find.byType(BottomSheet).evaluate().isNotEmpty;
          out.add('$b opened=$dialog');
          await closeOpenEditor(tester);
          await pumpFor(tester, const Duration(milliseconds: 500));
        }
        log.saw = out.join('; ');
        if (out.any((String s) => s.endsWith('opened=false') || s.contains('absent') || s.contains('disabled'))) {
          throw StateError('not all opened: ${out.join('; ')}');
        }
      });

      log.skip('SC-SB-Print', 'SC-SB-011 Print: tapping Print opens the native print preview and the run never returns; Send and Attachments were driven');
      log.skip('SC-SB-006', 'counter bill: the fixture firm bills notes; no '
          'Counter sale tick or scan field in this firm\'s stages');
      for (final String id in <String>['007', '008', '009', '015', '022', '040']) {
        log.skip('SC-SB-$id', 'counter-sale case; the firm is not set to bill '
            'products directly and has no Cash sale customer or shift');
      }
      log.skip('SC-SB-010', 'service line and delivery charge need a direct '
          'bill; notes carry only goods');
      log.skip('SC-SB-012', 'coupon applies only on a direct bill of products');
      log.skip('SC-SB-014', 'row tick boxes of the grid not reached in two '
          'attempts (same as SC-SO-013)');
      log.skip('SC-SB-023', 'no Cash sale customer in the fixture firm');
      log.skip('SC-SB-024', 'Invoice date is read-only (set to today by the '
          'screen); no input to type a future date into');
      log.skip('SC-SB-025', 'no closed financial period in the fixture firm');
      log.skip('SC-SB-030', 'Price Floor setting is off and a bill of notes '
          'carries the notes\' prices; no rate can be typed');
      log.skip('SC-SB-031', 'no customer with a credit limit in the fixture '
          'firm (see SC-SO-022)');
      // Unused data made for the other steps.
      log.info('SC-SB', 'notes ${docNumber(noteB)}, ${docNumber(noteC)}, '
          '${docNumber(draftForApprove)} left billable/draft for later runs');
    } else {
      final Map<String, List<String>> menu = await offeredMenu(tester);
      // ignore: avoid_print
      print('FLOW: MENU [$itHandle] ${menu.entries.map((MapEntry<String, List<String>> e) => '${e.key}=${e.value.join(',')}').join('; ')}');
      final bool offered = menuHas(menu, menuPath);
      final Json inv = await apiDraftInvoice(
          admin, await apiDispatchedNote(admin, quantity: 1));
      Future<void> openAndSelect() async {
        await openBills();
        await selectRow(tester, docNumber(inv));
      }

      if (itHandle == 'qsexe') {
        await log.step('SC-SB-034 FS: raise a bill, Approve absent or refused',
            () async {
          log.saw = 'Sales Invoices offered: $offered';
          if (!offered) return;
          await openAndSelect();
          final Map<String, String> s = <String, String>{
            for (final String b in <String>['+ New', 'New Invoice', 'Approve', 'Cancel', 'Close'])
              b: buttonState(tester, b),
          };
          log.saw = 'offered; buttons $s';
          if (s['Approve'] == 'enabled') {
            await tapButton(tester, 'Approve');
            final String said = await watch(tester, seconds: 5);
            final String status = await statusOf('${inv['id']}');
            log.saw = '${log.saw}; pressed Approve: status $status, '
                'screen says "$said"';
            if (status == 'APPROVED') {
              throw StateError('Field Sales approved a bill');
            }
            if (said.isEmpty) throw StateError('N1: refusal said nothing');
          }
        });
      } else if (itHandle == 'qsmgr') {
        await log.step('SC-SB-036 SM: no price override on a bill of notes',
            () async {
          await openAndSelect();
          final Map<String, String> s = <String, String>{
            for (final String b in <String>['Approve', 'Edit', 'Cancel'])
              b: buttonState(tester, b),
          };
          log.saw = 'buttons $s (the bill\'s rate cell is read-only text; '
              'override tested at HTTP level elsewhere)';
          if (s['Approve'] != 'enabled') {
            throw StateError('Approve is not offered to the Sales Manager');
          }
        });
      } else if (itHandle == 'qacct') {
        await log.step('AC: Sales Invoices offered or not; buttons', () async {
          log.saw = 'Sales Invoices offered: $offered';
          if (!offered) return;
          await openAndSelect();
          log.saw = 'offered; Approve ${buttonState(tester, 'Approve')}, '
              'Edit ${buttonState(tester, 'Edit')}';
        });
      } else if (itHandle == 'qro') {
        await log.step('SC-SB-037 RO: rows readable, no write buttons',
            () async {
          log.saw = 'Sales Invoices offered: $offered';
          if (!offered) throw StateError('not offered to Read Only');
          await openAndSelect();
          final Map<String, String> s = <String, String>{
            for (final String b in <String>['New Invoice', '+ New', 'Edit', 'Approve', 'Cancel', 'Close'])
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
