// Staff Advances: money given to an employee that comes back out of his
// salary, or is paid back.
//
// Requests this screen makes:
//  * Opening it makes ONE call, `GET /staff-advances/employees`.
//  * The account choices (`GET /staff-advances/accounts`) are read the first
//    time Give advance or Record recovery opens, and kept for the rest of the
//    visit.
//  * An employee's entries (`GET /staff-advances?employee_account_id=...`) are
//    read only when Entries is opened, one page at a time.
//  * Every save, and every cancel, reads the employee list once more.
//
// Phase 2 only. The page keeps no list of entries of its own.

import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/entities.dart';
import '../../models/staff_advance.dart';
import '../../phase2/indian_format.dart';
import '../workspace/cash_below_zero_prompt.dart';
import '../workspace/desktop_framework.dart';
import '../workspace/reason_prompt.dart';
import 'post_dated_cheque_page.dart' show ChequeDateField;

String _iso(DateTime date) => date.toIso8601String().substring(0, 10);

String _money(String value) {
  final double? amount = double.tryParse(value);
  return amount == null ? value : indianAmount(amount, full: true);
}

/// Staff Advances: one row per employee with what he still owes.
class StaffAdvancesPage extends StatefulWidget {
  const StaffAdvancesPage({
    super.key,
    required this.api,
    required this.permissions,
    required this.hasActiveFirm,
  });

  final ApiClient api;
  final PermissionService permissions;
  final bool hasActiveFirm;

  @override
  State<StaffAdvancesPage> createState() => _StaffAdvancesPageState();
}

class _StaffAdvancesPageState extends State<StaffAdvancesPage> {
  static const String _notice =
      'An advance is money given to an employee that he owes back. It is '
      'taken out of his salary or paid back, and what he still owes is '
      'worked out from the entries. A mistake is cancelled rather than '
      'edited: an opposite journal takes it back and both stay on the record.';

  List<StaffEmployee> _employees = const [];
  String? _selectedId;
  StaffAdvanceAccountChoices? _choices;
  bool _loading = true;
  String? _error;

  bool get _canView => widget.permissions.hasPermission('EXPENSE_VIEW');
  bool get _canCreate => widget.permissions.hasPermission('EXPENSE_CREATE');
  bool get _canCancel => widget.permissions.hasPermission('EXPENSE_CANCEL');

  StaffEmployee? get _selected => _employees
      .where((employee) => employee.accountId == _selectedId)
      .firstOrNull;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load({String? select}) async {
    if (!widget.hasActiveFirm || !_canView) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final List<StaffEmployee> rows = await widget.api.staffEmployees();
      if (!mounted) return;
      setState(() {
        _employees = rows;
        if (select != null) _selectedId = select;
      });
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() {
        _error = exception.message;
        _employees = const [];
      });
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  /// The account choices, read once and kept. Null when they could not be
  /// read; the reason is on the banner.
  Future<StaffAdvanceAccountChoices?> _ensureChoices() async {
    final StaffAdvanceAccountChoices? kept = _choices;
    if (kept != null) return kept;
    try {
      final StaffAdvanceAccountChoices read =
          await widget.api.staffAdvanceAccountChoices();
      if (!mounted) return null;
      setState(() => _choices = read);
      return read;
    } on ApiException catch (exception) {
      if (!mounted) return null;
      setState(() => _error = exception.message);
      return null;
    }
  }

  Future<void> _addEmployee() async {
    final StaffEmployee? added = await showDialog<StaffEmployee>(
      context: context,
      barrierDismissible: false,
      builder: (_) => _AddEmployeeDialog(api: widget.api),
    );
    if (added == null || !mounted) return;
    await _load(select: added.accountId);
    if (!mounted) return;
    NotificationService.show(
      context,
      '${added.name} added.',
      kind: AppNotificationKind.success,
    );
  }

