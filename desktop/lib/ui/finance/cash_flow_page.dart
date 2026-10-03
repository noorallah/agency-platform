import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/security/permission_service.dart';
import '../../models/finance.dart';
import '../workspace/desktop_framework.dart';
import 'statement_amount.dart';

/// The cash flow statement over a run of months in one financial year (ACC-9).
///
/// The standard indirect-method layout: net profit adjusted for working
/// capital, then investing and financing, down to the movement in cash and
/// bank. Amounts are signed -- cash in positive, cash out in brackets.
class CashFlowPage extends StatefulWidget {
  const CashFlowPage({
    super.key,
    required this.api,
    required this.permissions,
    required this.hasActiveFirm,
  });

  final ApiClient api;
  final PermissionService permissions;
  final bool hasActiveFirm;

  @override
  State<CashFlowPage> createState() => _CashFlowPageState();
}

class _CashFlowPageState extends State<CashFlowPage> {
  List<AccountingPeriod> _periods = const [];
  AccountingPeriod? _from;
  AccountingPeriod? _to;
  CashFlowReport? _report;
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
        ..sort((a, b) => a.startsOn.compareTo(b.startsOn));
      final AccountingPeriod? current = currentPeriod(ordered);
      setState(() {
        _periods = ordered;
        _to = current;
        // The year so far: from the first month of the current year.
        _from = current == null
            ? null
            : ordered.firstWhere(
                (period) => period.financialYearId == current.financialYearId,
              );
      });
      await _load();
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() => _error = exception.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _load() async {
    final AccountingPeriod? from = _from;
    final AccountingPeriod? to = _to;
    if (from == null || to == null) return;
    if (from.financialYearId != to.financialYearId) {
      setState(() => _error = 'A cash flow statement runs within one financial '
          'year; choose two months of the same year.');
      return;
    }
    if (from.startsOn.compareTo(to.startsOn) > 0) {
      setState(() => _error = 'The From month is after the To month.');
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final CashFlowReport report =
          await widget.api.cashFlow(fromPeriodId: from.id, toPeriodId: to.id);
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

  Widget _picker(String label, AccountingPeriod? value, Key key,
          ValueChanged<AccountingPeriod> onChanged) =>
      SizedBox(
        width: 190,
        child: DropdownButtonFormField<String>(
          key: key,
          initialValue: value?.id,
          isExpanded: true,
          decoration: InputDecoration(labelText: label, isDense: true),
          items: [
            for (final AccountingPeriod period in _periods)
              DropdownMenuItem(
                value: period.id,
                child: Text(period.name, overflow: TextOverflow.ellipsis),
              ),
          ],
          onChanged: (id) {
            final AccountingPeriod? match =
                _periods.where((period) => period.id == id).firstOrNull;
            if (match == null) return;
            onChanged(match);
            unawaited(_load());
          },
        ),
      );

  @override
  Widget build(BuildContext context) {
    if (!_canView) {
      return const StandardEmptyState(
        type: EmptyStateType.noPermissions,
        title: 'Cash flow statement',
        message: 'You do not have permission to view the cash flow statement.',
      );
    }
    if (!widget.hasActiveFirm) {
      return const StandardEmptyState(
        type: EmptyStateType.noFirmSelected,
        title: 'Cash flow statement',
        message: 'Choose a firm to see its cash flow.',
      );
    }
    return LoadingOverlay(
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
                _picker('From', _from, const ValueKey('cf-from'),
                    (period) => _from = period),
                _picker('To', _to, const ValueKey('cf-to'),
                    (period) => _to = period),
                IconButton(
                  tooltip: 'Refresh',
                  onPressed: _loading ? null : () => unawaited(_load()),
                  icon: const Icon(Icons.refresh),
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
  }

  Widget _body(BuildContext context) {
    final CashFlowReport? report = _report;
    if (_periods.isEmpty && !_loading) {
      return const StandardEmptyState(
        type: EmptyStateType.noRecords,
        title: 'No accounting periods',
        message: 'A cash flow statement is drawn for months of a financial '
            'year. Create a financial year and its periods first.',
      );
    }
    if (report == null) return const SizedBox.shrink();
    final ThemeData theme = Theme.of(context);
    return SingleChildScrollView(
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Phase2WideTable(
            table: DataTable(
              columns: const [
                DataColumn(label: Text('Particulars')),
                DataColumn(label: Text('Amount'), numeric: true),
              ],
              rows: [
                _heading(context, 'Cash flows from operating activities'),
                _line('Net profit', report.netProfit),
                _heading(context, 'Adjustments for working capital',
                    small: true),
                for (final CashFlowLine line in report.operating)
                  _line(line.accountName, line.amount, indent: true),
                _total(context, 'Net cash from operating activities',
                    report.operatingTotal),
                _heading(context, 'Cash flows from investing activities'),
                for (final CashFlowLine line in report.investing)
                  _line(line.accountName, line.amount, indent: true),
                _total(context, 'Net cash from investing activities',
                    report.investingTotal),
                _heading(context, 'Cash flows from financing activities'),
                for (final CashFlowLine line in report.financing)
                  _line(line.accountName, line.amount, indent: true),
                _total(context, 'Net cash from financing activities',
                    report.financingTotal),
                _total(context, 'Net increase/(decrease) in cash',
                    report.netChange,
                    emphasis: true),
                _line('Cash and bank at the start', report.openingCash),
                _total(context, 'Cash and bank at the end', report.closingCash,
                    emphasis: true),
              ],
            ),
          ),
          if (!report.isReconciled)
            Padding(
              padding: const EdgeInsets.only(top: AppSpacing.md),
              child: Row(children: [
                Icon(Icons.warning_amber, color: theme.colorScheme.error),
                const SizedBox(width: AppSpacing.sm),
                Expanded(
                  child: Text(
                    "Does not reconcile to cash and bank — check the chart's "
                    'groups',
                    key: const ValueKey('cf-not-reconciled'),
                    style: TextStyle(color: theme.colorScheme.error),
                  ),
                ),
              ]),
            ),
        ],
      ),
    );
  }

  DataRow _heading(BuildContext context, String title, {bool small = false}) =>
      DataRow(cells: [
        DataCell(Text(
          title,
          style: small
              ? Theme.of(context).textTheme.bodySmall
              : Theme.of(context).textTheme.titleSmall,
        )),
        const DataCell(Text('')),
      ]);

  DataRow _line(String label, String amount, {bool indent = false}) =>
      DataRow(cells: [
        DataCell(Padding(
          padding: EdgeInsets.only(left: indent ? AppSpacing.lg : 0),
          child: Text(label),
        )),
        DataCell(Text(presentAmount(amount))),
      ]);

  DataRow _total(BuildContext context, String label, String amount,
      {bool emphasis = false}) {
    final TextStyle? style = emphasis
        ? Theme.of(context).textTheme.titleSmall
        : Theme.of(context).textTheme.bodyMedium;
    return DataRow(
      color: WidgetStatePropertyAll(
        Theme.of(context).colorScheme.surfaceContainerHighest,
      ),
      cells: [
        DataCell(Text(label, style: style)),
        DataCell(Text(presentAmount(amount), style: style)),
      ],
    );
  }
}
