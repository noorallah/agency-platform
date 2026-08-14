import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/security/permission_service.dart';
import '../../models/finance.dart';
import '../workspace/desktop_framework.dart';
import 'statement_amount.dart';

/// What the firm owns and owes as at a period end.
///
/// The equity section is the part worth understanding: nothing in this ledger
/// posts a year-end closing entry, so income and expense accounts accumulate
/// and their net is the firm's earnings. It is carried here as two computed
/// rows rather than read from an account, and the screen says so -- a firm
/// whose chart has no equity account at all would otherwise be looking at a
/// figure with no visible source.
class BalanceSheetPage extends StatefulWidget {
  const BalanceSheetPage({
    super.key,
    required this.api,
    required this.permissions,
    required this.hasActiveFirm,
  });

  final ApiClient api;
  final PermissionService permissions;
  final bool hasActiveFirm;

  @override
  State<BalanceSheetPage> createState() => _BalanceSheetPageState();
}

class _BalanceSheetPageState extends State<BalanceSheetPage> {
  List<AccountingPeriod> _periods = const [];
  AccountingPeriod? _period;
  BalanceSheetReport _report = BalanceSheetReport.empty;
  bool _loading = false;
  String? _error;

  bool get _canView => widget.permissions.hasPermission('BALANCE_SHEET_VIEW');

  @override
  void initState() {
    super.initState();
    unawaited(_loadPeriods());
  }

