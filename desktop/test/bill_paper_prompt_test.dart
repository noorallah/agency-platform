// The paper a sales bill prints on, asked at the moment of printing (P1).

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/bill_paper.dart';
import 'package:agency_desktop/ui/sales/bill_paper_prompt.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

class _PaperApi extends ApiClient {
  _PaperApi(this.info)
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final BillPaper info;

  @override
  Future<BillPaper> salesInvoicePaper(String id) async => info;
}

BillPaper _paper({
  String firm = 'HALF',
  String? customer,
  String paper = 'HALF',
  bool fits = true,
  bool mayChoose = true,
}) =>
    BillPaper(
      firmPaper: firm,
      customerPaper: customer,
      paper: paper,
      fitsHalfPage: fits,
      mayChoose: mayChoose,
    );

/// Opens the question and records what it returned: `null` result is a
/// cancel, `BillPaperChoice.paper` is what would be sent.
Future<void> _open(WidgetTester tester, BillPaper info, List<Object?> out) async {
  await tester.pumpWidget(MaterialApp(
    home: Builder(
      builder: (BuildContext context) => TextButton(
        onPressed: () async {
          final BillPaperChoice? choice = await askBillPaper(
            context,
            _PaperApi(info),
            invoiceId: 'inv-1',
            number: 'SI-1',
          );
          out.add(choice == null ? 'cancelled' : choice.paper ?? 'none');
        },
        child: const Text('go'),
      ),
    ),
  ));
  await tester.tap(find.text('go'));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('a full-page firm is asked nothing and sends no paper',
      (WidgetTester tester) async {
    final List<Object?> out = <Object?>[];
    await _open(
        tester, _paper(firm: 'A4', paper: 'A4', mayChoose: false), out);
    expect(find.byType(AlertDialog), findsNothing);
    expect(out, <Object?>['none']);
  });

  testWidgets('a half-page firm says Half page and Print sends HALF',
      (WidgetTester tester) async {
    final List<Object?> out = <Object?>[];
    await _open(tester, _paper(), out);
    expect(find.text('Print SI-1'), findsOneWidget);
    expect(find.text('This bill prints on a Half page.'), findsOneWidget);
    expect(find.text('Half page'), findsOneWidget);
    expect(find.text('Full page'), findsOneWidget);
    expect(
      find.text("Check the paper in the printer's tray before printing."),
      findsOneWidget,
    );
    await tester.tap(find.text('Print'));
    await tester.pumpAndSettle();
    expect(out, <Object?>['HALF']);
  });

  testWidgets('switching to Full page sends A4', (WidgetTester tester) async {
    final List<Object?> out = <Object?>[];
    await _open(tester, _paper(), out);
    await tester.tap(find.text('Full page'));
    await tester.pumpAndSettle();
    expect(find.text('This bill prints on a Full page.'), findsOneWidget);
    await tester.tap(find.text('Print'));
    await tester.pumpAndSettle();
    expect(out, <Object?>['A4']);
  });

  testWidgets('a full-page customer opens on Full page with his sentence',
      (WidgetTester tester) async {
    final List<Object?> out = <Object?>[];
    await _open(tester, _paper(customer: 'A4', paper: 'A4'), out);
    expect(
      find.text("This bill prints on a Full page: this customer's bills are "
          'set to a full page.'),
      findsOneWidget,
    );
    await tester.tap(find.text('Print'));
    await tester.pumpAndSettle();
    expect(out, <Object?>['A4']);
  });

  testWidgets('a bill too long for half a page offers no choice',
      (WidgetTester tester) async {
    final List<Object?> out = <Object?>[];
    await _open(
        tester, _paper(paper: 'A4', fits: false, mayChoose: false), out);
    expect(
      find.text('This bill prints on a Full page: it is too long for half a '
          'page.'),
      findsOneWidget,
    );
    expect(find.byType(SegmentedButton<String>), findsNothing);
    await tester.tap(find.text('Print'));
    await tester.pumpAndSettle();
    expect(out, <Object?>['none']);
  });

  testWidgets('Cancel prints nothing', (WidgetTester tester) async {
    final List<Object?> out = <Object?>[];
    await _open(tester, _paper(), out);
    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();
    expect(out, <Object?>['cancelled']);
  });
}
