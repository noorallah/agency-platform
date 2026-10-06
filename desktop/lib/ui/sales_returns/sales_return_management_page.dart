import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/preferences/desktop_preferences_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/branch_warehouse.dart';
import '../../models/bulk_action.dart';
import '../../models/entities.dart';
import '../../models/sales_return.dart';
import '../../phase2/document_page.dart';
import '../../phase2/indian_format.dart';
import '../document_framework/document_steps.dart';
import '../workspace/bulk_action.dart';
import '../../models/document_file.dart';
import '../purchases/document_attachments_dialog.dart';
import '../workspace/desktop_framework.dart';
import '../workspace/reason_prompt.dart';
import '../workspace/printed_document.dart';
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
    required this.preferences,
    required this.permissions,
    required this.hasActiveFirm,
    this.today,
  });

  final ApiClient api;

  /// Where the grid's chosen columns are remembered.
  final DesktopPreferencesService preferences;
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

  /// The return dates the list is narrowed to (owner, 2026-09-27).
  DatePeriod _period = const DatePeriod.all();
  List<SalesReturn> _returns = const [];
  SalesReturn? _selected;

  /// The rows ticked for a bulk approve or cancel (backlog 56 A).
  Set<String> _ticked = <String>{};
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
        returnFrom: _period.from == null ? null : DatePeriod.iso(_period.from!),
        returnTo: _period.to == null ? null : DatePeriod.iso(_period.to!),
      );
      if (!mounted) return;
      setState(() {
        _returns = result.items;
        _total = result.total;
        _ticked = _ticked
            .where((id) => result.items.any((item) => item.id == id))
            .toSet();
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
    final Json? payload = await showDocument<Json>(
      context,
      title: 'New sales return',
      builder: (_) => SalesReturnEditorDialog(
        documents: documents,
        warehouses: warehouses,
        today: widget.today ?? DateTime.now(),
        loadSerials: (document, line) => widget.api.returnableSerials(
          sourceType: document.sourceType.code,
          sourceLineId: line.id,
        ),
        preview: widget.api.previewSalesReturn,
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

  /// The return's next steps -- Approve, Complete, Close, Cancel -- as its
  /// own window offers them too (D-BUY-22): one definition, so the bar and
  /// the window cannot disagree about one return. Raising is `SALES_RETURN`;
  /// these are `SALES_APPROVE`, and cancelling `SALES_CANCEL` with a reason.
  late final List<DocumentStep<SalesReturn>> _steps = [
    _lifecycleStep('approve', 'Approve', Icons.check_circle_outline,
        allows: (row) => row.isDraft, forward: true),
    _lifecycleStep('complete', 'Complete', Icons.done_all,
        allows: (row) => row.isApproved, forward: true),
    _lifecycleStep('close', 'Close', Icons.lock_outline,
        allows: (row) => row.isCompleted),
    DocumentStep<SalesReturn>(
      id: 'cancel',
      label: 'Cancel',
      icon: Icons.cancel_outlined,
      permitted: _canCancel,
      allows: (row) => !row.isCancelled && !row.isClosed,
      run: (context, row) async {
        final String? reason = await showDialog<String>(
          context: context,
          builder: (_) => _CancelReasonDialog(returnNumber: row.returnNumber),
        );
        if (reason == null) return null;
        return _call(row, 'cancel', reason: reason);
      },
    ),
  ];

  DocumentStep<SalesReturn> _lifecycleStep(
    String id,
    String label,
    IconData icon, {
    required bool Function(SalesReturn row) allows,
    bool forward = false,
  }) =>
      DocumentStep<SalesReturn>(
        id: id,
        label: label,
        icon: icon,
        permitted: _canApprove,
        forward: forward,
        allows: allows,
        run: (context, row) => _call(row, id),
      );

  DocumentStep<SalesReturn> _step(String id) =>
      _steps.firstWhere((step) => step.id == id);

  /// Call [action] on [row] and say what it did. A refusal is thrown, for
  /// whichever window or bar ran it to show where it shows refusals.
  Future<DocumentStepDone> _call(
    SalesReturn row,
    String action, {
    String? reason,
  }) async {
    final SalesReturn updated =
        await widget.api.salesReturnAction(row.id, action, reason: reason);
    // Past 30 November the credit no longer reduces tax (GST-1): said when
    // it is approved and when it is completed, before the credit posts.
    final String late = action == 'approve' || action == 'complete'
        ? updated.timeLimitWarning
        : '';
    return DocumentStepDone(
      '${_outcome(action, updated)}${late.isEmpty ? '' : ' $late'}',
      warning: late.isNotEmpty,
      step: action,
    );
  }

  /// Take a step against [row] from the bar. A refusal goes to the banner
  /// above the list, as it always has here.
  Future<void> _runStep(DocumentStep<SalesReturn> step, SalesReturn row) async {
    try {
      final DocumentStepDone? done = await step.run(context, row);
      if (done == null || !mounted) return;
      setState(() => _loading = true);
      showStepDone(context, done);
      await _load();
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() => _error = exception.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _act(SalesReturn row, String action) =>
      _runStep(_step(action), row);

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

  Future<void> _cancel(SalesReturn row) => _runStep(_step('cancel'), row);

  /// The minute a return was made, or nothing when the server said nothing.
  /// The customer as the list shows them: name, then code.
  String _customer(SalesReturn row) => [
        if (row.customerName.isNotEmpty) row.customerName,
        if (row.customerCode.isNotEmpty) row.customerCode,
      ].join('  ·  ');

  String _stamp(String createdAt) {
    final String stamp = createdStamp(createdAt);
    return stamp.isEmpty ? '' : '  ·  made $stamp';
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
    if (Phase2Scope.of(context)) return _grid(context);
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

  /// Phase 2 (owner, 2026-09-27): a full-width grid, as Sales Orders,
  /// Invoices and Delivery Notes -- the Period after the search, Columns,
  /// option C's bar naming the picked return with its steps, and a
  /// double-click to read it. The side pane went: it took more width than
  /// the list to show a return somebody had only pointed at.
  /// More than one row ticked: the bar names the batch and offers the two
  /// bulk actions instead of the one row's steps.
  bool get _bulkMode => _ticked.length > 1;

  List<SalesReturn> get _tickedRows =>
      _returns.where((row) => _ticked.contains(row.id)).toList();

  List<BulkRow> _bulkRows() => [
        for (final SalesReturn row in _tickedRows) (id: row.id, version: null),
      ];

  SelectionSummary _bulkSummary() {
    double total = 0;
    for (final SalesReturn row in _tickedRows) {
      total += double.tryParse(row.grandTotal) ?? 0;
    }
    return SelectionSummary(
      title: '${_ticked.length} selected',
      detail: indianAmount(total, full: true),
      onClear: () => setState(() => _ticked = <String>{}),
    );
  }

  /// The two bulk actions, each behind the permission the single one takes.
  List<ToolbarCommand> _bulkCommands() => [
        ToolbarCommand(
          id: 'bulk-approve',
          label: 'Approve selected',
          icon: Icons.check_circle_outline,
          onPressed: _loading || !_canApprove
              ? null
              : () => unawaited(_bulkApprove()),
        ),
        ToolbarCommand(
          id: 'cancel',
          label: 'Cancel selected',
          icon: Icons.cancel_outlined,
          onPressed: _loading || !_canCancel
              ? null
              : () => unawaited(_bulkCancel()),
        ),
      ];

  Future<void> _bulkApprove() async {
    final List<BulkRow> rows = _bulkRows();
    await runBulkAction(
      context,
      verb: 'Approved',
      rows: rows,
      send: widget.api.bulkApproveSalesReturns,
    );
    await _afterBulk();
  }

  Future<void> _bulkCancel() async {
    final List<BulkRow> rows = _bulkRows();
    final String? reason = await askForReason(
      context,
      title: 'Cancel ${rows.length} returns',
      explanation: 'Each return is cancelled on its own; one the server '
          'refuses does not stop the others. The reason is recorded on '
          'every return cancelled.',
      confirmLabel: 'Cancel returns',
    );
    if (reason == null || !mounted) return;
    await runBulkAction(
      context,
      verb: 'Cancelled',
      rows: rows,
      send: (rows) => widget.api.bulkCancelSalesReturns(rows, reason),
    );
    await _afterBulk();
  }

  Future<void> _afterBulk() async {
    if (!mounted) return;
    setState(() => _ticked = <String>{});
    await _load();
  }

  Widget _grid(BuildContext context) {
    final SalesReturn? selected = _selected;
    ToolbarCommand command(String id) => _step(id).command(
          selected,
          (step, row) => unawaited(_runStep(step, row)),
        );
    return LoadingOverlay(
      loading: _loading,
      child: ManagementWorkspaceLayout(
        toolbar: WorkspaceToolbar(
          actions: const [
            ToolbarAction.newItem,
            ToolbarAction.view,
            ToolbarAction.refresh,
          ],
          isVisible: (action) => action != ToolbarAction.newItem || _canRaise,
          isEnabled: (action) =>
              !_loading &&
              switch (action) {
                ToolbarAction.newItem => _canRaise,
                ToolbarAction.view => selected != null && !_bulkMode,
                ToolbarAction.refresh => true,
                _ => false,
              },
          onAction: (action) {
            switch (action) {
              case ToolbarAction.newItem:
                unawaited(_raiseReturn());
              case ToolbarAction.view:
                if (selected != null) unawaited(_openReturn(selected));
              case ToolbarAction.refresh:
                unawaited(_load());
              default:
                break;
            }
          },
          // Period right after the search, then Columns (owner).
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
          commands: _bulkMode
              ? _bulkCommands()
              : [
            ToolbarCommand(
              id: 'print-credit-note',
              label: 'Print credit note',
              icon: Icons.print_outlined,
              onPressed: selected == null
                  ? null
                  : () => unawaited(_printCreditNote(selected)),
            ),
            ToolbarCommand(
              id: 'attachments',
              label: 'Attachments',
              icon: Icons.attach_file,
              onPressed: selected == null
                  ? null
                  : () => unawaited(
                        showDocumentAttachments(
                          context,
                          api: widget.api,
                          kind: AttachableDocument.salesReturn,
                          documentId: selected.id,
                          subtitle: selected.returnNumber,
                          canEdit: widget.permissions.hasPermission('SALES_UPDATE'),
                        ),
                      ),
            ),
            command('approve'),
            command('complete'),
            command('close'),
            command('cancel'),
          ],
        ),
        selectionBar: true,
        selection: _bulkMode
            ? _bulkSummary()
            : selected == null
            ? null
            : SelectionSummary.document(
                number: selected.returnNumber,
                party: selected.customerName,
                status: selected.status,
                total: selected.grandTotal,
                onClear: () => setState(() => _selected = null),
              ),
        searchPanel: SearchFilterPanel(
          controller: _search,
          hintText: 'Search number or customer',
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
            // Nothing yet while the first read is out: the thin bar says it is
            // loading, and "nothing here" would be a claim not yet known.
            child: _loading && _returns.isEmpty
                ? const SizedBox.shrink()
                : _returns.isEmpty
                ? (_search.text.trim().isEmpty && _period.from == null
                    ? const StandardEmptyState(
                        type: EmptyStateType.noRecords,
                        title: 'Nothing has come back',
                        message: 'A sales return is raised against a delivery '
                            'note or a sales invoice. Completing one puts the '
                            'goods back on the shelf and credits what the '
                            'customer owes.',
                      )
                    : const StandardEmptyState(
                        type: EmptyStateType.noSearchResults,
                      ))
                : EnterpriseDataGrid<SalesReturn>(
                    columns: _columns.gridColumns,
                    items: _returns,
                    id: (item) => item.id,
                    selectedId: selected?.id,
                    // Ticks, for a bulk approve or cancel. A single row is
                    // still chosen by clicking it.
                    selectedIds: _ticked,
                    onSelectionChanged: (ticked) =>
                        setState(() => _ticked = ticked),
                    cells: _columns.cells,
                    onSelect: (item) => setState(() => _selected = item),
                    onOpen: (item) => unawaited(_openReturn(item)),
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
  late final ColumnChoice<SalesReturn> _columns = ColumnChoice(
    preferences: widget.preferences,
    stateKey: 'sales-returns.grid',
    columns: [
      ChoosableColumn(
        column: const GridColumn(key: 'number', label: 'Return Number'),
        cell: (item) => item.returnNumber,
        required: true,
      ),
      // A customer's PO scan or a signed challan kept with it (SG-6).
      ChoosableColumn(
        column: const GridColumn(key: 'files', label: 'Files'),
        cell: (item) => documentFilesCell(item.attachedFileCount),
        shownByDefault: true,
      ),
      // Whose return it is; kept at any width.
      ChoosableColumn(
        column:
            const GridColumn(key: 'customer', label: 'Customer', priority: 1),
        cell: (item) => item.customerName,
        shownByDefault: true,
      ),
      // One date: the return's, with the minute it was entered.
      ChoosableColumn(
        column: const GridColumn(key: 'date', label: 'Return Date'),
        cell: (item) => documentDateStamp(item.returnDate, item.createdAt),
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'reference', label: 'Their Reference'),
        cell: (item) => item.customerReturnNumber,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'reason', label: 'Reason'),
        cell: (item) => item.returnReason,
      ),
      ChoosableColumn(
        column: const GridColumn(
            key: 'returned', label: 'Quantity Returned', numeric: true),
        cell: (item) => item.totalCurrentReturnQuantity,
        shownByDefault: true,
      ),
      // Whether it has actually happened is what a list of returns has to
      // answer: nothing is restocked until the return is completed.
      ChoosableColumn(
        column: const GridColumn(
            key: 'restocked', label: 'Restocked', numeric: true),
        cell: (item) => item.totalRestockQuantity,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'status', label: 'Status'),
        cell: (item) => item.status,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(
            key: 'subtotal', label: 'Taxable Value', numeric: true),
        cell: (item) => item.subtotal,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'tax', label: 'Tax', numeric: true),
        cell: (item) => item.taxTotal,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'total', label: 'Grand Total'),
        cell: (item) => item.grandTotal,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'remarks', label: 'Remarks'),
        cell: (item) => item.remarks,
      ),
    ],
  );

  /// Read one return: what came back, what it credited, and each line. Its
  /// steps stay on the bar above the grid, so this only reads.
  Future<void> _openReturn(SalesReturn row) async {
    setState(() => _selected = row);
    final Object? outcome = await showDialog<Object>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Row(children: [
          Expanded(child: Text(row.returnNumber)),
          StatusBadge.fromStatus(row.status),
        ]),
        content: SizedBox(
          width: 560,
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                if (_customer(row).isNotEmpty) Text(_customer(row)),
                ..._facts(dialogContext, row),
              ],
            ),
          ),
        ),
        actions: [
          // The return's next steps (D-BUY-22), from the bar's definitions.
          DocumentStepStrip<SalesReturn>(record: row, steps: _steps),
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(),
            child: const Text('Close'),
          ),
        ],
      ),
    );
    if (outcome is! DocumentStepDone || !mounted) return;
    showStepDone(context, outcome);
    await _load();
  }

  Widget _list() => ListView.separated(
        itemCount: _returns.length,
        separatorBuilder: (_, __) => const Divider(height: 1),
        itemBuilder: (context, index) {
          final SalesReturn row = _returns[index];
          // Phase 2 reads figures as figures and a status as words: "2
          // restocked · 193.28 credited", "Completed".
          final bool phase2 = Phase2Scope.of(context);
          String quantity(String value) =>
              phase2 ? documentQuantity(value) : value;
          String money(String value) => phase2
              ? indianAmount(double.tryParse(value) ?? 0, full: true)
              : value;
          final String status = phase2 && row.status.isNotEmpty
              ? row.status[0] + row.status.substring(1).toLowerCase()
              : row.status;
          return ListTile(
            selected: row.id == _selected?.id,
            title: Text('${row.returnNumber}  ·  ${row.returnDate}'),
            // Whether it has actually happened is the thing a list of returns
            // has to answer; the status word alone does not say it.
            // Whose it is first (owner, 2026-09-27), then what happened.
            subtitle: Text([
              if (_customer(row).isNotEmpty) _customer(row),
              row.hasMoved
                  ? '${quantity(row.totalRestockQuantity)} restocked · '
                      '${money(row.grandTotal)} credited'
                      '${_stamp(row.createdAt)}'
                  : '${quantity(row.totalCurrentReturnQuantity)} awaiting '
                      'completion${_stamp(row.createdAt)}',
            ].join('\n')),
            isThreeLine: _customer(row).isNotEmpty,
            trailing: phase2
                ? StatusBadge.fromStatus(status)
                : StatusBadge(label: status),
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
          ..._facts(context, row),
          const SizedBox(height: AppSpacing.md),
          _actions(row),
        ],
      ),
    );
  }

  /// A return's reference, reason, what it moved and its lines -- the side
  /// pane's body, and the whole of phase 2's dialog.
  List<Widget> _facts(BuildContext context, SalesReturn row) => [
        if (row.customerReturnNumber.isNotEmpty)
          Text('Their reference: ${row.customerReturnNumber}',
              style: Theme.of(context).textTheme.bodySmall),
        if (row.returnReason.isNotEmpty)
          Text(row.returnReason, style: Theme.of(context).textTheme.bodySmall),
        const SizedBox(height: AppSpacing.md),
        _whatMoved(context, row),
        const SizedBox(height: AppSpacing.md),
        _lines(context, row),
      ];

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
                        '${(double.tryParse(line.freeQuantity) ?? 0) > 0 ? '${line.freeQuantity} of them free · ' : ''}'
                        '${line.restockQuantity} sellable · '
                        'from ${line.sourceDocumentNumber} '
                        'line ${line.sourceDocumentLineNumber} · '
                        '${line.pendingQuantity} still returnable',
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                      if (line.serials.isNotEmpty)
                        Text(
                          'Serials: '
                          '${line.serials.map((unit) => unit.serialNumber).join(', ')}',
                          style: Theme.of(context).textTheme.bodySmall,
                        ),
                    ],
                  ),
                ),
            ],
          ),
        ),
      );

  /// Render the credit note and hand it to whatever prints on this machine.
  Future<void> _printCreditNote(SalesReturn row) async {
    try {
      final List<int>? pdf = await fetchPrintablePdf(
        context,
        ({bool referenceCopy = false}) =>
            widget.api.creditNotePdf(row.id, referenceCopy: referenceCopy),
      );
      if (pdf == null || !mounted) return;
      await printDocument(context, bytes: pdf, documentName: row.returnNumber);
    } on ApiException catch (error) {
      if (!mounted) return;
      NotificationService.show(
        context,
        error.message,
        kind: AppNotificationKind.error,
      );
    }
  }

  Widget _actions(SalesReturn row) => Wrap(
        spacing: AppSpacing.sm,
        children: [
          // The customer's evidence that the money came back, and their
          // accountant needs it as much as they needed the invoice.
          OutlinedButton.icon(
            onPressed: () => unawaited(_printCreditNote(row)),
            icon: const Icon(Icons.print_outlined, size: 18),
            label: const Text('Print credit note'),
          ),
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
