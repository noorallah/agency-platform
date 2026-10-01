// Contra vouchers: money moved between the firm's own cash and bank accounts.
//
// A deposit, a withdrawal or a transfer. A voucher posts its journal the
// moment it is saved and is undone by a cancel that keeps its reason. Phase 2
// only.

import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/preferences/desktop_preferences_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/contra_voucher.dart';
import '../workspace/desktop_framework.dart';
import '../workspace/printed_document.dart';
import '../workspace/reason_prompt.dart';

/// The words on the screen's notice, behind the page line's (i).
const String _notice =
    'Use a contra voucher when money moves between the firm’s own cash and '
    'bank accounts: cash paid into the bank, cash drawn from it, or a '
    'transfer between two banks. It posts as soon as it is saved; a cancel '
    'puts it back.';

/// List the firm's contra vouchers, post one, print it or cancel it.
class ContraVoucherPage extends StatefulWidget {
  const ContraVoucherPage({
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
  State<ContraVoucherPage> createState() => _ContraVoucherPageState();
}

class _ContraVoucherPageState extends State<ContraVoucherPage> {
  List<ContraVoucher> _rows = const [];
  String? _error;
  String? _selectedId;
  bool _loading = true;

  final TextEditingController _search = TextEditingController();
  DatePeriod _period = const DatePeriod.all();

  String? get _from =>
      _period.from == null ? null : DatePeriod.iso(_period.from!);
  String? get _to => _period.to == null ? null : DatePeriod.iso(_period.to!);

  bool get _mayView => widget.permissions.hasPermission('JOURNAL_VIEW');
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

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final List<ContraVoucher> rows = await fetchAllPages<ContraVoucher>(
        (page) => widget.api.contraVouchers(
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

  ContraVoucher? get _selected =>
      _rows.where((row) => row.id == _selectedId).firstOrNull;

  /// Say what happened. A warning is not a refusal: the voucher is saved.
  void _tell(String done, ContraVoucher voucher) {
    final bool warned = voucher.balanceWarning.isNotEmpty;
    NotificationService.show(
      context,
      warned ? '$done ${voucher.balanceWarning}' : done,
      kind: warned ? AppNotificationKind.warning : AppNotificationKind.success,
    );
  }

  Future<void> _new() async {
    final ContraVoucher? saved = await showDialog<ContraVoucher>(
      context: context,
      builder: (_) => ContraVoucherDialog(api: widget.api),
    );
    if (saved == null || !mounted) return;
    setState(() => _selectedId = saved.id);
    _tell('${saved.voucherNumber} — posted.', saved);
    await _load();
  }

  Future<void> _print(ContraVoucher row) async {
    try {
      final List<int> pdf = await widget.api.contraVoucherPdf(row.id);
      if (!mounted) return;
      await printDocument(
        context,
        bytes: pdf,
        documentName: row.voucherNumber,
      );
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
  Future<void> _cancel(ContraVoucher row) async {
    final String? reason = await askForReason(
      context,
      title: 'Cancel ${row.voucherNumber}',
      explanation: 'The money is put back where it came from. The reason is '
          'kept on the voucher.',
      confirmLabel: 'Cancel voucher',
      cancelLabel: 'Keep it',
    );
    if (reason == null || !mounted) return;
    try {
      final ContraVoucher done = await widget.api.cancelContraVoucher(
        row.id,
        reason,
        expectedVersion: row.version,
      );
      if (!mounted) return;
      _tell('${row.voucherNumber} — cancelled.', done);
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
        message: 'Contra vouchers belong to one firm’s books.',
      );
    }
    if (!_mayView) {
      return const WorkspaceEmptyState(
        icon: Icons.lock_outline,
        title: 'You cannot see contra vouchers',
        message: 'Reading them needs the view journal entries permission.',
      );
    }
    final ContraVoucher? picked = _selected;
    return ManagementWorkspaceLayout(
      notice: _notice,
      toolbar: _toolbar(picked),
      searchPanel: SearchFilterPanel(
        controller: _search,
        hintText: 'Search number, account or reference',
        onSearch: (_) => unawaited(_load()),
      ),
      selectionBar: true,
      selection: picked == null
          ? null
          : SelectionSummary.document(
              number: picked.voucherNumber,
              party: '${picked.fromAccountName} → ${picked.toAccountName}',
              status: picked.status,
              total: picked.amount,
              onClear: () => setState(() => _selectedId = null),
            ),
      primaryContent: _content(),
      statusBar: WorkspaceStatusBar(
        total: _rows.length,
        selected: _selectedId != null,
        message: 'A voucher posts when it is saved.',
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

  WorkspaceToolbar _toolbar(ContraVoucher? selected) {
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
        ToolbarAction.print,
      ],
      isEnabled: (action) =>
          action != ToolbarAction.print || selected != null,
      onAction: (action) {
        switch (action) {
          case ToolbarAction.newItem:
            unawaited(_new());
          case ToolbarAction.print:
            if (selected != null) unawaited(_print(selected));
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

  late final ColumnChoice<ContraVoucher> _columns = ColumnChoice(
    preferences: widget.preferences,
    stateKey: 'contra-vouchers.grid',
    columns: [
      ChoosableColumn(
        column: const GridColumn(key: 'number', label: 'Number'),
        cell: (item) => item.voucherNumber,
        required: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'date', label: 'Date'),
        cell: (item) => item.voucherDate,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'kind', label: 'Kind'),
        cell: (item) => item.kindLabel,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'from', label: 'From', priority: 1),
        cell: (item) => item.fromAccountName,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'to', label: 'To', priority: 1),
        cell: (item) => item.toAccountName,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'amount', label: 'Amount', numeric: true),
        cell: (item) => _money(item.amount),
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'reference', label: 'Reference'),
        cell: (item) => item.reference,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'status', label: 'Status'),
        cell: (item) => item.status,
        shownByDefault: true,
      ),
    ],
  );

  /// Read one voucher: the accounts, the words and why it was cancelled.
  Future<void> _open(ContraVoucher listed) async {
    setState(() => _selectedId = listed.id);
    ContraVoucher row = listed;
    try {
      row = await widget.api.contraVoucher(listed.id);
    } on ApiException catch (error) {
      if (!mounted) return;
      NotificationService.show(
        context,
        error.message,
        kind: AppNotificationKind.error,
      );
      return;
    }
    if (!mounted) return;
    final ContraVoucher shown = row;
    await showDialog<void>(
      context: context,
      builder: (dialogContext) {
        final TextStyle? small = Theme.of(dialogContext).textTheme.bodySmall;
        return AlertDialog(
          title: Row(children: [
            Expanded(child: Text(shown.voucherNumber)),
            StatusBadge.fromStatus(shown.status),
          ]),
          content: SizedBox(
            width: 480,
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text('${shown.kindLabel} · ${shown.voucherDate}'),
                  const SizedBox(height: AppSpacing.sm),
                  Text('From: ${shown.fromAccountName}'),
                  Text('To: ${shown.toAccountName}'),
                  const SizedBox(height: AppSpacing.sm),
                  Text(_money(shown.amount)),
                  if (shown.reference.isNotEmpty)
                    Text('Reference: ${shown.reference}', style: small),
                  if (shown.remarks.isNotEmpty)
                    Text(shown.remarks, style: small),
                  if (shown.cancelReason.isNotEmpty)
                    Text('Cancelled: ${shown.cancelReason}', style: small),
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
        title: 'No contra vouchers yet',
        message: _mayPost
            ? 'Record cash paid into the bank, cash drawn from it, or a '
                'transfer between two accounts.'
            : 'Posting one needs the post journal entries permission.',
      );
    }
    return EnterpriseDataGrid<ContraVoucher>(
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

/// Post one voucher. Pops the saved [ContraVoucher]; stays open with the
/// server's message when it is refused.
class ContraVoucherDialog extends StatefulWidget {
  const ContraVoucherDialog({super.key, required this.api});

  final ApiClient api;

  @override
  State<ContraVoucherDialog> createState() => _ContraVoucherDialogState();
}

class _ContraVoucherDialogState extends State<ContraVoucherDialog>
    with SaveInDialog {
  final TextEditingController _amount = TextEditingController();
  final TextEditingController _reference = TextEditingController();
  final TextEditingController _remarks = TextEditingController();
  DateTime _date = DateTime.now();
  List<MoneyAccount> _accounts = const [];
  String? _fromId;
  String? _toId;
  bool _loading = true;
  String? _problem;

  @override
  void initState() {
    super.initState();
    unawaited(_read());
  }

  @override
  void dispose() {
    _amount.dispose();
    _reference.dispose();
    _remarks.dispose();
    super.dispose();
  }

  Future<void> _read() async {
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

  MoneyAccount? _account(String? id) =>
      _accounts.where((a) => a.id == id).firstOrNull;

  void _save() {
    final double? amount = double.tryParse(_amount.text.trim());
    String? problem;
    if (_fromId == null || _toId == null) {
      problem = 'Choose both the From and the To account.';
    } else if (_fromId == _toId) {
      problem = 'From and To must be different accounts.';
    } else if (amount == null || amount <= 0) {
      problem = 'Enter an amount above zero.';
    }
    setState(() => _problem = problem);
    if (problem != null) return;
    final String reference = _reference.text.trim();
    final String remarks = _remarks.text.trim();
    unawaited(saveAndClose<ContraVoucher>(
      () => widget.api.createContraVoucher(<String, dynamic>{
        'voucher_date': _isoDate,
        'from_account_id': _fromId,
        'to_account_id': _toId,
        'amount': _amount.text.trim(),
        if (reference.isNotEmpty) 'reference': reference,
        if (remarks.isNotEmpty) 'remarks': remarks,
      }),
    ));
  }

  Widget _picker(String key, String label, String? value,
      ValueChanged<String?> onChanged) {
    return DropdownButtonFormField<String>(
      key: ValueKey(key),
      initialValue: value,
      isExpanded: true,
      decoration: InputDecoration(labelText: label),
      items: [
        for (final MoneyAccount account in _accounts)
          DropdownMenuItem<String>(
            value: account.id,
            child: Text(
              '${account.label} (${account.isCash ? 'Cash' : 'Bank'})',
              overflow: TextOverflow.ellipsis,
            ),
          ),
      ],
      onChanged: saving ? null : onChanged,
    );
  }

  @override
  Widget build(BuildContext context) {
    final String hint = contraKindHint(_account(_fromId), _account(_toId));
    return AlertDialog(
      title: const Text('New contra voucher'),
      content: SizedBox(
        width: 460,
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
                          key: const ValueKey('contra-problem'),
                          style: TextStyle(
                              color: Theme.of(context).colorScheme.error),
                        ),
                      ),
                    InkWell(
                      key: const ValueKey('contra-date'),
                      onTap: saving
                          ? null
                          : () async {
                              final DateTime? picked = await showDatePicker(
                                context: context,
                                initialDate: _date,
                                firstDate: DateTime(2000),
                                lastDate: DateTime(2100),
                              );
                              if (picked != null) {
                                setState(() => _date = picked);
                              }
                            },
                      child: InputDecorator(
                        decoration: const InputDecoration(labelText: 'Dated'),
                        child: Text(_isoDate),
                      ),
                    ),
                    const SizedBox(height: AppSpacing.md),
                    _picker('contra-from', 'From', _fromId,
                        (v) => setState(() => _fromId = v)),
                    const SizedBox(height: AppSpacing.md),
                    _picker('contra-to', 'To', _toId,
                        (v) => setState(() => _toId = v)),
                    if (hint.isNotEmpty)
                      Padding(
                        padding: const EdgeInsets.only(top: AppSpacing.sm),
                        child: Text(
                          'This will be a $hint.',
                          key: const ValueKey('contra-kind-hint'),
                          style: Theme.of(context).textTheme.bodySmall,
                        ),
                      ),
                    const SizedBox(height: AppSpacing.md),
                    TextField(
                      key: const ValueKey('contra-amount'),
                      controller: _amount,
                      keyboardType:
                          const TextInputType.numberWithOptions(decimal: true),
                      decoration: const InputDecoration(labelText: 'Amount'),
                    ),
                    const SizedBox(height: AppSpacing.md),
                    TextField(
                      key: const ValueKey('contra-reference'),
                      controller: _reference,
                      decoration: const InputDecoration(
                        labelText: 'Reference',
                        helperText: 'A cheque, slip or transfer number.',
                      ),
                    ),
                    const SizedBox(height: AppSpacing.md),
                    TextField(
                      key: const ValueKey('contra-remarks'),
                      controller: _remarks,
                      decoration: const InputDecoration(labelText: 'Remarks'),
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
          key: const ValueKey('contra-save'),
          onPressed: saving || _loading ? null : _save,
          child: Text(saving ? 'Posting…' : 'Post'),
        ),
      ],
    );
  }
}
