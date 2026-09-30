import 'dart:convert';
import 'dart:io';

import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/security/permission_service.dart';
import '../../models/product_import.dart';
import '../workspace/desktop_framework.dart';

/// How bytes are written to disk. Tests inject one, because a widget test
/// cannot open a native save dialog.
typedef SaveBytesOverride = Future<void> Function(
  String suggestedName,
  List<int> bytes,
);

/// The problems list as a CSV a person can fix the file from.
String productImportProblemsCsv(List<ProductImportIssue> issues) {
  String quote(String value) => '"${value.replaceAll('"', '""')}"';
  final StringBuffer buffer = StringBuffer('Row,Code,Column,Problem\r\n');
  for (final ProductImportIssue issue in issues) {
    buffer.write(
      '${issue.row},${quote(issue.code ?? '')},${quote(issue.column ?? '')},'
      '${quote(issue.message)}\r\n',
    );
  }
  return buffer.toString();
}

/// Load products from a CSV or XLSX file.
///
/// The server does the checking. A check writes nothing; Import is offered only
/// after a clean check of the file as it now stands, with the same choice about
/// existing products, and the server writes the whole file or none of it.
/// Closes with the applied [ProductImportReport], or null if nothing was
/// imported.
class ProductImportDialog extends StatefulWidget {
  const ProductImportDialog({
    super.key,
    required this.api,
    required this.permissions,
    this.pickFileOverride,
    this.saveBytesOverride,
  });

  final ApiClient api;
  final PermissionService permissions;

  /// Injected by tests, which cannot open a native file dialog.
  final Future<XFile?> Function()? pickFileOverride;

  /// Injected by tests, which cannot open a native save dialog.
  final SaveBytesOverride? saveBytesOverride;

  @override
  State<ProductImportDialog> createState() => _ProductImportDialogState();
}

class _ProductImportDialogState extends State<ProductImportDialog> {
  String? _fileName;
  List<int>? _bytes;
  bool _updateExisting = false;
  bool _busy = false;
  String? _error;
  String? _notice;

  /// The last check, and the checkbox value it was made with.
  ProductImportReport? _report;
  bool _checkedWithUpdate = false;

  bool get _canUpdate => widget.permissions.hasPermission('PRODUCT_UPDATE');

  /// Import only after a clean check of this file with this choice.
  bool get _canImport =>
      !_busy &&
      _bytes != null &&
      _report != null &&
      _report!.isClean &&
      _report!.rows > 0 &&
      _checkedWithUpdate == _updateExisting;

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
      final List<int> bytes =
          await widget.api.productImportTemplate(format: format);
      await _save('product_import_template.$format', bytes);
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
            confirmButtonText: 'Select product file',
          );
    if (picked == null) return;
    final List<int> bytes = await picked.readAsBytes();
    if (!mounted) return;
    setState(() {
      _fileName = picked.name;
      _bytes = bytes;
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
      final ProductImportReport report = await widget.api.checkProductImportFile(
        fileName: name,
        bytes: bytes,
        updateExisting: update,
        apply: apply,
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
    final ProductImportReport? report = _report;
    if (report == null) return;
    await _save(
      'product_import_problems.csv',
      utf8.encode(productImportProblemsCsv(report.issues)),
    );
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final ProductImportReport? report = _report;
    return AlertDialog(
      icon: const Icon(Icons.upload_file_outlined),
      title: const Text('Import products'),
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
              const SizedBox(height: AppSpacing.sm),
              CheckboxListTile(
                contentPadding: EdgeInsets.zero,
                controlAffinity: ListTileControlAffinity.leading,
                dense: true,
                value: _updateExisting && _canUpdate,
                onChanged: _busy || !_canUpdate
                    ? null
                    : (value) => setState(() => _updateExisting = value == true),
                title: const Text(
                  'Update products that already exist (matched by code)',
                ),
                subtitle: _canUpdate
                    ? null
                    : const Text('You do not have permission to update products.'),
              ),
              const SizedBox(height: AppSpacing.sm),
              Text('3. Check the file.', style: theme.textTheme.bodyMedium),
              const SizedBox(height: AppSpacing.sm),
              Align(
                alignment: Alignment.centerLeft,
                child: FilledButton.tonalIcon(
                  onPressed:
                      _busy || _bytes == null ? null : () => _run(apply: false),
                  icon: const Icon(Icons.rule_folder_outlined),
                  label: const Text('Check file'),
                ),
              ),
              if (report != null) ...[
                const SizedBox(height: AppSpacing.lg),
                SelectableText(
                  '${report.rows} rows: ${report.toCreate} new, '
                  '${report.toUpdate} to update.',
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
