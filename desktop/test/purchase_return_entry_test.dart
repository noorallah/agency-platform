import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/batch_serial.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/goods_receipt.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/ui/purchase_returns/purchase_return_editor_dialog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// A completed receipt of twenty units, taken in on batch MARCH-01.
GoodsReceiptRecord _receipt() => GoodsReceiptRecord.fromJson({
      'id': 'grn-1',
      'grn_number': 'GRN-2026-000001',
      'receipt_date': '2026-08-10',
      'status': 'COMPLETED',
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
          'batch_number': 'MARCH-01',
        },
      ],
    });

class _ReturnApi extends ApiClient {
  _ReturnApi({this.registered = const [], this.earlierReturns = const []})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  /// Batch numbers the register holds for prod-1.
  final List<String> registered;

  /// Rows as `/purchase-returns` would return them.
  final List<Json> earlierReturns;
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
      {'data': earlierReturns};

  @override
  Future<PagedResult<BatchRecord>> batches({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    BatchQuery filters = const BatchQuery(),
  }) async =>
      PagedResult<BatchRecord>(
        items: [
          for (final String number in registered)
            BatchRecord.fromJson({
              'id': 'batch-$number',
              'product_id': 'prod-1',
              'batch_number': number,
              'expiry_date': '2027-03-31',
              'quantity': '20',
              'available_quantity': '20',
            }),
        ],
        total: registered.length,
      );

  @override
  Future<Json> create(String resource, Json body) async {
    sent = body;
    return {
      'data': {'id': 'pr-1', 'return_number': 'PR-1', 'status': 'DRAFT'}
    };
  }
}

Future<void> _openEditor(WidgetTester tester, _ReturnApi api) async {
  tester.view.physicalSize = const Size(1600, 1200);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: PurchaseReturnEditorDialog(
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

void main() {
  testWidgets('the batch comes from the register, not a text box', (
    tester,
  ) async {
    // The server refuses a batch number that was never received, because a
    // number nobody took in names stock that never arrived. Offering the
    // register means it cannot be got wrong; a text box means finding out on
    // save.
    final _ReturnApi api = _ReturnApi(registered: ['MARCH-01', 'JUNE-02']);
    await _openEditor(tester, api);

    expect(
      find.byType(DropdownButtonFormField<String>),
      findsNWidgets(2),
      reason: 'the receipt picker and the batch picker',
    );
    // The register's holdings are shown, so whoever picks knows what is there.
    await tester.tap(find.byType(DropdownButtonFormField<String>).last);
    await tester.pumpAndSettle();
    expect(find.textContaining('JUNE-02 · holds 20'), findsWidgets);
    await tester.tap(find.textContaining('JUNE-02').last);
    await tester.pumpAndSettle();

    await tester.tap(find.text('Save Return'));
    await tester.pumpAndSettle();

    final List<dynamic> lines = api.sent!['lines'] as List<dynamic>;
    expect((lines.first as Json)['batch_number'], 'JUNE-02');
  });

  testWidgets('the batch the goods arrived in is the default', (tester) async {
    final _ReturnApi api = _ReturnApi(registered: ['MARCH-01', 'JUNE-02']);
    await _openEditor(tester, api);

    expect(find.textContaining('Receipt said MARCH-01'), findsOneWidget);

    await tester.tap(find.text('Save Return'));
    await tester.pumpAndSettle();

    final List<dynamic> lines = api.sent!['lines'] as List<dynamic>;
    final Json line = lines.first as Json;
    expect(line['batch_number'], 'MARCH-01');
    expect(line['source_document_type'], 'GOODS_RECEIPT');
    expect(line['source_document_line_id'], 'grn-line-1');
    expect(line['current_return_quantity'], '20');
  });

  testWidgets('a product with no registered batches goes back untracked', (
    tester,
  ) async {
    // Nothing registered means nothing to choose. The line still returns --
    // against the product, which is what the server does with a blank number.
    final _ReturnApi api = _ReturnApi();
    await _openEditor(tester, api);

    expect(find.text('No batches registered for this product'), findsOneWidget);

    await tester.tap(find.text('Save Return'));
    await tester.pumpAndSettle();

    final List<dynamic> lines = api.sent!['lines'] as List<dynamic>;
    expect((lines.first as Json).containsKey('batch_number'), isFalse);
  });

  testWidgets('a part-returned receipt defaults to what is left', (
    tester,
  ) async {
    final _ReturnApi api = _ReturnApi(
      registered: ['MARCH-01'],
      earlierReturns: [
        {
          'id': 'pr-old',
          'status': 'COMPLETED',
          'lines': [
            {
              'source_document_line_id': 'grn-line-1',
              'current_return_quantity': '5',
            },
          ],
        },
      ],
    );
    await _openEditor(tester, api);

    expect(find.text('Received 20 · already returned 5'), findsOneWidget);
    final TextFormField returning = tester.widget<TextFormField>(
      find.ancestor(
        of: find.text('Returning *'),
        matching: find.byType(TextFormField),
      ),
    );
    expect(returning.initialValue, '15');
  });

  testWidgets('a cancelled return does not count against what is left', (
    tester,
  ) async {
    // Cancelling a return puts the goods back on the shelf, so it cannot go on
    // reserving part of the receipt against a future one.
    final _ReturnApi api = _ReturnApi(
      registered: ['MARCH-01'],
      earlierReturns: [
        {
          'id': 'pr-old',
          'status': 'CANCELLED',
          'lines': [
            {
              'source_document_line_id': 'grn-line-1',
              'current_return_quantity': '5',
            },
          ],
        },
      ],
    );
    await _openEditor(tester, api);

    expect(find.text('Received 20 · already returned 0'), findsOneWidget);
  });

  testWidgets('rejected cannot exceed what is going back', (tester) async {
    final _ReturnApi api = _ReturnApi(registered: ['MARCH-01']);
    await _openEditor(tester, api);

    await tester.enterText(
      find.ancestor(
        of: find.text('Rejected'),
        matching: find.byType(TextFormField),
      ),
      '25',
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Save Return'));
    await tester.pumpAndSettle();

    expect(find.textContaining('rejected cannot exceed'), findsOneWidget);
    expect(api.sent, isNull);
  });
}
