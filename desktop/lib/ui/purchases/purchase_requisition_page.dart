// Purchase requisitions (BUY-7): a request to buy, raised by whoever sees the
// need -- a storeman, an inventory manager -- and approved by a buyer before
// it becomes draft purchase orders, one per supplier. Phase 2 only.

import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/preferences/desktop_preferences_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/branch_warehouse.dart';
import '../../models/entities.dart';
import '../../models/product.dart';
import '../../models/purchase_requisition.dart';
import '../../models/vendor.dart';
import '../workspace/desktop_framework.dart';
import '../workspace/reason_prompt.dart';

/// List requisitions and raise, send, approve, cancel and convert them.
class PurchaseRequisitionPage extends StatefulWidget {
  const PurchaseRequisitionPage({
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
  State<PurchaseRequisitionPage> createState() =>
      _PurchaseRequisitionPageState();
}

class _PurchaseRequisitionPageState extends State<PurchaseRequisitionPage> {
  List<PurchaseRequisition> _rows = const [];
  String? _error;
  String? _selectedId;
  bool _loading = true;
  String _status = '';

  bool _may(String code) => widget.permissions.hasPermission(code);
  bool get _mayView =>
      _may('PURCHASE_VIEW') || _may('PURCHASE_REQUISITION_CREATE');
  bool get _mayRaise => _may('PURCHASE_REQUISITION_CREATE');

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
      final List<PurchaseRequisition> rows =
          await widget.api.listPurchaseRequisitions(status: _status);
      if (!mounted) return;
      setState(() {
        _rows = rows;
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

  PurchaseRequisition? get _selected =>
      _rows.where((row) => row.id == _selectedId).firstOrNull;

  void _say(String message, {bool error = false}) {
    if (!mounted) return;
    NotificationService.show(
      context,
      message,
      kind: error ? AppNotificationKind.error : AppNotificationKind.success,
    );
  }

  Future<void> _edit(PurchaseRequisition? row) async {
    final PurchaseRequisition? saved = await showDialog<PurchaseRequisition>(
      context: context,
      barrierDismissible: false,
      builder: (_) => RequisitionDialog(api: widget.api, existing: row),
    );
    if (saved == null || !mounted) return;
    _say('${saved.number} saved.');
    _selectedId = saved.id;
    await _load();
  }

  Future<void> _act(PurchaseRequisition row, String action) async {
    String? reason;
    if (action == 'cancel') {
      reason = await askForReason(
        context,
        title: 'Cancel ${row.number}',
        explanation: 'The reason stays on the requisition.',
        confirmLabel: 'Cancel requisition',
        cancelLabel: 'Keep',
      );
      if (reason == null) return;
    }
    try {
      await widget.api.actOnPurchaseRequisition(row.id, action, reason: reason);
      final String done = switch (action) {
        'submit' => 'sent for approval',
        'approve' => 'approved',
        _ => 'cancelled',
      };
      _say('${row.number} $done.');
      await _load();
    } on ApiException catch (error) {
      _say(error.message, error: true);
    }
  }

  Future<void> _convert(PurchaseRequisition row) async {
    try {
      final List<Json> orders =
          await widget.api.convertPurchaseRequisition(row.id);
      _say('${row.number}: ${orders.length} purchase '
          '${orders.length == 1 ? 'order' : 'orders'} raised.');
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
        message: 'Requisitions belong to one firm.',
      );
    }
    if (!_mayView) {
      return const WorkspaceEmptyState(
        icon: Icons.lock_outline,
        title: 'You cannot see requisitions',
        message: 'Reading them needs the view purchases permission.',
      );
    }
    final PurchaseRequisition? picked = _selected;
    return ManagementWorkspaceLayout(
      notice: 'A requisition asks for goods to be bought. Send it for '
          'approval, and once approved it is converted into draft purchase '
          'orders, one per supplier.',
      toolbar: _toolbar(picked),
      searchPanel: const SizedBox.shrink(),
      selectionBar: true,
      selection: picked == null
          ? null
          : SelectionSummary.document(
              number: picked.number,
              status: picked.status,
              onClear: () => setState(() => _selectedId = null),
            ),
      primaryContent: _content(),
      statusBar: WorkspaceStatusBar(
        total: _rows.length,
        selected: _selectedId != null,
        message: 'Requisitions',
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
        const SizedBox(height: AppSpacing.md),
        Expanded(child: _grid()),
      ],
    );
  }

  WorkspaceToolbar _toolbar(PurchaseRequisition? row) {
    final String status = row?.status ?? '';
    return WorkspaceToolbar(
      trailing: [
        Phase2MenuChip<String>(
          key: const ValueKey('requisition-status-filter'),
          label: 'Show: ${_status.isEmpty ? 'All' : _words(_status)}',
          itemBuilder: (_) => const [
            PopupMenuItem<String>(value: '', child: Text('All')),
            PopupMenuItem<String>(value: 'DRAFT', child: Text('Draft')),
            PopupMenuItem<String>(value: 'SUBMITTED', child: Text('Submitted')),
            PopupMenuItem<String>(value: 'APPROVED', child: Text('Approved')),
            PopupMenuItem<String>(value: 'ORDERED', child: Text('Ordered')),
            PopupMenuItem<String>(value: 'CANCELLED', child: Text('Cancelled')),
          ],
          onSelected: (value) {
            setState(() {
              _status = value;
              _selectedId = null;
            });
            unawaited(_load());
          },
        ),
      ],
      actions: [
        if (_mayRaise) ToolbarAction.newItem,
        if (_mayRaise) ToolbarAction.edit,
        ToolbarAction.refresh,
      ],
      isEnabled: (action) =>
          action != ToolbarAction.edit || (row != null && row.isEditable),
      onAction: (action) {
        switch (action) {
          case ToolbarAction.newItem:
            unawaited(_edit(null));
          case ToolbarAction.edit:
            if (row != null && row.isEditable) unawaited(_edit(row));
          default:
            unawaited(_load());
        }
      },
      commands: [
        if (_mayRaise)
          ToolbarCommand(
            id: 'submit',
            label: 'Submit',
            icon: Icons.send_outlined,
            onPressed: row != null && status == 'DRAFT'
                ? () => unawaited(_act(row, 'submit'))
                : null,
          ),
        if (_may('PURCHASE_APPROVE'))
          ToolbarCommand(
            id: 'approve',
            label: 'Approve',
            icon: Icons.verified_outlined,
            onPressed: row != null && status == 'SUBMITTED'
                ? () => unawaited(_act(row, 'approve'))
                : null,
          ),
        if (_may('PURCHASE_CREATE'))
          ToolbarCommand(
            id: 'convert',
            label: 'Convert to orders',
            icon: Icons.shopping_cart_checkout_outlined,
            onPressed: row != null && status == 'APPROVED'
                ? () => unawaited(_convert(row))
                : null,
          ),
        if (_mayRaise)
          ToolbarCommand(
            id: 'cancel',
            label: 'Cancel',
            icon: Icons.cancel_outlined,
            onPressed:
                row != null && status != 'CANCELLED' && status != 'ORDERED'
                    ? () => unawaited(_act(row, 'cancel'))
                    : null,
          ),
      ],
    );
  }

  late final ColumnChoice<PurchaseRequisition> _columns = ColumnChoice(
    preferences: widget.preferences,
    stateKey: 'purchase-requisitions.grid',
    columns: [
      ChoosableColumn(
        column: const GridColumn(key: 'number', label: 'Number'),
        cell: (item) => item.number,
        required: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'date', label: 'Date'),
        cell: (item) => item.date,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column:
            const GridColumn(key: 'needed', label: 'Needed by', priority: 1),
        cell: (item) => item.neededBy,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'status', label: 'Status'),
        cell: (item) => _words(item.status),
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'lines', label: 'Lines', numeric: true),
        cell: (item) => '${item.lines.length}',
        shownByDefault: true,
      ),
    ],
  );

