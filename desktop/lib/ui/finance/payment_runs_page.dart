// Payment runs (BUY-11): pick the supplier bills falling due, approve the run
// to record one bank payment per supplier, and download the bank's bulk file.
// Phase 2 only.

import 'dart:async';
import 'dart:io';

import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/preferences/desktop_preferences_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/payment_run.dart';
import '../../models/settlement.dart';
import '../../models/settlement_direction.dart';
import '../workspace/desktop_framework.dart';
import '../workspace/reason_prompt.dart';

String _iso(DateTime date) => date.toIso8601String().substring(0, 10);

String _money(String value) {
  final double? parsed = double.tryParse(value);
  return parsed == null ? value : parsed.toStringAsFixed(2);
}

String _words(String status) =>
    status.isEmpty ? status : status[0] + status.substring(1).toLowerCase();

/// List the firm's payment runs and move them along.
class PaymentRunsPage extends StatefulWidget {
  const PaymentRunsPage({
    super.key,
    required this.api,
    required this.preferences,
    required this.permissions,
    required this.hasActiveFirm,
    this.saveBytesOverride,
  });

  final ApiClient api;
  final DesktopPreferencesService preferences;
  final PermissionService permissions;
  final bool hasActiveFirm;

  /// Tests inject this, because a widget test cannot open a save panel.
  final SaveBytesOverride? saveBytesOverride;

  @override
  State<PaymentRunsPage> createState() => _PaymentRunsPageState();
}

class _PaymentRunsPageState extends State<PaymentRunsPage> {
  List<PaymentRun> _rows = const [];
  String? _error;
  String? _selectedId;
  bool _loading = true;
  final TextEditingController _search = TextEditingController();

  bool get _mayView => widget.permissions.hasPermission('PAYMENT_VIEW');
  bool get _mayWrite => widget.permissions.hasPermission('PAYMENT_CREATE');
  bool get _mayApprove =>
      widget.permissions.hasPermission('PAYMENT_RUN_APPROVE');

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
      final List<PaymentRun> rows = await widget.api.listPaymentRuns();
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

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  List<PaymentRun> get _shown {
    final String q = _search.text.trim().toLowerCase();
    if (q.isEmpty) return _rows;
    return _rows
        .where((row) =>
            row.runNumber.toLowerCase().contains(q) ||
            row.remarks.toLowerCase().contains(q))
        .toList();
  }

  PaymentRun? get _selected =>
      _rows.where((row) => row.id == _selectedId).firstOrNull;

  void _tell(String message, AppNotificationKind kind) =>
      NotificationService.show(context, message, kind: kind);

  Future<void> _new() async {
    final PaymentRun? saved = await showDialog<PaymentRun>(
      context: context,
      barrierDismissible: false,
      builder: (_) => NewPaymentRunDialog(api: widget.api),
    );
    if (saved == null || !mounted) return;
    setState(() => _selectedId = saved.id);
    _tell('Run ${saved.runNumber} saved as a draft.',
        AppNotificationKind.success);
    await _load();
  }

  Future<void> _act(
    PaymentRun run,
    Future<Object?> Function() call,
    String done,
  ) async {
    try {
      await call();
      if (!mounted) return;
      _tell('Run ${run.runNumber} $done.', AppNotificationKind.success);
      await _load();
    } on ApiException catch (error) {
      if (!mounted) return;
      _tell(error.message, AppNotificationKind.error);
    }
  }

  Future<void> _approve(PaymentRun run) => _act(
        run,
        () =>
            widget.api.approvePaymentRun(run.id, expectedVersion: run.version),
        'approved; the payments are recorded',
      );

  Future<void> _cancel(PaymentRun run) async {
    final String? reason = await askForReason(
      context,
      title: 'Cancel run ${run.runNumber}',
      explanation: 'The run is closed without paying anyone. The reason is '
          'kept on it.',
      confirmLabel: 'Cancel run',
      cancelLabel: 'Keep it',
    );
    if (reason == null || !mounted) return;
    await _act(
      run,
      () => widget.api.cancelPaymentRun(
        run.id,
        reason: reason,
        expectedVersion: run.version,
      ),
      'cancelled',
    );
  }

