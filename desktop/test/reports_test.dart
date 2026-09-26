import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
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
}
