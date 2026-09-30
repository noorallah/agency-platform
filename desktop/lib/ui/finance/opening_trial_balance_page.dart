import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/entities.dart';
import '../../models/finance.dart';
import '../../phase2/indian_format.dart';
import '../workspace/desktop_framework.dart';

/// One row being written, before it is anything the server has seen.
class _DraftLine {
  _DraftLine({
    this.ledgerAccountId = '',
    this.accountCode = '',
    this.debit = '',
    this.credit = '',
    this.description = '',
  });

  String ledgerAccountId;
  String accountCode;
  String debit;
  String credit;
  String description;

  double get debitValue => double.tryParse(debit.trim()) ?? 0;
  double get creditValue => double.tryParse(credit.trim()) ?? 0;

  /// A row nobody has filled in. Blank rows are dropped rather than sent,
  /// because an empty row is somebody's cursor, not an instruction.
  bool get isBlank =>
      ledgerAccountId.isEmpty && debitValue == 0 && creditValue == 0;

  /// A row cannot be an amount on both sides.
  bool get isTwoSided => debitValue > 0 && creditValue > 0;

  Json toJson() => {
        'account_code': accountCode,
        'debit_amount': debitValue.toStringAsFixed(2),
        'credit_amount': creditValue.toStringAsFixed(2),
        'description': description.trim(),
      };
}

/// The opening trial balance: where a firm's books stood on its cutover
/// date, account by account, re-entered whole (backlog 36).
///
/// Customer balances, supplier bills and stock keep their own opening paths
/// -- this is for everything else: cash, bank, fixed assets, loans, capital
/// and tax balances carried over from another tool. Whatever the statement
/// leaves unbalanced is credited or debited to Opening Balance Equity by the
/// server; nothing here writes to that account directly, because the server
/// refuses it as a line.
class OpeningTrialBalancePage extends StatefulWidget {
  const OpeningTrialBalancePage({
    super.key,
    required this.api,
    required this.permissions,
    required this.hasActiveFirm,
  });

  final ApiClient api;
  final PermissionService permissions;
  final bool hasActiveFirm;

  @override
  State<OpeningTrialBalancePage> createState() =>
      _OpeningTrialBalancePageState();
}

class _OpeningTrialBalancePageState extends State<OpeningTrialBalancePage> {
  List<LedgerAccount> _accounts = const [];
  OpeningTrialBalance _standing = OpeningTrialBalance.empty;
  final List<_DraftLine> _lines = [];
  String _asOfDate = '';

  bool _loading = true;
  bool _saving = false;
  String? _loadError;
  String? _saveError;

  bool get _canSave => widget.permissions.hasPermission('JOURNAL_POST');

