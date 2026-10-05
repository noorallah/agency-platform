// Party adjustments: clearing a balance with no money moving.
//
// A customer's bad debt written off, a supplier's balance written back, or a
// customer's balance set against the same business's supplier balance. Each is
// drafted first, posts nothing until approved, and is withdrawn by a cancel
// that keeps its reason. Phase 2 only.

import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/preferences/desktop_preferences_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/customer.dart';
import '../../models/entities.dart';
import '../../models/party_adjustment.dart';
import '../../models/settlement.dart';
import '../../models/vendor.dart';
import '../../phase2/document_page.dart';
import '../../phase2/indian_format.dart';
import '../workspace/desktop_framework.dart';
import '../workspace/reason_prompt.dart';

/// The words on the screen's notice, behind the page line's (i).
const String _notice =
    'Use these to clear a balance when no money moves: a customer who will '
    'never pay (write-off), a supplier who has forgiven part of what the firm '
    'owes (written back), or what a customer owes set against what the firm '
    'owes the same business as a supplier (set-off). Nothing is posted until '
    'an adjustment is approved; a cancel puts it back.';

const String _secondApproverHint =
    'Above the firm’s limit: needs a second person with approval rights';

/// List the firm's party adjustments, draft one, approve it or withdraw it.
class PartyAdjustmentPage extends StatefulWidget {
  const PartyAdjustmentPage({
    super.key,
    required this.api,
    required this.preferences,
    required this.permissions,
    required this.hasActiveFirm,
  });

  final ApiClient api;

  /// Where the grid's chosen columns are remembered.
  final DesktopPreferencesService preferences;
  final PermissionService permissions;
  final bool hasActiveFirm;

  @override
  State<PartyAdjustmentPage> createState() => _PartyAdjustmentPageState();
}

class _PartyAdjustmentPageState extends State<PartyAdjustmentPage> {
  List<PartyAdjustment> _rows = const [];
  String? _error;
  String? _selectedId;
  bool _loading = true;

  final TextEditingController _search = TextEditingController();
  DatePeriod _period = const DatePeriod.all();

  String? get _from =>
      _period.from == null ? null : DatePeriod.iso(_period.from!);
  String? get _to => _period.to == null ? null : DatePeriod.iso(_period.to!);

  bool get _mayView =>
      widget.permissions.hasPermission('PARTY_ADJUSTMENT_VIEW');
  bool get _mayManage =>
      widget.permissions.hasPermission('PARTY_ADJUSTMENT_MANAGE');

  /// Approving moves what a party owes, so it is its own permission.
  bool get _mayApprove =>
      widget.permissions.hasPermission('PARTY_ADJUSTMENT_APPROVE');

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
      final List<PartyAdjustment> rows =
          await fetchAllPages<PartyAdjustment>(
        (page) => widget.api.partyAdjustments(
          page: page,
          search: _search.text.trim(),
          dateFrom: _from,
          dateTo: _to,
        ),
      );
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

  PartyAdjustment? get _selected =>
      _rows.where((row) => row.id == _selectedId).firstOrNull;

  Future<void> _draft({String kind = 'CUSTOMER_WRITE_OFF'}) async {
    final bool? saved = await showDocument<bool>(
      context,
      title: kind == 'SET_OFF' ? 'New set-off' : 'New party adjustment',
      builder: (_) => PartyAdjustmentDialog(api: widget.api, initialKind: kind),
    );
    if (saved == true) await _load();
  }

  /// Read one adjustment as the server holds it now, or say why it could
  /// not be read. The list row may be minutes old: an edit must start from
  /// the current version, and a view should show what was approved since.
  Future<PartyAdjustment?> _fresh(PartyAdjustment row) async {
    try {
      return await widget.api.partyAdjustment(row.id);
    } on ApiException catch (error) {
      if (!mounted) return null;
      NotificationService.show(
        context,
        error.message,
        kind: AppNotificationKind.error,
      );
      return null;
    }
  }

  Future<void> _edit(PartyAdjustment listed) async {
    final PartyAdjustment? row = await _fresh(listed);
    if (row == null || !mounted) return;
    if (row.status != 'DRAFT') {
      NotificationService.show(
        context,
        '${row.adjustmentNumber} is no longer a draft, so it cannot be edited.',
        kind: AppNotificationKind.error,
      );
      await _load();
      return;
    }
    final bool? saved = await showDocument<bool>(
      context,
      title: 'Edit ${row.adjustmentNumber}',
      builder: (_) => PartyAdjustmentDialog(
        api: widget.api,
        initialKind: row.kind,
        existing: row,
      ),
    );
    if (saved == true) await _load();
  }

