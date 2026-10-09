import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../document_framework/document_line_labels.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/preferences/desktop_preferences_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/bulk_action.dart';
import '../../models/entities.dart';
import '../../models/document_framework.dart';
import '../../models/goods_receipt.dart';
import '../../models/product.dart';
import '../../phase2/indian_format.dart';
import '../document_framework/document_steps.dart';
import '../document_framework/document_view_dialog.dart';
import '../workspace/bulk_action.dart';
import '../workspace/desktop_framework.dart';
import '../workspace/reason_prompt.dart';
import 'purchase_return_editor_dialog.dart';
import 'purchase_return_steps.dart';

class PurchaseReturnManagementPage extends StatefulWidget {
  const PurchaseReturnManagementPage({
    super.key,
    required this.api,
    required this.preferences,
    required this.permissions,
    required this.hasActiveFirm,
    this.onOpenGlobalSearch,
  });

  final ApiClient api;
  final DesktopPreferencesService preferences;
  final PermissionService permissions;
  final bool hasActiveFirm;
  final Future<void> Function()? onOpenGlobalSearch;

  @override
  State<PurchaseReturnManagementPage> createState() =>
      _PurchaseReturnManagementPageState();
}

class _PurchaseReturnManagementPageState
    extends State<PurchaseReturnManagementPage> {
  static const int _rowsPerPage = 20;
  final TextEditingController _search = TextEditingController();

  /// The document dates the list is narrowed to (owner, 2026-09-27).
  DatePeriod _period = const DatePeriod.all();
  bool _loading = false;
  String? _error;
  int _page = 1;
  int _total = 0;
  Map<String, dynamic> _summary = const {};
  List<_PurchaseReturnRecord> _returns = const [];
  _PurchaseReturnRecord? _selected;

  /// The rows ticked for a bulk approve or cancel (backlog 56 A).
  Set<String> _ticked = <String>{};
  List<DocumentTimelineSnapshot> _history = const [];
  // Reference data the editor needs, loaded once with the workspace.
  List<GoodsReceiptRecord> _returnableReceipts = const [];
  List<Product> _products = const [];

  bool get _canCreate => widget.permissions.hasPermission('PURCHASE_CREATE');

  /// The lists the view dialog resolves a line's ids against. Read on their
  /// own, after the workspace's own data, so a failure here costs a name and
  /// never the list.
  DocumentLineLabels _labels = const DocumentLineLabels();

  Future<void> _loadLabels() async {
    // Products, units and tax profiles for the lines, and branches and
    // warehouses for the header: without the last two the view printed the
    // branch's id (D-UI-87). Each list that cannot be read is left empty.
    final DocumentLineLabels labels =
        await DocumentLineLabels.load(widget.api);
    if (!mounted) return;
    setState(() => _labels = labels);
  }

  @override
  void initState() {
    super.initState();
    unawaited(_load());
    unawaited(_loadLabels());
    unawaited(_loadReferenceData());
  }

  /// Load the receipts that can be sent back and the products they name.
  ///
  /// Failing here leaves the create action disabled rather than taking the
  /// workspace down; the list of returns is still readable without it.
  Future<void> _loadReferenceData() async {
    if (!widget.hasActiveFirm || !_canCreate) return;
    try {
      // Every page, not the newest hundred: past a hundred completed receipts
      // an older one could not be returned against from here (D-BUY-11).
      final List<dynamic> results = await Future.wait<dynamic>([
        fetchAllPages<GoodsReceiptRecord>(
          (int page) => widget.api.goodsReceipts(
            page: page,
            pageSize: maxApiPageSize,
            sortBy: 'receipt_date',
            descending: true,
            filters: const {'status': 'COMPLETED'},
          ),
        ),
        fetchAllPages<Product>(
          (int page) =>
              widget.api.products(page: page, pageSize: maxApiPageSize),
        ),
      ]);
      if (!mounted) return;
      setState(() {
        _returnableReceipts = results[0] as List<GoodsReceiptRecord>;
        _products = results[1] as List<Product>;
      });
    } on ApiException {
      if (!mounted) return;
      setState(() => _returnableReceipts = const []);
    }
  }

  /// Open the editor and reload if it saved a return.
  Future<void> _createReturn() async {
    final Object? outcome = await showDocument<Object>(
      context,
      title: 'New purchase return',
      builder: (_) => PurchaseReturnEditorDialog(
        api: widget.api,
        receipts: _returnableReceipts,
        products: _products,
        steps: [
          for (final DocumentStep<DocumentRef> step
              in purchaseReturnSteps(widget.api, widget.permissions))
            step.on<Json>(
              (json) => DocumentRef.fromJson(json, numberKey: 'return_number'),
            ),
        ],
      ),
    );
    if (await _afterWindow(outcome)) return;
    final Json? saved = outcome is Json ? outcome : null;
    if (saved == null || !mounted) return;
    await _load();
    if (!mounted) return;
    NotificationService.show(
      context,
      'Purchase return ${stringValue(saved['return_number'])} created as a '
      'draft. Approving and completing it is what takes the stock off.',
      kind: AppNotificationKind.success,
    );
  }

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  /// Whether the signed-in user may run this lifecycle action.
  ///
  /// The backend gates approve, close, complete and dispatch on
  /// PURCHASE_APPROVE and cancel on PURCHASE_CANCEL. The toolbar used to enable
  /// every action for anyone holding PURCHASE_VIEW, so a read-only user was
  /// offered buttons the server would refuse.
  bool _mayApprove() => widget.permissions.hasPermission('PURCHASE_APPROVE');

  /// The return's next steps -- Approve, Complete, Cancel, Close -- as its
  /// own windows offer them too (D-BUY-22): one definition, so the toolbar
  /// and the window cannot disagree about one return.
  late final List<DocumentStep<_PurchaseReturnRecord>> _steps = [
    for (final DocumentStep<DocumentRef> step
        in purchaseReturnSteps(widget.api, widget.permissions))
      step.on<_PurchaseReturnRecord>(
        (row) => DocumentRef(
          id: row.id,
          number: row.returnNumber,
          status: row.status,
        ),
      ),
  ];

  DocumentStep<_PurchaseReturnRecord> _step(String id) =>
      _steps.firstWhere((step) => step.id == id);

  /// Take a step against the selected return from the toolbar and reload.
  void _runStep(
    DocumentStep<_PurchaseReturnRecord> step,
    _PurchaseReturnRecord row,
  ) =>
      unawaited(runStepFromList(context, step, row, reload: _load));

  /// What a return's window closed with: a step it took, or anything else.
  Future<bool> _afterWindow(Object? outcome) async {
    if (outcome is! DocumentStepDone || !mounted) return false;
    await _load();
    if (mounted) showStepDone(context, outcome);
    return true;
  }

  Future<void> _load({int? requestedPage}) async {
    // Read before any await: whether to pick the first row (phase 1 only).
    // Phase 2 (option C, owner 2026-09-27): nothing is picked for the user --
    // the selection bar opens when somebody clicks a row, and stays with it.
    final bool pickFirst =
        context.getInheritedWidgetOfExactType<Phase2Scope>() == null;
    if (!widget.hasActiveFirm ||
        !widget.permissions.hasPermission('PURCHASE_VIEW')) {
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
      if (requestedPage != null) {
        _page = requestedPage;
      }
    });
    try {
      final List<dynamic> responses = await Future.wait<dynamic>([
        widget.api.documentSummary('purchase-returns'),
        widget.api.documentPage(
          'purchase-returns',
          page: _page,
          pageSize: _rowsPerPage,
          search: _search.text.trim(),
          sortBy: 'return_date',
          descending: true,
          additionalQuery: {
            if (_period.from != null)
              'return_from': DatePeriod.iso(_period.from!),
            if (_period.to != null) 'return_to': DatePeriod.iso(_period.to!),
          },
        ),
      ]);
      final Map<String, dynamic> summary = _unwrap(responses[0]);
      final Map<String, dynamic> page = _unwrap(responses[1]);
      final List<_PurchaseReturnRecord> returns = _recordsFromResponse(page);
      _PurchaseReturnRecord? selected = _selected;
      if (selected != null) {
        final String selectedId = selected.id;
        final List<_PurchaseReturnRecord> matches =
            returns.where((item) => item.id == selectedId).toList();
        selected = matches.isEmpty ? null : matches.first;
      }
      if (selected == null && pickFirst && returns.isNotEmpty) {
        selected = returns.first;
      }
      List<DocumentTimelineSnapshot> history = const [];
      if (selected != null) {
        try {
          final Map<String, dynamic> timeline = _unwrap(await widget.api
              .documentHistory('purchase-returns', selected.id));
          history = _timelineFromResponse(timeline);
        } on ApiException {
          history = const [];
        }
      }
      if (!mounted) {
        return;
      }
      setState(() {
        _summary = summary;
        _returns = returns;
        _total = pagedTotal(page, fallback: returns.length);
        _selected = selected;
        _ticked =
            _ticked.where((id) => returns.any((row) => row.id == id)).toSet();
        _history = history;
      });
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _error = error.toString();
        _returns = const [];
        _selected = null;
        _history = const [];
        _total = 0;
      });
    } finally {
      if (mounted) {
        setState(() => _loading = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return EnterpriseWorkspace(
      title: 'Purchase Returns',
      description:
          'Send goods back to a supplier. Completing a return is what takes '
          'the stock off.',
      breadcrumbs: const ['Workspace', 'Purchase Returns'],
      content: Column(
        children: [
          if (_loading) const LinearProgressIndicator(minHeight: 2),
          Padding(
            // Phase 2 draws the figures on the page's one line, so the gap
            // their row of cards needed goes with it.
            padding: Phase2Scope.of(context)
                ? EdgeInsets.zero
                : const EdgeInsets.fromLTRB(24, 0, 24, 12),
            child: SummaryCards(
              children: [
                _summaryCard('Total', '${_summary['total'] ?? 0}'),
                _summaryCard('Draft', '${_summary['draft'] ?? 0}'),
                _summaryCard('Approved', '${_summary['approved'] ?? 0}'),
                _summaryCard('Completed', '${_summary['completed'] ?? 0}'),
                _summaryCard('Cancelled', '${_summary['cancelled'] ?? 0}'),
                _summaryCard('Closed', '${_summary['closed'] ?? 0}'),
              ],
            ),
          ),
          // Bounded, so the layout below has a height to divide.
          Expanded(child: _buildGridWorkspace()),
        ],
      ),
    );
  }

  /// More than one row ticked: the bar names the batch and offers the two
  /// bulk actions instead of the one row's.
  bool get _bulkMode => _ticked.length > 1;

  List<_PurchaseReturnRecord> get _tickedRows =>
      _returns.where((row) => _ticked.contains(row.id)).toList();

  List<BulkRow> _bulkRows() => [
        for (final _PurchaseReturnRecord row in _tickedRows)
          (id: row.id, version: null),
      ];

  SelectionSummary _bulkSummary() {
    double total = 0;
    for (final _PurchaseReturnRecord row in _tickedRows) {
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
          onPressed: _loading || !_mayApprove()
              ? null
              : () => unawaited(_bulkApprove()),
        ),
        ToolbarCommand(
          id: 'cancel',
          label: 'Cancel selected',
          icon: Icons.cancel_outlined,
          onPressed:
              _loading || !widget.permissions.hasPermission('PURCHASE_CANCEL')
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
      send: widget.api.bulkApprovePurchaseReturns,
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
      send: (rows) => widget.api.bulkCancelPurchaseReturns(rows, reason),
    );
    await _afterBulk();
  }

  Future<void> _afterBulk() async {
    if (!mounted) return;
    setState(() => _ticked = <String>{});
    await _load();
  }

  Widget _buildGridWorkspace() => ManagementWorkspaceLayout(
        toolbar: _buildToolbar(),
        searchPanel: SearchFilterPanel(
          controller: _search,
          hintText: 'Search return number, supplier return or supplier',
          onSearch: (_) => _load(requestedPage: 1),
        ),
        // Option C (owner, 2026-09-27): the return's actions on a bar that
        // names it and its supplier, above the grid.
        selectionBar: true,
        selection: _bulkMode
            ? _bulkSummary()
            : _selected == null
            ? null
            : SelectionSummary.document(
                number: _selected!.returnNumber,
                party: _selected!.vendorName,
                status: _selected!.status,
                total: _selected!.grandTotal,
                onClear: () => setState(() => _selected = null),
              ),
        // Inside the frame rather than instead of it: the workspace still
        // names itself and its breadcrumbs when no firm is chosen, which is
        // what tells the user where they are while they choose one.
        primaryContent: !widget.hasActiveFirm
            ? const StandardEmptyState(type: EmptyStateType.noFirmSelected)
            : _error != null && !_loading
                ? WorkspaceEmptyState(
                    title: 'Purchase returns unavailable',
                    message: _error!,
                  )
                : _returns.isEmpty && !_loading
                    ? StandardEmptyState(
                        type: _search.text.trim().isEmpty
                            ? EmptyStateType.noRecords
                            : EmptyStateType.noSearchResults,
                      )
                    : _buildReturnGrid(),
        // No side pane. It sat at `flex: 4` against a `flex: 3` list, so the
        // preview of the one record pointed at had more room than every
        // record. Double-click opens it instead.
        detailsPanel: null,
        statusBar: WorkspaceStatusBar(
          total: _total,
          selected: _selected != null,
          message: _loading ? 'Loading...' : null,
        ),
      );

  Widget _buildToolbar() => WorkspaceToolbar(
        actions: const [
          ToolbarAction.newItem,
          ToolbarAction.view,
          ToolbarAction.refresh,
        ],
        isVisible: (action) => action != ToolbarAction.newItem || _canCreate,
        isEnabled: (action) =>
            !_loading &&
            switch (action) {
              // A return line needs a completed receipt line behind it, so
              // nothing to return against is a disabled button rather than an
              // empty dialog.
              ToolbarAction.newItem =>
                _canCreate && _returnableReceipts.isNotEmpty,
              ToolbarAction.view => _selected != null && !_bulkMode,
              ToolbarAction.refresh => true,
              _ => false,
            },
        onAction: (action) {
          switch (action) {
            case ToolbarAction.newItem:
              unawaited(_createReturn());
            case ToolbarAction.view:
              final _PurchaseReturnRecord? selected = _selected;
              if (selected != null) unawaited(_openReturn(selected));
            case ToolbarAction.refresh:
              unawaited(_load());
            default:
              break;
          }
        },
        // Only the four the backend has. The pane offered eight -- new, print,
        // export, email and reject among them -- and four fell through to a
        // notification saying "Placeholder action for purchase returns.".
        //
        // Worse, its **Close** button called `/complete`, which is the step
        // that takes the stock off, and `/close` was never called at all. A
        // button that posts a stock movement must not be named after the one
        // that ends the document.
        // Phase 2 (4.11): the same steps as commands, folded into "..."
        // when the line is short.
        commands: _bulkMode
            ? _bulkCommands()
            : Phase2Scope.of(context)
            ? [
                for (final DocumentStep<_PurchaseReturnRecord> step
                    in _steps)
                  step.command(_selected, _runStep),
                // Not a lifecycle step: say what the return comes back as,
                // any time before it is cancelled.
                ToolbarCommand(
                  id: 'change-outcome',
                  label: 'Change outcome',
                  icon: Icons.swap_horiz,
                  onPressed: _selected == null ||
                          _selected!.status.toUpperCase() == 'CANCELLED' ||
                          !widget.permissions
                              .hasPermission('PURCHASE_UPDATE')
                      ? null
                      : () => unawaited(_changeOutcome(_selected!)),
                ),
              ]
            : const [],
        // Period right after the search, then Columns, as every sales list
        // (owner, 2026-09-27).
        trailing: Phase2Scope.of(context)
            ? [
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
              ]
            : [
                _actionButton(_step('approve')),
                _actionButton(_step('complete')),
                _actionButton(_step('cancel')),
                _actionButton(_step('close')),
              ],
      );

  /// A lifecycle button, disabled unless the selected document's status
  /// allows it.
  ///
  /// Permission alone used to decide this, so Approve was live on an
  /// already-approved document and Close on a closed one. Pressing either
  /// produced a refusal the screen could have predicted.
  Widget _actionButton(DocumentStep<_PurchaseReturnRecord> step) =>
      Padding(
        padding: const EdgeInsets.only(left: 8),
        child: OutlinedButton.icon(
          onPressed: step.enabledFor(_selected)
              ? () => _runStep(step, _selected!)
              : null,
          icon: Icon(step.icon, size: 18),
          label: Text(step.label),
        ),
      );

  /// Every column the grid can show; Columns picks among them, remembered
  /// per screen on this PC (owner, 2026-09-27).
  late final ColumnChoice<_PurchaseReturnRecord> _columns = ColumnChoice(
    preferences: widget.preferences,
    stateKey: 'purchase-returns.grid',
    columns: [
      ChoosableColumn(
        column: const GridColumn(key: 'number', label: 'Return Number'),
        cell: (item) => item.returnNumber,
        required: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'vendor', label: 'Supplier', priority: 1),
        cell: (item) => item.vendorName,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'supplier', label: 'Supplier Return'),
        cell: (item) => item.supplierReturnNumber,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'outcome', label: 'Outcome'),
        cell: (item) => purchaseReturnOutcomes[item.outcome] ?? item.outcome,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'reason', label: 'Reason'),
        cell: (item) => item.returnReason,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'date', label: 'Return Date'),
        cell: (item) => documentDateStamp(item.returnDate, item.createdAt),
        shownByDefault: true,
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

  Widget _buildReturnGrid() => EnterpriseDataGrid<_PurchaseReturnRecord>(
        columns: _columns.gridColumns,
        items: _returns,
        id: (item) => item.id,
        selectedId: _selected?.id,
        // Ticks, for a bulk approve or cancel. A single row is still chosen
        // by clicking it.
        selectedIds: _ticked,
        onSelectionChanged: (ticked) => setState(() => _ticked = ticked),
        cells: _columns.cells,
        onSelect: (item) => unawaited(_selectReturn(item)),
        onOpen: (item) => unawaited(_openReturn(item)),
        total: _total,
        pageOffset: (_page - 1) * _rowsPerPage,
        rowsPerPage: _rowsPerPage,
        onPageChanged: (offset) {
          final int next = offset ~/ _rowsPerPage + 1;
          if (next != _page) _load(requestedPage: next);
        },
      );

  /// Show one return: header, lines, totals and timeline.
  Future<void> _openReturn(_PurchaseReturnRecord record) async {
    await _selectReturn(record);
    if (!mounted) return;
    final Object? outcome = await showDialog<Object>(
      context: context,
      builder: (_) => DocumentViewDialog(
        steps: DocumentStepStrip<_PurchaseReturnRecord>(
          record: record,
          steps: _steps,
        ),
        title: record.returnNumber,
        subtitle: 'Supplier return ${record.supplierReturnNumber}  ·  '
            'Outcome: ${purchaseReturnOutcomes[record.outcome] ?? record.outcome}',
        icon: Icons.assignment_return_outlined,
        header: record.toHeader(branchName: _labels.branch),
        lines: [
          for (final _PurchaseReturnLine line in record.lines)
            DocumentLineSnapshot(
              lineNumber: line.lineNumber,
              product: _labels.product(line.productId),
              description: line.description,
              uom: _labels.unit(line.returnUomId),
              packaging: line.packagingTypeId,
              quantity: line.shownQuantity,
              unitPrice: line.unitPrice,
              discount: line.discountAmount,
              taxProfile: _labels.taxProfile(line.taxProfileId),
              amount: line.grossAmount,
              netAmount: line.netAmount,
              remarks: line.remarks,
            ),
        ],
        totals: record.toTotals(),
        history: _history,
      ),
    );
    await _afterWindow(outcome);
  }

  /// Choose Credit, Replacement or Refund for the return. The server decides
  /// whether the change is allowed (a refund that stands pins it), and its
  /// message is shown as it is.
  Future<void> _changeOutcome(_PurchaseReturnRecord record) async {
    final String? chosen = await showDialog<String>(
      context: context,
      builder: (dialogContext) => SimpleDialog(
        title: Text('Outcome of ${record.returnNumber}'),
        children: [
          for (final MapEntry<String, String> entry
              in purchaseReturnOutcomes.entries)
            SimpleDialogOption(
              key: ValueKey<String>('outcome-${entry.key}'),
              onPressed: () => Navigator.pop(dialogContext, entry.key),
              child: Text(
                entry.key == record.outcome
                    ? '${entry.value} (current)'
                    : entry.value,
              ),
            ),
        ],
      ),
    );
    if (chosen == null || chosen == record.outcome || !mounted) return;
    try {
      await widget.api
          .setPurchaseReturnOutcome(returnId: record.id, outcome: chosen);
      await _load();
      if (!mounted) return;
      NotificationService.show(
        context,
        '${record.returnNumber} now comes back as '
        '${purchaseReturnOutcomes[chosen] ?? chosen}.',
        kind: AppNotificationKind.success,
      );
    } on ApiException catch (error) {
      if (!mounted) return;
      NotificationService.show(context, error.message,
          kind: AppNotificationKind.error);
    }
  }

  Future<void> _selectReturn(_PurchaseReturnRecord row) async {
    setState(() => _selected = row);
    try {
      final Map<String, dynamic> timeline =
          _unwrap(await widget.api.documentHistory('purchase-returns', row.id));
      if (!mounted) {
        return;
      }
      setState(() => _history = _timelineFromResponse(timeline));
    } on ApiException {
      if (!mounted) {
        return;
      }
      setState(() => _history = const []);
    }
  }

  Widget _summaryCard(String label, String value) =>
      SummaryCount(label: label, value: value);

  Map<String, dynamic> _unwrap(dynamic response) {
    if (response is Map<String, dynamic>) {
      final dynamic data = response['data'];
      if (data is Map<String, dynamic>) {
        return data;
      }
      return response;
    }
    return const <String, dynamic>{};
  }

  List<_PurchaseReturnRecord> _recordsFromResponse(
      Map<String, dynamic> response) {
    final dynamic data = response['data'];
    if (data is! List) {
      return const [];
    }
    return data
        .whereType<Map>()
        .map((item) =>
            _PurchaseReturnRecord.fromJson(Map<String, dynamic>.from(item)))
        .toList();
  }

  List<DocumentTimelineSnapshot> _timelineFromResponse(
      Map<String, dynamic> response) {
    final dynamic data = response['data'];
    if (data is! List) {
      return const [];
    }
    return data
        .whereType<Map>()
        .map((item) =>
            DocumentTimelineSnapshot.fromJson(Map<String, dynamic>.from(item)))
        .toList();
  }
}

