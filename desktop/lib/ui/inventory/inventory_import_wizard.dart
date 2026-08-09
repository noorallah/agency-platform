import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:csv/csv.dart';
import 'package:desktop_drop/desktop_drop.dart';
import 'package:excel/excel.dart' as xls;
import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/preferences/desktop_preferences_service.dart';
import '../../models/branch_warehouse.dart';
import '../../models/entities.dart';
import '../../models/inventory.dart';
import '../../models/product.dart';
import '../workspace/desktop_framework.dart';

enum InventoryImportType {
  openingStock,
  inventoryUpdate,
  inventoryAdjustment,
}

class InventoryImportWizardController {
  _InventoryImportWizardState? _state;

  Future<void> loadPreparedFile(String name, List<int> bytes) {
    final _InventoryImportWizardState? state = _state;
    if (state == null) {
      return Future<void>.error(
        StateError('Inventory import wizard is not attached.'),
      );
    }
    return state._loadPreparedFile(name, bytes);
  }

  Future<void> runImport() {
    final _InventoryImportWizardState? state = _state;
    if (state == null) {
      return Future<void>.error(
        StateError('Inventory import wizard is not attached.'),
      );
    }
    return state._runImport();
  }

  void cancelImport() {
    _state?._requestCancel();
  }

  bool get canImport => _state?._preview?.canImport == true;

  List<String> get validationIssues => _state?._preview?.rows
          .expand((row) => row.errors)
          .toSet()
          .toList(growable: false) ??
      const <String>[];

  void _attach(_InventoryImportWizardState state) {
    _state = state;
  }

  void _detach(_InventoryImportWizardState state) {
    if (identical(_state, state)) {
      _state = null;
    }
  }
}

class InventoryImportFileParser {
  const InventoryImportFileParser._();

  static List<Map<String, String>> parseBytes({
    required String fileName,
    required List<int> bytes,
  }) {
    final String extension = _extension(fileName).toLowerCase();
    if (extension == 'csv') {
      final String text = utf8.decode(bytes);
      final List<List<dynamic>> values =
          const CsvDecoder(dynamicTyping: false).convert(text);
      return _rowsFromMatrix(values);
    }
    if (extension == 'xlsx') {
      final xls.Excel excel = xls.Excel.decodeBytes(bytes);
      if (excel.tables.isEmpty) {
        return const [];
      }
      final xls.Sheet sheet = excel.tables.values.first;
      final List<List<dynamic>> values = sheet.rows
          .map(
            (row) => row
                .map((cell) => cell?.value?.toString() ?? '')
                .toList(growable: false),
          )
          .toList(growable: false);
      return _rowsFromMatrix(values);
    }
    throw UnsupportedError('Only CSV and XLSX files are supported.');
  }

  static List<Map<String, String>> _rowsFromMatrix(List<List<dynamic>> matrix) {
    if (matrix.isEmpty) return const [];
    final List<String> headers = matrix.first
        .map((value) => _normalizeHeader(value?.toString() ?? ''))
        .toList(growable: false);
    final List<Map<String, String>> rows = [];
    for (final List<dynamic> row in matrix.skip(1)) {
      if (row.every((value) => (value?.toString() ?? '').trim().isEmpty)) {
        continue;
      }
      final Map<String, String> mapped = <String, String>{};
      for (int index = 0; index < headers.length; index++) {
        final String header = headers[index];
        if (header.isEmpty) continue;
        mapped[header] =
            index < row.length ? (row[index]?.toString() ?? '').trim() : '';
      }
      rows.add(mapped);
    }
    return rows;
  }
}

extension InventoryImportTypeDetails on InventoryImportType {
  String get label => switch (this) {
        InventoryImportType.openingStock => 'Opening Stock',
        InventoryImportType.inventoryUpdate => 'Inventory Update',
        InventoryImportType.inventoryAdjustment => 'Inventory Adjustment',
      };

  String get description => switch (this) {
        InventoryImportType.openingStock =>
          'Create opening stock batches from grouped inventory rows.',
        InventoryImportType.inventoryUpdate =>
          'Bulk update inventory thresholds and status.',
        InventoryImportType.inventoryAdjustment =>
          'Post multiple inventory adjustments with validation and retry support.',
      };
}

class InventoryImportWizard extends StatefulWidget {
  const InventoryImportWizard({
    super.key,
    required this.api,
    required this.preferences,
    required this.branches,
    required this.warehouses,
    required this.products,
    required this.onViewImportedRecords,
    this.initialType,
    this.controller,
    this.initialFileBytes,
    this.initialFileName,
    this.pickFileOverride,
    this.saveTextOverride,
  });

  final ApiClient api;
  final DesktopPreferencesService preferences;
  final List<BranchRecord> branches;
  final List<WarehouseRecord> warehouses;
  final List<Product> products;
  final Future<void> Function(InventoryImportType type) onViewImportedRecords;
  final InventoryImportType? initialType;
  final InventoryImportWizardController? controller;
  final List<int>? initialFileBytes;
  final String? initialFileName;
  final Future<XFile?> Function(String? initialDirectory)? pickFileOverride;
  final Future<void> Function(String suggestedName, String content)? saveTextOverride;

  @override
  State<InventoryImportWizard> createState() => _InventoryImportWizardState();
}

class _InventoryImportWizardState extends State<InventoryImportWizard> {
  static const String _preferencesKey = 'inventory_import_wizard';
  static const List<XTypeGroup> _acceptedTypes = [
    XTypeGroup(
      label: 'Inventory import files',
      extensions: ['csv', 'xlsx'],
    ),
  ];

  InventoryImportType _type = InventoryImportType.openingStock;
  int _step = 0;
  bool _busy = false;
  bool _dragging = false;
  bool _cancelRequested = false;
  String? _error;
  _ImportFileSelection? _file;
  _InventoryImportPreview? _preview;
  _InventoryImportExecution? _execution;
  final TextEditingController _referencePrefix = TextEditingController(
    text: 'OPEN',
  );
  final TextEditingController _defaultPostingDate = TextEditingController(
    text: DateTime.now().toIso8601String().split('T').first,
  );
  bool _autoPostOpeningStock = true;
  String? _lastDirectory;
  final Set<String> _successfulSignatures = <String>{};

  @override
  void initState() {
    super.initState();
    widget.controller?._attach(this);
    _loadPreferences();
    if (widget.initialType != null) {
      _type = widget.initialType!;
    }
    if (widget.initialFileBytes != null &&
        widget.initialFileName?.trim().isNotEmpty == true) {
      unawaited(
        _loadPreparedFile(
          widget.initialFileName!.trim(),
          widget.initialFileBytes!,
        ),
      );
    }
  }

