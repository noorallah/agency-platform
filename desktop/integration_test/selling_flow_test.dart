import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'harness.dart';

/// The selling chain, driven through the real phase 2 screens against the live
/// server: quotation, order, delivery note, invoice, receipt, return.
///
/// Signs in as a fixture firm's administrator (IT_EMAIL / IT_PASSWORD) so the
/// documents it raises never touch a demo firm. Each step reads the result
/// back from the screen and from the server, records what is wrong as a
/// `FLOW:` line and carries on.
///
///     IT_EMAIL=... IT_PASSWORD=... bash integration_test/run.sh \
///         selling_flow_test.dart
void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('selling: quotation to return', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1600, 1000);
    tester.view.devicePixelRatio = 1;
    final Server server = await Server.connect();
    await startAndSignIn(tester);
    final FlowLog flow = FlowLog('selling');

    // -- Quotation ---------------------------------------------------------
    Json? quote;
    final bool quoted = await flow.step('SC-QT-002 quotation: new, line, save', () async {
      await openMenu(tester, 'sell', 'quotations');
      await tapNew(tester);
      await chooseIn(tester, 'quotation-customer', 'Vijaya Stores');
      await chooseIn(tester, 'quotation-line-product-0', 'Detergent');
      await typeIn(tester, 'quotation-line-0', 1, '10');
      await pumpFor(tester, const Duration(seconds: 3));
      await saveEditor(tester, 'quotation-save');
      await pumpFor(tester, const Duration(seconds: 3));
      quote = await server.newest('quotations');
      final String? fault = quote == null
          ? 'nothing was saved'
          : arithmeticFault(quote!, quantity: 10);
      if (fault != null) throw StateError(fault);
    });
    if (quoted) {
      await flow.step('SC-QT-003 quotation: list shows its number and total', () async {
        final String number = '${quote!['quotation_number']}';
        if (!screenHas(tester, number)) {
          throw StateError('list does not show $number');
        }
        final double grand = figuresOf(quote!).grand;
        if (!screenShowsMoney(tester, grand)) {
          flow.defect('quotation: list total',
              'the saved grand total $grand is not on the list screen');
        }
      });
      await flow.step('SC-QT-005 quotation: revise, change quantity, save', () async {
        await selectRow(tester, '${quote!['quotation_number']}');
        await tapButton(tester, 'Revise');
        await pumpFor(tester, const Duration(seconds: 3));
        await typeIn(tester, 'quotation-line-0', 1, '12');
        await pumpFor(tester, const Duration(seconds: 3));
        await saveEditor(tester, 'quotation-save');
        await pumpFor(tester, const Duration(seconds: 3));
        quote = await server.newest('quotations');
        final String? fault = arithmeticFault(quote!, quantity: 12);
        if (fault != null) throw StateError(fault);
      });
      for (final MapEntry<String, String> stepToStatus
          in const <String, String>{
        'Mark as sent': 'SENT',
        'Customer accepted': 'ACCEPTED',
        'Convert to order': 'CONVERTED',
      }.entries) {
        await flow.step(
            '${const <String, String>{'Mark as sent': 'SC-QT-006', 'Customer accepted': 'SC-QT-007', 'Convert to order': 'SC-QT-008'}[stepToStatus.key]} quotation: ${stepToStatus.key}',
            () async {
          await selectRow(tester, '${quote!['quotation_number']}');
          await tapButton(tester, stepToStatus.key);
          final String asked = noticeText(tester);
          await confirmIfAsked(tester);
          await pumpFor(tester, const Duration(seconds: 2));
          final Json now = await server.one('quotations', '${quote!['id']}');
          if ('${now['status']}' != stepToStatus.value) {
            throw StateError('quotation is ${now['status']} after '
                '${stepToStatus.key}, expected ${stepToStatus.value}; the '
                'screen asked "$asked" and said "${noticeText(tester)}"');
          }
        });
      }
    } else {
      flow.skip('quotation: revise, accept, convert', 'no quotation saved');
    }

    // -- Sales order -------------------------------------------------------
    Json? order;
    await flow.step('SC-SO-002 order: converted order exists with sound figures',
        () async {
      order = await server.newest('sales-orders');
      if (order == null) throw StateError('no sales order on the server');
      Json? q = quote;
      if (q != null) q = await server.one('quotations', '${q['id']}');
      if (q != null && '${q['converted_sales_order_id']}' != '${order!['id']}') {
        flow.defect(
            'order: converted from quote',
            'newest order ${order!['order_number']} is not the converted '
                'one; quote status is ${q['status']}');
      }
      final String? fault = arithmeticFault(order!);
      if (fault != null) throw StateError(fault);
    });
    if (order != null) {
      await flow.step('SC-SO-003 order: list shows it, approve', () async {
        await openMenu(tester, 'sell', 'salesOrders');
        final String number = '${order!['order_number']}';
        await selectRow(tester, number);
        if (!screenShowsMoney(tester, figuresOf(order!).grand)) {
          flow.defect('order: list total',
              'grand ${figuresOf(order!).grand} not on the list');
        }
        await tapButton(tester, 'Approve');
        await confirmIfAsked(tester);
        await pumpFor(tester, const Duration(seconds: 3));
        order = await server.one('sales-orders', '${order!['id']}');
        if ('${order!['status']}' != 'APPROVED') {
          throw StateError('status is ${order!['status']} after Approve');
        }
        if (!screenShowsStatus(tester, 'Approved')) {
          flow.defect('order: status on screen',
              'the list does not say Approved after approval');
        }
      });
    }

    // -- Delivery note -----------------------------------------------------
    Json? note;
    if (order != null && '${order!['status']}' == 'APPROVED') {
      await flow.step('SC-DN-002 delivery note: new off the order, save', () async {
        await openMenu(tester, 'sell', 'deliveryNotes/delivery-notes');
        await tapNew(tester);
        await chooseIn(
            tester, 'delivery-note-order', '${order!['order_number']}');
        await pumpFor(tester, const Duration(seconds: 2));
        await saveEditor(tester, 'delivery-note-save');
        await pumpFor(tester, const Duration(seconds: 3));
        note = await server.newest('delivery-notes');
        if (note == null) throw StateError('nothing was saved');
        if ('${note!['sales_order_id']}' != '${order!['id']}') {
          throw StateError('newest note is not for this order');
        }
      });
      if (note != null) {
        await flow.step('SC-DN-003 delivery note: approve (dispatch)', () async {
          await selectRow(tester, docNumber(note!));
          await tapButton(tester, 'Approve');
          await confirmIfAsked(tester);
          await pumpFor(tester, const Duration(seconds: 3));
          note = await server.one('delivery-notes', '${note!['id']}');
          if ('${note!['status']}' == 'DRAFT') {
            throw StateError('still DRAFT after Approve');
          }
        });
        await flow.step('SC-DN-004 delivery note: dispatch', () async {
          await selectRow(tester, docNumber(note!));
          await tapButton(tester, 'Dispatch');
          final String asked = noticeText(tester);
          // Dispatch offers to raise the bill there and then; this flow bills
          // the note by hand in the next step, so it dispatches without.
          final Finder anyway =
              find.byKey(const ValueKey<String>('dispatch-anyway'));
          if (anyway.evaluate().isNotEmpty) {
            await tester.tap(anyway.first);
          } else {
            await confirmIfAsked(tester);
          }
          await pumpFor(tester, const Duration(seconds: 3));
          final String said = noticeText(tester);
          note = await server.one('delivery-notes', '${note!['id']}');
          if ('${note!['status']}' != 'DISPATCHED') {
            throw StateError('status is ${note!['status']} after Dispatch; '
                'the screen said "$said" (before confirming: "$asked")');
          }
        });
      }
    } else {
      flow.skip('delivery note', 'no approved order');
    }

    // -- Sales invoice -----------------------------------------------------
    Json? invoice;
    if (note != null) {
      await flow.step('SC-SB-002 invoice: new, bill the note, save', () async {
        await openMenu(tester, 'sell', 'salesInvoices/sales-invoices');
        await tapNew(tester);
        await chooseIn(tester, 'sales-invoice-bill-customer', 'Vijaya Stores');
        await tapKey(tester, 'sales-invoice-choose-notes');
        await pumpFor(tester, const Duration(seconds: 2));
        await tester.tap(find
            .descendant(
                of: find.byType(Dialog), matching: find.byType(Checkbox))
            .first);
        await pumpFor(tester, const Duration(milliseconds: 500));
        await confirmIfAsked(tester);
        await pumpFor(tester, const Duration(seconds: 3));
        await saveEditor(tester, 'sales-invoice-save');
        await pumpFor(tester, const Duration(seconds: 3));
        invoice = await server.newest('sales-invoices');
        if (invoice == null) throw StateError('nothing was saved');
        final String? fault = arithmeticFault(invoice!);
        if (fault != null) throw StateError(fault);
        if (!sameMoney(figuresOf(invoice!).grand, figuresOf(order!).grand)) {
          flow.defect(
              'invoice: total against the order',
              'billed ${figuresOf(invoice!).grand}, order '
                  '${figuresOf(order!).grand}, all of it delivered');
        }
      });
      if (invoice != null) {
        await flow.step('SC-SB-003 invoice: approve', () async {
          await selectRow(tester, docNumber(invoice!));
          await tapButton(tester, 'Approve');
          await confirmIfAsked(tester);
          await pumpFor(tester, const Duration(seconds: 3));
          invoice = await server.one('sales-invoices', '${invoice!['id']}');
          if ('${invoice!['status']}' == 'DRAFT') {
            throw StateError('still DRAFT after Approve');
          }
          if (!screenShowsMoney(tester, figuresOf(invoice!).grand)) {
            flow.defect('invoice: list total',
                'grand ${figuresOf(invoice!).grand} not on the list');
          }
        });
      }
    } else {
      flow.skip('invoice', 'no delivery note');
    }

    // -- Receipt -----------------------------------------------------------
    if (invoice != null) {
      await flow.step('SC-RC-002 receipt: record against the bill', () async {
        await openMenu(tester, 'sell', 'accounting/receipts');
        await tapNew(tester);
        await typeLabelled(tester, 'Received from', 'Vijaya');
        await pumpFor(tester, const Duration(seconds: 1));
        await tester.tap(find.textContaining('Vijaya Stores').last);
        await pumpFor(tester, const Duration(seconds: 2));
        final double owed = figuresOf(invoice!).grand;
        await typeLabelled(tester, 'Amount', owed.toStringAsFixed(2));
        await tapButton(tester, 'Oldest first');
        await tapButtonStarting(tester, 'Record ');
        await pumpFor(tester, const Duration(seconds: 3));
        final Json? receipt = await server.newest('receipts');
        if (receipt == null) throw StateError('no receipt on the server');
        if (!sameMoney(num2(receipt['amount']), owed)) {
          throw StateError('receipt is ${receipt['amount']}, typed $owed');
        }
        invoice = await server.one('sales-invoices', '${invoice!['id']}');
        final double outstanding =
            num2(invoice!['outstanding_amount'] ?? invoice!['balance_due']);
        if (!outstanding.isNaN && outstanding != 0) {
          flow.defect('receipt: bill still owing',
              'invoice owes $outstanding after a full receipt');
        }
      });
    } else {
      flow.skip('receipt', 'no invoice');
    }

    // -- Sales return ------------------------------------------------------
    if (invoice != null) {
      await flow.step('SC-SR-002 SC-SR-003 return: new off the bill, save, approve', () async {
        await openMenu(tester, 'sell', 'salesReturns');
        await tapNew(tester);
        await chooseIn(
            tester, 'sales-return-document', docNumber(invoice!));
        await pumpFor(tester, const Duration(seconds: 2));
        await typeInKeyed(tester, 'sales-return-returning-', '1');
        await pumpFor(tester, const Duration(seconds: 2));
        await saveEditor(tester, 'sales-return-save');
        await pumpFor(tester, const Duration(seconds: 3));
        final Json? ret = await server.newest('sales-returns');
        if (ret == null) throw StateError('nothing was saved');
        final String? fault = arithmeticFault(ret);
        if (fault != null) throw StateError(fault);
        await selectRow(tester, docNumber(ret));
        await tapButton(tester, 'Approve');
        await confirmIfAsked(tester);
        await pumpFor(tester, const Duration(seconds: 3));
        final Json after = await server.one('sales-returns', '${ret['id']}');
        if ('${after['status']}' == 'DRAFT') {
          throw StateError('still DRAFT after Approve');
        }
      });
    } else {
      flow.skip('return', 'no invoice');
    }

    flow.finish();
  });
}
