// The post-dated cheque register (ACC-2): cheques received from customers and
// cheques the firm has issued to suppliers, one page for both.
//
// A cheque is held until its date, then banked (which raises the real receipt
// or payment), then cleared or returned. A return reverses what banking
// raised. Phase 2 only.

import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/preferences/desktop_preferences_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/post_dated_cheque.dart';
import '../../models/settlement.dart';
import '../../models/settlement_direction.dart';
import '../workspace/desktop_framework.dart';
import '../workspace/reason_prompt.dart';

const List<String> _statuses = [
  'HELD',
  'DEPOSITED',
  'CLEARED',
  'BOUNCED',
  'CANCELLED',
];

/// List the firm's post-dated cheques, take one in and move it along.
class PostDatedChequePage extends StatefulWidget {
  const PostDatedChequePage({
    super.key,
    required this.api,
    required this.preferences,
    required this.permissions,
    required this.hasActiveFirm,
    required this.issued,
  });

  final ApiClient api;

  /// Where the grid's chosen columns are remembered.
  final DesktopPreferencesService preferences;
  final PermissionService permissions;
  final bool hasActiveFirm;

  /// True for the firm's own cheques to suppliers, false for a customer's.
  final bool issued;

  @override
  State<PostDatedChequePage> createState() => _PostDatedChequePageState();
}

class _PostDatedChequePageState extends State<PostDatedChequePage> {
  List<PostDatedCheque> _rows = const [];
  String? _error;
  String? _selectedId;
  bool _loading = true;
  String? _status;
  bool _dueOnly = false;
  final TextEditingController _search = TextEditingController();

  bool get _mayView => widget.permissions
      .hasPermission(widget.issued ? 'PAYMENT_VIEW' : 'RECEIPT_VIEW');
  bool get _mayWrite => widget.permissions
      .hasPermission(widget.issued ? 'PAYMENT_CREATE' : 'RECEIPT_CREATE');

