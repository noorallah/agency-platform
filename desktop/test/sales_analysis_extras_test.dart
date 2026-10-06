// The sales analysis' extra controls: basis, filters, margin, last year, the
// chart, CSV and saved layouts. Each has to send exactly what was chosen and
// show only what the server supplied.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/sales/sales_analysis_page.dart';
import 'package:agency_desktop/ui/workspace/analysis_page.dart';
import 'package:agency_desktop/ui/workspace/export_file.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions() => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': <String>['SALES_VIEW'],
  }));

Map<String, dynamic> _figures(double net, {bool margin = false}) => {
      'quantity': 3,
      'taxable': net - 10,
      'tax': 10,
      'net': net,
      'invoices': 1,
      'average_bill': net,
      if (margin) ...{
        'cost': net / 2,
        'margin': net / 2,
        'margin_percent': 50,
      },
    };

Map<String, dynamic> _pivot({
  bool margin = false,
  bool previous = false,
}) =>
    {
      'rows': [
        {'key': 'c-1', 'label': 'Acme Traders'},
      ],
      'columns': [
        {'key': '', 'label': 'Total'},
      ],
      'cells': [
        {'row': 'c-1', 'column': '', 'figures': _figures(200, margin: margin)},
      ],
      'row_totals': {'c-1': _figures(200, margin: margin)},
      'column_totals': {'': _figures(200, margin: margin)},
      'grand_total': _figures(200, margin: margin),
      if (previous)
        'previous': {
          'rows': [
            {'key': 'c-1', 'label': 'Acme Traders'},
          ],
          'columns': [
            {'key': '', 'label': 'Total'},
          ],
          'cells': [],
          'row_totals': {'c-1': _figures(100)},
          'column_totals': {'': _figures(100)},
          'grand_total': _figures(100),
        },
    };

