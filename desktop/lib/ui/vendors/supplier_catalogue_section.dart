import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/dialogs/app_dialogs.dart';
import '../../core/notifications/notification_service.dart';
import '../../models/entities.dart' show Json;
import '../../models/file_import.dart';
import '../../models/product.dart';
import '../../models/supplier_catalogue.dart';
import '../workspace/desktop_framework.dart';

/// What a supplier sells and at what price (BUY-4), on the phase 2 supplier
/// record. Rows are never edited: a change is a new row from a later date.
class SupplierCatalogueSection extends StatefulWidget {
  const SupplierCatalogueSection({
    super.key,
    required this.api,
    required this.vendorId,
    this.canManage = false,
    this.canImport = false,
  });

  final ApiClient api;
  final String vendorId;

  /// `VENDOR_UPDATE`: add and delete rows.
  final bool canManage;

  /// `VENDOR_IMPORT`: bring rows in from a file.
  final bool canImport;

  @override
  State<SupplierCatalogueSection> createState() =>
      _SupplierCatalogueSectionState();
}

class _SupplierCatalogueSectionState extends State<SupplierCatalogueSection> {
  List<SupplierCatalogueRow>? _rows;
  bool _history = false;
  String? _selectedId;
  String? _error;

  @override
  void initState() {
    super.initState();
    unawaited(_reload());
  }