class _PurchaseReturnRecord {
  const _PurchaseReturnRecord({
    required this.id,
    required this.returnNumber,
    required this.returnDate,
    required this.supplierReturnNumber,
    required this.status,
    required this.subtotal,
    required this.taxTotal,
    required this.additionalCharges,
    required this.roundOff,
    required this.grandTotal,
    required this.businessProfileId,
    required this.branchId,
    required this.vendorId,
    this.vendorName = '',
    this.returnReason = '',
    this.outcome = 'CREDIT',
    this.createdAt = '',
    required this.currencyCode,
    required this.exchangeRate,
    required this.paymentTerms,
    required this.remarks,
    required this.lines,
    required this.sources,
  });

  final String id;
  final String returnNumber;
  final String returnDate;
  final String supplierReturnNumber;
  final String status;
  final String subtotal;
  final String taxTotal;
  final String additionalCharges;
  final String roundOff;
  final String grandTotal;
  final String businessProfileId;
  final String branchId;
  final String vendorId;

  /// Whose document it is, so the list can say so (owner, 2026-09-27).
  final String vendorName;
  final String returnReason;

  /// CREDIT, REPLACEMENT or REFUND; CREDIT on an answer that names none.
  final String outcome;
  final String createdAt;
  final String currencyCode;
  final String exchangeRate;
  final String paymentTerms;
  final String remarks;
  final List<_PurchaseReturnLine> lines;
  final List<Json> sources;

