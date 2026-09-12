import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/design/design_tokens.dart';
import 'package:agency_desktop/models/batch_serial.dart';
import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/goods_receipt.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/models/purchase.dart';
import 'package:agency_desktop/ui/goods_receipts/goods_receipt_editor_dialog.dart';
import 'package:agency_desktop/ui/purchase_returns/purchase_return_editor_dialog.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';

/// The pickers that name a source document print its number and its date.
///
/// Found on the 2026-09-12 manual pass (plan item 7.5): at 320 wide the
/// closed Purchase Order field cut a seeded number short, and the number is
/// the one part a reader chooses by. The widget test cannot render the
/// desktop's font -- the test font is a fixed-width block glyph, so any text
/// measured here is about twice as wide as it is on screen -- so the guard is
/// on the room the field gives the text: the paragraph's own width limit has
/// to hold a seeded number-and-date at the body size, taken at 8 px a
/// character, which is a generous mean for a 14 px proportional face.
const String _poNumber = 'PO-WHOLE01-BR_NORTH-2026-2027-000001';
const String _grnNumber = 'GRN-WHOLE01-WHL_HO-2026-2027-000006';
const double _pixelsPerCharacter = 8;

class _ReceiptApi extends ApiClient {
  _ReceiptApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  @override
  Future<PagedResult<GoodsReceiptRecord>> goodsReceipts({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    Map<String, String> filters = const {},
  }) async =>
      const PagedResult<GoodsReceiptRecord>(items: [], total: 0);
}

class _ReturnApi extends ApiClient {
  _ReturnApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

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

  @override
  Future<PagedResult<BatchRecord>> batches({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    BatchQuery filters = const BatchQuery(),
  }) async =>
      const PagedResult<BatchRecord>(items: [], total: 0);
}

/// The smallest screen the desktop supports, so a wider field is proven to
/// still fit the header's Wrap there and not only on a large test surface.
void _smallestDesktop(WidgetTester tester) {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
}

/// The width the closed field lets [label] have, after choosing it.
Future<double> _roomFor(WidgetTester tester, String label) async {
  await tester.tap(find.byType(DropdownButtonFormField<String>).first);
  await tester.pumpAndSettle();
  await tester.tap(find.text(label).last);
  await tester.pumpAndSettle();
  // A Text's own render object is the selection mouse region; the paragraph
  // is the RichText it builds.
  final RenderParagraph paragraph = tester.renderObject<RenderParagraph>(
    find.descendant(of: find.text(label), matching: find.byType(RichText)),
  );
  return paragraph.constraints.maxWidth;
}

void main() {
  testWidgets('the goods receipt picker shows a seeded order number whole', (
    tester,
  ) async {
    _smallestDesktop(tester);
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: GoodsReceiptEditorDialog(
            api: _ReceiptApi(),
            purchaseOrders: [
              PurchaseOrder.fromJson({
                'id': 'po-1',
                'po_number': _poNumber,
                'purchase_date': '2026-09-12',
                'warehouse_id': 'wh-1',
                'status': 'APPROVED',
                'lines': <Json>[],
              }),
            ],
            warehouses: [
              WarehouseRecord.fromJson({
                'id': 'wh-1',
                'code': 'WH_NORTH',
                'name': 'North',
              }),
            ],
            products: [
              Product.fromJson({
                'id': 'prod-1',
                'code': 'DETER1K',
                'name': 'Detergent',
              }),
            ],
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    const String label = '$_poNumber • 2026-09-12';
    final double room = await _roomFor(tester, label);
    expect(
      room,
      greaterThanOrEqualTo(label.length * _pixelsPerCharacter),
      reason: 'the closed field must hold the number and date at body size',
    );
    expect(
      tester.getSize(find.byType(DropdownButtonFormField<String>).first).width,
      AppDimensions.documentPickerWidth,
    );
  });

  testWidgets('the purchase return picker shows a seeded receipt number whole',
      (tester) async {
    _smallestDesktop(tester);
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: PurchaseReturnEditorDialog(
            api: _ReturnApi(),
            receipts: [
              GoodsReceiptRecord.fromJson({
                'id': 'grn-1',
                'grn_number': _grnNumber,
                'receipt_date': '2026-09-12',
                'status': 'COMPLETED',
                'lines': <Json>[],
              }),
            ],
            products: [
              Product.fromJson({
                'id': 'prod-1',
                'code': 'DETER1K',
                'name': 'Detergent',
              }),
            ],
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    const String label = '$_grnNumber • 2026-09-12';
    final double room = await _roomFor(tester, label);
    expect(
      room,
      greaterThanOrEqualTo(label.length * _pixelsPerCharacter),
      reason: 'the closed field must hold the number and date at body size',
    );
  });
}
