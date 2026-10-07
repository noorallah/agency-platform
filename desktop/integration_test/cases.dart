import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'harness.dart';

// Helpers for the screen case book (docs/qa/SCREEN_TEST_CASES_BUY_SELL_PRICE.md):
// refusals judged by the book's N1/N2/N3, what a role is offered, and the
// second user of a two-user case, who works over HTTP with their own token.

/// The part of the sign-in address after the last dot ("tradeadmin", "qsexe").
final String itHandle = itEmail.split('@').first.split('.').last;

/// The firm's password for the fixture users.
const String fixturePassword = 'Fixture@2026pw';

/// Sign in over HTTP as one of the fixture firm's users ("qsmgr", ...).
Future<Server> asUser(String handle) =>
    Server.connectAs('t10069cwy.$handle@fixtures.local', fixturePassword);

/// Retire the offers a flow raised in this run: every promotion still in
/// force (or in draft) whose code carries the run's own [stamp]. An offer left
/// active discounts every later sale of the fixture firm, and they stack.
Future<int> retireOffersOf(Server admin, String stamp) async {
  final dynamic rows = await admin.get('/api/v1/promotions?page_size=100');
  int retired = 0;
  for (final dynamic row in rows as List<dynamic>) {
    final Json offer = row as Json;
    if (!'${offer['code']}'.endsWith(stamp)) continue;
    if (offer['status'] != 'ACTIVE' && offer['status'] != 'DRAFT') continue;
    final ({int status, String text}) r = await admin.attempt(
        'DELETE', '/api/v1/promotions/${offer['id']}', null);
    if (r.status < 400) retired++;
  }
  return retired;
}

/// Number of records a collection holds, as the server counts them.
Future<int> totalOf(Server server, String collection) =>
    server.total('/api/v1/$collection');

final RegExp _refusalWords = RegExp(
    r'must|need|choose|required|select|pick|add a|cannot|can.t|not |refus|'
    r'invalid|already|exceed|more than|before|after|enter|insufficient|only|'
    r'greater|least|missing|changed|reload|permission|check|marked',
    caseSensitive: false);

/// Judge a refusal the way the book's N1 to N3 do and return what the screen
/// said. [press] makes the attempt; [openKey] is a key that exists only while
/// the editor (or dialog) is open; [typed] is text that must still be on
/// screen afterwards. Throws a [StateError] naming each of N1/N2/N3 that fails.
Future<String> expectRefusal(
  WidgetTester tester,
  Server server, {
  required String collection,
  required String openKey,
  required Future<void> Function() press,
  String? typed,
  String? known,
  bool allowStale = false,
  Duration wait = const Duration(seconds: 4),
}) async {
  final int before = await totalOf(server, collection);
  final Set<String> beforeText = textOnScreen(tester).toSet();
  await press();
  await pumpFor(tester, wait);
  final bool open =
      find.byKey(ValueKey<String>(openKey)).evaluate().isNotEmpty;
  final String notice = noticeText(tester);
  final List<String> said = <String>[
    if (notice.isNotEmpty) notice,
    ...textOnScreen(tester).where((String t) =>
        t.length < 200 &&
        (allowStale || !beforeText.contains(t)) &&
        _refusalWords.hasMatch(t)),
  ];
  final int after = await totalOf(server, collection);
  final String saw = 'open=$open, saved=${after - before}, '
      'said="${said.take(3).join(' | ')}"';
  final List<String> faults = <String>[
    if (said.isEmpty) 'N1: nothing on screen says why',
    if (!open) 'N2: the editor closed',
    if (open && typed != null && !screenHasTyped(tester, typed))
      'N2: typed "$typed" is gone',
    if (after != before) 'N3: ${after - before} record(s) saved',
  ];
  if (faults.isNotEmpty) {
    throw StateError('${faults.join('; ')} [$saw]'
        '${known == null ? '' : ' (known $known)'}');
  }
  return saw;
}