  factory _PurchaseReturnRecord.fromJson(Map<String, dynamic> json) {
    final List<_PurchaseReturnLine> lines = (json['lines'] is List)
        ? (json['lines'] as List)
            .whereType<Map>()
            .map((item) =>
                _PurchaseReturnLine.fromJson(Map<String, dynamic>.from(item)))
            .toList()
        : const [];
    return _PurchaseReturnRecord(
      id: stringValue(json['id']),
      returnNumber: stringValue(json['return_number']),
      returnDate: stringValue(json['return_date']),
      supplierReturnNumber: stringValue(json['supplier_return_number']),
      status: stringValue(json['status']),
      subtotal: stringValue(json['subtotal']),
      taxTotal: stringValue(json['tax_total']),
      additionalCharges: stringValue(json['additional_charges']),
      roundOff: stringValue(json['round_off']),
      grandTotal: stringValue(json['grand_total']),
      businessProfileId: stringValue(json['business_profile_id']),
      branchId: stringValue(json['branch_id']),
      vendorId: stringValue(json['vendor_id']),
      vendorName: stringValue(json['vendor_name']),
      returnReason: stringValue(json['return_reason']),
      outcome: stringValue(json['outcome']).isEmpty
          ? 'CREDIT'
          : stringValue(json['outcome']),
      createdAt: stringValue(json['created_at']),
      currencyCode: stringValue(json['currency_code']),
      exchangeRate: stringValue(json['exchange_rate']),
      paymentTerms: stringValue(json['payment_terms']),
      remarks: stringValue(json['remarks']),
      lines: lines,
      sources: (json['sources'] is List)
          ? (json['sources'] as List)
              .whereType<Map>()
              .map((item) => Map<String, dynamic>.from(item))
              .toList()
          : const [],
    );
  }

