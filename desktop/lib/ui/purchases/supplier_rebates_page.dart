// Supplier volume rebates (BUY-13): the agreements with suppliers that give a
// share of a period's purchases back, how far each has got up its ladder, and
// the three steps that follow -- accrue what was earned, settle it against the
// supplier's open bills (a party adjustment draft, approved in Party
// Adjustments), or reverse the accrual. Phase 2 only.

import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/preferences/desktop_preferences_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/party_adjustment.dart';
import '../../models/settlement.dart';
import '../../models/supplier_rebate.dart';
import '../../models/vendor.dart';
import '../workspace/desktop_framework.dart';

String _iso(DateTime date) => date.toIso8601String().substring(0, 10);

String _money(String value) {
  final double? parsed = double.tryParse(value);
  return parsed == null ? value : parsed.toStringAsFixed(2);
}

String _words(String status) =>
    status.isEmpty ? status : status[0] + status.substring(1).toLowerCase();

String _vendorLabel(Vendor vendor) =>
    vendor.displayName.isNotEmpty ? vendor.displayName : vendor.name;

/// List the agreements and move each one along.
class SupplierRebatesPage extends StatefulWidget {
  const SupplierRebatesPage({
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
  State<SupplierRebatesPage> createState() => _SupplierRebatesPageState();
}

class _SupplierRebatesPageState extends State<SupplierRebatesPage> {
  List<SupplierRebate> _rows = const [];
  String? _error;
  String? _selectedId;
  bool _loading = true;
  final TextEditingController _search = TextEditingController();

  bool get _mayView => widget.permissions.hasPermission('PURCHASE_VIEW');
  bool get _mayManage => widget.permissions.hasPermission('PURCHASE_APPROVE');
  bool get _maySettle =>
      widget.permissions.hasPermission('PARTY_ADJUSTMENT_MANAGE');

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
      final List<SupplierRebate> rows = await widget.api.supplierRebates();
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

  List<SupplierRebate> get _shown {
    final String q = _search.text.trim().toLowerCase();
    if (q.isEmpty) return _rows;
    return _rows
        .where((row) =>
            row.code.toLowerCase().contains(q) ||
            row.name.toLowerCase().contains(q) ||
            row.vendorName.toLowerCase().contains(q))
        .toList();
  }

  SupplierRebate? get _selected =>
      _rows.where((row) => row.id == _selectedId).firstOrNull;

  void _tell(String message, AppNotificationKind kind) =>
      NotificationService.show(context, message, kind: kind);

  Future<void> _edit({SupplierRebate? existing}) async {
    final SupplierRebate? saved = await showDialog<SupplierRebate>(
      context: context,
      barrierDismissible: false,
      builder: (_) => SupplierRebateDialog(api: widget.api, existing: existing),
    );
    if (saved == null || !mounted) return;
    setState(() => _selectedId = saved.id);
    _tell('Rebate ${saved.code} saved.', AppNotificationKind.success);
    await _load();
  }

  /// Ask first, run the call inside the dialog, and tell the user after.
  Future<void> _act(
    SupplierRebate rebate, {
    required String title,
    required String message,
    required String confirmLabel,
    required String done,
    required Future<SupplierRebate> Function(String? date) call,
    bool askDate = false,
  }) async {
    final SupplierRebate? saved = await showDialog<SupplierRebate>(
      context: context,
      barrierDismissible: false,
      builder: (_) => RebateActionDialog(
        title: title,
        message: message,
        confirmLabel: confirmLabel,
        askDate: askDate,
        call: call,
      ),
    );
    if (saved == null || !mounted) return;
    _tell(done, AppNotificationKind.success);
    await _load();
  }

  Future<void> _settle(SupplierRebate rebate) async {
    final PartyAdjustment? draft = await showDialog<PartyAdjustment>(
      context: context,
      barrierDismissible: false,
      builder: (_) => SettleRebateDialog(api: widget.api, rebate: rebate),
    );
    if (draft == null || !mounted) return;
    _tell(
      'Settlement ${draft.adjustmentNumber} drafted. It now awaits approval '
      'in Party Adjustments.',
      AppNotificationKind.success,
    );
    await _load();
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.hasActiveFirm) {
      return const WorkspaceEmptyState(
        title: 'Choose a firm',
        message: 'Supplier rebates belong to one firm’s books.',
      );
    }
    if (!_mayView) {
      return const WorkspaceEmptyState(
        icon: Icons.lock_outline,
        title: 'You cannot see supplier rebates',
        message: 'Reading them needs the view purchases permission.',
      );
    }
    final SupplierRebate? picked = _selected;
    return ManagementWorkspaceLayout(
      notice: 'Agreements where a supplier gives back a share of what the '
          'firm bought in a period, by a ladder of volume steps. Accrue what '
          'is earned once the period ends, then settle it against the '
          'supplier’s open bills.',
      toolbar: _toolbar(picked),
      searchPanel: SearchFilterPanel(
        controller: _search,
        hintText: 'Search code, name or supplier',
        onSearch: (_) => setState(() {}),
      ),
      selectionBar: true,
      selection: picked == null
          ? null
          : SelectionSummary.document(
              number: picked.code,
              party: picked.vendorName,
              status: picked.status,
              total: picked.earned,
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
                const SizedBox(height: AppSpacing.md),
                Expanded(child: _grid()),
              ],
            ),
      statusBar: WorkspaceStatusBar(
        total: _rows.length,
        selected: _selectedId != null,
        message: 'Supplier rebates',
      ),
    );
  }

