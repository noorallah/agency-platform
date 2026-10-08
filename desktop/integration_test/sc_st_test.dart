import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'cases.dart';
import 'harness.dart';
import 'sc_gt_test.dart'
    show
        leave,
        openArea,
        pickDropdown,
        pressAndRead;

// Stock screens (book: docs/qa/SCREEN_TEST_CASES_INVENTORY.md, ids SC-ST-).
// Run on the fixture firm T10069CWY-S as tradeadmin (every case), then as
// qfmgr (firm manager), qstore (inventory manager), qro (read only), qsmgr and
// qsexe (sales, no stock) for the Role cases. IT_PART names sections:
// lists, actions, adjust, opening, count, views, transfers, repack,
// approvals, settings, round2 (serial units on the move, a used reference;
// in pieces r2xfer, r2doc, r2open, r2ref), backorder. Role users run only the role section.

const String _part = String.fromEnvironment('IT_PART');
bool wants(String section) =>
    _part.isEmpty || _part.split(',').contains(section);

/// Open a Stock tab (`inventory`, `stock-ledger`, ...), once more after a
/// pause if the first try found the menu closed or covered.
Future<void> openStock(WidgetTester tester, String tab) async {
  try {
    await openArea(tester, 'stock', 'inventory/$tab');
  } catch (_) {
    await clean(tester);
    await pumpFor(tester, const Duration(seconds: 2));
    await openArea(tester, 'stock', 'inventory/$tab');
  }
}

/// Leave whatever is open; a dialog that offers no Cancel or Close is
/// dismissed with its close button or the Escape key.
Future<void> clean(WidgetTester tester) async {
  // A drop-down's open menu is a route of its own and covers the page.
  await tester.sendKeyEvent(LogicalKeyboardKey.escape);
  await pumpFor(tester, const Duration(milliseconds: 500));
  await leave(tester);
  for (int i = 0; i < 3 && find.byType(Dialog).evaluate().isNotEmpty; i++) {
    final Finder x = find.byTooltip('Close');
    if (x.evaluate().isNotEmpty) {
      await tester.tap(x.last);
    } else {
      await tester.sendKeyEvent(LogicalKeyboardKey.escape);
    }
    await pumpFor(tester, const Duration(milliseconds: 800));
    final Finder discard = find.text('Discard changes');
    if (discard.evaluate().isNotEmpty) {
      await tester.tap(discard.last);
      await pumpFor(tester, const Duration(milliseconds: 800));
    }
  }
}

/// Tap the last enabled button labelled [label] in the front dialog (a
/// segment of the same name can sit above the real Save button).
Future<void> tapDialogSave(WidgetTester tester, String label) async {
  final Finder dialog = find.byType(Dialog);
  await pumpUntil(tester, dialog, waitingFor: 'a dialog');
  final Finder b = find.descendant(
      of: dialog.last,
      matching: find.ancestor(
          of: find.text(label),
          matching: find.byWidgetPredicate(
              (Widget w) => w is ButtonStyleButton && w.onPressed != null)));
  await pumpUntil(tester, b, waitingFor: 'dialog button $label');
  await tester.ensureVisible(b.last);
  await tester.tap(b.last);
  await pumpFor(tester, const Duration(milliseconds: 800));
}

/// Press, then answer any confirmation the press raises, and say what the
/// screen announced meanwhile.
Future<String> pressWatch(Future<void> Function() press,
    WidgetTester tester) async {
  await press();
  return watch(tester, seconds: 6);
}

/// The selection bar's button for command [id], else the toolbar's own.
Finder _commandFinder(String id) {
  final Finder bar = find.byKey(ValueKey<String>('selection-$id'));
  return bar.evaluate().isNotEmpty
      ? bar
      : find.byKey(ValueKey<String>('toolbar-command-$id'));
}

/// Open the list's "+ filter" panel.
Future<void> openFilters(WidgetTester tester) async {
  await tapKey(tester, 'phase2-filters');
  await pumpFor(tester, const Duration(seconds: 1));
}

/// Press the toolbar command [id] (labelled [label]), on the line or under "...".
Future<void> command(WidgetTester tester, String id, String label) async {
  final Finder f = _commandFinder(id);
  if (f.evaluate().isNotEmpty) {
    await tester.ensureVisible(f.first);
    await tester.tap(f.first);
    await pumpFor(tester, const Duration(milliseconds: 900));
    return;
  }
  await tapMore(tester, label);
}

/// enabled / disabled / absent for the toolbar command [id].
Future<String> commandState(WidgetTester tester, String id, String label) async {
  final Finder f = _commandFinder(id);
  if (f.evaluate().isNotEmpty) {
    final Widget w = tester.widget(f.first);
    if (w is ButtonStyleButton) {
      return w.onPressed != null ? 'enabled' : 'disabled';
    }
    final Finder inner = find.descendant(
        of: f.first,
        matching: find.byWidgetPredicate((Widget x) => x is ButtonStyleButton));
    if (inner.evaluate().isNotEmpty) {
      return (tester.widget(inner.first) as ButtonStyleButton).onPressed != null
          ? 'enabled'
          : 'disabled';
    }
    return 'present';
  }
  return moreState(tester, label);
}

/// Select the grid row naming [code] (not [not]) after searching for it.
Future<void> pickProduct(WidgetTester tester, String code,
    {String? not, bool search = true, String? at = 'MAIN'}) async {
  if (search) await searchList(tester, code);
  final Finder row = find.byWidgetPredicate((Widget w) =>
      w is Text &&
      (w.data ?? '').contains(code) &&
      (not == null || !(w.data ?? '').contains(not)));
  await pumpUntil(tester, row, waitingFor: 'a row showing $code');
  int pick = 0;
  if (at != null) {
    final Finder where = find.text(at);
    for (int i = 0; i < row.evaluate().length; i++) {
      final double y = tester.getCenter(row.at(i)).dy;
      bool level = false;
      for (int j = 0; j < where.evaluate().length; j++) {
        if ((tester.getCenter(where.at(j)).dy - y).abs() < 6) level = true;
      }
      if (level) {
        pick = i;
        break;
      }
    }
  }
  await tester.tap(row.at(pick));
  await pumpFor(tester, const Duration(milliseconds: 700));
}

/// Type into the box whose label starts with [label] ("Code" or "Code *").
Future<void> typeField(WidgetTester tester, String label, String text) async {
  final Finder box = find.ancestor(
      of: find.byWidgetPredicate(
          (Widget w) => w is Text && (w.data ?? '').startsWith(label)),
      matching: find.byType(TextField));
  await pumpUntil(tester, box, waitingFor: 'field "$label"');
  await tester.ensureVisible(box.last);
  await tester.enterText(box.last, text);
  await pumpFor(tester, const Duration(milliseconds: 300));
}

