import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/security/permission_service.dart';
import '../../models/finance.dart';
import '../workspace/desktop_framework.dart';
import 'period_line.dart';
import 'profit_loss_range_view.dart';
import 'statement_amount.dart';

// Re-exported so a screen that shows figures does not have to know which file
// the formatter lives in; the profit and loss is where it was first needed.
export 'statement_amount.dart';

/// The profit and loss for one period, and the year it belongs to.
///
/// Two columns, because one on its own is the wrong answer half the time. A
/// month is what somebody asks about; the year to date is what tells them
/// whether the month was normal -- June 2026 in the seeded firm is a loss of
/// 2,657.46 inside a year that is 5,086.46 ahead, and either figure alone
/// misleads.
class ProfitLossPage extends StatefulWidget {
  const ProfitLossPage({
    super.key,
    required this.api,
    required this.permissions,
    required this.hasActiveFirm,
  });

  final ApiClient api;
  final PermissionService permissions;
  final bool hasActiveFirm;

  @override
  State<ProfitLossPage> createState() => _ProfitLossPageState();
}

class _ProfitLossPageState extends State<ProfitLossPage> {
  List<AccountingPeriod> _periods = const [];
  AccountingPeriod? _period;
  ProfitLossReport _report = ProfitLossReport.empty;

  /// One month with the year to date, or a run of months (backlog 50).
  bool _range = false;
  bool _loading = false;
  String? _error;

  bool get _canView => widget.permissions.hasPermission('PROFIT_LOSS_VIEW');

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
        // The period today falls in: the year's periods all exist from the
        // day the books open, so the newest is months ahead.
        _period = currentPeriod(ordered);
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
      final ProfitLossReport report = await widget.api.profitAndLoss(period.id);
      if (!mounted) return;
      setState(() => _report = report);
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() {
        _error = exception.message;
        _report = ProfitLossReport.empty;
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
        title: 'Profit and loss',
        message: 'You do not have permission to view the profit and loss.',
      );
    }
    if (!widget.hasActiveFirm) {
      return const StandardEmptyState(
        type: EmptyStateType.noFirmSelected,
        title: 'Profit and loss',
        message: 'Choose a firm to see its result.',
      );
    }
    final Widget show = SizedBox(
      width: 170,
      child: DropdownButtonFormField<bool>(
        key: const ValueKey('pl-show'),
        initialValue: _range,
        isExpanded: true,
        decoration: const InputDecoration(isDense: true, labelText: 'Show'),
        items: const [
          DropdownMenuItem(value: false, child: Text('One month')),
          DropdownMenuItem(value: true, child: Text('Months or year')),
        ],
        onChanged: (value) => setState(() => _range = value ?? false),
      ),
    );
    if (_range && _periods.isNotEmpty) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(
                AppSpacing.lg, AppSpacing.md, AppSpacing.lg, 0),
            child: Align(alignment: Alignment.centerLeft, child: show),
          ),
          Expanded(
            child: ProfitLossRangeView(api: widget.api, periods: _periods),
          ),
        ],
      );
    }
    return LoadingOverlay(
      loading: _loading,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Phase 2: the period and refresh on the page line (4.5).
          if (Phase2Scope.of(context))
            AccountingPeriodLine(
              leading: [show],
              periods: _periods,
              value: _period,
              hint: 'Accounting period',
              onChanged: (period) {
                setState(() => _period = period);
                unawaited(_loadReport());
              },
              onRefresh: _loading ? null : () => unawaited(_loadReport()),
              trailing: [],
            )
          else
          Padding(
            padding: const EdgeInsets.all(AppSpacing.lg),
            child: Row(children: [
              show,
              const SizedBox(width: AppSpacing.md),
              SizedBox(
                width: 360,
                child: DropdownButtonFormField<String>(
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
                ),
              ),
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

  Widget _body(BuildContext context) {
    if (_periods.isEmpty) {
      return const StandardEmptyState(
        type: EmptyStateType.noRecords,
        title: 'No accounting periods',
        message: 'A result is drawn for a period. Create a financial year and '
            'its periods first.',
      );
    }
    if (_report.isEmpty) {
      return const StandardEmptyState(
        type: EmptyStateType.noRecords,
        title: 'Nothing traded in this financial year',
        message: 'No income or expense account has moved. Approving an invoice '
            'or dispatching a delivery note is what puts a figure here.',
      );
    }
    return SingleChildScrollView(
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg),
      child: Phase2WideTable(
        table: DataTable(
          columns: const [
            DataColumn(label: Text('Code')),
            DataColumn(label: Text('Account')),
            DataColumn(label: Text('This period'), numeric: true),
            DataColumn(label: Text('Year to date'), numeric: true),
          ],
          rows: [
            ..._section(context, 'Income', _report.income),
            _totalRow(context, 'Total income', _report.totalIncome,
                _report.yearToDateIncome),
            ..._section(context, 'Expenses', _report.expenses),
            _totalRow(context, 'Total expenses', _report.totalExpense,
                _report.yearToDateExpense),
            // The point of the report, so it is the emphasised row. One label
            // for both columns: they can disagree about profit and loss, and
            // "profit" written over a negative number is worse than a figure
            // in parentheses under a neutral heading.
            _totalRow(
              context,
              'Net profit or loss',
              _report.netProfit,
              _report.yearToDateNetProfit,
              emphasis: true,
            ),
          ],
        ),
      ),
    );
  }

  List<DataRow> _section(
    BuildContext context,
    String title,
    List<ProfitLossLine> lines,
  ) =>
      [
        DataRow(cells: [
          const DataCell(Text('')),
          DataCell(
            Text(title, style: Theme.of(context).textTheme.titleSmall),
          ),
          const DataCell(Text('')),
          const DataCell(Text('')),
        ]),
        for (final ProfitLossLine line in lines)
          DataRow(cells: [
            DataCell(Text(line.accountCode)),
            DataCell(Text(line.accountName)),
            DataCell(Text(presentAmount(line.periodAmount))),
            DataCell(Text(presentAmount(line.yearToDateAmount))),
          ]),
        if (lines.isEmpty)
          DataRow(cells: [
            const DataCell(Text('')),
            DataCell(
              Text(
                'None in this year',
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ),
            const DataCell(Text('')),
            const DataCell(Text('')),
          ]),
      ];

  DataRow _totalRow(
    BuildContext context,
    String label,
    String period,
    String yearToDate, {
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
        DataCell(Text(presentAmount(period), style: style)),
        DataCell(Text(presentAmount(yearToDate), style: style)),
      ],
    );
  }
}
