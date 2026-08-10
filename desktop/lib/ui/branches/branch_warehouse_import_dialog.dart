import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../models/entities.dart';
import '../inventory/inventory_import_wizard.dart'
    show InventoryImportFileParser;

/// Which master the dialog is importing.
enum BranchImportTarget { branches, warehouses }

/// One column the importer reads, and whether a row is useless without it.
class _Column {
  const _Column(this.header, this.field, {this.required = false});

  final String header;
  final String field;
  final bool required;
}

const List<_Column> _branchColumns = [
  _Column('code', 'code', required: true),
  _Column('name', 'name', required: true),
  _Column('display_name', 'display_name'),
  _Column('description', 'description'),
  _Column('email', 'email'),
  _Column('phone', 'phone'),
  _Column('mobile', 'mobile'),
  _Column('address_line1', 'address_line1'),
  _Column('address_line2', 'address_line2'),
  _Column('currency_code', 'currency_code'),
  _Column('status', 'status'),
];

const List<_Column> _warehouseColumns = [
  _Column('branch_id', 'branch_id', required: true),
  _Column('code', 'code', required: true),
  _Column('name', 'name', required: true),
  _Column('display_name', 'display_name'),
  _Column('description', 'description'),
  _Column('address_line1', 'address_line1'),
  _Column('address_line2', 'address_line2'),
  _Column('capacity', 'capacity'),
  _Column('capacity_unit', 'capacity_unit'),
  _Column('status', 'status'),
];

/// One parsed row, with whatever is wrong with it.
class _Row {
  _Row({required this.number, required this.values, required this.errors});

  final int number;
  final Json values;
  final List<String> errors;

  bool get isValid => errors.isEmpty;
}

/// Load branches or warehouses from a spreadsheet.
///
/// The server writes the batch in one transaction, so this dialog can promise
/// something a per-row importer cannot: a refused import leaves nothing behind,
/// and the corrected file can simply be sent again. Rows are still validated
/// here first, because a round trip that fails on row 400 wastes the user's
/// time when the file could have been checked before sending.
class BranchWarehouseImportDialog extends StatefulWidget {
  const BranchWarehouseImportDialog({
    super.key,
    required this.api,
    required this.target,
    this.pickFileOverride,
  });

  final ApiClient api;
  final BranchImportTarget target;

  /// Injected by tests, which cannot open a native file dialog.
  final Future<XFile?> Function()? pickFileOverride;

  @override
  State<BranchWarehouseImportDialog> createState() =>
      _BranchWarehouseImportDialogState();
}