  Future<void> _act(
    PartyAdjustment row,
    Future<PartyAdjustment> Function() action,
    String done,
  ) async {
    try {
      await action();
      if (!mounted) return;
      NotificationService.show(
        context,
        '${row.adjustmentNumber} — $done',
        kind: AppNotificationKind.success,
      );
      await _load();
    } on ApiException catch (error) {
      if (!mounted) return;
      NotificationService.show(
        context,
        error.message,
        kind: AppNotificationKind.error,
      );
    }
  }

  /// A cancel is explained afterwards, so it asks why first.
  Future<void> _cancel(PartyAdjustment row) async {
    final String? reason = await askForReason(
      context,
      title: 'Cancel ${row.adjustmentNumber}',
      explanation: 'Whatever the adjustment did is put back. The reason is '
          'kept on it.',
      confirmLabel: 'Cancel adjustment',
      cancelLabel: 'Keep it',
    );
    if (reason == null || !mounted) return;
    await _act(
      row,
      () => widget.api.cancelPartyAdjustment(
        row.id,
        reason,
        expectedVersion: row.version,
      ),
      'cancelled. Whatever it did has been put back.',
    );
  }

  Future<void> _limits() async {
    await showDialog<Object>(
      context: context,
      builder: (_) => _LimitsDialog(api: widget.api, mayEdit: _mayApprove),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.hasActiveFirm) {
      return const WorkspaceEmptyState(
        title: 'Choose a firm',
        message: 'Party adjustments belong to one firm’s books.',
      );
    }
    if (!_mayView) {
      return const WorkspaceEmptyState(
        icon: Icons.lock_outline,
        title: 'You cannot see party adjustments',
        message: 'Reading them needs the view party adjustments permission.',
      );
    }
    final PartyAdjustment? picked = _selected;
    final bool needsSecond =
        picked != null && picked.isDraft && picked.needsSecondApprover;
    return ManagementWorkspaceLayout(
      notice: _notice,
      toolbar: _toolbar(picked),
      searchPanel: SearchFilterPanel(
        controller: _search,
        hintText: 'Search number, party or reason',
        onSearch: (_) => unawaited(_load()),
      ),
      selectionBar: true,
      selection: picked == null
          ? null
          : SelectionSummary.document(
              number: picked.adjustmentNumber,
              party: picked.partyLabel,
              status: picked.status,
              total: picked.amount,
              onClear: () => setState(() => _selectedId = null),
            ),
      primaryContent: _content(),
      statusBar: WorkspaceStatusBar(
        total: _rows.length,
        selected: _selectedId != null,
        message: needsSecond
            ? 'Needs a second approver.'
            : 'Approving moves the balance.',
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
          Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
        ],
        // Said in full here; the status bar has room for only a few words.
        if (_selected != null &&
            _selected!.isDraft &&
            _selected!.needsSecondApprover) ...[
          const SizedBox(height: AppSpacing.sm),
          Text(_secondApproverHint,
              style: Theme.of(context).textTheme.bodySmall),
        ],
        const SizedBox(height: AppSpacing.md),
        Expanded(child: _grid()),
      ],
    );
  }

  WorkspaceToolbar _toolbar(PartyAdjustment? selected) {
    return WorkspaceToolbar(
      trailing: [
        DateRangeFilter(
          value: _period,
          onChanged: (period) {
            setState(() => _period = period);
            unawaited(_load());
          },
        ),
        ColumnsButton(
          onPressed: () async {
            if (await _columns.choose(context) && mounted) setState(() {});
          },
        ),
      ],
      actions: [
        ToolbarAction.view,
        ToolbarAction.refresh,
        if (_mayManage) ToolbarAction.newItem,
      ],
      isEnabled: (action) =>
          action != ToolbarAction.view || selected != null,
      onAction: (action) {
        switch (action) {
          case ToolbarAction.newItem:
            unawaited(_draft());
          case ToolbarAction.view:
            if (selected != null) unawaited(_open(selected));
          default:
            unawaited(_load());
        }
      },
      commands: [
        // Not about the selected row, so it stays on whatever is picked.
        if (_mayManage)
          ToolbarCommand(
            id: 'new-set-off',
            label: 'New set-off',
            icon: Icons.swap_horiz,
            menuOnly: true,
            tooltip: 'Set what a customer owes against what the firm owes '
                'the same business as a supplier',
            onPressed: () => unawaited(_draft(kind: 'SET_OFF')),
          ),
        if (_mayManage)
          ToolbarCommand(
            id: 'edit',
            label: 'Edit',
            icon: Icons.edit_outlined,
            onPressed: selected != null && selected.isDraft
                ? () => unawaited(_edit(selected))
                : null,
          ),
        ToolbarCommand(
          id: 'approve',
          label: 'Approve',
          icon: Icons.check_circle_outline,
          tooltip: selected != null &&
                  selected.isDraft &&
                  selected.needsSecondApprover
              ? _secondApproverHint
              : null,
          onPressed: selected != null && selected.isDraft && _mayApprove
              ? () => _act(
                    selected,
                    () => widget.api.approvePartyAdjustment(
                      selected.id,
                      expectedVersion: selected.version,
                    ),
                    'approved. The balance has moved.',
                  )
              : null,
        ),
        ToolbarCommand(
          id: 'cancel',
          label: 'Cancel',
          icon: Icons.cancel_outlined,
          onPressed: selected != null &&
                  (selected.isDraft || selected.isApproved) &&
                  _mayManage
              ? () => unawaited(_cancel(selected))
              : null,
        ),
        // A firm-wide setting rather than anything about the picked row.
        ToolbarCommand(
          id: 'limits',
          label: 'Limits',
          icon: Icons.tune,
          menuOnly: true,
          onPressed: () => unawaited(_limits()),
        ),
      ],
    );
  }

  late final ColumnChoice<PartyAdjustment> _columns = ColumnChoice(
    preferences: widget.preferences,
    stateKey: 'party-adjustments.grid',
    columns: [
      ChoosableColumn(
        column: const GridColumn(key: 'number', label: 'Number'),
        cell: (item) => item.adjustmentNumber,
        required: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'date', label: 'Date'),
        cell: (item) => item.adjustmentDate,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'kind', label: 'Kind'),
        cell: (item) => item.kindLabel,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'party', label: 'Party', priority: 1),
        cell: (item) => item.partyLabel,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'amount', label: 'Amount', numeric: true),
        cell: (item) => _money(item.amount),
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'reason', label: 'Reason'),
        cell: (item) => item.reason,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'status', label: 'Status'),
        cell: (item) => item.status,
        shownByDefault: true,
      ),
    ],
  );

  /// Read one adjustment: who, why, and the bills it clears.
  Future<void> _open(PartyAdjustment listed) async {
    setState(() => _selectedId = listed.id);
    final PartyAdjustment? row = await _fresh(listed);
    if (row == null || !mounted) return;
    await showDialog<void>(
      context: context,
      builder: (dialogContext) {
        final TextStyle? small = Theme.of(dialogContext).textTheme.bodySmall;
        return AlertDialog(
          title: Row(children: [
            Expanded(child: Text(row.adjustmentNumber)),
            StatusBadge.fromStatus(row.status),
          ]),
          content: SizedBox(
            width: 520,
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text('${row.kindLabel} · ${row.adjustmentDate}'),
                  Text(row.partyLabel, style: small),
                  const SizedBox(height: AppSpacing.sm),
                  Text('Reason: ${row.reason}'),
                  const SizedBox(height: AppSpacing.md),
                  for (final PartyAdjustmentAllocation line in row.allocations)
                    Padding(
                      padding: const EdgeInsets.symmetric(vertical: 2),
                      child: Text(
                        '${line.isCustomerSide ? 'Customer bill' : 'Supplier bill'} '
                        '${line.billNumber} — ${_money(line.amount)}',
                        style: small,
                      ),
                    ),
                  const Divider(),
                  Text('${_money(row.amount)} adjusted'),
                  if (row.isDraft && row.needsSecondApprover)
                    Text(_secondApproverHint, style: small),
                  if (row.cancelReason.isNotEmpty)
                    Text('Cancelled: ${row.cancelReason}', style: small),
                ],
              ),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(dialogContext).pop(),
              child: const Text('Close'),
            ),
          ],
        );
      },
    );
  }

  Widget _grid() {
    if (_rows.isEmpty) {
      return WorkspaceEmptyState(
        title: 'No party adjustments yet',
        message: _mayManage
            ? 'Draft a write-off, a write-back or a set-off to clear a '
                'balance with no money moving.'
            : 'Drafting one needs the manage party adjustments permission.',
      );
    }
    return EnterpriseDataGrid<PartyAdjustment>(
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
      onOpen: (row) => unawaited(_open(row)),
      onPageChanged: (_) {},
    );
  }
}

