// A refused import names the row and the field.
//
// Raised from manual testing: the warehouse sample was refused with "The
// request validation failed." and nothing else -- the server's detail
// (`records.0.branch_id`, "Input should be a valid UUID") never reached the
// screen. The message is rendered per row now, numbered as a spreadsheet
// numbers them, so the person knows which cell to fix.

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/ui/branches/branch_warehouse_import_dialog.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('a validation refusal is rendered per row and field', () {
    const ApiException error = ApiException(
      'The request validation failed.',
      statusCode: 422,
      details: <Object>[
        <String, Object>{
          'field': 'records.4.branch_code',
          'message': 'String should have at least 2 characters',
          'code': 'string_too_short',
        },
        <String, Object>{
          'field': 'body.records.0.mobile',
          'message': 'A valid E.164 phone number is required.',
          'code': 'value_error',
        },
        // A rule about the whole row carries no field name after the index.
        <String, Object>{
          'field': 'body.records.1',
          'message': 'Value error, Either branch_id or branch_code is required.',
          'code': 'value_error',
        },
      ],
    );

    expect(
      importRefusalMessage(error),
      'Row 6: branch_code — String should have at least 2 characters\n'
      'Row 2: mobile — A valid E.164 phone number is required.\n'
      'Row 3: Value error, Either branch_id or branch_code is required. '
      'Nothing was imported — fix the file and try again.',
    );
  });

  test('a refusal without row detail keeps the server sentence', () {
    const ApiException error = ApiException(
      'No branch with code NOWHERE in this firm.',
      statusCode: 422,
    );
    expect(
      importRefusalMessage(error),
      'No branch with code NOWHERE in this firm. '
      'Nothing was imported — fix the file and try again.',
    );
  });

  test('the warehouse sample names the branch by code, never by id', () {
    final ImportSample sample =
        branchImportSample(BranchImportTarget.warehouses, branchCode: 'WHL_HO');
    expect(sample.columns.first, 'branch_code');
    expect(sample.columns, isNot(contains('branch_id')));
    expect(sample.example.first, 'WHL_HO');
  });
}
