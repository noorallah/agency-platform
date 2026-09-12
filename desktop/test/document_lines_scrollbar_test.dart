// The document lines table scrolls sideways under a bar that is always
// visible. Raised from manual testing: with thirteen columns and no bar, the
// table read as "not displaying" on a mouse-driven desktop.

import 'package:agency_desktop/models/document_framework.dart';
import 'package:agency_desktop/ui/document_framework/document_framework_widgets.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('the lines table carries a visible horizontal scrollbar',
      (tester) async {
    tester.view.physicalSize = const Size(900, 700);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: EnterpriseDocumentLines(
          lines: const [
            DocumentLineSnapshot(
              lineNumber: 1,
              product: 'DETER1K',
              description: 'Detergent',
              uom: 'PACK',
              packaging: '',
              quantity: '10',
              freeQuantity: '0',
              unitPrice: '100',
              discount: '0',
              taxProfile: 'GST_18_LOCAL',
              amount: '1000',
              netAmount: '1000',
              remarks: '',
            ),
          ],
        ),
      ),
    ));
    await tester.pumpAndSettle();

    final Scrollbar bar = tester.widget<Scrollbar>(find.byType(Scrollbar));
    expect(bar.thumbVisibility, isTrue);
    expect(bar.controller, isNotNull);
    final SingleChildScrollView view =
        tester.widget<SingleChildScrollView>(find.descendant(
      of: find.byType(DocumentLinesScroller),
      matching: find.byType(SingleChildScrollView),
    ));
    expect(view.scrollDirection, Axis.horizontal);
    expect(identical(view.controller, bar.controller), isTrue,
        reason: 'the bar and the view must share one controller');
    expect(find.text('PACK'), findsOneWidget);
  });
}
