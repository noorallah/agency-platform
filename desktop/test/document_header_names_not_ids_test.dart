// A document view names its branch and warehouse. The goods receipt, the
// purchase invoice, the purchase return and the delivery note each handed the
// header the record's `branch_id`, so the view printed a UUID under "Branch"
// (and the receipt its firm's id, the bills their business profile's).
// Found by the owner on the demo firm, 2026-10-09.

import 'dart:io';

import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/document_framework.dart';
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

  // The first fix (#1390) asked the page's lookup for the name, and the four
  // pages built that lookup without branches or warehouses, so it handed the
  // id straight back and the view still printed it.
  test('each page loads branches and warehouses into its lookup', () {
    for (final String path in <String>[
      'lib/ui/goods_receipts/goods_receipt_management_page.dart',
      'lib/ui/purchase_invoices/purchase_invoice_management_page.dart',
      'lib/ui/purchase_returns/purchase_return_management_page.dart',
      'lib/ui/delivery_notes/delivery_note_management_page.dart',
    ]) {
      final String source = File(path).readAsStringSync();
      expect(source, contains('DocumentLineLabels.load('), reason: path);
      expect(
        RegExp(r'_labels = DocumentLineLabels\(').hasMatch(source),
        isFalse,
        reason: '$path builds a lookup of its own, which is how the '
            'branches were left out',
      );
    }
  });

  test('a name the lookup cannot give is blank, never the id', () {
    const DocumentLineLabels empty = DocumentLineLabels();
    expect(namedOrBlank(empty.branch, 'b-1'), '');
    expect(namedOrBlank(null, 'b-1'), '');
    expect(namedOrBlank((String id) => 'HO - Head Office', 'b-1'),
        'HO - Head Office');
  });
}
