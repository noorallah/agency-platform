import 'dart:io';

import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/dialogs/app_dialogs.dart';
import '../../models/document_file.dart';
import '../workspace/desktop_framework.dart';

/// The supplier's bill, or a photo of it, kept with a purchase bill or a goods
/// receipt (PG-4): see the files, add one, open or save one, take one away.
///
/// Only PDF, JPG and PNG up to 10 MB; the type and size are checked here so
/// the person is told at once, and again by the server. A document not yet
/// saved has nothing to attach to, so it says so rather than offering Add.
/// [canEdit] hides Add and Delete for somebody without the document's
/// permission.
class DocumentAttachmentsDialog extends StatefulWidget {
  const DocumentAttachmentsDialog({
    super.key,
    required this.api,
    required this.kind,
    required this.documentId,
    required this.subtitle,
    this.canEdit = true,
    this.pickFile,
    this.openBytes,
    this.saveBytes,
  });

  final ApiClient api;
  final AttachableDocument kind;

  /// Null while the document has not been saved.
  final String? documentId;

  /// The bill's or receipt's number, for the title.
  final String subtitle;
  final bool canEdit;

  /// Injected by tests; the platform's file chooser otherwise.
  final Future<XFile?> Function()? pickFile;

  /// Injected by tests; writes a temp file and opens it otherwise.
  final Future<void> Function(String name, List<int> bytes)? openBytes;

  /// Injected by tests; asks where to save otherwise.
  final Future<void> Function(String name, List<int> bytes)? saveBytes;

  @override
  State<DocumentAttachmentsDialog> createState() =>
      _DocumentAttachmentsDialogState();
}

class _DocumentAttachmentsDialogState extends State<DocumentAttachmentsDialog> {
  List<DocumentFileRecord> _files = const [];
  final TextEditingController _caption = TextEditingController();
  bool _loading = true;
  bool _busy = false;
  String? _error;

  String? get _id => widget.documentId;

  @override
  void initState() {
    super.initState();
    if (_id == null) {
      _loading = false;
    } else {
      _load();
    }
  }