  Future<void> _bankFile(PaymentRun run) async {
    try {
      final List<int> csv = await widget.api.paymentRunBankFile(run.id);
      if (!mounted) return;
      final String name = 'Payment run ${run.runNumber}.csv';
      if (widget.saveBytesOverride != null) {
        await widget.saveBytesOverride!(name, csv);
      } else {
        final FileSaveLocation? location = await getSaveLocation(
          suggestedName: name,
          acceptedTypeGroups: const [
            XTypeGroup(label: 'CSV file', extensions: ['csv']),
          ],
        );
        if (location == null) return;
        await File(location.path).writeAsBytes(csv, flush: true);
      }
      if (!mounted) return;
      _tell('The bank file was saved.', AppNotificationKind.success);
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
        message: 'Payment runs belong to one firm’s books.',
      );
    }
    if (!_mayView) {
      return const WorkspaceEmptyState(
        icon: Icons.lock_outline,
        title: 'You cannot see payment runs',
        message: 'Reading them needs the view payments permission.',
      );
    }
    final PaymentRun? picked = _selected;
    return ManagementWorkspaceLayout(
      notice: 'Pay many suppliers at once. Pick the bills falling due, approve '
          'the run to record one bank payment per supplier, then download '
          'the file your bank takes for a bulk upload.',
      toolbar: _toolbar(picked),
      searchPanel: SearchFilterPanel(
        controller: _search,
        hintText: 'Search run number or remarks',
        onSearch: (_) => setState(() {}),
      ),
      selectionBar: true,
      selection: picked == null
          ? null
          : SelectionSummary.document(
              number: picked.runNumber,
              party: '${picked.supplierCount} suppliers',
              status: picked.status,
              total: picked.total,
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
                if (picked != null && picked.cancelReason.isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.only(top: AppSpacing.sm),
                    child: Text('Cancelled: ${picked.cancelReason}',
                        style: Theme.of(context).textTheme.bodySmall),
                  ),
              ],
            ),
      statusBar: WorkspaceStatusBar(
        total: _rows.length,
        selected: _selectedId != null,
        message: 'Payment runs',
      ),
    );
  }

  WorkspaceToolbar _toolbar(PaymentRun? selected) {
    final bool draft = selected != null && selected.isDraft;
    return WorkspaceToolbar(
      actions: [
        ToolbarAction.refresh,
        if (_mayWrite) ToolbarAction.newItem,
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
        if (_mayApprove)
          ToolbarCommand(
            id: 'approve',
            label: 'Approve',
            icon: Icons.check_circle_outline,
            onPressed: draft ? () => unawaited(_approve(selected)) : null,
          ),
        if (_mayWrite) ...[
          ToolbarCommand(
            id: 'cancel',
            label: 'Cancel',
            icon: Icons.cancel_outlined,
            onPressed: draft ? () => unawaited(_cancel(selected)) : null,
          ),
          ToolbarCommand(
            id: 'bank-file',
            label: 'Bank file',
            icon: Icons.download_outlined,
            onPressed: selected == null
                ? null
                : () => unawaited(_bankFile(selected)),
          ),
        ],
      ],
    );
  }

  late final ColumnChoice<PaymentRun> _columns = ColumnChoice(
    preferences: widget.preferences,
    stateKey: 'payment-runs.grid',
    columns: [
      ChoosableColumn(
        column: const GridColumn(key: 'number', label: 'Run'),
        cell: (item) => item.runNumber,
        required: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'date', label: 'Payment date'),
        cell: (item) => item.paymentDate,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'due', label: 'Due by', priority: 1),
        cell: (item) => item.dueBy,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'suppliers', label: 'Suppliers'),
        cell: (item) => '${item.supplierCount}',
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'bills', label: 'Bills', priority: 1),
        cell: (item) => '${item.lines.length}',
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'total', label: 'Total', numeric: true),
        cell: (item) => _money(item.total),
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'status', label: 'Status'),
        cell: (item) => _words(item.status),
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'remarks', label: 'Remarks', priority: 2),
        cell: (item) => item.remarks,
        shownByDefault: true,
      ),
    ],
  );

  Widget _grid() {
    final List<PaymentRun> rows = _shown;
    if (rows.isEmpty) {
      return WorkspaceEmptyState(
        title: 'No payment runs yet',
        message: _mayWrite
            ? 'Start a run to pay the bills falling due in one go.'
            : 'Starting one needs the create permission for payments.',
      );
    }
    return EnterpriseDataGrid<PaymentRun>(
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

/// Start a run: choose a due-by date, tick the bills, say how much of each.
/// Pops the saved [PaymentRun]; stays open with the server's message on a
/// refusal.
class NewPaymentRunDialog extends StatefulWidget {
  const NewPaymentRunDialog({super.key, required this.api});

  final ApiClient api;

  @override
  State<NewPaymentRunDialog> createState() => _NewPaymentRunDialogState();
}

class _NewPaymentRunDialogState extends State<NewPaymentRunDialog>
    with SaveInDialog {
  final TextEditingController _remarks = TextEditingController();
  final Map<String, TextEditingController> _amounts = {};
  final Set<String> _ticked = <String>{};
  Map<String, String> _names = const {};
  List<PaymentRunBill> _bills = const [];
  DateTime _dueBy = DateTime.now().add(const Duration(days: 7));
  DateTime _paymentDate = DateTime.now();
  bool _loading = true;
  String? _problem;

  @override
  void initState() {
    super.initState();
    unawaited(_readNames());
    unawaited(_readProposal());
  }

  @override
  void dispose() {
    _remarks.dispose();
    for (final TextEditingController c in _amounts.values) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _readNames() async {
    try {
      final List<PartyOption> parties = await widget.api
          .settlementParties(direction: SettlementDirection.payment);
      if (!mounted) return;
      setState(() => _names = {for (final p in parties) p.id: p.name});
    } on ApiException {
      // A missing name is not a reason to stop; the bill still shows.
    }
  }

  Future<void> _readProposal() async {
    setState(() {
      _loading = true;
      saveError = null;
    });
    try {
      final List<PaymentRunBill> bills =
          await widget.api.paymentRunProposal(dueBy: _iso(_dueBy));
      if (!mounted) return;
      for (final TextEditingController c in _amounts.values) {
        c.dispose();
      }
      _amounts.clear();
      for (final PaymentRunBill bill in bills) {
        _amounts[bill.invoiceId] = TextEditingController();
      }
      setState(() {
        _bills = bills;
        _ticked
          ..clear()
          ..addAll(bills.map((bill) => bill.invoiceId));
        _loading = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _bills = const [];
        saveError = error.message;
        _loading = false;
      });
    }
  }

  void _save() {
    String? problem;
    final List<Map<String, dynamic>> lines = [];
    for (final PaymentRunBill bill in _bills) {
      if (!_ticked.contains(bill.invoiceId)) continue;
      final String typed = _amounts[bill.invoiceId]!.text.trim();
      final double? value = double.tryParse(typed);
      if (typed.isNotEmpty && (value == null || value <= 0)) {
        problem = 'Bill ${bill.invoiceNumber}: the amount must be more than '
            'zero, or blank for all it owes.';
        break;
      }
      lines.add(<String, dynamic>{
        'invoice_id': bill.invoiceId,
        if (typed.isNotEmpty) 'amount': typed,
      });
    }
    if (problem == null && lines.isEmpty) {
      problem = 'Tick at least one bill.';
    }
    setState(() => _problem = problem);
    if (problem != null) return;
    final String remarks = _remarks.text.trim();
    unawaited(saveAndClose<PaymentRun>(
      () => widget.api.createPaymentRun(<String, dynamic>{
        'payment_date': _iso(_paymentDate),
        'due_by': _iso(_dueBy),
        if (remarks.isNotEmpty) 'remarks': remarks,
        'lines': lines,
      }),
    ));
  }

  Future<void> _pick(DateTime current, ValueChanged<DateTime> onPicked) async {
    final DateTime? picked = await showDatePicker(
      context: context,
      initialDate: current,
      firstDate: DateTime(2000),
      lastDate: DateTime(2100),
    );
    if (picked != null) onPicked(picked);
  }

  Widget _dateField(Key key, String label, DateTime value, VoidCallback tap) =>
      InkWell(
        key: key,
        onTap: saving ? null : tap,
        child: InputDecorator(
          decoration: InputDecoration(labelText: label),
          child: Text(_iso(value)),
        ),
      );

  List<Widget> _grouped() {
    final Map<String, List<PaymentRunBill>> bySupplier = {};
    for (final PaymentRunBill bill in _bills) {
      bySupplier.putIfAbsent(bill.partyId, () => []).add(bill);
    }
    final ThemeData theme = Theme.of(context);
    final List<Widget> out = [];
    bySupplier.forEach((partyId, bills) {
      final bool all = bills.every((b) => _ticked.contains(b.invoiceId));
      out.add(CheckboxListTile(
        key: ValueKey('run-supplier-$partyId'),
        dense: true,
        controlAffinity: ListTileControlAffinity.leading,
        value: all,
        onChanged: saving
            ? null
            : (on) => setState(() {
                  for (final PaymentRunBill b in bills) {
                    on == true
                        ? _ticked.add(b.invoiceId)
                        : _ticked.remove(b.invoiceId);
                  }
                }),
        title: Text(_names[partyId] ?? 'Supplier',
            style: theme.textTheme.titleSmall),
      ));
      for (final PaymentRunBill bill in bills) {
        out.add(Padding(
          padding: const EdgeInsets.only(left: AppSpacing.lg),
          child: Row(children: [
            Checkbox(
              key: ValueKey('run-bill-${bill.invoiceId}'),
              value: _ticked.contains(bill.invoiceId),
              onChanged: saving
                  ? null
                  : (on) => setState(() => on == true
                      ? _ticked.add(bill.invoiceId)
                      : _ticked.remove(bill.invoiceId)),
            ),
            Expanded(
              child: Text(
                '${bill.invoiceNumber}'
                '${bill.isOpeningBill ? ' (opening)' : ''}'
                '${bill.dueDate.isEmpty ? '' : ' · due ${bill.dueDate}'}',
                overflow: TextOverflow.ellipsis,
              ),
            ),
            SizedBox(
              width: 150,
              child: TextField(
                key: ValueKey('run-amount-${bill.invoiceId}'),
                controller: _amounts[bill.invoiceId],
                enabled: !saving && _ticked.contains(bill.invoiceId),
                keyboardType:
                    const TextInputType.numberWithOptions(decimal: true),
                decoration: InputDecoration(
                  isDense: true,
                  labelText: 'Amount',
                  helperText: 'Owes ${_money(bill.outstandingAmount)}',
                ),
              ),
            ),
          ]),
        ));
      }
    });
    return out;
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('New payment run'),
      content: SizedBox(
        width: 720,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            saveErrorBanner(),
            Row(children: [
              Expanded(
                child: _dateField(
                  const ValueKey('run-due-by'),
                  'Due by',
                  _dueBy,
                  () => unawaited(_pick(_dueBy, (date) {
                    setState(() => _dueBy = date);
                    unawaited(_readProposal());
                  })),
                ),
              ),
              const SizedBox(width: AppSpacing.md),
              Expanded(
                child: _dateField(
                  const ValueKey('run-payment-date'),
                  'Payment date',
                  _paymentDate,
                  () => unawaited(_pick(_paymentDate,
                      (date) => setState(() => _paymentDate = date))),
                ),
              ),
            ]),
            const SizedBox(height: AppSpacing.md),
            TextField(
              key: const ValueKey('run-remarks'),
              controller: _remarks,
              enabled: !saving,
              decoration: const InputDecoration(labelText: 'Remarks'),
            ),
            if (_problem != null)
              Padding(
                padding: const EdgeInsets.only(top: AppSpacing.sm),
                child: Text(_problem!,
                    key: const ValueKey('run-problem'),
                    style:
                        TextStyle(color: Theme.of(context).colorScheme.error)),
              ),
            const SizedBox(height: AppSpacing.sm),
            Flexible(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxHeight: 320),
                child: _loading
                    ? const SizedBox(
                        height: 80,
                        child: Center(child: CircularProgressIndicator()))
                    : _bills.isEmpty
                        ? const Padding(
                            padding: EdgeInsets.all(AppSpacing.md),
                            child: Text('No bills fall due by that date.'),
                          )
                        : ListView(shrinkWrap: true, children: _grouped()),
              ),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: saving ? null : () => Navigator.pop(context),
          child: const Text('Cancel'),
        ),
        FilledButton(
          key: const ValueKey('run-save'),
          onPressed: saving || _loading ? null : _save,
          child: Text(saving ? 'Saving…' : 'Save run'),
        ),
      ],
    );
  }
}