  @override
  void dispose() {
    widget.controller?._detach(this);
    _referencePrefix.dispose();
    _defaultPostingDate.dispose();
    super.dispose();
  }

  void _loadPreferences() {
    final Map<String, dynamic> raw =
        widget.preferences.current.serverPreferences[_preferencesKey] is Map
            ? Map<String, dynamic>.from(
                widget.preferences.current.serverPreferences[_preferencesKey]
                    as Map,
              )
            : const {};
    _lastDirectory = stringValue(raw['last_directory']).isEmpty
        ? null
        : stringValue(raw['last_directory']);
    _referencePrefix.text = stringValue(raw['reference_prefix']).isEmpty
        ? 'OPEN'
        : stringValue(raw['reference_prefix']);
    _defaultPostingDate.text = stringValue(raw['default_posting_date']).isEmpty
        ? DateTime.now().toIso8601String().split('T').first
        : stringValue(raw['default_posting_date']);
    _autoPostOpeningStock = boolValue(raw['auto_post_opening_stock'], fallback: true);
    _successfulSignatures.addAll(stringList(raw['successful_signatures']));
    final String savedType = stringValue(raw['last_type']);
    _type = InventoryImportType.values.firstWhere(
      (value) => value.name == savedType,
      orElse: () => InventoryImportType.openingStock,
    );
  }

  Future<void> _persistPreferences() =>
      widget.preferences.cacheServerPreferences({
        ...widget.preferences.current.serverPreferences,
        _preferencesKey: {
          'last_directory': _lastDirectory,
          'reference_prefix': _referencePrefix.text.trim(),
          'default_posting_date': _defaultPostingDate.text.trim(),
          'auto_post_opening_stock': _autoPostOpeningStock,
          'successful_signatures': _successfulSignatures.take(30).toList(),
          'last_type': _type.name,
        },
      });

  Future<void> _pickFile() async {
    final Future<XFile?> Function(String? initialDirectory) picker =
        widget.pickFileOverride ?? _pickNativeFile;
    final XFile? picked = await picker(_lastDirectory);
    if (picked == null) return;
    await _loadFile(picked);
  }

  Future<XFile?> _pickNativeFile(String? initialDirectory) => openFile(
        acceptedTypeGroups: _acceptedTypes,
        initialDirectory: initialDirectory,
        confirmButtonText: 'Select Import File',
      );

  Future<void> _handleDrop(DropDoneDetails details) async {
    if (details.files.isEmpty) return;
    await _loadFile(details.files.first);
  }

  Future<void> _loadFile(XFile file) async {
    final List<int> bytes = await file.readAsBytes();
    final FileStat? stat = await _tryStat(file.path);
    await _applyPreparedFile(
      name: _basename(file.path, fallback: file.name),
      bytes: bytes,
      extension: _extension(file.path).toLowerCase(),
      size: bytes.length,
      lastModified: stat?.modified,
      directory: _parentDirectory(file.path),
      file: file,
    );
  }

  Future<void> _loadPreparedFile(String name, List<int> bytes) => _applyPreparedFile(
        name: name,
        bytes: bytes,
        extension: _extension(name).toLowerCase(),
        size: bytes.length,
        lastModified: null,
        directory: null,
        file: null,
      );

  Future<void> _applyPreparedFile({
    required String name,
    required List<int> bytes,
    required String extension,
    required int size,
    required DateTime? lastModified,
    required String? directory,
    required XFile? file,
  }) async {
    setState(() {
      _busy = true;
      _error = null;
      _preview = null;
      _execution = null;
    });
    try {
      final _ImportFileSelection selection = _ImportFileSelection(
        file: file,
        bytes: bytes,
        name: name,
        size: size,
        lastModified: lastModified,
        extension: extension,
      );
      _lastDirectory = directory ?? _lastDirectory;
      _file = selection;
      _step = 1;
      await _persistPreferences();
      await _validate();
    } catch (error) {
      setState(() => _error = 'Unable to load the selected file: $error');
    } finally {
      if (mounted) {
        setState(() => _busy = false);
      }
    }
  }