  WorkspaceToolbar _toolbar(SupplierRebate? selected) {
    final SupplierRebate? r = selected;
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
            unawaited(_edit());
          default:
            unawaited(_load());
        }
      },
      commands: [
        // Settling drafts a party adjustment, so it follows that permission
        // and not the one that agrees the rebate (D-SELL-52): whoever states
        // the debt need not be the one who clears it.
        if (_maySettle)
          ToolbarCommand(
            id: 'settle-rebate',
            label: 'Settle against bills',
            icon: Icons.price_check_outlined,
            onPressed: r != null && r.isAccrued && r.toSettleAmount > 0
                ? () => unawaited(_settle(r))
                : null,
          ),
        if (_mayManage) ...[
          ToolbarCommand(
            id: 'edit-rebate',
            label: 'Edit',
            icon: Icons.edit_outlined,
            onPressed: r != null && r.isActive
                ? () => unawaited(_edit(existing: r))
                : null,
          ),
          ToolbarCommand(
            id: 'accrue',
            label: 'Accrue',
            icon: Icons.calculate_outlined,
            onPressed: r != null && r.isActive
                ? () => unawaited(_act(
                      r,
                      title: 'Accrue rebate ${r.code}',
                      message: 'Books the ${_money(r.earned)} earned so far as '
                          'owed by ${r.vendorName}. The period must have '
                          'ended. Leave the date to use today.',
                      confirmLabel: 'Accrue',
                      done: 'Rebate ${r.code} accrued.',
                      askDate: true,
                      call: (date) => widget.api.accrueSupplierRebate(
                        r.id,
                        accrualDate: date,
                        expectedVersion: r.version,
                      ),
                    ))
                : null,
          ),
          ToolbarCommand(
            id: 'reverse',
            label: 'Reverse accrual',
            icon: Icons.undo_outlined,
            onPressed: r != null && r.isAccrued
                ? () => unawaited(_act(
                      r,
                      title: 'Reverse accrual of ${r.code}',
                      message: 'Takes the accrual off the books. It is '
                          'refused once any of it has been settled.',
                      confirmLabel: 'Reverse accrual',
                      done: 'Accrual of ${r.code} reversed.',
                      call: (_) => widget.api.reverseSupplierRebateAccrual(
                        r.id,
                        expectedVersion: r.version,
                      ),
                    ))
                : null,
          ),
          ToolbarCommand(
            id: 'cancel',
            label: 'Cancel',
            icon: Icons.cancel_outlined,
            onPressed: r != null && r.isActive
                ? () => unawaited(_act(
                      r,
                      title: 'Cancel rebate ${r.code}',
                      message: 'The agreement is withdrawn and earns nothing '
                          'more.',
                      confirmLabel: 'Cancel rebate',
                      done: 'Rebate ${r.code} cancelled.',
                      call: (_) => widget.api.cancelSupplierRebate(
                        r.id,
                        expectedVersion: r.version,
                      ),
                    ))
                : null,
          ),
        ],
      ],
    );
  }

  String _nextSlab(SupplierRebate row) {
    if (row.nextThreshold.isEmpty) return 'Top step reached';
    final String rate =
        row.nextRatePercent.isEmpty ? '' : ' at ${row.nextRatePercent}%';
    final String togo =
        row.toNext.isEmpty ? '' : ' (${_money(row.toNext)} to go)';
    return '${_money(row.nextThreshold)}$rate$togo';
  }

  late final ColumnChoice<SupplierRebate> _columns = ColumnChoice(
    preferences: widget.preferences,
    stateKey: 'supplier-rebates.grid',
    columns: [
      ChoosableColumn(
        column: const GridColumn(key: 'code', label: 'Code'),
        cell: (item) => item.code,
        required: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'supplier', label: 'Supplier'),
        cell: (item) => item.vendorName,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'period', label: 'Period', priority: 2),
        cell: (item) => '${item.periodFrom} to ${item.periodTo}',
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'status', label: 'Status'),
        cell: (item) => _words(item.status),
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'volume', label: 'Volume', numeric: true),
        cell: (item) => _money(item.volume),
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'rate', label: 'Rate %', numeric: true),
        cell: (item) => item.ratePercent,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'earned', label: 'Earned', numeric: true),
        cell: (item) => _money(item.earned),
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(
            key: 'next', label: 'Next slab / To next', priority: 1),
        cell: _nextSlab,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(
            key: 'accrued', label: 'Accrued', numeric: true, priority: 2),
        cell: (item) =>
            item.accruedAmount.isEmpty ? '' : _money(item.accruedAmount),
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(
            key: 'settled', label: 'Settled', numeric: true, priority: 2),
        cell: (item) => _money(item.settled),
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(
            key: 'to-settle', label: 'To settle', numeric: true, priority: 1),
        cell: (item) => _money(item.toSettle),
        shownByDefault: true,
      ),
    ],
  );

  Widget _grid() {
    final List<SupplierRebate> rows = _shown;
    if (rows.isEmpty) {
      return WorkspaceEmptyState(
        title: 'No rebates yet',
        message: _mayManage
            ? 'Record a volume rebate a supplier has agreed.'
            : 'Recording one needs the approve purchases permission.',
      );
    }
    return EnterpriseDataGrid<SupplierRebate>(
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
}

/// A confirmation that runs its call inside itself: pops the returned
/// [SupplierRebate], or stays open showing the server's message. With
/// [askDate] it offers an optional date, passed to [call] as `YYYY-MM-DD`.
class RebateActionDialog extends StatefulWidget {
  const RebateActionDialog({
    super.key,
    required this.title,
    required this.message,
    required this.confirmLabel,
    required this.call,
    this.askDate = false,
  });

  final String title;
  final String message;
  final String confirmLabel;
  final bool askDate;
  final Future<SupplierRebate> Function(String? date) call;

  @override
  State<RebateActionDialog> createState() => _RebateActionDialogState();
}

class _RebateActionDialogState extends State<RebateActionDialog>
    with SaveInDialog {
  DateTime? _date;

  Future<void> _pickDate() async {
    final DateTime? picked = await showDatePicker(
      context: context,
      initialDate: _date ?? DateTime.now(),
      firstDate: DateTime(2000),
      lastDate: DateTime(2100),
    );
    if (picked != null) setState(() => _date = picked);
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text(widget.title),
      content: SizedBox(
        width: 460,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            saveErrorBanner(),
            Text(widget.message),
            if (widget.askDate) ...[
              const SizedBox(height: AppSpacing.md),
              InkWell(
                key: const ValueKey('rebate-action-date'),
                onTap: saving ? null : () => unawaited(_pickDate()),
                child: InputDecorator(
                  decoration:
                      const InputDecoration(labelText: 'Accrual date (optional)'),
                  child: Text(_date == null ? 'Today' : _iso(_date!)),
                ),
              ),
            ],
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: cancelHandler,
          child: const Text('Back'),
        ),
        FilledButton(
          key: const ValueKey('rebate-action-confirm'),
          onPressed: saving
              ? null
              : () => unawaited(saveAndClose<SupplierRebate>(
                    () => widget.call(_date == null ? null : _iso(_date!)),
                  )),
          child: Text(saving ? 'Working…' : widget.confirmLabel),
        ),
      ],
    );
  }
}

