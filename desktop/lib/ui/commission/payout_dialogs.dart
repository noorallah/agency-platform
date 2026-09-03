// The two things a commission payout needs a form for: accruing a period,
// and paying one.
//
// Both are deliberately small. The accrual takes a period and nothing else,
// because the amounts come from the report rather than from anybody's typing;
// the payment takes a date and the account the money left, because that is
// the only thing the ledger cannot work out for itself.

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/api/concurrency.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../models/commission.dart';
import '../../models/finance.dart';
import '../workspace/desktop_framework.dart';
import 'commission_page.dart' show CommissionDateField, isoDate, parseIsoDate;

/// Turn what a period earned into draft payouts.
///
/// One per person who earned something. Nobody who earned nothing gets a row:
/// a payout of zero is paperwork that has to be approved and paid like any
/// other and says nothing the report does not.
class CommissionAccrualDialog extends StatefulWidget {
  const CommissionAccrualDialog({super.key, required this.api});

  final ApiClient api;

  @override
  State<CommissionAccrualDialog> createState() =>
      _CommissionAccrualDialogState();
}

class _CommissionAccrualDialogState extends State<CommissionAccrualDialog> {
  late final TextEditingController _from =
      TextEditingController(text: isoDate(_firstOfLastMonth()));
  late final TextEditingController _to =
      TextEditingController(text: isoDate(_lastOfLastMonth()));

  bool _running = false;
  String? _error;

  /// Last month, because that is the period a firm accrues at the start of
  /// this one. Defaulting to the current month would offer a period that is
  /// still collecting money.
  static DateTime _firstOfLastMonth() {
    final DateTime now = DateTime.now();
    return DateTime(now.year, now.month - 1);
  }

  static DateTime _lastOfLastMonth() {
    final DateTime now = DateTime.now();
    return DateTime(now.year, now.month, 0);
  }

  @override
  void dispose() {
    _from.dispose();
    _to.dispose();
    super.dispose();
  }

  Future<void> _run() async {
    final DateTime? from = parseIsoDate(_from.text);
    final DateTime? to = parseIsoDate(_to.text);
    if (from == null || to == null) {
      setState(() => _error = 'Enter both dates as YYYY-MM-DD.');
      return;
    }
    if (to.isBefore(from)) {
      setState(() => _error = 'The period cannot end before it starts.');
      return;
    }
    setState(() {
      _running = true;
      _error = null;
    });
    try {
      final List<CommissionPayoutRecord> made =
          await widget.api.accrueCommissionPayouts(<String, dynamic>{
        'period_start': isoDate(from),
        'period_end': isoDate(to),
      });
      if (!mounted) return;
      NotificationService.show(
        context,
        made.isEmpty
            ? 'Nobody earned anything in that period.'
            : '${made.length} payout(s) accrued as drafts.',
        kind: made.isEmpty
            ? AppNotificationKind.information
            : AppNotificationKind.success,
      );
      Navigator.of(context).pop(true);
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.message;
        _running = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return AlertDialog(
      title: const Text('Accrue a period'),
      content: SizedBox(
        width: 460,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              'One draft payout per person who earned something, holding what '
              'the report says today. Nothing re-reads it afterwards.',
              style: theme.textTheme.bodySmall,
            ),
            const SizedBox(height: AppSpacing.md),
            Row(
              children: [
                Expanded(
                  child: CommissionDateField(
                    controller: _from,
                    label: 'From',
                    enabled: !_running,
                  ),
                ),
                const SizedBox(width: AppSpacing.lg),
                Expanded(
                  child: CommissionDateField(
                    controller: _to,
                    label: 'To',
                    enabled: !_running,
                  ),
                ),
              ],
            ),
            if (_error != null) ...[
              const SizedBox(height: AppSpacing.lg),
              Text(
                _error!,
                style: theme.textTheme.bodySmall
                    ?.copyWith(color: theme.colorScheme.error),
              ),
            ],
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: _running ? null : () => Navigator.of(context).pop(false),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: _running ? null : _run,
          child: Text(_running ? 'Accruing…' : 'Accrue'),
        ),
      ],
    );
  }
}

