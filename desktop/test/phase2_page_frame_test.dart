import 'package:agency_desktop/core/theme/theme_manager.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// The phase 2 page frame (UI_PHASE_2_DESIGN.md 4.5): nothing above the grid
/// but one line.
///
/// The owner circled everything above the Customers grid on 2026-09-25:
/// about 480 px of a ~1,100 px window before the first row. This builds a
/// page shaped like it -- title and description, a search, a toolbar, a
/// filter tile, a status bar -- from the shared framework every list screen
/// uses, once as phase 1 draws it and once inside [Phase2Scope], and measures
/// where the grid starts.
const Key _grid = ValueKey('grid');

Widget _customersShapedPage({bool withTabs = false}) => ModuleWorkspaceFrame(
      title: 'Customer Management',
      description: 'Manage firm-scoped customer masters, credit and groups.',
      breadcrumbs: const ['Workspace', 'Masters', 'Customer Management'],
      tabs: withTabs
          ? const [WorkspaceTab(label: 'List'), WorkspaceTab(label: 'Groups')]
          : null,
      child: ManagementWorkspaceLayout(
        searchPanel: SearchFilterPanel(
          controller: TextEditingController(),
          onSearch: (_) {},
          hintText: 'Search customers',
        ),
        toolbar: WorkspaceToolbar(
          onAction: (_) {},
          isEnabled: (_) => true,
          actions: const [
            ToolbarAction.newItem,
            ToolbarAction.edit,
            ToolbarAction.refresh,
          ],
        ),
        filterPanel: FilterPanel(
          activeFilterCount: 1,
          children: const [
            SizedBox(
              width: 220,
              child: TextField(
                key: ValueKey('city-filter'),
                decoration: InputDecoration(labelText: 'City'),
              ),
            ),
          ],
          onApply: () {},
          onClear: () {},
        ),
        primaryContent: const SizedBox.expand(key: _grid),
        statusBar: const WorkspaceStatusBar(total: 1, selected: false),
      ),
    );

Future<double> _gridTop(
  WidgetTester tester, {
  required bool phase2,
  bool withTabs = false,
}) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final Widget page = _customersShapedPage(withTabs: withTabs);
  await tester.pumpWidget(MaterialApp(
    theme: ThemeRegistry.themeFor(
      palette: AppPalette.neutral,
      brightness: Brightness.light,
    ),
    home: Scaffold(body: phase2 ? Phase2Scope(child: page) : page),
  ));
  await tester.pump();
  expect(tester.takeException(), isNull);
  return tester.getTopLeft(find.byKey(_grid)).dy;
}

