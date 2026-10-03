// TDS challans: tax deducted at source, paid to the government (ACC-7).
//
// A challan is the deposit (ITNS 281) and the deductions it paid. It posts its
// journal the moment it is saved and is undone by a cancel that keeps its
// reason; the deductions it covered become open again. Phase 2 only.

import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/preferences/desktop_preferences_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/contra_voucher.dart';
import '../../models/tds.dart';
import '../../models/tds_challan.dart';
import '../workspace/desktop_framework.dart';
import '../workspace/reason_prompt.dart';

/// The words on the screen's notice, behind the page line's (i).
const String _notice =
    'Record each deposit of tax deducted at source here: the bank, the '
    'challan serial, and the deductions it paid. Tick only what the challan '
    'covers. It posts as soon as it is saved; a cancel puts the deductions '
    'back among those still to be paid.';

/// List the firm's TDS challans, record one or cancel one.
class TdsChallanPage extends StatefulWidget {
  const TdsChallanPage({
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
  State<TdsChallanPage> createState() => _TdsChallanPageState();
}

class _TdsChallanPageState extends State<TdsChallanPage> {
  List<TdsChallan> _rows = const [];
  final Map<String, TdsChallan> _details = <String, TdsChallan>{};
  String? _error;
  String? _selectedId;
  bool _loading = true;

  final TextEditingController _search = TextEditingController();
  DatePeriod _period = const DatePeriod.all();

  String? get _from =>
      _period.from == null ? null : DatePeriod.iso(_period.from!);
  String? get _to => _period.to == null ? null : DatePeriod.iso(_period.to!);

  bool get _mayView =>
      widget.permissions.hasPermission('ACCOUNT_VIEW') ||
      widget.permissions.hasPermission('JOURNAL_VIEW');
  bool get _mayPost => widget.permissions.hasPermission('JOURNAL_POST');
  bool get _mayReverse => widget.permissions.hasPermission('JOURNAL_REVERSE');

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

  /// The rows the search box leaves in: the list is read whole, so it is
  /// narrowed here.
  List<TdsChallan> get _shown {
    final String query = _search.text.trim().toLowerCase();
    if (query.isEmpty) return _rows;
    return _rows
        .where((row) =>
            row.challanNumber.toLowerCase().contains(query) ||
            row.section.toLowerCase().contains(query) ||
            row.cin.toLowerCase().contains(query) ||
            row.paidFromAccountName.toLowerCase().contains(query))
        .toList();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final List<TdsChallan> rows = await fetchAllPages<TdsChallan>(
        (page) => widget.api.tdsChallans(
          page: page,
          fromDate: _from,
          toDate: _to,
        ),
      );
      if (!mounted) return;
      setState(() {
        _rows = rows;
        _details.clear();
        _loading = false;
      });
      final TdsChallan? picked = _selected;
      if (picked != null) unawaited(_readItems(picked));
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.message;
        _loading = false;
      });
    }
  }

  /// The listed row, or the whole challan once it has been read.
  TdsChallan? get _selected {
    final TdsChallan? listed =
        _rows.where((row) => row.id == _selectedId).firstOrNull;
    return listed == null ? null : _details[listed.id] ?? listed;
  }

  /// A list row may not carry its deductions; read the challan for them.
  Future<void> _readItems(TdsChallan row) async {
    if (row.items.isNotEmpty || _details.containsKey(row.id)) return;
    try {
      final TdsChallan whole = await widget.api.tdsChallan(row.id);
      if (!mounted) return;
      setState(() => _details[row.id] = whole);
    } on ApiException {
      // The deductions are a detail of the row, not a gate on it.
    }
  }

  void _select(TdsChallan row) {
    setState(() => _selectedId = row.id);
    unawaited(_readItems(row));
  }

  Future<void> _new() async {
    final TdsChallan? saved = await showDialog<TdsChallan>(
      context: context,
      barrierDismissible: false,
      builder: (_) => TdsChallanDialog(api: widget.api),
    );
    if (saved == null || !mounted) return;
    setState(() => _selectedId = saved.id);
    NotificationService.show(
      context,
      '${saved.challanNumber} — posted.',
      kind: AppNotificationKind.success,
    );
    await _load();
  }

  /// A cancel is explained afterwards, so it asks why first.
  Future<void> _cancel(TdsChallan row) async {
    final String? reason = await askForReason(
      context,
      title: 'Cancel ${row.challanNumber}',
      explanation: 'The deposit is reversed and its deductions become open '
          'again. The reason is kept on the challan.',
      confirmLabel: 'Cancel challan',
      cancelLabel: 'Keep it',
    );
    if (reason == null || !mounted) return;
    try {
      await widget.api.cancelTdsChallan(
        row.id,
        reason,
        expectedVersion: row.version,
      );
      if (!mounted) return;
      NotificationService.show(
        context,
        '${row.challanNumber} — cancelled.',
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

  @override
  Widget build(BuildContext context) {
    if (!widget.hasActiveFirm) {
      return const WorkspaceEmptyState(
        title: 'Choose a firm',
        message: 'TDS challans belong to one firm’s books.',
      );
    }
    if (!_mayView) {
      return const WorkspaceEmptyState(
        icon: Icons.lock_outline,
        title: 'You cannot see TDS challans',
        message: 'Reading them needs the view accounts permission.',
      );
    }
    final TdsChallan? picked = _selected;
    return ManagementWorkspaceLayout(
      notice: _notice,
      toolbar: _toolbar(picked),
      searchPanel: SearchFilterPanel(
        controller: _search,
        hintText: 'Search number, section, CIN or account',
        onSearch: (_) => setState(() {}),
      ),
      selectionBar: true,
      selection: picked == null
          ? null
          : SelectionSummary.document(
              number: picked.challanNumber,
              party: '${picked.section} · CIN ${picked.cin}',
              status: picked.status,
              total: picked.totalAmount,
              onClear: () => setState(() => _selectedId = null),
            ),
      primaryContent: _content(picked),
      statusBar: WorkspaceStatusBar(
        total: _rows.length,
        selected: _selectedId != null,
        message: 'A challan posts when it is saved.',
      ),
    );
  }

  Widget _content(TdsChallan? picked) {
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
        if (picked != null) _items(picked),
      ],
    );
  }

  /// The deductions the selected challan paid.
  Widget _items(TdsChallan challan) {
    final TextStyle? small = Theme.of(context).textTheme.bodySmall;
    return Container(
      key: const ValueKey('tds-challan-items'),
      height: 150,
      margin: const EdgeInsets.only(top: AppSpacing.sm),
      child: ListView(
        children: [
          Text(
            'Deductions on ${challan.challanNumber}'
            '${challan.cancelReason.isEmpty ? '' : ' (cancelled: ${challan.cancelReason})'}',
            style: Theme.of(context).textTheme.titleSmall,
          ),
          if (challan.items.isEmpty) Text('None to show.', style: small),
          for (final TdsChallanItem item in challan.items)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 2),
              child: Text(
                '${item.documentNumber} · ${item.documentDate} · '
                '${item.partyName}'
                '${item.pan.isEmpty ? '' : ' · ${item.pan}'}'
                ' · ${_money(item.tdsAmount)}',
              ),
            ),
        ],
      ),
    );
  }

  WorkspaceToolbar _toolbar(TdsChallan? selected) {
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
        ToolbarAction.refresh,
        if (_mayPost) ToolbarAction.newItem,
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
        ToolbarCommand(
          id: 'cancel',
          label: 'Cancel',
          icon: Icons.cancel_outlined,
          onPressed: selected != null && selected.isPosted && _mayReverse
              ? () => unawaited(_cancel(selected))
              : null,
        ),
      ],
    );
  }

  late final ColumnChoice<TdsChallan> _columns = ColumnChoice(
    preferences: widget.preferences,
    stateKey: 'tds-challans.grid',
    columns: [
      ChoosableColumn(
        column: const GridColumn(key: 'number', label: 'Number'),
        cell: (item) => item.challanNumber,
        required: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'date', label: 'Deposited'),
        cell: (item) => item.depositedOn,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'section', label: 'Section'),
        cell: (item) => item.section,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'cin', label: 'CIN'),
        cell: (item) => item.cin,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'tax', label: 'Tax', numeric: true),
        cell: (item) => _money(item.taxAmount),
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(
            key: 'extra', label: 'Interest + fee', numeric: true),
        cell: (item) => item.interestAndFee.toStringAsFixed(2),
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'total', label: 'Total', numeric: true),
        cell: (item) => _money(item.totalAmount),
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'from', label: 'Paid from', priority: 1),
        cell: (item) => item.paidFromAccountName,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'status', label: 'Status'),
        cell: (item) => item.status,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'late', label: 'Late'),
        cell: (item) => item.isLate ? 'Late' : '',
        shownByDefault: true,
      ),
    ],
  );

  Widget _grid() {
    final List<TdsChallan> shown = _shown;
    if (shown.isEmpty) {
      return WorkspaceEmptyState(
        title: 'No TDS challans yet',
        message: _mayPost
            ? 'Record a deposit of tax deducted at source and tick the '
                'deductions it paid.'
            : 'Recording one needs the post journal entries permission.',
      );
    }
    return EnterpriseDataGrid<TdsChallan>(
      items: shown,
      total: shown.length,
      pageOffset: 0,
      rowsPerPage: shown.length,
      availableRowsPerPage: [shown.length],
      selectedId: _selectedId,
      columns: _columns.gridColumns,
      id: (row) => row.id,
      cells: _columns.cells,
      onSelect: _select,
      onOpen: _select,
      onPageChanged: (_) {},
    );
  }
}