class _SlabRow {
  _SlabRow({String threshold = '', String rate = ''})
      : threshold = TextEditingController(text: threshold),
        rate = TextEditingController(text: rate);

  final TextEditingController threshold;
  final TextEditingController rate;

  void dispose() {
    threshold.dispose();
    rate.dispose();
  }
}

/// Record a rebate, or change one that is still ACTIVE: pops the saved
/// [SupplierRebate]; stays open with the server's message on a refusal.
class SupplierRebateDialog extends StatefulWidget {
  const SupplierRebateDialog({super.key, required this.api, this.existing});

  final ApiClient api;

  /// The ACTIVE rebate being changed; its supplier and code are fixed.
  final SupplierRebate? existing;

  @override
  State<SupplierRebateDialog> createState() => _SupplierRebateDialogState();
}

class _SupplierRebateDialogState extends State<SupplierRebateDialog>
    with SaveInDialog {
  final TextEditingController _code = TextEditingController();
  final TextEditingController _name = TextEditingController();
  final TextEditingController _notes = TextEditingController();
  final List<_SlabRow> _slabs = <_SlabRow>[];
  DateTime? _from;
  DateTime? _to;
  List<Vendor> _vendors = const [];
  String? _vendorId;
  String? _problem;
  String? _loadNote;

  bool get _editing => widget.existing != null;

  @override
  void initState() {
    super.initState();
    final SupplierRebate? row = widget.existing;
    if (row != null) {
      _vendorId = row.vendorId;
      _code.text = row.code;
      _name.text = row.name;
      _notes.text = row.notes;
      _from = DateTime.tryParse(row.periodFrom);
      _to = DateTime.tryParse(row.periodTo);
      for (final SupplierRebateSlab slab in row.slabs) {
        _slabs.add(_SlabRow(threshold: slab.threshold, rate: slab.ratePercent));
      }
    }
    if (_slabs.isEmpty) _slabs.add(_SlabRow());
    if (!_editing) unawaited(_readVendors());
  }

  @override
  void dispose() {
    _code.dispose();
    _name.dispose();
    _notes.dispose();
    for (final _SlabRow slab in _slabs) {
      slab.dispose();
    }
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

  Future<void> _pick({required bool from}) async {
    final DateTime? current = from ? _from : _to;
    final DateTime? picked = await showDatePicker(
      context: context,
      initialDate: current ?? DateTime.now(),
      firstDate: DateTime(2000),
      lastDate: DateTime(2100),
    );
    if (picked == null) return;
    setState(() => from ? _from = picked : _to = picked);
  }

  void _save() {
    String? problem;
    String? slabProblem;
    final List<Map<String, dynamic>> slabs = [];
    for (final _SlabRow row in _slabs) {
      final double? threshold = double.tryParse(row.threshold.text.trim());
      final double? rate = double.tryParse(row.rate.text.trim());
      if (threshold == null || threshold <= 0) {
        slabProblem ??= 'Every slab needs a threshold above zero.';
      } else if (rate == null || rate <= 0 || rate > 100) {
        slabProblem ??= 'Every slab needs a rate above 0 and up to 100 percent.';
      } else {
        slabs.add(<String, dynamic>{
          'threshold': row.threshold.text.trim(),
          'rate_percent': row.rate.text.trim(),
        });
      }
    }
    if (_vendorId == null) {
      problem = 'Choose the supplier.';
    } else if (_code.text.trim().isEmpty) {
      problem = 'Give the rebate a code.';
    } else if (_name.text.trim().isEmpty) {
      problem = 'Give the rebate a name.';
    } else if (_from == null || _to == null) {
      problem = 'Choose the period the rebate covers.';
    } else if (_to!.isBefore(_from!)) {
      problem = 'The period cannot end before it starts.';
    } else if (_slabs.isEmpty) {
      problem = 'Add at least one slab.';
    }
    problem ??= slabProblem;
    setState(() => _problem = problem);
    if (problem != null) return;
    final String notes = _notes.text.trim();
    final SupplierRebate? row = widget.existing;
    if (row == null) {
      unawaited(saveAndClose<SupplierRebate>(
        () => widget.api.createSupplierRebate(<String, dynamic>{
          'vendor_id': _vendorId,
          'code': _code.text.trim(),
          'name': _name.text.trim(),
          'period_from': _iso(_from!),
          'period_to': _iso(_to!),
          if (notes.isNotEmpty) 'notes': notes,
          'slabs': slabs,
        }),
      ));
    } else {
      unawaited(saveAndClose<SupplierRebate>(
        () => widget.api.updateSupplierRebate(
          row.id,
          <String, dynamic>{
            'name': _name.text.trim(),
            'period_from': _iso(_from!),
            'period_to': _iso(_to!),
            'notes': notes,
            'slabs': slabs,
          },
          expectedVersion: row.version,
        ),
      ));
    }
  }

  Widget _dateField(String label, DateTime? value, bool from) => InkWell(
        key: ValueKey(from ? 'rebate-from' : 'rebate-to'),
        onTap: saving ? null : () => unawaited(_pick(from: from)),
        child: InputDecorator(
          decoration: InputDecoration(labelText: label),
          child: Text(value == null ? 'Choose' : _iso(value)),
        ),
      );

  Widget _slabRow(int index) {
    final _SlabRow row = _slabs[index];
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: Row(children: [
        Expanded(
          child: TextField(
            key: ValueKey('rebate-slab-threshold-$index'),
            controller: row.threshold,
            enabled: !saving,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            decoration: const InputDecoration(
                labelText: 'From purchases of', isDense: true),
          ),
        ),
        const SizedBox(width: AppSpacing.md),
        Expanded(
          child: TextField(
            key: ValueKey('rebate-slab-rate-$index'),
            controller: row.rate,
            enabled: !saving,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            decoration:
                const InputDecoration(labelText: 'Rebate %', isDense: true),
          ),
        ),
        IconButton(
          key: ValueKey('rebate-slab-remove-$index'),
          tooltip: 'Remove slab',
          icon: const Icon(Icons.delete_outline),
          onPressed: saving || _slabs.length == 1
              ? null
              : () => setState(() => _slabs.removeAt(index).dispose()),
        ),
      ]),
    );
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final SupplierRebate? row = widget.existing;
    return AlertDialog(
      title: Text(_editing ? 'Edit rebate ${row!.code}' : 'New supplier rebate'),
      content: SizedBox(
        width: 580,
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
              if (_editing)
                InputDecorator(
                  key: const ValueKey('rebate-vendor-fixed'),
                  decoration: const InputDecoration(labelText: 'Supplier'),
                  child: Text(row!.vendorName, overflow: TextOverflow.ellipsis),
                )
              else
                DropdownButtonFormField<String>(
                  key: const ValueKey('rebate-vendor'),
                  isExpanded: true,
                  initialValue: _vendorId,
                  decoration: const InputDecoration(labelText: 'Supplier'),
                  items: [
                    for (final Vendor v in _vendors)
                      DropdownMenuItem<String>(
                        value: v.id,
                        child: Text(_vendorLabel(v),
                            overflow: TextOverflow.ellipsis),
                      ),
                  ],
                  onChanged:
                      saving ? null : (id) => setState(() => _vendorId = id),
                ),
              const SizedBox(height: AppSpacing.md),
              Row(children: [
                Expanded(
                  child: TextField(
                    key: const ValueKey('rebate-code'),
                    controller: _code,
                    enabled: !saving && !_editing,
                    decoration: const InputDecoration(labelText: 'Code'),
                  ),
                ),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                  flex: 2,
                  child: TextField(
                    key: const ValueKey('rebate-name'),
                    controller: _name,
                    enabled: !saving,
                    decoration: const InputDecoration(labelText: 'Name'),
                  ),
                ),
              ]),
              const SizedBox(height: AppSpacing.md),
              Row(children: [
                Expanded(child: _dateField('Period from', _from, true)),
                const SizedBox(width: AppSpacing.md),
                Expanded(child: _dateField('Period to', _to, false)),
              ]),
              const SizedBox(height: AppSpacing.md),
              TextField(
                key: const ValueKey('rebate-notes'),
                controller: _notes,
                enabled: !saving,
                decoration: const InputDecoration(labelText: 'Notes'),
              ),
              const SizedBox(height: AppSpacing.md),
              Text('Slabs', style: theme.textTheme.titleSmall),
              Text(
                'The rate of the highest step the period’s purchases reach '
                'applies to all of them.',
                style: theme.textTheme.bodySmall,
              ),
              const SizedBox(height: AppSpacing.sm),
              for (int i = 0; i < _slabs.length; i++) _slabRow(i),
              Align(
                alignment: Alignment.centerLeft,
                child: TextButton.icon(
                  key: const ValueKey('rebate-add-slab'),
                  onPressed:
                      saving ? null : () => setState(() => _slabs.add(_SlabRow())),
                  icon: const Icon(Icons.add),
                  label: const Text('Add slab'),
                ),
              ),
              if (_problem != null)
                Padding(
                  padding: const EdgeInsets.only(top: AppSpacing.sm),
                  child: Text(_problem!,
                      key: const ValueKey('rebate-problem'),
                      style: TextStyle(color: theme.colorScheme.error)),
                ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(onPressed: cancelHandler, child: const Text('Cancel')),
        FilledButton(
          key: const ValueKey('rebate-save'),
          onPressed: saving ? null : _save,
          child: Text(saving ? 'Saving…' : 'Save'),
        ),
      ],
    );
  }
}

