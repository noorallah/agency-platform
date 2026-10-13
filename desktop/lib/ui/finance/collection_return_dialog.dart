// The end-of-day line on one bill handed to a collector (backlog 124, M6):
// collected in full, part collected, promised, or not collected. One dialog
// serves the collector's own screen and the office's day sheet; it runs the
// save itself, so a refusal stays on screen with everything typed.

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/design/design_tokens.dart';
import '../../models/bill_handover.dart';
import '../../models/entities.dart';
import '../../phase2/display_dates.dart';
import '../../phase2/indian_format.dart';
import '../workspace/save_in_dialog.dart';

String _iso(DateTime date) => date.toIso8601String().substring(0, 10);

const Map<String, String> _modes = {
  'CASH': 'Cash',
  'CHEQUE': 'Cheque',
  'UPI': 'UPI',
  'BANK_TRANSFER': 'Bank transfer',
  'CARD': 'Card',
  'DEMAND_DRAFT': 'Demand draft',
  'OTHER': 'Other',
};

/// A payment mode in words; blank stays blank.
String collectionModeWords(String? mode) =>
    mode == null ? '' : (_modes[mode] ?? mode);

/// Opens the dialog. [onSave] receives the body to send and makes the call;
/// a refusal it throws as an `ApiException` is shown inside the dialog.
/// Returns true when the line was saved.
Future<bool> showCollectionReturnDialog(
  BuildContext context, {
  required String billNumber,
  required String customerName,
  required double owes,
  required String handoverId,
  required bool office,
  required bool collectorRecordsReceipt,
  required Future<void> Function(Json body) onSave,
}) async {
  final bool? saved = await showDialog<bool>(
    context: context,
    builder: (context) => SelectionArea(
      child: CollectionReturnDialog(
        billNumber: billNumber,
        customerName: customerName,
        owes: owes,
        handoverId: handoverId,
        office: office,
        collectorRecordsReceipt: collectorRecordsReceipt,
        onSave: onSave,
      ),
    ),
  );
  return saved == true;
}

class CollectionReturnDialog extends StatefulWidget {
  const CollectionReturnDialog({
    super.key,
    required this.billNumber,
    required this.customerName,
    required this.owes,
    required this.handoverId,
    required this.office,
    required this.collectorRecordsReceipt,
    required this.onSave,
  });

  final String billNumber;
  final String customerName;
  final double owes;
  final String handoverId;
  final bool office;
  final bool collectorRecordsReceipt;
  final Future<void> Function(Json body) onSave;

  @override
  State<CollectionReturnDialog> createState() => _CollectionReturnDialogState();
}

