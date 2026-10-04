// Supplier rate contracts (PG-9): a rate agreed with one supplier for a window
// of dates. Orders raised inside the window take the contracted rate and each
// draw is counted against the quantity agreed. Phase 2 only.

import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/preferences/desktop_preferences_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/entities.dart';
import '../../models/product.dart';
import '../../models/rate_contract.dart';
import '../../models/vendor.dart';
import '../workspace/desktop_framework.dart';
import '../workspace/reason_prompt.dart';
import 'purchase_requisition_page.dart' show ProductSearchBox;

String _words(String status) =>
    status.isEmpty ? '' : status[0] + status.substring(1).toLowerCase();

String _today() => DateTime.now().toIso8601String().split('T').first;

/// A chip label that cannot crowd the toolbar at the narrowest window.
String _short(String name) =>
    name.length <= 16 ? name : '${name.substring(0, 15)}…';

String _vendorName(Vendor v) => v.displayName.isEmpty ? v.name : v.displayName;

/// List rate contracts and drive them: approve, close, cancel, see releases.
class RateContractPage extends StatefulWidget {
  const RateContractPage({
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
  State<RateContractPage> createState() => _RateContractPageState();
}

class _RateContractPageState extends State<RateContractPage> {
  List<RateContract> _rows = const [];
  List<Vendor> _vendors = const [];
  String? _error;
  String? _selectedId;
  bool _loading = true;
  String _status = '';
  String _vendorId = '';

  bool _may(String code) => widget.permissions.hasPermission(code);
  bool get _mayView => _may('RATE_CONTRACT_VIEW');
  bool get _mayManage => _may('RATE_CONTRACT_MANAGE');
  bool get _mayApprove => _may('PURCHASE_APPROVE');

  @override
  void initState() {
    super.initState();
    if (widget.hasActiveFirm && _mayView) {
      unawaited(_loadVendors());
      unawaited(_load());
    }
  }

  Future<void> _loadVendors() async {
    try {
      final List<Vendor> vendors =
          await fetchAllPages((page) => widget.api.vendors(page: page));
      if (mounted) setState(() => _vendors = vendors);
    } on ApiException {
      // The filter then offers only "All suppliers"; the list still works.
    }
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final PagedResult<RateContract> page = await widget.api
          .rateContracts(status: _status, vendorId: _vendorId);
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

  RateContract? get _selected =>
      _rows.where((row) => row.id == _selectedId).firstOrNull;

  void _say(String message, {bool error = false}) {
    if (!mounted) return;
    NotificationService.show(
      context,
      message,
      kind: error ? AppNotificationKind.error : AppNotificationKind.success,
    );
  }

  Future<void> _edit(RateContract? row) async {
    RateContract? full = row;
    if (row != null) {
      try {
        full = await widget.api.rateContract(row.id);
      } on ApiException {
        full = row;
      }
    }
    if (!mounted) return;
    final RateContract? saved = await showDialog<RateContract>(
      context: context,
      barrierDismissible: false,
      builder: (_) => RateContractDialog(api: widget.api, existing: full),
    );
    if (saved == null || !mounted) return;
    _say('${saved.number} saved.');
    _selectedId = saved.id;
    await _load();
  }

  Future<void> _delete(RateContract row) async {
    final bool? sure = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('Delete ${row.number}'),
        content: const Text('A draft contract is removed outright.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text('Keep'),
          ),
          FilledButton(
            key: const ValueKey('rc-delete-confirm'),
            onPressed: () => Navigator.of(ctx).pop(true),
            child: const Text('Delete'),
          ),
        ],
      ),
    );
    if (sure != true) return;
    try {
      await widget.api.deleteRateContract(row.id);
      _say('${row.number} deleted.');
      _selectedId = null;
      await _load();
    } on ApiException catch (error) {
      _say(error.message, error: true);
    }
  }

  Future<void> _act(RateContract row, String action) async {
    String? reason;
    if (action == 'cancel') {
      reason = await askForReason(
        context,
        title: 'Cancel ${row.number}',
        explanation: 'The reason stays on the contract.',
        confirmLabel: 'Cancel contract',
        cancelLabel: 'Keep',
      );
      if (reason == null) return;
    }
    try {
      await widget.api.actOnRateContract(row.id, action, reason: reason);
      final String done = switch (action) {
        'approve' => 'approved',
        'close' => 'closed',
        _ => 'cancelled',
      };
      _say('${row.number} $done.');
      await _load();
    } on ApiException catch (error) {
      _say(error.message, error: true);
    }
  }

