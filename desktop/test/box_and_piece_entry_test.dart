// L5 (BOX_AND_PIECE_LINE_DESIGN 3.4, 4): a line typed as boxes and loose
// pieces. The quantity stays one figure in pieces; the shared helper is the
// one place the two cells are added up, split and made into full boxes, so
// it is checked here once rather than in each of the editors that draw it.
//
// The editors themselves are driven in their own files: the order
// (sales_order_editor_test.dart), the quotation
// (phase2_quotation_editor_test.dart) and the bill
// (sales_invoice_editor_test.dart), each under "L5".

import 'package:agency_desktop/models/customer.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/models/purchase.dart';
import 'package:agency_desktop/models/sales_invoice.dart';
import 'package:agency_desktop/models/vendor.dart';
import 'package:agency_desktop/phase2/document_page.dart';
import 'package:agency_desktop/ui/workspace/box_piece_cells.dart';
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
}
