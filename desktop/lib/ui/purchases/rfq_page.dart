// Requests for quotation (PG-8): ask several suppliers for a price on the same
// lines, key in what each answers, compare them side by side, and raise one
// purchase order per supplier chosen. Phase 2 only.

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
import '../../models/rfq.dart';
import '../../models/vendor.dart';
import '../workspace/desktop_framework.dart';
import '../workspace/reason_prompt.dart';
import 'purchase_requisition_page.dart' show ProductSearchBox;

String _words(String status) =>
    status.isEmpty ? '' : status[0] + status.substring(1).toLowerCase();

String _today() => DateTime.now().toIso8601String().split('T').first;

String _vendorName(Vendor v) => v.displayName.isEmpty ? v.name : v.displayName;

/// List requests for quotation and drive them: send, quote, compare, close.
class RfqPage extends StatefulWidget {
  const RfqPage({
    super.key,
    required this.api,
    required this.preferences,
    required this.permissions,
    required this.hasActiveFirm,
    this.onOpenPurchaseOrders,
  });

  final ApiClient api;
  final DesktopPreferencesService preferences;
  final PermissionService permissions;
  final bool hasActiveFirm;

  /// Takes the person to the purchase orders list once orders are raised.
  final VoidCallback? onOpenPurchaseOrders;

  @override
  State<RfqPage> createState() => _RfqPageState();
}

class _RfqPageState extends State<RfqPage> {
  List<Rfq> _rows = const [];
  String? _error;
  String? _selectedId;
  bool _loading = true;
  String _status = '';

  bool _may(String code) => widget.permissions.hasPermission(code);
  bool get _mayView => _may('RFQ_VIEW');
  bool get _mayManage => _may('RFQ_MANAGE');

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
      final PagedResult<Rfq> page = await widget.api.rfqs(status: _status);
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

  Rfq? get _selected => _rows.where((row) => row.id == _selectedId).firstOrNull;

  void _say(String message, {bool error = false}) {
    if (!mounted) return;
    NotificationService.show(
      context,
      message,
      kind: error ? AppNotificationKind.error : AppNotificationKind.success,
    );
  }

  Future<void> _edit(Rfq? row) async {
    final Rfq? saved = await showDialog<Rfq>(
      context: context,
      barrierDismissible: false,
      builder: (_) => RfqDialog(api: widget.api, existing: row),
    );
    if (saved == null || !mounted) return;
    _say('${saved.number} saved.');
    _selectedId = saved.id;
    await _load();
  }

  Future<void> _act(Rfq row, String action) async {
    String? reason;
    if (action == 'cancel') {
      reason = await askForReason(
        context,
        title: 'Cancel ${row.number}',
        explanation: 'The reason stays on the request.',
        confirmLabel: 'Cancel request',
        cancelLabel: 'Keep',
      );
      if (reason == null) return;
    }
    try {
      await widget.api.actOnRfq(row.id, action, reason: reason);
      final String done = switch (action) {
        'send' => 'sent',
        'close' => 'closed',
        _ => 'cancelled',
      };
      _say('${row.number} $done.');
      await _load();
    } on ApiException catch (error) {
      _say(error.message, error: true);
    }
  }

