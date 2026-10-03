// Landed cost vouchers (BUY-16): freight and clearing bills spread over the
// goods they brought in, so stock is worth what it cost to land. The register
// lists the vouchers, the details pane shows the charges and where each one
// went, and a new voucher is posted at once. Phase 2 only.

import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/preferences/desktop_preferences_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/goods_receipt.dart';
import '../../models/landed_cost.dart';
import '../../models/vendor.dart';
import '../workspace/desktop_framework.dart';
import '../workspace/reason_prompt.dart';

String _iso(DateTime date) => date.toIso8601String().substring(0, 10);

String _money(String value) {
  final double? parsed = double.tryParse(value);
  return parsed == null ? value : parsed.toStringAsFixed(2);
}

String _words(String status) =>
    status.isEmpty ? status : status[0] + status.substring(1).toLowerCase();

const List<(String, String)> _bases = [
  ('VALUE', 'By value'),
  ('QUANTITY', 'By quantity'),
  ('WEIGHT', 'By weight'),
];

String _basisLabel(String code) {
  for (final (String value, String label) in _bases) {
    if (value == code) return label;
  }
  return code;
}

String _vendorLabel(Vendor vendor) =>
    vendor.displayName.isNotEmpty ? vendor.displayName : vendor.name;

/// List the vouchers, post a new one and cancel a posted one.
class LandedCostsPage extends StatefulWidget {
  const LandedCostsPage({
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
  State<LandedCostsPage> createState() => _LandedCostsPageState();
}

class _LandedCostsPageState extends State<LandedCostsPage> {
  List<LandedCost> _rows = const [];
  LandedCost? _detail;
  String? _error;
  String? _selectedId;
  bool _loading = true;
  final TextEditingController _search = TextEditingController();

  bool get _mayView => widget.permissions.hasPermission('PURCHASE_VIEW');
  bool get _mayManage => widget.permissions.hasPermission('PURCHASE_APPROVE');

  @override
  void initState() {
    super.initState();
    if (widget.hasActiveFirm && _mayView) unawaited(_load());
  }

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final List<LandedCost> rows = await widget.api.landedCosts();
      if (!mounted) return;
      setState(() {
        _rows = rows;
        _loading = false;
      });
      if (_selectedId != null) unawaited(_read(_selectedId!));
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.message;
        _loading = false;
      });
    }
  }

  /// Re-read the picked voucher, so the details are the server's and not the
  /// list's.
  Future<void> _read(String id) async {
    try {
      final LandedCost voucher = await widget.api.landedCost(id);
      if (!mounted || _selectedId != id) return;
      setState(() => _detail = voucher);
    } on ApiException catch (error) {
      if (!mounted) return;
      _tell(error.message, AppNotificationKind.error);
    }
  }

  void _select(LandedCost row) {
    setState(() {
      _selectedId = row.id;
      _detail = row;
    });
    unawaited(_read(row.id));
  }

  List<LandedCost> get _shown {
    final String q = _search.text.trim().toLowerCase();
    if (q.isEmpty) return _rows;
    return _rows
        .where((row) =>
            row.voucherNumber.toLowerCase().contains(q) ||
            row.remarks.toLowerCase().contains(q))
        .toList();
  }

  LandedCost? get _selected {
    if (_selectedId == null) return null;
    if (_detail != null && _detail!.id == _selectedId) return _detail;
    return _rows.where((row) => row.id == _selectedId).firstOrNull;
  }

  void _tell(String message, AppNotificationKind kind) =>
      NotificationService.show(context, message, kind: kind);

  Future<void> _new() async {
    final LandedCost? saved = await showDialog<LandedCost>(
      context: context,
      barrierDismissible: false,
      builder: (_) => LandedCostDialog(api: widget.api),
    );
    if (saved == null || !mounted) return;
    setState(() {
      _selectedId = saved.id;
      _detail = saved;
    });
    _tell(
        'Voucher ${saved.voucherNumber} posted.', AppNotificationKind.success);
    await _load();
  }

  Future<void> _cancel(LandedCost voucher) async {
    final String? reason = await askForReason(
      context,
      title: 'Cancel voucher ${voucher.voucherNumber}',
      explanation: 'The charges come back out of the goods’ cost and the '
          'posting is reversed.',
      confirmLabel: 'Cancel voucher',
    );
    if (reason == null || !mounted) return;
    try {
      await widget.api.cancelLandedCost(voucher.id, reason);
      if (!mounted) return;
      _tell('Voucher ${voucher.voucherNumber} cancelled.',
          AppNotificationKind.success);
      await _load();
    } on ApiException catch (error) {
      if (!mounted) return;
      _tell(error.message, AppNotificationKind.error);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.hasActiveFirm) {
      return const WorkspaceEmptyState(
        title: 'Choose a firm',
        message: 'Landed cost vouchers belong to one firm’s books.',
      );
    }
    if (!_mayView) {
      return const WorkspaceEmptyState(
        icon: Icons.lock_outline,
        title: 'You cannot see landed cost vouchers',
        message: 'Reading them needs the view purchases permission.',
      );
    }
    final LandedCost? picked = _selected;
    return ManagementWorkspaceLayout(
      notice: 'Freight and clearing bills spread over the goods they brought '
          'in, by value, quantity or weight. The share for stock on hand is '
          'added to its cost; the share for goods already sold goes to cost '
          'of sales.',
      toolbar: _toolbar(picked),
      searchPanel: SearchFilterPanel(
        controller: _search,
        hintText: 'Search voucher number or remarks',
        onSearch: (_) => setState(() {}),
      ),
      selectionBar: true,
      selection: picked == null
          ? null
          : SelectionSummary.document(
              number: picked.voucherNumber,
              status: picked.status,
              total: picked.totalAmount,
              onClear: () => setState(() {
                _selectedId = null;
                _detail = null;
              }),
            ),
      detailsWidth: 460,
      detailsPanel: picked == null ? null : _details(picked),
      primaryContent: _loading
          ? const Center(child: CircularProgressIndicator())
          : Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                if (_error != null)
                  Padding(
                    padding: const EdgeInsets.only(top: AppSpacing.sm),
                    child: Text(_error!,
                        style: TextStyle(
                            color: Theme.of(context).colorScheme.error)),
                  ),
                const SizedBox(height: AppSpacing.md),
                Expanded(child: _grid()),
              ],
            ),
      statusBar: WorkspaceStatusBar(
        total: _rows.length,
        selected: _selectedId != null,
        message: 'Landed cost vouchers',
      ),
    );
  }

  WorkspaceToolbar _toolbar(LandedCost? selected) {
    final LandedCost? v = selected;
    return WorkspaceToolbar(
      trailing: [
        ColumnsButton(
          onPressed: () async {
            if (await _columns.choose(context) && mounted) setState(() {});
          },
        ),
      ],
      actions: [
        ToolbarAction.refresh,
        if (_mayManage) ToolbarAction.newItem,
      ],
      isEnabled: (action) => true,
      onAction: (action) {
        switch (action) {
          case ToolbarAction.newItem:
            unawaited(_new());
          default:
            unawaited(_load());
        }
      },
      commands: [
        if (_mayManage)
          ToolbarCommand(
            id: 'cancel',
            label: 'Cancel',
            icon: Icons.cancel_outlined,
            onPressed:
                v != null && v.isPosted ? () => unawaited(_cancel(v)) : null,
          ),
      ],
    );
  }

  late final ColumnChoice<LandedCost> _columns = ColumnChoice(
    preferences: widget.preferences,
    stateKey: 'landed-costs.grid',
    columns: [
      ChoosableColumn(
        column: const GridColumn(key: 'number', label: 'Number'),
        cell: (item) => item.voucherNumber,
        required: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'date', label: 'Date', priority: 2),
        cell: (item) => item.voucherDate,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'basis', label: 'Spread', priority: 2),
        cell: (item) => _basisLabel(item.basis),
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'total', label: 'Total', numeric: true),
        cell: (item) => _money(item.totalAmount),
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(
            key: 'stock', label: 'To stock', numeric: true, priority: 1),
        cell: (item) => _money(item.inventoryAmount),
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(
            key: 'cogs', label: 'To cost of sales', numeric: true, priority: 1),
        cell: (item) => _money(item.cogsAmount),
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'status', label: 'Status'),
        cell: (item) => _words(item.status),
        shownByDefault: true,
      ),
    ],
  );

  Widget _grid() {
    final List<LandedCost> rows = _shown;
    if (rows.isEmpty) {
      return WorkspaceEmptyState(
        title: 'No vouchers yet',
        message: _mayManage
            ? 'Add a freight or clearing bill to the cost of the goods it '
                'brought in.'
            : 'Posting one needs the approve purchases permission.',
      );
    }
    return EnterpriseDataGrid<LandedCost>(
      items: rows,
      total: rows.length,
      pageOffset: 0,
      rowsPerPage: rows.length,
      availableRowsPerPage: [rows.length],
      selectedId: _selectedId,
      columns: _columns.gridColumns,
      id: (row) => row.id,
      cells: _columns.cells,
      onSelect: _select,
      onOpen: _select,
      onPageChanged: (_) {},
    );
  }

  Widget _amountRow(String label, String value, {bool strong = false}) {
    final TextStyle? style = strong
        ? Theme.of(context).textTheme.titleSmall
        : Theme.of(context).textTheme.bodyMedium;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(children: [
        Expanded(child: Text(label, style: style)),
        Text(_money(value), style: style),
      ]),
    );
  }

  Widget _table(List<String> heads, List<List<String>> rows, Key key) {
    return SingleChildScrollView(
      key: key,
      scrollDirection: Axis.horizontal,
      child: DataTable(
        columnSpacing: AppSpacing.md,
        headingRowHeight: 32,
        dataRowMinHeight: 28,
        dataRowMaxHeight: 32,
        columns: [
          for (final String head in heads) DataColumn(label: Text(head)),
        ],
        rows: [
          for (final List<String> row in rows)
            DataRow(cells: [
              for (final String cell in row) DataCell(Text(cell)),
            ]),
        ],
      ),
    );
  }

  Widget _details(LandedCost voucher) {
    final ThemeData theme = Theme.of(context);
    return SingleChildScrollView(
      key: const ValueKey('landed-cost-details'),
      padding: const EdgeInsets.all(AppSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(children: [
            Expanded(
              child: Text(voucher.voucherNumber,
                  style: theme.textTheme.titleMedium),
            ),
            StatusBadge.fromStatus(voucher.status),
          ]),
          Text(
            '${voucher.voucherDate} · ${_basisLabel(voucher.basis)}',
            style: theme.textTheme.bodySmall,
          ),
          const SizedBox(height: AppSpacing.md),
          _amountRow('To stock on hand', voucher.inventoryAmount),
          _amountRow('To cost of sales', voucher.cogsAmount),
          const Divider(),
          _amountRow('Total', voucher.totalAmount, strong: true),
          if (voucher.remarks.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: AppSpacing.sm),
              child: Text(voucher.remarks, style: theme.textTheme.bodySmall),
            ),
          if (voucher.cancelReason.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: AppSpacing.sm),
              child: Text('Cancelled: ${voucher.cancelReason}',
                  style: theme.textTheme.bodySmall),
            ),
          const SizedBox(height: AppSpacing.md),
          Text('Charges', style: theme.textTheme.titleSmall),
          _table(
            const ['Charge', 'Supplier', 'Bill', 'Amount'],
            [
              for (final LandedCostCharge c in voucher.charges)
                [
                  c.description,
                  c.vendorName,
                  c.billReference,
                  _money(c.amount),
                ],
            ],
            const ValueKey('landed-cost-charges'),
          ),
          const SizedBox(height: AppSpacing.md),
          Text('Where it went', style: theme.textTheme.titleSmall),
          _table(
            const ['Receipt', 'Product', 'Qty', 'Share', 'To stock', 'To COGS'],
            [
              for (final LandedCostAllocation a in voucher.allocations)
                [
                  a.grnNumber,
                  a.productName,
                  a.quantity,
                  _money(a.amount),
                  _money(a.inventoryAmount),
                  _money(a.cogsAmount),
                ],
            ],
            const ValueKey('landed-cost-allocations'),
          ),
        ],
      ),
    );
  }
}