  Widget _grid() {
    if (_rows.isEmpty) {
      return const WorkspaceEmptyState(
        title: 'No requisitions',
        message: 'Raise one here, or from Below reorder level on the '
            'purchase orders screen.',
      );
    }
    return EnterpriseDataGrid<PurchaseRequisition>(
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
        if (row.isEditable && _mayRaise) unawaited(_edit(row));
      },
      onPageChanged: (_) {},
    );
  }
}

String _words(String status) =>
    status.isEmpty ? '' : status[0] + status.substring(1).toLowerCase();

/// One line being typed: its boxes belong to the dialog that shows it.
class _LineDraft {
  _LineDraft({
    this.productId = '',
    String product = '',
    String quantity = '',
    this.vendorId = '',
    String remarks = '',
  })  : product = TextEditingController(text: product),
        quantity = TextEditingController(text: quantity),
        remarks = TextEditingController(text: remarks);

  String productId;
  String vendorId;
  final TextEditingController product;
  final TextEditingController quantity;
  final TextEditingController remarks;

  void dispose() {
    product.dispose();
    quantity.dispose();
    remarks.dispose();
  }
}

/// Raise or change a requisition. Pops the saved [PurchaseRequisition]; stays
/// open with the server's message when refused.
class RequisitionDialog extends StatefulWidget {
  const RequisitionDialog({super.key, required this.api, this.existing});

