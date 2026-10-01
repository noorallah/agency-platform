import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/finance.dart';
import 'package:agency_desktop/ui/finance/profit_loss_page.dart';
import 'package:agency_desktop/ui/finance/profit_loss_range_view.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// The profit and loss over a whole year or any run of months (backlog 50).

PermissionService _permissions() {
  final String payload = base64Url.encode(
    utf8.encode(jsonEncode({
      'permissions': ['PROFIT_LOSS_VIEW'],
    })),
  );
  return PermissionService()..applyAccessToken('h.$payload.s');
}

/// Twelve months of 2026-27 and twelve of 2025-26.
List<AccountingPeriod> _periods() => [
      for (final (String year, int startYear) in [('fy-25', 2025), ('fy-26', 2026)])
        for (int n = 1; n <= 12; n++)
          AccountingPeriod.fromJson({
            'id': '$year-$n',
            'financial_year_id': year,
            'period_number': n,
            'code': 'P$n',
            'name': 'Month $n $startYear',
            'starts_on': DateTime(startYear, 3 + n, 1)
                .toIso8601String()
                .substring(0, 10),
            'ends_on': DateTime(startYear, 4 + n, 0)
                .toIso8601String()
                .substring(0, 10),
            'status': 'OPEN',
          }),
    ];

class _Api extends ApiClient {
  _Api()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<(String, String, bool)> asked = [];

  @override
  Future<List<AccountingPeriod>> accountingPeriods(
          {String? financialYearId}) async =>
      _periods();

  @override
  Future<ProfitLossReport> profitAndLoss(String accountingPeriodId) async =>
      ProfitLossReport.empty;

  @override
  Future<ProfitLossRangeReport> profitAndLossRange({
    required String fromPeriodId,
    required String toPeriodId,
    bool comparePreviousYear = false,
  }) async {
    asked.add((fromPeriodId, toPeriodId, comparePreviousYear));
    return ProfitLossRangeReport.fromJson({
      'data': {
        'months': [
          {'name': 'April 2026'},
          {'name': 'May 2026'},
        ],
        'income': [
          {
            'account_code': '4000',
            'account_name': 'Sales',
            'amount': '160.00',
            'months': ['100.00', '60.00'],
            'comparison_amount': comparePreviousYear ? '70.00' : null,
          },
        ],
        'expenses': <Object>[],
        'total_income': '160.00',
        'total_expense': '0.00',
        'net_profit': '160.00',
        'monthly_net_profit': ['100.00', '60.00'],
        'comparison_year_id': comparePreviousYear ? 'fy-25' : null,
        'comparison_income': comparePreviousYear ? '70.00' : null,
        'comparison_expense': comparePreviousYear ? '0.00' : null,
        'comparison_net_profit': comparePreviousYear ? '70.00' : null,
      },
    });
  }
}

void main() {
  group('presets stay inside one financial year', () {
    final DateTime today = DateTime(2026, 8, 15);

    test('this financial year is April to March', () {
      final span = presetSpan('year', _periods(), today)!;
      expect((span.$1.id, span.$2.id), ('fy-26-1', 'fy-26-12'));
    });

    test('year to date ends with the month today falls in', () {
      final span = presetSpan('ytd', _periods(), today)!;
      expect((span.$1.id, span.$2.id), ('fy-26-1', 'fy-26-5'));
    });

    test('this quarter is the year quarter today falls in', () {
      final span = presetSpan('quarter', _periods(), today)!;
      expect((span.$1.id, span.$2.id), ('fy-26-4', 'fy-26-6'));
    });

    test('last financial year is the year before', () {
      final span = presetSpan('last-year', _periods(), today)!;
      expect((span.$1.id, span.$2.id), ('fy-25-1', 'fy-25-12'));
    });
  });

  testWidgets('Months or year reads the whole year, then months and last year',
      (tester) async {
    tester.view.physicalSize = const Size(1400, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final _Api api = _Api();
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: ProfitLossPage(
          api: api,
          permissions: _permissions(),
          hasActiveFirm: true,
        ),
      ),
    ));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const ValueKey('pl-show')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Months or year').last);
    await tester.pumpAndSettle();

    expect(api.asked, isNotEmpty);
    expect(api.asked.last.$3, isFalse);
    expect(find.text('Total'), findsOneWidget);
    expect(find.text('April 2026'), findsNothing);

    await tester.tap(find.byKey(const ValueKey('pl-range-monthly')));
    await tester.pumpAndSettle();
    expect(find.text('April 2026'), findsOneWidget);
    expect(find.text('May 2026'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('pl-range-compare')));
    await tester.pumpAndSettle();
    expect(api.asked.last.$3, isTrue);
    expect(find.text('Last year'), findsOneWidget);
    expect(find.text('70.00'), findsWidgets);
    expect(tester.takeException(), isNull);
  });
}
