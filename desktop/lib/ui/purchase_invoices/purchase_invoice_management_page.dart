import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../models/product.dart';
import '../../models/purchase.dart';
import '../../models/line_tax_rule.dart';
import '../../models/vendor.dart';
import '../../models/tax_framework.dart';
import '../../models/uom_packaging.dart';
import '../document_framework/document_line_labels.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/preferences/desktop_preferences_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/entities.dart';
import '../../models/bulk_action.dart';
import '../../models/document_framework.dart';
import '../../phase2/indian_format.dart';
import '../../models/goods_receipt.dart';
import '../document_framework/document_steps.dart';
import '../document_framework/document_view_dialog.dart';
import '../workspace/bulk_action.dart';
import '../workspace/desktop_framework.dart';
import '../workspace/reason_prompt.dart';
import 'purchase_invoice_editor_dialog.dart';
import 'purchase_invoice_steps.dart';
import 'supplier_irn_dialog.dart';

class PurchaseInvoiceManagementPage extends StatefulWidget {
  const PurchaseInvoiceManagementPage({
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
  State<PurchaseInvoiceManagementPage> createState() =>
      _PurchaseInvoiceManagementPageState();
}

class _PurchaseInvoiceManagementPageState
    extends State<PurchaseInvoiceManagementPage> {
  static const int _rowsPerPage = 20;
  final TextEditingController _search = TextEditingController();

  /// The document dates the list is narrowed to (owner, 2026-09-27).
  DatePeriod _period = const DatePeriod.all();
  bool _loading = false;
  String? _error;
  int _page = 1;
  int _total = 0;
  Map<String, dynamic> _summary = const {};
  List<_PurchaseInvoiceRecord> _invoices = const [];
  _PurchaseInvoiceRecord? _selected;

  /// The rows ticked for a bulk approve or cancel (backlog 56 A).
  Set<String> _ticked = <String>{};
  List<DocumentTimelineSnapshot> _history = const [];
  // Reference data the editor needs, loaded once with the workspace.
  List<GoodsReceiptRecord> _billableReceipts = const [];
  List<Product> _products = const [];

  /// What a new bill names follows the firm's buying stages (backlog §38):
  /// receipts, approved orders, or -- typed directly -- a supplier.
  PurchaseWorkflowSettings _stages = PurchaseWorkflowSettings.wholeChain;
  List<PurchaseOrder> _billableOrders = const [];
  List<Vendor> _vendors = const [];

  bool get _canCreate => widget.permissions.hasPermission('PURCHASE_CREATE');

  /// The lists the view dialog resolves a line's ids against. Read on their
  /// own, after the workspace's own data, so a failure here costs a name and
  /// never the list.
  DocumentLineLabels _labels = const DocumentLineLabels();

  Future<void> _loadLabels() async {
    List<Product> products = const <Product>[];
    List<UomRecord> units = const <UomRecord>[];
    List<TaxProfileRecord> profiles = const <TaxProfileRecord>[];
    try {
      products = (await widget.api.products(page: 1, pageSize: 100)).items;
    } on ApiException {
      // A name falls back to its id.
    }
    try {
      units = await widget.api.uoms(includeInactive: true);
    } on ApiException {
      // As above.
    }
    try {
      profiles = (await widget.api.taxProfiles(page: 1, pageSize: 100)).items;
    } on ApiException {
      // As above.
    }
    if (!mounted) return;
    setState(() {
      _labels = DocumentLineLabels(
        products: products,
        units: units,
        taxProfiles: profiles,
      );
    });
  }

  @override
  void initState() {
    super.initState();
    unawaited(_load());
    unawaited(_loadLabels());
    unawaited(_loadReferenceData());
  }

  /// Load the receipts that can be billed and the products they name.
  ///
  /// Failing here leaves the create action disabled rather than taking the
  /// workspace down; the list of invoices is still readable without it.
  Future<void> _loadReferenceData() async {
    if (!widget.hasActiveFirm || !_canCreate) return;
    try {
      // Every page, not the newest hundred: past a hundred completed receipts
      // an older one could not be billed from here at all (D-BUY-11).
      final List<dynamic> results = await Future.wait<dynamic>([
        fetchAllPages<GoodsReceiptRecord>(
          (int page) => widget.api.goodsReceipts(
            page: page,
            pageSize: maxApiPageSize,
            sortBy: 'receipt_date',
            descending: true,
            // Only receipts with goods left to bill: one billed in full, or
            // sent back, is not offered again (D-BUY-27).
            filters: const {'status': 'COMPLETED', 'billable': 'true'},
          ),
        ),
        fetchAllPages<Product>(
          (int page) =>
              widget.api.products(page: page, pageSize: maxApiPageSize),
        ),
      ]);
      if (!mounted) return;
      setState(() {
        _billableReceipts = results[0] as List<GoodsReceiptRecord>;
        _products = results[1] as List<Product>;
      });
    } on ApiException {
      if (!mounted) return;
      setState(() => _billableReceipts = const []);
    }
    await _loadStages();
  }

  /// Learn which buying stages this firm types, and load what a bill can
  /// name when receipts are not typed.
  ///
  /// Fails open to the whole chain, as the sidebar does: an unreadable
  /// setting must not offer a mode the server would refuse, and on the whole
  /// chain a bill names a receipt, which it always may.
  Future<void> _loadStages() async {
    PurchaseWorkflowSettings stages = PurchaseWorkflowSettings.wholeChain;
    try {
      stages = await widget.api.purchaseWorkflowSettings();
    } on ApiException {
      stages = PurchaseWorkflowSettings.wholeChain;
    }
    if (!mounted) return;
    setState(() => _stages = stages);
    if (stages.goodsReceiptStage) return;
    try {
      final List<dynamic> results = await Future.wait<dynamic>([
        fetchAllPages<Vendor>(
          (int page) => widget.api.vendors(page: page),
        ),
        if (stages.purchaseOrderStage)
          for (final String status in const ['APPROVED', 'PARTIALLY_RECEIVED'])
            fetchAllPages<PurchaseOrder>(
              (int page) => widget.api.purchases(
                page: page,
                pageSize: maxApiPageSize,
                sortBy: 'purchase_date',
                descending: true,
                filters: PurchaseQuery(status: status),
              ),
            ),
      ]);
      if (!mounted) return;
      setState(() {
        _vendors = results[0] as List<Vendor>;
        _billableOrders = [
          for (final dynamic list in results.skip(1))
            ...list as List<PurchaseOrder>,
        ];
      });
    } on ApiException {
      if (!mounted) return;
      setState(() {
        _vendors = const [];
        _billableOrders = const [];
      });
    }
  }

  /// Whether there is anything a new bill could name.
  bool get _canStartBill {
    if (_stages.goodsReceiptStage) return _billableReceipts.isNotEmpty;
    if (_stages.purchaseOrderStage) return _billableOrders.isNotEmpty;
    return _vendors.isNotEmpty && _products.isNotEmpty;
  }

  /// Open the editor and reload if it saved a bill.
  ///
  /// Nothing called `POST /purchase-invoices` from the desktop until
  /// 2026-09-18 (BL-31.9): the screen listed, approved and closed bills the
  /// seeder had raised, and the orphan-route guard could not see it because
  /// the generic `documentPage` helper names the same literal.
  Future<void> _createInvoice() async {
    final Object? outcome = await showDocument<Object>(
      context,
      title: 'New purchase invoice',
      builder: (_) => PurchaseInvoiceEditorDialog(
        api: widget.api,
        receipts: _billableReceipts,
        products: _products,
        stages: _stages,
        orders: _billableOrders,
        vendors: _vendors,
        canAttach: widget.permissions.hasAnyPermission(
            const ['PURCHASE_CREATE', 'PURCHASE_UPDATE']),
        steps: [
          for (final DocumentStep<DocumentRef> step
              in purchaseInvoiceSteps(widget.api, widget.permissions))
            step.on<Json>(
              (json) => DocumentRef.fromJson(json, numberKey: 'invoice_number'),
            ),
        ],
      ),
    );
    if (await _afterWindow(outcome)) return;
    final Json? saved = outcome is Json ? outcome : null;
    if (saved == null || !mounted) return;
    await _load();
    if (!mounted) return;
    final String irnWarning = [
      stringValue(saved['irn_warning']),
      stringValue(saved['credit_time_limit_warning']),
    ].where((String text) => text.isNotEmpty).join(' ');
    NotificationService.show(
      context,
      'Purchase invoice ${stringValue(saved['invoice_number'])} created as a '
      'draft. Approving it is what posts it to the books.'
      '${irnWarning.isEmpty ? '' : ' $irnWarning'}',
      kind: irnWarning.isEmpty
          ? AppNotificationKind.success
          : AppNotificationKind.warning,
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

  /// The bill's next steps -- Approve, Cancel, Close -- as its own windows
  /// offer them too (D-BUY-22): one definition, so the toolbar and the
  /// window cannot disagree about one bill.
  late final List<DocumentStep<_PurchaseInvoiceRecord>> _steps = [
    for (final DocumentStep<DocumentRef> step
        in purchaseInvoiceSteps(widget.api, widget.permissions))
      step.on<_PurchaseInvoiceRecord>(
        (bill) => DocumentRef(
          id: bill.id,
          number: bill.invoiceNumber,
          status: bill.status,
        ),
      ),
  ];

  DocumentStep<_PurchaseInvoiceRecord> _step(String id) =>
      _steps.firstWhere((step) => step.id == id);

  /// Take a step against the selected bill from the toolbar and reload.
  void _runStep(
    DocumentStep<_PurchaseInvoiceRecord> step,
    _PurchaseInvoiceRecord bill,
  ) =>
      unawaited(runStepFromList(context, step, bill, reload: _load));

  /// What a bill's window closed with: a step it took, or anything else.
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
        widget.api.documentSummary('purchase-invoices'),
        widget.api.documentPage(
          'purchase-invoices',
          page: _page,
          pageSize: _rowsPerPage,
          search: _search.text.trim(),
          sortBy: 'invoice_date',
          descending: true,
          additionalQuery: {
            if (_period.from != null)
              'invoice_from': DatePeriod.iso(_period.from!),
            if (_period.to != null) 'invoice_to': DatePeriod.iso(_period.to!),
          },
        ),
      ]);
      final Map<String, dynamic> summary = _unwrap(responses[0]);
      final Map<String, dynamic> page = _unwrap(responses[1]);
      final List<_PurchaseInvoiceRecord> invoices = _recordsFromResponse(page);
      _PurchaseInvoiceRecord? selected = _selected;
      if (selected != null) {
        final String selectedId = selected.id;
        final List<_PurchaseInvoiceRecord> matches =
            invoices.where((item) => item.id == selectedId).toList();
        selected = matches.isEmpty ? null : matches.first;
      }
      if (selected == null && pickFirst && invoices.isNotEmpty) {
        selected = invoices.first;
      }
      List<DocumentTimelineSnapshot> history = const [];
      if (selected != null) {
        try {
          final Map<String, dynamic> timeline = _unwrap(await widget.api
              .documentHistory('purchase-invoices', selected.id));
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
        _invoices = invoices;
        _total = pagedTotal(page, fallback: invoices.length);
        _selected = selected;
        _ticked = _ticked
            .where((id) => invoices.any((row) => row.id == id))
            .toSet();
        _history = history;
      });
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _error = error.toString();
        _invoices = const [];
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
      title: 'Purchase Invoices',
      description:
          'Manage supplier invoices, GRN matching, and accounting events.',
      breadcrumbs: const ['Workspace', 'Purchase Invoices'],
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

  List<_PurchaseInvoiceRecord> get _tickedRows =>
      _invoices.where((row) => _ticked.contains(row.id)).toList();

  List<BulkRow> _bulkRows() => [
        for (final _PurchaseInvoiceRecord row in _tickedRows)
          (id: row.id, version: null),
      ];

  SelectionSummary _bulkSummary() {
    double total = 0;
    for (final _PurchaseInvoiceRecord row in _tickedRows) {
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
      send: widget.api.bulkApprovePurchaseInvoices,
    );
    await _afterBulk();
  }

  Future<void> _bulkCancel() async {
    final List<BulkRow> rows = _bulkRows();
    final String? reason = await askForReason(
      context,
      title: 'Cancel ${rows.length} invoices',
      explanation: 'Each invoice is cancelled on its own and its stock and '
          'journal are reversed; one the server refuses does not stop the '
          'others. The reason is recorded on every invoice cancelled.',
      confirmLabel: 'Cancel invoices',
    );
    if (reason == null || !mounted) return;
    await runBulkAction(
      context,
      verb: 'Cancelled',
      rows: rows,
      send: (rows) => widget.api.bulkCancelPurchaseInvoices(rows, reason),
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
          hintText: 'Search invoice number, supplier invoice or supplier',
          onSearch: (_) => _load(requestedPage: 1),
        ),
        // Option C (owner, 2026-09-27): the invoice's actions on a bar that
        // names it and its supplier, above the grid.
        selectionBar: true,
        selection: _bulkMode
            ? _bulkSummary()
            : _selected == null
            ? null
            : SelectionSummary.document(
                number: _selected!.invoiceNumber,
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
                    title: 'Purchase invoices unavailable',
                    message: _error!,
                  )
                : _invoices.isEmpty && !_loading
                    ? StandardEmptyState(
                        type: _search.text.trim().isEmpty
                            ? EmptyStateType.noRecords
                            : EmptyStateType.noSearchResults,
                      )
                    : _buildInvoiceGrid(),
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
              // A bill line needs a receipt line, an order line or -- typed
              // directly -- a product behind it, so nothing to bill against
              // is a disabled button rather than an empty dialog.
              ToolbarAction.newItem => _canCreate && _canStartBill,
              ToolbarAction.view => _selected != null && !_bulkMode,
              ToolbarAction.refresh => true,
              _ => false,
            },
        onAction: (action) {
          switch (action) {
            case ToolbarAction.newItem:
              unawaited(_createInvoice());
            case ToolbarAction.view:
              final _PurchaseInvoiceRecord? selected = _selected;
              if (selected != null) unawaited(_openInvoice(selected));
            case ToolbarAction.refresh:
              unawaited(_load());
            default:
              break;
          }
        },
        // Only the three lifecycle actions the backend has. The pane offered
        // eight -- print, export, email and reject among them -- and five fell
        // through to a notification saying "Placeholder action for purchase
        // invoices.", which is a button that exists to tell you it does
        // nothing. New is the standard action above, not one of these.
        // Phase 2 (4.11): the same steps as commands, folded into "..."
        // when the line is short.
        commands: _bulkMode
            ? _bulkCommands()
            : Phase2Scope.of(context)
            ? [
                for (final DocumentStep<_PurchaseInvoiceRecord> step
                    in _steps)
                  step.command(_selected, _runStep),
                _recordIrnCommand(),
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
  Widget _actionButton(DocumentStep<_PurchaseInvoiceRecord> step) =>
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

  /// Record the supplier's IRN on the selected bill. An approved bill's
  /// editor is read-only, so this is how the number gets onto it (backlog 78
  /// row 5); any bill that is not cancelled takes it.
  ToolbarCommand _recordIrnCommand() => ToolbarCommand(
        id: 'record-irn',
        label: 'Record IRN',
        icon: Icons.qr_code_2_outlined,
        onPressed: _selected == null ||
                _selected!.status == 'CANCELLED' ||
                !widget.permissions.hasPermission('PURCHASE_UPDATE')
            ? null
            : () => unawaited(_recordIrn()),
      );

  Future<void> _recordIrn() async {
    final _PurchaseInvoiceRecord? selected = _selected;
    if (selected == null) return;
    final Json? saved = await askForSupplierIrn(
      context,
      billNumber: selected.invoiceNumber,
      current: selected.supplierIrn,
      save: (irn) =>
          widget.api.setPurchaseInvoiceSupplierIrn(selected.id, irn),
    );
    if (saved == null || !mounted) return;
    await _load();
    if (!mounted) return;
    final dynamic data = saved['data'];
    final String warning =
        stringValue((data is Json ? data : saved)['irn_warning']);
    NotificationService.show(
      context,
      warning.isNotEmpty
          ? warning
          : 'IRN recorded on ${selected.invoiceNumber}.',
      kind: warning.isNotEmpty
          ? AppNotificationKind.warning
          : AppNotificationKind.success,
    );
  }

  /// Every column the grid can show; Columns picks among them, remembered
  /// per screen on this PC (owner, 2026-09-27).
  late final ColumnChoice<_PurchaseInvoiceRecord> _columns = ColumnChoice(
    preferences: widget.preferences,
    stateKey: 'purchase-invoices.grid',
    columns: [
      ChoosableColumn(
        column: const GridColumn(key: 'number', label: 'Invoice Number'),
        cell: (item) => item.invoiceNumber,
        required: true,
      ),
      // The supplier's bill kept with this one (PG-4): a clip and a count.
      ChoosableColumn(
        column: const GridColumn(key: 'files', label: 'Files'),
        cell: (item) =>
            item.attachedFileCount > 0 ? '\u{1F4CE} ${item.attachedFileCount}' : '',
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'vendor', label: 'Supplier', priority: 1),
        cell: (item) => item.vendorName,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'supplier', label: 'Supplier Invoice'),
        cell: (item) => item.supplierInvoiceNumber,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'due', label: 'Due Date'),
        cell: (item) => item.dueDate,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'date', label: 'Invoice Date'),
        cell: (item) => documentDateStamp(item.invoiceDate, item.createdAt),
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

  Widget _buildInvoiceGrid() => EnterpriseDataGrid<_PurchaseInvoiceRecord>(
        columns: _columns.gridColumns,
        items: _invoices,
        id: (item) => item.id,
        selectedId: _selected?.id,
        // Ticks, for a bulk approve or cancel. A single row is still chosen
        // by clicking it.
        selectedIds: _ticked,
        onSelectionChanged: (ticked) => setState(() => _ticked = ticked),
        cells: _columns.cells,
        onSelect: (item) => unawaited(_selectInvoice(item)),
        onOpen: (item) => unawaited(_openInvoice(item)),
        total: _total,
        pageOffset: (_page - 1) * _rowsPerPage,
        rowsPerPage: _rowsPerPage,
        onPageChanged: (offset) {
          final int next = offset ~/ _rowsPerPage + 1;
          if (next != _page) _load(requestedPage: next);
        },
      );

  /// Show one invoice: header, lines, totals and timeline.
  Future<void> _openInvoice(_PurchaseInvoiceRecord record) async {
    await _selectInvoice(record);
    if (!mounted) return;
    // Backlog 65 row 5: where this bill charges a rate other than its
    // receipt's. Null when it could not be asked, so the panel never claims
    // "no variance" for a read that failed.
    List<Json>? variance;
    try {
      variance = await widget.api.purchaseInvoicePriceVariance(record.id);
    } on ApiException {
      variance = null;
    }
    if (!mounted) return;
    // Backlog 68 row 8, phase 2 only: a reverse-charge bill names the
    // self-invoice raised for it and the tax the firm owes itself.
    final String selfInvoice = Phase2Scope.of(context) &&
            record.selfInvoiceNumber.isNotEmpty
        ? ' · Self-invoice ${record.selfInvoiceNumber}'
            ' (reverse charge ${record.reverseChargeTaxTotal})'
        : '';
    final Object? outcome = await showDialog<Object>(
      context: context,
      builder: (_) => DocumentViewDialog(
        steps: DocumentStepStrip<_PurchaseInvoiceRecord>(
          record: record,
          steps: _steps,
        ),
        title: record.invoiceNumber,
        subtitle:
            'Supplier invoice ${record.supplierInvoiceNumber}$selfInvoice',
        icon: Icons.request_quote_outlined,
        header: record.toHeader(),
        lines: [
          for (final _PurchaseInvoiceLine line in record.lines)
            DocumentLineSnapshot(
              lineNumber: line.lineNumber,
              product: _labels.product(line.productId),
              description: line.description,
              uom: _labels.unit(line.invoiceUomId),
              packaging: line.packagingTypeId,
              quantity: line.shownQuantity,
              unitPrice: line.unitPrice,
              discount: line.discountAmount,
              taxProfile: _labels.taxProfile(line.taxProfileId),
              amount: line.grossAmount,
              netAmount: line.netAmount,
              remarks: line.remarks,
              itcEligibility: line.itcEligibility,
            ),
        ],
        totals: record.toTotals(),
        history: _history,
        extra: variance == null ? null : _variancePanel(context, variance),
      ),
    );
    await _afterWindow(outcome);
  }

  /// The bill's price variance: each line charged at a rate other than its
  /// receipt's, with both rates and what the difference comes to.
  Widget _variancePanel(BuildContext context, List<Json> rows) {
    final ThemeData theme = Theme.of(context);
    return Column(
      key: const ValueKey('purchase-invoice-price-variance'),
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text('Price variance', style: theme.textTheme.titleSmall),
        const SizedBox(height: 4),
        if (rows.isEmpty)
          Text(
            'Every line is charged at its receipt’s rate.',
            style: theme.textTheme.bodySmall,
          )
        else
          for (final Json row in rows)
            Padding(
              padding: const EdgeInsets.only(bottom: 2),
              child: Text(_varianceLine(row),
                  style: theme.textTheme.bodySmall),
            ),
      ],
    );
  }

  static String _varianceLine(Json row) {
    final String note = stringValue(row['note']);
    final String head = 'Line ${row['line_number']} · ${row['product_name']}: '
        'received at ${row['receipt_rate']}, billed at ${row['bill_rate']} '
        '× ${row['quantity']}';
    return note.isNotEmpty ? '$head — $note' : '$head = ${row['variance']}';
  }

  Future<void> _selectInvoice(_PurchaseInvoiceRecord row) async {
    setState(() => _selected = row);
    try {
      final Map<String, dynamic> timeline = _unwrap(
          await widget.api.documentHistory('purchase-invoices', row.id));
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

  List<_PurchaseInvoiceRecord> _recordsFromResponse(
      Map<String, dynamic> response) {
    final dynamic data = response['data'];
    if (data is! List) {
      return const [];
    }
    return data
        .whereType<Map>()
        .map((item) =>
            _PurchaseInvoiceRecord.fromJson(Map<String, dynamic>.from(item)))
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

class _PurchaseInvoiceRecord {
  const _PurchaseInvoiceRecord({
    required this.id,
    required this.invoiceNumber,
    required this.invoiceDate,
    required this.supplierInvoiceNumber,
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
    this.dueDate = '',
    this.createdAt = '',
    this.selfInvoiceNumber = '',
    this.supplierIrn = '',
    this.reverseChargeTaxTotal = '0',
    required this.currencyCode,
    required this.exchangeRate,
    required this.paymentTerms,
    required this.remarks,
    this.attachedFileCount = 0,
    required this.lines,
    required this.sources,
  });

  final String id;
  final String invoiceNumber;
  final String invoiceDate;
  final String supplierInvoiceNumber;
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
  final String dueDate;
  final String createdAt;

  /// The self-invoice raised for a reverse-charge supply, and the tax the
  /// firm owes itself on it -- outside the payable (backlog 68 row 8).
  final String selfInvoiceNumber;

  /// The IRN printed on the supplier's e-invoice, empty when none is on file.
  final String supplierIrn;
  final String reverseChargeTaxTotal;
  final String currencyCode;
  final String exchangeRate;
  final String paymentTerms;
  final String remarks;
  final int attachedFileCount;
  final List<_PurchaseInvoiceLine> lines;
  final List<Json> sources;

  factory _PurchaseInvoiceRecord.fromJson(Map<String, dynamic> json) {
    final List<_PurchaseInvoiceLine> lines = (json['lines'] is List)
        ? (json['lines'] as List)
            .whereType<Map>()
            .map((item) =>
                _PurchaseInvoiceLine.fromJson(Map<String, dynamic>.from(item)))
            .toList()
        : const [];
    return _PurchaseInvoiceRecord(
      id: stringValue(json['id']),
      invoiceNumber: stringValue(json['invoice_number']),
      invoiceDate: stringValue(json['invoice_date']),
      supplierInvoiceNumber: stringValue(json['supplier_invoice_number']),
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
      dueDate: stringValue(json['due_date']),
      createdAt: stringValue(json['created_at']),
      selfInvoiceNumber: stringValue(json['self_invoice_number']),
      supplierIrn: stringValue(json['supplier_irn']),
      reverseChargeTaxTotal: stringValue(json['reverse_charge_tax_total']),
      currencyCode: stringValue(json['currency_code']),
      exchangeRate: stringValue(json['exchange_rate']),
      paymentTerms: stringValue(json['payment_terms']),
      remarks: stringValue(json['remarks']),
      attachedFileCount:
          int.tryParse(stringValue(json['attached_file_count'])) ?? 0,
      lines: lines,
      sources: (json['sources'] is List)
          ? (json['sources'] as List)
              .whereType<Map>()
              .map((item) => Map<String, dynamic>.from(item))
              .toList()
          : const [],
    );
  }

  DocumentHeaderSnapshot toHeader() => DocumentHeaderSnapshot(
        documentTypeCode: 'PURCHASE_INVOICE',
        documentTypeName: 'Purchase Invoice',
        documentNumber: invoiceNumber,
        documentDate: invoiceDate,
        reference: supplierInvoiceNumber,
        branch: branchId,
        firm: '',
        businessProfile: businessProfileId,
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

class _PurchaseInvoiceLine {
  const _PurchaseInvoiceLine({
    required this.lineNumber,
    required this.productId,
    required this.description,
    required this.invoiceUomId,
    required this.packagingTypeId,
    required this.currentInvoiceQuantity,
    required this.unitPrice,
    required this.discountAmount,
    required this.taxProfileId,
    required this.grossAmount,
    required this.netAmount,
    required this.remarks,
    this.enteredQuantity = '',
    this.itcEligibility = '',
    this.taxRuleCode,
    this.taxRuleVersion,
  });

  final int lineNumber;
  final String productId;
  final String description;
  final String invoiceUomId;
  final String packagingTypeId;
  final String currentInvoiceQuantity;

  /// What was typed, in [invoiceUomId], where the line was typed in another
  /// unit than the receipt line it bills (D-PRC-37); empty otherwise.
  /// [currentInvoiceQuantity] is then the same goods in the receipt line's
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
      enteredQuantity.isEmpty ? currentInvoiceQuantity : enteredQuantity;

  /// The input credit status the server resolved for the line.
  final String itcEligibility;

  /// The tax rule that decided this line's tax; null when none matched.
  final String? taxRuleCode;
  final int? taxRuleVersion;

  factory _PurchaseInvoiceLine.fromJson(Map<String, dynamic> json) =>
      _PurchaseInvoiceLine(
        lineNumber: (json['line_number'] as num?)?.toInt() ?? 0,
        productId: stringValue(json['product_id']),
        description: stringValue(json['description']),
        invoiceUomId: stringValue(json['invoice_uom_id']),
        packagingTypeId: stringValue(json['packaging_type_id']),
        currentInvoiceQuantity: stringValue(json['current_invoice_quantity']),
        enteredQuantity: stringValue(json['entered_quantity']),
        unitPrice: stringValue(json['unit_price']),
        discountAmount: stringValue(json['discount_amount']),
        taxProfileId: stringValue(json['tax_profile_id']),
        grossAmount: stringValue(json['gross_amount']),
        netAmount: stringValue(json['net_amount']),
        remarks: stringValue(json['remarks']),
        itcEligibility: stringValue(json['itc_eligibility']),
        taxRuleCode: LineTaxRule.fromJson(json).code,
        taxRuleVersion: LineTaxRule.fromJson(json).version,
      );
}
