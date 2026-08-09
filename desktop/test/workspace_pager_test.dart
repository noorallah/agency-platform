import 'package:agency_desktop/ui/workspace/workspace_components.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Six workspaces render their own list rather than composing
/// [EnterpriseDataGrid], and so had no pager: they fetched a total they
/// sometimes displayed and stayed on page one for the life of the screen, which
/// put every record past the first page out of reach.
Future<void> _pump(
  WidgetTester tester, {
  required int page,
  required int pageSize,
  required int total,
  required ValueChanged<int> onPageChanged,
}) =>
    tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: WorkspacePager(
            page: page,
            pageSize: pageSize,
            total: total,
            onPageChanged: onPageChanged,
          ),
        ),
      ),
    );

void main() {
  testWidgets('a single page of results shows no pager at all', (tester) async {
    await _pump(tester, page: 1, pageSize: 20, total: 20, onPageChanged: (_) {});
    expect(find.byIcon(Icons.chevron_right), findsNothing);
    expect(find.byIcon(Icons.chevron_left), findsNothing);
  });

  testWidgets('the range and total describe the page on screen', (tester) async {
    await _pump(tester, page: 2, pageSize: 20, total: 137, onPageChanged: (_) {});
    expect(find.text('21–40 of 137'), findsOneWidget);
  });

  testWidgets('the last page stops at the record count', (tester) async {
    await _pump(tester, page: 7, pageSize: 20, total: 137, onPageChanged: (_) {});
    expect(find.text('121–137 of 137'), findsOneWidget);
  });

  testWidgets('the first page cannot go back and the last cannot go on', (
    tester,
  ) async {
    await _pump(tester, page: 1, pageSize: 20, total: 137, onPageChanged: (_) {});
    expect(
      tester
          .widget<IconButton>(
            find.ancestor(
              of: find.byIcon(Icons.chevron_left),
              matching: find.byType(IconButton),
            ),
          )
          .onPressed,
      isNull,
    );

    await _pump(tester, page: 7, pageSize: 20, total: 137, onPageChanged: (_) {});
    expect(
      tester
          .widget<IconButton>(
            find.ancestor(
              of: find.byIcon(Icons.chevron_right),
              matching: find.byType(IconButton),
            ),
          )
          .onPressed,
      isNull,
    );
  });

  testWidgets('paging forward and back requests the neighbouring page', (
    tester,
  ) async {
    final List<int> requested = <int>[];
    await _pump(
      tester,
      page: 3,
      pageSize: 20,
      total: 137,
      onPageChanged: requested.add,
    );

    await tester.tap(find.byIcon(Icons.chevron_right));
    await tester.tap(find.byIcon(Icons.chevron_left));

    expect(requested, [4, 2]);
  });
}
