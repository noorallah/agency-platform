// The two things a commission payout needs a form for: accruing a period,
// and paying one.
//
// Both are deliberately small. The accrual takes a period -- the day it
// starts and how many days it runs -- and nothing else,
// because the amounts come from the report rather than from anybody's typing;
// the payment takes a date and the account the money left, because that is
// the only thing the ledger cannot work out for itself.

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/api/concurrency.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../models/commission.dart';
import '../workspace/desktop_framework.dart';
import 'commission_page.dart' show CommissionDateField, isoDate, parseIsoDate;

/// Turn what a period earned into draft payouts.
///
/// One per person who earned something. Nobody who earned nothing gets a row:
/// a payout of zero is paperwork that has to be approved and paid like any
/// other and says nothing the report does not.
class CommissionAccrualDialog extends StatefulWidget {
  const CommissionAccrualDialog({
    super.key,
    required this.api,
    this.previous,
    this.today,
  });

  final ApiClient api;

  /// The newest payout still standing, if there is one. The form then offers
  /// the period that follows it, the same length, so a firm paying every
  /// fortnight is not offered a month each time.
  final CommissionPayoutRecord? previous;

  /// The day the default period is worked out from. Left null it is this
  /// computer's day.
  final DateTime? today;

  /// The longest period the server takes as a number of days.
  static const int maxDays = 366;

  @override
  State<CommissionAccrualDialog> createState() =>
      _CommissionAccrualDialogState();
}

class _CommissionAccrualDialogState extends State<CommissionAccrualDialog> {
  late final TextEditingController _from;
  late final TextEditingController _days;

