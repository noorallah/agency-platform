import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/dialogs/app_dialogs.dart';
import '../../models/entities.dart' show Json;
import '../../models/inventory.dart';
import '../../models/settlement_direction.dart';
import '../inventory/stock_evidence_picker.dart';
import '../workspace/desktop_framework.dart';

/// The files kept with one journal entry, receipt or payment (ACC-10): see
/// them, attach more, take one away. The file stays where it is; the record
/// keeps its path, exactly as with a stock movement's evidence.
///
/// Name a journal with [journal], or a receipt or payment with [settlement]
/// and [direction]. A refusal from the server is shown inside the dialog and
/// nothing typed is lost.
class LedgerFilesDialog extends StatefulWidget {
  const LedgerFilesDialog({
    super.key,
    required this.api,
    required this.subtitle,
    required this.recordId,
    this.direction,
    this.canView = true,
    this.canEdit = true,
    this.pickFiles,
  });

  /// A journal entry's files.
  const LedgerFilesDialog.journal({
    super.key,
    required this.api,
    required this.subtitle,
    required String journalId,
    this.canView = true,
    this.canEdit = true,
    this.pickFiles,
  })  : recordId = journalId,
        direction = null;

  final ApiClient api;

  /// The journal's or settlement's id.
  final String recordId;

  /// Null for a journal entry; receipt or payment otherwise.
  final SettlementDirection? direction;

  /// What the files belong to, e.g. the entry's reference or the receipt
  /// number.
  final String subtitle;

  /// False when the reader lacks the view permission: nothing is listed.
  final bool canView;

  /// False hides attaching and removing, for a reader who may only look.
  final bool canEdit;

  /// Injected by tests; the platform's file chooser otherwise.
  final Future<List<XFile>> Function()? pickFiles;

  @override
  State<LedgerFilesDialog> createState() => _LedgerFilesDialogState();
}

class _LedgerFilesDialogState extends State<LedgerFilesDialog> {
  List<StockAttachmentRecord> _files = const [];
  List<Json> _pending = const [];
  // Bumped after a save so the picker starts empty again.
  int _pickerEpoch = 0;
  bool _loading = true;
  bool _busy = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    if (widget.canView) {
      _load();
    } else {
      _loading = false;
    }
  }

  Future<List<StockAttachmentRecord>> _fetch() => widget.direction == null
      ? widget.api.listJournalAttachments(widget.recordId)
      : widget.api.listSettlementAttachments(
          widget.direction!, widget.recordId);

  Future<void> _load() async {
    try {
      final List<StockAttachmentRecord> rows = await _fetch();
      if (!mounted) return;
      setState(() {
        _files = rows;
        _loading = false;
      });
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() {
        _error = exception.message;
        _loading = false;
      });
    }
  }

  Future<void> _save() async {
    if (_pending.isEmpty || _busy) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      if (widget.direction == null) {
        await widget.api.attachToJournal(widget.recordId, _pending);
      } else {
        await widget.api
            .attachToSettlement(widget.direction!, widget.recordId, _pending);
      }
      final List<StockAttachmentRecord> rows =
          widget.canView ? await _fetch() : _files;
      if (!mounted) return;
      setState(() {
        _files = rows;
        _pending = const [];
        _pickerEpoch++;
        _busy = false;
      });
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() {
        _error = exception.message;
        _busy = false;
      });
    }
  }

  Future<void> _remove(StockAttachmentRecord file) async {
    final bool go = await showWorkspaceConfirmDialog(
      context,
      title: 'Remove ${file.fileName}?',
      message: 'The file is taken off this record. The trail keeps that it '
          'was removed.',
      confirmLabel: 'Remove',
      type: ConfirmationType.delete,
    );
    if (!go || !mounted) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      if (widget.direction == null) {
        await widget.api.removeJournalAttachment(widget.recordId, file.id);
      } else {
        await widget.api.removeSettlementAttachment(
            widget.direction!, widget.recordId, file.id);
      }
      final List<StockAttachmentRecord> rows = await _fetch();
      if (!mounted) return;
      setState(() {
        _files = rows;
        _busy = false;
      });
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() {
        _error = exception.message;
        _busy = false;
      });
    }
  }

  String _day(String iso) => iso.length >= 10 ? iso.substring(0, 10) : iso;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return AlertDialog(
      title: Text('Files · ${widget.subtitle}'),
      content: SizedBox(
        width: 640,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (_error != null)
                Container(
                  key: const ValueKey<String>('ledger-files-error'),
                  margin: const EdgeInsets.only(bottom: AppSpacing.md),
                  padding: const EdgeInsets.all(AppSpacing.md),
                  color: theme.colorScheme.errorContainer,
                  child: Text(
                    _error!,
                    style: TextStyle(color: theme.colorScheme.onErrorContainer),
                  ),
                ),
              if (_loading)
                const Center(child: CircularProgressIndicator())
              else if (!widget.canView)
                const Padding(
                  padding: EdgeInsets.only(bottom: AppSpacing.md),
                  child: Text('You do not have permission to see the files.'),
                )
              else if (_files.isEmpty)
                const Padding(
                  padding: EdgeInsets.only(bottom: AppSpacing.md),
                  child: Text('Nothing is attached yet.'),
                )
              else
                for (final StockAttachmentRecord file in _files)
                  ListTile(
                    key: ValueKey<String>('ledger-file-${file.id}'),
                    dense: true,
                    contentPadding: EdgeInsets.zero,
                    leading: const Icon(Icons.attach_file),
                    title: Text(file.fileName, overflow: TextOverflow.ellipsis),
                    subtitle: Text(
                      [
                        if ((file.caption ?? '').isNotEmpty) file.caption!,
                        _day(file.createdAt),
                      ].join(' · '),
                      overflow: TextOverflow.ellipsis,
                    ),
                    trailing: widget.canEdit
                        ? IconButton(
                            tooltip: 'Remove',
                            icon: const Icon(Icons.delete_outline),
                            onPressed: _busy ? null : () => _remove(file),
                          )
                        : null,
                  ),
              if (widget.canEdit) ...[
                const Divider(),
                StockEvidencePicker(
                  key: ValueKey<int>(_pickerEpoch),
                  pickFiles: widget.pickFiles,
                  remaining: 10,
                  onChanged: (List<Json> files) =>
                      setState(() => _pending = files),
                ),
              ],
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Close'),
        ),
        if (widget.canEdit)
          FilledButton(
            onPressed: _busy || _pending.isEmpty ? null : _save,
            child: const Text('Save files'),
          ),
      ],
    );
  }
}
