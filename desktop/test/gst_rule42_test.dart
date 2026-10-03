// GST-4, desktop half: rule 42 (common credit for exempt sales).
//
// Pins: the period figures render; the post body carries exactly the keys the
// server declares; REPORT mode hides Post and OFF says it is switched off; a
// take-back sends its reason; the year view shows already reversed and the
// difference; the screen fits 800x600.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/sales/rule42_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

PermissionService _permissions(List<String> codes) {
  final String payload =
      base64Url.encode(utf8.encode(jsonEncode({'permissions': codes})));
  return PermissionService()..applyAccessToken('h.$payload.s');
}

Json _heads(String igst, String cgst, String sgst, String cess) =>
    {'igst': igst, 'cgst': cgst, 'sgst': sgst, 'cess': cess};

Json _record(String id, String status) => {
      'id': id,
      'kind': 'MONTHLY',
      'period_from': '2026-09-01',
      'period_to': '2026-09-30',
      'movement_date': '2026-09-30',
      'exempt_turnover': '25000.00',
      'total_turnover': '100000.00',
      'common': _heads('0.00', '900.00', '900.00', '0.00'),
      'reversed': _heads('0.00', '225.00', '225.00', '0.00'),
      'status': status,
      'journal_entry_id': 'j-1',
      'reversal_journal_entry_id': null,
      'reversal_reason': null,
      'reversed_at': null,
      'version': 1,
    };

class _Api extends ApiClient {
  _Api({this.mode = 'POST'})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final String mode;
  final List<String> askedPeriods = [];
  final List<String> askedYears = [];
  final List<Json> periodPosts = [];
  final List<Json> annualPosts = [];
  final List<Json> reversals = [];

  Json _figures() => {
        'mode': mode,
        'period_from': '2026-09-01',
        'period_to': '2026-09-30',
        'exempt_turnover': '25000.00',
        'total_turnover': '100000.00',
        'exempt_share': '0.25',
        'common': _heads('0.00', '900.00', '900.00', '0.00'),
        'reversal': _heads('0.00', '225.00', '225.00', '0.00'),
        'posted': null,
      };

  @override
  Future<Json> rule42Period(String returnPeriod) async {
    askedPeriods.add(returnPeriod);
    return _figures();
  }

  @override
  Future<Json> rule42Annual(String financialYear) async {
    askedYears.add(financialYear);
    return {
      ..._figures(),
      'already_reversed': _heads('0.00', '200.00', '200.00', '0.00'),
      'difference': _heads('0.00', '25.00', '-40.00', '0.00'),
    };
  }

  @override
  Future<List<Json>> rule42Posted() async =>
      [_record('r-1', 'POSTED'), _record('r-2', 'REVERSED')];

  @override
  Future<Json> postRule42Period(String returnPeriod,
      {String? postingDate}) async {
    periodPosts.add({
      'return_period': returnPeriod,
      if (postingDate != null) 'posting_date': postingDate,
    });
    return _record('r-3', 'POSTED');
  }

  @override
  Future<Json> postRule42Annual(String financialYear, String postingDate) async {
    annualPosts.add({'financial_year': financialYear, 'posting_date': postingDate});
    return _record('r-4', 'POSTED');
  }

  @override
  Future<Json> reverseRule42(String id, String reason) async {
    reversals.add({'id': id, 'reason': reason});
    return _record(id, 'REVERSED');
  }
}

