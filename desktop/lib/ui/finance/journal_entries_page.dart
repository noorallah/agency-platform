import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/preferences/desktop_preferences_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/entities.dart';
import '../../models/finance.dart';
import '../workspace/desktop_framework.dart';
import '../workspace/reason_prompt.dart';
import 'journal_entry_dialog.dart';
import 'journal_entry_view_dialog.dart';

/// The journal: everything posted to the ledger, and a way to add to it.
///
/// Most rows here were written by documents rather than people -- a completed
/// goods receipt, a dispatched delivery note, an approved invoice all post one.
/// The grid says which module raised each, because "who wrote this" is the
/// first question anybody asks of an entry they did not expect.
class JournalEntriesPage extends StatefulWidget {
  const JournalEntriesPage({
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
  State<JournalEntriesPage> createState() => _JournalEntriesPageState();
}

/// The modules that post to the ledger, as the server records them in
/// `source_module`, with the name a person reads (BL-31.15). The page showed
/// "Posted by" on each row and had no way to ask for one module's
/// entries.
const List<(String, String)> journalSourceModules = [
  ('commission', 'Commission'),
  ('credit_note', 'Credit notes'),
  ('customers', 'Customers'),
  ('delivery_note', 'Delivery notes'),
  ('goods_receipt', 'Goods receipts'),
  ('inventory', 'Inventory'),
  ('loyalty', 'Loyalty'),
  ('physical_count', 'Physical counts'),
  ('purchase_invoice', 'Purchase invoices'),
  ('purchase_return', 'Purchase returns'),
  ('sales_invoice', 'Sales invoices'),
  ('sales_return', 'Sales returns'),
  ('settlements', 'Receipts and payments'),
  ('tcs', 'TCS'),
];

class _JournalEntriesPageState extends State<JournalEntriesPage> {
  static const int _rowsPerPage = 20;
  final TextEditingController _search = TextEditingController();
  // Null is "All modules", hand journals included.
  String? _sourceModule;

  /// The journal dates the list is narrowed to (owner, 2026-09-27).
  DatePeriod _period = const DatePeriod.all();
  List<JournalEntry> _entries = const [];
  JournalEntry? _selected;
  int _page = 1;
  int _total = 0;
  bool _loading = false;
  String? _error;

  // Loaded only when the editor is opened: an entry cannot be written without
  // them, and nobody reading the list needs them.
  List<LedgerAccount> _accounts = const [];
  List<FinanceCentre> _costCenters = const [];
  List<FinanceCentre> _profitCenters = const [];
  List<AccountingPeriod> _periods = const [];
  List<FinanceTypeRef> _journalTypes = const [];
  List<FinanceTypeRef> _voucherTypes = const [];

  bool get _canView => widget.permissions.hasPermission('JOURNAL_VIEW');
  bool get _canCreate => widget.permissions.hasPermission('JOURNAL_CREATE');
  bool get _canPost => widget.permissions.hasPermission('JOURNAL_POST');
  bool get _canReverse => widget.permissions.hasPermission('JOURNAL_REVERSE');

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
      final PagedResult<JournalEntry> result = await widget.api.journalEntries(
        page: _page,
        pageSize: _rowsPerPage,
        search: _search.text.trim(),
        sourceModule: _sourceModule,
        journalFrom:
            _period.from == null ? null : DatePeriod.iso(_period.from!),
        journalTo: _period.to == null ? null : DatePeriod.iso(_period.to!),
      );
      if (!mounted) return;
      // Phase 2 lists pick nothing until the user does; phase 1 kept the
      // first row picked. Read without a dependency: this runs from
      // initState too.
      final bool phase2 =
          context.getInheritedWidgetOfExactType<Phase2Scope>() != null;
      setState(() {
        _entries = result.items;
        _total = result.total;
        final JournalEntry? kept = result.items
            .where((entry) => entry.id == _selected?.id)
            .firstOrNull;
        _selected = kept ??
            (phase2 || result.items.isEmpty ? null : result.items.first);
      });
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() {
        _error = exception.message;
        _entries = const [];
        _total = 0;
      });
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  /// Everything the editor needs to offer a choice, fetched when it opens.
  Future<bool> _loadEditorReferences() async {
    try {
      final List<dynamic> results = await Future.wait<dynamic>([
        // Only what a hand journal may post to (D-FIN-20): the server
        // refuses sub-ledger and CONTROL accounts by name.
        widget.api.ledgerAccounts(isActive: true, openToHandJournals: true),
        widget.api.accountingPeriods(),
        widget.api.journalTypes(),
        widget.api.voucherTypes(),
        widget.api.costCenters(),
        widget.api.profitCenters(),
      ]);
      if (!mounted) return false;
      final List<AccountingPeriod> periods =
          (results[1] as List<AccountingPeriod>).toList()
            ..sort((a, b) => b.startsOn.compareTo(a.startsOn));
      setState(() {
        _accounts = (results[0] as PagedResult<LedgerAccount>).items;
        // A closed period will not accept a posting, so it is not offered.
        _periods = periods.where((period) => period.status == 'OPEN').toList();
        _journalTypes = (results[2] as List<FinanceTypeRef>)
            .where((type) => type.isActive)
            .toList();
        _voucherTypes = (results[3] as List<FinanceTypeRef>)
            .where((type) => type.isActive)
            .toList();
        _costCenters = (results[4] as PagedResult<FinanceCentre>)
            .items
            .where((centre) => centre.isActive)
            .toList();
        _profitCenters = (results[5] as PagedResult<FinanceCentre>)
            .items
            .where((centre) => centre.isActive)
            .toList();
      });
      return true;
    } on ApiException catch (exception) {
      if (!mounted) return false;
      setState(() => _error = exception.message);
      return false;
    }
  }

  Future<void> _createEntry() async {
    setState(() => _loading = true);
    final bool ready = await _loadEditorReferences();
    if (mounted) setState(() => _loading = false);
    if (!ready || !mounted) return;
    if (_periods.isEmpty) {
      setState(() => _error =
          'There is no open accounting period to post into. Open one first.');
      return;
    }
    final JournalEntry? created = await showDocument<JournalEntry>(
      context,
      title: 'New journal entry',
      builder: (_) => JournalEntryDialog(
        api: widget.api,
        accounts: _accounts,
        periods: _periods,
        journalTypes: _journalTypes,
        voucherTypes: _voucherTypes,
        costCenters: _costCenters,
        profitCenters: _profitCenters,
      ),
    );
    if (created == null || !mounted) return;
    await _load(requestedPage: 1);
    if (!mounted) return;
    NotificationService.show(
      context,
      'Journal entry ${created.referenceNumber} saved as a draft. '
      'Post it to put it in the ledger.',
      kind: AppNotificationKind.success,
    );
  }

  Future<void> _editSelected() async {
    final JournalEntry? entry = _selected;
    if (entry == null || !entry.isManualDraft) return;
    setState(() => _loading = true);
    final bool ready = await _loadEditorReferences();
    if (mounted) setState(() => _loading = false);
    if (!ready || !mounted) return;
    final JournalEntry? saved = await showDocument<JournalEntry>(
      context,
      title: 'Edit journal entry',
      builder: (_) => JournalEntryDialog(
        api: widget.api,
        accounts: _accounts,
        periods: _periods,
        journalTypes: _journalTypes,
        voucherTypes: _voucherTypes,
        costCenters: _costCenters,
        profitCenters: _profitCenters,
        entry: entry,
      ),
    );
    if (saved == null || !mounted) return;
    await _load();
    if (!mounted) return;
    NotificationService.show(
      context,
      'Draft ${saved.referenceNumber} saved.',
      kind: AppNotificationKind.success,
    );
  }

  Future<void> _deleteSelected() async {
    final JournalEntry? entry = _selected;
    if (entry == null || !entry.isManualDraft) return;
    final bool? confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text('Delete ${entry.referenceNumber}?'),
        content: const Text(
          'The draft goes, and its reference stays taken: a number once '
          'issued is not handed out again.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(dialogContext, true),
            child: const Text('Delete'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    try {
      await widget.api.deleteJournalEntry(entry.id);
      await _load();
      if (!mounted) return;
      NotificationService.show(
        context,
        'Draft ${entry.referenceNumber} deleted.',
        kind: AppNotificationKind.success,
      );
    } on ApiException catch (exception) {
      if (!mounted) return;
      NotificationService.show(context, exception.message,
          kind: AppNotificationKind.error);
    }
  }

  Future<void> _rejectSelected() async {
    final JournalEntry? entry = _selected;
    if (entry == null || !entry.isManualDraft) return;
    final String? reason = await askForReason(
      context,
      title: 'Reject ${entry.referenceNumber}',
      explanation: 'A rejected draft stays on record and can never be '
          'posted, edited or deleted.',
      label: 'Why it is rejected',
      confirmLabel: 'Reject',
    );
    if (reason == null || !mounted) return;
    try {
      await widget.api.rejectJournalEntry(entry.id, reason: reason);
      await _load();
      if (!mounted) return;
      NotificationService.show(
        context,
        'Draft ${entry.referenceNumber} rejected. It stays on record and '
        'cannot be posted.',
        kind: AppNotificationKind.success,
      );
    } on ApiException catch (exception) {
      if (!mounted) return;
      NotificationService.show(context, exception.message,
          kind: AppNotificationKind.error);
    }
  }

  Future<void> _postSelected() async {
    final JournalEntry? entry = _selected;
    if (entry == null) return;
    try {
      await widget.api.postJournalEntry(entry.id);
      await _load();
      if (!mounted) return;
      NotificationService.show(
        context,
        'Journal entry ${entry.referenceNumber} posted.',
        kind: AppNotificationKind.success,
      );
    } on ApiException catch (exception) {
      if (!mounted) return;
      NotificationService.show(context, exception.message,
          kind: AppNotificationKind.error);
    }
  }

  Future<void> _reverseSelected() async {
    final JournalEntry? entry = _selected;
    if (entry == null) return;
    // A reversal is a new entry, so it needs its own reference. Offering the
    // original's with a suffix is a starting point, not a rule.
    final TextEditingController reference = TextEditingController(
      // Hand journals live under JV- (D-FIN-9), and so does their reversal.
      text: entry.referenceNumber.toUpperCase().startsWith('JV-')
          ? '${entry.referenceNumber}-REV'
          : 'JV-${entry.referenceNumber}-REV',
    );
    final bool? confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Reverse journal entry'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'A posted entry is not unposted. This writes an opposite entry '
              'in the same period, and both stay in the ledger.',
              style: Theme.of(dialogContext).textTheme.bodyMedium,
            ),
            const SizedBox(height: AppSpacing.lg),
            TextField(
              controller: reference,
              decoration: const InputDecoration(
                  labelText: 'Reference for the reversal'),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(dialogContext, true),
            child: const Text('Reverse'),
          ),
        ],
      ),
    );
    final String chosen = reference.text.trim();
    reference.dispose();
    if (confirmed != true || !mounted) return;
    try {
      await widget.api.reverseJournalEntry(entry.id, {
        'reference_number': chosen,
        'accounting_period_id': entry.accountingPeriodId,
        'journal_date': entry.journalDate,
      });
      await _load();
      if (!mounted) return;
      NotificationService.show(
        context,
        'Reversal $chosen posted against ${entry.referenceNumber}.',
        kind: AppNotificationKind.success,
      );
    } on ApiException catch (exception) {
      if (!mounted) return;
      NotificationService.show(context, exception.message,
          kind: AppNotificationKind.error);
    }
  }

  /// The module that posted an entry, as a person reads it.
  static String _postedBy(JournalEntry entry) {
    if (entry.isManual) return 'By hand';
    for (final (String code, String label) in journalSourceModules) {
      if (code == entry.sourceModule) return label;
    }
    return entry.sourceModule;
  }

  void _view(JournalEntry entry) {
    setState(() => _selected = entry);
    unawaited(
      JournalEntryViewDialog.show(context, api: widget.api, entry: entry),
    );
  }

  /// Phase 2 (owner, 2026-09-27): a full-width grid, as every list -- the
  /// Period after the search, "Posted by", Columns; option C's bar carries
  /// Post, Reverse and the draft's Edit, Delete and Reject; a double-click
  /// reads the entry's lines.
  Widget _grid(BuildContext context) {
    final JournalEntry? selected = _selected;
    final bool draft = selected != null && selected.isManualDraft;
    String sourceLabel = 'All';
    for (final (String code, String label) in journalSourceModules) {
      if (code == _sourceModule) sourceLabel = label;
    }
    return LoadingOverlay(
      loading: _loading,
      child: ManagementWorkspaceLayout(
        toolbar: WorkspaceToolbar(
          actions: const [
            ToolbarAction.view,
            ToolbarAction.edit,
            ToolbarAction.delete,
            ToolbarAction.refresh,
            ToolbarAction.newItem,
          ],
          isVisible: (action) => switch (action) {
            ToolbarAction.newItem ||
            ToolbarAction.edit ||
            ToolbarAction.delete =>
              _canCreate,
            _ => true,
          },
          isEnabled: (action) =>
              !_loading &&
              switch (action) {
                ToolbarAction.view => selected != null,
                // Only a hand-written draft; a document's entry is undone by
                // undoing the document (D-FIN-2, D-FIN-15).
                ToolbarAction.edit || ToolbarAction.delete => draft,
                ToolbarAction.refresh => true,
                ToolbarAction.newItem => _canCreate,
                _ => false,
              },
          onAction: (action) {
            switch (action) {
              case ToolbarAction.view:
                if (selected != null) _view(selected);
              case ToolbarAction.edit:
                unawaited(_editSelected());
              case ToolbarAction.delete:
                unawaited(_deleteSelected());
              case ToolbarAction.refresh:
                unawaited(_load());
              case ToolbarAction.newItem:
                unawaited(_createEntry());
              default:
                break;
            }
          },
          // Period right after the search, then who posted it, then Columns.
          trailing: [
            DateRangeFilter(
              value: _period,
              onChanged: (period) {
                setState(() => _period = period);
                unawaited(_load(requestedPage: 1));
              },
            ),
            Phase2MenuChip<String>(
              key: const ValueKey('journal-source-module'),
              label: 'Posted by: $sourceLabel',
              onSelected: (value) {
                setState(() => _sourceModule = value.isEmpty ? null : value);
                unawaited(_load(requestedPage: 1));
              },
              itemBuilder: (context) => [
                const PopupMenuItem<String>(value: '', child: Text('All')),
                for (final (String code, String label) in journalSourceModules)
                  PopupMenuItem<String>(value: code, child: Text(label)),
              ],
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
            ToolbarCommand(
              id: 'post',
              label: 'Post',
              icon: Icons.post_add,
              onPressed: selected != null && selected.isDraft && _canPost
                  ? () => unawaited(_postSelected())
                  : null,
            ),
            ToolbarCommand(
              id: 'reverse',
              label: 'Reverse',
              icon: Icons.undo,
              onPressed: selected != null &&
                      selected.isPosted &&
                      selected.isManual &&
                      _canReverse
                  ? () => unawaited(_reverseSelected())
                  : null,
            ),
            ToolbarCommand(
              id: 'reject',
              label: 'Reject draft',
              icon: Icons.block_outlined,
              onPressed:
                  draft && _canPost ? () => unawaited(_rejectSelected()) : null,
            ),
          ],
        ),
        selectionBar: true,
        selection: selected == null
            ? null
            : SelectionSummary.document(
                number: selected.referenceNumber,
                party: _postedBy(selected),
                status: selected.status,
                total: selected.totalDebit,
                onClear: () => setState(() => _selected = null),
              ),
        searchPanel: SearchFilterPanel(
          controller: _search,
          hintText: 'Search by reference or description',
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
            child: _entries.isEmpty
                ? (_search.text.trim().isEmpty &&
                        _period.from == null &&
                        _sourceModule == null
                    ? const StandardEmptyState(
                        type: EmptyStateType.noRecords,
                        title: 'No journal entries',
                        message: 'Completing a goods receipt, dispatching a '
                            'delivery note or approving an invoice writes '
                            'one. You can also write one by hand.',
                      )
                    : const StandardEmptyState(
                        type: EmptyStateType.noSearchResults,
                      ))
                : EnterpriseDataGrid<JournalEntry>(
                    columns: _columns.gridColumns,
                    items: _entries,
                    id: (item) => item.id,
                    selectedId: selected?.id,
                    cells: _columns.cells,
                    onSelect: (item) => setState(() => _selected = item),
                    onOpen: _view,
                    total: _total,
                    pageOffset: (_page - 1) * _rowsPerPage,
                    rowsPerPage: _rowsPerPage,
                    onPageChanged: (offset) {
                      final int next = offset ~/ _rowsPerPage + 1;
                      if (next != _page) unawaited(_load(requestedPage: next));
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
  /// per screen on this PC (owner, 2026-09-27).
  late final ColumnChoice<JournalEntry> _columns = ColumnChoice(
    preferences: widget.preferences,
    stateKey: 'journal-entries.grid',
    columns: [
      ChoosableColumn(
        column: const GridColumn(key: 'reference', label: 'Reference'),
        cell: (item) => item.referenceNumber,
        required: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'date', label: 'Date'),
        cell: (item) => item.journalDate,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(
            key: 'description', label: 'Description', priority: 1),
        cell: (item) => item.description,
        shownByDefault: true,
      ),
      // "Who wrote this" is the first question asked of an unexpected entry.
      ChoosableColumn(
        column: const GridColumn(key: 'source', label: 'Posted By'),
        cell: _postedBy,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'status', label: 'Status'),
        cell: (item) => item.status,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'debit', label: 'Debit', numeric: true),
        cell: (item) => item.totalDebit,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'credit', label: 'Credit', numeric: true),
        cell: (item) => item.totalCredit,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'posted', label: 'Posted At'),
        cell: (item) => createdStamp(item.postedAt),
      ),
    ],
  );

  @override
  Widget build(BuildContext context) {
    if (!_canView) {
      return const StandardEmptyState(
        type: EmptyStateType.noPermissions,
        title: 'Journal entries',
        message: 'You do not have permission to view the journal.',
      );
    }
    if (!widget.hasActiveFirm) {
      return const StandardEmptyState(
        type: EmptyStateType.noFirmSelected,
        title: 'Journal entries',
        message: 'Choose a firm to see its journal.',
      );
    }
    if (Phase2Scope.of(context)) return _grid(context);
    final JournalEntry? selected = _selected;
    return LoadingOverlay(
      loading: _loading,
      child: Column(children: [
        Padding(
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: Row(children: [
            Expanded(
              child: TextField(
                controller: _search,
                decoration: const InputDecoration(
                  labelText: 'Search by reference or description',
                  prefixIcon: Icon(Icons.search),
                ),
                onSubmitted: (_) => _load(requestedPage: 1),
              ),
            ),
            const SizedBox(width: AppSpacing.md),
            SizedBox(
              width: 220,
              child: DropdownButtonFormField<String?>(
                key: const ValueKey('journal-source-module'),
                initialValue: _sourceModule,
                isExpanded: true,
                decoration: const InputDecoration(labelText: 'Posted by'),
                items: [
                  const DropdownMenuItem<String?>(
                    value: null,
                    child: Text('All'),
                  ),
                  for (final (String code, String label)
                      in journalSourceModules)
                    DropdownMenuItem<String?>(
                      value: code,
                      child: Text(label, overflow: TextOverflow.ellipsis),
                    ),
                ],
                onChanged: (value) {
                  setState(() => _sourceModule = value);
                  unawaited(_load(requestedPage: 1));
                },
              ),
            ),
            const SizedBox(width: AppSpacing.md),
            // The lines -- accounts, debits, credits -- were nowhere on this
            // screen (plan item 10.9). Double-clicking a row does the same.
            OutlinedButton.icon(
              onPressed: selected == null
                  ? null
                  : () => unawaited(
                        JournalEntryViewDialog.show(
                          context,
                          api: widget.api,
                          entry: selected,
                        ),
                      ),
              icon: const Icon(Icons.visibility_outlined),
              label: const Text('View'),
            ),
            const SizedBox(width: AppSpacing.sm),
            if (_canPost)
              FilledButton.tonalIcon(
                // Only a draft can be posted, and only what is selected.
                onPressed: selected != null && selected.isDraft
                    ? () => unawaited(_postSelected())
                    : null,
                icon: const Icon(Icons.post_add),
                label: const Text('Post'),
              ),
            const SizedBox(width: AppSpacing.sm),
            if (_canReverse)
              OutlinedButton.icon(
                // Only a hand-written entry. One a document posted is undone
                // by cancelling or returning that document, which takes its
                // stock and balances back with it; the server refuses the
                // rest (D-FIN-2).
                onPressed:
                    selected != null && selected.isPosted && selected.isManual
                        ? () => unawaited(_reverseSelected())
                        : null,
                icon: const Icon(Icons.undo),
                label: const Text('Reverse'),
              ),
            // Edit, delete and reject a hand-written draft (D-FIN-15), kept
            // in one menu so the toolbar still fits the narrowest window.
            if (_canCreate || _canPost)
              PopupMenuButton<String>(
                key: const ValueKey('journal-draft-actions'),
                tooltip: 'Draft actions',
                enabled: selected != null && selected.isManualDraft,
                icon: const Icon(Icons.more_vert),
                onSelected: (action) => unawaited(switch (action) {
                  'edit' => _editSelected(),
                  'delete' => _deleteSelected(),
                  _ => _rejectSelected(),
                }),
                itemBuilder: (_) => [
                  if (_canCreate)
                    const PopupMenuItem<String>(
                      value: 'edit',
                      child: Text('Edit draft'),
                    ),
                  if (_canCreate)
                    const PopupMenuItem<String>(
                      value: 'delete',
                      child: Text('Delete draft'),
                    ),
                  if (_canPost)
                    const PopupMenuItem<String>(
                      value: 'reject',
                      child: Text('Reject draft'),
                    ),
                ],
              ),
            const SizedBox(width: AppSpacing.sm),
            if (_canCreate)
              FilledButton.icon(
                onPressed: () => unawaited(_createEntry()),
                icon: const Icon(Icons.add),
                label: const Text('New Entry'),
              ),
          ]),
        ),
        if (_error != null)
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg),
            child: MaterialBanner(
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
          child: _entries.isEmpty
              ? const StandardEmptyState(
                  type: EmptyStateType.noRecords,
                  title: 'No journal entries',
                  message:
                      'Completing a goods receipt, dispatching a delivery note '
                      'or approving an invoice writes one. You can also write '
                      'one by hand.',
                )
              : ListView.separated(
                  itemCount: _entries.length,
                  separatorBuilder: (_, __) => const Divider(height: 1),
                  itemBuilder: (context, index) {
                    final JournalEntry entry = _entries[index];
                    return GestureDetector(
                      onDoubleTap: () => unawaited(
                        JournalEntryViewDialog.show(
                          context,
                          api: widget.api,
                          entry: entry,
                        ),
                      ),
                      child: ListTile(
                        selected: entry.id == selected?.id,
                        title: Text(
                            '${entry.referenceNumber}  ·  ${entry.journalDate}'),
                        subtitle: Text(
                          entry.description.isEmpty
                              ? (entry.isManual
                                  ? 'Written by hand'
                                  : 'Posted by ${entry.sourceModule}')
                              : entry.description,
                        ),
                        trailing:
                            Row(mainAxisSize: MainAxisSize.min, children: [
                          Text(entry.totalDebit),
                          const SizedBox(width: AppSpacing.md),
                          StatusBadge(label: entry.status),
                        ]),
                        onTap: () => setState(() => _selected = entry),
                      ),
                    );
                  },
                ),
        ),
        WorkspacePager(
          page: _page,
          pageSize: _rowsPerPage,
          total: _total,
          onPageChanged: (next) => unawaited(_load(requestedPage: next)),
        ),
      ]),
    );
  }
}