  Future<void> _quotes(Rfq row) async {
    await showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (_) => RfqQuotesDialog(api: widget.api, rfq: row),
    );
    if (mounted) await _load();
  }

  Future<void> _compare(Rfq row) async {
    final bool? raised = await showDialog<bool>(
      context: context,
      barrierDismissible: false,
      builder: (_) => RfqComparisonDialog(
        api: widget.api,
        rfq: row,
        mayManage: _mayManage,
        mayRaise: _may('PURCHASE_CREATE'),
        onOpenPurchaseOrders: widget.onOpenPurchaseOrders,
      ),
    );
    if (raised == true && mounted) await _load();
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.hasActiveFirm) {
      return const WorkspaceEmptyState(
        title: 'Choose a firm',
        message: 'Requests for quotation belong to one firm.',
      );
    }
    if (!_mayView) {
      return const WorkspaceEmptyState(
        icon: Icons.lock_outline,
        title: 'You cannot see requests for quotation',
        message: 'Reading them needs the view RFQ permission.',
      );
    }
    final Rfq? picked = _selected;
    return ManagementWorkspaceLayout(
      notice: 'A request for quotation asks several suppliers for a price on '
          'the same lines. Send it, key in each answer, compare, and raise a '
          'purchase order to each supplier you choose.',
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
        message: 'Requests for quotation',
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

  WorkspaceToolbar _toolbar(Rfq? row) {
    final String status = row?.status ?? '';
    return WorkspaceToolbar(
      trailing: [
        Phase2MenuChip<String>(
          key: const ValueKey('rfq-status-filter'),
          label: 'Show: ${_status.isEmpty ? 'All' : _words(_status)}',
          itemBuilder: (_) => const [
            PopupMenuItem<String>(value: '', child: Text('All')),
            PopupMenuItem<String>(value: 'DRAFT', child: Text('Draft')),
            PopupMenuItem<String>(value: 'SENT', child: Text('Sent')),
            PopupMenuItem<String>(value: 'CLOSED', child: Text('Closed')),
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
        if (_mayManage) ToolbarAction.newItem,
        ToolbarAction.edit,
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
            id: 'send',
            label: 'Send',
            icon: Icons.send_outlined,
            onPressed: row != null && status == 'DRAFT'
                ? () => unawaited(_act(row, 'send'))
                : null,
          ),
        if (_mayManage)
          ToolbarCommand(
            id: 'quotes',
            label: 'Enter quotes',
            icon: Icons.edit_note_outlined,
            onPressed: row != null && status == 'SENT'
                ? () => unawaited(_quotes(row))
                : null,
          ),
        ToolbarCommand(
          id: 'compare',
          label: 'Compare',
          icon: Icons.compare_arrows_outlined,
          onPressed: row != null && (status == 'SENT' || status == 'CLOSED')
              ? () => unawaited(_compare(row))
              : null,
        ),
        if (_mayManage)
          ToolbarCommand(
            id: 'close',
            label: 'Close',
            icon: Icons.lock_outline,
            onPressed: row != null && status == 'SENT'
                ? () => unawaited(_act(row, 'close'))
                : null,
          ),
        if (_mayManage)
          ToolbarCommand(
            id: 'cancel',
            label: 'Cancel',
            icon: Icons.cancel_outlined,
            onPressed: row != null && (status == 'DRAFT' || status == 'SENT')
                ? () => unawaited(_act(row, 'cancel'))
                : null,
          ),
      ],
    );
  }

  late final ColumnChoice<Rfq> _columns = ColumnChoice(
    preferences: widget.preferences,
    stateKey: 'rfqs.grid',
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
            const GridColumn(key: 'required', label: 'Required by', priority: 1),
        cell: (item) => item.requiredBy,
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
      ChoosableColumn(
        column: const GridColumn(
            key: 'suppliers', label: 'Suppliers', numeric: true),
        cell: (item) => '${item.suppliers.length}',
        shownByDefault: true,
      ),
    ],
  );

  Widget _grid() {
    if (_rows.isEmpty) {
      return const WorkspaceEmptyState(
        title: 'No requests for quotation',
        message: 'Raise one here, or from an approved requisition.',
      );
    }
    return EnterpriseDataGrid<Rfq>(
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

/// One line being typed: its boxes belong to the dialog that shows it.
class _LineDraft {
  _LineDraft({
    this.productId = '',
    String product = '',
    String quantity = '',
    this.uomId = '',
    String notes = '',
  })  : product = TextEditingController(text: product),
        quantity = TextEditingController(text: quantity),
        notes = TextEditingController(text: notes);

  String productId;
  String uomId;
  final TextEditingController product;
  final TextEditingController quantity;
  final TextEditingController notes;

  void dispose() {
    product.dispose();
    quantity.dispose();
    notes.dispose();
  }
}

Widget _dateBox(
  String label,
  String value,
  VoidCallback? onTap, {
  Key? key,
}) =>
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

Future<String?> _pickDate(BuildContext context, String current) async {
  final DateTime? picked = await showDatePicker(
    context: context,
    initialDate: DateTime.tryParse(current) ?? DateTime.now(),
    firstDate: DateTime(2000),
    lastDate: DateTime(2100),
  );
  return picked?.toIso8601String().split('T').first;
}

/// Raise or change a request for quotation; read-only once it has left
/// draft. Pops the saved [Rfq]; stays open with the server's message when
/// refused.
class RfqDialog extends StatefulWidget {
  const RfqDialog({super.key, required this.api, this.existing});

  final ApiClient api;
  final Rfq? existing;

  @override
  State<RfqDialog> createState() => _RfqDialogState();
}

class _RfqDialogState extends State<RfqDialog> with SaveInDialog<RfqDialog> {
  List<BranchRecord> _branches = const [];
  List<WarehouseRecord> _warehouses = const [];
  List<Vendor> _vendors = const [];
  String _branchId = '';
  String _warehouseId = '';
  late String _date;
  String _requiredBy = '';
  final TextEditingController _notes = TextEditingController();
  final List<_LineDraft> _lines = <_LineDraft>[];
  final List<String> _vendorIds = <String>[];
  String? _problem;
  bool _loading = true;

  bool get _readOnly => widget.existing != null && !widget.existing!.isDraft;

  @override
  void initState() {
    super.initState();
    final Rfq? existing = widget.existing;
    _date = existing != null && existing.date.isNotEmpty
        ? existing.date
        : _today();
    if (existing != null) {
      _branchId = existing.branchId;
      _warehouseId = existing.warehouseId;
      _requiredBy = existing.requiredBy;
      _notes.text = existing.notes;
      for (final RfqLine line in existing.lines) {
        _lines.add(_LineDraft(
          productId: line.productId,
          product: '${line.productCode} · ${line.productName}',
          quantity: line.quantity,
          uomId: line.uomId,
          notes: line.notes,
        ));
      }
      _vendorIds.addAll(existing.suppliers.map((s) => s.vendorId));
    }
    if (_lines.isEmpty) _lines.add(_LineDraft());
    unawaited(_loadMasters());
  }

  @override
  void dispose() {
    _notes.dispose();
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

  String _nameOf(String vendorId) {
    final Vendor? vendor = _vendors.where((v) => v.id == vendorId).firstOrNull;
    if (vendor != null) return _vendorName(vendor);
    final RfqSupplier? invited = widget.existing?.suppliers
        .where((s) => s.vendorId == vendorId)
        .firstOrNull;
    return invited?.vendorName ?? vendorId;
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
      final String notes = line.notes.text.trim();
      lines.add(<String, dynamic>{
        'product_id': line.productId,
        'quantity': line.quantity.text.trim(),
        if (line.uomId.isNotEmpty) 'uom_id': line.uomId,
        if (notes.isNotEmpty) 'notes': notes,
      });
    }
    if (lines.isEmpty) problem ??= 'Add at least one line.';
    if (_vendorIds.isEmpty) problem ??= 'Invite at least one supplier.';
    setState(() => _problem = problem);
    if (problem != null) return;
    final String notes = _notes.text.trim();
    final Json body = <String, dynamic>{
      'branch_id': _branchId,
      'warehouse_id': _warehouseId,
      'rfq_date': _date,
      if (_requiredBy.isNotEmpty) 'required_by': _requiredBy,
      if (notes.isNotEmpty) 'notes': notes,
      'lines': lines,
      'vendor_ids': List<String>.of(_vendorIds),
    };
    final Rfq? existing = widget.existing;
    unawaited(saveAndClose<Rfq>(() => existing == null
        ? widget.api.createRfq(body)
        : widget.api
            .updateRfq(existing.id, body, expectedVersion: existing.version)));
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final bool locked = saving || _readOnly;
    final List<WarehouseRecord> warehouses =
        _warehouses.where((w) => w.branchId == _branchId).toList();
    return AlertDialog(
      title: Text(widget.existing == null
          ? 'New request for quotation'
          : 'Request ${widget.existing!.number}'),
      content: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 860, maxHeight: 460),
        child: SizedBox(
          width: 860,
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
                              key: const ValueKey('rfq-problem'),
                              style: TextStyle(color: theme.colorScheme.error)),
                        ),
                      if (_readOnly)
                        Padding(
                          padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                          child: Text(
                            'This request is ${_words(widget.existing!.status)} '
                            'and can no longer be changed.',
                            key: const ValueKey('rfq-read-only'),
                            style: theme.textTheme.bodySmall,
                          ),
                        ),
                      Row(children: [
                        Expanded(
                          child: DropdownButtonFormField<String>(
                            key: const ValueKey('rfq-branch'),
                            initialValue: _branchId.isEmpty ? null : _branchId,
                            isExpanded: true,
                            decoration: const InputDecoration(
                                labelText: 'Branch', isDense: true),
                            items: [
                              for (final BranchRecord b in _branches)
                                DropdownMenuItem(
                                    value: b.id, child: Text(b.name)),
                            ],
                            onChanged: locked
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
                            key: ValueKey('rfq-warehouse-$_branchId'),
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
                            onChanged: locked
                                ? null
                                : (v) => setState(() => _warehouseId = v ?? ''),
                          ),
                        ),
                      ]),
                      const SizedBox(height: AppSpacing.md),
                      Row(children: [
                        Expanded(
                          child: _dateBox(
                              'Date',
                              _date,
                              locked
                                  ? null
                                  : () async {
                                      final String? v =
                                          await _pickDate(context, _date);
                                      if (v != null) setState(() => _date = v);
                                    },
                              key: const ValueKey('rfq-date')),
                        ),
                        const SizedBox(width: AppSpacing.md),
                        Expanded(
                          child: _dateBox(
                              'Required by',
                              _requiredBy,
                              locked
                                  ? null
                                  : () async {
                                      final String? v = await _pickDate(
                                          context, _requiredBy);
                                      if (v != null) {
                                        setState(() => _requiredBy = v);
                                      }
                                    },
                              key: const ValueKey('rfq-required-by')),
                        ),
                        const SizedBox(width: AppSpacing.md),
                        Expanded(
                          flex: 2,
                          child: TextField(
                            key: const ValueKey('rfq-notes'),
                            controller: _notes,
                            enabled: !locked,
                            decoration: const InputDecoration(
                                labelText: 'Notes', isDense: true),
                          ),
                        ),
                      ]),
                      const SizedBox(height: AppSpacing.md),
                      Text('Lines', style: theme.textTheme.titleSmall),
                      const SizedBox(height: AppSpacing.sm),
                      for (int i = 0; i < _lines.length; i++) _lineRow(i, locked),
                      if (!_readOnly)
                        Align(
                          alignment: Alignment.centerLeft,
                          child: TextButton.icon(
                            key: const ValueKey('rfq-add-line'),
                            onPressed: locked
                                ? null
                                : () => setState(() => _lines.add(_LineDraft())),
                            icon: const Icon(Icons.add),
                            label: const Text('Add line'),
                          ),
                        ),
                      const SizedBox(height: AppSpacing.md),
                      Text('Suppliers invited', style: theme.textTheme.titleSmall),
                      const SizedBox(height: AppSpacing.sm),
                      _suppliers(locked),
                    ],
                  ),
                ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: cancelHandler,
          child: Text(_readOnly ? 'Close' : 'Cancel'),
        ),
        if (!_readOnly)
          FilledButton(
            key: const ValueKey('rfq-save'),
            onPressed: saving || _loading ? null : _save,
            child: Text(saving ? 'Saving…' : 'Save'),
          ),
      ],
    );
  }

  Widget _suppliers(bool locked) {
    final List<Vendor> available =
        _vendors.where((v) => !_vendorIds.contains(v.id)).toList();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Wrap(
          spacing: AppSpacing.sm,
          runSpacing: AppSpacing.xs,
          children: [
            for (final String id in _vendorIds)
              InputChip(
                key: ValueKey('rfq-supplier-chip-$id'),
                label: Text(_nameOf(id)),
                onDeleted: locked
                    ? null
                    : () => setState(() => _vendorIds.remove(id)),
              ),
          ],
        ),
        if (!_readOnly)
          Padding(
            padding: const EdgeInsets.only(top: AppSpacing.sm),
            child: SizedBox(
              width: 360,
              child: DropdownButtonFormField<String>(
                key: ValueKey('rfq-add-supplier-${_vendorIds.length}'),
                initialValue: null,
                isExpanded: true,
                decoration: const InputDecoration(
                    labelText: 'Add a supplier', isDense: true),
                items: [
                  for (final Vendor v in available)
                    DropdownMenuItem(
                      value: v.id,
                      child:
                          Text(_vendorName(v), overflow: TextOverflow.ellipsis),
                    ),
                ],
                onChanged: locked
                    ? null
                    : (v) {
                        if (v != null) setState(() => _vendorIds.add(v));
                      },
              ),
            ),
          ),
      ],
    );
  }

  Widget _lineRow(int index, bool locked) {
    final _LineDraft line = _lines[index];
    return Padding(
      key: ObjectKey(line),
      padding: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            flex: 5,
            child: ProductSearchBox(
              fieldKey: ValueKey('rfq-product-$index'),
              api: widget.api,
              controller: line.product,
              enabled: !locked,
              onPicked: (Product p) {
                line.productId = p.id;
                line.uomId =
                    p.purchaseUomId.isNotEmpty ? p.purchaseUomId : p.baseUomId;
              },
              onCleared: () {
                line.productId = '';
                line.uomId = '';
              },
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            flex: 2,
            child: TextField(
              key: ValueKey('rfq-quantity-$index'),
              controller: line.quantity,
              enabled: !locked,
              keyboardType:
                  const TextInputType.numberWithOptions(decimal: true),
              decoration:
                  const InputDecoration(labelText: 'Quantity', isDense: true),
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            flex: 3,
            child: TextField(
              key: ValueKey('rfq-line-notes-$index'),
              controller: line.notes,
              enabled: !locked,
              decoration:
                  const InputDecoration(labelText: 'Notes', isDense: true),
            ),
          ),
          if (!_readOnly)
            IconButton(
              tooltip: 'Remove line',
              onPressed: locked || _lines.length == 1
                  ? null
                  : () => setState(() => _lines.removeAt(index).dispose()),
              icon: const Icon(Icons.delete_outline),
            ),
        ],
      ),
    );
  }
}