  Future<void> _record(StaffEmployee employee, String kind) async {
    final StaffAdvanceAccountChoices? choices = await _ensureChoices();
    if (choices == null || !mounted) return;
    final StaffAdvanceEntry? saved = await showDialog<StaffAdvanceEntry>(
      context: context,
      barrierDismissible: false,
      builder: (_) => _EntryDialog(
        api: widget.api,
        employee: employee,
        choices: choices,
        kind: kind,
      ),
    );
    if (saved == null || !mounted) return;
    await _load();
    if (!mounted) return;
    NotificationService.show(
      context,
      '${saved.entryNumber} recorded and posted to the ledger.',
      kind: AppNotificationKind.success,
    );
  }

  Future<void> _openEntries(StaffEmployee employee) async {
    await showDialog<void>(
      context: context,
      builder: (_) => _EntriesDialog(
        api: widget.api,
        employee: employee,
        canCancel: _canCancel,
        onChanged: () => _load(),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (!_canView) {
      return const StandardEmptyState(
        type: EmptyStateType.noPermissions,
        title: 'Staff Advances',
        message: 'You do not have permission to view staff advances.',
      );
    }
    if (!widget.hasActiveFirm) {
      return const StandardEmptyState(
        type: EmptyStateType.noFirmSelected,
        title: 'Staff Advances',
        message: 'Choose a firm to see its staff advances.',
      );
    }
    final StaffEmployee? selected = _selected;
    final double totalOwed = _employees.fold<double>(
      0,
      (double sum, StaffEmployee employee) => sum + employee.owesValue,
    );
    final int rowsPerPage = _employees.length < 20 ? 20 : _employees.length;
    return LoadingOverlay(
      loading: _loading,
      child: ManagementWorkspaceLayout(
        notice: _notice,
        toolbar: WorkspaceToolbar(
          actions: const [ToolbarAction.newItem, ToolbarAction.refresh],
          newLabel: 'Add employee',
          isVisible: (action) => action != ToolbarAction.newItem || _canCreate,
          isEnabled: (action) =>
              !_loading &&
              switch (action) {
                ToolbarAction.newItem => _canCreate,
                ToolbarAction.refresh => true,
                _ => false,
              },
          onAction: (action) {
            switch (action) {
              case ToolbarAction.newItem:
                unawaited(_addEmployee());
              case ToolbarAction.refresh:
                unawaited(_load());
              default:
                break;
            }
          },
          commands: [
            if (_canCreate)
              ToolbarCommand(
                id: 'give-advance',
                label: 'Give advance',
                icon: Icons.north_east,
                onPressed: selected != null
                    ? () => unawaited(_record(selected, 'ADVANCE'))
                    : null,
              ),
            if (_canCreate)
              ToolbarCommand(
                id: 'record-recovery',
                label: 'Record recovery',
                icon: Icons.south_west,
                onPressed: selected != null
                    ? () => unawaited(_record(selected, 'RECOVERY'))
                    : null,
              ),
            ToolbarCommand(
              id: 'entries',
              label: 'Entries',
              icon: Icons.list_alt_outlined,
              onPressed:
                  selected != null ? () => unawaited(_openEntries(selected)) : null,
            ),
          ],
        ),
        selectionBar: true,
        selection: selected == null
            ? null
            : SelectionSummary.record(
                name: selected.name,
                facts: ['Still owes ${_money(selected.owes)}'],
                onClear: () => setState(() => _selectedId = null),
              ),
        searchPanel: const SizedBox.shrink(),
        primaryContent: Column(children: [
          if (_error != null)
            MaterialBanner(
              content: Text(_error!),
              actions: [
                TextButton(
                  onPressed: () => setState(() => _error = null),
                  child: const Text('Dismiss'),
                ),
              ],
            ),
          Expanded(
            child: _loading && _employees.isEmpty
                ? const SizedBox.shrink()
                : _employees.isEmpty
                    ? const StandardEmptyState(
                        type: EmptyStateType.noRecords,
                        title: 'No employees yet',
                        message:
                            'No employees yet. Add the first one to give an '
                            'advance.',
                      )
                    : EnterpriseDataGrid<StaffEmployee>(
                        columns: const [
                          GridColumn(key: 'name', label: 'Name', priority: 1),
                          GridColumn(
                              key: 'advanced',
                              label: 'Advanced',
                              numeric: true),
                          GridColumn(
                              key: 'recovered',
                              label: 'Recovered',
                              numeric: true),
                          GridColumn(
                              key: 'owes',
                              label: 'Still owes',
                              numeric: true,
                              priority: 1),
                        ],
                        items: _employees,
                        id: (item) => item.accountId,
                        selectedId: selected?.accountId,
                        cells: (item) => [
                          item.label,
                          item.advanced,
                          item.recovered,
                          item.owes,
                        ],
                        onSelect: (item) =>
                            setState(() => _selectedId = item.accountId),
                        onOpen: (item) => unawaited(_openEntries(item)),
                        total: _employees.length,
                        pageOffset: 0,
                        rowsPerPage: rowsPerPage,
                        onPageChanged: (_) {},
                      ),
          ),
          if (_employees.isNotEmpty)
            Padding(
              padding: const EdgeInsets.symmetric(
                horizontal: AppSpacing.md,
                vertical: AppSpacing.sm,
              ),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  const Text('Still owes in all: '),
                  Text(
                    indianAmount(totalOwed, full: true),
                    key: const ValueKey('staff-total-owed'),
                    style: const TextStyle(fontWeight: FontWeight.bold),
                  ),
                ],
              ),
            ),
        ]),
        statusBar: WorkspaceStatusBar(
          total: _employees.length,
          selected: selected != null,
          message: _loading ? 'Loading...' : null,
        ),
      ),
    );
  }
}

