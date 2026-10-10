import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/customer.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/models/quotation.dart';
import 'package:agency_desktop/ui/quotations/quotation_editor_dialog.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/first_line.dart';

/// The new-quotation screen in phase 2, as the owner approved it (wireframe
/// view 7): one screen whose figures are the server's own preview, a side
/// panel for the line being typed, and Save & print handed back to the list.
QuotationPreviewRecord _priced(Json draft) {
  final List<dynamic> lines = draft['lines'] as List<dynamic>;
  final Map<String, dynamic> line = lines.first as Map<String, dynamic>;
  final double quantity = double.parse('${line['quantity']}');
  final double net =
      quantity * double.parse('${line['unit_price'] ?? '26'}');
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
          'unit_price': line['unit_price'] ?? '26',
          'discount_percent': '0',
          'discount_source': 'none',
          // With its tax, as the server sends it (D-UI-95): this fake used
          // to send the pre-tax figure, which is how the screen came to
          // show the line's total under "Taxable" and no test saw it.
          'net_amount': (net * 1.18).toStringAsFixed(4),
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

/// A new quotation starts with no customer and no product (D-UI-22): take
/// the ones these tests were written against.
Future<void> chooseCustomerAndProduct(WidgetTester tester) async {
  await tester.tap(find.byKey(const ValueKey('quotation-customer')));
  await tester.pumpAndSettle();
  await tester.tap(find.textContaining('Sri Murugan').last);
  await tester.pumpAndSettle();
  await fillFirstLine(tester, document: 'quotation', product: 'Tata Salt');
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
    await chooseCustomerAndProduct(tester);
    // The first price is asked for once the customer and product are named.
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
    // D-UI-95: the line's taxable value is before its tax, so the rate
    // reads 18% -- not the 15.3% that 234 is of 1,534.
    expect(find.text('1,300.00'), findsWidgets);
    expect(find.text('18%'), findsWidgets);
    expect(find.text('15.3%'), findsNothing);
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

  Future<List<Json>> pumpEditor(
    WidgetTester tester, {
    Quotation? existing,
    bool rateIncludesTax = false,
    Size size = const Size(1600, 900),
    bool choose = true,
    required void Function(Json?) onResult,
  }) async {
    tester.view.physicalSize = size;
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final List<Json> asked = [];
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Builder(
          builder: (context) => TextButton(
            onPressed: () async {
              onResult(await Navigator.of(context).push<Json>(
                MaterialPageRoute(
                  builder: (_) => Scaffold(
                    body: Phase2Scope(
                      child: QuotationEditorDialog(
                        existing: existing,
                        rateIncludesTax: rateIncludesTax,
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
                        preview: (draft) async {
                          asked.add(draft);
                          return _priced(draft);
                        },
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
    if (existing == null && choose) await chooseCustomerAndProduct(tester);
    await tester.pump(const Duration(milliseconds: 400));
    await tester.pumpAndSettle();
    return asked;
  }

  testWidgets('a blank second line does not stop the first being priced',
      (tester) async {
    // D-UI-93: adding a row used to blank the pricing of every row.
    final List<Json> asked = await pumpEditor(tester, onResult: (_) {});
    final int before = asked.length;
    await tester.tap(find.textContaining('+ add a'));
    await tester.pump(const Duration(milliseconds: 400));
    await tester.pumpAndSettle();
    // Asked again, for the finished line alone.
    expect(asked.length, greaterThan(before));
    expect(asked.last['lines'], hasLength(1));
    // One at 26 with 18% tax: the first line still shows 30.68.
    expect(find.text('30.68'), findsWidgets);
    expect(tester.takeException(), isNull);
  });

  testWidgets('lines typed before a customer is chosen say why no tax shows',
      (tester) async {
    // D-UI-91: the owner added two lines, saw no tax and no reason.
    const String hint =
        'Choose a customer, and the offer is priced with its tax.';
    final List<Json> asked =
        await pumpEditor(tester, choose: false, onResult: (_) {});
    expect(find.text(hint), findsOneWidget);
    // D-UI-94: drawn as a warning label, not grey words at the foot.
    const ValueKey<String> label = ValueKey('document-totals-warning');
    expect(
      find.descendant(of: find.byKey(label), matching: find.text(hint)),
      findsOneWidget,
    );

    await fillFirstLine(tester, document: 'quotation', product: 'Tata Salt');
    await tester.pump(const Duration(milliseconds: 400));
    await tester.pumpAndSettle();
    // A finished line, and still nothing to price it for.
    expect(asked, isEmpty);
    expect(find.text(hint), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('quotation-customer')));
    await tester.pumpAndSettle();
    await tester.tap(find.textContaining('Sri Murugan').last);
    await tester.pumpAndSettle();
    await tester.pump(const Duration(milliseconds: 400));
    await tester.pumpAndSettle();
    expect(asked, isNotEmpty);
    expect(find.text(hint), findsNothing);
    expect(find.byKey(label), findsNothing);
    expect(tester.takeException(), isNull);
  });

  Quotation saved({
    String coupon = 'SAVE10',
    String free = '0',
    bool freeRefused = false,
    bool rateIncludesTax = false,
    String enteredRate = '',
  }) =>
      Quotation.fromJson({
        'rate_includes_tax': rateIncludesTax,
        'id': 'q1',
        'version': 3,
        'customer_id': 'c1',
        'branch_id': 'ho',
        'warehouse_id': 'w1',
        'quotation_number': 'QT-1',
        'quotation_date': '2026-09-20',
        'valid_until': '2026-10-20',
        'status': 'DRAFT',
        'coupon_code': coupon,
        'lines': [
          {
            'line_number': 1,
            'product_id': 'p1',
            'quantity': '10',
            'unit_price': '26.00',
            if (enteredRate.isNotEmpty) 'entered_rate': enteredRate,
            'discount_percent': '0',
            'free_quantity': free,
            if (freeRefused) 'free_goods_refused': true,
          },
        ],
      });

  Finder lineBoxes() => find.descendant(
        of: find.byKey(const ValueKey('quotation-line-0')),
        matching: find.byType(EditableText),
      );

  // Backlog 64 row 4: an offer quotes the shelf price.
  testWidgets('a new quotation starts from the firm default for GST rates',
      (tester) async {
    Json? result;
    final List<Json> asked = await pumpEditor(tester,
        rateIncludesTax: true, onResult: (value) => result = value);
    final Finder toggle =
        find.byKey(const ValueKey('quotation-rate-includes-tax'));
    expect(tester.widget<Switch>(toggle).value, isTrue);
    expect(find.text('Rate incl. GST'), findsOneWidget);
    expect(find.text('Shelf price'), findsOneWidget);
    // The product's own price is before tax: the box starts blank and the
    // preview is asked without a rate.
    expect(asked.last['rate_includes_tax'], isTrue);
    expect(asked.last['lines'][0].containsKey('unit_price'), isFalse);

    await tester.enterText(lineBoxes().at(3), '118');
    await tester.pump(const Duration(milliseconds: 400));
    await tester.pumpAndSettle();
    expect(asked.last['lines'][0]['unit_price'], '118');

    await tester.tap(find.byKey(const ValueKey('quotation-save-print')));
    await tester.pumpAndSettle();
    expect(result?['rate_includes_tax'], isTrue);
    expect(result?['lines'][0]['unit_price'], '118');
    expect(tester.takeException(), isNull);
  });

  testWidgets('the switch moves the product price out and back',
      (tester) async {
    Json? result;
    await pumpEditor(tester, onResult: (value) => result = value);
    final Finder toggle =
        find.byKey(const ValueKey('quotation-rate-includes-tax'));
    expect(tester.widget<Switch>(toggle).value, isFalse);
    expect(find.text('Rate incl. GST'), findsNothing);
    expect(
        tester.widget<EditableText>(lineBoxes().at(3)).controller.text, '26.00');

    await tester.tap(toggle);
    await tester.pumpAndSettle();
    expect(find.text('Rate incl. GST'), findsOneWidget);
    expect(
        tester.widget<EditableText>(lineBoxes().at(3)).controller.text, isEmpty);

    await tester.tap(toggle);
    await tester.pumpAndSettle();
    expect(find.text('Rate incl. GST'), findsNothing);
    expect(
        tester.widget<EditableText>(lineBoxes().at(3)).controller.text, '26.00');

    await tester.tap(find.byKey(const ValueKey('quotation-save-print')));
    await tester.pumpAndSettle();
    expect(result?['rate_includes_tax'], isFalse);
    expect(result?['lines'][0]['unit_price'], '26.00');
  });

  testWidgets('a quotation typed with GST shows its rate back as typed',
      (tester) async {
    Json? result;
    await pumpEditor(tester,
        existing: saved(rateIncludesTax: true, enteredRate: '30.68'),
        onResult: (value) => result = value);
    expect(find.text('Rate incl. GST'), findsOneWidget);
    expect(
        tester.widget<EditableText>(lineBoxes().at(3)).controller.text,
        '30.68');

    await tester.tap(find.byKey(const ValueKey('quotation-save-print')));
    await tester.pumpAndSettle();
    expect(result?['rate_includes_tax'], isTrue);
    expect(result?['lines'][0]['unit_price'], '30.68');
  });

  // D-SELL-43: a quotation is priced with the customer's coupon.
  testWidgets('a new quotation sends its coupon, trimmed, and prices with it',
      (tester) async {
    Json? result;
    final List<Json> asked =
        await pumpEditor(tester, onResult: (value) => result = value);
    expect(asked.last.containsKey('coupon_code'), isFalse);

    await tester.enterText(
        find.byKey(const ValueKey('quotation-coupon')), ' SAVE10 ');
    await tester.pump(const Duration(milliseconds: 400));
    await tester.pumpAndSettle();
    expect(asked.last['coupon_code'], 'SAVE10');

    await tester.tap(find.byKey(const ValueKey('quotation-save-print')));
    await tester.pumpAndSettle();
    expect(result?['coupon_code'], 'SAVE10');
  });

  testWidgets('an edit opens with the coupon the quotation was priced with',
      (tester) async {
    Json? result;
    await pumpEditor(tester,
        existing: saved(), onResult: (value) => result = value);
    expect(find.widgetWithText(TextFormField, 'SAVE10'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('quotation-save-print')));
    await tester.pumpAndSettle();
    // Sent back as it was read, so saving an edit does not drop the coupon.
    expect(result?['coupon_code'], 'SAVE10');
  });

  testWidgets('clearing the coupon on an edit sends none', (tester) async {
    Json? result;
    await pumpEditor(tester,
        existing: saved(), onResult: (value) => result = value);
    await tester.enterText(find.byKey(const ValueKey('quotation-coupon')), '');
    await tester.tap(find.byKey(const ValueKey('quotation-save-print')));
    await tester.pumpAndSettle();
    expect(result?.containsKey('coupon_code'), isFalse);
  });

  // D-SELL-41: blank free goods take the offer's; a typed 0 refuses them.
  testWidgets('free goods: blank is omitted, a typed zero is sent, and an '
      'edit does not prefill zero', (tester) async {
    Json? result;
    await pumpEditor(tester,
        existing: saved(coupon: '', free: '0'),
        onResult: (value) => result = value);
    // The line was stored with no free goods; the box reads empty.
    expect(
      tester
          .widget<EditableText>(lineBoxes().at(2))
          .controller
          .text,
      isEmpty,
    );
    await tester.tap(find.byKey(const ValueKey('quotation-save-print')));
    await tester.pumpAndSettle();
    expect((result!['lines'] as List).single.containsKey('free_quantity'),
        isFalse);
  });

  testWidgets('a typed zero in the free box is sent as zero', (tester) async {
    Json? result;
    await pumpEditor(tester,
        existing: saved(coupon: ''), onResult: (value) => result = value);
    await tester.enterText(lineBoxes().at(2), '0');
    await tester.tap(find.byKey(const ValueKey('quotation-save-print')));
    await tester.pumpAndSettle();
    expect((result!['lines'] as List).single['free_quantity'], '0');
  });

  // D-PRC-68: the one line whose free box is prefilled. "0 free" was typed to
  // refuse an offer, and a blank box would take the refusal back on re-save.
  testWidgets('a line whose free goods were refused opens at 0 and sends 0 '
      'back', (tester) async {
    Json? result;
    final List<Json> asked = await pumpEditor(tester,
        existing: saved(coupon: '', free: '0', freeRefused: true),
        size: const Size(1366, 768),
        onResult: (value) => result = value);
    expect(
      tester.widget<EditableText>(lineBoxes().at(2)).controller.text,
      '0',
    );
    // The figures on screen are priced with the refusal too.
    expect(asked.last['lines'][0]['free_quantity'], '0');
    expect(find.text('Free: blank takes the offer; 0 refuses it.'),
        findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('quotation-save-print')));
    await tester.pumpAndSettle();
    expect((result!['lines'] as List).single['free_quantity'], '0');
    expect(tester.takeException(), isNull);
  });
}