  String get _noun => widget.issued ? 'Issued cheques' : 'Cheques received';
  String get _depositWord => widget.issued ? 'Present' : 'Deposit';
  String get _bounceWord => widget.issued ? 'Returned' : 'Bounce';

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
    final String today = _iso(DateTime.now());
    final String search = _search.text.trim();
    try {
      final List<PostDatedCheque> rows = await fetchAllPages<PostDatedCheque>(
        (page) => widget.api.listPostDatedCheques(
          issued: widget.issued,
          page: page,
          search: search,
          status: _status,
          dueOn: _dueOnly ? today : null,
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

  PostDatedCheque? get _selected =>
      _rows.where((row) => row.id == _selectedId).firstOrNull;

  void _tell(String message, AppNotificationKind kind) =>
      NotificationService.show(context, message, kind: kind);

  Future<void> _new() async {
    final PostDatedCheque? saved = await showDialog<PostDatedCheque>(
      context: context,
      barrierDismissible: false,
      builder: (_) => NewPostDatedChequeDialog(
        api: widget.api,
        issued: widget.issued,
      ),
    );
    if (saved == null || !mounted) return;
    setState(() => _selectedId = saved.id);
    _tell('Cheque ${saved.chequeNumber} — held.', AppNotificationKind.success);
    await _load();
  }

  Future<void> _deposit(PostDatedCheque row) async {
    final PostDatedCheque? saved = await showDialog<PostDatedCheque>(
      context: context,
      barrierDismissible: false,
      builder: (_) => DepositPostDatedChequeDialog(
        api: widget.api,
        issued: widget.issued,
        cheque: row,
      ),
    );
    if (saved == null || !mounted) return;
    _tell(
      'Cheque ${row.chequeNumber} — '
      '${widget.issued ? 'presented' : 'deposited'}.',
      AppNotificationKind.success,
    );
    await _load();
  }

  Future<void> _clear(PostDatedCheque row) async {
    final PostDatedCheque? saved = await showDialog<PostDatedCheque>(
      context: context,
      barrierDismissible: false,
      builder: (_) => ClearPostDatedChequeDialog(
        api: widget.api,
        issued: widget.issued,
        cheque: row,
      ),
    );
    if (saved == null || !mounted) return;
    _tell('Cheque ${row.chequeNumber} — cleared.', AppNotificationKind.success);
    await _load();
  }

  Future<void> _bounce(PostDatedCheque row) async {
    final PostDatedCheque? saved = await showDialog<PostDatedCheque>(
      context: context,
      barrierDismissible: false,
      builder: (_) => BouncePostDatedChequeDialog(
        api: widget.api,
        issued: widget.issued,
        cheque: row,
      ),
    );
    if (saved == null || !mounted) return;
    _tell(
      'Cheque ${row.chequeNumber} — '
      '${widget.issued ? 'returned' : 'bounced'}.',
      AppNotificationKind.success,
    );
    await _load();
  }

  /// A cancel is explained afterwards, so it asks why first.
  Future<void> _cancel(PostDatedCheque row) async {
    final String? reason = await askForReason(
      context,
      title: 'Cancel cheque ${row.chequeNumber}',
      explanation: 'The cheque is taken off the register without being '
          'banked. The reason is kept on it.',
      confirmLabel: 'Cancel cheque',
      cancelLabel: 'Keep it',
    );
    if (reason == null || !mounted) return;
    try {
      await widget.api.cancelPostDatedCheque(
        issued: widget.issued,
        id: row.id,
        reason: reason,
        expectedVersion: row.version,
      );
      if (!mounted) return;
      _tell('Cheque ${row.chequeNumber} — cancelled.',
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
        message: 'Post-dated cheques belong to one firm’s books.',
      );
    }
    if (!_mayView) {
      return WorkspaceEmptyState(
        icon: Icons.lock_outline,
        title: 'You cannot see post-dated cheques',
        message: widget.issued
            ? 'Reading them needs the view payments permission.'
            : 'Reading them needs the view receipts permission.',
      );
    }
    final PostDatedCheque? picked = _selected;
    return ManagementWorkspaceLayout(
      notice: widget.issued
          ? 'Cheques you have given suppliers, dated ahead. Present one on '
              'its day and the payment is recorded; mark it cleared when '
              'the bank has paid it.'
          : 'Cheques customers have given you, dated ahead. Deposit one on '
              'its day and the receipt is recorded; mark it cleared when '
              'the bank has paid it, or bounced if it comes back.',
      toolbar: _toolbar(picked),
      searchPanel: SearchFilterPanel(
        controller: _search,
        hintText: 'Search cheque number',
        onSearch: (_) => unawaited(_load()),
      ),
      selectionBar: true,
      selection: picked == null
          ? null
          : SelectionSummary.document(
              number: picked.chequeNumber,
              party: picked.partyLabel,
              status: picked.status,
              total: picked.amount,
              onClear: () => setState(() => _selectedId = null),
            ),
      primaryContent: _content(picked),
      statusBar: WorkspaceStatusBar(
        total: _rows.length,
        selected: _selectedId != null,
        message: _noun,
      ),
    );
  }

  Widget _content(PostDatedCheque? picked) {
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
        if (picked != null) _detail(picked),
      ],
    );
  }

  /// What happened to the selected cheque, in the order it happened.
  Widget _detail(PostDatedCheque cheque) {
    final String banked = widget.issued ? 'Presented' : 'Deposited';
    final String returned = widget.issued ? 'Returned' : 'Bounced';
    final List<String> lines = [
      'Dated ${cheque.chequeDate}, taken on ${cheque.receivedOn}',
      if (cheque.depositedOn.isNotEmpty)
        '$banked ${cheque.depositedOn}'
            '${cheque.settlementNumber.isEmpty ? '' : ' as ${cheque.settlementNumber}'}',
      if (cheque.clearedOn.isNotEmpty) 'Cleared ${cheque.clearedOn}',
      if (cheque.bouncedOn.isNotEmpty)
        '$returned ${cheque.bouncedOn}: ${cheque.bounceReason}',
      if (cheque.cancelReason.isNotEmpty) 'Cancelled: ${cheque.cancelReason}',
      if (cheque.narration.isNotEmpty) cheque.narration,
    ];
    return Container(
      key: const ValueKey('pdc-detail'),
      margin: const EdgeInsets.only(top: AppSpacing.sm),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          for (final String line in lines)
            Text(line, style: Theme.of(context).textTheme.bodySmall),
        ],
      ),
    );
  }

  WorkspaceToolbar _toolbar(PostDatedCheque? selected) {
    final bool held = selected != null && selected.isHeld && _mayWrite;
    final bool banked = selected != null && selected.isDeposited && _mayWrite;
    return WorkspaceToolbar(
      trailing: [
        // One menu, because "due to deposit" is a held cheque whose day has
        // come: it is a view of the register, not a second filter.
        Phase2MenuChip<String>(
          key: const ValueKey('pdc-status-filter'),
          label: _dueOnly
              ? 'Show: Due to deposit'
              : _status == null
                  ? 'Show: All'
                  : 'Show: ${_words(_status!)}',
          itemBuilder: (_) => [
            const PopupMenuItem<String>(value: '', child: Text('All')),
            PopupMenuItem<String>(
              key: const ValueKey('pdc-due-filter'),
              value: 'DUE',
              child: Text(widget.issued ? 'Due to present' : 'Due to deposit'),
            ),
            for (final String status in _statuses)
              PopupMenuItem<String>(value: status, child: Text(_words(status))),
          ],
          onSelected: (value) {
            setState(() {
              _dueOnly = value == 'DUE';
              _status = value.isEmpty || _dueOnly ? null : value;
            });
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
        if (_mayWrite) ...[
          ToolbarCommand(
            id: 'deposit',
            label: _depositWord,
            icon: Icons.account_balance_outlined,
            onPressed: held ? () => unawaited(_deposit(selected)) : null,
          ),
          ToolbarCommand(
            id: 'mark-cleared',
            label: 'Clear',
            icon: Icons.check_circle_outline,
            onPressed: banked ? () => unawaited(_clear(selected)) : null,
          ),
          ToolbarCommand(
            id: 'bounce',
            label: _bounceWord,
            icon: Icons.undo,
            onPressed: banked ? () => unawaited(_bounce(selected)) : null,
          ),
          ToolbarCommand(
            id: 'cancel',
            label: 'Cancel',
            icon: Icons.cancel_outlined,
            onPressed: held ? () => unawaited(_cancel(selected)) : null,
          ),
        ],
      ],
    );
  }

  late final ColumnChoice<PostDatedCheque> _columns = ColumnChoice(
    preferences: widget.preferences,
    stateKey: widget.issued ? 'pdc-issued.grid' : 'pdc-received.grid',
    columns: [
      ChoosableColumn(
        column: const GridColumn(key: 'date', label: 'Cheque date'),
        cell: (item) => item.chequeDate,
        required: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'number', label: 'Cheque no.'),
        cell: (item) => item.chequeNumber,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: GridColumn(
            key: 'party', label: widget.issued ? 'Supplier' : 'Customer'),
        cell: (item) => item.partyName,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'bank', label: 'Bank', priority: 1),
        cell: (item) => item.drawnOnBank,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'amount', label: 'Amount', numeric: true),
        cell: (item) => _money(item.amount),
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'status', label: 'Status'),
        cell: (item) => _words(item.status),
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'due', label: 'Due'),
        cell: (item) => item.isDue ? 'Due' : '',
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: GridColumn(
            key: 'settlement',
            label: widget.issued ? 'Payment' : 'Receipt',
            priority: 1),
        cell: (item) => item.settlementNumber,
        shownByDefault: true,
      ),
    ],
  );

  Widget _grid() {
    if (_rows.isEmpty) {
      return WorkspaceEmptyState(
        title: _dueOnly ? 'Nothing is due today' : 'No cheques yet',
        message: _mayWrite
            ? 'Record a cheque that is dated ahead; it is held until its day.'
            : 'Recording one needs the create permission for '
                '${widget.issued ? 'payments' : 'receipts'}.',
      );
    }
    return EnterpriseDataGrid<PostDatedCheque>(
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
      onOpen: (row) => setState(() => _selectedId = row.id),
      onPageChanged: (_) {},
    );
  }
}

