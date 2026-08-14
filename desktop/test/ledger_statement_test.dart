import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/finance.dart';
import 'package:agency_desktop/ui/finance/ledger_statement_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// One account's ledger.
///
/// The trial balance answers "do the books balance". This answers the question
/// that follows, which is always "what is in that account" -- and the case that
/// has to be right is the quiet one, because an account that saw no movement is
/// not an account holding nothing.
PermissionService _permissionsFor(List<String> perms) {
  final String payload = base64Url.encode(
    utf8.encode(jsonEncode({'permissions': perms})),
  );
  return PermissionService()..applyAccessToken('h.$payload.s');
}

class _LedgerApi extends ApiClient {
  _LedgerApi({this.accounts = const [], this.periods = const [], this.report})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<LedgerAccount> accounts;
  final List<AccountingPeriod> periods;
  final GeneralLedgerReport? report;
  final List<String> requestedAccounts = [];

  @override
  Future<PagedResult<LedgerAccount>> ledgerAccounts({
    String? accountGroupId,
    bool? isActive,
  }) async =>
      PagedResult<LedgerAccount>(items: accounts, total: accounts.length);

  @override
  Future<List<AccountingPeriod>> accountingPeriods({String? financialYearId}) async =>
      periods;

  @override
  Future<GeneralLedgerReport> generalLedger({
    required String ledgerAccountId,
    required String accountingPeriodId,
  }) async {
    requestedAccounts.add(ledgerAccountId);
    return report ?? GeneralLedgerReport.empty;
  }
}

LedgerAccount _account(String id, String code, String name) =>
    LedgerAccount.fromJson({
      'id': id,
      'firm_id': 'firm-1',
      'account_group_id': 'g-1',
      'code': code,
      'name': name,
      'account_type': 'ASSET',
      'description': '',
      'is_balance_sheet': true,
      'is_profit_loss': false,
      'requires_cost_center': false,
      'requires_profit_center': false,
      'is_active': true,
    });

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

GeneralLedgerReport _report({
  String opening = '0.00',
  String debit = '0.00',
  String credit = '0.00',
  String closing = '0.00',
  List<Json> lines = const [],
}) =>
    GeneralLedgerReport.fromJson({
      'data': {
        'ledger_account_id': 'a-1',
        'account_code': '1100',
        'account_name': 'Trade Receivables',
        'account_type': 'ASSET',
        'accounting_period_id': 'p-1',
        'opening_balance': opening,
        'total_debit': debit,
        'total_credit': credit,
        'closing_balance': closing,
        'lines': lines,
      },
    });

Future<void> _pump(
  WidgetTester tester,
  _LedgerApi api, {
  List<String> perms = const ['LEDGER_VIEW'],
  bool hasActiveFirm = true,
}) async {
  tester.view.physicalSize = const Size(1400, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: LedgerStatementPage(
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
  group('reading a statement', () {
    test('the running balance comes down with the lines', () {
      // It starts from the opening balance and moves in whichever direction
      // the account type increases in, so adding the column up here would be a
      // second opinion about the ledger.
      final GeneralLedgerReport report = _report(
        opening: '231461.47',
        debit: '3823.20',
        closing: '235284.67',
        lines: [
          {
            'journal_entry_id': 'je-1',
            'journal_date': '2026-06-12',
            'reference_number': 'SI-2026-2027-000005',
            'description': 'Invoice SI-2026-2027-000005',
            'debit_amount': '3823.20',
            'credit_amount': '0.00',
            'running_balance': '235284.67',
          },
        ],
      );

      expect(report.lines.single.runningBalance, '235284.67');
      expect(report.closingBalance, '235284.67');
      expect(report.carriesABalance, isFalse, reason: 'it moved this period');
    });

    test('no movement against a balance is quiet, not empty', () {
      expect(_report(opening: '249236.70', closing: '249236.70').carriesABalance,
          isTrue);
    });

    test('no movement and no balance is empty', () {
      expect(_report().carriesABalance, isFalse);
    });
  });

  group('the statement screen', () {
    testWidgets('a quiet account shows the balance it is sitting on',
        (tester) async {
      // The defect this screen was built on top of: an account that saw no
      // movement reported opening 0 and closing 0, which says the account is
      // empty rather than that it was quiet. Trade Receivables read that way
      // for March 2027 while the firm was owed 249,236.70.
      final _LedgerApi api = _LedgerApi(
        accounts: [_account('a-1', '1100', 'Trade Receivables')],
        periods: [_period('p-1', '2027-03-01')],
        report: _report(opening: '249236.70', closing: '249236.70'),
      );
      await _pump(tester, api);

      expect(
        find.textContaining('Nothing on this account'),
        findsNothing,
        reason: 'a carried balance is not nothing',
      );
      expect(find.textContaining('carried 249236.70 in and still holds it'),
          findsOneWidget);
      expect(find.text('249236.70'), findsWidgets);
    });

    testWidgets('an account with no balance and no movement says so',
        (tester) async {
      final _LedgerApi api = _LedgerApi(
        accounts: [_account('a-1', '1100', 'Trade Receivables')],
        periods: [_period('p-1', '2027-03-01')],
        report: _report(),
      );
      await _pump(tester, api);

      expect(find.textContaining('Nothing on this account'), findsOneWidget);
    });

    testWidgets('movements are listed with what wrote them', (tester) async {
      // "Which document made this figure" is the whole point of the statement:
      // a number somebody disputes should be traceable, not arguable.
      final _LedgerApi api = _LedgerApi(
        accounts: [_account('a-1', '1100', 'Trade Receivables')],
        periods: [_period('p-1', '2026-06-01')],
        report: _report(
          opening: '231461.47',
          debit: '3823.20',
          closing: '235284.67',
          lines: [
            {
              'journal_entry_id': 'je-1',
              'journal_date': '2026-06-12',
              'reference_number': 'SI-2026-2027-000005',
              'description': 'Invoice SI-2026-2027-000005',
              'debit_amount': '3823.20',
              'credit_amount': '0.00',
              'running_balance': '235284.67',
            },
          ],
        ),
      );
      await _pump(tester, api);

      expect(find.text('SI-2026-2027-000005'), findsOneWidget);
      expect(find.text('231461.47'), findsOneWidget, reason: 'opening balance');
      expect(find.text('235284.67'), findsWidgets, reason: 'running and closing');
    });

    testWidgets('choosing another account re-reads the statement',
        (tester) async {
      final _LedgerApi api = _LedgerApi(
        accounts: [
          _account('a-1', '1000', 'Cash'),
          _account('a-2', '1100', 'Trade Receivables'),
        ],
        periods: [_period('p-1', '2026-06-01')],
        report: _report(opening: '10.00', closing: '10.00'),
      );
      await _pump(tester, api);
      expect(api.requestedAccounts, ['a-1'], reason: 'the first account opens');

      await tester.tap(find.text('1000  Cash').last);
      await tester.pumpAndSettle();
      await tester.tap(find.text('1100  Trade Receivables').last);
      await tester.pumpAndSettle();

      expect(api.requestedAccounts, ['a-1', 'a-2']);
    });

    testWidgets('without LEDGER_VIEW there is nothing to show', (tester) async {
      await _pump(tester, _LedgerApi(), perms: const ['ACCOUNT_VIEW']);
      expect(find.textContaining('do not have permission'), findsOneWidget);
    });

    testWidgets('with no chart of accounts it says where to start',
        (tester) async {
      final _LedgerApi api = _LedgerApi(periods: [_period('p-1', '2026-06-01')]);
      await _pump(tester, api);
      expect(find.textContaining('No ledger accounts'), findsOneWidget);
    });
  });
}
