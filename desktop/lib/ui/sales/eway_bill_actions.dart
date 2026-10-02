// What the desktop does about an e-way bill that is not on an e-invoiced
// invoice (backlog 77 rows 9 and 10): raise one for an invoice or a delivery
// note, record one raised by hand on the portal, and nudge the person when a
// consignment is worth more than the firm's limit and has none.
//
// Shared by the e-invoice screen, the delivery note screen and the sales
// invoice screen, so each says the same thing the same way.

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../models/einvoice.dart';
import '../../models/entities.dart';
import '../../phase2/indian_format.dart';
import '../workspace/reason_prompt.dart';
import '../workspace/save_in_dialog.dart';
import 'einvoice_page.dart' show EWayBillDialog;

/// Ask for the transport details and raise the e-way bill, for an invoice or
/// for a delivery note no invoice bills. True once it is raised; a refusal
/// stays in the dialog with the server's words.
Future<bool> raiseEwayBillFor(
  BuildContext context,
  ApiClient api, {
  String? invoiceId,
  String? noteId,
}) async {
  assert((invoiceId == null) != (noteId == null));
  final Json? details = await showDialog<Json>(
    context: context,
    builder: (_) => EWayBillDialog(
      onSave: (Json values) => invoiceId != null
          ? api.generateEwayBill(invoiceId, values)
          : api.generateDeliveryNoteEwayBill(noteId!, values),
    ),
  );
  return details != null;
}

/// Ask for the number of a bill raised on the portal and record it. True once
/// it is recorded.
Future<bool> recordEwayBillFor(
  BuildContext context,
  ApiClient api, {
  String? invoiceId,
  String? noteId,
}) async {
  assert((invoiceId == null) != (noteId == null));
  final Json? recorded = await showDialog<Json>(
    context: context,
    builder: (_) => RecordEwayBillDialog(
      invoiceId: invoiceId,
      noteId: noteId,
      onSave: (Json values) => api.recordEwayBill(values),
    ),
  );
  return recorded != null;
}

/// Record an e-way bill raised by hand on the portal: its number, and what
/// the person has to hand of its validity, distance and vehicle.
class RecordEwayBillDialog extends StatefulWidget {
  const RecordEwayBillDialog({
    super.key,
    this.invoiceId,
    this.noteId,
    this.onSave,
  });

  final String? invoiceId;
  final String? noteId;

  /// Records the bill; throws [ApiException] on a refusal, which the dialog
  /// shows without closing. Null closes with the details at once.
  final Future<void> Function(Json details)? onSave;

  @override
  State<RecordEwayBillDialog> createState() => _RecordEwayBillDialogState();
}

class _RecordEwayBillDialogState extends State<RecordEwayBillDialog>
    with SaveInDialog<RecordEwayBillDialog> {
  final TextEditingController _number = TextEditingController();
  final TextEditingController _distance = TextEditingController();
  final TextEditingController _vehicle = TextEditingController();
  String? _validUntil;
  String? _error;

  @override
  void dispose() {
    _number.dispose();
    _distance.dispose();
    _vehicle.dispose();
    super.dispose();
  }

  Future<void> _pickDate() async {
    final DateTime now = DateTime.now();
    final DateTime? picked = await showDatePicker(
      context: context,
      initialDate: DateTime.tryParse(_validUntil ?? '') ?? now,
      firstDate: DateTime(now.year - 1),
      lastDate: DateTime(now.year + 2),
    );
    if (picked == null || !mounted) return;
    setState(() => _validUntil = picked.toIso8601String().split('T').first);
  }

  void _submit() {
    final String number = _number.text.replaceAll(' ', '');
    if (!RegExp(r'^\d{12}$').hasMatch(number)) {
      setState(() => _error = 'An e-way bill number is 12 digits.');
      return;
    }
    final String typed = _distance.text.trim();
    final double? distance = double.tryParse(typed);
    if (typed.isNotEmpty && (distance == null || distance <= 0)) {
      setState(() => _error = 'Enter how far the goods travel, in kilometres.');
      return;
    }
    setState(() => _error = null);
    submit<Json>(<String, dynamic>{
      if (widget.invoiceId != null) 'sales_invoice_id': widget.invoiceId,
      if (widget.noteId != null) 'delivery_note_id': widget.noteId,
      'eway_bill_number': number,
      if (_validUntil != null) 'valid_until': _validUntil,
      if (typed.isNotEmpty) 'distance_km': typed,
      if (_vehicle.text.trim().isNotEmpty)
        'vehicle_number': _vehicle.text.trim(),
    }, widget.onSave);
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return AlertDialog(
      title: const Text('Record an e-way bill'),
      content: SizedBox(
        width: 480,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                'For a bill you raised on the e-way bill portal. Nothing is '
                'sent to the authority from here.',
                style: theme.textTheme.bodySmall,
              ),
              const SizedBox(height: AppSpacing.md),
              saveErrorBanner(),
              TextField(
                key: const ValueKey('eway-record-number'),
                controller: _number,
                keyboardType: TextInputType.number,
                inputFormatters: [
                  FilteringTextInputFormatter.allow(RegExp(r'[0-9 ]')),
                ],
                decoration: const InputDecoration(
                  labelText: 'E-way bill number',
                  helperText: '12 digits; spaces are fine.',
                ),
              ),
              const SizedBox(height: AppSpacing.md),
              InkWell(
                key: const ValueKey('eway-record-valid-until'),
                onTap: saving ? null : _pickDate,
                child: InputDecorator(
                  decoration: InputDecoration(
                    labelText: 'Valid until',
                    suffixIcon: _validUntil == null
                        ? const Icon(Icons.event, size: 18)
                        : IconButton(
                            tooltip: 'Clear',
                            iconSize: 16,
                            onPressed: () =>
                                setState(() => _validUntil = null),
                            icon: const Icon(Icons.close),
                          ),
                  ),
                  child: Text(_validUntil ?? 'Not set'),
                ),
              ),
              const SizedBox(height: AppSpacing.md),
              TextField(
                key: const ValueKey('eway-record-distance'),
                controller: _distance,
                keyboardType:
                    const TextInputType.numberWithOptions(decimal: true),
                inputFormatters: [
                  FilteringTextInputFormatter.allow(RegExp(r'[0-9.]')),
                ],
                decoration: const InputDecoration(labelText: 'Distance (km)'),
              ),
              const SizedBox(height: AppSpacing.md),
              TextField(
                key: const ValueKey('eway-record-vehicle'),
                controller: _vehicle,
                textCapitalization: TextCapitalization.characters,
                decoration: const InputDecoration(labelText: 'Vehicle number'),
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
      ),
      actions: [
        TextButton(onPressed: cancelHandler, child: const Text('Cancel')),
        FilledButton(
          key: const ValueKey('eway-record-save'),
          onPressed: saving ? null : _submit,
          child: const Text('Record'),
        ),
      ],
    );
  }
}