/// Show money at two decimals; the API answers at more.
String _money(String value) {
  final double? parsed = double.tryParse(value);
  return parsed == null ? value : parsed.toStringAsFixed(2);
}

double _number(String value) => double.tryParse(value.trim()) ?? 0;

/// The firm's two limits: when a second approver is needed, and how much a
/// rounding may be on a receipt or payment.
class _LimitsDialog extends StatefulWidget {
  const _LimitsDialog({required this.api, required this.mayEdit});

  final ApiClient api;
  final bool mayEdit;

  @override
  State<_LimitsDialog> createState() => _LimitsDialogState();
}

class _LimitsDialogState extends State<_LimitsDialog> with SaveInDialog {
  final TextEditingController _threshold = TextEditingController();
  final TextEditingController _rounding = TextEditingController();
  bool _loading = true;
  String? _loadError;
  bool _isDefault = false;

  @override
  void initState() {
    super.initState();
    unawaited(_read());
  }

  @override
  void dispose() {
    _threshold.dispose();
    _rounding.dispose();
    super.dispose();
  }

  Future<void> _read() async {
    try {
      final PartyAdjustmentSettings limits =
          await widget.api.partyAdjustmentSettings();
      if (!mounted) return;
      setState(() {
        _threshold.text = limits.approvalThreshold;
        _rounding.text = limits.roundingLimit;
        _isDefault = limits.isDefault;
        _loading = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _loadError = error.message;
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Adjustment limits'),
      content: SizedBox(
        width: 420,
        child: _loading
            ? const SizedBox(
                height: 80,
                child: Center(child: CircularProgressIndicator()),
              )
            : Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  saveErrorBanner(),
                  if (_loadError != null) Text(_loadError!),
                  TextField(
                    key: const ValueKey('pa-limit-threshold'),
                    controller: _threshold,
                    enabled: widget.mayEdit,
                    keyboardType:
                        const TextInputType.numberWithOptions(decimal: true),
                    decoration: const InputDecoration(
                      labelText: 'Second approver above',
                      helperText: 'An adjustment above this amount needs '
                          'a second person to approve it.',
                      helperMaxLines: 2,
                    ),
                  ),
                  const SizedBox(height: AppSpacing.md),
                  TextField(
                    key: const ValueKey('pa-limit-rounding'),
                    controller: _rounding,
                    enabled: widget.mayEdit,
                    keyboardType:
                        const TextInputType.numberWithOptions(decimal: true),
                    decoration: const InputDecoration(
                      labelText: 'Rounding limit',
                      helperText: 'The most a receipt or payment may be '
                          'rounded or short-paid by.',
                      helperMaxLines: 2,
                    ),
                  ),
                  if (_isDefault)
                    Padding(
                      padding: const EdgeInsets.only(top: AppSpacing.sm),
                      child: Text(
                        'These are the defaults; nothing has been set yet.',
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                    ),
                  if (!widget.mayEdit)
                    Padding(
                      padding: const EdgeInsets.only(top: AppSpacing.sm),
                      child: Text(
                        'Changing them needs the approve party adjustments '
                        'permission.',
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                    ),
                ],
              ),
      ),
      actions: [
        TextButton(
          onPressed: saving ? null : () => Navigator.of(context).pop(false),
          child: Text(widget.mayEdit ? 'Cancel' : 'Close'),
        ),
        if (widget.mayEdit)
          FilledButton(
            key: const ValueKey('pa-limits-save'),
            onPressed: saving || _loading
                ? null
                : () => saveAndClose<PartyAdjustmentSettings>(
                      () => widget.api.savePartyAdjustmentSettings(
                        <String, dynamic>{
                          'approval_threshold': _threshold.text.trim(),
                          'rounding_limit': _rounding.text.trim(),
                        },
                      ),
                    ),
            child: Text(saving ? 'Saving…' : 'Save'),
          ),
      ],
    );
  }
}

/// Draft one adjustment, or change a draft.
class PartyAdjustmentDialog extends StatefulWidget {
  const PartyAdjustmentDialog({
    super.key,
    required this.api,
    this.initialKind = 'CUSTOMER_WRITE_OFF',
    this.existing,
  });

  final ApiClient api;
  final String initialKind;

  /// The draft being changed; its kind is fixed.
  final PartyAdjustment? existing;

  @override
  State<PartyAdjustmentDialog> createState() => _PartyAdjustmentDialogState();
}

class _PartyAdjustmentDialogState extends State<PartyAdjustmentDialog> {
  static const List<(String, String)> _startable = [
    ('CUSTOMER_WRITE_OFF', 'Write-off (bad debt)'),
    ('SUPPLIER_WRITE_BACK', 'Written back'),
    ('SET_OFF', 'Set-off'),
  ];

  /// A rebate settlement starts from the Supplier Rebates screen, so it is not
  /// a choice here; one already drafted is shown (its kind is fixed).
  List<(String, String)> get _kinds => [
        ..._startable,
        if (_kind == 'SUPPLIER_REBATE')
          ('SUPPLIER_REBATE', partyAdjustmentKindLabel('SUPPLIER_REBATE')),
        if (_kind == 'CUSTOMER_REBATE')
          ('CUSTOMER_REBATE', partyAdjustmentKindLabel('CUSTOMER_REBATE')),
        if (_kind == 'PRINCIPAL_CLAIM')
          ('PRINCIPAL_CLAIM', partyAdjustmentKindLabel('PRINCIPAL_CLAIM')),
      ];

  final TextEditingController _amount = TextEditingController();
  final TextEditingController _reason = TextEditingController();
  final Map<String, TextEditingController> _allocations =
      <String, TextEditingController>{};

  late String _kind = widget.initialKind;
  DateTime _date = DateTime.now();
  List<Customer> _customers = const <Customer>[];
  List<Vendor> _vendors = const <Vendor>[];
  String _customerId = '';
  String _vendorId = '';
  // The menus show their own text, so a preselection has to write it.
  final TextEditingController _customerMenu = TextEditingController();
  final TextEditingController _vendorMenu = TextEditingController();
  // True while the party on show was filled in from the other one's link
  // (ACC-11), so choosing a different party on that side replaces it.
  bool _customerPreselected = false;
  bool _vendorPreselected = false;
  PartyAdjustmentOpenBills _bills = const PartyAdjustmentOpenBills();
  bool _loading = true;
  bool _loadingBills = false;
  bool _saving = false;
  String? _error;

  bool get _editing => widget.existing != null;
  bool get _needsCustomer =>
      _kind != 'SUPPLIER_WRITE_BACK' &&
      _kind != 'SUPPLIER_REBATE' &&
      _kind != 'PRINCIPAL_CLAIM';
  bool get _needsVendor =>
      _kind != 'CUSTOMER_WRITE_OFF' && _kind != 'CUSTOMER_REBATE';

  @override
  void initState() {
    super.initState();
    final PartyAdjustment? row = widget.existing;
    if (row != null) {
      _customerId = row.customerId;
      _vendorId = row.vendorId;
      _amount.text = _money(row.amount);
      _reason.text = row.reason;
      _date = DateTime.tryParse(row.adjustmentDate) ?? _date;
    }
    unawaited(_loadParties());
  }

  @override
  void dispose() {
    _amount.dispose();
    _reason.dispose();
    _customerMenu.dispose();
    _vendorMenu.dispose();
    for (final TextEditingController controller in _allocations.values) {
      controller.dispose();
    }
    super.dispose();
  }

  Future<void> _loadParties() async {
    try {
      final List<Customer> customers = await fetchAllPages<Customer>(
        (page) => widget.api.customers(page: page),
      );
      final List<Vendor> vendors = await fetchAllPages<Vendor>(
        (page) => widget.api.vendors(page: page),
      );
      if (!mounted) return;
      setState(() {
        _customers = customers;
        _vendors = vendors;
        _loading = false;
      });
      if (_customerId.isNotEmpty || _vendorId.isNotEmpty) {
        await _loadBills(keepExisting: true);
      }
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.message;
        _loading = false;
      });
    }
  }