/// Show money at two decimals; the API answers at more.
String _money(String value) {
  final double? parsed = double.tryParse(value);
  return parsed == null ? value : parsed.toStringAsFixed(2);
}

String _iso(DateTime date) => date.toIso8601String().substring(0, 10);

/// `HELD` as `Held`.
String _words(String status) => status.isEmpty
    ? status
    : status[0] + status.substring(1).toLowerCase();

DateTime? _parseDate(String value) =>
    value.length >= 10 ? DateTime.tryParse(value.substring(0, 10)) : null;

/// A date field that opens a picker.
class _DateField extends StatelessWidget {
  const _DateField({
    super.key,
    required this.label,
    required this.value,
    required this.onChanged,
    this.enabled = true,
    this.firstDate,
  });

  final String label;
  final DateTime value;
  final ValueChanged<DateTime> onChanged;
  final bool enabled;
  final DateTime? firstDate;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: !enabled
          ? null
          : () async {
              final DateTime? picked = await showDatePicker(
                context: context,
                initialDate: value,
                firstDate: firstDate ?? DateTime(2000),
                lastDate: DateTime(2100),
              );
              if (picked != null) onChanged(picked);
            },
      child: InputDecorator(
        decoration: InputDecoration(labelText: label),
        child: Text(_iso(value)),
      ),
    );
  }
}