  final ApiClient api;
  final PurchaseRequisition? existing;

  @override
  State<RequisitionDialog> createState() => _RequisitionDialogState();
}

class _RequisitionDialogState extends State<RequisitionDialog>
    with SaveInDialog<RequisitionDialog> {
  List<BranchRecord> _branches = const [];
  List<WarehouseRecord> _warehouses = const [];
  List<Vendor> _vendors = const [];
  String _branchId = '';
  String _warehouseId = '';
  late String _date;
  String _neededBy = '';
  final TextEditingController _remarks = TextEditingController();
  final List<_LineDraft> _lines = <_LineDraft>[];
  String? _problem;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    final PurchaseRequisition? existing = widget.existing;
    _date = existing != null && existing.date.isNotEmpty
        ? existing.date
        : DateTime.now().toIso8601String().split('T').first;
    if (existing != null) {
      _branchId = existing.branchId;
      _warehouseId = existing.warehouseId;
      _neededBy = existing.neededBy;
      _remarks.text = existing.remarks;
      for (final RequisitionLine line in existing.lines) {
        _lines.add(_LineDraft(
          productId: line.productId,
          product: '${line.productCode} · ${line.productName}',
          quantity: line.quantity,
          vendorId: line.vendorId,
          remarks: line.remarks,
        ));
      }
    }
    if (_lines.isEmpty) _lines.add(_LineDraft());
    unawaited(_loadMasters());
  }

  @override
  void dispose() {
    _remarks.dispose();
    for (final _LineDraft line in _lines) {
      line.dispose();
    }
    super.dispose();
  }

  Future<void> _loadMasters() async {
    try {
      final List<BranchRecord> branches = await fetchAllPages(
          (page) => widget.api.branches(page: page, pageSize: 100));
      final List<WarehouseRecord> warehouses = await fetchAllPages(
          (page) => widget.api.warehouses(page: page, pageSize: 100));
      final List<Vendor> vendors =
          await fetchAllPages((page) => widget.api.vendors(page: page));
      if (!mounted) return;
      setState(() {
        _branches = branches;
        _warehouses = warehouses;
        _vendors = vendors;
        if (_branchId.isEmpty && branches.length == 1) {
          _branchId = branches.single.id;
        }
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

  List<WarehouseRecord> get _branchWarehouses =>
      _warehouses.where((w) => w.branchId == _branchId).toList();

  Future<void> _pickDate(String current, ValueChanged<String> onPicked) async {
    final DateTime? picked = await showDatePicker(
      context: context,
      initialDate: DateTime.tryParse(current) ?? DateTime.now(),
      firstDate: DateTime(2000),
      lastDate: DateTime(2100),
    );
    if (picked != null) onPicked(picked.toIso8601String().split('T').first);
  }

  void _save() {
    String? problem;
    if (_branchId.isEmpty || _warehouseId.isEmpty) {
      problem = 'Choose the branch and the warehouse the goods are for.';
    }
    final List<Json> lines = <Json>[];
    for (final _LineDraft line in _lines) {
      if (line.productId.isEmpty && line.quantity.text.trim().isEmpty) continue;
      final double? quantity = double.tryParse(line.quantity.text.trim());
      if (line.productId.isEmpty || quantity == null || quantity <= 0) {
        problem ??= 'Each line needs a product and a quantity above zero.';
        continue;
      }
      final String remarks = line.remarks.text.trim();
      lines.add(<String, dynamic>{
        'product_id': line.productId,
        'quantity': line.quantity.text.trim(),
        if (line.vendorId.isNotEmpty) 'vendor_id': line.vendorId,
        if (remarks.isNotEmpty) 'remarks': remarks,
      });
    }
    if (lines.isEmpty) problem ??= 'Add at least one line.';
    setState(() => _problem = problem);
    if (problem != null) return;
    final String remarks = _remarks.text.trim();
    final Json body = <String, dynamic>{
      'branch_id': _branchId,
      'warehouse_id': _warehouseId,
      'requisition_date': _date,
      if (_neededBy.isNotEmpty) 'needed_by': _neededBy,
      if (remarks.isNotEmpty) 'remarks': remarks,
      'lines': lines,
    };
    final PurchaseRequisition? existing = widget.existing;
    unawaited(saveAndClose<PurchaseRequisition>(() => existing == null
        ? widget.api.createPurchaseRequisition(body)
        : widget.api.updatePurchaseRequisition(existing.id, body,
            expectedVersion: existing.version)));
  }

  Widget _dateBox(
    String label,
    String value,
    ValueChanged<String> onPicked, {
    Key? key,
  }) =>
      InkWell(
        key: key,
        onTap: saving ? null : () => _pickDate(value, onPicked),
        child: InputDecorator(
          decoration: InputDecoration(
            labelText: label,
            isDense: true,
            suffixIcon: const Icon(Icons.event, size: 16),
          ),
          child: Text(value.isEmpty ? '—' : value),
        ),
      );

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final List<WarehouseRecord> warehouses = _branchWarehouses;
    return AlertDialog(
      title: Text(widget.existing == null
          ? 'New requisition'
          : 'Requisition ${widget.existing!.number}'),
      content: SizedBox(
        width: 820,
        height: 460,
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
                            key: const ValueKey('requisition-problem'),
                            style: TextStyle(color: theme.colorScheme.error)),
                      ),
                    if (widget.existing?.status == 'SUBMITTED')
                      Padding(
                        padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                        child: Text(
                          'Saving sends it back to draft to be submitted '
                          'again.',
                          style: theme.textTheme.bodySmall,
                        ),
                      ),
                    Row(children: [
                      Expanded(
                        child: DropdownButtonFormField<String>(
                          key: const ValueKey('requisition-branch'),
                          initialValue: _branchId.isEmpty ? null : _branchId,
                          isExpanded: true,
                          decoration: const InputDecoration(
                              labelText: 'Branch', isDense: true),
                          items: [
                            for (final BranchRecord b in _branches)
                              DropdownMenuItem(
                                  value: b.id, child: Text(b.name)),
                          ],
                          onChanged: saving
                              ? null
                              : (v) => setState(() {
                                    _branchId = v ?? '';
                                    _warehouseId = '';
                                  }),
                        ),
                      ),
                      const SizedBox(width: AppSpacing.md),
                      Expanded(
                        child: DropdownButtonFormField<String>(
                          key: ValueKey('requisition-warehouse-$_branchId'),
                          initialValue:
                              _warehouseId.isEmpty ? null : _warehouseId,
                          isExpanded: true,
                          decoration: const InputDecoration(
                              labelText: 'Warehouse', isDense: true),
                          items: [
                            for (final WarehouseRecord w in warehouses)
                              DropdownMenuItem(
                                  value: w.id, child: Text(w.name)),
                          ],
                          onChanged: saving
                              ? null
                              : (v) => setState(() => _warehouseId = v ?? ''),
                        ),
                      ),
                    ]),
                    const SizedBox(height: AppSpacing.md),
                    Row(children: [
                      Expanded(
                        child: _dateBox(
                            'Date', _date, (v) => setState(() => _date = v),
                            key: const ValueKey('requisition-date')),
                      ),
                      const SizedBox(width: AppSpacing.md),
                      Expanded(
                        child: _dateBox('Needed by', _neededBy,
                            (v) => setState(() => _neededBy = v),
                            key: const ValueKey('requisition-needed-by')),
                      ),
                      const SizedBox(width: AppSpacing.md),
                      Expanded(
                        flex: 2,
                        child: TextField(
                          key: const ValueKey('requisition-remarks'),
                          controller: _remarks,
                          enabled: !saving,
                          decoration: const InputDecoration(
                              labelText: 'Remarks', isDense: true),
                        ),
                      ),
                    ]),
                    const SizedBox(height: AppSpacing.md),
                    Text('Lines', style: theme.textTheme.titleSmall),
                    const SizedBox(height: AppSpacing.sm),
                    for (int i = 0; i < _lines.length; i++) _lineRow(i),
                    Align(
                      alignment: Alignment.centerLeft,
                      child: TextButton.icon(
                        key: const ValueKey('requisition-add-line'),
                        onPressed: saving
                            ? null
                            : () => setState(() => _lines.add(_LineDraft())),
                        icon: const Icon(Icons.add),
                        label: const Text('Add line'),
                      ),
                    ),
                  ],
                ),
              ),
      ),
      actions: [
        TextButton(onPressed: cancelHandler, child: const Text('Cancel')),
        FilledButton(
          key: const ValueKey('requisition-save'),
          onPressed: saving || _loading ? null : _save,
          child: Text(saving ? 'Saving…' : 'Save'),
        ),
      ],
    );
  }

  Widget _lineRow(int index) {
    final _LineDraft line = _lines[index];
    return Padding(
      key: ObjectKey(line),
      padding: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            flex: 4,
            child: _ProductBox(
              fieldKey: ValueKey('requisition-product-$index'),
              api: widget.api,
              controller: line.product,
              enabled: !saving,
              onPicked: (Product p) => line.productId = p.id,
              onCleared: () => line.productId = '',
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            flex: 2,
            child: TextField(
              key: ValueKey('requisition-quantity-$index'),
              controller: line.quantity,
              enabled: !saving,
              keyboardType:
                  const TextInputType.numberWithOptions(decimal: true),
              decoration:
                  const InputDecoration(labelText: 'Quantity', isDense: true),
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            flex: 3,
            child: DropdownButtonFormField<String>(
              key: ValueKey('requisition-supplier-$index-${line.vendorId}'),
              initialValue: line.vendorId.isEmpty ? null : line.vendorId,
              isExpanded: true,
              decoration: InputDecoration(
                labelText: 'Supplier (optional)',
                isDense: true,
                suffixIcon: line.vendorId.isEmpty
                    ? null
                    : IconButton(
                        tooltip: 'No supplier',
                        iconSize: 14,
                        onPressed: saving
                            ? null
                            : () => setState(() => line.vendorId = ''),
                        icon: const Icon(Icons.close),
                      ),
              ),
              items: [
                for (final Vendor v in _vendors)
                  DropdownMenuItem(
                    value: v.id,
                    child: Text(v.displayName.isEmpty ? v.name : v.displayName,
                        overflow: TextOverflow.ellipsis),
                  ),
              ],
              onChanged: saving
                  ? null
                  : (v) => setState(() => line.vendorId = v ?? ''),
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            flex: 3,
            child: TextField(
              key: ValueKey('requisition-line-remarks-$index'),
              controller: line.remarks,
              enabled: !saving,
              decoration:
                  const InputDecoration(labelText: 'Remarks', isDense: true),
            ),
          ),
          IconButton(
            tooltip: 'Remove line',
            onPressed: saving || _lines.length == 1
                ? null
                : () => setState(() => _lines.removeAt(index).dispose()),
            icon: const Icon(Icons.delete_outline),
          ),
        ],
      ),
    );
  }
}