  Future<void> _releases(RateContract row) => showDialog<void>(
        context: context,
        builder: (_) => RateContractReleasesDialog(api: widget.api, row: row),
      );

  @override
  Widget build(BuildContext context) {
    if (!widget.hasActiveFirm) {
      return const WorkspaceEmptyState(
        title: 'Choose a firm',
        message: 'Rate contracts belong to one firm.',
      );
    }
    if (!_mayView) {
      return const WorkspaceEmptyState(
        icon: Icons.lock_outline,
        title: 'You cannot see rate contracts',
        message: 'Reading them needs the view rate contracts permission.',
      );
    }
    final RateContract? picked = _selected;
    return ManagementWorkspaceLayout(
      notice: 'A rate contract fixes what a supplier charges for a window of '
          'dates. Approve it and purchase orders inside the window take the '
          'contracted rate.',
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
        message: 'Rate contracts',
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
        Align(
          alignment: Alignment.centerLeft,
          child: _supplierFilter(),
        ),
        const SizedBox(height: AppSpacing.sm),
        Expanded(child: _grid()),
      ],
    );
  }

  /// Kept out of the toolbar: two chips there overflow at 800 wide.
  Widget _supplierFilter() {
    final Vendor? vendor = _vendors.where((v) => v.id == _vendorId).firstOrNull;
    return Phase2MenuChip<String>(
          key: const ValueKey('rc-vendor-filter'),
          label: vendor == null ? 'All suppliers' : _short(_vendorName(vendor)),
          itemBuilder: (_) => [
            const PopupMenuItem<String>(value: '', child: Text('All')),
            for (final Vendor v in _vendors)
              PopupMenuItem<String>(value: v.id, child: Text(_vendorName(v))),
          ],
          onSelected: (value) {
            setState(() {
              _vendorId = value;
              _selectedId = null;
            });
            unawaited(_load());
          },
        );
  }

  WorkspaceToolbar _toolbar(RateContract? row) {
    final String status = row?.status ?? '';
    return WorkspaceToolbar(
      trailing: [
        Phase2MenuChip<String>(
          key: const ValueKey('rc-status-filter'),
          label: 'Show: ${_status.isEmpty ? 'All' : _words(_status)}',
          itemBuilder: (_) => const [
            PopupMenuItem<String>(value: '', child: Text('All')),
            PopupMenuItem<String>(value: 'DRAFT', child: Text('Draft')),
            PopupMenuItem<String>(value: 'ACTIVE', child: Text('Active')),
            PopupMenuItem<String>(value: 'EXPIRED', child: Text('Expired')),
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
        if (_mayApprove)
          ToolbarCommand(
            id: 'approve',
            label: 'Approve',
            icon: Icons.check_circle_outline,
            onPressed: row != null && status == 'DRAFT'
                ? () => unawaited(_act(row, 'approve'))
                : null,
          ),
        ToolbarCommand(
          id: 'releases',
          label: 'Releases',
          icon: Icons.receipt_long_outlined,
          onPressed: row != null && status != 'DRAFT'
              ? () => unawaited(_releases(row))
              : null,
        ),
        if (_mayManage)
          ToolbarCommand(
            id: 'close',
            label: 'Close',
            icon: Icons.lock_outline,
            onPressed: row != null && (status == 'ACTIVE' || status == 'EXPIRED')
                ? () => unawaited(_act(row, 'close'))
                : null,
          ),
        if (_mayManage)
          ToolbarCommand(
            id: 'cancel',
            label: 'Cancel',
            icon: Icons.cancel_outlined,
            onPressed: row != null && (status == 'DRAFT' || status == 'ACTIVE')
                ? () => unawaited(_act(row, 'cancel'))
                : null,
          ),
        if (_mayManage)
          ToolbarCommand(
            id: 'delete',
            label: 'Delete',
            icon: Icons.delete_outline,
            onPressed: row != null && status == 'DRAFT'
                ? () => unawaited(_delete(row))
                : null,
          ),
      ],
    );
  }

  late final ColumnChoice<RateContract> _columns = ColumnChoice(
    preferences: widget.preferences,
    stateKey: 'rate-contracts.grid',
    columns: [
      ChoosableColumn(
        column: const GridColumn(key: 'number', label: 'Number'),
        cell: (item) => item.number,
        required: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'supplier', label: 'Supplier'),
        cell: (item) => item.vendorName,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'from', label: 'Valid from'),
        cell: (item) => item.validFrom,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'to', label: 'Valid to'),
        cell: (item) => item.validTo,
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
        column: const GridColumn(key: 'reference', label: 'Reference', priority: 1),
        cell: (item) => item.reference,
      ),
    ],
  );

  Widget _grid() {
    if (_rows.isEmpty) {
      return const WorkspaceEmptyState(
        title: 'No rate contracts',
        message: 'Record the rates a supplier has agreed to hold.',
      );
    }
    return EnterpriseDataGrid<RateContract>(
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
    String rate = '',
    String discount = '',
    String quantity = '',
    this.uomId = '',
    this.drawn = '',
    this.remaining = '',
  })  : product = TextEditingController(text: product),
        rate = TextEditingController(text: rate),
        discount = TextEditingController(text: discount),
        quantity = TextEditingController(text: quantity);

  String productId;
  String uomId;
  final String drawn;
  final String remaining;
  final TextEditingController product;
  final TextEditingController rate;
  final TextEditingController discount;
  final TextEditingController quantity;

  void dispose() {
    product.dispose();
    rate.dispose();
    discount.dispose();
    quantity.dispose();
  }
}