  @override
  void dispose() {
    _caption.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final List<DocumentFileRecord> rows =
          await widget.api.listDocumentFiles(widget.kind, _id!);
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

  /// Runs one action with the busy flag up and a refusal shown inside the
  /// dialog.
  Future<void> _run(Future<void> Function() action) async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await action();
    } on ApiException catch (exception) {
      _error = exception.message;
    } on FileSystemException catch (exception) {
      _error = 'The file could not be written: ${exception.message}';
    }
    if (mounted) setState(() => _busy = false);
  }

  Future<void> _refresh() async {
    final List<DocumentFileRecord> rows =
        await widget.api.listDocumentFiles(widget.kind, _id!);
    if (mounted) setState(() => _files = rows);
  }

  Future<XFile?> _chooseFile() => openFile(acceptedTypeGroups: const [
        XTypeGroup(
          label: 'PDF or photo',
          extensions: ['pdf', 'jpg', 'jpeg', 'png'],
        ),
      ]);

  Future<void> _add() async {
    final XFile? picked = await (widget.pickFile ?? _chooseFile)();
    if (picked == null || !mounted) return;
    final int size = await picked.length();
    final String? problem = documentFileProblem(picked.name, size);
    if (problem != null) {
      setState(() => _error = problem);
      return;
    }
    await _run(() async {
      await widget.api.uploadDocumentFile(
        widget.kind,
        _id!,
        fileName: picked.name,
        bytes: await picked.readAsBytes(),
        caption: _caption.text,
      );
      _caption.clear();
      await _refresh();
    });
  }

  Future<void> _open(DocumentFileRecord file) => _run(() async {
        final List<int> bytes =
            await widget.api.downloadDocumentFile(widget.kind, _id!, file.id);
        if (widget.openBytes != null) {
          await widget.openBytes!(file.fileName, bytes);
          return;
        }
        final Directory dir = await Directory.systemTemp.createTemp('bill-');
        final File out =
            File('${dir.path}${Platform.pathSeparator}${file.fileName}');
        await out.writeAsBytes(bytes, flush: true);
        if (Platform.isWindows) {
          await Process.run('cmd', ['/c', 'start', '', out.path]);
        } else if (Platform.isMacOS) {
          await Process.run('open', [out.path]);
        } else {
          await Process.run('xdg-open', [out.path]);
        }
      });

  Future<void> _save(DocumentFileRecord file) => _run(() async {
        final List<int> bytes =
            await widget.api.downloadDocumentFile(widget.kind, _id!, file.id);
        if (widget.saveBytes != null) {
          await widget.saveBytes!(file.fileName, bytes);
          return;
        }
        final FileSaveLocation? where =
            await getSaveLocation(suggestedName: file.fileName);
        if (where == null) return;
        await File(where.path).writeAsBytes(bytes, flush: true);
      });

  Future<void> _remove(DocumentFileRecord file) async {
    final bool go = await showWorkspaceConfirmDialog(
      context,
      title: 'Delete ${file.fileName}?',
      message: 'The file is taken off this document. The trail keeps that it '
          'was deleted.',
      confirmLabel: 'Delete',
      type: ConfirmationType.delete,
    );
    if (!go || !mounted) return;
    await _run(() async {
      await widget.api.removeDocumentFile(widget.kind, _id!, file.id);
      await _refresh();
    });
  }

  String _day(String iso) => iso.length >= 10 ? iso.substring(0, 10) : iso;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return AlertDialog(
      title: Text('Attachments · ${widget.subtitle}'),
      content: SizedBox(
        width: 640,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (_error != null)
                Container(
                  key: const ValueKey<String>('document-files-error'),
                  margin: const EdgeInsets.only(bottom: AppSpacing.md),
                  padding: const EdgeInsets.all(AppSpacing.md),
                  color: theme.colorScheme.errorContainer,
                  child: Text(
                    _error!,
                    style: TextStyle(color: theme.colorScheme.onErrorContainer),
                  ),
                ),
              if (_id == null)
                const Padding(
                  key: ValueKey<String>('document-files-save-first'),
                  padding: EdgeInsets.only(bottom: AppSpacing.md),
                  child: Text('Save first to attach files'),
                )
              else if (_loading)
                const Center(child: CircularProgressIndicator())
              else if (_files.isEmpty)
                const Padding(
                  padding: EdgeInsets.only(bottom: AppSpacing.md),
                  child: Text('Nothing is attached yet.'),
                )
              else
                for (final DocumentFileRecord file in _files)
                  ListTile(
                    key: ValueKey<String>('document-file-${file.id}'),
                    dense: true,
                    contentPadding: EdgeInsets.zero,
                    leading: const Icon(Icons.attach_file),
                    title: Text(file.fileName, overflow: TextOverflow.ellipsis),
                    subtitle: Text(
                      [
                        documentFileSize(file.sizeBytes),
                        _day(file.createdAt),
                        if (file.caption.isNotEmpty) file.caption,
                      ].join(' · '),
                      overflow: TextOverflow.ellipsis,
                    ),
                    trailing: Wrap(
                      children: [
                        IconButton(
                          tooltip: 'Open',
                          icon: const Icon(Icons.open_in_new),
                          onPressed: _busy ? null : () => _open(file),
                        ),
                        IconButton(
                          tooltip: 'Save as',
                          icon: const Icon(Icons.download_outlined),
                          onPressed: _busy ? null : () => _save(file),
                        ),
                        if (widget.canEdit)
                          IconButton(
                            tooltip: 'Delete',
                            icon: const Icon(Icons.delete_outline),
                            onPressed: _busy ? null : () => _remove(file),
                          ),
                      ],
                    ),
                  ),
              if (widget.canEdit && _id != null) ...[
                const Divider(),
                Row(
                  children: [
                    Expanded(
                      child: TextField(
                        key: const ValueKey<String>('document-file-caption'),
                        controller: _caption,
                        maxLength: 200,
                        decoration: const InputDecoration(
                          labelText: 'Caption (optional)',
                          counterText: '',
                        ),
                      ),
                    ),
                    const SizedBox(width: AppSpacing.md),
                    FilledButton.icon(
                      key: const ValueKey<String>('document-file-add'),
                      onPressed: _busy ? null : _add,
                      icon: const Icon(Icons.add),
                      label: const Text('Add file'),
                    ),
                  ],
                ),
                const SizedBox(height: AppSpacing.sm),
                Text(
                  'PDF, JPG or PNG, up to 10 MB.',
                  style: theme.textTheme.bodySmall,
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
      ],
    );
  }
}

/// Opens the attachments panel for one saved document (SG-6): the list
/// toolbars of the five sales documents call this, so approved and cancelled
/// documents -- which no editor opens -- can still be given their files.
Future<void> showDocumentAttachments(
  BuildContext context, {
  required ApiClient api,
  required AttachableDocument kind,
  required String documentId,
  required String subtitle,
  required bool canEdit,
}) =>
    showDialog<void>(
      context: context,
      builder: (_) => DocumentAttachmentsDialog(
        api: api,
        kind: kind,
        documentId: documentId,
        subtitle: subtitle,
        canEdit: canEdit,
      ),
    );