Future<void> _pump(
  WidgetTester tester,
  _Api api, {
  List<String> codes = const ['ACCOUNT_VIEW', 'JOURNAL_POST'],
  Size size = const Size(1366, 768),
}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Rule42Page(
        api: api,
        permissions: _permissions(codes),
        hasActiveFirm: true,
        today: DateTime(2026, 10, 3),
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('shows last month with the arithmetic and the heads',
      (tester) async {
    final _Api api = _Api();
    await _pump(tester, api);

    expect(api.askedPeriods.single, '2026-09');
    expect(find.text('25000.00'), findsOneWidget);
    expect(find.text('100000.00'), findsOneWidget);
    expect(find.text('25.00%'), findsOneWidget);
    expect(find.text('Common credit (C2)'), findsOneWidget);
    expect(find.text('Reversal (D1)'), findsOneWidget);
    expect(find.text('900.00'), findsNWidgets(2));
    expect(find.text('1800.00'), findsOneWidget);
    expect(find.text('450.00'), findsNWidgets(3)); // total + two posted rows
    expect(find.text('Already reversed'), findsNothing);
    expect(find.byKey(const ValueKey('rule42-report-note')), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('the posted list shows both rows, take back only on posted',
      (tester) async {
    await _pump(tester, _Api());
    expect(find.text('Monthly'), findsNWidgets(2));
    expect(find.text('Posted'), findsNWidgets(2)); // heading + badge
    expect(find.text('Taken back'), findsOneWidget);
    expect(find.byKey(const ValueKey('rule42-takeback-r-1')), findsOneWidget);
    expect(find.byKey(const ValueKey('rule42-takeback-r-2')), findsNothing);
  });

  testWidgets('posting a month sends exactly return_period', (tester) async {
    final _Api api = _Api();
    await _pump(tester, api);

    await tester.tap(find.byKey(const ValueKey('rule42-post')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('rule42-post-confirm')));
    await tester.pumpAndSettle();

    expect(api.periodPosts, [
      {'return_period': '2026-09'},
    ]);
    expect(api.askedPeriods, hasLength(2));
  });

  testWidgets('year view shows already reversed and the difference',
      (tester) async {
    final _Api api = _Api();
    await _pump(tester, api);

    await tester.tap(find.text('Year'));
    await tester.pumpAndSettle();
    expect(api.askedYears.single, '2026-27');
    expect(find.text('Already reversed'), findsOneWidget);
    expect(find.text('Difference'), findsOneWidget);
    expect(find.text('40.00 claim back'), findsOneWidget);
    expect(find.text('25.00'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('rule42-post')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('rule42-post-confirm')));
    await tester.pumpAndSettle();
    expect(api.annualPosts, [
      {'financial_year': '2026-27', 'posting_date': '2027-04-01'},
    ]);
  });

  testWidgets('REPORT mode hides Post and says so', (tester) async {
    await _pump(tester, _Api(mode: 'REPORT'));
    expect(find.byKey(const ValueKey('rule42-post')), findsNothing);
    expect(find.byKey(const ValueKey('rule42-report-note')), findsOneWidget);
    expect(find.text('25000.00'), findsOneWidget);
  });

  testWidgets('OFF mode says rule 42 is switched off', (tester) async {
    await _pump(tester, _Api(mode: 'OFF'));
    expect(find.byKey(const ValueKey('rule42-off')), findsOneWidget);
    expect(find.byKey(const ValueKey('rule42-post')), findsNothing);
    expect(find.text('Common credit (C2)'), findsNothing);
  });

  testWidgets('no journal permission, no Post or Take back', (tester) async {
    await _pump(tester, _Api(), codes: const ['SALES_VIEW']);
    expect(find.byKey(const ValueKey('rule42-post')), findsNothing);
    expect(find.byKey(const ValueKey('rule42-takeback-r-1')), findsNothing);
  });

  testWidgets('take back sends the reason', (tester) async {
    final _Api api = _Api();
    await _pump(tester, api);

    await tester.tap(find.byKey(const ValueKey('rule42-takeback-r-1')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'Posted by mistake');
    await tester.tap(find.widgetWithText(FilledButton, 'Take back'));
    await tester.pumpAndSettle();

    expect(api.reversals, [
      {'id': 'r-1', 'reason': 'Posted by mistake'},
    ]);
  });

  testWidgets('fits 800x600', (tester) async {
    final _Api api = _Api();
    await _pump(tester, api, size: const Size(800, 600));
    expect(tester.takeException(), isNull);
    await tester.tap(find.text('Year'));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
  });
}
