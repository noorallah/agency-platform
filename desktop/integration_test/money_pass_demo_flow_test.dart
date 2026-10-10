import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'cases.dart';
import 'harness.dart';

/// The money pass on a firm that must not be changed (a demo firm): every
/// document is typed, read and **cancelled**; nothing is saved.
///
/// `money_pass_flow_test.dart` saves each document and holds the row to what
/// the server saved, which is why it runs on a fixture firm. This one runs
/// where a customer will be looking, so it saves nothing and holds each row
/// to the server three other ways:
///
/// - **the server's own pricing of the same lines**, asked for over HTTP (a
///   preview, which stores nothing), for the quotation and the sales order;
/// - **the saved document the screen is restating**, read over HTTP: the
///   order a proforma states, the bill a sales return comes off, the receipt
///   a purchase return comes off;
/// - **the screen's own foot**, whose figures are the server's totals: the
///   rows' taxable values must add up to *Taxable* and their amounts to
///   *Total*, and each row's rate must be its product's.
///
/// It counts the firm's documents before and after and fails if any count
/// moved.
///
/// **Written on 2026-10-10 and not yet run.** It analyses clean and its
/// steps are those of `money_pass_flow_test.dart`, which has run; but a
/// click flow is not proven until it has been through the app, so its first
/// run may need a step corrected. The owner chose to test DEMO01 by hand
/// that evening. Take this paragraph out with the first passing run.
///
///     IT_EMAIL=admin@demo01.test IT_PASSWORD=... \
///         bash integration_test/run.sh money_pass_demo_flow_test.dart
const String _customer =
    String.fromEnvironment('IT_CUSTOMER', defaultValue: 'City Medicals');
const String _vendor = String.fromEnvironment('IT_VENDOR',
    defaultValue: 'Sanjeevani Pharma Distributors');

/// The products typed on the sales documents: one at each rate of tax the
/// demo firm sells at, with the quantity of each.
const List<(String, String)> _basket = <(String, String)>[
  ('MED-AMOX250', '10'),
  ('FOOD-OIL1L', '6'),
  ('PNT-PRIMER-1L', '3'),
];

const List<String> _counted = <String>[
  'quotations',
  'sales-orders',
  'delivery-notes',
  'sales-invoices',
  'sales-returns',
  'proforma-invoices',
  'purchases',
  'goods-receipts',
  'purchase-invoices',
  'purchase-returns',
];

double _money(String text) =>
    double.tryParse(text.replaceAll(',', '').trim()) ?? double.nan;

bool _near(double a, double b, [double by = 0.011]) => (a - b).abs() <= by;

/// What one line's row shows: its taxable value, its rate and its amount.
class _Row {
  _Row(this.taxable, this.rate, this.amount, this.texts);

  final double taxable;
  final double rate;
  final double amount;
  final List<String> texts;

  @override
  String toString() => 'taxable ${taxable.toStringAsFixed(2)}, '
      '${rate.toStringAsFixed(1)}%, amount ${amount.toStringAsFixed(2)}';
}

/// Read the row keyed [key]: the last percentage in it is the tax rate, with
/// the taxable value before it and the amount after.
_Row _row(WidgetTester tester, String key) {
  final Finder row = find.byKey(ValueKey<String>(key));
  if (row.evaluate().isEmpty) {
    throw StateError('no row keyed $key on screen: '
        '${textOnScreen(tester).skip(10).take(60).join(' | ')}');
  }
  final List<String> texts = <String>[
    for (final Text text in tester
        .widgetList<Text>(find.descendant(of: row, matching: find.byType(Text))))
      (text.data ?? text.textSpan?.toPlainText() ?? '').trim(),
  ].where((String t) => t.isNotEmpty).toList();
  final RegExp percent = RegExp(r'^\d+(\.\d+)?%$');
  final int at = texts.lastIndexWhere(percent.hasMatch);
  if (at < 1 || at + 1 >= texts.length) {
    throw StateError('row $key shows no tax rate between two amounts: '
        '${texts.join(' ; ')}');
  }
  return _Row(
    _money(texts[at - 1]),
    double.parse(texts[at].replaceAll('%', '')),
    _money(texts[at + 1]),
    texts,
  );
}

/// The figure the foot shows under [label] ("Taxable", "Total").
double _foot(WidgetTester tester, String label) {
  for (final String text in textOnScreen(tester)) {
    final RegExpMatch? match =
        RegExp('^$label\\s+([0-9,]+\\.[0-9]{2})\$').firstMatch(text);
    if (match != null) return _money(match.group(1)!);
  }
  throw StateError('the foot shows no "$label" figure: '
      '${textOnScreen(tester).where((String t) => t.contains(label)).join(' | ')}');
}

