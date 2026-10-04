// PG-6 (backlog 86 #9): TCS a supplier charged, typed on the phase 2 bill.
//
// The rate and amount boxes start blank and send nothing while blank -- the
// server reads absent as no TCS. A typed rate or amount is sent as typed
// under the names the server's PurchaseInvoiceCreate declares, and the totals
// show the TCS and what is owed with it.

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/document_preview.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/goods_receipt.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/ui/purchase_invoices/purchase_invoice_editor_dialog.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// A completed receipt of twenty units at 25 each.
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
        },
      ],
    });

class _TcsApi extends ApiClient {
  _TcsApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  Json? sent;
  final List<Json> previews = <Json>[];

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
      {'data': <Json>[]};

  /// Prices the bill at 500 with no tax, and works the TCS out as the server
  /// does: a typed amount wins, a rate alone is taken on the grand total.
  @override
  Future<PurchaseInvoicePreviewRecord> previewPurchaseInvoice(
    Json data,
  ) async {
    previews.add(data);
    const double total = 500;
    final double tcs = data['tcs_amount'] != null
        ? double.parse('${data['tcs_amount']}')
        : data['tcs_rate_percent'] != null
            ? total * double.parse('${data['tcs_rate_percent']}') / 100
            : 0;
    return PurchaseInvoicePreviewRecord.fromJson({
      'invoice': {
        'invoice_number': 'PI-2026-000009',
        'subtotal': '500.00',
        'tax_total': '0.00',
        'grand_total': '500.00',
        'tcs_amount': tcs.toStringAsFixed(2),
        'amount_owed': (total + tcs).toStringAsFixed(2),
        'lines': [
          {
            'line_number': 1,
            'source_document_line_id': 'grn-line-1',
            'gross_amount': '500.00',
            'discount_amount': '0',
            'tax_amount': '0.00',
          },
        ],
      },
      'interstate': false,
      'lines': <Json>[],
    });
  }

  @override
  Future<Json> createPurchaseInvoice(Json body) async {
    sent = body;
    return {
      'data': {'id': 'pi-1', 'invoice_number': 'PI-1', 'status': 'DRAFT'}
    };
  }
}

Future<void> _pump(WidgetTester tester, _TcsApi api) async {
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
  await tester
      .tap(find.byKey(const ValueKey('purchase-invoice-receipt-supplier')));
  await tester.pumpAndSettle();
  await tester.tap(find.text('Medico Distributors').last);
  await tester.pumpAndSettle();
  await tester.pump(const Duration(milliseconds: 400));
  await tester.pumpAndSettle();
}

Future<void> _type(WidgetTester tester, String key, String text) async {
  await tester.enterText(find.byKey(ValueKey<String>(key)), text);
  await tester.pump(const Duration(milliseconds: 400));
  await tester.pumpAndSettle();
}

Future<void> _save(WidgetTester tester) async {
  await tester.tap(find.byKey(const ValueKey('purchase-invoice-save')));
  await tester.pumpAndSettle();
}

/// A figure in the totals bar, which writes label and amount as one rich text.
Finder _figure(String text) => find.textContaining(text, findRichText: true);

void main() {
  testWidgets('blank TCS boxes send nothing', (tester) async {
    final _TcsApi api = _TcsApi();
    await _pump(tester, api);
    await _type(tester, 'purchase-invoice-supplier-number-0', 'SUP-5');
    await _save(tester);

    expect(api.sent, isNotNull);
    expect(api.sent!.containsKey('tcs_rate_percent'), isFalse);
    expect(api.sent!.containsKey('tcs_amount'), isFalse);
    expect(_figure('TCS charged  '), findsNothing);
  });

  testWidgets('a rate alone is sent and the total owed includes the TCS',
      (tester) async {
    final _TcsApi api = _TcsApi();
    await _pump(tester, api);
    await _type(tester, 'purchase-invoice-supplier-number-0', 'SUP-5');
    await _type(tester, 'purchase-invoice-tcs-rate', '0.1');

    expect(api.previews.last['tcs_rate_percent'], '0.1');
    expect(api.previews.last.containsKey('tcs_amount'), isFalse);
    expect(_figure('TCS charged  '), findsOneWidget);
    expect(_figure('Net payable  '), findsOneWidget);
    expect(_figure('500.50'), findsOneWidget);

    await _save(tester);
    expect(api.sent!['tcs_rate_percent'], '0.1');
    expect(api.sent!.containsKey('tcs_amount'), isFalse);
  });

  testWidgets('a typed amount is sent beside the rate, trimmed',
      (tester) async {
    final _TcsApi api = _TcsApi();
    await _pump(tester, api);
    await _type(tester, 'purchase-invoice-supplier-number-0', 'SUP-5');
    await _type(tester, 'purchase-invoice-tcs-rate', '0.1');
    await _type(tester, 'purchase-invoice-tcs-amount', ' 2.50 ');
    await _save(tester);

    expect(api.sent!['tcs_rate_percent'], '0.1');
    expect(api.sent!['tcs_amount'], '2.50');
  });

  testWidgets('a TCS figure that is not a number is refused before it is sent',
      (tester) async {
    final _TcsApi api = _TcsApi();
    await _pump(tester, api);
    await _type(tester, 'purchase-invoice-supplier-number-0', 'SUP-5');
    await _type(tester, 'purchase-invoice-tcs-amount', 'abc');
    await _save(tester);

    expect(api.sent, isNull);
    expect(find.textContaining('TCS amount must be a number'), findsWidgets);
  });
}
