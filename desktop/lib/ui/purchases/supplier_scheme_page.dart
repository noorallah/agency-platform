// Supplier free schemes (PG-11): buy so many of a product from a supplier, get
// so many free. A scheme with no supplier holds for every supplier. Phase 2
// only.

import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/preferences/desktop_preferences_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/entities.dart';
import '../../models/product.dart';
import '../../models/supplier_scheme.dart';
import '../../models/vendor.dart';
import '../workspace/desktop_framework.dart';
import 'purchase_requisition_page.dart' show ProductSearchBox;

String _vendorName(Vendor v) => v.displayName.isEmpty ? v.name : v.displayName;

String _today() => DateTime.now().toIso8601String().split('T').first;

String _productText(String code, String name) =>
    code.isEmpty && name.isEmpty ? '' : '$code · $name';

/// List the schemes suppliers run, and raise, change and remove them.
class SupplierSchemePage extends StatefulWidget {
  const SupplierSchemePage({
    super.key,
    required this.api,
    required this.preferences,
    required this.permissions,
    required this.hasActiveFirm,
  });

  final ApiClient api;
  final DesktopPreferencesService preferences;
  final PermissionService permissions;
  final bool hasActiveFirm;

  @override
  State<SupplierSchemePage> createState() => _SupplierSchemePageState();
}

class _SupplierSchemePageState extends State<SupplierSchemePage> {
  List<SupplierScheme> _rows = const [];
  String? _error;
  String? _selectedId;
  bool _loading = true;

  /// '' all, 'true' active only, 'false' switched off only.
  String _active = '';

  bool _may(String code) => widget.permissions.hasPermission(code);
  bool get _mayView => _may('SUPPLIER_SCHEME_VIEW');
  bool get _mayManage => _may('SUPPLIER_SCHEME_MANAGE');

