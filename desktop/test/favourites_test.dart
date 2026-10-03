import 'package:agency_desktop/core/theme/theme_manager.dart';
import 'package:agency_desktop/phase2/app_menu_bar.dart';
import 'package:agency_desktop/phase2/command_box.dart';
import 'package:agency_desktop/phase2/favourites.dart';
import 'package:agency_desktop/phase2/home_page.dart';
import 'package:agency_desktop/phase2/menu_layout.dart';
import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Favourites (D-UI-3, UI_PHASE_2_DESIGN.md 4.3, the branding wireframe's
/// step 7): the star in a drop-down, Home's FAVOURITES box and the top of
/// Ctrl+K, all one list kept in the user's server preferences -- and saved
/// in one request however many stars are clicked in a row (owner, 10-04).

/// A Home with nothing to fetch: every figure reads as empty.
class _QuietSource implements HomeSource {
  @override
  Future<List<Map<String, dynamic>>> invoiceRegister(
          DateTime from, DateTime to) async =>
      const [];
  @override
  Future<List<Map<String, dynamic>>> customerOutstanding() async => const [];
  @override
  Future<int> itemsBelowReorder() async => 0;
  @override
  Future<double> receiptsOn(DateTime day) async => 0;
  @override
  Future<int> batchesExpiringIn30Days() async => 0;
  @override
  Future<int> expiringLicences() async => 0;
  @override
  Future<Map<String, dynamic>> stockAlerts() async => const {};
  @override
  Future<List<Map<String, dynamic>>> taxCalendar() async => const [];
  @override
  Future<void> markGstReturnFiled(Map<String, dynamic> body) async {}
  @override
  Future<void> withdrawGstReturnFiling(String id) async {}
  @override
  Future<Map<String, dynamic>> summary(String path) async => const {};
}

/// Screens a Home can show with no figures behind them.
const Set<String> _allowed = {
  'quotations',
  'masters/customers',
  'masters/products',
  'accounting/payments',
  'masters/customer-statements',
};

/// What reached the server, one list per save.
class _Saves {
  final List<List<String>> calls = [];
  Future<void> call(List<String> paths) async => calls.add(paths);
}

Favourites _favourites(_Saves saves, {List<String>? stored}) => Favourites(
      stored: stored,
      defaults: Phase2HomePage.screens,
      save: saves.call,
    );

Widget _app(Widget body) => MaterialApp(
      theme: ThemeRegistry.themeFor(
        palette: AppPalette.neutral,
        brightness: Brightness.light,
      ),
      home: Scaffold(body: body),
    );

Future<List<String>> _pumpHome(
    WidgetTester tester, Favourites favourites) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final List<String> opened = [];
  await tester.pumpWidget(_app(Phase2HomePage(
    firmName: 'QA01 Traders',
    userName: 'Owner',
    today: DateTime.utc(2026, 10, 4),
    allowed: _allowed.contains,
    source: _QuietSource(),
    onOpen: (item) => opened.add(item.path),
    favourites: favourites,
  )));
  await tester.pump();
  return opened;
}

/// Point at [target] with the test's one mouse, adding it the first time.
Future<void> _hover(WidgetTester tester, Finder target) async {
  TestGesture? mouse = _mouse;
  if (mouse == null) {
    mouse = _mouse =
        await tester.createGesture(kind: PointerDeviceKind.mouse);
    await mouse.addPointer(location: Offset.zero);
    addTearDown(() async {
      await _mouse?.removePointer();
      _mouse = null;
    });
  }
  await mouse.moveTo(tester.getCenter(target));
  await tester.pump();
}

TestGesture? _mouse;

List<String> _homeOrder(WidgetTester tester) => [
      for (final Element box
          in find.byWidgetPredicate((widget) {
        final Key? key = widget.key;
        return key is ValueKey<String> &&
            key.value.startsWith('home-open-');
      }).evaluate())
        (box.widget.key! as ValueKey<String>)
            .value
            .substring('home-open-'.length),
    ];