/// "absent", "disabled" or "enabled" for the button labelled [label].
String buttonState(WidgetTester tester, String label) {
  final Finder f = find.ancestor(
      of: find.text(label),
      matching: find.byWidgetPredicate((Widget w) => w is ButtonStyleButton));
  if (f.evaluate().isEmpty) return 'absent';
  final bool on = f
      .evaluate()
      .any((Element e) => (e.widget as ButtonStyleButton).onPressed != null);
  return on ? 'enabled' : 'disabled';
}

/// The menu areas the signed-in user is offered, with the items under each
/// (including the "all screens" ones).
Future<Map<String, List<String>>> offeredMenu(WidgetTester tester) async {
  await closeOpenEditor(tester);
  final Finder areaKeys = find.byWidgetPredicate((Widget w) {
    final Key? k = w.key;
    return k is ValueKey<String> &&
        k.value.startsWith('menu-area-') &&
        !<String>['menu-area-current', 'menu-area-more', 'menu-area-home']
            .contains(k.value);
  });
  final List<String> areas = <String>{
    for (final Element e in areaKeys.evaluate())
      (e.widget.key! as ValueKey<String>).value.substring(10),
  }.toList();
  final Map<String, List<String>> out = <String, List<String>>{};
  for (final String area in areas) {
    if (area == 'settings') continue;
    await tester.tap(find.byKey(ValueKey<String>('menu-area-$area')));
    await pumpFor(tester, const Duration(milliseconds: 600));
    final Finder showAll = find.byKey(const ValueKey<String>('menu-show-all'));
    if (showAll.evaluate().isNotEmpty) {
      await tester.tap(showAll);
      await pumpFor(tester, const Duration(milliseconds: 600));
    }
    out[area] = <String>[
      for (final Element e in find
          .byWidgetPredicate((Widget w) {
            final Key? k = w.key;
            return k is ValueKey<String> && k.value.startsWith('menu-item-');
          })
          .evaluate())
        (e.widget.key! as ValueKey<String>).value.substring(10),
    ];
    await tester.sendKeyEvent(LogicalKeyboardKey.escape);
    await pumpFor(tester, const Duration(milliseconds: 400));
  }
  return out;
}

/// Whether the signed-in user's menu offers [path] anywhere.
bool menuHas(Map<String, List<String>> menu, String path) =>
    menu.values.any((List<String> items) => items.contains(path));

/// A draft sales order raised over HTTP by [server]'s user, copying the
/// customer, branch, warehouse and product of the newest order the firm has.
Future<Json> apiDraftOrder(Server server, {num quantity = 1}) async {
  final Json? seed = await server.newest('sales-orders');
  if (seed == null) throw StateError('no order to copy the masters from');
  final Json full = await server.one('sales-orders', '${seed['id']}');
  final String today = DateTime.now().toIso8601String().substring(0, 10);
  final Json first = (full['lines'] as List<dynamic>).first as Json;
  return (await server.write('POST', '/api/v1/sales-orders', <String, dynamic>{
    'customer_id': full['customer_id'],
    'branch_id': full['branch_id'],
    'warehouse_id': full['warehouse_id'],
    'order_date': today,
    'lines': <Json>[
      <String, dynamic>{
        'line_number': 1,
        'product_id': first['product_id'],
        'quantity': quantity,
      },
    ],
  })) as Json;
}

/// POST a lifecycle action (approve, hold, cancel...) over HTTP.
Future<Json> apiAct(Server server, String collection, String id, String action,
        [Json? body]) async =>
    (await server.write('POST', '/api/v1/$collection/$id/$action',
        body ?? <String, dynamic>{})) as Json;

/// Select the grid row showing [number], then press the toolbar button
/// [label] and give the screen a moment to answer.
Future<void> rowThen(WidgetTester tester, String number, String label) async {
  await selectRow(tester, number);
  await tapButton(tester, label);
  await pumpFor(tester, const Duration(seconds: 2));
}

