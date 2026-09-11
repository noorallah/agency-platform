import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../models/branch_warehouse.dart' show BranchRecord;
import '../../models/entities.dart';
import '../inventory/inventory_import_wizard.dart'
    show InventoryImportFileParser;
import '../workspace/desktop_framework.dart'
    show CopyableMessage, ImportSample, ImportSampleButton, SaveSampleOverride;

/// Which master the dialog is importing.
enum BranchImportTarget { branches, warehouses }

/// One column the importer reads, whether a row is useless without it, and
/// the value the sample file shows in it.
///
/// The example lives on the column so the sample cannot list a heading the
/// parser does not read, or read one the sample does not show.
class _Column {
  const _Column(
    this.header,
    this.field, {
    this.required = false,
    this.example = '',
  });

  final String header;
  final String field;
  final bool required;
  final String example;
}

const List<_Column> _branchColumns = [
  _Column('code', 'code', required: true, example: 'BR_NORTH'),
  _Column('name', 'name', required: true, example: 'North Branch'),
  _Column('display_name', 'display_name', example: 'North'),
  _Column('description', 'description', example: 'Northern region branch'),
  _Column('email', 'email', example: 'north@example.com'),
  // E.164, which is what the server accepts: a bare local number is refused.
  _Column('phone', 'phone', example: '+912212345678'),
  _Column('mobile', 'mobile', example: '+919876543210'),
  _Column('address_line1', 'address_line1', example: '12 Ring Road'),
  _Column('address_line2', 'address_line2', example: 'Sector 4'),
  _Column('currency_code', 'currency_code', example: 'INR'),
  _Column('status', 'status', example: 'ACTIVE'),
];

/// The example branch code when the firm's own could not be read.
const String _fallbackBranchCode = 'HO';

const List<_Column> _warehouseColumns = [
  // A code, never an id: nothing on a screen shows a person an id. The
  // server resolves it within the firm and refuses an unknown one by name.
  // The example is replaced with the firm's first real branch code when the
  // dialog opens, so the sample imports as it is.
  _Column(
    'branch_code',
    'branch_code',
    required: true,
    example: _fallbackBranchCode,
  ),
  _Column('code', 'code', required: true, example: 'WH_NORTH'),
  _Column('name', 'name', required: true, example: 'North Warehouse'),
  _Column('display_name', 'display_name', example: 'North WH'),
  _Column('description', 'description', example: 'Main store for the north'),
  _Column('address_line1', 'address_line1', example: '12 Ring Road'),
  _Column('address_line2', 'address_line2', example: 'Sector 4'),
  _Column('capacity', 'capacity', example: '5000'),
  _Column('capacity_unit', 'capacity_unit', example: 'SQFT'),
  _Column('status', 'status', example: 'ACTIVE'),
];

/// A heading as `InventoryImportFileParser` keys it: lower-case, letters and
/// digits only.
String _headerKey(String header) =>
    header.toLowerCase().replaceAll(RegExp(r'[^a-z0-9]'), '');

/// The sample file for one target: its headings and one example row.
///
/// [branchCode] is the firm's own branch code to show in a warehouse sample,
/// so the file imports without editing; the fallback is a guess.
ImportSample branchImportSample(
  BranchImportTarget target, {
  String branchCode = _fallbackBranchCode,
}) {
  final List<_Column> columns = switch (target) {
    BranchImportTarget.branches => _branchColumns,
    BranchImportTarget.warehouses => _warehouseColumns,
  };
  return ImportSample(
    fileName: '${target.name}_sample.csv',
    columns: [for (final _Column column in columns) column.header],
    example: [
      for (final _Column column in columns)
        column.header == 'branch_code' ? branchCode : column.example,
    ],
  );
}

