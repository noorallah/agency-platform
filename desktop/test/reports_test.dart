import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/finance.dart';
import 'package:agency_desktop/models/report.dart';
import 'package:agency_desktop/ui/reports/report_catalog.dart';
import 'package:agency_desktop/ui/reports/reports_workspace.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart' show ListViewRequest, ListViewRequestScope, Phase2Scope, EnterpriseDataGrid;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// The reports the server could always produce.
///
/// Thirty-four report endpoints existed across seven modules and the client
/// called none of them, while REPORT_VIEW was seeded and granted. The reports
/// are data here rather than screens, so the interesting behaviour is how a
/// definition turns into a grid.
PermissionService _permissionsFor(List<String> perms) {
  final String payload = base64Url.encode(
    utf8.encode(jsonEncode({'permissions': perms})),
  );
  return PermissionService()..applyAccessToken('h.$payload.s');
}

class _ReportApi extends ApiClient {
  _ReportApi({this.rows = const [], int? total})
      : total = total ?? rows.length,
        super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Json> rows;

  /// How many the window holds in all; the rows are one page of it.
  final int total;
  final List<String> requested = [];
  final List<Map<String, String>?> queries = [];
  final List<String?> rowsKeys = [];

  @override
  Future<ReportPage> reportRows(
    String path, {
    Map<String, String>? query,
    String? rowsKey,
  }) async {
    requested.add(path);
    queries.add(query);
    rowsKeys.add(rowsKey);
    return ReportPage(rows: rows, total: total);
  }

  /// Every journal opened from a row (55 M9).
  final List<String> journalsOpened = [];

  @override
  Future<JournalEntry> journalEntry(String id) async {
    journalsOpened.add(id);
    return JournalEntry.fromJson({
      'id': id,
      'reference_number': 'SI-7',
      'journal_date': '2026-05-05',
      'status': 'POSTED',
      'lines': const [],
    });
  }

  @override
  Future<PagedResult<LedgerAccount>> ledgerAccounts({
    String? accountGroupId,
    bool? isActive,
    bool openToHandJournals = false,
  }) async =>
      const PagedResult(items: [], total: 0);

  /// Every Form 26Q file asked for, as `year Qn format`.
  final List<String> files = [];

  @override
  Future<List<int>> tds26qFile({
    required String financialYear,
    required String quarter,
    String format = 'xlsx',
  }) async {
    files.add('$financialYear $quarter $format');
    return const [1, 2, 3];
  }
}