/// The rows must be what the foot adds up to, and each at its own rate.
/// Returns the sentence a result line carries.
String _reconcile(WidgetTester tester, List<_Row> rows,
    {List<double>? rates}) {
  final List<String> wrong = <String>[];
  double taxable = 0;
  double amount = 0;
  for (int i = 0; i < rows.length; i++) {
    final _Row row = rows[i];
    taxable += row.taxable;
    amount += row.amount;
    final double worked = row.taxable * (1 + row.rate / 100);
    if (!_near(worked, row.amount, 0.03)) {
      wrong.add('line ${i + 1}: ${row.taxable} at ${row.rate}% is '
          '${worked.toStringAsFixed(2)}, the row says ${row.amount}');
    }
    if (rates != null && !_near(row.rate, rates[i], 0.06)) {
      wrong.add('line ${i + 1}: rate ${row.rate}%, its product is taxed '
          'at ${rates[i]}%');
    }
  }
  final double footTaxable = _foot(tester, 'Taxable');
  final double footTotal = _foot(tester, 'Total');
  if (!_near(taxable, footTaxable, 0.011 * rows.length)) {
    wrong.add('the rows are taxable ${taxable.toStringAsFixed(2)} together, '
        'the foot says $footTaxable');
  }
  if (!_near(amount, footTotal, 0.011 * rows.length)) {
    wrong.add('the rows come to ${amount.toStringAsFixed(2)}, the foot '
        'says $footTotal');
  }
  final String said = 'rows: ${rows.join(' | ')}; foot: taxable '
      '$footTaxable, total $footTotal';
  if (wrong.isNotEmpty) throw StateError('${wrong.join('; ')}. $said');
  return said;
}

