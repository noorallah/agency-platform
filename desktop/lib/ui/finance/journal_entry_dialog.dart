import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../models/entities.dart';
import '../../models/finance.dart';
import '../workspace/desktop_framework.dart';

/// One line being written, before it is anything the server has seen.
class JournalDraftLine {
  JournalDraftLine({
    this.ledgerAccountId = '',
    this.debit = '',
    this.credit = '',
    this.description = '',
  });

  String ledgerAccountId;
  String debit;
  String credit;
  String description;

  double get debitValue => double.tryParse(debit.trim()) ?? 0;
  double get creditValue => double.tryParse(credit.trim()) ?? 0;

  /// A line nobody has filled in. Blank rows are dropped rather than sent,
  /// because an empty row is somebody's cursor, not an instruction.
  bool get isBlank =>
      ledgerAccountId.isEmpty && debitValue == 0 && creditValue == 0;

  /// A line cannot be an amount on both sides. The server refuses it too; this
  /// is so the person writing it is told while they are looking at it.
  bool get isTwoSided => debitValue > 0 && creditValue > 0;

  /// No line number: the engine assigns those, and `JournalLineInput` refuses
  /// one outright. Sending it was caught by posting a real entry rather than
  /// by reading the schema.
  Json toJson() => {
        'ledger_account_id': ledgerAccountId,
        'debit_amount': debitValue.toStringAsFixed(2),
        'credit_amount': creditValue.toStringAsFixed(2),
        if (description.trim().isNotEmpty) 'description': description.trim(),
      };
}

/// What is wrong with a set of lines, or null when nothing is.
///
/// Separated from the widget so the rule can be tested without a form: whether
/// an entry may be written is the one thing here worth being sure of.
String? validateJournalLines(List<JournalDraftLine> lines) {
  final List<JournalDraftLine> filled =
      lines.where((line) => !line.isBlank).toList();
  if (filled.length < 2) {
    return 'A journal entry needs at least two lines: something given and '
        'something taken.';
  }
  for (int index = 0; index < filled.length; index++) {
    final JournalDraftLine line = filled[index];
    if (line.ledgerAccountId.isEmpty) {
      return 'Line ${index + 1}: choose the account this amount belongs to.';
    }
    if (line.isTwoSided) {
      return 'Line ${index + 1}: an amount is either a debit or a credit, '
          'not both.';
    }
    if (line.debitValue == 0 && line.creditValue == 0) {
      return 'Line ${index + 1}: enter a debit or a credit.';
    }
  }
  final double debit = filled.fold(0, (sum, line) => sum + line.debitValue);
  final double credit = filled.fold(0, (sum, line) => sum + line.creditValue);
  // Compared to the paisa, because that is what the amounts are written in and
  // floating point will not make two typed decimals equal on its own.
  if ((debit - credit).abs() >= 0.005) {
    return 'Debits and credits must match. They differ by '
        '${(debit - credit).abs().toStringAsFixed(2)}.';
  }
  return null;
}

/// Write a journal entry by hand.
///
/// Most entries in this ledger are posted by documents. This is for the ones
/// that are not -- an opening balance, a correction, a depreciation charge --
/// and the rule that makes it a journal entry rather than a note is that it
/// balances. The running total is on screen while it is being written, because
/// finding out on save is finding out too late.
class JournalEntryDialog extends StatefulWidget {
  const JournalEntryDialog({
    super.key,
    required this.api,
    required this.accounts,
    required this.periods,
    required this.journalTypes,
    required this.voucherTypes,
  });

  final ApiClient api;
  final List<LedgerAccount> accounts;
  final List<AccountingPeriod> periods;
  final List<FinanceTypeRef> journalTypes;
  final List<FinanceTypeRef> voucherTypes;

  @override
  State<JournalEntryDialog> createState() => _JournalEntryDialogState();
}

class _JournalEntryDialogState extends State<JournalEntryDialog> {
  late String _periodId = widget.periods.isEmpty ? '' : widget.periods.first.id;
  late String _journalTypeId =
      widget.journalTypes.isEmpty ? '' : widget.journalTypes.first.id;
  late String _voucherTypeId =
      widget.voucherTypes.isEmpty ? '' : widget.voucherTypes.first.id;
  String _journalDate = DateTime.now().toIso8601String().split('T').first;
  String _reference = '';
  String _description = '';
  final List<JournalDraftLine> _lines = [
    JournalDraftLine(),
    JournalDraftLine(),
  ];
  bool _saving = false;
  String? _error;