  String _vendorLabel(Vendor vendor) =>
      vendor.displayName.isNotEmpty ? vendor.displayName : vendor.name;

  /// A customer was chosen: when a set-off needs a supplier and none was
  /// chosen by hand, preselect the customer's linked one (ACC-11). It stays
  /// changeable.
  void _preselectLinkedVendor(String customerId) {
    if (!_needsVendor || _editing) return;
    if (_vendorId.isNotEmpty && !_vendorPreselected) return;
    String linkedId = '';
    for (final Customer customer in _customers) {
      if (customer.id == customerId) linkedId = customer.linkedVendorId;
    }
    for (final Vendor vendor in _vendors) {
      if (vendor.id == linkedId) {
        _vendorId = vendor.id;
        _vendorMenu.text = _vendorLabel(vendor);
        _vendorPreselected = true;
        return;
      }
    }
  }

  /// A supplier was chosen: preselect the customer of the same business,
  /// asked of the server, when none was chosen by hand (ACC-11).
  Future<void> _preselectLinkedCustomer(String vendorId) async {
    if (!_needsCustomer || _editing) return;
    if (_customerId.isNotEmpty && !_customerPreselected) return;
    try {
      final Json? linked = await widget.api.linkedCustomerOfVendor(vendorId);
      if (!mounted || linked == null || _vendorId != vendorId) return;
      final String id = stringValue(linked['customer_id']);
      for (final Customer customer in _customers) {
        if (customer.id == id) {
          setState(() {
            _customerId = customer.id;
            _customerMenu.text = customer.name;
            _customerPreselected = true;
          });
          await _loadBills();
          return;
        }
      }
    } on Object {
      // A convenience only: nothing is preselected.
    }
  }