/// What one supplier answered, per line.
class _QuoteLineDraft {
  _QuoteLineDraft(this.line, QuotationLine? existing)
      : rate = TextEditingController(text: existing?.rate ?? ''),
        discount = TextEditingController(text: existing?.discountPercent ?? ''),
        leadTime = TextEditingController(
            text: existing?.leadTimeDays?.toString() ?? ''),
        notes = TextEditingController(text: existing?.notes ?? '');

  final RfqLine line;
  final TextEditingController rate;
  final TextEditingController discount;
  final TextEditingController leadTime;
  final TextEditingController notes;

  void dispose() {
    rate.dispose();
    discount.dispose();
    leadTime.dispose();
    notes.dispose();
  }
}

/// Key in, or correct, what each invited supplier quoted. Saving keeps the
/// dialog open so the next supplier can be keyed straight after.
class RfqQuotesDialog extends StatefulWidget {
  const RfqQuotesDialog({super.key, required this.api, required this.rfq});

  final ApiClient api;
  final Rfq rfq;

  @override
  State<RfqQuotesDialog> createState() => _RfqQuotesDialogState();
}

class _RfqQuotesDialogState extends State<RfqQuotesDialog>
    with SaveInDialog<RfqQuotesDialog> {
  List<SupplierQuotation> _quotations = const [];
  String _vendorId = '';
  String _quoteDate = _today();
  String _validUntil = '';
  final TextEditingController _ref = TextEditingController();
  final TextEditingController _notes = TextEditingController();
  List<_QuoteLineDraft> _drafts = const [];
  String? _problem;
  String? _done;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  @override
  void dispose() {
    _ref.dispose();
    _notes.dispose();
    for (final _QuoteLineDraft d in _drafts) {
      d.dispose();
    }
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final List<SupplierQuotation> quotations =
          await widget.api.rfqQuotations(widget.rfq.id);
      if (!mounted) return;
      _quotations = quotations;
      final List<RfqSupplier> suppliers = widget.rfq.suppliers;
      _choose(suppliers.isEmpty ? '' : suppliers.first.vendorId);
      setState(() => _loading = false);
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        saveError = error.message;
        _loading = false;
      });
    }
  }

  /// Fill the form from what is recorded for [vendorId], or blank.
  void _choose(String vendorId) {
    for (final _QuoteLineDraft d in _drafts) {
      d.dispose();
    }
    final SupplierQuotation? quote =
        _quotations.where((q) => q.vendorId == vendorId).firstOrNull;
    _vendorId = vendorId;
    _ref.text = quote?.quoteRef ?? '';
    _notes.text = quote?.notes ?? '';
    _quoteDate = quote != null && quote.quoteDate.isNotEmpty
        ? quote.quoteDate
        : _today();
    _validUntil = quote?.validUntil ?? '';
    _drafts = [
      for (final RfqLine line in widget.rfq.lines)
        _QuoteLineDraft(
          line,
          quote?.lines.where((l) => l.rfqLineId == line.id).firstOrNull,
        ),
    ];
    _problem = null;
    _done = null;
  }

  Future<void> _save() async {
    String? problem;
    final List<Json> lines = <Json>[];
    for (final _QuoteLineDraft d in _drafts) {
      final String rate = d.rate.text.trim();
      if (rate.isEmpty) continue;
      if (double.tryParse(rate) == null) {
        problem ??= 'A rate must be a number.';
        continue;
      }
      final String discount = d.discount.text.trim();
      final String lead = d.leadTime.text.trim();
      final String notes = d.notes.text.trim();
      lines.add(<String, dynamic>{
        'rfq_line_id': d.line.id,
        'rate': rate,
        if (discount.isNotEmpty) 'discount_percent': discount,
        if (lead.isNotEmpty && int.tryParse(lead) != null)
          'lead_time_days': int.parse(lead),
        if (notes.isNotEmpty) 'notes': notes,
      });
    }
    if (lines.isEmpty) problem ??= 'Key in a rate for at least one line.';
    setState(() => _problem = problem);
    if (problem != null || _vendorId.isEmpty) return;
    final String quoteRef = _ref.text.trim();
    final String notes = _notes.text.trim();
    final Json body = <String, dynamic>{
      if (quoteRef.isNotEmpty) 'quote_ref': quoteRef,
      'quote_date': _quoteDate,
      if (_validUntil.isNotEmpty) 'valid_until': _validUntil,
      if (notes.isNotEmpty) 'notes': notes,
      'lines': lines,
    };
    setState(() {
      saving = true;
      saveError = null;
      _done = null;
    });
    try {
      final SupplierQuotation saved =
          await widget.api.saveRfqQuotation(widget.rfq.id, _vendorId, body);
      if (!mounted) return;
      setState(() {
        _quotations = [
          ..._quotations.where((q) => q.vendorId != saved.vendorId),
          saved,
        ];
        saving = false;
        _done = 'Quote saved.';
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        saving = false;
        saveError = error.message;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return AlertDialog(
      title: Text('Quotes for ${widget.rfq.number}'),
      content: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 860, maxHeight: 460),
        child: SizedBox(
          width: 860,
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
                              key: const ValueKey('quote-problem'),
                              style: TextStyle(color: theme.colorScheme.error)),
                        ),
                      if (_done != null)
                        Padding(
                          padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                          child: Text(_done!,
                              key: const ValueKey('quote-done'),
                              style: theme.textTheme.bodySmall),
                        ),
                      Row(children: [
                        Expanded(
                          flex: 2,
                          child: DropdownButtonFormField<String>(
                            key: const ValueKey('quote-supplier'),
                            initialValue: _vendorId.isEmpty ? null : _vendorId,
                            isExpanded: true,
                            decoration: const InputDecoration(
                                labelText: 'Supplier', isDense: true),
                            items: [
                              for (final RfqSupplier s in widget.rfq.suppliers)
                                DropdownMenuItem(
                                  value: s.vendorId,
                                  child: Text(
                                    '${s.vendorName}'
                                    '${_quotations.any((q) => q.vendorId == s.vendorId) ? '  ✓' : ''}',
                                    overflow: TextOverflow.ellipsis,
                                  ),
                                ),
                            ],
                            onChanged: saving
                                ? null
                                : (v) => setState(() => _choose(v ?? '')),
                          ),
                        ),
                        const SizedBox(width: AppSpacing.md),
                        Expanded(
                          child: TextField(
                            key: const ValueKey('quote-ref'),
                            controller: _ref,
                            enabled: !saving,
                            decoration: const InputDecoration(
                                labelText: 'Their reference', isDense: true),
                          ),
                        ),
                      ]),
                      const SizedBox(height: AppSpacing.md),
                      Row(children: [
                        Expanded(
                          child: _dateBox(
                              'Quote date',
                              _quoteDate,
                              saving
                                  ? null
                                  : () async {
                                      final String? v =
                                          await _pickDate(context, _quoteDate);
                                      if (v != null) {
                                        setState(() => _quoteDate = v);
                                      }
                                    },
                              key: const ValueKey('quote-date')),
                        ),
                        const SizedBox(width: AppSpacing.md),
                        Expanded(
                          child: _dateBox(
                              'Valid until',
                              _validUntil,
                              saving
                                  ? null
                                  : () async {
                                      final String? v = await _pickDate(
                                          context, _validUntil);
                                      if (v != null) {
                                        setState(() => _validUntil = v);
                                      }
                                    },
                              key: const ValueKey('quote-valid-until')),
                        ),
                        const SizedBox(width: AppSpacing.md),
                        Expanded(
                          flex: 2,
                          child: TextField(
                            key: const ValueKey('quote-notes'),
                            controller: _notes,
                            enabled: !saving,
                            decoration: const InputDecoration(
                                labelText: 'Notes', isDense: true),
                          ),
                        ),
                      ]),
                      const SizedBox(height: AppSpacing.md),
                      for (int i = 0; i < _drafts.length; i++) _lineRow(i),
                    ],
                  ),
                ),
        ),
      ),
      actions: [
        TextButton(
          key: const ValueKey('quote-close'),
          onPressed: saving ? null : () => Navigator.pop(context),
          child: const Text('Close'),
        ),
        FilledButton(
          key: const ValueKey('quote-save'),
          onPressed: saving || _loading || _vendorId.isEmpty ? null : _save,
          child: Text(saving ? 'Saving…' : 'Save quote'),
        ),
      ],
    );
  }

  Widget _lineRow(int index) {
    final _QuoteLineDraft d = _drafts[index];
    return Padding(
      key: ObjectKey(d),
      padding: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            flex: 4,
            child: Padding(
              padding: const EdgeInsets.only(top: AppSpacing.sm),
              child: Text(
                '${d.line.productCode} · ${d.line.productName}  '
                '(${d.line.quantity})',
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            flex: 2,
            child: TextField(
              key: ValueKey('quote-rate-$index'),
              controller: d.rate,
              enabled: !saving,
              keyboardType:
                  const TextInputType.numberWithOptions(decimal: true),
              decoration: const InputDecoration(labelText: 'Rate', isDense: true),
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            flex: 2,
            child: TextField(
              key: ValueKey('quote-discount-$index'),
              controller: d.discount,
              enabled: !saving,
              keyboardType:
                  const TextInputType.numberWithOptions(decimal: true),
              decoration:
                  const InputDecoration(labelText: 'Discount %', isDense: true),
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            flex: 2,
            child: TextField(
              key: ValueKey('quote-lead-$index'),
              controller: d.leadTime,
              enabled: !saving,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(
                  labelText: 'Lead time (days)', isDense: true),
            ),
          ),
        ],
      ),
    );
  }
}

