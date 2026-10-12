// The Excel download every report and statement screen offers (backlog 117).
//
// One writer lays the sheet out, so what is asked of it is asked once here:
// a figure is a number Excel can add up, text stays text, and the title and
// what the report was asked for sit above the headings. Then the screens:
// a paged report is read to its end rather than saved a page at a time, and
// a statement's sheet carries the figures the screen shows.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/finance.dart';
import 'package:agency_desktop/models/report.dart';
import 'package:agency_desktop/phase2/list_view_request.dart';
import 'package:agency_desktop/ui/finance/trial_balance_page.dart';
import 'package:agency_desktop/ui/reports/report_catalog.dart';
import 'package:agency_desktop/ui/reports/reports_workspace.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:agency_desktop/ui/workspace/report_workbook.dart';
import 'package:excel/excel.dart' as xls;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

PermissionService _permissionsFor(List<String> perms) {
  final String payload = base64Url.encode(
    utf8.encode(jsonEncode({'permissions': perms})),
  );
  return PermissionService()..applyAccessToken('h.$payload.s');
}

/// The cells of a saved workbook's one sheet, as plain values.
List<List<Object?>> _cells(List<int> bytes) {
  final xls.Excel workbook = xls.Excel.decodeBytes(bytes);
  final xls.Sheet sheet = workbook.tables.values.first;
  return [
    for (final List<xls.Data?> row in sheet.rows)
      [
        for (final xls.Data? cell in row)
          switch (cell?.value) {
            final xls.DoubleCellValue value => value.value,
            final xls.IntCellValue value => value.value,
            final xls.TextCellValue value => '${value.value}',
            null => null,
            final xls.CellValue value => '$value',
          },
      ],
  ];
}

/// A paged report: 250 rows served a hundred at a time.
class _PagedApi extends ApiClient {
  _PagedApi(this.report)
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final ReportDefinition report;
  static const int total = 250;
  final List<String> pages = [];

  Json _row(int index) => {
        for (final ReportColumn column in report.columns)
          column.key: column.numeric ? '${index + 1}.50' : 'R${index + 1}',
      };

  @override
  Future<ReportPage> reportRows(
    String path, {
    Map<String, String>? query,
    String? rowsKey,
  }) async {
    final int page = int.parse(query?['page'] ?? '1');
    pages.add('$page');
    final int start = (page - 1) * 100;
    return ReportPage(
      rows: [
        for (int i = start; i < start + 100 && i < total; i++) _row(i),
      ],
      total: total,
    );
  }
}

class _TrialBalanceApi extends ApiClient {
  _TrialBalanceApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  @override
  Future<List<AccountingPeriod>> accountingPeriods({
    String? financialYearId,
  }) async =>
      [
        AccountingPeriod.fromJson({
          'id': 'p-1',
          'financial_year_id': 'fy-1',
          'period_number': 1,
          'code': 'p-1',
          'name': 'April 2026',
          'starts_on': '2026-04-01',
          'ends_on': '2026-04-30',
          'status': 'OPEN',
        }),
      ];

  @override
  Future<TrialBalanceReport> trialBalance(
    String accountingPeriodId, {
    String? toPeriodId,
  }) async =>
      TrialBalanceReport.fromJson({
        'accounting_period_id': 'p-1',
        'total_debit': '604976.70',
        'total_credit': '604976.70',
        'is_balanced': true,
        'lines': [
          {
            'account_code': '1200',
            'account_name': 'Inventory',
            'account_type': 'ASSET',
            'opening_balance': '0.00',
            'period_debit': '8040.00',
            'period_credit': '1150.52',
            'closing_balance': '6889.48',
          },
        ],
      });
}

