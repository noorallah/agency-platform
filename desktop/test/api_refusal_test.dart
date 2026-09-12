// A refusal names the fields it is about.
//
// "The request validation failed." on its own told nobody anything; the
// server sends the fields in `details`, and every editor dropped them.

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('a validation refusal lists its fields, rows numbered from one', () {
    const ApiException error = ApiException(
      'The request validation failed.',
      statusCode: 422,
      details: <Object>[
        <String, Object>{
          'field': 'body.po_number',
          'message': 'Extra inputs are not permitted',
          'code': 'extra_forbidden',
        },
        <String, Object>{
          'field': 'body.lines.0.unit_price',
          'message': 'Input should be greater than or equal to 0',
          'code': 'greater_than_equal',
        },
        <String, Object>{
          'field': 'body.lines.2',
          'message': 'Value error, a line needs a product',
          'code': 'value_error',
        },
      ],
    );
    expect(
      refusalMessage(error),
      'The request validation failed.\n'
      'po_number: Extra inputs are not permitted\n'
      'lines 1, unit_price: Input should be greater than or equal to 0\n'
      'lines 3: Value error, a line needs a product',
    );
  });

  test('a refusal with no detail is the message alone', () {
    const ApiException error = ApiException('Submit the order first.');
    expect(refusalMessage(error), 'Submit the order first.');
  });
}