/// Press Refresh on a list, if the screen has one.
Future<void> refreshList(WidgetTester tester) async {
  final Finder refresh = find.byTooltip('Refresh');
  if (refresh.evaluate().isNotEmpty) {
    await tester.tap(refresh.first);
  } else if (buttonState(tester, 'Refresh') == 'enabled') {
    await tapButton(tester, 'Refresh');
  }
  await pumpFor(tester, const Duration(seconds: 2));
}

/// Errors the app itself throws while a flow runs (an unmounted State used
/// after an await, say). The test framework would end the run on the first;
/// a flow wants them counted and printed as `FLOW: APPERROR`, then carried on.
final List<String> appErrors = <String>[];

/// Route Flutter's error reports to [appErrors] instead of failing the run.
void collectAppErrors() {
  FlutterError.onError = (FlutterErrorDetails details) {
    final String text = '${details.exception}'.split('\n').first;
    final String where = '${details.stack}'
        .split('\n')
        .where((String l) => l.contains('package:agency_desktop'))
        .take(2)
        .join(' <- ');
    appErrors.add('$text @ $where');
    // ignore: avoid_print
    print('FLOW: APPERROR ${text.length > 200 ? text.substring(0, 200) : text}'
        ' @ $where');
  };
}

/// True when [needle] is on screen as text or typed into / chosen in a box.
bool screenHasTyped(WidgetTester tester, String needle) =>
    screenHas(tester, needle) ||
    tester
        .widgetList<EditableText>(find.byType(EditableText))
        .any((EditableText e) => e.controller.text.contains(needle));

/// The text of an alert dialog that is open (its title and message), or ''.
String dialogText(WidgetTester tester) => <String>[
      for (final Text t in tester.widgetList<Text>(find.descendant(
          of: find.byType(AlertDialog), matching: find.byType(Text))))
        t.data ?? '',
    ].where((String t) => t.isNotEmpty).join(' | ');

/// What is typed in the boxes inside the widget with [key].
String boxesIn(WidgetTester tester, String key) => <String>[
      for (final EditableText e in tester.widgetList<EditableText>(find
          .descendant(
              of: find.byKey(ValueKey<String>(key)),
              matching: find.byType(EditableText))))
        e.controller.text,
    ].join(' / ');

/// Row texts: every Text whose vertical middle is level with the one showing
/// [needle], left to right (a grid row, however the grid builds it).
List<String> rowOf(WidgetTester tester, String needle) {
  final Finder anchor = find.textContaining(needle);
  if (anchor.evaluate().isEmpty) return <String>[];
  final double y = tester.getCenter(anchor.first).dy;
  final List<MapEntry<double, String>> found = <MapEntry<double, String>>[];
  for (final Element e in find.byType(Text).evaluate()) {
    final Text t = e.widget as Text;
    final String data = (t.data ?? '').trim();
    if (data.isEmpty) continue;
    final RenderObject? box = e.renderObject;
    if (box is! RenderBox || !box.attached) continue;
    final Offset c = box.localToGlobal(box.size.center(Offset.zero));
    if ((c.dy - y).abs() < 6) found.add(MapEntry<double, String>(c.dx, data));
  }
  found.sort((MapEntry<double, String> a, MapEntry<double, String> b) =>
      a.key.compareTo(b.key));
  return <String>[for (final MapEntry<double, String> m in found) m.value];
}

/// After pressing a button: watch for [seconds], confirming one confirmation
/// dialog if it appears (when [confirm]), and return every notice or dialog
/// text seen, joined. A snackbar lives about four seconds, so reading it after
/// a fixed wait finds nothing.
Future<String> watch(WidgetTester tester,
    {int seconds = 6, bool confirm = true}) async {
  final Set<String> seen = <String>{};
  bool confirmed = false;
  final DateTime end = DateTime.now().add(Duration(seconds: seconds));
  while (DateTime.now().isBefore(end)) {
    await tester.pump(const Duration(milliseconds: 200));
    final String n = noticeText(tester);
    if (n.isNotEmpty) seen.add(n);
    if (confirm && !confirmed && find.byType(Dialog).evaluate().isNotEmpty) {
      confirmed = await confirmIfAsked(tester);
    }
  }
  return seen.join(' || ');
}

