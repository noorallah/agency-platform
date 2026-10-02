import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../models/settlement.dart';
import '../workspace/desktop_framework.dart';
import '../workspace/reason_prompt.dart';

/// Each supplier credit with what the return came back as and what the
/// supplier has handed back, and the two things to do about a refund: record
/// one, or read and reverse the ones already recorded.
///
/// Recording a refund posts to the ledger (money in, supplier payable down);
/// the server accepts one for a debit note's credit, or for a return whose
/// outcome is Refund, and its
/// refusal is shown inside the dialog that asked.
class SupplierCreditsDialog extends StatefulWidget {
  const SupplierCreditsDialog({
    super.key,
    required this.api,
    required this.vendorId,
    required this.vendorName,
    required this.canManage,
  });

  final ApiClient api;
  final String vendorId;
  final String vendorName;

  /// Whether the signed-in user may record or reverse a refund.
  final bool canManage;

  @override
  State<SupplierCreditsDialog> createState() => _SupplierCreditsDialogState();
}

class _SupplierCreditsDialogState extends State<SupplierCreditsDialog> {
  List<SupplierCredit> _credits = const [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final List<SupplierCredit> rows =
          await widget.api.supplierCredits(widget.vendorId);
      if (!mounted) return;
      setState(() => _credits = rows);
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() => _error = exception.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _record(SupplierCredit credit) async {
    final SupplierRefund? saved = await showDialog<SupplierRefund>(
      context: context,
      barrierDismissible: false,
      builder: (_) => RecordSupplierRefundDialog(api: widget.api, credit: credit),
    );
    if (saved == null || !mounted) return;
    await _load();
    if (!mounted) return;
    NotificationService.show(
      context,
      'Refund of ${saved.amount} recorded against ${credit.label} '
      'and posted to the ledger.',
      kind: AppNotificationKind.success,
    );
  }

  Future<void> _refunds(SupplierCredit credit) async {
    await showDialog<void>(
      context: context,
      builder: (_) => SupplierRefundsDialog(
        api: widget.api,
        credit: credit,
        canManage: widget.canManage,
      ),
    );
    if (mounted) await _load();
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return AlertDialog(
      title: Text('Credits from ${widget.vendorName}'),
      content: SizedBox(
        width: 640,
        height: 360,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (_loading) const LinearProgressIndicator(minHeight: 2),
            if (_error != null)
              Padding(
                padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                child: Text(
                  _error!,
                  style: TextStyle(color: theme.colorScheme.error),
                ),
              ),
            Expanded(
              child: _credits.isEmpty && !_loading
                  ? Center(
                      child: Text(
                        'This supplier holds no credit from returns or debit notes.',
                        style: theme.textTheme.bodyMedium,
                      ),
                    )
                  : ListView.separated(
                      itemCount: _credits.length,
                      separatorBuilder: (_, __) => const Divider(height: 1),
                      itemBuilder: (_, index) => _row(context, _credits[index]),
                    ),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Close'),
        ),
      ],
    );
  }

  Widget _row(BuildContext context, SupplierCredit credit) {
    final bool canRefund =
        widget.canManage && credit.isRefundOutcome && credit.available > 0;
    return ListTile(
      key: ValueKey<String>('supplier-credit-${credit.sourceId}'),
      title: Text(
        '${credit.label}  ·  ${credit.returnDate}  ·  '
        'Outcome: ${_outcomeLabel(credit.outcome)}',
      ),
      subtitle: Text(
        'Credit ${credit.creditAmount}  ·  Applied ${credit.appliedAmount}  ·  '
        'Refunded ${credit.refundedAmount}  ·  '
        'Available ${credit.availableAmount}',
      ),
      trailing: Row(mainAxisSize: MainAxisSize.min, children: [
        if (canRefund)
          TextButton(
            onPressed: () => unawaited(_record(credit)),
            child: const Text('Record refund'),
          ),
        TextButton(
          onPressed: () => unawaited(_refunds(credit)),
          child: const Text('Refunds'),
        ),
      ]),
    );
  }

  static String _outcomeLabel(String outcome) => switch (outcome) {
        'REFUND' => 'Refund',
        'REPLACEMENT' => 'Replacement',
        _ => 'Credit',
      };
}

/// Money the supplier handed back against one credit.
class RecordSupplierRefundDialog extends StatefulWidget {
  const RecordSupplierRefundDialog({
    super.key,
    required this.api,
    required this.credit,
  });