/// Take a cheque in. Pops the saved [PostDatedCheque]; stays open with the
/// server's message when it is refused.
class NewPostDatedChequeDialog extends StatefulWidget {
  const NewPostDatedChequeDialog({
    super.key,
    required this.api,
    required this.issued,
  });

  final ApiClient api;
  final bool issued;

  @override
  State<NewPostDatedChequeDialog> createState() =>
      _NewPostDatedChequeDialogState();
}

class _NewPostDatedChequeDialogState extends State<NewPostDatedChequeDialog>
    with SaveInDialog {
  final TextEditingController _number = TextEditingController();
  final TextEditingController _bank = TextEditingController();
  final TextEditingController _amount = TextEditingController();
  final TextEditingController _narration = TextEditingController();
  DateTime _chequeDate = DateTime.now().add(const Duration(days: 30));
  DateTime _takenOn = DateTime.now();
  List<PartyOption> _parties = const [];
  PartyOption? _party;
  bool _loading = true;
  String? _problem;

  @override
  void initState() {
    super.initState();
    unawaited(_readParties());
  }

  @override
  void dispose() {
    _number.dispose();
    _bank.dispose();
    _amount.dispose();
    _narration.dispose();
    super.dispose();
  }

  Future<void> _readParties() async {
    try {
      final List<PartyOption> parties = await widget.api.settlementParties(
        direction: widget.issued
            ? SettlementDirection.payment
            : SettlementDirection.receipt,
      );
      if (!mounted) return;
      setState(() {
        _parties = parties;
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
    final String number = _number.text.trim();
    final String amount = _amount.text.trim();
    final double? value = double.tryParse(amount);
    String? problem;
    if (_party == null) {
      problem = widget.issued
          ? 'Choose the supplier the cheque is given to.'
          : 'Choose the customer who gave the cheque.';
    } else if (number.isEmpty || number.length > 30) {
      problem = 'The cheque number is one to thirty characters.';
    } else if (value == null || value <= 0) {
      problem = 'The amount must be more than zero.';
    }
    setState(() => _problem = problem);
    if (problem != null) return;
    final String bank = _bank.text.trim();
    final String narration = _narration.text.trim();
    unawaited(saveAndClose<PostDatedCheque>(
      () => widget.api.createPostDatedCheque(
        issued: widget.issued,
        body: <String, dynamic>{
          'party_id': _party!.id,
          'cheque_number': number,
          'cheque_date': _iso(_chequeDate),
          if (bank.isNotEmpty) 'drawn_on_bank': bank,
          'amount': amount,
          'received_on': _iso(_takenOn),
          if (narration.isNotEmpty) 'narration': narration,
        },
      ),
    ));
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text(widget.issued ? 'New issued cheque' : 'New cheque received'),
      content: SizedBox(
        width: 560,
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
                          key: const ValueKey('pdc-problem'),
                          style: TextStyle(
                              color: Theme.of(context).colorScheme.error),
                        ),
                      ),
                    Autocomplete<PartyOption>(
                      displayStringForOption: (party) => party.label,
                      optionsBuilder: (value) {
                        final String query = value.text.trim().toLowerCase();
                        return _parties.where((party) =>
                            party.code.toLowerCase().contains(query) ||
                            party.name.toLowerCase().contains(query));
                      },
                      onSelected: (party) => setState(() => _party = party),
                      fieldViewBuilder: (context, field, node, submit) =>
                          TextFormField(
                        key: const ValueKey('pdc-party'),
                        controller: field,
                        focusNode: node,
                        enabled: !saving,
                        onChanged: (_) {
                          if (_party != null) setState(() => _party = null);
                        },
                        decoration: InputDecoration(
                          labelText:
                              widget.issued ? 'Paid to' : 'Received from',
                          helperText:
                              'Type a code or a name to narrow the list.',
                          prefixIcon: const Icon(Icons.search),
                        ),
                      ),
                    ),
                    const SizedBox(height: AppSpacing.md),
                    Row(children: [
                      Expanded(
                        child: TextField(
                          key: const ValueKey('pdc-number'),
                          controller: _number,
                          enabled: !saving,
                          decoration:
                              const InputDecoration(labelText: 'Cheque number'),
                        ),
                      ),
                      const SizedBox(width: AppSpacing.md),
                      Expanded(
                        child: TextField(
                          key: const ValueKey('pdc-amount'),
                          controller: _amount,
                          enabled: !saving,
                          keyboardType: const TextInputType.numberWithOptions(
                              decimal: true),
                          decoration:
                              const InputDecoration(labelText: 'Amount'),
                        ),
                      ),
                    ]),
                    const SizedBox(height: AppSpacing.md),
                    Row(children: [
                      Expanded(
                        child: _DateField(
                          key: const ValueKey('pdc-cheque-date'),
                          label: 'Cheque date',
                          value: _chequeDate,
                          enabled: !saving,
                          onChanged: (date) =>
                              setState(() => _chequeDate = date),
                        ),
                      ),
                      const SizedBox(width: AppSpacing.md),
                      Expanded(
                        child: _DateField(
                          key: const ValueKey('pdc-taken-date'),
                          label: widget.issued ? 'Given on' : 'Received on',
                          value: _takenOn,
                          enabled: !saving,
                          onChanged: (date) => setState(() => _takenOn = date),
                        ),
                      ),
                    ]),
                    const SizedBox(height: AppSpacing.md),
                    TextField(
                      key: const ValueKey('pdc-bank'),
                      controller: _bank,
                      enabled: !saving,
                      decoration: InputDecoration(
                        labelText: widget.issued
                            ? 'Drawn on (our bank)'
                            : 'Drawn on (customer’s bank)',
                      ),
                    ),
                    const SizedBox(height: AppSpacing.md),
                    TextField(
                      key: const ValueKey('pdc-narration'),
                      controller: _narration,
                      enabled: !saving,
                      decoration: const InputDecoration(labelText: 'Narration'),
                    ),
                  ],
                ),
              ),
      ),
      actions: [
        TextButton(onPressed: cancelHandler, child: const Text('Cancel')),
        FilledButton(
          key: const ValueKey('pdc-save'),
          onPressed: saving || _loading ? null : _save,
          child: Text(saving ? 'Saving…' : 'Hold cheque'),
        ),
      ],
    );
  }
}

