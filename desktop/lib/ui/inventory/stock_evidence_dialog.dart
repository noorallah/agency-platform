import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/dialogs/app_dialogs.dart';
import '../../core/design/design_tokens.dart';
import '../../models/entities.dart' show Json;
import '../../models/inventory.dart';
import '../workspace/desktop_framework.dart';
import 'stock_evidence_picker.dart';

/// The photos and documents kept with one stock movement or one count sheet
/// (STK-9): see them, add more, take one away.
///
/// Name exactly one of [transactionId] and [countId]. A refusal from the
/// server is shown inside the dialog and nothing is lost.
class StockEvidenceDialog extends StatefulWidget {
  const StockEvidenceDialog({
    super.key,
    required this.api,
    required this.subtitle,
    this.transactionId,
    this.countId,
    this.canEdit = true,
    this.pickFiles,
  }) : assert((transactionId == null) != (countId == null));

  final ApiClient api;
  final String? transactionId;
  final String? countId;

  /// What the files belong to, e.g. the movement's reference or the count
  /// number.
  final String subtitle;

  /// False hides adding and removing, for a reader who may only look.
  final bool canEdit;

  /// Injected by tests; the platform's file chooser otherwise.
  final Future<List<XFile>> Function()? pickFiles;

  @override
  State<StockEvidenceDialog> createState() => _StockEvidenceDialogState();
}

class _StockEvidenceDialogState extends State<StockEvidenceDialog> {
  List<StockAttachmentRecord> _files = const [];
  List<Json> _pending = const [];
  // Bumped after an upload so the picker starts empty again.
  int _pickerEpoch = 0;
  bool _loading = true;
  bool _busy = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<List<StockAttachmentRecord>> _fetch() => widget.transactionId != null
      ? widget.api.listMovementAttachments(widget.transactionId!)
      : widget.api.listCountAttachments(widget.countId!);

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

  Future<void> _upload() async {
    if (_pending.isEmpty || _busy) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      if (widget.transactionId != null) {
        await widget.api.attachToMovement(widget.transactionId!, _pending);
      } else {
        await widget.api.attachToCount(widget.countId!, _pending);
      }
      final List<StockAttachmentRecord> rows = await _fetch();
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
      await widget.api.removeStockAttachment(file.id);
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
      title: Text('Evidence · ${widget.subtitle}'),
      content: SizedBox(
        width: 640,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (_error != null)
                Container(
                  key: const ValueKey<String>('evidence-error'),
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
              else if (_files.isEmpty)
                const Padding(
                  padding: EdgeInsets.only(bottom: AppSpacing.md),
                  child: Text('Nothing is attached yet.'),
                )
              else
                for (final StockAttachmentRecord file in _files)
                  ListTile(
                    key: ValueKey<String>('evidence-${file.id}'),
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
            onPressed: _busy || _pending.isEmpty ? null : _upload,
            child: const Text('Save files'),
          ),
      ],
    );
  }
}
