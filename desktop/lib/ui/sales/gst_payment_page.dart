import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/security/permission_service.dart';
import '../../models/expense.dart';
import '../../models/gst_payment.dart';
import '../workspace/desktop_framework.dart';
import '../workspace/reason_prompt.dart';

/// Paying a month's GST (backlog 63): what the month owes, what its input
/// credit pays by the statutory order, the cash left to pay, and recording the
/// challan, which posts the set-off and the payment in one journal.
///
/// The order is the law's (section 49(5), rule 88A): IGST credit first and
/// wholly, CGST credit never against SGST nor SGST against CGST, cess only
/// against cess. Filing on the portal is not done here.
class GstPaymentPage extends StatefulWidget {
  const GstPaymentPage({
    super.key,
    required this.api,
    required this.permissions,
    required this.hasActiveFirm,
    this.today,
  });

  final ApiClient api;
  final PermissionService permissions;
  final bool hasActiveFirm;

  /// For tests; the clock otherwise.
  final DateTime? today;

  @override
  State<GstPaymentPage> createState() => _GstPaymentPageState();
}

String _iso(DateTime value) => value.toIso8601String().substring(0, 10);

String _month(DateTime value) =>
    '${value.year.toString().padLeft(4, '0')}-'
    '${value.month.toString().padLeft(2, '0')}';

class _GstPaymentPageState extends State<GstPaymentPage> {
  late final DateTime _today = widget.today ?? DateTime.now();
  late String _period =
      _month(DateTime(_today.year, _today.month - 1)); // last month
  late final TextEditingController _paidOn =
      TextEditingController(text: _iso(_today));
  final TextEditingController _cpin = TextEditingController();
  final TextEditingController _cin = TextEditingController();
  final TextEditingController _interest = TextEditingController();
  final TextEditingController _lateFee = TextEditingController();
  final Map<String, TextEditingController> _opening = {
    for (final String head in const ['igst', 'cgst', 'sgst', 'cess'])
      head: TextEditingController(),
  };
  GstPaymentPreview? _preview;
  List<GstPaymentRecord> _history = const [];
  ExpenseAccountChoices? _accounts;
  String? _moneyAccountId;
  String? _interestAccountId;
  String? _lateFeeAccountId;
  bool _loading = false;
  String? _error;
  String? _notice;

  bool get _canView =>
      widget.permissions.hasPermission('ACCOUNT_VIEW') ||
      widget.permissions.hasPermission('SALES_VIEW');
  bool get _canRecord => widget.permissions.hasPermission('JOURNAL_POST');

  List<String> get _months => [
        for (int back = 0; back < 18; back++)
          _month(DateTime(_today.year, _today.month - back)),
      ];

  @override
  void initState() {
    super.initState();
    if (widget.hasActiveFirm && _canView) unawaited(_loadAll());
  }

  @override
  void dispose() {
    for (final TextEditingController controller in [
      _paidOn,
      _cpin,
      _cin,
      _interest,
      _lateFee,
      ..._opening.values,
    ]) {
      controller.dispose();
    }
    super.dispose();
  }

  Future<void> _loadAll() async {
    await Future.wait([_loadPreview(), _loadHistory(), _loadAccounts()]);
  }

  Future<void> _loadAccounts() async {
    if (!_canRecord) return;
    try {
      final ExpenseAccountChoices choices =
          await widget.api.expenseAccountChoices();
      if (!mounted) return;
      setState(() {
        _accounts = choices;
        if (choices.paidFromAccounts.length == 1) {
          _moneyAccountId = choices.paidFromAccounts.single.id;
        }
      });
    } on ApiException {
      // The record form says what is missing when it is used.
    }
  }

  Future<void> _loadHistory() async {
    try {
      final List<GstPaymentRecord> rows = await widget.api.gstPayments();
      if (!mounted) return;
      setState(() => _history = rows);
    } on ApiException catch (exception) {
      if (mounted) setState(() => _error = exception.message);
    }
  }

