import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/branch_warehouse.dart';
import '../../models/entities.dart';
import '../../models/sales_return.dart';
import '../workspace/desktop_framework.dart';
import 'sales_return_editor_dialog.dart';

/// Goods coming back from a customer.
///
/// The list is deliberately blunt about which of the three books have moved.
/// A draft or an approved return has taken nothing back and credited nobody;
/// completing it puts the stock on the shelf, drops what the customer owes and
/// writes both journals at once. Somebody looking at a screenful of returns
/// needs to know which of them have actually happened.
class SalesReturnManagementPage extends StatefulWidget {
  const SalesReturnManagementPage({
    super.key,
    required this.api,
    required this.permissions,
    required this.hasActiveFirm,
    this.today,
  });

  final ApiClient api;
  final PermissionService permissions;
  final bool hasActiveFirm;

  /// Overridable so a test can pin the date a new return carries.
  final DateTime? today;

  @override
  State<SalesReturnManagementPage> createState() =>
      _SalesReturnManagementPageState();
}

class _SalesReturnManagementPageState extends State<SalesReturnManagementPage> {
  static const int _rowsPerPage = 20;
  final TextEditingController _search = TextEditingController();
  List<SalesReturn> _returns = const [];
  SalesReturn? _selected;
  int _page = 1;
  int _total = 0;
  bool _loading = false;
  String? _error;

  bool get _canView => widget.permissions.hasPermission('SALES_VIEW');

