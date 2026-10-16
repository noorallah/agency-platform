import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'cases.dart';
import 'harness.dart';
import 'sc_gt_test.dart' show leave, openArea, pickRow, pressAndRead;

/// Costing by lot on the screens (book 07, TC-LOT-001 to TC-LOT-014; the
/// HTTP halves are `docs/qa/checks/lots/`). Run on the `lot-firm` fixture
/// (`docs/qa/checks/lots/setup.py`) as lotadmin, then as lotviewer; the
/// TC-LOT-001 preview runs as the admin of the firm still on Average that
/// setup.py makes (`IT_PART=average`).
///
/// The admin opens Settings > Stock > Costing method on a firm by lot (By
/// lot, its day, the billing switch, no way back) and turns the billing
/// switch on and off again, receives two batch lines of a new product on a
/// goods receipt on the screen and completes it, then reads the lots in
/// Stock valuation by lot. A delivery note line opens the batch picker: the
/// lots that agree are one row, an unprinted lot shows a dash. The four lot
/// reports open, and a lot's Trace lists what it went through. The viewer
/// does the same reading with every cost left out. The server is compared
/// before and after each write, and app errors and overflows are counted
/// the whole time.
///
/// Every run makes its own masters over HTTP (a supplier, a customer, a
/// batch-tracked product B and a plain product P, codes starting `0L` so
/// they sort first in the lot reports), named with the minute it started.

/// IT_PART=settings (or receipt, picker, reports, trace, average) runs only
/// that part. `average` runs only when asked for by name.
const String _part = String.fromEnvironment('IT_PART');
bool _runs(String part) =>
    (_part.isEmpty && part != 'average') || _part.split(',').contains(part);

const String _costingTab = 'settings/stock-costing';
const String _inv = '/api/v1/inventory';

String _today() => DateTime.now().toIso8601String().substring(0, 10);

String _day(DateTime d) => d.toIso8601String().substring(0, 10);