  /// The open bills of whichever parties are chosen. [keepExisting] fills
  /// the boxes from the draft being changed instead of clearing them.
  Future<void> _loadBills({bool keepExisting = false}) async {
    final String customerId = _needsCustomer ? _customerId : '';
    final String vendorId = _needsVendor ? _vendorId : '';
    for (final TextEditingController controller in _allocations.values) {
      controller.dispose();
    }
    _allocations.clear();
    if (customerId.isEmpty && vendorId.isEmpty) {
      setState(() => _bills = const PartyAdjustmentOpenBills());
      return;
    }
    setState(() {
      _loadingBills = true;
      _error = null;
    });
    try {
      final PartyAdjustmentOpenBills bills =
          await widget.api.partyAdjustmentOpenBills(
        customerId: customerId,
        vendorId: vendorId,
      );
      if (!mounted) return;
      setState(() {
        _bills = bills;
        for (final OutstandingInvoice bill in bills.customerBills) {
          _allocations['CUSTOMER:${bill.invoiceId}'] = TextEditingController();
        }
        for (final OutstandingInvoice bill in bills.supplierBills) {
          _allocations['SUPPLIER:${bill.invoiceId}'] = TextEditingController();
        }
        if (keepExisting) {
          for (final PartyAdjustmentAllocation line
              in widget.existing?.allocations ?? const []) {
            final TextEditingController? box =
                _allocations['${line.side}:${line.billId}'];
            if (box != null) box.text = _money(line.amount);
          }
        }
        _loadingBills = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.message;
        _loadingBills = false;
      });
    }
  }

