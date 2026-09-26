import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/customer.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/models/quotation.dart';
import 'package:agency_desktop/ui/quotations/quotation_editor_dialog.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// The new-quotation screen in phase 2, as the owner approved it (wireframe
/// view 7): one screen whose figures are the server's own preview, a side
/// panel for the line being typed, and Save & print handed back to the list.
QuotationPreviewRecord _priced(Json draft) {
  final List<dynamic> lines = draft['lines'] as List<dynamic>;
  final Map<String, dynamic> line = lines.first as Map<String, dynamic>;
  final double quantity = double.parse('${line['quantity']}');
  final double net = quantity * double.parse('${line['unit_price']}');
  return QuotationPreviewRecord.fromJson({
    'interstate': false,
    'quotation': {
      'id': '',
      'quotation_number': 'QT-2026-2027-000012',
      'customer_id': draft['customer_id'],
      'subtotal': net.toStringAsFixed(4),
      'tax_total': (net * .18).toStringAsFixed(4),
      'grand_total': (net * 1.18).toStringAsFixed(4),
      'lines': [
        {
          'line_number': 1,
          'product_id': line['product_id'],
          'quantity': line['quantity'],
          'unit_price': line['unit_price'],
          'discount_percent': '0',
          'discount_source': 'none',
          'net_amount': net.toStringAsFixed(4),
          'tax_amount': (net * .18).toStringAsFixed(4),
        },
      ],
    },
    'lines': [
      {
        'line_number': 1,
        'product_id': line['product_id'],
        'last_price': '82.5000',
        'last_invoice_number': 'SI-2026-2027-000012',
        'last_invoice_date': '2026-09-13',
        'available_quantity': '876.0000',
      },
    ],
  });
}

void main() {
  testWidgets('it prices as it is typed and hands back Save & print',
      (tester) async {
    tester.view.physicalSize = const Size(1600, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final List<Json> asked = [];
    Json? result;
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Phase2Scope(
          child: Builder(
            builder: (context) => TextButton(
              onPressed: () async {
                result = await Navigator.of(context).push<Json>(
                  MaterialPageRoute(
                    builder: (_) => Scaffold(
                      body: Phase2Scope(
                        child: QuotationEditorDialog(
                          customers: [
                            Customer.fromJson({
                              'id': 'c1',
                              'code': 'C-0102',
                              'name': 'Sri Murugan Stores',
                              'display_name': 'Sri Murugan Stores',
                              'gst_number': '33AAKFS1122K1Z4',
                              'current_outstanding': '86300',
                              'credit_limit': '100000',
                              'payment_terms_days': 30,
                            }),
                          ],
                          products: [
                            Product.fromJson({
                              'id': 'p1',
                              'code': 'P-1002',
                              'name': 'Tata Salt 1kg',
                              'selling_price': '26.00',
                              'mrp': '28.00',
                              'hsn_sac': '2501',
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
                          preview: (draft) async {
                            asked.add(draft);
                            return _priced(draft);
                          },
                        ),
                      ),
                    ),
                  ),
                );
              },
              child: const Text('open'),
            ),
          ),
        ),
      ),
    ));
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    // The first price is asked for as the screen opens.
    await tester.pump(const Duration(milliseconds: 400));
    await tester.pumpAndSettle();
    expect(asked, isNotEmpty);
    expect(tester.takeException(), isNull);

    // Type a quantity: the figures are the preview's.
    final Finder quantity = find
        .descendant(
          of: find.byKey(const ValueKey('quotation-line-0')),
          matching: find.byType(EditableText),
        )
        .at(1);
    await tester.enterText(quantity, '50');
    await tester.pump(const Duration(milliseconds: 400));
    await tester.pumpAndSettle();
    expect(asked.last['lines'][0]['quantity'], '50');
    expect(find.text('QT-2026-2027-000012 (new)'), findsOneWidget);
    // 50 x 26 = 1,300 taxable; 18% = 234; the side panel says where from.
    expect(find.text('1,534.00'), findsWidgets);
    expect(find.byKey(const ValueKey('document-side-panel')), findsOneWidget);
    expect(find.text('82.50'), findsOneWidget);
    expect(find.textContaining('One thousand five hundred thirty four'),
        findsOneWidget);
    // Payment terms came from the customer.
    expect(find.text('30 days'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('quotation-save-print')));
    await tester.pumpAndSettle();
    expect(result?[QuotationEditorDialog.printAfterSave], isTrue);
    expect(result?['customer_id'], 'c1');
  });
}