double _n(dynamic v) => double.tryParse('${v ?? ''}'.replaceAll(',', '')) ?? 0;

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('LOT: costing by lot ($itHandle)', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1600, 1000);
    tester.view.devicePixelRatio = 1;
    final bool average = _part.split(',').contains('average');
    final bool isAdmin = itHandle == 'lotadmin' || average;
    final Server admin = average
        ? await Server.connect()
        : await Server.connectAs(
            '$itSuffix.lotadmin@fixtures.local', fixturePassword);
    final Server me = await Server.connect();
    await startAndSignIn(tester);
    collectAppErrors();
    final FlowLog log = FlowLog('lot-$itHandle');

    final DateTime now = DateTime.now();
    final String stamp = '${now.hour.toString().padLeft(2, '0')}'
        '${now.minute.toString().padLeft(2, '0')}';
    final String tag = '$stamp${isAdmin ? 'A' : 'V'}';
    final String nameB = 'LT lot B $tag';
    final String nameP = 'LT lot P $tag';
    final String expiry = _day(now.add(const Duration(days: 182)));

    String errorsSince(int from) => appErrors.skip(from).take(3).join(' || ');

    // -- Reading the server --------------------------------------------------
    Future<List<Json>> list(String path) async => <Json>[
          for (final dynamic row in (await admin.get(path)) as List<dynamic>)
            row as Json,
        ];
    Future<Json> lotSettings() async =>
        (await admin.get('$_inv/lot-settings')) as Json;

    // -- Masters, made over HTTP ---------------------------------------------
    late Json branch, warehouse, vendor, customer, productB, productP;
    late String piece;
    Json? poB;

    Future<String> brandId() async {
      for (final Json b in await list('/api/v1/products/brands')) {
        if (b['name'] == 'Check Brand' || b['name'] == 'Fixture Brand') {
          return '${b['id']}';
        }
      }
      final Json company = (await admin.write('POST',
          '/api/v1/products/principals',
          <String, dynamic>{'code': 'FIXTURE', 'name': 'Fixture Company'})) as Json;
      final Json brand = (await admin.write('POST', '/api/v1/products/brands',
          <String, dynamic>{
            'name': 'Fixture Brand',
            'principal_id': company['id'],
          })) as Json;
      return '${brand['id']}';
    }

    Future<Json> makeProduct(String code, String name, bool batch) async =>
        (await admin.write('POST', '/api/v1/products', <String, dynamic>{
          'code': code,
          'brand_id': await brandId(),
          'name': name,
          'product_type': 'STOCK_ITEM',
          'tax_profile_group_code': 'GST_18_LOCAL',
          'selling_price': '100',
          'purchase_price': '50',
          'base_uom_id': piece,
          'inventory_uom_id': piece,
          'sales_uom_id': piece,
          'purchase_uom_id': piece,
          'track_batch': batch,
          'track_expiry': batch,
        })) as Json;

    /// An approved purchase order of [lines] (product, quantity, rate).
    Future<Json> approvedPo(List<(Json, num, num)> lines) async {
      final Json po = (await admin.write('POST', '/api/v1/purchases',
          <String, dynamic>{
            'vendor_id': vendor['id'],
            'branch_id': branch['id'],
            'warehouse_id': warehouse['id'],
            'purchase_date': _today(),
            'lines': <Json>[
              for (final (Json, num, num) l in lines)
                <String, dynamic>{
                  'product_id': l.$1['id'],
                  'ordered_quantity': '${l.$2}',
                  'unit_price': '${l.$3}',
                  'purchase_uom_id': piece,
                  'inventory_uom_id': piece,
                },
            ],
          })) as Json;
      await apiAct(admin, 'purchases', '${po['id']}', 'submit');
      await apiAct(admin, 'purchases', '${po['id']}', 'approve');
      return admin.one('purchases', '${po['id']}');
    }

    /// Receive every line of [po] over HTTP and complete it; [extra] adds
    /// batch fields per line.
    Future<Json> receiveOverHttp(Json po, List<Json> extra) async {
      final List<dynamic> lines = po['lines'] as List<dynamic>;
      final Json gr = (await admin.write('POST', '/api/v1/goods-receipts',
          <String, dynamic>{
            'purchase_order_id': po['id'],
            'receipt_date': _today(),
            'lines': <Json>[
              for (int i = 0; i < lines.length; i++)
                <String, dynamic>{
                  'purchase_order_line_id': (lines[i] as Json)['id'],
                  'line_number': i + 1,
                  'current_receipt_quantity':
                      (lines[i] as Json)['ordered_quantity'],
                  'warehouse_id': warehouse['id'],
                  ...extra[i],
                },
            ],
          })) as Json;
      await apiAct(admin, 'goods-receipts', '${gr['id']}', 'complete');
      return admin.one('goods-receipts', '${gr['id']}');
    }

    Future<List<Json>> batchesOf(Json product) async => <Json>[
          for (final Json b in await list('/api/v1/batch-serial/batches'
              '?product_id=${product['id']}&page_size=100'))
            if (b['product_id'] == product['id']) b,
        ];

    Future<List<Json>> lotsOf(Json product, Server who) async => <Json>[
          for (final dynamic r in (await who.get('$_inv/reports/stock-valuation/'
                  'lots?product_id=${product['id']}')) as List<dynamic>)
            r as Json,
        ];

    Future<void> masters() async {
      for (final Json b in await list('/api/v1/branches?page_size=100')) {
        if (b['code'] == 'HO') branch = b;
      }
      for (final Json w in await list('/api/v1/warehouses?page_size=100')) {
        if (w['code'] == 'MAIN') warehouse = w;
      }
      for (final Json u in await list('/api/v1/uom-framework/uoms?page_size=100')) {
        if (u['code'] == 'PIECE') piece = '${u['id']}';
      }
      vendor = (await admin.write('POST', '/api/v1/vendors', <String, dynamic>{
        'code': 'LV$tag',
        'name': 'LT supplier $tag',
      })) as Json;
      customer = (await admin.write('POST', '/api/v1/customers',
          <String, dynamic>{
            'code': 'LC$tag',
            'name': 'LT buyer $tag',
            'customer_type': 'BUSINESS',
            'currency_code': 'INR',
          })) as Json;
      productB = await makeProduct('0L$tag-B', nameB, true);
      productP = await makeProduct('0L$tag-P', nameP, false);
      poB = await approvedPo(<(Json, num, num)>[
        (productB, 10, 40),
        (productB, 5, 42),
      ]);
    }

    /// The rest of the stock: P received with no batch (an unprinted lot)
    /// and five more of B in a lot agreeing with LOTA in everything but its
    /// cost, so the picker has a group to show.
    Future<String> moreStock() async {
      final List<String> said = <String>[];
      final Json poP = await approvedPo(<(Json, num, num)>[(productP, 8, 30)]);
      await receiveOverHttp(poP, <Json>[<String, dynamic>{}]);
      Json? lotA;
      for (final Json b in await batchesOf(productB)) {
        if (b['batch_number'] == 'LOTA') lotA = b;
      }
      if (lotA == null) return 'no LOTA to agree with';
      final Json po3 = await approvedPo(<(Json, num, num)>[(productB, 5, 44)]);
      await receiveOverHttp(po3, <Json>[
        <String, dynamic>{
          'batch_number': 'LOTA',
          'expiry_date': lotA['expiry_date'],
          if (lotA['mrp'] != null) 'mrp': '${lotA['mrp']}',
          if (lotA['selling_price'] != null)
            'selling_price': '${lotA['selling_price']}',
          if (lotA['ptr'] != null) 'ptr': '${lotA['ptr']}',
          if (lotA['pts'] != null) 'pts': '${lotA['pts']}',
        },
      ]);
      said.add('P 8 at 30 received; B 5 at 44 into a second LOTA');
      return said.join('; ');
    }

    /// An approved order for 3 of B and 2 of P to the run's customer.
    Future<Json> approvedOrder() async {
      final Json o = (await admin.write('POST', '/api/v1/sales-orders',
          <String, dynamic>{
            'customer_id': customer['id'],
            'branch_id': branch['id'],
            'warehouse_id': warehouse['id'],
            'order_date': _today(),
            'lines': <Json>[
              <String, dynamic>{
                'line_number': 1,
                'product_id': productB['id'],
                'quantity': 3,
                'unit_price': '50',
              },
              <String, dynamic>{
                'line_number': 2,
                'product_id': productP['id'],
                'quantity': 2,
                'unit_price': '50',
              },
            ],
          })) as Json;
      await apiAct(admin, 'sales-orders', '${o['id']}', 'approve');
      return admin.one('sales-orders', '${o['id']}');
    }

    // -- Moving about --------------------------------------------------------
    Future<void> away() => leave(tester);

    /// The gear, Stock, the costing tab, its window.
    Future<bool> openCosting() async {
      await away();
      await tester.tap(find.byKey(const ValueKey<String>('menu-area-settings')));
      await pumpUntil(tester, find.byKey(const ValueKey<String>('setup-search')),
          waitingFor: 'the Settings page');
      await pumpFor(tester, const Duration(milliseconds: 500));
      final Finder tile = find.byKey(const ValueKey<String>('setup-section-Stock'));
      if (tile.evaluate().isEmpty) throw StateError('no Stock section in Settings');
      await tester.ensureVisible(tile);
      await tester.tap(tile);
      await pumpFor(tester, const Duration(milliseconds: 700));
      await tapKey(tester, 'setup-subject-stock');
      await pumpUntil(tester, find.byKey(const ValueKey<String>('subject-strip')),
          waitingFor: 'the Stock subject screen');
      await pumpFor(tester, const Duration(seconds: 1));
      final Finder tab = find.byKey(const ValueKey<String>('subject-tab-$_costingTab'));
      if (tab.evaluate().isEmpty) return false;
      await tester.ensureVisible(tab);
      await tester.tap(tab);
      await pumpFor(tester, const Duration(seconds: 2));
      final Finder window =
          find.byKey(const ValueKey<String>('subject-window-$_costingTab'));
      if (window.evaluate().isNotEmpty) {
        await tester.ensureVisible(window);
        await tester.tap(window);
      }
      await pumpUntil(tester, find.text('Costing method'),
          waitingFor: 'the Costing method window');
      await pumpUntil(tester, find.byKey(const ValueKey<String>('stock-costing-method')),
          waitingFor: 'the costing method read');
      await pumpFor(tester, const Duration(seconds: 1));
      return true;
    }

    String keyedText(String key) {
      final Finder f = find.byKey(ValueKey<String>(key));
      if (f.evaluate().isEmpty) return '(absent)';
      final Widget w = tester.widget(f.first);
      return w is Text ? (w.data ?? '') : '(not text)';
    }

    SwitchListTile? billingSwitch() {
      final Finder f = find.byKey(const ValueKey<String>('stock-costing-allow-billing'));
      return f.evaluate().isEmpty ? null : tester.widget<SwitchListTile>(f.first);
    }

    String switchButton() {
      final Finder f = find.byKey(const ValueKey<String>('stock-costing-switch'));
      if (f.evaluate().isEmpty) return 'absent';
      return tester.widget<FilledButton>(f.first).onPressed == null
          ? 'disabled'
          : 'enabled';
    }

    /// Every string key on screen starting [prefix].
    List<String> keysStarting(String prefix) => <String>{
          for (final Element e in find.byWidgetPredicate((Widget w) {
            final Key? k = w.key;
            return k is ValueKey<String> && k.value.startsWith(prefix);
          }).evaluate())
            (e.widget.key! as ValueKey<String>).value,
        }.toList();

    /// Every grid row whose cell reads exactly [name]: the texts level with
    /// each, left to right.
    List<List<String>> rowsNamed(String name) {
      final List<List<String>> out = <List<String>>[];
      for (final Element anchor in find
          .byWidgetPredicate((Widget w) => w is Text && (w.data ?? '').trim() == name)
          .evaluate()) {
        final RenderObject? ab = anchor.renderObject;
        if (ab is! RenderBox || !ab.attached) continue;
        final double y = ab.localToGlobal(ab.size.center(Offset.zero)).dy;
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
        out.add(<String>[for (final MapEntry<double, String> m in found) m.value]);
      }
      return out;
    }

    bool rowHasFigure(List<String> row, double value) => row.any(
        (String c) => (_n(c) - value).abs() < 0.005 && c.contains(RegExp(r'\d')));

    /// Pick [iso] in the date picker the box [key] opens.
    Future<void> pickDate(String key, String iso) async {
      await tapKey(tester, key);
      await pumpFor(tester, const Duration(milliseconds: 800));
      final Finder toInput = find.byTooltip('Switch to input');
      if (toInput.evaluate().isNotEmpty) {
        await tester.tap(toInput.last);
        await pumpFor(tester, const Duration(milliseconds: 500));
      }
      final Finder field = find.descendant(
          of: find.byType(Dialog).last, matching: find.byType(TextField));
      await pumpUntil(tester, field, waitingFor: 'the date picker box');
      final TextField box = tester.widget<TextField>(field.first);
      final String hint =
          (box.decoration?.hintText ?? box.decoration?.helperText ?? 'mm/dd/yyyy')
              .toLowerCase();
      final DateTime d = DateTime.parse(iso);
      String two(int v) => v.toString().padLeft(2, '0');
      final String sep = RegExp(r'[^a-z]').firstMatch(hint)?.group(0) ?? '/';
      final String typed = hint.startsWith('dd')
          ? '${two(d.day)}$sep${two(d.month)}$sep${d.year}'
          : hint.startsWith('y')
              ? '${d.year}$sep${two(d.month)}$sep${two(d.day)}'
              : '${two(d.month)}$sep${two(d.day)}$sep${d.year}';
      await tester.enterText(field.first, typed);
      await pumpFor(tester, const Duration(milliseconds: 300));
      await tapDialogButton(tester, 'OK');
      await pumpFor(tester, const Duration(milliseconds: 600));
    }

    /// Type into the box keyed exactly [key] (its inner editable text).
    Future<void> typeKeyed(String key, String text) async {
      final Finder box = find.byKey(ValueKey<String>(key));
      await pumpUntil(tester, box, waitingFor: 'box $key');
      await tester.ensureVisible(box.first);
      final Finder inner =
          find.descendant(of: box.first, matching: find.byType(EditableText));
      final Finder target = inner.evaluate().isEmpty ? box.first : inner.first;
      await tester.enterText(target, text);
      await pumpFor(tester, const Duration(milliseconds: 400));
      // A box that kept its old text did not take the keyboard: tap it
      // into focus and type again.
      if (inner.evaluate().isNotEmpty &&
          tester.widget<EditableText>(inner.first).controller.text != text) {
        await tester.tap(inner.first);
        await pumpFor(tester, const Duration(milliseconds: 400));
        await tester.enterText(inner.first, text);
        await pumpFor(tester, const Duration(milliseconds: 400));
      }
    }

    /// Reports > [area], the report labelled [label]; what the screen shows.
    Future<({bool offered, String error, bool grid, bool empty})> openReport(
        String area, String id, String label) async {
      await away();
      try {
        await openMenu(tester, 'reports', 'reports/$area');
      } catch (_) {
        // A dialog still closing can swallow the first tap on the menu.
        await tester.sendKeyEvent(LogicalKeyboardKey.escape);
        await away();
        await pumpFor(tester, const Duration(seconds: 1));
        await openMenu(tester, 'reports', 'reports/$area');
      }
      final Finder tile = find.widgetWithText(ListTile, label);
      // The list of reports (the 300-wide column on the left) is built
      // lazily, and keeps where it was scrolled: from its top, a step at a
      // time, until the tile is built.
      await pumpUntil(tester, find.byType(ListTile), waitingFor: 'the report list');
      ScrollableState? picker;
      for (final Element e in find
          .ancestor(of: find.byType(ListTile), matching: find.byType(Scrollable))
          .evaluate()) {
        final RenderObject? box = e.renderObject;
        if (box is RenderBox && box.hasSize && box.size.width <= 310) {
          picker = (e as StatefulElement).state as ScrollableState;
          break;
        }
      }
      if (picker != null) {
        picker.position.jumpTo(0);
        await pumpFor(tester, const Duration(milliseconds: 300));
        for (int i = 0; i < 60 && tile.evaluate().isEmpty; i++) {
          final ScrollPosition p = picker.position;
          if (p.pixels >= p.maxScrollExtent) break;
          p.jumpTo((p.pixels + 200).clamp(0, p.maxScrollExtent));
          await pumpFor(tester, const Duration(milliseconds: 250));
        }
      }
      if (tile.evaluate().isEmpty) {
        return (offered: false, error: '', grid: false, empty: false);
      }
      await Scrollable.ensureVisible(tester.element(tile.first), alignment: 0.3);
      await pumpFor(tester, const Duration(milliseconds: 400));
      await tester.tap(tile.first);
      final DateTime end = DateTime.now().add(const Duration(seconds: 45));
      bool grid = false, empty = false;
      while (DateTime.now().isBefore(end)) {
        await tester.pump(const Duration(milliseconds: 250));
        grid = find.byKey(ValueKey<String>('report-grid-$id')).evaluate().isNotEmpty ||
            find.byKey(ValueKey<String>('report-grid-$id-boxes')).evaluate().isNotEmpty;
        empty = find.text('Nothing to report').evaluate().isNotEmpty;
        if (grid || empty || buttonState(tester, 'Dismiss') != 'absent') break;
      }
      await pumpFor(tester, const Duration(seconds: 1));
      String error = '';
      if (buttonState(tester, 'Dismiss') != 'absent') {
        error = textOnScreen(tester)
            .where((String t) => t.length > 15 && t.length < 300)
            .where((String t) => RegExp(r'not|could|fail|error|denied|permission',
                    caseSensitive: false)
                .hasMatch(t))
            .take(2)
            .join(' | ');
        if (error.isEmpty) error = 'a banner with Dismiss';
      }
      return (offered: true, error: error, grid: grid, empty: empty);
    }

    // =======================================================================
    // TC-LOT-001: a firm still on Average (IT_PART=average)
    // =======================================================================
    if (average) {
      Json? product;
      await log.step('TC-LOT-001 prep: 10 in MAIN on the Average firm (HTTP)',
          () async {
        final Json settings = await lotSettings();
        if (settings['costing_method'] != 'AVERAGE') {
          throw StateError('the firm is ${settings['costing_method']}, not on '
              'Average; the case needs one still on Average');
        }
        for (final Json u
            in await list('/api/v1/uom-framework/uoms?page_size=100')) {
          if (u['code'] == 'PIECE') piece = '${u['id']}';
        }
        final List<Json> wh = await list('/api/v1/warehouses?page_size=5');
        final List<dynamic> found = (await admin.get(
            '/api/v1/products?search=0LAVG')) as List<dynamic>;
        if (found.isNotEmpty) {
          product = found.first as Json;
          log.saw = 'product ${product!['code']} already there';
          return;
        }
        product = await makeProduct('0LAVG$stamp', 'LT average item $stamp', false);
        final Json opening = (await admin.write('POST',
            '$_inv/opening-stock', <String, dynamic>{
              'warehouse_id': wh.first['id'],
              'branch_id': wh.first['branch_id'],
              'reference_number': 'LTAVG-$stamp',
              'posting_date': _today(),
              'lines': <Json>[
                <String, dynamic>{
                  'product_id': product!['id'],
                  'quantity': '10',
                  'unit_cost': '60',
                },
              ],
            })) as Json;
        await admin.write('POST', '$_inv/opening-stock/${opening['id']}/post',
            <String, dynamic>{});
        log.saw = 'made ${product!['code']} with 10 at 60';
      });

      Future<Json> serverPreview(String on) async =>
          (await admin.get('$_inv/lot-settings/switch-preview?on=$on')) as Json;

      await log.step('TC-LOT-001 step 1 the firm shows Average and the preview',
          () async {
        final int errs = appErrors.length;
        if (!await openCosting()) throw StateError('no Costing method tab');
        final String method = keyedText('stock-costing-method');
        final String day = boxesIn(tester, 'stock-costing-date');
        final Json server = await serverPreview(day);
        final List<String> shown = <String>[
          for (final String k in const <String>['items', 'lots', 'quantity', 'value'])
            '$k=${keyedText('stock-costing-$k')}',
        ];
        final List<String> refusals = <String>[
          for (final String k in keysStarting('stock-costing-refusal-')) keyedText(k),
        ];
        log.saw = 'method "$method"; day box "$day"; preview $shown; refusals '
            '$refusals; switch ${switchButton()}; server items=${server['items']} '
            'lots=${server['lots']} qty=${server['quantity']} '
            'value=${server['stock_value']} refusals=${server['refusals']}';
        if (method != 'Average cost') throw StateError('does not read Average cost');
        if (keyedText('stock-costing-items') == '(absent)') {
          throw StateError('no preview shown for the suggested day');
        }
        if ('${server['items']}' != keyedText('stock-costing-items')) {
          throw StateError('items differ from the server');
        }
        if ((refusals.isEmpty) != (switchButton() == 'enabled')) {
          throw StateError('the switch button does not follow the refusals');
        }
        if (appErrors.length > errs) throw StateError(errorsSince(errs));
      });

      Future<void> previewFor(String label, String day) async {
        await log.step(label, () async {
          final int errs = appErrors.length;
          await typeKeyed('stock-costing-date', day);
          await tapKey(tester, 'stock-costing-show');
          await pumpFor(tester, const Duration(seconds: 3));
          final List<String> refusals = <String>[
            for (final String k in keysStarting('stock-costing-refusal-'))
              keyedText(k),
          ];
          final Json server = await serverPreview(day);
          final Json after = await lotSettings();
          final String heading = textOnScreen(tester)
              .where((String t) =>
                  t.startsWith('Switching on') || t.startsWith('This was for'))
              .join(' | ');
          log.saw = 'for $day (box "${boxesIn(tester, 'stock-costing-date')}") '
              'heading "$heading"; refusals on screen $refusals; switch '
              '${switchButton()}; server refusals ${server['refusals']}; firm '
              'still ${after['costing_method']}';
          if (refusals.isEmpty) throw StateError('nothing refused on screen');
          final List<String> wanted = <String>[
            for (final dynamic r in (server['refusals'] as List<dynamic>?) ?? <dynamic>[])
              '$r',
          ];
          if (refusals.join('|') != wanted.join('|')) {
            throw StateError('the screen shows $refusals, the server says $wanted [${log.saw}; banner ${textOnScreen(tester).where((String t) => t.contains("YYYY") || t.contains("could") || t.contains("Type")).join(" | ")}]');
          }
          if (switchButton() == 'enabled') throw StateError('switch offered');
          if (after['costing_method'] != 'AVERAGE') throw StateError('switched');
          if (appErrors.length > errs) throw StateError(errorsSince(errs));
        });
      }

      await previewFor('TC-LOT-001 step 2 a day after today is refused',
          _day(now.add(const Duration(days: 1))));
      await previewFor('TC-LOT-001 step 2 a day before the latest movement is '
          'refused', _day(now.subtract(const Duration(days: 1))));
      await away();
      log.skip('TC-LOT-001 step 3', 'no product below zero on the new firm');
      log.skip('TC-LOT-001 step 4', 'HTTP, driven by docs/qa/checks/lots');
      log.info('errors', 'app errors and overflows this run: ${appErrors.length}');
      log.finish();
      return;
    }

    // =======================================================================
    // A firm by lot: lotadmin, then lotviewer
    // =======================================================================
    await log.step('LOT-PREP masters over HTTP', () async {
      await masters();
      log.saw = 'supplier LT supplier $tag, customer LT buyer $tag, '
          '${productB['code']} (batch, expiry), ${productP['code']} (plain), '
          'PO ${docNumber(poB!)} for 10 at 40 and 5 at 42';
    });

    if (_runs('settings')) {
      await log.step('TC-LOT-002 step 3 Costing method reads By lot, its day '
          'and no way back', () async {
        final int errs = appErrors.length;
        final Json server = await lotSettings();
        if (!await openCosting()) {
          log.saw = 'Costing method not offered; server ${server['costing_method']}';
          if (isAdmin) throw StateError('no Costing method tab for the admin');
          return;
        }
        final String method = keyedText('stock-costing-method');
        final SwitchListTile? sw = billingSwitch();
        final bool dateBox =
            find.byKey(const ValueKey<String>('stock-costing-date')).evaluate().isNotEmpty;
        log.saw = 'method "$method"; billing switch ${sw == null ? 'absent' : 'value=${sw.value}, enabled=${sw.onChanged != null}'}'
            '; switch button ${switchButton()}; date box $dateBox; server '
            '${server['costing_method']} since ${server['switched_on']}';
        final List<String> faults = <String>[
          if (method != 'By lot, since ${server['switched_on']}')
            'method reads "$method"',
          if (sw == null) 'no billing switch',
          if (sw != null && sw.value != server['allow_billing_without_stock'])
            'billing switch does not match the server',
          if (sw != null && (sw.onChanged != null) != isAdmin)
            'billing switch enabled=${sw.onChanged != null} for $itHandle',
          if (switchButton() != 'absent') 'a switch button is offered',
          if (dateBox) 'a day box is offered',
        ];
        if (faults.isNotEmpty) throw StateError(faults.join('; '));
        if (appErrors.length > errs) throw StateError(errorsSince(errs));
      });

      if (isAdmin) {
        final bool wasOn =
            (await lotSettings())['allow_billing_without_stock'] == true;
        try {
          await log.step('TC-LOT-002 step 3 the billing switch turns and is '
              'kept', () async {
            final int errs = appErrors.length;
            final Finder sw =
                find.byKey(const ValueKey<String>('stock-costing-allow-billing'));
            if (sw.evaluate().isEmpty) throw StateError('no switch');
            final String said1 = await pressAndRead(tester, () async {
              await tester.tap(sw);
              await pumpFor(tester, const Duration(milliseconds: 300));
            }, seconds: 3);
            final bool mid =
                (await lotSettings())['allow_billing_without_stock'] == true;
            final String said2 = await pressAndRead(tester, () async {
              await tester.tap(sw);
              await pumpFor(tester, const Duration(milliseconds: 300));
            }, seconds: 3);
            final bool end =
                (await lotSettings())['allow_billing_without_stock'] == true;
            log.saw = 'server $wasOn -> $mid ("$said1") -> $end ("$said2")';
            if (mid == wasOn) throw StateError('the first turn did not reach the server');
            if (end != wasOn) throw StateError('the second turn did not reach the server');
            if (appErrors.length > errs) throw StateError(errorsSince(errs));
          });
        } finally {
          if (((await lotSettings())['allow_billing_without_stock'] == true) != wasOn) {
            await admin.write('PUT', '$_inv/lot-settings',
                <String, dynamic>{'allow_billing_without_stock': wasOn});
            log.info('TC-LOT-002', 'billing switch put back over HTTP');
          }
        }
      }
      await away();
    }

    // -- TC-LOT-003: the receipt ---------------------------------------------
    bool received = false;
    if (isAdmin && _runs('receipt')) {
      await log.step('TC-LOT-003 step 1 a receipt of two batch lines, '
          'completed on the screen', () async {
        final int errs = appErrors.length;
        final String po = '${poB!['id']}';
        final int before = await admin.total('/api/v1/goods-receipts');
        await away();
        await openMenu(tester, 'buy', 'goodsReceipts/receipts');
        await tapNew(tester);
        await chooseIn(tester, 'goods-receipt-order', docNumber(poB!));
        await pumpFor(tester, const Duration(seconds: 2));
        const List<(String, String, String)> lines = <(String, String, String)>[
          ('10', 'LOTA', '60'),
          ('5', 'LOTB', '60'),
        ];
        for (int i = 0; i < lines.length; i++) {
          await typeKeyed('goods-receipt-accepted-$po-$i', lines[i].$1);
          await typeKeyed('goods-receipt-batch-$po-$i', lines[i].$2);
          await tester.tap(find.byKey(ValueKey<String>('goods-receipt-line-$i')));
          await pumpFor(tester, const Duration(milliseconds: 600));
          await pickDate('goods-receipt-expiry-$po-$i', expiry);
          final Finder mrp = find.byKey(ValueKey<String>('goods-receipt-mrp-$po-$i'));
          if (mrp.evaluate().isNotEmpty) {
            await typeKeyed('goods-receipt-mrp-$po-$i', lines[i].$3);
          }
        }
        final String said = await pressAndRead(
            tester, () => tapKey(tester, 'goods-receipt-save-complete'),
            seconds: 8, confirmWith: null);
        if (find.byType(Dialog).evaluate().isNotEmpty) await confirmIfAsked(tester);
        await pumpFor(tester, const Duration(seconds: 2));
        final int after = await admin.total('/api/v1/goods-receipts');
        Json? gr;
        for (final Json r in await list('/api/v1/goods-receipts?page_size=100')) {
          if (r['purchase_order_id'] == poB!['id']) gr = r;
        }
        final List<Json> lots = await lotsOf(productB, admin);
        final List<Json> batches = await batchesOf(productB);
        final bool open = find
            .byKey(const ValueKey<String>('goods-receipt-save-complete'))
            .evaluate()
            .isNotEmpty;
        log.saw = 'said "$said"; editor open=$open; receipts $before -> $after; '
            '${gr == null ? 'none for the PO' : '${docNumber(gr)} ${gr['status']}'}'
            '; lots ${[for (final Json l in lots) '${l['batch_number']} ${_n(l['quantity'])}@${_n(l['rate'])} exp ${l['expiry_date']} mrp ${l['mrp']} rec ${l['received_on']}']}';
        if (gr == null) throw StateError('no receipt saved');
        if ('${gr['status']}'.toUpperCase() != 'COMPLETED') {
          throw StateError('receipt is ${gr['status']}, not completed');
        }
        final Map<String, Json> byBatch = <String, Json>{
          for (final Json l in lots) '${l['batch_number']}': l,
        };
        final List<String> faults = <String>[
          if (lots.length != 2) '${lots.length} lots, not 2',
          if (_n(byBatch['LOTA']?['quantity']) != 10 ||
              (_n(byBatch['LOTA']?['rate']) - 40).abs() > 0.005)
            'LOTA is not 10 at 40',
          if (_n(byBatch['LOTB']?['quantity']) != 5 ||
              (_n(byBatch['LOTB']?['rate']) - 42).abs() > 0.005)
            'LOTB is not 5 at 42',
          for (final Json b in batches)
            if (b['expiry_date'] != expiry)
              '${b['batch_number']} expiry ${b['expiry_date']}, typed $expiry',
        ];
        if (faults.isNotEmpty) throw StateError(faults.join('; '));
        received = true;
        if (appErrors.length > errs) throw StateError(errorsSince(errs));
      });
      await away();
    }
    if (!received) {
      // The viewer cannot receive; the admin's lots come over HTTP when the
      // screen did not make them.
      try {
        await receiveOverHttp(poB!, <Json>[
          <String, dynamic>{'batch_number': 'LOTA', 'expiry_date': expiry, 'mrp': '60'},
          <String, dynamic>{'batch_number': 'LOTB', 'expiry_date': expiry, 'mrp': '60'},
        ]);
        log.info('LOT-PREP', 'LOTA 10 at 40 and LOTB 5 at 42 received over HTTP');
      } catch (error) {
        log.info('LOT-PREP', 'could not receive B over HTTP: $error');
      }
    }
    String more = '';
    try {
      more = await moreStock();
      log.info('LOT-PREP', more);
    } catch (error) {
      log.info('LOT-PREP', 'could not add the rest of the stock: $error');
    }

    if (_runs('receipt') || _runs('reports')) {
      bool lotReport = false;
      await log.step('TC-LOT-003 step 3 Stock valuation by lot lists each lot '
          'at its own cost', () async {
        final int errs = appErrors.length;
        final r = await openReport(
            'financial', 'stock-valuation-lots', 'Stock valuation by lot');
        if (!r.offered) throw StateError('report not offered');
        lotReport = r.error.isEmpty;
        final List<Json> server = await lotsOf(productB, me);
        final List<List<String>> rows = rowsNamed(nameB);
        log.saw = 'error "${r.error}"; grid=${r.grid}; rows for B on screen '
            '$rows; server ${[for (final Json l in server) '${l['batch_number']} ${_n(l['quantity'])} rate ${l['rate']} value ${l['value']}']}';
        if (r.error.isNotEmpty) throw StateError(r.error);
        if (rows.length != server.length) {
          throw StateError('${rows.length} rows on screen, ${server.length} on the server; grid=${r.grid}; screen ${textOnScreen(tester).skip(20).take(60).join(' | ')}');
        }
        for (final Json l in server) {
          final double value = _n(l['value']);
          final bool shown = rows.any((List<String> row) =>
              row.contains('${l['batch_number']}') &&
              rowHasFigure(row, _n(l['quantity'])) &&
              (l['value'] == null
                  ? !rowHasFigure(row, _n(l['quantity']) * 40)
                  : rowHasFigure(row, value)));
          if (!shown) {
            throw StateError('no row matching ${l['batch_number']} '
                '${_n(l['quantity'])} value ${l['value']}');
          }
        }
        if (!isAdmin && server.any((Json l) => l['rate'] != null || l['value'] != null)) {
          throw StateError('the server sent a cost to the viewer');
        }
        if (isAdmin && server.any((Json l) => l['rate'] == null)) {
          throw StateError('the server left the cost out for the admin');
        }
        if (appErrors.length > errs) throw StateError(errorsSince(errs));
      });

      await log.step('TC-LOT-012 step 2 a day before the switch: the lot '
          'report is empty', () async {
        final int errs = appErrors.length;
        if (!lotReport) throw StateError('the lot report did not open');
        final Json settings = await lotSettings();
        final String before = _day(DateTime.parse('${settings['switched_on']}')
            .subtract(const Duration(days: 1)));
        await typeKeyed('report-to', before);
        await tester.testTextInput.receiveAction(TextInputAction.done);
        await pumpFor(tester, const Duration(seconds: 4));
        final int server = await me.total(
            '$_inv/reports/stock-valuation/lots?to_date=$before');
        final bool empty = find.text('Nothing to report').evaluate().isNotEmpty;
        log.saw = 'as on $before: empty on screen=$empty; server rows $server';
        if (server != 0) throw StateError('the server lists $server lots');
        // The dates are the workspace's, shared by every report: put today
        // back so the reports after this one read today.
        await typeKeyed('report-to', _today());
        await tester.testTextInput.receiveAction(TextInputAction.done);
        await pumpFor(tester, const Duration(seconds: 2));
        if (!empty) throw StateError('the screen still lists rows');
        if (appErrors.length > errs) throw StateError(errorsSince(errs));
      });
      await away();
    }

    // -- TC-LOT-004 / TC-LOT-013: the batch picker ---------------------------
    Json? order;
    try {
      order = await approvedOrder();
    } catch (error) {
      log.info('LOT-PREP', 'could not raise the order: $error');
    }
    if (_runs('picker')) {
      if (order == null) {
        log.skip('TC-LOT-004', 'no approved order to deliver');
      } else {
        final List<dynamic> soLines = order['lines'] as List<dynamic>;
        String lineIdOf(Json product) {
          for (final dynamic l in soLines) {
            if ((l as Json)['product_id'] == product['id']) return '${l['id']}';
          }
          return '';
        }

        Json? draft;
        bool opened = false;
        await log.step(
            isAdmin
                ? 'TC-LOT-004 step 2 the delivery note line opens the batch '
                    'picker'
                : 'TC-LOT-013 step 1 batch picker: the viewer gets the '
                    'read-only note, and the lots with no cost', () async {
          final int errs = appErrors.length;
          await away();
          log.info('TC-LOT-004', 'opening Delivery Notes');
          await openMenu(tester, 'sell', 'deliveryNotes/delivery-notes');
          if (isAdmin) {
            await tapNew(tester);
            await chooseIn(tester, 'delivery-note-order', docNumber(order!));
          } else {
            // A viewer makes no note: the admin raises a draft over HTTP
            // and the viewer opens it.
            final Json line0 = soLines.first as Json;
            draft = (await admin.write('POST', '/api/v1/delivery-notes',
                <String, dynamic>{
                  'sales_order_id': order!['id'],
                  'delivery_date': _today(),
                  'lines': <Json>[
                    <String, dynamic>{
                      'sales_order_line_id': line0['id'],
                      'line_number': 1,
                      'current_delivery_quantity': 3,
                    },
                    <String, dynamic>{
                      'sales_order_line_id': (soLines[1] as Json)['id'],
                      'line_number': 2,
                      'current_delivery_quantity': 2,
                    },
                  ],
                })) as Json;
            log.info('TC-LOT-004', 'draft ${docNumber(draft!)} raised over HTTP');
            await refreshList(tester);
            await searchList(tester, docNumber(draft!));
            await pickRow(tester, docNumber(draft!));
            final String openState = buttonState(tester, 'Open') != 'absent'
                ? 'Open'
                : buttonState(tester, 'View') != 'absent'
                    ? 'View'
                    : '';
            if (openState.isEmpty) {
              throw StateError('no Open or View for the draft note; buttons: '
                  '${textOnScreen(tester).take(30).join(' | ')}');
            }
            log.info('TC-LOT-004', 'opening ${docNumber(draft!)} with $openState');
            await tapButton(tester, openState);
            await pumpFor(tester, const Duration(seconds: 3));
            // The picker lives in the note's editor, which needs the right
            // to make or change a note; a viewer's Open is the read-only
            // view. What the picker would show is asked of the server as
            // the viewer.
            final bool picker = find
                .byKey(const ValueKey<String>('delivery-note-batch-picker'))
                .evaluate()
                .isNotEmpty;
            final String newState = buttonState(tester, 'New') == 'absent'
                ? buttonState(tester, '+ New')
                : buttonState(tester, 'New');
            final List<dynamic> avail = (await me.get(
                '/api/v1/batch-serial/batches/availability?product_id='
                '${productB['id']}&warehouse_id=${warehouse['id']}'
                '&sales_order_line_id=${line0['id']}&quantity=3')) as List<dynamic>;
            final bool costSent =
                avail.any((dynamic a) => (a as Json)['unit_cost'] != null);
            final bool groups = avail.any((dynamic a) => (a as Json)['pick_group'] != null);
            log.saw = 'Open shows the read-only view (picker on screen=$picker, '
                'dialog "${noticeText(tester).split(' | ').take(4).join(' | ')}"); '
                'New $newState; availability as the viewer: ${avail.length} lots, '
                'pick groups sent=$groups, cost sent=$costSent';
            await away();
            if (costSent) throw StateError('the server sent the viewer a cost');
            if (newState == 'enabled') throw StateError('New offered to a viewer');
            if (picker && keysStarting('batch-cost-').isNotEmpty) {
              throw StateError('cost shown to the viewer');
            }
            if (appErrors.length > errs) throw StateError(errorsSince(errs));
            return;
          }
          await pumpUntil(tester,
              find.byKey(const ValueKey<String>('delivery-note-batch-picker')),
              timeout: const Duration(seconds: 20),
              waitingFor: 'the batch picker');
          await pumpFor(tester, const Duration(seconds: 2));
          opened = true;
          if (appErrors.length > errs) throw StateError(errorsSince(errs));
        });

        if (opened) {
          await log.step('TC-LOT-004 step 2 lots that agree are one row, '
              'nearest expiry first${isAdmin ? '' : '; TC-LOT-013 no cost'}',
              () async {
            final int errs = appErrors.length;
            final String lineB = lineIdOf(productB);
            final List<Json> avail = <Json>[
              for (final dynamic r in (await me.get('/api/v1/batch-serial/batches/'
                      'availability?product_id=${productB['id']}&warehouse_id='
                      '${warehouse['id']}&sales_order_line_id=$lineB&quantity=3'))
                  as List<dynamic>)
                r as Json,
            ];
            final List<String> groups = <String>[];
            for (final Json a in avail) {
              final String g = '${a['pick_group'] ?? 'batch:${a['batch_id']}'}';
              if (!groups.contains(g)) groups.add(g);
            }
            final List<String> labels = keysStarting('batch-label-$lineB-');
            final List<String> costs = keysStarting('batch-cost-$lineB-');
            final List<String> picker = <String>[
              for (final Text t in tester.widgetList<Text>(find.descendant(
                  of: find.byKey(const ValueKey<String>('delivery-note-batch-picker')),
                  matching: find.byType(Text))))
                if ((t.data ?? '').isNotEmpty) t.data!,
            ];
            final bool costSent = avail.any((Json a) => a['unit_cost'] != null);
            log.saw = 'picker rows ${labels.length} (${[for (final String k in labels) keyedText(k)]}); '
                'cost cells ${costs.length}; texts $picker; server ${avail.length} '
                'lots in ${groups.length} group(s), cost sent=$costSent';
            final List<String> faults = <String>[
              if (labels.length != groups.length)
                '${labels.length} rows for ${groups.length} groups',
              if (groups.length < avail.length &&
                  !picker.any((String t) => t.contains('${avail.length - groups.length + 1} lots')))
                'no row says how many lots it holds',
              if (avail.length == groups.length)
                'the server did not group the agreeing LOTA lots (${avail.length} lots, '
                    '${groups.length} groups)',
              if (costSent != isAdmin) 'cost sent=$costSent to $itHandle',
              if (costs.isNotEmpty != costSent)
                'cost column shown=${costs.isNotEmpty}, sent=$costSent',
            ];
            if (faults.isNotEmpty) throw StateError(faults.join('; '));
            if (appErrors.length > errs) throw StateError(errorsSince(errs));
          });

          await log.step('TC-LOT-004 step 4 the unprinted lot shows a dash and '
              'its received date, never our reference', () async {
            final int errs = appErrors.length;
            final String lineP = lineIdOf(productP);
            await tester.tap(find.byKey(const ValueKey<String>('delivery-note-line-1')));
            await pumpFor(tester, const Duration(seconds: 3));
            final List<String> labels = keysStarting('batch-label-$lineP-');
            final List<Json> lotsP = await lotsOf(productP, admin);
            final List<String> picker = <String>[
              for (final Text t in tester.widgetList<Text>(find.descendant(
                  of: find.byKey(const ValueKey<String>('delivery-note-batch-picker')),
                  matching: find.byType(Text))))
                if ((t.data ?? '').isNotEmpty) t.data!,
            ];
            final String ref = lotsP.isEmpty ? '' : '${lotsP.first['lot_reference']}';
            log.saw = 'labels ${[for (final String k in labels) keyedText(k)]}; '
                'texts $picker; our reference $ref; cost cells '
                '${keysStarting('batch-cost-$lineP-').length}';
            final List<String> faults = <String>[
              if (labels.isEmpty) 'no lot row for P',
              for (final String k in labels)
                if (keyedText(k) != '-') 'label reads "${keyedText(k)}"',
              if (!picker.any((String t) => t.contains('received ')))
                'no received date',
              if (ref.isNotEmpty && picker.any((String t) => t.contains(ref)))
                'our reference $ref is shown',
              if (!isAdmin && keysStarting('batch-cost-$lineP-').isNotEmpty)
                'cost shown to the viewer',
            ];
            if (faults.isNotEmpty) throw StateError(faults.join('; '));
            if (appErrors.length > errs) throw StateError(errorsSince(errs));
          });
        }
        await away();
        log.skip('TC-LOT-004 step 3', 'typing over a group is the picker\'s '
            'own widget test; not clicked here');
        if (draft != null) {
          await admin.attempt('POST',
              '/api/v1/delivery-notes/${draft!['id']}/cancel',
              <String, dynamic>{'reason': 'click flow clean-up'});
        }
      }
    }

    // -- TC-LOT-012 / TC-LOT-013: the four reports ---------------------------
    if (_runs('reports')) {
      for (final (String, String, String, String) rep in const <(String, String, String, String)>[
        ('financial', 'stock-valuation-lots', 'Stock valuation by lot',
            '$_inv/reports/stock-valuation/lots'),
        ('financial', 'margin-by-lot', 'Margin by lot',
            '/api/v1/sales-invoices/reports/margin-by-lot'),
        ('operational', 'stock-ageing', 'Stock ageing',
            '$_inv/reports/stock-ageing'),
        ('financial', 'lot-shortfalls', 'Bills waiting for their cost',
            '$_inv/lot-shortfalls'),
      ]) {
        await log.step('TC-LOT-012/013 ${rep.$3} opens without error', () async {
          final int errs = appErrors.length;
          final r = await openReport(rep.$1, rep.$2, rep.$3);
          if (!r.offered) throw StateError('not offered to $itHandle');
          final String fy = boxesIn(tester, 'report-from');
          final String q = rep.$2 == 'lot-shortfalls'
              ? ''
              : '?from_date=${fy.isEmpty ? '2026-04-01' : fy}&to_date=${boxesIn(tester, "report-to").isEmpty ? _today() : boxesIn(tester, "report-to")}&page_size=100';
          final List<dynamic> server =
              (await me.get('${rep.$4}$q')) as List<dynamic>;
          final Json? first = server.isEmpty ? null : server.first as Json;
          const List<String> costKeys = <String>[
            'rate', 'value', 'cost', 'margin', 'margin_percent', 'unit_cost',
            'cost_waiting',
          ];
          final List<String> costsSent = <String>[
            if (first != null)
              for (final String k in costKeys)
                if (first.containsKey(k) && first[k] != null) k,
          ];
          final bool usedHeader = screenHas(tester, 'Cost used');
          log.saw = 'error "${r.error}"; grid=${r.grid}, empty=${r.empty}; '
              'server ${server.length} rows, cost keys sent on row 1 $costsSent'
              '${rep.$2 == 'lot-shortfalls' ? '; "Cost used" header=$usedHeader' : ''}';
          final List<String> faults = <String>[
            if (r.error.isNotEmpty) 'error: ${r.error}',
            if (!r.grid && !r.empty) 'neither rows nor an empty note; screen ${textOnScreen(tester).skip(20).take(50).join(" | ")}',
            if (server.isNotEmpty && r.empty) 'empty on screen, ${server.length} on the server',
            if (server.isEmpty && r.grid) 'rows on screen, none on the server',
            if (!isAdmin && costsSent.isNotEmpty && rep.$2 != 'stock-ageing')
              'the server sent $costsSent to the viewer',
            if (rep.$2 == 'lot-shortfalls' && server.isNotEmpty &&
                usedHeader != (first!['unit_cost'] != null))
              '"Cost used" shown=$usedHeader, sent=${first['unit_cost'] != null}',
          ];
          if (faults.isNotEmpty) throw StateError(faults.join('; '));
          if (appErrors.length > errs) throw StateError(errorsSince(errs));
        });
      }
      await away();
    }

    // -- TC-LOT-014: Trace ---------------------------------------------------
    if (_runs('trace')) {
      // Three of B leave over HTTP first, so the trail has more than an
      // arrival in it.
      if (order != null) {
        try {
          final List<dynamic> soLines = order['lines'] as List<dynamic>;
          final Json note = (await admin.write('POST', '/api/v1/delivery-notes',
              <String, dynamic>{
                'sales_order_id': order['id'],
                'delivery_date': _today(),
                'lines': <Json>[
                  <String, dynamic>{
                    'sales_order_line_id': (soLines.first as Json)['id'],
                    'line_number': 1,
                    'current_delivery_quantity': 3,
                  },
                ],
              })) as Json;
          await apiAct(admin, 'delivery-notes', '${note['id']}', 'approve');
          await apiAct(admin, 'delivery-notes', '${note['id']}', 'dispatch');
          log.info('LOT-PREP', '3 of B dispatched on ${docNumber(note)}');
        } catch (error) {
          log.info('LOT-PREP', 'could not dispatch 3 of B: $error');
        }
      }
      await log.step('TC-LOT-014 steps 1-2 Batches > a LOTA > Trace lists its '
          'arrival and movements', () async {
        final int errs = appErrors.length;
        final Map<String, Json> trails = <String, Json>{};
        for (final Json b in await batchesOf(productB)) {
          if (b['batch_number'] != 'LOTA') continue;
          trails['${b['id']}'] = (await me.get(
              '/api/v1/batch-serial/batches/${b['id']}/trail')) as Json;
        }
        await openArea(tester, 'stock', 'inventory/batches');
        // The box searches the batch number alone: LOTA, then the row whose
        // product is the run's own.
        await searchList(tester, 'LOTA');
        final Finder row = find.byWidgetPredicate(
            (Widget w) => w is Text && (w.data ?? '').contains(nameB));
        await pumpUntil(tester, row, waitingFor: 'a LOTA row of $nameB');
        // The lot that moved most (the one the dispatch took from), found by
        // the quantity its row shows.
        double busiest = -1;
        int most = -1;
        for (final Json t in trails.values) {
          final int n = (t['events'] as List<dynamic>).length;
          if (n > most) {
            most = n;
            busiest = _n((t['batch'] as Json)['quantity']);
          }
        }
        Finder pick = row.first;
        for (int i = 0; i < row.evaluate().length; i++) {
          final RenderObject? box = row.at(i).evaluate().first.renderObject;
          if (box is! RenderBox || !box.attached) continue;
          final double y = box.localToGlobal(box.size.center(Offset.zero)).dy;
          final bool match = find.byType(Text).evaluate().any((Element e) {
            final RenderObject? b = e.renderObject;
            if (b is! RenderBox || !b.attached) return false;
            final double cy = b.localToGlobal(b.size.center(Offset.zero)).dy;
            final String d = ((e.widget as Text).data ?? '').trim();
            return (cy - y).abs() < 6 &&
                RegExp(r'^[\d.,]+$').hasMatch(d) &&
                (_n(d) - busiest).abs() < 0.0005;
          });
          if (match) {
            pick = row.at(i);
            break;
          }
        }
        await tester.tap(pick);
        await pumpFor(tester, const Duration(milliseconds: 700));
        await tapButton(tester, 'Open');
        await pumpFor(tester, const Duration(seconds: 1));
        await tapKey(tester, 'batch-trace');
        await pumpUntil(tester,
            find.byKey(const ValueKey<String>('lot-trail-reference')),
            waitingFor: 'the lot trail');
        await pumpFor(tester, const Duration(seconds: 2));
        final String reference = keyedText('lot-trail-reference');
        Json? trail;
        for (final Json t in trails.values) {
          if ('${t['lot_reference']}' == reference) trail = t;
        }
        // A TableRow's key is not a widget's, so the rows are read from the
        // table's texts: each event shows its document number once.
        final List<String> table = <String>[
          for (final Text t in tester.widgetList<Text>(find.descendant(
              of: find.byKey(const ValueKey<String>('lot-trail-events')),
              matching: find.byType(Text))))
            t.data ?? '',
        ];
        final Set<String> numbers = <String>{
          for (final dynamic e in (trail?['events'] as List<dynamic>?) ?? <dynamic>[])
            '${(e as Json)['document_number']}',
        };
        final List<String> shownNumbers =
            table.where((String t) => numbers.contains(t)).toList();
        final int shownEvents = shownNumbers.length;
        final List<String> firstRow =
            shownNumbers.isEmpty ? <String>[] : <String>[shownNumbers.first];
        final bool costHead = find
            .descendant(
                of: find.byKey(const ValueKey<String>('lot-trail-events')),
                matching: find.text('Cost'))
            .evaluate()
            .isNotEmpty;
        final String unitCost = keyedText('lot-trail-unit-cost');
        final List<dynamic> events = (trail?['events'] as List<dynamic>?) ?? <dynamic>[];
        log.saw = 'reference $reference; printed batch '
            '"${keyedText('lot-trail-printed-batch')}"; received '
            '"${keyedText('lot-trail-received')}"; unit cost "$unitCost"; '
            'events on screen $shownEvents, first $firstRow, cost column '
            '$costHead; server ${trail == null ? 'no trail with that reference' : '${events.length} events, first ${(events.isEmpty ? <String, dynamic>{} : events.first as Json)['document_type']} ${(events.isEmpty ? <String, dynamic>{} : events.first as Json)['document_number']}, unit_cost ${trail['unit_cost']}'}';
        final Json? e0 = events.isEmpty ? null : events.first as Json;
        final List<String> faults = <String>[
          if (trail == null) 'the reference is not one of the LOTA lots',
          if (trail != null && shownEvents != events.length)
            '$shownEvents events on screen, ${events.length} on the server',
          if (e0 != null && e0['document_type'] != 'GOODS_RECEIPT')
            'the first event is ${e0['document_type']}',
          if (e0 != null && !firstRow.contains('${e0['document_number']}'))
            'the first row does not carry ${e0['document_number']}',
          if (keyedText('lot-trail-printed-batch') != 'LOTA') 'printed batch is not LOTA',
          if (isAdmin && unitCost == '(absent)') 'no unit cost for the admin',
          if (!isAdmin && unitCost != '(absent)') 'unit cost shown to the viewer',
          if (!isAdmin && costHead) 'cost column shown to the viewer',
          if (!isAdmin && trail?['unit_cost'] != null) 'the server sent the viewer a cost',
        ];
        if (faults.isNotEmpty) throw StateError(faults.join('; '));
        if (appErrors.length > errs) throw StateError(errorsSince(errs));
      });
      await away();
    }

    log.skip('TC-LOT-002 steps 1-2, 4-6', 'the switch itself is one way and the '
        'fixture firm is already by lot; driven over HTTP');
    log.skip('TC-LOT-003 steps 2, 4', 'the plain receipt is made over HTTP; '
        'cancel after a sale is HTTP only');
    log.skip('TC-LOT-005..011', 'dispatch, returns, write-offs, settlement '
        'and supplier bills are HTTP cases (docs/qa/checks/lots)');
    log.info('errors', 'app errors and overflows this run: ${appErrors.length}');
    log.finish();
  });
}
