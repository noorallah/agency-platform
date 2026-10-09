import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'cases.dart';
import 'harness.dart';

// Goods types, backlog 89 (book: docs/qa/SCREEN_TEST_CASES_GOODS_TYPES.md).
// Run on TEST01 as `t1008nnr7.admin` (every Positive and Negative case), then
// as gtmanager (FM), gtsales (SM) and gtstore (WH) for the Role cases, and as
// the two firms of its own (pharmaadmin, pharmacashier, genericadmin) and the
// platform administrator for what the menu offers.

const String _types = 'products/goods-types';
const String _sets = 'uom-framework/unit-sets';
const String _dialog = 'crud-workspace-dialog-surface';

/// The sections to run (`IT_PART=types,categories`); empty runs them all.
/// A long run on a PC short of memory is cut off, so the book is run in parts.
const String _part = String.fromEnvironment('IT_PART');
bool wants(String section) =>
    _part.isEmpty || _part.split(',').contains(section);

/// Open a menu area's screen. A narrow window folds the last areas under
/// "More", where an area is a submenu named by its label and has no key.
Future<void> openArea(WidgetTester tester, String area, String path) async {
  await leave(tester);
  if (find.byKey(ValueKey<String>('menu-area-$area')).evaluate().isNotEmpty) {
    await openMenu(tester, area, path);
    return;
  }
  await tester.tap(find.byKey(const ValueKey<String>('menu-area-more')));
  await pumpFor(tester, const Duration(milliseconds: 700));
  final Finder folded = find.byWidgetPredicate((Widget w) =>
      w is MenuAcceleratorLabel &&
      w.label.replaceAll('&', '').toLowerCase() == area);
  await pumpUntil(tester, folded, waitingFor: 'the $area area under More');
  await tester.tap(folded.last);
  await pumpFor(tester, const Duration(milliseconds: 700));
  final Finder item = find.byKey(ValueKey<String>('menu-item-$path'));
  final Finder showAll = find.byKey(const ValueKey<String>('menu-show-all'));
  if (item.evaluate().isEmpty && showAll.evaluate().isNotEmpty) {
    await tester.tap(showAll);
    await pumpFor(tester, const Duration(milliseconds: 600));
  }
  await pumpUntil(tester, item, waitingFor: 'menu item $path');
  await tester.tap(item.first);
  await pumpFor(tester, const Duration(seconds: 3));
}

/// Leave whatever is open, answering the generic form's discard question
/// ("Discard changes") as well as the document editors'.
Future<void> leave(WidgetTester tester) async {
  for (int i = 0; i < 3; i++) {
    final Finder discard = find.text('Discard changes');
    if (discard.evaluate().isNotEmpty) {
      await tester.tap(discard.last);
      await pumpFor(tester, const Duration(milliseconds: 800));
    }
    await closeOpenEditor(tester);
    if (find.byType(Dialog).evaluate().isEmpty) return;
  }
}