void main() {
  tearDown(() => WorkbookDownloadButton.saveOverride = null);

  group('the sheet', () {
    test('a figure is a number and text stays text', () {
      final List<List<Object?>> cells = _cells(workbookBytes(
        const WorkbookSheet(
          title: 'Sales register',
          notes: ['From 2026-04-01 to 2026-04-30'],
          headers: ['Bill', 'Customer', 'Total', 'Paid'],
          numeric: {2},
          rows: [
            ['SI-1', 'Kumar Stores', '1234.50', true],
            ['0042', null, 7, false],
          ],
        ),
      ));
      expect(cells[0].first, 'Sales register');
      expect(cells[1].first, 'From 2026-04-01 to 2026-04-30');
      expect(cells[3], ['Bill', 'Customer', 'Total', 'Paid']);
      expect(cells[4], ['SI-1', 'Kumar Stores', 1234.5, 'Yes']);
      // A bill number that happens to be digits is not a figure: it sits in
      // a text column, so its leading zeros survive.
      expect(cells[5], ['0042', null, 7, 'No']);
    });

    test('a file name keeps only what a file system takes', () {
      expect(
        workbookFileName(['customer-statement', 'Kumar & Sons / Guntur', '']),
        'customer-statement-Kumar-Sons-Guntur.xlsx',
      );
      expect(workbookFileName(const []), 'report.xlsx');
    });
  });

  testWidgets('a paged report is downloaded whole, not the page on show',
      (tester) async {
    tester.view.physicalSize = const Size(1600, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final ReportDefinition report = reportCatalog.firstWhere((report) =>
        report.area == ReportArea.operational &&
        report.needsPeriod &&
        !report.asOnDate &&
        report.onDateParam == null &&
        !report.needsSupplier &&
        !report.ownScreen &&
        report.openToReportView &&
        report.rowsKey == null &&
        report.columns.any((column) => column.numeric));
    final _PagedApi api = _PagedApi(report);
    final List<List<int>> saved = [];
    final List<String> names = [];
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Phase2Scope(
          child: ListViewRequestScope(
            request: ListViewRequest(
              path: 'reports/operational',
              view: report.id,
              serial: 1,
            ),
            child: ReportsWorkspace(
              api: api,
              permissions: _permissionsFor(const ['REPORT_VIEW']),
              hasActiveFirm: true,
              tabId: 'operational',
              saveFile: (name, bytes) async {
                names.add(name);
                saved.add(bytes);
                return 'C:/out/$name';
              },
            ),
          ),
        ),
      ),
    ));
    await tester.pumpAndSettle();
    api.pages.clear();

    await tester.tap(find.byKey(const ValueKey<String>('workbook-download')));
    await tester.pumpAndSettle();

    expect(api.pages, ['1', '2', '3']);
    expect(names.single, startsWith('${report.id}-'));
    expect(names.single, endsWith('.xlsx'));
    final List<List<Object?>> cells = _cells(saved.single);
    expect(cells[0].first, report.label);
    expect(cells[1].first, startsWith('From '));
    expect(cells[3], [for (final ReportColumn c in report.columns) c.label]);
    // Title, period, a blank line and the headings, then every row.
    expect(cells, hasLength(4 + _PagedApi.total));
    final int figure = report.columns.indexWhere((column) => column.numeric);
    expect(cells[4][figure], 1.5);
    expect(cells.last[figure], 250.5);
    expect(tester.takeException(), isNull);
  });

  testWidgets('the trial balance downloads the table and its Total line',
      (tester) async {
    tester.view.physicalSize = const Size(1400, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final List<List<int>> saved = [];
    final List<String> names = [];
    WorkbookDownloadButton.saveOverride = (name, bytes) async {
      names.add(name);
      saved.add(bytes);
      return 'C:/out/$name';
    };
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Phase2Scope(
          child: TrialBalancePage(
            api: _TrialBalanceApi(),
            permissions: _permissionsFor(const ['TRIAL_BALANCE_VIEW']),
            hasActiveFirm: true,
          ),
        ),
      ),
    ));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const ValueKey<String>('workbook-download')));
    await tester.pumpAndSettle();

    expect(names.single, startsWith('trial-balance-'));
    final List<List<Object?>> cells = _cells(saved.single);
    expect(cells[0].first, 'Trial balance');
    expect(cells[3].sublist(0, 3), ['Code', 'Account', 'Type']);
    expect(cells[4].sublist(0, 3), ['1200', 'Inventory', 'ASSET']);
    expect(cells[4][5], 8040);
    expect(cells[4][6], 1150.52);
    expect(cells.last[1], 'Total');
    expect(cells.last[7], 604976.7);
    expect(cells.last[8], 604976.7);
    expect(tester.takeException(), isNull);
  });
}