  bool _running = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    final (DateTime start, int days) = _proposed();
    _from = TextEditingController(text: isoDate(start));
    _days = TextEditingController(text: '$days');
    // The end is worked out as either is typed, so it is on screen before
    // anything is sent.
    _from.addListener(_reworked);
    _days.addListener(_reworked);
  }

  void _reworked() {
    if (mounted) setState(() {});
  }

  /// The period offered: the one after the last payout, or last month.
  ///
  /// After a whole calendar month the next whole month follows, whatever its
  /// length -- thirty days after April would stop a day short of May's end.
  /// After anything else the same number of days follows. With nothing to
  /// follow it is last month, because that is the period a firm accrues at
  /// the start of this one; the current month is still collecting money.
  (DateTime, int) _proposed() {
    final DateTime? lastStart = parseIsoDate(widget.previous?.periodStart ?? '');
    final DateTime? lastEnd = parseIsoDate(widget.previous?.periodEnd ?? '');
    if (lastStart != null && lastEnd != null && !lastEnd.isBefore(lastStart)) {
      final DateTime start =
          DateTime(lastEnd.year, lastEnd.month, lastEnd.day + 1);
      final bool wholeMonth = lastStart.day == 1 &&
          lastStart.year == lastEnd.year &&
          lastStart.month == lastEnd.month &&
          start.day == 1;
      if (wholeMonth) {
        return (start, DateUtils.getDaysInMonth(start.year, start.month));
      }
      return (start, _daysBetween(lastStart, lastEnd) + 1);
    }
    final DateTime now = widget.today ?? DateTime.now();
    final DateTime start = DateTime(now.year, now.month - 1);
    return (start, DateUtils.getDaysInMonth(start.year, start.month));
  }

  /// Whole days from one date to another, by the calendar rather than by
  /// hours, so a clock change inside the period cannot lose one.
  static int _daysBetween(DateTime from, DateTime to) =>
      DateTime.utc(to.year, to.month, to.day)
          .difference(DateTime.utc(from.year, from.month, from.day))
          .inDays;

  /// The number of days typed, or null where it is not one the server takes.
  int? get _dayCount {
    final int? days = int.tryParse(_days.text.trim());
    if (days == null || days < 1 || days > CommissionAccrualDialog.maxDays) {
      return null;
    }
    return days;
  }

  /// The last day of the period as typed, the first day counted.
  DateTime? get _lastDay {
    final DateTime? from = parseIsoDate(_from.text);
    final int? days = _dayCount;
    if (from == null || days == null) return null;
    return DateTime(from.year, from.month, from.day + days - 1);
  }

  @override
  void dispose() {
    _from.dispose();
    _days.dispose();
    super.dispose();
  }

  Future<void> _run() async {
    final DateTime? from = parseIsoDate(_from.text);
    if (from == null) {
      setState(() => _error = 'Enter the start date as YYYY-MM-DD.');
      return;
    }
    final int? days = _dayCount;
    if (days == null) {
      setState(() => _error = 'Enter the number of days as a whole number '
          'from 1 to ${CommissionAccrualDialog.maxDays}.');
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
        'period_days': days,
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
    final DateTime? lastDay = _lastDay;
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
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: CommissionDateField(
                    controller: _from,
                    label: 'Starts on',
                    enabled: !_running,
                  ),
                ),
                const SizedBox(width: AppSpacing.lg),
                Expanded(
                  child: TextField(
                    key: const ValueKey<String>('accrual-days'),
                    controller: _days,
                    enabled: !_running,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(
                      labelText: 'Number of days',
                      helperText: 'The start day is counted',
                      isDense: true,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: AppSpacing.md),
            Text(
              lastDay == null
                  ? 'Ends on: enter a start date and a number of days.'
                  : 'Ends on ${isoDate(lastDay)}.',
              key: const ValueKey<String>('accrual-ends-on'),
              style: theme.textTheme.bodyMedium,
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
///
/// Commission leaves through the firm's cash or bank account -- the ones it
/// nominated under its control accounts, as a receipt or a payment does --
/// so the form asks which of the two rather than offering a chart of
/// accounts. A picker of ASSET accounts used to let a payment land on Trade
/// Receivables (D-TER-5); the API now refuses anything but the two.
class CommissionPaymentDialog extends StatefulWidget {
  const CommissionPaymentDialog({
    super.key,
    required this.payout,
    this.today,
  });

  final CommissionPayoutRecord payout;

  /// The day the payment is dated by default and the latest it may be. Left
  /// null it is this computer's day; the server judges it again on the firm's
  /// own calendar (D-PRC-9).
  final DateTime? today;

  @override
  State<CommissionPaymentDialog> createState() =>
      _CommissionPaymentDialogState();
}

class _CommissionPaymentDialogState extends State<CommissionPaymentDialog> {
  late final DateTime _today =
      DateUtils.dateOnly(widget.today ?? DateTime.now());

  /// The earliest day money may leave: the day the debt was agreed, which
  /// is the approval, and never before the accrual. `approved_at` is an
  /// instant, read here in this computer's day; the server's refusal stands
  /// if the firm's calendar disagrees.
  late final DateTime _earliest = () {
    final DateTime? approved =
        DateTime.tryParse(widget.payout.approvedAt)?.toLocal();
    final DateTime? accrued = DateTime.tryParse(widget.payout.accruedOn);
    // Nothing known of either: the picker's old five-year reach.
    DateTime first = DateTime(_today.year - 5, _today.month, _today.day);
    for (final DateTime? known in <DateTime?>[accrued, approved]) {
      if (known != null && DateUtils.dateOnly(known).isAfter(first)) {
        first = DateUtils.dateOnly(known);
      }
    }
    return first.isAfter(_today) ? _today : first;
  }();

  late final TextEditingController _paidOn =
      TextEditingController(text: isoDate(_today));
  String _method = 'BANK';
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
    if (DateUtils.dateOnly(paidOn).isAfter(_today)) {
      setState(() => _error =
          'A payout cannot be paid on a day that has not happened yet.');
      return;
    }
    if (DateUtils.dateOnly(paidOn).isBefore(_earliest)) {
      setState(() => _error = 'A payout cannot be paid before it was '
          'approved (${isoDate(_earliest)}).');
      return;
    }
    Navigator.of(context).pop(<String, dynamic>{
      'paid_on': isoDate(paidOn),
      'method': _method,
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
              helper: 'YYYY-MM-DD, from the day it was approved to today',
              firstDate: _earliest,
              lastDate: _today,
            ),
            const SizedBox(height: AppSpacing.md),
            DropdownButtonFormField<String>(
              isExpanded: true,
              initialValue: _method,
              decoration: const InputDecoration(
                labelText: 'Paid from',
                helperText: "The firm's bank or cash account, as set under "
                    'its control accounts.',
              ),
              items: const [
                DropdownMenuItem<String>(value: 'BANK', child: Text('Bank')),
                DropdownMenuItem<String>(value: 'CASH', child: Text('Cash')),
              ],
              onChanged: (value) =>
                  setState(() => _method = value ?? _method),
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
          onPressed: _submit,
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