  final ApiClient api;
  final SupplierCredit credit;

  @override
  State<RecordSupplierRefundDialog> createState() =>
      _RecordSupplierRefundDialogState();
}

class _RecordSupplierRefundDialogState extends State<RecordSupplierRefundDialog>
    with SaveInDialog<RecordSupplierRefundDialog> {
  // Blank, not prefilled: the amount is what the supplier actually paid back,
  // which is not always everything that is available.
  final TextEditingController _amount = TextEditingController();
  final TextEditingController _reference = TextEditingController();
  final TextEditingController _remarks = TextEditingController();
  String _method = 'BANK';
  DateTime _date = DateTime.now();
  String? _problem;

  @override
  void dispose() {
    _amount.dispose();
    _reference.dispose();
    _remarks.dispose();
    super.dispose();
  }

  String get _day => _date.toIso8601String().substring(0, 10);

  Future<void> _save() async {
    final double amount = double.tryParse(_amount.text.trim()) ?? 0;
    if (amount <= 0) {
      setState(() => _problem = 'Enter how much the supplier paid back.');
      return;
    }
    setState(() => _problem = null);
    await saveAndClose<SupplierRefund>(
      () => widget.api.recordSupplierRefund(
        sourceId: widget.credit.sourceId,
        amount: _amount.text.trim(),
        refundedOn: _day,
        method: _method,
        reference: _reference.text.trim(),
        remarks: _remarks.text.trim(),
      ),
    );
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: Text('Record refund for ${widget.credit.label}'),
        content: SizedBox(
          width: 460,
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                saveErrorBanner(),
                if (_problem != null)
                  Padding(
                    padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                    child: Text(
                      _problem!,
                      style: TextStyle(
                        color: Theme.of(context).colorScheme.error,
                      ),
                    ),
                  ),
                Text(
                  'Money the supplier has paid back. It posts to the ledger '
                  'and lowers what is available on this credit.',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
                const SizedBox(height: AppSpacing.md),
                TextField(
                  key: const ValueKey('supplier-refund-amount'),
                  controller: _amount,
                  keyboardType:
                      const TextInputType.numberWithOptions(decimal: true),
                  decoration: InputDecoration(
                    labelText: 'Amount',
                    helperText: 'up to ${widget.credit.availableAmount}',
                  ),
                ),
                const SizedBox(height: AppSpacing.sm),
                Row(children: [
                  Expanded(child: _dateField(context)),
                  const SizedBox(width: AppSpacing.md),
                  SizedBox(
                    width: 140,
                    child: DropdownButtonFormField<String>(
                      key: const ValueKey('supplier-refund-method'),
                      initialValue: _method,
                      decoration: const InputDecoration(labelText: 'Method'),
                      items: const [
                        DropdownMenuItem<String>(
                          value: 'BANK',
                          child: Text('Bank'),
                        ),
                        DropdownMenuItem<String>(
                          value: 'CASH',
                          child: Text('Cash'),
                        ),
                      ],
                      onChanged: (value) =>
                          setState(() => _method = value ?? 'BANK'),
                    ),
                  ),
                ]),
                const SizedBox(height: AppSpacing.sm),
                TextField(
                  key: const ValueKey('supplier-refund-reference'),
                  controller: _reference,
                  decoration: const InputDecoration(
                    labelText: 'Cheque or transfer reference',
                  ),
                ),
                const SizedBox(height: AppSpacing.sm),
                TextField(
                  key: const ValueKey('supplier-refund-remarks'),
                  controller: _remarks,
                  decoration: const InputDecoration(labelText: 'Remarks'),
                ),
              ],
            ),
          ),
        ),
        actions: [
          TextButton(onPressed: cancelHandler, child: const Text('Cancel')),
          FilledButton(
            key: const ValueKey('supplier-refund-save'),
            onPressed: saving ? null : () => unawaited(_save()),
            child: const Text('Record refund'),
          ),
        ],
      );

  Widget _dateField(BuildContext context) => InkWell(
        onTap: saving
            ? null
            : () async {
                final DateTime? picked = await showDatePicker(
                  context: context,
                  initialDate: _date,
                  firstDate: DateTime(2000),
                  lastDate: DateTime(2100),
                );
                if (picked != null) setState(() => _date = picked);
              },
        child: InputDecorator(
          decoration: const InputDecoration(
            labelText: 'Date refunded',
            suffixIcon: Icon(Icons.calendar_today, size: 18),
          ),
          child: Text(_day),
        ),
      );
}