/// Show money at two decimals; the API answers at more.
String _money(String value) {
  final double? parsed = double.tryParse(value);
  return parsed == null ? value : parsed.toStringAsFixed(2);
}

/// Record one challan. Pops the saved [TdsChallan]; stays open with the
/// server's message when it is refused.
class TdsChallanDialog extends StatefulWidget {
  const TdsChallanDialog({super.key, required this.api});

  final ApiClient api;

  @override
  State<TdsChallanDialog> createState() => _TdsChallanDialogState();
}

class _TdsChallanDialogState extends State<TdsChallanDialog> with SaveInDialog {
  final TextEditingController _bsr = TextEditingController();
  final TextEditingController _serial = TextEditingController();
  final TextEditingController _interest = TextEditingController();
  final TextEditingController _fee = TextEditingController();
  final TextEditingController _counterfoil = TextEditingController();
  final TextEditingController _remarks = TextEditingController();
  DateTime _date = DateTime.now();
  String? _section;
  String? _accountId;
  List<MoneyAccount> _accounts = const [];
  List<TdsOpenDeduction> _open = const [];
  final Set<String> _ticked = <String>{};
  bool _loading = true;
  bool _loadingOpen = false;
  String? _problem;

  /// Only the latest question about open deductions may answer.
  int _asked = 0;