class _BranchWarehouseImportDialogState
    extends State<BranchWarehouseImportDialog> {
  String? _fileName;
  List<_Row> _rows = const [];
  String? _error;
  bool _busy = false;
  int? _imported;

  List<_Column> get _columns => switch (widget.target) {
        BranchImportTarget.branches => _branchColumns,
        BranchImportTarget.warehouses => _warehouseColumns,
      };

  String get _noun => switch (widget.target) {
        BranchImportTarget.branches => 'branches',
        BranchImportTarget.warehouses => 'warehouses',
      };

  int get _validCount => _rows.where((row) => row.isValid).length;

  bool get _canImport =>
      !_busy && _rows.isNotEmpty && _validCount == _rows.length;

  Future<void> _pick() async {
    final XFile? picked = widget.pickFileOverride != null
        ? await widget.pickFileOverride!()
        : await openFile(
            acceptedTypeGroups: const [
              XTypeGroup(label: 'Spreadsheet', extensions: ['csv', 'xlsx']),
            ],
            confirmButtonText: 'Select import file',
          );
    if (picked == null) return;
    final List<int> bytes = await picked.readAsBytes();
    if (!mounted) return;
    setState(() {
      _fileName = picked.name;
      _imported = null;
      _error = null;
      try {
        _rows = _parse(
          InventoryImportFileParser.parseBytes(
            fileName: picked.name,
            bytes: bytes,
          ),
        );
        if (_rows.isEmpty) {
          _error = 'That file has no data rows.';
        }
      } on Exception catch (error) {
        _rows = const [];
        _error = 'Could not read that file: $error';
      }
    });
  }

  List<_Row> _parse(List<Map<String, String>> raw) {
    final List<_Row> rows = [];
    for (int index = 0; index < raw.length; index++) {
      final Map<String, String> source = raw[index];
      final Json values = <String, dynamic>{};
      final List<String> errors = [];
      for (final _Column column in _columns) {
        final String value = (source[column.header] ?? '').trim();
        if (value.isEmpty) {
          if (column.required) {
            errors.add('${column.header} is required');
          }
          continue;
        }
        values[column.field] = value;
      }
      // Mirrors the server's pattern so a doomed file is caught before sending.
      final Object? code = values['code'];
      if (code is String && !RegExp(r'^[A-Z0-9_-]{2,50}$').hasMatch(code)) {
        errors.add('code must be 2-50 upper-case letters, digits, _ or -');
      }
      rows.add(_Row(number: index + 2, values: values, errors: errors));
    }
    return rows;
  }

  Future<void> _import() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    final List<Json> records = _rows.map((row) => row.values).toList();
    try {
      final int count = switch (widget.target) {
        BranchImportTarget.branches =>
          (await widget.api.importBranches(records)).length,
        BranchImportTarget.warehouses =>
          (await widget.api.importWarehouses(records)).length,
      };
      if (!mounted) return;
      setState(() {
        _imported = count;
        _busy = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        // Worth saying explicitly: the user's next question is always whether
        // half of it went in.
        _error = '${error.message} Nothing was imported — fix the file and '
            'try again.';
        _busy = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final int imported = _imported ?? -1;
    return AlertDialog(
      icon: const Icon(Icons.upload_file_outlined),
      title: Text('Import $_noun'),
      // Scrollable: the issue list grows with the file, and an AlertDialog
      // gives its content whatever height is left rather than a fixed one.
      content: SizedBox(
        width: 620,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                'CSV or XLSX with a header row. Columns: '
                '${_columns.map((column) => column.header).join(', ')}. '
                'Required: '
                '${_columns.where((c) => c.required).map((c) => c.header).join(', ')}.',
                style: theme.textTheme.bodySmall,
              ),
              const SizedBox(height: AppSpacing.lg),
              Row(
                children: [
                  OutlinedButton.icon(
                    onPressed: _busy ? null : _pick,
                    icon: const Icon(Icons.folder_open_outlined),
                    label: Text(
                        _fileName == null ? 'Choose file' : 'Choose another'),
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
              if (_rows.isNotEmpty) ...[
                const SizedBox(height: AppSpacing.lg),
                Text(
                  _validCount == _rows.length
                      ? '${_rows.length} rows ready.'
                      : '$_validCount of ${_rows.length} rows are usable. '
                          'Every row must be valid before anything is sent.',
                  style: theme.textTheme.bodyMedium,
                ),
                const SizedBox(height: AppSpacing.sm),
                ConstrainedBox(
                  constraints: const BoxConstraints(maxHeight: 220),
                  child: _RowIssues(rows: _rows),
                ),
              ],
              if (imported >= 0) ...[
                const SizedBox(height: AppSpacing.lg),
                Text(
                  'Imported $imported $_noun.',
                  style: theme.textTheme.bodyMedium,
                ),
              ],
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
        TextButton(
          onPressed:
              _busy ? null : () => Navigator.of(context).pop(imported >= 0),
          child: Text(imported >= 0 ? 'Close' : 'Cancel'),
        ),
        FilledButton(
          onPressed: _canImport && imported < 0 ? _import : null,
          child: Text(_busy ? 'Importing…' : 'Import'),
        ),
      ],
    );
  }
}

/// List the rows that cannot be sent, and why.
class _RowIssues extends StatelessWidget {
  const _RowIssues({required this.rows});

  final List<_Row> rows;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final List<_Row> bad = rows.where((row) => !row.isValid).toList();
    if (bad.isEmpty) {
      return Align(
        alignment: Alignment.centerLeft,
        child: Text(
          'No problems found.',
          style: theme.textTheme.bodySmall
              ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
        ),
      );
    }
    return ListView.builder(
      shrinkWrap: true,
      itemCount: bad.length,
      itemBuilder: (context, index) {
        final _Row row = bad[index];
        return Padding(
          padding: const EdgeInsets.symmetric(vertical: AppSpacing.xs),
          child: Text(
            'Row ${row.number}: ${row.errors.join('; ')}',
            style: theme.textTheme.bodySmall
                ?.copyWith(color: theme.colorScheme.error),
          ),
        );
      },
    );
  }
}