  Future<void> _validate() async {
    final _ImportFileSelection? file = _file;
    if (file == null) return;
    setState(() {
      _busy = true;
      _error = null;
      _preview = null;
      _execution = null;
    });
    try {
      final List<Map<String, String>> rows = await _parseRows(file);
      final List<StorageNodeRecord> storageNodes = await _loadStorageNodes();
      final PagedResult<InventoryRecord> inventoryResult = await widget.api.inventory(
        page: 1,
        pageSize: 5000,
        search: '',
      );
      final _ImportValidationContext context = _ImportValidationContext(
        products: widget.products,
        branches: widget.branches,
        warehouses: widget.warehouses,
        storageNodes: storageNodes,
        inventory: inventoryResult.items,
        referencePrefix: _referencePrefix.text.trim(),
        defaultPostingDate: _defaultPostingDate.text.trim(),
        duplicateSignatures: _successfulSignatures,
      );
      final _InventoryImportPreview preview =
          _InventoryImportPreview.validate(_type, file, rows, context);
      if (!mounted) return;
      setState(() {
        _preview = preview;
        _step = 3;
      });
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() => _error = exception.message);
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = 'Validation failed: $error');
    } finally {
      if (mounted) {
        setState(() => _busy = false);
      }
    }
  }

  Future<List<StorageNodeRecord>> _loadStorageNodes() async {
    final List<Future<List<StorageNodeRecord>>> futures = widget.warehouses
        .map((warehouse) => widget.api.storageNodes(warehouse.id))
        .toList();
    final List<List<StorageNodeRecord>> results = await Future.wait(futures);
    return results.expand((items) => items).toList();
  }

  Future<List<Map<String, String>>> _parseRows(_ImportFileSelection file) async {
    return InventoryImportFileParser.parseBytes(
      fileName: file.name,
      bytes: file.bytes,
    );
  }

  Future<void> _saveReport(String suggestedName, String content) async {
    if (widget.saveTextOverride != null) {
      await widget.saveTextOverride!(suggestedName, content);
      return;
    }
    final FileSaveLocation? location =
        await getSaveLocation(suggestedName: suggestedName);
    if (location == null) return;
    await File(location.path).writeAsString(content, flush: true);
  }

  Future<void> _runImport() async {
    final _InventoryImportPreview? preview = _preview;
    if (preview == null || !preview.canImport) {
      return;
    }
    setState(() {
      _busy = true;
      _cancelRequested = false;
      _execution = _InventoryImportExecution.start(preview.rows.length);
      _step = 4;
      _error = null;
    });
    try {
      switch (_type) {
        case InventoryImportType.openingStock:
          await _runOpeningStockImport(preview);
          break;
        case InventoryImportType.inventoryUpdate:
          await _runInventoryUpdateImport(preview);
          break;
        case InventoryImportType.inventoryAdjustment:
          await _runInventoryAdjustmentImport(preview);
          break;
      }
      if (!mounted) return;
      if (!_execution!.cancelled && _execution!.failed == 0) {
        _successfulSignatures.add(preview.signature);
        await _persistPreferences();
      }
      setState(() => _step = 5);
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() {
        _error = exception.message;
        _execution = (_execution ?? _InventoryImportExecution.start(preview.rows.length))
            .copyWith(errorMessage: exception.message);
        _step = 5;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _error = '$error';
        _execution = (_execution ?? _InventoryImportExecution.start(preview.rows.length))
            .copyWith(errorMessage: '$error');
        _step = 5;
      });
    } finally {
      if (mounted) {
        setState(() => _busy = false);
      }
    }
  }

  Future<void> _runOpeningStockImport(_InventoryImportPreview preview) async {
    final Map<String, List<_ValidatedImportRow>> grouped = <String, List<_ValidatedImportRow>>{};
    for (final _ValidatedImportRow row in preview.rows.where((row) => row.isValid)) {
      grouped.putIfAbsent(row.groupKey!, () => <_ValidatedImportRow>[]).add(row);
    }
    final List<MapEntry<String, List<_ValidatedImportRow>>> batches =
        grouped.entries.toList(growable: false);
    for (final MapEntry<String, List<_ValidatedImportRow>> entry in batches) {
      if (_cancelRequested) {
        _markCancelled();
        return;
      }
      final _ValidatedImportRow first = entry.value.first;
      final Json payload = {
        'branch_id': first.branchId,
        'warehouse_id': first.warehouseId,
        'reference_number': first.referenceNumber,
        'posting_date': first.postingDate,
        if (first.remarks.isNotEmpty) 'remarks': first.remarks,
        'lines': entry.value
            .map(
              (row) => {
                'product_id': row.productId,
                'storage_node_id': row.storageNodeId,
                'quantity': row.quantity,
                if (row.minimumLevel != null) 'minimum_level': row.minimumLevel,
                if (row.maximumLevel != null) 'maximum_level': row.maximumLevel,
                if (row.reorderLevel != null) 'reorder_level': row.reorderLevel,
                if (row.safetyStock != null) 'safety_stock': row.safetyStock,
                if (row.remarks.isNotEmpty) 'remarks': row.remarks,
              },
            )
            .toList(),
      };
      final OpeningStockBatchRecord batch = await widget.api.createOpeningStock(payload);
      if (_autoPostOpeningStock) {
        await widget.api.postOpeningStock(batch.id);
      }
      _markSuccess(entry.value.length, 'Processed ${entry.value.length} opening stock rows.');
    }
  }

  Future<void> _runInventoryUpdateImport(_InventoryImportPreview preview) async {
    for (final _ValidatedImportRow row in preview.rows.where((row) => row.isValid)) {
      if (_cancelRequested) {
        _markCancelled();
        return;
      }
      try {
        await widget.api.updateInventoryRecord(
          row.inventoryId!,
          {
            'branch_id': row.branchId,
            'warehouse_id': row.warehouseId,
            'storage_node_id': row.storageNodeId,
            'product_id': row.productId,
            'minimum_level': row.minimumLevel,
            'maximum_level': row.maximumLevel,
            'reorder_level': row.reorderLevel,
            'safety_stock': row.safetyStock,
            'status': row.status ?? 'ACTIVE',
          },
        );
        _markSuccess(1, 'Updated inventory ${row.inventoryId}.');
      } on ApiException catch (exception) {
        _markFailure(row, exception.message);
      }
    }
  }

  Future<void> _runInventoryAdjustmentImport(_InventoryImportPreview preview) async {
    for (final _ValidatedImportRow row in preview.rows.where((row) => row.isValid)) {
      if (_cancelRequested) {
        _markCancelled();
        return;
      }
      try {
        await widget.api.createInventoryAdjustment({
          'branch_id': row.branchId,
          'warehouse_id': row.warehouseId,
          'storage_node_id': row.storageNodeId,
          'product_id': row.productId,
          'quantity': row.quantity,
          'reference_number': row.referenceNumber,
          'reference_type': 'ADJUSTMENT',
          'transaction_date': row.transactionDate,
          if (row.remarks.isNotEmpty) 'remarks': row.remarks,
        });
        _markSuccess(1, 'Adjusted inventory for ${row.productCode}.');
      } on ApiException catch (exception) {
        _markFailure(row, exception.message);
      }
    }
  }

  void _markSuccess(int count, String message) {
    setState(() {
      _execution = (_execution ?? _InventoryImportExecution.start(_preview?.rows.length ?? 0))
          .onSuccess(count, message);
    });
  }

  void _markFailure(_ValidatedImportRow row, String message) {
    setState(() {
      _execution = (_execution ?? _InventoryImportExecution.start(_preview?.rows.length ?? 0))
          .onFailure(row, message);
    });
  }

  void _markCancelled() {
    setState(() {
      _execution = (_execution ?? _InventoryImportExecution.start(_preview?.rows.length ?? 0))
          .copyWith(cancelled: true);
      _step = 5;
    });
  }

  void _requestCancel() {
    if (_busy) {
      setState(() => _cancelRequested = true);
    }
  }

  Future<void> _downloadValidationReport() async {
    final _InventoryImportPreview? preview = _preview;
    if (preview == null) return;
    await _saveReport(
      'inventory-validation-report.csv',
      preview.validationReportCsv(),
    );
  }

  Future<void> _downloadErrorReport() async {
    final _InventoryImportExecution? execution = _execution;
    if (execution == null) return;
    await _saveReport(
      'inventory-error-report.csv',
      execution.errorReportCsv(),
    );
  }

  Future<void> _downloadImportReport() async {
    final _InventoryImportExecution? execution = _execution;
    if (execution == null) return;
    await _saveReport(
      'inventory-import-report.csv',
      execution.importReportCsv(),
    );
  }

  @override
  Widget build(BuildContext context) => WorkspaceLayout(
        title: 'Inventory Import Wizard',
        description:
            'Import opening stock, inventory updates, or inventory adjustments from CSV or XLSX with preview and validation.',
        breadcrumbs: const ['Workspace', 'Inventory', 'Import'],
        toolbar: Wrap(
          spacing: 8,
          children: [
            OutlinedButton.icon(
              onPressed: _busy ? null : _pickFile,
              icon: const Icon(Icons.folder_open_outlined),
              label: const Text('Select File'),
            ),
            OutlinedButton.icon(
              onPressed: _busy ? null : _validate,
              icon: const Icon(Icons.rule_folder_outlined),
              label: const Text('Revalidate'),
            ),
            FilledButton.icon(
              onPressed: _busy || _preview?.canImport != true ? null : _runImport,
              icon: const Icon(Icons.file_upload_outlined),
              label: const Text('Import'),
            ),
          ],
        ),
        content: Stepper(
          currentStep: _step,
          controlsBuilder: (context, details) => const SizedBox.shrink(),
          onStepTapped: (value) {
            if (!_busy && value <= _maxAccessibleStep) {
              setState(() => _step = value);
            }
          },
          steps: [
            Step(
              title: const Text('Choose Import Type'),
              isActive: _step >= 0,
              state: _step > 0 ? StepState.complete : StepState.indexed,
              content: _buildTypeStep(),
            ),
            Step(
              title: const Text('Select File'),
              isActive: _step >= 1,
              state: _file != null ? StepState.complete : StepState.indexed,
              content: _buildFileStep(),
            ),
            Step(
              title: const Text('Preview'),
              isActive: _step >= 2,
              state: _preview != null ? StepState.complete : StepState.indexed,
              content: _buildPreviewStep(),
            ),
            Step(
              title: const Text('Validation Summary'),
              isActive: _step >= 3,
              state: _preview?.canImport == true
                  ? StepState.complete
                  : (_preview == null ? StepState.indexed : StepState.error),
              content: _buildSummaryStep(),
            ),
            Step(
              title: const Text('Import'),
              isActive: _step >= 4,
              state: _execution == null
                  ? StepState.indexed
                  : (_execution!.failed == 0 && !_execution!.cancelled
                      ? StepState.complete
                      : StepState.error),
              content: _buildImportStep(),
            ),
            Step(
              title: const Text('Completion'),
              isActive: _step >= 5,
              state: _step == 5 ? StepState.complete : StepState.indexed,
              content: _buildCompletionStep(),
            ),
          ],
        ),
      );

  int get _maxAccessibleStep {
    if (_execution != null) return 5;
    if (_preview != null) return 3;
    if (_file != null) return 1;
    return 0;
  }

  void _selectImportType(InventoryImportType? value) {
    if (value == null || _busy) return;
    setState(() {
      _type = value;
      _preview = null;
      _execution = null;
      _step = 0;
    });
    _persistPreferences();
  }

  Widget _buildTypeStep() => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // groupValue and onChanged moved onto RadioGroup in Flutter 3.32.
          // RadioGroup.onChanged is not nullable, so "disabled while busy" is
          // expressed by absorbing the gesture rather than by passing null.
          AbsorbPointer(
            absorbing: _busy,
            child: RadioGroup<InventoryImportType>(
              groupValue: _type,
              onChanged: _selectImportType,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  for (final InventoryImportType type
                      in InventoryImportType.values)
                    RadioListTile<InventoryImportType>(
                      value: type,
                      title: Text(type.label),
                      subtitle: Text(type.description),
                    ),
                ],
              ),
            ),
          ),
          if (_type == InventoryImportType.openingStock) ...[
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _referencePrefix,
                    decoration:
                        const InputDecoration(labelText: 'Fallback reference prefix'),
                    onChanged: (_) => _persistPreferences(),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: TextField(
                    controller: _defaultPostingDate,
                    decoration:
                        const InputDecoration(labelText: 'Default posting date'),
                    onChanged: (_) => _persistPreferences(),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            FilterChip(
              label: const Text('Post opening stock after import'),
              selected: _autoPostOpeningStock,
              onSelected: (value) {
                setState(() => _autoPostOpeningStock = value);
                _persistPreferences();
              },
            ),
          ],
        ],
      );

  Widget _buildFileStep() => DropTarget(
        onDragEntered: (_) => setState(() => _dragging = true),
        onDragExited: (_) => setState(() => _dragging = false),
        onDragDone: (details) async {
          setState(() => _dragging = false);
          await _handleDrop(details);
        },
        child: Card(
          color: _dragging
              ? Theme.of(context).colorScheme.primaryContainer
              : null,
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Select or drop a CSV/XLSX file',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                const SizedBox(height: 8),
                Text(
                  'The wizard remembers the last folder and preserves your selections across retries.',
                  style: Theme.of(context).textTheme.bodyMedium,
                ),
                const SizedBox(height: 16),
                Wrap(
                  spacing: 8,
                  children: [
                    FilledButton.icon(
                      onPressed: _busy ? null : _pickFile,
                      icon: const Icon(Icons.attach_file),
                      label: const Text('Browse'),
                    ),
                    OutlinedButton.icon(
                      onPressed: _file == null || _busy ? null : _validate,
                      icon: const Icon(Icons.visibility_outlined),
                      label: const Text('Preview File'),
                    ),
                  ],
                ),
                if (_file != null) ...[
                  const SizedBox(height: 16),
                  _metaLine('File name', _file!.name),
                  _metaLine('File size', '${_file!.size} bytes'),
                  _metaLine(
                    'Last modified',
                    _file!.lastModified?.toIso8601String() ?? 'Unknown',
                  ),
                ],
                if (_error != null) ...[
                  const SizedBox(height: 12),
                  Text(
                    _error!,
                    style: TextStyle(color: Theme.of(context).colorScheme.error),
                  ),
                ],
              ],
            ),
          ),
        ),
      );

  Widget _buildPreviewStep() {
    final _InventoryImportPreview? preview = _preview;
    if (preview == null) {
      return const Text('Load a file to preview the first 100 rows.');
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (preview.missingColumns.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: Wrap(
              spacing: 8,
              children: preview.missingColumns
                  .map(
                    (column) => Chip(
                      avatar: const Icon(Icons.error_outline, size: 18),
                      label: Text('Missing: $column'),
                    ),
                  )
                  .toList(),
            ),
          ),
        SizedBox(
          height: 320,
          child: preview.previewRows.isEmpty
              ? const StandardEmptyState(type: EmptyStateType.noRecords)
              : SingleChildScrollView(
                  scrollDirection: Axis.horizontal,
                  child: DataTable(
                    columns: const [
                      DataColumn(label: Text('Row')),
                      DataColumn(label: Text('Status')),
                      DataColumn(label: Text('Product')),
                      DataColumn(label: Text('Branch')),
                      DataColumn(label: Text('Warehouse')),
                      DataColumn(label: Text('Storage')),
                      DataColumn(label: Text('Quantity')),
                      DataColumn(label: Text('Errors / Warnings')),
                    ],
                    rows: preview.previewRows
                        .map(
                          (row) => DataRow(
                            color: WidgetStateProperty.resolveWith<Color?>(
                              (_) => row.errors.isNotEmpty
                                  ? Theme.of(context)
                                      .colorScheme
                                      .errorContainer
                                      .withValues(alpha: .35)
                                  : row.warnings.isNotEmpty
                                      ? Theme.of(context)
                                          .colorScheme
                                          .secondaryContainer
                                          .withValues(alpha: .35)
                                      : null,
                            ),
                            cells: [
                              DataCell(Text('${row.rowNumber}')),
                              DataCell(Text(row.isValid ? 'Valid' : 'Invalid')),
                              DataCell(Text(_prefer(row.productCode, row.productName))),
                              DataCell(Text(_prefer(row.branchCode, row.branchName))),
                              DataCell(Text(_prefer(row.warehouseCode, row.warehouseName))),
                              DataCell(Text(_prefer(row.storageCode, row.storageName))),
                              DataCell(Text(row.quantity?.toString() ?? '-')),
                              DataCell(
                                SizedBox(
                                  width: 320,
                                  child: Wrap(
                                    spacing: 6,
                                    runSpacing: 6,
                                    children: [
                                      ...row.errors.map(
                                        (message) => Chip(
                                          avatar: const Icon(Icons.error_outline, size: 18),
                                          label: Text(message),
                                        ),
                                      ),
                                      ...row.warnings.map(
                                        (message) => Chip(
                                          avatar: const Icon(Icons.warning_amber_outlined, size: 18),
                                          label: Text(message),
                                        ),
                                      ),
                                    ],
                                  ),
                                ),
                              ),
                            ],
                          ),
                        )
                        .toList(),
                  ),
                ),
        ),
      ],
    );
  }

  Widget _buildSummaryStep() {
    final _InventoryImportPreview? preview = _preview;
    if (preview == null) {
      return const Text('Validate a file to see the summary.');
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Wrap(
          spacing: 12,
          runSpacing: 12,
          children: [
            _summaryCard('Total Records', '${preview.totalRecords}'),
            _summaryCard('Valid Records', '${preview.validRecords}'),
            _summaryCard('Invalid Records', '${preview.invalidRecords}'),
            _summaryCard('Warnings', '${preview.warningCount}'),
            _summaryCard('Errors', '${preview.errorCount}'),
          ],
        ),
        const SizedBox(height: 16),
        if (preview.duplicateImport)
          Text(
            'This file signature has already been imported successfully. Duplicate imports are blocked.',
            style: TextStyle(color: Theme.of(context).colorScheme.error),
          ),
        const SizedBox(height: 16),
        Wrap(
          spacing: 8,
          children: [
            OutlinedButton.icon(
              onPressed: _downloadValidationReport,
              icon: const Icon(Icons.download_outlined),
              label: const Text('Download Validation Report'),
            ),
            FilledButton.icon(
              onPressed: preview.canImport && !_busy ? _runImport : null,
              icon: const Icon(Icons.file_upload_outlined),
              label: const Text('Start Import'),
            ),
          ],
        ),
      ],
    );
  }

  Widget _buildImportStep() {
    final _InventoryImportExecution? execution = _execution;
    final int total = execution?.total ?? (_preview?.rows.length ?? 0);
    final int processed = execution?.processed ?? 0;
    final double progress = total == 0 ? 0 : processed / total;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        LinearProgressIndicator(value: _busy ? progress.clamp(0, 1) : 1),
        const SizedBox(height: 12),
        Text('Processed: $processed'),
        Text('Remaining: ${execution?.remaining ?? total - processed}'),
        Text('Success: ${execution?.succeeded ?? 0}'),
        Text('Failed: ${execution?.failed ?? 0}'),
        if (execution?.message?.isNotEmpty == true) ...[
          const SizedBox(height: 8),
          Text(execution!.message!),
        ],
        const SizedBox(height: 12),
        Row(
          children: [
            FilledButton.tonalIcon(
              onPressed: _busy
                  ? () => setState(() => _cancelRequested = true)
                  : null,
              icon: const Icon(Icons.cancel_outlined),
              label: const Text('Cancel'),
            ),
            const SizedBox(width: 8),
            OutlinedButton.icon(
              onPressed: !_busy && _preview?.canImport == true ? _runImport : null,
              icon: const Icon(Icons.refresh),
              label: const Text('Retry'),
            ),
          ],
        ),
      ],
    );
  }

  Widget _buildCompletionStep() {
    final _InventoryImportExecution? execution = _execution;
    if (execution == null) {
      return const Text('Run an import to view the completion summary.');
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Wrap(
          spacing: 12,
          runSpacing: 12,
          children: [
            _summaryCard('Imported', '${execution.succeeded}'),
            _summaryCard('Skipped', '${execution.skipped}'),
            _summaryCard('Failed', '${execution.failed}'),
            _summaryCard('Warnings', '${execution.warningCount}'),
          ],
        ),
        if (execution.errorMessage?.isNotEmpty == true) ...[
          const SizedBox(height: 12),
          Text(
            execution.errorMessage!,
            style: TextStyle(color: Theme.of(context).colorScheme.error),
          ),
        ],
        const SizedBox(height: 16),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            if (execution.failed > 0 || execution.cancelled)
              FilledButton.tonalIcon(
                onPressed: _preview?.canImport == true && !_busy ? _runImport : null,
                icon: const Icon(Icons.refresh),
                label: const Text('Retry Import'),
              ),
            OutlinedButton.icon(
              onPressed: _downloadImportReport,
              icon: const Icon(Icons.download_outlined),
              label: const Text('Download Import Report'),
            ),
            OutlinedButton.icon(
              onPressed: execution.failed == 0 ? null : _downloadErrorReport,
              icon: const Icon(Icons.download_outlined),
              label: const Text('Download Error Report'),
            ),
            FilledButton.icon(
              onPressed: execution.succeeded == 0
                  ? null
                  : () => widget.onViewImportedRecords(_type),
              icon: const Icon(Icons.open_in_new),
              label: const Text('View Imported Records'),
            ),
          ],
        ),
      ],
    );
  }

  Widget _summaryCard(String label, String value) => SizedBox(
        width: 170,
        child: Card(
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(label, style: Theme.of(context).textTheme.labelLarge),
                const SizedBox(height: 8),
                Text(value, style: Theme.of(context).textTheme.headlineSmall),
              ],
            ),
          ),
        ),
      );

  Widget _metaLine(String label, String value) => Padding(
        padding: const EdgeInsets.only(bottom: 6),
        child: Text('$label: $value'),
      );
}

