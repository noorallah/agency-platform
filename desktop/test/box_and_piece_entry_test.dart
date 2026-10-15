// L5 (BOX_AND_PIECE_LINE_DESIGN 3.4, 4): a line typed as boxes and loose
// pieces. The quantity stays one figure in pieces; the shared helper is the
// one place the two cells are added up, split and made into full boxes, so
// it is checked here once rather than in each of the editors that draw it.
//
// The editors themselves are driven in their own files: the order
// (sales_order_editor_test.dart), the quotation
// (phase2_quotation_editor_test.dart) and the bill
// (sales_invoice_editor_test.dart), each under "L5". The counter bill's
// pack scan (L5 step 11) is driven here, at the end.

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/customer.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/models/purchase.dart';
import 'package:agency_desktop/models/sales_invoice.dart';
import 'package:agency_desktop/models/vendor.dart';
import 'package:agency_desktop/phase2/document_page.dart';
import 'package:agency_desktop/ui/sales/sales_invoice_editor_dialog.dart';
import 'package:agency_desktop/ui/workspace/box_piece_cells.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('the sum', () {
    test('a pack of one or none is no pack', () {
      expect(packOf('12.0000'), 12);
      expect(packOf(''), isNull);
      expect(packOf('1'), isNull);
      expect(packOf('0'), isNull);
    });

    test('pieces split into full boxes and what is left', () {
      final ({int boxes, double pieces}) split = splitPieces(41, 12);
      expect(split.boxes, 3);
      expect(split.pieces, 5);
      expect(splitPieces(24, 12).pieces, 0);
      expect(splitPieces(5, 12).boxes, 0);
    });

    test('boxes and pieces add up to pieces, nothing rounded', () {
      expect(addBoxesAndPieces(3, 5, 12), 41);
      expect(addBoxesAndPieces(0, 7, null), 7);
      expect(addBoxesAndPieces(2, 1.5, 10), 21.5);
    });

    test('read-only figures read 3 x 12 + 5', () {
      expect(boxesAndPieces('41.0000', '12.0000'), '3 x 12 + 5');
      expect(boxesAndPieces('24', '12'), '2 x 12');
      expect(boxesAndPieces('5', '12'), '5');
      expect(boxesAndPieces('41', ''), '41');
    });

    test("the side panel's line", () {
      expect(
        boxPieceSummary(
            packSize: '12', quantity: '41', free: '2', rate: '10.00'),
        'Box of 12. 3 boxes + 5 pcs = 41 pcs. Free 2 pcs. '
        'Rate of a box 120.00.',
      );
      expect(
        boxPieceSummary(packSize: '12', quantity: '12', free: '', rate: ''),
        'Box of 12. 1 box = 12 pcs.',
      );
      expect(
        boxPieceSummary(packSize: '', quantity: '7', free: '', rate: '5'),
        isEmpty,
      );
    });
  });

  group('one line', () {
    test('the cells fill from pieces and add back to them', () {
      final BoxPieceEntry entry = BoxPieceEntry()
        ..load(quantity: '41.0000', free: '14', pack: 12);
      expect(entry.box.text, '3');
      expect(entry.pcs.text, '5');
      expect(entry.freeBox.text, '1');
      expect(entry.freePcs.text, '2');
      expect(entry.quantityText(12), '41');
      expect(entry.freeText(12), '14');
      entry.dispose();
    });

    test('2 + 17 in a 12-pack becomes 3 + 5, said once', () {
      final BoxPieceEntry entry = BoxPieceEntry();
      entry.box.text = '2';
      entry.pcs.text = '17';
      expect(entry.normalise(12), isTrue);
      expect(entry.box.text, '3');
      expect(entry.pcs.text, '5');
      expect(entry.note, '17 pcs is 1 box + 5');
      expect(entry.quantityText(12), '41');
      // Already full boxes: nothing moves and nothing is said again.
      entry.note = '';
      expect(entry.normalise(12), isFalse);
      expect(entry.note, isEmpty);
      entry.dispose();
    });

    test('free goods: blank takes the offer, a typed 0 refuses it', () {
      final BoxPieceEntry entry = BoxPieceEntry()
        ..load(quantity: '5', free: '', pack: 12);
      expect(entry.freeBox.text, isEmpty);
      expect(entry.freePcs.text, isEmpty);
      expect(entry.freeText(12), isEmpty);
      entry.freePcs.text = '0';
      expect(entry.freeText(12), '0');
      entry.load(quantity: '5', free: '0', pack: 12);
      expect(entry.freePcs.text, '0');
      expect(entry.freeText(12), '0');
      entry.dispose();
    });

    test('an item with no pack is typed in pieces alone', () {
      final BoxPieceEntry entry = BoxPieceEntry()
        ..load(quantity: '7', free: '', pack: null);
      expect(entry.box.text, isEmpty);
      expect(entry.pcs.text, '7');
      entry.box.text = '9';
      // A stray figure in a closed box cell counts for nothing.
      expect(entry.quantityText(null), '7');
      expect(entry.normalise(null), isFalse);
      entry.dispose();
    });

    testWidgets('the cursor runs Box, Pcs, Free box, Free pcs and passes '
        "over an unpacked item's closed box cells", (tester) async {
      final BoxPieceEntry packed = BoxPieceEntry();
      final BoxPieceEntry loose = BoxPieceEntry();
      addTearDown(packed.dispose);
      addTearDown(loose.dispose);
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: Builder(
            builder: (context) => Column(children: [
              for (final (String prefix, BoxPieceEntry entry, double? pack)
                  in [('a', packed, 12.0), ('b', loose, null)])
                Row(children: [
                  for (final Widget cell in boxPieceCells(
                    context,
                    entry: entry,
                    pack: pack,
                    readOnly: false,
                    keyPrefix: prefix,
                    onChanged: () {},
                  ))
                    SizedBox(width: 80, child: cell),
                ]),
            ]),
          ),
        ),
      ));
      bool focused(String key) => tester
          .widget<EditableText>(find.descendant(
            of: find.byKey(ValueKey<String>(key)),
            matching: find.byType(EditableText),
          ))
          .focusNode
          .hasFocus;

      expect(find.byKey(const ValueKey('b-box-closed')), findsOneWidget);
      expect(find.byKey(const ValueKey('b-free-box-closed')), findsOneWidget);
      await tester.tap(find.byKey(const ValueKey('a-box')));
      await tester.pump();
      for (final String next in const [
        'a-pcs',
        'a-free-box',
        'a-free-pcs',
        'b-pcs',
        'b-free-pcs',
      ]) {
        await tester.sendKeyEvent(LogicalKeyboardKey.tab);
        await tester.pump();
        expect(focused(next), isTrue, reason: next);
      }
    });
  });

  group('what the screens read and send', () {
    test('the settings carry the switch, off by default', () {
      expect(SalesWorkflowSettings.wholeChain.boxAndPieceEntry, isFalse);
      expect(
        SalesWorkflowSettings.fromJson(<String, dynamic>{
          'box_and_piece_entry': true,
        }).toJson()['box_and_piece_entry'],
        isTrue,
      );
      expect(PurchaseWorkflowSettings.wholeChain.boxAndPieceEntry, isFalse);
      expect(
        PurchaseWorkflowSettings.fromJson(<String, dynamic>{
          'box_and_piece_entry': true,
        }).toJson()['box_and_piece_entry'],
        isTrue,
      );
    });

    test('customers, suppliers and items carry their mark and pack', () {
      expect(
        Customer.fromJson(<String, dynamic>{'box_and_piece_entry': true})
            .boxAndPieceEntry,
        isTrue,
      );
      expect(
        Vendor.fromJson(<String, dynamic>{'box_and_piece_entry': true})
            .boxAndPieceEntry,
        isTrue,
      );
      final Product item = Product.fromJson(<String, dynamic>{
        'id': 'p1',
        'pack_size': '12.0000',
        'pack_unit_code': 'BOX',
        'buying_pack_size': '24.0000',
        'buying_pack_unit_code': 'CTN',
      });
      expect(item.packSize, '12.0000');
      expect(item.packUnitCode, 'BOX');
      expect(item.buyingPackSize, '24.0000');
      expect(item.buyingPackUnitCode, 'CTN');
    });

    test('the lists filter by the mark only when asked', () {
      expect(const CustomerQuery().toQuery(), isEmpty);
      expect(
        const CustomerQuery(boxAndPieceEntry: true).toQuery(),
        <String, String>{'box_and_piece_entry': 'true'},
      );
      expect(
        const VendorQuery(boxAndPieceEntry: false).toQuery(),
        <String, String>{'box_and_piece_entry': 'false'},
      );
    });

    test('the four cells take the place of Qty and Free', () {
      expect(
        <String>[for (final DocumentColumn column in boxPieceColumns)
            column.label],
        <String>['Box', 'Pcs', 'Free box', 'Free pcs'],
      );
    });
  });

  // L5 step 11 (BOX_AND_PIECE_LINE_DESIGN 5, "Pack barcode"): on a counter
  // bill typed as boxes and pieces, a scan of the line's own pack adds one
  // to Box; any other scan adds its pieces to Pcs, evened out into boxes.
  group('the pack scan on the counter bill', () {
    Future<void> scan(WidgetTester tester, String code) async {
      await tester.enterText(
          find.byKey(const ValueKey('counter-scan-field')), code);
      await tester.testTextInput.receiveAction(TextInputAction.done);
      await tester.pump(const Duration(milliseconds: 400));
      await tester.pumpAndSettle();
    }

    String cell(WidgetTester tester, String name) => tester
        .widget<EditableText>(find.descendant(
          of: find.byKey(ValueKey<String>('sales-invoice-direct-0-$name')),
          matching: find.byType(EditableText),
        ))
        .controller
        .text;

    Future<_ScanApi> open(WidgetTester tester, {required bool marked}) async {
      final _ScanApi api = _ScanApi(marked: marked);
      tester.view.physicalSize = const Size(1600, 900);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: Phase2Scope(
            child: SalesInvoiceEditorDialog(
              api: api,
              today: DateTime(2026, 10, 15),
              printer: (context, bytes, name) async {},
            ),
          ),
        ),
      ));
      await tester.pumpAndSettle();
      await tester.pump(const Duration(milliseconds: 400));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('sales-invoice-customer')));
      await tester.pumpAndSettle();
      await tester.tap(find.textContaining('Kirana Stores').last);
      await tester.pumpAndSettle();
      return api;
    }

    testWidgets('a box of the line adds to Box; a piece and another pack add '
        'to Pcs and even out', (tester) async {
      final _ScanApi api = await open(tester, marked: true);
      expect(find.byKey(const ValueKey('sales-invoice-box-and-pieces')),
          findsOneWidget);

      // First on the bill: a line of its own, one box.
      await scan(tester, _boxOfSoap);
      expect(cell(tester, 'box'), '1');
      expect(cell(tester, 'pcs'), isEmpty);

      // The product's own barcode: one piece, in Pcs.
      await scan(tester, '8901234567890');
      expect(cell(tester, 'box'), '1');
      expect(cell(tester, 'pcs'), '1');

      await scan(tester, _boxOfSoap);
      expect(cell(tester, 'box'), '2');
      expect(cell(tester, 'pcs'), '1');

      // A case of 24 is not the line's box: its pieces go to Pcs, and 25
      // pieces are two boxes and one.
      await scan(tester, _caseOfSoap);
      expect(cell(tester, 'box'), '4');
      expect(cell(tester, 'pcs'), '1');
      expect(find.text('25 pcs is 2 boxes + 1'), findsOneWidget);
      expect(find.byKey(const ValueKey('sales-invoice-direct-1')),
          findsNothing);
      expect(api.lookups, [_boxOfSoap, _boxOfSoap, _caseOfSoap]);

      // What is priced is still one figure in pieces.
      final Json line = (api.previews.last['lines'] as List).first as Json;
      expect(line['current_invoice_quantity'], '49');
      expect(line['pack_size'], '12.0000');
      expect(tester.takeException(), isNull);
    });

    testWidgets('a bill in pieces only adds the pieces, as before',
        (tester) async {
      final _ScanApi api = await open(tester, marked: false);
      await scan(tester, _boxOfSoap);
      await scan(tester, '8901234567890');
      expect(find.byKey(const ValueKey('sales-invoice-direct-0-box')),
          findsNothing);
      final Json line = (api.previews.last['lines'] as List).first as Json;
      expect(line['current_invoice_quantity'], '13');
      expect(line.containsKey('pack_size'), isFalse);
      expect(tester.takeException(), isNull);
    });
  });
}