Widget _dateBox(String label, String value, VoidCallback? onTap, {Key? key}) =>
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

/// Raise or change a rate contract; read-only once it has left draft. Pops the
/// saved [RateContract]; stays open with the server's message when refused.
class RateContractDialog extends StatefulWidget {
  const RateContractDialog({super.key, required this.api, this.existing});

  final ApiClient api;
  final RateContract? existing;

  @override
  State<RateContractDialog> createState() => _RateContractDialogState();
}

class _RateContractDialogState extends State<RateContractDialog>
    with SaveInDialog<RateContractDialog> {
  List<Vendor> _vendors = const [];
  String _vendorId = '';
  late String _validFrom;
  String _validTo = '';
  final TextEditingController _reference = TextEditingController();
  final TextEditingController _notes = TextEditingController();
  final List<_LineDraft> _lines = <_LineDraft>[];
  String? _problem;
  bool _loading = true;

  bool get _readOnly => widget.existing != null && !widget.existing!.isDraft;

  @override
  void initState() {
    super.initState();
    final RateContract? existing = widget.existing;
    _validFrom = existing != null && existing.validFrom.isNotEmpty
        ? existing.validFrom
        : _today();
    if (existing != null) {
      _vendorId = existing.vendorId;
      _validTo = existing.validTo;
      _reference.text = existing.reference;
      _notes.text = existing.notes;
      for (final RateContractLine line in existing.lines) {
        _lines.add(_LineDraft(
          productId: line.productId,
          product: '${line.productCode} · ${line.productName}',
          rate: line.rate,
          discount: line.discountPercent,
          quantity: line.contractedQuantity,
          uomId: line.uomId,
          drawn: line.drawnQuantity,
          remaining: line.remainingQuantity,
        ));
      }
    }
    if (_lines.isEmpty) _lines.add(_LineDraft());
    unawaited(_loadVendors());
  }

  @override
  void dispose() {
    _reference.dispose();
    _notes.dispose();
    for (final _LineDraft line in _lines) {
      line.dispose();
    }
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
    if (_vendorId.isEmpty) problem = 'Choose the supplier.';
    if (_validTo.isEmpty) problem ??= 'Say when the contract runs to.';
    if (_validTo.isNotEmpty && _validTo.compareTo(_validFrom) < 0) {
      problem ??= 'The contract cannot end before it starts.';
    }
    final List<Json> lines = <Json>[];
    for (final _LineDraft line in _lines) {
      if (line.productId.isEmpty && line.rate.text.trim().isEmpty) continue;
      final double? rate = double.tryParse(line.rate.text.trim());
      if (line.productId.isEmpty || rate == null || rate < 0) {
        problem ??= 'Each line needs a product and a rate.';
        continue;
      }
      final String discount = line.discount.text.trim();
      final String quantity = line.quantity.text.trim();
      if (discount.isNotEmpty && double.tryParse(discount) == null) {
        problem ??= 'A discount must be a number, or left blank.';
        continue;
      }
      if (quantity.isNotEmpty && double.tryParse(quantity) == null) {
        problem ??= 'A contracted quantity must be a number, or left blank.';
        continue;
      }
      lines.add(<String, dynamic>{
        'product_id': line.productId,
        'rate': line.rate.text.trim(),
        // Blank is left out, never sent as 0: silence takes the server's
        // default and a literal zero would be an instruction.
        if (discount.isNotEmpty) 'discount_percent': discount,
        if (line.uomId.isNotEmpty) 'uom_id': line.uomId,
        if (quantity.isNotEmpty) 'contracted_quantity': quantity,
      });
    }
    if (lines.isEmpty) problem ??= 'Add at least one line.';
    setState(() => _problem = problem);
    if (problem != null) return;
    final String reference = _reference.text.trim();
    final String notes = _notes.text.trim();
    final Json body = <String, dynamic>{
      'vendor_id': _vendorId,
      'valid_from': _validFrom,
      'valid_to': _validTo,
      if (reference.isNotEmpty) 'reference': reference,
      if (notes.isNotEmpty) 'notes': notes,
      'lines': lines,
    };
    final RateContract? existing = widget.existing;
    unawaited(saveAndClose<RateContract>(() => existing == null
        ? widget.api.createRateContract(body)
        : widget.api.updateRateContract(existing.id, body,
            expectedVersion: existing.version)));
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final bool locked = saving || _readOnly;
    final RateContract? existing = widget.existing;
    // Held inside the window: an 800-wide screen leaves the dialog 720.
    final double width =
        (MediaQuery.sizeOf(context).width - 120).clamp(400.0, 860.0);
    return AlertDialog(
      title: Text(existing == null
          ? 'New rate contract'
          : 'Contract ${existing.number}'),
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
                              key: const ValueKey('rc-problem'),
                              style: TextStyle(color: theme.colorScheme.error)),
                        ),
                      if (_readOnly)
                        Padding(
                          padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                          child: Text(
                            'This contract is ${_words(existing!.status)} '
                            'and can no longer be changed.',
                            key: const ValueKey('rc-read-only'),
                            style: theme.textTheme.bodySmall,
                          ),
                        ),
                      if (existing != null && existing.cancelReason.isNotEmpty)
                        Padding(
                          padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                          child: Text('Cancelled: ${existing.cancelReason}',
                              style: theme.textTheme.bodySmall),
                        ),
                      Row(children: [
                        Expanded(
                          flex: 3,
                          child: DropdownButtonFormField<String>(
                            key: const ValueKey('rc-vendor'),
                            initialValue: _vendorId.isEmpty ? null : _vendorId,
                            isExpanded: true,
                            decoration: const InputDecoration(
                                labelText: 'Supplier', isDense: true),
                            items: [
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
                        ),
                        const SizedBox(width: AppSpacing.md),
                        Expanded(
                          flex: 2,
                          child: _dateBox(
                              'Valid from',
                              _validFrom,
                              locked
                                  ? null
                                  : () async {
                                      final String? v =
                                          await _pickDate(context, _validFrom);
                                      if (v != null) {
                                        setState(() => _validFrom = v);
                                      }
                                    },
                              key: const ValueKey('rc-valid-from')),
                        ),
                        const SizedBox(width: AppSpacing.md),
                        Expanded(
                          flex: 2,
                          child: _dateBox(
                              'Valid to',
                              _validTo,
                              locked
                                  ? null
                                  : () async {
                                      final String? v = await _pickDate(
                                          context,
                                          _validTo.isEmpty
                                              ? _validFrom
                                              : _validTo);
                                      if (v != null) {
                                        setState(() => _validTo = v);
                                      }
                                    },
                              key: const ValueKey('rc-valid-to')),
                        ),
                      ]),
                      const SizedBox(height: AppSpacing.md),
                      Row(children: [
                        Expanded(
                          child: TextField(
                            key: const ValueKey('rc-reference'),
                            controller: _reference,
                            enabled: !locked,
                            decoration: const InputDecoration(
                                labelText: 'Reference', isDense: true),
                          ),
                        ),
                        const SizedBox(width: AppSpacing.md),
                        Expanded(
                          flex: 2,
                          child: TextField(
                            key: const ValueKey('rc-notes'),
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
                            key: const ValueKey('rc-add-line'),
                            onPressed: locked
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
      ),
      actions: [
        TextButton(
          onPressed: cancelHandler,
          child: Text(_readOnly ? 'Close' : 'Cancel'),
        ),
        if (!_readOnly)
          FilledButton(
            key: const ValueKey('rc-save'),
            onPressed: saving || _loading ? null : _save,
            child: Text(saving ? 'Saving…' : 'Save'),
          ),
      ],
    );
  }

  Widget _readOnlyBox(String label, String value, Key key) => InputDecorator(
        key: key,
        decoration: InputDecoration(labelText: label, isDense: true),
        child: Text(value.isEmpty ? '—' : value,
            maxLines: 1, overflow: TextOverflow.ellipsis),
      );

  Widget _lineRow(int index, bool locked) {
    final _LineDraft line = _lines[index];
    final bool saved = widget.existing != null && line.drawn.isNotEmpty;
    return Padding(
      key: ObjectKey(line),
      padding: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            flex: 5,
            child: ProductSearchBox(
              fieldKey: ValueKey('rc-product-$index'),
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
              key: ValueKey('rc-rate-$index'),
              controller: line.rate,
              enabled: !locked,
              keyboardType:
                  const TextInputType.numberWithOptions(decimal: true),
              decoration: const InputDecoration(labelText: 'Rate', isDense: true),
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            flex: 2,
            child: TextField(
              key: ValueKey('rc-discount-$index'),
              controller: line.discount,
              enabled: !locked,
              keyboardType:
                  const TextInputType.numberWithOptions(decimal: true),
              decoration: const InputDecoration(
                labelText: 'Discount %',
                helperText: 'Blank: none',
                isDense: true,
              ),
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            flex: 2,
            child: TextField(
              key: ValueKey('rc-quantity-$index'),
              controller: line.quantity,
              enabled: !locked,
              keyboardType:
                  const TextInputType.numberWithOptions(decimal: true),
              decoration: const InputDecoration(
                labelText: 'Quantity',
                helperText: 'Blank: no limit',
                isDense: true,
              ),
            ),
          ),
          if (saved) ...[
            const SizedBox(width: AppSpacing.sm),
            Expanded(
              flex: 1,
              child: _readOnlyBox(
                  'Drawn', line.drawn, ValueKey('rc-drawn-$index')),
            ),
            const SizedBox(width: AppSpacing.sm),
            Expanded(
              flex: 1,
              child: _readOnlyBox(
                  'Left', line.remaining, ValueKey('rc-remaining-$index')),
            ),
          ],
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

/// The purchase order lines that draw on a contract.
class RateContractReleasesDialog extends StatefulWidget {
  const RateContractReleasesDialog(
      {super.key, required this.api, required this.row});

  final ApiClient api;
  final RateContract row;

  @override
  State<RateContractReleasesDialog> createState() =>
      _RateContractReleasesDialogState();
}

class _RateContractReleasesDialogState
    extends State<RateContractReleasesDialog> {
  List<RateContractRelease> _releases = const [];
  String? _error;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    try {
      final List<RateContractRelease> rows =
          await widget.api.rateContractReleases(widget.row.id);
      if (!mounted) return;
      setState(() {
        _releases = rows;
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

  String _productName(String productId) {
    final RateContractLine? line =
        widget.row.lines.where((l) => l.productId == productId).firstOrNull;
    if (line == null) return productId;
    return line.productName.isEmpty ? line.productCode : line.productName;
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final double width =
        (MediaQuery.sizeOf(context).width - 120).clamp(400.0, 760.0);
    return AlertDialog(
      title: Text('Releases against ${widget.row.number}'),
      content: ConstrainedBox(
        constraints: BoxConstraints(maxWidth: width, maxHeight: 420),
        child: SizedBox(
          width: width,
          child: _loading
              ? const Center(child: CircularProgressIndicator())
              : _error != null
                  ? Text(_error!,
                      style: TextStyle(color: theme.colorScheme.error))
                  : _releases.isEmpty
                      ? const Text('No purchase order has drawn on this '
                          'contract yet.')
                      : SingleChildScrollView(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              for (int i = 0; i < _releases.length; i++)
                                _row(theme, i, _releases[i]),
                            ],
                          ),
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

  Widget _row(ThemeData theme, int index, RateContractRelease r) => Padding(
        key: ValueKey('rc-release-$index'),
        padding: const EdgeInsets.symmetric(vertical: AppSpacing.xs),
        child: Row(
          children: [
            Expanded(
              flex: 2,
              child: Text('${r.poNumber} · line ${r.lineNumber}',
                  overflow: TextOverflow.ellipsis),
            ),
            Expanded(
              flex: 2,
              child: Text(r.purchaseDate, overflow: TextOverflow.ellipsis),
            ),
            Expanded(
              flex: 3,
              child: Text(_productName(r.productId),
                  overflow: TextOverflow.ellipsis),
            ),
            Expanded(
              child: Text('${r.orderedQuantity} @ ${r.unitPrice}',
                  overflow: TextOverflow.ellipsis),
            ),
            Expanded(
              child: Text(
                '${_words(r.orderStatus)}'
                '${r.countsAsDrawn ? '' : ' (not drawn)'}',
                style: theme.textTheme.bodySmall,
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ],
        ),
      );
}