class _ImportFileSelection {
  const _ImportFileSelection({
    required this.file,
    required this.bytes,
    required this.name,
    required this.size,
    required this.lastModified,
    required this.extension,
  });

  final XFile? file;
  final List<int> bytes;
  final String name;
  final int size;
  final DateTime? lastModified;
  final String extension;

  String get signature =>
      '$name|$size|${lastModified?.millisecondsSinceEpoch ?? 0}|$extension';
}

class _ImportValidationContext {
  const _ImportValidationContext({
    required this.products,
    required this.branches,
    required this.warehouses,
    required this.storageNodes,
    required this.inventory,
    required this.referencePrefix,
    required this.defaultPostingDate,
    required this.duplicateSignatures,
  });

  final List<Product> products;
  final List<BranchRecord> branches;
  final List<WarehouseRecord> warehouses;
  final List<StorageNodeRecord> storageNodes;
  final List<InventoryRecord> inventory;
  final String referencePrefix;
  final String defaultPostingDate;
  final Set<String> duplicateSignatures;
}

class _InventoryImportPreview {
  const _InventoryImportPreview({
    required this.signature,
    required this.rows,
    required this.previewRows,
    required this.missingColumns,
    required this.totalRecords,
    required this.validRecords,
    required this.invalidRecords,
    required this.warningCount,
    required this.errorCount,
    required this.duplicateImport,
  });