class _ChargeRow {
  final TextEditingController description = TextEditingController();
  final TextEditingController amount = TextEditingController();
  final TextEditingController bill = TextEditingController();
  String? vendorId;

  void dispose() {
    description.dispose();
    amount.dispose();
    bill.dispose();
  }
}

/// Post a voucher: the receipts, the charges and how to spread them. The call
/// runs inside the dialog, which pops the posted [LandedCost] or stays open
/// with the server's message.
class LandedCostDialog extends StatefulWidget {
  const LandedCostDialog({super.key, required this.api});

  final ApiClient api;

  @override
  State<LandedCostDialog> createState() => _LandedCostDialogState();
}

class _LandedCostDialogState extends State<LandedCostDialog>
    with SaveInDialog {
  final TextEditingController _remarks = TextEditingController();
  final List<_ChargeRow> _charges = <_ChargeRow>[_ChargeRow()];
  final Set<String> _picked = <String>{};
  List<GoodsReceiptRecord> _receipts = const [];
  List<Vendor> _vendors = const [];
  DateTime _date = DateTime.now();
  String _basis = 'VALUE';
  bool _loading = true;
  String? _problem;
  String? _loadNote;

  @override
  void initState() {
    super.initState();
    unawaited(_read());
  }

  @override
  void dispose() {
    _remarks.dispose();
    for (final _ChargeRow row in _charges) {
      row.dispose();
    }
    super.dispose();
  }

  Future<void> _read() async {
    try {
      final List<dynamic> found = await Future.wait<dynamic>([
        fetchAllPages<GoodsReceiptRecord>(
          (int page) => widget.api.goodsReceipts(
            page: page,
            pageSize: maxApiPageSize,
            sortBy: 'receipt_date',
            descending: true,
            filters: const {'status': 'COMPLETED'},
          ),
        ),
        fetchAllPages<Vendor>(
          (int page) => widget.api.vendors(page: page),
        ),
      ]);
      if (!mounted) return;
      setState(() {
        _receipts = found[0] as List<GoodsReceiptRecord>;
        _vendors = found[1] as List<Vendor>;
        _loading = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _loadNote = error.message;
        _loading = false;
      });
    }
  }

  Future<void> _pickDate() async {
    final DateTime? picked = await showDatePicker(
      context: context,
      initialDate: _date,
      firstDate: DateTime(2000),
      lastDate: DateTime(2100),
    );
    if (picked != null) setState(() => _date = picked);
  }

  double _number(String text) => double.tryParse(text.trim()) ?? 0;

  double get _total {
    double sum = 0;
    for (final _ChargeRow row in _charges) {
      sum += _number(row.amount.text);
    }
    return sum;
  }

  void _save() {
    String? problem;
    if (_picked.isEmpty) {
      problem = 'Choose at least one receipt the charges belong to.';
    } else if (_charges.any((row) =>
        row.description.text.trim().isEmpty || _number(row.amount.text) <= 0)) {
      problem = 'Every charge needs a description and an amount above zero.';
    }
    setState(() => _problem = problem);
    if (problem != null) return;
    final String remarks = _remarks.text.trim();
    unawaited(saveAndClose<LandedCost>(
      () => widget.api.postLandedCost(<String, dynamic>{
        'voucher_date': _iso(_date),
        'basis': _basis,
        'goods_receipt_ids': _picked.toList(),
        'charges': [
          for (final _ChargeRow row in _charges)
            <String, dynamic>{
              'description': row.description.text.trim(),
              'amount': row.amount.text.trim(),
              'vendor_id': row.vendorId,
              'bill_reference':
                  row.bill.text.trim().isEmpty ? null : row.bill.text.trim(),
            },
        ],
        'remarks': remarks.isEmpty ? null : remarks,
      }),
    ));
  }

  Widget _receiptRow(GoodsReceiptRecord receipt) => CheckboxListTile(
        key: ValueKey('landed-receipt-${receipt.id}'),
        dense: true,
        controlAffinity: ListTileControlAffinity.leading,
        contentPadding: EdgeInsets.zero,
        value: _picked.contains(receipt.id),
        onChanged: saving
            ? null
            : (on) => setState(() {
                  if (on == true) {
                    _picked.add(receipt.id);
                  } else {
                    _picked.remove(receipt.id);
                  }
                }),
        title: Text(
          [
            receipt.grnNumber,
            receipt.receiptDate,
            if (receipt.vendorName.isNotEmpty) receipt.vendorName,
          ].join(' · '),
          overflow: TextOverflow.ellipsis,
        ),
      );

  Widget _chargeRow(int index) {
    final _ChargeRow row = _charges[index];
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Expanded(
          flex: 3,
          child: TextField(
            key: ValueKey('landed-charge-description-$index'),
            controller: row.description,
            enabled: !saving,
            decoration:
                const InputDecoration(labelText: 'Description', isDense: true),
          ),
        ),
        const SizedBox(width: AppSpacing.sm),
        SizedBox(
          width: 110,
          child: TextField(
            key: ValueKey('landed-charge-amount-$index'),
            controller: row.amount,
            enabled: !saving,
            onChanged: (_) => setState(() {}),
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            decoration:
                const InputDecoration(labelText: 'Amount', isDense: true),
          ),
        ),
        const SizedBox(width: AppSpacing.sm),
        Expanded(
          flex: 3,
          child: DropdownButtonFormField<String?>(
            key: ValueKey('landed-charge-vendor-$index'),
            isExpanded: true,
            initialValue: row.vendorId,
            decoration: const InputDecoration(
                labelText: 'Supplier (optional)', isDense: true),
            items: [
              const DropdownMenuItem<String?>(value: null, child: Text('None')),
              for (final Vendor vendor in _vendors)
                DropdownMenuItem<String?>(
                  value: vendor.id,
                  child: Text(_vendorLabel(vendor),
                      overflow: TextOverflow.ellipsis),
                ),
            ],
            onChanged:
                saving ? null : (id) => setState(() => row.vendorId = id),
          ),
        ),
        const SizedBox(width: AppSpacing.sm),
        Expanded(
          flex: 2,
          child: TextField(
            key: ValueKey('landed-charge-bill-$index'),
            controller: row.bill,
            enabled: !saving,
            decoration:
                const InputDecoration(labelText: 'Bill ref.', isDense: true),
          ),
        ),
        IconButton(
          key: ValueKey('landed-charge-remove-$index'),
          tooltip: 'Remove charge',
          icon: const Icon(Icons.close),
          onPressed: saving || _charges.length == 1
              ? null
              : () => setState(() => _charges.removeAt(index).dispose()),
        ),
      ]),
    );
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return AlertDialog(
      title: const Text('New landed cost voucher'),
      content: SizedBox(
        width: 820,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              saveErrorBanner(),
              if (_loadNote != null)
                Padding(
                  padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                  child: Text(_loadNote!,
                      style: TextStyle(color: theme.colorScheme.error)),
                ),
              Text(
                'Book the freight or clearing bill itself to “Expenses '
                'Included in Valuation”; this voucher moves it into the '
                'goods’ cost.',
                style: theme.textTheme.bodySmall,
              ),
              const SizedBox(height: AppSpacing.md),
              Row(children: [
                Expanded(
                  child: InkWell(
                    key: const ValueKey('landed-date'),
                    onTap: saving ? null : () => unawaited(_pickDate()),
                    child: InputDecorator(
                      decoration:
                          const InputDecoration(labelText: 'Voucher date'),
                      child: Text(_iso(_date)),
                    ),
                  ),
                ),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                  child: DropdownButtonFormField<String>(
                    key: const ValueKey('landed-basis'),
                    isExpanded: true,
                    initialValue: _basis,
                    decoration:
                        const InputDecoration(labelText: 'Spread the charges'),
                    items: [
                      for (final (String code, String label) in _bases)
                        DropdownMenuItem<String>(
                            value: code, child: Text(label)),
                    ],
                    onChanged: saving
                        ? null
                        : (b) => setState(() => _basis = b ?? _basis),
                  ),
                ),
              ]),
              const SizedBox(height: AppSpacing.md),
              Text('Goods receipts (${_picked.length} chosen)',
                  style: theme.textTheme.titleSmall),
              if (_loading)
                const Padding(
                  padding: EdgeInsets.all(AppSpacing.md),
                  child: Center(child: CircularProgressIndicator()),
                )
              else if (_receipts.isEmpty)
                const Text('There are no completed goods receipts.')
              else
                ConstrainedBox(
                  constraints: const BoxConstraints(maxHeight: 200),
                  child: ListView(
                    shrinkWrap: true,
                    children: [
                      for (final GoodsReceiptRecord r in _receipts)
                        _receiptRow(r),
                    ],
                  ),
                ),
              const SizedBox(height: AppSpacing.md),
              Text('Charges', style: theme.textTheme.titleSmall),
              const SizedBox(height: AppSpacing.sm),
              for (int i = 0; i < _charges.length; i++) _chargeRow(i),
              Align(
                alignment: Alignment.centerLeft,
                child: TextButton.icon(
                  key: const ValueKey('landed-add-charge'),
                  onPressed: saving || _charges.length >= 20
                      ? null
                      : () => setState(() => _charges.add(_ChargeRow())),
                  icon: const Icon(Icons.add),
                  label: const Text('Add charge'),
                ),
              ),
              Text('Total ${_total.toStringAsFixed(2)}',
                  key: const ValueKey('landed-total'),
                  style: theme.textTheme.titleSmall),
              const SizedBox(height: AppSpacing.md),
              TextField(
                key: const ValueKey('landed-remarks'),
                controller: _remarks,
                enabled: !saving,
                decoration: const InputDecoration(labelText: 'Remarks'),
              ),
              if (_problem != null)
                Padding(
                  padding: const EdgeInsets.only(top: AppSpacing.sm),
                  child: Text(_problem!,
                      key: const ValueKey('landed-problem'),
                      style: TextStyle(color: theme.colorScheme.error)),
                ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(onPressed: cancelHandler, child: const Text('Cancel')),
        FilledButton(
          key: const ValueKey('landed-save'),
          onPressed: saving || _loading ? null : _save,
          child: Text(saving ? 'Posting…' : 'Post voucher'),
        ),
      ],
    );
  }
}
