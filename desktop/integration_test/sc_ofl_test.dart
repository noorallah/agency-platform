import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'cases.dart';
import 'harness.dart';
import 'sc_gt_test.dart' show leave, pickRow, pressAndRead;

/// Offers chosen on the bill line, on the screens (build row L7, steps 8 and
/// 9; book 09, TC-OFR-001 to TC-OFR-012, whose HTTP halves are
/// `docs/qa/checks/offers/tc_ofr_*.py`). Run on the `lot-firm` fixture
/// (TEST03) as lotadmin, then as lotviewer.
///
/// Every run makes its own scene over HTTP before the app starts, the
/// worked example of the offers note: one item at 100.00 (GST 12%), a
/// customer on a standing rate of 2% with a price list CITY at 4% of his
/// own, TEA-5 (5% off a line of 5 or more) and TEA-11 (buy 11 get 1 free,
/// part share allowed), 50 pieces in MAIN, and a draft order and a draft
/// quotation of 11 choosing CITY + TEA-11. Codes carry the minute and the
/// user (`1432A`).
///
/// As the admin: the new order's side panel at 9 and at 11, a tick on CITY,
/// F6 / arrows / Space / Enter, the save and its rows; a choice refused when
/// the quantity drops, a typed discount locking the block; a part share
/// saved; the same choice on a quotation and a counter bill; the third
/// setting of Sales stages (set, priced, put back over HTTP); the offer
/// form's "Allow a part share"; the saved order and quotation reopened. As
/// the viewer: the saved order and quotation, the setting and the offer form
/// read only. Every value on screen is set beside what the server returned
/// (a preview of the same lines, or the saved document); app errors and
/// overflows are counted.

/// IT_PART=order, refused, share, quote, counter, settings, promo, saved
/// (comma separated) runs those parts.
const String _part = String.fromEnvironment('IT_PART');
bool _runs(String part) => _part.isEmpty || _part.split(',').contains(part);

const String _workflow = '/api/v1/sales-orders/workflow-settings';

double _n(dynamic v) => double.tryParse('${v ?? ''}'.replaceAll(',', '')) ?? 0;

/// The first number in [text] ("₹1,045.00" -> 1045), or null.
double? _first(String text) {
  final Match? m = RegExp(r'-?[\d,]*\d(\.\d+)?').firstMatch(text);
  return m == null ? null : double.tryParse(m.group(0)!.replaceAll(',', ''));
}

bool _same(double? a, double b) => a != null && (a - b).abs() < 0.005;

