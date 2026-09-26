import 'package:agency_desktop/phase2/command_box.dart';
import 'package:agency_desktop/phase2/menu_layout.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

/// The Ctrl+K box (UI_PHASE_2_DESIGN.md 4.4).
final List<CommandScreen> _all = commandScreens(MenuLayout.all);

List<String> _labels(String query) =>
    [for (final CommandScreen s in matchScreens(_all, query)) s.item.label];

Future<CommandChoice?> _run(
  WidgetTester tester,
  Future<void> Function() interact, {
  List<CommandScreen>? screens,
}) async {
  CommandChoice? chosen;
  bool done = false;
  await tester.pumpWidget(MaterialApp(
    home: Builder(
      builder: (context) => Scaffold(
        body: TextButton(
          onPressed: () async {
            chosen = await showCommandBox(context, screens: screens ?? _all);
            done = true;
          },
          child: const Text('open'),
        ),
      ),
    ),
  ));
  await tester.tap(find.text('open'));
  await tester.pumpAndSettle();
  await interact();
  await tester.pumpAndSettle();
  expect(done, isTrue, reason: 'the box should have closed');
  return chosen;
}

void main() {
  test('every screen the menu offers is in the box', () {
    expect(_all.length,
        MenuLayout.all.fold<int>(0, (n, area) => n + area.items.length));
  });

  test('a name that starts with the words comes first', () {
    expect(_labels('sales').first, 'Sales Orders');
    expect(_labels('cust').first, 'Customers');
  });

  test('the words people use find the screen: bill, GRN, PO', () {
    expect(_labels('bill').first, 'Sales Invoices');
    expect(_labels('grn').first, 'Goods Receipts');
    expect(_labels('po').first, 'Purchase Orders');
    expect(_labels('supplier'), contains('Vendors'));
  });

  test('several words must all match', () {
    expect(_labels('stock ledger'), ['Stock Ledger']);
    expect(_labels('zzz'), isEmpty);
  });

  test('an empty box lists everything in menu order', () {
    expect(_labels(''), [for (final s in _all) s.item.label]);
  });

  testWidgets('typing and Enter opens the first match', (tester) async {
    final CommandChoice? choice = await _run(tester, () async {
      await tester.enterText(
          find.byKey(const ValueKey('command-box-input')), 'bill');
      await tester.pump();
      await tester.testTextInput.receiveAction(TextInputAction.done);
    });
    expect((choice! as OpenScreenChoice).item.path,
        'salesInvoices/sales-invoices');
  });

  testWidgets('arrow keys move, and the last row searches records',
      (tester) async {
    final CommandChoice? choice = await _run(tester, () async {
      await tester.enterText(
          find.byKey(const ValueKey('command-box-input')), 'grn');
      await tester.pump();
      // One screen matches; the next row down is the record search.
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
      await tester.pump();
      await tester.testTextInput.receiveAction(TextInputAction.done);
    });
    expect((choice! as SearchRecordsChoice).query, 'grn');
  });

  testWidgets('a screen the user may not open is never offered',
      (tester) async {
    final List<CommandScreen> limited = commandScreens(
      MenuLayout.areas.where((area) => area.id == 'masters'),
    );
    await _run(tester, () async {
      await tester.enterText(
          find.byKey(const ValueKey('command-box-input')), 'bill');
      await tester.pump();
      expect(find.text('Sales Invoices'), findsNothing);
      await tester.sendKeyEvent(LogicalKeyboardKey.escape);
    }, screens: limited);
  });
}
