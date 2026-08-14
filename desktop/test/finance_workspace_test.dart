import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/finance.dart';
import 'package:agency_desktop/ui/finance/trial_balance_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// The accounting screens.
///
/// The finance API has been live since `20260809_0042` and every goods
/// receipt, dispatch and invoice posts to the ledger through it, while the
/// module rendered "Coming Soon". A firm could trade for a year with no way to
/// see whether its books balanced.
PermissionService _permissionsFor(List<String> perms) {
  final String payload = base64Url.encode(
    utf8.encode(jsonEncode({'permissions': perms})),
  );
  return PermissionService()..applyAccessToken('h.$payload.s');
}

class _FinanceApi extends ApiClient {
  _FinanceApi({this.periods = const [], this.report})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<AccountingPeriod> periods;
  final TrialBalanceReport? report;
  final List<String> requestedPeriods = [];

  @override
  Future<List<AccountingPeriod>> accountingPeriods({String? financialYearId}) async =>
      periods;

  @override
  Future<TrialBalanceReport> trialBalance(String accountingPeriodId) async {
    requestedPeriods.add(accountingPeriodId);
    return report ?? TrialBalanceReport.empty;
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

Future<void> _pump(
  WidgetTester tester,
  _FinanceApi api, {
  List<String> perms = const ['LEDGER_VIEW'],
  bool hasActiveFirm = true,
}) async {
  tester.view.physicalSize = const Size(1400, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: TrialBalancePage(
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
  group('reading the API', () {
    test('a trial balance carries the server\'s own verdict', () {
      // Whether the books balance is the server's answer, not something
      // recomputed here: two places deciding it is two places that can
      // disagree, and the one with the ledger in front of it should win.
      final TrialBalanceReport report = TrialBalanceReport.fromJson({
        'data': {
          'accounting_period_id': 'p-1',
          'generated_at': '2026-08-14T00:00:00Z',
          'total_debit': '604976.70',
          'total_credit': '604976.70',
          'is_balanced': true,
          'lines': [
            {
              'ledger_account_id': 'a-1',
              'account_code': '1200',
              'account_name': 'Inventory',
              'account_type': 'ASSET',
              'opening_balance': '0.00',
              'period_debit': '8040.00',
              'period_credit': '1150.52',
              'closing_balance': '6889.48',
            },
          ],
        },
      });

      expect(report.isBalanced, isTrue);
      expect(report.lines, hasLength(1));
      expect(report.lines.first.accountName, 'Inventory');
      expect(report.totalDebit, '604976.70');
    });

    test('a ledger account reads through the envelope', () {
      final LedgerAccount account = LedgerAccount.fromJson({
        'data': {
          'id': 'a-1',
          'code': '1000',
          'name': 'Cash',
          'account_type': 'ASSET',
          'is_active': true,
        },
      });
      expect(account.code, '1000');
      expect(account.isActive, isTrue);
    });
  });

  group('the trial balance screen', () {
    testWidgets('opens on the most recent period', (tester) async {
      // The period somebody wants is almost always the one they are in.
      final _FinanceApi api = _FinanceApi(
        periods: [
          _period('old', '2025-04-01'),
          _period('recent', '2026-08-01'),
        ],
      );
      await _pump(tester, api);

      expect(api.requestedPeriods, ['recent']);
    });

    testWidgets('shows the totals and says it balances', (tester) async {
      final _FinanceApi api = _FinanceApi(
        periods: [_period('p-1', '2026-08-01')],
        report: TrialBalanceReport.fromJson({
          'accounting_period_id': 'p-1',
          'total_debit': '604976.70',
          'total_credit': '604976.70',
          'is_balanced': true,
          'lines': [
            {
              'account_code': '4000',
              'account_name': 'Sales',
              'account_type': 'INCOME',
              'opening_balance': '0.00',
              'period_debit': '0.00',
              'period_credit': '2340.00',
              'closing_balance': '2340.00',
            },
          ],
        }),
      );
      await _pump(tester, api);

      expect(find.text('Sales'), findsOneWidget);
      expect(find.text('Balanced'), findsOneWidget);
      expect(find.text('604976.70'), findsWidgets);
    });

    testWidgets('an unbalanced ledger says by how much', (tester) async {
      // The number is the point. "Out of balance" without it sends somebody
      // to a spreadsheet to work out what the screen already knew.
      final _FinanceApi api = _FinanceApi(
        periods: [_period('p-1', '2026-08-01')],
        report: TrialBalanceReport.fromJson({
          'accounting_period_id': 'p-1',
          'total_debit': '1000.00',
          'total_credit': '940.50',
          'is_balanced': false,
          'lines': [
            {
              'account_code': '1000',
              'account_name': 'Cash',
              'account_type': 'ASSET',
              'opening_balance': '0.00',
              'period_debit': '1000.00',
              'period_credit': '940.50',
              'closing_balance': '59.50',
            },
          ],
        }),
      );
      await _pump(tester, api);

      expect(find.textContaining('Out of balance by 59.50'), findsOneWidget);
      // And it says what the totals cover, because the report lists only the
      // accounts posted to in the period: a quiet period can read as out of
      // balance while the ledger itself is sound.
      expect(
        find.textContaining('accounts posted to in this period'),
        findsOneWidget,
      );
    });

    testWidgets('a period with no postings says so, and why', (tester) async {
      final _FinanceApi api = _FinanceApi(periods: [_period('p-1', '2026-08-01')]);
      await _pump(tester, api);

      expect(find.textContaining('Nothing posted in this period'), findsOneWidget);
      // And it names what puts entries there, rather than leaving a blank grid.
      expect(find.textContaining('goods receipt'), findsOneWidget);
    });

    testWidgets('no periods at all is a different message', (tester) async {
      await _pump(tester, _FinanceApi());
      expect(find.textContaining('No accounting periods'), findsOneWidget);
    });

    testWidgets('without LEDGER_VIEW it shows nothing and asks nothing',
        (tester) async {
      final _FinanceApi api = _FinanceApi(periods: [_period('p-1', '2026-08-01')]);
      await _pump(tester, api, perms: const ['ACCOUNT_VIEW']);

      expect(find.textContaining('permission'), findsOneWidget);
      expect(
        api.requestedPeriods,
        isEmpty,
        reason: 'a screen the user cannot see should not query for it',
      );
    });
  });
}
