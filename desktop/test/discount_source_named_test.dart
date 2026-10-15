import 'package:flutter_test/flutter_test.dart';
import 'package:agency_desktop/ui/workspace/discount_source.dart';

/// L7 step 2: the side panel names the arrangement a line's rate came from.
void main() {
  Map<String, dynamic> row(String source, String code, String discount,
          {String state = 'APPLIED'}) =>
      <String, dynamic>{
        'source': source,
        'code': code,
        'state': state,
        'discount_amount': discount,
      };

  test('a promotion is named by the offers that took something off', () {
    expect(
      discountSourceNamed('promotion', <dynamic>[
        row('promotion', 'TEA-5', '55.0000'),
        row('promotion', 'TEA-11', '0.0000'),
        row('promotion', 'TEA-2', '10.0000'),
      ]),
      'TEA-5 + TEA-2',
    );
  });

  test('a price list is named by its code', () {
    expect(
      discountSourceNamed('price_list', <dynamic>[
        row('promotion', 'TEA-11', '0'),
        row('price_list', 'CITY', '44.00'),
      ]),
      'price list CITY',
    );
  });

  test('without rows, or with refused ones only, the old words stand', () {
    expect(discountSourceNamed('promotion', null), 'a promotion');
    expect(
      discountSourceNamed('promotion', <dynamic>[
        row('promotion', 'TEA-9', '5', state: 'REFUSED'),
      ]),
      'a promotion',
    );
    expect(discountSourceNamed('customer', <dynamic>[]),
        "the customer's standing rate");
  });
}