/// A box of twelve soaps: the line's own pack.
const String _boxOfSoap = '8901234567906';

/// A case of twenty-four: a pack, but not the line's box.
const String _caseOfSoap = '8901234567913';

/// A counter bill's server: one customer, one soap twelve to a box, and the
/// barcode lookup for its box and its case.
class _ScanApi extends ApiClient {
  _ScanApi({required this.marked})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  /// Whether the customer is marked *Bills in boxes and pieces*.
  final bool marked;

  final List<String> lookups = <String>[];
  final List<Json> previews = <Json>[];

  @override
  Future<Json> request(
    String method,
    String path, {
    Json? body,
    Map<String, String>? query,
    bool authenticated = true,
    bool retrying = false,
    int? expectedVersion,
  }) async {
    if (path.contains('workflow-settings')) {
      return <String, dynamic>{
        'data': <String, dynamic>{
          'quotation_stage': false,
          'sales_order_stage': false,
          'delivery_note_stage': false,
          'default_warehouse_id': 'wh-main',
          'is_configured': true,
          'box_and_piece_entry': true,
        },
      };
    }
    if (path.endsWith('/batch-serial/sale-settings')) {
      return <String, dynamic>{
        'data': <String, dynamic>{'price_from_batch': false},
      };
    }
    if (method == 'GET' && path.startsWith('/api/v1/customers')) {
      return <String, dynamic>{
        'data': <Json>[
          <String, dynamic>{
            'id': 'cust-1',
            'code': 'C-1',
            'name': 'Kirana Stores',
            'display_name': 'Kirana Stores',
            'box_and_piece_entry': marked,
          },
        ],
      };
    }
    if (method == 'GET' && path.startsWith('/api/v1/products')) {
      return <String, dynamic>{
        'data': <Json>[
          <String, dynamic>{
            'id': 'prod-1',
            'code': 'P-1',
            'name': 'Soap',
            'barcode': '8901234567890',
            'selling_price': '50',
            'pack_size': '12.0000',
            'pack_unit_code': 'BOX',
          },
        ],
      };
    }
    if (path.contains('/uom-framework/barcode-lookup')) {
      final String code = Uri.parse(path).queryParameters['code'] ?? '';
      lookups.add(code);
      final bool box = code == _boxOfSoap;
      if (box || code == _caseOfSoap) {
        return <String, dynamic>{
          'data': <String, dynamic>{
            'code': code,
            'product_id': 'prod-1',
            'product_code': 'P-1',
            'product_name': 'Soap',
            'packaging_level_id': box ? 'level-box' : 'level-case',
            'level_name': box ? 'Box' : 'Case',
            'base_quantity': box ? '12.000000' : '24.000000',
            'matched_field': 'barcode',
            'uom_code': box ? 'BOX' : 'CASE',
            'stock_uom_code': 'PCS',
          },
        };
      }
      throw ApiException('Nothing in this firm carries the code $code.',
          statusCode: 404);
    }
    if (path.contains('billable')) return <String, dynamic>{'data': <Json>[]};
    if (method == 'POST' && path == '/api/v1/sales-invoices/preview') {
      previews.add(body!);
      return <String, dynamic>{
        'data': <String, dynamic>{
          'interstate': false,
          'invoice': <String, dynamic>{
            'invoice_number': 'SI-1',
            'subtotal': '0',
            'tax_total': '0',
            'grand_total': '0',
            'lines': const <Json>[],
          },
          'lines': const <Json>[],
        },
      };
    }
    return <String, dynamic>{'data': const <Json>[]};
  }
}
