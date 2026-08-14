import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/report.dart';
import 'package:agency_desktop/ui/reports/report_catalog.dart';
import 'package:agency_desktop/ui/reports/reports_workspace.dart';
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
  _ReportApi({this.rows = const []})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Json> rows;
  final List<String> requested = [];

  @override
  Future<List<Json>> reportRows(String path) async {
    requested.add(path);
    return rows;
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
      final List<ReportColumn> columns =
          columnsFor(plain, [
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
        columns: [ReportColumn(key: 'invoice_id', label: 'Reference')],
      );
      expect(columnsFor(named, [{'invoice_id': 'abc'}]).single.label, 'Reference');
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

      expect(api.requested.single, reportsFor(ReportArea.operational).first.path);
      expect(find.text('SI-1'), findsOneWidget);
      expect(find.text('1 row(s)'), findsOneWidget);
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
    });

    testWidgets('without REPORT_VIEW there is nothing to show', (tester) async {
      await _pump(tester, _ReportApi(), perms: const ['SALES_VIEW']);
      expect(find.textContaining('do not have permission'), findsOneWidget);
    });
  });
}
