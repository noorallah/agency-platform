import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/preferences/desktop_preferences_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/entities.dart';
import '../../models/expense.dart';
import '../workspace/desktop_framework.dart';
import '../workspace/reason_prompt.dart';
import 'record_expense_dialog.dart';

/// Rent, fuel, salaries: money spent that no document raised.
///
/// Tally's payment voucher and Zoho Books' *Expenses*: say what it was for,
/// how much, and where the money came from, and the journal is written and
/// posted for you (docs/PROFIT_AND_LOSS_GUIDE.md section 5 item 1). A mistake
/// is cancelled -- a mirror journal takes it back -- rather than edited.
class ExpensesPage extends StatefulWidget {
  const ExpensesPage({
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
  State<ExpensesPage> createState() => _ExpensesPageState();
}

class _ExpensesPageState extends State<ExpensesPage> {
  static const int _rowsPerPage = 20;
  static const String _notice =
      'Recording an expense posts its journal at once: the expense account '
      'is debited and the cash or bank account it was paid from is '
      'credited, so it reaches Profit & Loss straight away. A mistake is '
      'cancelled rather than edited -- an opposite journal takes it back '
      'and both stay on the record.';

  final TextEditingController _search = TextEditingController();
  List<Expense> _rows = const [];
  Expense? _selected;

  /// The expense dates the list is narrowed to.
  DatePeriod _period = const DatePeriod.all();
  int _page = 1;
  int _total = 0;

  /// True until the first read has answered, so the grid says nothing -- not
  /// "no expenses yet" -- while that is still unknown.
  bool _loading = true;
  String? _error;

  bool get _canView => widget.permissions.hasPermission('EXPENSE_VIEW');
  bool get _canCreate => widget.permissions.hasPermission('EXPENSE_CREATE');
  bool get _canCancel => widget.permissions.hasPermission('EXPENSE_CANCEL');

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  Future<void> _load({int? requestedPage}) async {
    if (!widget.hasActiveFirm || !_canView) return;
    setState(() {
      _loading = true;
      _error = null;
      if (requestedPage != null) _page = requestedPage;
    });
    try {
      final PagedResult<Expense> result = await widget.api.expenses(
        page: _page,
        pageSize: _rowsPerPage,
        search: _search.text.trim(),
        expenseFrom:
            _period.from == null ? null : DatePeriod.iso(_period.from!),
        expenseTo: _period.to == null ? null : DatePeriod.iso(_period.to!),
      );
      if (!mounted) return;
      setState(() {
        _rows = result.items;
        _total = result.total;
        // Keep the picked one across a reload, unless it fell off the page.
        final String? selectedId = _selected?.id;
        _selected = selectedId == null
            ? null
            : result.items.where((item) => item.id == selectedId).firstOrNull;
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

  Future<void> _record() async {
    final Expense? saved = await showDialog<Expense>(
      context: context,
      barrierDismissible: false,
      builder: (_) => RecordExpenseDialog(api: widget.api),
    );
    if (saved == null || !mounted) return;
    await _load(requestedPage: 1);
    if (!mounted) return;
    NotificationService.show(
      context,
      '${saved.expenseNumber} recorded and posted to the ledger.',
      kind: AppNotificationKind.success,
    );
  }

  /// Take one back, after saying why. Nothing is deleted: the expense and
  /// the opposite journal both stay on the record.
  Future<void> _cancel(Expense row) async {
    final String? why = await askForReason(
      context,
      title: 'Cancel ${row.expenseNumber}',
      explanation: 'This writes an opposite journal, so the '
          '${row.amount} comes back off ${row.expenseAccountName} and back '
          'into ${row.paidFromAccountName}. Nothing is deleted: both stay on '
          'the record.',
      label: 'Why is it being cancelled?',
      confirmLabel: 'Cancel expense',
      cancelLabel: 'Keep it',
    );
    if (why == null || !mounted) return;
    setState(() => _loading = true);
    try {
      await widget.api.cancelExpense(
        id: row.id,
        reason: why,
        expectedVersion: row.version,
      );
      await _load();
      if (!mounted) return;
      NotificationService.show(
        context,
        '${row.expenseNumber} cancelled.',
        kind: AppNotificationKind.success,
      );
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() => _error = exception.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!_canView) {
      return const StandardEmptyState(
        type: EmptyStateType.noPermissions,
        title: 'Expenses',
        message: 'You do not have permission to view expenses.',
      );
    }
    if (!widget.hasActiveFirm) {
      return const StandardEmptyState(
        type: EmptyStateType.noFirmSelected,
        title: 'Expenses',
        message: 'Choose a firm to see its expenses.',
      );
    }
    final Expense? selected = _selected;
    return LoadingOverlay(
      loading: _loading,
      child: ManagementWorkspaceLayout(
        notice: _notice,
        toolbar: WorkspaceToolbar(
          actions: const [
            ToolbarAction.newItem,
            ToolbarAction.view,
            ToolbarAction.refresh,
          ],
          isVisible: (action) => action != ToolbarAction.newItem || _canCreate,
          isEnabled: (action) =>
              !_loading &&
              switch (action) {
                ToolbarAction.newItem => _canCreate,
                ToolbarAction.view => selected != null,
                ToolbarAction.refresh => true,
                _ => false,
              },
          onAction: (action) {
            switch (action) {
              case ToolbarAction.newItem:
                unawaited(_record());
              case ToolbarAction.view:
                if (selected != null) unawaited(_open(selected));
              case ToolbarAction.refresh:
                unawaited(_load());
              default:
                break;
            }
          },
          trailing: [
            DateRangeFilter(
              value: _period,
              onChanged: (period) {
                setState(() => _period = period);
                unawaited(_load(requestedPage: 1));
              },
            ),
            ColumnsButton(
              onPressed: () async {
                if (await _columns.choose(context) && mounted) {
                  setState(() {});
                }
              },
            ),
          ],
          commands: [
            if (_canCancel)
              ToolbarCommand(
                id: 'cancel',
                label: 'Cancel',
                icon: Icons.undo,
                onPressed: selected != null && !selected.isCancelled
                    ? () => unawaited(_cancel(selected))
                    : null,
              ),
          ],
        ),
        selectionBar: true,
        selection: selected == null
            ? null
            : SelectionSummary.document(
                number: selected.expenseNumber,
                party: selected.expenseAccountName,
                status: selected.status,
                total: selected.amount,
                onClear: () => setState(() => _selected = null),
              ),
        searchPanel: SearchFilterPanel(
          controller: _search,
          hintText: 'Search number, payee, reference or expense',
          onSearch: (_) => unawaited(_load(requestedPage: 1)),
        ),
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
            // Nothing yet while the first read is out: the thin bar says it
            // is loading, and "nothing here" would be a claim not yet known.
            child: _loading && _rows.isEmpty
                ? const SizedBox.shrink()
                : _rows.isEmpty
                    ? (_search.text.trim().isEmpty && _period.from == null
                        ? const StandardEmptyState(
                            type: EmptyStateType.noRecords,
                            title: 'No expenses yet',
                            message: 'Record rent, fuel, salaries and other '
                                'running costs here. Each one posts to the '
                                'ledger as it is saved.',
                          )
                        : const StandardEmptyState(
                            type: EmptyStateType.noSearchResults,
                          ))
                    : EnterpriseDataGrid<Expense>(
                        columns: _columns.gridColumns,
                        items: _rows,
                        id: (item) => item.id,
                        selectedId: selected?.id,
                        cells: _columns.cells,
                        onSelect: (item) => setState(() => _selected = item),
                        onOpen: (item) => unawaited(_open(item)),
                        total: _total,
                        pageOffset: (_page - 1) * _rowsPerPage,
                        rowsPerPage: _rowsPerPage,
                        onPageChanged: (offset) {
                          final int next = offset ~/ _rowsPerPage + 1;
                          if (next != _page) {
                            unawaited(_load(requestedPage: next));
                          }
                        },
                      ),
          ),
        ]),
        statusBar: WorkspaceStatusBar(
          total: _total,
          selected: selected != null,
          message: _loading ? 'Loading...' : null,
        ),
      ),
    );
  }

  /// Every column the grid can show; Columns picks among them, remembered
  /// per screen on this PC.
  late final ColumnChoice<Expense> _columns = ColumnChoice(
    preferences: widget.preferences,
    stateKey: 'expenses.grid',
    columns: [
      ChoosableColumn(
        column: const GridColumn(key: 'number', label: 'Number'),
        cell: (item) => item.expenseNumber,
        required: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'date', label: 'Date'),
        cell: (item) => item.expenseDate,
        shownByDefault: true,
      ),
      // What the money was spent on; kept at any width.
      ChoosableColumn(
        column: const GridColumn(key: 'expense', label: 'Expense', priority: 1),
        cell: (item) => item.expenseAccountName,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'paid_from', label: 'Paid from'),
        cell: (item) => item.paidFromAccountName,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'payee', label: 'Payee'),
        cell: (item) => item.payee,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'reference', label: 'Reference'),
        cell: (item) => item.reference,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'status', label: 'Status'),
        cell: (item) => item.status,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'amount', label: 'Amount', numeric: true),
        cell: (item) => item.amount,
        shownByDefault: true,
      ),
      // Tax deducted at source (53.1); Columns turns these on.
      ChoosableColumn(
        column: const GridColumn(key: 'tds', label: 'TDS', numeric: true),
        cell: (item) => item.tdsAmount,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'tds_section', label: 'TDS Section'),
        cell: (item) => item.tdsSection,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'narration', label: 'Narration'),
        cell: (item) => item.narration,
      ),
    ],
  );

  /// Read one, as it stands now. Cancel stays on the bar above the grid, so
  /// this only reads.
  Future<void> _open(Expense row) async {
    setState(() => _selected = row);
    Expense shown = row;
    try {
      shown = await widget.api.expense(row.id);
    } on ApiException {
      // The row already in hand says the same, only possibly older.
    }
    if (!mounted) return;
    await showDialog<void>(
      context: context,
      builder: (dialogContext) {
        final TextStyle? small = Theme.of(dialogContext).textTheme.bodySmall;
        Widget fact(String label, String value) => value.isEmpty
            ? const SizedBox.shrink()
            : Padding(
                padding: const EdgeInsets.symmetric(vertical: 2),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    SizedBox(width: 120, child: Text(label, style: small)),
                    Expanded(child: Text(value)),
                  ],
                ),
              );
        return AlertDialog(
          title: Row(children: [
            Expanded(child: Text(shown.expenseNumber)),
            StatusBadge.fromStatus(shown.status),
          ]),
          content: SizedBox(
            width: 520,
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  fact('Date', shown.expenseDate),
                  fact('Expense', shown.expenseAccount),
                  fact('Paid from', shown.paidFromAccountName),
                  fact('Amount', shown.amount),
                  fact('Payee', shown.payee),
                  fact('Reference', shown.reference),
                  fact('Narration', shown.narration),
                  fact('Cancelled because', shown.cancelReason),
                  const SizedBox(height: AppSpacing.sm),
                  Text(
                    shown.isCancelled
                        ? 'Its journal was taken back by an opposite one; '
                            'both stay in Journal Entries.'
                        : 'Posted to the ledger under ${shown.expenseNumber} '
                            '-- search it in Journal Entries.',
                    style: small,
                  ),
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
}
