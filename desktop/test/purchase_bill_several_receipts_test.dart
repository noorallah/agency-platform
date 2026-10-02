// One supplier bill charges for several goods receipts (D-BUY-18, 2026-09-30;
// SEL-1, 2026-10-03).
//
// The server infers the sources from the lines and only asks that they share
// a vendor and a branch. The screen asks for the supplier first and offers
// their receipts as a tick list; a receipt of another branch cannot be ticked
// beside one already ticked, and says so. Both receipts' lines go in one
// payload numbered 1..n, and every receipt is named in `source_documents`.
//
// The buying editor only creates -- a draft bill is not reopened -- so there
// is no edit case here; the sales twin's edit case is in
// `sales_invoice_several_notes_test.dart`.

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

GoodsReceiptRecord _receipt(
  String id,
  String number, {
  String vendor = 'vendor-1',
  String branch = 'branch-1',
}) =>
    GoodsReceiptRecord.fromJson({
      'id': id,
      'grn_number': number,
      'receipt_date': '2026-08-10',
      'status': 'COMPLETED',
      'vendor_id': vendor,
      'vendor_name': vendor == 'vendor-1' ? 'Cipla Distributors' : 'Medline',
      'branch_id': branch,
      'purchase_order_number': 'PO-$number',
      'grand_total': '590',
      'lines': [
        {
          'id': '$id-l1',
          'line_number': 1,
          'product_id': 'prod-1',
          'description': 'Amoxicillin 500mg',
          'accepted_quantity': '20',
          'unit_price': '25',
          'purchase_uom_id': 'uom-box',
          'warehouse_id': 'wh-1',
          'tax_profile_id': 'tax-1',
          'batch_number': 'B-$id',
        },
      ],
    });

class _Api extends ApiClient {
  _Api()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

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
      {'data': const <Json>[]};

  @override
  Future<PurchaseInvoicePreviewRecord> previewPurchaseInvoice(
    Json data,
  ) async =>
      PurchaseInvoicePreviewRecord.fromJson({
        'invoice': {
          'invoice_number': 'PI-2026-000009',
          'subtotal': '0',
          'tax_total': '0',
          'grand_total': '0',
          'lines': const [],
        },
        'interstate': false,
        'lines': const [],
      });

  @override
  Future<Json> createPurchaseInvoice(Json body) async {
    sent = body;
    return {
      'data': {'id': 'pi-1', 'invoice_number': 'PI-1', 'status': 'DRAFT'}
    };
  }
}

