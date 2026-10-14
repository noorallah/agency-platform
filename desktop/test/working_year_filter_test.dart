// The working year is a filter, not a wall (the owner, 2026-10-13; IMP-3,
// backlog 155): a list of documents opens on the firm's current financial
// year, every date is one choice away, and nothing has to be switched to
// reach an older bill.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/sales/sales_order_management_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

class _OrdersApi extends ApiClient {
  _OrdersApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  /// The dates each list request asked for, `from..to`; '' for every date.
  final List<String> spans = [];

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
    if (path.endsWith('/summary')) {
      return <String, dynamic>{
        'data': <String, dynamic>{'total': 1, 'draft': 1},
      };
    }
    if (path == '/api/v1/sales-orders') {
      final String? from = query?['order_from'];
      final String? to = query?['order_to'];
      spans.add(from == null && to == null ? '' : '$from..$to');
    }
    return <String, dynamic>{
      'data': const <Json>[],
      'pagination': <String, dynamic>{'total_records': 0},
    };
  }
}

PermissionService _permissions() {
  final String payload = base64Url.encode(utf8.encode(jsonEncode({
    'permissions': ['SALES_VIEW'],
    'roles': const <String>[],
  })));
  return PermissionService()..applyAccessToken('h.$payload.s');
}

Future<_OrdersApi> _pump(
  WidgetTester tester, {
  ListViewRequest? request,
  int? yearStartMonth,
}) async {
  tester.view.physicalSize = const Size(1600, 1000);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final Directory temp = Directory.systemTemp.createTempSync('working-year');
  addTearDown(() => temp.deleteSync(recursive: true));
  final _OrdersApi api = _OrdersApi();
  Widget page = ListViewRequestScope(
    request: request,
    child: SalesOrderManagementPage(
      api: api,
      preferences: DesktopPreferencesService(directory: temp),
      permissions: _permissions(),
      hasActiveFirm: true,
    ),
  );
  if (yearStartMonth != null) {
    page = FirmYearScope(startMonth: yearStartMonth, child: page);
  }
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(body: Phase2Scope(child: page)),
  ));
  await tester.pumpAndSettle();
  return api;
}

String _span(DatePeriod p) =>
    '${DatePeriod.iso(p.from!)}..${DatePeriod.iso(p.to!)}';

void main() {
  test('a year that does not begin in April is the firm\'s own', () {
    final DateTime today = DateTime(2026, 10, 14);
    expect(
        _span(DatePeriod.of(PeriodKind.financialYear, today,
            yearStartMonth: DateTime.january)),
        '2026-01-01..2026-12-31');
    expect(
        _span(DatePeriod.of(PeriodKind.lastFinancialYear, today,
            yearStartMonth: DateTime.july)),
        '2025-07-01..2026-06-30');
    // A July year's quarters are Jul-Sep, Oct-Dec, Jan-Mar, Apr-Jun.
    expect(
        _span(DatePeriod.of(PeriodKind.quarter, DateTime(2026, 11, 3),
            yearStartMonth: DateTime.july)),
        '2026-10-01..2026-12-31');
    // A February year's: Feb-Apr, May-Jul, Aug-Oct, Nov-Jan.
    expect(
        _span(DatePeriod.of(PeriodKind.quarter, DateTime(2027, 1, 20),
            yearStartMonth: DateTime.february)),
        '2026-11-01..2027-01-31');
    expect(
        _span(DatePeriod.of(PeriodKind.financialYear, DateTime(2027, 1, 20),
            yearStartMonth: DateTime.february)),
        '2026-02-01..2027-01-31');
    // The button names the year only in the firm's own terms.
    final DatePeriod january = DatePeriod.of(PeriodKind.financialYear, today,
        yearStartMonth: DateTime.january);
    expect(january.label(today, yearStartMonth: DateTime.january),
        'This financial year');
    expect(january.label(today), '01-01-2026 – 31-12-2026');
  });

  test('the firm list says which month the year begins with', () {
    expect(
        AssignedFirm.fromJson(const {
          'id': 'f',
          'code': 'F',
          'name': 'Firm',
          'is_primary': true,
          'financial_year_start': '2025-01-01',
        }).financialYearStartMonth,
        DateTime.january);
    // An older server says nothing: April.
    expect(
        AssignedFirm.fromJson(const {
          'id': 'f',
          'code': 'F',
          'name': 'Firm',
          'is_primary': true,
        }).financialYearStartMonth,
        DateTime.april);
  });

  testWidgets('a list opens on the current financial year', (tester) async {
    final _OrdersApi api = await _pump(tester);
    final DatePeriod year =
        DatePeriod.of(PeriodKind.financialYear, DateTime.now());
    expect(api.spans, [_span(year)]);
    expect(find.text('This financial year'), findsOneWidget);
  });

  testWidgets('and on the firm\'s own year where that is not April',
      (tester) async {
    final _OrdersApi api =
        await _pump(tester, yearStartMonth: DateTime.january);
    final int year = DateTime.now().year;
    expect(api.spans, ['$year-01-01..$year-12-31']);
    expect(find.text('This financial year'), findsOneWidget);
  });

  testWidgets('an older bill is one step back, or every date',
      (tester) async {
    final _OrdersApi api = await _pump(tester);
    final DatePeriod year =
        DatePeriod.of(PeriodKind.financialYear, DateTime.now());

    await tester.tap(find.byKey(const ValueKey('period-back')));
    await tester.pumpAndSettle();
    expect(api.spans.last, _span(year.shifted(-1)));

    await tester.tap(find.byKey(const ValueKey('period-button')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('period-all')));
    await tester.pumpAndSettle();
    expect(api.spans.last, '');
    expect(find.text('All dates'), findsOneWidget);
  });

  testWidgets('opened from Home for a reason, a list shows every date',
      (tester) async {
    // Home counted the drafts over every date; one waiting since last year
    // is still waiting.
    final _OrdersApi api = await _pump(
      tester,
      request: const ListViewRequest(
          path: 'salesOrders', view: 'draft', serial: 1),
    );
    expect(api.spans.last, '');
    expect(find.text('All dates'), findsOneWidget);
  });

  testWidgets('dates that hold nothing say so, and a search says its own',
      (tester) async {
    final DatePeriod year =
        DatePeriod.of(PeriodKind.financialYear, DateTime(2026, 10, 14));
    Future<void> show(DatePeriod period, {required bool searching}) async {
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: PeriodEmptyState(period: period, searching: searching),
        ),
      ));
      await tester.pump(const Duration(seconds: 1));
    }

    await show(year, searching: false);
    expect(find.text('Nothing in these dates'), findsOneWidget);
    expect(find.textContaining('All dates'), findsOneWidget);

    await show(year, searching: true);
    expect(find.text('No search results'), findsOneWidget);

    await show(const DatePeriod.all(), searching: false);
    expect(find.text('No search results'), findsOneWidget);
  });
}
