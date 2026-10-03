import 'package:agency_desktop/core/theme/theme_manager.dart';
import 'package:agency_desktop/models/notification_feed.dart';
import 'package:agency_desktop/phase2/app_menu_bar.dart';
import 'package:agency_desktop/phase2/menu_layout.dart';
import 'package:agency_desktop/phase2/notification_bell.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// The bell on the phase 2 bar (PLT-2).
class _FakeFeed {
  _FakeFeed(this.items);

  List<NotificationItem> items;
  int loads = 0;
  bool failing = false;
  final List<List<String>> marked = [];

  Future<NotificationFeed> load() async {
    loads++;
    if (failing) throw StateError('offline');
    return NotificationFeed(
      items: items,
      unread: items.where((item) => !item.read).length,
    );
  }

  Future<void> markRead(List<String> keys) async => marked.add(keys);
}

NotificationItem _item(String key, String kind, {bool read = false}) =>
    NotificationItem(
      key: key,
      kind: kind,
      title: 'Title $key',
      detail: '3 waiting',
      count: 3,
      at: DateTime.now().subtract(const Duration(minutes: 5)),
      read: read,
    );

Future<void> _pump(
  WidgetTester tester,
  _FakeFeed feed, {
  bool enabled = true,
  Object? firmKey = 'firm-1',
  List<NotificationItem>? opened,
  Size size = const Size(1366, 768),
}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    theme: ThemeRegistry.themeFor(
      palette: AppPalette.neutral,
      brightness: Brightness.light,
    ),
    home: Scaffold(
      body: Column(children: [
        AppMenuBar(
          areas: MenuLayout.areas,
          settings: MenuLayout.settings,
          currentPath: 'home',
          onOpen: (_) {},
          onOpenSetUp: (_) {},
          trailing: [
            SearchLauncher(onPressed: () {}),
            NotificationBell(
              enabled: enabled,
              firmKey: firmKey,
              load: feed.load,
              markRead: feed.markRead,
              onOpen: (item) => opened?.add(item),
            ),
          ],
        ),
        const Expanded(child: SizedBox()),
      ]),
    ),
  ));
  await tester.pump();
}

Future<void> _openBell(WidgetTester tester) async {
  await tester.tap(find.byKey(const ValueKey('notification-bell')));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('the badge shows the unread count and hides at zero',
      (tester) async {
    final _FakeFeed feed = _FakeFeed([
      _item('a', 'stock_alert'),
      _item('b', 'message_failed'),
      _item('c', 'stock_alert', read: true),
    ]);
    await _pump(tester, feed);
    expect(find.byKey(const ValueKey('notification-badge')), findsOneWidget);
    expect(find.text('2'), findsOneWidget);

    feed.items = [_item('c', 'stock_alert', read: true)];
    await tester.pump(const Duration(seconds: 60));
    expect(find.byKey(const ValueKey('notification-badge')), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('opening the bell lists the lines, unread ones in bold',
      (tester) async {
    final _FakeFeed feed = _FakeFeed([
      _item('a', 'purchase_order_approval'),
      _item('b', 'stock_alert', read: true),
    ]);
    await _pump(tester, feed);
    await _openBell(tester);
    expect(find.text('Title a'), findsOneWidget);
    expect(find.text('Title b'), findsOneWidget);
    expect(find.textContaining('5 min ago'), findsNWidgets(2));
    final Text unread = tester.widget<Text>(find.text('Title a'));
    final Text read = tester.widget<Text>(find.text('Title b'));
    expect(unread.style?.fontWeight, FontWeight.w700);
    expect(read.style?.fontWeight, FontWeight.w400);
    expect(tester.takeException(), isNull);
  });

  testWidgets('clicking a line marks it read and opens its screen',
      (tester) async {
    final _FakeFeed feed = _FakeFeed([
      _item('po', 'purchase_order_approval'),
      _item('sa', 'stock_alert'),
    ]);
    final List<NotificationItem> opened = [];
    await _pump(tester, feed, opened: opened);
    await _openBell(tester);
    await tester.tap(find.byKey(const ValueKey('notification-po')));
    await tester.pumpAndSettle();
    expect(feed.marked, [
      ['po']
    ]);
    expect(opened.map((item) => item.kind), ['purchase_order_approval']);
    // One fewer unread on the badge at once.
    expect(find.text('1'), findsOneWidget);
  });

  testWidgets('Mark all as read posts every unread key', (tester) async {
    final _FakeFeed feed = _FakeFeed([
      _item('a', 'stock_alert'),
      _item('b', 'message_failed'),
      _item('c', 'stock_alert', read: true),
    ]);
    await _pump(tester, feed);
    await _openBell(tester);
    await tester.tap(find.byKey(const ValueKey('notification-mark-all')));
    await tester.pumpAndSettle();
    expect(feed.marked, [
      ['a', 'b']
    ]);
    expect(find.byKey(const ValueKey('notification-badge')), findsNothing);
  });

  testWidgets('it polls every sixty seconds and keeps the list when one fails',
      (tester) async {
    final _FakeFeed feed = _FakeFeed([_item('a', 'stock_alert')]);
    await _pump(tester, feed);
    expect(feed.loads, 1);
    await tester.pump(const Duration(seconds: 59));
    expect(feed.loads, 1);
    await tester.pump(const Duration(seconds: 1));
    expect(feed.loads, 2);

    feed.failing = true;
    await tester.pump(const Duration(seconds: 60));
    expect(feed.loads, 3);
    expect(find.byKey(const ValueKey('notification-badge')), findsOneWidget);
    expect(tester.takeException(), isNull);

    // Taking the bell down stops the timer.
    await tester.pumpWidget(const SizedBox());
    await tester.pump(const Duration(seconds: 120));
    expect(feed.loads, 3);
  });

  testWidgets('a firm switch refetches at once; no firm asks nothing',
      (tester) async {
    final _FakeFeed none = _FakeFeed([_item('a', 'stock_alert')]);
    await _pump(tester, none, enabled: false, firmKey: null);
    await tester.pump(const Duration(seconds: 120));
    expect(none.loads, 0);
    expect(find.byKey(const ValueKey('notification-bell')), findsNothing);

    final _FakeFeed feed = _FakeFeed([_item('a', 'stock_alert')]);
    await _pump(tester, feed);
    expect(feed.loads, 1);
    await _pump(tester, feed, firmKey: 'firm-2');
    expect(feed.loads, 2);
  });

  testWidgets('the bar stays overflow-free in the 800x600 window',
      (tester) async {
    final _FakeFeed feed = _FakeFeed([
      for (int i = 0; i < 120; i++) _item('k$i', 'stock_alert'),
    ]);
    await _pump(tester, feed, size: const Size(800, 600));
    expect(find.text('99+'), findsOneWidget);
    await _openBell(tester);
    expect(tester.takeException(), isNull);
  });
}
