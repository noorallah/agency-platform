// A document view names its branch and warehouse. The goods receipt, the
// purchase invoice, the purchase return and the delivery note each handed the
// header the record's `branch_id`, so the view printed a UUID under "Branch"
// (and the receipt its firm's id, the bills their business profile's).
// Found by the owner on the demo firm, 2026-10-09.

import 'dart:io';

import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/ui/document_framework/document_line_labels.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('no document header is handed a bare id', () {
    final RegExp bare = RegExp(
      r'\b(branch|warehouse|firm|businessProfile):\s*'
      r'(branchId|warehouseId|firmId|businessProfileId)\s*,',
    );
    final List<String> found = <String>[];
    for (final FileSystemEntity entry
        in Directory('lib').listSync(recursive: true)) {
      if (entry is! File || !entry.path.endsWith('.dart')) continue;
      final String source = entry.readAsStringSync();
      // Only where a header is being built; a model's own constructor
      // (`branchId: branchId`) is not a header.
      for (final RegExpMatch header
          in RegExp(r'DocumentHeaderSnapshot\(([^;]*?)\);', dotAll: true)
              .allMatches(source)) {
        for (final RegExpMatch match in bare.allMatches(header.group(1)!)) {
          found.add('${entry.path}: ${match.group(0)}');
        }
      }
    }
    expect(found, isEmpty, reason: 'a header shows what a person reads');
  });

  test('the lookup gives a code and a name for a branch and a warehouse', () {
    final DocumentLineLabels labels = DocumentLineLabels(
      branches: <BranchRecord>[
        BranchRecord.fromJson(<String, dynamic>{
          'id': 'b-1',
          'code': 'HO',
          'name': 'Head Office',
          'display_name': 'Head Office',
        }),
      ],
      warehouses: <WarehouseRecord>[
        WarehouseRecord.fromJson(<String, dynamic>{
          'id': 'w-1',
          'code': 'MAIN',
          'name': 'Main Warehouse',
          'display_name': 'Main Warehouse',
          'branch_id': 'b-1',
        }),
      ],
    );
    expect(labels.branch('b-1'), 'HO - Head Office');
    expect(labels.warehouse('w-1'), 'MAIN - Main Warehouse');
    expect(labels.branch(''), '');
  });
}