  Future<void> _reload() async {
    try {
      final List<SupplierCatalogueRow> rows = await widget.api
          .supplierCatalogue(widget.vendorId, history: _history);
      if (!mounted) return;
      setState(() {
        _rows = rows;
        _error = null;
        if (!rows.any((row) => row.id == _selectedId)) _selectedId = null;
      });
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() {
        _rows = const <SupplierCatalogueRow>[];
        _error = exception.message;
      });
    }
  }

  Future<void> _add() async {
    final bool? saved = await showDialog<bool>(
      context: context,
      builder: (context) => _AddCatalogueRowDialog(
        api: widget.api,
        vendorId: widget.vendorId,
      ),
    );
    if (saved == true) await _reload();
  }

  Future<void> _delete(SupplierCatalogueRow row) async {
    final bool confirmed = await showWorkspaceConfirmDialog(
      context,
      title: 'Delete catalogue row?',
      message: 'Remove ${row.productCode} from ${row.effectiveFrom}? Use this '
          'only for a row typed in error; a price change is a new row.',
      confirmLabel: 'Delete',
      type: ConfirmationType.delete,
    );
    if (!confirmed || !mounted) return;
    try {
      await widget.api.deleteSupplierCatalogueRow(widget.vendorId, row.id);
      await _reload();
    } on ApiException catch (exception) {
      if (!mounted) return;
      NotificationService.show(context, exception.message,
          kind: AppNotificationKind.error);
    }
  }

  Future<void> _import() async {
    final FileImportReport? report = await showDialog<FileImportReport>(
      context: context,
      barrierDismissible: false,
      builder: (context) => MasterImportDialog(
        noun: 'catalogue rows',
        fileStem: 'supplier_catalogue',
        downloadTemplate: (format) => widget.api
            .supplierCatalogueImportTemplate(widget.vendorId, format: format),
        mappingApi: widget.api,
        mappingKind: 'supplier-catalogue',
        checkFile: ({
          required String fileName,
          required List<int> bytes,
          required bool updateExisting,
          required bool apply,
          Map<String, String?>? mapping,
        }) =>
            widget.api.checkSupplierCatalogueImportFile(
          widget.vendorId,
          fileName: fileName,
          bytes: bytes,
          updateExisting: updateExisting,
          apply: apply,
          mapping: mapping,
        ),
        canUpdate: widget.canManage,
      ),
    );
    if (!mounted || report == null) return;
    await _reload();
    if (!mounted) return;
    NotificationService.show(
      context,
      'Imported ${report.toCreate} new, updated ${report.toUpdate} '
      'catalogue rows.',
      kind: AppNotificationKind.success,
    );
  }

  @override
  Widget build(BuildContext context) {
    final List<SupplierCatalogueRow>? rows = _rows;
    SupplierCatalogueRow? target;
    for (final SupplierCatalogueRow row in rows ?? const []) {
      if (row.id == _selectedId) target = row;
    }
    final SupplierCatalogueRow? selected = target;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Padding(
          padding: const EdgeInsets.symmetric(vertical: AppSpacing.sm),
          child: Wrap(
            spacing: AppSpacing.sm,
            runSpacing: AppSpacing.sm,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              FilterChip(
                key: const ValueKey('catalogue-history'),
                label: const Text('Show history'),
                selected: _history,
                onSelected: (value) {
                  setState(() => _history = value);
                  unawaited(_reload());
                },
              ),
              if (widget.canManage)
                OutlinedButton.icon(
                  key: const ValueKey('catalogue-add'),
                  onPressed: _add,
                  icon: const Icon(Icons.add),
                  label: const Text('Add row'),
                ),
              if (widget.canManage)
                OutlinedButton.icon(
                  key: const ValueKey('catalogue-delete'),
                  onPressed:
                      selected == null ? null : () => _delete(selected),
                  icon: const Icon(Icons.delete_outline),
                  label: const Text('Delete row'),
                ),
              if (widget.canImport)
                OutlinedButton.icon(
                  key: const ValueKey('catalogue-import'),
                  onPressed: _import,
                  icon: const Icon(Icons.upload_file),
                  label: const Text('Import file'),
                ),
            ],
          ),
        ),
        const Divider(height: 1),
        if (_error != null)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: AppSpacing.sm),
            child: Text(
              _error!,
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
          ),
        if (rows == null)
          const Center(child: CircularProgressIndicator())
        else if (rows.isEmpty)
          const StandardEmptyState(
            type: EmptyStateType.noRecords,
            message: 'Nothing in this supplier\'s catalogue yet. A change is '
                'a new row from a later date.',
          )
        else
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: DataTable(
              showCheckboxColumn: false,
              columns: const [
                DataColumn(label: Text('Product')),
                DataColumn(label: Text('Supplier code')),
                DataColumn(label: Text('Supplier name')),
                DataColumn(label: Text('Price'), numeric: true),
                DataColumn(label: Text('Pack'), numeric: true),
                DataColumn(label: Text('Min order'), numeric: true),
                DataColumn(label: Text('Multiple'), numeric: true),
                DataColumn(label: Text('Lead days'), numeric: true),
                DataColumn(label: Text('From')),
                DataColumn(label: Text('Status')),
              ],
              rows: [
                for (final SupplierCatalogueRow row in rows)
                  DataRow(
                    key: ValueKey<String>('catalogue-row-${row.id}'),
                    selected: row.id == _selectedId,
                    onSelectChanged: (_) =>
                        setState(() => _selectedId = row.id),
                    cells: [
                      DataCell(Text('${row.productCode} ${row.productName}')),
                      DataCell(Text(row.supplierProductCode)),
                      DataCell(Text(row.supplierProductName)),
                      DataCell(Text(row.unitPrice)),
                      DataCell(Text(row.packSize)),
                      DataCell(Text(row.minimumOrderQuantity)),
                      DataCell(Text(row.orderMultiple)),
                      DataCell(Text(row.leadTimeDays)),
                      DataCell(Text(row.effectiveFrom)),
                      DataCell(Text(row.isCurrent ? 'In force' : 'Past')),
                    ],
                  ),
              ],
            ),
          ),
      ],
    );
  }
}

class _AddCatalogueRowDialog extends StatefulWidget {
  const _AddCatalogueRowDialog({required this.api, required this.vendorId});

  final ApiClient api;
  final String vendorId;

  @override
  State<_AddCatalogueRowDialog> createState() => _AddCatalogueRowDialogState();
}

