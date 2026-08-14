import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/entities.dart';
import '../../models/finance.dart';
import '../workspace/desktop_framework.dart';
import 'journal_entry_dialog.dart';

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
    required this.permissions,
    required this.hasActiveFirm,
  });

  final ApiClient api;
  final PermissionService permissions;
  final bool hasActiveFirm;

  @override
  State<JournalEntriesPage> createState() => _JournalEntriesPageState();
}

class _JournalEntriesPageState extends State<JournalEntriesPage> {
  static const int _rowsPerPage = 20;
  final TextEditingController _search = TextEditingController();
  List<JournalEntry> _entries = const [];
  JournalEntry? _selected;
  int _page = 1;
  int _total = 0;
  bool _loading = false;
  String? _error;

  // Loaded only when the editor is opened: an entry cannot be written without
  // them, and nobody reading the list needs them.
  List<LedgerAccount> _accounts = const [];
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
      );
      if (!mounted) return;
      setState(() {
        _entries = result.items;
        _total = result.total;
        _selected = result.items.isEmpty
            ? null
            : result.items.firstWhere(
                (entry) => entry.id == _selected?.id,
                orElse: () => result.items.first,
              );
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
        widget.api.ledgerAccounts(isActive: true),
        widget.api.accountingPeriods(),
        widget.api.journalTypes(),
        widget.api.voucherTypes(),
      ]);
      if (!mounted) return false;
      final List<AccountingPeriod> periods =
          (results[1] as List<AccountingPeriod>).toList()
            ..sort((a, b) => b.startsOn.compareTo(a.startsOn));
      setState(() {
        _accounts = (results[0] as PagedResult<LedgerAccount>).items;
        // A closed period will not accept a posting, so it is not offered.
        _periods = periods.where((period) => period.status == 'OPEN').toList();
        _journalTypes = results[2] as List<FinanceTypeRef>;
        _voucherTypes = results[3] as List<FinanceTypeRef>;
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
    final JournalEntry? created = await showDialog<JournalEntry>(
      context: context,
      barrierDismissible: false,
      builder: (_) => JournalEntryDialog(
        api: widget.api,
        accounts: _accounts,
        periods: _periods,
        journalTypes: _journalTypes,
        voucherTypes: _voucherTypes,
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
    final TextEditingController reference =
        TextEditingController(text: '${entry.referenceNumber}-REV');
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
              decoration: const InputDecoration(labelText: 'Reference for the reversal'),
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
                onPressed: selected != null && selected.isPosted
                    ? () => unawaited(_reverseSelected())
                    : null,
                icon: const Icon(Icons.undo),
                label: const Text('Reverse'),
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
                    return ListTile(
                      selected: entry.id == selected?.id,
                      title: Text('${entry.referenceNumber}  ·  ${entry.journalDate}'),
                      subtitle: Text(
                        entry.description.isEmpty
                            ? (entry.isManual
                                ? 'Written by hand'
                                : 'Posted by ${entry.sourceModule}')
                            : entry.description,
                      ),
                      trailing: Row(mainAxisSize: MainAxisSize.min, children: [
                        Text(entry.totalDebit),
                        const SizedBox(width: AppSpacing.md),
                        StatusBadge(label: entry.status),
                      ]),
                      onTap: () => setState(() => _selected = entry),
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
