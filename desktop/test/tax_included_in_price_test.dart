// `included_in_price` says the price already contains the tax, so it is
// reported separately and never added to the document total. That is how MRP
// pricing works in retail and pharmacy.
//
// The engine has always honoured it, but the form could not set it: the
// profile payload sent a hardcoded `included_in_price: false`, neither draft
// class carried the field, and the client models dropped both it and
// `recoverable` when parsing the API response -- so editing a profile also
// silently reset `recoverable`.

import 'package:agency_desktop/models/tax_framework.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('the client keeps what the API sends', () {
    test('a profile component carries both flags', () {
      final TaxProfileComponentRecord component =
          TaxProfileComponentRecord.fromJson(const {
        'id': 'pc-1',
        'tax_component_id': 'c-1',
        'percentage': '18.0000',
        'label': 'GST',
        'short_label': 'GST',
        'calculation_order': 1,
        'included_in_price': true,
        'recoverable': true,
      });

      expect(component.includedInPrice, isTrue);
      expect(component.recoverable, isTrue,
          reason: 'editing a profile used to reset this to false');
    });

    test('a system component carries the defaults a profile starts from', () {
      final TaxComponentRecord component = TaxComponentRecord.fromJson(const {
        'id': 'c-1',
        'tax_system_id': 's-1',
        'code': 'CGST',
        'name': 'Central GST',
        'label': 'CGST',
        'percentage': '9.0000',
        'status': 'ACTIVE',
        'is_deleted': false,
        'included_in_price': true,
        'recoverable': true,
      });

      expect(component.includedInPrice, isTrue);
      expect(component.recoverable, isTrue);
    });

    test('an older payload without the flags still parses', () {
      // The fields are optional on purpose: a response from a server that
      // predates them must not throw.
      final TaxProfileComponentRecord component =
          TaxProfileComponentRecord.fromJson(const {
        'id': 'pc-1',
        'tax_component_id': 'c-1',
        'percentage': '5.0000',
        'label': 'VAT',
        'short_label': 'VAT',
        'calculation_order': 1,
      });

      expect(component.includedInPrice, isFalse);
      expect(component.recoverable, isFalse);
    });
  });
}
