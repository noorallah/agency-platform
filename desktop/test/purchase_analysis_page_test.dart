// Purchase analysis is a view: the screen chooses a shape and a period, and has
// to send exactly what was chosen -- and drill down with exactly the cell's
// own row and column, not the whole period.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/purchases/purchase_analysis_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions({List<String> perms = const ['PURCHASE_VIEW']}) =>
    PermissionService()
      ..applyAccessToken(_accessToken({
        'roles': <String>['user'],
        'permissions': perms,
      }));

Map<String, dynamic> _figures(double net, int invoices) => {
      'quantity': 3,
      'taxable': net - 10,
      'tax': 10,
      'net': net,
      'invoices': invoices,
      'average_bill': invoices == 0 ? null : net / invoices,
    };

Map<String, dynamic> _pivot() => {
      'rows': [
        {'key': 's-1', 'label': 'Acme Supplies'},
        {'key': '', 'label': ''},
      ],
      'columns': [
        {
          'key': '2026-10',
          'label': 'Oct 2026',
          'from_date': '2026-10-01',
          'to_date': '2026-10-31',
        },
      ],
      'cells': [
        {'row': 's-1', 'column': '2026-10', 'figures': _figures(111, 1)},
        {'row': '', 'column': '2026-10', 'figures': _figures(222, 2)},
      ],
      'row_totals': {'s-1': _figures(111, 1), '': _figures(222, 2)},
      'column_totals': {'2026-10': _figures(333, 3)},
      'grand_total': _figures(333, 3),
    };

class _PurchaseAnalysisApi extends ApiClient {
  _PurchaseAnalysisApi({this.empty = false})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final bool empty;
  final List<Map<String, String>> analysisQueries = [];
  final List<Map<String, String>> billQueries = [];

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
    if (path.endsWith('/analysis/bills')) {
      billQueries.add(query ?? {});
      return {
        'data': [
          {
            'id': 'b-1',
            'invoice_number': 'PI-2026-0042',
            'invoice_date': '2026-10-05',
            'vendor_id': 's-1',
            'net': 111,
          },
        ],
      };
    }
    expect(path, startsWith('/api/v1/purchase-invoices/reports/analysis'));
    analysisQueries.add(query ?? {});
    if (empty) {
      return {
        'data': {
          'rows': [],
          'columns': [],
          'cells': [],
          'row_totals': <String, dynamic>{},
          'column_totals': <String, dynamic>{},
          'grand_total': _figures(0, 0),
        },
      };
    }
    // Without columns the server answers a single "Total" column.
    final Map<String, dynamic> pivot = _pivot();
    if (query?['columns'] == null) {
      pivot['columns'] = [
        {'key': '', 'label': 'Total'},
      ];
    }
    return {'data': pivot};
  }
}

Future<void> _pump(
  WidgetTester tester,
  _PurchaseAnalysisApi api, {
  Size size = const Size(1366, 768),
}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: PurchaseAnalysisPage(
        api: api,
        permissions: _permissions(),
        hasActiveFirm: true,
        today: DateTime(2026, 10, 15),
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

Future<void> _choose(WidgetTester tester, String field, String option) async {
  await tester.tap(find.widgetWithText(DropdownButtonFormField<String>, field));
  await tester.pumpAndSettle();
  await tester.tap(find.text(option).last);
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('the pivot shows labels, headings, cells and the total row',
      (tester) async {
    final api = _PurchaseAnalysisApi();
    await _pump(tester, api);

    expect(api.analysisQueries.single['rows'], 'supplier');
    expect(api.analysisQueries.single.containsKey('columns'), isFalse);
    expect(api.analysisQueries.single['from_date'], '2026-10-01');
    expect(api.analysisQueries.single['to_date'], '2026-10-15');
    expect(api.analysisQueries.single['net_of_returns'], 'true');

    expect(find.text('Acme Supplies'), findsOneWidget);
    expect(find.text('(none)'), findsOneWidget);
    // One column heading: the "Total" the server sends, plus our own.
    expect(find.text('Total'), findsWidgets);
    expect(find.text('Total').evaluate().length, greaterThanOrEqualTo(2));
    expect(find.text('111.00'), findsWidgets);
    expect(find.text('333.00'), findsWidgets);
    expect(tester.takeException(), isNull);
  });

  testWidgets('changing Rows and Columns asks again with those dimensions',
      (tester) async {
    final api = _PurchaseAnalysisApi();
    await _pump(tester, api);

    await _choose(tester, 'Rows', 'Product');
    expect(api.analysisQueries.last['rows'], 'product');

    await _choose(tester, 'Columns', 'Month');
    expect(api.analysisQueries.last['rows'], 'product');
    expect(api.analysisQueries.last['columns'], 'month');
    expect(find.text('Oct 2026'), findsOneWidget);

    await _choose(tester, 'Columns', 'None');
    expect(api.analysisQueries.last.containsKey('columns'), isFalse);
  });

  testWidgets('Net of returns off is sent as false', (tester) async {
    final api = _PurchaseAnalysisApi();
    await _pump(tester, api);

    await tester.tap(find.byType(Switch));
    await tester.pumpAndSettle();
    expect(api.analysisQueries.last['net_of_returns'], 'false');
  });

  testWidgets('a cell opens the bills behind it, narrowed to its row and '
      'column', (tester) async {
    final api = _PurchaseAnalysisApi();
    await _pump(tester, api);
    await _choose(tester, 'Columns', 'Month');

    await tester.tap(find.text('111.00').first);
    await tester.pumpAndSettle();

    final Map<String, String> query = api.billQueries.single;
    expect(query['supplier_id'], 's-1');
    expect(query['from_date'], '2026-10-01');
    expect(query['to_date'], '2026-10-15', reason: 'clipped to the period');
    expect(find.text('PI-2026-0042'), findsOneWidget);
  });

  testWidgets('a row with no key cannot be drilled into', (tester) async {
    final api = _PurchaseAnalysisApi();
    await _pump(tester, api);

    await tester.tap(find.text('222.00').first);
    await tester.pumpAndSettle();
    expect(api.billQueries, isEmpty);
  });

  testWidgets('an empty period says so', (tester) async {
    await _pump(tester, _PurchaseAnalysisApi(empty: true));
    expect(find.text('Nothing bought in this period'), findsOneWidget);
  });

  testWidgets('it fits an 800x600 window', (tester) async {
    final api = _PurchaseAnalysisApi();
    await _pump(tester, api, size: const Size(800, 600));
    await _choose(tester, 'Columns', 'Month');
    expect(tester.takeException(), isNull);
  });
}
