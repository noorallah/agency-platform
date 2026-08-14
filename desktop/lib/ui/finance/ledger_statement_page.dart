import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/security/permission_service.dart';
import '../../models/entities.dart';
import '../../models/finance.dart';
import '../workspace/desktop_framework.dart';

/// One account's ledger: what it opened at, every movement, what it closed at.
///
/// The trial balance answers "do the books balance"; this answers the question
/// that follows it, which is always "what is in that account". Every line names
/// the entry that made it, so a figure somebody disputes can be traced back to
/// the goods receipt or invoice that wrote it rather than argued about.
class LedgerStatementPage extends StatefulWidget {
  const LedgerStatementPage({
    super.key,
    required this.api,
    required this.permissions,
    required this.hasActiveFirm,
  });

  final ApiClient api;
  final PermissionService permissions;
  final bool hasActiveFirm;

  @override
  State<LedgerStatementPage> createState() => _LedgerStatementPageState();
}

class _LedgerStatementPageState extends State<LedgerStatementPage> {
  List<LedgerAccount> _accounts = const [];
  List<AccountingPeriod> _periods = const [];
  LedgerAccount? _account;
  AccountingPeriod? _period;
  GeneralLedgerReport _report = GeneralLedgerReport.empty;
  bool _loading = false;
  String? _error;

  bool get _canView => widget.permissions.hasPermission('LEDGER_VIEW');

  @override
  void initState() {
    super.initState();
    unawaited(_loadReferences());
  }

