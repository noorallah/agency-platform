import 'package:agency_desktop/ui/workspace/desktop_framework.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

/// Documents as full-page tabs (UI_PHASE_2_DESIGN.md 4.8, decision 4).
///
/// Every editor was written as a dialog: opened with `showDialog`, closed with
/// `Navigator.pop(result)`, its caller awaiting the result. `showDocument`
/// must keep each of those true in both apps, or an editor saves and its list
/// never hears about it.
Widget _editor(BuildContext context, {String body = 'order lines'}) =>
    WorkspaceDialog(
      title: 'New sales order',
      subtitle: 'Taken over the counter.',
      body: Center(child: Text(body)),
      onSave: () => Navigator.of(context).pop(true),
      saveLabel: 'Create draft',
    );

void main() {
  testWidgets('phase 1: showDocument is the dialog it always was',
      (tester) async {
    bool? result;
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Builder(
          builder: (context) => TextButton(
            onPressed: () async => result = await showDocument<bool>(
              context,
              title: 'New sales order',
              builder: (context) => _editor(context),
            ),
            child: const Text('open'),
          ),
        ),
      ),
    ));
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    expect(find.byType(Dialog), findsOneWidget);
    await tester.tap(find.text('Create draft'));
    await tester.pumpAndSettle();
    expect(result, isTrue);
  });

  group('phase 2', () {
    late DocumentTabsController tabs;

    Future<void> pumpHost(WidgetTester tester) async {
      tabs = DocumentTabsController();
      addTearDown(tabs.dispose);
      tester.view.physicalSize = const Size(1366, 768);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: DocumentTabsScope(
            controller: tabs,
            child: AnimatedBuilder(
              animation: tabs,
              builder: (context, _) => Stack(children: [
                const Text('the list'),
                for (final OpenDocument document in tabs.documents)
                  DocumentNavigator(
                    key: ValueKey(document.id),
                    document: document,
                  ),
              ]),
            ),
          ),
        ),
      ));
    }

    testWidgets('a document opens as a page, not a dialog', (tester) async {
      await pumpHost(tester);
      final BuildContext context = tester.element(find.text('the list'));
      showDocument<bool>(
        context,
        title: 'New sales order',
        builder: (context) => _editor(context),
      );
      await tester.pump();
      expect(tabs.documents.single.title, 'New sales order');
      expect(find.text('order lines'), findsOneWidget);
      expect(find.byType(Dialog), findsNothing);
      // The title line is one line: the subtitle beside the title.
      expect(
        (tester.getCenter(find.text('Taken over the counter.')).dy -
                tester.getCenter(find.text('New sales order')).dy)
            .abs(),
        lessThan(4),
      );
      // The buttons are along the bottom of the page.
      expect(tester.getBottomLeft(find.text('Create draft')).dy,
          greaterThan(700));
      expect(tester.takeException(), isNull);
    });

    testWidgets("the editor's own pop closes the tab and returns its result",
        (tester) async {
      await pumpHost(tester);
      bool? result;
      final BuildContext context = tester.element(find.text('the list'));
      showDocument<bool>(
        context,
        title: 'New sales order',
        builder: (context) => _editor(context),
      ).then((value) => result = value);
      await tester.pump();
      await tester.tap(find.text('Create draft'));
      await tester.pump();
      expect(result, isTrue);
      expect(tabs.documents, isEmpty);
      expect(find.text('order lines'), findsNothing);
    });

    testWidgets('closing the tab is Cancel: nothing is returned',
        (tester) async {
      await pumpHost(tester);
      Object? result = 'untouched';
      final BuildContext context = tester.element(find.text('the list'));
      showDocument<bool>(
        context,
        title: 'New sales order',
        builder: (context) => _editor(context),
      ).then((value) => result = value);
      await tester.pump();
      tabs.close(tabs.documents.single.id);
      await tester.pump();
      expect(result, isNull);
      expect(tabs.documents, isEmpty);
    });

    testWidgets('Escape closes the document, as it closed the dialog',
        (tester) async {
      await pumpHost(tester);
      final BuildContext context = tester.element(find.text('the list'));
      showDocument<bool>(
        context,
        title: 'New sales order',
        builder: (context) => _editor(context),
      );
      await tester.pump();
      await tester.pump();
      await tester.sendKeyEvent(LogicalKeyboardKey.escape);
      await tester.pump();
      expect(tabs.documents, isEmpty);
    });
  });
}