  final String signature;
  final List<_ValidatedImportRow> rows;
  final List<_ValidatedImportRow> previewRows;
  final List<String> missingColumns;
  final int totalRecords;
  final int validRecords;
  final int invalidRecords;
  final int warningCount;
  final int errorCount;
  final bool duplicateImport;

  bool get canImport =>
      missingColumns.isEmpty &&
      invalidRecords == 0 &&
      !duplicateImport &&
      rows.isNotEmpty;

  static _InventoryImportPreview validate(
    InventoryImportType type,
    _ImportFileSelection file,
    List<Map<String, String>> rows,
    _ImportValidationContext context,
  ) {
    final Set<String> duplicateKeys = <String>{};
    final Set<String> seenKeys = <String>{};
    final List<_ValidatedImportRow> validated = [];
    final List<String> requiredColumns = _requiredColumns(type);
    final Set<String> headers = rows.isEmpty ? <String>{} : rows.first.keys.toSet();
    final List<String> missingColumns = requiredColumns
        .where((column) => !headers.contains(column))
        .toList(growable: false);
    for (int index = 0; index < rows.length; index++) {
      final _ValidatedImportRow row = _validateRow(
        rowNumber: index + 2,
        type: type,
        row: rows[index],
        context: context,
      );
      final String? duplicateKey = row.duplicateKey;
      if (duplicateKey != null && duplicateKey.isNotEmpty) {
        if (!seenKeys.add(duplicateKey)) {
          duplicateKeys.add(duplicateKey);
        }
      }
      validated.add(row);
    }
    final List<_ValidatedImportRow> finalized = validated
        .map(
          (row) => duplicateKeys.contains(row.duplicateKey)
              ? row.copyWith(
                  errors: [...row.errors, 'Duplicate record in import file'],
                )
              : row,
        )
        .toList(growable: false);
    final int valid = finalized.where((row) => row.isValid).length;
    final int warnings =
        finalized.fold(0, (sum, row) => sum + row.warnings.length);
    final int errors = finalized.fold(0, (sum, row) => sum + row.errors.length);
    return _InventoryImportPreview(
      signature: file.signature,
      rows: finalized,
      previewRows: finalized.take(100).toList(growable: false),
      missingColumns: missingColumns,
      totalRecords: finalized.length,
      validRecords: valid,
      invalidRecords: finalized.length - valid,
      warningCount: warnings,
      errorCount: errors,
      duplicateImport: context.duplicateSignatures.contains(file.signature),
    );
  }