/// Suppliers side by side, one row per line. The lowest landed rate is
/// highlighted; tapping a cell chooses it, and a choice that is not the lowest
/// asks why. Saving sends the whole list of choices; raising orders turns each
/// supplier's chosen lines into a purchase order.
class RfqComparisonDialog extends StatefulWidget {
  const RfqComparisonDialog({
    super.key,
    required this.api,
    required this.rfq,
    required this.mayManage,
    required this.mayRaise,
    this.onOpenPurchaseOrders,
  });

  final ApiClient api;
  final Rfq rfq;
  final bool mayManage;
  final bool mayRaise;
  final VoidCallback? onOpenPurchaseOrders;

  @override
  State<RfqComparisonDialog> createState() => _RfqComparisonDialogState();
}

class _RfqComparisonDialogState extends State<RfqComparisonDialog>
    with SaveInDialog<RfqComparisonDialog> {
  RfqComparison? _comparison;
  final Map<String, String> _chosen = <String, String>{};
  final Map<String, String> _reasons = <String, String>{};
  bool _dirty = false;
  bool _raised = false;
  bool _loading = true;

  static const double _labelWidth = 220;
  static const double _cellWidth = 160;

  bool get _canChoose => widget.mayManage && widget.rfq.status == 'SENT';

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  void _adopt(RfqComparison comparison) {
    _comparison = comparison;
    _chosen.clear();
    _reasons.clear();
    for (final ComparisonLine line in comparison.lines) {
      if (line.selectedQuotationLineId.isNotEmpty) {
        _chosen[line.rfqLineId] = line.selectedQuotationLineId;
        if (line.selectionReason.isNotEmpty) {
          _reasons[line.rfqLineId] = line.selectionReason;
        }
      }
    }
    _dirty = false;
  }

  Future<void> _load() async {
    try {
      final RfqComparison comparison =
          await widget.api.rfqComparison(widget.rfq.id);
      if (!mounted) return;
      setState(() {
        _adopt(comparison);
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

  Future<void> _tap(ComparisonLine line, ComparisonQuote quote) async {
    if (!_canChoose || saving) return;
    if (_chosen[line.rfqLineId] == quote.quotationLineId) {
      setState(() {
        _chosen.remove(line.rfqLineId);
        _reasons.remove(line.rfqLineId);
        _dirty = true;
      });
      return;
    }
    String? reason;
    if (!quote.isLowest) {
      reason = await askForReason(
        context,
        title: 'Not the lowest rate',
        explanation: '${quote.vendorName} is not the lowest landed rate for '
            '${line.productName}. Say why it is chosen.',
        confirmLabel: 'Choose it',
      );
      if (reason == null || !mounted) return;
    }
    setState(() {
      _chosen[line.rfqLineId] = quote.quotationLineId;
      if (reason == null) {
        _reasons.remove(line.rfqLineId);
      } else {
        _reasons[line.rfqLineId] = reason;
      }
      _dirty = true;
    });
  }

  Future<void> _saveSelections() async {
    final List<Json> selections = [
      for (final MapEntry<String, String> e in _chosen.entries)
        <String, dynamic>{
          'rfq_line_id': e.key,
          'quotation_line_id': e.value,
          if (_reasons[e.key] != null) 'reason': _reasons[e.key],
        },
    ];
    setState(() {
      saving = true;
      saveError = null;
    });
    try {
      final RfqComparison saved =
          await widget.api.saveRfqSelections(widget.rfq.id, selections);
      if (!mounted) return;
      setState(() {
        _adopt(saved);
        saving = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        saving = false;
        saveError = error.message;
      });
    }
  }

  Future<void> _raiseOrders() async {
    final bool? yes = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Raise purchase orders'),
        content: const Text('One purchase order is raised to each supplier '
            'with lines chosen. This cannot be undone from here.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Not yet'),
          ),
          FilledButton(
            key: const ValueKey('rfq-raise-confirm'),
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Raise orders'),
          ),
        ],
      ),
    );
    if (yes != true || !mounted) return;
    setState(() {
      saving = true;
      saveError = null;
    });
    try {
      final List<Json> orders = await widget.api.raiseRfqOrders(widget.rfq.id);
      if (!mounted) return;
      setState(() {
        saving = false;
        _raised = true;
      });
      await showDialog<void>(
        context: context,
        builder: (context) => AlertDialog(
          key: const ValueKey('rfq-orders-raised'),
          title: Text('${orders.length} purchase '
              '${orders.length == 1 ? 'order' : 'orders'} raised'),
          content: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 420, maxHeight: 280),
            child: SingleChildScrollView(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  for (final Json order in orders)
                    Padding(
                      padding: const EdgeInsets.symmetric(
                          vertical: AppSpacing.xs),
                      child: Text(stringValue(order['po_number']).isEmpty
                          ? stringValue(order['id'])
                          : stringValue(order['po_number'])),
                    ),
                ],
              ),
            ),
          ),
          actions: [
            if (widget.onOpenPurchaseOrders != null)
              TextButton(
                key: const ValueKey('rfq-open-orders'),
                onPressed: () {
                  Navigator.pop(context);
                  widget.onOpenPurchaseOrders!();
                },
                child: const Text('Open purchase orders'),
              ),
            FilledButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Done'),
            ),
          ],
        ),
      );
      if (mounted) Navigator.pop(context, true);
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        saving = false;
        saveError = error.message;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text('Compare quotes for ${widget.rfq.number}'),
      content: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 900, maxHeight: 440),
        child: SizedBox(
          width: 900,
          child: _loading
              ? const Center(child: CircularProgressIndicator())
              : Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    saveErrorBanner(),
                    if (_canChoose)
                      Padding(
                        padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                        child: Text(
                          'Click a rate to choose it. The lowest landed rate '
                          'is highlighted.',
                          style: Theme.of(context).textTheme.bodySmall,
                        ),
                      ),
                    Expanded(child: _grid(context)),
                  ],
                ),
        ),
      ),
      actions: [
        TextButton(
          key: const ValueKey('cmp-close'),
          onPressed: saving ? null : () => Navigator.pop(context, _raised),
          child: const Text('Close'),
        ),
        if (_canChoose)
          OutlinedButton(
            key: const ValueKey('cmp-save'),
            onPressed: saving || _loading || !_dirty ? null : _saveSelections,
            child: const Text('Save selections'),
          ),
        if (_canChoose && widget.mayRaise)
          FilledButton(
            key: const ValueKey('cmp-raise'),
            onPressed: saving || _loading || _dirty || _chosen.isEmpty
                ? null
                : _raiseOrders,
            child: const Text('Raise orders'),
          ),
      ],
    );
  }

  Widget _grid(BuildContext context) {
    final RfqComparison? comparison = _comparison;
    if (comparison == null || comparison.lines.isEmpty) {
      return const Center(child: Text('Nothing to compare yet.'));
    }
    final Map<String, String> suppliers = <String, String>{};
    for (final ComparisonLine line in comparison.lines) {
      for (final ComparisonQuote q in line.quotes) {
        suppliers[q.vendorId] = q.vendorName;
      }
    }
    if (suppliers.isEmpty) {
      return const Center(
          child: Text('No supplier has quoted yet. Enter quotes first.'));
    }
    final List<MapEntry<String, String>> columns = suppliers.entries.toList()
      ..sort((a, b) => a.value.compareTo(b.value));
    final ThemeData theme = Theme.of(context);
    return Scrollbar(
      child: SingleChildScrollView(
        child: SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(children: [
                const SizedBox(width: _labelWidth),
                for (final MapEntry<String, String> c in columns)
                  SizedBox(
                    width: _cellWidth,
                    child: Padding(
                      padding: const EdgeInsets.all(AppSpacing.xs),
                      child: Text(c.value,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: theme.textTheme.titleSmall),
                    ),
                  ),
              ]),
              for (final ComparisonLine line in comparison.lines)
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    SizedBox(
                      width: _labelWidth,
                      child: Padding(
                        padding: const EdgeInsets.all(AppSpacing.xs),
                        child: Text(
                          '${line.productCode} · ${line.productName}\n'
                          'Qty ${line.quantity}',
                          maxLines: 3,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ),
                    for (final MapEntry<String, String> c in columns)
                      SizedBox(
                        width: _cellWidth,
                        child: _cell(
                          context,
                          line,
                          line.quotes
                              .where((q) => q.vendorId == c.key)
                              .firstOrNull,
                        ),
                      ),
                  ],
                ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _cell(BuildContext context, ComparisonLine line, ComparisonQuote? q) {
    final ColorScheme colors = Theme.of(context).colorScheme;
    if (q == null) {
      return const Padding(
        padding: EdgeInsets.all(AppSpacing.sm),
        child: Text('—'),
      );
    }
    final bool picked = _chosen[line.rfqLineId] == q.quotationLineId;
    return Padding(
      padding: const EdgeInsets.all(AppSpacing.xs),
      child: InkWell(
        key: ValueKey('cmp-cell-${line.rfqLineId}-${q.vendorId}'),
        onTap: _canChoose ? () => unawaited(_tap(line, q)) : null,
        child: Container(
          padding: const EdgeInsets.all(AppSpacing.sm),
          decoration: BoxDecoration(
            color: q.isLowest ? colors.tertiaryContainer : null,
            border: Border.all(
              color: picked ? colors.primary : colors.outlineVariant,
              width: picked ? 2 : 1,
            ),
            borderRadius: BorderRadius.circular(6),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(children: [
                Expanded(
                  child: Text(q.landedRate,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(fontWeight: FontWeight.w700)),
                ),
                if (picked) Icon(Icons.check_circle, size: 16, color: colors.primary),
              ]),
              Text(
                q.leadTimeDays == null ? 'Lead time —' : '${q.leadTimeDays} days',
                style: Theme.of(context).textTheme.bodySmall,
                overflow: TextOverflow.ellipsis,
              ),
              if (q.isLowest)
                Text('Lowest',
                    key: ValueKey('cmp-lowest-${line.rfqLineId}-${q.vendorId}'),
                    style: Theme.of(context).textTheme.labelSmall),
            ],
          ),
        ),
      ),
    );
  }
}
