import 'dart:convert';
import 'dart:io';

import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../models/file_import.dart';
import 'desktop_framework.dart';
import 'import_mapping_panel.dart';

/// How bytes are written to disk. Tests inject one, because a widget test
/// cannot open a native save dialog.
typedef SaveBytesOverride = Future<void> Function(
  String suggestedName,
  List<int> bytes,
);

/// The problems list as a CSV a person can fix the file from.
String importProblemsCsv(List<FileImportIssue> issues) {
  String quote(String value) => '"${value.replaceAll('"', '""')}"';
  final StringBuffer buffer = StringBuffer('Row,Code,Column,Problem\r\n');
  for (final FileImportIssue issue in issues) {
    buffer.write(
      '${issue.row},${quote(issue.code ?? '')},${quote(issue.column ?? '')},'
      '${quote(issue.message)}\r\n',
    );
  }
  return buffer.toString();
}

/// Load master records (products, customers) from a CSV or XLSX file.
///
/// The server does the checking. A check writes nothing; Import is offered only
/// after a clean check of the file as it now stands, with the same choice about
/// existing products, and the server writes the whole file or none of it.
/// Closes with the applied [FileImportReport], or null if nothing was
/// imported.
class MasterImportDialog extends StatefulWidget {
  const MasterImportDialog({
    super.key,
    required this.noun,
    required this.fileStem,
    required this.downloadTemplate,
    required this.checkFile,
    required this.canUpdate,
    this.mappingApi,
    this.mappingKind,
    this.offersUpdate = true,
    this.csvOnly = false,
    this.extraFields,
    this.pickFileOverride,
    this.saveBytesOverride,
  });

  /// Plural, lower case: "products", "customers".
  final String noun;

  /// Singular, used in suggested file names: "product" gives
  /// `product_import_template.xlsx`.
  final String fileStem;

  /// Fetches the blank template in `xlsx` or `csv`.
  final Future<List<int>> Function(String format) downloadTemplate;

  /// Checks (`apply: false`) or imports a file.
  final Future<FileImportReport> Function({
    required String fileName,
    required List<int> bytes,
    required bool updateExisting,
    required bool apply,
    Map<String, String?>? mapping,
  }) checkFile;

  /// Whether the user may update existing records.
  final bool canUpdate;

  /// Where the mapping step (B3) reads a file's headings and saved mappings,
  /// and the import's kind there. Without both the step is not offered and the
  /// file is read as before.
  final ApiClient? mappingApi;
  final String? mappingKind;

  /// Whether "update existing" means anything for this import at all. Opening
  /// stock is posted once, so it has nothing to update and hides the option.
  final bool offersUpdate;

  /// The server's template is a CSV only (price revisions): the Excel
  /// template button is not offered.
  final bool csvOnly;

  /// Fields the import needs besides the file -- the posting date of opening
  /// stock -- shown under the file. The owner keeps their values and reads
  /// them in [checkFile]; it calls `changed` whenever one changes, which
  /// discards the last check so Import is offered only for what was checked.
  final Widget Function(BuildContext context, VoidCallback changed)?
      extraFields;

  /// Injected by tests, which cannot open a native file dialog.
  final Future<XFile?> Function()? pickFileOverride;

  /// Injected by tests, which cannot open a native save dialog.
  final SaveBytesOverride? saveBytesOverride;

  @override
  State<MasterImportDialog> createState() => _MasterImportDialogState();
}

class _MasterImportDialogState extends State<MasterImportDialog> {
  String? _fileName;
  List<int>? _bytes;
  bool _updateExisting = false;
  bool _busy = false;
  String? _error;
  String? _notice;

  /// The mapping step's answer: what to send (null reads the file as before),
  /// whether it is unusable, and whether the preview is still on its way.
  Map<String, String?>? _mapping;
  bool _mappingBlocked = false;
  bool _mappingLoading = false;
  int _fileSerial = 0;

  bool get _mapped => widget.mappingApi != null && widget.mappingKind != null;

  /// The last check, and the checkbox value it was made with.
  FileImportReport? _report;
  bool _checkedWithUpdate = false;

  bool get _canUpdate => widget.canUpdate;

  /// Import only after a clean check of this file with this choice.
  bool get _canImport =>
      !_busy &&
      _bytes != null &&
      !_mappingLoading &&
      !_mappingBlocked &&
      _report != null &&
      _report!.isClean &&
      _report!.rows > 0 &&
      _checkedWithUpdate == _updateExisting;