/// Record that an approved payout has been paid.
class CommissionPaymentDialog extends StatefulWidget {
  const CommissionPaymentDialog({
    super.key,
    required this.payout,
    required this.accounts,
  });

  final CommissionPayoutRecord payout;

  /// Only accounts money can leave from. Offering the whole chart would
  /// invite a payment posted against revenue.
  final List<LedgerAccount> accounts;

  @override
  State<CommissionPaymentDialog> createState() =>
      _CommissionPaymentDialogState();
}

class _CommissionPaymentDialogState extends State<CommissionPaymentDialog> {
  late final TextEditingController _paidOn =
      TextEditingController(text: isoDate(DateTime.now()));
  late String _accountId =
      widget.accounts.isEmpty ? '' : widget.accounts.first.id;
  String? _error;

  @override
  void dispose() {
    _paidOn.dispose();
    super.dispose();
  }

  void _submit() {
    final DateTime? paidOn = parseIsoDate(_paidOn.text);
    if (paidOn == null) {
      setState(() => _error = 'Enter the date the money left as YYYY-MM-DD.');
      return;
    }
    if (_accountId.isEmpty) {
      setState(() => _error = 'Choose the account the money left.');
      return;
    }
    Navigator.of(context).pop(<String, dynamic>{
      'paid_on': isoDate(paidOn),
      'money_account_id': _accountId,
    });
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return AlertDialog(
      title: Text('Pay ${widget.payout.salesmanName}'),
      content: SizedBox(
        width: 460,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              '${widget.payout.payableAmount} for '
              '${widget.payout.periodLabel}. The cost was recognised when '
              'this was approved; paying clears what is still owed.',
              style: theme.textTheme.bodySmall,
            ),
            const SizedBox(height: AppSpacing.md),
            CommissionDateField(
              controller: _paidOn,
              label: 'Paid on',
            ),
            const SizedBox(height: AppSpacing.md),
            if (widget.accounts.isEmpty)
              Text(
                'This firm has no cash or bank account to pay from. Add one '
                'to the chart of accounts first.',
                style: theme.textTheme.bodySmall
                    ?.copyWith(color: theme.colorScheme.error),
              )
            else
              DropdownButtonFormField<String>(
                isExpanded: true,
                initialValue: _accountId,
                decoration: const InputDecoration(labelText: 'Paid from'),
                items: [
                  for (final LedgerAccount account in widget.accounts)
                    DropdownMenuItem<String>(
                      value: account.id,
                      child: Text(
                        '${account.code} — ${account.name}',
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                ],
                onChanged: (value) =>
                    setState(() => _accountId = value ?? _accountId),
              ),
            if (_error != null) ...[
              const SizedBox(height: AppSpacing.lg),
              Text(
                _error!,
                style: theme.textTheme.bodySmall
                    ?.copyWith(color: theme.colorScheme.error),
              ),
            ],
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: widget.accounts.isEmpty ? null : _submit,
          child: const Text('Record payment'),
        ),
      ],
    );
  }
}


/// Correct what a draft payout owes, before anybody approves it.
///
/// Only a draft. Changing what was approved would leave the accrual journal
/// saying one number and the record saying another, and the way to correct an
/// approved payout is to cancel it -- which reverses the journal -- and accrue
/// the period again. The service refuses it either way; the screen says so
/// rather than letting somebody find out.
class CommissionAdjustmentDialog extends StatefulWidget {
  const CommissionAdjustmentDialog({
    super.key,
    required this.api,
    required this.payout,
  });

  final ApiClient api;
  final CommissionPayoutRecord payout;

  @override
  State<CommissionAdjustmentDialog> createState() =>
      _CommissionAdjustmentDialogState();
}