/// The texts level with the grid row showing [needle]; the row is the last
/// match, because a search box holding the same text comes first.
List<String> gridRow(WidgetTester tester, String needle) {
  final Finder anchor = find.text(needle);
  if (anchor.evaluate().isEmpty) return <String>[];
  final double y = tester.getCenter(anchor.last).dy;
  final List<MapEntry<double, String>> found = <MapEntry<double, String>>[];
  for (final Element e in find.byType(Text).evaluate()) {
    final String data = ((e.widget as Text).data ?? '').trim();
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

/// Tap the grid row whose cell reads exactly [text].
Future<void> pickRow(WidgetTester tester, String text) async {
  final Finder row = find.byWidgetPredicate(
      (Widget w) => w is Text && (w.data ?? '').trim() == text);
  await pumpUntil(tester, row, waitingFor: 'a row showing $text');
  await tester.tap(row.last);
  await pumpFor(tester, const Duration(milliseconds: 700));
}

/// Every string key on screen that starts with [prefix].
List<String> keysStarting(WidgetTester tester, String prefix) => <String>{
      for (final Element e in find.byWidgetPredicate((Widget w) {
        final Key? k = w.key;
        return k is ValueKey<String> && k.value.startsWith(prefix);
      }).evaluate())
        (e.widget.key! as ValueKey<String>).value,
    }.toList();

/// The value of the switch (or tick box) titled [label]; null when absent.
bool? switchOf(WidgetTester tester, String label) {
  for (final Element e in find
      .byWidgetPredicate(
          (Widget w) => w is SwitchListTile || w is CheckboxListTile)
      .evaluate()) {
    final Widget w = e.widget;
    final Widget? title =
        w is SwitchListTile ? w.title : (w as CheckboxListTile).title;
    if (title is Text && title.data == label) {
      return w is SwitchListTile ? w.value : (w as CheckboxListTile).value;
    }
  }
  return null;
}

/// The tracking switches a product form shows, with their values.
String trackingShown(WidgetTester tester) => <String>[
      for (final String label in const <String>[
        'Track batch',
        'Track lot',
        'Track serial',
        'Track expiry',
        'Track manufacturing date',
        'Track warranty',
      ])
        if (switchOf(tester, label) != null)
          '$label=${switchOf(tester, label)}',
    ].join(', ');

/// What is typed in the box labelled [label], or null when it is absent.
String? boxText(WidgetTester tester, String label) {
  final Finder box = fieldLabelled(label);
  if (box.evaluate().isEmpty) return null;
  return tester.widget<TextField>(box.first).controller?.text;
}

/// Pick [entry] in the drop-down labelled [label].
Future<void> pickDropdown(
    WidgetTester tester, String label, String entry) async {
  final Finder box = find.ancestor(
      of: find.text(label),
      matching: find.byWidgetPredicate(
          (Widget w) => w is DropdownButtonFormField<String>));
  await pumpUntil(tester, box, waitingFor: 'the $label box');
  await Scrollable.ensureVisible(tester.element(box.last), alignment: 0.5);
  await pumpFor(tester, const Duration(milliseconds: 400));
  await tester.tap(box.last);
  await pumpFor(tester, const Duration(milliseconds: 700));
  final Finder item = find.textContaining(entry);
  await pumpUntil(tester, item, waitingFor: '$label entry "$entry"');
  await tester.tap(item.last);
  await pumpFor(tester, const Duration(seconds: 3));
}

/// Tap the [index]th chip whose label contains [label].
Future<void> tapChip(WidgetTester tester, String label,
    {int index = 0}) async {
  final Finder chip = find.byWidgetPredicate((Widget w) =>
      w is FilterChip &&
      w.label is Text &&
      ((w.label as Text).data ?? '').contains(label));
  await pumpUntil(tester, chip, waitingFor: 'a chip "$label"');
  await tester.ensureVisible(chip.at(index));
  await pumpFor(tester, const Duration(milliseconds: 300));
  await tester.tap(chip.at(index));
  await pumpFor(tester, const Duration(milliseconds: 500));
}

/// The chips on screen whose label matches [pattern].
List<String> chipsMatching(WidgetTester tester, RegExp pattern) => <String>{
      for (final FilterChip c
          in tester.widgetList<FilterChip>(find.byType(FilterChip)))
        if (c.label is Text && pattern.hasMatch((c.label as Text).data ?? ''))
          '${(c.label as Text).data}${c.selected ? '*' : ''}',
    }.toList();

/// Press something and return what the screen said in the next seconds: a
/// notice, a dialog, or any short text that was not there before.
Future<String> pressAndRead(
  WidgetTester tester,
  Future<void> Function() press, {
  int seconds = 5,
  String? confirmWith,
}) async {
  final Set<String> before = textOnScreen(tester).toSet();
  await press();
  final Set<String> seen = <String>{};
  bool confirmed = confirmWith == null;
  final DateTime end = DateTime.now().add(Duration(seconds: seconds));
  while (DateTime.now().isBefore(end)) {
    await tester.pump(const Duration(milliseconds: 200));
    if (!confirmed && find.byType(Dialog).evaluate().isNotEmpty) {
      seen.add('asked: ${dialogText(tester)}');
      await tapDialogButton(tester, confirmWith!);
      confirmed = true;
      continue;
    }
    final String n = noticeText(tester);
    if (n.isNotEmpty) seen.add(n);
    for (final String t in textOnScreen(tester)) {
      if (t.length < 240 && t.length > 12 && !before.contains(t)) seen.add(t);
    }
  }
  return seen.join(' || ');
}

/// One goods type as the server holds it, by code.
Future<Json?> typeByCode(Server server, String code) async {
  for (final dynamic row
      in (await server.get('/api/v1/$_types')) as List<dynamic>) {
    if ((row as Json)['code'] == code) return row;
  }
  return null;
}

/// The first row of [path] whose [field] is [value].
Future<Json?> rowWhere(
    Server server, String path, String field, String value) async {
  final dynamic rows = await server.get(path);
  for (final dynamic row in rows as List<dynamic>) {
    if ('${(row as Json)[field]}' == value) return row;
  }
  return null;
}

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('GT: goods type cases ($itHandle)', (WidgetTester tester) async {
    // The smallest screen the app promises: an overflow here is a finding.
    tester.view.physicalSize = const Size(1366, 768);
    tester.view.devicePixelRatio = 1;
    final FlowLog log = FlowLog('gt-$itHandle');
    late final Server me;
    final String stamp = DateTime.now()
        .millisecondsSinceEpoch
        .toRadixString(36)
        .toUpperCase()
        .substring(3);
    // Sorts before every other category, newest first, so the product
    // form's category box shows it without scrolling.
    final String top =
        '0${9999999999 - DateTime.now().millisecondsSinceEpoch ~/ 1000}';
    late final Json medicine;
    late final Json paint;
    late final Json electronics;
    late final Json catMed;
    late final Json catPlain;
    late final Json prodMed;
    late final Json prodPlain;
    late final String piece;
    Future<Json> category(String name, Json? type) async =>
        (await me.write('POST', '/api/v1/products/categories',
            <String, dynamic>{
              'code': '$top-${name.toUpperCase()}',
              'name': '$top $name',
              if (type != null) 'goods_type_id': type['id'],
            })) as Json;
    // Before the app starts: a screen the app reopens at sign-in reads its
    // lists then, and would not hold records made after it.
    final bool ready = itHandle != 'admin' ||
        await log.step('set-up over HTTP', () async {
      me = await Server.connect();
      medicine = (await typeByCode(me, 'MEDICINE'))!;
      paint = (await typeByCode(me, 'PAINT'))!;
      electronics = (await typeByCode(me, 'ELECTRONICS'))!;
      catMed = await category('Med', medicine);
      catPlain = await category('Plain', null);
      await category('Phone', electronics);
      piece = '${(await rowWhere(me, '/api/v1/uom-framework/uoms?page_size=100', 'code', 'PIECE'))!['id']}';
      Future<Json> product(String code, Json cat) async =>
          (await me.write('POST', '/api/v1/products', <String, dynamic>{
            'code': code,
            'name': 'SG $code',
            'product_type': 'STOCK_ITEM',
            'category_id': cat['id'],
            'tax_profile_group_code': 'GST_18_LOCAL',
            'selling_price': '100',
            'purchase_price': '60',
            'base_uom_id': piece,
            'inventory_uom_id': piece,
            'sales_uom_id': piece,
            'purchase_uom_id': piece,
          })) as Json;
      prodMed = await product('SGM$stamp', catMed);
      prodPlain = await product('SGP$stamp', catPlain);
    });
    await startAndSignIn(tester);
    collectAppErrors();
    if (!ready) {
      log.finish();
      return;
    }

    Future<bool> openTypes() async {
      await leave(tester);
      try {
        await openSetUp(tester, 'administration/goods-types', section: 'Firm');
        return true;
      } on TestFailure {
        return false;
      }
    }

    Future<bool> openSets() async {
      await leave(tester);
      try {
        await openSetUp(tester, 'administration/unit-sets',
            section: 'Business profile');
        return true;
      } on TestFailure {
        return false;
      }
    }

    Future<bool> openCategories() async {
      await leave(tester);
      try {
        await openSetUp(tester, 'masters/product-categories',
            section: 'Item lists');
        return true;
      } on TestFailure {
        return false;
      }
    }

    Future<bool> openProducts() async {
      try {
        await openArea(tester, 'masters', 'masters/products');
        return true;
      } on TestFailure {
        return false;
      } on StateError {
        return false;
      }
    }

    // ---- What the menu offers, for every user -------------------------
    await log.step('SC-GM-001 the Stock menu offers only the tracking the '
        "firm's goods need", () async {
      // Only the Stock area is read: walking every area is what the role
      // flows do, and a bar that folds between two taps loses the walk.
      final List<String> areas = keysStarting(tester, 'menu-area-')
          .map((String k) => k.substring(10))
          .toList();
      final List<String> stock = <String>[];
      if (areas.contains('stock')) {
        await tester.tap(find.byKey(const ValueKey<String>('menu-area-stock')));
        await pumpFor(tester, const Duration(milliseconds: 700));
        final Finder all = find.byKey(const ValueKey<String>('menu-show-all'));
        if (all.evaluate().isNotEmpty) {
          await tester.tap(all);
          await pumpFor(tester, const Duration(milliseconds: 700));
        }
        stock.addAll(keysStarting(tester, 'menu-item-')
            .map((String k) => k.substring(10)));
        await tester.sendKeyEvent(LogicalKeyboardKey.escape);
        await pumpFor(tester, const Duration(milliseconds: 500));
      }
      if (itHandle == 'platform') {
        log.info('SC-GM-001', 'no firm chosen: areas $areas; on screen '
            '${textOnScreen(tester).take(40).join(' | ')}');
      }
      final List<String> tracked = <String>[
        for (final String item in stock)
          if (RegExp('batches|lots|serials|expiry').hasMatch(item)) item,
      ];
      String asked = 'not asked';
      if (itHandle != 'platform') {
        final Server me = await Server.connect();
        final dynamic modules =
            await me.get('/api/v1/business-framework/active-modules');
        Set<String>? tracking;
        for (final dynamic m in modules as List<dynamic>) {
          if ((m as Json)['code'] == 'INVENTORY' &&
              m['goods_tracking'] != null) {
            tracking = <String>{
              for (final dynamic t in m['goods_tracking'] as List<dynamic>)
                '$t',
            };
          }
        }
        asked = 'server tracking=$tracking';
        if (tracking != null && stock.isNotEmpty) {
          final Map<String, String> needs = <String, String>{
            'inventory/batches': 'BATCH',
            'inventory/serials': 'SERIAL',
            'inventory/expiry-monitor': 'EXPIRY',
          };
          final List<String> wrong = <String>[
            for (final MapEntry<String, String> e in needs.entries)
              if (stock.contains(e.key) != tracking.contains(e.value))
                '${e.key} offered=${stock.contains(e.key)} but '
                    '${e.value} needed=${tracking.contains(e.value)}',
          ];
          // A role without the permission is offered nothing whatever the
          // goods need; only an offer the goods do not need is wrong for it.
          final List<String> extra = <String>[
            for (final MapEntry<String, String> e in needs.entries)
              if (stock.contains(e.key) && !tracking.contains(e.value)) e.key,
          ];
          if (itHandle.endsWith('admin') && wrong.isNotEmpty) {
            throw StateError('$wrong [$asked, stock menu $stock]');
          }
          if (extra.isNotEmpty) {
            throw StateError('offered without the goods: $extra [$asked]');
          }
        }
      }
      log.saw = 'areas $areas, tracking screens $tracked, '
          '$asked, settings offered='
          '${find.byKey(const ValueKey<String>('menu-area-settings')).evaluate().isNotEmpty}';
      if (areas.isEmpty) throw StateError('no menu area is offered at all');
    });

    if (itHandle == 'admin') {
      final String own = 'SG$stamp';

      // ================= Goods Types =================
      if (wants('types')) {
      await log.step('SC-GT-001 Goods Types opens with shared and own rows',
          () async {
        if (!await openTypes()) throw StateError('not offered');
        final List<String> missing = <String>[
          for (final String h in <String>[
            'Code', 'Name', 'Kind', 'Tracks', 'In use', 'Default HSN',
            'Default tax group', 'Shared', 'Own', '+ New',
          ])
            if (!screenHas(tester, h)) h,
        ];
        await searchList(tester, 'MEDICINE');
        log.saw = 'Medicine row: ${gridRow(tester, 'MEDICINE')}; missing '
            '$missing';
        if (missing.isNotEmpty) throw StateError('not on screen: $missing');
      });

      await log.step('SC-GT-003 a new type with the code of a shared one is '
          'refused', () async {
        if (!await openTypes()) throw StateError('not offered');
        await tapNew(tester);
        await typeLabelled(tester, 'Code', 'MEDICINE');
        await typeLabelled(tester, 'Name', 'Typed $stamp');
        log.saw = await expectRefusal(tester, me,
            collection: _types,
            openKey: _dialog,
            typed: 'Typed $stamp',
            press: () => tapButton(tester, 'Save & Close'));
      });
      await leave(tester);

      await log.step('SC-GT-004 a new type with no name is refused', () async {
        if (!await openTypes()) throw StateError('not offered');
        await tapNew(tester);
        await typeLabelled(tester, 'Code', 'NN$stamp');
        log.saw = await expectRefusal(tester, me,
            collection: _types,
            openKey: _dialog,
            typed: 'NN$stamp',
            press: () => tapButton(tester, 'Save & Close'));
      });
      await leave(tester);

      await log.step('SC-GT-012 Cancel on a typed goods type asks first',
          () async {
        if (!await openTypes()) throw StateError('not offered');
        await tapNew(tester);
        await typeLabelled(tester, 'Name', 'Left $stamp');
        await tapButton(tester, 'Cancel');
        await pumpFor(tester, const Duration(seconds: 1));
        final bool asks = screenHas(tester, 'Discard unsaved changes?');
        final bool open =
            find.byKey(const ValueKey<String>(_dialog)).evaluate().isNotEmpty;
        log.saw = 'asked=$asks, dialog open=$open, question='
            '"${noticeText(tester).split(' | ').where((String t) => t.contains('iscard') || t.contains('unsaved')).join(' | ')}"';
        if (!asks) throw StateError('Cancel asked nothing (open=$open)');
        await tapDialogButton(tester, 'Cancel');
        if (!screenHasTyped(tester, 'Left $stamp')) {
          throw StateError('Keep editing lost what was typed');
        }
      });
      await leave(tester);

      await log.step('SC-GT-002 the firm adds a goods type of its own',
          () async {
        if (!await openTypes()) throw StateError('not offered');
        await tapNew(tester);
        await typeLabelled(tester, 'Code', own);
        await typeLabelled(tester, 'Name', 'Own $stamp');
        await tester.ensureVisible(find.text('Batches').last);
        await tester.tap(find.text('Batches').last);
        await pumpFor(tester, const Duration(milliseconds: 400));
        final String said = await pressAndRead(
            tester, () => tapButton(tester, 'Save & Close'));
        final Json? row = await typeByCode(me, own);
        log.saw = 'said "$said"; server ${row == null ? 'has none' : 'track_batch=${row['track_batch']}, in_use=${row['in_use']}, firm=${row['firm_id'] != null}'}';
        if (row == null) throw StateError('not saved [$said]');
        if (row['track_batch'] != true || row['in_use'] != true) {
          throw StateError('saved wrong: $row');
        }
        await searchList(tester, own);
        final List<String> line = gridRow(tester, own);
        log.saw = '${log.saw}; row $line';
        if (!line.contains('Own') || !line.contains('Batch')) {
          throw StateError('the row does not read Own / Batch: $line');
        }
      });
      await leave(tester);

      await log.step('SC-GT-013 the firm changes its own type', () async {
        if (!await openTypes()) throw StateError('not offered');
        await searchList(tester, own);
        await pickRow(tester, own);
        await tapButton(tester, 'Edit');
        await pumpFor(tester, const Duration(seconds: 1));
        final Finder code = fieldLabelled('Code');
        final bool locked = code.evaluate().isNotEmpty &&
            (tester.widget<TextField>(code.first).readOnly ||
                tester.widget<TextField>(code.first).enabled == false);
        await typeLabelled(tester, 'Name', 'Own renamed $stamp');
        final String said = await pressAndRead(
            tester, () => tapButton(tester, 'Save & Close'));
        final Json? row = await typeByCode(me, own);
        log.saw = 'code locked=$locked; said "$said"; server name '
            '${row?['name']}, track_batch=${row?['track_batch']}';
        if (row?['name'] != 'Own renamed $stamp') {
          throw StateError('the name was not saved');
        }
        if (row?['track_batch'] != true) {
          throw StateError('the edit dropped the Batches switch');
        }
        if (!locked) throw StateError('the code can be typed over on Edit');
      });
      await leave(tester);

      await log.step('SC-GT-009 Set defaults with an unknown tax group is '
          'refused in the dialog', () async {
        if (!await openTypes()) throw StateError('not offered');
        await searchList(tester, own);
        await pickRow(tester, own);
        await tapButton(tester, 'Set defaults');
        await tester.enterText(
            find.byKey(const ValueKey<String>('goods-type-defaults-hsn')),
            '3004');
        await tester.enterText(
            find.byKey(const ValueKey<String>('goods-type-defaults-tax-group')),
            'NO_SUCH_$stamp');
        log.saw = await expectRefusal(tester, me,
            collection: _types,
            openKey: 'goods-type-defaults-save',
            typed: 'NO_SUCH_$stamp',
            press: () => tapKey(tester, 'goods-type-defaults-save'));
        final Json? row = await typeByCode(me, own);
        if (row?['default_hsn_sac'] != null) {
          throw StateError('N3: the HSN was saved beside a refused group');
        }
      });

      await log.step('SC-GT-008 Set defaults saves the HSN code and the tax '
          'group', () async {
        if (find
            .byKey(const ValueKey<String>('goods-type-defaults-save'))
            .evaluate()
            .isEmpty) {
          if (!await openTypes()) throw StateError('not offered');
          await searchList(tester, own);
          await pickRow(tester, own);
          await tapButton(tester, 'Set defaults');
        }
        await tester.enterText(
            find.byKey(const ValueKey<String>('goods-type-defaults-hsn')),
            '3004');
        await tester.enterText(
            find.byKey(const ValueKey<String>('goods-type-defaults-tax-group')),
            'GST_12_LOCAL');
        final String said = await pressAndRead(
            tester, () => tapKey(tester, 'goods-type-defaults-save'));
        final Json? row = await typeByCode(me, own);
        await searchList(tester, own);
        log.saw = 'said "$said"; server hsn=${row?['default_hsn_sac']}, '
            'group=${row?['default_tax_profile_group_code']}; row '
            '${gridRow(tester, own)}';
        if (row?['default_hsn_sac'] != '3004' ||
            row?['default_tax_profile_group_code'] != 'GST_12_LOCAL') {
          throw StateError('defaults not saved');
        }
        if (!gridRow(tester, own).contains('GST_12_LOCAL')) {
          throw StateError('the grid does not show the new default');
        }
      });
      await leave(tester);

      await log.step('SC-GT-005 a shared type offers no Edit or Delete and '
          'says why', () async {
        if (!await openTypes()) throw StateError('not offered');
        await searchList(tester, 'MEDICINE');
        await pickRow(tester, 'MEDICINE');
        final String edit = buttonState(tester, 'Edit');
        final String delete = buttonState(tester, 'Delete');
        await tapButton(tester, 'Open');
        await pumpFor(tester, const Duration(seconds: 1));
        final bool why = screenHas(tester, 'A shared goods type cannot be');
        log.saw = 'Edit $edit, Delete $delete, Open says why=$why, '
            'Save ${buttonState(tester, 'Save & Close')}';
        if (edit == 'enabled' || delete == 'enabled') {
          throw StateError('a shared type can be changed: $edit / $delete');
        }
        if (!why) throw StateError('nothing says why it cannot be changed');
      });
      await leave(tester);

      await log.step('SC-GT-006 Use in this firm, then Stop using', () async {
        if (!await openTypes()) throw StateError('not offered');
        final Json food = (await typeByCode(me, 'FOOD'))!;
        if (food['in_use'] == true) {
          await me.write('PUT', '/api/v1/$_types/${food['id']}/use',
              <String, dynamic>{'in_use': false});
          await refreshList(tester);
        }
        await searchList(tester, 'FOOD');
        await pickRow(tester, 'FOOD');
        final String on = await pressAndRead(
            tester, () => tapButton(tester, 'Use in this firm'));
        final bool used = (await typeByCode(me, 'FOOD'))!['in_use'] == true;
        await pickRow(tester, 'FOOD');
        final String off =
            await pressAndRead(tester, () => tapButton(tester, 'Stop using'));
        final bool still = (await typeByCode(me, 'FOOD'))!['in_use'] == true;
        log.saw = 'use said "$on" (server in_use=$used); stop said "$off" '
            '(server in_use=$still)';
        if (!used || still) throw StateError('the server did not follow');
        if (!on.contains('in use') || !off.contains('no longer')) {
          throw StateError('the screen did not say what happened');
        }
      });

      await log.step('SC-GT-007 Stop using a type a category carries is '
          'refused in words', () async {
        if (!await openTypes()) throw StateError('not offered');
        await searchList(tester, 'MEDICINE');
        await pickRow(tester, 'MEDICINE');
        final String said =
            await pressAndRead(tester, () => tapButton(tester, 'Stop using'));
        final bool still =
            (await typeByCode(me, 'MEDICINE'))!['in_use'] == true;
        log.saw = 'said "$said"; server in_use=$still';
        if (!still) throw StateError('N3: Medicine was taken out of use');
        if (!RegExp('categor|carr|cannot|still', caseSensitive: false)
            .hasMatch(said)) {
          throw StateError('N1: nothing on screen says why');
        }
      });

      await log.step('SC-GT-010 Delete of a type a category carries is '
          'refused in words', () async {
        final Json held = (await me.write(
            'POST', '/api/v1/$_types', <String, dynamic>{
          'code': 'SH$stamp',
          'name': 'Held $stamp',
          'track_batch': true,
        })) as Json;
        await category('Held', held);
        if (!await openTypes()) throw StateError('not offered');
        await refreshList(tester);
        await searchList(tester, 'SH$stamp');
        await pickRow(tester, 'SH$stamp');
        final String said = await pressAndRead(
            tester, () => tapButton(tester, 'Delete'),
            confirmWith: 'Delete', seconds: 6);
        final bool there = await typeByCode(me, 'SH$stamp') != null;
        log.saw = 'said "$said"; still on the server=$there';
        if (!there) throw StateError('N3: the type was deleted');
        if (!RegExp('categor|carr|cannot|Deactivate', caseSensitive: false)
            .hasMatch(said.split('||').skip(1).join(' '))) {
          throw StateError('N1: nothing on screen says why [${log.saw}]');
        }
      });
      await leave(tester);

      await log.step('SC-GT-011 Delete of an own type nothing uses', () async {
        if (!await openTypes()) throw StateError('not offered');
        await searchList(tester, own);
        await pickRow(tester, own);
        final String said = await pressAndRead(
            tester, () => tapButton(tester, 'Delete'),
            confirmWith: 'Delete', seconds: 6);
        final bool there = await typeByCode(me, own) != null;
        log.saw = 'said "$said"; still on the server=$there';
        if (there) throw StateError('the type is still there');
      });
      await leave(tester);

      }
      // ================= Product categories =================
      if (wants('categories')) {
      await log.step('SC-GC-001 the category list names each goods type',
          () async {
        if (!await openCategories()) throw StateError('not offered');
        final int named = find.text('Medicine').evaluate().length +
            find.text('Paint').evaluate().length +
            find.text('Electronics').evaluate().length;
        final int general = find.text('General').evaluate().length;
        log.info('SC-GC-001', 'first page: $named rows name a goods type, '
            '$general read General');
        await searchList(tester, top);
        final List<String> med = gridRow(tester, '${catMed['code']}');
        final List<String> plain = gridRow(tester, '${catPlain['code']}');
        log.saw = 'med $med; plain $plain';
        if (!med.contains('Medicine')) throw StateError('no Medicine: $med');
        if (!plain.contains('General')) throw StateError('no General: $plain');
      });

      final String newCat = '$top-NEW';
      await log.step('SC-GC-002 a new category takes a goods type', () async {
        if (!await openCategories()) throw StateError('not offered');
        await tapNew(tester);
        await pumpFor(tester, const Duration(seconds: 2));
        await typeLabelled(tester, 'Category code', newCat);
        await typeLabelled(tester, 'Name', '$top New');
        final List<String> offered = chipsMatching(tester,
            RegExp(r'Medicine|Paint|Food|Cosmetics|Electronics|General'));
        await tapChip(tester, 'Paint');
        final String said = await pressAndRead(
            tester, () => tapButton(tester, 'Save & Close'));
        final Json? row = await rowWhere(
            me, '/api/v1/products/categories?search=$newCat', 'code', newCat);
        log.saw = 'goods type chips $offered; said "$said"; server type '
            '${row?['goods_type_id'] == paint['id'] ? 'Paint' : row?['goods_type_id']}';
        if (row == null) throw StateError('not saved [$said]');
        if (row['goods_type_id'] != paint['id']) {
          throw StateError('saved with the wrong type');
        }
      });
      await leave(tester);

      await log.step('SC-GC-003 a category changes its goods type', () async {
        if (!await openCategories()) throw StateError('not offered');
        await refreshList(tester);
        await searchList(tester, newCat);
        final List<String> listed = gridRow(tester, newCat);
        await pickRow(tester, newCat);
        await tapButton(tester, 'Edit');
        await pumpUntil(
            tester,
            find.byWidgetPredicate((Widget w) =>
                w is FilterChip &&
                w.label is Text &&
                ((w.label as Text).data ?? '').startsWith('Medicine')),
            waitingFor: 'the goods type chips');
        final List<String> chosen = chipsMatching(tester, RegExp('Paint'))
            .where((String c) => c.endsWith('*'))
            .toList();
        await tapChip(tester, 'Medicine');
        final String said = await pressAndRead(
            tester, () => tapButton(tester, 'Save & Close'));
        final Json? row = await rowWhere(
            me, '/api/v1/products/categories?search=$newCat', 'code', newCat);
        log.saw = 'grid row $listed; opened with $chosen; said "$said"; server type '
            '${row?['goods_type_id'] == medicine['id'] ? 'Medicine' : row?['goods_type_id']}';
        if (chosen.isEmpty) throw StateError('Edit did not show Paint chosen');
        if (row?['goods_type_id'] != medicine['id']) {
          throw StateError('the change was not saved');
        }
      });
      await leave(tester);

      await log.step('SC-GC-004 a category with a code already used is '
          'refused', () async {
        if (!await openCategories()) throw StateError('not offered');
        await tapNew(tester);
        await pumpFor(tester, const Duration(seconds: 2));
        await typeLabelled(tester, 'Category code', '${catMed['code']}');
        await typeLabelled(tester, 'Name', 'Twice $stamp');
        log.saw = await expectRefusal(tester, me,
            collection: 'products/categories',
            openKey: _dialog,
            typed: 'Twice $stamp',
            press: () => tapButton(tester, 'Save & Close'));
      });
      await leave(tester);

      }
      // ================= Product form =================
      if (wants('products')) {
      Future<void> newProduct(String categoryName) async {
        if (!await openProducts()) throw StateError('Products not offered');
        await tapNew(tester);
        await pumpFor(tester, const Duration(seconds: 3));
        await pickDropdown(tester, 'Category', categoryName);
      }

      String goodsTypeLine() {
        final Finder line =
            find.byKey(const ValueKey<String>('product-goods-type'));
        return line.evaluate().isEmpty
            ? 'absent'
            : tester.widget<Text>(line.first).data ?? '';
      }

      await log.step('SC-GP-001 a Medicine category fills the type, its '
          'switches, HSN and tax group', () async {
        await newProduct('$top Med');
        final String line = goodsTypeLine();
        final String tracking = trackingShown(tester);
        final String? hsn = boxText(tester, 'HSN / SAC');
        final List<String> tax = keysStarting(tester, 'product-tax-profile-');
        log.saw = '"$line"; switches [$tracking]; HSN "$hsn"; tax $tax';
        if (line != 'Goods type: Medicine') throw StateError('type: $line');
        if (switchOf(tester, 'Track batch') != true) {
          throw StateError('Track batch is not on: [$tracking]');
        }
        if (switchOf(tester, 'Track serial') != null) {
          throw StateError('Track serial is shown for a medicine');
        }
        if (hsn != '3004') throw StateError('HSN not filled: "$hsn"');
        if (!tax.contains('product-tax-profile-GST_12_LOCAL')) {
          throw StateError('tax group not filled: $tax');
        }
      });

      await log.step('SC-GP-004 the unit set box offers the sets of the '
          'goods type, and Show all the rest', () async {
        if (goodsTypeLine() != 'Goods type: Medicine') {
          await newProduct('$top Med');
        }
        Future<List<String>> entries() async {
          final Set<String> before = textOnScreen(tester).toSet();
          await tapKey(tester, 'product-unit-set');
          await pumpFor(tester, const Duration(milliseconds: 700));
          final List<String> seen = textOnScreen(tester)
              .where((String t) => !before.contains(t))
              .toSet()
              .toList();
          await tester.tap(find.text('None (choose the units below)').last);
          await pumpFor(tester, const Duration(milliseconds: 700));
          return seen;
        }

        final List<String> first = await entries();
        await tapKey(tester, 'product-show-all-unit-sets');
        final List<String> all = await entries();
        await tapKey(tester, 'product-show-all-unit-sets');
        log.saw = 'offered ${first.length}: ${first.take(14).toList()}; with '
            'Show all ${all.length}';
        if (!first.contains('Strip, box of 10')) {
          throw StateError('Strip, box of 10 is not offered: $first');
        }
        if (first.contains('Litre, loose')) {
          throw StateError('a Paint-only set is offered to a medicine');
        }
        if (all.length <= first.length) {
          throw StateError('Show all unit sets added nothing');
        }
      });

      final String saved = 'SG Tablet $stamp';
      await log.step('SC-GP-005 a product saved from a type and a unit set',
          () async {
        if (goodsTypeLine() != 'Goods type: Medicine') {
          await newProduct('$top Med');
        }
        await typeLabelled(tester, 'Product name *', saved);
        await pickDropdown(tester, 'Unit set', 'Strip, box of 10');
        final Finder factor = find.descendant(
            of: find.byKey(
                const ValueKey<String>('product-unit-conversion-factor')),
            matching: find.byType(EditableText));
        final String typedFactor = factor.evaluate().isEmpty
            ? 'no box'
            : tester.widget<EditableText>(factor.first).controller.text;
        await saveEditor(tester, 'product-save');
        final Json? row = await rowWhere(
            me, '/api/v1/products?search=$stamp&page_size=25', 'name', saved);
        log.saw = 'conversion box "$typedFactor"; server '
            '${row == null ? 'has none' : 'type=${row['goods_type_id'] == medicine['id'] ? 'Medicine' : row['goods_type_id']}, batch=${row['track_batch']}, expiry=${row['track_expiry']}, unit_set=${row['unit_set_id'] != null}, hsn=${row['hsn_sac'] ?? row['hsn_code']}'}';
        if (row == null) throw StateError('not saved');
        if (row['goods_type_id'] != medicine['id'] ||
            row['track_batch'] != true ||
            row['unit_set_id'] == null) {
          throw StateError('saved wrong');
        }
        if (!typedFactor.startsWith('10')) {
          throw StateError('the set did not fill the conversion');
        }
      });
      await leave(tester);

      await log.step('SC-GP-006 a saved product shows its type and where its '
          'units came from, and no unit set box', () async {
        if (!await openProducts()) throw StateError('not offered');
        await refreshList(tester);
        await searchList(tester, saved);
        await pickRow(tester, saved);
        await tapButton(
            tester, buttonState(tester, 'Edit') == 'enabled' ? 'Edit' : 'Open');
        await pumpFor(tester, const Duration(seconds: 3));
        final Finder origin =
            find.byKey(const ValueKey<String>('product-unit-set-origin'));
        final String from = origin.evaluate().isEmpty
            ? 'absent'
            : tester.widget<Text>(origin.first).data ?? '';
        final bool picker = find
            .byKey(const ValueKey<String>('product-unit-set'))
            .evaluate()
            .isNotEmpty;
        log.saw = '"${goodsTypeLine()}"; units line "$from"; unit set box '
            'shown=$picker; switches [${trackingShown(tester)}]';
        if (goodsTypeLine() != 'Goods type: Medicine') {
          throw StateError('type line: ${goodsTypeLine()}');
        }
        if (picker) throw StateError('an existing product offers a unit set');
        if (!from.contains('Strip, box of 10')) {
          throw StateError('the units line does not name the set: $from');
        }
      });
      await leave(tester);

      await log.step('SC-GP-002 a category with no type shows no tracking '
          'until Show all tracking options', () async {
        await newProduct('$top Plain');
        final String line = goodsTypeLine();
        final bool hint = find
            .byKey(const ValueKey<String>('product-no-tracking-hint'))
            .evaluate()
            .isNotEmpty;
        final String hidden = trackingShown(tester);
        await tapKey(tester, 'product-show-all-tracking');
        final String shown = trackingShown(tester);
        log.saw = '"$line"; hint=$hint; before [$hidden]; after Show all '
            '[$shown]';
        if (line != 'Goods type: General') throw StateError('type: $line');
        if (!hint || hidden.isNotEmpty) {
          throw StateError('tracking shown for General: [$hidden]');
        }
        if (switchOf(tester, 'Track batch') != false ||
            switchOf(tester, 'Track serial') != false) {
          throw StateError('Show all did not offer the switches: [$shown]');
        }
      });
      await leave(tester);

      await log.step('SC-GP-003 an Electronics category shows serial numbers '
          'and warranty, not batches', () async {
        await newProduct('$top Phone');
        final String tracking = trackingShown(tester);
        log.saw = '"${goodsTypeLine()}"; switches [$tracking]';
        if (goodsTypeLine() != 'Goods type: Electronics') {
          throw StateError('type: ${goodsTypeLine()}');
        }
        if (switchOf(tester, 'Track serial') != true) {
          throw StateError('Track serial is not on: [$tracking]');
        }
        if (switchOf(tester, 'Track batch') != null) {
          throw StateError('Track batch is shown for electronics');
        }
      });

      await log.step('SC-GP-009 changing the category of an unsaved product '
          'follows the new goods type', () async {
        if (goodsTypeLine() != 'Goods type: Electronics') {
          await newProduct('$top Phone');
        }
        await pickDropdown(tester, 'Category', '$top Med');
        final String tracking = trackingShown(tester);
        log.saw = '"${goodsTypeLine()}"; switches [$tracking]; HSN '
            '"${boxText(tester, 'HSN / SAC')}"';
        if (goodsTypeLine() != 'Goods type: Medicine') {
          throw StateError('type: ${goodsTypeLine()}');
        }
        if (switchOf(tester, 'Track serial') == true) {
          throw StateError('the old type left Track serial on: [$tracking]');
        }
        if (switchOf(tester, 'Track batch') != true) {
          throw StateError('the new type did not switch batches on');
        }
      });
      await leave(tester);

      await log.step('SC-GP-007 a product with no name is refused', () async {
        if (!await openProducts()) throw StateError('not offered');
        await tapNew(tester);
        await pumpFor(tester, const Duration(seconds: 3));
        log.saw = await expectRefusal(tester, me,
            collection: 'products',
            openKey: 'product-save',
            allowStale: true,
            press: () => tapKey(tester, 'product-save'));
      });
      await leave(tester);

      await log.step('SC-GP-008 a product with a code already used is '
          'refused and the typing kept', () async {
        if (!await openProducts()) throw StateError('not offered');
        await tapNew(tester);
        await pumpFor(tester, const Duration(seconds: 3));
        await typeLabelled(tester, 'Product code', '${prodMed['code']}');
        await typeLabelled(tester, 'Product name *', 'Twice $stamp');
        log.saw = await expectRefusal(tester, me,
            collection: 'products',
            openKey: 'product-save',
            typed: 'Twice $stamp',
            press: () => tapKey(tester, 'product-save'));
        if (log.saw!.contains('Somebody else saved')) {
          throw StateError('N1: a code that exists is worded as a lost race: '
              '${log.saw}');
        }
      });
      await leave(tester);

      await log.step('SC-GI-001 the product import is offered and says what '
          'a file may carry', () async {
        if (!await openProducts()) throw StateError('not offered');
        await tester.tap(find.text('…').first);
        await pumpFor(tester, const Duration(milliseconds: 700));
        final List<String> entries = textOnScreen(tester)
            .where((String t) => RegExp('mport|xport|emplate').hasMatch(t))
            .toList();
        log.saw = '… menu entries $entries';
        log.info('SC-GI-001', log.saw!);
        final Finder import = find.text('Import products').evaluate().isEmpty
            ? find.textContaining('Import')
            : find.text('Import products');
        if (import.evaluate().isEmpty) {
          throw StateError('no Import entry: $entries');
        }
        await tester.tap(import.last);
        await pumpFor(tester, const Duration(seconds: 3));
        log.saw = '${log.saw}; dialog: '
            '${noticeText(tester).split(' | ').take(14).join(' | ')}';
        if (find.byType(Dialog).evaluate().isEmpty) {
          throw StateError('Import opened nothing');
        }
      });
      await leave(tester);

      }
      // ================= Unit Sets =================
      if (wants('sets')) {
      final String setName = 'SG set $stamp';
      await log.step('SC-US-001 Unit Sets lists each set with its conversion',
          () async {
        if (!await openSets()) throw StateError('not offered');
        await searchList(tester, 'Strip, box of 10');
        final List<String> line = gridRow(tester, 'Strip, box of 10');
        log.saw = 'row $line';
        if (!line.contains('1 Box = 10 Strip') || !line.contains('Shared')) {
          throw StateError('the row does not read as expected: $line');
        }
      });

      await log.step('SC-US-003 a unit set with no base unit is refused',
          () async {
        if (!await openSets()) throw StateError('not offered');
        await tapNew(tester);
        await pumpFor(tester, const Duration(seconds: 3));
        await typeLabelled(tester, 'Name', setName);
        log.saw = await expectRefusal(tester, me,
            collection: _sets,
            openKey: _dialog,
            typed: setName,
            press: () => tapButton(tester, 'Save & Close'));
      });

      await log.step('SC-US-002 the firm adds a unit set of its own',
          () async {
        if (find.byKey(const ValueKey<String>(_dialog)).evaluate().isEmpty) {
          if (!await openSets()) throw StateError('not offered');
          await tapNew(tester);
          await pumpFor(tester, const Duration(seconds: 3));
          await typeLabelled(tester, 'Name', setName);
        }
        // The unit chips repeat once per unit field, in the form's order:
        // base, stock, purchase, sales.
        await tapChip(tester, 'Strip · STRIP');
        await tapChip(tester, 'Box · BOX', index: 2);
        final bool asked = fieldLabelled(
                'Conversion: 1 purchase unit = ? stock units')
            .evaluate()
            .isNotEmpty;
        if (asked) {
          await typeLabelled(
              tester, 'Conversion: 1 purchase unit = ? stock units', '10');
        }
        final String said = await pressAndRead(
            tester, () => tapButton(tester, 'Save & Close'));
        final Json? row = await rowWhere(
            me, '/api/v1/$_sets?search=$stamp', 'name', setName);
        log.saw = 'conversion box shown=$asked; said "$said"; server '
            '${row == null ? 'has none' : 'factor=${row['conversion_factor']}, purchase unit set=${row['purchase_uom_id'] != null}'}';
        if (!asked) throw StateError('the conversion box did not appear');
        if (row == null) throw StateError('not saved [$said]');
        if (num2(row['conversion_factor']) != 10) {
          throw StateError('factor saved as ${row['conversion_factor']}');
        }
      });
      await leave(tester);

      await log.step('SC-US-004 a name that differs only in capitals is '
          'refused', () async {
        if (!await openSets()) throw StateError('not offered');
        await tapNew(tester);
        await pumpFor(tester, const Duration(seconds: 3));
        await typeLabelled(tester, 'Name', 'strip, BOX of 10');
        await tapChip(tester, 'Strip · STRIP');
        log.saw = await expectRefusal(tester, me,
            collection: _sets,
            openKey: _dialog,
            typed: 'strip, BOX of 10',
            press: () => tapButton(tester, 'Save & Close'));
      });
      await leave(tester);

      await log.step('SC-US-005 a shared set offers no Edit or Delete and '
          'says why', () async {
        if (!await openSets()) throw StateError('not offered');
        await searchList(tester, 'Piece, loose');
        await pickRow(tester, 'Piece, loose');
        final String edit = buttonState(tester, 'Edit');
        final String delete = buttonState(tester, 'Delete');
        await tapButton(tester, 'Open');
        await pumpFor(tester, const Duration(seconds: 2));
        final bool why = screenHas(tester, 'A shared unit set cannot be');
        log.saw = 'Edit $edit, Delete $delete, Open says why=$why';
        if (edit == 'enabled' || delete == 'enabled') {
          throw StateError('a shared set can be changed');
        }
        if (!why) throw StateError('nothing says why');
      });
      await leave(tester);

      await log.step('SC-US-006 the firm deletes its own unit set', () async {
        if (!await openSets()) throw StateError('not offered');
        await refreshList(tester);
        await searchList(tester, setName);
        await pickRow(tester, setName);
        final String said = await pressAndRead(
            tester, () => tapButton(tester, 'Delete'),
            confirmWith: 'Delete', seconds: 6);
        final Json? row = await rowWhere(
            me, '/api/v1/$_sets?search=$stamp', 'name', setName);
        log.saw = 'said "$said"; still on the server=${row != null}';
        if (row != null) throw StateError('the set is still there');
      });
      await leave(tester);

      }
      // ================= Extra fields =================
      if (wants('fields')) {
      await log.step('SC-GF-001 a shared extra field is switched off for the '
          'firm and on again', () async {
        await leave(tester);
        await openSetUp(tester, 'administration/firm-custom-fields',
            section: 'Firm');
        await searchList(tester, 'GTQ_TRADE_LICENCE_NO');
        await pickRow(tester, 'GTQ_TRADE_LICENCE_NO');
        final List<String> first = keysStarting(tester, 'selection-switch');
        if (first.isEmpty) throw StateError('no switch is offered on the row');
        final List<String> rowBefore = gridRow(tester, 'GTQ_TRADE_LICENCE_NO');
        final String said1 =
            await pressAndRead(tester, () => tapKey(tester, first.first));
        await searchList(tester, 'GTQ_TRADE_LICENCE_NO');
        await pickRow(tester, 'GTQ_TRADE_LICENCE_NO');
        final List<String> rowMid = gridRow(tester, 'GTQ_TRADE_LICENCE_NO');
        final List<String> second = keysStarting(tester, 'selection-switch');
        final String said2 = second.isEmpty
            ? ''
            : await pressAndRead(tester, () => tapKey(tester, second.first));
        log.saw = '${first.first} said "$said1", row $rowBefore -> $rowMid; '
            '${second.isEmpty ? 'nothing to switch back' : second.first} said '
            '"$said2"';
        if (second.isEmpty || second.first == first.first) {
          throw StateError('the row offers no way back: $second');
        }
        if (said1.isEmpty || said2.isEmpty) {
          throw StateError('a switch said nothing');
        }
      });
      await leave(tester);

      }
      // ================= Batches =================
      if (wants('batches')) {
      /// Add Batch for [product] and say what the screen and server did.
      Future<({String said, int saved, bool open})> addBatch(
        String product,
        String number, {
        String? made,
        String? expires,
      }) async {
        await openArea(tester, 'stock', 'inventory/batches');
        final int before = await totalOf(me, 'batch-serial/batches');
        await tapNew(tester);
        await pumpFor(tester, const Duration(seconds: 2));
        if (product.isNotEmpty) {
          await tester.enterText(
              find.byKey(const ValueKey<String>('batch-form-product')),
              product);
          await pumpFor(tester, const Duration(seconds: 3));
          final Finder option = find.textContaining('$product · ');
          await pumpUntil(tester, option,
              waitingFor: 'the product $product in the box');
          await tester.tap(option.last);
          await pumpFor(tester, const Duration(milliseconds: 600));
        }
        await typeLabelled(tester, 'Batch Number *', number);
        if (made != null) {
          await typeLabelled(tester, 'Manufacturing Date (YYYY-MM-DD)', made);
        }
        if (expires != null) {
          await typeLabelled(tester, 'Expiry Date (YYYY-MM-DD)', expires);
        }
        final String said =
            await pressAndRead(tester, () => tapButton(tester, 'Create'));
        final bool open = find
            .byKey(const ValueKey<String>('batch-form-mrp'))
            .evaluate()
            .isNotEmpty;
        final bool kept = !open || screenHasTyped(tester, number);
        final int after = await totalOf(me, 'batch-serial/batches');
        return (
          said: '$said${kept ? '' : ' [the typed number is gone]'}',
          saved: after - before,
          open: open,
        );
      }

      await log.step('SC-GB-001 Add Batch for a product that tracks batches '
          'and expiry', () async {
        final ({String said, int saved, bool open}) r = await addBatch(
            '${prodMed['code']}', 'SGB$stamp',
            made: '2026-01-01', expires: '2028-01-01');
        log.saw = 'said "${r.said}"; saved=${r.saved}; dialog open=${r.open}';
        if (r.saved != 1) throw StateError('not saved: ${log.saw}');
      });
      await leave(tester);

      await log.step('SC-GB-002 an expiry date before the manufacturing date '
          'is refused in words', () async {
        final ({String said, int saved, bool open}) r = await addBatch(
            '${prodMed['code']}', 'SGX$stamp',
            made: '2027-06-01', expires: '2026-06-01');
        log.saw = 'said "${r.said}"; saved=${r.saved}; dialog open=${r.open}';
        if (r.saved != 0) throw StateError('N3: saved: ${log.saw}');
        if (!r.open || r.said.contains('is gone')) {
          throw StateError('N2: ${log.saw}');
        }
        if (!RegExp('before|after|earlier|later', caseSensitive: false)
            .hasMatch(r.said)) {
          throw StateError('N1: nothing says the dates are the wrong way '
              'round: ${log.saw}');
        }
      });
      await leave(tester);

      await log.step('SC-GB-004 a batch for a product that tracks none is '
          'refused in words', () async {
        final ({String said, int saved, bool open}) r =
            await addBatch('${prodPlain['code']}', 'SGN$stamp');
        log.saw = 'said "${r.said}"; saved=${r.saved}; dialog open=${r.open}';
        if (r.saved != 0) throw StateError('N3: saved: ${log.saw}');
        if (!r.open || r.said.contains('is gone')) {
          throw StateError('N2: ${log.saw}');
        }
        if (!RegExp('track|batch', caseSensitive: false).hasMatch(
            r.said.replaceAll('Batch Number', ''))) {
          throw StateError('N1: nothing says why: ${log.saw}');
        }
      });
      await leave(tester);

      await log.step('SC-GB-005 Add Batch with no product chosen says so and '
          'sends nothing', () async {
        final ({String said, int saved, bool open}) r =
            await addBatch('', 'SGQ$stamp');
        log.saw = 'said "${r.said}"; saved=${r.saved}; dialog open=${r.open}';
        if (r.saved != 0 || !r.open) throw StateError(log.saw!);
        if (!r.said.contains('Choose the product')) {
          throw StateError('N1: the product is not named as missing: '
              '${log.saw}');
        }
      });
      await leave(tester);

      await log.step('SC-GB-003 what a batch row offers', () async {
        await openArea(tester, 'stock', 'inventory/batches');
        final Json? any = await me.newest('batch-serial/batches');
        if (any == null) throw StateError('no batch to select');
        await searchList(tester, '${any['batch_number']}');
        await pickRow(tester, '${any['batch_number']}');
        log.saw = 'actions ${keysStarting(tester, 'selection-')}';
        if (buttonState(tester, 'Open') != 'enabled') {
          throw StateError('a batch cannot be opened');
        }
      });
      await leave(tester);

      }
      // ================= Goods receipt =================
      if (wants('receipt')) {
      await log.step('SC-GX-001 a receipt asks an expiry date only for the '
          'product that tracks one', () async {
        final Json? seed = await me.newest('purchases');
        if (seed == null) throw StateError('no purchase order to copy from');
        final Json f = await me.one('purchases', '${seed['id']}');
        final Json po = (await me.write(
            'POST', '/api/v1/purchases', <String, dynamic>{
          'vendor_id': f['vendor_id'],
          'branch_id': f['branch_id'],
          'warehouse_id': f['warehouse_id'],
          'buyer_id': f['buyer_id'],
          'purchase_date': DateTime.now().toIso8601String().substring(0, 10),
          'lines': <Json>[
            for (final Json p in <Json>[prodMed, prodPlain])
              <String, dynamic>{
                'product_id': p['id'],
                'ordered_quantity': 5,
                'unit_price': '60',
                'purchase_uom_id': piece,
                'inventory_uom_id': piece,
              },
          ],
        })) as Json;
        await apiAct(me, 'purchases', '${po['id']}', 'submit');
        await apiAct(me, 'purchases', '${po['id']}', 'approve');
        final String number = docNumber(await me.one('purchases', '${po['id']}'));
        await openArea(tester, 'buy', 'goodsReceipts/receipts');
        await refreshList(tester);
        await tapNew(tester);
        await pumpFor(tester, const Duration(seconds: 3));
        await chooseFiltered(tester, 'goods-receipt-order', number);
        await pumpFor(tester, const Duration(seconds: 3));
        final Map<int, String> perLine = <int, String>{};
        for (final int index in <int>[0, 1]) {
          final Finder line =
              find.byKey(ValueKey<String>('goods-receipt-line-$index'));
          if (line.evaluate().isNotEmpty) {
            await tester.ensureVisible(line.first);
            await tester.tap(line.first);
            await pumpFor(tester, const Duration(seconds: 1));
          }
          perLine[index] = 'expiry='
              '${keysStarting(tester, 'goods-receipt-expiry-').where((String k) => k.endsWith('-$index')).isNotEmpty}'
              ', mfg='
              '${keysStarting(tester, 'goods-receipt-mfg-').where((String k) => k.endsWith('-$index')).isNotEmpty}';
        }
        log.saw = '$number: medicine line ${perLine[0]}; plain line '
            '${perLine[1]}';
        if (perLine[0] != 'expiry=true, mfg=true') {
          throw StateError('the medicine line asks no expiry: $perLine');
        }
        if (perLine[1] != 'expiry=false, mfg=false') {
          throw StateError('the untracked line asks for dates: $perLine');
        }
      });
      await leave(tester);
      }
    } else if (itHandle.startsWith('gt')) {
      // ---- Roles on TEST01: what each may open and do ----------------
      final Map<String, String> expectNew = <String, String>{
        // FIRM_MANAGER keeps unit sets and products, not goods types.
        'gtmanager': 'types=no sets=yes products=yes',
        'gtsales': 'types=no sets=no products=no',
        'gtstore': 'types=no sets=no products=no',
      };
      String can(String state) => state == 'enabled' ? 'yes' : 'no';
      String got = '';
      await log.step('SC-GT-020 Goods Types for $itHandle: read, never '
          'changed', () async {
        final bool offered = await openTypes();
        String neu = 'absent';
        String use = 'absent';
        String defaults = 'absent';
        if (offered) {
          neu = buttonState(tester, '+ New');
          await searchList(tester, 'MEDICINE');
          await pickRow(tester, 'MEDICINE');
          use = buttonState(tester, 'Stop using');
          defaults = buttonState(tester, 'Set defaults');
        }
        got = 'types=${can(neu)}';
        log.saw = 'offered=$offered, + New $neu, Stop using $use, Set '
            'defaults $defaults';
        if (neu == 'enabled' || use == 'enabled' || defaults == 'enabled') {
          throw StateError('a write is offered: ${log.saw}');
        }
      });
      await leave(tester);
      await log.step('SC-US-020 Unit Sets for $itHandle', () async {
        final bool offered = await openSets();
        final String neu = offered ? buttonState(tester, '+ New') : 'absent';
        got = '$got sets=${can(neu)}';
        log.saw = 'offered=$offered, + New $neu';
      });
      await leave(tester);
      await log.step('SC-GP-020 Products for $itHandle', () async {
        final bool offered = await openProducts();
        final String neu = offered ? buttonState(tester, '+ New') : 'absent';
        got = '$got products=${can(neu)}';
        log.saw = 'offered=$offered, + New $neu; rights "$got", expected '
            '"${expectNew[itHandle]}"';
        if (got != expectNew[itHandle]) {
          throw StateError('rights differ from the seed: ${log.saw}');
        }
      });
      await leave(tester);
    }
    for (final String error in appErrors) {
      if (error.contains('overflowed')) {
        log.defect('1366x768', 'overflow: $error');
      }
    }
    log.finish();
  });
}