  String validationReportCsv() {
    final StringBuffer buffer = StringBuffer(
      'Row,Valid,ProductCode,BranchCode,WarehouseCode,StorageCode,Errors,Warnings\n',
    );
    for (final _ValidatedImportRow row in rows) {
      buffer.writeln(
        [
          row.rowNumber,
          row.isValid,
          _csvField(row.productCode ?? row.productName ?? ''),
          _csvField(row.branchCode ?? row.branchName ?? ''),
          _csvField(row.warehouseCode ?? row.warehouseName ?? ''),
          _csvField(row.storageCode ?? row.storageName ?? ''),
          _csvField(row.errors.join(' | ')),
          _csvField(row.warnings.join(' | ')),
        ].join(','),
      );
    }
    return buffer.toString();
  }
}

class _ValidatedImportRow {
  const _ValidatedImportRow({
    required this.rowNumber,
    required this.source,
    this.inventoryId,
    this.productId,
    this.productCode,
    this.productName,
    this.branchId,
    this.branchCode,
    this.branchName,
    this.warehouseId,
    this.warehouseCode,
    this.warehouseName,
    this.storageNodeId,
    this.storageCode,
    this.storageName,
    this.referenceNumber,
    this.postingDate,
    this.transactionDate,
    this.quantity,
    this.minimumLevel,
    this.maximumLevel,
    this.reorderLevel,
    this.safetyStock,
    this.status,
    this.remarks = '',
    this.groupKey,
    this.duplicateKey,
    this.errors = const [],
    this.warnings = const [],
  });

  final int rowNumber;
  final Map<String, String> source;
  final String? inventoryId;
  final String? productId;
  final String? productCode;
  final String? productName;
  final String? branchId;
  final String? branchCode;
  final String? branchName;
  final String? warehouseId;
  final String? warehouseCode;
  final String? warehouseName;
  final String? storageNodeId;
  final String? storageCode;
  final String? storageName;
  final String? referenceNumber;
  final String? postingDate;
  final String? transactionDate;
  final num? quantity;
  final num? minimumLevel;
  final num? maximumLevel;
  final num? reorderLevel;
  final num? safetyStock;
  final String? status;
  final String remarks;
  final String? groupKey;
  final String? duplicateKey;
  final List<String> errors;
  final List<String> warnings;

  bool get isValid => errors.isEmpty;

  _ValidatedImportRow copyWith({
    List<String>? errors,
    List<String>? warnings,
  }) =>
      _ValidatedImportRow(
        rowNumber: rowNumber,
        source: source,
        inventoryId: inventoryId,
        productId: productId,
        productCode: productCode,
        productName: productName,
        branchId: branchId,
        branchCode: branchCode,
        branchName: branchName,
        warehouseId: warehouseId,
        warehouseCode: warehouseCode,
        warehouseName: warehouseName,
        storageNodeId: storageNodeId,
        storageCode: storageCode,
        storageName: storageName,
        referenceNumber: referenceNumber,
        postingDate: postingDate,
        transactionDate: transactionDate,
        quantity: quantity,
        minimumLevel: minimumLevel,
        maximumLevel: maximumLevel,
        reorderLevel: reorderLevel,
        safetyStock: safetyStock,
        status: status,
        remarks: remarks,
        groupKey: groupKey,
        duplicateKey: duplicateKey,
        errors: errors ?? this.errors,
        warnings: warnings ?? this.warnings,
      );
}