/// Hold [rows] to the lines of a document the server priced or holds.
void _holdToLines(List<_Row> rows, List<dynamic> lines, String what) {
  if (lines.length < rows.length) {
    throw StateError('$what has ${lines.length} line(s), the screen '
        '${rows.length}');
  }
  for (int i = 0; i < rows.length; i++) {
    final Json line = lines[i] as Json;
    final double net = num2(line['net_amount']);
    final double tax = num2(line['tax_amount']);
    if (!_near(rows[i].taxable, net - tax) || !_near(rows[i].amount, net)) {
      throw StateError('line ${i + 1}: the row shows ${rows[i]}, $what says '
          'taxable ${(net - tax).toStringAsFixed(2)}, amount '
          '${net.toStringAsFixed(2)}');
    }
  }
}

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('money pass, saving nothing', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1600, 1000);
    tester.view.devicePixelRatio = 1;
    final Server server = await Server.connect();
    final Map<String, int> before = <String, int>{
      for (final String name in _counted) name: await totalOf(server, name),
    };
    await startAndSignIn(tester);
    final FlowLog flow = FlowLog('money-demo');

    // The masters, read once.
    Future<Json> oneOf(String collection, String search) async {
      final List<dynamic> rows = await server.get(
              '/api/v1/$collection?search=${Uri.encodeQueryComponent(search)}'
              '&page_size=20') as List<dynamic>;
      if (rows.isEmpty) throw StateError('no $collection matching "$search"');
      return rows.first as Json;
    }

    final Json customer = await oneOf('customers', _customer);
    final List<Json> products = <Json>[
      for (final (String code, String _) in _basket)
        await oneOf('products', code),
    ];
    final List<double> rates = <double>[
      for (final Json product in products)
        double.parse(RegExp(r'_(\d+)_')
            .firstMatch('${product['tax_profile_group_code']}')!
            .group(1)!),
    ];
    final List<dynamic> branches =
        await server.get('/api/v1/branches?page_size=50') as List<dynamic>;
    final Json branch = branches.cast<Json>().firstWhere(
        (Json b) => b['is_default'] == true,
        orElse: () => branches.first as Json);
    final List<dynamic> warehouses =
        await server.get('/api/v1/warehouses?page_size=50') as List<dynamic>;
    final Json warehouse = warehouses.cast<Json>().firstWhere(
        (Json w) => w['branch_id'] == branch['id'] && w['is_default'] == true,
        orElse: () => warehouses.cast<Json>().firstWhere(
            (Json w) => w['branch_id'] == branch['id'],
            orElse: () => warehouses.first as Json));
    final String today = DateTime.now().toIso8601String().substring(0, 10);

    /// Type the basket on a sales document whose keys start with [prefix].
    Future<List<_Row>> typeBasket(String prefix) async {
      await chooseIn(tester, '$prefix-customer', _customer);
      for (int i = 0; i < _basket.length; i++) {
        if (i > 0) {
          await tester.tap(find.textContaining('+ add a'));
          await pumpFor(tester, const Duration(milliseconds: 600));
        }
        await chooseIn(
            tester, '$prefix-line-product-$i', '${products[i]['name']}');
        await typeIn(tester, '$prefix-line-$i', 1, _basket[i].$2);
      }
      await pumpFor(tester, const Duration(seconds: 5));
      return <_Row>[
        for (int i = 0; i < _basket.length; i++) _row(tester, '$prefix-line-$i'),
      ];
    }

    List<Json> basketLines(String quantityKey) => <Json>[
          for (int i = 0; i < _basket.length; i++)
            <String, dynamic>{
              'line_number': i + 1,
              'product_id': products[i]['id'],
              quantityKey: _basket[i].$2,
              'unit_price': products[i]['selling_price'],
            },
        ];

    // -- Quotation ---------------------------------------------------------
    await flow.step('quotation: three lines at three rates, not saved',
        () async {
      await openMenu(tester, 'sell', 'quotations');
      await tapNew(tester);
      final List<_Row> rows = await typeBasket('quotation');
      final String said = _reconcile(tester, rows, rates: rates);
      final Json priced = (await server
          .write('POST', '/api/v1/quotations/preview', <String, dynamic>{
        'customer_id': customer['id'],
        'branch_id': branch['id'],
        'warehouse_id': warehouse['id'],
        'quotation_date': today,
        'valid_until': DateTime.now()
            .add(const Duration(days: 30))
            .toIso8601String()
            .substring(0, 10),
        'rate_includes_tax': false,
        'lines': basketLines('quantity'),
      })) as Json;
      final Json quotation = priced['quotation'] as Json;
      _holdToLines(rows, quotation['lines'] as List<dynamic>,
          "the server's own pricing");
      final double total = _foot(tester, 'Total');
      if (!_near(total, num2(quotation['grand_total']))) {
        throw StateError('the foot says $total, the server prices the same '
            'lines at ${quotation['grand_total']}');
      }
      flow.saw = '$said; the server priced the same lines at '
          '${quotation['grand_total']}';
      await closeOpenEditor(tester);
    });

    // -- Sales order -------------------------------------------------------
    await flow.step('sales order: three lines at three rates, not saved',
        () async {
      await openMenu(tester, 'sell', 'salesOrders');
      await tapNew(tester);
      final List<_Row> rows = await typeBasket('sales-order');
      final String said = _reconcile(tester, rows, rates: rates);
      final Json priced = (await server
          .write('POST', '/api/v1/sales-orders/preview', <String, dynamic>{
        'customer_id': customer['id'],
        'branch_id': branch['id'],
        'warehouse_id': warehouse['id'],
        'order_date': today,
        'rate_includes_tax': false,
        'lines': basketLines('quantity'),
      })) as Json;
      final Json order = priced['order'] as Json;
      _holdToLines(
          rows, order['lines'] as List<dynamic>, "the server's own pricing");
      final double total = _foot(tester, 'Total');
      if (!_near(total, num2(order['grand_total']))) {
        throw StateError('the foot says $total, the server prices the same '
            'lines at ${order['grand_total']}');
      }
      flow.saw = '$said; the server priced the same lines at '
          '${order['grand_total']}';
      await closeOpenEditor(tester);
    });

    // -- Proforma, of an order already approved ----------------------------
    await flow.step('proforma: the rows against the approved order it states',
        () async {
      final List<dynamic> orders = await server
          .get('/api/v1/sales-orders?page_size=100') as List<dynamic>;
      final Json approved = orders.cast<Json>().firstWhere(
          (Json o) => o['status'] == 'APPROVED',
          orElse: () => throw StateError('no approved order on the firm'));
      final Json order = await server.one('sales-orders', '${approved['id']}');
      final List<dynamic> lines = order['lines'] as List<dynamic>;
      await openMenu(tester, 'sell', 'sales/proforma-invoices');
      await tapNew(tester);
      await pumpUntil(
          tester, find.byKey(const ValueKey<String>('proforma-raise')),
          waitingFor: 'the proforma editor');
      await chooseFiltered(tester, 'proforma-order', docNumber(order));
      await pumpFor(tester, const Duration(seconds: 2));
      final List<_Row> rows = <_Row>[
        for (int i = 0; i < lines.length; i++) _row(tester, 'proforma-line-$i'),
      ];
      _holdToLines(rows, lines, 'the order ${docNumber(order)}');
      flow.saw = '${docNumber(order)}: ${rows.join(' | ')}; the order holds '
          'the same';
      await closeOpenEditor(tester);
    });

    // -- Sales return, off a bill already approved --------------------------
    await flow.step('sales return: one unit off an approved bill, not saved',
        () async {
      final List<dynamic> bills = await server
          .get('/api/v1/sales-invoices?page_size=100') as List<dynamic>;
      final Json approved = bills.cast<Json>().firstWhere(
          (Json b) => b['status'] == 'APPROVED',
          orElse: () => throw StateError('no approved bill on the firm'));
      final Json bill = await server.one('sales-invoices', '${approved['id']}');
      final Json billed = (bill['lines'] as List<dynamic>).first as Json;
      final double quantity = num2(billed['current_invoice_quantity']);
      await openMenu(tester, 'sell', 'salesReturns');
      await tapNew(tester);
      await chooseIn(tester, 'sales-return-document', docNumber(bill));
      await pumpFor(tester, const Duration(seconds: 2));
      await typeInKeyed(tester, 'sales-return-returning-', '1');
      await pumpFor(tester, const Duration(seconds: 5));
      final _Row row = _row(tester, 'sales-return-line-0');
      final double net = num2(billed['net_amount']);
      final double tax = num2(billed['tax_amount']);
      final double taxable = (net - tax) / quantity;
      final double amount = net / quantity;
      // One of several billed: the share is rounded, so a paisa either way.
      if (!_near(row.taxable, taxable, 0.02) ||
          !_near(row.amount, amount, 0.02)) {
        throw StateError('the row shows $row; one of the $quantity billed '
            'on ${docNumber(bill)} is taxable ${taxable.toStringAsFixed(2)}, '
            'amount ${amount.toStringAsFixed(2)}');
      }
      flow.saw = '${docNumber(bill)}: row $row; one of the $quantity billed '
          'is taxable ${taxable.toStringAsFixed(2)}, amount '
          '${amount.toStringAsFixed(2)}';
      await closeOpenEditor(tester);
    });

    // -- Purchase order ----------------------------------------------------
    await flow.step('purchase order: one line, not saved', () async {
      await openMenu(tester, 'buy', 'purchases/purchase-orders');
      await tapNew(tester);
      await chooseIn(tester, 'purchase-order-vendor', _vendor);
      await chooseInKeyed(tester, 'purchase-order-line-product-',
          '${products.first['name']}');
      await typeInKeyed(tester, 'purchase-order-qty-', '10');
      await pumpFor(tester, const Duration(seconds: 5));
      final _Row row = _row(tester, 'purchase-order-line-0');
      flow.saw = _reconcile(tester, <_Row>[row], rates: <double>[rates.first]);
      await closeOpenEditor(tester);
    });

    // -- Purchase return, off a receipt already completed -------------------
    await flow.step(
        'purchase return: one unit off a completed receipt, not saved',
        () async {
      final List<dynamic> receipts = await server
          .get('/api/v1/goods-receipts?page_size=100') as List<dynamic>;
      final Json completed = receipts.cast<Json>().firstWhere(
          (Json r) => r['status'] == 'COMPLETED',
          orElse: () => throw StateError('no completed receipt on the firm'));
      final Json receipt =
          await server.one('goods-receipts', '${completed['id']}');
      final String number = '${receipt['grn_number']}';
      await openMenu(tester, 'buy', 'purchaseReturns');
      await tapNew(tester);
      await chooseIn(tester, 'purchase-return-receipt', number);
      await pumpFor(tester, const Duration(seconds: 2));
      await typeInKeyed(tester, 'purchase-return-returning-', '1');
      await pumpFor(tester, const Duration(seconds: 5));
      final _Row row = _row(tester, 'purchase-return-line-0');
      final Json taken = (receipt['lines'] as List<dynamic>).first as Json;
      final double price = num2(taken['unit_price']);
      // One unit at the receipt's price, less any discount the receipt took.
      if (row.taxable > price + 0.011) {
        throw StateError('the row shows $row for one unit received at '
            '$price on $number');
      }
      flow.saw = '$number: row $row for one unit received at '
          '${price.toStringAsFixed(2)}; ${_reconcile(tester, <_Row>[row])}';
      await closeOpenEditor(tester);
    });

    // -- Nothing was saved ---------------------------------------------------
    await flow.step('the firm holds the same documents as before', () async {
      final List<String> moved = <String>[];
      for (final String name in _counted) {
        final int now = await totalOf(server, name);
        if (now != before[name]) moved.add('$name ${before[name]} -> $now');
      }
      if (moved.isNotEmpty) {
        throw StateError('documents were added: ${moved.join(', ')}');
      }
      flow.saw = before.entries
          .map((MapEntry<String, int> e) => '${e.key} ${e.value}')
          .join(', ');
    });

    flow.finish();
  });
}
