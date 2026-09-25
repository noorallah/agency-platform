import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/customer.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/ui/document_framework/document_line_labels.dart';
import 'package:agency_desktop/ui/quotations/quotation_editor_dialog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// A new document ships from the firm's default warehouse, never the newest.
///
/// D-QA-17, found on the installed laptop 2026-09-25: the firm had MAIN (made
/// default by the Set up panel) and STORE2 (added by hand). Warehouses are
/// listed newest first and the quotation form took the first, so the quote
/// shipped from STORE2, the converted order inherited it, and approving the
/// order reserved four units in a warehouse holding none while MAIN's ten sat
/// untouched. The order view never printed its warehouse, so it read as an
/// order with none.
BranchRecord _branch(String id, {bool isDefault = false}) =>
    BranchRecord.fromJson({
      'id': id,
      'code': id.toUpperCase(),
      'name': 'Branch $id',
      'display_name': 'Branch $id',
      'is_default': isDefault,
    });

WarehouseRecord _warehouse(
  String id,
  String code, {
  required String branchId,
  bool isDefault = false,
}) =>
    WarehouseRecord.fromJson({
      'id': id,
      'code': code,
      'name': '$code store',
      'display_name': '$code store',
      'branch_id': branchId,
      'is_default': isDefault,
    });

/// Newest first, the way `GET /warehouses` answers by default.
final List<WarehouseRecord> _newestFirst = <WarehouseRecord>[
  _warehouse('w-store2', 'STORE2', branchId: 'ho'),
  _warehouse('w-main', 'MAIN', branchId: 'ho', isDefault: true),
];

void main() {
  group('the default a new document takes', () {
    test('is the branch default warehouse, not the newest', () {
      expect(preferredWarehouseId(_newestFirst, branchId: 'ho'), 'w-main');
      expect(preferredWarehouseId(_newestFirst), 'w-main');
    });

    test('is the chosen branch\'s default, not another branch\'s', () {
      final List<WarehouseRecord> two = <WarehouseRecord>[
        _warehouse('w-north', 'NORTH', branchId: 'north', isDefault: true),
        ..._newestFirst,
      ];
      expect(preferredWarehouseId(two, branchId: 'ho'), 'w-main');
      expect(preferredWarehouseId(two, branchId: 'north'), 'w-north');
      // Two branch defaults and no branch named: nothing is guessed.
      expect(preferredWarehouseId(two), isNull);
    });

    test('is nothing when several warehouses and none is marked', () {
      final List<WarehouseRecord> unmarked = <WarehouseRecord>[
        _warehouse('w-a', 'A', branchId: 'ho'),
        _warehouse('w-b', 'B', branchId: 'ho'),
      ];
      expect(preferredWarehouseId(unmarked, branchId: 'ho'), isNull);
      expect(
        preferredWarehouseId(unmarked.sublist(1), branchId: 'ho'),
        'w-b',
      );
    });

    test('is the default branch, not the newest', () {
      expect(
        preferredBranchId(<BranchRecord>[
          _branch('new'),
          _branch('ho', isDefault: true),
        ]),
        'ho',
      );
      expect(preferredBranchId(<BranchRecord>[_branch('a'), _branch('b')]),
          isNull);
      expect(preferredBranchId(<BranchRecord>[_branch('only')]), 'only');
    });
  });

  testWidgets('a new quotation ships from the default warehouse',
      (tester) async {
    tester.view.physicalSize = const Size(1366, 768);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: QuotationEditorDialog(
            customers: [
              Customer.fromJson({
                'id': 'c1',
                'code': 'QA-C1',
                'name': 'QA Customer',
                'display_name': 'QA Customer',
              }),
            ],
            products: [
              Product.fromJson({'id': 'p1', 'code': 'QA-P1', 'name': 'QA'}),
            ],
            branches: [_branch('ho', isDefault: true)],
            warehouses: _newestFirst,
            today: DateTime(2026, 9, 25),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    final DropdownButton<String> shipsFrom = tester.widget(
      find.descendant(
        of: find.widgetWithText(DropdownButtonFormField<String>, 'Ships from'),
        matching: find.byType(DropdownButton<String>),
      ),
    );
    expect(shipsFrom.value, 'w-main');
  });

  test('the order view names where the order ships from', () {
    final DocumentLineLabels labels = DocumentLineLabels(
      branches: <BranchRecord>[_branch('ho', isDefault: true)],
      warehouses: _newestFirst,
    );
    expect(labels.warehouse('w-main'), 'MAIN - MAIN store');
    expect(labels.branch('ho'), 'HO - Branch ho');
    // A warehouse the list does not hold prints its id, never nothing.
    expect(labels.warehouse('w-gone'), 'w-gone');
  });
}