/// Bank a held cheque. The server raises the receipt or payment; with no
/// invoices named the money stays on account.
class DepositPostDatedChequeDialog extends StatefulWidget {
  const DepositPostDatedChequeDialog({
    super.key,
    required this.api,
    required this.issued,
    required this.cheque,
  });

  final ApiClient api;
  final bool issued;
  final PostDatedCheque cheque;

  @override
  State<DepositPostDatedChequeDialog> createState() =>
      _DepositPostDatedChequeDialogState();
}

class _DepositPostDatedChequeDialogState
    extends State<DepositPostDatedChequeDialog> with SaveInDialog {
  late DateTime _date = _initialDate();

  /// Today, but never before the day on the cheque.
  DateTime _initialDate() {
    final DateTime today = DateTime.now();
    final DateTime? dated = _parseDate(widget.cheque.chequeDate);
    return dated != null && dated.isAfter(today) ? dated : today;
  }

  @override
  Widget build(BuildContext context) {
    final String verb = widget.issued ? 'Present' : 'Deposit';
    final String record = widget.issued ? 'payment' : 'receipt';
    return AlertDialog(
      title: Text('$verb cheque ${widget.cheque.chequeNumber}'),
      content: SizedBox(
        width: 460,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            saveErrorBanner(),
            _DateField(
              key: const ValueKey('pdc-deposit-date'),
              label: widget.issued ? 'Presented on' : 'Deposited on',
              value: _date,
              enabled: !saving,
              firstDate: _parseDate(widget.cheque.chequeDate),
              onChanged: (date) => setState(() => _date = date),
            ),
            const SizedBox(height: AppSpacing.md),
            Text(
              'This records a $record of ${_money(widget.cheque.amount)} '
              'with ${widget.cheque.partyName}. It is not set against any '
              'invoice, so the money stays on account until you apply it. '
              'The date cannot be before the cheque’s own date, '
              '${widget.cheque.chequeDate}.',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ],
        ),
      ),
      actions: [
        TextButton(onPressed: cancelHandler, child: const Text('Cancel')),
        FilledButton(
          key: const ValueKey('pdc-deposit-save'),
          onPressed: saving
              ? null
              : () => unawaited(saveAndClose<PostDatedCheque>(
                    () => widget.api.depositPostDatedCheque(
                      issued: widget.issued,
                      id: widget.cheque.id,
                      expectedVersion: widget.cheque.version,
                      body: <String, dynamic>{
                        'deposited_on': _iso(_date),
                        'allocations': <Map<String, dynamic>>[],
                      },
                    ),
                  )),
          child: Text(saving ? 'Saving…' : verb),
        ),
      ],
    );
  }
}

