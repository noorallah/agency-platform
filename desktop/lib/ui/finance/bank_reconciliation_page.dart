// Bank reconciliation: tie the bank's statement to the books (ACC-1).
//
// Import a statement, let the matcher pair what is unambiguous, match the rest
// by hand (one statement line to one or more book entries that add up to it
// exactly), and read the reconciliation statement as on a date. Phase 2 only.

import 'dart:async';
import 'dart:io';

import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/preferences/desktop_preferences_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/bank_reconciliation.dart';
import '../../models/file_import.dart';
import '../workspace/desktop_framework.dart';
import 'statement_amount.dart';

/// The words on the screen's notice, behind the page line's (i).
const String _notice =
    'Import the bank’s statement, then match each line to the entries in the '
    'books it stands for. Pick one statement line and the entries that add up '
    'to it exactly; Match is offered only when they do. The reconciliation '
    'statement lists what still stands between the books and the bank.';

/// Match statement lines to book entries and read the reconciliation.
class BankReconciliationPage extends StatefulWidget {
  const BankReconciliationPage({
    super.key,
    required this.api,
    required this.preferences,
    required this.permissions,
    required this.hasActiveFirm,
    this.pickFileOverride,
    this.saveBytesOverride,
  });

  final ApiClient api;

  /// Kept for the screens beside this one, which remember their columns.
  final DesktopPreferencesService preferences;
  final PermissionService permissions;
  final bool hasActiveFirm;

  /// Injected by tests, which cannot open a native file or save dialog.
  final Future<XFile?> Function()? pickFileOverride;
  final SaveBytesOverride? saveBytesOverride;

  @override
  State<BankReconciliationPage> createState() => _BankReconciliationPageState();
}

enum _View { match, statement }

class _BankReconciliationPageState extends State<BankReconciliationPage> {
  List<ReconBankAccount> _accounts = const [];
  String? _accountId;
  List<BankStatement> _statements = const [];
  String? _statementId;

  /// `UNMATCHED`, `MATCHED`, or null for both.
  String? _status = 'UNMATCHED';
  List<BankStatementLine> _lines = const [];
  List<BookEntry> _entries = const [];
  String? _lineId;
  final Set<String> _picked = <String>{};

  _View _view = _View.match;
  DateTime _asOn = DateTime.now();
  BankReconciliationStatement? _brs;
  String? _brsError;

  bool _loading = true;
  bool _busy = false;
  String? _error;
  final TextEditingController _search = TextEditingController();

  bool get _mayView => widget.permissions.hasPermission('LEDGER_VIEW');
  bool get _mayPost => widget.permissions.hasPermission('JOURNAL_POST');

  @override
  void initState() {
    super.initState();
    if (widget.hasActiveFirm && _mayView) unawaited(_loadAccounts());
  }

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  void _tell(String message, AppNotificationKind kind) {
    if (!mounted) return;
    NotificationService.show(context, message, kind: kind);
  }