/// A product box that searches the firm's products as you type.
class _ProductBox extends StatefulWidget {
  const _ProductBox({
    required this.fieldKey,
    required this.api,
    required this.controller,
    required this.enabled,
    required this.onPicked,
    required this.onCleared,
  });

  final Key fieldKey;
  final ApiClient api;
  final TextEditingController controller;
  final bool enabled;
  final ValueChanged<Product> onPicked;
  final VoidCallback onCleared;

  @override
  State<_ProductBox> createState() => _ProductBoxState();
}

class _ProductBoxState extends State<_ProductBox> {
  final FocusNode _focus = FocusNode();

  @override
  void dispose() {
    _focus.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return RawAutocomplete<Product>(
      textEditingController: widget.controller,
      focusNode: _focus,
      displayStringForOption: (p) => '${p.code} · ${p.name}',
      optionsBuilder: (value) async {
        final String text = value.text.trim();
        if (text.length < 2) return const <Product>[];
        try {
          final result = await widget.api.products(search: text, pageSize: 10);
          return result.items;
        } on ApiException {
          return const <Product>[];
        }
      },
      onSelected: widget.onPicked,
      fieldViewBuilder: (context, textController, focusNode, onSubmit) =>
          TextField(
        key: widget.fieldKey,
        controller: textController,
        focusNode: focusNode,
        enabled: widget.enabled,
        decoration: const InputDecoration(
          labelText: 'Product',
          hintText: 'Type a code or name',
          isDense: true,
        ),
        onChanged: (_) => widget.onCleared(),
      ),
      optionsViewBuilder: (context, onSelected, options) => Align(
        alignment: Alignment.topLeft,
        child: Material(
          elevation: 4,
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxHeight: 240, maxWidth: 420),
            child: ListView(
              shrinkWrap: true,
              children: [
                for (final Product p in options)
                  ListTile(
                    dense: true,
                    title: Text('${p.code} · ${p.name}',
                        overflow: TextOverflow.ellipsis),
                    onTap: () => onSelected(p),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
