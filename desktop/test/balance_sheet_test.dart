import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/finance.dart';
import 'package:agency_desktop/ui/finance/balance_sheet_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// The balance sheet.
///
/// The part that needs explaining on screen is equity: nothing in this ledger
/// posts a year-end closing entry, so the accumulated result of the income and
/// expense accounts is carried into equity as two computed rows. A firm whose
/// chart has no equity account at all -- which is every seeded firm -- would
/// otherwise be reading a figure with no visible source.
PermissionService _permissionsFor(List<String> perms) {
  final String payload = base64Url.encode(
    utf8.encode(jsonEncode({'permissions': perms})),
  );
  return PermissionService()..applyAccessToken('h.$payload.s');
}

class _BalanceSheetApi extends ApiClient {
  _BalanceSheetApi({this.periods = const [], this.report})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<AccountingPeriod> periods;
  final BalanceSheetReport? report;
  final List<String> requestedPeriods = [];

  @override
  Future<List<AccountingPeriod>> accountingPeriods({String? financialYearId}) async =>
      periods;

  @override
  Future<BalanceSheetReport> balanceSheet(String accountingPeriodId) async {
    requestedPeriods.add(accountingPeriodId);
    return report ?? BalanceSheetReport.empty;
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

Json _line(String code, String name, String type, String amount) => {
      'ledger_account_id': 'a-$code',
      'account_code': code,
      'account_name': name,
      'account_type': type,
      'amount': amount,
    };

/// March 2027 in the seeded firm, which has no equity account at all: the whole
/// equity side is the accumulated result.
BalanceSheetReport _march({bool balanced = true}) =>
    BalanceSheetReport.fromJson({
      'data': {
        'accounting_period_id': 'p-1',
        'financial_year_id': 'fy-1',
        'generated_at': '2026-08-14T00:00:00Z',
        'assets': [
          _line('1100', 'Trade Receivables', 'ASSET', '249236.70'),
          _line('1200', 'Inventory', 'ASSET', '235653.59'),
        ],
        'liabilities': [
          _line('2200', 'Output Tax', 'LIABILITY', '38019.20'),
          _line('2300', 'Goods Received Not Invoiced', 'LIABILITY', '355740.00'),
        ],
        'equity': const [],
        'total_assets': '484890.29',
        'total_liabilities': '393759.20',
        'total_equity': '91131.09',
        'retained_earnings_brought_forward': '80811.99',
        'result_for_the_year': '10319.10',
        'is_balanced': balanced,
      },
    });

Future<void> _pump(
  WidgetTester tester,
  _BalanceSheetApi api, {
  List<String> perms = const ['BALANCE_SHEET_VIEW'],
  bool hasActiveFirm = true,
}) async {
  tester.view.physicalSize = const Size(1400, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: BalanceSheetPage(
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
  group('reading the report', () {
    test('the verdict is the server\'s, carried through', () {
      // Two places deciding whether a sheet balances is two places that can
      // disagree, and the one holding the ledger should win.
      expect(_march().isBalanced, isTrue);
      expect(_march(balanced: false).isBalanced, isFalse);
    });

    test('the two earnings figures come through', () {
      final BalanceSheetReport report = _march();
      expect(report.retainedEarningsBroughtForward, '80811.99');
      expect(report.resultForTheYear, '10319.10');
      expect(report.totalEquity, '91131.09',
          reason: 'both are already inside the equity total');
    });

    test('a firm with nothing on the books is empty', () {
      expect(BalanceSheetReport.empty.isEmpty, isTrue);
    });
  });

  group('the balance sheet screen', () {
    testWidgets('equity with no equity account still adds up on screen',
        (tester) async {
      final _BalanceSheetApi api = _BalanceSheetApi(
        periods: [_period('p-1', '2027-03-01')],
        report: _march(),
      );
      await _pump(tester, api);

      expect(find.text('Retained earnings brought forward'), findsOneWidget);
      expect(find.text('80811.99'), findsOneWidget);
      expect(find.text('Result for the year'), findsOneWidget);
      expect(find.text('10319.10'), findsOneWidget);
      expect(find.text('91131.09'), findsOneWidget, reason: 'total equity');
      // And it says where that figure comes from, because a firm with no
      // equity account would otherwise be reading a number with no source.
      expect(find.textContaining('year-end closing entry'), findsOneWidget);
    });

    testWidgets('the closing line is assets against liabilities and equity',
        (tester) async {
      final _BalanceSheetApi api = _BalanceSheetApi(
        periods: [_period('p-1', '2027-03-01')],
        report: _march(),
      );
      await _pump(tester, api);

      expect(find.text('Total assets'), findsOneWidget);
      expect(find.text('Liabilities and equity'), findsOneWidget);
      // 393759.20 + 91131.09, added here only to put the two sides side by
      // side; the verdict itself is the server's.
      expect(find.text('484890.29'), findsNWidgets(2));
      expect(find.text('Balanced'), findsOneWidget);
    });

    testWidgets('a sheet that does not balance says what could cause it',
        (tester) async {
      // Only asset, liability and equity accounts appear, so a memo or control
      // account holding a balance shows up as the difference rather than being
      // absorbed silently.
      final _BalanceSheetApi api = _BalanceSheetApi(
        periods: [_period('p-1', '2027-03-01')],
        report: _march(balanced: false),
      );
      await _pump(tester, api);

      expect(find.text('Does not balance'), findsOneWidget);
      expect(find.textContaining('memo or control account'), findsOneWidget);
    });

    testWidgets('a section with nothing in it says so rather than vanishing',
        (tester) async {
      final _BalanceSheetApi api = _BalanceSheetApi(
        periods: [_period('p-1', '2027-03-01')],
        report: _march(),
      );
      await _pump(tester, api);

      expect(find.text('Equity'), findsOneWidget);
      expect(find.text('No account of this kind holds a balance'), findsOneWidget);
    });

    testWidgets('a firm with nothing on the books gets an empty state',
        (tester) async {
      final _BalanceSheetApi api =
          _BalanceSheetApi(periods: [_period('p-1', '2027-03-01')]);
      await _pump(tester, api);

      expect(find.textContaining('Nothing on the books'), findsOneWidget);
      expect(api.requestedPeriods, ['p-1']);
    });

    testWidgets('without BALANCE_SHEET_VIEW there is nothing to show',
        (tester) async {
      await _pump(tester, _BalanceSheetApi(), perms: const ['PROFIT_LOSS_VIEW']);
      expect(find.textContaining('do not have permission'), findsOneWidget);
    });
  });
}
