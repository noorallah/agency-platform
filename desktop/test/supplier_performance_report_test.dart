import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/report.dart';
import 'package:agency_desktop/models/vendor.dart';
import 'package:agency_desktop/ui/reports/report_catalog.dart';
import 'package:agency_desktop/ui/reports/reports_workspace.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show ListViewRequest, ListViewRequestScope, Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// BUY-12: the supplier performance report and the supplier price trend.
PermissionService _permissions() {
  final String payload = base64Url.encode(
    utf8.encode(jsonEncode({
      'permissions': ['PURCHASE_VIEW'],
    })),
  );
  return PermissionService()..applyAccessToken('h.$payload.s');
}

class _Api extends ApiClient {
  _Api(this.rows)
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Json> rows;
  final List<String> requested = [];
  final List<Map<String, String>?> queries = [];

  @override
  Future<ReportPage> reportRows(
    String path, {
    Map<String, String>? query,
    String? rowsKey,
  }) async {
    requested.add(path);
    queries.add(query);
    return ReportPage(rows: rows, total: rows.length);
  }

  @override
  Future<PagedResult<Vendor>> vendors({
    int page = 1,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    VendorQuery filters = const VendorQuery(),
  }) async =>
      PagedResult(items: [
        Vendor.fromJson({'id': 'v-1', 'name': 'Acme Traders'}),
      ], total: 1);
}

Future<void> _open(WidgetTester tester, _Api api, String view) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Phase2Scope(
        child: ListViewRequestScope(
          request: ListViewRequest(
              path: 'reports/operational', view: view, serial: 1),
          child: ReportsWorkspace(
            api: api,
            permissions: _permissions(),
            hasActiveFirm: true,
            tabId: 'operational',
          ),
        ),
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

void main() {
  test('both reports are in the catalogue', () {
    final ReportDefinition performance =
        reportCatalog.firstWhere((r) => r.id == 'supplier-performance');
    final ReportDefinition trend =
        reportCatalog.firstWhere((r) => r.id == 'supplier-price-trend');
    expect(performance.needsPeriod, isTrue);
    expect(performance.needsSupplier, isFalse);
    expect(trend.needsSupplier, isTrue);
  });

  testWidgets('performance sends the window, a page, and shows a row',
      (tester) async {
    final _Api api = _Api([
      {
        'vendor_id': 'v-1',
        'vendor_name': 'Acme Traders',
        'receipts': 4,
        'on_time_percent': 75,
        'rejected_percent': null,
        'returned_percent': 2.5,
        'short_percent': 10,
      },
    ]);
    await _open(tester, api, 'supplier-performance');
    expect(api.requested.last,
        '/api/v1/purchases/reports/supplier-performance');
    final Map<String, String> query = api.queries.last!;
    expect(query.keys,
        containsAll(['from_date', 'to_date', 'page', 'page_size']));
    expect(query.containsKey('vendor_id'), isFalse);
    expect(find.text('Acme Traders'), findsOneWidget);
    expect(find.text('On time %'), findsOneWidget);
    expect(find.text('Short %'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('price trend asks nothing until a supplier is chosen, then '
      'sends vendor_id', (tester) async {
    final _Api api = _Api([
      {'month': '2026-09', 'quantity': 40, 'average_rate': 12.5},
    ]);
    await _open(tester, api, 'supplier-price-trend');
    expect(api.requested.where((p) => p.contains('price-trend')), isEmpty);

    await tester.tap(find.byKey(const ValueKey<String>('report-supplier')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Acme Traders').last);
    await tester.pumpAndSettle();

    expect(api.requested.last,
        '/api/v1/purchases/reports/supplier-price-trend');
    expect(api.queries.last!['vendor_id'], 'v-1');
    expect(api.queries.last!.containsKey('page'), isFalse);
    expect(find.text('2026-09'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