class _Api extends ApiClient {
  _Api({this.margin = false})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final bool margin;
  final List<Map<String, String>> queries = [];
  final List<Json> saved = [];
  final List<String> deleted = [];
  final List<Map<String, dynamic>> layouts = [
    {
      'id': 'l-1',
      'report_code': 'sales_analysis',
      'name': 'Orders by group',
      'version': 1,
      'settings': {
        'rows': 'customer_group',
        'columns': null,
        'basis': 'ordered',
        'net_of_returns': false,
        'compare_previous_year': true,
        'filters': {'brand_id': 'b-9'},
        'filter_labels': {'brand_id': 'Surf'},
        'from_date': '2026-04-01',
        'to_date': '2026-09-30',
      },
    },
  ];

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
        return {'data': {...body, 'id': 'l-2', 'version': 1}};
      }
      return {'data': layouts};
    }
    if (path.startsWith('/api/v1/report-layouts/')) {
      deleted.add(path.split('/').last);
      return {};
    }
    if (path == '/api/v1/customers/groups') {
      return {
        'data': [
          {'id': 'g-1', 'code': 'RET', 'name': 'Retailers'},
        ],
      };
    }
    if (path.endsWith('/analysis/invoices')) return {'data': []};
    queries.add(query ?? {});
    return {
      'data': _pivot(
        margin: margin && query?['basis'] != 'ordered',
        previous: query?['compare_previous_year'] == 'true',
      ),
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
      body: SalesAnalysisPage(
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
  testWidgets('basis is sent, and orders booked cannot be drilled into',
      (tester) async {
    final api = _Api();
    await _pump(tester, api);
    expect(api.queries.single['basis'], 'billed');
    expect(api.queries.single.containsKey('compare_previous_year'), isFalse);

    await tester.tap(find.widgetWithText(DropdownButtonFormField<String>, 'Basis'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Orders booked').last);
    await tester.pumpAndSettle();
    expect(api.queries.last['basis'], 'ordered');

    // Drilling is for invoices; an order figure opens nothing.
    await tester.tap(find.text('200.00').first);
    await tester.pumpAndSettle();
    expect(find.byType(AlertDialog), findsNothing);
  });

  testWidgets('no margin columns when the server sends no margin',
      (tester) async {
    await _pump(tester, _Api());
    expect(find.text('Margin'), findsNothing);
    expect(find.text('Cost'), findsNothing);
  });

  testWidgets('margin columns appear when the server sends a margin',
      (tester) async {
    await _pump(tester, _Api(margin: true));
    expect(find.text('Cost'), findsOneWidget);
    expect(find.text('Margin'), findsOneWidget);
    expect(find.text('Margin %'), findsOneWidget);
    expect(find.text('50.0%'), findsWidgets);
  });

  testWidgets('comparing with last year shows last year and the change',
      (tester) async {
    final api = _Api();
    await _pump(tester, api);
    await tester.tap(find.text('Compare with last year'));
    await tester.pumpAndSettle();

    expect(api.queries.last['compare_previous_year'], 'true');
    expect(find.text('Last year'), findsOneWidget);
    expect(find.text('Change %'), findsOneWidget);
    expect(find.text('100.00'), findsWidgets);
    expect(find.text('+100.0%'), findsWidgets);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a picked filter is sent, shown as a chip, and removable',
      (tester) async {
    final api = _Api();
    await _pump(tester, api);

    await tester.tap(find.text('Add filter'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Customer group').last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Retailers'));
    await tester.pumpAndSettle();

    expect(api.queries.last['customer_group_id'], 'g-1');
    expect(find.text('Customer group: Retailers'), findsOneWidget);

    await tester.tap(find.descendant(
      of: find.byType(InputChip),
      matching: find.byType(Icon),
    ));
    await tester.pumpAndSettle();
    expect(api.queries.last.containsKey('customer_group_id'), isFalse);
  });

  testWidgets('the chart shows the row totals as bars', (tester) async {
    await _pump(tester, _Api());
    await tester.tap(find.byTooltip('Show a chart'));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('analysis-chart')), findsOneWidget);
    expect(find.text('Acme Traders'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('export hands the visible grid to the save dialog as CSV',
      (tester) async {
    String? name;
    String? content;
    await _pump(tester, _Api(margin: true), export: (suggested, text) async {
      name = suggested;
      content = text;
      return 'C:/out/$suggested';
    });
    await tester.tap(find.byTooltip('Export to CSV'));
    await tester.pumpAndSettle();

    expect(name, 'sales-analysis.csv');
    final List<String> lines = content!.split('\r\n');
    expect(lines.first, 'Customer,Total,Cost,Margin,Margin %');
    expect(lines[1], 'Acme Traders,200.00,100.00,100.00,50.0%');
    expect(lines.last, startsWith('Total,'));
    expect(find.textContaining('Export saved to'), findsOneWidget);
  });

  test('analysisCsv quotes what needs quoting', () {
    expect(
      analysisCsv(['A', 'B'], [
        ['x, y', 'say "hi"'],
      ]),
      'A,B\r\n"x, y","say ""hi"""',
    );
  });

  testWidgets('Save as posts report_code, name and the screen settings',
      (tester) async {
    final api = _Api();
    await _pump(tester, api);
    await tester.tap(find.text('Layouts'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Save as...'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).last, 'My view');
    await tester.pump();
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();

    final Json body = api.saved.single;
    expect(body.keys.toSet(), {'report_code', 'name', 'settings'});
    expect(body['report_code'], 'sales_analysis');
    expect(body['name'], 'My view');
    final settings = body['settings'] as Map<String, dynamic>;
    expect(settings['rows'], 'customer');
    expect(settings['basis'], 'billed');
    expect(settings['net_of_returns'], true);
    expect(settings['from_date'], '2026-10-01');
  });

  testWidgets('opening a layout asks again with its parameters',
      (tester) async {
    final api = _Api();
    await _pump(tester, api);
    await tester.tap(find.text('Layouts'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Orders by group'));
    await tester.pumpAndSettle();

    final Map<String, String> q = api.queries.last;
    expect(q['rows'], 'customer_group');
    expect(q['basis'], 'ordered');
    expect(q['net_of_returns'], 'false');
    expect(q['compare_previous_year'], 'true');
    expect(q['brand_id'], 'b-9');
    expect(q['from_date'], '2026-04-01');
    expect(q['to_date'], '2026-09-30');
    expect(find.text('Brand: Surf'), findsOneWidget);
  });

  testWidgets('a layout can be deleted', (tester) async {
    final api = _Api();
    await _pump(tester, api);
    await tester.tap(find.text('Layouts'));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Delete Orders by group'));
    await tester.pumpAndSettle();
    expect(api.deleted, ['l-1']);
  });
}
