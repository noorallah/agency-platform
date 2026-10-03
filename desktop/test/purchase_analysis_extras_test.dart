// The purchase analysis' extra controls: basis (billed, received, ordered),
// last year, the average rate, the chart, CSV and saved layouts -- and the
// rate trend. Each has to send exactly what was chosen and show only what
// the server supplied.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/purchases/purchase_analysis_page.dart';
import 'package:agency_desktop/ui/purchases/purchase_rate_trend_page.dart';
import 'package:agency_desktop/ui/workspace/export_file.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions() => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': <String>['PURCHASE_VIEW'],
  }));

Map<String, dynamic> _figures(double net) => {
      'quantity': 3,
      'taxable': net - 10,
      'tax': 10,
      'net': net,
      'invoices': 1,
      'average_bill': net,
      'average_rate': (net - 10) / 3,
    };

Map<String, dynamic> _pivot({bool previous = false}) => {
      'rows': [
        {'key': 's-1', 'label': 'Acme Supplies'},
      ],
      'columns': [
        {'key': '', 'label': 'Total'},
      ],
      'cells': [
        {'row': 's-1', 'column': '', 'figures': _figures(200)},
      ],
      'row_totals': {'s-1': _figures(200)},
      'column_totals': {'': _figures(200)},
      'grand_total': _figures(200),
      if (previous)
        'previous': {
          'rows': [
            {'key': 's-1', 'label': 'Acme Supplies'},
          ],
          'columns': [
            {'key': '', 'label': 'Total'},
          ],
          'cells': [],
          'row_totals': {'s-1': _figures(100)},
          'column_totals': {'': _figures(100)},
          'grand_total': _figures(100),
        },
    };

class _Api extends ApiClient {
  _Api()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Map<String, String>> queries = [];
  final List<Map<String, String>> trendQueries = [];
  final List<Json> saved = [];

  @override
  Future<Json> request(
    String method,
    String path, {
    Json? body,
    Map<String, String>? query,
    bool authenticated = true,
    bool retrying = false,
    int? expectedVersion,
  }) async {
    if (path == '/api/v1/report-layouts') {
      if (method == 'POST') {
        saved.add(body!);
        return {
          'data': {...body, 'id': 'l-2', 'version': 1},
        };
      }
      return {'data': <Map<String, dynamic>>[]};
    }
    if (path.endsWith('/analysis/bills')) return {'data': <dynamic>[]};
    if (path.endsWith('/reports/rate-trend')) {
      trendQueries.add(query ?? {});
      return {
        'data': [
          for (final (i, rate) in [100.0, 90.0, 110.0].indexed)
            {
              'bill_id': 'b-$i',
              'bill_number': 'PB-00$i',
              'bill_date': '2026-0${i + 1}-10',
              'supplier_id': 's-1',
              'supplier_name': 'Acme Supplies',
              'quantity': 5,
              'rate': rate,
            },
        ],
      };
    }
    if (path == '/api/v1/products') {
      return {
        'data': [
          {'id': 'p-1', 'name': 'Basmati 25kg', 'sku': 'B1'},
        ],
        'pagination': {
          'page': 1,
          'page_size': 50,
          'total_records': 1,
          'total_pages': 1,
        },
      };
    }
    queries.add(query ?? {});
    return {
      'data': _pivot(previous: query?['compare_previous_year'] == 'true'),
    };
  }
}

Future<void> _pump(
  WidgetTester tester,
  _Api api, {
  SaveExportOverride? export,
}) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: PurchaseAnalysisPage(
        api: api,
        permissions: _permissions(),
        hasActiveFirm: true,
        today: DateTime(2026, 10, 15),
        saveExportOverride: export,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('basis is sent, and only billed can be drilled into',
      (tester) async {
    final api = _Api();
    await _pump(tester, api);
    expect(api.queries.single['basis'], 'billed');

    await tester
        .tap(find.widgetWithText(DropdownButtonFormField<String>, 'Basis'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Received').last);
    await tester.pumpAndSettle();
    expect(api.queries.last['basis'], 'received');

    await tester.tap(find.text('200.00').first);
    await tester.pumpAndSettle();
    expect(find.byType(AlertDialog), findsNothing);

    await tester
        .tap(find.widgetWithText(DropdownButtonFormField<String>, 'Basis'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Ordered').last);
    await tester.pumpAndSettle();
    expect(api.queries.last['basis'], 'ordered');
    await tester.tap(find.text('200.00').first);
    await tester.pumpAndSettle();
    expect(find.byType(AlertDialog), findsNothing);
  });

  testWidgets('billed can still be drilled into', (tester) async {
    await _pump(tester, _Api());
    await tester.tap(find.text('200.00').first);
    await tester.pumpAndSettle();
    expect(find.byType(AlertDialog), findsOneWidget);
  });

  testWidgets('last year and the change are shown when compared',
      (tester) async {
    final api = _Api();
    await _pump(tester, api);
    await tester.tap(find.text('Compare with last year'));
    await tester.pumpAndSettle();
    expect(api.queries.last['compare_previous_year'], 'true');
    expect(find.text('Last year'), findsOneWidget);
    expect(find.text('+100.0%'), findsWidgets);
  });

  testWidgets('the average rate is a column and there is no margin',
      (tester) async {
    await _pump(tester, _Api());
    expect(find.text('Avg rate'), findsOneWidget);
    expect(find.text('63.33'), findsWidgets);
    expect(find.text('Margin'), findsNothing);
  });

  testWidgets('Save as files the layout under purchase_analysis',
      (tester) async {
    final api = _Api();
    await _pump(tester, api);
    await tester.tap(find.text('Layouts'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Save as...'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).last, 'Buying view');
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();
    final Json body = api.saved.single;
    expect(body['report_code'], 'purchase_analysis');
    expect(body['name'], 'Buying view');
    expect((body['settings'] as Map)['basis'], 'billed');
  });

  testWidgets('the chart and export are on offer', (tester) async {
    String? name;
    await _pump(tester, _Api(), export: (suggested, text) async {
      name = suggested;
      return 'C:/out/$suggested';
    });
    await tester.tap(find.byTooltip('Show a chart'));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('analysis-chart')), findsOneWidget);
    await tester.tap(find.byTooltip('Export to CSV'));
    await tester.pumpAndSettle();
    expect(name, 'purchase-analysis.csv');
  });

  testWidgets('the rate trend asks for the product and shows the summary',
      (tester) async {
    tester.view.physicalSize = const Size(1366, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final api = _Api();
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: PurchaseRateTrendPage(
          api: api,
          permissions: _permissions(),
          hasActiveFirm: true,
        ),
      ),
    ));
    await tester.pumpAndSettle();
    expect(api.trendQueries, isEmpty);
    expect(find.text('Choose a product'), findsWidgets);

    await tester.tap(find.byKey(const ValueKey('rate-trend-product')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Basmati 25kg'));
    await tester.pumpAndSettle();

    expect(api.trendQueries.single['product_id'], 'p-1');
    expect(api.trendQueries.single.containsKey('supplier_id'), isFalse);
    expect(find.byKey(const ValueKey('rate-trend-chart')), findsOneWidget);
    expect(find.text('PB-001'), findsOneWidget);
    expect(find.text('Acme Supplies'), findsNWidgets(3));
    // Lowest 90, highest 110, last 110, +10.0% since the first (100).
    expect(find.text('90.00'), findsWidgets);
    expect(find.text('110.00'), findsWidgets);
    expect(find.text('+10.0%'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