/// The refunds recorded against one credit, each with a Reverse while it
/// stands.
class SupplierRefundsDialog extends StatefulWidget {
  const SupplierRefundsDialog({
    super.key,
    required this.api,
    required this.credit,
    required this.canManage,
  });

  final ApiClient api;
  final SupplierCredit credit;
  final bool canManage;

  @override
  State<SupplierRefundsDialog> createState() => _SupplierRefundsDialogState();
}

class _SupplierRefundsDialogState extends State<SupplierRefundsDialog> {
  List<SupplierRefund> _refunds = const [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final List<SupplierRefund> rows =
          await widget.api.supplierRefunds(widget.credit.sourceId);
      if (!mounted) return;
      setState(() => _refunds = rows);
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() => _error = exception.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _reverse(SupplierRefund refund) async {
    final String? reason = await askForReason(
      context,
      title: 'Reverse refund of ${refund.amount}',
      explanation: 'This writes an opposite journal and puts the amount back '
          'on the credit. Nothing is deleted: the refund and its reversal '
          'both stay on the record.',
      label: 'Why is it being reversed?',
      confirmLabel: 'Reverse',
    );
    if (reason == null || !mounted) return;
    try {
      await widget.api
          .reverseSupplierRefund(refundId: refund.id, reason: reason);
      await _load();
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() => _error = exception.message);
    }
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return AlertDialog(
      title: Text('Refunds on ${widget.credit.label}'),
      content: SizedBox(
        width: 560,
        height: 300,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (_loading) const LinearProgressIndicator(minHeight: 2),
            if (_error != null)
              Padding(
                padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                child: Text(
                  _error!,
                  style: TextStyle(color: theme.colorScheme.error),
                ),
              ),
            Expanded(
              child: _refunds.isEmpty && !_loading
                  ? Center(
                      child: Text(
                        'No refund has been recorded against this credit.',
                        style: theme.textTheme.bodyMedium,
                      ),
                    )
                  : ListView.separated(
                      itemCount: _refunds.length,
                      separatorBuilder: (_, __) => const Divider(height: 1),
                      itemBuilder: (_, index) => _row(_refunds[index]),
                    ),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Close'),
        ),
      ],
    );
  }

  Widget _row(SupplierRefund refund) => ListTile(
        key: ValueKey<String>('supplier-refund-${refund.id}'),
        title: Text(
          '${refund.refundedOn}  ·  ${refund.amount}  ·  ${refund.method}'
          '${refund.reference.isEmpty ? '' : '  ·  ${refund.reference}'}',
        ),
        subtitle: refund.isReversed && refund.reversalReason.isNotEmpty
            ? Text('Reversed because ${refund.reversalReason}')
            : refund.remarks.isEmpty
                ? null
                : Text(refund.remarks),
        trailing: refund.isReversed
            ? const StatusBadge(label: 'Reversed')
            : Row(mainAxisSize: MainAxisSize.min, children: [
                const StatusBadge(label: 'Posted'),
                if (widget.canManage)
                  TextButton(
                    onPressed: () => unawaited(_reverse(refund)),
                    child: const Text('Reverse'),
                  ),
              ]),
      );
}