/// Draft the party adjustment that takes an accrued rebate off the supplier's
/// open bills: pops the drafted [PartyAdjustment]; stays open with the
/// server's message on a refusal. Approval happens in Party Adjustments.
class SettleRebateDialog extends StatefulWidget {
  const SettleRebateDialog({super.key, required this.api, required this.rebate});

  final ApiClient api;
  final SupplierRebate rebate;

  @override
  State<SettleRebateDialog> createState() => _SettleRebateDialogState();
}

class _SettleRebateDialogState extends State<SettleRebateDialog>
    with SaveInDialog {
  late final TextEditingController _reason = TextEditingController(
      text: 'Supplier credit note for ${widget.rebate.code}');
  final Map<String, TextEditingController> _boxes =
      <String, TextEditingController>{};
  List<OutstandingInvoice> _bills = const [];
  DateTime _date = DateTime.now();
  bool _loading = true;
  String? _problem;
  String? _loadNote;

  double get _cap => widget.rebate.toSettleAmount;

  @override
  void initState() {
    super.initState();
    unawaited(_readBills());
  }

  @override
  void dispose() {
    _reason.dispose();
    for (final TextEditingController box in _boxes.values) {
      box.dispose();
    }
    super.dispose();
  }

  Future<void> _readBills() async {
    try {
      final PartyAdjustmentOpenBills found = await widget.api
          .partyAdjustmentOpenBills(vendorId: widget.rebate.vendorId);
      if (!mounted) return;
      setState(() {
        _bills = found.supplierBills;
        for (final OutstandingInvoice bill in _bills) {
          _boxes[bill.invoiceId] = TextEditingController();
        }
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

  double _number(String text) => double.tryParse(text.trim()) ?? 0;

  double get _total {
    double sum = 0;
    for (final TextEditingController box in _boxes.values) {
      sum += _number(box.text);
    }
    return sum;
  }

  void _save() {
    String? problem;
    for (final OutstandingInvoice bill in _bills) {
      final double value = _number(_boxes[bill.invoiceId]!.text);
      if (value - bill.outstanding > 0.005) {
        problem = 'Bill ${bill.invoiceNumber} owes '
            '${bill.outstanding.toStringAsFixed(2)}, so ${value.toStringAsFixed(2)} '
            'cannot be taken off it.';
        break;
      }
    }
    if (problem == null) {
      if (_total <= 0) {
        problem = 'Enter an amount against at least one bill.';
      } else if (_total - _cap > 0.005) {
        problem = 'No more than ${_cap.toStringAsFixed(2)} is left to settle.';
      } else if (_reason.text.trim().isEmpty) {
        problem = 'Say why the balance is being adjusted.';
      }
    }
    setState(() => _problem = problem);
    if (problem != null) return;
    final String amount = _total.toStringAsFixed(2);
    unawaited(saveAndClose<PartyAdjustment>(
      () => widget.api.createPartyAdjustment(<String, dynamic>{
        'kind': 'SUPPLIER_REBATE',
        'vendor_id': widget.rebate.vendorId,
        'amount': amount,
        'reason': _reason.text.trim(),
        'adjustment_date': _iso(_date),
        'rebate_agreement_id': widget.rebate.id,
        'allocations': [
          for (final OutstandingInvoice bill in _bills)
            if (_number(_boxes[bill.invoiceId]!.text) > 0)
              <String, dynamic>{
                'side': 'SUPPLIER',
                'bill_id': bill.invoiceId,
                'amount': _boxes[bill.invoiceId]!.text.trim(),
              },
        ],
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

  Widget _billRow(OutstandingInvoice bill) => Padding(
        padding: const EdgeInsets.only(bottom: AppSpacing.sm),
        child: Row(children: [
          Expanded(
            flex: 3,
            child: Text(
              '${bill.invoiceNumber} · ${bill.invoiceDate}',
              overflow: TextOverflow.ellipsis,
            ),
          ),
          Expanded(
            flex: 2,
            child: Text('Owes ${_money(bill.outstandingAmount)}',
                textAlign: TextAlign.end),
          ),
          const SizedBox(width: AppSpacing.md),
          SizedBox(
            width: 130,
            child: TextField(
              key: ValueKey('settle-bill-${bill.invoiceId}'),
              controller: _boxes[bill.invoiceId],
              enabled: !saving,
              onChanged: (_) => setState(() {}),
              keyboardType:
                  const TextInputType.numberWithOptions(decimal: true),
              decoration:
                  const InputDecoration(labelText: 'Amount', isDense: true),
            ),
          ),
        ]),
      );

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return AlertDialog(
      title: Text('Settle rebate ${widget.rebate.code}'),
      content: SizedBox(
        width: 620,
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
                '${widget.rebate.vendorName}: ${_cap.toStringAsFixed(2)} left '
                'to settle. Choose how much comes off each open bill; this '
                'drafts a party adjustment that is approved in Party '
                'Adjustments.',
                style: theme.textTheme.bodySmall,
              ),
              const SizedBox(height: AppSpacing.md),
              if (_loading)
                const Center(child: CircularProgressIndicator())
              else if (_bills.isEmpty)
                const Text('This supplier has no open bills.')
              else
                for (final OutstandingInvoice bill in _bills) _billRow(bill),
              const SizedBox(height: AppSpacing.sm),
              Text('Total ${_total.toStringAsFixed(2)} of '
                  '${_cap.toStringAsFixed(2)}',
                  key: const ValueKey('settle-total'),
                  style: theme.textTheme.titleSmall),
              const SizedBox(height: AppSpacing.md),
              Row(children: [
                Expanded(
                  flex: 3,
                  child: TextField(
                    key: const ValueKey('settle-reason'),
                    controller: _reason,
                    enabled: !saving,
                    decoration: const InputDecoration(labelText: 'Reason'),
                  ),
                ),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                  flex: 2,
                  child: InkWell(
                    key: const ValueKey('settle-date'),
                    onTap: saving ? null : () => unawaited(_pickDate()),
                    child: InputDecorator(
                      decoration: const InputDecoration(labelText: 'Date'),
                      child: Text(_iso(_date)),
                    ),
                  ),
                ),
              ]),
              if (_problem != null)
                Padding(
                  padding: const EdgeInsets.only(top: AppSpacing.sm),
                  child: Text(_problem!,
                      key: const ValueKey('settle-problem'),
                      style: TextStyle(color: theme.colorScheme.error)),
                ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(onPressed: cancelHandler, child: const Text('Cancel')),
        FilledButton(
          key: const ValueKey('settle-save'),
          onPressed: saving || _loading ? null : _save,
          child: Text(saving ? 'Saving…' : 'Draft settlement'),
        ),
      ],
    );
  }
}