void main() {
  group('the list', () {
    test('somebody who never chose starts with the common screens', () {
      expect(Favourites.read(const {}), isNull);
      expect(Favourites.read(null), isNull);
      final Favourites favourites = _favourites(_Saves());
      expect(favourites.paths, Phase2HomePage.screens);
      favourites.dispose();
    });

    test('an emptied list stays empty rather than refilling', () {
      expect(Favourites.read(const {'favourites': <String>[]}), isEmpty);
      final Favourites favourites = _favourites(_Saves(), stored: const []);
      expect(favourites.paths, isEmpty);
      favourites.dispose();
    });

    test('dropping a box on another takes its place', () {
      final Favourites favourites =
          _favourites(_Saves(), stored: const ['a', 'b', 'c', 'd']);
      favourites.move('a', 'c');
      expect(favourites.paths, ['b', 'c', 'a', 'd']);
      favourites.move('d', 'b');
      expect(favourites.paths, ['d', 'b', 'c', 'a']);
      favourites.move('d', 'missing');
      expect(favourites.paths, ['d', 'b', 'c', 'a']);
      favourites.dispose();
    });

    testWidgets('a run of changes is one request, with the final list',
        (tester) async {
      final _Saves saves = _Saves();
      final Favourites favourites = _favourites(saves, stored: const ['a']);
      favourites
        ..toggle('b')
        ..toggle('c')
        ..remove('a')
        ..move('c', 'b');
      expect(saves.calls, isEmpty);
      await tester.pump(const Duration(milliseconds: 500));
      favourites.toggle('d');
      await tester.pump(const Duration(milliseconds: 500));
      expect(saves.calls, isEmpty, reason: 'still within the pause');
      await tester.pump(const Duration(milliseconds: 400));
      expect(saves.calls, [
        ['c', 'b', 'd'],
      ]);
      favourites.dispose();
      expect(saves.calls, hasLength(1), reason: 'nothing left to save');
    });

    testWidgets('a change still waiting is saved when the window closes',
        (tester) async {
      final _Saves saves = _Saves();
      final Favourites favourites = _favourites(saves, stored: const []);
      favourites.toggle('quotations');
      favourites.dispose();
      expect(saves.calls, [
        ['quotations'],
      ]);
    });
  });

  group('the star in a drop-down', () {
    Future<List<MenuItemSpec>> pumpBar(
        WidgetTester tester, Favourites favourites) async {
      tester.view.physicalSize = const Size(1920, 768);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      final List<MenuItemSpec> opened = [];
      await tester.pumpWidget(_app(Column(children: [
        AppMenuBar(
          areas: MenuLayout.areas,
          settings: MenuLayout.settings,
          currentPath: 'masters/customers',
          onOpen: opened.add,
          onOpenSetUp: (_) {},
          trailing: const [],
          favourites: favourites,
        ),
        const Expanded(child: SizedBox()),
      ])));
      await tester.tap(find.byKey(const ValueKey('menu-area-sell')));
      await tester.pumpAndSettle();
      return opened;
    }

    testWidgets('a favourite is gold; another shows its star when pointed at',
        (tester) async {
      final _Saves saves = _Saves();
      final Favourites favourites =
          _favourites(saves, stored: const ['salesOrders']);
      addTearDown(favourites.dispose);
      await pumpBar(tester, favourites);

      final Finder starred = find.byKey(const ValueKey('menu-star-salesOrders'));
      expect(starred, findsOneWidget);
      expect(
        tester
            .widget<Icon>(
                find.descendant(of: starred, matching: find.byType(Icon)))
            .icon,
        Icons.star,
      );
      const ValueKey<String> quotes = ValueKey('menu-star-quotations');
      expect(find.byKey(quotes), findsNothing);

      await _hover(tester, find.byKey(const ValueKey('menu-item-quotations')));
      expect(find.byKey(quotes), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('clicking stars keeps the panel open and saves once',
        (tester) async {
      final _Saves saves = _Saves();
      final Favourites favourites = _favourites(saves, stored: const []);
      addTearDown(favourites.dispose);
      final List<MenuItemSpec> opened = await pumpBar(tester, favourites);

      for (final String path in [
        'quotations',
        'salesOrders',
        'salesInvoices/sales-invoices',
      ]) {
        await _hover(tester, find.byKey(ValueKey('menu-item-$path')));
        await tester.tap(find.byKey(ValueKey('menu-star-$path')));
        await tester.pump();
      }
      // Unstar one again: the request carries only where it ended.
      await tester.tap(find.byKey(const ValueKey('menu-star-salesOrders')));
      await tester.pump();

      expect(opened, isEmpty, reason: 'a star opens nothing');
      expect(find.byKey(const ValueKey('menu-item-quotations')), findsOneWidget,
          reason: 'the panel stays open');
      expect(favourites.paths, ['quotations', 'salesInvoices/sales-invoices']);
      expect(saves.calls, isEmpty);
      await tester.pump(const Duration(seconds: 1));
      expect(saves.calls, [
        ['quotations', 'salesInvoices/sales-invoices'],
      ]);
    });
  });

  group("Home's FAVOURITES", () {
    testWidgets('shows the starred screens this user may open, in order',
        (tester) async {
      final Favourites favourites = _favourites(_Saves(), stored: const [
        'masters/products',
        'salesInvoices/sales-invoices', // not this user's
        'quotations',
      ]);
      addTearDown(favourites.dispose);
      final List<String> opened = await _pumpHome(tester, favourites);
      expect(_homeOrder(tester), ['masters/products', 'quotations']);
      await tester.tap(find.byKey(const ValueKey('home-open-quotations')));
      expect(opened, ['quotations']);
    });

    testWidgets('x removes one; with none left Home says how to add them',
        (tester) async {
      final _Saves saves = _Saves();
      final Favourites favourites =
          _favourites(saves, stored: const ['quotations']);
      addTearDown(favourites.dispose);
      await _pumpHome(tester, favourites);
      const ValueKey<String> unstar = ValueKey('home-unstar-quotations');
      expect(find.byKey(unstar), findsNothing);
      await _hover(tester, find.byKey(const ValueKey('home-open-quotations')));
      await tester.tap(find.byKey(unstar));
      await tester.pump();
      expect(_homeOrder(tester), isEmpty);
      expect(find.text('FAVOURITES'), findsOneWidget);
      expect(find.byKey(const ValueKey('home-favourites-empty')),
          findsOneWidget);
      await tester.pump(const Duration(seconds: 1));
      expect(saves.calls, [<String>[]]);
    });

    testWidgets('dragging a box onto another reorders them', (tester) async {
      final _Saves saves = _Saves();
      final Favourites favourites = _favourites(saves, stored: const [
        'quotations',
        'masters/customers',
        'masters/products',
      ]);
      addTearDown(favourites.dispose);
      await _pumpHome(tester, favourites);
      final TestGesture drag = await tester.startGesture(
        tester.getCenter(find.byKey(const ValueKey('home-open-quotations'))),
        kind: PointerDeviceKind.mouse,
      );
      await tester.pump();
      await drag.moveTo(tester
          .getCenter(find.byKey(const ValueKey('home-open-masters/products'))));
      await tester.pump();
      await drag.up();
      await tester.pump();
      expect(_homeOrder(tester),
          ['masters/customers', 'masters/products', 'quotations']);
      await tester.pump(const Duration(seconds: 1));
      expect(saves.calls, hasLength(1));
    });
  });

  group('Ctrl+K', () {
    final List<CommandScreen> all = commandScreens(MenuLayout.all);

    test('with nothing typed, favourites lead in their order', () {
      final List<String> top = [
        for (final CommandScreen screen in matchScreens(all, '',
                favourites: const ['masters/products', 'quotations']))
          screen.item.path,
      ];
      expect(top.take(2), ['masters/products', 'quotations']);
      expect(top.where((path) => path == 'quotations'), hasLength(1));
      expect(top, hasLength(all.length));
    });

    test('among equally good matches a favourite comes first', () {
      String first(List<String> favourites) =>
          matchScreens(all, 'statement', favourites: favourites)
              .first
              .item
              .path;
      expect(first(const []), 'masters/customer-statements');
      expect(first(const ['masters/supplier-statements']),
          'masters/supplier-statements');
    });
  });
}
