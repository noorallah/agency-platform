// Customer turnover rebates (SG-9): the agreements that give a customer, or a
// group of customers, back a share of what they bought in a period, how far
// each has got up its ladder, and the steps that follow -- accrue what was
// earned once the period ends, settle it against the customer's open bills (a
// party adjustment draft, approved in Party Adjustments), or reverse the
// accrual. The mirror of the supplier rebate screen. Phase 2 only.

import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/preferences/desktop_preferences_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/customer.dart';
import '../../models/customer_rebate.dart';
import '../../models/entities.dart';
import '../../models/party_adjustment.dart';
import '../../models/settlement.dart';
import '../workspace/desktop_framework.dart';

String _iso(DateTime date) => date.toIso8601String().substring(0, 10);

String _money(String value) {
  final double? parsed = double.tryParse(value);
  return parsed == null ? value : parsed.toStringAsFixed(2);
}

String _words(String status) =>
    status.isEmpty ? status : status[0] + status.substring(1).toLowerCase();

String _customerLabel(Customer customer) =>
    customer.displayName.isNotEmpty ? customer.displayName : customer.name;

/// List the agreements and move each one along.
class CustomerRebatesPage extends StatefulWidget {
  const CustomerRebatesPage({
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
  State<CustomerRebatesPage> createState() => _CustomerRebatesPageState();
}

class _CustomerRebatesPageState extends State<CustomerRebatesPage> {
  List<CustomerRebate> _rows = const [];
  String? _error;
  String? _selectedId;
  bool _loading = true;
  final TextEditingController _search = TextEditingController();

  bool get _mayView => widget.permissions.hasPermission('SALES_VIEW');
  bool get _mayManage => widget.permissions.hasPermission('SALES_APPROVE');

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
      final List<Json> found = await fetchAllPages<Json>(
        (page) => widget.api.customerRebates(page: page, pageSize: 100),
      );
      if (!mounted) return;
      setState(() {
        _rows = found.map(CustomerRebate.fromJson).toList();
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

  List<CustomerRebate> get _shown {
    final String q = _search.text.trim().toLowerCase();
    if (q.isEmpty) return _rows;
    return _rows
        .where((row) =>
            row.code.toLowerCase().contains(q) ||
            row.name.toLowerCase().contains(q) ||
            row.partyName.toLowerCase().contains(q))
        .toList();
  }

  CustomerRebate? get _selected =>
      _rows.where((row) => row.id == _selectedId).firstOrNull;

  void _tell(String message, AppNotificationKind kind) =>
      NotificationService.show(context, message, kind: kind);

  Future<void> _edit({CustomerRebate? existing}) async {
    final CustomerRebate? saved = await showDialog<CustomerRebate>(
      context: context,
      barrierDismissible: false,
      builder: (_) => CustomerRebateDialog(api: widget.api, existing: existing),
    );
    if (saved == null || !mounted) return;
    setState(() => _selectedId = saved.id);
    _tell('Rebate ${saved.code} saved.', AppNotificationKind.success);
    await _load();
  }

  /// Ask first, run the call inside the dialog, and tell the user after.
  Future<void> _act({
    required String title,
    required String message,
    required String confirmLabel,
    required String done,
    required Future<CustomerRebate> Function(String? date) call,
    bool askDate = false,
  }) async {
    final CustomerRebate? saved = await showDialog<CustomerRebate>(
      context: context,
      barrierDismissible: false,
      builder: (_) => CustomerRebateActionDialog(
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

  Future<void> _settle(CustomerRebate rebate) async {
    final PartyAdjustment? draft = await showDialog<PartyAdjustment>(
      context: context,
      barrierDismissible: false,
      builder: (_) => SettleCustomerRebateDialog(
        api: widget.api,
        rebate: rebate,
      ),
    );
    if (draft == null || !mounted) return;
    _tell(
      'Settlement ${draft.adjustmentNumber} drafted. It now awaits approval '
      'in Party Adjustments.',
      AppNotificationKind.success,
    );
    await _load();
  }

  Future<void> _statement(CustomerRebate rebate) => showDialog<void>(
        context: context,
        builder: (_) => CustomerRebateStatementDialog(
          api: widget.api,
          rebate: rebate,
        ),
      );

  @override
  Widget build(BuildContext context) {
    if (!widget.hasActiveFirm) {
      return const WorkspaceEmptyState(
        title: 'Choose a firm',
        message: 'Customer rebates belong to one firm’s books.',
      );
    }
    if (!_mayView) {
      return const WorkspaceEmptyState(
        icon: Icons.lock_outline,
        title: 'You cannot see customer rebates',
        message: 'Reading them needs the view sales permission.',
      );
    }
    final CustomerRebate? picked = _selected;
    return ManagementWorkspaceLayout(
      notice: 'Agreements where the firm gives a customer, or a group of '
          'customers, back a share of what they bought in a period, by a '
          'ladder of turnover steps. Accrue what is earned once the period '
          'ends, then settle it against the customer’s open bills.',
      toolbar: _toolbar(picked),
      searchPanel: SearchFilterPanel(
        controller: _search,
        hintText: 'Search code, name or customer',
        onSearch: (_) => setState(() {}),
      ),
      selectionBar: true,
      selection: picked == null
          ? null
          : SelectionSummary.document(
              number: picked.code,
              party: picked.partyName,
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
        message: 'Customer rebates',
      ),
    );
  }

  WorkspaceToolbar _toolbar(CustomerRebate? selected) {
    final CustomerRebate? r = selected;
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
        ToolbarCommand(
          id: 'rebate-statement',
          label: 'Statement',
          icon: Icons.receipt_long_outlined,
          onPressed: r != null ? () => unawaited(_statement(r)) : null,
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
            onPressed: r != null && r.isActive && r.periodEnded(_iso(DateTime.now()))
                ? () => unawaited(_act(
                      title: 'Accrue rebate ${r.code}',
                      message: 'Books the ${_money(r.earned)} earned as owed '
                          'to ${r.partyName}. The period has ended, so the '
                          'turnover is final. Leave the date to use today.',
                      confirmLabel: 'Accrue',
                      done: 'Rebate ${r.code} accrued.',
                      askDate: true,
                      call: (date) async => CustomerRebate.fromJson(
                        await widget.api.accrueCustomerRebate(
                          r.id,
                          accrualDate: date,
                          expectedVersion: r.version,
                        ),
                      ),
                    ))
                : null,
          ),
          ToolbarCommand(
            id: 'settle-rebate',
            label: 'Settle against bills',
            icon: Icons.price_check_outlined,
            onPressed: r != null && r.isAccrued && r.toSettleAmount > 0
                ? () => unawaited(_settle(r))
                : null,
          ),
          ToolbarCommand(
            id: 'reverse',
            label: 'Reverse accrual',
            icon: Icons.undo_outlined,
            onPressed: r != null && r.isAccrued
                ? () => unawaited(_act(
                      title: 'Reverse accrual of ${r.code}',
                      message: 'Takes the accrual off the books. It is '
                          'refused once any of it has been settled.',
                      confirmLabel: 'Reverse accrual',
                      done: 'Accrual of ${r.code} reversed.',
                      call: (_) async => CustomerRebate.fromJson(
                        await widget.api.reverseCustomerRebateAccrual(
                          r.id,
                          expectedVersion: r.version,
                        ),
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
                      title: 'Cancel rebate ${r.code}',
                      message: 'The agreement is withdrawn and earns nothing '
                          'more.',
                      confirmLabel: 'Cancel rebate',
                      done: 'Rebate ${r.code} cancelled.',
                      call: (_) async => CustomerRebate.fromJson(
                        await widget.api.cancelCustomerRebate(
                          r.id,
                          expectedVersion: r.version,
                        ),
                      ),
                    ))
                : null,
          ),
        ],
      ],
    );
  }

  String _nextSlab(CustomerRebate row) {
    if (row.nextThreshold.isEmpty) return 'Top step reached';
    final String rate =
        row.nextRatePercent.isEmpty ? '' : ' at ${row.nextRatePercent}%';
    final String togo =
        row.toNext.isEmpty ? '' : ' (${_money(row.toNext)} to go)';
    return '${_money(row.nextThreshold)}$rate$togo';
  }

  late final ColumnChoice<CustomerRebate> _columns = ColumnChoice(
    preferences: widget.preferences,
    stateKey: 'customer-rebates.grid',
    columns: [
      ChoosableColumn(
        column: const GridColumn(key: 'code', label: 'Code'),
        cell: (item) => item.code,
        required: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'name', label: 'Name', priority: 2),
        cell: (item) => item.name,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'customer', label: 'Customer or group'),
        cell: (item) =>
            item.isGroup ? '${item.partyName} (group)' : item.partyName,
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
        column:
            const GridColumn(key: 'turnover', label: 'Turnover', numeric: true),
        cell: (item) => _money(item.turnover),
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
    final List<CustomerRebate> rows = _shown;
    if (rows.isEmpty) {
      return WorkspaceEmptyState(
        title: 'No rebates yet',
        message: _mayManage
            ? 'Record a turnover rebate the firm has agreed with a customer.'
            : 'Recording one needs the approve sales permission.',
      );
    }
    return EnterpriseDataGrid<CustomerRebate>(
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
/// [CustomerRebate], or stays open showing the server's message. With
/// [askDate] it offers an optional date, passed to [call] as `YYYY-MM-DD`.
class CustomerRebateActionDialog extends StatefulWidget {
  const CustomerRebateActionDialog({
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
  final Future<CustomerRebate> Function(String? date) call;

  @override
  State<CustomerRebateActionDialog> createState() =>
      _CustomerRebateActionDialogState();
}

class _CustomerRebateActionDialogState extends State<CustomerRebateActionDialog>
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
                  decoration: const InputDecoration(
                      labelText: 'Accrual date (optional)'),
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
              : () => unawaited(saveAndClose<CustomerRebate>(
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
/// [CustomerRebate]; stays open with the server's message on a refusal.
class CustomerRebateDialog extends StatefulWidget {
  const CustomerRebateDialog({super.key, required this.api, this.existing});

  final ApiClient api;

  /// The ACTIVE rebate being changed; its party and code are fixed.
  final CustomerRebate? existing;

  @override
  State<CustomerRebateDialog> createState() => _CustomerRebateDialogState();
}

class _CustomerRebateDialogState extends State<CustomerRebateDialog>
    with SaveInDialog {
  final TextEditingController _code = TextEditingController();
  final TextEditingController _name = TextEditingController();
  final TextEditingController _notes = TextEditingController();
  final List<_SlabRow> _slabs = <_SlabRow>[];
  DateTime? _from;
  DateTime? _to;
  List<Customer> _customers = const [];
  List<CustomerGroup> _groups = const [];
  bool _forGroup = false;
  bool _agreedBeforeSale = false;
  String? _customerId;
  String? _groupId;
  String? _problem;
  String? _loadNote;

  bool get _editing => widget.existing != null;

  @override
  void initState() {
    super.initState();
    final CustomerRebate? row = widget.existing;
    if (row != null) {
      _forGroup = row.isGroup;
      _code.text = row.code;
      _name.text = row.name;
      _notes.text = row.notes;
      _agreedBeforeSale = row.agreedBeforeSale;
      _from = DateTime.tryParse(row.periodFrom);
      _to = DateTime.tryParse(row.periodTo);
      for (final CustomerRebateSlab slab in row.slabs) {
        _slabs.add(_SlabRow(threshold: slab.threshold, rate: slab.ratePercent));
      }
    }
    if (_slabs.isEmpty) _slabs.add(_SlabRow());
    if (!_editing) unawaited(_readParties());
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

  Future<void> _readParties() async {
    try {
      final List<Customer> customers = await fetchAllPages<Customer>(
          (page) => widget.api.customers(page: page));
      final List<CustomerGroup> groups = await fetchAllPages<CustomerGroup>(
          (page) => widget.api.customerGroups(page: page));
      if (!mounted) return;
      setState(() {
        _customers = customers;
        _groups = groups;
      });
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
    if (!_editing && !_forGroup && _customerId == null) {
      problem = 'Choose the customer.';
    } else if (!_editing && _forGroup && _groupId == null) {
      problem = 'Choose the customer group.';
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
    final CustomerRebate? row = widget.existing;
    if (row == null) {
      unawaited(saveAndClose<CustomerRebate>(
        () async => CustomerRebate.fromJson(
          await widget.api.createCustomerRebate(<String, dynamic>{
            if (_forGroup) 'customer_group_id': _groupId,
            if (!_forGroup) 'customer_id': _customerId,
            'code': _code.text.trim(),
            'name': _name.text.trim(),
            'period_from': _iso(_from!),
            'period_to': _iso(_to!),
            'agreed_before_sale': _agreedBeforeSale,
            if (notes.isNotEmpty) 'notes': notes,
            'slabs': slabs,
          }),
        ),
      ));
    } else {
      unawaited(saveAndClose<CustomerRebate>(
        () async => CustomerRebate.fromJson(
          await widget.api.updateCustomerRebate(
            row.id,
            <String, dynamic>{
              'name': _name.text.trim(),
              'period_from': _iso(_from!),
              'period_to': _iso(_to!),
              'agreed_before_sale': _agreedBeforeSale,
              'notes': notes,
              'slabs': slabs,
            },
            expectedVersion: row.version,
          ),
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
                labelText: 'From turnover of', isDense: true),
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

  Widget _partyChooser() {
    final CustomerRebate? row = widget.existing;
    if (row != null) {
      return InputDecorator(
        key: const ValueKey('rebate-party-fixed'),
        decoration: InputDecoration(
            labelText: row.isGroup ? 'Customer group' : 'Customer'),
        child: Text(row.partyName, overflow: TextOverflow.ellipsis),
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        SegmentedButton<bool>(
          key: const ValueKey('rebate-party-kind'),
          segments: const [
            ButtonSegment<bool>(value: false, label: Text('Customer')),
            ButtonSegment<bool>(value: true, label: Text('Customer group')),
          ],
          selected: {_forGroup},
          onSelectionChanged:
              saving ? null : (value) => setState(() => _forGroup = value.first),
        ),
        const SizedBox(height: AppSpacing.md),
        if (_forGroup)
          DropdownButtonFormField<String>(
            key: const ValueKey('rebate-group'),
            isExpanded: true,
            initialValue: _groupId,
            decoration: const InputDecoration(labelText: 'Customer group'),
            items: [
              for (final CustomerGroup g in _groups)
                DropdownMenuItem<String>(
                  value: g.id,
                  child: Text(g.name, overflow: TextOverflow.ellipsis),
                ),
            ],
            onChanged: saving ? null : (id) => setState(() => _groupId = id),
          )
        else
          DropdownButtonFormField<String>(
            key: const ValueKey('rebate-customer'),
            isExpanded: true,
            initialValue: _customerId,
            decoration: const InputDecoration(labelText: 'Customer'),
            items: [
              for (final Customer c in _customers)
                DropdownMenuItem<String>(
                  value: c.id,
                  child:
                      Text(_customerLabel(c), overflow: TextOverflow.ellipsis),
                ),
            ],
            onChanged: saving ? null : (id) => setState(() => _customerId = id),
          ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final CustomerRebate? row = widget.existing;
    return AlertDialog(
      title: Text(
          _editing ? 'Edit rebate ${row!.code}' : 'New customer rebate'),
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
              _partyChooser(),
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
              CheckboxListTile(
                key: const ValueKey('rebate-agreed-before-sale'),
                contentPadding: EdgeInsets.zero,
                controlAffinity: ListTileControlAffinity.leading,
                value: _agreedBeforeSale,
                onChanged: saving
                    ? null
                    : (value) =>
                        setState(() => _agreedBeforeSale = value ?? false),
                title: const Text('Agreed before the sale'),
                subtitle: const Text(
                    'Only informs your CA’s decision on a GST credit note; '
                    'no GST is worked out here.'),
              ),
              const SizedBox(height: AppSpacing.sm),
              Text('Slabs', style: theme.textTheme.titleSmall),
              Text(
                'The rate of the highest step the period’s turnover reaches '
                'applies to all of it.',
                style: theme.textTheme.bodySmall,
              ),
              const SizedBox(height: AppSpacing.sm),
              for (int i = 0; i < _slabs.length; i++) _slabRow(i),
              Align(
                alignment: Alignment.centerLeft,
                child: TextButton.icon(
                  key: const ValueKey('rebate-add-slab'),
                  onPressed: saving || _slabs.length >= 20
                      ? null
                      : () => setState(() => _slabs.add(_SlabRow())),
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

/// What an agreement's turnover is made of: by customer and kind of document,
/// the settlements so far, and the note on GST for the firm's CA.
class CustomerRebateStatementDialog extends StatefulWidget {
  const CustomerRebateStatementDialog({
    super.key,
    required this.api,
    required this.rebate,
  });

  final ApiClient api;
  final CustomerRebate rebate;

  @override
  State<CustomerRebateStatementDialog> createState() =>
      _CustomerRebateStatementDialogState();
}

class _CustomerRebateStatementDialogState
    extends State<CustomerRebateStatementDialog> {
  CustomerRebateStatement? _statement;
  String? _error;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    try {
      final Json found = await widget.api.customerRebateStatement(widget.rebate.id);
      if (!mounted) return;
      setState(() => _statement = CustomerRebateStatement.fromJson(found));
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() => _error = error.message);
    }
  }

  DataCell _cell(String value) =>
      DataCell(Align(alignment: Alignment.centerRight, child: Text(_money(value))));

  DataColumn _column(String label) =>
      DataColumn(label: Text(label), numeric: true);

  Widget _body(CustomerRebateStatement s, ThemeData theme) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          '${s.agreement.partyName} · ${s.agreement.periodFrom} to '
          '${s.agreement.periodTo} · ${_words(s.agreement.status)}',
          style: theme.textTheme.bodySmall,
        ),
        const SizedBox(height: AppSpacing.md),
        SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: DataTable(
            key: const ValueKey('statement-turnover'),
            columns: [
              const DataColumn(label: Text('Customer')),
              _column('Invoiced'),
              _column('Returned'),
              _column('Credit notes'),
              _column('Debit notes'),
              _column('Turnover'),
            ],
            rows: [
              for (final CustomerRebateTurnoverRow row in s.customers)
                DataRow(cells: [
                  DataCell(Text(row.customerName)),
                  _cell(row.invoiced),
                  _cell(row.returned),
                  _cell(row.creditNotes),
                  _cell(row.debitNotes),
                  _cell(row.turnover),
                ]),
              DataRow(cells: [
                const DataCell(Text('Total')),
                _cell(s.invoiced),
                _cell(s.returned),
                _cell(s.creditNotes),
                _cell(s.debitNotes),
                _cell(s.turnoverToday),
              ]),
            ],
          ),
        ),
        const SizedBox(height: AppSpacing.sm),
        Text('Turnover today ${_money(s.turnoverToday)} · earned '
            '${_money(s.agreement.earned)} · settled '
            '${_money(s.agreement.settled)} · to settle '
            '${_money(s.agreement.toSettle)}',
            key: const ValueKey('statement-today'),
            style: theme.textTheme.titleSmall),
        const SizedBox(height: AppSpacing.md),
        Text('Settlements', style: theme.textTheme.titleSmall),
        if (s.settlements.isEmpty)
          const Text('Nothing has been settled yet.')
        else
          for (final CustomerRebateSettlementRow row in s.settlements)
            Padding(
              padding: const EdgeInsets.only(top: AppSpacing.xs),
              child: Text('${row.adjustmentNumber} · ${row.adjustmentDate} · '
                  '${row.customerName} · ${_money(row.amount)} · '
                  '${_words(row.status)}'),
            ),
        const SizedBox(height: AppSpacing.md),
        Text(s.gstNote,
            key: const ValueKey('statement-gst-note'),
            style: theme.textTheme.bodySmall),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final CustomerRebateStatement? s = _statement;
    return AlertDialog(
      title: Text('Statement of rebate ${widget.rebate.code}'),
      content: SizedBox(
        width: 720,
        child: SingleChildScrollView(
          child: _error != null
              ? Text(_error!, style: TextStyle(color: theme.colorScheme.error))
              : s == null
                  ? const Center(child: CircularProgressIndicator())
                  : _body(s, theme),
        ),
      ),
      actions: [
        TextButton(
          key: const ValueKey('statement-close'),
          onPressed: () => Navigator.pop(context),
          child: const Text('Close'),
        ),
      ],
    );
  }
}

/// Draft the party adjustment that takes an accrued rebate off the customer's
/// account: pops the drafted [PartyAdjustment]; stays open with the server's
/// message on a refusal. Approval happens in Party Adjustments. For a group
/// agreement the customer is chosen from the members who traded.
class SettleCustomerRebateDialog extends StatefulWidget {
  const SettleCustomerRebateDialog({
    super.key,
    required this.api,
    required this.rebate,
  });

  final ApiClient api;
  final CustomerRebate rebate;

  @override
  State<SettleCustomerRebateDialog> createState() =>
      _SettleCustomerRebateDialogState();
}

class _SettleCustomerRebateDialogState
    extends State<SettleCustomerRebateDialog> with SaveInDialog {
  late final TextEditingController _reason = TextEditingController(
      text: 'Customer rebate ${widget.rebate.code}');
  late final TextEditingController _amount =
      TextEditingController(text: _money(widget.rebate.toSettle));
  final Map<String, TextEditingController> _boxes =
      <String, TextEditingController>{};
  List<CustomerRebateTurnoverRow> _members = const [];
  List<OutstandingInvoice> _bills = const [];
  String _customerId = '';
  DateTime _date = DateTime.now();
  bool _loading = true;
  String? _problem;
  String? _loadNote;

  double get _cap => widget.rebate.toSettleAmount;

  @override
  void initState() {
    super.initState();
    if (widget.rebate.isGroup) {
      unawaited(_readMembers());
    } else {
      _customerId = widget.rebate.customerId;
      unawaited(_readBills());
    }
  }

  @override
  void dispose() {
    _reason.dispose();
    _amount.dispose();
    for (final TextEditingController box in _boxes.values) {
      box.dispose();
    }
    super.dispose();
  }

  Future<void> _readMembers() async {
    try {
      final CustomerRebateStatement found = CustomerRebateStatement.fromJson(
          await widget.api.customerRebateStatement(widget.rebate.id));
      if (!mounted) return;
      setState(() {
        _members = found.customers;
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

  Future<void> _readBills() async {
    setState(() {
      _loading = true;
      _loadNote = null;
    });
    try {
      final PartyAdjustmentOpenBills found = await widget.api
          .partyAdjustmentOpenBills(customerId: _customerId);
      if (!mounted) return;
      setState(() {
        for (final TextEditingController box in _boxes.values) {
          box.dispose();
        }
        _boxes.clear();
        _bills = found.customerBills;
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

  double get _allocated {
    double sum = 0;
    for (final TextEditingController box in _boxes.values) {
      sum += _number(box.text);
    }
    return sum;
  }

  void _save() {
    String? problem;
    final double amount = _number(_amount.text);
    if (_customerId.isEmpty) {
      problem = 'Choose the customer.';
    }
    if (problem == null) {
      for (final OutstandingInvoice bill in _bills) {
        final double value = _number(_boxes[bill.invoiceId]!.text);
        if (value - bill.outstanding > 0.005) {
          problem = 'Bill ${bill.invoiceNumber} is owed '
              '${bill.outstanding.toStringAsFixed(2)}, so '
              '${value.toStringAsFixed(2)} cannot be taken off it.';
          break;
        }
      }
    }
    if (problem == null) {
      if (amount <= 0) {
        problem = 'Enter the amount to settle.';
      } else if (amount - _cap > 0.005) {
        problem = 'No more than ${_cap.toStringAsFixed(2)} is left to settle.';
      } else if (_allocated - amount > 0.005) {
        problem = 'The bills add up to ${_allocated.toStringAsFixed(2)}, more '
            'than the ${amount.toStringAsFixed(2)} being settled.';
      } else if (_reason.text.trim().isEmpty) {
        problem = 'Say why the balance is being adjusted.';
      }
    }
    setState(() => _problem = problem);
    if (problem != null) return;
    unawaited(saveAndClose<PartyAdjustment>(
      () => widget.api.createPartyAdjustment(<String, dynamic>{
        'kind': 'CUSTOMER_REBATE',
        'customer_id': _customerId,
        'amount': amount.toStringAsFixed(2),
        'reason': _reason.text.trim(),
        'adjustment_date': _iso(_date),
        'customer_rebate_agreement_id': widget.rebate.id,
        'allocations': [
          for (final OutstandingInvoice bill in _bills)
            if (_number(_boxes[bill.invoiceId]!.text) > 0)
              <String, dynamic>{
                'side': 'CUSTOMER',
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
            child: Text('Owed ${_money(bill.outstandingAmount)}',
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

  Widget _memberChooser() => DropdownButtonFormField<String>(
        key: const ValueKey('settle-customer'),
        isExpanded: true,
        initialValue: _customerId.isEmpty ? null : _customerId,
        decoration: const InputDecoration(labelText: 'Customer in the group'),
        items: [
          for (final CustomerRebateTurnoverRow m in _members)
            DropdownMenuItem<String>(
              value: m.customerId,
              child: Text(m.customerName, overflow: TextOverflow.ellipsis),
            ),
        ],
        onChanged: saving
            ? null
            : (id) {
                if (id == null) return;
                setState(() => _customerId = id);
                unawaited(_readBills());
              },
      );

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final bool group = widget.rebate.isGroup;
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
                '${widget.rebate.partyName}: ${_cap.toStringAsFixed(2)} left '
                'to settle. This drafts a party adjustment that credits the '
                'customer’s account; it is approved in Party Adjustments. '
                'Optionally choose how much comes off each open bill.',
                style: theme.textTheme.bodySmall,
              ),
              const SizedBox(height: AppSpacing.md),
              if (group) ...[
                _memberChooser(),
                const SizedBox(height: AppSpacing.md),
              ],
              if (_loading)
                const Center(child: CircularProgressIndicator())
              else if (_customerId.isNotEmpty && _bills.isEmpty)
                const Text('This customer has no open bills.')
              else
                for (final OutstandingInvoice bill in _bills) _billRow(bill),
              const SizedBox(height: AppSpacing.sm),
              Row(children: [
                Expanded(
                  child: TextField(
                    key: const ValueKey('settle-amount'),
                    controller: _amount,
                    enabled: !saving,
                    keyboardType:
                        const TextInputType.numberWithOptions(decimal: true),
                    decoration:
                        const InputDecoration(labelText: 'Amount to settle'),
                  ),
                ),
                const SizedBox(width: AppSpacing.md),
                Expanded(
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
              const SizedBox(height: AppSpacing.md),
              TextField(
                key: const ValueKey('settle-reason'),
                controller: _reason,
                enabled: !saving,
                decoration: const InputDecoration(labelText: 'Reason'),
              ),
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