Future<void> _pump(
  WidgetTester tester,
  _ReportApi api, {
  String tabId = 'operational',
  List<String> perms = const ['REPORT_VIEW'],
  bool hasActiveFirm = true,
}) async {
  tester.view.physicalSize = const Size(1600, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: ReportsWorkspace(
          api: api,
          permissions: _permissionsFor(perms),
          hasActiveFirm: hasActiveFirm,
          tabId: tabId,
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  group('turning rows into a grid', () {
    const ReportDefinition plain = ReportDefinition(
      id: 'r',
      label: 'A report',
      description: 'what it answers',
      path: '/api/v1/x',
      area: ReportArea.operational,
      permission: 'REPORT_VIEW',
    );

    test('identifiers are left out', () {
      // A report that leads with invoice_id shows a reader a UUID where they
      // wanted an invoice number, and every record carries both.
      final List<ReportColumn> columns = columnsFor(plain, [
        {'invoice_id': 'abc', 'invoice_number': 'SI-1', 'grand_total': '10.00'},
      ]);
      expect(columns.map((c) => c.key), ['invoice_number', 'grand_total']);
    });

    test('a column is named in words', () {
      final List<ReportColumn> columns = columnsFor(plain, [
        {'grand_total': '10.00'}
      ]);
      expect(columns.single.label, 'Grand total');
    });

    test('amounts sit right, dates do not', () {
      // Decimals arrive as strings to keep their precision, so the type alone
      // does not say which is which.
      final List<ReportColumn> columns = columnsFor(plain, [
        {'grand_total': '10.00', 'invoice_date': '2026-08-14', 'count': 3},
      ]);
      expect(columns[0].numeric, isTrue);
      expect(columns[1].numeric, isFalse, reason: 'a date is not a number');
      expect(columns[2].numeric, isTrue);
    });

    test('a definition can name its own columns', () {
      const ReportDefinition named = ReportDefinition(
        id: 'r',
        label: 'A report',
        description: 'what it answers',
        path: '/api/v1/x',
        area: ReportArea.operational,
        permission: 'REPORT_VIEW',
        columns: [ReportColumn(key: 'invoice_id', label: 'Reference')],
      );
      expect(
          columnsFor(named, [
            {'invoice_id': 'abc'}
          ]).single.label,
          'Reference');
    });

    test('a nested value is not a cell', () {
      // Several endpoints answer with whole documents; `lines` in one cell is
      // a Dart list printed at a reader.
      final List<ReportColumn> columns = columnsFor(plain, [
        {'id': 'u', 'invoice_number': 'SI-1', 'lines': [], 'notes': {}},
      ]);
      expect(columns.map((c) => c.key), ['invoice_number']);
    });

    test('an empty result has no columns to guess at', () {
      expect(columnsFor(plain, const []), isEmpty);
    });

    test('a missing value reads as absent rather than as nothing', () {
      expect(cellValue({'due_date': null}, 'due_date'), '—');
      expect(cellValue({'amount': '0.00'}, 'amount'), '0.00');
    });
  });

  group('the catalogue', () {
    test('every report has a path, and no two share an id', () {
      final Set<String> ids = {for (final r in reportCatalog) r.id};
      expect(ids.length, reportCatalog.length);
      for (final ReportDefinition report in reportCatalog) {
        expect(report.path, startsWith('/api/v1/'));
        expect(report.description, isNotEmpty);
      }
    });

    test('a document-shaped report names its own columns', () {
      // Deriving from a forty-field document gives forty columns, so these
      // must not fall back to the derived set.
      const Set<String> documentShaped = {
        'delivery-note-pending',
        'goods-receipt-pending',
        'goods-receipt-completed',
        'goods-receipt-rejected',
        'goods-receipt-damaged',
        'sales-invoice-pending',
        'sales-invoice-overdue',
        'purchase-invoice-pending',
        'purchase-invoice-overdue',
      };
      for (final ReportDefinition report in reportCatalog) {
        if (documentShaped.contains(report.id)) {
          expect(report.columns, isNotEmpty, reason: report.id);
        }
      }
    });

    test('both tabs have reports behind them', () {
      // A tab offered with nothing behind it is the Coming Soon this replaced.
      expect(reportsFor(ReportArea.operational), isNotEmpty);
      expect(reportsFor(ReportArea.financial), isNotEmpty);
    });
  });

  group('the workspace', () {
    testWidgets('it opens the first report of the tab', (tester) async {
      final _ReportApi api = _ReportApi(rows: [
        {'invoice_number': 'SI-1', 'grand_total': '100.00'},
      ]);
      await _pump(tester, api);

      expect(
          api.requested.single, reportsFor(ReportArea.operational).first.path);
      expect(find.text('SI-1'), findsOneWidget);
      expect(find.text('1–1 of 1'), findsOneWidget);
    });

    testWidgets('choosing another report reads it', (tester) async {
      final _ReportApi api = _ReportApi();
      await _pump(tester, api);
      final ReportDefinition second = reportsFor(ReportArea.operational)[1];

      await tester.tap(find.text(second.label));
      await tester.pumpAndSettle();

      expect(api.requested.last, second.path);
    });

    testWidgets('the financial tab shows financial reports', (tester) async {
      final _ReportApi api = _ReportApi();
      await _pump(tester, api, tabId: 'financial');

      expect(api.requested.single, reportsFor(ReportArea.financial).first.path);
      expect(find.text('Customer outstanding'), findsOneWidget);
    });

    testWidgets('the stock valuation asks for one day, not a period',
        (tester) async {
      // D-GOLIVE-3: a valuation is as on a day; From and To would ask the
      // accountant a question the report cannot answer.
      final _ReportApi api = _ReportApi();
      await _pump(tester, api, tabId: 'financial');
      await tester.scrollUntilVisible(find.text('Stock valuation'), 200,
          scrollable: find.byType(Scrollable).first);
      await tester.tap(find.text('Stock valuation'));
      await tester.pumpAndSettle();

      expect(api.requested.last, '/api/v1/inventory/reports/stock-valuation');
      expect(find.byKey(const ValueKey<String>('report-from')), findsNothing);
      expect(find.widgetWithText(TextField, 'As on'), findsOneWidget);
    });

    testWidgets('a report says what question it answers', (tester) async {
      // "Reconciliation" tells nobody what is being reconciled.
      await _pump(tester, _ReportApi());
      expect(
        find.text(reportsFor(ReportArea.operational).first.description),
        findsOneWidget,
      );
    });

    testWidgets('an empty report says so rather than showing a blank grid',
        (tester) async {
      await _pump(tester, _ReportApi());
      expect(find.textContaining('Nothing to report'), findsOneWidget);
    });

    testWidgets('a wide report scrolls sideways rather than overflowing',
        (tester) async {
      // The overflow matrix pumps this screen with no firm, so it only ever
      // sees the empty state. A report with more columns than the smallest
      // supported window can hold is the shape that actually breaks.
      final _ReportApi api = _ReportApi(rows: [
        for (int row = 0; row < 3; row++)
          {for (int c = 0; c < 14; c++) 'column_number_$c': 'value $row.$c'},
      ]);
      tester.view.physicalSize = const Size(1366, 768);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: ReportsWorkspace(
            api: api,
            permissions: _permissionsFor(const ['REPORT_VIEW']),
            hasActiveFirm: true,
            tabId: 'operational',
          ),
        ),
      ));
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
      // A bar that is always there, pinned under the table's viewport, and
      // the columns off the right edge can be reached (plan item 10.8).
      final Scrollbar bar = tester.widget<Scrollbar>(
        find.byKey(const ValueKey<String>('report-horizontal-scrollbar')),
      );
      expect(bar.thumbVisibility, isTrue);
      final ScrollController controller = bar.controller!;
      expect(controller.position.maxScrollExtent, greaterThan(0));
      controller.jumpTo(controller.position.maxScrollExtent);
      await tester.pumpAndSettle();
      expect(find.text('value 0.13'), findsOneWidget);
    });

    testWidgets('a module code alone opens its own reports and no other',
        (tester) async {
      // The screen used to be offered on REPORT_VIEW alone while every route
      // took its module's code, so an accountant holding REPORT_VIEW was
      // refused every entry and a sales manager without it saw no screen
      // (D-RPT-4). Now either opens a report, and the picker lists only what
      // the caller can read -- asserted on what the workspace asks the server
      // for, because the picker is a lazy list.
      bool purchaseOnly(ReportDefinition r) => r.permission == 'PURCHASE_VIEW';
      final List<ReportDefinition> purchase =
          reportsFor(ReportArea.operational, canRead: purchaseOnly);
      expect(purchase, isNotEmpty);
      expect(purchase.every(purchaseOnly), isTrue);
      expect(
          purchase.length, lessThan(reportsFor(ReportArea.operational).length));

      final _ReportApi api = _ReportApi();
      await _pump(tester, api, perms: const ['PURCHASE_VIEW']);
      expect(api.requested.single, purchase.first.path);
      // Once in the picker and once as the open report's title.
      expect(find.text(purchase.first.label), findsNWidgets(2));
      expect(find.text('Sales order register'), findsNothing);
    });

    testWidgets('REPORT_VIEW alone opens every report', (tester) async {
      final _ReportApi api = _ReportApi();
      await _pump(tester, api, perms: const ['REPORT_VIEW']);
      expect(
          api.requested.single, reportsFor(ReportArea.operational).first.path);
      expect(find.text('Sales order register'), findsOneWidget);
    });

    testWidgets('a report that needs a period is asked for one',
        (tester) async {
      // BL-31.15: the targets achievement and commission reports lived only
      // on their own screens. Both routes require from_date and to_date and
      // answer 422 without them, so the workspace sends the boxes it shows.
      final _ReportApi api = _ReportApi();
      await _pump(tester, api, perms: const ['SALES_TARGET_VIEW']);
      expect(api.requested.single, '/api/v1/sales-targets/achievement');
      expect(api.queries.single?.keys, containsAll(['from_date', 'to_date']));
      expect(find.byKey(const ValueKey<String>('report-from')), findsOneWidget);

      await tester.enterText(
          find.byKey(const ValueKey<String>('report-from')), '2026-04-01');
      await tester.enterText(
          find.byKey(const ValueKey<String>('report-to')), '2026-06-30');
      await tester.testTextInput.receiveAction(TextInputAction.done);
      await tester.pumpAndSettle();
      expect(api.queries.last,
          containsPair('from_date', '2026-04-01'));
      expect(api.queries.last, containsPair('to_date', '2026-06-30'));
    });

    testWidgets('a dated report is paged a hundred at a time', (tester) async {
      // The whole history used to arrive at once (D-RPT-18): the first
      // report of the tab is a register, so it is dated and paged.
      final _ReportApi api = _ReportApi(
        rows: <Json>[
          for (int i = 0; i < 100; i++)
            <String, dynamic>{'quotation_number': 'QT-$i'},
        ],
        total: 250,
      );
      await _pump(tester, api);
      expect(api.queries.single, containsPair('page', '1'));
      expect(api.queries.single, containsPair('page_size', '100'));
      expect(find.text('1–100 of 250'), findsOneWidget);

      await tester.tap(find.byTooltip('Next page'));
      await tester.pumpAndSettle();

      expect(api.queries.last, containsPair('page', '2'));
      expect(find.text('101–200 of 250'), findsOneWidget);
    });

    testWidgets('a snapshot report is neither dated nor paged',
        (tester) async {
      // Pending, overdue, outstanding: a window would hide the old item
      // the report exists to show, so the route takes nothing.
      final _ReportApi api = _ReportApi(rows: const <Json>[]);
      await _pump(tester, api);
      final ReportDefinition snapshot = reportsFor(ReportArea.operational)
          .firstWhere((report) => !report.needsPeriod);
      await tester.ensureVisible(find.text(snapshot.label));
      await tester.tap(find.text(snapshot.label));
      await tester.pumpAndSettle();

      expect(api.requested.last, snapshot.path);
      expect(api.queries.last, isNull);
      expect(find.byKey(const ValueKey<String>('report-from')), findsNothing);
    });

    testWidgets('the commission report reads its rows out of the object',
        (tester) async {
      final _ReportApi api = _ReportApi();
      await _pump(tester, api,
          tabId: 'financial', perms: const ['COMMISSION_VIEW']);
      expect(api.requested.single, '/api/v1/commission/report');
      expect(api.rowsKeys.single, 'rows');
    });

    test('REPORT_VIEW does not offer a report its route does not accept it on',
        () {
      // The two routes check only their module's code; listing them to a
      // REPORT_VIEW holder would offer a report the server refuses (D-RPT-4).
      final Iterable<String> closed = reportCatalog
          .where((report) => !report.openToReportView)
          .map((report) => report.path);
      expect(
          closed,
          containsAll(<String>[
            '/api/v1/sales-targets/achievement',
            '/api/v1/commission/report',
          ]));
    });

    testWidgets('with no report-backing code there is nothing to show',
        (tester) async {
      await _pump(tester, _ReportApi(), perms: const ['CUSTOMER_VIEW']);
      expect(find.textContaining('do not have permission'), findsOneWidget);
    });
  });

  group('opened for a reason (phase 2 Home)', () {
    Future<void> pumpWith(
      WidgetTester tester,
      _ReportApi api,
      ListViewRequest request,
      List<String> perms,
    ) async {
      tester.view.physicalSize = const Size(1600, 900);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: ListViewRequestScope(
            request: request,
            child: ReportsWorkspace(
              api: api,
              permissions: _permissionsFor(perms),
              hasActiveFirm: true,
              tabId: 'financial',
            ),
          ),
        ),
      ));
      await tester.pumpAndSettle();
    }

    testWidgets("Home's 'Invoices overdue' opens the overdue report",
        (tester) async {
      final _ReportApi api = _ReportApi();
      await pumpWith(
        tester,
        api,
        const ListViewRequest(
          path: 'reports/financial',
          view: 'sales-invoice-overdue',
          serial: 1,
        ),
        const ['REPORT_VIEW', 'SALES_VIEW', 'SALES_INVOICE_VIEW'],
      );
      expect(api.requested.last, '/api/v1/sales-invoices/reports/overdue');
    });

    testWidgets('a report the user may not read is not opened by asking',
        (tester) async {
      final _ReportApi api = _ReportApi();
      await pumpWith(
        tester,
        api,
        const ListViewRequest(
          path: 'reports/financial',
          view: 'no-such-report',
          serial: 1,
        ),
        const ['REPORT_VIEW', 'SALES_VIEW', 'SALES_INVOICE_VIEW'],
      );
      expect(api.requested, isNot(contains('/api/v1/sales-invoices/reports/overdue')));
    });
  });

  testWidgets('phase 2 draws a report as a list: words, Yes/No, Indian digits',
      (tester) async {
    tester.view.physicalSize = const Size(1600, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final _ReportApi api = _ReportApi(rows: [
      {
        'quotation_number': 'QT-1',
        'status': 'CONVERTED',
        'is_expired': false,
        'grand_total': '112050.4168',
      },
    ]);
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Phase2Scope(
          child: ReportsWorkspace(
            api: api,
            permissions: _permissionsFor(const ['REPORT_VIEW']),
            hasActiveFirm: true,
            tabId: 'operational',
          ),
        ),
      ),
    ));
    await tester.pumpAndSettle();
    expect(find.byType(EnterpriseDataGrid<Json>), findsOneWidget);
    expect(find.text('Converted'), findsOneWidget);
    expect(find.text('No'), findsOneWidget);
    expect(find.text('1,12,050.42'), findsOneWidget);
    expect(find.text('false'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  group('the day book and the cash and bank books (55 M9)', () {
    Future<void> pumpBook(
        WidgetTester tester, _ReportApi api, String view) async {
      tester.view.physicalSize = const Size(1600, 900);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: Phase2Scope(
            child: ListViewRequestScope(
              request:
                  ListViewRequest(path: 'reports/financial', view: view, serial: 1),
              child: ReportsWorkspace(
                api: api,
                permissions:
                    _permissionsFor(const ['JOURNAL_VIEW', 'LEDGER_VIEW']),
                hasActiveFirm: true,
                tabId: 'financial',
              ),
            ),
          ),
        ),
      ));
      await tester.pumpAndSettle();
    }

    test('each is listed under Financial, dated, and opens its journal', () {
      for (final String id in ['day-book', 'cash-book', 'bank-book']) {
        final ReportDefinition report =
            reportCatalog.singleWhere((report) => report.id == id);
        expect(report.area, ReportArea.financial, reason: id);
        expect(report.needsPeriod, isTrue, reason: id);
        expect(report.drill, ReportDrill.journal, reason: id);
      }
    });

    testWidgets('double-clicking a day book voucher shows its journal',
        (tester) async {
      final _ReportApi api = _ReportApi(rows: [
        {
          'journal_entry_id': 'je-7',
          'journal_date': '2026-05-05',
          'voucher': 'SI-7',
          'voucher_type': 'Sales',
          'source': 'Sales invoice',
          'narration': 'Sales invoice SI-7',
          'debit': '118.00',
          'credit': '118.00',
          'status': 'POSTED',
        },
      ]);
      await pumpBook(tester, api, 'day-book');
      expect(api.requested.last, '/api/v1/finance/reports/day-book');
      await tester.tap(find.text('SI-7'));
      await tester.pump(const Duration(milliseconds: 50));
      await tester.tap(find.text('SI-7'));
      await tester.pumpAndSettle();
      expect(api.journalsOpened, ['je-7']);
      expect(find.byType(Dialog), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('an opening balance row opens nothing', (tester) async {
      final _ReportApi api = _ReportApi(rows: [
        {
          'row_type': 'OPENING',
          'date': '2026-05-01',
          'voucher': '',
          'particulars': 'Opening balance',
          'balance': '50.00',
          'journal_entry_id': null,
        },
      ]);
      await pumpBook(tester, api, 'cash-book');
      expect(api.requested.last, '/api/v1/finance/reports/cash-book');
      await tester.tap(find.text('Opening balance'));
      await tester.pump(const Duration(milliseconds: 50));
      await tester.tap(find.text('Opening balance'));
      await tester.pumpAndSettle();
      expect(api.journalsOpened, isEmpty);
      expect(tester.takeException(), isNull);
    });
  });

  group('discount given and collections (67 rows 8 and 9)', () {
    test('discounts are operational, collections financial, all dated', () {
      const Map<String, ReportArea> expected = {
        'discount-by-customer': ReportArea.operational,
        'discount-by-salesman': ReportArea.operational,
        'discount-by-product': ReportArea.operational,
        'discount-by-promotion': ReportArea.operational,
        'collections-by-day': ReportArea.financial,
        'collections-by-salesman': ReportArea.financial,
        'collections-by-mode': ReportArea.financial,
      };
      for (final MapEntry<String, ReportArea> entry in expected.entries) {
        final ReportDefinition report =
            reportCatalog.singleWhere((report) => report.id == entry.key);
        expect(report.area, entry.value, reason: entry.key);
        expect(report.needsPeriod, isTrue, reason: entry.key);
        expect(report.columns, isNotEmpty, reason: entry.key);
      }
      final ReportDefinition byCustomer = reportCatalog
          .singleWhere((report) => report.id == 'discount-by-customer');
      expect(byCustomer.columns.map((column) => column.key),
          containsAll(['typed_discount', 'arranged_discount']));
    });

    testWidgets('collections by salesman name their first column',
        (tester) async {
      final _ReportApi api = _ReportApi(rows: [
        {
          'key': 'On account',
          'label': 'On account',
          'receipts': 1,
          'collected': '100.00',
          'reversals': 0,
          'reversed': '0.00',
          'net_collected': '100.00',
        },
      ]);
      tester.view.physicalSize = const Size(1600, 900);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: Phase2Scope(
            child: ListViewRequestScope(
              request: const ListViewRequest(
                path: 'reports/financial',
                view: 'collections-by-salesman',
                serial: 1,
              ),
              child: ReportsWorkspace(
                api: api,
                permissions: _permissionsFor(const ['RECEIPT_VIEW']),
                hasActiveFirm: true,
                tabId: 'financial',
              ),
            ),
          ),
        ),
      ));
      await tester.pumpAndSettle();
      expect(api.requested.last,
          '/api/v1/receipts/reports/collections-by-salesman');
      expect(find.text('Salesman'), findsWidgets);
      expect(find.text('On account'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });
  });

  group('stock ageing, slow and dead stock, vendor ageing (55 S7)', () {
    test('each is catalogued with its columns', () {
      for (final String id in [
        'stock-ageing',
        'slow-moving',
        'dead-stock',
        'vendor-ageing',
      ]) {
        final ReportDefinition report =
            reportCatalog.singleWhere((report) => report.id == id);
        expect(report.columns, isNotEmpty, reason: id);
      }
      expect(
          reportCatalog.singleWhere((r) => r.id == 'slow-moving').days, 90);
      expect(
          reportCatalog.singleWhere((r) => r.id == 'dead-stock').days, 180);
      expect(
          reportCatalog.singleWhere((r) => r.id == 'vendor-ageing').needsPeriod,
          isFalse,
          reason: 'an ageing is as on today, not over a period');
    });

    testWidgets('dead stock asks for a day and a number of days',
        (tester) async {
      final _ReportApi api = _ReportApi(rows: [
        {
          'product_code': 'P-9',
          'product_name': 'Old stock',
          'quantity': '4',
          'value': '40.00',
        },
      ]);
      tester.view.physicalSize = const Size(1600, 900);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: Phase2Scope(
            child: ListViewRequestScope(
              request: const ListViewRequest(
                path: 'reports/operational',
                view: 'dead-stock',
                serial: 1,
              ),
              child: ReportsWorkspace(
                api: api,
                permissions: _permissionsFor(const ['INVENTORY_VIEW']),
                hasActiveFirm: true,
                tabId: 'operational',
              ),
            ),
          ),
        ),
      ));
      await tester.pumpAndSettle();
      expect(api.requested.last, '/api/v1/inventory/reports/dead-stock');
      expect(api.queries.last!['days'], '180');
      expect(find.byKey(const ValueKey<String>('report-from')), findsNothing);
      expect(find.byKey(const ValueKey<String>('report-days')), findsOneWidget);

      await tester.enterText(
          find.byKey(const ValueKey<String>('report-days')), '60');
      await tester.testTextInput.receiveAction(TextInputAction.done);
      await tester.pumpAndSettle();
      expect(api.queries.last!['days'], '60');
      expect(find.text('P-9'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });
  });

  group('the quarterly TDS return (53.1)', () {
    test('a screen opens on the last quarter that has ended', () {
      expect(lastEndedReturnQuarter(DateTime(2026, 10, 1)), ('2026-27', 2));
      expect(lastEndedReturnQuarter(DateTime(2026, 7, 15)), ('2026-27', 1));
      // April to June is Q1, so in May the quarter that ended is last
      // year's Q4.
      expect(lastEndedReturnQuarter(DateTime(2026, 5, 2)), ('2025-26', 4));
      expect(lastEndedReturnQuarter(DateTime(2027, 2, 28)), ('2026-27', 3));
    });

    testWidgets('26Q asks for a year and a quarter, and downloads the file',
        (tester) async {
      tester.view.physicalSize = const Size(1600, 900);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      final _ReportApi api = _ReportApi(rows: [
        {
          'serial': 1,
          'section': '194Q',
          'deductee_code': '01',
          'pan': 'AAACP1234C',
          'party_name': 'Principal Ltd',
          'payment_date': '2026-05-10',
          'amount_paid': '100000.00',
          'tds_amount': '100.00',
          'rate_percent': '0.1000',
          'higher_rate_reason': '',
          'document_number': 'PAY-1',
        },
      ]);
      final List<String> saved = [];
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: Phase2Scope(
            child: ListViewRequestScope(
              request: const ListViewRequest(
                path: 'reports/financial',
                view: 'tds-26q',
                serial: 1,
              ),
              child: ReportsWorkspace(
                api: api,
                permissions: _permissionsFor(const ['ACCOUNT_VIEW']),
                hasActiveFirm: true,
                tabId: 'financial',
                saveFile: (name, bytes) async {
                  saved.add('$name ${bytes.length}');
                  return 'C:/out/$name';
                },
              ),
            ),
          ),
        ),
      ));
      await tester.pumpAndSettle();
      expect(api.requested.last, '/api/v1/finance/reports/tds-26q');
      final Map<String, String> query = api.queries.last!;
      expect(query.keys, containsAll(['financial_year', 'quarter', 'page']));
      expect(query.containsKey('from_date'), isFalse,
          reason: 'a return is one quarter, never a span of dates');
      expect(query['quarter'], matches(RegExp(r'^Q[1-4]$')));
      expect(find.byKey(const ValueKey<String>('report-financial-year')),
          findsOneWidget);
      expect(find.byKey(const ValueKey<String>('report-quarter')),
          findsOneWidget);
      expect(find.text('AAACP1234C'), findsOneWidget);

      await tester.enterText(
          find.byKey(const ValueKey<String>('report-financial-year')),
          '2026-27');
      await tester.tap(find.byKey(const ValueKey<String>('report-quarter')));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Q1 Apr-Jun').last);
      await tester.pumpAndSettle();
      expect(api.queries.last!['quarter'], 'Q1');
      expect(api.queries.last!['financial_year'], '2026-27');

      await tester.tap(find.byKey(const ValueKey<String>('report-download')));
      await tester.pumpAndSettle();
      expect(api.files, ['2026-27 Q1 xlsx']);
      expect(saved, ['26Q-2026-27-Q1.xlsx 3']);
      expect(tester.takeException(), isNull);
    });
  });
}
