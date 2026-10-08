import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'cases.dart';
import 'harness.dart';
import 'sc_gt_test.dart'
    show leave, openArea, pickDropdown, pickRow, pressAndRead;

// Batches, lots, serial numbers and the expiry monitor (book:
// docs/qa/SCREEN_TEST_CASES_INVENTORY.md, ids SC-BS-). Run as tradeadmin
// (every case), then qfmgr, qstore, qro for the Role cases. IT_PART names
// sections: batches, lots, serials, expiry.

const String _part = String.fromEnvironment('IT_PART');
bool wants(String section) =>
    _part.isEmpty || _part.split(',').contains(section);

Future<void> openTracking(WidgetTester tester, String tab) =>
    openArea(tester, 'stock', 'inventory/$tab');

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('BS: batch and serial cases ($itHandle)',
      (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1366, 768);
    tester.view.devicePixelRatio = 1;
    final FlowLog log = FlowLog('bs-$itHandle');
    final String stamp = DateTime.now()
        .millisecondsSinceEpoch
        .toRadixString(36)
        .toUpperCase()
        .substring(3);
    final Server me = await Server.connect();
    final bool admin = itHandle == 'tradeadmin';
    final String year = '${DateTime.now().year}';

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
        log.info('APPERROR',
            '$where: ${fresh.where((String e) => !bad.contains(e)).first}');
      }
    }

    /// Pick a product in a form's search box by typing its code.
    Future<void> chooseProduct(String key, String code) async {
      await tester.enterText(find.byKey(ValueKey<String>(key)), code);
      await pumpFor(tester, const Duration(seconds: 3));
      final Finder option = find.textContaining('$code · ');
      await pumpUntil(tester, option, waitingFor: 'the product $code in the box');
      await tester.tap(option.last);
      await pumpFor(tester, const Duration(milliseconds: 600));
    }

    /// Say what pressing [press] in an open form did: the words, whether the
    /// form stayed open, and how many records the server gained.
    Future<({String said, int saved, bool open})> tryForm(
      String collection,
      String openKey,
      Future<void> Function() press,
      String typed,
    ) async {
      final int before = await me.total('/api/v1/batch-serial/$collection');
      final String said = await pressAndRead(tester, press, seconds: 5);
      final bool open = find.byKey(ValueKey<String>(openKey)).evaluate().isNotEmpty;
      final bool kept = !open || screenHasTyped(tester, typed);
      final int after = await me.total('/api/v1/batch-serial/$collection');
      return (
        said: '$said${kept ? '' : ' [the typed text is gone]'}',
        saved: after - before,
        open: open,
      );
    }

    void judgeRefusal(({String said, int saved, bool open}) r, {String? must}) {
      log.saw = 'said "${r.said}"; saved=${r.saved}; dialog open=${r.open}';
      final List<String> faults = <String>[
        if (r.said.isEmpty) 'N1: nothing says why',
        if (must != null && !r.said.toLowerCase().contains(must.toLowerCase()))
          'N1: does not say "$must"',
        if (!r.open || r.said.contains('is gone')) 'N2: closed or lost typing',
        if (r.saved != 0) 'N3: ${r.saved} saved',
      ];
      if (faults.isNotEmpty) throw StateError('${faults.join('; ')} [${log.saw}]');
    }

    // ================= Role cases =================
    if (!admin) {
      final Map<String, List<String>> menu = await offeredMenu(tester);
      // ignore: avoid_print
      print('FLOW: MENU [$itHandle] ${menu.entries.map((MapEntry<String, List<String>> e) => '${e.key}=${e.value.join(',')}').join('; ')}');
      final List<String> items = menu['stock'] ?? <String>[];
      final ({int status, String text}) listApi = await me.attempt(
          'GET', '/api/v1/batch-serial/batches?page_size=1', null);
      final ({int status, String text}) createApi = await me.attempt(
          'POST', '/api/v1/batch-serial/batches', <String, dynamic>{});
      final String id = <String, String>{
        'qfmgr': 'SC-BS-040 firm manager',
        'qstore': 'SC-BS-041 inventory manager',
        'qro': 'SC-BS-042 read only',
        'qsmgr': 'SC-BS-043 sales manager',
        'qsexe': 'SC-BS-043 sales executive',
      }[itHandle] ?? 'SC-BS-04x $itHandle';
      await log.step('$id: what Tracking offers', () async {
        final List<String> tracking = <String>[
          for (final String t in <String>['batches', 'lots', 'serials', 'expiry-monitor'])
            if (items.contains('inventory/$t')) t,
        ];
        log.saw = 'tracking screens offered $tracking; batch list API '
            '${listApi.status}; batch create API (empty body) ${createApi.status}';
        if ((listApi.status == 200) != tracking.isNotEmpty) {
          throw StateError('menu and server disagree: ${log.saw}');
        }
      });
      for (final String tab in <String>['batches', 'lots', 'serials', 'expiry-monitor']) {
        if (!items.contains('inventory/$tab')) continue;
        await log.step('$id: $tab opens; New is offered only with the right',
            () async {
          await openTracking(tester, tab);
          overflow(tab);
          final String add = buttonState(tester, 'New');
          final String plus = buttonState(tester, '+ New');
          log.saw = 'New=$add, + New=$plus; create API ${createApi.status}; '
              'texts ${textOnScreen(tester).take(10).join(' | ')}';
          final bool on = add == 'enabled' || plus == 'enabled';
          if (createApi.status == 403 && on) {
            throw StateError('New offered to a role the server refuses: ${log.saw}');
          }
          if (screenHas(tester, 'Unable to load')) {
            throw StateError('error panel: ${log.saw}');
          }
        });
      }
      log.finish();
      return;
    }

    // ===================================================================
    // Batches
    // ===================================================================
    if (wants('batches')) {
      Future<void> addBatch(String product, String number,
          {String? made, String? expires, String? mrp, String? sell}) async {
        await openTracking(tester, 'batches');
        await tapNew(tester);
        await pumpFor(tester, const Duration(seconds: 2));
        if (product.isNotEmpty) {
          await chooseProduct('batch-form-product', product);
        }
        if (number.isNotEmpty) {
          await typeLabelled(tester, 'Batch Number *', number);
        }
        if (made != null) {
          await typeLabelled(tester, 'Manufacturing Date (YYYY-MM-DD)', made);
        }
        if (expires != null) {
          await typeLabelled(tester, 'Expiry Date (YYYY-MM-DD)', expires);
        }
        if (mrp != null) await typeLabelled(tester, 'MRP', mrp);
        if (sell != null) await typeLabelled(tester, 'Selling price', sell);
      }

      await log.step('SC-BS-001 Batches list opens with its columns', () async {
        await openTracking(tester, 'batches');
        await refreshList(tester);
        overflow('Batches');
        final List<String> missing = <String>[
          for (final String h in <String>['Batch', 'Product', 'Status', 'Expiry'])
            if (!screenHas(tester, h)) h,
        ];
        log.saw = 'INVB1 shown=${screenHas(tester, 'INVB1')}, INVB2 shown=${screenHas(tester, 'INVB2')}';
        if (missing.isNotEmpty) throw StateError('not on screen: $missing');
        if (!screenHas(tester, 'INVB1')) throw StateError(log.saw!);
      });

      await log.step('SC-BS-002 search narrows to one batch', () async {
        await openTracking(tester, 'batches');
        await searchList(tester, 'INVB2');
        final bool one = screenHas(tester, 'INVB2');
        final bool other = screenHas(tester, 'INVB1');
        log.saw = 'INVB2 shown=$one, INVB1 shown=$other';
        await searchList(tester, '');
        if (!one || other) throw StateError(log.saw!);
      });

      await log.step('SC-BS-003 Add Batch saves and the row appears', () async {
        await addBatch('INVSCR-B', 'BSA$stamp',
            made: '$year-01-01', expires: '${DateTime.now().year + 2}-01-01', mrp: '120', sell: '100');
        overflow('Add Batch');
        final r = await tryForm('batches', 'batch-form-mrp',
            () => tapButton(tester, 'Create'), 'BSA$stamp');
        await pumpFor(tester, const Duration(seconds: 2));
        log.saw = 'said "${r.said}"; saved=${r.saved}; open=${r.open}; on the list='
            '${screenHas(tester, 'BSA$stamp')}';
        if (r.saved != 1 || r.open) throw StateError(log.saw!);
      });
      await leave(tester);

      await log.step('SC-BS-004 expiry before manufacturing is refused in words',
          () async {
        await addBatch('INVSCR-B', 'BSX$stamp',
            made: '${DateTime.now().year + 1}-06-01', expires: '$year-01-01');
        judgeRefusal(
            await tryForm('batches', 'batch-form-mrp',
                () => tapButton(tester, 'Create'), 'BSX$stamp'),
            must: 'date');
      });
      await leave(tester);

      await log.step('SC-BS-005 a batch number already used for the product is refused',
          () async {
        await addBatch('INVSCR-B', 'INVB1');
        judgeRefusal(
            await tryForm('batches', 'batch-form-mrp',
                () => tapButton(tester, 'Create'), 'INVB1'),
            must: 'INVB1');
      });
      await leave(tester);

      await log.step('SC-BS-006 no batch number is refused', () async {
        await addBatch('INVSCR-B', '');
        judgeRefusal(await tryForm('batches', 'batch-form-mrp',
            () => tapButton(tester, 'Create'), 'INVSCR-B'));
      });
      await leave(tester);

      await log.step('SC-BS-007 a product that tracks no batch is refused',
          () async {
        await addBatch('INVSCR-N', 'BSN$stamp');
        judgeRefusal(
            await tryForm('batches', 'batch-form-mrp',
                () => tapButton(tester, 'Create'), 'BSN$stamp'),
            must: 'batch');
      });
      await leave(tester);

      await log.step('SC-BS-008 a selling price above the MRP is refused',
          () async {
        await addBatch('INVSCR-B', 'BSM$stamp', mrp: '50', sell: '90');
        final r = await tryForm('batches', 'batch-form-mrp',
            () => tapButton(tester, 'Create'), 'BSM$stamp');
        log.saw = 'said "${r.said}"; saved=${r.saved}; open=${r.open}';
        if (r.saved != 0) throw StateError('a batch selling above its MRP was saved: ${log.saw}');
      });
      await leave(tester);

    }
    if (wants('batches2')) {
      // An earlier run left the Status filter on EXPIRED for this user.
      await openTracking(tester, 'batches');
      if (find.text('Clear').evaluate().isEmpty) {
        await tapKey(tester, 'phase2-filters');
        await pumpFor(tester, const Duration(seconds: 1));
      }
      if (find.text('Clear').evaluate().isNotEmpty) {
        await tester.tap(find.text('Clear').last);
        await pumpFor(tester, const Duration(milliseconds: 600));
        await tester.tap(find.text('Apply').last);
        await pumpFor(tester, const Duration(seconds: 2));
      }
      String bsa = 'BSA';
      final dynamic made =
          await me.get('/api/v1/batch-serial/batches?page_size=100&search=BSA');
      for (final dynamic b in made as List<dynamic>) {
        final String n = '${(b as Json)['batch_number']}';
        if (n.startsWith('BSA') && b['is_deleted'] != true) {
          bsa = n;
          break;
        }
      }
      await log.step('SC-BS-009 Open a batch shows its details', () async {
        await openTracking(tester, 'batches');
        await searchList(tester, 'INVB1');
        await pickRow(tester, 'INVB1');
        await tapButton(tester, 'Open');
        await pumpFor(tester, const Duration(seconds: 1));
        overflow('Batch details');
        final bool title = screenHas(tester, 'Batch: INVB1');
        log.saw = 'title shown=$title; ${noticeText(tester).split(' | ').take(10).join(' | ')}';
        if (!title) throw StateError(log.saw!);
      });
      await leave(tester);

      await log.step('SC-BS-010 Edit a batch: change the remarks and save',
          () async {
        await openTracking(tester, 'batches');
        await searchList(tester, bsa);
        await pickRow(tester, bsa);
        await tapButton(tester, 'Open');
        await pumpFor(tester, const Duration(seconds: 1));
        await tapDialogButton(tester, 'Edit');
        await pumpFor(tester, const Duration(seconds: 1));
        await typeLabelled(tester, 'Remarks', 'edited $stamp');
        final String said =
            await pressAndRead(tester, () => tapButton(tester, 'Save'));
        await pumpFor(tester, const Duration(seconds: 2));
        final dynamic rows = await me.get('/api/v1/batch-serial/batches?page_size=100&search=$bsa');
        final String remarks = '${((rows as List<dynamic>).first as Json)['remarks']}';
        log.saw = 'said "$said"; server remarks "$remarks"';
        if (remarks != 'edited $stamp') throw StateError(log.saw!);
      });
      await leave(tester);

      await log.step('SC-BS-011 Delete a batch through the row menu asks first',
          () async {
        await openTracking(tester, 'batches');
        await searchList(tester, bsa);
        final Finder row = find.byWidgetPredicate(
            (Widget w) => w is Text && (w.data ?? '').trim() == bsa);
        await pumpUntil(tester, row, waitingFor: 'the BSA row');
        await tester.tapAt(tester.getCenter(row.last), buttons: kSecondaryMouseButton);
        await pumpFor(tester, const Duration(seconds: 2));
        final Finder del = find.text('Delete');
        if (del.evaluate().isEmpty) {
          throw StateError('no Delete in the row menu: ${textOnScreen(tester).take(30)}');
        }
        await tester.tap(del.last);
        await pumpFor(tester, const Duration(seconds: 1));
        final bool asked = screenHas(tester, 'Delete batch?');
        final String said = await pressAndRead(
            tester, () => tapDialogButton(tester, 'Delete'));
        await pumpFor(tester, const Duration(seconds: 2));
        final dynamic rows = await me.get('/api/v1/batch-serial/batches?page_size=100&search=$bsa');
        log.saw = 'asked=$asked; said "$said"; batches left on server ${(rows as List<dynamic>).length}';
        if (!asked || rows.isNotEmpty) throw StateError(log.saw!);
      });
      await leave(tester);

      await log.step('SC-BS-012 a batch holding stock cannot be deleted; the words stay',
          () async {
        await openTracking(tester, 'batches');
        await searchList(tester, 'INVB2');
        final Finder row = find.byWidgetPredicate(
            (Widget w) => w is Text && (w.data ?? '').trim() == 'INVB2');
        await pumpUntil(tester, row, waitingFor: 'the INVB2 row');
        await tester.tapAt(tester.getCenter(row.last), buttons: kSecondaryMouseButton);
        await pumpFor(tester, const Duration(seconds: 2));
        await tester.tap(find.text('Delete').last);
        await pumpFor(tester, const Duration(seconds: 1));
        final String said = await pressAndRead(
            tester, () => tapDialogButton(tester, 'Delete'));
        final dynamic rows = await me.get('/api/v1/batch-serial/batches?page_size=100&search=INVB2');
        log.saw = 'said "$said"; INVB2 still on server=${(rows as List<dynamic>).isNotEmpty}';
        if (rows.isEmpty) throw StateError('a batch holding 20 on hand was deleted');
        if (said.isEmpty) throw StateError('N1: nothing said: ${log.saw}');
      });
      await leave(tester);

      await log.step('SC-BS-013 the Status filter keeps only that status', () async {
        await openTracking(tester, 'batches');
        await tapKey(tester, 'phase2-filters');
        await pumpFor(tester, const Duration(seconds: 1));
        await pickDropdown(tester, 'Status', 'EXPIRED');
        await tapButton(tester, 'Apply');
        await pumpFor(tester, const Duration(seconds: 2));
        final bool mine = screenHas(tester, 'INVB1');
        log.saw = 'an AVAILABLE batch shown under EXPIRED=$mine';
        await tester.tap(find.text('Clear').last);
        await pumpFor(tester, const Duration(milliseconds: 600));
        await tester.tap(find.text('Apply').last);
        await pumpFor(tester, const Duration(seconds: 2));
        if (mine) throw StateError(log.saw!);
      });
      await leave(tester);
    }

    // ===================================================================
    // Lots
    // ===================================================================
    if (wants('lots')) {
      Future<void> addLot(String product, String number, {String? qty}) async {
        await openTracking(tester, 'lots');
        await tapNew(tester);
        await pumpFor(tester, const Duration(seconds: 2));
        if (product.isNotEmpty) await chooseProduct('lot-form-product', product);
        if (number.isNotEmpty) await typeLabelled(tester, 'Lot Number *', number);
        if (qty != null) await typeLabelled(tester, 'Quantity', qty);
      }

      await log.step('SC-BS-014 Lots list opens', () async {
        await openTracking(tester, 'lots');
        overflow('Lots');
        final bool ok = screenHas(tester, 'Lot') || screenHas(tester, 'No ');
        log.saw = 'texts ${textOnScreen(tester).take(16).join(' | ')}';
        if (!ok) throw StateError(log.saw!);
      });

      await log.step('SC-BS-015 Add Lot saves and the row appears', () async {
        await addLot('INVSCR-B', 'LOT$stamp', qty: '10');
        overflow('Add Lot');
        final r = await tryForm('lots', 'lot-form-product',
            () => tapButton(tester, 'Create'), 'LOT$stamp');
        await pumpFor(tester, const Duration(seconds: 2));
        log.saw = 'said "${r.said}"; saved=${r.saved}; open=${r.open}; on list='
            '${screenHas(tester, 'LOT$stamp')}';
        if (r.saved != 1 || r.open) throw StateError(log.saw!);
      });
      await leave(tester);

    }
    if (wants('lots2')) {
      Future<void> addLot(String product, String number, {String? qty}) async {
        await openTracking(tester, 'lots');
        await tapNew(tester);
        await pumpFor(tester, const Duration(seconds: 2));
        if (product.isNotEmpty) await chooseProduct('lot-form-product', product);
        if (number.isNotEmpty) await typeLabelled(tester, 'Lot Number *', number);
        if (qty != null) await typeLabelled(tester, 'Quantity', qty);
      }
      String lotNo = 'LOT';
      final dynamic lots = await me.get('/api/v1/batch-serial/lots?page_size=100&search=LOT');
      if ((lots as List<dynamic>).isNotEmpty) lotNo = '${(lots.first as Json)['lot_number']}';
      await log.step('SC-BS-016 a lot with no number is refused', () async {
        await addLot('INVSCR-B', '', qty: '5');
        judgeRefusal(await tryForm('lots', 'lot-form-product',
            () => tapButton(tester, 'Create'), '5'));
      });
      await leave(tester);

      await log.step('SC-BS-017 a lot number already used is refused', () async {
        await addLot('INVSCR-B', lotNo, qty: '3');
        judgeRefusal(await tryForm('lots', 'lot-form-product',
            () => tapButton(tester, 'Create'), lotNo));
      });
      await leave(tester);

      await log.step('SC-BS-018 a lot with a negative quantity is refused',
          () async {
        await addLot('INVSCR-B', 'LOTN$stamp', qty: '-5');
        judgeRefusal(await tryForm('lots', 'lot-form-product',
            () => tapButton(tester, 'Create'), 'LOTN$stamp'));
      });
      await leave(tester);

      await log.step('SC-BS-019 Open a lot shows its details', () async {
        await openTracking(tester, 'lots');
        await searchList(tester, lotNo);
        await pickRow(tester, lotNo);
        await tapButton(tester, 'Open');
        await pumpFor(tester, const Duration(seconds: 1));
        final bool title = screenHas(tester, 'Lot: $lotNo');
        log.saw = 'title shown=$title';
        if (!title) throw StateError(log.saw!);
      });
      await leave(tester);
    }

    // ===================================================================
    // Serial numbers
    // ===================================================================
    if (wants('serials')) {
      Future<void> addSerial(String product, String number,
          {String? wStart, String? wEnd}) async {
        await openTracking(tester, 'serials');
        await tapNew(tester);
        await pumpFor(tester, const Duration(seconds: 2));
        if (product.isNotEmpty) await chooseProduct('serial-form-product', product);
        if (number.isNotEmpty) await typeLabelled(tester, 'Serial Number *', number);
        if (wStart != null) await typeLabelled(tester, 'Warranty Start (YYYY-MM-DD)', wStart);
        if (wEnd != null) await typeLabelled(tester, 'Warranty End (YYYY-MM-DD)', wEnd);
      }

      await log.step('SC-BS-020 Serial Numbers list opens with the three serials',
          () async {
        await openTracking(tester, 'serials');
        overflow('Serial Numbers');
        final bool all = screenHas(tester, 'INVS-0001') && screenHas(tester, 'INVS-0003');
        log.saw = 'INVS-0001..3 shown=$all';
        if (!all) throw StateError(log.saw!);
      });

      await log.step('SC-BS-021 Add Serial saves and the row appears', () async {
        await addSerial('INVSCR-S', 'BSS$stamp',
            wStart: '$year-01-01', wEnd: '${DateTime.now().year + 1}-01-01');
        overflow('Add Serial');
        final r = await tryForm('serials', 'serial-form-product',
            () => tapButton(tester, 'Create'), 'BSS$stamp');
        await pumpFor(tester, const Duration(seconds: 2));
        log.saw = 'said "${r.said}"; saved=${r.saved}; open=${r.open}; on list='
            '${screenHas(tester, 'BSS$stamp')}';
        if (r.saved != 1 || r.open) throw StateError(log.saw!);
      });
      await leave(tester);

      await log.step('SC-BS-022 a serial number already used is refused',
          () async {
        await addSerial('INVSCR-S', 'INVS-0001');
        judgeRefusal(await tryForm('serials', 'serial-form-product',
            () => tapButton(tester, 'Create'), 'INVS-0001'),
            must: 'INVS-0001');
      });
      await leave(tester);

      await log.step('SC-BS-023 a serial with no number is refused', () async {
        await addSerial('INVSCR-S', '');
        judgeRefusal(await tryForm('serials', 'serial-form-product',
            () => tapButton(tester, 'Create'), 'INVSCR-S'));
      });
      await leave(tester);

      await log.step('SC-BS-024 warranty ending before it starts is refused',
          () async {
        await addSerial('INVSCR-S', 'BSW$stamp',
            wStart: '${DateTime.now().year + 1}-06-01', wEnd: '$year-01-01');
        judgeRefusal(await tryForm('serials', 'serial-form-product',
            () => tapButton(tester, 'Create'), 'BSW$stamp'),
            must: 'warranty');
      });
      await leave(tester);

      await log.step('SC-BS-025 a serial for a product that tracks none is refused',
          () async {
        await addSerial('INVSCR-N', 'BSZ$stamp');
        judgeRefusal(await tryForm('serials', 'serial-form-product',
            () => tapButton(tester, 'Create'), 'BSZ$stamp'),
            must: 'serial');
      });
      await leave(tester);

      await log.step('SC-BS-026 Open a serial shows its warranty', () async {
        await openTracking(tester, 'serials');
        await searchList(tester, 'INVS-0002');
        await pickRow(tester, 'INVS-0002');
        await tapButton(tester, 'Open');
        await pumpFor(tester, const Duration(seconds: 1));
        overflow('Serial details');
        final bool title = screenHas(tester, 'Serial: INVS-0002');
        final bool warranty = screenHas(tester, 'Warranty');
        log.saw = 'title shown=$title, warranty shown=$warranty';
        if (!title || !warranty) throw StateError(log.saw!);
      });
      await leave(tester);

      await log.step('SC-BS-027 the Status filter keeps only that status', () async {
        await openTracking(tester, 'serials');
        await tapKey(tester, 'phase2-filters');
        await pumpFor(tester, const Duration(seconds: 1));
        await pickDropdown(tester, 'Status', 'SOLD');
        await tapButton(tester, 'Apply');
        await pumpFor(tester, const Duration(seconds: 2));
        final bool mine = screenHas(tester, 'INVS-0001');
        log.saw = 'an AVAILABLE serial shown under SOLD=$mine';
        await tester.tap(find.text('Clear').last);
        await pumpFor(tester, const Duration(milliseconds: 600));
        await tester.tap(find.text('Apply').last);
        await pumpFor(tester, const Duration(seconds: 2));
        if (mine) throw StateError(log.saw!);
      });
      await leave(tester);
    }

    // ===================================================================
    // Expiry monitor
    // ===================================================================
    if (wants('expiry')) {
      await log.step('SC-BS-030 Expiry Monitor shows its six cards and the batch grid',
          () async {
        await openTracking(tester, 'expiry-monitor');
        overflow('Expiry Monitor');
        final List<String> missing = <String>[
          for (final String h in <String>[
            'Expired today', 'In 7 days', 'In 30 days', 'Expired', 'Quarantine', 'Recalled'
          ])
            if (!screenHas(tester, h)) h,
        ];
        log.saw = 'cards missing: $missing; texts ${textOnScreen(tester).take(24).join(' | ')}';
        if (missing.isNotEmpty) throw StateError(log.saw!);
      });

      await log.step('SC-BS-031 the 30-day card counts the batch that expires in 20 days',
          () async {
        await openTracking(tester, 'expiry-monitor');
        final dynamic dash =
            await me.get('/api/v1/batch-serial/batches/expiry-dashboard');
        final List<String> shown = textOnScreen(tester);
        final int idx = shown.indexWhere((String t) => t.toLowerCase() == 'in 30 days');
        final String cardValue = idx >= 0 && idx + 1 < shown.length ? shown[idx + 1] : '?';
        final String near = idx > 0 ? shown[idx - 1] : '?';
        log.saw = 'server $dash; card neighbours "$near" / "$cardValue"';
        final String server30 = '${(dash as Json)['expire_in_30_days']}';
        if (cardValue != server30 && near != server30) {
          throw StateError('the card does not match the server: ${log.saw}');
        }
      });

      await log.step('SC-BS-032 Refresh re-reads the monitor without an error',
          () async {
        await openTracking(tester, 'expiry-monitor');
        await refreshList(tester);
        log.saw = 'error panel=${screenHas(tester, 'Failed to load')}';
        if (screenHas(tester, 'Failed to load')) throw StateError(log.saw!);
      });

      await log.step('SC-BS-033 batch rows in the monitor show INVB1 with its expiry',
          () async {
        await openTracking(tester, 'expiry-monitor');
        final bool row = screenHas(tester, 'INVB1');
        log.saw = 'INVB1 listed=$row';
        if (!row) throw StateError(log.saw!);
      });
    }
    await me.get('/api/v1/batch-serial/batches?page_size=1');
    log.finish();
  });
}