class _AddCatalogueRowDialogState extends State<_AddCatalogueRowDialog>
    with SaveInDialog {
  final TextEditingController _supplierCode = TextEditingController();
  final TextEditingController _supplierName = TextEditingController();
  final TextEditingController _price = TextEditingController();
  final TextEditingController _pack = TextEditingController();
  final TextEditingController _minimum = TextEditingController();
  final TextEditingController _multiple = TextEditingController();
  final TextEditingController _lead = TextEditingController();
  final TextEditingController _remarks = TextEditingController();
  List<Product> _products = const <Product>[];
  String? _productId;
  DateTime _from = DateTime.now();
  String? _problem;

  @override
  void initState() {
    super.initState();
    unawaited(_loadProducts());
  }

  Future<void> _loadProducts() async {
    try {
      final List<Product> products = await fetchAllPages<Product>(
        (page) => widget.api.products(page: page, pageSize: 100),
      );
      if (mounted) setState(() => _products = products);
    } on ApiException {
      // The picker stays empty and Save says a product is needed.
    }
  }

  @override
  void dispose() {
    _supplierCode.dispose();
    _supplierName.dispose();
    _price.dispose();
    _pack.dispose();
    _minimum.dispose();
    _multiple.dispose();
    _lead.dispose();
    _remarks.dispose();
    super.dispose();
  }

  String _iso(DateTime date) => date.toIso8601String().substring(0, 10);

  Future<void> _pickDate() async {
    final DateTime? picked = await showDatePicker(
      context: context,
      initialDate: _from,
      firstDate: DateTime(2000),
      lastDate: DateTime(2100),
    );
    if (picked != null) setState(() => _from = picked);
  }

  void _save() {
    if (_productId == null) {
      setState(() => _problem = 'Choose the product.');
      return;
    }
    setState(() => _problem = null);
    final Json body = <String, dynamic>{
      'product_id': _productId,
      'effective_from': _iso(_from),
    };
    void put(String key, TextEditingController controller) {
      final String value = controller.text.trim();
      if (value.isNotEmpty) body[key] = value;
    }

    put('supplier_product_code', _supplierCode);
    put('supplier_product_name', _supplierName);
    put('unit_price', _price);
    put('pack_size', _pack);
    put('minimum_order_quantity', _minimum);
    put('order_multiple', _multiple);
    put('lead_time_days', _lead);
    put('remarks', _remarks);
    unawaited(saveAndClose<bool>(() async {
      await widget.api.addSupplierCatalogueRow(widget.vendorId, body);
      return true;
    }));
  }

  Widget _field(String key, String label, TextEditingController controller,
          {bool number = false, int lines = 1}) =>
      Padding(
        padding: const EdgeInsets.only(top: 12),
        child: TextField(
          key: ValueKey<String>(key),
          controller: controller,
          maxLines: lines,
          keyboardType: number ? TextInputType.number : null,
          decoration: InputDecoration(labelText: label),
        ),
      );

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: const Text('Add catalogue row'),
        content: SizedBox(
          width: 460,
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                saveErrorBanner(),
                if (_problem != null)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 8),
                    child: Text(
                      _problem!,
                      style: TextStyle(
                          color: Theme.of(context).colorScheme.error),
                    ),
                  ),
                DropdownButtonFormField<String>(
                  key: const ValueKey('catalogue-product'),
                  isExpanded: true,
                  initialValue: _productId,
                  decoration: const InputDecoration(labelText: 'Product'),
                  items: [
                    for (final Product p in _products)
                      DropdownMenuItem<String>(
                        value: p.id,
                        child: Text(
                          '${p.code} ${p.name}',
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                  ],
                  onChanged: (value) => setState(() => _productId = value),
                ),
                _field('catalogue-supplier-code', 'Supplier code',
                    _supplierCode),
                _field('catalogue-supplier-name', 'Supplier name',
                    _supplierName),
                _field('catalogue-price', 'Unit price', _price, number: true),
                _field('catalogue-pack', 'Pack size', _pack, number: true),
                _field('catalogue-minimum', 'Minimum order', _minimum,
                    number: true),
                _field('catalogue-multiple', 'Order multiple', _multiple,
                    number: true),
                _field('catalogue-lead', 'Lead time (days)', _lead,
                    number: true),
                const SizedBox(height: 12),
                InkWell(
                  key: const ValueKey('catalogue-from'),
                  onTap: _pickDate,
                  child: InputDecorator(
                    decoration: const InputDecoration(
                      labelText: 'Effective from',
                      helperText: 'A change is a new row from a later date',
                      helperMaxLines: 2,
                      suffixIcon: Icon(Icons.calendar_today, size: 18),
                    ),
                    child: Text(_iso(_from)),
                  ),
                ),
                _field('catalogue-remarks', 'Remarks', _remarks, lines: 2),
              ],
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: cancelHandler,
            child: const Text('Cancel'),
          ),
          FilledButton(
            key: const ValueKey('catalogue-save'),
            onPressed: saving ? null : _save,
            child: const Text('Save'),
          ),
        ],
      );
}
