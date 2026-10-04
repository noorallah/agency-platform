// A supplier bill can be raised from the desktop (BL-31.9, 2026-09-18).
//
// Until this dialog existed the Purchase Invoices screen listed, approved and
// closed bills the seeder had raised and never called
// `POST /api/v1/purchase-invoices`. The orphan-route guard could not see it:
// the generic `documentPage` helper names the literal `'purchase-invoices'`,
// so the create route read as called. These pin the body the dialog sends
// and what it shows when the server refuses it.

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/document_preview.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/goods_receipt.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/models/purchase.dart';
import 'package:agency_desktop/models/vendor.dart';
import 'package:agency_desktop/ui/purchase_invoices/purchase_invoice_editor_dialog.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// A completed receipt of twenty units at 25 each, on batch MARCH-01.
GoodsReceiptRecord _receipt() => GoodsReceiptRecord.fromJson({
      'id': 'grn-1',
      'grn_number': 'GRN-2026-000001',
      'receipt_date': '2026-08-10',
      'status': 'COMPLETED',
      'vendor_id': 'vendor-1',
      'vendor_name': 'Medico Distributors',
      'branch_id': 'branch-1',
      'lines': [
        {
          'id': 'grn-line-1',
          'line_number': 1,
          'product_id': 'prod-1',
          'description': 'Amoxicillin 500mg',
          'accepted_quantity': '20',
          'unit_price': '25',
          'purchase_uom_id': 'uom-box',
          'warehouse_id': 'wh-1',
          'tax_profile_id': 'tax-1',
          'batch_number': 'MARCH-01',
        },
      ],
    });

class _InvoiceApi extends ApiClient {
  _InvoiceApi({this.earlierInvoices = const [], this.refusal})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  /// Rows as `/purchase-invoices` would return them.
  final List<Json> earlierInvoices;

  /// What the server answers the create with, when it refuses.
  final ApiException? refusal;
  Json? sent;

  @override
  Future<Json> documentPage(
    String resource, {
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    Map<String, String> additionalQuery = const {},
  }) async =>
      {'data': earlierInvoices};

  /// Every draft phase 2 asked to be priced.
  final List<Json> previews = <Json>[];

  /// Prices each draft at 18% within the state, the way the server would.
  @override
  Future<PurchaseInvoicePreviewRecord> previewPurchaseInvoice(
    Json data,
  ) async {
    previews.add(data);
    final Json line = (data['lines'] as List<dynamic>).first as Json;
    final double price = double.parse('${line['unit_price'] ?? '25'}');
    final double gross =
        double.parse('${line['current_invoice_quantity']}') * price;
    final double tax = gross * .18;
    return PurchaseInvoicePreviewRecord.fromJson({
      'invoice': {
        'invoice_number': 'PI-2026-000009',
        'subtotal': gross.toStringAsFixed(2),
        'tax_total': tax.toStringAsFixed(2),
        'grand_total': (gross + tax).toStringAsFixed(2),
        'irn_warning': data['supplier_invoice_number'] == 'SUP-2'
            ? 'Supplier One e-invoices, and this bill has no IRN.'
            : null,
        'duplicate_warning': data['supplier_invoice_number'] == 'SUP-1'
            ? 'A purchase invoice with this supplier invoice number already '
                'exists.'
            : null,
        'lines': [
          {
            'line_number': 1,
            'source_document_line_id': 'grn-line-1',
            'gross_amount': gross.toStringAsFixed(2),
            'discount_amount': '0',
            'tax_amount': tax.toStringAsFixed(2),
          },
        ],
      },
      'interstate': false,
      'lines': [
        {
          'line_number': 1,
          'product_id': 'prod-1',
          'last_price': '24.00',
          'last_invoice_number': 'PI-7',
          'last_invoice_date': '2026-07-20',
          'available_quantity': '20',
        },
      ],
    });
  }

  @override
  Future<Json> createPurchaseInvoice(Json body) async {
    sent = body;
    final ApiException? refused = refusal;
    if (refused != null) throw refused;
    return {
      'data': {'id': 'pi-1', 'invoice_number': 'PI-1', 'status': 'DRAFT'}
    };
  }
}