  @override
  void initState() {
    super.initState();
    if (widget.hasActiveFirm && _mayView) unawaited(_load());
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final PagedResult<SupplierScheme> page = await widget.api
          .supplierSchemes(isActive: _active.isEmpty ? null : _active == 'true');
      if (!mounted) return;
      setState(() {
        _rows = page.items;
        _loading = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.message;
        _loading = false;
      });
    }
  }

  SupplierScheme? get _selected =>
      _rows.where((row) => row.id == _selectedId).firstOrNull;

  void _say(String message, {bool error = false}) {
    if (!mounted) return;
    NotificationService.show(
      context,
      message,
      kind: error ? AppNotificationKind.error : AppNotificationKind.success,
    );
  }

  Future<void> _edit(SupplierScheme? row) async {
    if (row != null && !_mayManage) return;
    final SupplierScheme? saved = await showDialog<SupplierScheme>(
      context: context,
      barrierDismissible: false,
      builder: (_) => SupplierSchemeDialog(api: widget.api, existing: row),
    );
    if (saved == null || !mounted) return;
    _say('Scheme ${saved.label} saved.');
    _selectedId = saved.id;
    await _load();
  }

  Future<void> _delete(SupplierScheme row) async {
    final bool? sure = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('Delete scheme ${row.label}'),
        content: const Text(
            'Orders already raised keep the free goods they were given.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text('Keep'),
          ),
          FilledButton(
            key: const ValueKey('ss-delete-confirm'),
            onPressed: () => Navigator.of(ctx).pop(true),
            child: const Text('Delete'),
          ),
        ],
      ),
    );
    if (sure != true) return;
    try {
      await widget.api.deleteSupplierScheme(row.id);
      _say('Scheme ${row.label} deleted.');
      _selectedId = null;
      await _load();
    } on ApiException catch (error) {
      _say(error.message, error: true);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.hasActiveFirm) {
      return const WorkspaceEmptyState(
        title: 'Choose a firm',
        message: 'Supplier schemes belong to one firm.',
      );
    }
    if (!_mayView) {
      return const WorkspaceEmptyState(
        icon: Icons.lock_outline,
        title: 'You cannot see supplier schemes',
        message: 'Reading them needs the view supplier schemes permission.',
      );
    }
    final SupplierScheme? picked = _selected;
    return ManagementWorkspaceLayout(
      notice: 'A scheme gives free goods for buying so many, such as 10+2. '
          'A purchase order that earns one is offered the free goods.',
      toolbar: _toolbar(picked),
      searchPanel: const SizedBox.shrink(),
      selectionBar: true,
      selection: picked == null
          ? null
          : SelectionSummary.document(
              number: picked.label,
              status: picked.isActive ? 'ACTIVE' : 'INACTIVE',
              onClear: () => setState(() => _selectedId = null),
            ),
      primaryContent: _content(),
      statusBar: WorkspaceStatusBar(
        total: _rows.length,
        selected: _selectedId != null,
        message: 'Supplier schemes',
      ),
    );
  }

  Widget _content() {
    if (_loading) return const Center(child: CircularProgressIndicator());
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (_error != null) ...[
          const SizedBox(height: AppSpacing.sm),
          Text(_error!,
              style: TextStyle(color: Theme.of(context).colorScheme.error)),
        ],
        const SizedBox(height: AppSpacing.sm),
        Expanded(child: _grid()),
      ],
    );
  }

  WorkspaceToolbar _toolbar(SupplierScheme? row) => WorkspaceToolbar(
        trailing: [
          Phase2MenuChip<String>(
            key: const ValueKey('ss-active-filter'),
            label: 'Show: ${switch (_active) {
              'true' => 'Active',
              'false' => 'Switched off',
              _ => 'All',
            }}',
            itemBuilder: (_) => const [
              PopupMenuItem<String>(value: '', child: Text('All')),
              PopupMenuItem<String>(value: 'true', child: Text('Active')),
              PopupMenuItem<String>(
                  value: 'false', child: Text('Switched off')),
            ],
            onSelected: (value) {
              setState(() {
                _active = value;
                _selectedId = null;
              });
              unawaited(_load());
            },
          ),
        ],
        actions: [
          if (_mayManage) ToolbarAction.newItem,
          if (_mayManage) ToolbarAction.edit,
          ToolbarAction.refresh,
        ],
        isEnabled: (action) => action != ToolbarAction.edit || row != null,
        onAction: (action) {
          switch (action) {
            case ToolbarAction.newItem:
              unawaited(_edit(null));
            case ToolbarAction.edit:
              if (row != null) unawaited(_edit(row));
            default:
              unawaited(_load());
          }
        },
        commands: [
          if (_mayManage)
            ToolbarCommand(
              id: 'delete',
              label: 'Delete',
              icon: Icons.delete_outline,
              onPressed: row == null ? null : () => unawaited(_delete(row)),
            ),
        ],
      );

  late final ColumnChoice<SupplierScheme> _columns = ColumnChoice(
    preferences: widget.preferences,
    stateKey: 'supplier-schemes.grid',
    columns: [
      ChoosableColumn(
        column: const GridColumn(key: 'scheme', label: 'Scheme'),
        cell: (item) => item.label,
        required: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'supplier', label: 'Supplier'),
        cell: (item) =>
            item.vendorId.isEmpty ? 'All suppliers' : item.vendorName,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'product', label: 'Product'),
        cell: (item) => _productText(item.productCode, item.productName),
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'free', label: 'Free product'),
        cell: (item) => item.freeProductId.isEmpty
            ? 'Same product'
            : _productText(item.freeProductCode, item.freeProductName),
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'from', label: 'Valid from'),
        cell: (item) => item.validFrom,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'to', label: 'Valid to'),
        cell: (item) => item.validTo.isEmpty ? 'Open' : item.validTo,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'status', label: 'Status'),
        cell: (item) => !item.isActive
            ? 'Switched off'
            : item.inForce
                ? 'In force'
                : 'Not in force',
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'notes', label: 'Notes', priority: 1),
        cell: (item) => item.notes,
      ),
    ],
  );

  Widget _grid() {
    if (_rows.isEmpty) {
      return const WorkspaceEmptyState(
        title: 'No supplier schemes',
        message: 'Record the free goods a supplier gives, such as 10+2.',
      );
    }
    return EnterpriseDataGrid<SupplierScheme>(
      items: _rows,
      total: _rows.length,
      pageOffset: 0,
      rowsPerPage: _rows.length,
      availableRowsPerPage: [_rows.length],
      selectedId: _selectedId,
      columns: _columns.gridColumns,
      id: (row) => row.id,
      cells: _columns.cells,
      onSelect: (row) => setState(() => _selectedId = row.id),
      onOpen: (row) {
        setState(() => _selectedId = row.id);
        unawaited(_edit(row));
      },
      onPageChanged: (_) {},
    );
  }
}

/// Raise or change a scheme. Pops the saved [SupplierScheme]; stays open with
/// the server's message when refused. Nothing is prefilled except the start
/// date: a blank free product means the same product, a blank end date means
/// no end, and "All suppliers" means every supplier.
class SupplierSchemeDialog extends StatefulWidget {
  const SupplierSchemeDialog({super.key, required this.api, this.existing});

  final ApiClient api;
  final SupplierScheme? existing;

  @override
  State<SupplierSchemeDialog> createState() => _SupplierSchemeDialogState();
}