  Future<void> _loadAccounts() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final List<ReconBankAccount> accounts =
          await widget.api.bankReconciliationAccounts();
      if (!mounted) return;
      final bool keeps = accounts.any((a) => a.id == _accountId);
      setState(() {
        _accounts = accounts;
        if (!keeps) _accountId = accounts.isEmpty ? null : accounts.first.id;
      });
      await _loadAccount();
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.message;
        _loading = false;
      });
    }
  }

  /// Everything that depends on the chosen account, read afresh.
  Future<void> _loadAccount() async {
    final String? account = _accountId;
    if (account == null) {
      setState(() {
        _statements = const [];
        _lines = const [];
        _entries = const [];
        _loading = false;
      });
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final List<BankStatement> statements = await fetchAllPages<BankStatement>(
        (page) => widget.api
            .bankStatements(ledgerAccountId: account, page: page),
      );
      if (!mounted) return;
      if (!statements.any((s) => s.id == _statementId)) _statementId = null;
      final List<BankStatementLine> lines =
          await fetchAllPages<BankStatementLine>(
        (page) => widget.api.bankStatementLines(
          ledgerAccountId: account,
          statementId: _statementId,
          status: _status,
          page: page,
        ),
      );
      final List<BookEntry> entries = await fetchAllPages<BookEntry>(
        (page) =>
            widget.api.bankBookEntries(ledgerAccountId: account, page: page),
      );
      if (!mounted) return;
      setState(() {
        _statements = statements;
        _lines = lines;
        _entries = entries;
        if (!lines.any((l) => l.id == _lineId)) _lineId = null;
        _picked.removeWhere((id) => !entries.any((e) => e.glPostingId == id));
        _loading = false;
      });
      if (_view == _View.statement) unawaited(_loadBrs());
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.message;
        _loading = false;
      });
    }
  }

  Future<void> _loadBrs() async {
    final String? account = _accountId;
    if (account == null) return;
    try {
      final BankReconciliationStatement brs =
          await widget.api.bankReconciliationStatement(
        account,
        asOn: DatePeriod.iso(_asOn),
      );
      if (!mounted) return;
      setState(() {
        _brs = brs;
        _brsError = null;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _brs = null;
        _brsError = error.message;
      });
    }
  }

  BankStatementLine? get _line =>
      _lines.where((l) => l.id == _lineId).firstOrNull;

  double get _pickedSum => _entries
      .where((e) => _picked.contains(e.glPostingId))
      .fold<double>(0, (sum, e) => sum + e.amountValue);

  /// Match is offered only for an unmatched line and entries that add up to
  /// it to the paisa; the server checks again.
  bool get _canMatch {
    final BankStatementLine? line = _line;
    return _mayPost &&
        !_busy &&
        line != null &&
        !line.isMatched &&
        _picked.isNotEmpty &&
        (_pickedSum - line.signedAmount).abs() < 0.005;
  }

  Future<void> _run(Future<void> Function() action) async {
    setState(() => _busy = true);
    try {
      await action();
    } on ApiException catch (error) {
      _tell(error.message, AppNotificationKind.error);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _match() async {
    final BankStatementLine? line = _line;
    if (line == null) return;
    await _run(() async {
      await widget.api.matchBankLine(line.id, _picked.toList());
      _picked.clear();
      _tell('Line matched.', AppNotificationKind.success);
      await _loadAccount();
    });
  }

  Future<void> _unmatch(BankStatementLine line) => _run(() async {
        await widget.api.unmatchBankLine(line.id);
        _tell('Line unmatched.', AppNotificationKind.success);
        await _loadAccount();
      });

  Future<void> _autoMatch() => _run(() async {
        final AutoMatchResult result = await widget.api
            .autoMatchBankLines(_accountId!, statementId: _statementId);
        _tell(result.message, AppNotificationKind.success);
        await _loadAccount();
      });

  Future<void> _import() async {
    final String? account = _accountId;
    if (account == null) return;
    final FileImportReport? report = await showDialog<FileImportReport>(
      context: context,
      builder: (_) => BankStatementImportDialog(
        api: widget.api,
        ledgerAccountId: account,
        pickFileOverride: widget.pickFileOverride,
        saveBytesOverride: widget.saveBytesOverride,
      ),
    );
    if (report == null || !mounted) return;
    _tell('${report.rows} statement lines imported.',
        AppNotificationKind.success);
    await _loadAccount();
  }

  Future<void> _template() => _run(() async {
        final List<int> bytes =
            await widget.api.bankStatementImportTemplate(format: 'xlsx');
        const String name = 'bank_statement_template.xlsx';
        if (widget.saveBytesOverride != null) {
          await widget.saveBytesOverride!(name, bytes);
        } else {
          final FileSaveLocation? location =
              await getSaveLocation(suggestedName: name);
          if (location == null) return;
          await File(location.path).writeAsBytes(bytes, flush: true);
        }
        _tell('The template was saved.', AppNotificationKind.success);
      });

  Future<void> _removeStatement() async {
    final BankStatement? statement =
        _statements.where((s) => s.id == _statementId).firstOrNull;
    if (statement == null) return;
    final bool? sure = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Remove statement'),
        content: Text(
          'Remove ${statement.label} with its ${statement.lineCount} lines? '
          'Entries it cleared go back to uncleared.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: const Text('Keep it'),
          ),
          FilledButton(
            key: const ValueKey<String>('recon-remove-confirm'),
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: const Text('Remove statement'),
          ),
        ],
      ),
    );
    if (sure != true || !mounted) return;
    await _run(() async {
      await widget.api.deleteBankStatement(statement.id);
      _statementId = null;
      _tell('Statement removed.', AppNotificationKind.success);
      await _loadAccounts();
    });
  }

  Future<void> _pickAsOn() async {
    final DateTime? picked = await showDatePicker(
      context: context,
      initialDate: _asOn,
      firstDate: DateTime(2000),
      lastDate: DateTime(2100),
    );
    if (picked == null || !mounted) return;
    setState(() => _asOn = picked);
    await _loadBrs();
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.hasActiveFirm) {
      return const WorkspaceEmptyState(
        title: 'Choose a firm',
        message: 'Bank reconciliation belongs to one firm’s books.',
      );
    }
    if (!_mayView) {
      return const WorkspaceEmptyState(
        icon: Icons.lock_outline,
        title: 'You cannot see bank reconciliation',
        message: 'Reading it needs the view ledger permission.',
      );
    }
    return ManagementWorkspaceLayout(
      notice: _notice,
      toolbar: _toolbar(),
      searchPanel: SearchFilterPanel(
        controller: _search,
        hintText: 'Search description or reference',
        onSearch: (_) => setState(() {}),
      ),
      primaryContent: _content(),
      statusBar: WorkspaceStatusBar(
        total: _lines.length,
        selected: false,
        message: 'Matching writes nothing to the books.',
      ),
    );
  }

  WorkspaceToolbar _toolbar() {
    final bool hasAccount = _accountId != null;
    return WorkspaceToolbar(
      actions: const [ToolbarAction.refresh],
      isEnabled: (_) => true,
      onAction: (_) => unawaited(_loadAccounts()),
      commands: [
        ToolbarCommand(
          id: 'import',
          label: 'Import statement',
          icon: Icons.upload_file_outlined,
          onPressed:
              _mayPost && hasAccount ? () => unawaited(_import()) : null,
        ),
        ToolbarCommand(
          id: 'auto-match',
          label: 'Auto-match',
          icon: Icons.auto_fix_high_outlined,
          onPressed: _mayPost && hasAccount && !_busy
              ? () => unawaited(_autoMatch())
              : null,
        ),
        ToolbarCommand(
          id: 'template',
          label: 'Download template',
          icon: Icons.download_outlined,
          onPressed: _busy ? null : () => unawaited(_template()),
        ),
        ToolbarCommand(
          id: 'remove-statement',
          label: 'Remove statement',
          icon: Icons.delete_outline,
          onPressed: _mayPost && _statementId != null && !_busy
              ? () => unawaited(_removeStatement())
              : null,
        ),
      ],
    );
  }

  Widget _content() {
    if (_loading) return const Center(child: CircularProgressIndicator());
    final ColorScheme scheme = Theme.of(context).colorScheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (_error != null)
          Padding(
            padding: const EdgeInsets.only(top: AppSpacing.sm),
            child: Text(_error!, style: TextStyle(color: scheme.error)),
          ),
        const SizedBox(height: AppSpacing.sm),
        _selectors(),
        const SizedBox(height: AppSpacing.sm),
        if (_accountId == null)
          const Expanded(
            child: WorkspaceEmptyState(
              title: 'No bank accounts',
              message: 'Add a bank account to the chart of accounts first.',
            ),
          )
        else
          Expanded(
            child: _view == _View.match ? _matchView() : _statementView(),
          ),
      ],
    );
  }

  Widget _selectors() => Wrap(
        spacing: AppSpacing.md,
        runSpacing: AppSpacing.sm,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          SizedBox(
            width: 280,
            child: DropdownButtonFormField<String>(
              key: const ValueKey<String>('recon-account'),
              initialValue: _accountId,
              isExpanded: true,
              decoration: const InputDecoration(labelText: 'Bank account'),
              items: [
                for (final ReconBankAccount a in _accounts)
                  DropdownMenuItem<String>(
                    value: a.id,
                    child: Text(
                      '${a.label} (${a.unmatchedLines} unmatched)',
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
              ],
              onChanged: (value) {
                if (value == null || value == _accountId) return;
                setState(() {
                  _accountId = value;
                  _statementId = null;
                  _lineId = null;
                  _picked.clear();
                  _brs = null;
                });
                unawaited(_loadAccount());
              },
            ),
          ),
          if (_view == _View.match)
            SizedBox(
              width: 280,
              child: DropdownButtonFormField<String?>(
                key: const ValueKey<String>('recon-statement'),
                initialValue: _statementId,
                isExpanded: true,
                decoration: const InputDecoration(labelText: 'Statement'),
                items: [
                  const DropdownMenuItem<String?>(
                    value: null,
                    child: Text('All statements'),
                  ),
                  for (final BankStatement s in _statements)
                    DropdownMenuItem<String?>(
                      value: s.id,
                      child: Text(
                        '${s.label} · ${s.matchedCount}/${s.lineCount}',
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                ],
                onChanged: (value) {
                  setState(() {
                    _statementId = value;
                    _lineId = null;
                    _picked.clear();
                  });
                  unawaited(_loadAccount());
                },
              ),
            ),
          SegmentedButton<_View>(
            key: const ValueKey<String>('recon-view'),
            showSelectedIcon: false,
            segments: const [
              ButtonSegment<_View>(
                value: _View.match,
                label: Text('Match'),
              ),
              ButtonSegment<_View>(
                value: _View.statement,
                label: Text('Reconciliation statement'),
              ),
            ],
            selected: {_view},
            onSelectionChanged: (value) {
              setState(() => _view = value.first);
              if (_view == _View.statement) unawaited(_loadBrs());
            },
          ),
        ],
      );

  // ---- match view ------------------------------------------------------

  bool _hit(String? a, String? b) {
    final String q = _search.text.trim().toLowerCase();
    if (q.isEmpty) return true;
    return (a ?? '').toLowerCase().contains(q) ||
        (b ?? '').toLowerCase().contains(q);
  }

  Widget _matchView() {
    final List<BankStatementLine> lines =
        _lines.where((l) => _hit(l.description, l.reference)).toList();
    final List<BookEntry> entries = _entries
        .where((e) => _hit(e.description,
            '${e.referenceNumber} ${e.instrumentReference}'))
        .toList();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _matchBar(),
        const SizedBox(height: AppSpacing.sm),
        Expanded(
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Expanded(child: _linesPane(lines)),
              const SizedBox(width: AppSpacing.md),
              Expanded(child: _entriesPane(entries)),
            ],
          ),
        ),
      ],
    );
  }

  Widget _matchBar() {
    final ThemeData theme = Theme.of(context);
    final BankStatementLine? line = _line;
    final String text;
    if (line == null) {
      text = 'Pick a statement line, then the entries it stands for.';
    } else if (line.isMatched) {
      text = 'This line is matched.';
    } else {
      text = 'Entries ${_money(_pickedSum)} of line '
          '${_money(line.signedAmount)}';
    }
    return Row(
      children: [
        Expanded(
          child: Text(
            text,
            key: const ValueKey<String>('recon-sum'),
            overflow: TextOverflow.ellipsis,
            style: theme.textTheme.bodyMedium,
          ),
        ),
        const SizedBox(width: AppSpacing.sm),
        if (line != null && line.isMatched && _mayPost)
          OutlinedButton(
            key: const ValueKey<String>('recon-unmatch'),
            onPressed: _busy ? null : () => unawaited(_unmatch(line)),
            child: const Text('Unmatch'),
          )
        else
          FilledButton(
            key: const ValueKey<String>('recon-match'),
            onPressed: _canMatch ? () => unawaited(_match()) : null,
            child: const Text('Match'),
          ),
      ],
    );
  }

  Widget _pane({
    required String title,
    required Widget filter,
    required Widget body,
  }) {
    final ThemeData theme = Theme.of(context);
    return DecoratedBox(
      decoration: BoxDecoration(
        border: Border.all(color: theme.colorScheme.outlineVariant),
        borderRadius: AppRadius.medium,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.all(AppSpacing.sm),
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    title,
                    overflow: TextOverflow.ellipsis,
                    style: theme.textTheme.titleSmall,
                  ),
                ),
                filter,
              ],
            ),
          ),
          const Divider(height: 1),
          Expanded(child: body),
        ],
      ),
    );
  }

  Widget _linesPane(List<BankStatementLine> lines) {
    final ThemeData theme = Theme.of(context);
    return _pane(
      title: 'Statement lines (${lines.length})',
      filter: DropdownButton<String?>(
        key: const ValueKey<String>('recon-status'),
        value: _status,
        underline: const SizedBox.shrink(),
        items: const [
          DropdownMenuItem<String?>(value: 'UNMATCHED', child: Text('Unmatched')),
          DropdownMenuItem<String?>(value: 'MATCHED', child: Text('Matched')),
          DropdownMenuItem<String?>(value: null, child: Text('All')),
        ],
        onChanged: (value) {
          setState(() {
            _status = value;
            _lineId = null;
            _picked.clear();
          });
          unawaited(_loadAccount());
        },
      ),
      body: lines.isEmpty
          ? const Center(child: Text('No statement lines.'))
          : ListView.builder(
              itemCount: lines.length,
              itemBuilder: (context, index) {
                final BankStatementLine line = lines[index];
                final bool out = line.signedAmount < 0;
                return ListTile(
                  key: ValueKey<String>('recon-line-${line.id}'),
                  dense: true,
                  selected: line.id == _lineId,
                  selectedTileColor: theme.colorScheme.primaryContainer,
                  title: Text(
                    line.description.isEmpty ? line.reference : line.description,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  subtitle: Text(
                    [
                      line.lineDate,
                      if (line.reference.isNotEmpty) line.reference,
                      if (line.isMatched)
                        'Matched to ${line.matches.map((m) => m.referenceNumber).join(', ')}',
                    ].join(' · '),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  trailing: Text(
                    presentAmount(_money(line.signedAmount)),
                    style: out ? TextStyle(color: theme.colorScheme.error) : null,
                  ),
                  onTap: () => setState(() {
                    _lineId = line.id;
                    _picked.clear();
                  }),
                );
              },
            ),
    );
  }

  Widget _entriesPane(List<BookEntry> entries) {
    final ThemeData theme = Theme.of(context);
    return _pane(
      title: 'Uncleared book entries (${entries.length})',
      filter: Text('${_picked.length} picked', style: theme.textTheme.bodySmall),
      body: entries.isEmpty
          ? const Center(child: Text('Nothing is waiting to clear.'))
          : ListView.builder(
              itemCount: entries.length,
              itemBuilder: (context, index) {
                final BookEntry entry = entries[index];
                final bool out = entry.amountValue < 0;
                return CheckboxListTile(
                  key: ValueKey<String>('recon-entry-${entry.glPostingId}'),
                  dense: true,
                  controlAffinity: ListTileControlAffinity.leading,
                  value: _picked.contains(entry.glPostingId),
                  onChanged: _line == null || _line!.isMatched
                      ? null
                      : (on) => setState(() {
                            if (on == true) {
                              _picked.add(entry.glPostingId);
                            } else {
                              _picked.remove(entry.glPostingId);
                            }
                          }),
                  title: Text(
                    entry.instrumentReference.isEmpty
                        ? entry.referenceNumber
                        : '${entry.referenceNumber} · '
                            '${entry.instrumentReference}',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  subtitle: Text(
                    [
                      entry.journalDate,
                      if (entry.description.isNotEmpty) entry.description,
                    ].join(' · '),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  secondary: Text(
                    presentAmount(_money(entry.amountValue)),
                    style: out ? TextStyle(color: theme.colorScheme.error) : null,
                  ),
                );
              },
            ),
    );
  }

  // ---- reconciliation statement ----------------------------------------

  Widget _statementView() {
    final ThemeData theme = Theme.of(context);
    final BankReconciliationStatement? brs = _brs;
    return ListView(
      children: [
        Row(
          children: [
            const Text('As on '),
            TextButton.icon(
              key: const ValueKey<String>('recon-as-on'),
              onPressed: () => unawaited(_pickAsOn()),
              icon: const Icon(Icons.calendar_today_outlined, size: 16),
              label: Text(DatePeriod.iso(_asOn)),
            ),
          ],
        ),
        if (_brsError != null)
          Text(_brsError!, style: TextStyle(color: theme.colorScheme.error)),
        if (brs == null && _brsError == null)
          const Padding(
            padding: EdgeInsets.all(AppSpacing.lg),
            child: Center(child: CircularProgressIndicator()),
          ),
        if (brs != null) ..._statementRows(brs),
      ],
    );
  }

  List<Widget> _statementRows(BankReconciliationStatement brs) {
    final ThemeData theme = Theme.of(context);
    final TextStyle? bold = theme.textTheme.titleSmall;
    Widget line(String label, String value,
            {TextStyle? style, Key? key, Color? color}) =>
        Padding(
          padding: const EdgeInsets.symmetric(vertical: 2),
          child: Row(
            children: [
              Expanded(
                child: Text(label, style: style, overflow: TextOverflow.ellipsis),
              ),
              Text(
                value,
                key: key,
                style: (style ?? const TextStyle()).copyWith(color: color),
              ),
            ],
          ),
        );
    List<Widget> items(List<ReconcilingItem> list) => [
          for (final ReconcilingItem item in list)
            Padding(
              padding: const EdgeInsets.only(left: AppSpacing.lg),
              child: line(
                [
                  item.on,
                  if (item.reference.isNotEmpty) item.reference,
                  if (item.description.isNotEmpty) item.description,
                ].join(' · '),
                presentAmount(_money(double.tryParse(item.amount) ?? 0)),
                style: theme.textTheme.bodySmall,
              ),
            ),
        ];
    String m(String value) => presentAmount(_money(double.tryParse(value) ?? 0));
    final Color? differenceColor = brs.isOut ? theme.colorScheme.error : null;
    return [
      line('Balance as per books', m(brs.bookBalance),
          style: bold, key: const ValueKey<String>('recon-book-balance')),
      const Divider(),
      line('Less: deposits not cleared', m(brs.depositsNotClearedTotal),
          style: bold, key: const ValueKey<String>('recon-deposits-total')),
      ...items(brs.depositsNotCleared),
      line('Add: payments not presented', m(brs.paymentsNotPresentedTotal),
          style: bold, key: const ValueKey<String>('recon-payments-total')),
      ...items(brs.paymentsNotPresented),
      line('Add / (less): in the bank, not in the books', m(brs.bankOnlyNet),
          style: bold, key: const ValueKey<String>('recon-bank-only-total')),
      ...items(brs.bankOnly),
      const Divider(),
      line('Balance the bank should show', m(brs.bankBalancePerBooks),
          style: bold, key: const ValueKey<String>('recon-per-books')),
      line(
        'Balance on the statement',
        brs.statementBalance.isEmpty ? 'none imported' : m(brs.statementBalance),
        style: bold,
        key: const ValueKey<String>('recon-statement-balance'),
      ),
      if (brs.hasDifference)
        line('Difference', m(brs.difference),
            style: bold,
            key: const ValueKey<String>('recon-difference'),
            color: differenceColor),
    ];
  }
}

/// Show money at two decimals.
String _money(double value) => value.toStringAsFixed(2);

/// Import a bank statement: the shared [MasterImportDialog] wired to the bank
/// statement endpoints, with an optional name for the statement. Closes with
/// the applied report, or null if nothing was imported.
class BankStatementImportDialog extends StatefulWidget {
  const BankStatementImportDialog({
    super.key,
    required this.api,
    required this.ledgerAccountId,
    this.pickFileOverride,
    this.saveBytesOverride,
  });

  final ApiClient api;
  final String ledgerAccountId;
  final Future<XFile?> Function()? pickFileOverride;
  final SaveBytesOverride? saveBytesOverride;

  @override
  State<BankStatementImportDialog> createState() =>
      _BankStatementImportDialogState();
}

class _BankStatementImportDialogState extends State<BankStatementImportDialog> {
  final TextEditingController _name = TextEditingController();

  @override
  void dispose() {
    _name.dispose();
    super.dispose();
  }

  Widget _fields(BuildContext context, VoidCallback changed) => TextField(
        key: const ValueKey<String>('bank-statement-import-name'),
        controller: _name,
        onChanged: (_) => changed(),
        decoration: const InputDecoration(
          labelText: 'Statement name (optional)',
          helperText: 'The file’s name is used when this is left blank.',
        ),
      );

  @override
  Widget build(BuildContext context) => MasterImportDialog(
        noun: 'bank statement lines',
        fileStem: 'bank_statement',
        downloadTemplate: (format) =>
            widget.api.bankStatementImportTemplate(format: format),
        checkFile: ({
          required String fileName,
          required List<int> bytes,
          required bool updateExisting,
          required bool apply,
          Map<String, String?>? mapping,
        }) =>
            widget.api.checkBankStatementFile(
          ledgerAccountId: widget.ledgerAccountId,
          fileName: fileName,
          bytes: bytes,
          apply: apply,
          name: _name.text.trim(),
          mapping: mapping,
        ),
        mappingApi: widget.api,
        mappingKind: 'bank-statement',
        canUpdate: false,
        offersUpdate: false,
        extraFields: _fields,
        pickFileOverride: widget.pickFileOverride,
        saveBytesOverride: widget.saveBytesOverride,
      );
}
