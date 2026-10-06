import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'harness.dart';

/// The buying chain, driven through the real phase 2 screens against the live
/// server: purchase order, goods receipt, purchase invoice, payment, return.
///
///     IT_EMAIL=... IT_PASSWORD=... bash integration_test/run.sh \
///         buying_flow_test.dart
void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('buying: order to return', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1600, 1000);
    tester.view.devicePixelRatio = 1;
    final Server server = await Server.connect();
    await startAndSignIn(tester);
    final FlowLog flow = FlowLog('buying');

    // -- Purchase order ----------------------------------------------------
    Json? order;
    final bool ordered = await flow.step('order: new, line, save', () async {
      await openMenu(tester, 'buy', 'purchases/purchase-orders');
      await tapNew(tester);
      await chooseIn(tester, 'purchase-order-vendor', 'Principal supplier');
      await chooseInKeyed(
          tester, 'purchase-order-line-product-', 'Detergent');
      await typeIn(tester, 'purchase-order-line-0', 1, '10');
      await pumpFor(tester, const Duration(seconds: 3));
      await saveEditor(tester, 'purchase-order-save');
      await pumpFor(tester, const Duration(seconds: 3));
      order = await server.newest('purchase-orders');
      final String? fault = order == null
          ? 'nothing was saved'
          : arithmeticFault(order!, quantity: 10);
      if (fault != null) throw StateError(fault);
    });
    if (ordered) {
      await flow.step('order: list shows number and total', () async {
        if (!screenHas(tester, docNumber(order!))) {
          throw StateError('list does not show ${docNumber(order!)}');
        }
        final double grand = figuresOf(order!).grand;
        if (!screenShowsMoney(tester, grand)) {
          flow.defect('order: list total',
              'saved grand total $grand is not on the list screen');
        }
      });
      await flow.step('order: reopen, change quantity, save', () async {
        await selectRow(tester, docNumber(order!));
        await tapButton(tester, 'Edit');
        await pumpFor(tester, const Duration(seconds: 3));
        await typeIn(tester, 'purchase-order-line-0', 1, '12');
        await pumpFor(tester, const Duration(seconds: 3));
        await saveEditor(tester, 'purchase-order-save');
        await pumpFor(tester, const Duration(seconds: 3));
        order = await server.one('purchase-orders', '${order!['id']}');
        final String? fault = arithmeticFault(order!, quantity: 12);
        if (fault != null) throw StateError(fault);
      });
      await flow.step('order: approve', () async {
        await selectRow(tester, docNumber(order!));
        await tapButton(tester, 'Approve');
        await confirmIfAsked(tester);
        await pumpFor(tester, const Duration(seconds: 3));
        order = await server.one('purchase-orders', '${order!['id']}');
        if ('${order!['status']}' != 'APPROVED') {
          throw StateError('status is ${order!['status']} after Approve');
        }
        if (!screenShowsStatus(tester, 'Approved')) {
          flow.defect('order: status on screen',
              'the list does not say Approved after approval');
        }
      });
    }

    // -- Goods receipt -----------------------------------------------------
    Json? receipt;
    if (order != null && '${order!['status']}' == 'APPROVED') {
      await flow.step('receipt: new off the order, complete', () async {
        await openMenu(tester, 'buy', 'goodsReceipts/receipts');
        await tapNew(tester);
        await chooseIn(tester, 'goods-receipt-order', docNumber(order!));
        await pumpFor(tester, const Duration(seconds: 2));
        await saveEditor(tester, 'goods-receipt-save-complete');
        await confirmIfAsked(tester);
        await pumpFor(tester, const Duration(seconds: 3));
        receipt = await server.newest('goods-receipts');
        if (receipt == null) throw StateError('nothing was saved');
        if ('${receipt!['status']}' == 'DRAFT') {
          throw StateError('still DRAFT after Save and complete');
        }
        final dynamic lines = receipt!['lines'];
        if (lines is List && lines.isNotEmpty) {
          final double got = num2((lines.first as Json)['received_quantity'] ??
              (lines.first as Json)['accepted_quantity'] ??
              (lines.first as Json)['quantity']);
          if (got != 12) {
            flow.defect('receipt: quantity',
                'receipt line is $got, the order is for 12');
          }
        }
      });
    } else {
      flow.skip('goods receipt', 'no approved order');
    }

    // -- Purchase invoice --------------------------------------------------
    Json? bill;
    if (receipt != null) {
      await flow.step('bill: new off the receipt, save', () async {
        await openMenu(tester, 'buy', 'purchaseInvoices');
        await tapNew(tester);
        await chooseIn(tester, 'purchase-invoice-order', docNumber(order!));
        await pumpFor(tester, const Duration(seconds: 3));
        await saveEditor(tester, 'purchase-invoice-save');
        await pumpFor(tester, const Duration(seconds: 3));
        bill = await server.newest('purchase-invoices');
        if (bill == null) throw StateError('nothing was saved');
        final String? fault = arithmeticFault(bill!);
        if (fault != null) throw StateError(fault);
        if (!sameMoney(figuresOf(bill!).grand, figuresOf(order!).grand)) {
          flow.defect(
              'bill: total against the order',
              'billed ${figuresOf(bill!).grand}, order '
                  '${figuresOf(order!).grand}, all of it received');
        }
      });
      if (bill != null) {
        await flow.step('bill: approve', () async {
          await selectRow(tester, docNumber(bill!));
          await tapButton(tester, 'Approve');
          await confirmIfAsked(tester);
          await pumpFor(tester, const Duration(seconds: 3));
          bill = await server.one('purchase-invoices', '${bill!['id']}');
          if ('${bill!['status']}' == 'DRAFT') {
            throw StateError('still DRAFT after Approve');
          }
        });
      }
    } else {
      flow.skip('bill', 'no goods receipt');
    }

    // -- Payment -----------------------------------------------------------
    if (bill != null) {
      await flow.step('payment: record against the bill', () async {
        await openMenu(tester, 'buy', 'accounting/payments');
        await tapNew(tester);
        await typeLabelled(tester, 'Paid to', 'Principal');
        await pumpFor(tester, const Duration(seconds: 1));
        await tester.tap(find.textContaining('Principal supplier').last);
        await pumpFor(tester, const Duration(seconds: 2));
        final double owed = figuresOf(bill!).grand;
        await typeLabelled(tester, 'Amount', owed.toStringAsFixed(2));
        await tapButton(tester, 'Oldest first');
        await tapButtonStarting(tester, 'Record ');
        await pumpFor(tester, const Duration(seconds: 3));
        final Json? payment = await server.newest('payments');
        if (payment == null) throw StateError('no payment on the server');
        if (!sameMoney(num2(payment['amount']), owed)) {
          throw StateError('payment is ${payment['amount']}, typed $owed');
        }
        bill = await server.one('purchase-invoices', '${bill!['id']}');
        final double outstanding =
            num2(bill!['outstanding_amount'] ?? bill!['balance_due']);
        if (!outstanding.isNaN && outstanding != 0) {
          flow.defect('payment: bill still owing',
              'bill owes $outstanding after a full payment');
        }
      });
    } else {
      flow.skip('payment', 'no bill');
    }

    // -- Purchase return ---------------------------------------------------
    if (receipt != null) {
      await flow.step('return: new off the receipt, save, approve', () async {
        await openMenu(tester, 'buy', 'purchaseReturns');
        await tapNew(tester);
        await chooseIn(tester, 'purchase-return-receipt', docNumber(receipt!));
        await pumpFor(tester, const Duration(seconds: 2));
        await typeInKeyed(tester, 'purchase-return-returning-', '1');
        await pumpFor(tester, const Duration(seconds: 2));
        await saveEditor(tester, 'purchase-return-save');
        await pumpFor(tester, const Duration(seconds: 3));
        final Json? ret = await server.newest('purchase-returns');
        if (ret == null) throw StateError('nothing was saved');
        final String? fault = arithmeticFault(ret);
        if (fault != null) throw StateError(fault);
        await selectRow(tester, docNumber(ret));
        await tapButton(tester, 'Approve');
        await confirmIfAsked(tester);
        await pumpFor(tester, const Duration(seconds: 3));
        final Json after = await server.one('purchase-returns', '${ret['id']}');
        if ('${after['status']}' == 'DRAFT') {
          throw StateError('still DRAFT after Approve');
        }
      });
    } else {
      flow.skip('return', 'no goods receipt');
    }

    flow.finish();
  });
}