/// Answer an askForReason prompt that is open, and read what follows.
Future<String> answerReason(WidgetTester tester,
    {String reason = 'screen case', int seconds = 5}) async {
  await pumpFor(tester, const Duration(milliseconds: 900));
  final Finder dialog = find.byType(Dialog);
  if (dialog.evaluate().isNotEmpty) {
    final Finder box =
        find.descendant(of: dialog.last, matching: find.byType(EditableText));
    if (box.evaluate().isNotEmpty) {
      await tester.enterText(box.first, reason);
      await pumpFor(tester, const Duration(milliseconds: 300));
    }
    final Finder yes = find.descendant(
        of: dialog.last,
        matching: find.byWidgetPredicate(
            (Widget w) => w is FilledButton && w.onPressed != null));
    if (yes.evaluate().isNotEmpty) await tester.tap(yes.last);
  }
  return watch(tester, confirm: false, seconds: seconds);
}

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('ST: stock cases ($itHandle)', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1366, 768);
    tester.view.devicePixelRatio = 1;
    final FlowLog log = FlowLog('st-$itHandle');
    final String stamp = DateTime.now()
        .millisecondsSinceEpoch
        .toRadixString(36)
        .toUpperCase()
        .substring(3);
    final Server me = await Server.connect();
    final String today = DateTime.now().toIso8601String().substring(0, 10);
    final bool admin = itHandle == 'tradeadmin';

    Future<Json> productByCode(String code) async {
      for (final dynamic p
          in (await me.get('/api/v1/products?page_size=100')) as List<dynamic>) {
        if ((p as Json)['code'] == code) return p;
      }
      throw StateError('product $code is not on the firm');
    }

    late final Json pN;
    late final Json pN2;
    late final Json whMain;
    late final Json whTwo;
    late final String branchId;
    if (admin) {
      pN = await productByCode('INVSCR-N');
      pN2 = await productByCode('INVSCR-N2');
      final List<dynamic> whs =
          (await me.get('/api/v1/warehouses?page_size=50')) as List<dynamic>;
      whMain = whs.firstWhere((dynamic w) => (w as Json)['code'] == 'MAIN') as Json;
      whTwo = whs.firstWhere((dynamic w) => (w as Json)['code'] == 'QW2') as Json;
      branchId = '${whMain['branch_id']}';
    }

    Future<Json?> invRow(Json product, Json wh) async {
      final dynamic rows = await me.get(
          '/api/v1/inventory?page_size=100&product_id=${product['id']}');
      for (final dynamic r in rows as List<dynamic>) {
        if ((r as Json)['warehouse_id'] == wh['id'] &&
            (r['batch_id'] == null)) {
          return r;
        }
      }
      return null;
    }

    Future<double> onHand(Json product, Json wh) async =>
        num2((await invRow(product, wh))?['current_quantity'] ?? 0);

    Future<int> movements() => me.total('/api/v1/inventory/transactions');

    Future<void> api(String path, Json body) async {
      await me.write('POST', path, body);
    }

    Future<void> adjustApi(Json product, double qty, {Json? wh}) => api(
        '/api/v1/inventory/adjustments', <String, dynamic>{
      'branch_id': branchId,
      'warehouse_id': (wh ?? whMain)['id'],
      'product_id': product['id'],
      'quantity': qty,
      'transaction_date': today,
      'remarks': 'screen cases: set-up',
    });

    // Warm the stock a case draws on before the app starts.
    if (admin) {
      for (final Json p in <Json>[pN, pN2]) {
        final double have = await onHand(p, whMain);
        if (have < 60) await adjustApi(p, 60 - have);
      }
    }

    await startAndSignIn(tester);
    collectAppErrors();
    int seenErrors = 0;
    void overflow(String where) {
      final List<String> fresh = appErrors.skip(seenErrors).toList();
      seenErrors = appErrors.length;
      final List<String> bad = <String>[
        for (final String e in fresh)
          if (e.contains('overflow') || e.contains('RenderFlex')) e,
      ];
      if (bad.isNotEmpty) log.info('OVERFLOW', '$where: ${bad.first}');
      if (fresh.length > bad.length) {
        log.info('APPERROR', '$where: ${fresh.where((String e) => !bad.contains(e)).first}');
      }
    }

    bool dialogOpen(String title) => screenHas(tester, title);

    /// Judge a refusal inside a dialog the way the book's N1 to N3 do.
    Future<String> refuse(
      String title,
      Future<void> Function() press, {
      String? typed,
      Future<int> Function()? count,
      String? mustSay,
    }) async {
      final Future<int> Function() counter = count ?? movements;
      final int before = await counter();
      final String said = await pressAndRead(tester, press, seconds: 4);
      final bool open = dialogOpen(title);
      final int after = await counter();
      final String saw = 'open=$open, saved=${after - before}, said="$said"';
      final List<String> faults = <String>[
        if (said.isEmpty) 'N1: nothing on screen says why',
        if (mustSay != null &&
            !said.toLowerCase().contains(mustSay.toLowerCase()))
          'N1: the sentence does not say "$mustSay"',
        if (!open) 'N2: the dialog closed',
        if (open && typed != null && !screenHasTyped(tester, typed))
          'N2: typed "$typed" is gone',
        if (after != before) 'N3: ${after - before} record(s) saved',
      ];
      if (faults.isNotEmpty) {
        throw StateError('${faults.join('; ')} [$saw]');
      }
      return saw;
    }

    /// Open the stock dialog [command] on the row of [code].
    Future<void> openAction(String id, String label, String code,
        {String? not}) async {
      await openStock(tester, 'inventory');
      await pickProduct(tester, code, not: not);
      await command(tester, id, label);
      await pumpUntil(tester, find.byType(Dialog), waitingFor: 'the $label dialog');
    }

    // ================= Role cases for the other users =================
    if (!admin) {
      final Map<String, List<String>> menu = await offeredMenu(tester);
      // ignore: avoid_print
      print('FLOW: MENU [$itHandle] ${menu.entries.map((MapEntry<String, List<String>> e) => '${e.key}=${e.value.join(',')}').join('; ')}');
      final bool stockArea = menu.containsKey('stock');
      final List<String> stockItems = menu['stock'] ?? <String>[];
      final ({int status, String text}) listApi =
          await me.attempt('GET', '/api/v1/inventory?page_size=1', null);
      final ({int status, String text}) adjApi =
          await me.attempt('POST', '/api/v1/inventory/adjustments', <String, dynamic>{});
      final String id = <String, String>{
        'qfmgr': 'SC-ST-070 firm manager',
        'qstore': 'SC-ST-071 inventory manager',
        'qro': 'SC-ST-072 read only',
        'qsmgr': 'SC-ST-073 sales manager',
        'qsexe': 'SC-ST-073 sales executive',
      }[itHandle] ?? 'SC-ST-07x $itHandle';
      await log.step('$id: what Stock offers', () async {
        log.saw = 'stock area offered=$stockArea, items=$stockItems; '
            'inventory list API ${listApi.status}; adjustment API (empty body) '
            '${adjApi.status}';
        final bool mayView = listApi.status == 200;
        if (mayView != stockArea) {
          throw StateError('menu and server disagree: ${log.saw}');
        }
      });
      if (stockArea) {
        await log.step('$id: Inventory buttons for this role', () async {
          await openStock(tester, 'inventory');
          await searchList(tester, 'INVSCR-N2');
          await pickProduct(tester, 'INVSCR-N2');
          final Map<String, String> s = <String, String>{
            'Transfer': await commandState(tester, 'transfer', 'Transfer'),
            'Write off': await commandState(tester, 'write-off', 'Write off'),
            'Quarantine':
                await commandState(tester, 'quarantine', 'Quarantine'),
          };
          overflow('Inventory ($itHandle)');
          log.saw = 'rows readable; buttons $s; adjustment API ${adjApi.status}';
          final bool mayAdjust = adjApi.status != 403;
          final bool anyOn = s.values.any((String v) => v == 'enabled');
          if (mayAdjust != anyOn) {
            throw StateError('screen offers $s but the server answers '
                '${adjApi.status} to an adjustment');
          }
        });
        for (final String tab in <String>[
          'stock-ledger',
          'transactions',
          'stock-summary',
          'opening-stock',
          'physical-counts',
          'stock-transfers',
          'repacking',
          'adjustment-approvals',
          'batches',
          'lots',
          'serials',
          'expiry-monitor',
        ]) {
          if (!stockItems.contains('inventory/$tab')) {
            log.info(id, '$tab is not offered');
            continue;
          }
          final bool tracking = const <String>[
            'batches',
            'lots',
            'serials',
            'expiry-monitor'
          ].contains(tab);
          final String stepId =
              tracking ? id.replaceFirst('SC-ST-07', 'SC-BS-04') : id;
          await log.step('$stepId: $tab opens', () async {
            await openStock(tester, tab);
            overflow(tab);
            final bool failed = screenHas(tester, 'Unable to load') ||
                screenHas(tester, 'failed to render');
            log.saw = 'texts ${textOnScreen(tester).take(40).join(' | ')}';
            if (failed) throw StateError('error panel on screen: ${log.saw}');
          });
        }
        await log.step('$id: write buttons on Opening stock, Transfers, Repacking',
            () async {
          final Map<String, String> seen = <String, String>{};
          if (stockItems.contains('inventory/opening-stock')) {
            await openStock(tester, 'opening-stock');
            seen['New opening stock'] = buttonState(tester, 'New');
          }
          if (stockItems.contains('inventory/stock-transfers')) {
            await openStock(tester, 'stock-transfers');
            seen['New transfer'] = buttonState(tester, 'New transfer');
          }
          if (stockItems.contains('inventory/repacking')) {
            await openStock(tester, 'repacking');
            seen['New repack'] = buttonState(tester, 'New repack');
          }
          if (stockItems.contains('inventory/batches')) {
            await openStock(tester, 'batches');
            seen['New batch'] = buttonState(tester, 'New') == 'enabled' ||
                    buttonState(tester, '+ New') == 'enabled'
                ? 'enabled'
                : 'absent or disabled';
          }
          log.saw = '$seen; adjustment API ${adjApi.status}';
          final bool mayWrite = adjApi.status != 403;
          for (final MapEntry<String, String> e in seen.entries) {
            if (!mayWrite && e.value == 'enabled') {
              throw StateError('${e.key} is offered to a role the server '
                  'refuses: $seen');
            }
          }
        });
      }
      log.finish();
      return;
    }

    // ===================================================================
    // Administrator: the whole book
    // ===================================================================

    // ---------------- lists -------------------------------------------
    if (wants('lists')) {
      await log.step('SC-ST-001 Inventory list opens with its columns',
          () async {
        await openStock(tester, 'inventory');
        await refreshList(tester);
        final List<String> missing = <String>[
          for (final String h in <String>[
            'Product', 'Branch', 'Warehouse', 'Current', 'Available', 'Reserved', 'Status'
          ])
            if (!screenHas(tester, h)) h,
        ];
        overflow('Inventory');
        log.saw = 'columns present; rows of INVSCR visible=${screenHas(tester, 'INVSCR')}';
        if (missing.isNotEmpty) throw StateError('not on screen: $missing');
      });

      await log.step('SC-ST-002 search narrows the list to one product',
          () async {
        await openStock(tester, 'inventory');
        await searchList(tester, 'INVSCR-S');
        final bool mine = screenHas(tester, 'INVSCR-S');
        final bool other = screenHas(tester, 'INVSCR-B') ||
            screenHas(tester, 'T10069CWY-DET');
        log.saw = 'INVSCR-S shown=$mine, other products shown=$other';
        await searchList(tester, '');
        if (!mine || other) throw StateError(log.saw!);
      });

      await log.step('SC-ST-003 a stock row opens its details', () async {
        await openStock(tester, 'inventory');
        await pickProduct(tester, 'INVSCR-S');
        final String said = await pressAndRead(
            tester, () => tapButton(tester, 'Open'));
        overflow('Inventory details');
        log.saw = 'after Open: ${said.length > 300 ? said.substring(0, 300) : said}';
        final bool open = find.byType(Dialog).evaluate().isNotEmpty;
        if (!open) throw StateError('no details dialog opened: ${log.saw}');
      });
      await clean(tester);

    }
    if (wants('presets')) {
      await log.step('SC-ST-004 the low / out of stock presets filter the list',
          () async {
        await openStock(tester, 'inventory');
        await openFilters(tester);
        final Finder preset = find.text('Preset: Out of stock');
        await pumpUntil(tester, preset, waitingFor: 'the Out of stock preset');
        await tester.tap(preset.first);
        await pumpFor(tester, const Duration(seconds: 1));
        await tapButton(tester, 'Apply');
        await pumpFor(tester, const Duration(seconds: 2));
        final bool mine = screenHas(tester, 'INVSCR-N');
        log.saw = 'out-of-stock preset applied; INVSCR-N (60+ on hand) shown=$mine';
        // The filter is remembered for the user: put it back.
        await tapButton(tester, 'Clear');
        await tapButton(tester, 'Apply');
        await pumpFor(tester, const Duration(seconds: 2));
        if (mine) throw StateError('a product with stock is listed as out of stock');
      });
      await clean(tester);
    }

    // ---------------- actions: transfer / write off / quarantine -----------
    if (wants('xfer')) {
      await log.step('SC-ST-005 Transfer 3 to the second warehouse', () async {
        final double before2 = await onHand(pN, whTwo);
        final double beforeMain = await onHand(pN, whMain);
        final int mv = await movements();
        await openAction('transfer', 'Transfer', 'INVSCR-N', not: 'INVSCR-N2');
        await typeLabelled(tester, 'Quantity', '3');
        await pickDropdown(tester, 'Move it to', 'QW2');
        await typeLabelled(tester, 'Reference (optional)', 'TRF$stamp');
        final String said = await pressAndRead(
            tester, () => tapDialogSave(tester, 'Transfer'));
        await pumpFor(tester, const Duration(seconds: 2));
        final double after2 = await onHand(pN, whTwo);
        final double afterMain = await onHand(pN, whMain);
        overflow('Transfer dialog');
        log.saw = 'said "$said"; QW2 $before2 -> $after2; MAIN $beforeMain -> '
            '$afterMain; movements +${await movements() - mv}';
        if (!sameMoney(after2, before2 + 3) || !sameMoney(afterMain, beforeMain - 3)) {
          throw StateError(log.saw!);
        }
        if (dialogOpen('Transfer stock')) throw StateError('dialog stayed open');
      });
      await clean(tester);

      await log.step('SC-ST-006 the dialog says what is available and that no journal is written',
          () async {
        await openAction('transfer', 'Transfer', 'INVSCR-N', not: 'INVSCR-N2');
        final bool avail = screenHas(tester, 'available here');
        final bool note = screenHas(tester, 'writes no journal');
        log.saw = 'available line=$avail, journal note=$note';
        await clean(tester);
        if (!avail || !note) throw StateError(log.saw!);
      });

      for (final ({String id, String q, String why}) c in <({String id, String q, String why})>[
        (id: 'SC-ST-007', q: '', why: 'quantity left empty'),
        (id: 'SC-ST-008', q: '0', why: 'quantity 0'),
        (id: 'SC-ST-009', q: '9999999', why: 'quantity above what is held'),
      ]) {
        await log.step('${c.id} Transfer with ${c.why} is refused', () async {
          await openAction('transfer', 'Transfer', 'INVSCR-N', not: 'INVSCR-N2');
          await pickDropdown(tester, 'Move it to', 'QW2');
          if (c.q.isNotEmpty) await typeLabelled(tester, 'Quantity', c.q);
          log.saw = await refuse('Transfer stock',
              () => tapDialogSave(tester, 'Transfer'),
              typed: c.q.isEmpty ? null : c.q);
        });
        await clean(tester);
      }

      await log.step('SC-ST-010 Transfer with no destination is refused',
          () async {
        await openAction('transfer', 'Transfer', 'INVSCR-N', not: 'INVSCR-N2');
        await typeLabelled(tester, 'Quantity', '1');
        log.saw = await refuse('Transfer stock',
            () => tapDialogSave(tester, 'Transfer'),
            typed: '1', mustSay: 'warehouse');
      });
      await clean(tester);

      await log.step('SC-ST-011 a one-character reference is refused',
          () async {
        await openAction('transfer', 'Transfer', 'INVSCR-N', not: 'INVSCR-N2');
        await typeLabelled(tester, 'Quantity', '1');
        await pickDropdown(tester, 'Move it to', 'QW2');
        await typeLabelled(tester, 'Reference (optional)', 'X');
        log.saw = await refuse('Transfer stock',
            () => tapDialogSave(tester, 'Transfer'),
            typed: 'X', mustSay: 'reference');
      });
      await clean(tester);

    }
    if (wants('woff')) {
      await log.step('SC-ST-012 Write off 1 for Damage', () async {
        final double before = await onHand(pN2, whMain);
        await openAction('write-off', 'Write off', 'INVSCR-N2');
        await typeLabelled(tester, 'Quantity', '1');
        await typeLabelled(tester, 'Reference (optional)', 'WO$stamp');
        final String said = await pressAndRead(
            tester, () => tapDialogSave(tester, 'Write off'));
        await pumpFor(tester, const Duration(seconds: 2));
        final double after = await onHand(pN2, whMain);
        final Json? ledger = await rowWhereRef('WO$stamp');
        overflow('Write off dialog');
        log.saw = 'said "$said"; on hand $before -> $after; ledger type '
            '${ledger?['transaction_type']}';
        if (!sameMoney(after, before - 1)) throw StateError(log.saw!);
        if (dialogOpen('Write off stock')) throw StateError('dialog stayed open');
      });
      await clean(tester);

      await log.step('SC-ST-013 Write off with quantity 0 is refused', () async {
        await openAction('write-off', 'Write off', 'INVSCR-N2');
        await typeLabelled(tester, 'Quantity', '0');
        log.saw = await refuse('Write off stock',
            () => tapDialogSave(tester, 'Write off'), typed: '0');
      });
      await clean(tester);

      await log.step('SC-ST-014 Write off of more than is held is refused',
          () async {
        await openAction('write-off', 'Write off', 'INVSCR-N2');
        await typeLabelled(tester, 'Quantity', '99999');
        log.saw = await refuse('Write off stock',
            () => tapDialogSave(tester, 'Write off'),
            typed: '99999', mustSay: 'cannot be moved');
      });
      await clean(tester);

      await log.step(
          'SC-ST-015 Write off for a free gift without a customer is refused',
          () async {
        await openAction('write-off', 'Write off', 'INVSCR-N2');
        await typeLabelled(tester, 'Quantity', '1');
        await pickDropdown(tester, 'Reason', 'customer');
        log.saw = await refuse('Write off stock',
            () => tapDialogSave(tester, 'Write off'),
            typed: '1', mustSay: 'customer');
      });
      await clean(tester);

      await log.step(
          'SC-ST-016 a write-off the server refuses keeps its words and the typing',
          () async {
        // The row is read with 60+ available; another user then takes most of
        // it, so the dialog's own check passes and only the server can refuse.
        final double have = await onHand(pN2, whMain);
        await openAction('write-off', 'Write off', 'INVSCR-N2');
        await adjustApi(pN2, -(have - 2));
        try {
          await typeLabelled(tester, 'Quantity', '${(have - 5).floor()}');
          await typeLabelled(tester, 'Remarks', 'keep-me-$stamp');
          log.saw = await refuse('Write off stock',
              () => tapDialogSave(tester, 'Write off'),
              typed: 'keep-me-$stamp');
        } finally {
          await adjustApi(pN2, have - 2);
        }
      });
      await clean(tester);

    }
    if (wants('quar')) {
      await log.step('SC-ST-017 Quarantine: hold back 2', () async {
        await openAction('quarantine', 'Quarantine', 'INVSCR-N', not: 'INVSCR-N2');
        await typeLabelled(tester, 'Quantity', '2');
        await typeLabelled(tester, 'Reference (optional)', 'QH$stamp');
        final String said = await pressAndRead(
            tester, () => tapDialogSave(tester, 'Hold back'));
        await pumpFor(tester, const Duration(seconds: 2));
        final Json? row = await invRow(pN, whMain);
        log.saw = 'said "$said"; quarantine_quantity ${row?['quarantine_quantity']}, '
            'current ${row?['current_quantity']}, available ${row?['available_quantity']}';
        if (num2(row?['quarantine_quantity']) < 2) throw StateError(log.saw!);
      });
      await clean(tester);

      await log.step('SC-ST-018 Quarantine: release 2', () async {
        await openAction('quarantine', 'Quarantine', 'INVSCR-N', not: 'INVSCR-N2');
        await tester.tap(find.text('Release').last);
        await pumpFor(tester, const Duration(milliseconds: 600));
        await typeLabelled(tester, 'Quantity', '2');
        await typeLabelled(tester, 'Reference (optional)', 'QR$stamp');
        final String said = await pressAndRead(
            tester, () => tapDialogSave(tester, 'Release'));
        await pumpFor(tester, const Duration(seconds: 2));
        final Json? row = await invRow(pN, whMain);
        log.saw = 'said "$said"; quarantine_quantity ${row?['quarantine_quantity']}';
        if (num2(row?['quarantine_quantity']) != 0) throw StateError(log.saw!);
      });
      await clean(tester);

      await log.step('SC-ST-019 releasing more than is held is refused',
          () async {
        await openAction('quarantine', 'Quarantine', 'INVSCR-N', not: 'INVSCR-N2');
        await tester.tap(find.text('Release').last);
        await pumpFor(tester, const Duration(milliseconds: 600));
        await typeLabelled(tester, 'Quantity', '5');
        log.saw = await refuse('Quarantine stock',
            () => tapDialogSave(tester, 'Release'), typed: '5');
      });
      await clean(tester);

      await log.step('SC-ST-020 holding back more than is available is refused',
          () async {
        await openAction('quarantine', 'Quarantine', 'INVSCR-N', not: 'INVSCR-N2');
        await typeLabelled(tester, 'Quantity', '9999999');
        log.saw = await refuse('Quarantine stock',
            () => tapDialogSave(tester, 'Hold back'), typed: '9999999');
      });
      await clean(tester);
    }

    // ---------------- adjustments (Transactions) ---------------------------
    if (wants('adjust')) {
      Future<void> openAdjust() async {
        await openStock(tester, 'transactions');
        await tapNew(tester);
        await pumpUntil(tester, find.text('New inventory adjustment'),
            waitingFor: 'the adjustment dialog');
      }

      await log.step('SC-ST-021 Transactions list opens with its columns',
          () async {
        await openStock(tester, 'transactions');
        overflow('Transactions');
        final List<String> missing = <String>[
          for (final String h in <String>['Date', 'Type', 'Reference', 'Product', 'Quantity'])
            if (!screenHas(tester, h)) h,
        ];
        log.saw = 'columns present';
        if (missing.isNotEmpty) throw StateError('not on screen: $missing');
      });

      await log.step('SC-ST-022 New adjustment +5 on a plain product', () async {
        final double before = await onHand(pN2, whMain);
        await openAdjust();
        await pickDropdown(tester, 'Warehouse', 'MAIN');
        await pickDropdown(tester, 'Product', 'INVSCR-N2');
        await typeLabelled(tester, 'Quantity (+ or - value)', '5');
        await typeLabelled(tester, 'Reference (optional)', 'ADJ$stamp');
        final String said = await pressAndRead(
            tester, () => tapDialogSave(tester, 'Post adjustment'));
        await pumpFor(tester, const Duration(seconds: 2));
        final double after = await onHand(pN2, whMain);
        overflow('Adjustment dialog');
        final bool listed = screenHas(tester, 'ADJ$stamp');
        log.saw = 'said "$said"; on hand $before -> $after; reference on the '
            'list=$listed';
        if (!sameMoney(after, before + 5)) throw StateError(log.saw!);
        if (!listed) throw StateError('the new adjustment is not on the list: ${log.saw}');
      });
      await clean(tester);

      await log.step('SC-ST-023 adjustment with the quantity empty is refused',
          () async {
        await openAdjust();
        log.saw = await refuse('New inventory adjustment',
            () => tapDialogSave(tester, 'Post adjustment'),
            mustSay: 'non-zero');
      });
      await clean(tester);

      await log.step('SC-ST-024 adjustment of 0 is refused', () async {
        await openAdjust();
        await typeLabelled(tester, 'Quantity (+ or - value)', '0');
        log.saw = await refuse('New inventory adjustment',
            () => tapDialogSave(tester, 'Post adjustment'),
            typed: '0', mustSay: 'non-zero');
      });
      await clean(tester);

      await log.step(
          'SC-ST-025 an adjustment taking stock below zero is refused by the server',
          () async {
        final double had = await onHand(pN2, whTwo);
        await openAdjust();
        await pickDropdown(tester, 'Warehouse', 'QW2');
        await pickDropdown(tester, 'Product', 'INVSCR-N2');
        await typeLabelled(tester, 'Quantity (+ or - value)', '${-(had + 50)}');
        await typeLabelled(tester, 'Remarks', 'keep-$stamp');
        try {
          log.saw = await refuse('New inventory adjustment',
              () => tapDialogSave(tester, 'Post adjustment'),
              typed: 'keep-$stamp');
        } finally {
          final double now = await onHand(pN2, whTwo);
          if (now != had) await adjustApi(pN2, had - now, wh: whTwo);
        }
      });
      await clean(tester);

      await log.step(
          'SC-ST-026 adjusting a batch-tracked product asks which batch',
          () async {
        await openAdjust();
        await pickDropdown(tester, 'Product', 'INVSCR-B');
        await pumpFor(tester, const Duration(seconds: 1));
        final bool batchBox = screenHas(tester, 'Batch');
        log.saw = 'a Batch box is offered=$batchBox';
        await clean(tester);
        if (!batchBox) {
          throw StateError('no way to name the batch for a batch-tracked '
              'product: the adjustment would land on an untracked row '
              '(D-STK-1 says it must name one)');
        }
      });
      await clean(tester);

      await log.step('SC-ST-027 Evidence is offered only with a movement picked',
          () async {
        await openStock(tester, 'transactions');
        final String none = await commandState(tester, 'evidence', 'Evidence');
        await pickProduct(tester, 'INVSCR');
        final String some = await commandState(tester, 'evidence', 'Evidence');
        log.saw = 'no row: $none; row picked: $some';
        if (none == 'enabled' || some != 'enabled') throw StateError(log.saw!);
      });
      await clean(tester);
    }

    // ---------------- opening stock ------------------------------------------
    if (wants('opening')) {
      Future<void> openOpening() async {
        await openStock(tester, 'opening-stock');
        await tapNew(tester);
        await pumpUntil(tester, find.text('New opening stock'),
            waitingFor: 'the opening stock dialog');
        await pickDropdown(tester, 'Warehouse', 'MAIN');
      }

      await log.step('SC-ST-028 Opening Stock list opens', () async {
        await openStock(tester, 'opening-stock');
        overflow('Opening Stock');
        final bool cols = screenHas(tester, 'Reference') && screenHas(tester, 'Status');
        log.saw = 'columns present=$cols; texts ${textOnScreen(tester).take(14).join(' | ')}';
        if (!cols) throw StateError(log.saw!);
      });

      await log.step('SC-ST-029 New opening stock saved as a draft', () async {
        await openOpening();
        await typeLabelled(tester, 'Reference', 'OS$stamp');
        await pickDropdown(tester, 'Product', 'INVSCR-N');
        await typeLabelled(tester, 'Quantity', '7');
        await typeLabelled(tester, 'Unit cost', '60');
        final String said =
            await pressAndRead(tester, () => tapDialogSave(tester, 'Save'));
        await pumpFor(tester, const Duration(seconds: 2));
        overflow('Opening stock dialog');
        final dynamic rows = await me.get('/api/v1/inventory/opening-stock?page_size=100');
        final Json? mine = (rows as List<dynamic>).cast<Json?>().firstWhere(
            (Json? r) => r?['reference_number'] == 'OS$stamp',
            orElse: () => null);
        log.saw = 'said "$said"; server status ${mine?['status']}; on list='
            '${screenHas(tester, 'OS$stamp')}';
        if (mine == null) throw StateError('nothing saved: ${log.saw}');
        if (dialogOpen('New opening stock')) throw StateError('dialog stayed open');
      });
      await clean(tester);

      await log.step('SC-ST-030 Post draft makes the opening stock real',
          () async {
        final double before = await onHand(pN, whMain);
        await openStock(tester, 'opening-stock');
        await pickProduct(tester, 'OS$stamp');
        final String said = await pressWatch(
            () => command(tester, 'post-draft', 'Post draft'), tester);
        await pumpFor(tester, const Duration(seconds: 2));
        final double after = await onHand(pN, whMain);
        log.saw = 'said "$said"; on hand $before -> $after';
        if (!sameMoney(after, before + 7)) throw StateError(log.saw!);
      });
      await clean(tester);

      await log.step('SC-ST-031 a line with no quantity is refused', () async {
        await openOpening();
        await typeLabelled(tester, 'Reference', 'OQ$stamp');
        await pickDropdown(tester, 'Product', 'INVSCR-N');
        log.saw = await refuse('New opening stock',
            () => tapDialogSave(tester, 'Save'),
            typed: 'OQ$stamp',
            count: () => me.total('/api/v1/inventory/opening-stock'),
            mustSay: 'quantity');
      });
      await clean(tester);

      await log.step('SC-ST-032 a batch-tracked product without a batch number is refused',
          () async {
        await openOpening();
        await typeLabelled(tester, 'Reference', 'OB$stamp');
        await pickDropdown(tester, 'Product', 'INVSCR-B');
        await typeLabelled(tester, 'Quantity', '3');
        await typeLabelled(tester, 'Unit cost', '60');
        log.saw = await refuse('New opening stock',
            () => tapDialogSave(tester, 'Save'),
            typed: 'OB$stamp',
            count: () => me.total('/api/v1/inventory/opening-stock'),
            mustSay: 'batch');
      });
      await clean(tester);

      await log.step('SC-ST-033 a reference already used is refused by the server',
          () async {
        await openOpening();
        await typeLabelled(tester, 'Reference', 'OS$stamp');
        await pickDropdown(tester, 'Product', 'INVSCR-N');
        await typeLabelled(tester, 'Quantity', '1');
        await typeLabelled(tester, 'Unit cost', '60');
        log.saw = await refuse('New opening stock',
            () => tapDialogSave(tester, 'Save'),
            typed: 'OS$stamp',
            count: () => me.total('/api/v1/inventory/opening-stock'));
      });
      await clean(tester);

      await log.step('SC-ST-034 a line with no cost warns once, then keeps zero on a second press',
          () async {
        await openOpening();
        await typeLabelled(tester, 'Reference', 'OZ$stamp');
        await pickDropdown(tester, 'Product', 'INVSCR-N2');
        await typeLabelled(tester, 'Quantity', '1');
        await typeLabelled(tester, 'Unit cost', '0');
        final int before = await me.total('/api/v1/inventory/opening-stock');
        final String first =
            await pressAndRead(tester, () => tapDialogSave(tester, 'Save'));
        final int mid = await me.total('/api/v1/inventory/opening-stock');
        await pressAndRead(tester, () => tapDialogSave(tester, 'Save'));
        final int after = await me.total('/api/v1/inventory/opening-stock');
        log.saw = 'first press said "$first" (saved ${mid - before}); second '
            'saved ${after - mid}';
        if (mid != before || after != mid + 1 || !first.contains('valued at zero')) {
          throw StateError(log.saw!);
        }
      });
      await clean(tester);
    }

    // ---------------- physical count ------------------------------------------
    if (wants('count')) {
      Future<void> openCount() async {
        await openStock(tester, 'physical-counts');
        await tapButtonStarting(tester, '+ New');
        await pumpUntil(tester, find.text('Open a count'),
            waitingFor: 'the Open a count dialog');
        await pickDropdown(tester, 'Warehouse', 'MAIN');
      }

      Future<void> countInRow(String code, String value) async {
        final Finder anchor = find.byWidgetPredicate((Widget w) =>
            w is Text && (w.data ?? '').contains(code) && !(w.data ?? '').contains('${code}2'));
        await pumpUntil(tester, anchor, waitingFor: 'the $code line');
        await tester.ensureVisible(anchor.first);
        await pumpFor(tester, const Duration(milliseconds: 300));
        final double y = tester.getCenter(anchor.first).dy;
        final Finder boxes = find.byType(TextField);
        TextField? best;
        double gap = 1e9;
        Finder? bestFinder;
        for (int i = 0; i < boxes.evaluate().length; i++) {
          final double d = (tester.getCenter(boxes.at(i)).dy - y).abs();
          if (d < gap) {
            gap = d;
            best = tester.widget<TextField>(boxes.at(i));
            bestFinder = boxes.at(i);
          }
        }
        if (best == null || gap > 20) throw StateError('no Counted box level with $code');
        await tester.enterText(bestFinder!, value);
        await pumpFor(tester, const Duration(milliseconds: 300));
      }

      await log.step('SC-ST-035 Physical Count list opens', () async {
        await openStock(tester, 'physical-counts');
        overflow('Physical Count');
        final bool cols = screenHas(tester, 'Count Number') || screenHas(tester, 'No counts yet');
        log.saw = 'texts ${textOnScreen(tester).take(16).join(' | ')}';
        if (!cols) throw StateError(log.saw!);
      });

      await log.step('SC-ST-036 Open a count, count one line, save, post', () async {
        final double before = await onHand(pN, whMain);
        await openCount();
        final String opened =
            await pressAndRead(tester, () => tapDialogSave(tester, 'Open'));
        await pumpUntil(tester, find.text('Counted'), waitingFor: 'the count sheet');
        overflow('Count sheet');
        final String target = '${before - 1}';
        await countInRow('INVSCR-N', target);
        final String diff = textOnScreen(tester).where((String t) => t.startsWith('-1')).join(',');
        final String saved = await pressAndRead(
            tester, () => tapButton(tester, 'Save progress'));
        final String posted = await pressAndRead(tester, () async {
          await tapButton(tester, 'Post count');
          await pumpFor(tester, const Duration(milliseconds: 800));
          await tapDialogSave(tester, 'Post count');
        }, seconds: 6);
        await pumpFor(tester, const Duration(seconds: 2));
        final double after = await onHand(pN, whMain);
        log.saw = 'opened: "$opened"; difference shown "$diff"; saved "$saved"; '
            'posted "$posted"; on hand $before -> $after';
        if (!sameMoney(after, before - 1)) throw StateError(log.saw!);
      });
      await clean(tester);

      await log.step('SC-ST-037 a count sheet can be abandoned; nothing moves',
          () async {
        final double before = await onHand(pN, whMain);
        await openCount();
        await pressAndRead(tester, () => tapDialogSave(tester, 'Open'));
        await pumpUntil(tester, find.text('Counted'), waitingFor: 'the count sheet');
        await countInRow('INVSCR-N', '1');
        final String said = await pressAndRead(tester, () async {
          await tapButton(tester, 'Abandon sheet');
          await pumpFor(tester, const Duration(milliseconds: 800));
          await tapDialogSave(tester, 'Abandon');
        });
        await pumpFor(tester, const Duration(seconds: 2));
        final double after = await onHand(pN, whMain);
        log.saw = 'said "$said"; on hand $before -> $after';
        if (!sameMoney(before, after)) throw StateError(log.saw!);
      });
      await clean(tester);

      await log.step('SC-ST-038 a negative counted quantity is refused in words',
          () async {
        await openCount();
        await pressAndRead(tester, () => tapDialogSave(tester, 'Open'));
        await pumpUntil(tester, find.text('Counted'), waitingFor: 'the count sheet');
        await countInRow('INVSCR-N', '-4');
        final int before = await movements();
        final String said = await pressAndRead(
            tester, () => tapButton(tester, 'Save progress'));
        final bool open = screenHas(tester, 'Post count');
        final int after = await movements();
        log.saw = 'said "$said"; sheet open=$open; movements +${after - before}';
        // Abandon the sheet so no draft count is left on the firm.
        await tapButton(tester, 'Abandon sheet');
        await pumpFor(tester, const Duration(milliseconds: 800));
        await tapDialogSave(tester, 'Abandon');
        await pumpFor(tester, const Duration(seconds: 2));
        if (said.isEmpty) throw StateError('N1: nothing says why: ${log.saw}');
      });
      await clean(tester);
    }

    // ---------------- ledger, summary, search --------------------------------
    if (wants('views')) {
      await log.step('SC-ST-039 Stock Ledger opens and explains a product',
          () async {
        await openStock(tester, 'stock-ledger');
        overflow('Stock Ledger');
        await searchList(tester, 'INVSCR-N2');
        final bool cols = screenHas(tester, 'New balance') || screenHas(tester, 'Balance');
        log.saw = 'rows for INVSCR-N2=${screenHas(tester, 'INVSCR-N2')}, balance column=$cols';
        if (!screenHas(tester, 'INVSCR-N2')) throw StateError(log.saw!);
      });

      await log.step('SC-ST-040 a ledger row opens its details', () async {
        await openStock(tester, 'stock-ledger');
        await pickProduct(tester, 'INVSCR-N2');
        await tapButton(tester, 'Open');
        await pumpFor(tester, const Duration(seconds: 2));
        log.saw = 'dialog texts ${noticeText(tester).split(' | ').take(10).join(' | ')}';
        final bool open = find.byType(Dialog).evaluate().isNotEmpty;
        await clean(tester);
        if (!open) throw StateError('no details dialog');
      });
      await clean(tester);

    }
    if (wants('views2')) {
      await log.step('SC-ST-041 Transactions filter by type keeps only that type',
          () async {
        await openStock(tester, 'transactions');
        if (find.text('Transaction type').evaluate().isEmpty) {
          await openFilters(tester);
        }
        await pumpFor(tester, const Duration(seconds: 1));
        final Finder typeBox = find.ancestor(
            of: find.text('Transaction type'),
            matching: find.byType(DropdownButtonFormField<String>));
        await pumpUntil(tester, typeBox, waitingFor: 'the Transaction type box');
        await tester.tap(typeBox.last);
        await pumpFor(tester, const Duration(seconds: 1));
        log.info('SC-ST-041', 'menu texts: ${textOnScreen(tester).where((String t) => t.length < 40).take(60).join(' | ')}');
        final Finder entry = find.text('Write-off');
        await pumpUntil(tester, entry, waitingFor: 'the Write-off entry');
        await tester.tap(entry.last);
        await pumpFor(tester, const Duration(seconds: 2));
        await tapButton(tester, 'Apply');
        await pumpFor(tester, const Duration(seconds: 2));
        final bool wo = screenHas(tester, 'WO$stamp') || screenHas(tester, 'Write');
        final bool adj = textOnScreen(tester).any((String t) =>
            t.toUpperCase() == 'ADJUSTMENT' || t.toUpperCase() == 'ADJ');
        log.saw = 'write-off rows shown=$wo, adjustment row shown=$adj';
        await tapButton(tester, 'Clear');
        await tapButton(tester, 'Apply');
        await pumpFor(tester, const Duration(seconds: 2));
        if (adj) throw StateError('the type filter let an adjustment through');
      });
      await clean(tester);

      await log.step('SC-ST-042 Stock Summary opens with its counts', () async {
        await openStock(tester, 'stock-summary');
        overflow('Stock Summary');
        final bool counts = screenHas(tester, 'Records') && screenHas(tester, 'Out of stock');
        log.saw = 'summary counts present=$counts; ${textOnScreen(tester).take(14).join(' | ')}';
        if (!counts) throw StateError(log.saw!);
      });

      await log.step('SC-ST-043 Stock Search finds a product by code', () async {
        await openStock(tester, 'stock-search');
        overflow('Stock Search');
        await searchList(tester, 'INVSCR-S');
        log.saw = 'INVSCR-S found=${screenHas(tester, 'INVSCR-S')}';
        if (!screenHas(tester, 'INVSCR-S')) throw StateError(log.saw!);
      });

      await log.step('SC-ST-044 Stock Search with no match says so', () async {
        await openStock(tester, 'stock-search');
        await searchList(tester, 'NOSUCHTHING$stamp');
        final bool empty = screenHas(tester, 'No ') && screenHas(tester, 'result') ||
            screenHas(tester, 'No records') || screenHas(tester, 'Nothing');
        log.saw = 'texts ${textOnScreen(tester).take(20).join(' | ')}';
        if (!empty) throw StateError('no empty-state message: ${log.saw}');
      });
    }

    // ---------------- stock transfers (document) -----------------------------
    if (wants('transfers')) {
      Future<void> openNewTransfer() async {
        await openStock(tester, 'stock-transfers');
        await tapKey(tester, 'transfer-new');
        await pumpUntil(tester, find.byKey(const ValueKey<String>('transfer-save')),
            waitingFor: 'the transfer dialog');
      }

      Future<void> fillTransfer(String product, String qty,
          {String to = 'QW2'}) async {
        await chooseIn(tester, 'transfer-from', 'MAIN');
        await chooseIn(tester, 'transfer-to', to);
        await chooseIn(tester, 'transfer-product-0', product);
        if (qty.isNotEmpty) {
          await tester.enterText(
              find.byKey(const ValueKey<String>('transfer-quantity-0')), qty);
          await pumpFor(tester, const Duration(milliseconds: 300));
        }
      }

      Future<Json?> transferOf(String number) async {
        final dynamic rows = await me.get('/api/v1/inventory/stock-transfers?page_size=100');
        for (final dynamic r in rows as List<dynamic>) {
          if ((r as Json)['transfer_number'] == number) return r;
        }
        return null;
      }

      Future<int> transferCount() async =>
          ((await me.get('/api/v1/inventory/stock-transfers?page_size=100')) as List<dynamic>).length;

      await log.step('SC-ST-045 Stock Transfers list opens', () async {
        await openStock(tester, 'stock-transfers');
        overflow('Stock Transfers');
        final bool cols = (screenHas(tester, 'Transfer') && screenHas(tester, 'Status')) ||
            screenHas(tester, 'No stock transfers');
        log.saw = 'texts ${textOnScreen(tester).take(16).join(' | ')}';
        if (!cols) throw StateError(log.saw!);
      });

      String? number;
      await log.step('SC-ST-046 New transfer MAIN to QW2 saved as a draft',
          () async {
        final int before = await transferCount();
        await openNewTransfer();
        await fillTransfer('INVSCR-N2', '4');
        overflow('Transfer dialog');
        final String said =
            await pressAndRead(tester, () => tapKey(tester, 'transfer-save'));
        await pumpFor(tester, const Duration(seconds: 2));
        final dynamic rows = await me.get('/api/v1/inventory/stock-transfers?page_size=100');
        final List<Json> list = <Json>[for (final dynamic r in rows as List<dynamic>) r as Json];
        list.sort((Json a, Json b) => '${b['created_at']}'.compareTo('${a['created_at']}'));
        number = list.isEmpty ? null : '${list.first['transfer_number']}';
        log.saw = 'said "$said"; transfers $before -> ${list.length}; newest '
            '$number status ${list.isEmpty ? null : list.first['status']}';
        if (list.length != before + 1) throw StateError(log.saw!);
        if (!screenHas(tester, number!)) throw StateError('not on the list: ${log.saw}');
      });
      await clean(tester);

      await log.step('SC-ST-047 Dispatch takes the stock off MAIN into transit',
          () async {
        final double before = await onHand(pN2, whMain);
        await openStock(tester, 'stock-transfers');
        await selectRow(tester, number!);
        final String said = await pressWatch(
            () => tapKey(tester, 'transfer-dispatch'), tester);
        await pumpFor(tester, const Duration(seconds: 2));
        final double after = await onHand(pN2, whMain);
        final Json? t = await transferOf(number!);
        log.saw = 'said "$said"; MAIN $before -> $after; status ${t?['status']}';
        if (!sameMoney(after, before - 4)) throw StateError(log.saw!);
      });
      await clean(tester);

      await log.step('SC-ST-048 Receive puts it into QW2', () async {
        final double before = await onHand(pN2, whTwo);
        await openStock(tester, 'stock-transfers');
        await selectRow(tester, number!);
        await tapKey(tester, 'transfer-receive');
        await pumpFor(tester, const Duration(seconds: 2));
        final String said = await pressAndRead(
            tester, () => tapDialogSave(tester, 'Receive'));
        await pumpFor(tester, const Duration(seconds: 2));
        final double after = await onHand(pN2, whTwo);
        final Json? t = await transferOf(number!);
        log.saw = 'said "$said"; QW2 $before -> $after; status ${t?['status']}';
        if (!sameMoney(after, before + 4)) throw StateError(log.saw!);
      });
      await clean(tester);

      await log.step('SC-ST-049 a transfer to the same warehouse is refused',
          () async {
        await openNewTransfer();
        await fillTransfer('INVSCR-N2', '1', to: 'MAIN');
        log.saw = await refuse('New stock transfer',
            () => tapKey(tester, 'transfer-save'),
            count: transferCount, mustSay: 'different');
      });
      await clean(tester);

      await log.step('SC-ST-050 a transfer with the quantity empty is refused',
          () async {
        await openNewTransfer();
        await fillTransfer('INVSCR-N2', '');
        log.saw = await refuse('New stock transfer',
            () => tapKey(tester, 'transfer-save'),
            count: transferCount, mustSay: 'quantity');
      });
      await clean(tester);

      String? bigNumber;
      String? bigId;
      await log.step('SC-ST-051 a transfer of more than MAIN holds: what the save says',
          () async {
        final int before = await transferCount();
        await openNewTransfer();
        await fillTransfer('INVSCR-N2', '999999');
        final String said =
            await pressAndRead(tester, () => tapKey(tester, 'transfer-save'));
        await pumpFor(tester, const Duration(seconds: 2));
        final int after = await transferCount();
        final bool open = find.byKey(const ValueKey<String>('transfer-save')).evaluate().isNotEmpty;
        if (after > before) {
          final dynamic rows = await me.get('/api/v1/inventory/stock-transfers?page_size=100');
          final List<Json> list = <Json>[for (final dynamic r in rows as List<dynamic>) r as Json];
          list.sort((Json a, Json b) => '${b['created_at']}'.compareTo('${a['created_at']}'));
          bigNumber = '${list.first['transfer_number']}';
          bigId = '${list.first['id']}';
        }
        log.saw = 'saved=${after - before}, dialog open=$open, said "$said"';
        if (!open && after == before) throw StateError('closed and saved nothing: ${log.saw}');
      });
      await clean(tester);

      await log.step('SC-ST-052 dispatching more than is held keeps its words',
          () async {
        if (bigNumber == null) {
          log.saw = 'the save refused the 999999 draft, so there is nothing to dispatch';
          return;
        }
        await openStock(tester, 'stock-transfers');
        await selectRow(tester, bigNumber!);
        final String said = await pressWatch(
            () => tapKey(tester, 'transfer-dispatch'), tester);
        final dynamic t = await me.one('inventory/stock-transfers', bigId!);
        log.saw = 'said "$said"; status ${(t as Json)['status']}';
        if ('${t['status']}' != 'DRAFT') throw StateError('it was dispatched: ${log.saw}');
        if (said.isEmpty) throw StateError('N1: nothing said why: ${log.saw}');
      });
      await clean(tester);
      if (bigId != null) {
        try {
          await me.write('POST', '/api/v1/inventory/stock-transfers/$bigId/cancel',
              <String, dynamic>{'reason': 'screen cases: tidy'});
        } catch (_) {}
      }

      await log.step('SC-ST-053 Cancel a draft transfer asks a reason', () async {
        await openNewTransfer();
        await fillTransfer('INVSCR-N2', '2');
        await tapKey(tester, 'transfer-save');
        await pumpFor(tester, const Duration(seconds: 2));
        await clean(tester);
        final dynamic rows = await me.get('/api/v1/inventory/stock-transfers?page_size=100');
        final List<Json> drafts = <Json>[
          for (final dynamic r in rows as List<dynamic>)
            if ((r as Json)['status'] == 'DRAFT') r,
        ];
        drafts.sort((Json a, Json b) => '${b['created_at']}'.compareTo('${a['created_at']}'));
        await openStock(tester, 'stock-transfers');
        await selectRow(tester, '${drafts.first['transfer_number']}');
        await tapKey(tester, 'transfer-cancel');
        final String said = await answerReason(tester);
        final Json? t = await transferOf('${drafts.first['transfer_number']}');
        log.saw = 'said "$said"; status ${t?['status']}';
        if ('${t?['status']}' != 'CANCELLED') throw StateError(log.saw!);
      });
      await clean(tester);
    }

    // ---------------- repacking -----------------------------------------------
    if (wants('repack')) {
      Future<void> openNewRepack() async {
        await openStock(tester, 'repacking');
        await tapKey(tester, 'repack-new');
        await pumpUntil(tester, find.byKey(const ValueKey<String>('repack-save')),
            waitingFor: 'the repack dialog');
        await pumpFor(tester, const Duration(seconds: 1));
      }

      Future<void> fillRepack(String consume, String cq, String produce, String pq) async {
        final Finder branch = find.byKey(const ValueKey<String>('repack-branch'));
        if (branch.evaluate().isNotEmpty) {
          final DropdownButtonFormField<String> d =
              tester.widget<DropdownButtonFormField<String>>(branch.first);
          if (d.initialValue == null) await chooseIn(tester, 'repack-branch', 'HO');
        }
        final Finder wh = find.byWidgetPredicate((Widget w) {
          final Key? k = w.key;
          return k is ValueKey<String> && k.value.startsWith('repack-warehouse-');
        });
        if (wh.evaluate().isNotEmpty) {
          await chooseInKeyed(tester, 'repack-warehouse-', 'MAIN');
        }
        if (consume.isNotEmpty) {
          await chooseIn(tester, 'repack-consume-product-0', consume);
        }
        if (cq.isNotEmpty) {
          await tester.enterText(
              find.byKey(const ValueKey<String>('repack-consume-quantity-0')), cq);
        }
        if (produce.isNotEmpty) {
          await chooseIn(tester, 'repack-produce-product-0', produce);
        }
        if (pq.isNotEmpty) {
          await tester.enterText(
              find.byKey(const ValueKey<String>('repack-produce-quantity-0')), pq);
        }
        await pumpFor(tester, const Duration(milliseconds: 400));
      }

      Future<int> repackCount() async =>
          ((await me.get('/api/v1/inventory/repacks')) as List<dynamic>).length;

      await log.step('SC-ST-054 Repacking list opens', () async {
        await openStock(tester, 'repacking');
        overflow('Repacking');
        final bool ok = screenHas(tester, 'Repack') || screenHas(tester, 'No repacks yet');
        log.saw = 'texts ${textOnScreen(tester).take(16).join(' | ')}';
        if (!ok) throw StateError(log.saw!);
      });

      String? repackNumber;
      await log.step('SC-ST-055 New repack: 2 of one product into 4 of another',
          () async {
        final double bn = await onHand(pN, whMain);
        final double bn2 = await onHand(pN2, whMain);
        final int before = await repackCount();
        await openNewRepack();
        await fillRepack('INVSCR-N2', '2', 'INVSCR-N', '4');
        overflow('Repack dialog');
        final String said =
            await pressAndRead(tester, () => tapKey(tester, 'repack-save'));
        await pumpFor(tester, const Duration(seconds: 2));
        final double an = await onHand(pN, whMain);
        final double an2 = await onHand(pN2, whMain);
        final int after = await repackCount();
        final dynamic rows = await me.get('/api/v1/inventory/repacks');
        final List<Json> list = <Json>[for (final dynamic r in rows as List<dynamic>) r as Json];
        list.sort((Json a, Json b) => '${b['created_at']}'.compareTo('${a['created_at']}'));
        repackNumber = list.isEmpty ? null : '${list.first['repack_number']}';
        log.saw = 'said "$said"; N $bn -> $an; N2 $bn2 -> $an2; repacks $before -> $after';
        if (after != before + 1 || !sameMoney(an, bn + 4) || !sameMoney(an2, bn2 - 2)) {
          throw StateError(log.saw!);
        }
      });
      await clean(tester);

      await log.step('SC-ST-056 a repack with no produce product is refused',
          () async {
        await openNewRepack();
        await fillRepack('INVSCR-N2', '1', '', '');
        log.saw = await refuse('New repack', () => tapKey(tester, 'repack-save'),
            count: repackCount, mustSay: 'produce');
      });
      await clean(tester);

      await log.step('SC-ST-057 a repack with quantity 0 is refused', () async {
        await openNewRepack();
        await fillRepack('INVSCR-N2', '0', 'INVSCR-N', '1');
        log.saw = await refuse('New repack', () => tapKey(tester, 'repack-save'),
            count: repackCount, mustSay: 'quantity');
      });
      await clean(tester);

      await log.step('SC-ST-058 wastage of 100 is refused', () async {
        await openNewRepack();
        await fillRepack('INVSCR-N2', '1', 'INVSCR-N', '1');
        await tester.enterText(
            find.byKey(const ValueKey<String>('repack-wastage')), '100');
        log.saw = await refuse('New repack', () => tapKey(tester, 'repack-save'),
            count: repackCount, mustSay: 'wastage');
      });
      await clean(tester);

      await log.step('SC-ST-059 consuming more than is held is refused by the server',
          () async {
        await openNewRepack();
        await fillRepack('INVSCR-N2', '999999', 'INVSCR-N', '1');
        await tester.enterText(
            find.byKey(const ValueKey<String>('repack-wastage')), '0');
        log.saw = await refuse('New repack', () => tapKey(tester, 'repack-save'),
            count: repackCount);
      });
      await clean(tester);

      await log.step('SC-ST-060 Cancel repack reverses the stock', () async {
        final double bn = await onHand(pN, whMain);
        await openStock(tester, 'repacking');
        await selectRow(tester, repackNumber!);
        await tapKey(tester, 'repack-cancel');
        final String said = await answerReason(tester);
        await pumpFor(tester, const Duration(seconds: 2));
        final double an = await onHand(pN, whMain);
        log.saw = 'said "$said"; N $bn -> $an';
        if (!sameMoney(an, bn - 4)) throw StateError(log.saw!);
      });
      await clean(tester);
    }

    // ---------------- approvals, reasons, settings -----------------------------
    if (wants('approvals')) {
      Future<Server> store() => asUser('qstore');
      await me.write('PUT', '/api/v1/inventory/adjustment-limits', <String, dynamic>{
        'limits': <Json>[
          <String, dynamic>{'role_code': 'INVENTORY_MANAGER', 'max_value': '1'}
        ]
      });
      Future<Json> raise(Server s, double qty) async => (await s.write(
              'POST', '/api/v1/inventory/adjustment-requests', <String, dynamic>{
            'kind': 'ADJUSTMENT',
            'adjustment': <String, dynamic>{
              'branch_id': branchId,
              'warehouse_id': whMain['id'],
              'product_id': pN2['id'],
              'quantity': qty,
              'transaction_date': today,
              'remarks': 'screen cases $stamp',
            },
          })) as Json;
      Future<int> pending() async =>
          ((await me.get('/api/v1/inventory/adjustment-requests?status=PENDING')) as List<dynamic>).length;

      await log.step('SC-ST-061 Adjustment Approvals lists a pending request',
          () async {
        final Server s = await store();
        await raise(s, 3);
        await raise(s, 2);
        await openStock(tester, 'adjustment-approvals');
        overflow('Adjustment Approvals');
        final bool ok = screenHas(tester, 'Pending') && screenHas(tester, 'INVSCR-N2');
        log.saw = 'pending on server ${await pending()}; texts ${textOnScreen(tester).take(20).join(' | ')}';
        if (!ok) throw StateError(log.saw!);
      });

      await log.step('SC-ST-062 Approve posts the adjustment', () async {
        final double before = await onHand(pN2, whMain);
        final int p0 = await pending();
        await openStock(tester, 'adjustment-approvals');
        await pickProduct(tester, 'INVSCR-N2', search: false, at: null);
        final String said = await pressWatch(
            () => tapKey(tester, 'adjustment-approve'), tester);
        await pumpFor(tester, const Duration(seconds: 2));
        final double after = await onHand(pN2, whMain);
        log.saw = 'said "$said"; on hand $before -> $after; pending $p0 -> ${await pending()}';
        if (await pending() != p0 - 1) throw StateError(log.saw!);
      });
      await clean(tester);

      await log.step('SC-ST-063 Reject asks a reason and posts nothing', () async {
        final double before = await onHand(pN2, whMain);
        final int p0 = await pending();
        await openStock(tester, 'adjustment-approvals');
        await pickProduct(tester, 'INVSCR-N2', search: false, at: null);
        await tapKey(tester, 'adjustment-reject');
        final String said = await answerReason(tester, reason: 'not needed');
        await pumpFor(tester, const Duration(seconds: 2));
        final double after = await onHand(pN2, whMain);
        log.saw = 'said "$said"; on hand $before -> $after; pending $p0 -> ${await pending()}';
        if (!sameMoney(before, after) || await pending() != p0 - 1) {
          throw StateError(log.saw!);
        }
      });
      await clean(tester);

      await log.step('SC-ST-064 Approve with nothing picked is not offered',
          () async {
        await openStock(tester, 'adjustment-approvals');
        final Finder f = find.byKey(const ValueKey<String>('adjustment-approve'));
        String state = 'absent';
        if (f.evaluate().isNotEmpty) {
          final Widget w = tester.widget(f.first);
          state = w is ButtonStyleButton && w.onPressed == null ? 'disabled' : 'enabled';
        }
        log.saw = 'Approve is $state with no row picked';
        if (state == 'enabled') throw StateError(log.saw!);
      });
      await me.write('PUT', '/api/v1/inventory/adjustment-limits',
          <String, dynamic>{'limits': <dynamic>[]});
    }

    if (wants('settings')) {
      await log.step('SC-ST-065 Adjustment Reasons lists the firm\'s reasons',
          () async {
        await openSetUp(tester, 'inventory/adjustment-reasons', section: 'Stock');
        overflow('Adjustment Reasons');
        final bool ok = screenHas(tester, 'Damage') && screenHas(tester, 'Expiry');
        log.saw = 'texts ${textOnScreen(tester).take(20).join(' | ')}';
        if (!ok) throw StateError(log.saw!);
      });

      final String reasonCode = 'SCR$stamp';
      await log.step('SC-ST-066 New reason saved', () async {
        await openSetUp(tester, 'inventory/adjustment-reasons', section: 'Stock');
        await tapNew(tester);
        await typeField(tester, 'Code', reasonCode);
        await typeField(tester, 'Name', 'Screen reason $stamp');
        final String said = await pressAndRead(
            tester, () => tapButtonStarting(tester, 'Save'));
        await pumpFor(tester, const Duration(seconds: 2));
        final dynamic rows = await me.get('/api/v1/inventory/adjustment-reasons');
        final bool onServer = (rows as List<dynamic>).any((dynamic r) => (r as Json)['code'] == reasonCode);
        log.saw = 'said "$said"; on server=$onServer; on list=${screenHas(tester, reasonCode)}';
        if (!onServer) throw StateError(log.saw!);
      });
      await clean(tester);

      await log.step('SC-ST-067 a reason with no name is refused', () async {
        await openSetUp(tester, 'inventory/adjustment-reasons', section: 'Stock');
        await tapNew(tester);
        await typeField(tester, 'Code', 'SCN$stamp');
        log.saw = await refuse('Reason', () => tapButtonStarting(tester, 'Save'),
            typed: 'SCN$stamp',
            count: () async => ((await me.get('/api/v1/inventory/adjustment-reasons')) as List<dynamic>).length);
      });
      await clean(tester);

      await log.step('SC-ST-068 a reason code already used is refused', () async {
        await openSetUp(tester, 'inventory/adjustment-reasons', section: 'Stock');
        await tapNew(tester);
        await typeField(tester, 'Code', reasonCode);
        await typeField(tester, 'Name', 'Duplicate $stamp');
        log.saw = await refuse('Reason', () => tapButtonStarting(tester, 'Save'),
            typed: 'Duplicate $stamp',
            count: () async => ((await me.get('/api/v1/inventory/adjustment-reasons')) as List<dynamic>).length);
      });
      await clean(tester);

      await log.step('SC-ST-069 Inventory Settings opens', () async {
        await openSetUp(tester, 'inventory/inventory-settings', section: 'Stock');
        overflow('Inventory Settings');
        final bool ok = screenHas(tester, 'opening-stock') || screenHas(tester, 'export format');
        log.saw = 'texts ${textOnScreen(tester).take(20).join(' | ')}';
        if (!ok) throw StateError(log.saw!);
      });

      await log.step('SC-ST-075 Adjustment Limits: add a role limit and save',
          () async {
        await openSetUp(tester, 'settings/adjustment-limits', section: 'Stock');
        await pumpUntil(tester, find.text('Adjustment limits'),
            waitingFor: 'the Adjustment limits dialog');
        await tapKey(tester, 'adjustment-limit-add');
        await chooseIn(tester, 'adjustment-limit-role-0', 'Inventory');
        await typeInKeyed(tester, 'adjustment-limit-amount-0', '500');
        final String said = await pressAndRead(
            tester, () => tapKey(tester, 'adjustment-limits-save'));
        await pumpFor(tester, const Duration(seconds: 2));
        final dynamic rows = await me.get('/api/v1/inventory/adjustment-limits');
        log.saw = 'said "$said"; server limits $rows';
        if ((rows as List<dynamic>).isEmpty) throw StateError(log.saw!);
      });
      await clean(tester);

      await log.step('SC-ST-076 a limit with no amount is refused', () async {
        await openSetUp(tester, 'settings/adjustment-limits', section: 'Stock');
        await pumpUntil(tester, find.text('Adjustment limits'),
            waitingFor: 'the Adjustment limits dialog');
        await tapKey(tester, 'adjustment-limit-add');
        await chooseIn(tester, 'adjustment-limit-role-1', 'Sales Manager');
        final String said = await pressAndRead(
            tester, () => tapKey(tester, 'adjustment-limits-save'));
        final dynamic rows = await me.get('/api/v1/inventory/adjustment-limits');
        log.saw = 'said "$said"; dialog open=${screenHas(tester, 'Adjustment limits')}; server limits ${(rows as List<dynamic>).length}';
        if (rows.any((dynamic r) => (r as Json)['role_code'] == 'SALES_MANAGER')) {
          throw StateError('a limit with no amount was saved: ${log.saw}');
        }
        if (said.isEmpty) throw StateError('N1: nothing said why: ${log.saw}');
      });
      await clean(tester);

      // Put the firm back the way it was found.
      await me.write('PUT', '/api/v1/inventory/adjustment-limits',
          <String, dynamic>{'limits': <dynamic>[]});
    }

    // ---------------- round 2: serial units on the move, used reference ------
    // The app sometimes ends by itself a few minutes in, so the part also runs
    // in pieces: r2xfer, r2doc, r2open, r2ref.
    bool r2(String name) => wants('round2') || wants('r2$name');
    Future<void> piece(
        String name, String label, Future<void> Function() body) async {
      if (r2(name)) {
        await log.step(label, body);
      }
    }
    if (r2('xfer') || r2('doc') || r2('open') || r2('ref')) {
      final Json pS = await productByCode('INVSCR-S');
      const String serialsPath = '/api/v1/batch-serial/serials';

      /// The units numbered `R2<stamp>-n`, by number.
      Future<Map<String, Json>> units([Json? product]) async {
        final dynamic rows = await me.get(
            '$serialsPath?page_size=100&product_id=${(product ?? pS)['id']}&search=R2$stamp');
        return <String, Json>{
          for (final dynamic r in rows as List<dynamic>)
            '${(r as Json)['serial_number']}': r,
        };
      }

      String where(Json? unit) => unit == null
          ? 'missing'
          : '${unit['status']}@${unit['warehouse_id'] == whMain['id'] ? 'MAIN' : unit['warehouse_id'] == whTwo['id'] ? 'QW2' : unit['warehouse_id']}';

      Future<void> pickUnit(String id, {String prefix = 'serial-pick-'}) async {
        final Finder chip = find.byKey(ValueKey<String>('$prefix$id'));
        await pumpUntil(tester, chip, waitingFor: 'the chip $prefix$id');
        await tester.ensureVisible(chip.first);
        await pumpFor(tester, const Duration(milliseconds: 300));
        await tester.tap(chip.first);
        await pumpFor(tester, const Duration(milliseconds: 400));
      }

      String pickHeading() {
        final Finder f = find.byKey(const ValueKey<String>('serial-pick-count'));
        return f.evaluate().isEmpty
            ? '(no picker)'
            : tester.widget<Text>(f.first).data ?? '';
      }

      Future<List<Json>> transfers() async => <Json>[
            for (final dynamic r in (await me
                .get('/api/v1/inventory/stock-transfers?page_size=100')) as List<dynamic>)
              r as Json,
          ]..sort((Json a, Json b) =>
              '${b['created_at']}'.compareTo('${a['created_at']}'));

      // Six fresh units on the MAIN shelf, with the stock to stand behind them.
      final double haveS = await onHand(pS, whMain);
      if (haveS < 12) await adjustApi(pS, 12 - haveS);
      for (int i = 1; i <= 6; i++) {
        await me.write('POST', serialsPath, <String, dynamic>{
          'product_id': pS['id'],
          'warehouse_id': whMain['id'],
          'branch_id': branchId,
          'serial_number': 'R2$stamp-$i',
        });
      }
      final Map<String, Json> made = await units();
      String idOf(int i) => '${made['R2$stamp-$i']!['id']}';

      await piece('xfer', 
          'SC-ST-077 Transfer of a serial-tracked product with one unit picked for two is refused',
          () async {
        await openAction('transfer', 'Transfer', 'INVSCR-S');
        await pickDropdown(tester, 'Move it to', 'QW2');
        await typeLabelled(tester, 'Quantity', '2');
        final String heading = pickHeading();
        await pickUnit(idOf(1));
        overflow('Transfer dialog with the unit picker');
        final String picked = pickHeading();
        final String saw = await refuse('Transfer stock',
            () => tapDialogSave(tester, 'Transfer'),
            typed: '2', mustSay: 'serial number');
        log.saw = 'heading "$heading" -> "$picked"; $saw';
      });
      await clean(tester);

      await piece('xfer', 
          'SC-ST-078 Transfer 2 units: the two picked land in the second warehouse',
          () async {
        final double before2 = await onHand(pS, whTwo);
        await openAction('transfer', 'Transfer', 'INVSCR-S');
        await pickDropdown(tester, 'Move it to', 'QW2');
        await typeLabelled(tester, 'Quantity', '2');
        await pickUnit(idOf(1));
        await pickUnit(idOf(2));
        final String heading = pickHeading();
        final String said = await pressAndRead(
            tester, () => tapDialogSave(tester, 'Transfer'));
        await pumpFor(tester, const Duration(seconds: 2));
        final Map<String, Json> now = await units();
        final double after2 = await onHand(pS, whTwo);
        log.saw = 'heading "$heading"; said "$said"; QW2 $before2 -> $after2; '
            'unit 1 ${where(now['R2$stamp-1'])}, unit 2 ${where(now['R2$stamp-2'])}, '
            'unit 3 ${where(now['R2$stamp-3'])}';
        if (!sameMoney(after2, before2 + 2) ||
            where(now['R2$stamp-1']) != 'AVAILABLE@QW2' ||
            where(now['R2$stamp-2']) != 'AVAILABLE@QW2' ||
            where(now['R2$stamp-3']) != 'AVAILABLE@MAIN') {
          throw StateError(log.saw!);
        }
        if (dialogOpen('Transfer stock')) throw StateError('dialog stayed open');
      });
      await clean(tester);

      String? sentNumber;
      String? sentId;
      await piece('doc', 
          'SC-ST-079 New transfer of 2 serial units saved as a draft names them',
          () async {
        final int before = (await transfers()).length;
        await openStock(tester, 'stock-transfers');
        await tapKey(tester, 'transfer-new');
        await pumpUntil(tester, find.byKey(const ValueKey<String>('transfer-save')),
            waitingFor: 'the transfer dialog');
        await chooseIn(tester, 'transfer-from', 'MAIN');
        await chooseIn(tester, 'transfer-to', 'QW2');
        await chooseIn(tester, 'transfer-product-0', 'INVSCR-S');
        await tester.enterText(
            find.byKey(const ValueKey<String>('transfer-quantity-0')), '2');
        await pumpFor(tester, const Duration(seconds: 2));
        final String heading = pickHeading();
        await pickUnit(idOf(3));
        await pickUnit(idOf(4));
        overflow('Transfer document with the unit picker');
        final String picked = pickHeading();
        final String said =
            await pressAndRead(tester, () => tapKey(tester, 'transfer-save'));
        await pumpFor(tester, const Duration(seconds: 2));
        final List<Json> list = await transfers();
        if (list.length != before + 1) {
          throw StateError('nothing saved: heading "$heading" -> "$picked"; said "$said"');
        }
        sentNumber = '${list.first['transfer_number']}';
        sentId = '${list.first['id']}';
        final Json doc = await me.one('inventory/stock-transfers', sentId!);
        final List<dynamic> named =
            ((doc['lines'] as List<dynamic>).first as Json)['serials'] as List<dynamic>? ?? <dynamic>[];
        log.saw = 'heading "$heading" -> "$picked"; said "$said"; $sentNumber '
            '${doc['status']}; units named ${named.map((dynamic s) => (s as Json)['serial_number']).join(', ')}';
        if (named.length != 2) throw StateError(log.saw!);
      });
      await clean(tester);

      await piece('doc', 
          'SC-ST-080 dispatching a draft that names one unit of two is refused in words',
          () async {
        final dynamic draft = await me.write(
            'POST', '/api/v1/inventory/stock-transfers', <String, dynamic>{
          'transfer_date': today,
          'from_warehouse_id': whMain['id'],
          'to_warehouse_id': whTwo['id'],
          'lines': <dynamic>[
            <String, dynamic>{
              'product_id': pS['id'],
              'quantity': '2',
              'serial_ids': <String>[idOf(5)],
            },
          ],
        });
        final String shortId = '${(draft as Json)['id']}';
        final String shortNumber = '${draft['transfer_number']}';
        await openStock(tester, 'stock-transfers');
        await refreshList(tester);
        await pumpFor(tester, const Duration(seconds: 2));
        await selectRow(tester, shortNumber);
        final String said = await pressWatch(
            () => tapKey(tester, 'transfer-dispatch'), tester);
        final Json t = await me.one('inventory/stock-transfers', shortId);
        final bool open = find.byType(Dialog).evaluate().isNotEmpty;
        final String onScreen = open
            ? textOnScreen(tester)
                .where((String x) => x.toLowerCase().contains('serial'))
                .join(' | ')
            : '';
        log.saw = '$shortNumber: said "$said"; dialog open=$open, it reads '
            '"$onScreen"; status ${t['status']}';
        await clean(tester);
        try {
          await me.write('POST',
              '/api/v1/inventory/stock-transfers/$shortId/cancel',
              <String, dynamic>{'reason': 'screen cases: tidy'});
        } catch (_) {}
        if ('${t['status']}' != 'DRAFT') throw StateError('it left: ${log.saw}');
        if (said.isEmpty && onScreen.isEmpty) {
          throw StateError('N1: nothing says why: ${log.saw}');
        }
      });
      await clean(tester);

      await piece('doc', 'SC-ST-081 Dispatch puts the two units in transit',
          () async {
        if (sentNumber == null) throw StateError('SC-ST-079 saved no draft');
        await openStock(tester, 'stock-transfers');
        await selectRow(tester, sentNumber!);
        final String said = await pressWatch(
            () => tapKey(tester, 'transfer-dispatch'), tester);
        await pumpFor(tester, const Duration(seconds: 2));
        final Json t = await me.one('inventory/stock-transfers', sentId!);
        final Map<String, Json> now = await units();
        log.saw = 'said "$said"; status ${t['status']}; unit 3 '
            '${now['R2$stamp-3']?['status']}, unit 4 ${now['R2$stamp-4']?['status']}';
        if ('${now['R2$stamp-3']?['status']}' != 'IN_TRANSIT' ||
            '${now['R2$stamp-4']?['status']}' != 'IN_TRANSIT') {
          throw StateError(log.saw!);
        }
      });
      await clean(tester);

      Future<void> openReceive() async {
        await openStock(tester, 'stock-transfers');
        await selectRow(tester, sentNumber!);
        await tapKey(tester, 'transfer-receive');
        await pumpUntil(tester, find.byKey(const ValueKey<String>('receive-save')),
            waitingFor: 'the receive dialog');
        await tester.enterText(
            find.byKey(const ValueKey<String>('receive-damaged-0')), '1');
        await pumpFor(tester, const Duration(milliseconds: 600));
      }

      await piece('doc', 
          'SC-ST-082 Receive with one damaged and no unit ticked is refused',
          () async {
        if (sentNumber == null) throw StateError('SC-ST-079 saved no draft');
        await openReceive();
        overflow('Receive dialog with the unit ticks');
        final String said = await pressAndRead(
            tester, () => tapKey(tester, 'receive-save'), seconds: 4);
        final bool open =
            find.byKey(const ValueKey<String>('receive-save')).evaluate().isNotEmpty;
        final Json t = await me.one('inventory/stock-transfers', sentId!);
        log.saw = 'said "$said"; dialog open=$open; status ${t['status']}';
        if (!open) throw StateError('N2: the dialog closed: ${log.saw}');
        if (!said.contains('Tick which')) {
          throw StateError('N1: the sentence does not say which to tick: ${log.saw}');
        }
        if ('${t['status']}' == 'RECEIVED') throw StateError('N3: received: ${log.saw}');
      });
      await clean(tester);

      await piece('doc', 
          'SC-ST-083 Receive with the damaged unit ticked: one usable, one damaged, both there',
          () async {
        if (sentNumber == null) throw StateError('SC-ST-079 saved no draft');
        final double before2 = await onHand(pS, whTwo);
        await openReceive();
        await pickUnit(idOf(4), prefix: 'receive-damaged-pick-0-');
        final String said = await pressAndRead(
            tester, () => tapKey(tester, 'receive-save'));
        await pumpFor(tester, const Duration(seconds: 2));
        final Json t = await me.one('inventory/stock-transfers', sentId!);
        final Map<String, Json> now = await units();
        final double after2 = await onHand(pS, whTwo);
        log.saw = 'said "$said"; status ${t['status']}; QW2 $before2 -> $after2; '
            'unit 3 ${where(now['R2$stamp-3'])}, unit 4 ${where(now['R2$stamp-4'])}';
        if (where(now['R2$stamp-3']) != 'AVAILABLE@QW2' ||
            where(now['R2$stamp-4']) != 'DAMAGED@QW2') {
          throw StateError(log.saw!);
        }
      });
      await clean(tester);

      Future<Json?> openingOf(String reference) async {
        final dynamic rows =
            await me.get('/api/v1/inventory/opening-stock?page_size=100');
        for (final dynamic r in rows as List<dynamic>) {
          if ((r as Json)['reference_number'] == reference) return r;
        }
        return null;
      }

      // Opening stock is posted once per item and warehouse, so these two cases
      // take a serial-tracked product of the run's own.
      final String ownCode = 'R2S$stamp';
      final Json pOwn = (await me.write('POST', '/api/v1/products', <String, dynamic>{
        'code': ownCode,
        'name': 'Serial opening $stamp',
        'product_type': pS['product_type'],
        'category_id': pS['category_id'],
        'tax_profile_group_code': pS['tax_profile_group_code'],
        'selling_price': '100',
        'purchase_price': '60',
        'base_uom_id': pS['base_uom_id'],
        'inventory_uom_id': pS['inventory_uom_id'],
        'sales_uom_id': pS['sales_uom_id'],
        'purchase_uom_id': pS['purchase_uom_id'],
      })) as Json;

      await piece('open', 
          'SC-ST-085 posting opening stock that numbers two units of three is refused in words',
          () async {
        await me.write('POST', '/api/v1/inventory/opening-stock', <String, dynamic>{
          'branch_id': branchId,
          'warehouse_id': whMain['id'],
          'reference_number': 'SX$stamp',
          'posting_date': today,
          'lines': <dynamic>[
            <String, dynamic>{
              'product_id': pOwn['id'],
              'quantity': '3',
              'unit_cost': '60',
              'serial_numbers': <String>['R2$stamp-X1', 'R2$stamp-X2'],
            },
          ],
        });
        final double before = await onHand(pOwn, whMain);
        await openStock(tester, 'opening-stock');
        await pickProduct(tester, 'SX$stamp');
        final String said = await pressWatch(
            () => command(tester, 'post-draft', 'Post draft'), tester);
        await pumpFor(tester, const Duration(seconds: 2));
        final Json? after = await openingOf('SX$stamp');
        final double now = await onHand(pOwn, whMain);
        final String banner = bannerText(tester);
        log.saw = 'said "$said"; banner "$banner"; status ${after?['status']}; '
            'on hand $before -> $now';
        if ('${after?['status']}' != 'DRAFT' || !sameMoney(before, now)) {
          throw StateError('it posted: ${log.saw}');
        }
        if (said.isEmpty && banner.isEmpty) {
          throw StateError('N1: nothing says why: ${log.saw}');
        }
        if (!'$said $banner'.toLowerCase().contains('serial')) {
          throw StateError('N1: the sentence does not name the serial numbers: ${log.saw}');
        }
      });
      await clean(tester);

      await piece('open', 
          'SC-ST-084 Opening stock of a serial product takes its numbers and posting makes the units',
          () async {
        await openStock(tester, 'opening-stock');
        await tapNew(tester);
        await pumpUntil(tester, find.text('New opening stock'),
            waitingFor: 'the opening stock dialog');
        await pickDropdown(tester, 'Warehouse', 'MAIN');
        await typeLabelled(tester, 'Reference', 'SN$stamp');
        await pickDropdown(tester, 'Product', ownCode);
        await typeLabelled(tester, 'Quantity', '2');
        await typeLabelled(tester, 'Unit cost', '60');
        final Finder box = find.byKey(const ValueKey<String>('opening-serials-0'));
        await pumpUntil(tester, box, waitingFor: 'the Serial numbers box');
        await tester.ensureVisible(box.first);
        await tester.enterText(box.first, 'R2$stamp-O1\nR2$stamp-O2');
        await pumpFor(tester, const Duration(milliseconds: 600));
        overflow('Opening stock dialog with Serial numbers');
        final bool counted = screenHas(tester, '2 of 2 entered');
        final String said =
            await pressAndRead(tester, () => tapDialogSave(tester, 'Save'));
        await pumpFor(tester, const Duration(seconds: 2));
        final Json? draft = await openingOf('SN$stamp');
        if (draft == null) throw StateError('nothing saved: said "$said"');
        await clean(tester);
        await openStock(tester, 'opening-stock');
        await pickProduct(tester, 'SN$stamp');
        final String posted = await pressWatch(
            () => command(tester, 'post-draft', 'Post draft'), tester);
        await pumpFor(tester, const Duration(seconds: 2));
        final Map<String, Json> now = await units(pOwn);
        final Json? after = await openingOf('SN$stamp');
        log.saw = 'helper counted 2 of 2=$counted; save said "$said"; post said '
            '"$posted"; status ${after?['status']}; O1 ${where(now['R2$stamp-O1'])}, '
            'O2 ${where(now['R2$stamp-O2'])}';
        if (where(now['R2$stamp-O1']) != 'AVAILABLE@MAIN' ||
            where(now['R2$stamp-O2']) != 'AVAILABLE@MAIN') {
          throw StateError(log.saw!);
        }
      });
      await clean(tester);

      await piece('ref', 
          'SC-ST-086 a second write-off under a reference already used is refused in stock words',
          () async {
        await openAction('write-off', 'Write off', 'INVSCR-N2');
        await typeLabelled(tester, 'Quantity', '1');
        await typeLabelled(tester, 'Reference (optional)', 'WR$stamp');
        final String first = await pressAndRead(
            tester, () => tapDialogSave(tester, 'Write off'));
        await pumpFor(tester, const Duration(seconds: 2));
        await clean(tester);
        final double before = await onHand(pN2, whMain);
        await openAction('write-off', 'Write off', 'INVSCR-N2');
        await typeLabelled(tester, 'Quantity', '1');
        await typeLabelled(tester, 'Reference (optional)', 'WR$stamp');
        final String saw = await refuse('Write off stock',
            () => tapDialogSave(tester, 'Write off'),
            typed: 'WR$stamp', mustSay: 'WR$stamp');
        final double after = await onHand(pN2, whMain);
        log.saw = 'first said "$first"; second: $saw; on hand $before -> $after';
        if (!sameMoney(before, after)) throw StateError(log.saw!);
      });
      await clean(tester);
    }

    // ---------------- round 2: an order owed more than is held ----------------
    if (wants('backorder')) {
      await log.step(
          'SC-ST-087 a note for the four held of an order for ten is dispatched; the row reads 0 on hand, 6 reserved',
          () async {
        final String code = 'R2B$stamp';
        final Json made = (await me.write('POST', '/api/v1/products', <String, dynamic>{
          'code': code,
          'name': 'Back order $stamp',
          'product_type': pN['product_type'],
          'category_id': pN['category_id'],
          'tax_profile_group_code': pN['tax_profile_group_code'],
          'selling_price': '100',
          'purchase_price': '60',
          'base_uom_id': pN['base_uom_id'],
          'inventory_uom_id': pN['inventory_uom_id'],
          'sales_uom_id': pN['sales_uom_id'],
          'purchase_uom_id': pN['purchase_uom_id'],
        })) as Json;
        await adjustApi(made, 4);
        final Json? seed = await me.newest('sales-orders');
        if (seed == null) throw StateError('no order to copy the customer from');
        final Json order = (await me.write('POST', '/api/v1/sales-orders', <String, dynamic>{
          'customer_id': seed['customer_id'],
          'branch_id': branchId,
          'warehouse_id': whMain['id'],
          'order_date': today,
          'lines': <Json>[
            <String, dynamic>{'line_number': 1, 'product_id': made['id'], 'quantity': 10},
          ],
        })) as Json;
        await apiAct(me, 'sales-orders', '${order['id']}', 'approve');
        final Json approved = await me.one('sales-orders', '${order['id']}');
        final Json note = (await me.write('POST', '/api/v1/delivery-notes', <String, dynamic>{
          'sales_order_id': order['id'],
          'delivery_date': today,
          'lines': <Json>[
            <String, dynamic>{
              'sales_order_line_id': ((approved['lines'] as List<dynamic>).first as Json)['id'],
              'line_number': 1,
              'current_delivery_quantity': 4,
            },
          ],
        })) as Json;
        await apiAct(me, 'delivery-notes', '${note['id']}', 'approve');
        final Json? held = await invRow(made, whMain);
        await leave(tester);
        await openMenu(tester, 'sell', 'deliveryNotes/delivery-notes');
        await refreshList(tester);
        await selectRow(tester, docNumber(note));
        await tapButton(tester, 'Dispatch');
        final Finder anyway = find.byKey(const ValueKey<String>('dispatch-anyway'));
        final String asked = noticeText(tester);
        if (anyway.evaluate().isNotEmpty) await tester.tap(anyway.first);
        final String said = await watch(tester, seconds: 6);
        final Json now = await me.one('delivery-notes', '${note['id']}');
        final Json? row = await invRow(made, whMain);
        await openStock(tester, 'inventory');
        await searchList(tester, code);
        overflow('Inventory list with a back order');
        log.saw = 'before: on hand ${held?['current_quantity']}, reserved '
            '${held?['reserved_quantity']}; asked "$asked"; said "$said"; note '
            '${now['status']}; after: on hand ${row?['current_quantity']}, reserved '
            '${row?['reserved_quantity']}, available ${row?['available_quantity']}; '
            'the list shows the product=${screenHas(tester, code)}';
        if ('${now['status']}' != 'DISPATCHED' ||
            !sameMoney(num2(row?['current_quantity']), 0) ||
            !sameMoney(num2(row?['reserved_quantity']), 6)) {
          throw StateError(log.saw!);
        }
      });
      await clean(tester);
    }

    log.finish();
  });

  // (the helper below is declared after main so the file reads top-down)
}

/// The newest ledger row carrying [reference], over HTTP.
Future<Json?> rowWhereRef(String reference) async {
  final Server s = await Server.connect();
  final dynamic rows = await s.get(
      '/api/v1/inventory/transactions?page_size=20&reference_number=$reference');
  final List<dynamic> list = rows as List<dynamic>;
  return list.isEmpty ? null : list.first as Json;
}
