// Supplier gifts (BUY-2): the register of what suppliers gave the firm, a
// dialog to record one (it posts its journal), a take-back that reverses it,
// and the year's 194R summary. Phase 2 only.

import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/preferences/desktop_preferences_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/entities.dart';
import '../../models/finance.dart';
import '../../models/supplier_gift.dart';
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

/// What each `kept_by` code is called on screen.
const Map<String, String> _keptByLabels = {
  'ASSET': 'Business asset',
  'EXPENSE': 'Used up by business',
  'OWNER': 'Owner',
};

/// List the register and move it along.
class SupplierGiftsPage extends StatefulWidget {
  const SupplierGiftsPage({
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
  State<SupplierGiftsPage> createState() => _SupplierGiftsPageState();
}

class _SupplierGiftsPageState extends State<SupplierGiftsPage> {
  List<SupplierGift> _rows = const [];
  List<SupplierGiftSummary> _summary = const [];
  String? _error;
  String? _selectedId;
  bool _loading = true;
  bool _showSummary = false;
  final TextEditingController _search = TextEditingController();

  bool get _mayView => widget.permissions.hasPermission('VENDOR_VIEW');
  bool get _mayManage =>
      widget.permissions.hasPermission('SUPPLIER_GIFT_MANAGE');

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
      final List<SupplierGift> rows = await widget.api.supplierGifts();
      final List<SupplierGiftSummary> summary =
          await widget.api.supplierGiftSummary(on: _iso(DateTime.now()));
      if (!mounted) return;
      setState(() {
        _rows = rows;
        _summary = summary;
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

  List<SupplierGift> get _shown {
    final String q = _search.text.trim().toLowerCase();
    if (q.isEmpty) return _rows;
    return _rows
        .where((row) =>
            row.giftNumber.toLowerCase().contains(q) ||
            row.vendorName.toLowerCase().contains(q) ||
            row.item.toLowerCase().contains(q))
        .toList();
  }

  SupplierGift? get _selected =>
      _rows.where((row) => row.id == _selectedId).firstOrNull;

  void _tell(String message, AppNotificationKind kind) =>
      NotificationService.show(context, message, kind: kind);

  Future<void> _record() async {
    final SupplierGift? saved = await showDialog<SupplierGift>(
      context: context,
      barrierDismissible: false,
      builder: (_) => RecordSupplierGiftDialog(api: widget.api),
    );
    if (saved == null || !mounted) return;
    setState(() => _selectedId = saved.id);
    _tell('Gift ${saved.giftNumber} recorded.', AppNotificationKind.success);
    await _load();
  }

  Future<void> _takeBack(SupplierGift gift) async {
    final String? reason = await askForReason(
      context,
      title: 'Take back gift ${gift.giftNumber}',
      explanation: 'The journal it posted is reversed. The reason is kept on '
          'the gift.',
      confirmLabel: 'Take back',
      cancelLabel: 'Keep it',
    );
    if (reason == null || !mounted) return;
    try {
      await widget.api.cancelSupplierGift(
        gift.id,
        reason: reason,
        expectedVersion: gift.version,
      );
      if (!mounted) return;
      _tell('Gift ${gift.giftNumber} taken back.', AppNotificationKind.success);
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
        message: 'Supplier gifts belong to one firm’s books.',
      );
    }
    if (!_mayView) {
      return const WorkspaceEmptyState(
        icon: Icons.lock_outline,
        title: 'You cannot see supplier gifts',
        message: 'Reading them needs the view suppliers permission.',
      );
    }
    final SupplierGift? picked = _selected;
    return ManagementWorkspaceLayout(
      notice: 'Gifts suppliers give the firm, in cash or kind. Each one posts '
          'to the books as the firm keeps it, and the 194R summary shows who '
          'has gone past the yearly limit.',
      toolbar: _toolbar(picked),
      searchPanel: SearchFilterPanel(
        controller: _search,
        hintText: 'Search gift, supplier or item',
        onSearch: (_) => setState(() {}),
      ),
      selectionBar: true,
      selection: picked == null || _showSummary
          ? null
          : SelectionSummary.document(
              number: picked.giftNumber,
              party: picked.vendorName,
              status: picked.status,
              total: picked.value,
              onClear: () => setState(() => _selectedId = null),
            ),
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
                const SizedBox(height: AppSpacing.sm),
                Align(
                  alignment: Alignment.centerLeft,
                  child: SegmentedButton<bool>(
                    key: const ValueKey('gifts-view'),
                    showSelectedIcon: false,
                    segments: const [
                      ButtonSegment<bool>(
                          value: false,
                          label: Text('Register'),
                          icon: Icon(Icons.card_giftcard_outlined)),
                      ButtonSegment<bool>(
                          value: true,
                          label: Text('194R summary'),
                          icon: Icon(Icons.summarize_outlined)),
                    ],
                    selected: {_showSummary},
                    onSelectionChanged: (value) =>
                        setState(() => _showSummary = value.first),
                  ),
                ),
                const SizedBox(height: AppSpacing.sm),
                Expanded(child: _showSummary ? _summaryGrid() : _grid()),
                if (!_showSummary &&
                    picked != null &&
                    picked.cancelReason.isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.only(top: AppSpacing.sm),
                    child: Text('Taken back: ${picked.cancelReason}',
                        style: Theme.of(context).textTheme.bodySmall),
                  ),
              ],
            ),
      statusBar: WorkspaceStatusBar(
        total: _showSummary ? _summary.length : _rows.length,
        selected: _selectedId != null && !_showSummary,
        message: _showSummary ? '194R summary' : 'Supplier gifts',
      ),
    );
  }

  WorkspaceToolbar _toolbar(SupplierGift? selected) {
    final bool canTakeBack = selected != null && selected.isPosted;
    return WorkspaceToolbar(
      actions: [
        ToolbarAction.refresh,
        if (_mayManage) ToolbarAction.newItem,
      ],
      isEnabled: (action) => true,
      onAction: (action) {
        switch (action) {
          case ToolbarAction.newItem:
            unawaited(_record());
          default:
            unawaited(_load());
        }
      },
      commands: [
        if (_mayManage)
          ToolbarCommand(
            id: 'take-back',
            label: 'Take back',
            icon: Icons.undo_outlined,
            onPressed: canTakeBack && !_showSummary
                ? () => unawaited(_takeBack(selected))
                : null,
          ),
      ],
    );
  }

  late final ColumnChoice<SupplierGift> _columns = ColumnChoice(
    preferences: widget.preferences,
    stateKey: 'supplier-gifts.grid',
    columns: [
      ChoosableColumn(
        column: const GridColumn(key: 'number', label: 'Gift'),
        cell: (item) => item.giftNumber,
        required: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'date', label: 'Date'),
        cell: (item) => item.giftDate,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'supplier', label: 'Supplier'),
        cell: (item) => item.vendorName,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'item', label: 'Item'),
        cell: (item) => item.item,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'value', label: 'Value', numeric: true),
        cell: (item) => _money(item.value),
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'kept', label: 'Kept by', priority: 1),
        cell: (item) => _keptByLabels[item.keptBy] ?? item.keptBy,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(
            key: 'tds', label: '194R TDS', numeric: true, priority: 2),
        cell: (item) => _money(item.tds194rAmount),
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'scheme', label: 'Scheme', priority: 2),
        cell: (item) => item.schemeName,
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
    final List<SupplierGift> rows = _shown;
    if (rows.isEmpty) {
      return WorkspaceEmptyState(
        title: 'No gifts recorded yet',
        message: _mayManage
            ? 'Record a gift a supplier gave the firm.'
            : 'Recording one needs the manage supplier gifts permission.',
      );
    }
    return EnterpriseDataGrid<SupplierGift>(
      items: rows,
      total: rows.length,
      pageOffset: 0,
      rowsPerPage: rows.length,
      availableRowsPerPage: [rows.length],
      selectedId: _selectedId,
      columns: _columns.gridColumns,
      id: (row) => row.id,
      cells: _columns.cells,
      onSelect: (row) => setState(() => _selectedId = row.id),
      onOpen: (row) => setState(() => _selectedId = row.id),
      onPageChanged: (_) {},
    );
  }

  static const List<GridColumn> _summaryColumns = [
    GridColumn(key: 'supplier', label: 'Supplier'),
    GridColumn(key: 'gifts', label: 'Gifts', numeric: true),
    GridColumn(key: 'value', label: 'Total value', numeric: true),
    GridColumn(key: 'tds', label: 'TDS deducted', numeric: true),
    GridColumn(key: 'over', label: 'Over the limit'),
  ];

  Widget _summaryGrid() {
    final List<SupplierGiftSummary> rows = _summary;
    if (rows.isEmpty) {
      return const WorkspaceEmptyState(
        title: 'No gifts this year',
        message: 'Nothing has been recorded in the current financial year.',
      );
    }
    final SupplierGiftSummary first = rows.first;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          'Financial year ${first.yearFrom} to ${first.yearTo}. Suppliers over '
          'the 194R limit are marked in red.',
          style: Theme.of(context).textTheme.bodySmall,
        ),
        const SizedBox(height: AppSpacing.sm),
        Expanded(
          child: EnterpriseDataGrid<SupplierGiftSummary>(
            items: rows,
            total: rows.length,
            pageOffset: 0,
            rowsPerPage: rows.length,
            availableRowsPerPage: [rows.length],
            columns: _summaryColumns,
            id: (row) => row.vendorId,
            cells: (row) => [
              row.vendorName,
              '${row.gifts}',
              _money(row.totalValue),
              _money(row.tdsDeducted),
              row.overThreshold ? 'Yes' : 'No',
            ],
            alertCell: (column, row) => row.overThreshold,
            onSelect: (_) {},
            onPageChanged: (_) {},
          ),
        ),
      ],
    );
  }
}