  void _extraChanged() {
    if (!mounted) return;
    setState(() {
      _report = null;
      _notice = null;
    });
  }

  void _mappingChanged({
    required Map<String, String?>? mapping,
    required bool blocked,
    required bool loading,
  }) {
    if (!mounted) return;
    setState(() {
      _mapping = mapping;
      _mappingBlocked = blocked;
      _mappingLoading = loading;
      _report = null;
      _notice = null;
    });
  }

  Future<void> _save(String name, List<int> bytes) async {
    if (widget.saveBytesOverride != null) {
      await widget.saveBytesOverride!(name, bytes);
      return;
    }
    final FileSaveLocation? location =
        await getSaveLocation(suggestedName: name);
    if (location == null) return;
    await File(location.path).writeAsBytes(bytes, flush: true);
    if (mounted) setState(() => _notice = 'Saved to ${location.path}.');
  }

  Future<void> _template(String format) async {
    setState(() {
      _busy = true;
      _error = null;
      _notice = null;
    });
    try {
      final List<int> bytes = await widget.downloadTemplate(format);
      await _save('${widget.fileStem}_import_template.$format', bytes);
    } on ApiException catch (error) {
      if (mounted) setState(() => _error = error.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _pick() async {
    final XFile? picked = widget.pickFileOverride != null
        ? await widget.pickFileOverride!()
        : await openFile(
            acceptedTypeGroups: const [
              XTypeGroup(label: 'Spreadsheet', extensions: ['csv', 'xlsx']),
            ],
            confirmButtonText: 'Select ${widget.fileStem} file',
          );
    if (picked == null) return;
    final List<int> bytes = await picked.readAsBytes();
    if (!mounted) return;
    setState(() {
      _fileName = picked.name;
      _bytes = bytes;
      _fileSerial++;
      _mapping = null;
      _mappingBlocked = false;
      _mappingLoading = _mapped;
      _report = null;
      _error = null;
      _notice = null;
    });
  }

  Future<void> _run({required bool apply}) async {
    final List<int>? bytes = _bytes;
    final String? name = _fileName;
    if (bytes == null || name == null) return;
    setState(() {
      _busy = true;
      _error = null;
      _notice = null;
    });
    final bool update = _updateExisting;
    try {
      final FileImportReport report = await widget.checkFile(
        fileName: name,
        bytes: bytes,
        updateExisting: update,
        apply: apply,
        mapping: _mapping,
      );
      if (!mounted) return;
      if (apply && report.imported) {
        Navigator.of(context).pop(report);
        return;
      }
      setState(() {
        _report = report;
        _checkedWithUpdate = update;
        _busy = false;
        if (apply) {
          _notice = 'Nothing was imported. Fix the problems and check again.';
        }
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.message;
        _busy = false;
      });
    }
  }

  Future<void> _saveProblems() async {
    final FileImportReport? report = _report;
    if (report == null) return;
    await _save(
      '${widget.fileStem}_import_problems.csv',
      utf8.encode(importProblemsCsv(report.issues)),
    );
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final FileImportReport? report = _report;
    return AlertDialog(
      icon: const Icon(Icons.upload_file_outlined),
      title: Text('Import ${widget.noun}'),
      content: SizedBox(
        width: 620,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                '1. Download the template, fill it in, keep the header row.',
                style: theme.textTheme.bodyMedium,
              ),
              const SizedBox(height: AppSpacing.sm),
              Wrap(
                spacing: AppSpacing.md,
                runSpacing: AppSpacing.sm,
                children: [
                  if (!widget.csvOnly)
                    OutlinedButton.icon(
                      onPressed: _busy ? null : () => _template('xlsx'),
                      icon: const Icon(Icons.download_outlined),
                      label: const Text('Template (Excel)'),
                    ),
                  OutlinedButton.icon(
                    onPressed: _busy ? null : () => _template('csv'),
                    icon: const Icon(Icons.download_outlined),
                    label: const Text('Template (CSV)'),
                  ),
                ],
              ),
              const SizedBox(height: AppSpacing.lg),
              Text('2. Choose the file.', style: theme.textTheme.bodyMedium),
              const SizedBox(height: AppSpacing.sm),
              Row(
                children: [
                  OutlinedButton.icon(
                    onPressed: _busy ? null : _pick,
                    icon: const Icon(Icons.folder_open_outlined),
                    label: const Text('Choose file…'),
                  ),
                  const SizedBox(width: AppSpacing.md),
                  if (_fileName != null)
                    Expanded(
                      child: Text(
                        _fileName!,
                        overflow: TextOverflow.ellipsis,
                        style: theme.textTheme.bodyMedium,
                      ),
                    ),
                ],
              ),
              if (_mapped && _bytes != null) ...[
                const SizedBox(height: AppSpacing.md),
                ImportMappingPanel(
                  key: ValueKey<int>(_fileSerial),
                  api: widget.mappingApi!,
                  kind: widget.mappingKind!,
                  fileName: _fileName!,
                  bytes: _bytes!,
                  onChanged: _mappingChanged,
                ),
              ],
              if (widget.extraFields != null) ...[
                const SizedBox(height: AppSpacing.md),
                widget.extraFields!(context, _extraChanged),
              ],
              const SizedBox(height: AppSpacing.sm),
              if (widget.offersUpdate)
                CheckboxListTile(
                  contentPadding: EdgeInsets.zero,
                  controlAffinity: ListTileControlAffinity.leading,
                  dense: true,
                  value: _updateExisting && _canUpdate,
                  onChanged: _busy || !_canUpdate
                      ? null
                      : (value) =>
                          setState(() => _updateExisting = value == true),
                  title: Text(
                    'Update ${widget.noun} that already exist (matched by code)',
                  ),
                  subtitle: _canUpdate
                      ? null
                      : Text(
                          'You do not have permission to update ${widget.noun}.',
                        ),
                ),
              const SizedBox(height: AppSpacing.sm),
              Text('3. Check the file.', style: theme.textTheme.bodyMedium),
              const SizedBox(height: AppSpacing.sm),
              Align(
                alignment: Alignment.centerLeft,
                child: FilledButton.tonalIcon(
                  onPressed: _busy ||
                          _bytes == null ||
                          _mappingLoading ||
                          _mappingBlocked
                      ? null
                      : () => _run(apply: false),
                  icon: const Icon(Icons.rule_folder_outlined),
                  label: const Text('Check file'),
                ),
              ),
              if (report != null) ...[
                const SizedBox(height: AppSpacing.lg),
                SelectableText(
                  widget.offersUpdate
                      ? '${report.rows} rows: ${report.toCreate} new, '
                          '${report.toUpdate} to update.'
                      : '${report.rows} rows to import.',
                  style: theme.textTheme.titleSmall,
                ),
                if (report.columnsUsed.isNotEmpty)
                  SelectableText(
                    'Columns used: ${report.columnsUsed.join(', ')}',
                    style: theme.textTheme.bodySmall,
                  ),
                if (report.columnsIgnored.isNotEmpty)
                  SelectableText(
                    'Columns ignored: ${report.columnsIgnored.join(', ')}',
                    style: theme.textTheme.bodySmall,
                  ),
                const SizedBox(height: AppSpacing.sm),
                if (report.isClean)
                  Text(
                    'No problems found.',
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  )
                else ...[
                  Text(
                    '${report.issues.length} problems. Nothing is written '
                    'until the file is clean.',
                    style: theme.textTheme.bodySmall
                        ?.copyWith(color: theme.colorScheme.error),
                  ),
                  const SizedBox(height: AppSpacing.xs),
                  ConstrainedBox(
                    constraints: const BoxConstraints(maxHeight: 200),
                    child: ListView.builder(
                      shrinkWrap: true,
                      itemCount: report.issues.length,
                      itemBuilder: (context, index) => Padding(
                        padding:
                            const EdgeInsets.symmetric(vertical: AppSpacing.xs),
                        child: SelectableText(
                          report.issues[index].text,
                          style: theme.textTheme.bodySmall
                              ?.copyWith(color: theme.colorScheme.error),
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(height: AppSpacing.sm),
                  Align(
                    alignment: Alignment.centerLeft,
                    child: OutlinedButton.icon(
                      onPressed: _busy ? null : _saveProblems,
                      icon: const Icon(Icons.download_outlined),
                      label: const Text('Save problems…'),
                    ),
                  ),
                ],
              ],
              if (_notice != null) ...[
                const SizedBox(height: AppSpacing.lg),
                CopyableMessage(message: _notice!),
              ],
              if (_error != null) ...[
                const SizedBox(height: AppSpacing.lg),
                CopyableMessage(message: _error!, isError: true),
              ],
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: _busy ? null : () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: _canImport ? () => _run(apply: true) : null,
          child: Text(_busy ? 'Working…' : 'Import'),
        ),
      ],
    );
  }
}
