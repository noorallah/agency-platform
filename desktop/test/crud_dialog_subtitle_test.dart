// A dialog should say which record it is about.
//
// The header's second line read "Edit existing record", which is true of every
// dialog in the application and therefore tells the reader nothing. That is
// tolerable on a form carrying the record's own name and code; it is not
// tolerable on an assignment screen, where the form is a picker and nothing on
// screen names the firm, user or role being changed.
//
// A profile decides which features and modules a firm operates, so assigning
// one to the wrong firm is not a cosmetic mistake.

import 'package:agency_desktop/ui/resource_management_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Future<void> _pump(WidgetTester tester, Widget header) async {
  await tester.pumpWidget(MaterialApp(home: Scaffold(body: header)));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('a subtitle replaces the generic mode line', (tester) async {
    await _pump(
      tester,
      const CrudWorkspaceHeader(
        title: 'Profile Assignment',
        subtitle: 'WHOLE01 — Wholesale Hub  ·  Chennai  ·  IN  ·  Active',
        mode: CrudDialogMode.edit,
        onClose: null,
      ),
    );

    expect(find.textContaining('WHOLE01 — Wholesale Hub'), findsOneWidget);
    expect(find.text('Edit existing record'), findsNothing);
  });

  testWidgets('without one the mode line still shows', (tester) async {
    // Every other dialog keeps its current behaviour: this is an opt-in, so a
    // screen that says nothing must not end up with a blank second line.
    await _pump(
      tester,
      const CrudWorkspaceHeader(
        title: 'Products',
        mode: CrudDialogMode.edit,
        onClose: null,
      ),
    );

    expect(find.text('Edit existing record'), findsOneWidget);
  });

  testWidgets('a create says so rather than naming a record', (tester) async {
    await _pump(
      tester,
      const CrudWorkspaceHeader(
        title: 'Products',
        mode: CrudDialogMode.create,
        onClose: null,
      ),
    );

    expect(find.text('Create new record'), findsOneWidget);
  });

  testWidgets('a long subtitle does not overflow the header', (tester) async {
    // The header is a Row; an unbounded string in it is the classic overflow,
    // and a firm name is user-supplied text of no fixed length.
    tester.view.physicalSize = const Size(600, 300);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await _pump(
      tester,
      CrudWorkspaceHeader(
        title: 'Profile Assignment',
        subtitle: 'WHOLE01 — ${'A very long firm name ' * 12}  ·  Active',
        mode: CrudDialogMode.edit,
        onClose: () {},
      ),
    );

    expect(tester.takeException(), isNull);
  });
}