Finder _field(String label) => find.ancestor(
      of: find.text(label),
      matching: find.byType(TextFormField),
    );

Future<void> _openEditor(WidgetTester tester, _InvoiceApi api) async {
  tester.view.physicalSize = const Size(1600, 1200);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: PurchaseInvoiceEditorDialog(
          api: api,
          receipts: [_receipt()],
          products: [
            Product.fromJson({
              'id': 'prod-1',
              'code': 'SKU-1',
              'name': 'Amoxicillin 500mg',
            }),
          ],
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
  await tester.tap(find.byType(DropdownButtonFormField<String>).first);
  await tester.pumpAndSettle();
  await tester.tap(find.text('GRN-2026-000001 • 2026-08-10').last);
  await tester.pumpAndSettle();
}

Future<void> _fillHeader(WidgetTester tester) async {
  await tester.enterText(_field('Supplier Invoice Number *'), 'SUP-778');
  await tester.enterText(_field('Supplier Invoice Date *'), '2026-08-12');
  await tester.enterText(_field('Invoice Date *'), '2026-08-13');
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('the bill is posted against the receipt line, price left blank', (
    tester,
  ) async {
    final _InvoiceApi api = _InvoiceApi();
    await _openEditor(tester, api);
    await _fillHeader(tester);

    await tester.tap(find.text('Save Invoice'));
    await tester.pumpAndSettle();

    final Json sent = api.sent!;
    expect(sent['invoice_date'], '2026-08-13');
    expect(sent['supplier_invoice_number'], 'SUP-778');
    expect(sent['supplier_invoice_date'], '2026-08-12');
    expect(sent['source_documents'], [
      {'source_document_type': 'GOODS_RECEIPT', 'source_document_id': 'grn-1'},
    ]);
    // The server takes the vendor and branch from the receipt; a copy sent
    // from here is one more thing that can disagree with it.
    expect(sent.containsKey('vendor_id'), isFalse);
    expect(sent.containsKey('branch_id'), isFalse);

    final List<dynamic> lines = sent['lines'] as List<dynamic>;
    expect(lines, hasLength(1));
    final Json line = lines.first as Json;
    expect(line['source_document_type'], 'GOODS_RECEIPT');
    expect(line['source_document_id'], 'grn-1');
    expect(line['source_document_line_id'], 'grn-line-1');
    expect(line['line_number'], 1);
    expect(line['current_invoice_quantity'], '20');
    expect(line['purchase_uom_id'], 'uom-box');
    expect(line['invoice_uom_id'], 'uom-box');
    expect(line['warehouse_id'], 'wh-1');
    expect(line['tax_profile_id'], 'tax-1');
    expect(line['batch_number'], 'MARCH-01');
    // A blank price is absent, never '0': absent takes the receipt line's
    // price, zero says the supplier charged nothing.
    expect(line.containsKey('unit_price'), isFalse);
    // Silence on the discount takes the receipt's rate; a literal zero would
    // refuse it. And the server derives the description and forbids the key.
    expect(line.containsKey('discount_percent'), isFalse);
    expect(line.containsKey('discount_amount'), isFalse);
    expect(line.containsKey('description'), isFalse);
  });

  testWidgets('a typed price is sent as typed', (tester) async {
    final _InvoiceApi api = _InvoiceApi();
    await _openEditor(tester, api);
    await _fillHeader(tester);
    expect(find.text('Blank takes 25'), findsOneWidget);

    await tester.enterText(_field('Unit Price'), '24.50');
    await tester.pumpAndSettle();
    await tester.tap(find.text('Save Invoice'));
    await tester.pumpAndSettle();

    final List<dynamic> lines = api.sent!['lines'] as List<dynamic>;
    expect((lines.first as Json)['unit_price'], '24.50');
  });

  testWidgets('a part-billed receipt defaults to what is left', (tester) async {
    final _InvoiceApi api = _InvoiceApi(
      earlierInvoices: [
        {
          'id': 'pi-old',
          'status': 'APPROVED',
          'lines': [
            {
              'source_document_line_id': 'grn-line-1',
              'current_invoice_quantity': '5',
            },
          ],
        },
      ],
    );
    await _openEditor(tester, api);

    expect(find.text('Received 20 · already billed 5'), findsOneWidget);
    expect(tester.widget<TextFormField>(_field('Billing *')).initialValue, '15');
  });

  testWidgets('a cancelled bill does not count against what is left', (
    tester,
  ) async {
    // Cancelling a bill withdraws its charge, so it cannot go on reserving
    // part of the receipt against the bill that replaces it.
    final _InvoiceApi api = _InvoiceApi(
      earlierInvoices: [
        {
          'id': 'pi-old',
          'status': 'CANCELLED',
          'lines': [
            {
              'source_document_line_id': 'grn-line-1',
              'current_invoice_quantity': '5',
            },
          ],
        },
      ],
    );
    await _openEditor(tester, api);

    expect(find.text('Received 20 · already billed 0'), findsOneWidget);
  });

  testWidgets('billing past what is left is refused before it is sent', (
    tester,
  ) async {
    final _InvoiceApi api = _InvoiceApi();
    await _openEditor(tester, api);
    await _fillHeader(tester);

    await tester.enterText(_field('Billing *'), '25');
    await tester.pumpAndSettle();
    await tester.tap(find.text('Save Invoice'));
    await tester.pumpAndSettle();

    expect(find.textContaining('exceeds what the receipt'), findsOneWidget);
    expect(api.sent, isNull);
  });

  testWidgets("the supplier's invoice number is required", (tester) async {
    final _InvoiceApi api = _InvoiceApi();
    await _openEditor(tester, api);

    await tester.tap(find.text('Save Invoice'));
    await tester.pumpAndSettle();

    expect(find.textContaining("supplier's invoice number"), findsOneWidget);
    expect(api.sent, isNull);
  });

  testWidgets("the server's refusal is shown and the dialog stays open", (
    tester,
  ) async {
    final _InvoiceApi api = _InvoiceApi(
      refusal: const ApiException(
        'Supplier invoice number already exists for this vendor.',
        statusCode: 422,
      ),
    );
    await _openEditor(tester, api);
    await _fillHeader(tester);

    await tester.tap(find.text('Save Invoice'));
    await tester.pumpAndSettle();

    expect(api.sent, isNotNull);
    expect(
      find.textContaining('Supplier invoice number already exists'),
      findsOneWidget,
    );
    // Still open, with what was typed, so the number can be corrected rather
    // than the whole bill typed again.
    expect(find.text('New Purchase Invoice'), findsOneWidget);
    expect(find.text('Save Invoice'), findsOneWidget);
  });

  testWidgets('phase 2 bills on one screen, priced to check against the paper',
      (tester) async {
    tester.view.physicalSize = const Size(1600, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final _InvoiceApi api = _InvoiceApi();
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Phase2Scope(
            child: PurchaseInvoiceEditorDialog(
              api: api,
              receipts: [_receipt()],
              products: [
                Product.fromJson({
                  'id': 'prod-1',
                  'code': 'SKU-1',
                  'name': 'Amoxicillin 500mg',
                }),
              ],
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('No goods receipt chosen'), findsOneWidget);

    await tester.tap(
        find.byKey(const ValueKey('purchase-invoice-receipt-supplier')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Medico Distributors').last);
    await tester.pumpAndSettle();
    await tester.pump(const Duration(milliseconds: 400));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);

    // Twenty at the receipt's 25: 500 taxable, 90 tax, 590; priced before
    // the supplier's number is typed.
    expect(api.previews, isNotEmpty);
    expect(api.previews.last['supplier_invoice_number'], '-');
    expect(find.text('PI-2026-000009 (new)'), findsOneWidget);
    expect(find.text('590.00'), findsWidgets);
    expect(find.text('Last bill from them'), findsOneWidget);

    // The supplier charged 24.
    await tester.enterText(
      find.byKey(const ValueKey<String>('purchase-invoice-rate-grn-1-0')),
      '24',
    );
    await tester.pump(const Duration(milliseconds: 400));
    await tester.pumpAndSettle();
    expect(api.previews.last['lines'][0]['unit_price'], '24');
    expect(find.text('566.40'), findsWidgets);

    // A number already on file is said while typing.
    await tester.enterText(
      find.byKey(
        const ValueKey<String>('purchase-invoice-supplier-number-0'),
      ),
      'SUP-1',
    );
    await tester.pump(const Duration(milliseconds: 400));
    await tester.pumpAndSettle();
    expect(find.textContaining('entered twice'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('purchase-invoice-save')));
    await tester.pumpAndSettle();
    expect(api.sent?['supplier_invoice_number'], 'SUP-1');
    expect(api.sent?['lines'][0]['unit_price'], '24');
  });

  group("the supplier's IRN (backlog 78 row 5)", () {
    const String irn =
        '0123456789abcdef0123456789abcdef0123456789abcdef0123456789ABCDEF';

    Future<void> pumpPhase2(WidgetTester tester, _InvoiceApi api) async {
      tester.view.physicalSize = const Size(1600, 900);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: Phase2Scope(
              child: PurchaseInvoiceEditorDialog(
                api: api,
                receipts: [_receipt()],
                products: [
                  Product.fromJson({
                    'id': 'prod-1',
                    'code': 'SKU-1',
                    'name': 'Amoxicillin 500mg',
                  }),
                ],
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(
        find.byKey(const ValueKey('purchase-invoice-receipt-supplier')));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Medico Distributors').last);
      await tester.pumpAndSettle();
      await tester.pump(const Duration(milliseconds: 400));
      await tester.pumpAndSettle();
    }

    Future<void> type(WidgetTester tester, String key, String text) async {
      await tester.enterText(find.byKey(ValueKey<String>(key)), text);
      await tester.pump(const Duration(milliseconds: 400));
      await tester.pumpAndSettle();
    }

    testWidgets('a blank IRN is sent as null', (tester) async {
      final _InvoiceApi api = _InvoiceApi();
      await pumpPhase2(tester, api);
      await type(tester, 'purchase-invoice-supplier-number-0', 'SUP-5');
      await tester.tap(find.byKey(const ValueKey('purchase-invoice-save')));
      await tester.pumpAndSettle();
      expect(api.sent!.containsKey('supplier_irn'), isTrue);
      expect(api.sent!['supplier_irn'], isNull);
    });

    testWidgets('a typed IRN is sent as typed, trimmed', (tester) async {
      final _InvoiceApi api = _InvoiceApi();
      await pumpPhase2(tester, api);
      await type(tester, 'purchase-invoice-supplier-number-0', 'SUP-5');
      await type(tester, 'purchase-invoice-supplier-irn', '  $irn ');
      expect(api.previews.last['supplier_irn'], irn);
      await tester.tap(find.byKey(const ValueKey('purchase-invoice-save')));
      await tester.pumpAndSettle();
      expect(api.sent!['supplier_irn'], irn);
    });

    testWidgets('half an IRN is refused before it is sent', (tester) async {
      final _InvoiceApi api = _InvoiceApi();
      await pumpPhase2(tester, api);
      await type(tester, 'purchase-invoice-supplier-number-0', 'SUP-5');
      await type(tester, 'purchase-invoice-supplier-irn', 'abc123');
      await tester.tap(find.byKey(const ValueKey('purchase-invoice-save')));
      await tester.pumpAndSettle();
      expect(find.textContaining('64 characters'), findsWidgets);
      expect(api.sent, isNull);
    });

    testWidgets("the server's IRN warning is shown", (tester) async {
      final _InvoiceApi api = _InvoiceApi();
      await pumpPhase2(tester, api);
      await type(tester, 'purchase-invoice-supplier-number-0', 'SUP-2');
      expect(find.textContaining('has no IRN'), findsOneWidget);
    });
  });

  // Backlog §38: a firm that types no receipts bills an order, and one that
  // types neither bills products; the server raises what is missing.
  group('buying stages switched off', () {
    const PurchaseWorkflowSettings direct = PurchaseWorkflowSettings(
      purchaseOrderStage: false,
      goodsReceiptStage: false,
      isConfigured: true,
    );
    const PurchaseWorkflowSettings ordersOnly = PurchaseWorkflowSettings(
      purchaseOrderStage: true,
      goodsReceiptStage: false,
      isConfigured: true,
    );
    final Product tracked = Product.fromJson({
      'id': 'prod-1',
      'code': 'SKU-1',
      'name': 'Amoxicillin 500mg',
      'purchase_price': '25',
      'track_batch': true,
      'track_expiry': true,
    });
    final Vendor vendor = Vendor.fromJson({
      'id': 'vendor-1',
      'code': 'V-001',
      'name': 'Medico Distributors',
      'display_name': 'Medico Distributors',
    });

    Future<void> pumpPhase2(
      WidgetTester tester,
      _InvoiceApi api, {
      required PurchaseWorkflowSettings stages,
      List<PurchaseOrder> orders = const [],
      List<GoodsReceiptRecord> receipts = const [],
    }) async {
      tester.view.physicalSize = const Size(1600, 900);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: Phase2Scope(
              child: PurchaseInvoiceEditorDialog(
                api: api,
                receipts: receipts,
                products: [tracked],
                stages: stages,
                orders: orders,
                vendors: [vendor],
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
    }

    Future<void> choose(WidgetTester tester, String key, String text) async {
      await tester.tap(find.byKey(ValueKey<String>(key)));
      await tester.pumpAndSettle();
      await tester.tap(find.textContaining(text).last);
      await tester.pumpAndSettle();
    }

    Future<void> typeSupplierNumber(WidgetTester tester) async {
      await tester.enterText(
        find.byKey(
          const ValueKey<String>('purchase-invoice-supplier-number-0'),
        ),
        'SUP-900',
      );
      await tester.pumpAndSettle();
    }

    Future<void> typeDirectLine(WidgetTester tester) async {
      await choose(tester, 'purchase-invoice-vendor', 'Medico Distributors');
      await choose(tester, 'purchase-invoice-direct-product-0', 'SKU-1');
      await tester.enterText(
        find.byKey(
          const ValueKey<String>('purchase-invoice-direct-quantity-direct-0'),
        ),
        '10',
      );
      await tester.enterText(
        find.byKey(
          const ValueKey<String>('purchase-invoice-direct-free-direct-0'),
        ),
        '1',
      );
      await typeSupplierNumber(tester);
    }

    testWidgets('a tracked product is refused without its batch and expiry', (
      tester,
    ) async {
      final _InvoiceApi api = _InvoiceApi();
      await pumpPhase2(tester, api, stages: direct);
      expect(
        find.byKey(const ValueKey('purchase-invoice-receipt')),
        findsNothing,
      );
      await typeDirectLine(tester);

      await tester.tap(find.byKey(const ValueKey('purchase-invoice-save')));
      await tester.pumpAndSettle();
      expect(find.textContaining('tracked by batch'), findsOneWidget);
      expect(api.sent, isNull);

      await tester.enterText(
        find.byKey(
          const ValueKey<String>('purchase-invoice-batch-direct-0-prod-1'),
        ),
        'B-77',
      );
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('purchase-invoice-save')));
      await tester.pumpAndSettle();
      expect(find.textContaining('tracked by expiry'), findsOneWidget);
      expect(api.sent, isNull);
      expect(tester.takeException(), isNull);
    });

    testWidgets('a bill of products names the supplier and each product', (
      tester,
    ) async {
      final _InvoiceApi api = _InvoiceApi();
      await pumpPhase2(tester, api, stages: direct);
      await typeDirectLine(tester);
      await tester.enterText(
        find.byKey(
          const ValueKey<String>('purchase-invoice-batch-direct-0-prod-1'),
        ),
        'B-77',
      );
      await tester.pumpAndSettle();
      // The expiry box is a date picker: take the day it opens on.
      await tester.tap(
        find.byKey(
          const ValueKey<String>('purchase-invoice-expiry-direct-0-prod-1'),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('OK'));
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const ValueKey('purchase-invoice-save')));
      await tester.pumpAndSettle();

      final Json sent = api.sent!;
      expect(sent['vendor_id'], 'vendor-1');
      expect(sent.containsKey('source_documents'), isFalse);
      final Json line = (sent['lines'] as List<dynamic>).single as Json;
      expect(line['product_id'], 'prod-1');
      expect(line['line_number'], 1);
      expect(line['current_invoice_quantity'], '10');
      expect(line['free_quantity'], '1');
      expect(line['batch_number'], 'B-77');
      expect(
        '${line['expiry_date']}',
        matches(RegExp(r'^\d{4}-\d{2}-\d{2}$')),
      );
      expect(line.containsKey('source_document_line_id'), isFalse);
      // Blank is absent, never '0': absent takes the product's price.
      expect(line.containsKey('unit_price'), isFalse);
      expect(line.containsKey('discount_percent'), isFalse);
    });

    testWidgets('an order is billed at what is still to arrive', (
      tester,
    ) async {
      final PurchaseOrder order = PurchaseOrder.fromJson({
        'id': 'po-1',
        'po_number': 'PO-2026-000004',
        'vendor_id': 'vendor-1',
        'purchase_date': '2026-08-01',
        'status': 'PARTIALLY_RECEIVED',
        'lines': [
          {
            'id': 'po-line-1',
            'line_number': 1,
            'product_id': 'prod-1',
            'ordered_quantity': '30',
            'unit_price': '25',
            'purchase_uom_id': 'uom-box',
            'warehouse_id': 'wh-1',
          },
        ],
      });
      // Twenty of the thirty already came in on a receipt.
      final GoodsReceiptRecord earlier = GoodsReceiptRecord.fromJson({
        'id': 'grn-9',
        'grn_number': 'GRN-9',
        'purchase_order_id': 'po-1',
        'status': 'COMPLETED',
        'lines': [
          {
            'id': 'grn-9-1',
            'purchase_order_line_id': 'po-line-1',
            'product_id': 'prod-1',
            'accepted_quantity': '20',
          },
        ],
      });
      final _InvoiceApi api = _InvoiceApi();
      await pumpPhase2(
        tester,
        api,
        stages: ordersOnly,
        orders: [order],
        receipts: [earlier],
      );
      expect(find.text('No purchase order chosen'), findsOneWidget);

      await choose(tester, 'purchase-invoice-order', 'PO-2026-000004');
      await tester.enterText(
        find.byKey(const ValueKey<String>('purchase-invoice-batch-po-1-0')),
        'B-12',
      );
      await typeSupplierNumber(tester);
      await tester.tap(find.byKey(const ValueKey('purchase-invoice-save')));
      await tester.pumpAndSettle();

      final Json sent = api.sent!;
      expect(sent.containsKey('vendor_id'), isFalse);
      expect(sent.containsKey('source_documents'), isFalse);
      final Json line = (sent['lines'] as List<dynamic>).single as Json;
      expect(line['source_document_type'], 'PURCHASE_ORDER');
      expect(line['source_document_id'], 'po-1');
      expect(line['source_document_line_id'], 'po-line-1');
      expect(line['current_invoice_quantity'], '10');
      expect(line['batch_number'], 'B-12');
      expect(tester.takeException(), isNull);
    });
  });

  // D-BUY-26: goods sent back off the receipt before any bill reached them
  // are not the supplier's to bill, so the line starts at what is left.
  test('a bill line offers what was kept, not what was received', () {
    final GoodsReceiptLine line = GoodsReceiptLine.fromJson({
      'id': 'grn-line-1',
      'accepted_quantity': '6',
      'returned_unbilled_quantity': '2',
    });
    expect(line.returnedUnbilledQuantity, '2');
    final PurchaseInvoiceDraftLine draft = PurchaseInvoiceDraftLine(
      sourceDocumentId: 'grn-1',
      sourceDocumentLineId: line.id,
      lineNumber: 1,
      productId: 'product-1',
      description: '',
      receivedQuantity: line.acceptedQuantity,
      alreadyInvoiced: '0',
      returnedBeforeBilling: line.returnedUnbilledQuantity,
      receiptUnitPrice: '100',
      purchaseUomId: '',
      taxProfileId: '',
      warehouseId: '',
      batchNumber: '',
      invoiceQuantity: '0',
    );
    expect(draft.outstanding, 4);
  });
}