class _CollectionReturnDialogState extends State<CollectionReturnDialog>
    with SaveInDialog<CollectionReturnDialog> {
  final TextEditingController _amount = TextEditingController();
  final TextEditingController _reference = TextEditingController();
  final TextEditingController _note = TextEditingController();
  String _outcome = 'COLLECTED';
  String _mode = 'CASH';
  DateTime _day = DateTime.now();
  DateTime? _promisedOn;
  String? _problem;

  bool get _takesMoney => _outcome == 'COLLECTED' || _outcome == 'PART';
  bool get _recordsReceipt => widget.office || widget.collectorRecordsReceipt;

  @override
  void dispose() {
    _amount.dispose();
    _reference.dispose();
    _note.dispose();
    super.dispose();
  }

  String get _owesText => indianAmount(widget.owes, full: true);

  String get _helper => _recordsReceipt
      ? 'Save records the receipt.'
      : 'Save notes what you collected. The office records the receipt.';

  String _dayText(DateTime day) => DisplayDates.write(day);

  Future<void> _pickDay() async {
    final DateTime? picked = await showDatePicker(
      context: context,
      initialDate: _day,
      firstDate: DateTime(2000),
      lastDate: DateTime.now(),
    );
    if (picked != null) setState(() => _day = picked);
  }

  Future<void> _pickPromised() async {
    final DateTime now = DateTime.now();
    final DateTime? picked = await showDatePicker(
      context: context,
      initialDate: _promisedOn ?? now,
      firstDate: DateTime(now.year, now.month, now.day),
      lastDate: DateTime(2100),
    );
    if (picked != null) setState(() => _promisedOn = picked);
  }

  /// What is wrong, or null.
  String? _validate() {
    if (_outcome == 'PART') {
      final double? amount = double.tryParse(_amount.text.trim());
      if (amount == null || amount <= 0) {
        return 'Enter the amount collected, more than 0.';
      }
      if (amount >= widget.owes) {
        return 'A part payment must be less than the $_owesText the bill '
            'owes. Choose Collected in full instead.';
      }
    }
    if (_outcome == 'PROMISED' && _promisedOn == null) {
      return 'Choose the day the customer promised to pay.';
    }
    return null;
  }

  /// Only keys the server declares; a key that does not apply is left out.
  Json _body() {
    final String reference = _reference.text.trim();
    final String note = _note.text.trim();
    final DateTime today = DateTime.now();
    final bool pastDay = widget.office &&
        _iso(_day) != _iso(DateTime(today.year, today.month, today.day));
    return <String, dynamic>{
      'handover_id': widget.handoverId,
      'outcome': _outcome,
      if (pastDay) 'return_date': _iso(_day),
      if (_outcome == 'PART') 'amount_collected': _amount.text.trim(),
      if (_takesMoney) 'payment_mode': _mode,
      if (_takesMoney && reference.isNotEmpty) 'instrument_reference': reference,
      if ((_outcome == 'PROMISED' || _outcome == 'PART') &&
          _promisedOn != null)
        'promised_on': _iso(_promisedOn!),
      if (note.isNotEmpty) 'note': note,
    };
  }

  Future<void> _save() async {
    final String? problem = _validate();
    if (problem != null) {
      setState(() => _problem = problem);
      return;
    }
    setState(() => _problem = null);
    final Json body = _body();
    await saveAndClose<bool>(() async {
      await widget.onSave(body);
      return true;
    });
  }

  Widget _dayBox(Key key, String label, DateTime? value, VoidCallback? onTap) =>
      InkWell(
        key: key,
        onTap: onTap,
        child: InputDecorator(
          decoration: InputDecoration(
            labelText: label,
            isDense: true,
            suffixIcon: const Icon(Icons.event_outlined, size: 16),
          ),
          child: Text(value == null ? '' : _dayText(value)),
        ),
      );

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final String? error = saveError ?? _problem;
    return AlertDialog(
      title: Text('Day’s line: ${widget.billNumber}'),
      content: SizedBox(
        width: 420,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                '${widget.customerName}. The bill owes $_owesText.',
                style: theme.textTheme.bodySmall,
              ),
              const SizedBox(height: AppSpacing.md),
              if (widget.office) ...[
                _dayBox(const ValueKey('return-day'), 'Day', _day,
                    saving ? null : () => _pickDay()),
                const SizedBox(height: AppSpacing.sm),
              ],
              DropdownButtonFormField<String>(
                key: const ValueKey('return-outcome'),
                isExpanded: true,
                initialValue: _outcome,
                decoration: const InputDecoration(
                    labelText: 'What happened', isDense: true),
                items: [
                  for (final String outcome in returnOutcomes)
                    DropdownMenuItem(
                      value: outcome,
                      child: Text(outcome == 'COLLECTED'
                          ? 'Collected in full'
                          : returnOutcomeWords(outcome)),
                    ),
                ],
                onChanged: saving
                    ? null
                    : (value) => setState(() {
                          _outcome = value ?? _outcome;
                          _problem = null;
                        }),
              ),
              const SizedBox(height: AppSpacing.xs),
              Text(_helper,
                  key: const ValueKey('return-helper'),
                  style: theme.textTheme.bodySmall),
              if (_takesMoney) ...[
                const SizedBox(height: AppSpacing.sm),
                if (_outcome == 'COLLECTED')
                  InputDecorator(
                    key: const ValueKey('return-amount'),
                    decoration: const InputDecoration(
                        labelText: 'Amount collected', isDense: true),
                    child: Text(_owesText),
                  )
                else
                  TextField(
                    key: const ValueKey('return-amount'),
                    controller: _amount,
                    enabled: !saving,
                    keyboardType:
                        const TextInputType.numberWithOptions(decimal: true),
                    inputFormatters: [
                      FilteringTextInputFormatter.allow(RegExp(r'[0-9.]')),
                    ],
                    decoration: const InputDecoration(
                        labelText: 'Amount collected', isDense: true),
                  ),
                const SizedBox(height: AppSpacing.sm),
                DropdownButtonFormField<String>(
                  key: const ValueKey('return-mode'),
                  isExpanded: true,
                  initialValue: _mode,
                  decoration: const InputDecoration(
                      labelText: 'How paid', isDense: true),
                  items: [
                    for (final MapEntry<String, String> mode in _modes.entries)
                      DropdownMenuItem(value: mode.key, child: Text(mode.value)),
                  ],
                  onChanged: saving
                      ? null
                      : (value) => setState(() => _mode = value ?? _mode),
                ),
                const SizedBox(height: AppSpacing.sm),
                TextField(
                  key: const ValueKey('return-reference'),
                  controller: _reference,
                  enabled: !saving,
                  maxLength: 120,
                  decoration: const InputDecoration(
                    labelText: 'Cheque or transfer number',
                    isDense: true,
                    counterText: '',
                  ),
                ),
              ],
              if (_outcome == 'PROMISED' || _outcome == 'PART') ...[
                const SizedBox(height: AppSpacing.sm),
                _dayBox(
                  const ValueKey('return-promised-on'),
                  _outcome == 'PROMISED'
                      ? 'Promised to pay on'
                      : 'Promise for the rest on (optional)',
                  _promisedOn,
                  saving ? null : () => _pickPromised(),
                ),
              ],
              const SizedBox(height: AppSpacing.sm),
              TextField(
                key: const ValueKey('return-note'),
                controller: _note,
                enabled: !saving,
                maxLength: 2000,
                decoration: const InputDecoration(
                    labelText: 'Note', isDense: true, counterText: ''),
              ),
              if (error != null) ...[
                const SizedBox(height: AppSpacing.sm),
                Text(
                  error,
                  key: const ValueKey('return-error'),
                  style: theme.textTheme.bodySmall
                      ?.copyWith(color: theme.colorScheme.error),
                ),
              ],
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: cancelHandler,
          child: const Text('Cancel'),
        ),
        FilledButton(
          key: const ValueKey('return-save'),
          onPressed: saving ? null : () => _save(),
          child: Text(saving ? 'Saving…' : 'Save'),
        ),
      ],
    );
  }
}
