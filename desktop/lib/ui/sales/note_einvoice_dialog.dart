// A credit or customer debit note's e-invoice (backlog 77 row 4): its
// registration where it has one, and Register or Withdraw where it has not.
//
// Shared by the credit note and customer debit note screens so each says the
// same thing the same way. The server decides whether a note may be filed;
// its message is shown as given when it refuses.

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../models/einvoice.dart';
import '../workspace/copy_value_button.dart';
import '../workspace/reason_prompt.dart';

/// The path segment the credit note routes live under.
const String creditNotesEInvoiceKind = 'credit-notes';

/// The path segment the customer debit note routes live under.
const String debitNotesEInvoiceKind = 'debit-notes';

/// Show [noteNumber]'s registration and what can be done about it. [kind] is
/// [creditNotesEInvoiceKind] or [debitNotesEInvoiceKind]. True once something
/// changed, so the caller can refresh.
Future<bool> showNoteEInvoice(
  BuildContext context,
  ApiClient api, {
  required String kind,
  required String noteId,
  required String noteNumber,
  required bool mayManage,
}) async {
  final bool? changed = await showDialog<bool>(
    context: context,
    // Selectable, as every dialog's text (backlog 83).
    builder: (_) => SelectionArea(
      child: _NoteEInvoiceDialog(
        api: api,
        kind: kind,
        noteId: noteId,
        noteNumber: noteNumber,
        mayManage: mayManage,
      ),
    ),
  );
  return changed ?? false;
}

class _NoteEInvoiceDialog extends StatefulWidget {
  const _NoteEInvoiceDialog({
    required this.api,
    required this.kind,
    required this.noteId,
    required this.noteNumber,
    required this.mayManage,
  });

  final ApiClient api;
  final String kind;
  final String noteId;
  final String noteNumber;
  final bool mayManage;

  @override
  State<_NoteEInvoiceDialog> createState() => _NoteEInvoiceDialogState();
}

class _NoteEInvoiceDialogState extends State<_NoteEInvoiceDialog> {
  EInvoiceRegistrationRecord? _row;
  String? _error;
  bool _loading = true;
  bool _busy = false;
  bool _changed = false;
  bool _loadFailed = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
      _loadFailed = false;
    });
    try {
      final EInvoiceRegistrationRecord? row = await widget.api
          .einvoiceNoteRegistration(widget.kind, widget.noteId);
      if (!mounted) return;
      setState(() {
        _row = row;
        _loading = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.message;
        _loading = false;
        _loadFailed = true;
      });
    }
  }

  /// Run one step; a refusal stays on the dialog in the server's words.
  Future<void> _run(Future<EInvoiceRegistrationRecord> Function() step) async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final EInvoiceRegistrationRecord row = await step();
      _changed = true;
      if (!mounted) return;
      setState(() {
        _row = row;
        _busy = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.message;
        _busy = false;
      });
    }
  }

  Future<void> _withdraw() async {
    final String? reason = await askForReason(
      context,
      title: 'Withdraw registration',
      explanation: 'The authority requires a reason, and allows 24 hours.',
    );
    if (reason == null) return;
    await _run(() => widget.api
        .cancelEInvoiceNote(widget.kind, widget.noteId, reason: reason));
  }

  Widget _detail(ThemeData theme, EInvoiceRegistrationRecord row) {
    // [copy] puts a copy icon beside the value (backlog 83): the IRN and
    // the acknowledgement are what people paste into the portal.
    Widget line(String label, String value, {bool copy = false}) => Padding(
          padding: const EdgeInsets.only(bottom: AppSpacing.xs),
          child: Row(children: [
            Flexible(child: Text('$label: ${value.isEmpty ? '—' : value}')),
            if (copy)
              CopyValueButton(
                key: ValueKey<String>('copy-$label'),
                value: value,
                what: label,
              ),
          ]),
        );
    return Column(
      key: const ValueKey('note-einvoice-state'),
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        line('Status', row.status),
        line('Mode', row.mode),
        if (row.isRegistered) ...[
          line('IRN', row.irn, copy: true),
          line('Acknowledgement', row.acknowledgementNumber, copy: true),
          if (row.isSandbox)
            Text(
              'Sandbox — nothing was filed.',
              style: theme.textTheme.bodySmall,
            ),
        ] else if (row.errorMessage.isNotEmpty)
          Text(
            row.errorMessage,
            style: TextStyle(color: theme.colorScheme.error),
          ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final EInvoiceRegistrationRecord? row = _row;
    final bool ready = !_loading && !_busy;
    return AlertDialog(
      title: Text('E-invoice: ${widget.noteNumber}'),
      content: SizedBox(
        width: 460,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (_loading)
              const Padding(
                padding: EdgeInsets.all(AppSpacing.lg),
                child: Center(child: CircularProgressIndicator()),
              )
            else if (row != null)
              _detail(theme, row)
            else if (_error == null)
              const Text(
                'This note has not been e-invoiced.',
                key: ValueKey('note-einvoice-state'),
              ),
            if (_error != null)
              Padding(
                padding: const EdgeInsets.only(top: AppSpacing.sm),
                child: Text(
                  _error!,
                  key: const ValueKey('note-einvoice-error'),
                  style: TextStyle(color: theme.colorScheme.error),
                ),
              ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(_changed),
          child: const Text('Close'),
        ),
        if (widget.mayManage && ready && row != null && row.isRegistered)
          OutlinedButton(
            key: const ValueKey('note-einvoice-withdraw'),
            onPressed: _withdraw,
            child: const Text('Withdraw'),
          ),
        // A refusal keeps its row, so the same call is the retry. A withdrawn
        // IRN is never reissued for the same number, so it offers nothing.
        if (widget.mayManage &&
            ready &&
            !_loadFailed &&
            (row == null || row.isFailed))
          FilledButton(
            key: const ValueKey('note-einvoice-register'),
            onPressed: () => _run(
                () => widget.api.registerEInvoiceNote(widget.kind, widget.noteId)),
            child: Text(row == null ? 'Register' : 'Try again'),
          ),
      ],
    );
  }
}
