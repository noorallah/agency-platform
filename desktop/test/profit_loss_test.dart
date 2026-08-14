import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/finance.dart';
import 'package:agency_desktop/ui/finance/profit_loss_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// The profit and loss.
///
/// Two columns, because one on its own is the wrong answer half the time: June
/// 2026 in the seeded firm is a loss of 2,657.46 inside a year that is 5,086.46
/// ahead, and either figure alone misleads.
PermissionService _permissionsFor(List<String> perms) {
  final String payload = base64Url.encode(
    utf8.encode(jsonEncode({'permissions': perms})),
  );
  return PermissionService()..applyAccessToken('h.$payload.s');
}

class _ProfitLossApi extends ApiClient {
  _ProfitLossApi({this.periods = const [], this.report})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<AccountingPeriod> periods;
  final ProfitLossReport? report;
  final List<String> requestedPeriods = [];

  @override
  Future<List<AccountingPeriod>> accountingPeriods({String? financialYearId}) async =>
      periods;

  @override
  Future<ProfitLossReport> profitAndLoss(String accountingPeriodId) async {
    requestedPeriods.add(accountingPeriodId);
    return report ?? ProfitLossReport.empty;
  }
}

AccountingPeriod _period(String id, String starts) => AccountingPeriod.fromJson({
      'id': id,
      'financial_year_id': 'fy-1',
      'period_number': 1,
      'code': id,
      'name': 'Period $id',
      'starts_on': starts,
      'ends_on': starts,
      'status': 'OPEN',
    });

Json _line(String code, String name, String period, String ytd) => {
      'ledger_account_id': 'a-$code',
      'account_code': code,
      'account_name': name,
      'account_type': 'INCOME',
      'period_amount': period,
      'year_to_date_amount': ytd,
    };

/// June 2026 in the seeded firm, which is the case that matters: a month in
/// the red inside a year in the black.
ProfitLossReport _june() => ProfitLossReport.fromJson({
      'data': {
        'accounting_period_id': 'p-1',
        'financial_year_id': 'fy-1',
        'generated_at': '2026-08-14T00:00:00Z',
        'income': [_line('4000', 'Sales', '3240.00', '20690.00')],
        'expenses': [_line('5200', 'Cost of Goods Sold', '5897.46', '15603.54')],
        'total_income': '3240.00',
        'total_expense': '5897.46',
        'net_profit': '-2657.46',
        'year_to_date_income': '20690.00',
        'year_to_date_expense': '15603.54',
        'year_to_date_net_profit': '5086.46',
      },
    });

Future<void> _pump(
  WidgetTester tester,
  _ProfitLossApi api, {
  List<String> perms = const ['PROFIT_LOSS_VIEW'],
  bool hasActiveFirm = true,
}) async {
  tester.view.physicalSize = const Size(1400, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: ProfitLossPage(
          api: api,
          permissions: _permissionsFor(perms),
          hasActiveFirm: hasActiveFirm,
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  group('writing a figure the way a statement writes it', () {
    test('a negative is in parentheses, not behind a minus sign', () {
      // A minus sign in a column of money is easy to miss and easy to mistake
      // for a hyphen.
      expect(presentAmount('-2657.46'), '(2657.46)');
    });

    test('a positive is left alone', () {
      expect(presentAmount('5086.46'), '5086.46');
    });

    test('zero is not a negative', () {
      expect(presentAmount('0.00'), '0.00');
    });
  });

  group('reading the report', () {
    test('both columns come through', () {
      final ProfitLossReport report = _june();
      expect(report.income.single.periodAmount, '3240.00');
      expect(report.income.single.yearToDateAmount, '20690.00');
      expect(report.netProfit, '-2657.46');
      expect(report.yearToDateNetProfit, '5086.46');
      expect(report.isEmpty, isFalse);
    });

    test('a year with no trading is empty', () {
      expect(ProfitLossReport.empty.isEmpty, isTrue);
    });
  });

  group('the profit and loss screen', () {
    testWidgets('a month in the red inside a year in the black shows both',
        (tester) async {
      final _ProfitLossApi api = _ProfitLossApi(
        periods: [_period('p-1', '2026-06-01')],
        report: _june(),
      );
      await _pump(tester, api);

      expect(find.text('(2657.46)'), findsOneWidget, reason: 'the month lost');
      expect(find.text('5086.46'), findsOneWidget, reason: 'the year is ahead');
      // One label over both columns: they disagree here, and "profit" written
      // over a negative number is worse than parentheses under a neutral
      // heading.
      expect(find.text('Net profit or loss'), findsOneWidget);
      expect(find.text('Sales'), findsOneWidget);
      expect(find.text('Cost of Goods Sold'), findsOneWidget);
    });

    testWidgets('a section with nothing in it says so rather than vanishing',
        (tester) async {
      // An empty Expenses section is a fact about the year. Dropping the
      // heading would leave a reader wondering whether it was not reported.
      final _ProfitLossApi api = _ProfitLossApi(
        periods: [_period('p-1', '2026-06-01')],
        report: ProfitLossReport.fromJson({
          'data': {
            'accounting_period_id': 'p-1',
            'financial_year_id': 'fy-1',
            'income': [_line('4000', 'Sales', '100.00', '100.00')],
            'expenses': const [],
            'total_income': '100.00',
            'total_expense': '0.00',
            'net_profit': '100.00',
            'year_to_date_income': '100.00',
            'year_to_date_expense': '0.00',
            'year_to_date_net_profit': '100.00',
          },
        }),
      );
      await _pump(tester, api);

      expect(find.text('Expenses'), findsOneWidget);
      expect(find.text('None in this year'), findsOneWidget);
    });

    testWidgets('a year that has not traded is an empty state', (tester) async {
      final _ProfitLossApi api =
          _ProfitLossApi(periods: [_period('p-1', '2026-06-01')]);
      await _pump(tester, api);

      expect(find.textContaining('Nothing traded'), findsOneWidget);
      expect(api.requestedPeriods, ['p-1']);
    });

    testWidgets('choosing another period re-reads the result', (tester) async {
      final _ProfitLossApi api = _ProfitLossApi(
        periods: [_period('p-2', '2026-07-01'), _period('p-1', '2026-06-01')],
        report: _june(),
      );
      await _pump(tester, api);
      expect(api.requestedPeriods, ['p-2'], reason: 'the newest period opens');

      await tester.tap(find.text('Period p-2  (2026-07-01 to 2026-07-01)').last);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Period p-1  (2026-06-01 to 2026-06-01)').last);
      await tester.pumpAndSettle();

      expect(api.requestedPeriods, ['p-2', 'p-1']);
    });

    testWidgets('without PROFIT_LOSS_VIEW there is nothing to show',
        (tester) async {
      await _pump(tester, _ProfitLossApi(), perms: const ['LEDGER_VIEW']);
      expect(find.textContaining('do not have permission'), findsOneWidget);
    });
  });
}