  double get _debitTotal =>
      _lines.fold(0, (sum, line) => sum + line.debitValue);
  double get _creditTotal =>
      _lines.fold(0, (sum, line) => sum + line.creditValue);
  double get _difference => _debitTotal - _creditTotal;

  String _accountLabel(String id) {
    for (final LedgerAccount account in widget.accounts) {
      if (account.id == id) return '${account.code} — ${account.name}';
    }
    return id;
  }

  Future<void> _save() async {
    final String? problem = _reference.trim().isEmpty
        ? 'A reference number identifies this entry in the ledger.'
        : validateJournalLines(_lines);
    if (problem != null) {
      setState(() => _error = problem);
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final List<JournalDraftLine> sending =
          _lines.where((line) => !line.isBlank).toList();
      final JournalEntry created = await widget.api.createJournalEntry({
        'journal_type_id': _journalTypeId,
        'voucher_type_id': _voucherTypeId,
        'accounting_period_id': _periodId,
        'journal_date': _journalDate,
        'reference_number': _reference.trim(),
        if (_description.trim().isNotEmpty) 'description': _description.trim(),
        'lines': [for (final JournalDraftLine line in sending) line.toJson()],
      });
      if (!mounted) return;
      Navigator.pop(context, created);
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() {
        _error = exception.message;
        _saving = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) => WorkspaceDialog(
        title: 'New Journal Entry',
        subtitle: 'Saved as a draft. Posting it is a separate step.',
        icon: Icons.menu_book_outlined,
        loading: _saving,
        onClose: _saving ? null : () => Navigator.pop(context),
        onSave: _saving ? null : _save,
        footer: Padding(
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: Row(children: [
            _balanceSummary(context),
            const Spacer(),
            TextButton(
              onPressed: _saving ? null : () => Navigator.pop(context),
              child: const Text('Cancel'),
            ),
            const SizedBox(width: AppSpacing.md),
            FilledButton.icon(
              onPressed: _saving ? null : _save,
              icon: const Icon(Icons.save_outlined),
              label: const Text('Save Draft'),
            ),
          ]),
        ),
        body: SingleChildScrollView(
          padding: const EdgeInsets.all(AppSpacing.xl),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (_error != null) ...[
                MaterialBanner(
                  content: Text(_error!),
                  actions: [
                    TextButton(
                      onPressed: () => setState(() => _error = null),
                      child: const Text('Dismiss'),
                    ),
                  ],
                ),
                const SizedBox(height: AppSpacing.lg),
              ],
              const SectionHeader(
                title: 'Entry',
                description: 'When it belongs, and what it is for.',
              ),
              const SizedBox(height: AppSpacing.md),
              _header(),
              const SizedBox(height: AppSpacing.xl),
              const SectionHeader(
                title: 'Lines',
                description:
                    'Every amount is a debit or a credit, and the two sides '
                    'must match before this can be saved.',
              ),
              const SizedBox(height: AppSpacing.md),
              ..._lineRows(),
              const SizedBox(height: AppSpacing.md),
              Align(
                alignment: Alignment.centerLeft,
                child: TextButton.icon(
                  onPressed: () => setState(() => _lines.add(JournalDraftLine())),
                  icon: const Icon(Icons.add),
                  label: const Text('Add line'),
                ),
              ),
            ],
          ),
        ),
      );

  /// The running total, on screen while the entry is being written.
  Widget _balanceSummary(BuildContext context) {
    final bool balanced = _difference.abs() < 0.005 && _debitTotal > 0;
    return Row(children: [
      Icon(
        balanced ? Icons.check_circle_outline : Icons.balance_outlined,
        size: 18,
        color: balanced
            ? Theme.of(context).colorScheme.primary
            : Theme.of(context).colorScheme.onSurfaceVariant,
      ),
      const SizedBox(width: AppSpacing.sm),
      Text(
        balanced
            ? 'Balanced at ${_debitTotal.toStringAsFixed(2)}'
            : 'Debit ${_debitTotal.toStringAsFixed(2)} · '
                'Credit ${_creditTotal.toStringAsFixed(2)} · '
                'difference ${_difference.abs().toStringAsFixed(2)}',
        style: Theme.of(context).textTheme.bodyMedium,
      ),
    ]);
  }