/// A quantity without trailing zeros, as the screen words it.
String _plain(dynamic v) {
  final double d = _n(v);
  if (d == d.roundToDouble()) return d.toInt().toString();
  String t = d.toStringAsFixed(4);
  while (t.endsWith('0')) {
    t = t.substring(0, t.length - 1);
  }
  return t;
}

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('OFL: offers on the bill line ($itHandle)',
      (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1600, 1000);
    tester.view.devicePixelRatio = 1;
    final bool isAdmin = itHandle == 'lotadmin';
    final Server admin = await Server.connectAs(
        '$itSuffix.lotadmin@fixtures.local', fixturePassword);
    final Server me = await Server.connect();
    final FlowLog log = FlowLog('ofl-$itHandle');

    final DateTime now = DateTime.now();
    final String stamp = '${now.hour.toString().padLeft(2, '0')}'
        '${now.minute.toString().padLeft(2, '0')}';
    final String tag = '$stamp${isAdmin ? 'A' : 'V'}';
    // The firm's business day (India), as the server judges it.
    final String today = DateTime.now()
        .toUtc()
        .add(const Duration(hours: 5, minutes: 30))
        .toIso8601String()
        .substring(0, 10);
    final String validUntil = DateTime.now()
        .toUtc()
        .add(const Duration(days: 15, hours: 5, minutes: 30))
        .toIso8601String()
        .substring(0, 10);

    Future<List<Json>> list(String path) async => <Json>[
          for (final dynamic row in (await admin.get(path)) as List<dynamic>)
            row as Json,
        ];

    // -- The scene, made over HTTP before the app starts ---------------------
    late Json branch, warehouse, product, customer, city, tea5, tea11;
    late Json savedOrder, savedQuote;
    late String piece;
    final String nameP = 'OL tea $tag';
    final String nameC = 'OL buyer $tag';

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

    Future<Json> offer(String name, Json action, int priority,
        {String? minimum, bool partShare = false}) async {
      final Json made = (await admin.write('POST', '/api/v1/promotions',
          <String, dynamic>{
            'code': '$name-$tag',
            'name': '$name $tag',
            'priority': priority,
            'status': 'ACTIVE',
            'effective_from': '2020-01-01',
            'conditions': <Json>[
              <String, dynamic>{
                'field_key': 'product_id',
                'operator': 'EQUALS',
                'value_text': product['id'],
              },
              if (minimum != null)
                <String, dynamic>{
                  'field_key': 'line_quantity',
                  'operator': 'GREATER_OR_EQUAL',
                  'value_number': minimum,
                  'sequence': 2,
                },
            ],
            'actions': <Json>[action],
            if (partShare) 'allow_part_share': true,
          })) as Json;
      return made;
    }

    String key5() => '${tea5['version_group_id']}';
    String key11() => '${tea11['version_group_id']}';
    String keyCity() => '${city['id']}';

    Json line(String qty, [Json extra = const <String, dynamic>{}]) =>
        <String, dynamic>{
          'line_number': 1,
          'product_id': product['id'],
          'quantity': qty,
          ...extra,
        };

    Json orderBody(List<Json> lines) => <String, dynamic>{
          'customer_id': customer['id'],
          'order_date': today,
          'branch_id': branch['id'],
          'warehouse_id': warehouse['id'],
          'lines': lines,
        };

    Json quoteBody(List<Json> lines) => <String, dynamic>{
          'customer_id': customer['id'],
          'quotation_date': today,
          'valid_until': validUntil,
          'branch_id': branch['id'],
          'warehouse_id': warehouse['id'],
          'lines': lines,
        };

    Json billBody(List<Json> lines) => <String, dynamic>{
          'customer_id': customer['id'],
          'branch_id': branch['id'],
          'invoice_date': today,
          'lines': <Json>[
            for (final Json l in lines)
              <String, dynamic>{
                for (final MapEntry<String, dynamic> e in l.entries)
                  if (e.key != 'quantity') e.key: e.value,
                'current_invoice_quantity': l['quantity'],
              },
          ],
        };

    Json cityAndTea11() => <String, dynamic>{
          'offer_choice': <String, dynamic>{
            'discount_from': keyCity(),
            'offers': <String>[key11()],
          },
        };

    final bool ready = await log.step('OFL-PREP the scene over HTTP', () async {
      for (final Json b in await list('/api/v1/branches?page_size=100')) {
        if (b['code'] == 'HO') branch = b;
      }
      for (final Json w in await list('/api/v1/warehouses?page_size=100')) {
        if (w['code'] == 'MAIN') warehouse = w;
      }
      for (final Json u in await list('/api/v1/uom-framework/uoms?page_size=100')) {
        if (u['code'] == 'PIECE') piece = '${u['id']}';
      }
      product = (await admin.write('POST', '/api/v1/products', <String, dynamic>{
        'code': '0O$tag',
        'name': nameP,
        'brand_id': await brandId(),
        'product_type': 'STOCK_ITEM',
        'tax_profile_group_code': 'GST_12_LOCAL',
        'selling_price': '100',
        'purchase_price': '60',
        'base_uom_id': piece,
        'inventory_uom_id': piece,
        'sales_uom_id': piece,
        'purchase_uom_id': piece,
      })) as Json;
      customer = (await admin.write('POST', '/api/v1/customers', <String, dynamic>{
        'code': 'OC$tag',
        'name': nameC,
        'customer_type': 'BUSINESS',
        'currency_code': 'INR',
        'default_discount_percent': '2',
      })) as Json;
      city = (await admin.write('POST', '/api/v1/price-lists', <String, dynamic>{
        'code': 'CITY$tag',
        'name': 'City $tag',
        'customer_id': customer['id'],
        'effective_from': '2000-01-01',
        'items': <Json>[
          <String, dynamic>{
            'product_id': product['id'],
            'min_quantity': '0',
            'discount_percent': '4',
          },
        ],
      })) as Json;
      tea5 = await offer('TEA5', <String, dynamic>{
        'action_type': 'LINE_DISCOUNT_PERCENT',
        'percent': '5',
      }, 10, minimum: '5');
      tea11 = await offer('TEA11', <String, dynamic>{
        'action_type': 'FREE_QUANTITY',
        'buy_quantity': '11',
        'free_quantity': '1',
      }, 20, partShare: true);
      final Json stock = (await admin.write('POST',
          '/api/v1/inventory/opening-stock', <String, dynamic>{
        'branch_id': branch['id'],
        'warehouse_id': warehouse['id'],
        'reference_number': 'OS-OL$tag',
        'posting_date': today,
        'lines': <Json>[
          <String, dynamic>{
            'product_id': product['id'],
            'quantity': '50',
            'unit_cost': '60',
          },
        ],
      })) as Json;
      await admin.write('POST',
          '/api/v1/inventory/opening-stock/${stock['id']}/post', <String, dynamic>{});
      final Json so = (await admin.write('POST', '/api/v1/sales-orders',
          orderBody(<Json>[line('11', cityAndTea11())]))) as Json;
      savedOrder = await admin.one('sales-orders', '${so['id']}');
      final Json qt = (await admin.write('POST', '/api/v1/quotations',
          quoteBody(<Json>[line('11', cityAndTea11())]))) as Json;
      savedQuote = await admin.one('quotations', '${qt['id']}');
      log.saw = 'item ${product['code']} at 100 (GST 12), customer $nameC '
          '(2%), CITY ${city['code']} 4%, ${tea5['code']}, ${tea11['code']} '
          '(part share ${tea11['allow_part_share']}), 50 in MAIN; draft order '
          '${docNumber(savedOrder)}, draft quotation ${docNumber(savedQuote)}';
    });

    await startAndSignIn(tester);
    collectAppErrors();
    final void Function(FlutterErrorDetails)? collect = FlutterError.onError;
    FlutterError.onError = (FlutterErrorDetails details) {
      collect?.call(details);
      final String all = details.toString();
      if (all.contains('overflowed')) {
        final String where = all
            .split('\n')
            .where((String l) =>
                l.contains('.dart:') ||
                l.contains('constraints') ||
                l.contains('size:'))
            .take(6)
            .join(' | ');
        // ignore: avoid_print
        print('FLOW: INFO [ofl-$itHandle] overflow at :: $where');
      }
    };
    if (!ready) {
      log.finish();
      return;
    }

    String errorsSince(int from) => appErrors.skip(from).take(3).join(' || ');
    Future<void> away() => leave(tester);

    // -- Reading the screen --------------------------------------------------
    List<String> keysStarting(String prefix) => <String>{
          for (final Element e in find.byWidgetPredicate((Widget w) {
            final Key? k = w.key;
            return k is ValueKey<String> && k.value.startsWith(prefix);
          }).evaluate())
            (e.widget.key! as ValueKey<String>).value,
        }.toList();

    List<String> textsUnder(String key) {
      final Finder f = find.byKey(ValueKey<String>(key));
      if (f.evaluate().isEmpty) return <String>[];
      return <String>[
        for (final Text t in tester.widgetList<Text>(
            find.descendant(of: f.first, matching: find.byType(Text))))
          if ((t.data ?? '').trim().isNotEmpty) t.data!.trim(),
        if (tester.widget(f.first) is Text)
          (tester.widget(f.first) as Text).data ?? '',
      ];
    }

    List<String> boxList(String key) => <String>[
          for (final EditableText e in tester.widgetList<EditableText>(find
              .descendant(
                  of: find.byKey(ValueKey<String>(key)),
                  matching: find.byType(EditableText))))
            e.controller.text,
        ];

    /// One block row as shown: its texts, and its tick (null: no tick).
    ({List<String> texts, bool? ticked, bool enabled}) rowOf(
        String prefix, String key) {
      final String rowKey = '$prefix-$key';
      final Finder tick = find.byKey(ValueKey<String>('$rowKey-tick'));
      final Checkbox? box =
          tick.evaluate().isEmpty ? null : tester.widget<Checkbox>(tick.first);
      return (
        texts: textsUnder(rowKey),
        ticked: box?.value,
        enabled: box?.onChanged != null,
      );
    }

    /// The candidate in [cands] with this offer code or source.
    Json? cand(List<dynamic> cands, String codeOrSource) {
      for (final dynamic c in cands) {
        if ((c as Json)['code'] == codeOrSource || c['source'] == codeOrSource) {
          return c;
        }
      }
      return null;
    }

    /// How the block should word a candidate's status and gives.
    ({String status, String gives}) wordsOf(Json c, bool ticked) {
      final bool available = c['available'] != false;
      final String hint = c['needs_more'] == null || c['then_gives'] == null
          ? ''
          : '${_plain(c['needs_more'])} more to get ${c['then_gives']}';
      final String status = !available && hint.isNotEmpty
          ? hint
          : ticked
              ? 'applied'
              : '${c['reason'] ?? ''}';
      final Json gives = (c['gives'] as Json?) ?? <String, dynamic>{};
      final bool discounts = gives['percent'] != null || gives['amount'] != null;
      // Nothing earned on the line gives no figure (D-UI-116).
      final String g = !available || _n(c['worth']) <= 0
          ? ''
          : discounts
          ? '${c['worth']}'
          : gives['free_quantity'] != null
              ? '${_plain(gives['free_quantity'])} free'
              : '';
      return (status: status, gives: g);
    }

    /// Set each server candidate of line 1 beside its row on screen.
    List<String> compareBlock(String prefix, List<dynamic> cands,
        {Set<String>? tickedKeys}) {
      final List<String> faults = <String>[];
      final List<String> shownKeys = keysStarting('$prefix-')
          .where((String k) =>
              !k.endsWith('-tick') &&
              !k.endsWith('-part-share') &&
              !k.endsWith('-block') &&
              !k.endsWith('-refused') &&
              !k.endsWith('-note') &&
              !k.contains('-saved-'))
          .toList();
      if (shownKeys.length != cands.length) {
        faults.add('${shownKeys.length} rows on screen, server '
            '${cands.length}');
      }
      for (final dynamic raw in cands) {
        final Json c = raw as Json;
        final String name = '${c['code']}'.isEmpty ? '${c['source']}' : '${c['code']}';
        final ({List<String> texts, bool? ticked, bool enabled}) r =
            rowOf(prefix, '${c['key']}');
        if (r.texts.isEmpty) {
          faults.add('no row for $name');
          continue;
        }
        final bool available = c['available'] != false;
        final bool wantTick =
            tickedKeys?.contains('${c['key']}') ?? c['applied'] == true;
        if (available && r.ticked != wantTick) {
          faults.add('$name ticked ${r.ticked}, server applied ${c['applied']}');
        }
        if (!available && r.ticked != null) faults.add('$name has a tick');
        final ({String status, String gives}) w = wordsOf(c, wantTick);
        final String all = r.texts.join(' | ');
        if (w.status.isNotEmpty && !r.texts.contains(w.status)) {
          faults.add('$name says "$all", not "${w.status}"');
        }
        if (w.gives.isEmpty &&
            r.texts.any((String t) =>
                RegExp(r'^[\d.]+ free$').hasMatch(t) ||
                RegExp(r'^[₹]?[\d,]+\.\d\d$').hasMatch(t))) {
          faults.add('$name gives a figure for nothing: "$all"');
        }
        if (w.gives.isNotEmpty) {
          final bool money = !w.gives.contains('free');
          final bool shown = money
              ? r.texts.any((String t) =>
                  _same(_first(t), _n(w.gives)) && t.contains('.'))
              : r.texts.contains(w.gives);
          if (!shown) faults.add('$name gives not ${w.gives}: "$all"');
        }
      }
      return faults;
    }

    /// The hint under the quantity: the first candidate's that has one.
    String hintOf(List<dynamic> cands) {
      for (final dynamic c in cands) {
        if ((c as Json)['needs_more'] != null && c['then_gives'] != null) {
          return '${_plain(c['needs_more'])} more: ${c['then_gives']}';
        }
      }
      return '';
    }

    String blockSeen(String prefix, List<dynamic> cands) => <String>[
          for (final dynamic c in cands)
            '${(c as Json)['code'] == '' ? c['source'] : c['code']}: '
                '${rowOf(prefix, '${c['key']}').texts.join(' / ')} '
                '[tick ${rowOf(prefix, '${c['key']}').ticked}]',
        ].join('; ');

    String serverCands(List<dynamic> cands) => <String>[
          for (final dynamic c in cands)
            '${(c as Json)['code'] == '' ? c['source'] : c['code']} '
                'applied ${c['applied']} worth ${c['worth']} '
                '${c['available'] == false ? 'unavailable ' : ''}'
                '${c['reason'] ?? ''}'
                '${c['needs_more'] == null ? '' : ' needs ${c['needs_more']} -> ${c['then_gives']}'}',
        ].join('; ');

    Json line1(Json doc) {
      for (final dynamic l in doc['lines'] as List<dynamic>) {
        if (((l as Json)['line_number'] as num?)?.toInt() == 1) return l;
      }
      return (doc['lines'] as List<dynamic>).first as Json;
    }

    /// A previewed line: the document's figures and the line's offers.
    Json figures(Json preview) => <String, dynamic>{
          for (final dynamic doc in preview.values)
            if (doc is Json && doc['lines'] is List) ...line1(doc),
          ...line1(preview),
        };

    List<dynamic> candsOf(Json preview) =>
        (line1(preview)['candidates'] as List<dynamic>?) ?? <dynamic>[];

    /// A line's offers rows, short: "CITY APPLIED chosen 44 free 0".
    List<String> rowsOf(Json l) => <String>[
          for (final dynamic r in (l['offers'] as List<dynamic>?) ?? <dynamic>[])
            '${(r as Json)['source'] == 'promotion' ? '${r['code']}'.split('-').first : r['source']} '
                '${r['state']}${r['chosen'] == true ? ' chosen' : ''} '
                '${_n(r['discount_amount'])}'
                '${_n(r['free_quantity']) > 0 ? ' free ${_plain(r['free_quantity'])}' : ''}'
                '${r['part_share'] == true ? ' part' : ''}',
        ];

    Future<Json> preview(String path, Json body) async =>
        (await admin.write('POST', path, body)) as Json;

    Future<void> settle() => pumpFor(tester, const Duration(seconds: 3));

    /// Pick [name] from the picker [key], filtered to the run's own entry:
    /// the firm's lists are long and a picker shows only its first rows.
    Future<void> pick(String key, String filter, String name) async {
      await tapKey(tester, key);
      final Finder box = find.descendant(
          of: find.byKey(ValueKey<String>(key)),
          matching: find.byType(EditableText));
      if (box.evaluate().isNotEmpty) {
        await tester.enterText(box.first, filter);
        await pumpFor(tester, const Duration(seconds: 1));
      }
      final Finder entry = find.textContaining(name);
      await pumpUntil(tester, entry, waitingFor: 'entry $name');
      await tester.tap(entry.last, warnIfMissed: false);
      await pumpFor(tester, const Duration(seconds: 1));
    }

    /// Open a new document editor and fill the customer and the item.
    Future<void> newDocument(String menu, String prefix,
        {String area = 'sell'}) async {
      await away();
      try {
        await openMenu(tester, area, menu);
      } on TestFailure {
        await away();
        await pumpFor(tester, const Duration(seconds: 1));
        await openMenu(tester, area, menu);
      }
      await tapNew(tester);
      await pumpUntil(tester, find.byKey(ValueKey<String>('$prefix-save')),
          waitingFor: '$prefix editor');
      await pick('$prefix-customer', 'OC$tag', nameC);
      await pick('$prefix-line-product-0', '0O$tag', nameP);
      await settle();
    }

    /// The quantity box of [row]: the first box after the product's.
    Future<void> typeQty(String row, String qty) async {
      await typeIn(tester, row, 1, qty);
      await pumpFor(tester, const Duration(seconds: 3));
    }

    Future<void> tick(String prefix, String key) async {
      final Finder f = find.byKey(ValueKey<String>('$prefix-$key-tick'));
      await pumpUntil(tester, f, waitingFor: 'tick $prefix-$key');
      await tester.ensureVisible(f.first);
      await tester.tap(f.first);
      await pumpFor(tester, const Duration(seconds: 3));
    }

    Future<Set<String>> idsFor(String collection) async => <String>{
          for (final Json r in await list('/api/v1/$collection?page_size=100'))
            '${r['id']}',
        };

    Future<Json?> newFor(String collection, Set<String> before) async {
      for (final Json r in await list('/api/v1/$collection?page_size=100')) {
        if (!before.contains('${r['id']}') && r['customer_id'] == customer['id']) {
          return admin.one(collection, '${r['id']}');
        }
      }
      return null;
    }

    /// The faults of a saved line holding CITY + TEA-11 chosen, TEA-5 passed
    /// over: TC-OFR-003 (2), the worked example.
    List<String> chosenFaults(Json? doc, String qtyField) {
      if (doc == null) return <String>['nothing saved'];
      final Json l = line1(doc);
      final List<String> rows = rowsOf(l);
      return <String>[
        if (!_same(_n(l['discount_amount']), 44)) 'discount ${l['discount_amount']}',
        if (!_same(_n(l['free_quantity']), 1)) 'free ${l['free_quantity']}',
        if (!_same(_n(l[qtyField]), 11)) '$qtyField ${l[qtyField]}',
        if (!rows.contains('price_list APPLIED chosen 44.0')) 'no CITY chosen 44',
        if (!rows.any((String r) => r.startsWith('TEA11 APPLIED chosen') && r.contains('free 1')))
          'no TEA11 chosen 1 free',
        if (!rows.any((String r) => r.startsWith('TEA5 REFUSED'))) 'TEA5 not passed over',
      ];
    }

    // =======================================================================
    // TC-OFR-001 / 002 / 003: the new order's side panel, a tick, the keys
    // =======================================================================
    if (isAdmin && _runs('order')) {
      const String p = 'sales-order-offer';
      bool opened = false;
      await log.step('TC-OFR-002 (1) a line of 9: the block as the preview, '
          'the hint under the quantity', () async {
        final int errs = appErrors.length;
        await newDocument('salesOrders', 'sales-order');
        await typeQty('sales-order-line-0', '9');
        opened = true;
        final Json pv = await preview(
            '/api/v1/sales-orders/preview', orderBody(<Json>[line('9')]));
        final List<dynamic> cs = candsOf(pv);
        final String hint =
            textsUnder('sales-order-line-offer-hint-0').join(' ');
        final Json? t11 = cand(cs, '${tea11['code']}');
        final String wantHint = hintOf(cs);
        log.saw = 'line boxes ${boxList('sales-order-line-0')}; hint "$hint"; '
            'screen ${blockSeen(p, cs)}; server ${serverCands(cs)}';
        final List<String> faults = <String>[
          ...compareBlock(p, cs),
          if (t11?['needs_more'] == null) 'the server gives TEA11 no hint at 9',
          if (hint != wantHint) 'hint under the quantity "$hint", not "$wantHint"',
          if (!_same(_n(cand(cs, '${tea5['code']}')?['worth']), 45)) 'TEA5 not 45.00',
        ];
        if (faults.isNotEmpty) throw StateError(faults.join('; '));
        if (appErrors.length > errs) throw StateError(errorsSince(errs));
      });
      if (opened) {
        await log.step('TC-OFR-001 (2) a line of 11: TEA5 55.00 and TEA11 1 '
            'free applied, CITY and the standing rate beside', () async {
          final int errs = appErrors.length;
          await typeQty('sales-order-line-0', '11');
          final Json pv = await preview(
              '/api/v1/sales-orders/preview', orderBody(<Json>[line('11')]));
          final List<dynamic> cs = candsOf(pv);
          final Json l = figures(pv);
          final String hint =
              textsUnder('sales-order-line-offer-hint-0').join(' ');
          log.saw = 'screen ${blockSeen(p, cs)}; hint "$hint"; server '
              '${serverCands(cs)}; line ${l['discount_amount']} off, free '
              '${l['free_quantity']}';
          final List<String> faults = <String>[
            ...compareBlock(p, cs),
            if (!_same(_n(l['discount_amount']), 55)) 'server discount ${l['discount_amount']}',
            if (!_same(_n(l['free_quantity']), 1)) 'server free ${l['free_quantity']}',
            if (hint != hintOf(cs)) 'hint "$hint", server "${hintOf(cs)}"',
          ];
          if (faults.isNotEmpty) throw StateError(faults.join('; '));
          if (appErrors.length > errs) throw StateError(errorsSince(errs));
        });

        await log.step('TC-OFR-003 (1) CITY ticked: priced again, CITY 44.00 '
            'and TEA11, TEA5 off', () async {
          final int errs = appErrors.length;
          await tick(p, keyCity());
          final Json pv = await preview('/api/v1/sales-orders/preview',
              orderBody(<Json>[line('11', cityAndTea11())]));
          final List<dynamic> cs = candsOf(pv);
          final Json l = figures(pv);
          final String discount = textOnScreen(tester)
              .where((String t) => t.startsWith('from '))
              .join(' | ');
          log.saw = 'screen ${blockSeen(p, cs)}; side "$discount"; server '
              '${serverCands(cs)}; line ${l['discount_amount']} off from '
              '${l['discount_source']}, free ${l['free_quantity']}, refused '
              '${l['choice_refused']}';
          final List<String> faults = <String>[
            ...compareBlock(p, cs,
                tickedKeys: <String>{keyCity(), key11()}),
            if (!_same(_n(l['discount_amount']), 44)) 'server discount ${l['discount_amount']}',
            if (l['choice_refused'] != null) 'server refused the choice',
            if (find.byKey(const ValueKey<String>('$p-refused')).evaluate().isNotEmpty)
              'a refusal on screen',
          ];
          if (faults.isNotEmpty) throw StateError(faults.join('; '));
          if (appErrors.length > errs) throw StateError(errorsSince(errs));
        });

        await log.step('L7-KEYS F6 into the block, arrows, Space ticks and '
            'unticks, Enter goes back', () async {
          final int errs = appErrors.length;
          final Finder qty = find
              .descendant(
                  of: find.byKey(const ValueKey<String>('sales-order-line-0')),
                  matching: find.byType(EditableText))
              .at(1);
          await tester.tap(qty);
          await pumpFor(tester, const Duration(milliseconds: 500));
          final FocusNode? before = FocusManager.instance.primaryFocus;
          await tester.sendKeyEvent(LogicalKeyboardKey.f6);
          await pumpFor(tester, const Duration(milliseconds: 600));
          final String inBlock =
              '${FocusManager.instance.primaryFocus?.debugLabel}';
          final List<dynamic> cs = candsOf(await preview(
              '/api/v1/sales-orders/preview',
              orderBody(<Json>[line('11', cityAndTea11())])));
          final List<String> tickable = <String>[
            for (final dynamic c in cs)
              if ((c as Json)['available'] != false) '${c['key']}',
          ];
          // The highlight starts on the first tickable row (TEA5).
          await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
          await tester.sendKeyEvent(LogicalKeyboardKey.arrowUp);
          await pumpFor(tester, const Duration(milliseconds: 300));
          await tester.sendKeyEvent(LogicalKeyboardKey.space);
          await pumpFor(tester, const Duration(milliseconds: 400));
          final String afterTea5 = 'TEA5 ${rowOf(p, key5()).ticked}, CITY '
              '${rowOf(p, keyCity()).ticked}';
          for (int i = 0; i < tickable.indexOf(keyCity()); i++) {
            await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
          }
          await tester.sendKeyEvent(LogicalKeyboardKey.space);
          await pumpFor(tester, const Duration(milliseconds: 400));
          final String afterCity = 'TEA5 ${rowOf(p, key5()).ticked}, CITY '
              '${rowOf(p, keyCity()).ticked}';
          await tester.sendKeyEvent(LogicalKeyboardKey.enter);
          await pumpFor(tester, const Duration(seconds: 3));
          final FocusNode? after = FocusManager.instance.primaryFocus;
          final List<dynamic> cs2 = candsOf(await preview(
              '/api/v1/sales-orders/preview',
              orderBody(<Json>[line('11', cityAndTea11())])));
          log.saw = 'focus after F6 "$inBlock"; Space on the first row: '
              '$afterTea5; down to CITY, Space: $afterCity; after Enter focus '
              'back on the box ${identical(after, before)} '
              '("${after?.debugLabel}"); block ${blockSeen(p, cs2)}';
          final List<String> faults = <String>[
            if (!inBlock.contains('offers')) 'F6 did not move into the block',
            if (tickable.first != key5()) 'TEA5 is not the first row',
            if (afterTea5 != 'TEA5 true, CITY false') 'Space on TEA5: $afterTea5',
            if (afterCity != 'TEA5 false, CITY true') 'Space on CITY: $afterCity',
            if (!identical(after, before)) 'Enter did not hand focus back',
            ...compareBlock(p, cs2, tickedKeys: <String>{keyCity(), key11()}),
          ];
          if (faults.isNotEmpty) throw StateError(faults.join('; '));
          if (appErrors.length > errs) throw StateError(errorsSince(errs));
        });

        await log.step('TC-OFR-003 (2) the order saved: CITY and TEA11 chosen, '
            'TEA5 passed over', () async {
          final int errs = appErrors.length;
          final Set<String> before = await idsFor('sales-orders');
          final String said = await pressAndRead(
              tester, () => tapKey(tester, 'sales-order-save'),
              seconds: 8);
          final Json? made = await newFor('sales-orders', before);
          log.saw = 'said "${said.split(' || ').first}"; ${made == null ? 'none' : '${docNumber(made)} line ${line1(made)['quantity']} ${line1(made)['discount_amount']} off, rows ${rowsOf(line1(made))}'}';
          final List<String> faults = chosenFaults(made, 'quantity');
          if (faults.isNotEmpty) throw StateError(faults.join('; '));
          if (appErrors.length > errs) throw StateError(errorsSince(errs));
        });
      }
      await away();
    }

    // =======================================================================
    // TC-OFR-004: a choice refused; a typed discount locks the block
    // =======================================================================
    if (isAdmin && _runs('refused')) {
      const String p = 'sales-order-offer';
      bool opened = false;
      await log.step('TC-OFR-004 (2)/(5) TEA5 chosen at 9, the quantity '
          'lowered to 3: the refusal on the line', () async {
        final int errs = appErrors.length;
        await newDocument('salesOrders', 'sales-order');
        await typeQty('sales-order-line-0', '9');
        opened = true;
        // Untick then tick TEA5: a real choice of TEA5 alone.
        await tick(p, key5());
        await tick(p, key5());
        await typeQty('sales-order-line-0', '3');
        await pumpFor(tester, const Duration(seconds: 2));
        final Json pv = await preview(
            '/api/v1/sales-orders/preview',
            orderBody(<Json>[
              line('3', <String, dynamic>{
                'offer_choice': <String, dynamic>{
                  'discount_from': 'offers',
                  'offers': <String>[key5()],
                },
              }),
            ]));
        final Json l = figures(pv);
        final String shown = textsUnder('$p-refused').join(' ');
        log.saw = 'refusal on screen "$shown"; server "${l['choice_refused']}", '
            'line ${l['discount_amount']} off from ${l['discount_source']}; '
            'block ${blockSeen(p, candsOf(pv))}';
        final List<String> faults = <String>[
          if ('${l['choice_refused'] ?? ''}'.isEmpty) 'the server refused nothing',
          if (shown != '${l['choice_refused']}') 'the line does not carry the server\'s words',
        ];
        if (faults.isNotEmpty) throw StateError(faults.join('; '));
        if (appErrors.length > errs) throw StateError(errorsSince(errs));
      });
      if (opened) {
        await log.step('TC-OFR-004 (1) 11, CITY ticked, then 3% typed: the '
            'block locked, the save sends no choice', () async {
          final int errs = appErrors.length;
          await typeQty('sales-order-line-0', '11');
          await tick(p, keyCity());
          final List<String> boxes = boxList('sales-order-line-0');
          int rate = -1;
          for (int i = 1; i < boxes.length; i++) {
            if (_same(_first(boxes[i]), 100) && boxes[i].contains('.')) rate = i;
          }
          if (rate < 0) throw StateError('no rate box in $boxes');
          await typeIn(tester, 'sales-order-line-0', rate + 1, '3');
          await pumpFor(tester, const Duration(seconds: 3));
          final String note = textOnScreen(tester)
              .where((String t) => t.startsWith('A discount typed on the line'))
              .join(' | ');
          final List<String> enabled = <String>[
            for (final String k in keysStarting('$p-'))
              if (k.endsWith('-tick') &&
                  tester.widget<Checkbox>(find.byKey(ValueKey<String>(k))).onChanged != null)
                k,
          ];
          final Set<String> before = await idsFor('sales-orders');
          final String said = await pressAndRead(
              tester, () => tapKey(tester, 'sales-order-save'),
              seconds: 8);
          final Json? made = await newFor('sales-orders', before);
          final Json? l = made == null ? null : line1(made);
          log.saw = 'boxes after typing ${boxList('sales-order-line-0')}; note '
              '"$note"; ticks enabled $enabled; said "$said"; '
              '${l == null ? 'none saved' : '${docNumber(made!)} ${l['discount_percent']}% ${l['discount_amount']} from ${l['discount_source']}, rows ${rowsOf(l)}'}';
          final List<String> faults = <String>[
            if (note.isEmpty) 'no lock note',
            if (enabled.isNotEmpty) 'ticks still enabled',
            if (l == null) 'not saved (a choice sent beside a typed discount?)',
            if (l != null && !_same(_n(l['discount_percent']), 3)) 'not 3% typed',
            if (l != null && rowsOf(l).any((String r) => r.contains('chosen')))
              'a chosen row beside a typed discount',
          ];
          if (faults.isNotEmpty) throw StateError(faults.join('; '));
          if (appErrors.length > errs) throw StateError(errorsSince(errs));
        });
      }
      await away();
    }

    // =======================================================================
    // TC-OFR-008: a part share
    // =======================================================================
    if (isAdmin && _runs('share')) {
      const String p = 'sales-order-offer';
      bool opened = false;
      await log.step('TC-OFR-008 (1) a line of 6: TEA11 offers 5.5 + 0.5 free',
          () async {
        final int errs = appErrors.length;
        await newDocument('salesOrders', 'sales-order');
        await typeQty('sales-order-line-0', '6');
        opened = true;
        final Json pv = await preview(
            '/api/v1/sales-orders/preview', orderBody(<Json>[line('6')]));
        final Json? t11 = cand(candsOf(pv), '${tea11['code']}');
        final Json? share = t11?['part_share'] as Json?;
        final String button =
            textsUnder('$p-${key11()}-part-share').join(' ');
        final String want = share == null
            ? '(none)'
            : 'Part share: ${_plain(share['charged_quantity'])} + '
                '${_plain(share['free_quantity'])} free';
        log.saw = 'button "$button"; server part share $share; block '
            '${blockSeen(p, candsOf(pv))}';
        final List<String> faults = <String>[
          if (share == null) 'the server offers no part share',
          if (button != want) 'button "$button", not "$want"',
          ...compareBlock(p, candsOf(pv)),
        ];
        if (faults.isNotEmpty) throw StateError(faults.join('; '));
        if (appErrors.length > errs) throw StateError(errorsSince(errs));
      });
      if (opened) {
        await log.step('TC-OFR-008 (2) Part share pressed: 5.5 charged, "0.5 '
            'free from TEA11", saved', () async {
          final int errs = appErrors.length;
          await tapKey(tester, '$p-${key11()}-part-share');
          await pumpFor(tester, const Duration(seconds: 3));
          final String qty = boxList('sales-order-line-0').length > 1
              ? boxList('sales-order-line-0')[1]
              : '(none)';
          final String note = textsUnder('$p-part-share-note').join(' ');
          final Set<String> before = await idsFor('sales-orders');
          final String said = await pressAndRead(
              tester, () => tapKey(tester, 'sales-order-save'),
              seconds: 8);
          final Json? made = await newFor('sales-orders', before);
          final Json? l = made == null ? null : line1(made);
          log.saw = 'quantity box "$qty"; note "$note"; said "$said"; '
              '${l == null ? 'none' : '${docNumber(made!)} ${l['quantity']} + ${l['free_quantity']} free, ${l['discount_amount']} off, rows ${rowsOf(l)}'}';
          final List<String> faults = <String>[
            if (!_same(_first(qty), 5.5)) 'quantity box not 5.5',
            if (note != '0.5 free from ${tea11['code']}') 'note "$note"',
            if (l == null) 'not saved',
            if (l != null && !_same(_n(l['quantity']), 5.5)) 'server quantity ${l['quantity']}',
            if (l != null && !_same(_n(l['free_quantity']), 0.5)) 'server free ${l['free_quantity']}',
            if (l != null && !_same(_n(l['discount_amount']), 27.5)) 'server discount ${l['discount_amount']}',
            if (l != null &&
                !rowsOf(l).any((String r) =>
                    r.startsWith('TEA11 APPLIED chosen') && r.endsWith('part')))
              'no TEA11 part share row',
          ];
          if (faults.isNotEmpty) throw StateError(faults.join('; '));
          if (appErrors.length > errs) throw StateError(errorsSince(errs));
        });
      }
      await away();
    }

    // =======================================================================
    // TC-OFR-010 (1)-(2): the quotation
    // =======================================================================
    if (isAdmin && _runs('quote')) {
      const String p = 'quotation-offer';
      bool opened = false;
      await log.step('TC-OFR-010 (1) a quotation line of 11, CITY ticked: as '
          'the preview', () async {
        final int errs = appErrors.length;
        await newDocument('quotations', 'quotation');
        await typeQty('quotation-line-0', '11');
        opened = true;
        final List<dynamic> start = candsOf(await preview(
            '/api/v1/quotations/preview', quoteBody(<Json>[line('11')])));
        final List<String> first = compareBlock(p, start);
        await tick(p, keyCity());
        final Json pv = await preview('/api/v1/quotations/preview',
            quoteBody(<Json>[line('11', cityAndTea11())]));
        log.saw = 'before the tick ${first.isEmpty ? 'as the server' : first}; '
            'after ${blockSeen(p, candsOf(pv))}; server ${serverCands(candsOf(pv))}';
        final List<String> faults = <String>[
          ...first,
          ...compareBlock(p, candsOf(pv), tickedKeys: <String>{keyCity(), key11()}),
          if (!_same(_n(figures(pv)['discount_amount']), 44)) 'server discount',
        ];
        if (faults.isNotEmpty) throw StateError(faults.join('; '));
        if (appErrors.length > errs) throw StateError(errorsSince(errs));
      });
      if (opened) {
        await log.step('TC-OFR-010 (2) the quotation saved: CITY and TEA11 '
            'chosen, TEA5 passed over', () async {
          final int errs = appErrors.length;
          final Set<String> before = await idsFor('quotations');
          final String said = await pressAndRead(
              tester, () => tapKey(tester, 'quotation-save'),
              seconds: 8);
          final Json? made = await newFor('quotations', before);
          log.saw = 'said "${said.split(' || ').first}"; ${made == null ? 'none' : '${docNumber(made)} rows ${rowsOf(line1(made))}'}';
          final List<String> faults = chosenFaults(made, 'quantity');
          if (faults.isNotEmpty) throw StateError(faults.join('; '));
          if (appErrors.length > errs) throw StateError(errorsSince(errs));
        });
      }
      await away();
    }

    // =======================================================================
    // TC-OFR-009 (1)-(3): the counter bill
    // =======================================================================
    if (isAdmin && _runs('counter')) {
      const String p = 'sales-invoice-offer';
      final Json stages = (await admin.get(_workflow)) as Json;
      const List<String> stageKeys = <String>[
        'quotation_stage', 'sales_order_stage', 'delivery_note_stage',
        'default_branch_id', 'default_warehouse_id', 'promotion_mode',
        'max_line_discount_percent', 'rate_includes_tax',
        'new_outlets_need_approval', 'reservation_lapse_days',
        'sales_order_approval', 'delivery_note_approval',
        'sales_invoice_approval', 'round_bills_to_rupee', 'salesman_required',
        'box_and_piece_entry',
      ];
      final Json stagesBack = <String, dynamic>{
        for (final String k in stageKeys)
          if (stages.containsKey(k)) k: stages[k],
      };
      try {
        await admin.write('PUT', _workflow, <String, dynamic>{
          ...stagesBack,
          'quotation_stage': false,
          'sales_order_stage': false,
          'delivery_note_stage': false,
          'default_branch_id': branch['id'],
          'default_warehouse_id': warehouse['id'],
        });
        log.info('TC-OFR-009', 'order and note stages off over HTTP');
        bool opened = false;
        await log.step('TC-OFR-009 (1) a counter line of 11, CITY ticked: as '
            'the preview', () async {
          final int errs = appErrors.length;
          await away();
          await openMenu(tester, 'sell', 'salesInvoices/sales-invoices');
          await tapNew(tester);
          await pumpFor(tester, const Duration(seconds: 2));
          await pick('sales-invoice-customer', 'OC$tag', nameC);
          await pick('sales-invoice-direct-product-0', '0O$tag', nameP);
          await settle();
          await typeQty('sales-invoice-direct-0', '11');
          opened = true;
          final List<dynamic> start = candsOf(await preview(
              '/api/v1/sales-invoices/preview', billBody(<Json>[line('11')])));
          final List<String> first = compareBlock(p, start);
          await tick(p, keyCity());
          final Json pv = await preview('/api/v1/sales-invoices/preview',
              billBody(<Json>[line('11', cityAndTea11())]));
          final String bill = textsUnder('bill-offers').join(' | ');
          log.saw = 'before the tick ${first.isEmpty ? 'as the server' : first}; '
              'after ${blockSeen(p, candsOf(pv))}; server '
              '${serverCands(candsOf(pv))}; bill offers "$bill", server '
              '${(pv['bill_candidates'] as List<dynamic>?)?.length ?? 0}';
          final List<String> faults = <String>[
            ...first,
            ...compareBlock(p, candsOf(pv), tickedKeys: <String>{keyCity(), key11()}),
            if (!_same(_n(figures(pv)['discount_amount']), 44)) 'server discount',
          ];
          if (faults.isNotEmpty) throw StateError(faults.join('; '));
          if (appErrors.length > errs) throw StateError(errorsSince(errs));
        });
        if (opened) {
          await log.step('TC-OFR-009 (2)-(3) saved as a draft: the bill line '
              'and its order carry CITY and TEA11 chosen', () async {
            final int errs = appErrors.length;
            final Set<String> before = await idsFor('sales-invoices');
            final Set<String> orders = await idsFor('sales-orders');
            final String said = await pressAndRead(
                tester, () => tapKey(tester, 'sales-invoice-save'),
                seconds: 10);
            await admin.write('PUT', _workflow, stagesBack);
            final Json? made = await newFor('sales-invoices', before);
            final Json? so = await newFor('sales-orders', orders);
            log.saw = 'said "${said.split(' || ').first}"; ${made == null ? 'no bill' : '${docNumber(made)} ${made['status']} rows ${rowsOf(line1(made))}'}; '
                '${so == null ? 'no order' : 'order ${docNumber(so)} rows ${rowsOf(line1(so))}'}';
            if (made != null) {
              final ({int status, String text}) gone = await admin.attempt('POST',
                  '/api/v1/sales-invoices/${made['id']}/cancel',
                  <String, dynamic>{'reason': 'click flow clean-up'});
              log.info('TC-OFR-009', 'draft cancelled: ${gone.status}');
            }
            final List<String> faults = <String>[
              ...chosenFaults(made, 'current_invoice_quantity'),
              ...chosenFaults(so, 'quantity').map((String f) => 'order: $f'),
            ];
            if (faults.isNotEmpty) throw StateError(faults.join('; '));
            if (appErrors.length > errs) throw StateError(errorsSince(errs));
          });
        }
        await admin.write('PUT', _workflow, stagesBack);
        await away();
      } finally {
        await admin.write('PUT', _workflow, stagesBack);
        final Json back = (await admin.get(_workflow)) as Json;
        log.info('TC-OFR-009', 'stages put back over HTTP: order '
            '${back['sales_order_stage']}, note ${back['delivery_note_stage']}, '
            'quotation ${back['quotation_stage']}');
      }
    }

    // =======================================================================
    // TC-OFR-007 (5)-(6): Sales stages' third setting
    // =======================================================================
    if (_runs('settings')) {
      final Json held = (await admin.get(_workflow)) as Json;
      final String heldMode = '${held['promotion_mode']}';
      Future<void> openStages() async {
        await away();
        await tester.tap(find.byKey(const ValueKey<String>('menu-area-settings')));
        await pumpFor(tester, const Duration(seconds: 1));
        await tapKey(tester, 'setup-section-Selling');
        await pumpFor(tester, const Duration(milliseconds: 600));
        await tapKey(tester, 'setup-subject-selling');
        await pumpFor(tester, const Duration(seconds: 2));
        await tapKey(tester, 'subject-tab-settings/sales-stages');
        await pumpFor(tester, const Duration(seconds: 2));
        await tapButtonStarting(tester, 'Open ');
        await pumpFor(tester, const Duration(seconds: 3));
        await pumpUntil(tester,
            find.byKey(const ValueKey<String>('sales-settings-promotion-mode')),
            waitingFor: 'the offers setting');
      }

      try {
        await log.step('TC-OFR-007 Sales stages: the three offer settings, '
            'as the server', () async {
          final int errs = appErrors.length;
          await openStages();
          final Finder dd =
              find.byKey(const ValueKey<String>('sales-settings-promotion-mode'));
          final DropdownButtonFormField<String> field =
              tester.widget<DropdownButtonFormField<String>>(dd.first);
          final String shown = textsUnder('sales-settings-promotion-mode').join(' | ');
          final bool editable = tester
                  .widgetList<DropdownButton<String>>(find.descendant(
                      of: dd.first, matching: find.byType(DropdownButton<String>)))
                  .firstOrNull
                  ?.onChanged !=
              null;
          List<String> options = <String>[];
          if (editable) {
            await tester.tap(dd.first);
            await pumpFor(tester, const Duration(milliseconds: 800));
            options = <String>[
              for (final String t in <String>[
                'Combine offers', 'Best offer only',
                'Best one, the bill maker may add more',
              ])
                if (find.text(t).evaluate().length > (shown.contains(t) ? 1 : 0)) t,
            ];
          }
          log.saw = 'shows "$shown", editable $editable, options in the list '
              '$options; server $heldMode; field ${field.key}';
          final String want = switch (heldMode) {
            'ASK' => 'Best one, the bill maker may add more',
            'BEST_OFFER' => 'Best offer only',
            _ => 'Combine offers',
          };
          final List<String> faults = <String>[
            if (!shown.contains(want)) 'does not show "$want"',
            if (isAdmin && !editable) 'the admin may not change it',
            if (!isAdmin && editable) 'the viewer may change it',
            if (isAdmin && options.length != 3) 'options $options',
          ];
          if (faults.isNotEmpty) throw StateError(faults.join('; '));
          if (appErrors.length > errs) throw StateError(errorsSince(errs));
        });

        if (isAdmin) {
          bool asked = false;
          await log.step('TC-OFR-007 (5) "Best one, the bill maker may add '
              'more" chosen and saved: the server holds ASK', () async {
            final int errs = appErrors.length;
            if (find.text('Best one, the bill maker may add more').evaluate().isEmpty) {
              await tester.tap(find.byKey(
                  const ValueKey<String>('sales-settings-promotion-mode')));
              await pumpFor(tester, const Duration(milliseconds: 800));
            }
            await tester.tap(find.text('Best one, the bill maker may add more').last);
            await pumpFor(tester, const Duration(milliseconds: 800));
            final bool cap = find
                .byKey(const ValueKey<String>('sales-settings-line-discount-cap'))
                .evaluate()
                .isNotEmpty;
            final String said = await pressAndRead(
                tester, () => tapButton(tester, 'Save'),
                seconds: 6);
            final Json now = (await admin.get(_workflow)) as Json;
            asked = now['promotion_mode'] == 'ASK';
            log.saw = 'line cap box shown $cap; said "$said"; server '
                '${now['promotion_mode']}';
            if (!asked) throw StateError('the server holds ${now['promotion_mode']}');
            if (!cap) throw StateError('no line cap under ASK');
            if (appErrors.length > errs) throw StateError(errorsSince(errs));
          });
          if (asked) {
            const String p = 'sales-order-offer';
            bool opened = false;
            await log.step('TC-OFR-007 (5) under ASK a line of 11: TEA11 and '
                'CITY 44.00, TEA5 not applied', () async {
              final int errs = appErrors.length;
              await newDocument('salesOrders', 'sales-order');
              await typeQty('sales-order-line-0', '11');
              opened = true;
              final Json pv = await preview(
                  '/api/v1/sales-orders/preview', orderBody(<Json>[line('11')]));
              final Json l = figures(pv);
              log.saw = 'screen ${blockSeen(p, candsOf(pv))}; server '
                  '${serverCands(candsOf(pv))}; line ${l['discount_amount']} '
                  'off from ${l['discount_source']}, free ${l['free_quantity']}';
              final List<String> faults = <String>[
                ...compareBlock(p, candsOf(pv)),
                if (!_same(_n(l['discount_amount']), 44)) 'server discount ${l['discount_amount']}',
                if (!_same(_n(l['free_quantity']), 1)) 'server free ${l['free_quantity']}',
              ];
              if (faults.isNotEmpty) throw StateError(faults.join('; '));
              if (appErrors.length > errs) throw StateError(errorsSince(errs));
            });
            if (opened) {
              await log.step('TC-OFR-007 (6) TEA5 ticked as well: 55.00 off and '
                  '1 free, both chosen when saved', () async {
                final int errs = appErrors.length;
                await tick(p, key5());
                final Json pv = await preview(
                    '/api/v1/sales-orders/preview',
                    orderBody(<Json>[
                      line('11', <String, dynamic>{
                        'offer_choice': <String, dynamic>{
                          'discount_from': 'offers',
                          'offers': <String>[key11(), key5()],
                        },
                      }),
                    ]));
                final List<String> shownFaults = compareBlock(
                    p, candsOf(pv), tickedKeys: <String>{key5(), key11()});
                final String refused = textsUnder('$p-refused').join(' ');
                final String seen = blockSeen(p, candsOf(pv));
                final Set<String> before = await idsFor('sales-orders');
                final String said = await pressAndRead(
                    tester, () => tapKey(tester, 'sales-order-save'),
                    seconds: 8);
                final Json? made = await newFor('sales-orders', before);
                final Json? l = made == null ? null : line1(made);
                log.saw = 'screen $seen; refused '
                    '"$refused"; server preview ${figures(pv)['discount_amount']} '
                    'off, free ${figures(pv)['free_quantity']}; said "$said"; '
                    '${l == null ? 'none' : 'saved ${l['discount_amount']} off, free ${l['free_quantity']}, rows ${rowsOf(l)}'}';
                final List<String> faults = <String>[
                  ...shownFaults,
                  if (refused.isNotEmpty) 'refused "$refused"',
                  if (l == null) 'not saved',
                  if (l != null && !_same(_n(l['discount_amount']), 55)) 'saved discount',
                  if (l != null && !_same(_n(l['free_quantity']), 1)) 'saved free',
                  if (l != null &&
                      !rowsOf(l).any((String r) => r.startsWith('TEA5 APPLIED chosen')))
                    'TEA5 not chosen',
                ];
                if (faults.isNotEmpty) throw StateError(faults.join('; '));
                if (appErrors.length > errs) throw StateError(errorsSince(errs));
              });
            }
          }
        }
        await away();
      } finally {
        if (isAdmin) {
          final Json cur = (await admin.get(_workflow)) as Json;
          if (cur['promotion_mode'] != heldMode) {
            await admin.write('PUT', _workflow, <String, dynamic>{
              'quotation_stage': cur['quotation_stage'],
              'sales_order_stage': cur['sales_order_stage'],
              'delivery_note_stage': cur['delivery_note_stage'],
              'promotion_mode': heldMode,
            });
          }
          final Json back = (await admin.get(_workflow)) as Json;
          log.info('TC-OFR-007', 'promotion_mode put back over HTTP: '
              '${back['promotion_mode']} (was $heldMode); stages '
              '${back['quotation_stage']}/${back['sales_order_stage']}/'
              '${back['delivery_note_stage']}, cap '
              '${back['max_line_discount_percent']}, boxes '
              '${back['box_and_piece_entry']}');
        }
      }
    }

    // =======================================================================
    // L7 step 8: the offer form's "Allow a part share"
    // =======================================================================
    if (_runs('promo')) {
      Future<String> openOffer(Json o) async {
        await away();
        await tester.tap(find.byKey(const ValueKey<String>('menu-area-settings')));
        await pumpFor(tester, const Duration(seconds: 1));
        await tapKey(tester, 'setup-section-Pricing');
        await pumpFor(tester, const Duration(milliseconds: 600));
        await tapKey(tester, 'setup-subject-pricing');
        await pumpFor(tester, const Duration(seconds: 2));
        await tapKey(tester, 'subject-tab-sales/promotions');
        await pumpFor(tester, const Duration(seconds: 3));
        if (buttonState(tester, 'Open Promotions') == 'enabled') {
          await tapButton(tester, 'Open Promotions');
          await pumpFor(tester, const Duration(seconds: 3));
        }
        await refreshList(tester);
        await searchList(tester, '${o['code']}');
        await pickRow(tester, '${o['code']}');
        for (final String b in const <String>['Edit', 'Open', 'View']) {
          if (buttonState(tester, b) == 'enabled') {
            await tapButton(tester, b);
            await pumpFor(tester, const Duration(seconds: 3));
            return b;
          }
        }
        throw StateError('no Edit, Open or View for ${o['code']}');
      }

      await log.step('L7-PROMO TEA11\'s form: "Allow a part share" ticked, '
          'as the server', () async {
        final int errs = appErrors.length;
        final String how = await openOffer(tea11);
        final Finder f =
            find.byKey(const ValueKey<String>('promotion-allow-part-share'));
        final CheckboxListTile? tile = f.evaluate().isEmpty
            ? null
            : tester.widget<CheckboxListTile>(f.first);
        final Json server = await me.one('promotions', '${tea11['id']}');
        // The read-only view (Open) says it in words (D-UI-119).
        final String said = textsUnder('promotion-part-share').join(' ');
        log.saw = 'opened with $how; box ${tile == null ? 'absent' : 'value ${tile.value}, editable ${tile.onChanged != null}'}; '
            'view says "$said"; server allow_part_share ${server['allow_part_share']}';
        final List<String> faults = <String>[
          if (tile == null && said.isEmpty) 'no "Allow a part share"',
          if (tile == null &&
              said.isNotEmpty &&
              said.startsWith('A part share') != (server['allow_part_share'] == true))
            'the view is not what the server holds',
          if (tile != null && tile.value != (server['allow_part_share'] == true))
            'the box is not the server\'s',
          if (!isAdmin && tile?.onChanged != null && buttonState(tester, 'Save') == 'enabled')
            'the viewer may change it',
        ];
        if (faults.isNotEmpty) throw StateError(faults.join('; '));
        if (appErrors.length > errs) throw StateError(errorsSince(errs));
      });
      await log.step('L7-PROMO TEA5 (a discount) has no "Allow a part share"',
          () async {
        final int errs = appErrors.length;
        final String how = await openOffer(tea5);
        final bool shown = find
                .byKey(const ValueKey<String>('promotion-allow-part-share'))
                .evaluate()
                .isNotEmpty ||
            find
                .byKey(const ValueKey<String>('promotion-part-share'))
                .evaluate()
                .isNotEmpty;
        log.saw = 'opened with $how; box shown $shown; server '
            '${tea5['allow_part_share']}';
        if (shown) throw StateError('offered on a discount offer');
        if (appErrors.length > errs) throw StateError(errorsSince(errs));
      });
      await away();
    }

    // =======================================================================
    // L7 step 9 / TC-OFR-011 (1): the saved order and quotation reopened
    // =======================================================================
    if (_runs('saved')) {
      Future<String> openFromList(String number) async {
        await refreshList(tester);
        await searchList(tester, number);
        await pickRow(tester, number);
        for (final String b in const <String>['Edit', 'Open', 'View']) {
          if (buttonState(tester, b) == 'enabled') {
            await tapButton(tester, b);
            await pumpFor(tester, const Duration(seconds: 4));
            return b;
          }
        }
        throw StateError('no Edit, Open or View for $number');
      }

      /// "Price list CITY... · 44.00 off · chosen by a person" and the rest.
      List<String> wordsFor(Json l) {
        final List<Json> rows = <Json>[
          for (final dynamic r in (l['offers'] as List<dynamic>?) ?? <dynamic>[])
            if ((r as Json)['state'] == 'APPLIED' || r['state'] == 'REFUSED') r,
        ]..sort((Json a, Json b) =>
            _n(a['sequence']).compareTo(_n(b['sequence'])));
        return <String>[
          for (final Json r in rows)
            switch ('${r['source']}') {
              'price_list' => 'Price list ${r['code']}',
              'customer' => 'Standing rate',
              'customer_group' => 'Group rate',
              _ => '${r['code']}',
            } +
                (r['state'] == 'REFUSED'
                    ? ' · passed over'
                    : '${_n(r['discount_amount']) > 0 ? ' · ${_n(r['discount_amount']).toStringAsFixed(2)} off' : ''}'
                        '${_n(r['free_quantity']) > 0 ? ' · ${_plain(r['free_quantity'])} free' : ''}'
                        '${r['part_share'] == true ? ' · part share' : ''}'
                        ' · ${r['chosen'] == true ? 'chosen by a person' : 'applied'}'),
        ];
      }

      Future<void> savedStep(String what, String menu, String prefix,
          String collection, Json doc) async {
        await log.step('L7-SAVED $what ${docNumber(doc)} opened: each row '
            '"applied", "chosen by a person", "passed over"', () async {
          final int errs = appErrors.length;
          await away();
          try {
            await openMenu(tester, 'sell', menu);
          } on TestFailure {
            await away();
            await openMenu(tester, 'sell', menu);
          }
          final String how = await openFromList(docNumber(doc));
          // The first line is the one the side panel follows.
          final Finder row = find.byKey(ValueKey<String>('$prefix-line-0'));
          if (row.evaluate().isNotEmpty) {
            await tester.tap(row.first, warnIfMissed: false);
            await pumpFor(tester, const Duration(seconds: 3));
          }
          final Json server = await me.one(collection, '${doc['id']}');
          final List<String> want = wordsFor(line1(server));
          final List<String> saved = <String>[
            for (final String k in keysStarting('$prefix-offer-saved-')..sort())
              ...textsUnder(k),
          ];
          final List<dynamic> candsShown = keysStarting('$prefix-offer-')
              .where((String k) => k.endsWith('-tick'))
              .toList();
          List<String> onScreenOffers() => <String>[
                for (final String t in textOnScreen(tester))
                  if (t.contains('chosen by a person') ||
                      t.contains('passed over') ||
                      t.endsWith('· applied'))
                    t,
              ];
          final List<String> onScreen = onScreenOffers();
          log.saw = 'opened with $how; saved rows $saved; ticks $candsShown; '
              'such texts anywhere $onScreen; server ${rowsOf(line1(server))} '
              '-> expected $want';
          String plainText(String t) => t.replaceAll('₹', '').replaceAll(',', '');
          final String viewText = onScreenOffers().map(plainText).join(' | ');
          final String pvPath = collection == 'quotations'
              ? '/api/v1/quotations/preview'
              : '/api/v1/sales-orders/preview';
          final List<dynamic> held = candsShown.isEmpty
              ? <dynamic>[]
              : candsOf(await preview(
                  pvPath,
                  collection == 'quotations'
                      ? quoteBody(<Json>[line('11', cityAndTea11())])
                      : orderBody(<Json>[line('11', cityAndTea11())])));
          log.saw = '${log.saw}; view offers "$viewText"'
              '${held.isEmpty ? '' : '; editor block ${blockSeen('$prefix-offer', held)}'}';
          final List<String> faults = <String>[
            if (want.isEmpty) 'the server holds no rows',
            if (saved.isEmpty && candsShown.isEmpty && viewText.isEmpty)
              'no offer rows at all on the opened $what',
            if (saved.isNotEmpty &&
                !want.every((String w) =>
                    saved.any((String s) => plainText(s) == w)))
              'saved rows $saved are not $want',
            if (saved.isEmpty && candsShown.isEmpty && viewText.isNotEmpty &&
                !want.every(viewText.contains))
              'the view says "$viewText", not $want',
            // A draft reopened in its editor is priced again: as saved.
            if (candsShown.isNotEmpty)
              ...compareBlock('$prefix-offer', held,
                  tickedKeys: <String>{keyCity(), key11()}),
          ];
          if (faults.isNotEmpty) {
            throw StateError('${faults.join('; ')} :: ${log.saw}; screen '
                '${textOnScreen(tester).skip(20).take(80).join(' | ')}');
          }
          if (appErrors.length > errs) throw StateError(errorsSince(errs));
        });
        await away();
      }

      await savedStep('the order', 'salesOrders', 'sales-order', 'sales-orders',
          savedOrder);
      if (isAdmin) {
        await log.step('TC-OFR-011 (2) the reopened draft saved unchanged: '
            'the choice kept', () async {
          final int errs = appErrors.length;
          await away();
          await openMenu(tester, 'sell', 'salesOrders');
          await openFromList(docNumber(savedOrder));
          final String said = await pressAndRead(
              tester, () => tapKey(tester, 'sales-order-save'),
              seconds: 8);
          final Json now = await admin.one('sales-orders', '${savedOrder['id']}');
          log.saw = 'said "${said.split(' || ').first}"; version '
              '${savedOrder['version']} -> ${now['version']}; rows '
              '${rowsOf(line1(now))}';
          final List<String> faults = chosenFaults(now, 'quantity');
          if (faults.isNotEmpty) throw StateError(faults.join('; '));
          if (appErrors.length > errs) throw StateError(errorsSince(errs));
        });
        await away();
      }
      await savedStep('the quotation', 'quotations', 'quotation', 'quotations',
          savedQuote);
    }

    if (!isAdmin) {
      log.skip('L7 read-only block', 'the viewer cannot raise an order; a '
          'user holding SALES_CREATE less SALES_OFFER_CHOOSE is not in TEST03');
    }
    log.skip('TC-OFR-005', 'SOLO-3 (does not combine) is HTTP (tc_ofr_005.py)');
    log.skip('TC-OFR-006', 'needs a user without SALES_OFFER_CHOOSE who may '
        'sell (tc_ofr_006.py)');
    log.skip('TC-OFR-012', 'the discount reports are HTTP (tc_ofr_012.py)');
    log.info('errors', 'app errors and overflows this run: ${appErrors.length}');
    log.finish();
  });
}