class _SupplierSchemeDialogState extends State<SupplierSchemeDialog>
    with SaveInDialog<SupplierSchemeDialog> {
  List<Vendor> _vendors = const [];
  String _vendorId = '';
  String _productId = '';
  String _freeProductId = '';
  late String _validFrom;
  String _validTo = '';
  bool _active = true;
  bool _loading = true;
  String? _problem;
  final TextEditingController _product = TextEditingController();
  final TextEditingController _freeProduct = TextEditingController();
  final TextEditingController _buy = TextEditingController();
  final TextEditingController _free = TextEditingController();
  final TextEditingController _notes = TextEditingController();

  @override
  void initState() {
    super.initState();
    final SupplierScheme? s = widget.existing;
    _validFrom = s != null && s.validFrom.isNotEmpty ? s.validFrom : _today();
    if (s != null) {
      _vendorId = s.vendorId;
      _productId = s.productId;
      _freeProductId = s.freeProductId;
      _validTo = s.validTo;
      _active = s.isActive;
      _product.text = _productText(s.productCode, s.productName);
      _freeProduct.text = _productText(s.freeProductCode, s.freeProductName);
      _buy.text = s.buyQuantity;
      _free.text = s.freeQuantity;
      _notes.text = s.notes;
    }
    unawaited(_loadVendors());
  }

  @override
  void dispose() {
    _product.dispose();
    _freeProduct.dispose();
    _buy.dispose();
    _free.dispose();
    _notes.dispose();
    super.dispose();
  }

  Future<void> _loadVendors() async {
    try {
      final List<Vendor> vendors =
          await fetchAllPages((page) => widget.api.vendors(page: page));
      if (!mounted) return;
      setState(() {
        _vendors = vendors;
        _loading = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        saveError = error.message;
        _loading = false;
      });
    }
  }

  void _save() {
    String? problem;
    final String buy = _buy.text.trim();
    final String free = _free.text.trim();
    final double? buyNumber = double.tryParse(buy);
    final double? freeNumber = double.tryParse(free);
    if (_productId.isEmpty) problem = 'Choose the product that is bought.';
    if (buyNumber == null || buyNumber <= 0) {
      problem ??= 'Say how many must be bought.';
    }
    if (freeNumber == null || freeNumber <= 0) {
      problem ??= 'Say how many come free.';
    }
    if (_validTo.isNotEmpty && _validTo.compareTo(_validFrom) < 0) {
      problem ??= 'The scheme cannot end before it starts.';
    }
    setState(() => _problem = problem);
    if (problem != null) return;
    final String notes = _notes.text.trim();
    // Every field is named so an edit can clear one: null is "every
    // supplier", "same product", "no end" and "no note".
    final Json body = <String, dynamic>{
      'vendor_id': _vendorId.isEmpty ? null : _vendorId,
      'product_id': _productId,
      'buy_quantity': buy,
      'free_quantity': free,
      'free_product_id': _freeProductId.isEmpty ? null : _freeProductId,
      'valid_from': _validFrom,
      'valid_to': _validTo.isEmpty ? null : _validTo,
      'is_active': _active,
      'notes': notes.isEmpty ? null : notes,
    };
    final SupplierScheme? existing = widget.existing;
    unawaited(saveAndClose<SupplierScheme>(() => existing == null
        ? widget.api.createSupplierScheme(body)
        : widget.api.updateSupplierScheme(existing.id, body,
            expectedVersion: existing.version)));
  }

  Widget _dateBox(String label, String value, VoidCallback? onTap, Key key) =>
      InkWell(
        key: key,
        onTap: onTap,
        child: InputDecorator(
          decoration: InputDecoration(
            labelText: label,
            isDense: true,
            suffixIcon: const Icon(Icons.event, size: 16),
          ),
          child: Text(value.isEmpty ? '—' : value),
        ),
      );

  Future<String?> _pick(String current) async {
    final DateTime? picked = await showDatePicker(
      context: context,
      initialDate: DateTime.tryParse(current) ?? DateTime.now(),
      firstDate: DateTime(2000),
      lastDate: DateTime(2100),
    );
    return picked?.toIso8601String().split('T').first;
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final bool locked = saving;
    final double width =
        (MediaQuery.sizeOf(context).width - 120).clamp(400.0, 720.0);
    return AlertDialog(
      title: Text(widget.existing == null
          ? 'New supplier scheme'
          : 'Scheme ${widget.existing!.label}'),
      content: ConstrainedBox(
        constraints: BoxConstraints(maxWidth: width, maxHeight: 460),
        child: SizedBox(
          width: width,
          child: _loading
              ? const Center(child: CircularProgressIndicator())
              : SingleChildScrollView(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      saveErrorBanner(),
                      if (_problem != null)
                        Padding(
                          padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                          child: Text(_problem!,
                              key: const ValueKey('ss-problem'),
                              style: TextStyle(color: theme.colorScheme.error)),
                        ),
                      DropdownButtonFormField<String>(
                        key: const ValueKey('ss-vendor'),
                        initialValue: _vendorId,
                        isExpanded: true,
                        decoration: const InputDecoration(
                            labelText: 'Supplier', isDense: true),
                        items: [
                          const DropdownMenuItem(
                              value: '', child: Text('All suppliers')),
                          for (final Vendor v in _vendors)
                            DropdownMenuItem(
                              value: v.id,
                              child: Text(_vendorName(v),
                                  overflow: TextOverflow.ellipsis),
                            ),
                        ],
                        onChanged: locked
                            ? null
                            : (v) => setState(() => _vendorId = v ?? ''),
                      ),
                      const SizedBox(height: AppSpacing.md),
                      ProductSearchBox(
                        fieldKey: const ValueKey('ss-product'),
                        api: widget.api,
                        controller: _product,
                        enabled: !locked,
                        onPicked: (Product p) => _productId = p.id,
                        onCleared: () => _productId = '',
                      ),
                      const SizedBox(height: AppSpacing.md),
                      Row(children: [
                        Expanded(
                          child: TextField(
                            key: const ValueKey('ss-buy'),
                            controller: _buy,
                            enabled: !locked,
                            keyboardType: const TextInputType.numberWithOptions(
                                decimal: true),
                            decoration: const InputDecoration(
                                labelText: 'Buy quantity', isDense: true),
                          ),
                        ),
                        const SizedBox(width: AppSpacing.md),
                        Expanded(
                          child: TextField(
                            key: const ValueKey('ss-free'),
                            controller: _free,
                            enabled: !locked,
                            keyboardType: const TextInputType.numberWithOptions(
                                decimal: true),
                            decoration: const InputDecoration(
                                labelText: 'Free quantity', isDense: true),
                          ),
                        ),
                      ]),
                      const SizedBox(height: AppSpacing.md),
                      Text('Free product', style: theme.textTheme.labelMedium),
                      const SizedBox(height: AppSpacing.xs),
                      ProductSearchBox(
                        fieldKey: const ValueKey('ss-free-product'),
                        api: widget.api,
                        controller: _freeProduct,
                        enabled: !locked,
                        onPicked: (Product p) => _freeProductId = p.id,
                        onCleared: () => _freeProductId = '',
                      ),
                      Text('Blank: the same product is given free.',
                          style: theme.textTheme.bodySmall),
                      const SizedBox(height: AppSpacing.md),
                      Row(children: [
                        Expanded(
                          child: _dateBox(
                            'Valid from',
                            _validFrom,
                            locked
                                ? null
                                : () async {
                                    final String? v = await _pick(_validFrom);
                                    if (v != null) {
                                      setState(() => _validFrom = v);
                                    }
                                  },
                            const ValueKey('ss-valid-from'),
                          ),
                        ),
                        const SizedBox(width: AppSpacing.md),
                        Expanded(
                          child: _dateBox(
                            'Valid to (blank: no end)',
                            _validTo,
                            locked
                                ? null
                                : () async {
                                    final String? v = await _pick(
                                        _validTo.isEmpty ? _validFrom : _validTo);
                                    if (v != null) {
                                      setState(() => _validTo = v);
                                    }
                                  },
                            const ValueKey('ss-valid-to'),
                          ),
                        ),
                        IconButton(
                          key: const ValueKey('ss-clear-valid-to'),
                          tooltip: 'No end date',
                          onPressed: locked || _validTo.isEmpty
                              ? null
                              : () => setState(() => _validTo = ''),
                          icon: const Icon(Icons.clear, size: 16),
                        ),
                      ]),
                      const SizedBox(height: AppSpacing.md),
                      TextField(
                        key: const ValueKey('ss-notes'),
                        controller: _notes,
                        enabled: !locked,
                        decoration: const InputDecoration(
                            labelText: 'Notes', isDense: true),
                      ),
                      CheckboxListTile(
                        key: const ValueKey('ss-active'),
                        contentPadding: EdgeInsets.zero,
                        controlAffinity: ListTileControlAffinity.leading,
                        title: const Text('Active'),
                        value: _active,
                        onChanged: locked
                            ? null
                            : (v) => setState(() => _active = v ?? true),
                      ),
                    ],
                  ),
                ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: saving ? null : () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
        FilledButton(
          key: const ValueKey('ss-save'),
          onPressed: saving ? null : _save,
          child: const Text('Save'),
        ),
      ],
    );
  }
}
