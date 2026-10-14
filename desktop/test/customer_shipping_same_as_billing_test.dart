// A customer is billed at one address and his goods go to one address, and
// most of the time it is the same one (the owner, 2026-10-14). The flags were
// already there -- an address is the default billing one, the default
// shipping one, or both -- but a new address started with neither ticked, so
// a customer's only address was marked for nothing unless somebody knew to
// tick both. These pin the words a counter uses: Same as billing, or
// Different.

import 'package:agency_desktop/ui/customers/customer_management_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Future<void> _openAddresses(WidgetTester tester) async {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = const Size(1366, 900);
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: CustomerWorkspaceDialog(
          mode: CustomerDialogMode.create,
          customer: null,
          onSave: (_) async => throw UnimplementedError(),
          loadPlaces: (level, {parentId = ''}) async => const [],
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
  await tester.tap(find.text('Address'));
  await tester.pumpAndSettle();
}

Future<void> _addAddress(WidgetTester tester) async {
  await tester.tap(find.text('Add address'));
  await tester.pumpAndSettle();
}

/// Billing and shipping, in card order: [billing1, shipping1, billing2, ...].
List<bool> _flags(WidgetTester tester) => <bool>[
      for (final FilterChip chip
          in tester.widgetList<FilterChip>(find.byType(FilterChip)))
        chip.selected,
    ];

Future<void> _choose(WidgetTester tester, String label) async {
  await tester.tap(find.descendant(
    of: find.byKey(const ValueKey('customer-shipping-same')),
    matching: find.text(label),
  ));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('the first address is the billing and the shipping one',
      (tester) async {
    await _openAddresses(tester);
    expect(find.byKey(const ValueKey('customer-shipping-same')), findsNothing,
        reason: 'no address, nothing to choose');

    await _addAddress(tester);

    expect(_flags(tester), <bool>[true, true]);
    final SegmentedButton<bool> choice = tester.widget(
        find.byKey(const ValueKey('customer-shipping-same')));
    expect(choice.selected, <bool>{true});
  });

  testWidgets('a second address added by hand is marked for nothing',
      (tester) async {
    await _openAddresses(tester);
    await _addAddress(tester);
    await _addAddress(tester);

    expect(_flags(tester), <bool>[true, true, false, false]);
  });

  testWidgets('Different opens a shipping address to fill in', (tester) async {
    await _openAddresses(tester);
    await _addAddress(tester);

    await _choose(tester, 'Different');

    expect(find.text('Address 2'), findsOneWidget);
    expect(_flags(tester), <bool>[true, false, false, true]);
  });

  testWidgets('Same again puts shipping back on billing and deletes nothing',
      (tester) async {
    await _openAddresses(tester);
    await _addAddress(tester);
    await _choose(tester, 'Different');

    await _choose(tester, 'Same as billing');

    expect(find.text('Address 2'), findsOneWidget,
        reason: 'the other address stays, it is only no longer the default');
    expect(_flags(tester), <bool>[true, true, false, false]);
  });

  testWidgets('Different uses an address already there before adding one',
      (tester) async {
    await _openAddresses(tester);
    await _addAddress(tester);
    await _addAddress(tester);

    await _choose(tester, 'Different');

    expect(find.text('Address 3'), findsNothing);
    expect(_flags(tester), <bool>[true, false, false, true]);
  });
}