  double _allocatedOn(String side) {
    double total = 0;
    _allocations.forEach((key, controller) {
      if (key.startsWith('$side:')) total += _number(controller.text);
    });
    return total;
  }

  /// Say what is wrong before the server has to; it refuses all of this too.
  String? _problem() {
    if (_needsCustomer && _customerId.isEmpty) {
      return 'Choose the customer.';
    }
    if (_needsVendor && _vendorId.isEmpty) return 'Choose the supplier.';
    final double amount = _number(_amount.text);
    if (amount <= 0) return 'Enter the amount being adjusted.';
    if (_reason.text.trim().isEmpty) {
      return 'Say why the balance is being adjusted.';
    }
    final Map<String, double> owed = {
      for (final OutstandingInvoice bill in _bills.customerBills)
        'CUSTOMER:${bill.invoiceId}': bill.outstanding,
      for (final OutstandingInvoice bill in _bills.supplierBills)
        'SUPPLIER:${bill.invoiceId}': bill.outstanding,
    };
    for (final MapEntry<String, TextEditingController> entry
        in _allocations.entries) {
      final double value = _number(entry.value.text);
      if (value > 0 && value - (owed[entry.key] ?? 0) > 0.005) {
        return 'A bill owes ${(owed[entry.key] ?? 0).toStringAsFixed(2)}, so '
            '${value.toStringAsFixed(2)} cannot be taken off it.';
      }
    }
    for (final String side in const ['CUSTOMER', 'SUPPLIER']) {
      if (_allocatedOn(side) - amount > 0.005) {
        return 'More is taken off the ${side == 'CUSTOMER' ? 'customer’s' : 'supplier’s'} '
            'bills than the ${amount.toStringAsFixed(2)} being adjusted.';
      }
    }
    return null;
  }

  List<Map<String, dynamic>> _allocationBody() => [
        for (final MapEntry<String, TextEditingController> entry
            in _allocations.entries)
          if (_number(entry.value.text) > 0)
            <String, dynamic>{
              'side': entry.key.split(':').first,
              'bill_id': entry.key.split(':').last,
              'amount': entry.value.text.trim(),
            },
      ];

  String get _isoDate => _date.toIso8601String().substring(0, 10);