  Future<void> _loadPreview() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final GstPaymentPreview preview = await widget.api.gstPaymentPreview(
        returnPeriod: _period,
        paymentDate: _paidOn.text.trim(),
        openingCredit: {
          for (final MapEntry<String, TextEditingController> entry
              in _opening.entries)
            entry.key: entry.value.text,
        },
      );
      if (!mounted) return;
      setState(() {
        _preview = preview;
        _interest.text = (double.tryParse(preview.suggestedInterest) ?? 0) > 0
            ? preview.suggestedInterest
            : '';
      });
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() {
        _error = exception.message;
        _preview = null;
      });
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _record() async {
    final GstPaymentPreview? preview = _preview;
    if (preview == null) return;
    if (_moneyAccountId == null) {
      setState(() => _error = 'Choose the bank account the challan was paid from.');
      return;
    }
    final double interest = double.tryParse(_interest.text.trim()) ?? 0;
    final double lateFee = double.tryParse(_lateFee.text.trim()) ?? 0;
    if (interest > 0 && _interestAccountId == null) {
      setState(() => _error = 'Choose the expense account for the interest.');
      return;
    }
    if (lateFee > 0 && _lateFeeAccountId == null) {
      setState(() => _error = 'Choose the expense account for the late fee.');
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final GstPaymentRecord saved = await widget.api.recordGstPayment({
        'return_period': _period,
        'payment_date': _paidOn.text.trim(),
        'money_account_id': _moneyAccountId,
        if (_cpin.text.trim().isNotEmpty) 'challan_cpin': _cpin.text.trim(),
        if (_cin.text.trim().isNotEmpty) 'challan_cin': _cin.text.trim(),
        if (interest > 0) ...{
          'interest_amount': _interest.text.trim(),
          'interest_account_id': _interestAccountId,
        },
        if (lateFee > 0) ...{
          'late_fee_amount': _lateFee.text.trim(),
          'late_fee_account_id': _lateFeeAccountId,
        },
        if (!preview.previousSettled)
          for (final MapEntry<String, TextEditingController> entry
              in _opening.entries)
            if (entry.value.text.trim().isNotEmpty)
              'opening_credit_${entry.key}': entry.value.text.trim(),
      });
      if (!mounted) return;
      setState(() => _notice =
          'GST for ${saved.returnPeriod} recorded: ${saved.cashTotal} paid in '
          'cash, the rest set off from credit.');
      await _loadAll();
    } on ApiException catch (exception) {
      if (mounted) setState(() => _error = exception.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _reverse(GstPaymentRecord row) async {
    final String? reason = await askForReason(
      context,
      title: 'Reverse GST for ${row.returnPeriod}',
      explanation: 'The set-off and the payment are taken back with a mirror '
          'journal. Only the latest settled month can be reversed.',
      confirmLabel: 'Reverse',
    );
    if (reason == null || !mounted) return;
    try {
      await widget.api.reverseGstPayment(row.id, reason);
      if (!mounted) return;
      setState(() => _notice = 'GST for ${row.returnPeriod} reversed.');
      await _loadAll();
    } on ApiException catch (exception) {
      if (mounted) setState(() => _error = exception.message);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!_canView) {
      return const StandardEmptyState(
        type: EmptyStateType.noPermissions,
        title: 'GST payment',
        message: 'You do not have permission to view what GST is owed.',
      );
    }
    if (!widget.hasActiveFirm) {
      return const StandardEmptyState(
        type: EmptyStateType.noFirmSelected,
        title: 'GST payment',
        message: 'Choose a firm to see what it owes.',
      );
    }
    final ThemeData theme = Theme.of(context);
    final GstPaymentPreview? preview = _preview;
    return LoadingOverlay(
      loading: _loading,
      child: ListView(
        padding: const EdgeInsets.all(AppSpacing.lg),
        children: [
          Wrap(
            spacing: AppSpacing.md,
            runSpacing: AppSpacing.sm,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              SizedBox(
                width: 150,
                child: DropdownButtonFormField<String>(
                  key: const ValueKey('gst-pay-period'),
                  initialValue: _period,
                  decoration: const InputDecoration(
                      labelText: 'Return month', isDense: true),
                  items: [
                    for (final String month in _months)
                      DropdownMenuItem(value: month, child: Text(month)),
                  ],
                  onChanged: (value) {
                    if (value == null) return;
                    setState(() => _period = value);
                    unawaited(_loadPreview());
                  },
                ),
              ),
              SizedBox(
                width: 150,
                child: TextField(
                  key: const ValueKey('gst-pay-date'),
                  controller: _paidOn,
                  decoration: const InputDecoration(
                      labelText: 'Paid on', isDense: true),
                  onSubmitted: (_) => unawaited(_loadPreview()),
                ),
              ),
              Phase2Refresh(
                onPressed: _loading ? null : () => unawaited(_loadPreview()),
                child: const SizedBox.shrink(),
              ),
            ],
          ),
          if (_error != null)
            Padding(
              padding: const EdgeInsets.only(top: AppSpacing.sm),
              child: Text(_error!,
                  style: TextStyle(color: theme.colorScheme.error)),
            ),
          if (_notice != null)
            Padding(
              padding: const EdgeInsets.only(top: AppSpacing.sm),
              child: Text(_notice!, style: theme.textTheme.bodyMedium),
            ),
          if (preview != null) ...[
            const SizedBox(height: AppSpacing.md),
            Text(
              'Due ${preview.dueDate}'
              '${preview.daysLate > 0 ? ' -- ${preview.daysLate} days late; interest at 18% a year is suggested below' : ''}.'
              ' Cash to pay: ${preview.cashTotal}.',
              style: theme.textTheme.titleSmall,
            ),
            if (!preview.previousSettled) ...[
              const SizedBox(height: AppSpacing.sm),
              Text(
                'No settlement of the month before is recorded. If the firm '
                'carried credit in from before, enter it from the portal\'s '
                'electronic credit ledger, then refresh.',
                style: theme.textTheme.bodySmall,
              ),
              Wrap(spacing: AppSpacing.md, children: [
                for (final MapEntry<String, TextEditingController> entry
                    in _opening.entries)
                  SizedBox(
                    width: 130,
                    child: TextField(
                      key: ValueKey('gst-pay-opening-${entry.key}'),
                      controller: entry.value,
                      decoration: InputDecoration(
                        labelText: 'Opening ${entry.key.toUpperCase()}',
                        isDense: true,
                      ),
                    ),
                  ),
              ]),
            ],
            const SizedBox(height: AppSpacing.sm),
            Phase2WideTable(
              table: DataTable(
                columns: const [
                  DataColumn(label: Text('Head')),
                  DataColumn(label: Text('Owed'), numeric: true),
                  DataColumn(label: Text('Credit b/f'), numeric: true),
                  DataColumn(label: Text('Credit available'), numeric: true),
                  DataColumn(label: Text('Paid by credit'), numeric: true),
                  DataColumn(label: Text('Cash'), numeric: true),
                  DataColumn(
                      label: Tooltip(
                        message: 'Reverse charge on purchases (3B 3.1(d)): '
                            'paid in cash only, never by credit',
                        child: Text('Reverse charge (cash)'),
                      ),
                      numeric: true),
                  DataColumn(label: Text('Credit carried'), numeric: true),
                ],
                rows: [
                  for (final GstHeadRow row in preview.heads)
                    DataRow(cells: [
                      DataCell(Text(row.head)),
                      DataCell(Text(row.liability)),
                      DataCell(Text(row.creditBroughtForward)),
                      DataCell(Text(row.creditAvailable)),
                      DataCell(Text(row.paidByCredit)),
                      DataCell(Text(row.cash)),
                      DataCell(Text(row.reverseCharge,
                          key: ValueKey('gst-pay-rcm-${row.head}'))),
                      DataCell(Text(row.carriedForward)),
                    ]),
                ],
              ),
            ),
            if (preview.utilisation.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(top: AppSpacing.sm),
                child: Text(
                  'Credit used: ${preview.utilisation.join('; ')}.',
                  style: theme.textTheme.bodySmall,
                ),
              ),
            if (_canRecord) ...[
              const Divider(height: AppSpacing.xl),
              Text('Record the challan', style: theme.textTheme.titleSmall),
              const SizedBox(height: AppSpacing.sm),
              _recordForm(context),
            ],
          ],
          const Divider(height: AppSpacing.xl),
          Text('Months recorded', style: theme.textTheme.titleSmall),
          if (_history.isEmpty)
            Text('None yet.', style: theme.textTheme.bodySmall),
          for (final GstPaymentRecord row in _history)
            ListTile(
              dense: true,
              title: Text('${row.returnPeriod}  ${row.status}'),
              subtitle: Text(
                'Paid ${row.paymentDate}: cash ${row.cashTotal}'
                '${row.challanCpin.isEmpty ? '' : ', CPIN ${row.challanCpin}'}',
              ),
              trailing: _canRecord && !row.isReversed
                  ? TextButton(
                      key: ValueKey('gst-pay-reverse-${row.returnPeriod}'),
                      onPressed: () => unawaited(_reverse(row)),
                      child: const Text('Reverse'),
                    )
                  : null,
            ),
        ],
      ),
    );
  }

  Widget _account(String label, String? value, List<ExpenseAccountOption> options,
          Key key, ValueChanged<String?> onChanged) =>
      SizedBox(
        width: 240,
        child: DropdownButtonFormField<String>(
          key: key,
          initialValue: value,
          isExpanded: true,
          decoration: InputDecoration(labelText: label, isDense: true),
          items: [
            for (final ExpenseAccountOption account in options)
              DropdownMenuItem(
                value: account.id,
                child: Text('${account.code} ${account.name}',
                    overflow: TextOverflow.ellipsis),
              ),
          ],
          onChanged: onChanged,
        ),
      );

  Widget _recordForm(BuildContext context) {
    final ExpenseAccountChoices? accounts = _accounts;
    final List<ExpenseAccountOption> money =
        accounts?.paidFromAccounts ?? const [];
    final List<ExpenseAccountOption> expenses =
        accounts?.expenseAccounts ?? const [];
    return Wrap(
      spacing: AppSpacing.md,
      runSpacing: AppSpacing.sm,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        _account('Paid from', _moneyAccountId, money,
            const ValueKey('gst-pay-bank'),
            (id) => setState(() => _moneyAccountId = id)),
        SizedBox(
          width: 170,
          child: TextField(
            key: const ValueKey('gst-pay-cpin'),
            controller: _cpin,
            decoration: const InputDecoration(labelText: 'CPIN', isDense: true),
          ),
        ),
        SizedBox(
          width: 170,
          child: TextField(
            key: const ValueKey('gst-pay-cin'),
            controller: _cin,
            decoration: const InputDecoration(labelText: 'CIN', isDense: true),
          ),
        ),
        SizedBox(
          width: 120,
          child: TextField(
            key: const ValueKey('gst-pay-interest'),
            controller: _interest,
            decoration:
                const InputDecoration(labelText: 'Interest', isDense: true),
          ),
        ),
        _account('Interest to', _interestAccountId, expenses,
            const ValueKey('gst-pay-interest-account'),
            (id) => setState(() => _interestAccountId = id)),
        SizedBox(
          width: 120,
          child: TextField(
            key: const ValueKey('gst-pay-late-fee'),
            controller: _lateFee,
            decoration:
                const InputDecoration(labelText: 'Late fee', isDense: true),
          ),
        ),
        _account('Late fee to', _lateFeeAccountId, expenses,
            const ValueKey('gst-pay-late-fee-account'),
            (id) => setState(() => _lateFeeAccountId = id)),
        FilledButton(
          key: const ValueKey('gst-pay-record'),
          onPressed: _loading ? null : () => unawaited(_record()),
          child: const Text('Record GST payment'),
        ),
      ],
    );
  }
}
