import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../models/expense.dart';
import '../../models/tds.dart';
import '../workspace/desktop_framework.dart';

/// Record one expense: what it was for, how much, and where it came from.
///
/// Saving posts the journal -- Dr the expense account, Cr the cash or bank
/// account -- so what the server refuses (no open period, an account that
/// needs a cost centre) is shown here in its own words and nothing is saved.
/// The dialog owns its controllers, so none is disposed while it animates out.
class RecordExpenseDialog extends StatefulWidget {
  const RecordExpenseDialog({super.key, required this.api, this.today});

  final ApiClient api;

  /// For tests; the clock otherwise.
  final DateTime? today;

  @override
  State<RecordExpenseDialog> createState() => _RecordExpenseDialogState();
}

class _RecordExpenseDialogState extends State<RecordExpenseDialog> {
  final TextEditingController _amount = TextEditingController();
  final TextEditingController _payee = TextEditingController();
  final TextEditingController _reference = TextEditingController();
  final TextEditingController _narration = TextEditingController();

  /// Tax deducted at source out of the amount (backlog 53.1): rent, fees and
  /// transport commonly carry it. The expense is the whole amount; the money
  /// paid out is the rest, and the deduction is owed to the government.
  final TextEditingController _tds = TextEditingController();
  final TextEditingController _payeePan = TextEditingController();
  String? _tdsSection;
  late DateTime _date = widget.today ?? DateTime.now();
  ExpenseAccountChoices? _choices;
  String? _expenseAccountId;
  String? _paidFromAccountId;
  bool _busy = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    unawaited(_loadAccounts());
  }

  @override
  void dispose() {
    _amount.dispose();
    _payee.dispose();
    _reference.dispose();
    _narration.dispose();
    _tds.dispose();
    _payeePan.dispose();
    super.dispose();
  }

  Future<void> _loadAccounts() async {
    try {
      final ExpenseAccountChoices choices =
          await widget.api.expenseAccountChoices();
      if (!mounted) return;
      setState(() {
        _choices = choices;
        // One money account is the usual case for a small firm; choosing it
        // for them saves a click and cannot be wrong.
        if (choices.paidFromAccounts.length == 1) {
          _paidFromAccountId = choices.paidFromAccounts.single.id;
        }
      });
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() => _error = exception.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  String? _problem() {
    if (_expenseAccountId == null) return 'Choose what the money was spent on.';
    if (_paidFromAccountId == null) return 'Choose where the money came from.';
    final double? amount = double.tryParse(_amount.text.trim());
    if (amount == null || amount <= 0) {
      return 'Enter an amount greater than zero.';
    }
    final String? tds = tdsProblem(
      amount: _amount.text,
      tdsAmount: _tds.text,
      section: _tdsSection,
    );
    if (tds != null) return tds;
    if (_deducted > 0 && _payee.text.trim().isEmpty) {
      return 'Name the payee: the TDS return lists every deduction by '
          'deductee.';
    }
    return null;
  }

  double get _deducted => double.tryParse(_tds.text.trim()) ?? 0;

  Future<void> _save() async {
    final String? problem = _problem();
    if (problem != null) {
      setState(() => _error = problem);
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    String text(TextEditingController controller) => controller.text.trim();
    try {
      final Expense saved = await widget.api.recordExpense(<String, dynamic>{
        'expense_date': DatePeriod.iso(_date),
        'expense_account_id': _expenseAccountId,
        'paid_from_account_id': _paidFromAccountId,
        'amount': text(_amount),
        if (text(_payee).isNotEmpty) 'payee': text(_payee),
        if (text(_reference).isNotEmpty) 'reference': text(_reference),
        if (text(_narration).isNotEmpty) 'narration': text(_narration),
        if (_deducted > 0) ...{
          'tds_amount': text(_tds),
          'tds_section': _tdsSection,
          if (text(_payeePan).isNotEmpty) 'payee_pan': text(_payeePan),
        },
      });
      if (!mounted) return;
      Navigator.of(context).pop(saved);
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() => _error = exception.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final ExpenseAccountChoices? choices = _choices;
    return AlertDialog(
      title: const Text('Record an expense'),
      // Bounded, because an AlertDialog gives its content unbounded height.
      content: SizedBox(
        width: 520,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                'Money already spent. Saving posts it to the ledger.',
                style: Theme.of(context).textTheme.bodySmall,
              ),
              const SizedBox(height: AppSpacing.md),
              if (_error != null)
                Padding(
                  padding: const EdgeInsets.only(bottom: AppSpacing.md),
                  child: Text(
                    _error!,
                    style: TextStyle(
                      color: Theme.of(context).colorScheme.error,
                    ),
                  ),
                ),
              if (_busy && choices == null)
                const LinearProgressIndicator()
              else if (choices != null) ...[
                if (choices.expenseAccounts.isEmpty)
                  Padding(
                    padding: const EdgeInsets.only(bottom: AppSpacing.md),
                    child: Text(
                      'The firm has no expense account to record against. '
                      'Add one under Accounts > Chart of Accounts, type '
                      'EXPENSE.',
                      style: Theme.of(context).textTheme.bodyMedium,
                    ),
                  ),
                Row(children: [
                  SizedBox(width: 170, child: _dateField(context)),
                  const SizedBox(width: AppSpacing.md),
                  Expanded(
                    child: TextField(
                      key: const ValueKey('expense-amount'),
                      controller: _amount,
                      keyboardType: const TextInputType.numberWithOptions(
                        decimal: true,
                      ),
                      decoration: const InputDecoration(labelText: 'Amount'),
                    ),
                  ),
                ]),
                const SizedBox(height: AppSpacing.md),
                _accountPicker(
                  key: const ValueKey('expense-account'),
                  label: 'Expense',
                  options: choices.expenseAccounts,
                  value: _expenseAccountId,
                  onChanged: (id) => setState(() => _expenseAccountId = id),
                ),
                const SizedBox(height: AppSpacing.md),
                _accountPicker(
                  key: const ValueKey('expense-paid-from'),
                  label: 'Paid from',
                  options: choices.paidFromAccounts,
                  value: _paidFromAccountId,
                  onChanged: (id) => setState(() => _paidFromAccountId = id),
                ),
                const SizedBox(height: AppSpacing.md),
                Row(children: [
                  Expanded(
                    child: TextField(
                      key: const ValueKey('expense-payee'),
                      controller: _payee,
                      decoration: const InputDecoration(labelText: 'Payee'),
                    ),
                  ),
                  const SizedBox(width: AppSpacing.md),
                  Expanded(
                    child: TextField(
                      key: const ValueKey('expense-reference'),
                      controller: _reference,
                      decoration: const InputDecoration(
                        labelText: 'Bill or receipt number',
                      ),
                    ),
                  ),
                ]),
                const SizedBox(height: AppSpacing.md),
                Row(children: [
                  SizedBox(
                    width: 130,
                    child: TextField(
                      key: const ValueKey('expense-tds-amount'),
                      controller: _tds,
                      keyboardType: const TextInputType.numberWithOptions(
                        decimal: true,
                      ),
                      onChanged: (_) => setState(() {}),
                      decoration:
                          const InputDecoration(labelText: 'TDS deducted'),
                    ),
                  ),
                  const SizedBox(width: AppSpacing.md),
                  Expanded(
                    child: DropdownButtonFormField<String>(
                      key: const ValueKey('expense-tds-section'),
                      initialValue: _tdsSection,
                      isExpanded: true,
                      decoration:
                          const InputDecoration(labelText: 'TDS section'),
                      items: [
                        for (final MapEntry<String, String> entry
                            in tdsSections.entries)
                          DropdownMenuItem(
                            value: entry.key,
                            child: Text(
                              '${entry.key} - ${entry.value}',
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                      ],
                      onChanged: (value) =>
                          setState(() => _tdsSection = value),
                    ),
                  ),
                  const SizedBox(width: AppSpacing.md),
                  SizedBox(
                    width: 130,
                    child: TextField(
                      key: const ValueKey('expense-payee-pan'),
                      controller: _payeePan,
                      textCapitalization: TextCapitalization.characters,
                      decoration:
                          const InputDecoration(labelText: "Payee's PAN"),
                    ),
                  ),
                ]),
                if (_deducted > 0)
                  Padding(
                    padding: const EdgeInsets.only(top: AppSpacing.xs),
                    child: Text(
                      'Paid out: '
                      '${((double.tryParse(_amount.text.trim()) ?? 0) - _deducted).toStringAsFixed(2)}. '
                      'The expense is the whole amount; the deduction is '
                      'owed to the government.',
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ),
                const SizedBox(height: AppSpacing.md),
                TextField(
                  key: const ValueKey('expense-narration'),
                  controller: _narration,
                  decoration: const InputDecoration(labelText: 'Narration'),
                ),
              ],
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: _busy ? null : () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: _busy || choices == null ? null : () => unawaited(_save()),
          child: const Text('Save'),
        ),
      ],
    );
  }

  Widget _accountPicker({
    required Key key,
    required String label,
    required List<ExpenseAccountOption> options,
    required String? value,
    required ValueChanged<String?> onChanged,
  }) =>
      DropdownButtonFormField<String>(
        key: key,
        initialValue: value,
        isExpanded: true,
        decoration: InputDecoration(labelText: label),
        items: [
          for (final ExpenseAccountOption option in options)
            DropdownMenuItem<String>(
              value: option.id,
              child: Text(option.label, overflow: TextOverflow.ellipsis),
            ),
        ],
        onChanged: _busy ? null : onChanged,
      );

  Widget _dateField(BuildContext context) => InkWell(
        onTap: () async {
          final DateTime? picked = await showDatePicker(
            context: context,
            initialDate: _date,
            firstDate: DateTime(2000),
            lastDate: DateTime(2100),
          );
          if (picked == null) return;
          setState(() => _date = picked);
        },
        child: InputDecorator(
          decoration: const InputDecoration(
            labelText: 'Date',
            suffixIcon: Icon(Icons.calendar_today, size: 18),
          ),
          child: Text(DatePeriod.iso(_date)),
        ),
      );
}
