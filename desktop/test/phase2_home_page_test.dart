import 'package:agency_desktop/core/api/api_client.dart';
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
  final List<Map<String, dynamic>> marked = [];
  final List<String> withdrawn = [];
  String? refuseMarkWith;

  List<Map<String, dynamic>> calendar = [
    {
      'kind': 'GSTR3B',
      'return_period': '2026-08',
      'due_date': '2026-09-14',
      'amount': '72.00',
      'status': 'LATE',
      'days_late': 12,
      'done_on': null,
      'reference': null,
      'filing_id': null,
    },
    {
      'kind': 'GSTR1',
      'return_period': '2026-08',
      'due_date': '2026-09-11',
      'amount': '180.00',
      'status': 'DONE',
      'days_late': 0,
      'done_on': '2026-09-10',
      'reference': null,
      'filing_id': 'f-1',
    },
  ];

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
  Future<double> receiptsOn(DateTime day) => _answer('receipts', 42500.0);

  @override
  Future<int> batchesExpiringIn30Days() => _answer('expiring', 2);

  @override
  Future<int> expiringLicences() => _answer('licences', 0);

  @override
  Future<List<Map<String, dynamic>>> taxCalendar() =>
      _answer('calendar', calendar);

  @override
  Future<void> markGstReturnFiled(Map<String, dynamic> body) async {
    if (refuseMarkWith != null) throw ApiException(refuseMarkWith!);
    marked.add(body);
    calendar = [
      for (final Map<String, dynamic> row in calendar)
        if (row['kind'] == body['return_type'])
          {...row, 'status': 'DONE', 'done_on': body['filed_on']}
        else
          row,
    ];
  }

  @override
  Future<void> withdrawGstReturnFiling(String id) async {
    withdrawn.add(id);
  }

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
  'accounting/receipts',
  'salesOrders',
  'deliveryNotes/delivery-notes',
  'goodsReceipts/receipts',
  'purchaseInvoices',
  'inventory/inventory',
  'inventory/expiry-monitor',
  'masters/customers',
  'masters/customer-statements',
  'sales/gst-payment',
  'sales/gst-returns',
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
    // The greeting alone, as the wireframe: the user's name is often the
    // firm's, which the chip beside it already shows (owner, 2026-09-26).
    expect(find.textContaining('Owner'), findsNothing);
    expect(find.textContaining('QA01 Traders'), findsOneWidget);
    expect(find.text('FAVOURITES'), findsOneWidget);
    expect(find.textContaining('Saturday 26-09-2026'), findsOneWidget);

    // 4,720 + 1,80,000 today; the draft and the cancelled bill are not sales.
    expect(_kpi(tester, 'sales-today'), '1.85 L');
    expect(_kpi(tester, 'sales-fortnight'), '2.35 L');
    // 6,00,000 + 1,20,000 owed; the advance is not.
    expect(_kpi(tester, 'receivable'), '7.20 L');
    expect(find.text('Receivable, 3 overdue'), findsOneWidget);
    expect(_kpi(tester, 'below-reorder'), '14');
    // The fourth key figure: money received today (backlog 49 item 4).
    expect(find.text('Receipts today'), findsOneWidget);
    expect(_kpi(tester, 'receipts-today'), isNotEmpty);
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
    expect(
        find.byKey(const ValueKey('home-kpi-receipts-today')), findsNothing);
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

  testWidgets('Customise sits at the far right of the greeting line',
      (tester) async {
    await _pump(tester,
        allowed: _owner, source: _Source(), onCustomise: (_) {});
    // The page is 1366 wide; the page bar has 12 px of padding each side.
    expect(tester.getTopRight(find.byKey(const ValueKey('home-customise'))).dx,
        closeTo(1366 - 12, 1));
  });

  testWidgets('tax calendar: a late return with its amount, a filed one ticked',
      (tester) async {
    await _pump(tester, allowed: _owner, source: _Source());
    final Finder late = find.byKey(const ValueKey('home-tax-GSTR3B-2026-08'));
    expect(find.descendant(of: late, matching: find.text('GSTR-3B · Aug 2026')),
        findsOneWidget);
    expect(find.descendant(of: late, matching: find.text('72')),
        findsOneWidget);
    final Finder lateText =
        find.descendant(of: late, matching: find.textContaining('12 days late'));
    expect(lateText, findsOneWidget);
    expect(tester.widget<Text>(lateText).style?.color,
        Theme.of(tester.element(lateText)).colorScheme.error);
    final Finder done = find.byKey(const ValueKey('home-tax-GSTR1-2026-08'));
    expect(find.descendant(of: done, matching: find.text('Filed 10 Sep')),
        findsOneWidget);
    expect(find.descendant(of: done, matching: find.byIcon(Icons.check_circle)),
        findsOneWidget);
    expect(find.byKey(const ValueKey('home-tax-undo-GSTR1-2026-08')),
        findsOneWidget);
  });

  testWidgets('tax calendar: IFF optional, PMT-06 and a quarter named (GST-7)',
      (tester) async {
    final _Source source = _Source();
    source.calendar = [
      {
        'kind': 'GSTR1',
        'return_period': '2026-09',
        'period_from': '2026-07-01',
        'due_date': '2026-10-13',
        'amount': '0',
        'status': 'DUE',
      },
      {
        'kind': 'IFF',
        'return_period': '2026-08',
        'period_from': '2026-08-01',
        'due_date': '2026-09-13',
        'amount': '0',
        'status': 'OPTIONAL',
      },
      {
        'kind': 'PMT06',
        'return_period': '2026-08',
        'period_from': '2026-08-01',
        'due_date': '2026-09-25',
        'amount': '5000',
        'status': 'DUE',
      },
    ];
    await _pump(tester, allowed: _owner, source: source);
    expect(find.text('GSTR-1 · Jul-Sep 2026'), findsOneWidget);
    expect(find.text('IFF (optional) · Aug 2026'), findsOneWidget);
    expect(find.text('PMT-06 deposit · Aug 2026'), findsOneWidget);
    expect(find.textContaining('optional · by 13 Sep'), findsOneWidget);
    // An IFF is marked filed like a GSTR-1; a deposit is not a filing.
    expect(find.byKey(const ValueKey('home-tax-mark-IFF-2026-08')),
        findsOneWidget);
    expect(find.byKey(const ValueKey('home-tax-mark-PMT06-2026-08')),
        findsNothing);
  });

  testWidgets('tax calendar: absent without the GST Payment screen',
      (tester) async {
    final _Source source = _Source();
    await _pump(tester,
        allowed: _owner.difference({'sales/gst-payment'}), source: source);
    expect(find.text('TAX CALENDAR'), findsNothing);
    expect(source.asked, isNot(contains('calendar')));
  });

  testWidgets('tax calendar: a row opens its screen', (tester) async {
    final List<String> opened =
        await _pump(tester, allowed: _owner, source: _Source());
    await tester.tap(find.byKey(const ValueKey('home-tax-GSTR3B-2026-08')));
    await tester.tap(find.byKey(const ValueKey('home-tax-GSTR1-2026-08')));
    expect(opened, ['sales/gst-payment', 'sales/gst-returns']);
  });

  testWidgets('Mark filed sends the filing and reloads the calendar',
      (tester) async {
    final _Source source = _Source();
    await _pump(tester, allowed: _owner, source: source);
    await tester.tap(find.byKey(const ValueKey('home-tax-mark-GSTR3B-2026-08')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const ValueKey('home-tax-arn')), 'AA123');
    await tester.tap(find.byKey(const ValueKey('home-tax-save')));
    await tester.pumpAndSettle();
    expect(source.marked, [
      {
        'return_type': 'GSTR3B',
        'return_period': '2026-08',
        'filed_on': '2026-09-26',
        'arn': 'AA123',
      },
    ]);
    expect(source.asked.where((a) => a == 'calendar').length, 2);
    expect(find.text('Filed 26 Sep'), findsOneWidget);
    expect(find.byType(AlertDialog), findsNothing);
  });

  testWidgets('Mark filed stays open with the refusal', (tester) async {
    final _Source source = _Source()..refuseMarkWith = 'Not yet filable';
    await _pump(tester, allowed: _owner, source: source);
    await tester.tap(find.byKey(const ValueKey('home-tax-mark-GSTR3B-2026-08')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('home-tax-save')));
    await tester.pumpAndSettle();
    expect(find.text('Not yet filable'), findsOneWidget);
    expect(find.byType(AlertDialog), findsOneWidget);
  });

  testWidgets('Undo withdraws the filing and reloads', (tester) async {
    final _Source source = _Source();
    await _pump(tester, allowed: _owner, source: source);
    await tester.tap(find.byKey(const ValueKey('home-tax-undo-GSTR1-2026-08')));
    await tester.pumpAndSettle();
    expect(source.withdrawn, ['f-1']);
    expect(source.asked.where((a) => a == 'calendar').length, 2);
  });
}
