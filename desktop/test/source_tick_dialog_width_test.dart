import 'package:agency_desktop/phase2/source_tick_dialog.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';

/// The bill's "Goods receipts to bill" tick list prints whole numbers.
///
/// Found in the purchasing walkthrough on QA01 (2026-10-04, D-UI-7): at 620
/// wide the number and order columns cut `GRN-QA01-HO-2026-2027-000003` to
/// "GRN-QA01-H..." and two receipts on one order could only be told apart by
/// their amounts. As in `source_document_picker_width_test.dart`, the test
/// font is a fixed-width block glyph, so the guard is on the room each column
/// gives its text -- 8 px a character, a generous mean for the 14 px face.
const String _grnNumber = 'GRN-WHOLE01-WHL_HO-2026-2027-000006';
const String _poNumber = 'PO-WHOLE01-BR_NORTH-2026-2027-000001';
const double _pixelsPerCharacter = 8;

/// The width the paragraph showing [text] is allowed to take.
double _roomFor(WidgetTester tester, String text) {
  // The paragraph under the Text: inside a SelectionArea (backlog 83) a
  // Text draws a mouse region around its paragraph.
  final RenderParagraph paragraph = tester.renderObject<RenderParagraph>(
    find.descendant(of: find.text(text), matching: find.byType(RichText)),
  );
  return paragraph.constraints.maxWidth;
}

void main() {
  testWidgets('the tick list gives a long receipt and order number room',
      (tester) async {
    tester.view.physicalSize = const Size(1366, 768);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(
      home: Builder(
        builder: (context) => Scaffold(
          body: TextButton(
            onPressed: () => showSourceTickDialog(
              context,
              title: 'Goods receipts to bill',
              keyPrefix: 'test',
              rows: const [
                SourceTickRow(
                  id: 'r1',
                  number: _grnNumber,
                  date: '04-10-2026',
                  order: _poNumber,
                  amount: '708.00',
                ),
              ],
              initial: const {},
              clashFor: (id, ticked) => null,
              numberLabel: 'Goods receipt',
              amountLabel: 'Received value',
              confirmNoun: 'receipt',
            ),
            child: const Text('open'),
          ),
        ),
      ),
    ));
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();

    expect(_roomFor(tester, _grnNumber),
        greaterThanOrEqualTo(_grnNumber.length * _pixelsPerCharacter));
    expect(_roomFor(tester, _poNumber),
        greaterThanOrEqualTo(_poNumber.length * _pixelsPerCharacter));
  });

  testWidgets('the tick list still fits a narrow window', (tester) async {
    tester.view.physicalSize = const Size(800, 600);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(
      home: Builder(
        builder: (context) => Scaffold(
          body: TextButton(
            onPressed: () => showSourceTickDialog(
              context,
              title: 'Goods receipts to bill',
              keyPrefix: 'test',
              rows: const [
                SourceTickRow(id: 'r1', number: _grnNumber, date: '04-10-2026'),
              ],
              initial: const {},
              clashFor: (id, ticked) => null,
              numberLabel: 'Goods receipt',
              amountLabel: 'Received value',
              confirmNoun: 'receipt',
            ),
            child: const Text('open'),
          ),
        ),
      ),
    ));
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
  });
}