/// Record a gift: pops the saved [SupplierGift]; stays open with the server's
/// message on a refusal. [vendorId] / [vendorName] fix the supplier (from a
/// goods receipt) and [goodsReceiptId] ties the gift to that delivery.
class RecordSupplierGiftDialog extends StatefulWidget {
  const RecordSupplierGiftDialog({
    super.key,
    required this.api,
    this.vendorId,
    this.vendorName,
    this.goodsReceiptId,
  });

  final ApiClient api;
  final String? vendorId;
  final String? vendorName;
  final String? goodsReceiptId;

  @override
  State<RecordSupplierGiftDialog> createState() =>
      _RecordSupplierGiftDialogState();
}

class _RecordSupplierGiftDialogState extends State<RecordSupplierGiftDialog>
    with SaveInDialog {
  final TextEditingController _item = TextEditingController();
  final TextEditingController _value = TextEditingController();
  final TextEditingController _scheme = TextEditingController();
  final TextEditingController _tds = TextEditingController();
  final TextEditingController _remarks = TextEditingController();
  DateTime _date = DateTime.now();
  List<Vendor> _vendors = const [];
  List<LedgerAccount> _accounts = const [];
  String? _vendorId;
  String _keptBy = 'ASSET';
  String? _accountId;
  String? _problem;
  String? _loadNote;

  bool get _fixedVendor => widget.vendorId != null;

  @override
  void initState() {
    super.initState();
    _vendorId = widget.vendorId;
    if (!_fixedVendor) unawaited(_readVendors());
    unawaited(_readAccounts());
  }

  @override
  void dispose() {
    _item.dispose();
    _value.dispose();
    _scheme.dispose();
    _tds.dispose();
    _remarks.dispose();
    super.dispose();
  }

  Future<void> _readVendors() async {
    try {
      final List<Vendor> vendors =
          await fetchAllPages<Vendor>((page) => widget.api.vendors(page: page));
      if (!mounted) return;
      setState(() => _vendors = vendors);
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() => _loadNote = error.message);
    }
  }

  Future<void> _readAccounts() async {
    try {
      final PagedResult<LedgerAccount> found =
          await widget.api.ledgerAccounts(isActive: true);
      if (!mounted) return;
      setState(() => _accounts = found.items);
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() => _loadNote = error.message);
    }
  }

  /// The accounts the chosen "Kept by" can land in: an asset or an expense
  /// account, matching the choice. Owner has none.
  List<LedgerAccount> get _accountChoices =>
      _accounts.where((a) => a.accountType == _keptBy).toList();

  void _save() {
    String? problem;
    final double? value = double.tryParse(_value.text.trim());
    final String tdsText = _tds.text.trim();
    final double? tds = tdsText.isEmpty ? 0 : double.tryParse(tdsText);
    if (_vendorId == null) {
      problem = 'Choose the supplier.';
    } else if (_item.text.trim().isEmpty) {
      problem = 'Say what the gift is.';
    } else if (value == null || value <= 0) {
      problem = 'The value must be more than zero.';
    } else if (tds == null || tds < 0) {
      problem = 'The 194R TDS deducted must be zero or more.';
    } else if (_keptBy != 'OWNER' && _accountId == null) {
      problem = 'Choose the account the gift is booked to.';
    }
    setState(() => _problem = problem);
    if (problem != null) return;
    final String scheme = _scheme.text.trim();
    final String remarks = _remarks.text.trim();
    unawaited(saveAndClose<SupplierGift>(
      () => widget.api.createSupplierGift(<String, dynamic>{
        'gift_date': _iso(_date),
        'vendor_id': _vendorId,
        'item': _item.text.trim(),
        'value': _value.text.trim(),
        'kept_by': _keptBy,
        if (_keptBy != 'OWNER') 'debit_account_id': _accountId,
        if (widget.goodsReceiptId != null)
          'goods_receipt_id': widget.goodsReceiptId,
        if (scheme.isNotEmpty) 'scheme_name': scheme,
        'tds_194r_amount': tdsText.isEmpty ? '0' : tdsText,
        if (remarks.isNotEmpty) 'remarks': remarks,
      }),
    ));
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

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return AlertDialog(
      title: const Text('Record supplier gift'),
      content: SizedBox(
        width: 560,
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
              Row(children: [
                Expanded(
                  child: InkWell(
                    key: const ValueKey('gift-date'),
                    onTap: saving ? null : () => unawaited(_pickDate()),
                    child: InputDecorator(
                      decoration: const InputDecoration(labelText: 'Date'),
                      child: Text(_iso(_date)),
                    ),
                  ),
                ),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                  child: _fixedVendor
                      ? InputDecorator(
                          key: const ValueKey('gift-vendor-fixed'),
                          decoration:
                              const InputDecoration(labelText: 'Supplier'),
                          child: Text(widget.vendorName ?? '',
                              overflow: TextOverflow.ellipsis),
                        )
                      : DropdownButtonFormField<String>(
                          key: const ValueKey('gift-vendor'),
                          isExpanded: true,
                          initialValue: _vendorId,
                          decoration:
                              const InputDecoration(labelText: 'Supplier'),
                          items: [
                            for (final Vendor v in _vendors)
                              DropdownMenuItem<String>(
                                value: v.id,
                                child: Text(
                                  v.displayName.isEmpty
                                      ? v.name
                                      : v.displayName,
                                  overflow: TextOverflow.ellipsis,
                                ),
                              ),
                          ],
                          onChanged: saving
                              ? null
                              : (id) => setState(() => _vendorId = id),
                        ),
                ),
              ]),
              const SizedBox(height: AppSpacing.md),
              Row(children: [
                Expanded(
                  flex: 3,
                  child: TextField(
                    key: const ValueKey('gift-item'),
                    controller: _item,
                    enabled: !saving,
                    decoration: const InputDecoration(labelText: 'Item'),
                  ),
                ),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                  flex: 2,
                  child: TextField(
                    key: const ValueKey('gift-value'),
                    controller: _value,
                    enabled: !saving,
                    keyboardType:
                        const TextInputType.numberWithOptions(decimal: true),
                    decoration: const InputDecoration(labelText: 'Value'),
                  ),
                ),
              ]),
              const SizedBox(height: AppSpacing.md),
              DropdownButtonFormField<String>(
                key: const ValueKey('gift-kept-by'),
                isExpanded: true,
                initialValue: _keptBy,
                decoration: const InputDecoration(labelText: 'Kept by'),
                items: [
                  for (final MapEntry<String, String> e
                      in _keptByLabels.entries)
                    DropdownMenuItem<String>(
                        value: e.key, child: Text(e.value)),
                ],
                onChanged: saving
                    ? null
                    : (code) => setState(() {
                          _keptBy = code ?? 'ASSET';
                          _accountId = null;
                        }),
              ),
              if (_keptBy != 'OWNER') ...[
                const SizedBox(height: AppSpacing.md),
                DropdownButtonFormField<String>(
                  key: ValueKey('gift-account-$_keptBy'),
                  isExpanded: true,
                  initialValue: _accountId,
                  decoration: InputDecoration(
                    labelText: _keptBy == 'ASSET'
                        ? 'Asset account'
                        : 'Expense account',
                    helperText: _keptBy == 'ASSET'
                        ? 'Where the gift is held on the books.'
                        : 'Where its cost is booked.',
                  ),
                  items: [
                    for (final LedgerAccount a in _accountChoices)
                      DropdownMenuItem<String>(
                        value: a.id,
                        child: Text('${a.code} · ${a.name}',
                            overflow: TextOverflow.ellipsis),
                      ),
                  ],
                  onChanged:
                      saving ? null : (id) => setState(() => _accountId = id),
                ),
              ],
              const SizedBox(height: AppSpacing.md),
              Row(children: [
                Expanded(
                  child: TextField(
                    key: const ValueKey('gift-scheme'),
                    controller: _scheme,
                    enabled: !saving,
                    decoration:
                        const InputDecoration(labelText: 'Scheme (optional)'),
                  ),
                ),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                  child: TextField(
                    key: const ValueKey('gift-tds'),
                    controller: _tds,
                    enabled: !saving,
                    keyboardType:
                        const TextInputType.numberWithOptions(decimal: true),
                    decoration: const InputDecoration(
                        labelText: '194R TDS deducted',
                        helperText: 'Leave blank if none'),
                  ),
                ),
              ]),
              const SizedBox(height: AppSpacing.md),
              TextField(
                key: const ValueKey('gift-remarks'),
                controller: _remarks,
                enabled: !saving,
                decoration: const InputDecoration(labelText: 'Remarks'),
              ),
              if (_problem != null)
                Padding(
                  padding: const EdgeInsets.only(top: AppSpacing.sm),
                  child: Text(_problem!,
                      key: const ValueKey('gift-problem'),
                      style: TextStyle(color: theme.colorScheme.error)),
                ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: saving ? null : () => Navigator.pop(context),
          child: const Text('Cancel'),
        ),
        FilledButton(
          key: const ValueKey('gift-save'),
          onPressed: saving ? null : _save,
          child: Text(saving ? 'Saving…' : 'Record gift'),
        ),
      ],
    );
  }
}