/// Mark a banked cheque as paid by the bank.
class ClearPostDatedChequeDialog extends StatefulWidget {
  const ClearPostDatedChequeDialog({
    super.key,
    required this.api,
    required this.issued,
    required this.cheque,
  });

  final ApiClient api;
  final bool issued;
  final PostDatedCheque cheque;

  @override
  State<ClearPostDatedChequeDialog> createState() =>
      _ClearPostDatedChequeDialogState();
}

class _ClearPostDatedChequeDialogState extends State<ClearPostDatedChequeDialog>
    with SaveInDialog {
  DateTime _date = DateTime.now();

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text('Clear cheque ${widget.cheque.chequeNumber}'),
      content: SizedBox(
        width: 420,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            saveErrorBanner(),
            _DateField(
              key: const ValueKey('pdc-clear-date'),
              label: 'Cleared on',
              value: _date,
              enabled: !saving,
              onChanged: (date) => setState(() => _date = date),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(onPressed: cancelHandler, child: const Text('Cancel')),
        FilledButton(
          key: const ValueKey('pdc-clear-save'),
          onPressed: saving
              ? null
              : () => unawaited(saveAndClose<PostDatedCheque>(
                    () => widget.api.clearPostDatedCheque(
                      issued: widget.issued,
                      id: widget.cheque.id,
                      expectedVersion: widget.cheque.version,
                      body: <String, dynamic>{'cleared_on': _iso(_date)},
                    ),
                  )),
          child: Text(saving ? 'Saving…' : 'Clear'),
        ),
      ],
    );
  }
}

/// A banked cheque that came back. Reverses what banking raised.
class BouncePostDatedChequeDialog extends StatefulWidget {
  const BouncePostDatedChequeDialog({
    super.key,
    required this.api,
    required this.issued,
    required this.cheque,
  });

  final ApiClient api;
  final bool issued;
  final PostDatedCheque cheque;

  @override
  State<BouncePostDatedChequeDialog> createState() =>
      _BouncePostDatedChequeDialogState();
}