  /// Runs the save itself and stays open with the server's message on a
  /// refusal, so nothing typed is lost.
  Future<void> _save() async {
    final String? problem = _problem();
    if (problem != null) {
      setState(() => _error = problem);
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final PartyAdjustment? row = widget.existing;
      if (row == null) {
        await widget.api.createPartyAdjustment(<String, dynamic>{
          'kind': _kind,
          'adjustment_date': _isoDate,
          if (_needsCustomer) 'customer_id': _customerId,
          if (_needsVendor) 'vendor_id': _vendorId,
          'amount': _amount.text.trim(),
          'reason': _reason.text.trim(),
          'allocations': _allocationBody(),
        });
      } else {
        // The kind and the status are not accepted on an update.
        await widget.api.updatePartyAdjustment(
          row.id,
          <String, dynamic>{
            'adjustment_date': _isoDate,
            if (_needsCustomer) 'customer_id': _customerId,
            if (_needsVendor) 'vendor_id': _vendorId,
            'amount': _amount.text.trim(),
            'reason': _reason.text.trim(),
            'allocations': _allocationBody(),
          },
          expectedVersion: row.version,
        );
      }
      if (!mounted) return;
      Navigator.of(context).pop(true);
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = refusalMessage(error);
        _saving = false;
      });
    }
  }

  InputDecorationTheme _menuTheme(ColorScheme scheme) => InputDecorationTheme(
        isDense: true,
        filled: true,
        fillColor: scheme.surfaceContainerLowest,
        contentPadding: const EdgeInsets.symmetric(horizontal: 8),
        constraints: const BoxConstraints(maxHeight: 36),
        border: OutlineInputBorder(borderRadius: BorderRadius.circular(5)),
      );

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
    if (_loading) return const Center(child: CircularProgressIndicator());
    final PartyAdjustment? row = widget.existing;
    return Material(
      color: scheme.surface,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          DocumentPageBand(
            title: _editing ? 'Edit party adjustment' : 'New party adjustment',
            number: row?.adjustmentNumber ?? '',
            chips: const ['Draft'],
            hint: 'Posts nothing until approved',
            actions: [
              TextButton(
                onPressed:
                    _saving ? null : () => Navigator.of(context).pop(false),
                child: const Text('Cancel'),
              ),
              FilledButton(
                key: const ValueKey('pa-save'),
                onPressed: _saving ? null : () => unawaited(_save()),
                child: Text(_saving
                    ? 'Saving…'
                    : _editing
                        ? 'Save changes'
                        : 'Save draft'),
              ),
            ],
          ),
          if (_error != null)
            Padding(
              padding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
              child: MaterialBanner(
                contentTextStyle: theme.textTheme.bodyMedium,
                content: Text(_error!),
                actions: [
                  TextButton(
                    onPressed: () => setState(() => _error = null),
                    child: const Text('Dismiss'),
                  ),
                ],
              ),
            ),
          Expanded(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(AppSpacing.md),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  _header(context, scheme),
                  const SizedBox(height: AppSpacing.md),
                  if (_loadingBills)
                    const Center(child: CircularProgressIndicator())
                  else ...[
                    if (_needsCustomer)
                      _billTable(
                        context,
                        heading: 'Customer’s open bills',
                        side: 'CUSTOMER',
                        bills: _bills.customerBills,
                        chosen: _customerId.isNotEmpty,
                        total: _bills.customerBalance,
                        totalLabel: 'Customer owes',
                      ),
                    if (_needsCustomer && _needsVendor)
                      const SizedBox(height: AppSpacing.lg),
                    if (_needsVendor)
                      _billTable(
                        context,
                        heading: 'Supplier’s open bills',
                        side: 'SUPPLIER',
                        bills: _bills.supplierBills,
                        chosen: _vendorId.isNotEmpty,
                        total: _bills.supplierOutstanding,
                        totalLabel: 'Firm owes supplier',
                      ),
                  ],
                  const SizedBox(height: AppSpacing.md),
                  Text(
                    _kind == 'SET_OFF'
                        ? 'A set-off must be the same business on both sides, '
                            'and no more than either side owes. What is not '
                            'taken off a bill stays on account.'
                        : 'What is not taken off a bill moves the balance on '
                            'account.',
                    style: theme.textTheme.bodySmall,
                  ),
                  if (row != null && row.needsSecondApprover)
                    Padding(
                      padding: const EdgeInsets.only(top: AppSpacing.sm),
                      child: Text(_secondApproverHint,
                          style: theme.textTheme.bodySmall),
                    ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _header(BuildContext context, ColorScheme scheme) {
    return DocumentHeader(children: [
      DocumentField(
        label: 'Kind',
        width: 220,
        child: DropdownButtonFormField<String>(
          key: const ValueKey('pa-kind'),
          isExpanded: true,
          isDense: true,
          initialValue: _kind,
          decoration: documentBoxDecoration(context),
          items: [
            for (final (String code, String label) in _kinds)
              DropdownMenuItem<String>(
                value: code,
                child: Text(label, overflow: TextOverflow.ellipsis),
              ),
          ],
          // The kind is fixed once a draft exists.
          onChanged: _saving || _editing
              ? null
              : (value) {
                  if (value == null || value == _kind) return;
                  setState(() => _kind = value);
                  unawaited(_loadBills());
                },
        ),
      ),
      if (_needsCustomer)
        DocumentField(
          label: 'Customer',
          width: 240,
          child: DropdownMenu<String>(
            key: const ValueKey('pa-customer'),
            controller: _customerMenu,
            initialSelection: _customerId.isEmpty ? null : _customerId,
            width: 240,
            enabled: !_saving,
            enableFilter: true,
            requestFocusOnTap: true,
            menuHeight: 320,
            inputDecorationTheme: _menuTheme(scheme),
            dropdownMenuEntries: [
              for (final Customer customer in _customers)
                DropdownMenuEntry<String>(
                  value: customer.id,
                  label: customer.name,
                ),
            ],
            onSelected: (value) {
              if (value == null || value == _customerId) return;
              setState(() {
                _customerId = value;
                _customerPreselected = false;
                _preselectLinkedVendor(value);
              });
              unawaited(_loadBills());
            },
          ),
        ),
      if (_needsVendor)
        DocumentField(
          label: 'Supplier',
          width: 240,
          child: DropdownMenu<String>(
            key: const ValueKey('pa-vendor'),
            controller: _vendorMenu,
            initialSelection: _vendorId.isEmpty ? null : _vendorId,
            width: 240,
            enabled: !_saving,
            enableFilter: true,
            requestFocusOnTap: true,
            menuHeight: 320,
            inputDecorationTheme: _menuTheme(scheme),
            dropdownMenuEntries: [
              for (final Vendor vendor in _vendors)
                DropdownMenuEntry<String>(
                  value: vendor.id,
                  label: vendor.displayName.isNotEmpty
                      ? vendor.displayName
                      : vendor.name,
                ),
            ],
            onSelected: (value) {
              if (value == null || value == _vendorId) return;
              setState(() {
                _vendorId = value;
                _vendorPreselected = false;
              });
              unawaited(_loadBills());
              unawaited(_preselectLinkedCustomer(value));
            },
          ),
        ),
      DocumentField(
        label: 'Dated',
        width: 140,
        child: InkWell(
          onTap: _saving
              ? null
              : () async {
                  final DateTime? picked = await showDatePicker(
                    context: context,
                    initialDate: _date,
                    firstDate: DateTime(2000),
                    lastDate: DateTime(2100),
                  );
                  if (picked != null) setState(() => _date = picked);
                },
          child: InputDecorator(
            decoration: documentBoxDecoration(context),
            child: Text(_isoDate),
          ),
        ),
      ),
      DocumentField(
        label: 'Amount',
        width: 140,
        child: TextFormField(
          key: const ValueKey('pa-amount'),
          controller: _amount,
          readOnly: _saving,
          textAlign: TextAlign.right,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          decoration: documentBoxDecoration(context),
          onChanged: (_) => setState(() {}),
        ),
      ),
      DocumentField(
        label: 'Reason (required)',
        width: 320,
        child: TextFormField(
          key: const ValueKey('pa-reason'),
          controller: _reason,
          readOnly: _saving,
          decoration: documentBoxDecoration(context),
        ),
      ),
    ]);
  }

  /// One side's open bills, each with a box for what is taken off it.
  Widget _billTable(
    BuildContext context, {
    required String heading,
    required String side,
    required List<OutstandingInvoice> bills,
    required bool chosen,
    required double? total,
    required String totalLabel,
  }) {
    final ThemeData theme = Theme.of(context);
    final double amount = _number(_amount.text);
    final double allocated = _allocatedOn(side);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(children: [
          Text(heading, style: theme.textTheme.titleSmall),
          const Spacer(),
          if (total != null)
            Text('$totalLabel ${indianAmount(total, full: true)}',
                style: theme.textTheme.bodyMedium),
        ]),
        const SizedBox(height: AppSpacing.xs),
        if (!chosen)
          Text(
            side == 'CUSTOMER'
                ? 'Choose a customer to see what they owe.'
                : 'Choose a supplier to see what the firm owes them.',
            style: theme.textTheme.bodySmall,
          )
        else if (bills.isEmpty)
          Text(
            'No open bills. The whole amount moves the balance on account.',
            style: theme.textTheme.bodySmall,
          )
        else ...[
          for (final OutstandingInvoice bill in bills)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 2),
              child: Row(children: [
                Expanded(
                  flex: 2,
                  child: Text(bill.invoiceNumber,
                      overflow: TextOverflow.ellipsis),
                ),
                Expanded(child: Text(bill.invoiceDate)),
                Expanded(
                  child: Text('Owes ${_money(bill.outstandingAmount)}',
                      textAlign: TextAlign.right),
                ),
                const SizedBox(width: AppSpacing.md),
                SizedBox(
                  width: 120,
                  child: TextField(
                    key: ValueKey<String>('pa-alloc-$side-${bill.invoiceId}'),
                    controller: _allocations['$side:${bill.invoiceId}'],
                    readOnly: _saving,
                    textAlign: TextAlign.right,
                    keyboardType:
                        const TextInputType.numberWithOptions(decimal: true),
                    decoration: const InputDecoration(
                      isDense: true,
                      hintText: '0',
                    ),
                    onChanged: (_) => setState(() {}),
                  ),
                ),
              ]),
            ),
          Padding(
            padding: const EdgeInsets.only(top: AppSpacing.xs),
            child: Align(
              alignment: Alignment.centerRight,
              child: Text(
                amount <= 0
                    ? 'Enter the amount to see what stays on account'
                    : '${allocated.toStringAsFixed(2)} off bills, '
                        '${(amount - allocated).toStringAsFixed(2)} on account',
                style: theme.textTheme.bodySmall,
              ),
            ),
          ),
        ],
      ],
    );
  }
}
