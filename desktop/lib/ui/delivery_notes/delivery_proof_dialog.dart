import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../models/entities.dart' show Json;
import '../../phase2/document_page.dart' show documentDate;
import '../workspace/save_in_dialog.dart';

/// The mime type a picked file is sent with, from its extension.
String proofMimeType(String fileName) {
  final String lower = fileName.toLowerCase();
  if (lower.endsWith('.pdf')) return 'application/pdf';
  if (lower.endsWith('.png')) return 'image/png';
  if (lower.endsWith('.jpg') || lower.endsWith('.jpeg')) return 'image/jpeg';
  return 'application/octet-stream';
}

/// Record that a dispatched note's goods arrived (backlog 67 row 6): when,
/// who signed for them, a remark, and optionally the signed copy.
///
/// The dialog makes the call itself and stays open with the server's message
/// on a refusal, every field kept (D-DLG-1). It closes with the note as the
/// server returned it.
class DeliveryProofDialog extends StatefulWidget {
  const DeliveryProofDialog({
    super.key,
    required this.api,
    required this.noteId,
    required this.noteNumber,
    required this.now,
    this.pickFile,
  });

  final ApiClient api;
  final String noteId;
  final String noteNumber;

  /// The moment the form starts at; passed in so the dialog is testable.
  final DateTime now;

  /// How a file is picked: the platform's file chooser unless a test says
  /// otherwise.
  final Future<XFile?> Function()? pickFile;

  @override
  State<DeliveryProofDialog> createState() => _DeliveryProofDialogState();
}

class _DeliveryProofDialogState extends State<DeliveryProofDialog>
    with SaveInDialog<DeliveryProofDialog> {
  final TextEditingController _receivedBy = TextEditingController();
  final TextEditingController _remarks = TextEditingController();
  late DateTime _deliveredAt = widget.now;
  XFile? _file;
  String? _problem;

  @override
  void dispose() {
    _receivedBy.dispose();
    _remarks.dispose();
    super.dispose();
  }

  Future<void> _pickDay() async {
    final DateTime? picked = await showDatePicker(
      context: context,
      initialDate: _deliveredAt,
      firstDate: DateTime(2000),
      lastDate: widget.now.add(const Duration(days: 1)),
      helpText: 'Delivered on',
    );
    if (picked == null) return;
    setState(() {
      _deliveredAt = DateTime(
        picked.year,
        picked.month,
        picked.day,
        _deliveredAt.hour,
        _deliveredAt.minute,
      );
    });
  }

  Future<void> _pickTime() async {
    final TimeOfDay? picked = await showTimePicker(
      context: context,
      initialTime: TimeOfDay.fromDateTime(_deliveredAt),
    );
    if (picked == null) return;
    setState(() {
      _deliveredAt = DateTime(
        _deliveredAt.year,
        _deliveredAt.month,
        _deliveredAt.day,
        picked.hour,
        picked.minute,
      );
    });
  }

  Future<void> _attach() async {
    final XFile? file = await (widget.pickFile ?? openFile)();
    if (file == null || !mounted) return;
    setState(() => _file = file);
  }

  void _submit() {
    final String receivedBy = _receivedBy.text.trim();
    if (receivedBy.isEmpty) {
      setState(() => _problem = 'Say who received the goods.');
      return;
    }
    if (_deliveredAt.isAfter(widget.now.add(const Duration(minutes: 5)))) {
      setState(() => _problem = 'The goods cannot have been delivered in the '
          'future.');
      return;
    }
    setState(() => _problem = null);
    final XFile? file = _file;
    final String remarks = _remarks.text.trim();
    saveAndClose<Json>(
      () => widget.api.recordDeliveryProof(
        widget.noteId,
        deliveredAt: _deliveredAt,
        receivedBy: receivedBy,
        remarks: remarks.isEmpty ? null : remarks,
        attachment: file == null
            ? null
            : <String, dynamic>{
                'file_name': file.name,
                'mime_type': proofMimeType(file.name),
                'file_path': file.path,
              },
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final String? shownProblem = _problem;
    return AlertDialog(
      title: Text('Proof of delivery · ${widget.noteNumber}'),
      content: SizedBox(
        width: 460,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              saveErrorBanner(),
              Row(children: [
                Expanded(
                  child: InkWell(
                    key: const ValueKey('proof-day'),
                    onTap: saving ? null : _pickDay,
                    child: InputDecorator(
                      decoration: const InputDecoration(
                        labelText: 'Delivered on',
                        suffixIcon: Icon(Icons.event, size: 18),
                      ),
                      child: Text(documentDate(_deliveredAt)),
                    ),
                  ),
                ),
                const SizedBox(width: AppSpacing.md),
                SizedBox(
                  width: 130,
                  child: InkWell(
                    key: const ValueKey('proof-time'),
                    onTap: saving ? null : _pickTime,
                    child: InputDecorator(
                      decoration: const InputDecoration(
                        labelText: 'At',
                        suffixIcon: Icon(Icons.schedule, size: 18),
                      ),
                      child: Text(
                        '${_deliveredAt.hour.toString().padLeft(2, '0')}:'
                        '${_deliveredAt.minute.toString().padLeft(2, '0')}',
                      ),
                    ),
                  ),
                ),
              ]),
              const SizedBox(height: AppSpacing.md),
              TextField(
                key: const ValueKey('proof-received-by'),
                controller: _receivedBy,
                enabled: !saving,
                maxLength: 120,
                decoration: const InputDecoration(
                  labelText: 'Received by *',
                  helperText: 'Whoever signed for the goods.',
                ),
              ),
              const SizedBox(height: AppSpacing.sm),
              TextField(
                key: const ValueKey('proof-remarks'),
                controller: _remarks,
                enabled: !saving,
                minLines: 2,
                maxLines: 4,
                decoration: const InputDecoration(labelText: 'Remarks'),
              ),
              const SizedBox(height: AppSpacing.md),
              Row(children: [
                OutlinedButton.icon(
                  key: const ValueKey('proof-attach'),
                  onPressed: saving ? null : _attach,
                  icon: const Icon(Icons.attach_file, size: 18),
                  label: Text(
                    _file == null ? 'Attach signed copy' : 'Change file',
                  ),
                ),
                const SizedBox(width: AppSpacing.md),
                if (_file != null)
                  Expanded(
                    child: InputChip(
                      key: const ValueKey('proof-file'),
                      label: Text(_file!.name, overflow: TextOverflow.ellipsis),
                      onDeleted:
                          saving ? null : () => setState(() => _file = null),
                    ),
                  ),
              ]),
              if (shownProblem != null) ...[
                const SizedBox(height: AppSpacing.lg),
                Text(
                  shownProblem,
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
          key: const ValueKey('proof-save'),
          onPressed: saving ? null : _submit,
          child: const Text('Record delivery'),
        ),
      ],
    );
  }
}
