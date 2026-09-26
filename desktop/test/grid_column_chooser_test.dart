// The Columns button on the sales lists (owner, 2026-09-27): a list offers
// every column it can show, starts with its defaults, keeps the number
// column whatever is chosen, and remembers the choice per screen.

import 'dart:async';
import 'dart:io';

import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Directory _scratch() {
  final Directory directory =
      Directory.systemTemp.createTempSync('grid-columns-test');
  addTearDown(() => directory.deleteSync(recursive: true));
  return directory;
}

List<ChoosableColumn<String>> _columns() => [
      ChoosableColumn(
        column: const GridColumn(key: 'number', label: 'Number'),
        cell: (item) => item,
        required: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'customer', label: 'Customer'),
        cell: (item) => 'c-$item',
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'tax', label: 'Tax'),
        cell: (item) => 't-$item',
      ),
    ];

void main() {
  test('defaults first; a choice is kept, with the number always shown',
      () async {
    final DesktopPreferencesService preferences =
        DesktopPreferencesService(directory: _scratch());
    await preferences.load();
    final ColumnChoice<String> choice = ColumnChoice(
      preferences: preferences,
      stateKey: 'test.grid',
      columns: _columns(),
    );
    expect(choice.shown, {'number', 'customer'});
    expect(choice.cells('7'), ['7', 'c-7', 't-7']);
    expect(
      [for (final GridColumn c in choice.gridColumns) c.visible],
      [true, true, false],
    );

    await choice.apply({'tax'});

    expect(choice.shown, {'number', 'tax'});
    final ColumnChoice<String> reopened = ColumnChoice(
      preferences: preferences,
      stateKey: 'test.grid',
      columns: _columns(),
    );
    expect(reopened.shown, {'number', 'tax'});
  });

  testWidgets('the chooser offers every column but the number',
      (tester) async {
    final DesktopPreferencesService preferences =
        DesktopPreferencesService(directory: _scratch());
    final ColumnChoice<String> choice = ColumnChoice(
      preferences: preferences,
      stateKey: 'test.grid',
      columns: _columns(),
    );
    late BuildContext context;
    await tester.pumpWidget(MaterialApp(
      home: Builder(builder: (c) {
        context = c;
        return const SizedBox();
      }),
    ));
    Set<String>? picked;
    unawaited(choice.pick(context).then((value) => picked = value));
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('grid-column-number')), findsNothing);
    await tester.tap(find.byKey(const ValueKey('grid-column-tax')));
    await tester.tap(find.byKey(const ValueKey('grid-column-customer')));
    await tester.tap(find.byKey(const ValueKey('grid-columns-apply')));
    await tester.pumpAndSettle();

    expect(picked, {'number', 'tax'});
  });
}
