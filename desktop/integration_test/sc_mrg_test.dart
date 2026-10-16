import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'cases.dart';
import 'harness.dart';
import 'sc_gt_test.dart' show leave, openArea, pickDropdown, pickRow, pressAndRead;

/// Lot margins on the screens (book 07, TC-LOT-015 to TC-LOT-022; the HTTP
/// halves are `docs/qa/checks/lots/tc_lot_015.py` .. `tc_lot_022.py`). Run on
/// the `lot-firm` fixture (TEST03) as lotadmin, then as lotviewer.
///
/// Every run makes its own masters over HTTP before the app starts (so the
/// screens read them at sign-in): a goods type with margins 25 / 12.5 and a
/// category on it, three batch-tracked products with margins 25 / 12.5 (MA
/// for the receipt, MC with two lots at PTR 100 and 112 for the order and the
/// counter, MD with one lot at cost 80 for the cost and margin), a retailer
/// and a stockist customer, a supplier, an approved purchase order of four
/// lines of MA at 80, and for MD an order, a dispatched note and a draft
/// bill of 2 at 100, plus a second draft order of 2 at 100. Codes carry the
/// minute and the user (`1432A`).
///
/// As the admin: the product form fills the goods type's margins, keeps a
/// typed one, refuses -1; a goods receipt's four lines (margins blank, MRP
/// 130 with retail 40, typed PTR 104, typed PTR 104 then retail 40), saved
/// (the MRP warning keeps it open), read and completed; two refusals on a
/// second receipt; the lot page's retail price changed to 108 and refused
/// at 85; a sales order's Price level for a retailer and a stockist; the
/// cost and margin on the draft order and the draft bill; a counter bill of
/// 15 split over the two lots of MC, and again with a typed rate. As the
/// viewer: no Edit on the lot page (and the server refuses the save), no
/// Cost or Margin on the order or the bill. Every value on screen is set
/// beside what the server returned; app errors and overflows are counted.

/// IT_PART=product (or receipt, lot, order, bill, counter) runs that part.
const String _part = String.fromEnvironment('IT_PART');
bool _runs(String part) => _part.isEmpty || _part.split(',').contains(part);

const String _workflow = '/api/v1/sales-orders/workflow-settings';

String _today() => DateTime.now().toIso8601String().substring(0, 10);

double _n(dynamic v) => double.tryParse('${v ?? ''}'.replaceAll(',', '')) ?? 0;

/// The first number in [text] ("₹1,12.00 est." -> 112), or null.
double? _first(String text) {
  final Match? m = RegExp(r'-?[\d,]+(\.\d+)?').firstMatch(text);
  return m == null ? null : double.tryParse(m.group(0)!.replaceAll(',', ''));
}

