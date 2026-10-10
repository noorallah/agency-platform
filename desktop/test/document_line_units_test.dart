import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/models/uom_packaging.dart';
import 'package:agency_desktop/ui/document_framework/document_line_labels.dart';
import 'package:flutter_test/flutter_test.dart';

/// D-UI-98: a sales line names a unit only when it was typed in a unit other
/// than its product's own, so an opened sales order, delivery note or bill
/// printed '-' under Unit for every ordinary line, and the Unit column of a
/// quotation, an order and a bill being typed read blank.
Product _product(Map<String, dynamic> more) => Product.fromJson({
      'id': 'p1',
      'code': 'MED-AMOX250',
      'name': 'Amoxicillin 250 mg',
      ...more,
    });

void main() {
  final List<UomRecord> units = [
    UomRecord.fromJson({'id': 'u-strip', 'code': 'STRIP', 'name': 'Strip'}),
    UomRecord.fromJson({'id': 'u-box', 'code': 'BOX', 'name': 'Box'}),
    UomRecord.fromJson({'id': 'u-piece', 'code': 'PIECE', 'name': 'Piece'}),
  ];

  DocumentLineLabels labels(Map<String, dynamic> product) =>
      DocumentLineLabels(products: [_product(product)], units: units);

  test('a line that names its unit shows that unit', () {
    final DocumentLineLabels shown = labels({'sales_uom_id': 'u-strip'});
    expect(shown.unitOf('u-box', 'p1'), 'BOX');
  });

  test("a line that names none shows its product's selling unit", () {
    final DocumentLineLabels shown = labels({
      'sales_uom_id': 'u-strip',
      'inventory_uom_id': 'u-box',
      'base_uom_id': 'u-piece',
    });
    expect(shown.unitOf('', 'p1'), 'STRIP');
  });

  test('with no selling unit the stock unit stands in, then the base', () {
    expect(
      labels({'inventory_uom_id': 'u-box', 'base_uom_id': 'u-piece'})
          .unitOf('', 'p1'),
      'BOX',
    );
    expect(labels({'base_uom_id': 'u-piece'}).unitOf('', 'p1'), 'PIECE');
  });

  test('a product naming no unit by id shows the words typed on it', () {
    expect(labels({'unit': 'Bottle'}).unitOf('', 'p1'), 'Bottle');
    expect(labels({'unit_code': 'STRIP'}).unitOf('', 'p1'), 'STRIP');
  });

  test('a product the view does not hold shows nothing, never an id', () {
    expect(labels({'sales_uom_id': 'u-strip'}).unitOf('', 'p-other'), '');
  });

  test("a product's display unit is its words, else the server's code", () {
    expect(_product({'unit': 'Bottle', 'unit_code': 'PIECE'}).displayUnit,
        'Bottle');
    expect(_product({'unit': '', 'unit_code': 'STRIP'}).displayUnit, 'STRIP');
    expect(_product({'unit': '  ', 'unit_code': 'STRIP'}).displayUnit, 'STRIP');
    expect(_product(const {}).displayUnit, '');
  });
}
