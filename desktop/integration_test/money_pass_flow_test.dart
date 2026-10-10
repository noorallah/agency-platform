import 'package:agency_desktop/phase2/document_page.dart'
    show documentQuantity;
import 'package:agency_desktop/phase2/indian_format.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'buy_data.dart';
import 'cases.dart';
import 'harness.dart';
import 'sell_data.dart';

/// The money pass (D-UI-97, the fourth measure): every document screen that
/// shows a priced line, typed into in the real phase 2 app against the live
/// server, and each row read back and held to what the server then saved.
///
/// D-UI-95 was a line's total with tax shown under *Taxable* on three
/// screens; D-UI-96 was five more screens working the taxable value out
/// short. The widget tests now hold those screens to the server's kept
/// answers. This is the same check with nothing standing in for anything:
/// the real app, the real server, the figures a person would be looking at.
///
/// For each document the flow types a line, waits for the server's pricing,
/// **reads the row and the foot before saving**, saves, reads the saved
/// document back over HTTP and compares: the row must have shown the line's
/// taxable value (its amount less its tax), the rate that tax is of it, and
/// its amount; the screen must have shown the document's total.
///
/// It saves documents, so it signs in to a fixture firm (`selling-firm` of
/// `backend/scripts/test_fixture.py`, with one supplier added) and never to
/// a demo firm:
///
///     IT_EMAIL=<suffix>.tradeadmin@fixtures.local IT_PASSWORD=... \
///         bash integration_test/run.sh money_pass_flow_test.dart
const String _supplier = String.fromEnvironment('IT_SUPPLIER',
    defaultValue: 'Money Pass Supplier');

/// What a screen showed just before its document was saved.
class _Seen {
  _Seen(this.row, this.screen);

  /// The texts of the line's row, in paint order.
  final List<String> row;

  /// Every text on the screen.
  final List<String> screen;
}

/// Read row [rowKey] and the whole screen as they stand.
_Seen _look(WidgetTester tester, String rowKey) {
  final Finder row = find.byKey(ValueKey<String>(rowKey));
  if (row.evaluate().isEmpty) {
    throw StateError('no row keyed $rowKey on screen: '
        '${textOnScreen(tester).skip(10).take(60).join(' | ')}');
  }
  return _Seen(
    <String>[
      for (final Text text in tester.widgetList<Text>(
          find.descendant(of: row, matching: find.byType(Text))))
        (text.data ?? text.textSpan?.toPlainText() ?? '').trim(),
    ].where((String t) => t.isNotEmpty).toList(),
    textOnScreen(tester),
  );
}

/// Hold what was [seen] to line 1 of the saved [document]; returns the
/// sentence a result line carries. Throws naming what the row lacked.
String _hold(_Seen seen, Json document) {
  final Json line = (document['lines'] as List<dynamic>).first as Json;
  final double net = num2(line['net_amount']);
  final double tax = num2(line['tax_amount']);
  if (net.isNaN || tax.isNaN) {
    throw StateError('the saved line carries no amount or tax '
        '(keys: ${line.keys.take(40).join(',')})');
  }
  final double taxable = net - tax;
  final String wantTaxable = indianAmount(taxable, full: true);
  final String wantAmount = indianAmount(net, full: true);
  final String wantRate = taxable == 0
      ? ''
      : '${documentQuantity((tax / taxable * 100).toStringAsFixed(1))}%';
  final String wantTotal =
      indianAmount(figuresOf(document).grand, full: true);
  final List<String> wrong = <String>[
    if (!seen.row.contains(wantTaxable)) 'taxable $wantTaxable',
    if (wantRate.isNotEmpty && !seen.row.contains(wantRate)) 'rate $wantRate',
    if (!seen.row.contains(wantAmount)) 'amount $wantAmount',
    if (!seen.screen.any((String t) => t.contains(wantTotal)))
      'the total $wantTotal at the foot',
  ];
  final String said = 'server: taxable $wantTaxable, tax '
      '${indianAmount(tax, full: true)} ($wantRate), amount $wantAmount, '
      'total $wantTotal. Row showed: ${seen.row.join(' ; ')}';
  if (wrong.isNotEmpty) {
    throw StateError('the row did not show ${wrong.join(', ')}. $said');
  }
  return said;
}

