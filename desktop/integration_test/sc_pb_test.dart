import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'buy_data.dart';
import 'cases.dart';
import 'harness.dart';
import 'sell_data.dart';

/// Supplier bills (book section PB). Run as tradeadmin, then qpexe (PU),
/// qpmgr (PM), qacct (AC), qstore (WH), qro.
void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('PB: supplier bill cases ($itHandle)',
      (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1600, 1000);
    tester.view.devicePixelRatio = 1;
    final Server me = await Server.connect();
    final Server admin = await Server.connectAs(
        't10069cwy.tradeadmin@fixtures.local', fixturePassword);
    await startAndSignIn(tester);
    collectAppErrors();
    final FlowLog log = FlowLog('pb-$itHandle');
    const String menuPath = 'purchaseInvoices';

    Future<void> openBills() async {
      await openMenu(tester, 'buy', menuPath);
      await refreshList(tester);
    }

    Future<String> statusOf(String id) async =>
        '${(await admin.one('purchase-invoices', id))['status']}';

    Future<void> newBillFromSupplier() async {
      await openBills();
      await tapNew(tester);
      await chooseIn(
          tester, 'purchase-invoice-receipt-supplier', 'Principal supplier');
      await tester.enterText(
          find.byWidgetPredicate((Widget w) =>
              w is TextField && w.decoration?.hintText == 'as printed'),
          'SUP-${DateTime.now().millisecondsSinceEpoch}');
      await pumpFor(tester, const Duration(milliseconds: 300));
    }

    Future<void> tickReceipt() async {
      await tapKey(tester, 'purchase-invoice-choose-receipts');
      await pumpFor(tester, const Duration(seconds: 2));
      await tester.tap(find
          .descendant(of: find.byType(Dialog), matching: find.byType(Checkbox))
          .first);
      await pumpFor(tester, const Duration(milliseconds: 500));
      await confirmIfAsked(tester);
      await pumpFor(tester, const Duration(seconds: 3));
    }

    Future<String> refuse(Future<void> Function() typing) => expectRefusal(
        tester, me,
        collection: 'purchase-invoices',
        openKey: 'purchase-invoice-save',
        press: () async {
          await typing();
          await tapKey(tester, 'purchase-invoice-save');
        });

    Map<String, String> buttons(List<String> names) => <String, String>{
          for (final String b in names) b: buttonState(tester, b),
        };

    if (itHandle == 'tradeadmin') {
      final Json draftForApprove = await apiBill(
          admin, await apiReceiptOf(admin, await apiPo(admin)));
      final Json draftForPay = await apiBill(
          admin, await apiReceiptOf(admin, await apiPo(admin)));
      final Json draftForPayTooMuch = await apiBill(
          admin, await apiReceiptOf(admin, await apiPo(admin)));
      final Json draftStale = await apiBill(
          admin, await apiReceiptOf(admin, await apiPo(admin)));
      final Json draftRace = await apiBill(
          admin, await apiReceiptOf(admin, await apiPo(admin)));
      final Json billed = await apiApprovedBill(admin);
      final Json paid = await apiApprovedBill(admin);
      await apiPayment(admin, paid, 40);
      final Json withReturn = await apiApprovedBill(admin);
      await apiPurchaseReturn(admin, withReturn['receipt'] as Json);
      final Json forClose = await apiApprovedBill(admin);
      final Json forCancel = await apiApprovedBill(admin);
      // An unbilled completed receipt for the "offered" check.
      final Json waitingGr = await apiReceiptOf(admin, await apiPo(admin));

      await log.step('SC-PB-001 list opens with its columns', () async {
        await openBills();
        final List<String> missing = <String>[
          for (final String h in <String>[
            'Invoice Number',
            'Supplier',
            'Supplier Invoice',
            'Invoice Date',
            'Status',
            'Grand Total'
          ])
            if (!screenHas(tester, h)) h,
        ];
        log.info('SC-PB-001', 'short texts: ${textOnScreen(tester).where((String t) => t.length < 26).take(70).join(' | ')}');
        if (missing.isNotEmpty) {
          throw StateError('not on screen: ${missing.join(', ')}');
        }
        log.saw = 'columns present';
      });

      // -- Negative -------------------------------------------------------
      await log.step('SC-PB-014 no supplier: Save is refused', () async {
        await openBills();
        await tapNew(tester);
        log.saw = await refuse(() async {});
      });
      await closeOpenEditor(tester);

      await log.step('SC-PB-015 supplier but no receipt: Save is refused',
          () async {
        await newBillFromSupplier();
        log.saw = await refuse(() async {});
      });
      await closeOpenEditor(tester);

      await log.step('SC-PB-016 billing 99999 of what was received', () async {
        await newBillFromSupplier();
        await tickReceipt();
        log.saw = await refuse(() async {
          await typeInKeyed(tester, 'purchase-invoice-line-0', '99999');
        });
      });
      await closeOpenEditor(tester);

      await log.step('SC-PB-017 a billed receipt is not offered', () async {
        await newBillFromSupplier();
        await tapKey(tester, 'purchase-invoice-choose-receipts');
        await pumpFor(tester, const Duration(seconds: 2));
        final String billedNo = docNumber(billed['receipt'] as Json);
        final String waitingNo = docNumber(waitingGr);
        final bool b = screenHas(tester, billedNo);
        final bool w = screenHas(tester, waitingNo);
        log.saw = 'billed receipt $billedNo offered=$b; unbilled $waitingNo '
            'offered=$w';
        await closeOpenEditor(tester);
        if (b) throw StateError('a billed receipt is offered');
        if (!w) throw StateError('an unbilled receipt is not offered');
      });
      await closeOpenEditor(tester);

      await log.step('SC-PB-028 the Cancel button on a typed-in editor asks',
          () async {
        await newBillFromSupplier();
        await tapButton(tester, 'Cancel');
        await pumpFor(tester, const Duration(seconds: 1));
        final bool gone = find
            .byKey(const ValueKey<String>('purchase-invoice-save'))
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

      await log.step('SC-PB-024 an Approved bill cannot be edited', () async {
        await openBills();
        await selectRow(tester, docNumber(billed));
        final String e = buttonState(tester, 'Edit');
        log.saw = 'Edit is $e on an Approved bill';
        if (e == 'enabled') throw StateError('Edit offered');
      });

      await log.step('SC-PB-025 Cancel with a payment resting on the bill',
          () async {
        await openBills();
        await selectRow(tester, docNumber(paid));
        final String said = await pressWithReason(tester, 'Cancel');
        final String st = await statusOf('${paid['id']}');
        log.saw = 'status $st, screen says "$said"';
        if (st == 'CANCELLED') {
          throw StateError('a bill with a payment on it was cancelled');
        }
        if (said.isEmpty) throw StateError('N1: refusal said nothing');
      });

      await log.step('SC-PB-026 Cancel with a purchase return resting on it',
          () async {
        await openBills();
        await selectRow(tester, docNumber(withReturn));
        final String said = await pressWithReason(tester, 'Cancel');
        final String st = await statusOf('${withReturn['id']}');
        log.saw = 'status $st, screen says "$said"';
        if (st == 'CANCELLED') {
          throw StateError('a bill with a return on it was cancelled');
        }
        if (said.isEmpty) throw StateError('N1: refusal said nothing');
      });

      await log.step('SC-PB-022 Pay now more than the bill is refused',
          () async {
        await openBills();
        await selectRow(tester, docNumber(draftForPayTooMuch));
        await tapButton(tester, 'Approve');
        await pumpUntil(
            tester, find.byKey(const ValueKey<String>('approve-bill-confirm')),
            waitingFor: 'the approve dialog');
        await tester.tap(find.byKey(const ValueKey<String>('paid-now')));
        await pumpFor(tester, const Duration(milliseconds: 600));
        log.saw = await expectRefusal(tester, me,
            collection: 'payments',
            openKey: 'approve-bill-confirm',
            press: () async {
              await typeInKeyed(tester, 'paid-now-amount', '99999');
              await tapKey(tester, 'approve-bill-confirm');
            });
        final String st = await statusOf('${draftForPayTooMuch['id']}');
        log.saw = '${log.saw}; bill status $st';
        if (st == 'APPROVED') {
          throw StateError('the bill was approved though the payment was '
              'refused (half done)');
        }
      });
      await closeOpenEditor(tester);

      await log.step('SC-PB-021 a second bill with the same supplier number '
          '(HTTP)', () async {
        final Json gr = await apiReceiptOf(admin, await apiPo(admin));
        final Json first = await apiBill(admin, gr, quantity: 4);
        final ({int status, String text}) r = await admin.attempt(
            'POST', '/api/v1/purchase-invoices', <String, dynamic>{
          'vendor_id': gr['vendor_id'],
          'branch_id': gr['branch_id'],
          'invoice_date': DateTime.now().toIso8601String().substring(0, 10),
          'supplier_invoice_number': first['supplier_invoice_number'],
          'supplier_invoice_date':
              DateTime.now().toIso8601String().substring(0, 10),
          'source_documents': <Json>[
            <String, dynamic>{
              'source_document_type': 'GOODS_RECEIPT',
              'source_document_id': gr['id'],
            },
          ],
          'lines': <Json>[
            <String, dynamic>{
              'source_document_type': 'GOODS_RECEIPT',
              'source_document_id': gr['id'],
              'source_document_line_id':
                  ((gr['lines'] as List<dynamic>).first as Json)['id'],
              'line_number': 1,
              'current_invoice_quantity': 3,
            },
          ],
        });
        log.saw = 'second bill with the same number answered ${r.status}: '
            '${r.text.length > 200 ? r.text.substring(0, 200) : r.text}';
        if (r.status >= 400) {
          throw StateError('a repeated supplier number was refused; the book '
              'says it is a warning');
        }
        final RegExpMatch? warned =
            RegExp(r'"duplicate_warning":\s*"([^"]+)').firstMatch(r.text);
        if (warned == null) {
          throw StateError('accepted with no duplicate_warning on the answer');
        }
        log.saw = 'second bill with the same number answered ${r.status}, '
            'warning "${warned.group(1)}"';
      });

      // -- Positive -------------------------------------------------------
      await log.step('SC-PB-004 approve and pay part of it now', () async {
        final int before = await totalOf(me, 'payments');
        await openBills();
        await selectRow(tester, docNumber(draftForPay));
        await tapButton(tester, 'Approve');
        await pumpUntil(
            tester, find.byKey(const ValueKey<String>('approve-bill-confirm')),
            waitingFor: 'the approve dialog');
        await tester.tap(find.byKey(const ValueKey<String>('paid-now')));
        await pumpFor(tester, const Duration(milliseconds: 600));
        await typeInKeyed(tester, 'paid-now-amount', '50');
        await tapKey(tester, 'approve-bill-confirm');
        final String said = await watch(tester, confirm: false, seconds: 5);
        final String st = await statusOf('${draftForPay['id']}');
        final int after = await totalOf(me, 'payments');
        log.saw = 'status $st; payments +${after - before}; screen says '
            '"$said"';
        if (st != 'APPROVED' || after - before != 1) {
          throw StateError('status $st, payments +${after - before}');
        }
      });
      await closeOpenEditor(tester);

      await log.step('SC-PB-010 Close an Approved bill', () async {
        await openBills();
        await selectRow(tester, docNumber(forClose));
        final String said = await pressWithReason(tester, 'Close');
        final String st = await statusOf('${forClose['id']}');
        log.saw = 'status $st, screen says "$said"';
        if (st != 'CLOSED') throw StateError('status $st');
      });

      await log.step('SC-PB-011 Cancel an Approved bill', () async {
        await openBills();
        await selectRow(tester, docNumber(forCancel));
        final String said = await pressWithReason(tester, 'Cancel');
        final String st = await statusOf('${forCancel['id']}');
        log.saw = 'status $st, screen says "$said"';
        if (st != 'CANCELLED') throw StateError('status $st');
      });

      // -- Multi-user -----------------------------------------------------
      await log.step('SC-PB-035 stale Approve after another user approved',
          () async {
        await openBills();
        await selectRow(tester, docNumber(draftStale));
        await apiAct(await asUser('qpmgr'), 'purchase-invoices',
            '${draftStale['id']}', 'approve');
        await tapButton(tester, 'Approve');
        await pumpFor(tester, const Duration(seconds: 1));
        final String said = await watch(tester, seconds: 5);
        final String asked = noticeText(tester);
        log.saw = 'status ${await statusOf('${draftStale['id']}')}, screen '
            'says "$said" / "$asked"';
        if (said.isEmpty && asked.isEmpty) {
          throw StateError('N1: the stale Approve said nothing');
        }
      });
      await closeOpenEditor(tester);

      await log.step('SC-PB-036 stale save after another user changed the '
          'bill', () async {
        await openBills();
        await selectRow(tester, docNumber(draftRace));
        await tapButton(tester, 'Edit');
        await pumpFor(tester, const Duration(seconds: 2));
        final Json cur = await admin.one('purchase-invoices', '${draftRace['id']}');
        final Json l = (cur['lines'] as List<dynamic>).first as Json;
        await (await asUser('qpmgr')).write(
            'PUT', '/api/v1/purchase-invoices/${cur['id']}', <String, dynamic>{
          'vendor_id': cur['vendor_id'],
          'branch_id': cur['branch_id'],
          'invoice_date': cur['invoice_date'],
          'supplier_invoice_number': cur['supplier_invoice_number'],
          'supplier_invoice_date': cur['supplier_invoice_date'],
          'payment_terms': 'NET 45',
          'source_documents': <Json>[
            for (final dynamic s in cur['sources'] as List<dynamic>)
              <String, dynamic>{
                'source_document_type': (s as Json)['source_document_type'],
                'source_document_id': s['source_document_id'],
              },
          ],
          'lines': <Json>[
            <String, dynamic>{
              'source_document_type': l['source_document_type'],
              'source_document_id': l['source_document_id'],
              'source_document_line_id': l['source_document_line_id'],
              'line_number': 1,
              'current_invoice_quantity': l['current_invoice_quantity'],
            },
          ],
        });
        await tester.enterText(
            find.byWidgetPredicate((Widget w) =>
                w is TextField && w.decoration?.hintText == 'as printed'),
            'MY-TYPED-NUMBER');
        await pumpFor(tester, const Duration(milliseconds: 400));
        final Set<String> before = textOnScreen(tester).toSet();
        await tapKey(tester, 'purchase-invoice-save');
        final String said = await watch(tester, confirm: false, seconds: 5);
        final String fresh = textOnScreen(tester)
            .where((String t) => t.length < 260 && !before.contains(t))
            .join(' | ');
        final bool open = find
            .byKey(const ValueKey<String>('purchase-invoice-save'))
            .evaluate()
            .isNotEmpty;
        final Json now = await admin.one('purchase-invoices', '${draftRace['id']}');
        log.saw = 'editor open=$open; terms ${now['payment_terms']}; number '
            '${now['supplier_invoice_number']}; says "$said" / "$fresh"';
        if (!open || now['payment_terms'] != 'NET 45') {
          throw StateError('HIGH: the stale save went through (open=$open, '
              'terms ${now['payment_terms']})');
        }
        if (said.isEmpty && fresh.isEmpty) {
          throw StateError('N1: the stale save said nothing');
        }
        if (!screenHasTyped(tester, 'MY-TYPED-NUMBER')) {
          throw StateError('N2: typing lost');
        }
      });
      await closeOpenEditor(tester);

      log.skip('SC-PB-005', 'the firm bills receipts only; a bill with no '
          'receipt cannot be started on screen');
      log.skip('SC-PB-006', 'no foreign-currency supplier in the fixture');
      log.skip('SC-PB-007', 'no TDS section set up in the fixture');
      log.skip('SC-PB-008', 'TCS boxes not driven');
      log.skip('SC-PB-009', 'file picker not drivable');
      log.skip('SC-PB-012', 'Payables by Month report not reached');
      log.skip('SC-PB-013', 'IRN dialog not driven');
      log.skip('SC-PB-018', 'Bill date is not a typed box');
      log.skip('SC-PB-019', 'no closed period in the fixture firm');
      log.skip('SC-PB-020', 'no tolerance set in the fixture firm');
      log.skip('SC-PB-027', 'no capital goods line in the fixture');
      log.skip('SC-PB-034', 'covered by the PO and PY files');
      log.info('SC-PB', 'left over: ${docNumber(draftForApprove)}');
    } else {
      final Map<String, List<String>> menu = await offeredMenu(tester);
      // ignore: avoid_print
      print('FLOW: MENU [$itHandle] ${menu.entries.map((MapEntry<String, List<String>> e) => '${e.key}=${e.value.join(',')}').join('; ')}');
      final bool offered = menuHas(menu, menuPath);
      final ({int status, String text}) api =
          await me.attempt('GET', '/api/v1/purchase-invoices?page_size=1', null);
      final Json draft = await apiBill(
          admin, await apiReceiptOf(admin, await apiPo(admin)));
      Future<void> openAndSelect() async {
        await openBills();
        await selectRow(tester, docNumber(draft));
      }

      if (itHandle == 'qpexe') {
        await log.step('SC-PB-029 PU: New offered, Approve absent', () async {
          log.saw = 'offered: $offered; list ${api.status}';
          if (!offered) throw StateError('not offered to PU');
          await openAndSelect();
          final Map<String, String> s =
              buttons(<String>['+ New', 'New', 'Approve', 'Edit']);
          log.saw = '${log.saw}; $s';
          if (s['Approve'] == 'enabled') {
            throw StateError('PU is offered Approve: $s');
          }
        });
      } else if (itHandle == 'qpmgr') {
        await log.step('SC-PB-030 PM: Approve offered, Pay now absent',
            () async {
          log.saw = 'offered: $offered';
          if (!offered) throw StateError('not offered to PM');
          await openAndSelect();
          final String a = buttonState(tester, 'Approve');
          if (a != 'enabled') throw StateError('Approve $a for PM');
          await tapButton(tester, 'Approve');
          await pumpFor(tester, const Duration(seconds: 2));
          final bool payNow =
              find.byKey(const ValueKey<String>('paid-now')).evaluate().isNotEmpty;
          log.saw = '${log.saw}; Approve $a; Pay now control shown=$payNow';
          await closeOpenEditor(tester);
          if (payNow) throw StateError('PM is offered Pay now');
        });
      } else if (itHandle == 'qacct') {
        await log.step('SC-PB-031 AC: Purchase Invoices offered or not',
            () async {
          log.saw = 'offered: $offered; list ${api.status}; payables '
              'offered: ${menu.values.any((List<String> v) => v.any((String s) => s.contains('payable')))}';
          if (offered != (api.status == 200)) {
            throw StateError('menu ($offered) and server (${api.status}) '
                'disagree');
          }
        });
        for (final MapEntry<String, String> screen
            in <String, String>{
          'buy': 'purchaseInvoices',
          'sell': 'salesInvoices/sales-invoices',
        }.entries) {
          await log.step('SC-PB-031 AC: ${screen.value} opens without an '
              'error and offers no write', () async {
            final bool here = menuHas(menu, screen.value);
            if (!here) throw StateError('${screen.value} not offered');
            await openMenu(tester, screen.key, screen.value);
            await pumpFor(tester, const Duration(seconds: 3));
            final List<String> errors = textOnScreen(tester)
                .where((String t) =>
                    t.length < 200 &&
                    RegExp(r"403|forbidden|not allowed|permission|cannot|"
                            r"Could not|error|failed",
                        caseSensitive: false)
                        .hasMatch(t))
                .toList();
            final Map<String, String> b = <String, String>{
              for (final String l in <String>[
                '+ New', 'New', 'Approve', 'Cancel', 'Close', 'Edit'
              ])
                l: buttonState(tester, l),
            };
            final List<String> head = rowOf(tester, 'Status');
            log.saw = 'errors on screen: $errors; buttons $b; header '
                '${head.take(8).join(' / ')}; first rows '
                '${textOnScreen(tester).where((String t) => RegExp(r"^(PI|SI)-").hasMatch(t)).take(3).join(', ')}';
            log.saw = '${log.saw}; screen: ${textOnScreen(tester).skip(12).where((String t) => t.length < 60).take(45).join(' | ')}';
            if (errors.isNotEmpty) throw StateError('error on screen: $errors');
            final List<String> on = <String>[
              for (final MapEntry<String, String> e in b.entries)
                if (e.value == 'enabled') e.key,
            ];
            if (on.isNotEmpty) throw StateError('write buttons enabled: $on');
          });
        }
      } else if (itHandle == 'qstore') {
        await log.step('SC-PB-032 WH: bills not offered', () async {
          log.saw = 'offered: $offered; list ${api.status}';
          if (offered) throw StateError('bills offered to WH');
        });
      } else if (itHandle == 'qro') {
        await log.step('SC-PB-033 RO: rows readable, no write buttons',
            () async {
          log.saw = 'offered: $offered';
          if (!offered) throw StateError('not offered to Read Only');
          await openAndSelect();
          final Map<String, String> s = buttons(<String>[
            '+ New', 'New', 'Edit', 'Approve', 'Cancel', 'Close'
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