/// A non-blocking nudge after a consignment leaves or an invoice is approved:
/// "worth more than the limit: raise its e-way bill?". One per screen, so the
/// firm's limit is read once and kept.
///
/// Silent whenever it cannot be sure -- the settings cannot be read, the
/// consignment is under the limit, or it already has a live e-way bill --
/// because a prompt that is wrong is worse than none and the server, not this
/// screen, is what refuses.
class EwayBillNudge {
  EwayBillNudge(this.api);

  final ApiClient api;
  double? _limit;
  bool _read = false;

  Future<double?> _limitOnce() async {
    if (!_read) {
      _read = true;
      try {
        _limit = double.tryParse((await api.gstComplianceSettings()).ewayBillLimit);
      } catch (_) {
        _limit = null;
      }
    }
    return _limit;
  }

  /// Offer to raise or record the bill of the document just moved. Pass
  /// exactly one of [invoiceId] and [noteId]. [onDone] runs after a raise or a
  /// record, so the screen can refresh.
  Future<void> offer(
    BuildContext context, {
    String? invoiceId,
    String? noteId,
    required String grandTotal,
    VoidCallback? onDone,
  }) async {
    final double? value = double.tryParse(grandTotal);
    final double? limit = await _limitOnce();
    if (value == null || limit == null || value <= limit) return;
    try {
      final EWayBillRecord? bill = invoiceId != null
          ? await api.ewayBill(invoiceId)
          : await api.deliveryNoteEwayBill(noteId!);
      if (bill != null && bill.isGenerated) return;
    } catch (_) {
      return;
    }
    if (!context.mounted) return;
    // Queued behind whatever is showing -- an approval's credit warning must
    // not be pushed off the screen by this one.
    final ScaffoldMessengerState messenger = ScaffoldMessenger.of(context);

    Future<void> act(
      Future<bool> Function(BuildContext, ApiClient, {String? invoiceId, String? noteId})
          step,
      String done,
    ) async {
      messenger.hideCurrentSnackBar();
      if (!context.mounted) return;
      try {
        if (!await step(context, api, invoiceId: invoiceId, noteId: noteId)) {
          return;
        }
      } on ApiException catch (error) {
        if (context.mounted) {
          NotificationService.show(context, error.message,
              kind: AppNotificationKind.error);
        }
        return;
      }
      if (!context.mounted) return;
      NotificationService.show(context, done,
          kind: AppNotificationKind.success);
      onDone?.call();
    }

    messenger.showSnackBar(
      SnackBar(
        key: const ValueKey('eway-nudge'),
        duration: const Duration(seconds: 20),
        behavior: SnackBarBehavior.floating,
        content: Row(
          children: [
            const Icon(Icons.local_shipping_outlined),
            const SizedBox(width: 12),
            Expanded(
              child: Text(
                'This consignment is worth more than ₹'
                '${indianAmount(limit)}: raise its e-way bill?',
              ),
            ),
            TextButton(
              key: const ValueKey('eway-nudge-raise'),
              onPressed: () => act(raiseEwayBillFor, 'E-way bill raised.'),
              child: const Text('Raise'),
            ),
            TextButton(
              key: const ValueKey('eway-nudge-record'),
              onPressed: () => act(recordEwayBillFor, 'E-way bill recorded.'),
              child: const Text('Record'),
            ),
            TextButton(
              key: const ValueKey('eway-nudge-later'),
              onPressed: messenger.hideCurrentSnackBar,
              child: const Text('Later'),
            ),
          ],
        ),
      ),
    );
  }
}