  Widget _header() => Wrap(
        spacing: AppSpacing.lg,
        runSpacing: AppSpacing.lg,
        children: [
          SizedBox(
            width: 300,
            child: DropdownButtonFormField<String>(
              initialValue: _periodId.isEmpty ? null : _periodId,
              isExpanded: true,
              decoration: const InputDecoration(labelText: 'Accounting period *'),
              items: [
                for (final AccountingPeriod period in widget.periods)
                  DropdownMenuItem<String>(
                    value: period.id,
                    child: Text(period.name, overflow: TextOverflow.ellipsis),
                  ),
              ],
              onChanged: (value) => setState(() => _periodId = value ?? ''),
            ),
          ),
          SizedBox(
            width: 220,
            child: DropdownButtonFormField<String>(
              initialValue: _journalTypeId.isEmpty ? null : _journalTypeId,
              isExpanded: true,
              decoration: const InputDecoration(labelText: 'Journal type *'),
              items: [
                for (final FinanceTypeRef type in widget.journalTypes)
                  DropdownMenuItem<String>(
                    value: type.id,
                    child: Text(type.label, overflow: TextOverflow.ellipsis),
                  ),
              ],
              onChanged: (value) => setState(() => _journalTypeId = value ?? ''),
            ),
          ),
          SizedBox(
            width: 220,
            child: DropdownButtonFormField<String>(
              initialValue: _voucherTypeId.isEmpty ? null : _voucherTypeId,
              isExpanded: true,
              decoration: const InputDecoration(labelText: 'Voucher type *'),
              items: [
                for (final FinanceTypeRef type in widget.voucherTypes)
                  DropdownMenuItem<String>(
                    value: type.id,
                    child: Text(type.label, overflow: TextOverflow.ellipsis),
                  ),
              ],
              onChanged: (value) => setState(() => _voucherTypeId = value ?? ''),
            ),
          ),
          SizedBox(
            width: 180,
            child: TextFormField(
              initialValue: _journalDate,
              decoration: const InputDecoration(
                labelText: 'Date *',
                hintText: 'YYYY-MM-DD',
              ),
              onChanged: (value) => setState(() => _journalDate = value),
            ),
          ),
          SizedBox(
            width: 220,
            child: TextFormField(
              initialValue: _reference,
              decoration: const InputDecoration(labelText: 'Reference *'),
              onChanged: (value) => setState(() => _reference = value),
            ),
          ),
          SizedBox(
            width: 320,
            child: TextFormField(
              initialValue: _description,
              decoration: const InputDecoration(labelText: 'Description'),
              onChanged: (value) => setState(() => _description = value),
            ),
          ),
        ],
      );

  List<Widget> _lineRows() => [
        for (int index = 0; index < _lines.length; index++)
          Padding(
            padding: const EdgeInsets.only(bottom: AppSpacing.md),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  flex: 3,
                  child: DropdownButtonFormField<String>(
                    initialValue: _lines[index].ledgerAccountId.isEmpty
                        ? null
                        : _lines[index].ledgerAccountId,
                    isExpanded: true,
                    decoration: InputDecoration(labelText: 'Account ${index + 1}'),
                    items: [
                      for (final LedgerAccount account in widget.accounts)
                        DropdownMenuItem<String>(
                          value: account.id,
                          child: Text(
                            _accountLabel(account.id),
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                    ],
                    onChanged: (value) => setState(
                        () => _lines[index].ledgerAccountId = value ?? ''),
                  ),
                ),
                const SizedBox(width: AppSpacing.md),
                SizedBox(
                  width: 130,
                  child: TextFormField(
                    initialValue: _lines[index].debit,
                    decoration: const InputDecoration(labelText: 'Debit'),
                    keyboardType: TextInputType.number,
                    onChanged: (value) => setState(() => _lines[index].debit = value),
                  ),
                ),
                const SizedBox(width: AppSpacing.md),
                SizedBox(
                  width: 130,
                  child: TextFormField(
                    initialValue: _lines[index].credit,
                    decoration: const InputDecoration(labelText: 'Credit'),
                    keyboardType: TextInputType.number,
                    onChanged: (value) =>
                        setState(() => _lines[index].credit = value),
                  ),
                ),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                  flex: 2,
                  child: TextFormField(
                    initialValue: _lines[index].description,
                    decoration: const InputDecoration(labelText: 'Narration'),
                    onChanged: (value) =>
                        setState(() => _lines[index].description = value),
                  ),
                ),
                IconButton(
                  tooltip: 'Remove line',
                  // Two lines is the floor: an entry with one line cannot
                  // balance, so removing to one would only produce something
                  // that can never be saved.
                  onPressed: _lines.length <= 2
                      ? null
                      : () => setState(() => _lines.removeAt(index)),
                  icon: const Icon(Icons.delete_outline),
                ),
              ],
            ),
          ),
      ];
}
