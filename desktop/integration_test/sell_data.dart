import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'cases.dart';
import 'harness.dart';

// Data for the selling cases (SB, RC, SR...), set up over HTTP rather than
// through the screens: a dispatched note, a bill off it, a receipt, a return.

String _today() => DateTime.now().toIso8601String().substring(0, 10);

/// A dispatched delivery note for [quantity] units, with the order it came off.
/// Returns the note read back whole, with `order` added under that key.
Future<Json> apiDispatchedNote(Server admin, {num quantity = 5}) async {
  final Json o = await apiDraftOrder(admin, quantity: quantity);
  await apiAct(admin, 'sales-orders', '${o['id']}', 'approve');
  final Json order = await admin.one('sales-orders', '${o['id']}');
  final Json line = (order['lines'] as List<dynamic>).first as Json;
  final Json note = (await admin
      .write('POST', '/api/v1/delivery-notes', <String, dynamic>{
    'sales_order_id': order['id'],
    'delivery_date': _today(),
    'lines': <Json>[
      <String, dynamic>{
        'sales_order_line_id': line['id'],
        'line_number': 1,
        'current_delivery_quantity': quantity,
      },
    ],
  })) as Json;
  await apiAct(admin, 'delivery-notes', '${note['id']}', 'approve');
  await apiAct(admin, 'delivery-notes', '${note['id']}', 'dispatch');
  final Json whole = await admin.one('delivery-notes', '${note['id']}');
  whole['order'] = order;
  return whole;
}

/// A draft bill for [quantity] (or all that is left) of a dispatched [note].
Future<Json> apiDraftInvoice(Server admin, Json note, {num? quantity}) async {
  final dynamic rows = await admin.get('/api/v1/sales-invoices/billable');
  final Json b = (rows as List<dynamic>).cast<Json>().firstWhere(
      (Json r) => '${r['source_document_id']}' == '${note['id']}');
  final Json l = (b['lines'] as List<dynamic>).first as Json;
  return (await admin.write('POST', '/api/v1/sales-invoices', <String, dynamic>{
    'customer_id': b['customer_id'],
    'branch_id': b['branch_id'],
    'invoice_date': _today(),
    'source_documents': <Json>[
      <String, dynamic>{
        'source_document_type': 'DELIVERY_NOTE',
        'source_document_id': note['id'],
      },
    ],
    'lines': <Json>[
      <String, dynamic>{
        'source_document_type': 'DELIVERY_NOTE',
        'source_document_id': note['id'],
        'source_document_line_id': l['source_document_line_id'],
        'line_number': 1,
        'current_invoice_quantity': quantity ?? l['remaining_quantity'],
      },
    ],
  })) as Json;
}

/// An approved bill, from a fresh dispatched note; `note` is added to it.
Future<Json> apiApprovedInvoice(Server admin, {num quantity = 5}) async {
  final Json note = await apiDispatchedNote(admin, quantity: quantity);
  final Json draft = await apiDraftInvoice(admin, note);
  await apiAct(admin, 'sales-invoices', '${draft['id']}', 'approve');
  final Json whole = await admin.one('sales-invoices', '${draft['id']}');
  whole['note'] = note;
  return whole;
}

/// A cash receipt for [amount] against [invoice] (all of it, or none if
/// [allocate] is false, which leaves it an advance).
Future<Json> apiReceipt(Server server, Json invoice, num amount,
    {bool allocate = true}) async {
  return (await server.write('POST', '/api/v1/receipts', <String, dynamic>{
    'party_id': invoice['customer_id'],
    'settlement_date': _today(),
    // A receipt takes two decimals; a bill's total can carry four.
    'amount': amount.toStringAsFixed(2),
    'method': 'CASH',
    if (allocate)
      'allocations': <Json>[
        <String, dynamic>{
          'invoice_id': invoice['id'],
          'amount': amount.toStringAsFixed(2),
        },
      ],
  })) as Json;
}

/// A draft sales return of [quantity] off the approved [invoice] (whose
/// `note` carries the warehouse through its order).
Future<Json> apiDraftReturn(Server server, Json invoice,
    {num quantity = 1}) async {
  final Json line = (invoice['lines'] as List<dynamic>).first as Json;
  final Json order = (invoice['note'] as Json)['order'] as Json;
  return (await server.write('POST', '/api/v1/sales-returns', <String, dynamic>{
    'customer_id': invoice['customer_id'],
    'branch_id': invoice['branch_id'],
    'warehouse_id': order['warehouse_id'],
    'return_date': _today(),
    'source_documents': <Json>[
      <String, dynamic>{
        'source_document_type': 'SALES_INVOICE',
        'source_document_id': invoice['id'],
      },
    ],
    'lines': <Json>[
      <String, dynamic>{
        'source_document_type': 'SALES_INVOICE',
        'source_document_id': invoice['id'],
        'source_document_line_id': line['id'],
        'line_number': 1,
        'current_return_quantity': quantity,
      },
    ],
  })) as Json;
}

/// Press the toolbar button [label] and, if it asks for a reason, give one and
/// confirm. Returns every notice or dialog text seen over the next [seconds].
/// Press [label] where it is a button on the page, or else in the "..." menu
/// the toolbar keeps its less used commands behind.
Future<void> tapButtonOrMenu(WidgetTester tester, String label) async {
  final Finder direct = find.ancestor(
      of: find.text(label),
      matching: find.byWidgetPredicate((Widget w) => w is ButtonStyleButton));
  if (direct.evaluate().isNotEmpty) {
    await tapButton(tester, label);
    return;
  }
  final Finder more = find.text('…');
  if (more.evaluate().isNotEmpty) {
    await tester.tap(more.first);
    await pumpFor(tester, const Duration(milliseconds: 600));
  }
  await pumpUntil(tester, find.text(label), waitingFor: 'menu entry "$label"');
  await tester.tap(find.text(label).last);
  await pumpFor(tester, const Duration(milliseconds: 400));
}

Future<String> pressWithReason(WidgetTester tester, String label,
    {String reason = 'screen case', int seconds = 5}) async {
  await tapButtonOrMenu(tester, label);
  await pumpFor(tester, const Duration(milliseconds: 900));
  final Finder dialog = find.byType(Dialog);
  final Set<String> seen = <String>{};
  if (dialog.evaluate().isNotEmpty) {
    final Finder box = find.descendant(
        of: dialog.last, matching: find.byType(EditableText));
    if (box.evaluate().isNotEmpty) {
      await tester.enterText(box.first, reason);
      await pumpFor(tester, const Duration(milliseconds: 300));
    }
    final Finder yes = find.descendant(
        of: dialog.last,
        matching: find.byWidgetPredicate(
            (Widget w) => w is FilledButton && w.onPressed != null));
    if (yes.evaluate().isNotEmpty) await tester.tap(yes.last);
  }
  final String after = await watch(tester, confirm: false, seconds: seconds);
  if (after.isNotEmpty) seen.add(after);
  return seen.join(' || ');
}

/// Tick the first [count] delivery notes in the bill editor's tick list.
Future<void> tickNotes(WidgetTester tester, {int count = 1}) async {
  await tapKey(tester, 'sales-invoice-choose-notes');
  await pumpFor(tester, const Duration(seconds: 2));
  final Finder boxes =
      find.descendant(of: find.byType(Dialog), matching: find.byType(Checkbox));
  for (int i = 0; i < count; i++) {
    await tester.tap(boxes.at(i));
    await pumpFor(tester, const Duration(milliseconds: 400));
  }
  await confirmIfAsked(tester);
  await pumpFor(tester, const Duration(seconds: 3));
}
