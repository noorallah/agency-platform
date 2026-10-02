import 'package:flutter/material.dart';

import '../../core/design/design_tokens.dart';
import '../workspace/save_in_dialog.dart';

/// Why [number] is not an e-way bill number, or null when it is one or is
/// blank.
///
/// An e-way bill number is 12 digits; spaces and hyphens as the portal prints
/// them are allowed and the server strips them (backlog 78 row 6).
String? ewayBillProblem(String number) {
  final String text = number.trim();
  if (text.isEmpty) return null;
  if (!RegExp(r'^\d{12}$').hasMatch(text.replaceAll(RegExp(r'[\s-]'), ''))) {
    return 'An e-way bill number is 12 digits.';
  }
  return null;
}

/// Ask for the e-way bill the supplier raised and record it on the receipt
/// through [save]. Returns the server's reply once it is saved, or null when
/// dismissed. The dialog saves itself and stays open with the server's
/// message on a refusal (D-DLG-1).
Future<Object?> askForEwayBill(
  BuildContext context, {
  required String receiptNumber,
  required String currentNumber,
  required String currentDate,
  required Future<Object> Function(String? number, String? date) save,
}) =>
    showDialog<Object>(
      context: context,
      builder: (_) => EwayBillDialog(
        receiptNumber: receiptNumber,
        currentNumber: currentNumber,
        currentDate: currentDate,
        save: save,
      ),
    );

class EwayBillDialog extends StatefulWidget {
  const EwayBillDialog({
    super.key,
    required this.receiptNumber,
    required this.currentNumber,
    required this.currentDate,
    required this.save,
  });

  final String receiptNumber;
  final String currentNumber;
  final String currentDate;

  /// Records the number and date; a blank number is sent as null, which
  /// clears it.
  final Future<Object> Function(String? number, String? date) save;

  @override
  State<EwayBillDialog> createState() => _EwayBillDialogState();
}

class _EwayBillDialogState extends State<EwayBillDialog>
    with SaveInDialog<EwayBillDialog> {
  late final TextEditingController _number =
      TextEditingController(text: widget.currentNumber);
  late final TextEditingController _date =
      TextEditingController(text: widget.currentDate);
  String? _problem;
  String? _dateProblem;

  @override
  void dispose() {
    _number.dispose();
    _date.dispose();
    super.dispose();
  }

  Future<void> _confirm() async {
    final String? problem = ewayBillProblem(_number.text);
    final String date = _date.text.trim();
    final String? dateProblem =
        date.isNotEmpty && !RegExp(r'^\d{4}-\d{2}-\d{2}$').hasMatch(date)
            ? 'Write the date as YYYY-MM-DD.'
            : null;
    if (problem != null || dateProblem != null) {
      setState(() {
        _problem = problem;
        _dateProblem = dateProblem;
      });
      return;
    }
    setState(() {
      _problem = null;
      _dateProblem = null;
    });
    final String number = _number.text.trim();
    await saveAndClose<Object>(() => widget.save(
          number.isEmpty ? null : number,
          number.isEmpty || date.isEmpty ? null : date,
        ));
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: Text('E-way bill on ${widget.receiptNumber}'),
        content: SizedBox(
          width: 520,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              saveErrorBanner(),
              Text(
                "The number is on the supplier's e-way bill, 12 digits. "
                'Leave it empty to clear it.',
                style: Theme.of(context).textTheme.bodySmall,
              ),
              const SizedBox(height: AppSpacing.md),
              TextField(
                key: const ValueKey('eway-bill-number-input'),
                controller: _number,
                autofocus: true,
                enabled: !saving,
                decoration: InputDecoration(
                  labelText: 'E-way bill number',
                  errorText: _problem,
                ),
                onSubmitted: (_) => _confirm(),
              ),
              const SizedBox(height: AppSpacing.md),
              TextField(
                key: const ValueKey('eway-bill-date-input'),
                controller: _date,
                enabled: !saving,
                decoration: InputDecoration(
                  labelText: 'E-way bill date (optional)',
                  hintText: 'YYYY-MM-DD',
                  errorText: _dateProblem,
                ),
                onSubmitted: (_) => _confirm(),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: saving ? null : () => Navigator.of(context).pop(),
            child: const Text('Cancel'),
          ),
          FilledButton(
            key: const ValueKey('eway-bill-save'),
            onPressed: saving ? null : _confirm,
            child: const Text('Record e-way bill'),
          ),
        ],
      );
}
