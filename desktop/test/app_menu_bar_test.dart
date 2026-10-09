import 'package:agency_desktop/core/theme/theme_manager.dart';
import 'package:agency_desktop/phase2/app_menu_bar.dart';
import 'package:agency_desktop/phase2/menu_layout.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

/// The phase 2 menu bar (UI_PHASE_2_DESIGN.md 4.1-4.3, 4.11).
Future<List<MenuItemSpec>> _pump(
  WidgetTester tester, {
  double width = 1366,
  List<MenuAreaSpec> areas = MenuLayout.areas,
  List<String?>? setUps,
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
          areas: areas,
          settings: MenuLayout.settings,
          currentPath: 'masters/customers',
          onOpen: opened.add,
          onOpenSetUp: (section) => setUps?.add(section),
          trailing: [SearchLauncher(onPressed: () {})],
        ),
        const Expanded(child: SizedBox()),
      ]),
    ),
  ));
  return opened;
}

void main() {
  testWidgets('every area is on the bar on a wide window, with no overflow',
      (tester) async {
    // The bar measures its labels as drawn, and the test font is about
    // twice as wide as Segoe UI; 1920 fits all eight in it. On the laptop's
    // 1366 with the real font they fit too -- checked by rendering the shell.
    await _pump(tester, width: 1920);
    for (final MenuAreaSpec area in MenuLayout.areas) {
      expect(find.byKey(ValueKey('menu-area-${area.id}')), findsOneWidget,
          reason: area.label);
    }
    expect(find.byKey(const ValueKey('menu-area-more')), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('the area you are in is marked as the wireframe draws it',
      (tester) async {
    await _pump(tester);
    // The page on show is Masters > Customers: the Masters pill carries the
    // light-blue bar along its bottom edge, and no other area does.
    expect(
      find.descendant(
        of: find.byKey(const ValueKey('menu-area-masters')),
        matching: find.byKey(const ValueKey('menu-area-current')),
      ),
      findsOneWidget,
    );
    expect(find.byKey(const ValueKey('menu-area-current')), findsOneWidget);
    // A pill, not a block the bar's full height: what is drawn is the
    // button's Material; the button around it keeps a full-height target.
    final Size pill = tester.getSize(find
        .descendant(
          of: find.byKey(const ValueKey('menu-area-sell')),
          matching: find.byType(Material),
        )
        .first);
    expect(pill.height, lessThanOrEqualTo(34));
    expect(pill.height, lessThan(AppMenuBar.height - 8));
  });

  testWidgets('an area drops every screen it has, and choosing one opens it',
      (tester) async {
    // The laptop's 1366: the widest panel must fit it with no overflow.
    final List<MenuItemSpec> opened = await _pump(tester);
    await tester.tap(find.byKey(const ValueKey('menu-area-sell')));
    await tester.pumpAndSettle();
    final MenuAreaSpec sell = MenuLayout.areas[1];
    // The full menu (owner, 2026-10-09): nothing is one click further away.
    for (final MenuItemSpec item in sell.items) {
      expect(find.byKey(ValueKey('menu-item-${item.path}')), findsOneWidget,
          reason: item.label);
    }
    expect(find.text('FIELD SALES'), findsOneWidget);
    // What the light menu had, and the full menu does not need.
    expect(find.byKey(const ValueKey('menu-show-all')), findsNothing);
    expect(find.byKey(const ValueKey('menu-show-daily')), findsNothing);
    expect(find.byKey(const ValueKey('menu-returns-toggle')), findsNothing);
    expect(tester.takeException(), isNull);
    await tester.tap(find.text('Sales Orders'));
    await tester.pumpAndSettle();
    expect(opened.single.path, 'salesOrders');
    // The panel closes on a choice.
    expect(find.text('FIELD SALES'), findsNothing);
  });

  testWidgets('in each group the daily screens come first, above a line',
      (tester) async {
    await _pump(tester, width: 1920);
    await tester.tap(find.byKey(const ValueKey('menu-area-sell')));
    await tester.pumpAndSettle();
    final MenuAreaSpec sell = MenuLayout.areas[1];
    final Set<String> often = sell.dailyPaths;
    // Returns and notes are daily screens too, shown in place.
    expect(often, containsAll(sell.shortList));
    double top(String path) =>
        tester.getTopLeft(find.byKey(ValueKey('menu-item-$path'))).dy;
    for (final MenuGroupSpec group in sell.groups) {
      final List<String> daily = [
        for (final MenuItemSpec item in group.items)
          if (often.contains(item.path)) item.path,
      ];
      final List<String> rest = [
        for (final MenuItemSpec item in group.items)
          if (!often.contains(item.path)) item.path,
      ];
      for (final String first in daily) {
        for (final String later in rest) {
          expect(top(first), lessThan(top(later)),
              reason: '$first stands above $later in ${group.label}');
        }
      }
    }
    // Documents and Money each hold both kinds, so each has its line; a
    // group that is all one kind has none.
    expect(find.byKey(const ValueKey('menu-daily-line')), findsNWidgets(2));
    // A daily screen is drawn heavier than the rest.
    FontWeight? weight(String label) => tester
        .widget<DefaultTextStyle>(find
            .ancestor(
                of: find.text(label), matching: find.byType(DefaultTextStyle))
            .first)
        .style
        .fontWeight;
    expect(weight('Sales Orders'), FontWeight.w600);
    expect(weight('Enquiries'), isNot(FontWeight.w600));
  });

  testWidgets('every area fits the laptop width with its full menu',
      (tester) async {
    await _pump(tester);
    for (final MenuAreaSpec area in MenuLayout.areas) {
      if (area.items.length == 1) continue;
      final Finder button = find.byKey(ValueKey('menu-area-${area.id}'));
      if (button.evaluate().isEmpty) continue; // folded under More
      await tester.tap(button);
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull, reason: area.label);
      await tester.sendKeyEvent(LogicalKeyboardKey.escape);
      await tester.pumpAndSettle();
    }
  });

  testWidgets('each area links to its own sections of Settings',
      (tester) async {
    final List<String?> setUps = [];
    await _pump(tester, width: 1920, setUps: setUps);
    await tester.tap(find.byKey(const ValueKey('menu-area-masters')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('menu-item-masters/vendor-categories')),
        findsNothing);
    expect(find.text('SETTINGS'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('menu-setup-Item lists')));
    await tester.pumpAndSettle();
    expect(setUps, ['Item lists']);
    // Buy and Stock had no link at all before; now each opens its settings.
    await tester.tap(find.byKey(const ValueKey('menu-area-buy')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('menu-setup-Buying')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('menu-area-stock')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('menu-setup-Stock')));
    await tester.pumpAndSettle();
    expect(setUps, ['Item lists', 'Buying', 'Stock']);
    expect(tester.takeException(), isNull);
  });

  testWidgets('Alt+S opens Sell from the keyboard, and Enter opens a screen',
      (tester) async {
    final List<MenuItemSpec> opened = await _pump(tester, width: 1920);
    await tester.sendKeyDownEvent(LogicalKeyboardKey.altLeft);
    await tester.pump();
    await tester.sendKeyEvent(LogicalKeyboardKey.keyS, character: 's');
    await tester.sendKeyUpEvent(LogicalKeyboardKey.altLeft);
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('menu-item-quotations')), findsOneWidget);
    // Down into the panel and Enter on its first item.
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
    await tester.pump(const Duration(milliseconds: 100));
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pumpAndSettle();
    expect(opened.single.path, 'quotations');
  });

  testWidgets('Home is one screen, so it opens rather than dropping a panel',
      (tester) async {
    final List<MenuItemSpec> opened = await _pump(tester);
    await tester.tap(find.byKey(const ValueKey('menu-area-home')));
    await tester.pumpAndSettle();
    expect(opened.single.path, MenuLayout.homeRoute);
  });

  testWidgets('the gear opens the Settings page', (tester) async {
    final List<String?> setUps = [];
    await _pump(tester, setUps: setUps);
    await tester.tap(find.byKey(const ValueKey('menu-area-settings')));
    await tester.pumpAndSettle();
    expect(setUps, [null]);
  });

  testWidgets('a narrow window folds the areas that do not fit into More',
      (tester) async {
    await _pump(tester, width: 900);
    expect(find.byKey(const ValueKey('menu-area-more')), findsOneWidget);
    expect(find.byKey(const ValueKey('menu-area-home')), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('an area the user may not open is not drawn', (tester) async {
    await _pump(
      tester,
      areas: MenuLayout.areas.where((area) => area.id != 'reports').toList(),
    );
    expect(find.byKey(const ValueKey('menu-area-reports')), findsNothing);
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