  /// The header a document view shows. [branchName] and [warehouseName]
  /// turn an id into what a person reads; without them the id is all this
  /// record holds, and an id is never worth showing, so the field is blank.
  DocumentHeaderSnapshot toHeader({
    String Function(String id)? branchName,
  }) => DocumentHeaderSnapshot(
        documentTypeCode: 'PURCHASE_RETURN',
        documentTypeName: 'Purchase Return',
        documentNumber: returnNumber,
        documentDate: returnDate,
        reference: supplierReturnNumber,
        branch: namedOrBlank(branchName, branchId),
        firm: '',
        currency: currencyCode,
        exchangeRate: exchangeRate,
        status: status,
        remarks: remarks,
      );

  DocumentTotalsSnapshot toTotals() => DocumentTotalsSnapshot(
        subtotal: subtotal,
        discount: '0',
        tax: taxTotal,
        charges: additionalCharges,
        roundOff: roundOff,
        grandTotal: grandTotal,
      );
}

class _PurchaseReturnLine {
  const _PurchaseReturnLine({
    required this.lineNumber,
    required this.productId,
    required this.description,
    required this.returnUomId,
    required this.packagingTypeId,
    required this.currentReturnQuantity,
    required this.unitPrice,
    required this.discountAmount,
    required this.taxProfileId,
    required this.grossAmount,
    required this.netAmount,
    required this.remarks,
    this.enteredQuantity = '',
  });

