// Firm bank details printed on bills (ACC-4).
//
// The firm keeps bank particulars against its asset ledger accounts; the one
// marked "Print on bills" prints its bank, number and IFSC on the bill, and
// its UPI ID as a pay-by-scan code. Phase 2 only.

import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/preferences/desktop_preferences_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/bank_account_details.dart';
import '../../models/entities.dart';
import '../../models/finance.dart';
import '../workspace/desktop_framework.dart';

/// The words on the screen's notice, behind the page line's (i).
const String _notice =
    'Keep the firm’s bank particulars here. The account marked Print on '
    'bills appears on the firm’s bills with its bank, number and IFSC, '
    'and its UPI ID as a pay-by-scan code, unless the print template has its '
    'own bank text. Only one account is printed; marking another moves it.';

const String _printHelp =
    'Bills print this account’s bank, number and IFSC, and its UPI ID as '
    'a pay-by-scan code, unless the print template has its own bank text.';

const Map<String, String> _kinds = <String, String>{
  'CURRENT': 'Current',
  'SAVINGS': 'Savings',
  'CASH_CREDIT': 'Cash credit',
  'OVERDRAFT': 'Overdraft',
};

/// List the firm's bank details; add, change or remove them.
class BankDetailsPage extends StatefulWidget {
  const BankDetailsPage({
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
  State<BankDetailsPage> createState() => _BankDetailsPageState();
}

class _BankDetailsPageState extends State<BankDetailsPage> {
  List<BankAccountDetails> _rows = const [];
  String? _error;
  String? _selectedId;
  bool _loading = true;

  final TextEditingController _search = TextEditingController();

  bool get _mayView =>
      widget.permissions.hasPermission('ACCOUNT_VIEW') ||
      widget.permissions.hasPermission('PAYMENT_CREATE');
  bool get _mayManage => widget.permissions.hasPermission('ACCOUNT_MANAGE');

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

  List<BankAccountDetails> get _shown {
    final String query = _search.text.trim().toLowerCase();
    if (query.isEmpty) return _rows;
    return _rows
        .where((row) =>
            row.bankName.toLowerCase().contains(query) ||
            row.ledgerAccountName.toLowerCase().contains(query) ||
            row.ledgerAccountCode.toLowerCase().contains(query) ||
            row.ifsc.toLowerCase().contains(query) ||
            row.accountNumber.toLowerCase().contains(query))
        .toList();
  }

  BankAccountDetails? get _selected =>
      _rows.where((row) => row.id == _selectedId).firstOrNull;

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final List<BankAccountDetails> rows = await widget.api.listBankDetails();
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

  Future<void> _open({BankAccountDetails? existing}) async {
    final BankAccountDetails? saved = await showDialog<BankAccountDetails>(
      context: context,
      barrierDismissible: false,
      builder: (_) => BankDetailsDialog(
        api: widget.api,
        existing: existing,
        kept: {for (final row in _rows) row.ledgerAccountId},
      ),
    );
    if (saved == null || !mounted) return;
    setState(() => _selectedId = saved.id);
    NotificationService.show(
      context,
      '${saved.bankName} — saved.',
      kind: AppNotificationKind.success,
    );
    await _load();
  }

  Future<void> _remove(BankAccountDetails row) async {
    final bool? yes = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('Remove ${row.bankName} details'),
        content: Text(
          'The bank particulars kept for ${row.ledgerAccountName} are '
          'removed and no longer print on bills. The ledger account stays.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Keep them'),
          ),
          FilledButton(
            key: const ValueKey('bank-details-remove-confirm'),
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Remove'),
          ),
        ],
      ),
    );
    if (yes != true || !mounted) return;
    try {
      await widget.api.removeBankDetails(row.ledgerAccountId);
      if (!mounted) return;
      setState(() => _selectedId = null);
      NotificationService.show(
        context,
        '${row.bankName} — removed.',
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
        message: 'Bank details belong to one firm’s books.',
      );
    }
    if (!_mayView) {
      return const WorkspaceEmptyState(
        icon: Icons.lock_outline,
        title: 'You cannot see bank details',
        message: 'Reading them needs the view accounts permission.',
      );
    }
    final BankAccountDetails? picked = _selected;
    return ManagementWorkspaceLayout(
      notice: _notice,
      toolbar: _toolbar(picked),
      searchPanel: SearchFilterPanel(
        controller: _search,
        hintText: 'Search bank, account, number or IFSC',
        onSearch: (_) => setState(() {}),
      ),
      selectionBar: true,
      selection: picked == null
          ? null
          : SelectionSummary.document(
              number: picked.bankName,
              party: '${picked.ledgerAccountCode} · '
                  '${picked.ledgerAccountName}',
              status: picked.printOnDocuments ? 'Printed on bills' : 'Kept',
              total: picked.accountNumber,
              onClear: () => setState(() => _selectedId = null),
            ),
      primaryContent: _content(),
      statusBar: WorkspaceStatusBar(
        total: _rows.length,
        selected: _selectedId != null,
        message: 'One account prints on bills.',
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

  WorkspaceToolbar _toolbar(BankAccountDetails? selected) {
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
        if (_mayManage) ...[
          ToolbarAction.newItem,
          ToolbarAction.edit,
          ToolbarAction.delete,
        ],
      ],
      newLabel: '+ Add',
      isEnabled: (action) => switch (action) {
        ToolbarAction.edit || ToolbarAction.delete => selected != null,
        _ => true,
      },
      onAction: (action) {
        switch (action) {
          case ToolbarAction.newItem:
            unawaited(_open());
          case ToolbarAction.edit:
            if (selected != null) unawaited(_open(existing: selected));
          case ToolbarAction.delete:
            if (selected != null) unawaited(_remove(selected));
          default:
            unawaited(_load());
        }
      },
    );
  }

  late final ColumnChoice<BankAccountDetails> _columns = ColumnChoice(
    preferences: widget.preferences,
    stateKey: 'bank-details.grid',
    columns: [
      ChoosableColumn(
        column: const GridColumn(key: 'account', label: 'Ledger account'),
        cell: (item) => '${item.ledgerAccountCode} ${item.ledgerAccountName}',
        required: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'bank', label: 'Bank'),
        cell: (item) => item.bankName,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'number', label: 'Account number'),
        cell: (item) => item.accountNumber,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'ifsc', label: 'IFSC'),
        cell: (item) => item.ifsc,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'kind', label: 'Kind'),
        cell: (item) => _kinds[item.accountKind] ?? item.accountKind,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'branch', label: 'Branch', priority: 1),
        cell: (item) => item.branch,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'upi', label: 'UPI ID', priority: 1),
        cell: (item) => item.upiId,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'printed', label: 'On bills'),
        cell: (item) => item.printOnDocuments ? 'Printed on bills' : '',
        shownByDefault: true,
      ),
    ],
  );

  Widget _grid() {
    final List<BankAccountDetails> shown = _shown;
    if (shown.isEmpty) {
      return WorkspaceEmptyState(
        title: 'No bank details yet',
        message: _mayManage
            ? 'Add the bank particulars of an account and mark the one that '
                'prints on bills.'
            : 'Adding them needs the manage accounts permission.',
      );
    }
    return EnterpriseDataGrid<BankAccountDetails>(
      items: shown,
      total: shown.length,
      pageOffset: 0,
      rowsPerPage: shown.length,
      availableRowsPerPage: [shown.length],
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

/// Add or change one account's bank details. Pops the saved
/// [BankAccountDetails]; stays open with the server's message when refused.
class BankDetailsDialog extends StatefulWidget {
  const BankDetailsDialog({
    super.key,
    required this.api,
    this.existing,
    this.kept = const <String>{},
  });

  final ApiClient api;

  /// The row being changed; null adds details to another account.
  final BankAccountDetails? existing;

  /// Ledger accounts that already have details, left out of the picker.
  final Set<String> kept;

  @override
  State<BankDetailsDialog> createState() => _BankDetailsDialogState();
}

class _BankDetailsDialogState extends State<BankDetailsDialog>
    with SaveInDialog {
  late final TextEditingController _bank;
  late final TextEditingController _holder;
  late final TextEditingController _number;
  late final TextEditingController _ifsc;
  late final TextEditingController _branch;
  late final TextEditingController _swift;
  late final TextEditingController _upi;
  String? _kind;
  String? _accountId;
  bool _print = false;
  List<LedgerAccount> _accounts = const [];
  bool _loading = true;
  String? _problem;

  bool get _editing => widget.existing != null;

  @override
  void initState() {
    super.initState();
    final BankAccountDetails? row = widget.existing;
    _bank = TextEditingController(text: row?.bankName ?? '');
    _holder = TextEditingController(text: row?.accountName ?? '');
    // A masked number is never sent back, so it is retyped rather than shown.
    _number = TextEditingController(
        text: row == null || row.masked ? '' : row.accountNumber);
    _ifsc = TextEditingController(text: row?.ifsc ?? '');
    _branch = TextEditingController(text: row?.branch ?? '');
    _swift = TextEditingController(text: row?.swiftCode ?? '');
    _upi = TextEditingController(text: row?.upiId ?? '');
    _kind = row == null || row.accountKind.isEmpty ? null : row.accountKind;
    _accountId = row?.ledgerAccountId;
    _print = row?.printOnDocuments ?? false;
    if (_editing) {
      _loading = false;
    } else {
      unawaited(_readAccounts());
    }
  }

  @override
  void dispose() {
    _bank.dispose();
    _holder.dispose();
    _number.dispose();
    _ifsc.dispose();
    _branch.dispose();
    _swift.dispose();
    _upi.dispose();
    super.dispose();
  }

  Future<void> _readAccounts() async {
    try {
      final PagedResult<LedgerAccount> result =
          await widget.api.ledgerAccounts(isActive: true);
      if (!mounted) return;
      setState(() {
        _accounts = result.items
            .where((account) =>
                account.accountType == 'ASSET' &&
                !widget.kept.contains(account.id))
            .toList();
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
    final String bank = _bank.text.trim();
    final String holder = _holder.text.trim();
    final String number = _number.text.trim();
    final String ifsc = _ifsc.text.trim().toUpperCase();
    final bool wasMasked = widget.existing?.masked ?? false;
    String? problem;
    if (_accountId == null) {
      problem = 'Choose the ledger account these details belong to.';
    } else if (bank.isEmpty) {
      problem = 'Enter the bank’s name.';
    } else if (holder.isEmpty) {
      problem = 'Enter the account holder’s name.';
    } else if (number.isEmpty) {
      problem = wasMasked
          ? 'Retype the full account number; the screen only knows its '
              'last four digits.'
          : 'Enter the account number.';
    } else if (ifsc.isNotEmpty &&
        !RegExp(r'^[A-Z]{4}0[A-Z0-9]{6}$').hasMatch(ifsc)) {
      problem = 'An IFSC is eleven characters, like HDFC0001234.';
    }
    setState(() => _problem = problem);
    if (problem != null) return;
    final String id = _accountId!;
    unawaited(saveAndClose<BankAccountDetails>(
      () => widget.api.saveBankDetails(
        id,
        bankDetailsWriteJson(
          bankName: bank,
          accountName: holder,
          accountNumber: number,
          ifsc: ifsc,
          branch: _branch.text,
          accountKind: _kind,
          swiftCode: _swift.text,
          upiId: _upi.text,
          printOnDocuments: _print,
        ),
      ),
    ));
  }

  Widget _accountField() {
    final BankAccountDetails? row = widget.existing;
    if (row != null) {
      return InputDecorator(
        key: const ValueKey('bank-details-account-fixed'),
        decoration: const InputDecoration(labelText: 'Ledger account'),
        child: Text('${row.ledgerAccountCode}  ${row.ledgerAccountName}'),
      );
    }
    return DropdownButtonFormField<String>(
      key: const ValueKey('bank-details-account'),
      initialValue: _accountId,
      isExpanded: true,
      decoration: const InputDecoration(
        labelText: 'Ledger account',
        helperText: 'Only asset accounts, such as a bank account.',
      ),
      items: [
        for (final LedgerAccount account in _accounts)
          DropdownMenuItem<String>(
            value: account.id,
            child: Text('${account.code}  ${account.name}',
                overflow: TextOverflow.ellipsis),
          ),
      ],
      onChanged: saving ? null : (value) => setState(() => _accountId = value),
    );
  }

  @override
  Widget build(BuildContext context) {
    final bool masked = widget.existing?.masked ?? false;
    return AlertDialog(
      title: Text(_editing ? 'Change bank details' : 'Add bank details'),
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
                          key: const ValueKey('bank-details-problem'),
                          style: TextStyle(
                              color: Theme.of(context).colorScheme.error),
                        ),
                      ),
                    _accountField(),
                    const SizedBox(height: AppSpacing.md),
                    Row(children: [
                      Expanded(
                        child: TextField(
                          key: const ValueKey('bank-details-bank'),
                          controller: _bank,
                          decoration:
                              const InputDecoration(labelText: 'Bank name'),
                        ),
                      ),
                      const SizedBox(width: AppSpacing.md),
                      Expanded(
                        child: TextField(
                          key: const ValueKey('bank-details-holder'),
                          controller: _holder,
                          decoration: const InputDecoration(
                              labelText: 'Account holder'),
                        ),
                      ),
                    ]),
                    const SizedBox(height: AppSpacing.md),
                    Row(children: [
                      Expanded(
                        child: TextField(
                          key: const ValueKey('bank-details-number'),
                          controller: _number,
                          decoration: InputDecoration(
                            labelText: 'Account number',
                            helperText: masked
                                ? 'Retype the full number to save.'
                                : null,
                          ),
                        ),
                      ),
                      const SizedBox(width: AppSpacing.md),
                      Expanded(
                        child: TextField(
                          key: const ValueKey('bank-details-ifsc'),
                          controller: _ifsc,
                          textCapitalization: TextCapitalization.characters,
                          decoration: const InputDecoration(
                            labelText: 'IFSC',
                            helperText: 'Eleven characters, HDFC0001234',
                          ),
                        ),
                      ),
                    ]),
                    const SizedBox(height: AppSpacing.md),
                    Row(children: [
                      Expanded(
                        child: TextField(
                          key: const ValueKey('bank-details-branch'),
                          controller: _branch,
                          decoration:
                              const InputDecoration(labelText: 'Branch'),
                        ),
                      ),
                      const SizedBox(width: AppSpacing.md),
                      Expanded(
                        child: DropdownButtonFormField<String?>(
                          key: const ValueKey('bank-details-kind'),
                          initialValue: _kind,
                          isExpanded: true,
                          decoration:
                              const InputDecoration(labelText: 'Account kind'),
                          items: [
                            const DropdownMenuItem<String?>(
                              value: null,
                              child: Text('Not recorded'),
                            ),
                            for (final MapEntry<String, String> kind
                                in _kinds.entries)
                              DropdownMenuItem<String?>(
                                value: kind.key,
                                child: Text(kind.value),
                              ),
                          ],
                          onChanged: saving
                              ? null
                              : (value) => setState(() => _kind = value),
                        ),
                      ),
                    ]),
                    const SizedBox(height: AppSpacing.md),
                    Row(children: [
                      Expanded(
                        child: TextField(
                          key: const ValueKey('bank-details-swift'),
                          controller: _swift,
                          decoration:
                              const InputDecoration(labelText: 'SWIFT code'),
                        ),
                      ),
                      const SizedBox(width: AppSpacing.md),
                      Expanded(
                        child: TextField(
                          key: const ValueKey('bank-details-upi'),
                          controller: _upi,
                          decoration: const InputDecoration(
                              labelText: 'UPI ID',
                              helperText: 'Printed as a pay-by-scan code'),
                        ),
                      ),
                    ]),
                    const SizedBox(height: AppSpacing.sm),
                    CheckboxListTile(
                      key: const ValueKey('bank-details-print'),
                      contentPadding: EdgeInsets.zero,
                      controlAffinity: ListTileControlAffinity.leading,
                      value: _print,
                      title: const Text('Print on bills'),
                      subtitle: const Text(_printHelp),
                      onChanged: saving
                          ? null
                          : (value) => setState(() => _print = value ?? false),
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
          key: const ValueKey('bank-details-save'),
          onPressed: saving || _loading ? null : _save,
          child: Text(saving ? 'Saving…' : 'Save'),
        ),
      ],
    );
  }
}
