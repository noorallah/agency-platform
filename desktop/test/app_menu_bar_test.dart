import 'package:agency_desktop/core/theme/theme_manager.dart';
import 'package:agency_desktop/phase2/app_menu_bar.dart';
import 'package:agency_desktop/phase2/menu_layout.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// The phase 2 menu bar (UI_PHASE_2_DESIGN.md 4.1-4.3, 4.11).
Future<List<MenuItemSpec>> _pump(
  WidgetTester tester, {
  double width = 1366,
  List<MenuAreaSpec> areas = MenuLayout.areas,
}) async {
  tester.view.physicalSize = Size(width, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final List<MenuItemSpec> opened = [];
  await tester.pumpWidget(MaterialApp(
    theme: ThemeRegistry.themeFor(
      palette: AppPalette.neutral,
      brightness: Brightness.light,
    ),
    home: Scaffold(
      body: Column(children: [
        AppMenuBar(
          appName: 'Agency',
          areas: areas,
          settings: MenuLayout.settings,
          currentPath: 'masters/customers',
          onOpen: opened.add,
          trailing: [SearchLauncher(onPressed: () {})],
        ),
        const Expanded(child: SizedBox()),
      ]),
    ),
  ));
  return opened;
}

void main() {
  testWidgets('every area is on the bar at 1366 x 768, with no overflow',
      (tester) async {
    await _pump(tester);
    for (final MenuAreaSpec area in MenuLayout.areas) {
      expect(find.byKey(ValueKey('menu-area-${area.id}')), findsOneWidget,
          reason: area.label);
    }
    expect(find.byKey(const ValueKey('menu-area-more')), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('an area drops a panel of every item, and choosing one opens it',
      (tester) async {
    final List<MenuItemSpec> opened = await _pump(tester);
    await tester.tap(find.byKey(const ValueKey('menu-area-sell')));
    await tester.pumpAndSettle();
    // All at once, grouped in columns: no scrolling, nothing to expand.
    for (final MenuItemSpec item in MenuLayout.areas[1].items) {
      expect(find.byKey(ValueKey('menu-item-${item.path}')), findsOneWidget,
          reason: item.label);
    }
    expect(find.text('FIELD SALES'), findsOneWidget);
    await tester.tap(find.text('Sales Orders'));
    await tester.pumpAndSettle();
    expect(opened.single.path, 'salesOrders');
    // The panel closes on a choice.
    expect(find.text('FIELD SALES'), findsNothing);
  });

  testWidgets('Home is one screen, so it opens rather than dropping a panel',
      (tester) async {
    final List<MenuItemSpec> opened = await _pump(tester);
    await tester.tap(find.byKey(const ValueKey('menu-area-home')));
    await tester.pumpAndSettle();
    expect(opened.single.path, 'dashboard');
  });

  testWidgets('the gear holds the settings, by topic', (tester) async {
    final List<MenuItemSpec> opened = await _pump(tester);
    await tester.tap(find.byKey(const ValueKey('menu-area-settings')));
    await tester.pumpAndSettle();
    expect(find.text('BUSINESS PROFILE'), findsOneWidget);
    await tester.tap(find.text('Financial Years'));
    await tester.pumpAndSettle();
    expect(opened.single.path, 'masters/financial-years');
  });

  testWidgets('a narrow window folds the areas that do not fit into More',
      (tester) async {
    await _pump(tester, width: 900);
    expect(find.byKey(const ValueKey('menu-area-more')), findsOneWidget);
    expect(find.byKey(const ValueKey('menu-area-home')), findsOneWidget);
    expect(find.byKey(const ValueKey('menu-area-admin')), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('an area the user may not open is not drawn', (tester) async {
    await _pump(
      tester,
      areas: MenuLayout.areas.where((area) => area.id != 'admin').toList(),
    );
    expect(find.byKey(const ValueKey('menu-area-admin')), findsNothing);
  });

  group('open-screen tabs', () {
    test('opening adds at the end and never twice', () {
      expect(openScreen(['a'], 'b'), ['a', 'b']);
      expect(openScreen(['a', 'b'], 'a'), ['a', 'b']);
    });

    test('past the limit the oldest tab closes', () {
      expect(openScreen(['a', 'b', 'c'], 'd', limit: 3), ['b', 'c', 'd']);
    });

    test('closing the tab on show moves to its right, else its left', () {
      expect(closeScreen(['a', 'b', 'c'], 'b', 'b').next, 'c');
      expect(closeScreen(['a', 'b', 'c'], 'c', 'c').next, 'b');
      expect(closeScreen(['a'], 'a', 'a').next, isNull);
    });

    test('closing a tab in the background leaves the screen alone', () {
      final result = closeScreen(['a', 'b', 'c'], 'a', 'c');
      expect(result.open, ['b', 'c']);
      expect(result.next, isNull);
    });

    testWidgets('tabs show, select and close', (tester) async {
      final List<String> events = [];
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: OpenScreenTabs(
            paths: const ['masters/customers', 'salesOrders'],
            activePath: 'salesOrders',
            labelFor: (path) => MenuLayout.itemFor(path)!.label,
            onSelect: (path) => events.add('select $path'),
            onClose: (path) => events.add('close $path'),
          ),
        ),
      ));
      await tester.tap(find.text('Customers'));
      await tester.tap(find.descendant(
        of: find.byKey(const ValueKey('open-screen-salesOrders')),
        matching: find.byIcon(Icons.close),
      ));
      expect(events, ['select masters/customers', 'close salesOrders']);
    });
  });
}
