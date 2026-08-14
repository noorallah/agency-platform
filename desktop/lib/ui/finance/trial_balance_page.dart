import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/security/permission_service.dart';
import '../../models/finance.dart';
import '../workspace/desktop_framework.dart';

/// The trial balance for one accounting period.
///
/// Every goods receipt, dispatch and invoice has been posting to the general
/// ledger since the finance module went live, and until now nothing in the
/// client could show the result: a firm could trade for a year with no way to
/// see whether its books balanced.
class TrialBalancePage extends StatefulWidget {
  const TrialBalancePage({
    super.key,
    required this.api,
    required this.permissions,
    required this.hasActiveFirm,
  });

  final ApiClient api;
  final PermissionService permissions;
  final bool hasActiveFirm;

  @override
  State<TrialBalancePage> createState() => _TrialBalancePageState();
}

class _TrialBalancePageState extends State<TrialBalancePage> {
  List<AccountingPeriod> _periods = const [];
  AccountingPeriod? _period;
  TrialBalanceReport _report = TrialBalanceReport.empty;
  bool _loading = false;
  String? _error;

  bool get _canView => widget.permissions.hasPermission('LEDGER_VIEW');

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
      // Newest first: the period somebody wants is almost always the one they
      // are in, and it is the last one the year created.
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
      final TrialBalanceReport report = await widget.api.trialBalance(period.id);
      if (!mounted) return;
      setState(() => _report = report);
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() {
        _error = exception.message;
        _report = TrialBalanceReport.empty;
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
        title: 'Trial balance',
        message: 'You do not have permission to view the ledger.',
      );
    }
    if (!widget.hasActiveFirm) {
      return const StandardEmptyState(
        type: EmptyStateType.noFirmSelected,
        title: 'Trial balance',
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
              const SizedBox(width: AppSpacing.lg),
              if (_report.lines.isNotEmpty) _balanceBadge(context),
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
          Expanded(
            child: _periods.isEmpty
                ? const StandardEmptyState(
                    type: EmptyStateType.noRecords,
                    title: 'No accounting periods',
                    message:
                        'A trial balance is drawn for a period. Create a financial '
                        'year and its periods first.',
                  )
                : _report.lines.isEmpty
                    ? const StandardEmptyState(
                        type: EmptyStateType.noRecords,
                        title: 'Nothing posted in this period',
                        message:
                            'No ledger entries fall in it yet. Completing a goods '
                            'receipt, dispatching a delivery note or approving an '
                            'invoice posts to the ledger.',
                      )
                    : _table(context),
          ),
        ],
      ),
    );
  }

  /// Whether the books balance, as the server reported it.
  Widget _balanceBadge(BuildContext context) => Chip(
        avatar: Icon(
          _report.isBalanced ? Icons.check_circle_outline : Icons.error_outline,
          size: 18,
          color: _report.isBalanced
              ? Theme.of(context).colorScheme.primary
              : Theme.of(context).colorScheme.error,
        ),
        label: Text(
          _report.isBalanced
              ? 'Balanced'
              : 'Out of balance by ${_difference()}',
        ),
      );

  String _difference() {
    final double debit = double.tryParse(_report.totalDebit) ?? 0;
    final double credit = double.tryParse(_report.totalCredit) ?? 0;
    return (debit - credit).abs().toStringAsFixed(2);
  }

  Widget _table(BuildContext context) => SingleChildScrollView(
        padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg),
        child: SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: DataTable(
            columns: const [
              DataColumn(label: Text('Code')),
              DataColumn(label: Text('Account')),
              DataColumn(label: Text('Type')),
              DataColumn(label: Text('Opening'), numeric: true),
              DataColumn(label: Text('Debit'), numeric: true),
              DataColumn(label: Text('Credit'), numeric: true),
              DataColumn(label: Text('Closing'), numeric: true),
            ],
            rows: [
              for (final TrialBalanceLine line in _report.lines)
                DataRow(cells: [
                  DataCell(Text(line.accountCode)),
                  DataCell(Text(line.accountName)),
                  DataCell(Text(line.accountType)),
                  DataCell(Text(line.openingBalance)),
                  DataCell(Text(line.periodDebit)),
                  DataCell(Text(line.periodCredit)),
                  DataCell(Text(line.closingBalance)),
                ]),
              DataRow(
                color: WidgetStatePropertyAll(
                  Theme.of(context).colorScheme.surfaceContainerHighest,
                ),
                cells: [
                  const DataCell(Text('')),
                  const DataCell(Text('Total')),
                  const DataCell(Text('')),
                  const DataCell(Text('')),
                  DataCell(Text(_report.totalDebit)),
                  DataCell(Text(_report.totalCredit)),
                  const DataCell(Text('')),
                ],
              ),
            ],
          ),
        ),
      );
}