Future<void> _open(WidgetTester tester, _Api api) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: Phase2Scope(
          child: PurchaseInvoiceEditorDialog(
            api: api,
            receipts: [
              _receipt('grn-1', 'GRN-000001'),
              _receipt('grn-2', 'GRN-000002'),
              _receipt('grn-3', 'GRN-000003', vendor: 'vendor-2'),
              _receipt('grn-4', 'GRN-000004', branch: 'branch-2'),
            ],
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
}

Future<void> _chooseSupplier(WidgetTester tester, String name) async {
  await tester
      .tap(find.byKey(const ValueKey('purchase-invoice-receipt-supplier')));
  await tester.pumpAndSettle();
  await tester.tap(find.text(name).last);
  await tester.pumpAndSettle();
}

Future<void> _tick(WidgetTester tester, String id) async {
  await tester.tap(find.byKey(ValueKey<String>('purchase-invoice-tick-$id')));
  await tester.pumpAndSettle();
}

Future<void> _done(WidgetTester tester) async {
  await tester.tap(find.byKey(const ValueKey('purchase-invoice-tick-done')));
  await tester.pumpAndSettle();
  await tester.pump(const Duration(milliseconds: 400));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('the supplier comes first, then a tick list of their receipts',
      (tester) async {
    final _Api api = _Api();
    await _open(tester, api);
    expect(find.byKey(const ValueKey('purchase-invoice-choose-receipts')),
        findsNothing);

    await _chooseSupplier(tester, 'Cipla Distributors');
    expect(tester.takeException(), isNull);
    // Three receipts of this supplier, so the list opened by itself; the
    // other supplier's is not in it.
    expect(find.byKey(const ValueKey('purchase-invoice-tick-grn-1')),
        findsOneWidget);
    expect(
        find.byKey(const ValueKey('purchase-invoice-tick-grn-3')), findsNothing);
    expect(find.text('PO-GRN-000002'), findsOneWidget);

    await _tick(tester, 'grn-1');
    // Another branch's receipt cannot join, and says why.
    final Checkbox other = tester.widget<Checkbox>(
        find.byKey(const ValueKey('purchase-invoice-tick-grn-4')));
    expect(other.onChanged, isNull);
    expect(find.byKey(const ValueKey('purchase-invoice-clash-grn-4')),
        findsOneWidget);
    await _tick(tester, 'grn-2');
    await _done(tester);
    expect(tester.takeException(), isNull);

    // Two rows, each saying which receipt it is from.
    expect(
        find.byKey(const ValueKey('purchase-invoice-line-0')), findsOneWidget);
    expect(
        find.byKey(const ValueKey('purchase-invoice-line-1')), findsOneWidget);
    expect(find.text('receipt GRN-000002'), findsOneWidget);
    expect(find.byKey(const ValueKey('purchase-invoice-receipt-chip-grn-2')),
        findsOneWidget);

    await tester.enterText(
      find.byKey(
        const ValueKey<String>('purchase-invoice-supplier-number-0'),
      ),
      'SUP-77',
    );
    await tester.tap(find.byKey(const ValueKey('purchase-invoice-save')));
    await tester.pumpAndSettle();

    final Json sent = api.sent!;
    final List<dynamic> lines = sent['lines'] as List<dynamic>;
    expect(
      [for (final dynamic l in lines) (l as Json)['source_document_id']],
      ['grn-1', 'grn-2'],
    );
    expect(
      [for (final dynamic l in lines) (l as Json)['line_number']],
      [1, 2],
    );
    expect(
      [
        for (final dynamic s in sent['source_documents'] as List<dynamic>)
          (s as Json)['source_document_id']
      ],
      ['grn-1', 'grn-2'],
    );
  });

  testWidgets('unticking a receipt takes its lines off the bill',
      (tester) async {
    final _Api api = _Api();
    await _open(tester, api);
    await _chooseSupplier(tester, 'Cipla Distributors');
    await _tick(tester, 'grn-1');
    await _tick(tester, 'grn-2');
    await _done(tester);
    expect(
        find.byKey(const ValueKey('purchase-invoice-line-1')), findsOneWidget);

    await tester
        .tap(find.byKey(const ValueKey('purchase-invoice-choose-receipts')));
    await tester.pumpAndSettle();
    await _tick(tester, 'grn-2');
    await _done(tester);
    expect(find.byKey(const ValueKey('purchase-invoice-line-1')), findsNothing);

    await tester.enterText(
      find.byKey(
        const ValueKey<String>('purchase-invoice-supplier-number-0'),
      ),
      'SUP-78',
    );
    await tester.tap(find.byKey(const ValueKey('purchase-invoice-save')));
    await tester.pumpAndSettle();
    final Json sent = api.sent!;
    expect((sent['lines'] as List<dynamic>).length, 1);
    expect((sent['source_documents'] as List<dynamic>).length, 1);
  });

  testWidgets("a supplier's only receipt is ticked without asking",
      (tester) async {
    final _Api api = _Api();
    await _open(tester, api);
    await _chooseSupplier(tester, 'Medline');
    await tester.pump(const Duration(milliseconds: 400));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('purchase-invoice-tick-done')),
        findsNothing);
    expect(find.byKey(const ValueKey('purchase-invoice-receipt-chip-grn-3')),
        findsOneWidget);
    expect(
        find.byKey(const ValueKey('purchase-invoice-line-0')), findsOneWidget);
  });
}