/// Tap an editor's save button and wait for the editor to close. Where it
/// stays open, say what the screen newly showed, which is where a refusal
/// is written.
Future<void> _save(WidgetTester tester, String key) async {
  final Set<String> before = textOnScreen(tester).toSet();
  await tapKey(tester, key);
  final Finder button = find.byKey(ValueKey<String>(key));
  final DateTime deadline = DateTime.now().add(const Duration(seconds: 20));
  while (DateTime.now().isBefore(deadline)) {
    await tester.pump(const Duration(milliseconds: 200));
    if (button.evaluate().isEmpty) {
      await pumpFor(tester, const Duration(seconds: 1));
      return;
    }
  }
  final String fresh = textOnScreen(tester)
      .where((String t) => !before.contains(t) && t.length < 300)
      .take(20)
      .join(' | ');
  throw StateError('the editor stayed open after $key. New on screen: '
      '"$fresh". Notice: "${noticeText(tester)}"');
}

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('money pass: every priced document screen',
      (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1600, 1000);
    tester.view.devicePixelRatio = 1;
    final Server server = await Server.connect();
    await startAndSignIn(tester);
    final FlowLog flow = FlowLog('money');

    // -- Quotation ---------------------------------------------------------
    await flow.step('quotation: the row against the saved quotation',
        () async {
      await openMenu(tester, 'sell', 'quotations');
      await tapNew(tester);
      await chooseIn(tester, 'quotation-customer', 'Vijaya Stores');
      await chooseIn(tester, 'quotation-line-product-0', 'Detergent');
      await typeIn(tester, 'quotation-line-0', 1, '10');
      await pumpFor(tester, const Duration(seconds: 4));
      final _Seen seen = _look(tester, 'quotation-line-0');
      await _save(tester, 'quotation-save');
      await pumpFor(tester, const Duration(seconds: 3));
      final Json? saved = await server.newest('quotations');
      if (saved == null) throw StateError('nothing was saved');
      flow.saw =
          _hold(seen, await server.one('quotations', '${saved['id']}'));
    });

    // -- Sales order -------------------------------------------------------
    Json? order;
    await flow.step('sales order: the row against the saved order', () async {
      await openMenu(tester, 'sell', 'salesOrders');
      await tapNew(tester);
      await chooseIn(tester, 'sales-order-customer', 'Vijaya Stores');
      await chooseIn(tester, 'sales-order-line-product-0', 'Detergent');
      await typeIn(tester, 'sales-order-line-0', 1, '10');
      await pumpFor(tester, const Duration(seconds: 4));
      final _Seen seen = _look(tester, 'sales-order-line-0');
      await _save(tester, 'sales-order-save');
      await pumpFor(tester, const Duration(seconds: 3));
      final Json? saved = await server.newest('sales-orders');
      if (saved == null) throw StateError('nothing was saved');
      order = await server.one('sales-orders', '${saved['id']}');
      flow.saw = _hold(seen, order!);
    });

    // -- Proforma ----------------------------------------------------------
    if (order != null) {
      await flow.step('proforma: the row against the order it states',
          () async {
        await apiAct(server, 'sales-orders', '${order!['id']}', 'approve');
        order = await server.one('sales-orders', '${order!['id']}');
        await openMenu(tester, 'sell', 'sales/proforma-invoices');
        await tapNew(tester);
        await pumpUntil(
            tester, find.byKey(const ValueKey<String>('proforma-raise')),
            waitingFor: 'the proforma editor');
        await chooseFiltered(tester, 'proforma-order', docNumber(order!));
        await pumpFor(tester, const Duration(seconds: 2));
        flow.saw = _hold(_look(tester, 'proforma-line-0'), order!);
        await closeOpenEditor(tester);
      });
    } else {
      flow.skip('proforma', 'no order saved');
    }

    // -- Sales invoice, off a delivery note --------------------------------
    Json? invoice;
    await flow.step('sales invoice: the row against the saved bill', () async {
      final Json note = await apiDispatchedNote(server, quantity: 5);
      await openMenu(tester, 'sell', 'salesInvoices/sales-invoices');
      await tapNew(tester);
      await chooseIn(tester, 'sales-invoice-bill-customer', 'Vijaya Stores');
      await tickNotes(tester);
      await pumpFor(tester, const Duration(seconds: 3));
      final _Seen seen = _look(tester, 'sales-invoice-line-0');
      await _save(tester, 'sales-invoice-save');
      await pumpFor(tester, const Duration(seconds: 3));
      final Json? saved = await server.newest('sales-invoices');
      if (saved == null) throw StateError('nothing was saved');
      invoice = await server.one('sales-invoices', '${saved['id']}');
      flow.saw = '${_hold(seen, invoice!)} (note ${docNumber(note)})';
    });

    // -- Sales return ------------------------------------------------------
    if (invoice != null) {
      await flow.step('sales return: the row against the saved return',
          () async {
        await apiAct(server, 'sales-invoices', '${invoice!['id']}', 'approve');
        await openMenu(tester, 'sell', 'salesReturns');
        await tapNew(tester);
        await chooseIn(tester, 'sales-return-document', docNumber(invoice!));
        await pumpFor(tester, const Duration(seconds: 2));
        await typeInKeyed(tester, 'sales-return-returning-', '2');
        await pumpFor(tester, const Duration(seconds: 4));
        final _Seen seen = _look(tester, 'sales-return-line-0');
        await _save(tester, 'sales-return-save');
        await pumpFor(tester, const Duration(seconds: 3));
        final Json? saved = await server.newest('sales-returns');
        if (saved == null) throw StateError('nothing was saved');
        flow.saw =
            _hold(seen, await server.one('sales-returns', '${saved['id']}'));
      });
    } else {
      flow.skip('sales return', 'no bill saved');
    }

    // -- Purchase order ----------------------------------------------------
    Json? purchase;
    await flow.step('purchase order: the row against the saved order',
        () async {
      await openMenu(tester, 'buy', 'purchases/purchase-orders');
      await tapNew(tester);
      await chooseIn(tester, 'purchase-order-vendor', _supplier);
      await chooseInKeyed(tester, 'purchase-order-line-product-', 'Detergent');
      await typeInKeyed(tester, 'purchase-order-qty-', '10');
      await pumpFor(tester, const Duration(seconds: 4));
      final _Seen seen = _look(tester, 'purchase-order-line-0');
      await _save(tester, 'purchase-order-save');
      await pumpFor(tester, const Duration(seconds: 3));
      final Json? saved = await server.newest('purchases');
      if (saved == null) throw StateError('nothing was saved');
      purchase = await server.one('purchases', '${saved['id']}');
      flow.saw = _hold(seen, purchase!);
    });

    // -- Purchase bill, off a goods receipt --------------------------------
    Json? receipt;
    if (purchase != null) {
      await flow.step('purchase bill: the row against the saved bill',
          () async {
        final String id = '${purchase!['id']}';
        await apiAct(server, 'purchases', id, 'submit');
        await apiAct(server, 'purchases', id, 'approve');
        purchase = await server.one('purchases', id);
        receipt = await apiReceiptOf(server, purchase!, quantity: 10);
        await openMenu(tester, 'buy', 'purchaseInvoices');
        await tapNew(tester);
        await chooseIn(tester, 'purchase-invoice-receipt-supplier', _supplier);
        await tapKey(tester, 'purchase-invoice-choose-receipts');
        await pumpFor(tester, const Duration(seconds: 2));
        await tester.tap(find
            .descendant(
                of: find.byType(Dialog), matching: find.byType(Checkbox))
            .first);
        await pumpFor(tester, const Duration(milliseconds: 500));
        await confirmIfAsked(tester);
        await pumpFor(tester, const Duration(seconds: 2));
        // Typed after the receipts are chosen, the order a person works in:
        // the receipts decide which bill this is.
        await tester.enterText(
            find.byWidgetPredicate((Widget w) =>
                w is TextField && w.decoration?.hintText == 'as printed'),
            'SUP-${DateTime.now().millisecondsSinceEpoch}');
        await pumpFor(tester, const Duration(seconds: 4));
        final _Seen seen = _look(tester, 'purchase-invoice-line-0');
        await _save(tester, 'purchase-invoice-save');
        await pumpFor(tester, const Duration(seconds: 3));
        final Json? saved = await server.newest('purchase-invoices');
        if (saved == null) throw StateError('nothing was saved');
        flow.saw = _hold(
            seen, await server.one('purchase-invoices', '${saved['id']}'));
      });
    } else {
      flow.skip('purchase bill', 'no purchase order saved');
    }

    // -- Purchase return ---------------------------------------------------
    if (receipt != null) {
      await flow.step('purchase return: the row against the saved return',
          () async {
        await openMenu(tester, 'buy', 'purchaseReturns');
        await tapNew(tester);
        await chooseIn(tester, 'purchase-return-receipt', docNumber(receipt!));
        await pumpFor(tester, const Duration(seconds: 2));
        await typeInKeyed(tester, 'purchase-return-returning-', '2');
        await pumpFor(tester, const Duration(seconds: 4));
        final _Seen seen = _look(tester, 'purchase-return-line-0');
        await _save(tester, 'purchase-return-save');
        await pumpFor(tester, const Duration(seconds: 3));
        final Json? saved = await server.newest('purchase-returns');
        if (saved == null) throw StateError('nothing was saved');
        flow.saw = _hold(
            seen, await server.one('purchase-returns', '${saved['id']}'));
      });
    } else {
      flow.skip('purchase return', 'no goods receipt');
    }

    flow.finish();
  });
}
