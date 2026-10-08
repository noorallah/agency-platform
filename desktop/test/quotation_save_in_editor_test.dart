import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/customer.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/ui/quotations/quotation_editor_dialog.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/first_line.dart';

/// The quotation editor says why a save did not happen and keeps what was
/// typed (D-UI-64, D-UI-65). Before, a save with no customer did nothing and
/// said nothing, and a save the server refused closed the editor first.
Future<void> _open(
  WidgetTester tester, {
  required Future<void> Function(Json payload) onSave,
  required void Function(Json? result) onClosed,
}) async {
  tester.view.physicalSize = const Size(1600, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Builder(
        builder: (context) => TextButton(
          onPressed: () async {
            onClosed(await Navigator.of(context).push<Json>(
              MaterialPageRoute(
                builder: (_) => Scaffold(
                  body: Phase2Scope(
                    child: QuotationEditorDialog(
                      onSave: onSave,
                      customers: [
                        Customer.fromJson({
                          'id': 'c1',
                          'code': 'C-0102',
                          'name': 'Sri Murugan Stores',
                          'display_name': 'Sri Murugan Stores',
                        }),
                      ],
                      products: [
                        Product.fromJson({
                          'id': 'p1',
                          'code': 'P-1002',
                          'name': 'Tata Salt 1kg',
                          'selling_price': '26.00',
                        }),
                      ],
                      branches: [
                        BranchRecord.fromJson({
                          'id': 'ho',
                          'code': 'HO',
                          'name': 'Head office',
                          'display_name': 'Head office',
                          'is_default': true,
                        }),
                      ],
                      warehouses: [
                        WarehouseRecord.fromJson({
                          'id': 'w1',
                          'code': 'MAIN',
                          'name': 'Main',
                          'display_name': 'Main',
                          'branch_id': 'ho',
                          'is_default': true,
                        }),
                      ],
                      today: DateTime(2026, 9, 26),
                    ),
                  ),
                ),
              ),
            ));
          },
          child: const Text('open'),
        ),
      ),
    ),
  ));
  await tester.tap(find.text('open'));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('a save with no customer names the customer', (tester) async {
    int saves = 0;
    bool closed = false;
    await _open(
      tester,
      onSave: (_) async => saves += 1,
      onClosed: (_) => closed = true,
    );
    await fillFirstLine(tester, document: 'quotation', product: 'Tata Salt');

    await tester.tap(find.byKey(const ValueKey('quotation-save')));
    await tester.pumpAndSettle();

    expect(find.text('Choose the customer.'), findsOneWidget);
    expect(saves, 0);
    expect(closed, isFalse);
  });

  testWidgets('a save with no product names the line', (tester) async {
    int saves = 0;
    await _open(tester, onSave: (_) async => saves += 1, onClosed: (_) {});
    await tester.tap(find.byKey(const ValueKey('quotation-customer')));
    await tester.pumpAndSettle();
    await tester.tap(find.textContaining('Sri Murugan').last);
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const ValueKey('quotation-save')));
    await tester.pumpAndSettle();

    expect(find.text('Choose a product on line 1.'), findsOneWidget);
    expect(saves, 0);
  });

  testWidgets('a refused save keeps the editor open with what was typed',
      (tester) async {
    bool refuse = true;
    Json? sent;
    Json? result;
    bool closed = false;
    await _open(
      tester,
      onSave: (payload) async {
        if (refuse) {
          throw const ApiException(
            'Customer C-0102 is inactive.',
            statusCode: 422,
          );
        }
        sent = payload;
      },
      onClosed: (value) {
        closed = true;
        result = value;
      },
    );
    await tester.tap(find.byKey(const ValueKey('quotation-customer')));
    await tester.pumpAndSettle();
    await tester.tap(find.textContaining('Sri Murugan').last);
    await tester.pumpAndSettle();
    await fillFirstLine(
      tester,
      document: 'quotation',
      product: 'Tata Salt',
      quantity: '7',
    );

    await tester.tap(find.byKey(const ValueKey('quotation-save')));
    await tester.pumpAndSettle();

    expect(closed, isFalse);
    expect(find.byKey(const ValueKey('quotation-save-error')), findsOneWidget);
    expect(find.textContaining('Customer C-0102 is inactive.'), findsOneWidget);
    // The quantity typed is still in its box.
    expect(find.text('7'), findsWidgets);

    refuse = false;
    await tester.tap(find.byKey(const ValueKey('quotation-save-print')));
    await tester.pumpAndSettle();

    expect(closed, isTrue);
    expect(sent?['customer_id'], 'c1');
    // The save itself never carries the list's print flag.
    expect(sent?.containsKey(QuotationEditorDialog.printAfterSave), isFalse);
    expect(result?[QuotationEditorDialog.printAfterSave], isTrue);
  });
}
