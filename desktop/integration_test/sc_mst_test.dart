import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'cases.dart';
import 'harness.dart';

/// Masters screens, click round: Products, Vendors (suppliers) and Places
/// (geography). Run once as the fixture firm's administrator and once as the
/// VIEWER:
///
///     for h in tradeadmin qro; do
///       IT_EMAIL=<suffix>.$h@fixtures.local IT_PASSWORD=Fixture@2026pw \
///         LIMIT=580 bash integration_test/run.sh sc_mst_test.dart; done
///
/// Case ids are MST-PR (products), MST-VN (vendors), MST-GE (places). Every
/// list is looked at at 1600x1000 and again at 800x600, where the menu bar
/// folds Masters under More.
void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('MST: products, vendors, places ($itHandle)',
      (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1600, 1000);
    tester.view.devicePixelRatio = 1;
    final Server me = await Server.connect();
    final Server admin =
        await Server.connectAs(fixtureAdminEmail, fixturePassword);
    await startAndSignIn(tester);
    collectAppErrors();
    final FlowLog log = FlowLog('mst-$itHandle');
    final bool writer = itHandle == 'tradeadmin';
    const String vendorName = 'MST Screen Vendor';
    final String stamp =DateTime.now().millisecondsSinceEpoch.toString();

    // IT_PART: lists, places or editors; empty runs all three.
    const String chosen = String.fromEnvironment('IT_PART');
    bool part(String name) => chosen.isEmpty || chosen == name;

    String shown() => textOnScreen(tester).skip(10).take(70).join(' | ');

    Future<void> sizeIs(Size size) async {
      tester.view.physicalSize = size;
      await pumpFor(tester, const Duration(seconds: 1));
    }

    /// Open a Masters screen; at a width where Masters is folded under More,
    /// go through More.
    Future<void> open(String path) async {
      await closeOpenEditor(tester);
      await tester.sendKeyEvent(LogicalKeyboardKey.escape);
      await pumpFor(tester, const Duration(milliseconds: 300));
      if (find.byKey(const ValueKey<String>('menu-area-masters'))
          .evaluate()
          .isNotEmpty) {
        await openMenu(tester, 'masters', path);
      } else {
        await tester.tap(find.byKey(const ValueKey<String>('menu-area-more')));
        await pumpFor(tester, const Duration(milliseconds: 600));
        final Finder area = find.text('Masters', findRichText: true);
        await pumpUntil(tester, area, waitingFor: 'Masters under More');
        await tester.tap(area.last);
        await pumpFor(tester, const Duration(milliseconds: 600));
        final Finder item = find.byKey(ValueKey<String>('menu-item-$path'));
        await pumpUntil(tester, item, waitingFor: 'menu item $path');
        await tester.tap(item.first);
        await pumpFor(tester, const Duration(seconds: 3));
      }
      await refreshList(tester);
    }

    /// Places sit in Settings > Locations, not in the Masters menu.
    Future<void> openPlaces() async {
      await closeOpenEditor(tester);
      final Finder gear =
          find.byKey(const ValueKey<String>('menu-area-settings'));
      await pumpUntil(tester, gear, waitingFor: 'the Settings menu');
      await tester.tap(gear);
      await pumpFor(tester, const Duration(milliseconds: 800));
      final Finder tile =
          find.byKey(const ValueKey<String>('setup-section-Locations'));
      final Finder subject =
          find.byKey(const ValueKey<String>('setup-subject-locations'));
      await pumpUntil(
          tester,
          find.byWidgetPredicate((Widget w) =>
              w.key == const ValueKey<String>('setup-section-Locations') ||
              w.key == const ValueKey<String>('setup-subject-locations')),
          waitingFor: 'the Locations section');
      if (tile.evaluate().isNotEmpty) {
        await tester.tap(tile);
        await pumpFor(tester, const Duration(milliseconds: 600));
      }
      await pumpUntil(tester, subject, waitingFor: 'the Locations card');
      await tester.tap(subject.first);
      await pumpFor(tester, const Duration(seconds: 2));
      final Finder tab = find.byKey(
          const ValueKey<String>('subject-tab-masters/geography-masters'));
      await pumpUntil(tester, tab, waitingFor: 'the Places tab');
      await tester.tap(tab.first);
      await pumpFor(tester, const Duration(seconds: 3));
      await refreshList(tester);
    }

    void noNewAppErrors(int before) {
      if (appErrors.length > before) {
        throw StateError('the app threw: '
            '${appErrors.skip(before).take(3).join(' || ')}');
      }
    }

    Future<String> firstName(String collection) async {
      final dynamic rows = await admin.get('/api/v1/$collection?page_size=5');
      return '${((rows as List<dynamic>).first as Json)['name']}';
    }

    Future<void> closeMenus() async {
      await tester.sendKeyEvent(LogicalKeyboardKey.escape);
      await pumpFor(tester, const Duration(milliseconds: 400));
    }

    /// The toolbar commands a user is given on the selected row.
    Future<String> commandsOnRow(String name) async {
      await selectRow(tester, name);
      final String edit = buttonState(tester, 'Edit');
      final String edit2 = edit == 'absent' ? await moreState(tester, 'Edit') : edit;
      await closeMenus();
      final String del = buttonState(tester, 'Delete');
      final String del2 = del == 'absent' ? await moreState(tester, 'Delete') : del;
      await closeMenus();
      return 'Edit $edit2, Delete $del2';
    }

    /// Leave a record editor (a page with Cancel and Ctrl+S) without saving.
    Future<void> closeEditor() async {
      if (buttonState(tester, 'Cancel') == 'enabled') {
        await tapButton(tester, 'Cancel');
        await pumpFor(tester, const Duration(seconds: 1));
        final Finder discard = find.text('Discard and close');
        if (discard.evaluate().isNotEmpty) {
          await tester.tap(discard.first);
          await pumpFor(tester, const Duration(seconds: 1));
        }
      }
      await closeOpenEditor(tester);
    }

    Future<void> listCases(String tag, String path, String collection,
        String newLabel, String saveLabel) async {
      for (final Size size in const <Size>[Size(1600, 1000), Size(800, 600)]) {
        final String at = '${size.width.toInt()}x${size.height.toInt()}';
        await sizeIs(size);
        final int errs = appErrors.length;
        await log.step('$tag-001 opens at $at', () async {
          await open(path);
          final int total = await me.total('/api/v1/$collection');
          log.saw = 'api total $total; screen: ${shown()}';
          noNewAppErrors(errs);
        });
        await log.step('$tag-002 search finds a known name at $at', () async {
          final String name = await firstName(collection);
          await searchList(tester, name);
          if (!screenHas(tester, name)) {
            throw StateError('searched "$name", not on screen. ${shown()}');
          }
          log.saw = 'found "$name"';
          noNewAppErrors(errs);
        });
        await log.step('$tag-003 search with no match at $at', () async {
          await searchList(tester, 'zzqx-no-such-$stamp');
          log.saw = shown();
          if (!screenHas(tester, 'No records') && !screenHas(tester, '0 records')) {
            throw StateError('no "No records" message. ${shown()}');
          }
          await searchList(tester, '');
          noNewAppErrors(errs);
        });
        await log.step('$tag-004 write buttons for this user at $at',
            () async {
          // A row tap selects it and shows Open / Edit / Delete beside it.
          final String state = buttonState(tester, newLabel);
          final String name = await firstName(collection);
          await selectRow(tester, name);
          await pumpFor(tester, const Duration(seconds: 1));
          final String openState = buttonState(tester, 'Open');
          final String edit = buttonState(tester, 'Edit');
          final String del = buttonState(tester, 'Delete');
          String save = 'not opened';
          if (openState == 'enabled' || edit == 'enabled') {
            await tapButton(tester, edit == 'enabled' ? 'Edit' : 'Open');
            await pumpFor(tester, const Duration(seconds: 3));
            save = buttonState(tester, saveLabel);
          }
          log.saw = '"$newLabel" $state; selected row: Open $openState, Edit $edit, '
              'Delete $del; the editor it opens: "$saveLabel" $save';
          await closeEditor();
          if (!writer &&
              (state == 'enabled' ||
                  edit == 'enabled' ||
                  del == 'enabled' ||
                  save == 'enabled')) {
            throw StateError('a VIEWER is offered a write button: ${log.saw}');
          }
          if (writer &&
              (state != 'enabled' || edit != 'enabled' || save != 'enabled')) {
            throw StateError('administrator: ${log.saw}');
          }
        });
      }
      await sizeIs(const Size(1600, 1000));
    }

    if (part('lists')) {
      await listCases(
          'MST-VN', 'masters/vendors', 'vendors', '+ New', 'Save vendor');
      await listCases(
          'MST-PR', 'masters/products', 'products', '+ New', 'Save product');
    }

    // -- Places ----------------------------------------------------------
    for (final Size size in part('places')
        ? const <Size>[Size(1600, 1000), Size(800, 600)]
        : const <Size>[]) {
      final String at = '${size.width.toInt()}x${size.height.toInt()}';
      await sizeIs(size);
      final int errs = appErrors.length;
      await log.step('MST-GE-001 Places opens at $at', () async {
        await openPlaces();
        log.saw = shown();
        if (!screenHas(tester, 'India')) {
          throw StateError('India is not listed. ${shown()}');
        }
        noNewAppErrors(errs);
      });
      await log.step('MST-GE-002 Places search at $at', () async {
        await searchList(tester, 'zzqx-none');
        log.saw = shown();
        await searchList(tester, 'India');
        if (!screenHas(tester, 'India')) throw StateError('India not found');
        await searchList(tester, '');
        noNewAppErrors(errs);
      });
      await log.step('MST-GE-003 Places write buttons at $at', () async {
        final String state = buttonState(tester, '+ New');
        final String onRow = await commandsOnRow('India');
        log.saw = '"+ New" $state; on India: $onRow';
        if (state == 'enabled' || onRow.contains('enabled')) {
          throw StateError('a firm user can change geography: ${log.saw}');
        }
      });
      await log.step('MST-GE-004 drill into India at $at', () async {
        await selectRow(tester, 'India');
        await tester.tap(find.text('India').first);
        await pumpFor(tester, const Duration(seconds: 1));
        await tester.tap(find.text('India').first);
        await pumpFor(tester, const Duration(seconds: 3));
        log.saw = shown();
        noNewAppErrors(errs);
      });
    }
    await sizeIs(const Size(1600, 1000));

    if (!part('editors')) {
      // nothing more in this part
    } else if (writer) {
      // -- Vendor editor ------------------------------------------------
      await log.step('MST-VN-010 New vendor, Save with nothing typed',
          () async {
        await open('masters/vendors');
        await tapNew(tester);
        await pumpFor(tester, const Duration(seconds: 2));
        log.saw = 'editor: ${shown()}';
        final int before = await me.total('/api/v1/vendors');
        await tapButton(tester, 'Save vendor');
        await pumpFor(tester, const Duration(seconds: 3));
        final int after = await me.total('/api/v1/vendors');
        log.saw =
            '${log.saw} || after Save: ${shown()} || saved ${after - before}';
        if (after != before) throw StateError('an empty vendor was saved');
        if (buttonState(tester, 'Save vendor') == 'absent') {
          throw StateError('editor closed on an empty Save');
        }
      });
      Future<void> refusedSave(String what, String field, String value) async {
        await closeEditor();
        await open('masters/vendors');
        await tapNew(tester);
        await pumpFor(tester, const Duration(seconds: 2));
        // A name of its own, so a refusal for a repeated name cannot pass
        // for the refusal being tested.
        await typeLabelled(
            tester, 'Vendor Name', 'MST Refusal Probe $field $stamp');
        await typeLabelled(tester, field, value);
        final int before = await me.total('/api/v1/vendors');
        await tapButton(tester, 'Save vendor');
        await pumpFor(tester, const Duration(seconds: 3));
        final int after = await me.total('/api/v1/vendors');
        final List<String> said = textOnScreen(tester)
            .where((String t) =>
                t.length < 120 &&
                RegExp(r'valid|invalid|must|required|not ', caseSensitive: false)
                    .hasMatch(t))
            .toList();
        final List<String> typed = <String>[
          for (final EditableText e
              in tester.widgetList<EditableText>(find.byType(EditableText)))
            if (e.controller.text.isNotEmpty) e.controller.text,
        ];
        log.saw = '$what: saved ${after - before}; said ${said.take(4)}; '
            'boxes hold $typed';
        if (after != before) throw StateError('$what was saved');
        if (buttonState(tester, 'Save vendor') == 'absent') {
          throw StateError('editor closed although $what was refused');
        }
        if (said.isEmpty) throw StateError('N1: nothing says why ($what)');
        await closeEditor();
      }

      await log.step('MST-VN-011 bad email refused', () async {
        await refusedSave('email "not-an-email"', 'Email', 'not-an-email');
      });
      await log.step('MST-VN-011b bad GSTIN refused', () async {
        await refusedSave('GSTIN "12ABC"', 'GSTIN', '12ABC');
      });
      await log.step('MST-VN-011c bad phone refused', () async {
        await refusedSave('phone "98123"', 'Phone', '98123');
      });
      await log.step('MST-VN-012 valid vendor saves and is listed', () async {
        final dynamic have = await admin
            .get('/api/v1/vendors?search=MST%20Screen%20Vendor&page_size=5');
        final bool exists = (have as List<dynamic>).isNotEmpty;
        if (exists) {
          log.saw = 'the vendor from an earlier run exists, not created again';
          await closeEditor();
        } else {
          await closeEditor();
          await open('masters/vendors');
          await tapNew(tester);
          await pumpFor(tester, const Duration(seconds: 2));
          await typeLabelled(tester, 'Vendor Name', vendorName);
          final int before = await me.total('/api/v1/vendors');
          await tapButton(tester, 'Save vendor');
          await pumpFor(tester, const Duration(seconds: 3));
          final int after = await me.total('/api/v1/vendors');
          log.saw = 'saved ${after - before}; ${shown()}';
          if (after != before + 1) {
            throw StateError('expected one new vendor, got ${after - before}');
          }
        }
        await open('masters/vendors');
        await searchList(tester, vendorName);
        if (!screenHas(tester, vendorName)) {
          throw StateError('saved vendor not in the list. ${shown()}');
        }
      });
      await log.step('MST-VN-013 open the vendor, change phone, read back',
          () async {
        await open('masters/vendors');
        await searchList(tester, '');
        await selectRow(tester, vendorName);
        await pumpFor(tester, const Duration(seconds: 1));
        await tapButton(tester, 'Edit');
        await pumpFor(tester, const Duration(seconds: 3));
        await typeLabelled(tester, 'Phone', '+919812345678');
        await tapButton(tester, 'Save vendor');
        await pumpFor(tester, const Duration(seconds: 3));
        final dynamic rows = await admin
            .get('/api/v1/vendors?search=MST%20Screen%20Vendor&page_size=5');
        final Json v = (rows as List<dynamic>).first as Json;
        log.saw = 'phone on server ${v['phone']}';
        if ('${v['phone']}' != '+919812345678') {
          throw StateError('phone not saved: ${v['phone']}');
        }
      });
      // -- Product editor -----------------------------------------------
      await log.step('MST-PR-010 New product, Save with nothing typed',
          () async {
        await open('masters/products');
        await tapNew(tester);
        await pumpFor(tester, const Duration(seconds: 2));
        log.saw = 'editor: ${shown()}';
        final int before = await me.total('/api/v1/products');
        await tapButton(tester, 'Save product');
        await pumpFor(tester, const Duration(seconds: 3));
        final int after = await me.total('/api/v1/products');
        log.saw =
            '${log.saw} || after Save: ${shown()} || saved ${after - before}';
        if (after != before) throw StateError('an empty product was saved');
        if (buttonState(tester, 'Save product') == 'absent') {
          throw StateError('editor closed on an empty Save');
        }
      });
      await log.step('MST-PR-011 editor Cancel leaves nothing', () async {
        final int before = await me.total('/api/v1/products');
        await closeOpenEditor(tester);
        final int after = await me.total('/api/v1/products');
        log.saw = shown();
        if (after != before) throw StateError('Cancel saved a product');
      });
      await log.step('MST-PR-012 open the first product to read it',
          () async {
        await open('masters/products');
        final String name = await firstName('products');
        await selectRow(tester, name);
        await pumpFor(tester, const Duration(seconds: 2));
        await tapButton(tester, 'Open');
        await pumpFor(tester, const Duration(seconds: 3));
        log.saw = shown();
        await closeEditor();
      });
    } else {
      await log.step('MST-VN-020 viewer opens a vendor read-only', () async {
        await open('masters/vendors');
        final String name = await firstName('vendors');
        await selectRow(tester, name);
        await pumpFor(tester, const Duration(seconds: 1));
        final String openState = buttonState(tester, 'Open');
        if (openState == 'enabled') {
          await tapButton(tester, 'Open');
          await pumpFor(tester, const Duration(seconds: 3));
        }
        final String save = buttonState(tester, 'Save vendor');
        log.saw = 'Open $openState; Save vendor $save; ${shown()}';
        await closeEditor();
        if (save == 'enabled') {
          throw StateError('a VIEWER can Save a vendor: ${log.saw}');
        }
      });
      await log.step('MST-PR-020 viewer opens a product read-only', () async {
        await open('masters/products');
        final String name = await firstName('products');
        await selectRow(tester, name);
        await pumpFor(tester, const Duration(seconds: 1));
        final String openState = buttonState(tester, 'Open');
        if (openState == 'enabled') {
          await tapButton(tester, 'Open');
          await pumpFor(tester, const Duration(seconds: 3));
        }
        final String save = buttonState(tester, 'Save product');
        log.saw = 'Open $openState; Save product $save; ${shown()}';
        await closeEditor();
        if (save == 'enabled') {
          throw StateError('a VIEWER can Save a product: ${log.saw}');
        }
      });
      final int status = (await me.attempt('POST', '/api/v1/vendors',
              <String, dynamic>{'name': 'viewer-attempt'}))
          .status;
      log.info('API: a write to /vendors by this user answered', '$status');
    }

    if (part('editors')) {
      await log.step('MST-VN-013 searched list, row click selects', () async {
        await open('masters/vendors');
        await searchList(tester, vendorName);
        if (!screenHas(tester, vendorName)) {
          throw StateError('searched "$vendorName", not on screen. ${shown()}');
        }
        final String before = '${buttonState(tester, 'Open')}/'
            '${buttonState(tester, 'Edit')}';
        // The search stays as typed: the row is tapped in the searched list.
        // The search box holds the same text, so take the list's own Text.
        final Finder rowText = find.byWidgetPredicate(
            (Widget w) => w is Text && (w.data ?? '').contains(vendorName));
        await pumpUntil(tester, rowText, waitingFor: 'the searched row');
        await tester.tap(rowText.first);
        await pumpFor(tester, const Duration(seconds: 1));
        final String openState = buttonState(tester, 'Open');
        final String edit = buttonState(tester, 'Edit');
        log.saw = 'Open/Edit before $before; after Open $openState, '
            'Edit $edit; ${shown()}';
        // A VIEWER has no Open/Edit beside a vendor, so the status bar's
        // "1 selected" counts as the row being selected too.
        if (openState != 'enabled' &&
            edit != 'enabled' &&
            !screenHas(tester, '1 selected')) {
          throw StateError('row not selected after a click in the searched '
              'list. ${log.saw}');
        }
        await searchList(tester, '');
      });
    }

    log.finish();
  });
}
