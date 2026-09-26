import 'package:agency_desktop/core/theme/theme_manager.dart';
import 'package:agency_desktop/phase2/home_page.dart';
import 'package:agency_desktop/phase2/menu_layout.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Home in the phase 2 app (UI_PHASE_2_DESIGN.md 4.9), as the owner approved
/// it in the wireframe -- the key figures, sales over 14 days, recent
/// invoices, a to-do list and the user's screens -- each part only for a
/// role that may open the list behind it.
final DateTime _today = DateTime.utc(2026, 9, 26);

class _Source implements HomeSource {
  _Source({this.failing = const {}});

  final Set<String> failing;
  final List<String> asked = [];

  Future<T> _answer<T>(String what, T value) async {
    asked.add(what);
    if (failing.contains(what)) throw StateError('refused');
    return value;
  }

  @override
  Future<List<Map<String, dynamic>>> invoiceRegister(
          DateTime from, DateTime to) =>
      _answer('register', [
        {
          'invoice_number': 'SI-0003',
          'customer_name': 'Sri Murugan Stores',
          'invoice_date': '2026-09-26',
          'grand_total': '4720.00',
          'status': 'APPROVED',
        },
        {
          'invoice_number': 'SI-0002',
          'customer_name': 'QA Retail',
          'invoice_date': '2026-09-26',
          'grand_total': '180000',
          'status': 'CLOSED',
        },
        // Neither a draft nor a cancelled bill is a sale.
        {
          'invoice_number': 'SI-0004',
          'customer_name': 'Draft Co',
          'invoice_date': '2026-09-26',
          'grand_total': '99999',
          'status': 'DRAFT',
        },
        {
          'invoice_number': 'SI-0005',
          'customer_name': 'Cancelled Co',
          'invoice_date': '2026-09-26',
          'grand_total': '55555',
          'status': 'CANCELLED',
        },
        {
          'invoice_number': 'SI-0001',
          'customer_name': 'Anand Traders',
          'invoice_date': '2026-09-20',
          'grand_total': '50000',
          'status': 'APPROVED',
        },
      ]);

  @override
  Future<List<Map<String, dynamic>>> customerOutstanding() =>
      _answer('outstanding', [
        {'customer_name': 'A', 'outstanding_amount': '600000'},
        {'customer_name': 'B', 'outstanding_amount': '120000'},
        // An advance is not money owed.
        {'customer_name': 'C', 'outstanding_amount': '-5000'},
      ]);

  @override
  Future<int> itemsBelowReorder() => _answer('reorder', 14);

  @override
  Future<int> batchesExpiringIn30Days() => _answer('expiring', 2);

  @override
  Future<Map<String, dynamic>> summary(String path) => _answer(path, {
        'draft': 4,
        'pending_orders': 6,
        'overdue_invoices': 3,
        'pending_purchase_orders': 1,
      });
}

const Set<String> _owner = {
  'salesInvoices/sales-invoices',
  'salesOrders',
  'deliveryNotes/delivery-notes',
  'goodsReceipts/receipts',
  'purchaseInvoices',
  'inventory/inventory',
  'inventory/expiry-monitor',
  'masters/customers',
  'masters/customer-statements',
};

const Set<String> _storeman = {
  'inventory/inventory',
  'inventory/expiry-monitor',
  'goodsReceipts/receipts',
};

