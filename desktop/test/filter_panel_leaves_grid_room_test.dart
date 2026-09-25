// D-QA-15: on the tester's laptop, expanding the Stock Ledger's filters left
// the grid a sliver with no reachable rows. The filter panel sat in the
// workspace column with no bound, so a dozen fields on a short or highly
// scaled display took nearly all the height. Every screen built on
// ManagementWorkspaceLayout shared it; the panel is now capped and scrolls.

import 'package:agency_desktop/ui/workspace/desktop_framework.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('an expanded filter panel leaves the grid most of the height',
      (tester) async {
    const double height = 560;
    await tester.binding.setSurfaceSize(const Size(1366, height));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    double? gridHeight;

    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: ManagementWorkspaceLayout(
          toolbar: const SizedBox(width: 100, height: 40),
          searchPanel: const SizedBox(height: 40),
          filterPanel: FilterPanel(
            expanded: true,
            children: [
              for (int index = 0; index < 24; index++)
                SizedBox(
                  width: 300,
                  height: 56,
                  child: Text('Filter $index'),
                ),
            ],
          ),
          primaryContent: LayoutBuilder(builder: (context, constraints) {
            gridHeight = constraints.maxHeight;
            return const SizedBox.expand();
          }),
          statusBar: const SizedBox(height: 28),
        ),
      ),
    ));
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
    expect(gridHeight, isNotNull);
    expect(gridHeight!, greaterThan(height * 0.35),
        reason: 'the grid must keep room for rows whatever the filters take');

    // The fields past the cap are still reachable, by scrolling the panel.
    await tester.scrollUntilVisible(find.text('Apply filters'), 100,
        scrollable: find
            .descendant(
              of: find.byType(ManagementWorkspaceLayout),
              matching: find.byType(Scrollable),
            )
            .first);
    expect(find.text('Apply filters'), findsOneWidget);
  });
}