  Future<void> _loadReferences() async {
    if (!widget.hasActiveFirm || !_canView) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final List<dynamic> results = await Future.wait<dynamic>([
        // Inactive accounts are still offered: an account is deactivated rather
        // than deleted precisely because its history has to stay readable, and
        // hiding it here would make that history unreachable.
        widget.api.ledgerAccounts(),
        widget.api.accountingPeriods(),
      ]);
      if (!mounted) return;
      final List<LedgerAccount> accounts =
          (results[0] as PagedResult<LedgerAccount>).items.toList()
            ..sort((a, b) => a.code.compareTo(b.code));
      // Newest first: the period somebody wants is nearly always the one they
      // are in, and it is the last one the year created.
      final List<AccountingPeriod> periods = (results[1] as List<AccountingPeriod>)
          .toList()
        ..sort((a, b) => b.startsOn.compareTo(a.startsOn));
      setState(() {
        _accounts = accounts;
        _periods = periods;
        _account = accounts.isEmpty ? null : accounts.first;
        _period = periods.isEmpty ? null : periods.first;
      });
      if (_account != null && _period != null) await _loadReport();
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() => _error = exception.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _loadReport() async {
    final LedgerAccount? account = _account;
    final AccountingPeriod? period = _period;
    if (account == null || period == null) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final GeneralLedgerReport report = await widget.api.generalLedger(
        ledgerAccountId: account.id,
        accountingPeriodId: period.id,
      );
      if (!mounted) return;
      setState(() => _report = report);
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() {
        _error = exception.message;
        _report = GeneralLedgerReport.empty;
      });
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!_canView) {
      return const StandardEmptyState(
        type: EmptyStateType.noPermissions,
        title: 'Ledgers',
        message: 'You do not have permission to view the ledger.',
      );
    }
    if (!widget.hasActiveFirm) {
      return const StandardEmptyState(
        type: EmptyStateType.noFirmSelected,
        title: 'Ledgers',
        message: 'Choose a firm to see its ledger.',
      );
    }
    return LoadingOverlay(
      loading: _loading,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.all(AppSpacing.lg),
            child: Row(children: [
              SizedBox(width: 320, child: _accountPicker()),
              const SizedBox(width: AppSpacing.md),
              SizedBox(width: 300, child: _periodPicker()),
              const Spacer(),
              IconButton(
                tooltip: 'Refresh',
                onPressed: _loading ? null : () => unawaited(_loadReport()),
                icon: const Icon(Icons.refresh),
              ),
            ]),
          ),
          if (_error != null)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg),
              child: MaterialBanner(
                content: Text(_error!),
                actions: [
                  TextButton(
                    onPressed: () => setState(() => _error = null),
                    child: const Text('Dismiss'),
                  ),
                ],
              ),
            ),
          Expanded(child: _body(context)),
        ],
      ),
    );
  }

  Widget _accountPicker() => DropdownButtonFormField<String>(
        initialValue: _account?.id,
        isExpanded: true,
        decoration: const InputDecoration(labelText: 'Account'),
        items: [
          for (final LedgerAccount account in _accounts)
            DropdownMenuItem<String>(
              value: account.id,
              child: Text(
                '${account.code}  ${account.name}',
                overflow: TextOverflow.ellipsis,
              ),
            ),
        ],
        onChanged: (value) {
          final Iterable<LedgerAccount> match =
              _accounts.where((account) => account.id == value);
          if (match.isEmpty) return;
          setState(() => _account = match.first);
          unawaited(_loadReport());
        },
      );

  Widget _periodPicker() => DropdownButtonFormField<String>(
        initialValue: _period?.id,
        isExpanded: true,
        decoration: const InputDecoration(labelText: 'Accounting period'),
        items: [
          for (final AccountingPeriod period in _periods)
            DropdownMenuItem<String>(
              value: period.id,
              child: Text(period.label, overflow: TextOverflow.ellipsis),
            ),
        ],
        onChanged: (value) {
          final Iterable<AccountingPeriod> match =
              _periods.where((period) => period.id == value);
          if (match.isEmpty) return;
          setState(() => _period = match.first);
          unawaited(_loadReport());
        },
      );

  Widget _body(BuildContext context) {
    if (_accounts.isEmpty) {
      return const StandardEmptyState(
        type: EmptyStateType.noRecords,
        title: 'No ledger accounts',
        message: 'A statement is drawn for an account. Set up the chart of '
            'accounts first.',
      );
    }
    if (_periods.isEmpty) {
      return const StandardEmptyState(
        type: EmptyStateType.noRecords,
        title: 'No accounting periods',
        message: 'A statement is drawn for a period. Create a financial year '
            'and its periods first.',
      );
    }
    // A quiet account still has a statement worth showing: the balance it is
    // sitting on is the answer to the question that was asked. Only an account
    // with no movement *and* nothing carried in has nothing to say.
    if (_report.lines.isEmpty && !_report.carriesABalance) {
      return const StandardEmptyState(
        type: EmptyStateType.noRecords,
        title: 'Nothing on this account in this period',
        message: 'It holds no balance from an earlier period and nothing was '
            'posted to it in this one.',
      );
    }
    return SingleChildScrollView(
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _summary(context),
          const SizedBox(height: AppSpacing.lg),
          if (_report.lines.isEmpty)
            Padding(
              padding: const EdgeInsets.only(bottom: AppSpacing.md),
              child: Text(
                'Nothing was posted to this account in this period. It carried '
                '${_report.openingBalance} in and still holds it.',
                style: Theme.of(context).textTheme.bodyMedium,
              ),
            )
          else
            _table(context),
        ],
      ),
    );
  }

  /// The four figures that make a statement a statement.
  ///
  /// Opening and closing sit either side of the movement totals because that
  /// is the arithmetic being claimed: this is where the account started, this
  /// is what happened, this is where it ended.
  Widget _summary(BuildContext context) => Wrap(
        spacing: AppSpacing.xl,
        runSpacing: AppSpacing.md,
        children: [
          _figure(context, 'Opening balance', _report.openingBalance),
          _figure(context, 'Debits', _report.totalDebit),
          _figure(context, 'Credits', _report.totalCredit),
          _figure(context, 'Closing balance', _report.closingBalance,
              emphasis: true),
        ],
      );

  Widget _figure(
    BuildContext context,
    String label,
    String amount, {
    bool emphasis = false,
  }) =>
      Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(label, style: Theme.of(context).textTheme.labelMedium),
          Text(
            amount,
            style: emphasis
                ? Theme.of(context).textTheme.titleMedium
                : Theme.of(context).textTheme.bodyLarge,
          ),
        ],
      );

  Widget _table(BuildContext context) => SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: DataTable(
          columns: const [
            DataColumn(label: Text('Date')),
            DataColumn(label: Text('Reference')),
            DataColumn(label: Text('Narration')),
            DataColumn(label: Text('Debit'), numeric: true),
            DataColumn(label: Text('Credit'), numeric: true),
            DataColumn(label: Text('Balance'), numeric: true),
          ],
          rows: [
            for (final GeneralLedgerLine line in _report.lines)
              DataRow(cells: [
                DataCell(Text(line.journalDate)),
                DataCell(Text(line.referenceNumber)),
                DataCell(
                  SizedBox(
                    width: 320,
                    child: Text(line.description, overflow: TextOverflow.ellipsis),
                  ),
                ),
                DataCell(Text(line.debitAmount)),
                DataCell(Text(line.creditAmount)),
                DataCell(Text(line.runningBalance)),
              ]),
          ],
        ),
      );
}