class _InventoryImportExecution {
  const _InventoryImportExecution({
    required this.total,
    required this.processed,
    required this.succeeded,
    required this.failed,
    required this.skipped,
    required this.warningCount,
    required this.cancelled,
    required this.failures,
    required this.messages,
    this.errorMessage,
  });

  final int total;
  final int processed;
  final int succeeded;
  final int failed;
  final int skipped;
  final int warningCount;
  final bool cancelled;
  final List<_ImportFailure> failures;
  final List<String> messages;
  final String? errorMessage;

  int get remaining => (total - processed).clamp(0, total);
  String? get message => messages.isEmpty ? null : messages.last;

  static _InventoryImportExecution start(int total) => _InventoryImportExecution(
        total: total,
        processed: 0,
        succeeded: 0,
        failed: 0,
        skipped: 0,
        warningCount: 0,
        cancelled: false,
        failures: const [],
        messages: const [],
      );

  _InventoryImportExecution onSuccess(int count, String message) =>
      _InventoryImportExecution(
        total: total,
        processed: processed + count,
        succeeded: succeeded + count,
        failed: failed,
        skipped: skipped,
        warningCount: warningCount,
        cancelled: false,
        failures: failures,
        messages: [...messages, message],
        errorMessage: errorMessage,
      );

  _InventoryImportExecution onFailure(_ValidatedImportRow row, String message) =>
      _InventoryImportExecution(
        total: total,
        processed: processed + 1,
        succeeded: succeeded,
        failed: failed + 1,
        skipped: skipped,
        warningCount: warningCount,
        cancelled: false,
        failures: [...failures, _ImportFailure(row.rowNumber, row.source, message)],
        messages: [...messages, message],
        errorMessage: errorMessage,
      );

  _InventoryImportExecution copyWith({
    bool? cancelled,
    String? errorMessage,
  }) =>
      _InventoryImportExecution(
        total: total,
        processed: processed,
        succeeded: succeeded,
        failed: failed,
        skipped: skipped,
        warningCount: warningCount,
        cancelled: cancelled ?? this.cancelled,
        failures: failures,
        messages: messages,
        errorMessage: errorMessage ?? this.errorMessage,
      );

  String importReportCsv() {
    final StringBuffer buffer =
        StringBuffer('Metric,Value\nImported,$succeeded\nSkipped,$skipped\nFailed,$failed\nWarnings,$warningCount\nCancelled,$cancelled\n');
    return buffer.toString();
  }

  String errorReportCsv() {
    final StringBuffer buffer = StringBuffer('Row,Error,Source\n');
    for (final _ImportFailure failure in failures) {
      buffer.writeln(
        '${failure.rowNumber},${_csvField(failure.message)},${_csvField(jsonEncode(failure.source))}',
      );
    }
    return buffer.toString();
  }
}

class _ImportFailure {
  const _ImportFailure(this.rowNumber, this.source, this.message);

  final int rowNumber;
  final Map<String, String> source;
  final String message;
}

_ValidatedImportRow _validateRow({
  required int rowNumber,
  required InventoryImportType type,
  required Map<String, String> row,
  required _ImportValidationContext context,
}) {
  final List<String> errors = [];
  final List<String> warnings = [];
  final Product? product = _resolveProduct(row, context.products);
  final BranchRecord? branch = _resolveBranch(row, context.branches);
  final WarehouseRecord? warehouse =
      _resolveWarehouse(row, context.warehouses, branch?.id);
  final StorageNodeRecord? storage =
      _resolveStorage(row, context.storageNodes, warehouse?.id);
  final String remarks = _value(row, 'remarks');
  final num? quantity = _parseNum(_value(row, 'quantity'));
  final num? minimum = _parseNum(_value(row, 'minimumlevel'));
  final num? maximum = _parseNum(_value(row, 'maximumlevel'));
  final num? reorder = _parseNum(_value(row, 'reorderlevel'));
  final num? safety = _parseNum(_value(row, 'safetystock'));
  final String status = _value(row, 'status');
  final String reference = _value(row, 'referencenumber').isNotEmpty
      ? _value(row, 'referencenumber')
      : '${context.referencePrefix}-${rowNumber.toString().padLeft(4, '0')}';
  final String postingDate = _value(row, 'postingdate').isNotEmpty
      ? _value(row, 'postingdate')
      : context.defaultPostingDate;
  final String transactionDate = _value(row, 'transactiondate').isNotEmpty
      ? _value(row, 'transactiondate')
      : context.defaultPostingDate;
  if (product == null) {
    errors.add('Unknown product');
  }
  if (branch == null) {
    errors.add('Unknown branch');
  }
  if (warehouse == null) {
    errors.add('Unknown warehouse');
  }
  if (_value(row, 'storagecode').isNotEmpty && storage == null) {
    errors.add('Unknown storage location');
  }
  switch (type) {
    case InventoryImportType.openingStock:
      if (quantity == null || quantity <= 0) {
        errors.add('Quantity must be greater than zero');
      }
      if (!_isIsoDate(postingDate)) {
        errors.add('Posting date must be ISO yyyy-mm-dd');
      }
      break;
    case InventoryImportType.inventoryUpdate:
      if (minimum == null &&
          maximum == null &&
          reorder == null &&
          safety == null &&
          status.trim().isEmpty) {
        warnings.add('No changes were provided for this inventory row');
      }
      break;
    case InventoryImportType.inventoryAdjustment:
      if (quantity == null || quantity == 0) {
        errors.add('Quantity must be non-zero');
      }
      if (reference.trim().isEmpty) {
        errors.add('Reference number is required');
      }
      if (!_isIsoDate(transactionDate)) {
        errors.add('Transaction date must be ISO yyyy-mm-dd');
      }
      break;
  }
  InventoryRecord? inventory;
  String? inventoryId = _value(row, 'inventoryid');
  if (type != InventoryImportType.openingStock) {
    inventory = _resolveInventory(
      inventoryId: inventoryId,
      productId: product?.id,
      branchId: branch?.id,
      warehouseId: warehouse?.id,
      storageNodeId: storage?.id,
      inventory: context.inventory,
    );
    if (inventory == null) {
      errors.add('Unknown inventory record');
    } else {
      inventoryId = inventory.id;
    }
  }
  return _ValidatedImportRow(
    rowNumber: rowNumber,
    source: row,
    inventoryId: inventoryId,
    productId: product?.id,
    productCode: product?.code,
    productName: product?.name,
    branchId: branch?.id,
    branchCode: branch?.code,
    branchName: branch?.name,
    warehouseId: warehouse?.id,
    warehouseCode: warehouse?.code,
    warehouseName: warehouse?.name,
    storageNodeId: storage?.id,
    storageCode: storage?.code,
    storageName: storage?.name,
    referenceNumber: reference,
    postingDate: postingDate,
    transactionDate: transactionDate,
    quantity: quantity,
    minimumLevel: minimum,
    maximumLevel: maximum,
    reorderLevel: reorder,
    safetyStock: safety,
    status: status.trim().isEmpty ? null : status.trim().toUpperCase(),
    remarks: remarks,
    groupKey: type == InventoryImportType.openingStock
        ? '${branch?.id}|${warehouse?.id}|$postingDate|$reference'
        : null,
    duplicateKey: switch (type) {
      InventoryImportType.openingStock =>
        '${branch?.id}|${warehouse?.id}|${storage?.id}|${product?.id}|$postingDate|$reference',
      // _value returns '' rather than null for a missing column, and a row that
      // resolves gets the real id assigned above, so the composite fallback
      // that used to sit here could never run. An unresolved row is already an
      // error and its empty key is skipped by the duplicate check.
      InventoryImportType.inventoryUpdate => inventoryId,
      InventoryImportType.inventoryAdjustment =>
        '$reference|$transactionDate|${branch?.id}|${warehouse?.id}|${storage?.id}|${product?.id}|$quantity',
    },
    errors: errors,
    warnings: warnings,
  );
}