/// A delivery note's e-way bill: its number where it has one, and what can be
/// done about it. True once something changed, so the caller can refresh.
///
/// The server decides whether the note may carry one at all -- a note an
/// invoice bills travels on that invoice's bill -- and its message is shown
/// as given when it refuses.
Future<bool> showNoteEwayBill(
  BuildContext context,
  ApiClient api, {
  required String noteId,
  required String noteNumber,
  required bool mayManage,
}) async {
  final bool? changed = await showDialog<bool>(
    context: context,
    builder: (_) => _NoteEwayBillDialog(
      api: api,
      noteId: noteId,
      noteNumber: noteNumber,
      mayManage: mayManage,
    ),
  );
  return changed ?? false;
}

class _NoteEwayBillDialog extends StatefulWidget {
  const _NoteEwayBillDialog({
    required this.api,
    required this.noteId,
    required this.noteNumber,
    required this.mayManage,
  });

  final ApiClient api;
  final String noteId;
  final String noteNumber;
  final bool mayManage;

  @override
  State<_NoteEwayBillDialog> createState() => _NoteEwayBillDialogState();
}

class _NoteEwayBillDialogState extends State<_NoteEwayBillDialog> {
  EWayBillRecord? _bill;
  String? _error;
  bool _loading = true;
  bool _changed = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final EWayBillRecord? bill =
          await widget.api.deliveryNoteEwayBill(widget.noteId);
      if (!mounted) return;
      setState(() {
        _bill = bill;
        _loading = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.message;
        _loading = false;
      });
    }
  }

  Future<void> _step(
    Future<bool> Function(BuildContext, ApiClient, {String? invoiceId, String? noteId})
        step,
  ) async {
    if (!await step(context, widget.api, noteId: widget.noteId)) return;
    _changed = true;
    if (mounted) await _load();
  }

  /// Withdraw the note's live bill, with the reason the portal requires.
  /// A refusal -- past the window, say -- stays in the dialog.
  Future<void> _withdraw() async {
    final String? reason = await askForReason(
      context,
      title: 'Withdraw e-way bill',
      explanation: 'The portal allows a bill to be cancelled within 24 hours '
          'of generation, and asks why.',
      confirmLabel: 'Withdraw',
    );
    if (reason == null) return;
    try {
      await widget.api.cancelDeliveryNoteEwayBill(widget.noteId, reason: reason);
      _changed = true;
      if (mounted) await _load();
    } on ApiException catch (error) {
      if (mounted) setState(() => _error = error.message);
    }
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final EWayBillRecord? bill = _bill;
    final bool live = bill != null && bill.isGenerated;
    return AlertDialog(
      title: Text('E-way bill: ${widget.noteNumber}'),
      content: SizedBox(
        width: 460,
        child: _loading
            ? const Padding(
                padding: EdgeInsets.all(AppSpacing.lg),
                child: Center(child: CircularProgressIndicator()),
              )
            : _error != null
                ? Text(_error!, style: TextStyle(color: theme.colorScheme.error))
                : Text(
                    live
                        ? bill.referenceLabel
                        : 'This delivery note has no e-way bill. Raise one '
                            'from here, or record one you raised on the '
                            'e-way bill portal.',
                    key: const ValueKey('note-eway-state'),
                  ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(_changed),
          child: const Text('Close'),
        ),
        if (widget.mayManage && !_loading && live)
          OutlinedButton(
            key: const ValueKey('note-eway-withdraw'),
            onPressed: _withdraw,
            child: const Text('Withdraw...'),
          ),
        if (widget.mayManage && !_loading && _error == null && !live) ...[
          OutlinedButton(
            key: const ValueKey('note-eway-record'),
            onPressed: () => _step(recordEwayBillFor),
            child: const Text('Record...'),
          ),
          FilledButton(
            key: const ValueKey('note-eway-raise'),
            onPressed: () => _step(raiseEwayBillFor),
            child: const Text('Raise e-way bill'),
          ),
        ],
      ],
    );
  }
}
