import 'package:agency_desktop/core/theme/theme_manager.dart';
import 'package:agency_desktop/phase2/home_page.dart';
import 'package:agency_desktop/phase2/menu_layout.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Home in the phase 2 app (UI_PHASE_2_DESIGN.md 4.9).
///
/// The owner's report: "home page missing". Phase 1's Dashboard is a
/// platform administrator's page, so a firm user had no Home. This one is
/// everybody's, and shows only what the user's role may open.
Future<List<String>> _pump(
  WidgetTester tester, {
  required Set<String> allowed,
  Map<String, Map<String, dynamic>> summaries = const {},
  Set<String> failing = const {},
}) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final List<String> opened = [];
  await tester.pumpWidget(MaterialApp(
    theme: ThemeRegistry.themeFor(
      palette: AppPalette.neutral,
      brightness: Brightness.light,
    ),
    home: Scaffold(
      body: Phase2HomePage(
        firmName: 'MarketBridge Wholesale',
        userName: 'Whole Admin',
        allowed: allowed.contains,
        loadSummary: (path) async {
          if (failing.contains(path)) throw StateError('refused');
          return summaries[path] ?? const {};
        },
        onOpen: (item) => opened.add(item.path),
      ),
    ),
  ));
  await tester.pump();
  await tester.pump();
  expect(tester.takeException(), isNull);
  return opened;
}

void main() {
  testWidgets('today shows the figures of the lists the user may open',
      (tester) async {
    await _pump(
      tester,
      allowed: {'salesInvoices/sales-invoices', 'salesOrders'},
      summaries: {
        'salesInvoices/sales-invoices': {
          'overdue_invoices': 3,
          'pending_invoices': 7,
          'draft': 2,
        },
        'salesOrders': {'draft': 4, 'approved': 9},
      },
    );
    expect(find.text('Welcome, Whole Admin'), findsOneWidget);
    expect(find.text('MarketBridge Wholesale'), findsOneWidget);
    expect(find.byKey(const ValueKey('home-tile-salesInvoices/sales-invoices')),
        findsOneWidget);
    expect(find.text('Overdue'), findsOneWidget);
    expect(find.text('7'), findsOneWidget);
    expect(find.text('9'), findsOneWidget);
    // A list the role may not open has no tile, and its summary is never
    // asked for.
    expect(find.byKey(const ValueKey('home-tile-purchaseInvoices')),
        findsNothing);
  });

  testWidgets('an overdue figure above zero is red', (tester) async {
    await _pump(
      tester,
      allowed: {'salesInvoices/sales-invoices'},
      summaries: {
        'salesInvoices/sales-invoices': {
          'overdue_invoices': 3,
          'pending_invoices': 0,
          'draft': 0,
        },
      },
    );
    final BuildContext context = tester.element(find.text('3'));
    expect(tester.widget<Text>(find.text('3')).style?.color,
        Theme.of(context).colorScheme.error);
  });

  testWidgets('a summary that cannot be read shows dashes, not zeros',
      (tester) async {
    await _pump(
      tester,
      allowed: {'salesOrders'},
      failing: {'salesOrders'},
    );
    expect(find.text('-'), findsNWidgets(2));
    expect(find.text('0'), findsNothing);
  });

  testWidgets('a tile and a daily-screen button open their screen',
      (tester) async {
    final List<String> opened = await _pump(
      tester,
      allowed: {'salesOrders', 'masters/customers'},
      summaries: {
        'salesOrders': {'draft': 1, 'approved': 1},
      },
    );
    await tester.tap(find.byKey(const ValueKey('home-tile-salesOrders')));
    await tester
        .tap(find.byKey(const ValueKey('home-open-masters/customers')));
    expect(opened, ['salesOrders', 'masters/customers']);
  });

  testWidgets('with nothing to show, Home says where to go', (tester) async {
    await _pump(tester, allowed: const {});
    expect(find.textContaining('Ctrl+K'), findsOneWidget);
  });

  test('every tile and daily screen is a real menu screen', () {
    for (final String path in [
      for (final HomeTile tile in Phase2HomePage.tiles) tile.path,
      ...Phase2HomePage.daily,
    ]) {
      expect(MenuLayout.itemFor(path), isNotNull, reason: path);
    }
  });
}
