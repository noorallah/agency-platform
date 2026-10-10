import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/phase2/document_page.dart';
import 'package:agency_desktop/phase2/indian_format.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// One of the server's own pricing answers, kept in
/// `test/fixtures/server_pricing`.
///
/// They are written by the backend's
/// `tests/unit/test_desktop_pricing_fixtures.py`, which prices each case with
/// the real service and fails when a file and the service disagree. A test
/// that needs a priced document reads one of these and does not write its
/// own: a stand-in written by hand carries the writer's idea of the answer,
/// which is how three screens showed a line's total with tax under *Taxable*
/// while every test passed (D-UI-95).
Json serverPricing(String name) => jsonDecode(
      File('test/fixtures/server_pricing/$name.json').readAsStringSync(),
    ) as Json;

double _figure(Object? value) => double.parse('$value');

/// The lines of [document] somebody typed (not an offer's own free line).
List<Json> pricedLines(Json document) => <Json>[
      for (final dynamic line in document['lines'] as List<dynamic>)
        if (_figure((line as Map)['net_amount']) != 0)
          Map<String, dynamic>.from(line),
    ];

/// The server's figures must add up before a screen is judged against them:
/// the lines' tax is the document's tax, and the lines' amounts with the
/// document's own charges and rounding are its total.
void expectDocumentAddsUp(Json document) {
  double tax = 0;
  double net = 0;
  for (final Json line in pricedLines(document)) {
    tax += _figure(line['tax_amount']);
    net += _figure(line['net_amount']);
  }
  expect(tax, closeTo(_figure(document['tax_total']), .011),
      reason: "the lines' tax is the document's tax");
  final double extras = _figure(document['additional_charges'] ?? 0) +
      _figure(document['round_off'] ?? 0);
  expect(net + extras, closeTo(_figure(document['grand_total']), .011),
      reason: "the lines' amounts come to the document's total");
}

/// Every priced line's row shows what the server priced, and the foot shows
/// the document's total.
///
/// Row [index] is found by `ValueKey('$rowKey$index')`. For each line the row
/// must show:
///
/// - its **taxable value**: the line's amount less its tax, worked out here
///   and not by the screen's own code;
/// - its **tax rate**: that tax as a percentage of that taxable value;
/// - its **amount**: what the server calls `net_amount`, tax included.
///
/// A screen that reads the amount as the taxable value, or that works the
/// taxable value out as gross less the line's own discount, fails here on
/// any document with tax, a bill discount or a delivery charge.
void expectLinesReconcile(
  WidgetTester tester, {
  required Json document,
  required String rowKey,
}) {
  expectDocumentAddsUp(document);
  final List<Json> lines = pricedLines(document);
  expect(lines, isNotEmpty, reason: 'the document has a priced line');
  for (int index = 0; index < lines.length; index += 1) {
    final double net = _figure(lines[index]['net_amount']);
    final double tax = _figure(lines[index]['tax_amount']);
    final double taxable = net - tax;
    final String rate =
        '${documentQuantity((tax / taxable * 100).toStringAsFixed(1))}%';
    final Finder row = find.byKey(ValueKey<String>('$rowKey$index'));
    expect(row, findsOneWidget, reason: 'line ${index + 1} has a row');
    Finder inRow(String text) =>
        find.descendant(of: row, matching: find.text(text));
    expect(inRow(indianAmount(taxable, full: true)), findsWidgets,
        reason: 'line ${index + 1} shows its taxable value, before tax');
    expect(inRow(rate), findsOneWidget,
        reason: 'line ${index + 1} shows the rate its tax is of that value');
    expect(inRow(indianAmount(net, full: true)), findsWidgets,
        reason: 'line ${index + 1} shows its amount, tax included');
  }
  expect(
    find.text(indianAmount(_figure(document['grand_total']), full: true)),
    findsWidgets,
    reason: "the foot shows the document's total",
  );
}