  /// `SALES_RETURN` is the code the server gates raising one on. It has been
  /// seeded since the identity seed was written and enforced nowhere until the
  /// document existed.
  bool get _canRaise => widget.permissions.hasPermission('SALES_RETURN');
  bool get _canApprove => widget.permissions.hasPermission('SALES_APPROVE');
  bool get _canCancel => widget.permissions.hasPermission('SALES_CANCEL');

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
      final PagedResult<SalesReturn> result = await widget.api.salesReturns(
        page: _page,
        pageSize: _rowsPerPage,
        search: _search.text.trim(),
      );
      if (!mounted) return;
      setState(() {
        _returns = result.items;
        _total = result.total;
        // Keep the open return selected across a reload, unless it fell off
        // the page -- reading a document that just changed is the common case.
        final String? selectedId = _selected?.id;
        _selected = selectedId == null
            ? null
            : result.items.where((item) => item.id == selectedId).firstOrNull;
      });
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() {
        _error = exception.message;
        _returns = const [];
        _total = 0;
      });
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _raiseReturn() async {
    setState(() => _loading = true);
    List<ReturnableDocument> documents = const [];
    List<WarehouseRecord> warehouses = const [];
    try {
      final List<dynamic> results = await Future.wait<dynamic>([
        widget.api.returnableDocuments(),
        widget.api.warehouses(page: 1, pageSize: 100),
      ]);
      documents = results[0] as List<ReturnableDocument>;
      warehouses = (results[1] as PagedResult<WarehouseRecord>).items;
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() => _error = exception.message);
      return;
    } finally {
      if (mounted) setState(() => _loading = false);
    }
    if (!mounted) return;
    final Json? payload = await showDialog<Json>(
      context: context,
      barrierDismissible: false,
      builder: (_) => SalesReturnEditorDialog(
        documents: documents,
        warehouses: warehouses,
        today: widget.today ?? DateTime.now(),
      ),
    );
    if (payload == null) return;
    try {
      final SalesReturn created = await widget.api.createSalesReturn(payload);
      if (!mounted) return;
      NotificationService.show(
        context,
        '${created.returnNumber} created as a draft. Approving and completing '
        'it is what takes the goods back and credits the customer.',
        kind: AppNotificationKind.success,
      );
      await _load(requestedPage: 1);
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() => _error = exception.message);
    }
  }

  Future<void> _act(SalesReturn row, String action, {String? reason}) async {
    setState(() => _loading = true);
    try {
      final SalesReturn updated =
          await widget.api.salesReturnAction(row.id, action, reason: reason);
      if (!mounted) return;
      setState(() => _selected = updated);
      NotificationService.show(
        context,
        _outcome(action, updated),
        kind: AppNotificationKind.success,
      );
      await _load();
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() => _error = exception.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  /// Say what the action did, not that it succeeded.
  ///
  /// Completing a return is the only irreversible-feeling step in the flow and
  /// it moves three things at once; "Completed" tells nobody which.
  String _outcome(String action, SalesReturn row) => switch (action) {
        'approve' => '${row.returnNumber} approved. Nothing has moved yet — '
            'completing it takes the goods back.',
        'complete' =>
          '${row.returnNumber} completed: ${row.totalRestockQuantity} back on '
              'the shelf and ${row.grandTotal} credited to the customer.',
        'cancel' => '${row.returnNumber} cancelled. The stock, the customer’s '
            'balance and both journals have been put back.',
        'close' => '${row.returnNumber} closed.',
        _ => '${row.returnNumber} updated.',
      };

  Future<void> _cancel(SalesReturn row) async {
    final String? reason = await showDialog<String>(
      context: context,
      builder: (_) => _CancelReasonDialog(returnNumber: row.returnNumber),
    );
    if (reason == null) return;
    await _act(row, 'cancel', reason: reason);
  }

  @override
  Widget build(BuildContext context) {
    if (!_canView) {
      return const StandardEmptyState(
        type: EmptyStateType.noPermissions,
        title: 'Sales returns',
        message: 'You do not have permission to view sales documents.',
      );
    }
    if (!widget.hasActiveFirm) {
      return const StandardEmptyState(
        type: EmptyStateType.noFirmSelected,
        title: 'Sales returns',
        message: 'Choose a firm to see the goods coming back to it.',
      );
    }
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
                  labelText: 'Search by return number',
                  prefixIcon: Icon(Icons.search),
                  hintText: 'SR-…',
                ),
                onSubmitted: (_) => unawaited(_load(requestedPage: 1)),
              ),
            ),
            const SizedBox(width: AppSpacing.md),
            if (_canRaise)
              FilledButton.icon(
                onPressed: () => unawaited(_raiseReturn()),
                icon: const Icon(Icons.assignment_return_outlined),
                label: const Text('New Return'),
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
          child: _returns.isEmpty
              ? const StandardEmptyState(
                  type: EmptyStateType.noRecords,
                  title: 'Nothing has come back',
                  message: 'A sales return is raised against a delivery note '
                      'or a sales invoice. Completing one puts the goods back '
                      'on the shelf and credits what the customer owes.',
                )
              : Row(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                  Expanded(flex: 3, child: _list()),
                  const VerticalDivider(width: 1),
                  Expanded(flex: 4, child: _detail(context)),
                ]),
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

  Widget _list() => ListView.separated(
        itemCount: _returns.length,
        separatorBuilder: (_, __) => const Divider(height: 1),
        itemBuilder: (context, index) {
          final SalesReturn row = _returns[index];
          return ListTile(
            selected: row.id == _selected?.id,
            title: Text('${row.returnNumber}  ·  ${row.returnDate}'),
            // Whether it has actually happened is the thing a list of returns
            // has to answer; the status word alone does not say it.
            subtitle: Text(
              row.hasMoved
                  ? '${row.totalRestockQuantity} restocked · '
                      '${row.grandTotal} credited'
                  : '${row.totalCurrentReturnQuantity} awaiting completion',
            ),
            trailing: StatusBadge(label: row.status),
            onTap: () => setState(() => _selected = row),
          );
        },
      );

  Widget _detail(BuildContext context) {
    final SalesReturn? row = _selected;
    if (row == null) {
      return const StandardEmptyState(
        type: EmptyStateType.noRecords,
        title: 'No return selected',
        message: 'Choose a return to see what came back and what it credited.',
      );
    }
    return SingleChildScrollView(
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(children: [
            Expanded(
              child: Text(row.returnNumber,
                  style: Theme.of(context).textTheme.titleMedium),
            ),
            StatusBadge(label: row.status),
          ]),
          if (row.customerReturnNumber.isNotEmpty)
            Text('Their reference: ${row.customerReturnNumber}',
                style: Theme.of(context).textTheme.bodySmall),
          if (row.returnReason.isNotEmpty)
            Text(row.returnReason, style: Theme.of(context).textTheme.bodySmall),
          const SizedBox(height: AppSpacing.md),
          _whatMoved(context, row),
          const SizedBox(height: AppSpacing.md),
          _lines(context, row),
          const SizedBox(height: AppSpacing.md),
          _actions(row),
        ],
      ),
    );
  }

  /// The three books, and whether each has moved.
  Widget _whatMoved(BuildContext context, SalesReturn row) => Card(
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.md),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('What this moves',
                  style: Theme.of(context).textTheme.labelLarge),
              const SizedBox(height: AppSpacing.sm),
              _fact(
                context,
                'Stock',
                '${row.totalRestockQuantity} of '
                    '${row.totalCurrentReturnQuantity} back on the shelf',
                done: row.hasMoved,
              ),
              _fact(
                context,
                'Customer',
                '${row.grandTotal} credited '
                    '(${row.subtotal} + ${row.taxTotal} tax)',
                done: row.hasMoved,
              ),
              _fact(
                context,
                'Ledger',
                row.journalEntryId.isEmpty && row.hasMoved
                    // A return worth nothing has nothing to say to the ledger,
                    // which is a fact rather than a failure.
                    ? 'nothing to post — this return is worth nothing'
                    : 'credit and cost posted',
                done: row.hasMoved,
              ),
              if (row.cancelReason.isNotEmpty) ...[
                const SizedBox(height: AppSpacing.sm),
                Text('Cancelled: ${row.cancelReason}',
                    style: Theme.of(context).textTheme.bodySmall),
              ],
            ],
          ),
        ),
      );

  Widget _fact(BuildContext context, String label, String value,
          {required bool done}) =>
      Padding(
        padding: const EdgeInsets.symmetric(vertical: 2),
        child: Row(children: [
          Icon(
            done ? Icons.check_circle_outline : Icons.schedule,
            size: 16,
            color: Theme.of(context).colorScheme.outline,
          ),
          const SizedBox(width: AppSpacing.sm),
          SizedBox(width: 76, child: Text(label)),
          Expanded(
            child: Text(value, style: Theme.of(context).textTheme.bodySmall),
          ),
        ]),
      );

  Widget _lines(BuildContext context, SalesReturn row) => Card(
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.md),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Lines', style: Theme.of(context).textTheme.labelLarge),
              const SizedBox(height: AppSpacing.sm),
              for (final SalesReturnLine line in row.lines)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 4),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(line.description.isEmpty
                          ? 'Line ${line.lineNumber}'
                          : line.description),
                      Text(
                        '${line.currentReturnQuantity} returned · '
                        '${line.restockQuantity} sellable · '
                        'from ${line.sourceDocumentNumber} '
                        'line ${line.sourceDocumentLineNumber} · '
                        '${line.pendingQuantity} still returnable',
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                    ],
                  ),
                ),
            ],
          ),
        ),
      );

  Widget _actions(SalesReturn row) => Wrap(
        spacing: AppSpacing.sm,
        children: [
          if (row.isDraft && _canApprove)
            FilledButton(
              onPressed: () => unawaited(_act(row, 'approve')),
              child: const Text('Approve'),
            ),
          if (row.isApproved && _canApprove)
            FilledButton(
              onPressed: () => unawaited(_act(row, 'complete')),
              child: const Text('Complete'),
            ),
          if (row.isCompleted && _canApprove)
            OutlinedButton(
              onPressed: () => unawaited(_act(row, 'close')),
              child: const Text('Close'),
            ),
          if (!row.isCancelled && !row.isClosed && _canCancel)
            TextButton(
              onPressed: () => unawaited(_cancel(row)),
              child: const Text('Cancel'),
            ),
        ],
      );
}