/// Tap the filled or text button labelled [label] inside the open dialog.
Future<void> tapDialogButton(WidgetTester tester, String label) async {
  final Finder dialog = find.byType(Dialog);
  await pumpUntil(tester, dialog, waitingFor: 'a dialog');
  final Finder b = find.descendant(
      of: dialog.last,
      matching: find.ancestor(
          of: find.text(label),
          matching:
              find.byWidgetPredicate((Widget w) => w is ButtonStyleButton)));
  await pumpUntil(tester, b, waitingFor: 'dialog button $label');
  await tester.tap(b.first);
  await pumpFor(tester, const Duration(milliseconds: 800));
}

/// Put stock on the shelf (an adjustment over HTTP) until the first product
/// the firm holds has at least [wanted] available. Dispatch needs real stock,
/// and every run of the flows dispatches some.
Future<void> topUpStock(Server server, {num wanted = 300}) async {
  final dynamic rows = await server.get('/api/v1/inventory?page_size=1');
  final Json row = (rows as List<dynamic>).first as Json;
  final double available = num2(row['available_quantity']);
  if (available >= wanted) return;
  await server.write('POST', '/api/v1/inventory/adjustments', <String, dynamic>{
    'branch_id': row['branch_id'],
    'warehouse_id': row['warehouse_id'],
    'product_id': row['product_id'],
    'quantity': (wanted - available).ceil(),
    'transaction_date': DateTime.now().toIso8601String().substring(0, 10),
    'remarks': 'screen cases: stock for dispatch',
  });
}

/// Pick the entry showing [label] from a filtering dropdown whose key is
/// [key]: type the label into its box first, so the entry is built whatever
/// the length of the list.
Future<void> chooseFiltered(
    WidgetTester tester, String key, String label) async {
  await tapKey(tester, key);
  final Finder box = find.descendant(
      of: find.byKey(ValueKey<String>(key)),
      matching: find.byType(EditableText));
  if (box.evaluate().isNotEmpty) {
    await tester.enterText(box.first, label);
    await pumpFor(tester, const Duration(milliseconds: 600));
  }
  final Finder entry = find.textContaining(label);
  await pumpUntil(tester, entry, waitingFor: 'picker entry "$label"');
  await tester.tap(entry.last);
  await pumpFor(tester, const Duration(milliseconds: 600));
}

/// Press a toolbar command that lives under the "…" menu of a phase 2 list.
Future<void> tapMore(WidgetTester tester, String label) async {
  final Finder more = find.text('…');
  await pumpUntil(tester, more, waitingFor: 'the … menu');
  await tester.tap(more.first);
  await pumpFor(tester, const Duration(milliseconds: 600));
  final Finder item = find.text(label);
  await pumpUntil(tester, item, waitingFor: 'menu entry "$label"');
  await tester.tap(item.last);
  await pumpFor(tester, const Duration(milliseconds: 800));
}

/// "enabled", "disabled" or "absent" for the entry [label] in the "…" menu.
Future<String> moreState(WidgetTester tester, String label) async {
  final Finder more = find.text('…');
  if (more.evaluate().isEmpty) return 'absent';
  await tester.tap(more.first);
  await pumpFor(tester, const Duration(milliseconds: 600));
  String state = 'absent';
  final Finder item = find.text(label);
  if (item.evaluate().isNotEmpty) {
    final Finder tile = find.ancestor(
        of: item.last,
        matching: find.byWidgetPredicate(
            (Widget w) => w is MenuItemButton || w is PopupMenuItem));
    if (tile.evaluate().isEmpty) {
      state = 'enabled';
    } else {
      final Widget w = tile.evaluate().first.widget;
      final bool on = w is MenuItemButton
          ? w.onPressed != null
          : (w as PopupMenuItem<dynamic>).enabled;
      state = on ? 'enabled' : 'disabled';
    }
  }
  await tester.sendKeyEvent(LogicalKeyboardKey.escape);
  await pumpFor(tester, const Duration(milliseconds: 400));
  return state;
}