  @override
  void initState() {
    super.initState();
    if (widget.hasActiveFirm) _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _loadError = null;
    });
    try {
      final List<dynamic> results = await Future.wait<dynamic>([
        widget.api.getOpeningTrialBalance(),
        // Only what a hand line may post to (D-FIN-20): the server refuses
        // sub-ledger and CONTROL accounts by name, and Opening Balance
        // Equity is refused as a line here whatever the filter leaves in.
        widget.api.ledgerAccounts(isActive: true, openToHandJournals: true),
        widget.api.controlAccounts(),
      ]);
      if (!mounted) return;
      final OpeningTrialBalance standing = results[0] as OpeningTrialBalance;
      final List<LedgerAccount> accounts =
          (results[1] as PagedResult<LedgerAccount>).items;
      final List<ControlAccountMapping> mappings =
          results[2] as List<ControlAccountMapping>;
      final String? equityAccountId = mappings
          .where((row) => row.purpose == 'OPENING_BALANCE_EQUITY')
          .map((row) => row.ledgerAccountId)
          .firstOrNull;
      setState(() {
        _standing = standing;
        _accounts = [
          for (final LedgerAccount account in accounts)
            if (account.id != equityAccountId) account,
        ];
        _asOfDate = standing.asOfDate ??
            DateTime.now().toIso8601String().split('T').first;
        _lines
          ..clear()
          ..addAll([
            for (final OpeningBalanceLine line in standing.lines)
              _DraftLine(
                ledgerAccountId: line.ledgerAccountId,
                accountCode: line.accountCode,
                debit: (double.tryParse(line.debitAmount) ?? 0) == 0
                    ? ''
                    : line.debitAmount,
                credit: (double.tryParse(line.creditAmount) ?? 0) == 0
                    ? ''
                    : line.creditAmount,
                description: line.description,
              ),
          ]);
        if (_lines.isEmpty) _lines.add(_DraftLine());
        _loading = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _loadError = error.message;
      });
    }
  }

  double get _debitTotal =>
      _lines.fold(0, (sum, line) => sum + line.debitValue);
  double get _creditTotal =>
      _lines.fold(0, (sum, line) => sum + line.creditValue);

  /// Positive: credited to Opening Balance Equity. Negative: debited.
  double get _equityDifference => _debitTotal - _creditTotal;

  LedgerAccount? _accountOf(_DraftLine line) {
    for (final LedgerAccount account in _accounts) {
      if (account.id == line.ledgerAccountId) return account;
    }
    return null;
  }

  Future<void> _save() async {
    final List<_DraftLine> filled =
        _lines.where((line) => !line.isBlank).toList();
    for (int index = 0; index < filled.length; index++) {
      final _DraftLine line = filled[index];
      if (line.ledgerAccountId.isEmpty) {
        setState(() =>
            _saveError = 'Row ${index + 1}: choose the account this amount '
                'belongs to.');
        return;
      }
      if (line.isTwoSided) {
        setState(() => _saveError = 'Row ${index + 1}: an amount is either a '
            'debit or a credit, not both.');
        return;
      }
    }
    if (_asOfDate.trim().isEmpty) {
      setState(() => _saveError = 'A cutover date is needed.');
      return;
    }
    await _replace(filled);
  }

  Future<void> _clear() async {
    final bool confirmed = await showWorkspaceConfirmDialog(
      context,
      title: 'Clear the opening trial balance?',
      message: 'Every line is taken off. The posted journal is reversed, '
          'and nothing replaces it until this is entered again.',
      confirmLabel: 'Clear',
    );
    if (!confirmed || !mounted) return;
    await _replace(const []);
  }

  Future<void> _replace(List<_DraftLine> lines) async {
    setState(() {
      _saving = true;
      _saveError = null;
    });
    try {
      final Json body = {
        'as_of_date': _asOfDate.trim(),
        'lines': [for (final _DraftLine line in lines) line.toJson()],
      };
      final (OpeningTrialBalance standing, String message) =
          await widget.api.replaceOpeningTrialBalance(body);
      if (!mounted) return;
      setState(() {
        _standing = standing;
        _asOfDate = standing.asOfDate ?? _asOfDate;
        _lines
          ..clear()
          ..addAll([
            for (final OpeningBalanceLine line in standing.lines)
              _DraftLine(
                ledgerAccountId: line.ledgerAccountId,
                accountCode: line.accountCode,
                debit: (double.tryParse(line.debitAmount) ?? 0) == 0
                    ? ''
                    : line.debitAmount,
                credit: (double.tryParse(line.creditAmount) ?? 0) == 0
                    ? ''
                    : line.creditAmount,
                description: line.description,
              ),
          ]);
        if (_lines.isEmpty) _lines.add(_DraftLine());
        _saving = false;
      });
      NotificationService.show(
        context,
        message.isEmpty ? 'Opening trial balance saved.' : message,
        kind: AppNotificationKind.success,
      );
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _saving = false;
        _saveError = error.message;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.hasActiveFirm) {
      return const StandardEmptyState(
        type: EmptyStateType.noFirmSelected,
        title: 'Select a firm',
        message: 'The opening trial balance belongs to a firm. Choose one to '
            'see where its books stood on its cutover date.',
      );
    }
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_loadError != null) {
      return StandardEmptyState(
        type: EmptyStateType.noRecords,
        title: 'Could not load the opening trial balance',
        message: _loadError!,
        action: FilledButton(onPressed: _load, child: const Text('Retry')),
      );
    }
    final ThemeData theme = Theme.of(context);
    return SingleChildScrollView(
      padding: const EdgeInsets.all(AppSpacing.xl),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            _standing.referenceNumber == null
                ? 'Nothing has been entered yet.'
                : 'Standing as ${_standing.referenceNumber}, as of '
                    '${_standing.asOfDate}.',
            style: theme.textTheme.bodyMedium,
          ),
          const SizedBox(height: AppSpacing.sm),
          Text(
            'Customer balances, supplier bills and stock have their own '
            'opening screens.',
            style: theme.textTheme.bodySmall
                ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
          ),
          const SizedBox(height: AppSpacing.xl),
          SizedBox(
            width: 180,
            child: TextFormField(
              key: const ValueKey('opening-trial-balance-date'),
              initialValue: _asOfDate,
              decoration: const InputDecoration(
                labelText: 'As of *',
                hintText: 'YYYY-MM-DD',
              ),
              onChanged: (value) => setState(() => _asOfDate = value),
            ),
          ),
          const SizedBox(height: AppSpacing.xl),
          const SectionHeader(
            title: 'Lines',
            description:
                'One account, one side. What the lines leave unbalanced is '
                'credited or debited to Opening Balance Equity.',
          ),
          const SizedBox(height: AppSpacing.md),
          ..._lineRows(),
          const SizedBox(height: AppSpacing.sm),
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton.icon(
              key: const ValueKey('opening-trial-balance-add-row'),
              onPressed: () => setState(() => _lines.add(_DraftLine())),
              icon: const Icon(Icons.add),
              label: const Text('Add row'),
            ),
          ),
          const SizedBox(height: AppSpacing.lg),
          _totals(theme),
          if (_saveError != null) ...[
            const SizedBox(height: AppSpacing.lg),
            MaterialBanner(
              content: Text(_saveError!),
              actions: [
                TextButton(
                  onPressed: () => setState(() => _saveError = null),
                  child: const Text('Dismiss'),
                ),
              ],
            ),
          ],
          const SizedBox(height: AppSpacing.xl),
          Row(
            children: [
              if (_standing.referenceNumber != null)
                TextButton(
                  key: const ValueKey('opening-trial-balance-clear'),
                  onPressed: _canSave && !_saving ? _clear : null,
                  child: const Text('Clear'),
                ),
              const Spacer(),
              FilledButton(
                key: const ValueKey('opening-trial-balance-save'),
                onPressed: _canSave && !_saving ? _save : null,
                child: Text(_saving ? 'Saving…' : 'Save'),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _totals(ThemeData theme) {
    final double difference = _equityDifference;
    final String verb = difference > 0
        ? 'credited to'
        : difference < 0
            ? 'debited from'
            : 'nothing goes to';
    return Wrap(
      spacing: AppSpacing.xl,
      runSpacing: AppSpacing.sm,
      children: [
        _totalTile(theme, 'Debit', _debitTotal),
        _totalTile(theme, 'Credit', _creditTotal),
        Text(
          difference == 0
              ? 'Balanced -- $verb Opening Balance Equity.'
              : 'Difference to Opening Balance Equity: '
                  '${indianAmount(difference.abs(), full: true)} will be '
                  '$verb Opening Balance Equity.',
          style: theme.textTheme.bodyMedium,
        ),
      ],
    );
  }

  Widget _totalTile(ThemeData theme, String label, double value) => Text(
        '$label ${indianAmount(value, full: true)}',
        style: theme.textTheme.titleSmall,
      );

  List<Widget> _lineRows() => [
        for (int index = 0; index < _lines.length; index++)
          Padding(
            padding: const EdgeInsets.only(bottom: AppSpacing.md),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  flex: 3,
                  child: DropdownButtonFormField<String>(
                    key: ValueKey('opening-trial-balance-account-$index'),
                    // Only an account the list offers: a statement written
                    // before D-FIN-20 may hold one the server now refuses.
                    initialValue: _accountOf(_lines[index]) == null
                        ? null
                        : _lines[index].ledgerAccountId,
                    isExpanded: true,
                    decoration:
                        InputDecoration(labelText: 'Account ${index + 1}'),
                    items: [
                      for (final LedgerAccount account in _accounts)
                        DropdownMenuItem<String>(
                          value: account.id,
                          child: Text(
                            '${account.code} — ${account.name}',
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                    ],
                    onChanged: (value) => setState(() {
                      _lines[index].ledgerAccountId = value ?? '';
                      final LedgerAccount? account = _accounts
                          .where((account) => account.id == value)
                          .firstOrNull;
                      _lines[index].accountCode = account?.code ?? '';
                    }),
                  ),
                ),
                const SizedBox(width: AppSpacing.md),
                SizedBox(
                  width: 130,
                  child: TextFormField(
                    key: ValueKey('opening-trial-balance-debit-$index'),
                    initialValue: _lines[index].debit,
                    decoration: const InputDecoration(labelText: 'Debit'),
                    keyboardType: TextInputType.number,
                    onChanged: (value) =>
                        setState(() => _lines[index].debit = value),
                  ),
                ),
                const SizedBox(width: AppSpacing.md),
                SizedBox(
                  width: 130,
                  child: TextFormField(
                    key: ValueKey('opening-trial-balance-credit-$index'),
                    initialValue: _lines[index].credit,
                    decoration: const InputDecoration(labelText: 'Credit'),
                    keyboardType: TextInputType.number,
                    onChanged: (value) =>
                        setState(() => _lines[index].credit = value),
                  ),
                ),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                  flex: 2,
                  child: TextFormField(
                    key: ValueKey('opening-trial-balance-note-$index'),
                    initialValue: _lines[index].description,
                    decoration: const InputDecoration(labelText: 'Note'),
                    onChanged: (value) =>
                        setState(() => _lines[index].description = value),
                  ),
                ),
                const SizedBox(width: AppSpacing.md),
                IconButton(
                  key: ValueKey('opening-trial-balance-remove-$index'),
                  tooltip: 'Remove row',
                  onPressed: _lines.length <= 1
                      ? null
                      : () => setState(() => _lines.removeAt(index)),
                  icon: const Icon(Icons.delete_outline),
                ),
              ],
            ),
          ),
      ];
}