/// Why a return is being cancelled.
///
/// Asked for rather than optional: cancelling a completed return takes stock
/// off the shelf again and puts a balance back on a customer's account, and
/// the person who finds it later needs to know why.
class _CancelReasonDialog extends StatefulWidget {
  const _CancelReasonDialog({required this.returnNumber});

  final String returnNumber;

  @override
  State<_CancelReasonDialog> createState() => _CancelReasonDialogState();
}

class _CancelReasonDialogState extends State<_CancelReasonDialog> {
  final TextEditingController _reason = TextEditingController();

  @override
  void initState() {
    super.initState();
    // Without this the confirm button never enables: it is disabled until a
    // reason is typed, and typing alone does not rebuild the dialog. Caught by
    // the test, which could not cancel a return however much it typed.
    _reason.addListener(() => setState(() {}));
  }

  @override
  void dispose() {
    _reason.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: Text('Cancel ${widget.returnNumber}'),
        content: Column(mainAxisSize: MainAxisSize.min, children: [
          const Text(
            'If it was completed, the stock comes back off the shelf, the '
            'customer owes it again and both journals are reversed.',
          ),
          const SizedBox(height: AppSpacing.md),
          TextField(
            controller: _reason,
            autofocus: true,
            decoration: const InputDecoration(labelText: 'Reason'),
          ),
        ]),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Keep it'),
          ),
          FilledButton(
            onPressed: _reason.text.trim().isEmpty
                ? null
                : () => Navigator.of(context).pop(_reason.text.trim()),
            child: const Text('Cancel return'),
          ),
        ],
      );
}