/// A small dialog with one Name box.
class _AddEmployeeDialog extends StatefulWidget {
  const _AddEmployeeDialog({required this.api});

  final ApiClient api;

  @override
  State<_AddEmployeeDialog> createState() => _AddEmployeeDialogState();
}

class _AddEmployeeDialogState extends State<_AddEmployeeDialog>
    with SaveInDialog {
  final TextEditingController _name = TextEditingController();
  String? _problem;

  @override
  void dispose() {
    _name.dispose();
    super.dispose();
  }

  void _save() {
    final String name = _name.text.trim();
    if (name.isEmpty) {
      setState(() => _problem = 'Enter the employee\'s name.');
      return;
    }
    setState(() => _problem = null);
    unawaited(saveAndClose<StaffEmployee>(
      () => widget.api.addStaffEmployee(name),
    ));
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: const Text('Add employee'),
        content: SizedBox(
          width: 420,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              saveErrorBanner(),
              TextField(
                key: const ValueKey('staff-employee-name'),
                controller: _name,
                enabled: !saving,
                autofocus: true,
                maxLength: 100,
                onSubmitted: (_) => _save(),
                decoration: InputDecoration(
                  labelText: 'Name',
                  errorText: _problem,
                ),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(onPressed: cancelHandler, child: const Text('Cancel')),
          FilledButton(
            key: const ValueKey('staff-employee-save'),
            onPressed: saving ? null : _save,
            child: Text(saving ? 'Saving...' : 'Add employee'),
          ),
        ],
      );
}

const String _fromSalary = 'SALARY';
const String _paidBack = 'MONEY';

/// Give an advance, or record a recovery. Pops the saved entry; stays open
/// with the server's message when it is refused.
class _EntryDialog extends StatefulWidget {
  const _EntryDialog({
    required this.api,
    required this.employee,
    required this.choices,
    required this.kind,
  });

  final ApiClient api;
  final StaffEmployee employee;
  final StaffAdvanceAccountChoices choices;

  /// `ADVANCE` or `RECOVERY`.
  final String kind;

  @override
  State<_EntryDialog> createState() => _EntryDialogState();
}

class _EntryDialogState extends State<_EntryDialog> with SaveInDialog {
  final TextEditingController _amount = TextEditingController();
  final TextEditingController _note = TextEditingController();
  DateTime _date = DateTime.now();
  String _side = _fromSalary;
  String? _otherId;
  String? _problem;

  bool get _isAdvance => widget.kind == 'ADVANCE';

  /// Cash accounts first, then banks, each in the order the server gave.
  List<StaffAdvanceAccount> get _moneyChoices => [
        ...widget.choices.moneyAccounts
            .where((account) => account.kind == 'CASH'),
        ...widget.choices.moneyAccounts
            .where((account) => account.kind != 'CASH'),
      ];

  List<StaffAdvanceAccount> get _options =>
      _isAdvance || _side == _paidBack ? _moneyChoices : widget.choices.salaryAccounts;

  @override
  void initState() {
    super.initState();
    _otherId = _defaultFor(_options);
  }

  @override
  void dispose() {
    _amount.dispose();
    _note.dispose();
    super.dispose();
  }

  String? _defaultFor(List<StaffAdvanceAccount> options) {
    if (options.isEmpty) return null;
    if (_isAdvance || _side == _paidBack) return options.first.id;
    final StaffAdvanceAccount? named = options
        .where((account) => account.name.toLowerCase().contains('salar'))
        .firstOrNull;
    if (named != null) return named.id;
    return options.length == 1 ? options.single.id : null;
  }

  void _chooseSide(String? side) {
    if (side == null || side == _side) return;
    setState(() {
      _side = side;
      _otherId = _defaultFor(_options);
    });
  }

  void _save() {
    final String amountText = _amount.text.trim();
    final double? amount = double.tryParse(amountText);
    final StaffEmployee employee = widget.employee;
    String? problem;
    if (_iso(_date).compareTo(_iso(DateTime.now())) > 0) {
      problem = 'The date cannot be after today.';
    } else if (_otherId == null) {
      problem = _isAdvance
          ? 'Choose the account the money is paid from.'
          : _side == _fromSalary
              ? 'Choose the salary account.'
              : 'Choose the account the money was paid into.';
    } else if (amount == null || amount <= 0) {
      problem = 'The amount must be more than zero.';
    } else if (!_isAdvance && amount > employee.owesValue + 0.004) {
      problem = 'He owes only ${_money(employee.owes)}.';
    }
    setState(() => _problem = problem);
    if (problem != null) return;
    final String note = _note.text.trim();
    unawaited(_send(amountText, note));
  }

  Future<void> _send(String amount, String note) async {
    setState(() {
      saving = true;
      saveError = null;
    });
    try {
      final StaffAdvanceEntry? saved = await saveAskingAboutCash<
          StaffAdvanceEntry>(
        context,
        (bool confirmed) => widget.api.recordStaffAdvance(<String, dynamic>{
          if (confirmed) 'cash_below_zero_confirmed': true,
          'kind': widget.kind,
          'entry_date': _iso(_date),
          'employee_account_id': widget.employee.accountId,
          'other_account_id': _otherId,
          'amount': amount,
          if (note.isNotEmpty) 'narration': note,
        }),
      );
      if (!mounted) return;
      if (saved == null) {
        // Went back from the question: the form stays as typed.
        setState(() => saving = false);
        return;
      }
      Navigator.of(context).pop(saved);
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() {
        saving = false;
        saveError = exception.message;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final StaffEmployee employee = widget.employee;
    final List<StaffAdvanceAccount> options = _options;
    final String otherLabel = _isAdvance
        ? 'Paid from'
        : _side == _fromSalary
            ? 'Salary account'
            : 'Paid into';
    return AlertDialog(
      title: Text(_isAdvance ? 'Give advance' : 'Record recovery'),
      content: SizedBox(
        width: 520,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              saveErrorBanner(),
              if (_problem != null)
                Padding(
                  padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                  child: Text(
                    _problem!,
                    key: const ValueKey('staff-problem'),
                    style: TextStyle(color: theme.colorScheme.error),
                  ),
                ),
              InputDecorator(
                decoration: const InputDecoration(labelText: 'Employee'),
                child: Text(employee.name, key: const ValueKey('staff-who')),
              ),
              const SizedBox(height: AppSpacing.md),
              ChequeDateField(
                key: const ValueKey('staff-date'),
                label: 'Date',
                value: _date,
                enabled: !saving,
                onChanged: (date) => setState(() => _date = date),
              ),
              const SizedBox(height: AppSpacing.md),
              if (!_isAdvance) ...[
                DropdownButtonFormField<String>(
                  key: const ValueKey('staff-side'),
                  initialValue: _side,
                  isExpanded: true,
                  decoration: const InputDecoration(labelText: 'Recovery'),
                  items: const [
                    DropdownMenuItem(
                      value: _fromSalary,
                      child: Text('Taken from salary'),
                    ),
                    DropdownMenuItem(
                      value: _paidBack,
                      child: Text('Paid back in cash or bank'),
                    ),
                  ],
                  onChanged: saving ? null : _chooseSide,
                ),
                const SizedBox(height: AppSpacing.md),
              ],
              DropdownButtonFormField<String>(
                key: ValueKey('staff-other-$_side'),
                initialValue: _otherId,
                isExpanded: true,
                decoration: InputDecoration(
                  labelText: otherLabel,
                  helperText: !_isAdvance && _side == _fromSalary
                      ? 'The salary account is charged this amount. Record '
                          'the rest of the salary, the part paid now, as an '
                          'expense.'
                      : null,
                  helperMaxLines: 3,
                ),
                items: [
                  for (final StaffAdvanceAccount account in options)
                    DropdownMenuItem<String>(
                      value: account.id,
                      child: Text(account.label,
                          overflow: TextOverflow.ellipsis),
                    ),
                ],
                onChanged: saving ? null : (id) => setState(() => _otherId = id),
              ),
              const SizedBox(height: AppSpacing.md),
              TextField(
                key: const ValueKey('staff-amount'),
                controller: _amount,
                enabled: !saving,
                keyboardType: const TextInputType.numberWithOptions(
                  decimal: true,
                ),
                decoration: InputDecoration(
                  labelText: 'Amount',
                  helperText:
                      _isAdvance ? null : 'He owes ${_money(employee.owes)}.',
                ),
              ),
              const SizedBox(height: AppSpacing.md),
              TextField(
                key: const ValueKey('staff-note'),
                controller: _note,
                enabled: !saving,
                decoration: const InputDecoration(labelText: 'Note'),
              ),
              if (_isAdvance)
                Padding(
                  padding: const EdgeInsets.only(top: AppSpacing.sm),
                  child: Text(
                    'He owes ${_money(employee.owes)} now.',
                    key: const ValueKey('staff-owes-now'),
                    style: theme.textTheme.bodySmall,
                  ),
                ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(onPressed: cancelHandler, child: const Text('Cancel')),
        FilledButton(
          key: const ValueKey('staff-save'),
          onPressed: saving ? null : _save,
          child: Text(saving ? 'Saving...' : 'Save'),
        ),
      ],
    );
  }
}

/// One employee's advances and recoveries, newest first, a page at a time.
class _EntriesDialog extends StatefulWidget {
  const _EntriesDialog({
    required this.api,
    required this.employee,
    required this.canCancel,
    required this.onChanged,
  });

  final ApiClient api;
  final StaffEmployee employee;
  final bool canCancel;

  /// Called after a cancel, so the employee list reads itself again.
  final Future<void> Function() onChanged;

  @override
  State<_EntriesDialog> createState() => _EntriesDialogState();
}

class _EntriesDialogState extends State<_EntriesDialog> {
  static const int _rowsPerPage = 10;

  List<StaffAdvanceEntry> _rows = const [];
  int _page = 1;
  int _total = 0;
  bool _loading = true;
  String? _error;

  int get _pages => _total == 0 ? 1 : (_total + _rowsPerPage - 1) ~/ _rowsPerPage;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load({int? page}) async {
    setState(() {
      _loading = true;
      _error = null;
      if (page != null) _page = page;
    });
    try {
      final PagedResult<StaffAdvanceEntry> result =
          await widget.api.staffAdvances(
        page: _page,
        pageSize: _rowsPerPage,
        employeeAccountId: widget.employee.accountId,
      );
      if (!mounted) return;
      setState(() {
        _rows = result.items;
        _total = result.total;
      });
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() {
        _error = exception.message;
        _rows = const [];
        _total = 0;
      });
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _cancel(StaffAdvanceEntry row) async {
    final String? why = await askForReason(
      context,
      title: 'Cancel ${row.entryNumber}',
      explanation: 'This writes an opposite journal, so the ${row.amount} '
          'comes back off ${row.employeeName}\'s account. Nothing is '
          'deleted: both stay on the record.',
      label: 'Why is it being cancelled?',
      confirmLabel: 'Cancel entry',
      cancelLabel: 'Keep it',
    );
    if (why == null || !mounted) return;
    setState(() => _loading = true);
    try {
      await widget.api.cancelStaffAdvance(
        row.id,
        reason: why,
        version: row.version,
      );
      await widget.onChanged();
      if (!mounted) return;
      await _load();
      if (!mounted) return;
      NotificationService.show(
        context,
        '${row.entryNumber} cancelled.',
        kind: AppNotificationKind.success,
      );
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() {
        _error = exception.message;
        _loading = false;
      });
    }
  }

  Widget _cell(String text, {double? width, bool right = false, TextStyle? style}) {
    final Widget child = Text(
      text,
      overflow: TextOverflow.ellipsis,
      textAlign: right ? TextAlign.right : TextAlign.left,
      style: style,
    );
    return width == null
        ? Expanded(child: child)
        : SizedBox(width: width, child: child);
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final TextStyle? head = theme.textTheme.labelMedium;
    return AlertDialog(
      title: Text('${widget.employee.name}: entries'),
      content: SizedBox(
        width: 860,
        height: 440,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (_error != null)
              Padding(
                padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                child: Text(
                  _error!,
                  key: const ValueKey('staff-entries-error'),
                  style: TextStyle(color: theme.colorScheme.error),
                ),
              ),
            Row(children: [
              _cell('Date', width: 100, style: head),
              _cell('Number', width: 190, style: head),
              _cell('What', width: 150, style: head),
              _cell('Account', style: head),
              _cell('Amount', width: 110, right: true, style: head),
              _cell('Status', width: 90, style: head),
              const SizedBox(width: 90),
            ]),
            const Divider(),
            Expanded(
              child: _loading && _rows.isEmpty
                  ? const Center(child: CircularProgressIndicator())
                  : _rows.isEmpty
                      ? const Center(child: Text('No entries yet.'))
                      : ListView(children: [
                          for (final StaffAdvanceEntry row in _rows)
                            Padding(
                              padding: const EdgeInsets.symmetric(vertical: 2),
                              child: Row(children: [
                                _cell(row.entryDate, width: 100),
                                _cell(row.entryNumber, width: 190),
                                _cell(row.what, width: 150),
                                _cell(row.otherAccountName),
                                _cell(_money(row.amount),
                                    width: 110, right: true),
                                _cell(
                                  row.isCancelled ? 'Cancelled' : 'Posted',
                                  width: 90,
                                ),
                                SizedBox(
                                  width: 90,
                                  child: widget.canCancel && !row.isCancelled
                                      ? TextButton(
                                          key: ValueKey('staff-cancel-${row.id}'),
                                          onPressed: _loading
                                              ? null
                                              : () => unawaited(_cancel(row)),
                                          child: const Text('Cancel'),
                                        )
                                      : null,
                                ),
                              ]),
                            ),
                        ]),
            ),
            Row(
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                TextButton(
                  key: const ValueKey('staff-entries-newer'),
                  onPressed: _loading || _page <= 1
                      ? null
                      : () => unawaited(_load(page: _page - 1)),
                  child: const Text('Newer'),
                ),
                Text('Page $_page of $_pages'),
                TextButton(
                  key: const ValueKey('staff-entries-older'),
                  onPressed: _loading || _page >= _pages
                      ? null
                      : () => unawaited(_load(page: _page + 1)),
                  child: const Text('Older'),
                ),
              ],
            ),
          ],
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
}