Future<List<String>> _pump(
  WidgetTester tester, {
  required Set<String> allowed,
  required HomeSource source,
  double width = 1366,
  Set<String> hidden = const {},
  ValueChanged<Set<String>>? onCustomise,
  List<String>? views,
}) async {
  tester.view.physicalSize = Size(width, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final List<String> opened = [];
  await tester.pumpWidget(MaterialApp(
    theme: ThemeRegistry.themeFor(
      palette: AppPalette.neutral,
      brightness: Brightness.light,
    ),
    home: Scaffold(
      body: Phase2HomePage(
        firmName: 'QA01 Traders',
        userName: 'Owner',
        today: _today,
        allowed: allowed.contains,
        source: source,
        onOpen: (item) => opened.add(item.path),
        hidden: hidden,
        onCustomise: onCustomise,
        onOpenView: views == null
            ? null
            : (item, view) => views.add('${item.path} $view'),
      ),
    ),
  ));
  await tester.pump();
  await tester.pump();
  expect(tester.takeException(), isNull);
  return opened;
}

String _kpi(WidgetTester tester, String key) {
  final Finder texts = find.descendant(
    of: find.byKey(ValueKey('home-kpi-$key')),
    matching: find.byType(Text),
  );
  return tester.widget<Text>(texts.first).data!;
}

void main() {
  testWidgets("the owner's Home: the wireframe's figures, from the day's bills",
      (tester) async {
    await _pump(tester, allowed: _owner, source: _Source());
    expect(find.textContaining('Owner'), findsOneWidget);
    expect(find.textContaining('QA01 Traders'), findsOneWidget);
    expect(find.textContaining('Saturday 26-09-2026'), findsOneWidget);

    // 4,720 + 1,80,000 today; the draft and the cancelled bill are not sales.
    expect(_kpi(tester, 'sales-today'), '1.85 L');
    expect(_kpi(tester, 'sales-fortnight'), '2.35 L');
    // 6,00,000 + 1,20,000 owed; the advance is not.
    expect(_kpi(tester, 'receivable'), '7.20 L');
    expect(find.text('Receivable, 3 overdue'), findsOneWidget);
    expect(_kpi(tester, 'below-reorder'), '14');
  });

  testWidgets('sales over 14 days: one bar a day, the busiest the tallest',
      (tester) async {
    await _pump(tester, allowed: _owner, source: _Source());
    expect(find.text('SALES, LAST 14 DAYS'), findsOneWidget);
    final List<double> heights = [
      for (int i = 0; i < 14; i++)
        tester.getSize(find.byKey(ValueKey('home-bar-$i'))).height,
    ];
    expect(heights.last, heights.reduce((a, b) => a > b ? a : b));
    // 20-09 is day 7 of the 14 (the fortnight starts 13-09).
    expect(heights[7], greaterThan(heights[6]));
    expect(find.byTooltip('26-09: 1,84,720.00'), findsOneWidget);
  });

  testWidgets('recent invoices, newest first', (tester) async {
    await _pump(tester, allowed: _owner, source: _Source());
    final double first =
        tester.getTopLeft(find.byKey(const ValueKey('home-recent-SI-0005'))).dy;
    final double last =
        tester.getTopLeft(find.byKey(const ValueKey('home-recent-SI-0001'))).dy;
    expect(first, lessThan(last));
    expect(find.text('1,80,000.00'), findsOneWidget);
  });

  testWidgets('to do: counts from each list, an overdue count in red',
      (tester) async {
    final List<String> opened =
        await _pump(tester, allowed: _owner, source: _Source());
    expect(find.text('Orders to approve'), findsOneWidget);
    expect(find.text('Batches expiring in 30 days'), findsOneWidget);
    final Finder overdue = find.descendant(
      of: find.byKey(const ValueKey('home-todo-Invoices overdue')),
      matching: find.text('3'),
    );
    final BuildContext context = tester.element(overdue);
    expect(tester.widget<Text>(overdue).style?.color,
        Theme.of(context).colorScheme.error);
    await tester.tap(find.byKey(const ValueKey('home-todo-Orders to approve')));
    expect(opened, ['salesOrders']);
  });

  testWidgets("a storeman's Home: stock and batches, no sales or receivables",
      (tester) async {
    final _Source source = _Source();
    await _pump(tester, allowed: _storeman, source: source);
    expect(
        find.byKey(const ValueKey('home-kpi-below-reorder')), findsOneWidget);
    expect(find.text('POs to receive'), findsOneWidget);
    expect(find.text('Batches expiring in 30 days'), findsOneWidget);
    expect(find.byKey(const ValueKey('home-kpi-sales-today')), findsNothing);
    expect(find.byKey(const ValueKey('home-kpi-receivable')), findsNothing);
    expect(find.text('SALES, LAST 14 DAYS'), findsNothing);
    expect(find.text('Orders to approve'), findsNothing);
    // What a role may not see is never even asked for.
    expect(source.asked, isNot(contains('register')));
    expect(source.asked, isNot(contains('outstanding')));
  });

  testWidgets('a figure that cannot be read is a dash, never a zero',
      (tester) async {
    await _pump(
      tester,
      allowed: _owner,
      source: _Source(failing: {'register', 'reorder'}),
    );
    expect(_kpi(tester, 'sales-today'), '-');
    expect(_kpi(tester, 'below-reorder'), '-');
    expect(find.text('Sales could not be read.'), findsOneWidget);
  });

  testWidgets('two columns on a laptop, one on a narrow window',
      (tester) async {
    await _pump(tester, allowed: _owner, source: _Source());
    final double chartLeft =
        tester.getTopLeft(find.text('SALES, LAST 14 DAYS')).dx;
    final double todoLeft = tester.getTopLeft(find.text('TO DO')).dx;
    expect(todoLeft, greaterThan(chartLeft + 400));

    await _pump(tester, allowed: _owner, source: _Source(), width: 700);
    expect(tester.getTopLeft(find.text('TO DO')).dx,
        lessThan(tester.getTopLeft(find.text('SALES, LAST 14 DAYS')).dx + 10));
  });

  testWidgets('with nothing to show, Home says where to go', (tester) async {
    await _pump(tester, allowed: const {}, source: _Source());
    expect(find.textContaining('Ctrl+K'), findsOneWidget);
  });

  test('amounts read the Indian way', () {
    expect(indianAmount(184000), '1.84 L');
    expect(indianAmount(21000000), '2.10 Cr');
    expect(indianAmount(62400), '62,400');
    expect(indianAmount(112050, full: true), '1,12,050.00');
    expect(indianAmount(999), '999');
  });

  test('every to-do and screen names a real menu screen', () {
    for (final String path in [
      for (final HomeTodo todo in Phase2HomePage.todos) todo.path,
      ...Phase2HomePage.screens,
      Phase2HomePage.expiry,
      Phase2HomePage.stock,
    ]) {
      expect(MenuLayout.itemFor(path), isNotNull, reason: path);
    }
  });

  testWidgets('Customise: choose which parts of Home to see', (tester) async {
    Set<String>? kept;
    await _pump(tester,
        allowed: _owner, source: _Source(), onCustomise: (h) => kept = h);
    await tester.tap(find.byKey(const ValueKey('home-customise')));
    await tester.pumpAndSettle();
    for (final String id in Phase2HomePage.sections.keys) {
      expect(find.byKey(ValueKey('home-show-$id')), findsOneWidget, reason: id);
    }
    await tester.tap(find.byKey(const ValueKey('home-show-chart')));
    await tester.pump();
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();
    expect(kept, {'chart'});
  });

  testWidgets('a hidden part is not drawn', (tester) async {
    await _pump(tester,
        allowed: _owner, source: _Source(), hidden: {'chart', 'todo'});
    expect(find.text('SALES, LAST 14 DAYS'), findsNothing);
    expect(find.text('TO DO'), findsNothing);
    expect(find.text('RECENT INVOICES'), findsOneWidget);
  });

  testWidgets("Customise offers only the parts the user's role has",
      (tester) async {
    await _pump(tester,
        allowed: _storeman, source: _Source(), onCustomise: (_) {});
    await tester.tap(find.byKey(const ValueKey('home-customise')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('home-show-chart')), findsNothing);
    expect(find.byKey(const ValueKey('home-show-todo')), findsOneWidget);
  });

  testWidgets('to-do lines land on exactly what they counted', (tester) async {
    final List<String> views = [];
    await _pump(tester,
        allowed: {..._owner, 'reports/operational', 'reports/financial'},
        source: _Source(),
        views: views);
    for (final String line in [
      'Orders to approve',
      'Orders to deliver',
      'Invoices overdue',
      'POs to receive',
      'Purchase bills overdue',
    ]) {
      await tester.tap(find.byKey(ValueKey('home-todo-$line')));
    }
    expect(views, [
      'salesOrders draft',
      'reports/operational sales-order-pending',
      'reports/financial sales-invoice-overdue',
      'reports/operational purchase-order-pending',
      'reports/financial purchase-invoice-overdue',
    ]);
  });

  testWidgets('without the report, a to-do line opens its list',
      (tester) async {
    final List<String> views = [];
    final List<String> opened = await _pump(tester,
        allowed: _owner, source: _Source(), views: views);
    await tester.tap(find.byKey(const ValueKey('home-todo-Invoices overdue')));
    expect(views, isEmpty);
    expect(opened, ['salesInvoices/sales-invoices']);
  });
}