class _BouncePostDatedChequeDialogState
    extends State<BouncePostDatedChequeDialog> with SaveInDialog {
  final TextEditingController _reason = TextEditingController();
  final TextEditingController _bankCharges = TextEditingController();
  final TextEditingController _customerCharge = TextEditingController();
  DateTime _date = DateTime.now();
  String? _problem;

  @override
  void dispose() {
    _reason.dispose();
    _bankCharges.dispose();
    _customerCharge.dispose();
    super.dispose();
  }

  bool _badNumber(String text) =>
      text.isNotEmpty && (double.tryParse(text) ?? -1) < 0;

  void _save() {
    final String reason = _reason.text.trim();
    final String bank = _bankCharges.text.trim();
    final String customer = _customerCharge.text.trim();
    String? problem;
    if (reason.isEmpty) {
      problem = 'Say why the cheque came back.';
    } else if (_badNumber(bank)) {
      problem = 'The bank charges must be a number.';
    } else if (!widget.issued && _badNumber(customer)) {
      problem = 'The charge to the customer must be a number.';
    }
    setState(() => _problem = problem);
    if (problem != null) return;
    unawaited(saveAndClose<PostDatedCheque>(
      () => widget.api.bouncePostDatedCheque(
        issued: widget.issued,
        id: widget.cheque.id,
        expectedVersion: widget.cheque.version,
        body: <String, dynamic>{
          'bounced_on': _iso(_date),
          'reason': reason,
          if (bank.isNotEmpty) 'bank_charges_amount': bank,
          if (!widget.issued && customer.isNotEmpty)
            'customer_charge_amount': customer,
        },
      ),
    ));
  }

  @override
  Widget build(BuildContext context) {
    final String record = widget.issued ? 'payment' : 'receipt';
    final String number = widget.cheque.settlementNumber;
    return AlertDialog(
      title: Text(
        '${widget.issued ? 'Cheque returned' : 'Cheque bounced'}: '
        '${widget.cheque.chequeNumber}',
      ),
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
                    key: const ValueKey('pdc-problem'),
                    style:
                        TextStyle(color: Theme.of(context).colorScheme.error),
                  ),
                ),
              Text(
                'The $record${number.isEmpty ? '' : ' $number'} is reversed, '
                'so ${widget.issued ? 'the supplier is owed' : 'the customer owes'} '
                'the money again.',
                style: Theme.of(context).textTheme.bodySmall,
              ),
              const SizedBox(height: AppSpacing.md),
              _DateField(
                key: const ValueKey('pdc-bounce-date'),
                label: widget.issued ? 'Returned on' : 'Bounced on',
                value: _date,
                enabled: !saving,
                onChanged: (date) => setState(() => _date = date),
              ),
              const SizedBox(height: AppSpacing.md),
              TextField(
                key: const ValueKey('pdc-bounce-reason'),
                controller: _reason,
                enabled: !saving,
                decoration: const InputDecoration(labelText: 'Reason'),
              ),
              const SizedBox(height: AppSpacing.md),
              TextField(
                key: const ValueKey('pdc-bank-charges'),
                controller: _bankCharges,
                enabled: !saving,
                keyboardType:
                    const TextInputType.numberWithOptions(decimal: true),
                decoration: const InputDecoration(
                  labelText: 'Bank charges',
                  helperText: 'What the bank took for the return, if anything.',
                ),
              ),
              if (!widget.issued) ...[
                const SizedBox(height: AppSpacing.md),
                TextField(
                  key: const ValueKey('pdc-customer-charge'),
                  controller: _customerCharge,
                  enabled: !saving,
                  keyboardType:
                      const TextInputType.numberWithOptions(decimal: true),
                  decoration: const InputDecoration(
                    labelText: 'Charge to the customer',
                    helperText: 'Added to what the customer owes, if any.',
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
      actions: [
        TextButton(onPressed: cancelHandler, child: const Text('Cancel')),
        FilledButton(
          key: const ValueKey('pdc-bounce-save'),
          onPressed: saving ? null : _save,
          child: Text(saving ? 'Saving…' : 'Record'),
        ),
      ],
    );
  }
}