bool _same(double? a, double b) => a != null && (a - b).abs() < 0.005;

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('MRG: lot margins ($itHandle)', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1600, 1000);
    tester.view.devicePixelRatio = 1;
    final bool isAdmin = itHandle == 'lotadmin';
    final Server admin = await Server.connectAs(
        '$itSuffix.lotadmin@fixtures.local', fixturePassword);
    final Server me = await Server.connect();
    final FlowLog log = FlowLog('mrg-$itHandle');

    final DateTime now = DateTime.now();
    final String stamp = '${now.hour.toString().padLeft(2, '0')}'
        '${now.minute.toString().padLeft(2, '0')}';
    final String tag = '$stamp${isAdmin ? 'A' : 'V'}';
    // Sorts first, newest first, in the product form's category box.
    final String top =
        '0${9999999999 - DateTime.now().millisecondsSinceEpoch ~/ 1000}';

    // -- Reading the server --------------------------------------------------
    Future<List<Json>> list(String path) async => <Json>[
          for (final dynamic row in (await admin.get(path)) as List<dynamic>)
            row as Json,
        ];

    // -- Masters, made over HTTP before the app starts -----------------------
    late Json branch, warehouse, vendor, retailer, stockist;
    late Json goodsType, category, productA, productC, productD;
    late Json poA, poRefused, draftOrder, draftBill;
    late String piece;
    final Map<String, Json> levels = <String, Json>{};

    String brandName = 'Fixture Brand';
    Future<String> brandId() async {
      for (final Json b in await list('/api/v1/products/brands')) {
        if (b['name'] == 'Check Brand' || b['name'] == 'Fixture Brand') {
          brandName = '${b['name']}';
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

    Future<Json> makeProduct(String code, String name) async =>
        (await admin.write('POST', '/api/v1/products', <String, dynamic>{
          'code': code,
          'brand_id': await brandId(),
          'name': name,
          'product_type': 'STOCK_ITEM',
          'tax_profile_group_code': 'GST_18_LOCAL',
          // Not a lot price, so a line priced from the product shows.
          'selling_price': '70',
          'purchase_price': '80',
          'base_uom_id': piece,
          'inventory_uom_id': piece,
          'sales_uom_id': piece,
          'purchase_uom_id': piece,
          'track_batch': true,
          'retail_margin_percent': '25',
          'wholesale_margin_percent': '12.5',
        })) as Json;

    Future<Json> approvedPo(Json product, int lines) async {
      final Json po = (await admin.write('POST', '/api/v1/purchases',
          <String, dynamic>{
            'vendor_id': vendor['id'],
            'branch_id': branch['id'],
            'warehouse_id': warehouse['id'],
            'purchase_date': _today(),
            'lines': <Json>[
              for (int i = 0; i < lines; i++)
                <String, dynamic>{
                  'product_id': product['id'],
                  'ordered_quantity': '10',
                  'unit_price': '80',
                  'purchase_uom_id': piece,
                  'inventory_uom_id': piece,
                },
            ],
          })) as Json;
      await apiAct(admin, 'purchases', '${po['id']}', 'submit');
      await apiAct(admin, 'purchases', '${po['id']}', 'approve');
      return admin.one('purchases', '${po['id']}');
    }

    Future<Json> receiveOverHttp(Json po, List<Json> extra) async {
      final List<dynamic> lines = po['lines'] as List<dynamic>;
      final Json gr = (await admin.write('POST', '/api/v1/goods-receipts',
          <String, dynamic>{
            'purchase_order_id': po['id'],
            'receipt_date': _today(),
            'lines': <Json>[
              for (int i = 0; i < extra.length; i++)
                <String, dynamic>{
                  'purchase_order_line_id': (lines[i] as Json)['id'],
                  'line_number': i + 1,
                  'current_receipt_quantity': '10',
                  'unit_price': '80',
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

    Future<Json?> batchNamed(Json product, String number) async {
      for (final Json b in await batchesOf(product)) {
        if (b['batch_number'] == number) return b;
      }
      return null;
    }

    Future<Json> customer(String code, String name, String kind) async =>
        (await admin.write('POST', '/api/v1/customers', <String, dynamic>{
          'code': code,
          'name': name,
          'customer_type': 'BUSINESS',
          'currency_code': 'INR',
          'trade_class': kind,
        })) as Json;

    final String nameA = 'LM rec $tag';
    final String nameC = 'LM two $tag';
    final String nameD = 'LM cost $tag';
    final String nameR = 'LM retailer $tag';
    final String nameW = 'LM stockist $tag';
    final String catName = '$top margins';

    final bool ready = await log.step('MRG-PREP masters over HTTP', () async {
      for (final Json b in await list('/api/v1/branches?page_size=100')) {
        if (b['code'] == 'HO') branch = b;
      }
      for (final Json w in await list('/api/v1/warehouses?page_size=100')) {
        if (w['code'] == 'MAIN') warehouse = w;
      }
      for (final Json u in await list('/api/v1/uom-framework/uoms?page_size=100')) {
        if (u['code'] == 'PIECE') piece = '${u['id']}';
      }
      for (final Json l in await list('/api/v1/price-levels')) {
        levels['${l['code']}'] = l;
      }
      goodsType = (await admin.write('POST', '/api/v1/products/goods-types',
          <String, dynamic>{
            'code': 'GM$tag',
            'name': 'Margin type $tag',
            'track_batch': true,
            'retail_margin_percent': '25',
            'wholesale_margin_percent': '12.5',
          })) as Json;
      category = (await admin.write('POST', '/api/v1/products/categories',
          <String, dynamic>{
            'code': '$top-M',
            'name': catName,
            'goods_type_id': goodsType['id'],
          })) as Json;
      vendor = (await admin.write('POST', '/api/v1/vendors', <String, dynamic>{
        'code': 'MV$tag',
        'name': 'LM supplier $tag',
      })) as Json;
      retailer = await customer('MR$tag', nameR, 'RETAILER');
      stockist = await customer('MW$tag', nameW, 'STOCKIST');
      productA = await makeProduct('0M$tag-A', nameA);
      productC = await makeProduct('0M$tag-C', nameC);
      productD = await makeProduct('0M$tag-D', nameD);
      // MC: two lots, PTR 100 (margins blank) and PTR 112 (retail 40).
      await receiveOverHttp(await approvedPo(productC, 2), <Json>[
        <String, dynamic>{'batch_number': 'C1$tag'},
        <String, dynamic>{'batch_number': 'C2$tag', 'retail_margin_percent': '40'},
      ]);
      // MD: one lot at 80, then 2 sold at 100 and billed in draft.
      await receiveOverHttp(await approvedPo(productD, 1), <Json>[
        <String, dynamic>{'batch_number': 'D1$tag'},
      ]);
      final Json order = (await admin.write('POST', '/api/v1/sales-orders',
          <String, dynamic>{
            'customer_id': retailer['id'],
            'branch_id': branch['id'],
            'warehouse_id': warehouse['id'],
            'order_date': _today(),
            'lines': <Json>[
              <String, dynamic>{
                'line_number': 1,
                'product_id': productD['id'],
                'quantity': '2',
                'unit_price': '100',
              },
            ],
          })) as Json;
      await apiAct(admin, 'sales-orders', '${order['id']}', 'approve');
      final Json so = await admin.one('sales-orders', '${order['id']}');
      final Json note = (await admin.write('POST', '/api/v1/delivery-notes',
          <String, dynamic>{
            'sales_order_id': so['id'],
            'delivery_date': _today(),
            'lines': <Json>[
              <String, dynamic>{
                'sales_order_line_id':
                    ((so['lines'] as List<dynamic>).first as Json)['id'],
                'line_number': 1,
                'current_delivery_quantity': '2',
              },
            ],
          })) as Json;
      await apiAct(admin, 'delivery-notes', '${note['id']}', 'approve');
      await apiAct(admin, 'delivery-notes', '${note['id']}', 'dispatch');
      final Json dn = await admin.one('delivery-notes', '${note['id']}');
      final Json bill = (await admin.write('POST', '/api/v1/sales-invoices',
          <String, dynamic>{
            'customer_id': retailer['id'],
            'branch_id': branch['id'],
            'invoice_date': _today(),
            'source_documents': <Json>[
              <String, dynamic>{
                'source_document_type': 'DELIVERY_NOTE',
                'source_document_id': dn['id'],
              },
            ],
            'lines': <Json>[
              <String, dynamic>{
                'source_document_type': 'DELIVERY_NOTE',
                'source_document_id': dn['id'],
                'source_document_line_id':
                    ((dn['lines'] as List<dynamic>).first as Json)['id'],
                'line_number': 1,
                'current_invoice_quantity': '2',
              },
            ],
          })) as Json;
      draftBill = await admin.one('sales-invoices', '${bill['id']}');
      final Json second = (await admin.write('POST', '/api/v1/sales-orders',
          <String, dynamic>{
            'customer_id': retailer['id'],
            'branch_id': branch['id'],
            'warehouse_id': warehouse['id'],
            'order_date': _today(),
            'lines': <Json>[
              <String, dynamic>{
                'line_number': 1,
                'product_id': productD['id'],
                'quantity': '2',
                'unit_price': '100',
              },
            ],
          })) as Json;
      draftOrder = await admin.one('sales-orders', '${second['id']}');
      poA = await approvedPo(productA, 4);
      poRefused = await approvedPo(productA, 1);
      log.saw = 'type GM$tag (25/12.5), category "$catName", products '
          '${productA['code']}, ${productC['code']} (lots C1 PTR 100, C2 PTR '
          '112), ${productD['code']} (lot D1 at 80); customers $nameR '
          '(RETAILER), $nameW (STOCKIST); PO ${docNumber(poA)} (4 x 10 at '
          '80), PO ${docNumber(poRefused)}; draft bill '
          '${docNumber(draftBill)}, draft order ${docNumber(draftOrder)}; '
          'levels ${levels.keys.toList()}';
    });

    await startAndSignIn(tester);
    collectAppErrors();
    // Where an overflow is, which the shared collector does not say.
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
        print('FLOW: INFO [mrg-$itHandle] overflow at :: $where');
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

    /// The texts under the widget keyed [key], in order.
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

    /// The value beside the label [label] in a row (a side pair, a detail).
    String besideLabel(String label) {
      final Finder l = find.text(label);
      if (l.evaluate().isEmpty) return '(absent)';
      final Finder row = find.ancestor(of: l.last, matching: find.byType(Row));
      if (row.evaluate().isEmpty) return '(no row)';
      final List<String> out = <String>[
        for (final Text t in tester.widgetList<Text>(
            find.descendant(of: row.first, matching: find.byType(Text))))
          if ((t.data ?? '').trim().isNotEmpty && t.data != label) t.data!,
        for (final SelectableText t in tester.widgetList<SelectableText>(
            find.descendant(of: row.first, matching: find.byType(SelectableText))))
          t.data ?? '',
      ];
      return out.isEmpty ? '' : out.last;
    }

    /// What the boxes under the widget keyed [prefix]... hold.
    String boxesStarting(String prefix) {
      final List<String> keys = keysStarting(prefix);
      return keys.isEmpty ? '(absent)' : boxesIn(tester, keys.first);
    }

    List<String> boxList(String key) => <String>[
          for (final EditableText e in tester.widgetList<EditableText>(find
              .descendant(
                  of: find.byKey(ValueKey<String>(key)),
                  matching: find.byType(EditableText))))
            e.controller.text,
        ];

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
      if (inner.evaluate().isNotEmpty &&
          tester.widget<EditableText>(inner.first).controller.text != text) {
        await tester.tap(inner.first);
        await pumpFor(tester, const Duration(milliseconds: 400));
        await tester.enterText(inner.first, text);
        await pumpFor(tester, const Duration(milliseconds: 400));
      }
    }

    /// Open the record [number] from the list on screen: Edit where offered,
    /// else Open or View.
    Future<String> openFromList(String number) async {
      await refreshList(tester);
      await searchList(tester, number);
      await pickRow(tester, number);
      for (final String b in const <String>['Edit', 'Open', 'View']) {
        if (buttonState(tester, b) == 'enabled') {
          await tapButton(tester, b);
          await pumpFor(tester, const Duration(seconds: 3));
          return b;
        }
      }
      throw StateError('no Edit, Open or View for $number');
    }

    // =======================================================================
    // TC-LOT-015: the product form
    // =======================================================================
    if (isAdmin && _runs('product')) {
      Future<void> newProduct() async {
        await openArea(tester, 'masters', 'masters/products');
        await tapNew(tester);
        await pumpFor(tester, const Duration(seconds: 3));
        await pickDropdown(tester, 'Category', catName);
        await pumpFor(tester, const Duration(seconds: 1));
        await tapKey(tester, 'product-brand');
        await pumpFor(tester, const Duration(milliseconds: 700));
        await tester.tap(find.textContaining(brandName).last);
        await pumpFor(tester, const Duration(milliseconds: 700));
      }

      String box(String label) {
        final Finder f = fieldLabelled(label);
        return f.evaluate().isEmpty
            ? '(absent)'
            : tester.widget<TextField>(f.first).controller?.text ?? '';
      }

      await log.step('TC-LOT-015 step 1 a product in the type\'s category '
          'fills its margins', () async {
        final int errs = appErrors.length;
        await newProduct();
        final String r = box('Retail margin %');
        final String w = box('Wholesale margin %');
        log.saw = 'boxes retail "$r", wholesale "$w"; server type '
            '${goodsType['retail_margin_percent']} / '
            '${goodsType['wholesale_margin_percent']}';
        if (!_same(_first(r), _n(goodsType['retail_margin_percent'])) ||
            !_same(_first(w), _n(goodsType['wholesale_margin_percent']))) {
          throw StateError('the boxes do not hold the type\'s margins');
        }
        if (appErrors.length > errs) throw StateError(errorsSince(errs));
      });

      final String typedName = 'LM typed $tag';
      await log.step('TC-LOT-015 step 2 retail 30 typed, wholesale from the '
          'type, saved', () async {
        final int errs = appErrors.length;
        if (box('Retail margin %') == '(absent)') await newProduct();
        await typeLabelled(tester, 'Product name *', typedName);
        await typeLabelled(tester, 'Retail margin %', '30');
        final String said = await pressAndRead(
            tester, () => tapKey(tester, 'product-save'),
            seconds: 6);
        Json? row;
        for (final Json p in await list(
            '/api/v1/products?search=${Uri.encodeQueryComponent(typedName)}')) {
          if (p['name'] == typedName) row = p;
        }
        log.saw = 'said "$said"; server '
            '${row == null ? 'none' : 'retail ${row['retail_margin_percent']}, wholesale ${row['wholesale_margin_percent']}, category ${row['category_id'] == category['id']}'}';
        if (row == null) throw StateError('not saved: ${log.saw}');
        if (!_same(_n(row['retail_margin_percent']), 30) ||
            !_same(_n(row['wholesale_margin_percent']), 12.5)) {
          throw StateError('saved with the wrong margins');
        }
        if (appErrors.length > errs) throw StateError(errorsSince(errs));
      });
      await away();

      await log.step('TC-LOT-015 step 4 a margin of -1 is refused naming the '
          'field', () async {
        final int errs = appErrors.length;
        final int before = await admin.total('/api/v1/products?search=LM%20bad%20$tag');
        await newProduct();
        await typeLabelled(tester, 'Product name *', 'LM bad $tag');
        await typeLabelled(tester, 'Retail margin %', '-1');
        final String said = await pressAndRead(
            tester, () => tapKey(tester, 'product-save'),
            seconds: 6);
        final int after = await admin.total('/api/v1/products?search=LM%20bad%20$tag');
        final bool open =
            find.byKey(const ValueKey<String>('product-save')).evaluate().isNotEmpty;
        log.saw = 'said "$said"; editor open=$open; products named so '
            '$before -> $after';
        if (after != before) throw StateError('saved with -1');
        if (!open) throw StateError('the editor closed');
        if (!said.toLowerCase().contains('margin')) {
          throw StateError('the refusal does not name the margin: ${log.saw}');
        }
        if (appErrors.length > errs) throw StateError(errorsSince(errs));
      });
      await away();
    }

    // =======================================================================
    // TC-LOT-016 / 017 / 018: the goods receipt
    // =======================================================================
    final String po = '${poA['id']}';
    // (batch, mrp, typed ptr, typed retail margin), in typing order PTR
    // then margin, the boxes' own order left to right.
    final List<(String, String, String, String)> plan =
        <(String, String, String, String)>[
      ('A0$tag', '', '', ''),
      ('A1$tag', '130', '', '40'),
      ('A2$tag', '', '104', ''),
      ('A3$tag', '', '104', '40'),
    ];
    // Expected (ptr, pts, retail margin, wholesale margin) per line.
    const List<(double, double, double, double)> want =
        <(double, double, double, double)>[
      (100, 90, 25, 12.5),
      (112, 90, 40, 12.5),
      (104, 90, 30, 12.5),
      (104, 90, 30, 12.5),
    ];
    bool received = false;
    if (isAdmin && _runs('receipt')) {
      Json? gr;
      final List<String> afterTyping = <String>[];
      await log.step('TC-LOT-016/017/018 a receipt of four lines saved on the '
          'screen', () async {
        final int errs = appErrors.length;
        await away();
        await openMenu(tester, 'buy', 'goodsReceipts/receipts');
        await tapNew(tester);
        await chooseIn(tester, 'goods-receipt-order', docNumber(poA));
        await pumpFor(tester, const Duration(seconds: 2));
        for (int i = 0; i < plan.length; i++) {
          final (String batch, String mrp, String ptr, String margin) = plan[i];
          await typeKeyed('goods-receipt-accepted-$po-$i', '10');
          await typeKeyed('goods-receipt-batch-$po-$i', batch);
          await tester.tap(find.byKey(ValueKey<String>('goods-receipt-line-$i')));
          await pumpFor(tester, const Duration(milliseconds: 700));
          if (mrp.isNotEmpty) await typeKeyed('goods-receipt-mrp-$po-$i', mrp);
          if (ptr.isNotEmpty) await typeKeyed('goods-receipt-ptr-$po-$i', ptr);
          if (margin.isNotEmpty) {
            await typeKeyed('goods-receipt-retail-margin-$po-$i', margin);
          }
          afterTyping.add('line ${i + 1}: PTR box '
              '"${boxesStarting('goods-receipt-ptr-$po-$i')}", margin box '
              '"${boxesStarting('goods-receipt-retail-margin-$po-$i')}"');
        }
        final String said = await pressAndRead(
            tester, () => tapKey(tester, 'goods-receipt-save'),
            seconds: 8);
        for (final Json r in await list('/api/v1/goods-receipts?page_size=100')) {
          if (r['purchase_order_id'] == poA['id']) gr = r;
        }
        if (gr != null) gr = await admin.one('goods-receipts', '${gr!['id']}');
        final bool open = find
            .byKey(const ValueKey<String>('goods-receipt-save-complete'))
            .evaluate()
            .isNotEmpty;
        log.saw = '${afterTyping.join('; ')}; said "$said"; editor open=$open; '
            '${gr == null ? 'no receipt' : '${docNumber(gr!)} ${gr!['status']}'}';
        if (gr == null) throw StateError('no receipt saved');
        if (!open) {
          throw StateError('the editor closed although line 2 bills above '
              'the MRP with tax');
        }
        if (appErrors.length > errs) throw StateError(errorsSince(errs));
      });

      Json? lineOf(int i) {
        for (final dynamic l in (gr?['lines'] as List<dynamic>?) ?? <dynamic>[]) {
          if (((l as Json)['line_number'] as num?)?.toInt() == i + 1) return l;
        }
        return null;
      }

      if (gr != null) {
        for (int i = 0; i < plan.length; i++) {
          final String what = <String>[
            'TC-LOT-016 step 1 margins blank: PTR 100.00, PTS 90.00',
            'TC-LOT-016 step 2 retail 40 with MRP 130: PTR 112.00, PTS 90.00',
            'TC-LOT-017 step 1 PTR 104.00 typed: margin 30.00 worked back',
            'TC-LOT-017 step 2 PTR 104.00 and margin 40 typed: the price stands',
          ][i];
          await log.step('$what (screen = server)', () async {
            final int errs = appErrors.length;
            await tester.tap(find.byKey(ValueKey<String>('goods-receipt-line-$i')));
            await pumpFor(tester, const Duration(milliseconds: 800));
            final String sPtr = textsUnder('goods-receipt-saved-ptr-$i').lastOrNull ?? '(absent)';
            final String sPts = textsUnder('goods-receipt-saved-pts-$i').lastOrNull ?? '(absent)';
            final String sRm = besideLabel('Retail margin as saved');
            final String sWm = besideLabel('Wholesale margin as saved');
            final Json? l = lineOf(i);
            final (double ptr, double pts, double rm, double wm) = want[i];
            log.saw = 'screen PTR "$sPtr", PTS "$sPts", margins "$sRm" / '
                '"$sWm"; server ${l == null ? 'no line' : 'PTR ${l['ptr']}, PTS ${l['pts']}, margins ${l['retail_margin_percent']} / ${l['wholesale_margin_percent']}'}';
            if (l == null) throw StateError('no server line ${i + 1}');
            final List<String> faults = <String>[
              if (!_same(_first(sPtr), _n(l['ptr']))) 'PTR on screen is not the server\'s',
              if (!_same(_first(sPts), _n(l['pts']))) 'PTS on screen is not the server\'s',
              if (!_same(_first(sRm), _n(l['retail_margin_percent'])))
                'retail margin on screen is not the server\'s',
              if (!_same(_first(sWm), _n(l['wholesale_margin_percent'])))
                'wholesale margin on screen is not the server\'s',
              if (!_same(_n(l['ptr']), ptr)) 'server PTR ${l['ptr']}, expected $ptr',
              if (!_same(_n(l['pts']), pts)) 'server PTS ${l['pts']}, expected $pts',
              if (!_same(_n(l['retail_margin_percent']), rm))
                'server retail margin ${l['retail_margin_percent']}, expected $rm',
              if (!_same(_n(l['wholesale_margin_percent']), wm))
                'server wholesale margin ${l['wholesale_margin_percent']}, expected $wm',
            ];
            if (faults.isNotEmpty) throw StateError(faults.join('; '));
            if (appErrors.length > errs) throw StateError(errorsSince(errs));
          });
        }

        await log.step('TC-LOT-018 step 1 the MRP warning is shown as the '
            'server words it', () async {
          final int errs = appErrors.length;
          final String banner =
              textsUnder('goods-receipt-mrp-warnings').join(' | ');
          await tester.tap(find.byKey(const ValueKey<String>('goods-receipt-line-1')));
          await pumpFor(tester, const Duration(milliseconds: 600));
          final String inPlace =
              textsUnder('goods-receipt-mrp-warning-1').join(' | ');
          final String server = '${lineOf(1)?['mrp_warning'] ?? ''}';
          final List<String> others = <String>[
            for (int i = 0; i < plan.length; i++)
              if (i != 1 && '${lineOf(i)?['mrp_warning'] ?? ''}'.isNotEmpty)
                'line ${i + 1}',
          ];
          log.saw = 'banner "$banner"; beside the line "$inPlace"; server '
              '"$server"; other lines warned: $others';
          final List<String> faults = <String>[
            if (server.isEmpty) 'the server sent no warning',
            if (!server.contains('132.16') || !server.contains('110.16'))
              'the server warning does not name 132.16 and 110.16',
            if (!banner.contains(server)) 'the banner does not carry it',
            if (inPlace != server) 'the line does not carry it',
            if (others.isNotEmpty) 'warned on $others too',
          ];
          if (faults.isNotEmpty) throw StateError(faults.join('; '));
          if (appErrors.length > errs) throw StateError(errorsSince(errs));
        });

        await log.step('TC-LOT-016 step 3 completed: each lot holds its '
            'line\'s prices and margins', () async {
          final int errs = appErrors.length;
          final String said = await pressAndRead(
              tester, () => tapKey(tester, 'goods-receipt-save-complete'),
              seconds: 8);
          if (find.byType(Dialog).evaluate().isNotEmpty) {
            await confirmIfAsked(tester);
          }
          await pumpFor(tester, const Duration(seconds: 2));
          final Json now = await admin.one('goods-receipts', '${gr!['id']}');
          final List<String> lots = <String>[];
          final List<String> faults = <String>[];
          for (int i = 0; i < plan.length; i++) {
            final Json? b = await batchNamed(productA, plan[i].$1);
            final (double ptr, double pts, double rm, double wm) = want[i];
            lots.add(b == null
                ? '${plan[i].$1} none'
                : '${plan[i].$1} ${b['ptr']}/${b['pts']} ${b['retail_margin_percent']}/${b['wholesale_margin_percent']}');
            if (b == null) {
              faults.add('no lot ${plan[i].$1}');
            } else if (!_same(_n(b['ptr']), ptr) ||
                !_same(_n(b['pts']), pts) ||
                !_same(_n(b['retail_margin_percent']), rm) ||
                !_same(_n(b['wholesale_margin_percent']), wm)) {
              faults.add('${plan[i].$1} is not $ptr/$pts $rm/$wm');
            }
          }
          log.saw = 'said "$said"; receipt ${now['status']}; lots $lots';
          if ('${now['status']}'.toUpperCase() != 'COMPLETED') {
            faults.add('receipt is ${now['status']}');
          } else {
            received = true;
          }
          if (faults.isNotEmpty) throw StateError(faults.join('; '));
          if (appErrors.length > errs) throw StateError(errorsSince(errs));
        });
      }
      await away();

      // -- Two refusals on a receipt of one line ----------------------------
      final String po2 = '${poRefused['id']}';
      bool opened = false;
      await log.step('TC-LOT-018 step 3 PTS above PTR is refused naming both '
          'prices', () async {
        final int errs = appErrors.length;
        await openMenu(tester, 'buy', 'goodsReceipts/receipts');
        await tapNew(tester);
        await chooseIn(tester, 'goods-receipt-order', docNumber(poRefused));
        await pumpFor(tester, const Duration(seconds: 2));
        opened = true;
        await typeKeyed('goods-receipt-accepted-$po2-0', '10');
        await typeKeyed('goods-receipt-batch-$po2-0', 'AR$tag');
        await tester.tap(find.byKey(const ValueKey<String>('goods-receipt-line-0')));
        await pumpFor(tester, const Duration(milliseconds: 700));
        await typeKeyed('goods-receipt-retail-margin-$po2-0', '10');
        await typeKeyed('goods-receipt-wholesale-margin-$po2-0', '40');
        final String said = await pressAndRead(
            tester, () => tapKey(tester, 'goods-receipt-save'),
            seconds: 6);
        final int saved = (await list('/api/v1/goods-receipts?page_size=100'))
            .where((Json r) => r['purchase_order_id'] == poRefused['id'])
            .length;
        log.saw = 'said "$said"; receipts for the order on the server $saved';
        if (saved != 0) throw StateError('a receipt was saved');
        if (!said.contains('112.00') || !said.contains('88.00')) {
          throw StateError('the refusal does not name PTS 112.00 and PTR 88.00');
        }
        if (appErrors.length > errs) throw StateError(errorsSince(errs));
      });
      if (opened) {
        await log.step('TC-LOT-018 step 2 a price above the MRP before tax is '
            'refused', () async {
          final int errs = appErrors.length;
          await typeKeyed('goods-receipt-wholesale-margin-$po2-0', '');
          await typeKeyed('goods-receipt-mrp-$po2-0', '100');
          await typeKeyed('goods-receipt-retail-margin-$po2-0', '40');
          final String said = await pressAndRead(
              tester, () => tapKey(tester, 'goods-receipt-save'),
              seconds: 6);
          final int saved = (await list('/api/v1/goods-receipts?page_size=100'))
              .where((Json r) => r['purchase_order_id'] == poRefused['id'])
              .length;
          log.saw = 'said "$said"; receipts for the order on the server $saved';
          if (saved != 0) throw StateError('a receipt was saved');
          if (!said.toLowerCase().contains('mrp')) {
            throw StateError('the refusal does not name the MRP');
          }
          if (appErrors.length > errs) throw StateError(errorsSince(errs));
        });
      }
      await away();
    }
    if (!received) {
      // The viewer receives nothing: the admin's lots come over HTTP.
      try {
        await receiveOverHttp(poA, <Json>[
          for (final (String batch, String mrp, String ptr, String margin) in plan)
            <String, dynamic>{
              'batch_number': batch,
              if (mrp.isNotEmpty) 'mrp': mrp,
              if (ptr.isNotEmpty) 'ptr': ptr,
              if (margin.isNotEmpty) 'retail_margin_percent': margin,
            },
        ]);
        log.info('MRG-PREP', 'the four MA lines received over HTTP');
      } catch (error) {
        log.info('MRG-PREP', 'could not receive MA over HTTP: $error');
      }
    }

    // =======================================================================
    // TC-LOT-019: the lot page
    // =======================================================================
    if (_runs('lot')) {
      final String lotNo = 'A0$tag';
      Future<void> openLot() async {
        await openArea(tester, 'stock', 'inventory/batches');
        await searchList(tester, lotNo);
        await pickRow(tester, lotNo);
        await tapButton(tester, 'Open');
        await pumpFor(tester, const Duration(seconds: 1));
      }

      String retailLabel() => find.text('Retail price (PTR)').evaluate().isNotEmpty
          ? 'Retail price (PTR)'
          : 'Retail price';
      String wholesaleLabel() =>
          find.text('Wholesale price (PTS)').evaluate().isNotEmpty
              ? 'Wholesale price (PTS)'
              : 'Wholesale price';

      Future<String> shownLot() async {
        await openLot();
        return 'retail "${besideLabel(retailLabel())}" margin '
            '"${besideLabel('Retail margin %')}", wholesale '
            '"${besideLabel(wholesaleLabel())}" margin '
            '"${besideLabel('Wholesale margin %')}"';
      }

      await log.step('TC-LOT-019 step 1 the lot page shows both prices and '
          'margins', () async {
        final int errs = appErrors.length;
        final Json? b = await batchNamed(productA, lotNo);
        final String shown = await shownLot();
        log.saw = '$shown; server ${b == null ? 'none' : '${b['ptr']} / ${b['retail_margin_percent']}, ${b['pts']} / ${b['wholesale_margin_percent']}'}';
        if (b == null) throw StateError('no lot $lotNo');
        final List<String> faults = <String>[
          if (!_same(_first(besideLabel(retailLabel())), _n(b['ptr']))) 'retail price',
          if (!_same(_first(besideLabel('Retail margin %')),
              _n(b['retail_margin_percent'])))
            'retail margin',
          if (!_same(_first(besideLabel(wholesaleLabel())), _n(b['pts']))) 'wholesale price',
          if (!_same(_first(besideLabel('Wholesale margin %')),
              _n(b['wholesale_margin_percent'])))
            'wholesale margin',
        ];
        if (faults.isNotEmpty) {
          throw StateError('not as the server: ${faults.join(', ')}');
        }
        if (appErrors.length > errs) throw StateError(errorsSince(errs));
      });

      if (isAdmin) {
        bool editing = false;
        await log.step('TC-LOT-019 step 2 retail price 108.00 saved: margin '
            '35.00, wholesale unchanged', () async {
          final int errs = appErrors.length;
          if (buttonState(tester, 'Edit') == 'absent') await openLot();
          await tapButton(tester, 'Edit');
          await pumpUntil(tester, find.byKey(const ValueKey<String>('batch-form-ptr')),
              waitingFor: 'the lot form');
          editing = true;
          await typeKeyed('batch-form-ptr', '108');
          final String said = await pressAndRead(
              tester, () => tapButton(tester, 'Save'),
              seconds: 5);
          final Json? b = await batchNamed(productA, lotNo);
          final String shown = await shownLot();
          log.saw = 'said "$said"; then $shown; server ${b?['ptr']} / '
              '${b?['retail_margin_percent']}, ${b?['pts']} / '
              '${b?['wholesale_margin_percent']}';
          final List<String> faults = <String>[
            if (!_same(_n(b?['ptr']), 108)) 'server PTR ${b?['ptr']}',
            if (!_same(_n(b?['retail_margin_percent']), 35))
              'server margin ${b?['retail_margin_percent']}',
            if (!_same(_n(b?['pts']), 90)) 'server PTS ${b?['pts']}',
            if (!_same(_first(besideLabel(retailLabel())), 108)) 'screen PTR',
            if (!_same(_first(besideLabel('Retail margin %')), 35)) 'screen margin',
          ];
          if (faults.isNotEmpty) throw StateError(faults.join('; '));
          if (appErrors.length > errs) throw StateError(errorsSince(errs));
        });
        if (editing) {
          await log.step('TC-LOT-019 step 3 retail price 85.00 refused below '
              'wholesale 90.00', () async {
            final int errs = appErrors.length;
            if (buttonState(tester, 'Edit') == 'absent') await openLot();
            await tapButton(tester, 'Edit');
            await pumpUntil(tester, find.byKey(const ValueKey<String>('batch-form-ptr')),
                waitingFor: 'the lot form');
            await typeKeyed('batch-form-ptr', '85');
            final String said = await pressAndRead(
                tester, () => tapButton(tester, 'Save'),
                seconds: 5);
            final bool open = find
                .byKey(const ValueKey<String>('batch-form-ptr'))
                .evaluate()
                .isNotEmpty;
            final Json? b = await batchNamed(productA, lotNo);
            log.saw = 'said "$said"; form open=$open; server PTR ${b?['ptr']}';
            if (!_same(_n(b?['ptr']), 108)) throw StateError('the server took it');
            if (!open) throw StateError('the form closed');
            if (!said.contains('90')) {
              throw StateError('the refusal does not name 90.00');
            }
            if (appErrors.length > errs) throw StateError(errorsSince(errs));
          });
        }
      } else {
        await log.step('TC-LOT-019 step 4 the viewer: no Edit, and the server '
            'refuses the save', () async {
          final int errs = appErrors.length;
          if (find.text('Trace').evaluate().isEmpty) await openLot();
          final String edit = buttonState(tester, 'Edit');
          final Json? b = await batchNamed(productA, lotNo);
          final ({int status, String text}) put = await me.attempt('PUT',
              '/api/v1/batch-serial/batches/${b?['id']}',
              <String, dynamic>{'ptr': '108.00'});
          log.saw = 'Edit $edit; PUT as the viewer ${put.status}';
          if (edit == 'enabled') throw StateError('Edit offered to the viewer');
          if (put.status != 403) throw StateError('server answered ${put.status}');
          if (appErrors.length > errs) throw StateError(errorsSince(errs));
        });
      }
      await away();
    }

    // =======================================================================
    // TC-LOT-020: the Price level on a sales order
    // =======================================================================
    Future<({double price, String level})> serverPrice(Json who, Json? level) async {
      final Json got = (await admin.get('/api/v1/price-levels/unit-prices'
          '?product_ids=${productC['id']}&on=${_today()}&customer_id=${who['id']}'
          '&branch_id=${branch['id']}&warehouse_id=${warehouse['id']}'
          '${level == null ? '' : '&price_level_id=${level['id']}'}')) as Json;
      return (
        price: _n(((got['prices'] as List<dynamic>).first as Json)['unit_price']),
        level: '${got['price_level_id']}',
      );
    }

    String levelName(String id) {
      for (final Json l in levels.values) {
        if ('${l['id']}' == id) return '${l['name']}';
      }
      return id;
    }

    if (isAdmin && _runs('order')) {
      Future<String> newOrderFor(String name) async {
        await away();
        await openMenu(tester, 'sell', 'salesOrders');
        await tapNew(tester);
        await pumpUntil(tester, find.byKey(const ValueKey<String>('sales-order-save')));
        await chooseIn(tester, 'sales-order-customer', name);
        await chooseIn(tester, 'sales-order-line-product-0', nameC);
        await pumpFor(tester, const Duration(seconds: 3));
        final Finder helper = find.byKey(const ValueKey<String>('price-level-helper'));
        return helper.evaluate().isEmpty
            ? '(no helper)'
            : tester.widget<Text>(helper.first).data ?? '';
      }

      bool hasPrice(double v) => boxList('sales-order-line-0')
          .skip(1)
          .any((String t) => _same(_first(t), v) && t.contains('.'));

      bool started = false;
      await log.step('TC-LOT-020 step 1 a retailer: Retail, priced at the '
          'first lot, 100.00', () async {
        final int errs = appErrors.length;
        final String helper = await newOrderFor(nameR);
        started = true;
        final ({double price, String level}) s = await serverPrice(retailer, null);
        log.saw = 'helper "$helper"; line boxes ${boxList('sales-order-line-0')}; '
            'server ${s.price} at ${levelName(s.level)}';
        if (!_same(s.price, 100) || s.level != '${levels['RETAIL']?['id']}') {
          throw StateError('the server is not Retail 100.00');
        }
        if (!helper.contains(levelName(s.level))) {
          throw StateError('the helper does not name ${levelName(s.level)}');
        }
        if (!hasPrice(s.price)) throw StateError('the line is not at ${s.price}');
        if (appErrors.length > errs) throw StateError(errorsSince(errs));
      });
      if (started) {
        await log.step('TC-LOT-020 step 2 switched to Wholesale: 90.00',
            () async {
          final int errs = appErrors.length;
          final Json whole = levels['WHOLESALE']!;
          await tapKey(tester, 'sales-order-price-level');
          await pumpFor(tester, const Duration(milliseconds: 700));
          await tester.tap(find.text('${whole['name']}').last);
          await pumpFor(tester, const Duration(seconds: 3));
          final ({double price, String level}) s = await serverPrice(retailer, whole);
          log.saw = 'line boxes ${boxList('sales-order-line-0')}; server '
              '${s.price} at ${levelName(s.level)}';
          if (!_same(s.price, 90)) throw StateError('the server is not 90.00 (${s.price})');
          if (!hasPrice(s.price)) throw StateError('the line is not at ${s.price}');
          if (appErrors.length > errs) throw StateError(errorsSince(errs));
        });
      }
      await log.step('TC-LOT-020 step 3 a stockist: Wholesale, 90.00', () async {
        final int errs = appErrors.length;
        final String helper = await newOrderFor(nameW);
        final ({double price, String level}) s = await serverPrice(stockist, null);
        log.saw = 'helper "$helper"; line boxes ${boxList('sales-order-line-0')}; '
            'server ${s.price} at ${levelName(s.level)}';
        if (!_same(s.price, 90) || s.level != '${levels['WHOLESALE']?['id']}') {
          throw StateError('the server is not Wholesale 90.00');
        }
        if (!helper.contains(levelName(s.level))) {
          throw StateError('the helper does not name ${levelName(s.level)}');
        }
        if (!hasPrice(s.price)) throw StateError('the line is not at ${s.price}');
        if (appErrors.length > errs) throw StateError(errorsSince(errs));
      });
      await log.step('TC-LOT-020 step 4 switched to Retail: 100.00', () async {
        final int errs = appErrors.length;
        final Json retail = levels['RETAIL']!;
        await tapKey(tester, 'sales-order-price-level');
        await pumpFor(tester, const Duration(milliseconds: 700));
        await tester.tap(find.text('${retail['name']}').last);
        await pumpFor(tester, const Duration(seconds: 3));
        final ({double price, String level}) s = await serverPrice(stockist, retail);
        log.saw = 'line boxes ${boxList('sales-order-line-0')}; server '
            '${s.price} at ${levelName(s.level)}';
        if (!_same(s.price, 100)) throw StateError('the server is not 100.00');
        if (!hasPrice(s.price)) throw StateError('the line is not at ${s.price}');
        if (appErrors.length > errs) throw StateError(errorsSince(errs));
      });
      await away();
    }

    // =======================================================================
    // TC-LOT-021: cost and margin on the line
    // =======================================================================
    if (_runs('bill')) {
      await log.step(
          isAdmin
              ? 'TC-LOT-021 step 1 the draft order: cost 160.00 est., margin '
                  '40.00, 25 %'
              : 'TC-LOT-021 step 3 the order shows the viewer no Cost or Margin',
          () async {
        final int errs = appErrors.length;
        await away();
        await openMenu(tester, 'sell', 'salesOrders');
        final String how = await openFromList(docNumber(draftOrder));
        final Json server = await me.one('sales-orders', '${draftOrder['id']}');
        final Json l = (server['lines'] as List<dynamic>).first as Json;
        final String cost = textsUnder('sales-order-line-cost-0').join(' ');
        final String margin = textsUnder('sales-order-line-margin-0').join(' ');
        final bool heads = find.text('Cost').evaluate().isNotEmpty ||
            find.text('Margin').evaluate().isNotEmpty;
        final String strip = textOnScreen(tester)
            .where((String t) => t.startsWith('Cost '))
            .join(' | ');
        log.saw = 'opened with $how; cost cell "$cost", margin cell "$margin", '
            'strip "$strip", Cost/Margin header $heads; server cost '
            '${l['cost_amount']} (est. ${l['cost_is_estimate']}), margin '
            '${l['margin_amount']}, ${l['margin_percent']} %';
        final List<String> faults = isAdmin
            ? <String>[
                if (!_same(_n(l['cost_amount']), 160)) 'server cost ${l['cost_amount']}',
                if (!_same(_n(l['margin_amount']), 40)) 'server margin ${l['margin_amount']}',
                if (!_same(_n(l['margin_percent']), 25)) 'server % ${l['margin_percent']}',
                if (!_same(_first(cost), _n(l['cost_amount']))) 'cost cell',
                if (l['cost_is_estimate'] == true && !cost.contains('est.'))
                  'no est. on an estimate',
                if (!_same(_first(margin), _n(l['margin_amount']))) 'margin cell',
                if (!margin.contains('25.0')) 'no 25 % in the margin cell',
                if (!strip.contains('160.00')) 'the totals strip',
              ]
            : <String>[
                if (l['cost_amount'] != null || l['margin_amount'] != null)
                  'the server sent the viewer a cost',
                if (keysStarting('sales-order-line-cost-').isNotEmpty ||
                    keysStarting('sales-order-line-margin-').isNotEmpty)
                  'cost cells shown',
                if (heads) 'a Cost or Margin header shown',
                if (strip.isNotEmpty) 'a cost strip shown',
              ];
        if (faults.isNotEmpty) throw StateError(faults.join('; '));
        if (appErrors.length > errs) throw StateError(errorsSince(errs));
      });

      if (isAdmin) {
        await log.step('TC-LOT-021 step 2 the quantity changed unsaved: the '
            'figures say as last saved', () async {
          final int errs = appErrors.length;
          if (keysStarting('sales-order-line-0').isEmpty) {
            throw StateError('the order editor is not open');
          }
          final List<String> boxes = boxList('sales-order-line-0');
          await typeIn(tester, 'sales-order-line-0', 1, '3');
          await pumpFor(tester, const Duration(seconds: 3));
          final String strip = textOnScreen(tester)
              .where((String t) => t.startsWith('Cost '))
              .join(' | ');
          final String cost = textsUnder('sales-order-line-cost-0').join(' ');
          log.saw = 'boxes before $boxes, after ${boxList('sales-order-line-0')}; '
              'cost cell "$cost"; strip "$strip"';
          if (!strip.contains('as last saved')) {
            throw StateError('the strip does not say as last saved');
          }
          if (appErrors.length > errs) throw StateError(errorsSince(errs));
        });
      }
      await away();

      await log.step(
          isAdmin
              ? 'TC-LOT-021 step 1 the draft bill: cost 160.00, margin 40.00 on '
                  '200.00, 25 %'
              : 'TC-LOT-021 step 3 the bill shows the viewer no Cost or Margin',
          () async {
        final int errs = appErrors.length;
        try {
          await openMenu(tester, 'sell', 'salesInvoices/sales-invoices');
        } on TestFailure {
          // A view still closing can swallow the first tap on the menu.
          await away();
          await pumpFor(tester, const Duration(seconds: 1));
          await openMenu(tester, 'sell', 'salesInvoices/sales-invoices');
        }
        final String how = await openFromList(docNumber(draftBill));
        final Json server = await me.one('sales-invoices', '${draftBill['id']}');
        final Json l = (server['lines'] as List<dynamic>).first as Json;
        final String cost = textsUnder('sales-invoice-line-cost-0').join(' ');
        final String margin = textsUnder('sales-invoice-line-margin-0').join(' ');
        final bool heads = find.text('Cost').evaluate().isNotEmpty ||
            find.text('Margin').evaluate().isNotEmpty;
        final String strip = textOnScreen(tester)
            .where((String t) => t.startsWith('Cost '))
            .join(' | ');
        log.saw = 'opened with $how; cost cell "$cost", margin cell "$margin", '
            'strip "$strip", header $heads; server gross ${l['gross_amount']}, '
            'cost ${l['cost_amount']} (est. ${l['cost_is_estimate']}), margin '
            '${l['margin_amount']}, ${l['margin_percent']} %, totals '
            '${server['cost_total']} / ${server['margin_total']}';
        final List<String> faults = isAdmin
            ? <String>[
                if (!_same(_n(l['gross_amount']), 200)) 'server gross ${l['gross_amount']}',
                if (!_same(_n(l['cost_amount']), 160)) 'server cost ${l['cost_amount']}',
                if (!_same(_n(l['margin_amount']), 40)) 'server margin ${l['margin_amount']}',
                if (!_same(_first(cost), _n(l['cost_amount']))) 'cost cell',
                if ((l['cost_is_estimate'] == true) != cost.contains('est.'))
                  'est. shown=${cost.contains('est.')}, sent ${l['cost_is_estimate']}',
                if (!_same(_first(margin), _n(l['margin_amount']))) 'margin cell',
                if (!margin.contains('25.0')) 'no 25 % in the margin cell',
                if (!strip.contains('160.00')) 'the totals strip',
              ]
            : <String>[
                if (l['cost_amount'] != null || server['cost_total'] != null)
                  'the server sent the viewer a cost',
                if (keysStarting('sales-invoice-line-cost-').isNotEmpty)
                  'cost cells shown',
                if (heads) 'a Cost or Margin header shown',
                if (strip.isNotEmpty) 'a cost strip shown',
              ];
        if (faults.isNotEmpty) throw StateError(faults.join('; '));
        if (appErrors.length > errs) throw StateError(errorsSince(errs));
      });
      await away();
    }

    // =======================================================================
    // TC-LOT-022: the counter bill split over two lots
    // =======================================================================
    if (isAdmin && _runs('counter')) {
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
      int rateBox = -1;
      try {
        await admin.write('PUT', _workflow, <String, dynamic>{
          ...stagesBack,
          'quotation_stage': false,
          'sales_order_stage': false,
          'delivery_note_stage': false,
          'default_branch_id': branch['id'],
          'default_warehouse_id': warehouse['id'],
        });
        log.info('TC-LOT-022', 'order and note stages off over HTTP');

        Future<void> counterLine({String? rate}) async {
          await away();
          await openMenu(tester, 'sell', 'salesInvoices/sales-invoices');
          await tapNew(tester);
          await pumpFor(tester, const Duration(seconds: 2));
          // The firm's lists are long: filter each to the run's own entry.
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

          await pick('sales-invoice-customer', 'MR$tag', nameR);
          await pick('sales-invoice-direct-product-0', '0M$tag-C', nameC);
          final String chosen = boxesIn(tester, 'sales-invoice-customer');
          log.info('TC-LOT-022', 'customer box "$chosen"');
          await pumpFor(tester, const Duration(seconds: 3));
          final List<String> boxes = boxList('sales-invoice-direct-0');
          log.info('TC-LOT-022', 'line 1 after the product: $boxes');
          if (rateBox < 0) {
            for (int i = 1; i < boxes.length; i++) {
              if (_same(_first(boxes[i]), 100) && boxes[i].contains('.')) {
                rateBox = i;
              }
            }
          }
          if (rate != null) {
            if (rateBox < 0) throw StateError('no rate box found in $boxes');
            await typeIn(tester, 'sales-invoice-direct-0', rateBox, rate);
          }
          await typeIn(tester, 'sales-invoice-direct-0', 1, '15');
          await pumpFor(tester, const Duration(seconds: 4));
        }

        ({double qty, double rate}) partOf(int i) {
          final List<String> b = boxList('sales-invoice-direct-$i');
          return (
            qty: b.length > 1 ? (_first(b[1]) ?? -1) : -1,
            rate: rateBox > 0 && b.length > rateBox ? (_first(b[rateBox]) ?? -1) : -1,
          );
        }

        await log.step('TC-LOT-022 steps 1-2 a line of 15 splits: 10 at '
            '100.00 and 5 at 112.00', () async {
          final int errs = appErrors.length;
          await counterLine();
          final List<Json> avail = <Json>[
            for (final dynamic r in (await admin.get(
                    '/api/v1/batch-serial/batches/availability?product_id='
                    '${productC['id']}&warehouse_id=${warehouse['id']}'
                    '&quantity=15&customer_id=${retailer['id']}')) as List<dynamic>)
              r as Json,
          ];
          final List<String> serverParts = <String>[
            for (final Json a in avail)
              if (_n(a['fefo']) > 0) '${_n(a['fefo'])} at ${a['ptr']}',
          ];
          final List<String> lines = keysStarting('sales-invoice-direct-')
              .where((String k) => RegExp(r'^sales-invoice-direct-\d+$').hasMatch(k))
              .toList()
            ..sort();
          final String note = textOnScreen(tester)
              .where((String t) => t.contains('split into'))
              .join(' | ');
          log.saw = 'rate box $rateBox; lines on screen ${[for (final String k in lines) boxList(k)]}; '
              'note "$note"; server lots $serverParts';
          final ({double qty, double rate}) a = partOf(0);
          final ({double qty, double rate}) b = partOf(1);
          final List<String> faults = <String>[
            if (serverParts.length != 2) 'the server takes from ${serverParts.length} lots',
            if (lines.length < 2) 'not split',
            if (!_same(a.qty, 10) || !_same(a.rate, 100)) 'line 1 is ${a.qty} at ${a.rate}',
            if (!_same(b.qty, 5) || !_same(b.rate, 112)) 'line 2 is ${b.qty} at ${b.rate}',
            if (avail.isNotEmpty && !_same(_n(avail.first['ptr']), a.rate))
              'line 1 is not at the server\'s first lot price',
          ];
          if (faults.isNotEmpty) throw StateError(faults.join('; '));
          if (appErrors.length > errs) throw StateError(errorsSince(errs));
        });

        await log.step('TC-LOT-022 the split bill saved as a draft: the server '
            'holds 10 at 100.00 and 5 at 112.00', () async {
          final int errs = appErrors.length;
          final Set<String> before = <String>{
            for (final Json r in await list('/api/v1/sales-invoices?page_size=100'))
              '${r['id']}',
          };
          final String said = await pressAndRead(
              tester, () => tapKey(tester, 'sales-invoice-save'),
              seconds: 8);
          Json? made;
          for (final Json r in await list('/api/v1/sales-invoices?page_size=100')) {
            if (!before.contains('${r['id']}') && r['customer_id'] == retailer['id']) {
              made = await admin.one('sales-invoices', '${r['id']}');
            }
          }
          final List<String> got = <String>[
            for (final dynamic l in (made?['lines'] as List<dynamic>?) ?? <dynamic>[])
              '${_n((l as Json)['current_invoice_quantity'] ?? l['quantity'])} at ${_n(l['unit_price'])}',
          ];
          log.saw = 'said "$said"; ${made == null ? 'no bill' : '${docNumber(made)} ${made['status']}'}; '
              'lines $got';
          if (made != null) {
            final ({int status, String text}) gone = await admin.attempt('POST',
                '/api/v1/sales-invoices/${made['id']}/cancel',
                <String, dynamic>{'reason': 'click flow clean-up'});
            log.info('TC-LOT-022', 'draft cancelled: ${gone.status}');
          }
          if (made == null) throw StateError('no bill saved');
          if (!got.contains('10.0 at 100.0') || !got.contains('5.0 at 112.0')) {
            throw StateError('the server lines are $got');
          }
          if (appErrors.length > errs) throw StateError(errorsSince(errs));
        });

        await log.step('TC-LOT-022 step 4 a typed rate 105.00 stays on every '
            'part', () async {
          final int errs = appErrors.length;
          await counterLine(rate: '105');
          final ({double qty, double rate}) a = partOf(0);
          final ({double qty, double rate}) b = partOf(1);
          // Put the stages back at once: a run cut off before its finally
          // left the firm billing directly once (2026-10-16).
          await admin.write('PUT', _workflow, stagesBack);
          log.saw = 'lines ${boxList('sales-invoice-direct-0')} / '
              '${boxList('sales-invoice-direct-1')}';
          final List<String> faults = <String>[
            if (!_same(a.rate, 105)) 'line 1 at ${a.rate}',
            if (keysStarting('sales-invoice-direct-1').isNotEmpty && !_same(b.rate, 105))
              'line 2 at ${b.rate}',
          ];
          if (faults.isNotEmpty) throw StateError(faults.join('; '));
          if (appErrors.length > errs) throw StateError(errorsSince(errs));
        });
        await away();
      } finally {
        await admin.write('PUT', _workflow, stagesBack);
        log.info('TC-LOT-022', 'workflow stages put back over HTTP');
      }
    }

    log.skip('TC-LOT-015 step 3', 'changing a goods type after the fact is '
        'HTTP (tc_lot_015.py); the form only reads the type at creation');
    log.skip('TC-LOT-020 step 5', 'renaming and deleting Retail is HTTP '
        '(tc_lot_020.py)');
    log.skip('TC-LOT-021 step 4', 'print and PDF are the printing round');
    log.skip('TC-LOT-022 step 3', 'the bare line refused is HTTP (tc_lot_022.py)');
    log.info('errors', 'app errors and overflows this run: ${appErrors.length}');
    log.finish();
  });
}