/// Turn a server refusal into the sentence the dialog shows.
///
/// A validation refusal arrives as "The request validation failed." with the
/// detail in `details` -- `records.4.branch_code` and a message -- which is
/// the one part the person needs. Rendered per row, numbered as the
/// spreadsheet numbers them (the header is row 1).
String importRefusalMessage(ApiException error) {
  final Object? details = error.details;
  final List<String> lines = <String>[];
  if (details is List) {
    for (final Object? item in details) {
      if (item is! Map) continue;
      final String field = '${item['field'] ?? ''}';
      final String message = '${item['message'] ?? ''}';
      // `body.records.4.branch_code` for a field; `body.records.4` alone for
      // a rule about the whole row, such as "name the branch one way or the
      // other".
      final RegExpMatch? at =
          RegExp(r'records\.(\d+)(?:\.(.+))?$').firstMatch(field);
      if (at != null) {
        final int row = int.parse(at.group(1)!) + 2;
        final String? name = at.group(2);
        lines.add(name == null ? 'Row $row: $message' : 'Row $row: $name — $message');
      } else if (message.isNotEmpty) {
        lines.add(field.isEmpty ? message : '$field — $message');
      }
    }
  }
  final String detail = lines.isEmpty ? error.message : lines.join('\n');
  return '$detail Nothing was imported — fix the file and try again.';
}

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
    this.saveSampleOverride,
  });

  final ApiClient api;
  final BranchImportTarget target;

  /// Injected by tests, which cannot open a native file dialog.
  final Future<XFile?> Function()? pickFileOverride;

  /// Injected by tests, which cannot open a native save dialog either.
  final SaveSampleOverride? saveSampleOverride;

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
  bool _sampleSaved = false;

  /// The firm's first branch code, for the warehouse sample's example row.
  String _branchCode = _fallbackBranchCode;

  @override
  void initState() {
    super.initState();
    if (widget.target == BranchImportTarget.warehouses) {
      _loadBranchCode();
    }
  }

  Future<void> _loadBranchCode() async {
    try {
      final PagedResult<BranchRecord> page = await widget.api.branches(
        pageSize: 1,
        sortBy: 'code',
        descending: false,
      );
      if (!mounted || page.items.isEmpty) return;
      setState(() => _branchCode = page.items.first.code);
    } on ApiException {
      // The fallback stays; the sample is still a valid file to edit.
    }
  }

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
        // The parser normalises every heading to lower-case letters and
        // digits, so `display_name` arrives as `displayname`. Reading the
        // heading as written matched only the single-word columns, and the
        // rest -- branch_id among them, which is required -- were silently
        // dropped from every file until 2026-09-11.
        final String value = (source[_headerKey(column.header)] ?? '').trim();
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
        _error = importRefusalMessage(error);
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
              SelectableText(
                'CSV or XLSX with a header row. Columns: '
                '${_columns.map((column) => column.header).join(', ')}. '
                'Required: '
                '${_columns.where((c) => c.required).map((c) => c.header).join(', ')}. '
                'Sample file gives the headings and one example row.',
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
                  ImportSampleButton(
                    sample: branchImportSample(
                      widget.target,
                      branchCode: _branchCode,
                    ),
                    enabled: !_busy,
                    saveOverride: widget.saveSampleOverride,
                    onSaved: () {
                      if (mounted) setState(() => _sampleSaved = true);
                    },
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
              if (_sampleSaved) ...[
                const SizedBox(height: AppSpacing.sm),
                Text(
                  'Sample saved. Fill it in, keep the header row, and choose it '
                  'here.',
                  style: theme.textTheme.bodySmall,
                ),
              ],
              if (_rows.isNotEmpty) ...[
                const SizedBox(height: AppSpacing.lg),
                SelectableText(
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
                CopyableMessage(message: 'Imported $imported $_noun.'),
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
          child: SelectableText(
            'Row ${row.number}: ${row.errors.join('; ')}',
            style: theme.textTheme.bodySmall
                ?.copyWith(color: theme.colorScheme.error),
          ),
        );
      },
    );
  }
}
