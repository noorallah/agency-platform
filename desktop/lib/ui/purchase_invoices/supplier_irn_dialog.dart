import 'package:flutter/material.dart';

import '../../core/design/design_tokens.dart';
import '../../models/entities.dart';
import '../workspace/save_in_dialog.dart';

/// Why [irn] is not an IRN, or null when it is one or is blank.
///
/// An IRN is a 64-character SHA-256 hash, printed under the QR code of an
/// e-invoice. The server refuses anything else, so this says so before the
/// request (backlog 78 row 5).
String? supplierIrnProblem(String irn) {
  final String text = irn.trim();
  if (text.isEmpty) return null;
  if (!RegExp(r'^[0-9a-fA-F]{64}$').hasMatch(text)) {
    return 'An IRN is 64 characters, 0-9 and a-f. Copy it from under the '
        "bill's QR code.";
  }
  return null;
}

/// Ask for the IRN printed on a supplier's bill and record it on the bill
/// through [save]. Returns the server's reply once it is saved, or null when
/// dismissed. The dialog saves itself and stays open with the server's
/// message on a refusal (D-DLG-1).
Future<Json?> askForSupplierIrn(
  BuildContext context, {
  required String billNumber,
  required String current,
  required Future<Json> Function(String? irn) save,
}) =>
    showDialog<Json>(
      context: context,
      builder: (_) => SupplierIrnDialog(
        billNumber: billNumber,
        current: current,
        save: save,
      ),
    );

class SupplierIrnDialog extends StatefulWidget {
  const SupplierIrnDialog({
    super.key,
    required this.billNumber,
    required this.current,
    required this.save,
  });

  final String billNumber;
  final String current;

  /// Records the IRN; a blank box is sent as null, which clears it.
  final Future<Json> Function(String? irn) save;

  @override
  State<SupplierIrnDialog> createState() => _SupplierIrnDialogState();
}

class _SupplierIrnDialogState extends State<SupplierIrnDialog>
    with SaveInDialog<SupplierIrnDialog> {
  late final TextEditingController _irn =
      TextEditingController(text: widget.current);
  String? _problem;

  @override
  void dispose() {
    _irn.dispose();
    super.dispose();
  }

  Future<void> _confirm() async {
    final String? problem = supplierIrnProblem(_irn.text);
    if (problem != null) {
      setState(() => _problem = problem);
      return;
    }
    setState(() => _problem = null);
    final String text = _irn.text.trim();
    await saveAndClose<Json>(() => widget.save(text.isEmpty ? null : text));
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: Text('IRN on ${widget.billNumber}'),
        content: SizedBox(
          width: 520,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              saveErrorBanner(),
              Text(
                'The IRN is printed under the QR code on the '
                "supplier's e-invoice. Leave it empty to clear it.",
                style: Theme.of(context).textTheme.bodySmall,
              ),
              const SizedBox(height: AppSpacing.md),
              TextField(
                key: const ValueKey('supplier-irn-input'),
                controller: _irn,
                autofocus: true,
                enabled: !saving,
                decoration: InputDecoration(
                  labelText: "IRN (from the supplier's e-invoice)",
                  errorText: _problem,
                  errorMaxLines: 2,
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
            key: const ValueKey('supplier-irn-save'),
            onPressed: saving ? null : _confirm,
            child: const Text('Record IRN'),
          ),
        ],
      );
}