  final int lineNumber;
  final String productId;
  final String description;
  final String returnUomId;
  final String packagingTypeId;
  final String currentReturnQuantity;

  /// What was typed, in [returnUomId], where the line was typed in another
  /// unit than the line it sends back (D-PRC-37); empty otherwise.
  /// [currentReturnQuantity] is then the same goods in the source line's
  /// unit, so it is not what the unit beside the figure counts.
  final String enteredQuantity;
  final String unitPrice;
  final String discountAmount;
  final String taxProfileId;
  final String grossAmount;
  final String netAmount;
  final String remarks;

  /// The quantity the line's own unit counts.
  String get shownQuantity =>
      enteredQuantity.isEmpty ? currentReturnQuantity : enteredQuantity;

  factory _PurchaseReturnLine.fromJson(Map<String, dynamic> json) =>
      _PurchaseReturnLine(
        lineNumber: (json['line_number'] as num?)?.toInt() ?? 0,
        productId: stringValue(json['product_id']),
        description: stringValue(json['description']),
        returnUomId: stringValue(json['return_uom_id']),
        packagingTypeId: stringValue(json['packaging_type_id']),
        currentReturnQuantity: stringValue(json['current_return_quantity']),
        enteredQuantity: stringValue(json['entered_quantity']),
        unitPrice: stringValue(json['unit_price']),
        discountAmount: stringValue(json['discount_amount']),
        taxProfileId: stringValue(json['tax_profile_id']),
        grossAmount: stringValue(json['gross_amount']),
        netAmount: stringValue(json['net_amount']),
        remarks: stringValue(json['remarks']),
      );
}
