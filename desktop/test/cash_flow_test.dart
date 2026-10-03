import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/finance.dart';
import 'package:agency_desktop/ui/finance/cash_flow_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// The cash flow statement (ACC-9).

PermissionService _permissions() {
  final String payload = base64Url.encode(
    utf8.encode(jsonEncode({
      'permissions': ['PROFIT_LOSS_VIEW'],
    })),
  );
  return PermissionService()..applyAccessToken('h.$payload.s');
}

List<AccountingPeriod> _periods() => [
      for (int n = 1; n <= 12; n++)
        AccountingPeriod.fromJson({
          'id': 'p-$n',
          'financial_year_id': 'fy',
          'period_number': n,
          'code': 'P$n',
          'name': 'Month $n',
          'starts_on': DateTime(2026, 3 + n, 1).toIso8601String().substring(0, 10),
          'ends_on': DateTime(2026, 4 + n, 0).toIso8601String().substring(0, 10),
          'status': 'OPEN',
        }),
    ];

class _Api extends ApiClient {
  _Api({this.reconciled = true})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final bool reconciled;
  final List<(String, String)> asked = [];

  @override
  Future<List<AccountingPeriod>> accountingPeriods(
          {String? financialYearId}) async =>
      _periods();

  @override
  Future<CashFlowReport> cashFlow({
    required String fromPeriodId,
    required String toPeriodId,
  }) async {
    asked.add((fromPeriodId, toPeriodId));
    Map<String, Object> line(String name, String amount) => {
          'ledger_account_id': name,
          'account_code': '1',
          'account_name': name,
          'amount': amount,
        };
    return CashFlowReport.fromJson({
      'from_date': '2026-04-01',
      'to_date': '2026-08-31',
      'net_profit': '1000.00',
      'operating': [
        line('Trade Receivables', '-300.00'),
        line('Trade Payables', '200.00'),
      ],
      'operating_total': '900.00',
      'investing': [line('Plant and Machinery', '-400.00')],
      'investing_total': '-400.00',
      'financing': [line('Bank Loan', '500.00')],
      'financing_total': '500.00',
      'net_change': '1000.00',
      'opening_cash': '50.00',
      'closing_cash': '1050.00',
      'is_reconciled': reconciled,
    });
  }
}

Future<_Api> _show(WidgetTester tester, {bool reconciled = true}) async {
  tester.view.physicalSize = const Size(800, 600);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final _Api api = _Api(reconciled: reconciled);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: CashFlowPage(
        api: api,
        permissions: _permissions(),
        hasActiveFirm: true,
      ),
    ),
  ));
  await tester.pumpAndSettle();
  return api;
}

void main() {
  testWidgets('shows the three sections, totals and brackets at 800x600',
      (tester) async {
    final _Api api = await _show(tester);
    expect(api.asked, isNotEmpty);

    expect(find.text('Cash flows from operating activities'), findsOneWidget);
    expect(find.text('Adjustments for working capital'), findsOneWidget);
    expect(find.text('Cash flows from investing activities'), findsOneWidget);
    expect(find.text('Cash flows from financing activities'), findsOneWidget);
    expect(find.text('Net cash from operating activities'), findsOneWidget);
    expect(find.text('Net increase/(decrease) in cash'), findsOneWidget);
    expect(find.text('Cash and bank at the start'), findsOneWidget);
    expect(find.text('Cash and bank at the end'), findsOneWidget);

    expect(find.text('900.00'), findsOneWidget);
    expect(find.text('(300.00)'), findsOneWidget);
    expect(find.text('(400.00)'), findsNWidgets(2));
    expect(find.text('1050.00'), findsOneWidget);
    expect(find.byKey(const ValueKey('cf-not-reconciled')), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('warns when it does not reconcile', (tester) async {
    await _show(tester, reconciled: false);
    expect(find.byKey(const ValueKey('cf-not-reconciled')), findsOneWidget);
    expect(find.textContaining('Does not reconcile to cash and bank'),
        findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