void main() {
  testWidgets('phase 2 starts the grid at least 100 px higher than phase 1',
      (tester) async {
    final double phase1 = await _gridTop(tester, phase2: false);
    final double phase2 = await _gridTop(tester, phase2: true);
    debugPrint('grid starts at ${phase1.toStringAsFixed(0)} px in phase 1, '
        '${phase2.toStringAsFixed(0)} px in phase 2');
    expect(phase2, lessThan(100),
        reason: 'one line of title and one of search and actions: the grid '
            'started at ${phase2.toStringAsFixed(0)} px');
    expect(phase1 - phase2, greaterThan(100),
        reason: 'phase 1 ${phase1.toStringAsFixed(0)} px, '
            'phase 2 ${phase2.toStringAsFixed(0)} px');
  });

  testWidgets('a screen with tabs keeps them on the title line',
      (tester) async {
    final double without = await _gridTop(tester, phase2: true);
    final double withTabs = await _gridTop(tester, phase2: true, withTabs: true);
    // Beside the title, not on a row of their own: the page grows only by
    // how much taller a tab button is than the title text.
    expect(
      (tester.getCenter(find.text('Groups')).dy -
              tester.getCenter(find.text('Customer Management')).dy)
          .abs(),
      lessThan(4),
    );
    expect(withTabs - without, lessThanOrEqualTo(16));
  });

  testWidgets('the breadcrumb goes and the description moves behind (i)',
      (tester) async {
    await _gridTop(tester, phase2: true);
    expect(find.text('Masters'), findsNothing);
    expect(
      find.text('Manage firm-scoped customer masters, credit and groups.'),
      findsNothing,
    );
    expect(
      find.byTooltip('Manage firm-scoped customer masters, credit and groups.'),
      findsOneWidget,
    );
  });

  testWidgets('filters open beside the grid and never push it down',
      (tester) async {
    final double before = await _gridTop(tester, phase2: true);
    expect(find.byKey(const ValueKey('city-filter')), findsNothing);
    // The active count is on the button, so a filtered list says so.
    expect(find.text('Filters (1)'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('phase2-filters')));
    await tester.pump();
    expect(find.byKey(const ValueKey('city-filter')), findsOneWidget);
    expect(tester.getTopLeft(find.byKey(_grid)).dy, before);
    // Beside it: the panel starts to the right of where the grid ends.
    expect(
      tester.getTopLeft(find.byKey(const ValueKey('city-filter'))).dx,
      greaterThan(tester.getTopRight(find.byKey(_grid)).dx),
    );
    expect(tester.takeException(), isNull);

    await tester.tap(find.byTooltip('Close filters'));
    await tester.pump();
    expect(find.byKey(const ValueKey('city-filter')), findsNothing);
  });

  testWidgets('a summary figure is a one-line counter, not a card',
      (tester) async {
    Future<Size> sizeOf({required bool phase2}) async {
      const Widget card = SummaryMetricCard(
        key: ValueKey('metric'),
        label: 'Open orders',
        value: '12',
        icon: Icons.receipt_long_outlined,
      );
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: Align(
            alignment: Alignment.topLeft,
            child: phase2 ? const Phase2Scope(child: card) : card,
          ),
        ),
      ));
      return tester.getSize(find.byKey(const ValueKey('metric')));
    }

    final Size card = await sizeOf(phase2: false);
    final Size counter = await sizeOf(phase2: true);
    expect(counter.height, lessThan(36));
    expect(card.height - counter.height, greaterThan(40));
    expect(find.text('Open orders'), findsOneWidget);
    expect(find.text('12'), findsOneWidget);
  });

  testWidgets('phase 1 draws exactly what it drew before', (tester) async {
    await _gridTop(tester, phase2: false);
    expect(find.text('Masters'), findsOneWidget);
    // The breadcrumb's last item and the title.
    expect(find.text('Customer Management'), findsNWidgets(2));
    expect(
      find.text('Manage firm-scoped customer masters, credit and groups.'),
      findsOneWidget,
    );
    expect(find.byType(ExpansionTile), findsOneWidget);
    expect(find.byKey(const ValueKey('phase2-filters')), findsNothing);
  });

  group('a document list with summary figures (Sales Orders)', () {
    Future<List<String>> pumpOrders(
      WidgetTester tester, {
      required bool phase2,
    }) async {
      tester.view.physicalSize = const Size(1366, 768);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      final List<String> tapped = [];
      final Widget page = EnterpriseWorkspace(
        title: 'Sales Orders',
        description: 'Manage customer sales orders.',
        breadcrumbs: const ['Workspace', 'Sales Orders'],
        content: Column(children: [
          Padding(
            // As the six document screens now do.
            padding: phase2
                ? EdgeInsets.zero
                : const EdgeInsets.fromLTRB(24, 0, 24, 12),
            child: SummaryCards(children: [
              for (final String label in ['Total', 'Draft', 'Approved'])
                SummaryCount(
                  key: ValueKey('count-$label'),
                  label: label,
                  value: '${label.length}',
                  onTap: () => tapped.add(label),
                ),
            ]),
          ),
          Expanded(
            child: ManagementWorkspaceLayout(
              searchPanel: SearchFilterPanel(
                controller: TextEditingController(),
                onSearch: (_) {},
                hintText: 'Search orders',
              ),
              toolbar: WorkspaceToolbar(
                onAction: (_) {},
                isEnabled: (_) => true,
                actions: const [ToolbarAction.newItem, ToolbarAction.refresh],
              ),
              primaryContent: const SizedBox.expand(key: _grid),
              statusBar: const WorkspaceStatusBar(total: 3, selected: false),
            ),
          ),
        ]),
      );
      await tester.pumpWidget(MaterialApp(
        theme: ThemeRegistry.themeFor(
          palette: AppPalette.neutral,
          brightness: Brightness.light,
        ),
        home: phase2 ? Phase2Scope(child: page) : page,
      ));
      // The figures and the claim reach the line a frame after the build.
      await tester.pump();
      await tester.pump();
      expect(tester.takeException(), isNull);
      return tapped;
    }

    testWidgets('title, figures, search and actions share one line',
        (tester) async {
      await pumpOrders(tester, phase2: true);
      final double line = tester.getCenter(find.text('Sales Orders')).dy;
      for (final Finder part in [
        find.byKey(const ValueKey('count-Draft')),
        find.byType(TextField),
        find.text('New'),
      ]) {
        expect((tester.getCenter(part).dy - line).abs(), lessThan(6),
            reason: '$part is not on the title line');
      }
      // Drawn once, on the line -- not also as a title band above it.
      expect(find.text('Sales Orders'), findsOneWidget);
      expect(find.byType(Card), findsNothing);
      final double top = tester.getTopLeft(find.byKey(_grid)).dy;
      debugPrint('Sales Orders grid starts at ${top.toStringAsFixed(0)} px');
      expect(top, lessThan(64));
    });

    testWidgets('a figure is a filter: clicking it chooses what it counts',
        (tester) async {
      final List<String> tapped = await pumpOrders(tester, phase2: true);
      await tester.tap(find.byKey(const ValueKey('count-Draft')));
      expect(tapped, ['Draft']);
    });

    testWidgets('phase 1 keeps its title band and its cards', (tester) async {
      await pumpOrders(tester, phase2: false);
      expect(find.byType(Card), findsNWidgets(3));
      expect(find.text('Manage customer sales orders.'), findsOneWidget);
      expect(tester.getTopLeft(find.byKey(_grid)).dy, greaterThan(200));
    });
  });

  testWidgets('a page with no list keeps a compact title line with its figures',
      (tester) async {
    await tester.pumpWidget(MaterialApp(
      home: Phase2Scope(
        child: ModuleWorkspaceFrame(
          title: 'Stock Summary',
          description: 'Balances by location.',
          child: const Column(children: [
            SummaryCards(children: [
              SummaryCount(
                  key: ValueKey('count-low'), label: 'Low stock', value: '4'),
            ]),
            Expanded(child: SizedBox.expand(key: _grid)),
          ]),
        ),
      ),
    ));
    await tester.pump();
    await tester.pump();
    expect(
      (tester.getCenter(find.byKey(const ValueKey('count-low'))).dy -
              tester.getCenter(find.text('Stock Summary')).dy)
          .abs(),
      lessThan(6),
    );
    expect(tester.takeException(), isNull);
  });

  testWidgets("a list's status goes into the window's one bottom bar",
      (tester) async {
    final ValueNotifier<Widget?> left = ValueNotifier(null);
    addTearDown(left.dispose);
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Phase2Scope(
          child: Phase2StatusScope(
            left: left,
            alive: () => true,
            child: const Column(children: [
              Expanded(child: SizedBox.expand(key: _grid)),
              WorkspaceStatusBar(total: 12, selected: true, selectedCount: 1),
            ]),
          ),
        ),
      ),
    ));
    await tester.pump();
    // Nothing drawn here: no second bar above the window's.
    expect(find.text('12 records'), findsNothing);
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: left.value!)));
    expect(find.text('12 records'), findsOneWidget);
    expect(find.text('1 selected'), findsOneWidget);
  });
}