List<String> _requiredColumns(InventoryImportType type) => switch (type) {
      InventoryImportType.openingStock => const [
          'productcode',
          'branchcode',
          'warehousecode',
          'quantity',
        ],
      InventoryImportType.inventoryUpdate => const [
          'productcode',
          'branchcode',
          'warehousecode',
        ],
      InventoryImportType.inventoryAdjustment => const [
          'productcode',
          'branchcode',
          'warehousecode',
          'quantity',
          'referencenumber',
          'transactiondate',
        ],
    };

Product? _resolveProduct(Map<String, String> row, List<Product> products) {
  final String code = _upper(_value(row, 'productcode'));
  final String barcode = _upper(_value(row, 'barcode'));
  final String name = _upper(_value(row, 'productname'));
  for (final Product product in products) {
    if (code.isNotEmpty && _upper(product.code) == code) return product;
    if (barcode.isNotEmpty && _upper(product.barcode) == barcode) return product;
    if (name.isNotEmpty && _upper(product.name) == name) return product;
  }
  return null;
}

BranchRecord? _resolveBranch(Map<String, String> row, List<BranchRecord> branches) {
  final String code = _upper(_value(row, 'branchcode'));
  final String name = _upper(_value(row, 'branchname'));
  for (final BranchRecord branch in branches) {
    if (code.isNotEmpty && _upper(branch.code) == code) return branch;
    if (name.isNotEmpty && _upper(branch.name) == name) return branch;
  }
  return null;
}

WarehouseRecord? _resolveWarehouse(
  Map<String, String> row,
  List<WarehouseRecord> warehouses,
  String? branchId,
) {
  final String code = _upper(_value(row, 'warehousecode'));
  final String name = _upper(_value(row, 'warehousename'));
  final Iterable<WarehouseRecord> scoped = branchId == null
      ? warehouses
      : warehouses.where((warehouse) => warehouse.branchId == branchId);
  for (final WarehouseRecord warehouse in scoped) {
    if (code.isNotEmpty && _upper(warehouse.code) == code) return warehouse;
    if (name.isNotEmpty && _upper(warehouse.name) == name) return warehouse;
  }
  return null;
}

StorageNodeRecord? _resolveStorage(
  Map<String, String> row,
  List<StorageNodeRecord> nodes,
  String? warehouseId,
) {
  final String code = _upper(_value(row, 'storagecode'));
  final String name = _upper(_value(row, 'storagename'));
  if (code.isEmpty && name.isEmpty) {
    return null;
  }
  final Iterable<StorageNodeRecord> scoped = warehouseId == null
      ? nodes
      : nodes.where((node) => node.warehouseId == warehouseId);
  for (final StorageNodeRecord node in scoped) {
    if (code.isNotEmpty && _upper(node.code) == code) return node;
    if (name.isNotEmpty && _upper(node.name) == name) return node;
  }
  return null;
}

InventoryRecord? _resolveInventory({
  required String? inventoryId,
  required String? productId,
  required String? branchId,
  required String? warehouseId,
  required String? storageNodeId,
  required List<InventoryRecord> inventory,
}) {
  for (final InventoryRecord row in inventory) {
    if (inventoryId?.isNotEmpty == true && row.id == inventoryId) {
      return row;
    }
  }
  for (final InventoryRecord row in inventory) {
    if (row.productId == productId &&
        row.branchId == branchId &&
        row.warehouseId == warehouseId &&
        row.storageNodeId == (storageNodeId ?? '')) {
      return row;
    }
  }
  return null;
}

String _value(Map<String, String> row, String key) => row[key] ?? '';
String _upper(String value) => value.trim().toUpperCase();
String _normalizeHeader(String value) =>
    value.trim().toLowerCase().replaceAll(RegExp(r'[^a-z0-9]'), '');
String _basename(String path, {required String fallback}) {
  if (path.isEmpty) return fallback;
  final List<String> parts = path.split(RegExp(r'[\\/]'));
  return parts.isEmpty ? fallback : parts.last;
}

String _extension(String path) {
  final String name = _basename(path, fallback: path);
  final int index = name.lastIndexOf('.');
  if (index < 0) return '';
  return name.substring(index + 1);
}

String? _parentDirectory(String path) {
  if (path.isEmpty) return null;
  final int index = path.lastIndexOf(RegExp(r'[\\/]'));
  if (index <= 0) return null;
  return path.substring(0, index);
}

Future<FileStat?> _tryStat(String path) async {
  if (path.isEmpty) return null;
  try {
    return await File(path).stat();
  } on FileSystemException {
    return null;
  }
}

num? _parseNum(String value) {
  final String text = value.trim();
  if (text.isEmpty) return null;
  return num.tryParse(text);
}

bool _isIsoDate(String value) => DateTime.tryParse(value.trim()) != null;
String _prefer(String? primary, String? secondary) =>
    (primary?.isNotEmpty == true ? primary! : secondary?.isNotEmpty == true ? secondary! : '-');
String _csvField(String value) => '"${value.replaceAll('"', '""')}"';
