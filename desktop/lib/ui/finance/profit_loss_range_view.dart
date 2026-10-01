import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../models/finance.dart';
import '../workspace/desktop_framework.dart';
import 'statement_amount.dart';

/// Which run of months a preset names, from the firm's own periods.
///
/// The Tally / Zoho presets (backlog 50). Every one stays inside one
/// financial year, because the server refuses a span across two: profit
/// resets at the year end. Returns null when the firm has no such months.
(AccountingPeriod, AccountingPeriod)? presetSpan(
  String preset,
  List<AccountingPeriod> periods,
  DateTime today,
) {
  if (periods.isEmpty) return null;
  final String day = today.toIso8601String().substring(0, 10);
  final List<AccountingPeriod> ordered = [...periods]
    ..sort((a, b) => a.startsOn.compareTo(b.startsOn));
  final AccountingPeriod current = ordered.lastWhere(
    (period) => period.startsOn.compareTo(day) <= 0,
    orElse: () => ordered.first,
  );
  List<AccountingPeriod> yearOf(String yearId) =>
      ordered.where((period) => period.financialYearId == yearId).toList();
  final List<AccountingPeriod> year = yearOf(current.financialYearId);
  switch (preset) {
    case 'year':
      return (year.first, year.last);
    case 'ytd':
      return (year.first, current);
    case 'quarter':
      final int quarter = (current.periodNumber - 1) ~/ 3;
      final List<AccountingPeriod> months = year
          .where((period) => (period.periodNumber - 1) ~/ 3 == quarter)
          .toList();
      return months.isEmpty ? null : (months.first, months.last);
    case 'last-year':
      final List<AccountingPeriod> earlier = ordered
          .where((period) => period.startsOn.compareTo(year.first.startsOn) < 0)
          .toList();
      if (earlier.isEmpty) return null;
      final List<AccountingPeriod> last = yearOf(earlier.last.financialYearId);
      return (last.first, last.last);
  }
  return null;
}

/// The profit and loss over a run of months in one financial year (50).
///
/// A preset or a From and To month; the total of the span, optionally a
/// column per month, and optionally the same months of the year before --
/// how owners compare one month or one year with another.
class ProfitLossRangeView extends StatefulWidget {
  const ProfitLossRangeView({
    super.key,
    required this.api,
    required this.periods,
    this.today,
  });

  final ApiClient api;
  final List<AccountingPeriod> periods;

  /// For tests; the clock otherwise.
  final DateTime? today;

  @override
  State<ProfitLossRangeView> createState() => _ProfitLossRangeViewState();
}

class _ProfitLossRangeViewState extends State<ProfitLossRangeView> {
  static const Map<String, String> _presets = {
    'year': 'This financial year',
    'ytd': 'Year to date',
    'quarter': 'This quarter',
    'last-year': 'Last financial year',
    'custom': 'Custom',
  };

  String _preset = 'year';
  AccountingPeriod? _from;
  AccountingPeriod? _to;
  bool _monthly = false;
  bool _compare = false;
  ProfitLossRangeReport? _report;
  bool _loading = false;
  String? _error;

  List<AccountingPeriod> get _ordered => [...widget.periods]
    ..sort((a, b) => a.startsOn.compareTo(b.startsOn));

  @override
  void initState() {
    super.initState();
    _applyPreset('year');
  }

  void _applyPreset(String preset) {
    _preset = preset;
    if (preset == 'custom') return;
    final (AccountingPeriod, AccountingPeriod)? span =
        presetSpan(preset, widget.periods, widget.today ?? DateTime.now());
    if (span == null) {
      setState(() {
        _error = 'The firm has no months for ${_presets[preset]}.';
        _report = null;
      });
      return;
    }
    _from = span.$1;
    _to = span.$2;
    unawaited(_load());
  }