  Future<void> _loadPeriods() async {
    if (!widget.hasActiveFirm || !_canView) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final List<AccountingPeriod> periods = await widget.api.accountingPeriods();
      if (!mounted) return;
      final List<AccountingPeriod> ordered = [...periods]
        ..sort((a, b) => b.startsOn.compareTo(a.startsOn));
      setState(() {
        _periods = ordered;
        _period = ordered.isEmpty ? null : ordered.first;
      });
      if (_period != null) await _loadReport();
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() => _error = exception.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _loadReport() async {
    final AccountingPeriod? period = _period;
    if (period == null) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final BalanceSheetReport report = await widget.api.balanceSheet(period.id);
      if (!mounted) return;
      setState(() => _report = report);
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() {
        _error = exception.message;
        _report = BalanceSheetReport.empty;
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
        title: 'Balance sheet',
        message: 'You do not have permission to view the balance sheet.',
      );
    }
    if (!widget.hasActiveFirm) {
      return const StandardEmptyState(
        type: EmptyStateType.noFirmSelected,
        title: 'Balance sheet',
        message: 'Choose a firm to see its position.',
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
              SizedBox(
                width: 360,
                child: DropdownButtonFormField<String>(
                  initialValue: _period?.id,
                  isExpanded: true,
                  decoration: const InputDecoration(labelText: 'As at period end'),
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
                ),
              ),
              const SizedBox(width: AppSpacing.lg),
              if (!_report.isEmpty) _balanceBadge(context),
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

  /// Whether the sheet balances, as the server reported it.
  ///
  /// Carried through, never recomputed here, for the same reason the trial
  /// balance's verdict is: two places deciding it is two places that can
  /// disagree, and the one holding the ledger should win.
  Widget _balanceBadge(BuildContext context) => Chip(
        avatar: Icon(
          _report.isBalanced ? Icons.check_circle_outline : Icons.error_outline,
          size: 18,
          color: _report.isBalanced
              ? Theme.of(context).colorScheme.primary
              : Theme.of(context).colorScheme.error,
        ),
        label: Text(_report.isBalanced ? 'Balanced' : 'Does not balance'),
      );

  Widget _body(BuildContext context) {
    if (_periods.isEmpty) {
      return const StandardEmptyState(
        type: EmptyStateType.noRecords,
        title: 'No accounting periods',
        message: 'A balance sheet is drawn as at a period end. Create a '
            'financial year and its periods first.',
      );
    }
    if (_report.isEmpty) {
      return const StandardEmptyState(
        type: EmptyStateType.noRecords,
        title: 'Nothing on the books yet',
        message: 'No account holds a balance as at this period. Completing a '
            'goods receipt or approving an invoice is what puts one here.',
      );
    }
    return SingleChildScrollView(
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: DataTable(
              columns: const [
                DataColumn(label: Text('Code')),
                DataColumn(label: Text('Account')),
                DataColumn(label: Text('Amount'), numeric: true),
              ],
              rows: [
                ..._section(context, 'Assets', _report.assets),
                _totalRow(context, 'Total assets', _report.totalAssets),
                ..._section(context, 'Liabilities', _report.liabilities),
                _totalRow(context, 'Total liabilities', _report.totalLiabilities),
                ..._section(context, 'Equity', _report.equity),
                // Computed, not accounts. They are listed as rows because they
                // are part of the equity total and hiding them would leave the
                // section not adding up on screen.
                _plainRow(
                  context,
                  'Retained earnings brought forward',
                  _report.retainedEarningsBroughtForward,
                ),
                _plainRow(
                  context,
                  'Result for the year',
                  _report.resultForTheYear,
                ),
                _totalRow(context, 'Total equity', _report.totalEquity),
                _totalRow(
                  context,
                  'Liabilities and equity',
                  _sum(_report.totalLiabilities, _report.totalEquity),
                  emphasis: true,
                ),
              ],
            ),
          ),
          const SizedBox(height: AppSpacing.md),
          Text(
            'Earnings are computed rather than held in an account: nothing '
            'posts a year-end closing entry, so the accumulated result of the '
            'income and expense accounts is carried into equity here.',
            style: Theme.of(context).textTheme.bodySmall,
          ),
          if (!_report.isBalanced)
            Padding(
              padding: const EdgeInsets.only(top: AppSpacing.sm),
              child: Text(
                'Assets do not equal liabilities and equity. Only asset, '
                'liability and equity accounts appear here, so a memo or '
                'control account holding a balance would show up as this '
                'difference rather than being absorbed silently.',
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ),
          const SizedBox(height: AppSpacing.lg),
        ],
      ),
    );
  }

  /// Add two server figures for the closing check line.
  ///
  /// The only arithmetic this screen does, and it is a presentation total
  /// rather than a second opinion: whether the sheet balances is still the
  /// server's answer, shown on the badge.
  String _sum(String left, String right) {
    final double total =
        (double.tryParse(left) ?? 0) + (double.tryParse(right) ?? 0);
    return total.toStringAsFixed(2);
  }

  List<DataRow> _section(
    BuildContext context,
    String title,
    List<BalanceSheetLine> lines,
  ) =>
      [
        DataRow(cells: [
          const DataCell(Text('')),
          DataCell(Text(title, style: Theme.of(context).textTheme.titleSmall)),
          const DataCell(Text('')),
        ]),
        for (final BalanceSheetLine line in lines)
          DataRow(cells: [
            DataCell(Text(line.accountCode)),
            DataCell(Text(line.accountName)),
            DataCell(Text(presentAmount(line.amount))),
          ]),
        if (lines.isEmpty)
          DataRow(cells: [
            const DataCell(Text('')),
            DataCell(
              Text(
                'No account of this kind holds a balance',
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ),
            const DataCell(Text('')),
          ]),
      ];

  DataRow _plainRow(BuildContext context, String label, String amount) =>
      DataRow(cells: [
        const DataCell(Text('')),
        DataCell(Text(label)),
        DataCell(Text(presentAmount(amount))),
      ]);

  DataRow _totalRow(
    BuildContext context,
    String label,
    String amount, {
    bool emphasis = false,
  }) {
    final TextStyle? style = emphasis
        ? Theme.of(context).textTheme.titleSmall
        : Theme.of(context).textTheme.bodyMedium;
    return DataRow(
      color: WidgetStatePropertyAll(
        Theme.of(context).colorScheme.surfaceContainerHighest,
      ),
      cells: [
        const DataCell(Text('')),
        DataCell(Text(label, style: style)),
        DataCell(Text(presentAmount(amount), style: style)),
      ],
    );
  }
}
