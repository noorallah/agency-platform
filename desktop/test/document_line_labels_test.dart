// A document view prints names for the ids a line carries.
//
// Raised from manual testing at 7.8: the goods receipt view showed the
// product as its UUID. Every workspace already reads the firm's products;
// this resolves the ids against those lists, falling back to the id itself
// for one the lists do not hold so a stale list never blanks a line.

import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/models/tax_framework.dart';
import 'package:agency_desktop/models/uom_packaging.dart';
import 'package:agency_desktop/ui/document_framework/document_line_labels.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  final DocumentLineLabels labels = DocumentLineLabels(
    products: [
      Product.fromJson(<String, dynamic>{
        'id': 'p-1',
        'firm_id': 'firm-1',
        'code': 'DETER1K',
        'name': 'Detergent Powder 1kg',
        'status': 'ACTIVE',
      }),
    ],
    units: [
      UomRecord.fromJson(<String, dynamic>{
        'id': 'u-kg',
        'code': 'KG',
        'name': 'Kilogram',
        'status': 'ACTIVE',
      }),
    ],
    taxProfiles: [
      TaxProfileRecord.fromJson(<String, dynamic>{
        'id': 't-18',
        'tax_system_id': 'gst',
        'code': 'GST_18_LOCAL',
        'name': 'GST 18% local',
        'label': 'GST 18%',
        'status': 'ACTIVE',
        'components': <Map<String, dynamic>>[],
      }),
    ],
  );

  test('a known id becomes its code and name', () {
    expect(labels.product('p-1'), 'DETER1K — Detergent Powder 1kg');
    expect(labels.unit('u-kg'), 'KG');
    expect(labels.taxProfile('t-18'), 'GST_18_LOCAL');
  });

  test('an unknown id is shown as itself, never blanked', () {
    expect(labels.product('p-9'), 'p-9');
    expect(labels.unit('u-9'), 'u-9');
    expect(labels.taxProfile('t-9'), 't-9');
  });

  test('an empty id stays empty', () {
    expect(labels.product(''), '');
    expect(labels.unit(''), '');
    expect(labels.taxProfile(''), '');
  });

  test('with no lists at all the ids are shown, as the views did before', () {
    const DocumentLineLabels none = DocumentLineLabels();
    expect(none.product('p-1'), 'p-1');
  });
}
