import 'package:agency_desktop/core/theme/theme_manager.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
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
    final double withTabs =
        await _gridTop(tester, phase2: true, withTabs: true);
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
        find.text('+ New'),
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

  testWidgets('a phase 2 grid fills its width and draws its heading line',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 600);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Phase2Scope(
          child: EnterpriseDataGrid<String>(
            items: const ['a', 'b'],
            total: 2,
            pageOffset: 0,
            columns: const [
              GridColumn(key: 'code', label: 'Code'),
              GridColumn(key: 'amount', label: 'Amount', numeric: true),
            ],
            id: (item) => item,
            cells: (item) => [item, '112050'],
            onSelect: (_) {},
            onPageChanged: (_) {},
          ),
        ),
      ),
    ));
    await tester.pump();
    // A Stack around the table once loosened its width and it shrank to its
    // two columns; the grid is the width it is given.
    expect(tester.getSize(find.byType(DataTable)).width, 1200);
    expect(find.byKey(const ValueKey('grid-heading-line')), findsOneWidget);
    // Amounts in Indian digits.
    expect(find.text('1,12,050'), findsNWidgets(2));
  });

  Future<void> customersGrid(WidgetTester tester, double width) async {
    tester.view.physicalSize = Size(width, 600);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Phase2Scope(
          child: EnterpriseDataGrid<String>(
            items: const ['a'],
            total: 1,
            pageOffset: 0,
            // The wireframe's Customers: GST is p3, Phone p2, Credit limit p3.
            columns: const [
              GridColumn(key: 'code', label: 'Code'),
              GridColumn(key: 'name', label: 'Name'),
              GridColumn(key: 'gst', label: 'GST'),
              GridColumn(key: 'phone', label: 'Phone'),
              GridColumn(key: 'city', label: 'City'),
              GridColumn(key: 'status', label: 'Status'),
              GridColumn(key: 'limit', label: 'Credit limit', numeric: true),
              GridColumn(key: 'balance', label: 'Balance', numeric: true),
            ],
            id: (item) => item,
            cells: (item) => [
              'C-0001',
              'Sri Lakshmi General Stores and Wholesale Traders',
              '33AABCS1234F1Z5',
              '+91 98400 12345',
              'Coimbatore',
              'ON_HOLD',
              '250000.00',
              '112050.00',
            ],
            onSelect: (_) {},
            onPageChanged: (_) {},
          ),
        ),
      ),
    ));
    await tester.pump();
  }

  testWidgets('a status with a note reads as words, the note kept',
      (tester) async {
    tester.view.physicalSize = const Size(1400, 600);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Phase2Scope(
          child: EnterpriseDataGrid<String>(
            items: const ['a'],
            total: 1,
            pageOffset: 0,
            columns: const [
              GridColumn(key: 'number', label: 'Order Number'),
              GridColumn(key: 'status', label: 'Status'),
            ],
            id: (item) => item,
            // How the orders list marks an order on hold.
            cells: (item) => ['SO-1', 'APPROVED (on hold)'],
            onSelect: (_) {},
            onPageChanged: (_) {},
          ),
        ),
      ),
    ));
    await tester.pump();
    expect(find.text('Approved (on hold)'), findsOneWidget);
  });

  testWidgets('a narrow window drops the least important columns first',
      (tester) async {
    await customersGrid(tester, 2400);
    for (final String heading in ['GST', 'Phone', 'Credit limit']) {
      expect(find.text(heading), findsOneWidget, reason: heading);
    }
    // A status reads as words, as the wireframe.
    expect(find.text('On hold'), findsOneWidget);

    await customersGrid(tester, 1100);
    // p3 goes first, then p2; the code, name, status and balance stay.
    expect(find.text('GST'), findsNothing);
    expect(find.text('Credit limit'), findsNothing);
    for (final String heading in [
      'Code',
      'Name',
      'City',
      'Status',
      'Balance'
    ]) {
      expect(find.text(heading), findsOneWidget, reason: heading);
    }
    // Nothing scrolls sideways while dropping columns is enough.
    final ScrollPosition sideways = tester
        .state<ScrollableState>(find
            .descendant(
              of: find.byType(EnterpriseDataGrid<String>),
              matching: find.byType(Scrollable),
            )
            .last)
        .position;
    expect(sideways.maxScrollExtent, 0);
    expect(tester.takeException(), isNull);
  });

  testWidgets('an amount heading with numbers in it is drawn as a figure',
      (tester) async {
    tester.view.physicalSize = const Size(1600, 600);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Phase2Scope(
          child: EnterpriseDataGrid<String>(
            items: const ['a'],
            total: 1,
            pageOffset: 0,
            // None declared numeric, as most document lists never did.
            columns: const [
              GridColumn(key: 'number', label: 'Order Number'),
              GridColumn(key: 'total', label: 'Grand Total'),
              GridColumn(key: 'qty', label: 'Qty'),
              GridColumn(key: 'tax', label: 'Tax System'),
            ],
            id: (item) => item,
            cells: (item) => ['SO-0001', '112050.4128', '876.0000', 'GST'],
            onSelect: (_) {},
            onPageChanged: (_) {},
          ),
        ),
      ),
    ));
    await tester.pump();
    expect(find.text('1,12,050.41'), findsOneWidget);
    expect(find.text('876'), findsOneWidget);
    // A heading that names tax but holds words stays words.
    expect(find.text('GST'), findsOneWidget);
    expect(find.text('SO-0001'), findsOneWidget);
  });

  testWidgets("a screen's own commands fold into ... when the line is short",
      (tester) async {
    Future<void> pumpAt(double width) async {
      tester.view.physicalSize = Size(width, 600);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: Phase2Scope(
            child: ModuleWorkspaceFrame(
              title: 'Sales Orders',
              description: 'Orders',
              child: ManagementWorkspaceLayout(
                searchPanel: SearchFilterPanel(
                  controller: TextEditingController(),
                  onSearch: (_) {},
                ),
                toolbar: WorkspaceToolbar(
                  onAction: (_) {},
                  isEnabled: (_) => true,
                  actions: const [
                    ToolbarAction.view,
                    ToolbarAction.refresh,
                    ToolbarAction.newItem,
                  ],
                  commands: [
                    for (final String step in [
                      'Approve',
                      'Hold',
                      'Cancel',
                      'Close',
                      'Print',
                      'Use points',
                    ])
                      ToolbarCommand(
                        id: step,
                        label: step,
                        icon: Icons.check,
                        onPressed: () {},
                      ),
                    ToolbarCommand(
                      id: 'settings',
                      label: 'Print settings',
                      icon: Icons.tune,
                      menuOnly: true,
                      onPressed: () {},
                    ),
                  ],
                ),
                primaryContent: const SizedBox.expand(),
                statusBar: const WorkspaceStatusBar(total: 0, selected: false),
              ),
            ),
          ),
        ),
      ));
      await tester.pump();
      await tester.pump();
    }

    await pumpAt(3000);
    expect(tester.takeException(), isNull);
    expect(find.byKey(const ValueKey('toolbar-command-Use points')),
        findsOneWidget);
    // Set-up actions are never on the line.
    expect(
        find.byKey(const ValueKey('toolbar-command-settings')), findsNothing);

    await pumpAt(1000);
    // Narrow: nothing overflows, and what did not fit is behind "...".
    expect(tester.takeException(), isNull);
    expect(
        find.byKey(const ValueKey('toolbar-command-Use points')), findsNothing);
    expect(find.byKey(const ValueKey('toolbar-new')), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('toolbar-more')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('toolbar-command-Use points-menu')),
        findsOneWidget);
    expect(find.byKey(const ValueKey('toolbar-command-settings-menu')),
        findsOneWidget);
  });

  testWidgets("a screen's own search and New go on the frame's line",
      (tester) async {
    tester.view.physicalSize = const Size(1366, 768);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Phase2Scope(
          child: ModuleWorkspaceFrame(
            title: 'Quotations',
            description: 'Offers',
            child: LoadingOverlay(
              loading: true,
              child: Column(children: [
                Phase2LineTools(children: [
                  SizedBox(
                    width: 260,
                    child: SearchFilterPanel(
                      controller: TextEditingController(),
                      onSearch: (_) {},
                    ),
                  ),
                  FilledButton(
                    key: const ValueKey('line-new'),
                    onPressed: () {},
                    child: const Text('+ New'),
                  ),
                ]),
                const Expanded(child: SizedBox.expand(key: _grid)),
              ]),
            ),
          ),
        ),
      ),
    ));
    await tester.pump();
    await tester.pump();
    expect(tester.takeException(), isNull);
    // On the title's line, not a second one below it.
    final double title = tester.getCenter(find.text('Quotations')).dy;
    expect(tester.getCenter(find.byKey(const ValueKey('line-new'))).dy,
        closeTo(title, 2));
    expect(tester.getTopLeft(find.byKey(_grid)).dy, lessThan(60));
    // Loading is a thin bar, not a grey sheet over the screen.
    expect(find.byKey(const ValueKey('loading-bar')), findsOneWidget);
    expect(find.byType(CircularProgressIndicator), findsNothing);
  });

  testWidgets("a search's own filters move into the + filter panel",
      (tester) async {
    tester.view.physicalSize = const Size(1366, 768);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Phase2Scope(
          child: ManagementWorkspaceLayout(
            searchPanel: SearchFilterPanel(
              controller: TextEditingController(),
              onSearch: (_) {},
              filters: const [
                SizedBox(
                  width: 180,
                  child: TextField(
                    key: ValueKey('area-filter'),
                    decoration: InputDecoration(labelText: 'Area'),
                  ),
                ),
              ],
            ),
            toolbar: WorkspaceToolbar(
              onAction: (_) {},
              isEnabled: (_) => true,
              actions: const [ToolbarAction.refresh],
            ),
            primaryContent: const SizedBox.expand(key: _grid),
            statusBar: const WorkspaceStatusBar(total: 0, selected: false),
          ),
        ),
      ),
    ));
    await tester.pump();
    expect(find.byKey(const ValueKey('area-filter')), findsNothing);
    expect(tester.getTopLeft(find.byKey(_grid)).dy, lessThan(60));
    await tester.tap(find.byKey(const ValueKey('phase2-filters')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('area-filter')), findsOneWidget);
  });

  testWidgets("a screen's own table fills the width with Indian digits",
      (tester) async {
    tester.view.physicalSize = const Size(1200, 600);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Phase2Scope(
          child: Phase2WideTable(
            table: DataTable(
              columns: const [
                DataColumn(label: Text('Account')),
                DataColumn(label: Text('Closing Dr'), numeric: true),
              ],
              rows: const [
                DataRow(cells: [
                  DataCell(Text('Bank')),
                  DataCell(Text('158117.39')),
                ]),
              ],
            ),
          ),
        ),
      ),
    ));
    await tester.pump();
    expect(tester.getSize(find.byType(DataTable)).width, 1200);
    expect(find.text('1,58,117.39'), findsOneWidget);
    expect(find.text('Bank'), findsOneWidget);
  });

  testWidgets("a screen's own New moves to the end of its buttons",
      (tester) async {
    tester.view.physicalSize = const Size(1600, 600);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Phase2Scope(
          child: ManagementWorkspaceLayout(
            searchPanel: const SizedBox.shrink(),
            toolbar: Wrap(spacing: 8, children: [
              FilledButton(
                key: const ValueKey('own-new'),
                onPressed: () {},
                child: const Text('New price list'),
              ),
              OutlinedButton(
                key: const ValueKey('own-other'),
                onPressed: () {},
                child: const Text('Other'),
              ),
            ]),
            primaryContent: const SizedBox.expand(),
            statusBar: const WorkspaceStatusBar(total: 0, selected: false),
          ),
        ),
      ),
    ));
    await tester.pump();
    expect(
      tester.getTopLeft(find.byKey(const ValueKey('own-new'))).dx,
      greaterThan(
          tester.getTopLeft(find.byKey(const ValueKey('own-other'))).dx),
    );
  });

  testWidgets('own tabs sit small on the title line', (tester) async {
    tester.view.physicalSize = const Size(1200, 600);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Phase2ScreenTitle(
          title: 'Tax Rules',
          child: DefaultTabController(
            length: 2,
            child: Builder(
              builder: (context) => Phase2TabsLine(
                controller: DefaultTabController.of(context),
                labels: const ['Rules', 'Priority Manager'],
              ),
            ),
          ),
        ),
      ),
    ));
    await tester.pump();
    final double title = tester.getCenter(find.text('Tax Rules')).dy;
    expect(
        tester.getCenter(find.text('Priority Manager')).dy, closeTo(title, 3));
  });

  testWidgets('a frame reused for a screen with no list gets its title back',
      (tester) async {
    Widget page(String title, Widget body) => MaterialApp(
          home: Scaffold(
            body: Phase2Scope(
              child: ModuleWorkspaceFrame(
                title: title,
                description: '',
                child: body,
              ),
            ),
          ),
        );
    await tester.pumpWidget(page(
      'Units',
      ManagementWorkspaceLayout(
        searchPanel: const SizedBox.shrink(),
        toolbar: const SizedBox.shrink(),
        primaryContent: const SizedBox.expand(),
        statusBar: const WorkspaceStatusBar(total: 0, selected: false),
      ),
    ));
    await tester.pump();
    await tester.pump();
    // The admin area keeps one frame for all its screens: the next screen
    // has no list, and the line the last one took must come back.
    await tester.pumpWidget(page('Numbering', const Text('series')));
    await tester.pump();
    await tester.pump();
    expect(find.text('Numbering'), findsOneWidget);
  });

  testWidgets('every list answers Ctrl+N, F2, F5, Delete and "/"',
      (tester) async {
    tester.view.physicalSize = const Size(1366, 768);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final List<ToolbarAction> run = [];
    final TextEditingController search = TextEditingController();
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Phase2Scope(
          child: ManagementWorkspaceLayout(
            searchPanel: SearchFilterPanel(
              controller: search,
              onSearch: (_) {},
            ),
            toolbar: WorkspaceToolbar(
              onAction: run.add,
              isEnabled: (action) => action != ToolbarAction.delete,
              actions: const [
                ToolbarAction.edit,
                ToolbarAction.delete,
                ToolbarAction.refresh,
                ToolbarAction.newItem,
              ],
            ),
            primaryContent: const TextField(key: ValueKey('remark')),
            statusBar: const WorkspaceStatusBar(total: 0, selected: false),
          ),
        ),
      ),
    ));
    await tester.pump();

    await tester.sendKeyDownEvent(LogicalKeyboardKey.controlLeft);
    await tester.sendKeyEvent(LogicalKeyboardKey.keyN);
    await tester.sendKeyUpEvent(LogicalKeyboardKey.controlLeft);
    await tester.sendKeyEvent(LogicalKeyboardKey.f2);
    await tester.sendKeyEvent(LogicalKeyboardKey.f5);
    // Disabled on the toolbar, so the key does nothing either.
    await tester.sendKeyEvent(LogicalKeyboardKey.delete);
    expect(run, [
      ToolbarAction.newItem,
      ToolbarAction.edit,
      ToolbarAction.refresh,
    ]);

    // "/" puts the keyboard in the search box...
    await tester.sendKeyEvent(LogicalKeyboardKey.slash, character: '/');
    await tester.pump();
    final EditableText box = tester.widget<EditableText>(find.descendant(
      of: find.byType(SearchFilterPanel),
      matching: find.byType(EditableText),
    ));
    expect(box.focusNode.hasFocus, isTrue);

    // ...but typed into a box it is a slash, and no key runs an action.
    await tester.tap(find.byKey(const ValueKey('remark')));
    await tester.pump();
    run.clear();
    await tester.sendKeyEvent(LogicalKeyboardKey.f5);
    await tester.sendKeyEvent(LogicalKeyboardKey.slash, character: '/');
    await tester.pump();
    expect(run, isEmpty);
    expect(box.focusNode.hasFocus, isFalse);
  });
}