  @override
  void initState() {
    super.initState();
    unawaited(_readAccounts());
  }

  @override
  void dispose() {
    _bsr.dispose();
    _serial.dispose();
    _interest.dispose();
    _fee.dispose();
    _counterfoil.dispose();
    _remarks.dispose();
    super.dispose();
  }

  Future<void> _readAccounts() async {
    try {
      final List<MoneyAccount> accounts =
          await widget.api.contraMoneyAccounts();
      if (!mounted) return;
      setState(() {
        _accounts = accounts;
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

  String get _isoDate => _date.toIso8601String().substring(0, 10);

  /// The deductions for the chosen section dated on or before the deposit,
  /// all ticked until somebody unticks one.
  Future<void> _readOpen() async {
    final String? section = _section;
    if (section == null) return;
    final int asked = ++_asked;
    setState(() {
      _loadingOpen = true;
      _open = const [];
      _ticked.clear();
    });
    try {
      final List<TdsOpenDeduction> rows = await widget.api.tdsOpenDeductions(
        section: section,
        toDate: _isoDate,
      );
      if (!mounted || asked != _asked) return;
      setState(() {
        _open = rows;
        _ticked.addAll(rows.map((row) => row.key));
        _loadingOpen = false;
      });
    } on ApiException catch (error) {
      if (!mounted || asked != _asked) return;
      setState(() {
        saveError = error.message;
        _loadingOpen = false;
      });
    }
  }

  double get _tax => _open
      .where((row) => _ticked.contains(row.key))
      .fold<double>(0, (sum, row) => sum + row.tax);

  void _save() {
    final String bsr = _bsr.text.trim();
    final String serial = _serial.text.trim();
    final String interest = _interest.text.trim();
    final String fee = _fee.text.trim();
    final String counterfoil = _counterfoil.text.trim();
    final String remarks = _remarks.text.trim();
    String? problem;
    if (!RegExp(r'^\d{7}$').hasMatch(bsr)) {
      problem = 'The BSR code is seven digits.';
    } else if (!RegExp(r'^\d{1,5}$').hasMatch(serial)) {
      problem = 'The challan serial is one to five digits.';
    } else if (_section == null) {
      problem = 'Choose the section this challan pays.';
    } else if (_accountId == null) {
      problem = 'Choose the account the money was paid from.';
    } else if (_ticked.isEmpty) {
      problem = 'Tick at least one deduction this challan pays.';
    } else if (interest.isNotEmpty && double.tryParse(interest) == null) {
      problem = 'Interest must be a number.';
    } else if (fee.isNotEmpty && double.tryParse(fee) == null) {
      problem = 'The late fee must be a number.';
    } else if (counterfoil.isNotEmpty && double.tryParse(counterfoil) == null) {
      problem = 'The counterfoil amount must be a number.';
    }
    setState(() => _problem = problem);
    if (problem != null) return;
    unawaited(saveAndClose<TdsChallan>(
      () => widget.api.createTdsChallan(<String, dynamic>{
        'deposited_on': _isoDate,
        'bsr_code': bsr,
        'challan_serial': serial,
        'section': _section,
        'paid_from_account_id': _accountId,
        if (counterfoil.isNotEmpty) 'tax_amount': counterfoil,
        'interest_amount': interest.isEmpty ? '0' : interest,
        'fee_amount': fee.isEmpty ? '0' : fee,
        if (remarks.isNotEmpty) 'remarks': remarks,
        'deductions': [
          for (final TdsOpenDeduction row in _open)
            if (_ticked.contains(row.key))
              <String, dynamic>{'kind': row.kind, 'id': row.id},
        ],
      }),
    ));
  }

  Widget _deductions(BuildContext context) {
    if (_section == null) {
      return const Text('Choose a section to see what is still to be paid.');
    }
    if (_loadingOpen) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_open.isEmpty) {
      return const Text(
        'Nothing is waiting to be paid under this section on or before that '
        'date.',
        key: ValueKey('tds-challan-none'),
      );
    }
    final TextStyle? small = Theme.of(context).textTheme.bodySmall;
    return ListView(
      children: [
        for (final TdsOpenDeduction row in _open)
          CheckboxListTile(
            key: ValueKey('tds-open-${row.key}'),
            dense: true,
            contentPadding: EdgeInsets.zero,
            controlAffinity: ListTileControlAffinity.leading,
            value: _ticked.contains(row.key),
            onChanged: saving
                ? null
                : (value) => setState(() {
                      if (value ?? false) {
                        _ticked.add(row.key);
                      } else {
                        _ticked.remove(row.key);
                      }
                    }),
            title: Text(
              '${row.documentNumber} · ${row.partyName} · ${_money(row.tdsAmount)}',
              overflow: TextOverflow.ellipsis,
            ),
            subtitle: Text(
              '${row.documentDate}'
              '${row.pan.isEmpty ? '' : ' · ${row.pan}'}'
              '${row.dueDate.isEmpty ? '' : ' · due ${row.dueDate}'}',
              style: small,
            ),
          ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Record TDS challan'),
      content: SizedBox(
        width: 640,
        child: _loading
            ? const SizedBox(
                height: 80,
                child: Center(child: CircularProgressIndicator()),
              )
            : SingleChildScrollView(
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
                          key: const ValueKey('tds-challan-problem'),
                          style: TextStyle(
                              color: Theme.of(context).colorScheme.error),
                        ),
                      ),
                    Row(children: [
                      Expanded(
                        child: InkWell(
                          key: const ValueKey('tds-challan-date'),
                          onTap: saving
                              ? null
                              : () async {
                                  final DateTime? picked = await showDatePicker(
                                    context: context,
                                    initialDate: _date,
                                    firstDate: DateTime(2000),
                                    lastDate: DateTime(2100),
                                  );
                                  if (picked == null) return;
                                  setState(() => _date = picked);
                                  unawaited(_readOpen());
                                },
                          child: InputDecorator(
                            decoration: const InputDecoration(
                                labelText: 'Deposited on'),
                            child: Text(_isoDate),
                          ),
                        ),
                      ),
                      const SizedBox(width: AppSpacing.md),
                      Expanded(
                        child: TextField(
                          key: const ValueKey('tds-challan-bsr'),
                          controller: _bsr,
                          decoration:
                              const InputDecoration(labelText: 'BSR code'),
                        ),
                      ),
                      const SizedBox(width: AppSpacing.md),
                      Expanded(
                        child: TextField(
                          key: const ValueKey('tds-challan-serial'),
                          controller: _serial,
                          decoration: const InputDecoration(
                              labelText: 'Challan serial'),
                        ),
                      ),
                    ]),
                    const SizedBox(height: AppSpacing.md),
                    Row(children: [
                      Expanded(
                        child: DropdownButtonFormField<String>(
                          key: const ValueKey('tds-challan-section'),
                          initialValue: _section,
                          isExpanded: true,
                          decoration:
                              const InputDecoration(labelText: 'Section'),
                          items: [
                            for (final MapEntry<String, String> entry
                                in tdsSections.entries)
                              DropdownMenuItem(
                                value: entry.key,
                                child: Text(
                                  '${entry.key} - ${entry.value}',
                                  overflow: TextOverflow.ellipsis,
                                ),
                              ),
                          ],
                          onChanged: saving
                              ? null
                              : (value) {
                                  setState(() => _section = value);
                                  unawaited(_readOpen());
                                },
                        ),
                      ),
                      const SizedBox(width: AppSpacing.md),
                      Expanded(
                        child: DropdownButtonFormField<String>(
                          key: const ValueKey('tds-challan-account'),
                          initialValue: _accountId,
                          isExpanded: true,
                          decoration:
                              const InputDecoration(labelText: 'Paid from'),
                          items: [
                            for (final MoneyAccount account in _accounts)
                              DropdownMenuItem<String>(
                                value: account.id,
                                child: Text(
                                  '${account.label} '
                                  '(${account.isCash ? 'Cash' : 'Bank'})',
                                  overflow: TextOverflow.ellipsis,
                                ),
                              ),
                          ],
                          onChanged: saving
                              ? null
                              : (value) => setState(() => _accountId = value),
                        ),
                      ),
                    ]),
                    const SizedBox(height: AppSpacing.md),
                    Row(children: [
                      Expanded(
                        child: TextField(
                          key: const ValueKey('tds-challan-interest'),
                          controller: _interest,
                          keyboardType: const TextInputType.numberWithOptions(
                              decimal: true),
                          decoration:
                              const InputDecoration(labelText: 'Interest'),
                        ),
                      ),
                      const SizedBox(width: AppSpacing.md),
                      Expanded(
                        child: TextField(
                          key: const ValueKey('tds-challan-fee'),
                          controller: _fee,
                          keyboardType: const TextInputType.numberWithOptions(
                              decimal: true),
                          decoration:
                              const InputDecoration(labelText: 'Late fee'),
                        ),
                      ),
                      const SizedBox(width: AppSpacing.md),
                      Expanded(
                        child: TextField(
                          key: const ValueKey('tds-challan-counterfoil'),
                          controller: _counterfoil,
                          keyboardType: const TextInputType.numberWithOptions(
                              decimal: true),
                          decoration: const InputDecoration(
                            labelText: 'Counterfoil amount',
                            helperText: 'Optional check',
                          ),
                        ),
                      ),
                    ]),
                    const SizedBox(height: AppSpacing.md),
                    TextField(
                      key: const ValueKey('tds-challan-remarks'),
                      controller: _remarks,
                      decoration: const InputDecoration(labelText: 'Remarks'),
                    ),
                    const SizedBox(height: AppSpacing.md),
                    Text(
                      'Deductions this challan pays',
                      style: Theme.of(context).textTheme.titleSmall,
                    ),
                    const SizedBox(height: AppSpacing.sm),
                    SizedBox(height: 180, child: _deductions(context)),
                    const SizedBox(height: AppSpacing.sm),
                    Text(
                      'Tax: ₹${_tax.toStringAsFixed(2)}',
                      key: const ValueKey('tds-challan-tax'),
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                  ],
                ),
              ),
      ),
      actions: [
        TextButton(
          onPressed: saving ? null : () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
        FilledButton(
          key: const ValueKey('tds-challan-save'),
          onPressed: saving || _loading ? null : _save,
          child: Text(saving ? 'Posting…' : 'Record'),
        ),
      ],
    );
  }
}
