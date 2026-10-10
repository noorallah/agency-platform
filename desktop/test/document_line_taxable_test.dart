import 'package:agency_desktop/phase2/document_page.dart';
import 'package:flutter_test/flutter_test.dart';

/// D-UI-95, D-UI-96: a line's taxable value is its amount less its tax,
/// whatever went into the amount. The figures are the running server's own,
/// priced on the demo firm on 2026-10-10.
void main() {
  test('a sales line: ten at 52.00 with 12% GST', () {
    // The server sends 582.40 as the line's amount and 62.40 as its tax.
    expect(documentLineTaxable('582.4000', '62.4000'), closeTo(520, .0001));
  });

  test('a purchase order line under a discount on the whole order', () {
    // Ten at 42.00 is 420.00; the order's discount of 100.00 falls on the
    // line, so it is taxed on 320.00: 38.40 at 12%, 358.40 in all. Worked
    // as gross less the line's own discount, the screen said 420.00.
    final double taxable = documentLineTaxable('358.4000', '38.4000')!;
    expect(taxable, closeTo(320, .0001));
    expect(38.4 / taxable * 100, closeTo(12, .0001));
  });

  test('a line with no tax is worth its amount', () {
    expect(documentLineTaxable('250.00', null), 250);
    expect(documentLineTaxable(250, 0), 250);
  });

  test('a line not priced yet has no taxable value', () {
    expect(documentLineTaxable(null, null), isNull);
    expect(documentLineTaxable('', '10'), isNull);
  });
}