  Future<void> _load() async {
    final AccountingPeriod? from = _from;
    final AccountingPeriod? to = _to;
    if (from == null || to == null) return;
    if (from.financialYearId != to.financialYearId) {
      setState(() => _error =
          'A profit and loss runs within one financial year; choose two '
          'months of the same year.');
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final ProfitLossRangeReport report = await widget.api.profitAndLossRange(
        fromPeriodId: from.id,
        toPeriodId: to.id,
        comparePreviousYear: _compare,
      );
      if (!mounted) return;
      setState(() => _report = report);
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() {
        _error = exception.message;
        _report = null;
      });
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Widget _monthPicker(String label, AccountingPeriod? value, Key key,
          ValueChanged<AccountingPeriod> onChanged) =>
      SizedBox(
        width: 170,
        child: DropdownButtonFormField<String>(
          key: key,
          initialValue: value?.id,
          isExpanded: true,
          decoration: InputDecoration(labelText: label, isDense: true),
          items: [
            for (final AccountingPeriod period in _ordered)
              DropdownMenuItem(
                value: period.id,
                child: Text(period.name, overflow: TextOverflow.ellipsis),
              ),
          ],
          onChanged: (id) {
            final AccountingPeriod? match =
                _ordered.where((period) => period.id == id).firstOrNull;
            if (match == null) return;
            setState(() => _preset = 'custom');
            onChanged(match);
            unawaited(_load());
          },
        ),
      );

  @override
  Widget build(BuildContext context) => LoadingOverlay(
        loading: _loading,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Padding(
              padding: const EdgeInsets.symmetric(
                horizontal: AppSpacing.lg,
                vertical: AppSpacing.sm,
              ),
              child: Wrap(
                spacing: AppSpacing.md,
                runSpacing: AppSpacing.sm,
                crossAxisAlignment: WrapCrossAlignment.center,
                children: [
                  SizedBox(
                    width: 190,
                    child: DropdownButtonFormField<String>(
                      key: const ValueKey('pl-range-preset'),
                      initialValue: _preset,
                      isExpanded: true,
                      decoration: const InputDecoration(
                          labelText: 'Months', isDense: true),
                      items: [
                        for (final MapEntry<String, String> entry
                            in _presets.entries)
                          DropdownMenuItem(
                              value: entry.key, child: Text(entry.value)),
                      ],
                      onChanged: (value) {
                        if (value != null) setState(() => _applyPreset(value));
                      },
                    ),
                  ),
                  _monthPicker('From', _from, const ValueKey('pl-range-from'),
                      (period) => _from = period),
                  _monthPicker('To', _to, const ValueKey('pl-range-to'),
                      (period) => _to = period),
                  FilterChip(
                    key: const ValueKey('pl-range-monthly'),
                    label: const Text('Month by month'),
                    selected: _monthly,
                    onSelected: (value) => setState(() => _monthly = value),
                  ),
                  FilterChip(
                    key: const ValueKey('pl-range-compare'),
                    label: const Text('Compare with last year'),
                    selected: _compare,
                    onSelected: (value) {
                      setState(() => _compare = value);
                      unawaited(_load());
                    },
                  ),
                ],
              ),
            ),
            if (_error != null)
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg),
                child: Text(
                  _error!,
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
              ),
            Expanded(child: _body(context)),
          ],
        ),
      );

  Widget _body(BuildContext context) {
    final ProfitLossRangeReport? report = _report;
    if (report == null) return const SizedBox.shrink();
    if (report.isEmpty) {
      return const StandardEmptyState(
        type: EmptyStateType.noRecords,
        title: 'Nothing traded in these months',
        message: 'No income or expense account moved in the months chosen.',
      );
    }
    final bool monthly = _monthly && report.monthNames.length > 1;
    final bool compare = _compare && report.hasComparison;
    return SingleChildScrollView(
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (_compare && !report.hasComparison)
            Padding(
              padding: const EdgeInsets.only(bottom: AppSpacing.sm),
              child: Text(
                'The previous financial year is not in these books, so there '
                'is nothing to compare with.',
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ),
          Phase2WideTable(
            table: DataTable(
              columns: [
                const DataColumn(label: Text('Code')),
                const DataColumn(label: Text('Account')),
                if (monthly)
                  for (final String name in report.monthNames)
                    DataColumn(label: Text(name), numeric: true),
                const DataColumn(label: Text('Total'), numeric: true),
                if (compare)
                  const DataColumn(label: Text('Last year'), numeric: true),
              ],
              rows: [
                ..._section(context, 'Income', report.income, report, monthly,
                    compare),
                _total(context, 'Total income', report.totalIncome,
                    report.comparisonIncome, report, monthly, compare,
                    months: [
                      for (int i = 0; i < report.monthNames.length; i++)
                        ProfitLossRangeReport.monthTotal(report.income, i),
                    ]),
                ..._section(context, 'Expenses', report.expenses, report,
                    monthly, compare),
                _total(context, 'Total expenses', report.totalExpense,
                    report.comparisonExpense, report, monthly, compare,
                    months: [
                      for (int i = 0; i < report.monthNames.length; i++)
                        ProfitLossRangeReport.monthTotal(report.expenses, i),
                    ]),
                _total(context, 'Net profit or loss', report.netProfit,
                    report.comparisonNetProfit, report, monthly, compare,
                    months: report.monthlyNetProfit, emphasis: true),
              ],
            ),
          ),
        ],
      ),
    );
  }

  List<DataRow> _section(
    BuildContext context,
    String title,
    List<ProfitLossRangeLine> lines,
    ProfitLossRangeReport report,
    bool monthly,
    bool compare,
  ) {
    final int blanks =
        (monthly ? report.monthNames.length : 0) + 1 + (compare ? 1 : 0);
    return [
      DataRow(cells: [
        const DataCell(Text('')),
        DataCell(Text(title, style: Theme.of(context).textTheme.titleSmall)),
        for (int i = 0; i < blanks; i++) const DataCell(Text('')),
      ]),
      for (final ProfitLossRangeLine line in lines)
        DataRow(cells: [
          DataCell(Text(line.accountCode)),
          DataCell(Text(line.accountName)),
          if (monthly)
            for (final String value in line.months)
              DataCell(Text(presentAmount(value))),
          DataCell(Text(presentAmount(line.amount))),
          if (compare) DataCell(Text(presentAmount(line.comparisonAmount))),
        ]),
    ];
  }

  DataRow _total(
    BuildContext context,
    String label,
    String total,
    String comparison,
    ProfitLossRangeReport report,
    bool monthly,
    bool compare, {
    required List<String> months,
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
        if (monthly)
          for (final String value in months)
            DataCell(Text(presentAmount(value), style: style)),
        DataCell(Text(presentAmount(total), style: style)),
        if (compare) DataCell(Text(presentAmount(comparison), style: style)),
      ],
    );
  }
}