class _CommissionAdjustmentDialogState
    extends State<CommissionAdjustmentDialog> {
  late final TextEditingController _amount =
      TextEditingController(text: widget.payout.adjustmentAmount);
  late final TextEditingController _reason =
      TextEditingController(text: widget.payout.adjustmentReason);
  late final TextEditingController _notes =
      TextEditingController(text: widget.payout.notes);

  bool _saving = false;
  String? _error;

  @override
  void dispose() {
    // Owned here, not by the caller: disposing after `showDialog` returns
    // disposes mid-animation, with the fields still rebuilding.
    _amount.dispose();
    _reason.dispose();
    _notes.dispose();
    super.dispose();
  }

  double get _earned => double.tryParse(widget.payout.earnedAmount) ?? 0;

  double get _adjustment => double.tryParse(_amount.text.trim()) ?? 0;

  /// What the firm would owe. Shown live, because the interesting number is
  /// the total rather than the correction, and a negative one is refused.
  double get _payable => _earned + _adjustment;

  Future<void> _save() async {
    final String reason = _reason.text.trim();
    // The server refuses an unexplained adjustment; saying so here keeps the
    // typing rather than losing it to a round trip.
    if (_adjustment != 0 && reason.isEmpty) {
      setState(() => _error = 'Say why the payout is being adjusted. An '
          'adjustment with no reason is a number nobody can explain at the '
          'year end.');
      return;
    }
    if (_payable < 0) {
      setState(() => _error = 'That would make the payout negative. A payout '
          'cannot take money back — record what is owed as zero and settle '
          'the difference separately.');
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      await widget.api.updateCommissionPayout(
        widget.payout.id,
        <String, dynamic>{
          'adjustment_amount': _amount.text.trim().isEmpty
              ? '0'
              : _amount.text.trim(),
          'adjustment_reason': reason,
          'notes': _notes.text.trim(),
        },
        expectedVersion: widget.payout.version,
      );
      if (!mounted) return;
      Navigator.of(context).pop(true);
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.isConflict
            ? concurrencyMessage('payout', changesKept: true)
            : error.message;
        _saving = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) => WorkspaceDialog(
        title: 'Adjust ${widget.payout.salesmanName}',
        subtitle: '${widget.payout.periodStart} to '
            '${widget.payout.periodEnd}, on the '
            '${widget.payout.basis.toLowerCase()} basis',
        icon: Icons.tune,
        body: SingleChildScrollView(
          padding: const EdgeInsets.all(AppSpacing.md),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (_error != null) ...[
                Text(_error!, style: const TextStyle(color: Colors.redAccent)),
                const SizedBox(height: AppSpacing.sm),
              ],
              Text(
                'Earned ${widget.payout.earnedAmount} on measured '
                '${widget.payout.measuredAmount}. The earned figure was read '
                'once, when the period was accrued, so it does not move if a '
                'rate is corrected afterwards — an adjustment is how it gets '
                'put right.',
                style: Theme.of(context).textTheme.bodySmall,
              ),
              const SizedBox(height: AppSpacing.md),
              TextField(
                controller: _amount,
                keyboardType:
                    const TextInputType.numberWithOptions(signed: true),
                decoration: const InputDecoration(
                  labelText: 'Adjustment',
                  helperText: 'Negative to reduce what is owed. Blank or zero '
                      'for none.',
                  helperMaxLines: 2,
                ),
                onChanged: (_) => setState(() {}),
              ),
              const SizedBox(height: AppSpacing.sm),
              TextField(
                controller: _reason,
                decoration: const InputDecoration(
                  labelText: 'Reason',
                  helperText: 'Required for any adjustment other than zero.',
                  helperMaxLines: 2,
                ),
                onChanged: (_) => setState(() {}),
              ),
              const SizedBox(height: AppSpacing.sm),
              TextField(
                controller: _notes,
                maxLines: 2,
                decoration: const InputDecoration(labelText: 'Notes'),
              ),
              const SizedBox(height: AppSpacing.md),
              Text(
                'Payable becomes ${_payable.toStringAsFixed(2)}.',
                style: Theme.of(context).textTheme.titleSmall,
              ),
            ],
          ),
        ),
        onClose: () => Navigator.of(context).pop(false),
        onSave: _saving ? null : _save,
        saveLabel: 'Save',
      );
}
