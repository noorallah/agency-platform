import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/preferences/desktop_preferences_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/bulk_action.dart';
import '../../models/document_framework.dart';
import '../../phase2/indian_format.dart';
import '../document_framework/document_framework_widgets.dart';
import '../document_framework/document_status_gate.dart';
import '../document_framework/document_line_labels.dart';
import '../document_framework/document_view_dialog.dart';
import '../../models/entities.dart';
import '../trade_licences/licence_check_dialog.dart';
import '../workspace/bulk_action.dart';
import '../workspace/desktop_framework.dart';
import '../workspace/reason_prompt.dart';
import 'sales_invoice_editor_dialog.dart';
import '../workspace/print_settings_dialog.dart';
import '../workspace/printed_document.dart';
import 'credit_notice.dart';
import 'price_floor_check_dialog.dart';
import 'sales_workflow_settings_dialog.dart';

/// A named view over the one sales invoice list.
///
/// The module declared seven sidebar entries -- Pending, Overdue, Register,
/// Invoice vs Delivery, Customer Outstanding and History alongside the list --
/// and this page never took a tab id, so all seven opened exactly this screen.
/// The five report entries name endpoints that do exist
/// (`/api/v1/sales-invoices/reports/*`) and are reachable from **Reports**,
/// which is where a report belongs.
enum SalesInvoiceView {
  all,
  draft,
  approved,
  cancelled,
  closed;

  /// The status this view filters on, or null for every status.
  String? get status => switch (this) {
        SalesInvoiceView.draft => 'DRAFT',
        SalesInvoiceView.approved => 'APPROVED',
        SalesInvoiceView.cancelled => 'CANCELLED',
        SalesInvoiceView.closed => 'CLOSED',
        SalesInvoiceView.all => null,
      };

  /// The query the list is asked for.
  Map<String, String> get query =>
      status == null ? const {} : {'status': status!};

  String get label => switch (this) {
        SalesInvoiceView.all => 'All',
        SalesInvoiceView.draft => 'Draft',
        SalesInvoiceView.approved => 'Approved',
        SalesInvoiceView.cancelled => 'Cancelled',
        SalesInvoiceView.closed => 'Closed',
      };

  /// The view a retired sidebar entry stood for.
  ///
  /// Only Pending has one: `/reports/pending` is the invoices still in draft,
  /// so somebody whose stored workspace says `pending-invoices` gets Draft.
  /// Overdue cannot be a view here -- it needs the due date *and* what is
  /// still unpaid, which the list endpoint cannot express and the report can.
  static SalesInvoiceView fromTabId(String? tabId) =>
      tabId == 'pending-invoices'
          ? SalesInvoiceView.draft
          : SalesInvoiceView.all;
}

class SalesInvoiceManagementPage extends StatefulWidget {
  const SalesInvoiceManagementPage({
    super.key,
    required this.api,
    required this.preferences,
    required this.permissions,
    required this.hasActiveFirm,
    this.initialView = SalesInvoiceView.all,
    this.onOpenGlobalSearch,
  });

  final ApiClient api;
  final DesktopPreferencesService preferences;
  final PermissionService permissions;
  final bool hasActiveFirm;
  final SalesInvoiceView initialView;
  final Future<void> Function()? onOpenGlobalSearch;

  @override
  State<SalesInvoiceManagementPage> createState() =>
      _SalesInvoiceManagementPageState();
}

class _SalesInvoiceManagementPageState
    extends State<SalesInvoiceManagementPage> {
  final TextEditingController _search = TextEditingController();

  /// The document dates the list is narrowed to (owner, 2026-09-27).
  DatePeriod _period = const DatePeriod.all();
  late SalesInvoiceView _view = widget.initialView;
  bool _loading = false;
  static const int _rowsPerPage = 50;
  int _page = 1;
  int _total = 0;
  String? _error;
  List<Map<String, dynamic>> _invoices = const [];
  Map<String, dynamic>? _selected;
  Map<String, dynamic> _summary = const {};

  /// The rows ticked for a bulk approve or cancel (backlog 56 A). Only rows
  /// on the page being read stay ticked.
  Set<String> _ticked = <String>{};

  /// What the invoice view prints for a line's product, unit and tax profile.
  DocumentLineLabels _labels = const DocumentLineLabels();

  Future<void> _loadLabels() async {
    final DocumentLineLabels labels = await DocumentLineLabels.load(widget.api);
    if (!mounted) return;
    setState(() => _labels = labels);
  }

  @override
  void initState() {
    super.initState();
    unawaited(_load());
    unawaited(_loadLabels());
  }

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  /// Whether the signed-in user may run this lifecycle action.
  ///
  /// The backend gates approve, close, complete and dispatch on
  /// SALES_APPROVE and cancel on SALES_CANCEL. The toolbar used to enable
  /// every action for anyone holding SALES_VIEW, so a read-only user was
  /// offered buttons the server would refuse.
  bool _mayApprove() => widget.permissions.hasPermission('SALES_APPROVE');

  bool _mayRun(DocumentToolbarAction action) => switch (action) {
        DocumentToolbarAction.approve ||
        DocumentToolbarAction.close ||
        DocumentToolbarAction.archive ||
        DocumentToolbarAction.requestApproval =>
          _mayApprove(),
        DocumentToolbarAction.cancel ||
        DocumentToolbarAction.reject =>
          widget.permissions.hasPermission('SALES_CANCEL'),
        DocumentToolbarAction.newDocument => widget.permissions.hasPermission(
            'SALES_CREATE',
          ),
        DocumentToolbarAction.save => widget.permissions.hasPermission(
            'SALES_UPDATE',
          ),
        DocumentToolbarAction.exportDocument =>
          widget.permissions.hasPermission(
            'SALES_EXPORT',
          ),
        _ => true,
      };

  /// The lifecycle action a toolbar button stands for, or null when it is not
  /// a lifecycle action at all.
  DocumentLifecycleAction? _lifecycleOf(DocumentToolbarAction action) =>
      switch (action) {
        DocumentToolbarAction.approve => DocumentLifecycleAction.approve,
        DocumentToolbarAction.dispatch => DocumentLifecycleAction.dispatch,
        DocumentToolbarAction.complete => DocumentLifecycleAction.complete,
        DocumentToolbarAction.cancel => DocumentLifecycleAction.cancel,
        DocumentToolbarAction.close => DocumentLifecycleAction.close,
        _ => null,
      };

  /// Whether [action] may run against the selected document right now.
  ///
  /// Permission alone used to decide this, so Approve was live on an
  /// already-approved document and Close on a closed one; pressing either
  /// produced a refusal the screen could have predicted. The gate states the
  /// same rule the service enforces.
  bool _statusAllows(DocumentToolbarAction action, String? status) {
    final DocumentLifecycleAction? lifecycle = _lifecycleOf(action);
    // Not a lifecycle action -- New, Print and the rest are unaffected.
    if (lifecycle == null) return true;
    return DocumentStatusGate.salesInvoice.allows(lifecycle, status);
  }

  Future<void> _load({int? requestedPage}) async {
    // Read before any await: whether to pick the first row (phase 1 only).
    final bool pickFirst =
        context.getInheritedWidgetOfExactType<Phase2Scope>() == null;
    if (!widget.hasActiveFirm ||
        !widget.permissions.hasPermission('SALES_VIEW')) {
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
        widget.api.documentSummary('sales-invoices', path: 'reports/summary'),
        widget.api.documentPage(
          'sales-invoices',
          page: _page,
          pageSize: _rowsPerPage,
          search: _search.text.trim(),
          sortBy: 'invoice_date',
          descending: true,
          additionalQuery: {
            ..._view.query,
            ..._period.query('invoice_from', 'invoice_to'),
          },
        ),
      ]);
      final Map<String, dynamic> summary = _unwrap(responses[0]);
      final Map<String, dynamic> page = _unwrap(responses[1]);
      final List<Map<String, dynamic>> rows =
          ((page['data'] as List?) ?? const [])
              .whereType<Map>()
              .map((item) => Map<String, dynamic>.from(item))
              .toList(growable: false);
      final Object? pagination = page['pagination'];
      final int total = pagination is Map
          ? (pagination['total_records'] as num?)?.toInt() ?? rows.length
          : rows.length;
      // Phase 2 (option C): nothing is picked for the user -- the selection
      // bar opens when somebody clicks a row, and stays with that row.
      final Map<String, dynamic>? kept = _selected == null
          ? null
          : rows.cast<Map<String, dynamic>?>().firstWhere(
                (item) => item!['id'] == _selected!['id'],
                orElse: () => null,
              );
      final Map<String, dynamic>? selected =
          kept ?? (pickFirst && rows.isNotEmpty ? rows.first : null);
      if (!mounted) return;
      setState(() {
        _summary = summary;
        _invoices = rows;
        _total = total;
        _selected = selected;
        _ticked = _ticked
            .where((id) => rows.any((row) => '${row['id']}' == id))
            .toSet();
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() => _error = error.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  /// More than one row ticked: the bar names the batch and offers the two
  /// bulk actions instead of the one row's.
  bool get _bulkMode => _ticked.length > 1;

  List<Map<String, dynamic>> get _tickedRows => [
        for (final Map<String, dynamic> row in _invoices)
          if (_ticked.contains('${row['id']}')) row,
      ];

  List<BulkRow> _bulkRows() => [
        for (final Map<String, dynamic> row in _tickedRows)
          (id: '${row['id']}', version: (row['version'] as num?)?.toInt()),
      ];

  SelectionSummary _bulkSummary() {
    double total = 0;
    for (final Map<String, dynamic> row in _tickedRows) {
      total += double.tryParse('${row['grand_total'] ?? ''}') ?? 0;
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
              _loading || !widget.permissions.hasPermission('SALES_CANCEL')
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
      send: widget.api.bulkApproveSalesInvoices,
    );
    await _afterBulk();
  }

  Future<void> _bulkCancel() async {
    final List<BulkRow> rows = _bulkRows();
    final String? reason = await askForReason(
      context,
      title: 'Cancel ${rows.length} invoices',
      explanation: 'Each invoice is cancelled on its own and its journal is '
          'reversed; one the server refuses does not stop the others. The '
          'reason is recorded on every invoice cancelled.',
      confirmLabel: 'Cancel invoices',
    );
    if (reason == null || !mounted) return;
    await runBulkAction(
      context,
      verb: 'Cancelled',
      rows: rows,
      send: (rows) => widget.api.bulkCancelSalesInvoices(rows, reason),
    );
    await _afterBulk();
  }

  Future<void> _afterBulk() async {
    if (!mounted) return;
    setState(() => _ticked = <String>{});
    await _load();
  }

  Future<void> _act(
    String suffix, {
    String? overrideReason,
    String? priceOverrideReason,
  }) async {
    final Map<String, dynamic>? selected = _selected;
    if (selected == null) return;
    try {
      await widget.api.documentAction(
        'sales-invoices',
        selected['id'] as String,
        suffix,
        query: overrideReason == null && priceOverrideReason == null
            ? null
            : {
                if (overrideReason != null)
                  'licence_override_reason': overrideReason,
                if (priceOverrideReason != null)
                  'price_override_reason': priceOverrideReason,
              },
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

  /// Warn before approving, because approval is where the receivable is
  /// posted and the credit limit is committed.
  ///
  /// The check has to run *before* the call: once the invoice is approved its
  /// value is already in the outstanding balance, and asking afterwards with
  /// the same amount would count it twice.
  Future<void> _warnOnCredit(Map<String, dynamic> invoice) =>
      warnOnCreditExposure(
        context,
        widget.api,
        customerId: invoice['customer_id'] as String?,
        amount: '${invoice['grand_total'] ?? '0'}',
      );

  /// Ask what the invoice's lines need, licence-wise, before approving it
  /// (backlog 54), before the call for the same reason as [_warnOnCredit].
  Future<LicenceCheckOutcome> _checkLicences(Map<String, dynamic> invoice) =>
      confirmLicenceCheck(
        context,
        widget.api,
        widget.permissions,
        document: 'SALES_INVOICE',
        documentId: invoice['id'] as String,
      );

  /// Ask whether the invoice's lines are priced under their floor before
  /// approving it (backlog 64 row 2), before the call for the same reason as
  /// [_warnOnCredit]. A block carries the reason of whoever may override it.
  Future<PriceFloorOutcome> _checkPriceFloor(Map<String, dynamic> invoice) =>
      confirmPriceFloor(
        context,
        widget.permissions,
        check: () => widget.api.salesInvoicePriceCheck(invoice['id'] as String),
      );

  DocumentHeaderSnapshot _headerFor(Map<String, dynamic> row) =>
      DocumentHeaderSnapshot(
        documentTypeCode: 'SALES_INVOICE',
        documentTypeName: 'Sales Invoice',
        documentNumber: '${row['invoice_number'] ?? '-'}',
        documentDate: '${row['invoice_date'] ?? '-'}',
        status: '${row['status'] ?? 'DRAFT'}',
        party: '${row['customer_name'] ?? ''}',
        partyLabel: 'Customer',
        reference: (row['reference_number'] as String?) ?? '',
        branch: _labels.branch('${row['branch_id'] ?? ''}'),
        remarks: (row['remarks'] as String?) ?? '',
      );

  DocumentTotalsSnapshot _totalsFor(Map<String, dynamic> row) =>
      DocumentTotalsSnapshot(
        subtotal: '${row['subtotal'] ?? '0'}',
        discount: '${row['line_discount_total'] ?? '0'}',
        tax: '${row['tax_total'] ?? '0'}',
        charges: '${row['additional_charges'] ?? '0'}',
        roundOff: '${row['round_off'] ?? '0'}',
        grandTotal: '${row['grand_total'] ?? '0'}',
      );

  List<DocumentLineSnapshot> _linesFor(Map<String, dynamic> row) =>
      ((row['lines'] as List?) ?? const []).whereType<Map>().map((line) {
        final Map<String, dynamic> item = Map<String, dynamic>.from(line);
        return DocumentLineSnapshot(
          lineNumber: (item['line_number'] as num?)?.toInt() ?? 0,
          product: _labels.product('${item['product_id'] ?? ''}'),
          description: (item['description'] as String?) ?? '',
          uom: _labels.unit('${item['invoice_uom_id'] ?? ''}'),
          packaging: '${item['packaging_type_id'] ?? ''}',
          quantity: '${item['current_invoice_quantity'] ?? '0'}',
          unitPrice: '${item['unit_price'] ?? '0'}',
          discount: '${item['discount_amount'] ?? '0'}',
          discountPercent: '${item['discount_percent'] ?? ''}',
          taxProfile: _labels.taxProfile('${item['tax_profile_id'] ?? ''}'),
          amount: '${item['gross_amount'] ?? '0'}',
          netAmount: '${item['net_amount'] ?? '0'}',
          remarks: (item['remarks'] as String?) ?? '',
        );
      }).toList(growable: false);

  /// Select a row. Selecting no longer costs a request.
  void _selectInvoice(Map<String, dynamic> row) {
    setState(() => _selected = row);
  }

  /// Show one invoice: header, lines, totals and timeline.
  Future<void> _openInvoice(Map<String, dynamic> row) async {
    setState(() => _selected = row);
    List<DocumentTimelineSnapshot> history = const [];
    try {
      final Map<String, dynamic> timeline = _unwrap(
        await widget.api.documentHistory('sales-invoices', row['id']),
      );
      history = ((timeline['data'] as List?) ?? const [])
          .whereType<Map>()
          .map(
            (item) => DocumentTimelineSnapshot.fromJson(
              Map<String, dynamic>.from(item),
            ),
          )
          .toList(growable: false);
    } on ApiException {
      history = const [];
    }
    if (!mounted) return;
    await showDialog<void>(
      context: context,
      builder: (_) => DocumentViewDialog(
        title: '${row['invoice_number'] ?? '-'}',
        subtitle: 'Sales invoice dated ${row['invoice_date'] ?? '-'}',
        icon: Icons.receipt_long_outlined,
        header: _headerFor(row),
        lines: _linesFor(row),
        totals: _totalsFor(row),
        history: history,
      ),
    );
  }

  /// Run a lifecycle action, warning first where the firm's credit policy
  /// says to.
  ///
  /// Before the approval, not after: the document has to be counted once in
  /// the exposure it is being checked against. A warning and never a block --
  /// the server refuses when the policy says Block.
  Future<void> _run(DocumentToolbarAction action, String suffix) async {
    final Map<String, dynamic>? selected = _selected;
    if (selected == null) return;
    if (action == DocumentToolbarAction.approve) {
      await _warnOnCredit(selected);
      if (!mounted) return;
      final LicenceCheckOutcome licence = await _checkLicences(selected);
      if (!licence.proceed) return;
      if (!mounted) return;
      final PriceFloorOutcome price = await _checkPriceFloor(selected);
      if (!price.proceed) return;
      await _act(
        suffix,
        overrideReason: licence.overrideReason,
        priceOverrideReason: price.overrideReason,
      );
      return;
    }
    await _act(suffix);
  }

  @override
  Widget build(BuildContext context) => EnterpriseWorkspace(
        title: 'Sales Invoices',
        description:
            'Manage customer invoices, receivables, and accounting events.',
        breadcrumbs: const ['Workspace', 'Sales Invoices'],
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
                children: Phase2Scope.of(context)
                    ? _viewCounters()
                    : [
                        _card('Total', '${_summary['total'] ?? 0}'),
                        _card('Draft', '${_summary['draft'] ?? 0}'),
                        _card('Approved', '${_summary['approved'] ?? 0}'),
                        _card(
                            'Pending', '${_summary['pending_invoices'] ?? 0}'),
                        _card(
                            'Overdue', '${_summary['overdue_invoices'] ?? 0}'),
                      ],
              ),
            ),
            // Bounded, so the layout below has a height to divide.
            Expanded(child: _buildGridWorkspace()),
          ],
        ),
      );

  /// Raise an invoice against a delivery note that still has something to bill.
  Future<void> _newInvoice() async {
    // A tab of its own in phase 2 (4.8), the same dialog in phase 1.
    final bool? created = await showDocument<bool>(
      context,
      title: 'New invoice',
      builder: (_) =>
          SalesInvoiceEditorDialog(api: widget.api, today: DateTime.now()),
    );
    if (created != true) return;
    if (!mounted) return;
    NotificationService.show(
      context,
      'Invoice created as a draft. Approve it to post the journal.',
      kind: AppNotificationKind.success,
    );
    await _load(requestedPage: 1);
  }

  /// Reopen a draft and correct it.
  Future<void> _editInvoice(Map<String, dynamic> invoice) async {
    final bool? saved = await showDocument<bool>(
      context,
      title: 'Invoice ${invoice['invoice_number'] ?? ''}'.trim(),
      builder: (_) => SalesInvoiceEditorDialog(
        api: widget.api,
        today: DateTime.now(),
        invoiceId: invoice['id'] as String,
      ),
    );
    if (saved != true) return;
    if (!mounted) return;
    NotificationService.show(
      context,
      'Invoice updated.',
      kind: AppNotificationKind.success,
    );
    await _load();
  }

  /// Save the bill and hand it to whatever opens PDFs on this machine.
  ///
  /// Saved rather than shown in a viewer of our own: the file is the thing the
  /// customer is sent, and the operating system already has a reader for it.
  Future<void> _printInvoice(Map<String, dynamic> invoice) async {
    final String number = '${invoice['invoice_number'] ?? 'invoice'}';
    try {
      final List<int> pdf = await widget.api.salesInvoicePdf(
        invoice['id'] as String,
      );
      if (!mounted) return;
      await printDocument(context, bytes: pdf, documentName: number);
    } on ApiException catch (exception) {
      if (!mounted) return;
      NotificationService.show(
        context,
        exception.message,
        kind: AppNotificationKind.error,
      );
    }
  }

  /// How this firm prints its bills: copies, letterhead, terms, paper.
  Future<void> _openPrintSettings() async {
    await showDialog<bool>(
      context: context,
      builder: (_) => PrintSettingsDialog(
        api: widget.api,
        permissions: widget.permissions,
        documentType: 'SALES_INVOICE',
        documentLabel: 'sales invoice',
      ),
    );
  }

  /// Phase 2 (UI_PHASE_2_DESIGN.md 4.5): one counter per view with its
  /// count, and clicking one is choosing that view -- click it again for
  /// all. The summary endpoint counts every status the views filter on.
  List<Widget> _viewCounters() => [
        for (final SalesInvoiceView view in SalesInvoiceView.values)
          SummaryCount(
            key: ValueKey('view-counter-${view.name}'),
            label: view.label,
            value: '${_summary[view.status?.toLowerCase() ?? 'total'] ?? 0}',
            selected: _view == view,
            onTap: _loading
                ? null
                : () => _selectView(
                      _view == view ? SalesInvoiceView.all : view,
                    ),
          ),
        SummaryCount(
          label: 'Pending',
          value: '${_summary['pending_invoices'] ?? 0}',
        ),
        SummaryCount(
          label: 'Overdue',
          value: '${_summary['overdue_invoices'] ?? 0}',
          alert: true,
        ),
      ];

  void _selectView(SalesInvoiceView view) {
    if (view == _view) return;
    setState(() {
      _view = view;
      _page = 1;
      _selected = null;
    });
    unawaited(_load(requestedPage: 1));
  }

  /// The status bar: All / Draft / Approved / Cancelled / Closed.
  Widget _buildViewBar() => SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: SegmentedButton<SalesInvoiceView>(
          segments: [
            for (final SalesInvoiceView view in SalesInvoiceView.values)
              ButtonSegment<SalesInvoiceView>(
                  value: view, label: Text(view.label)),
          ],
          selected: <SalesInvoiceView>{_view},
          onSelectionChanged:
              _loading ? null : (selection) => _selectView(selection.first),
          showSelectedIcon: false,
        ),
      );

  Widget _buildGridWorkspace() => ManagementWorkspaceLayout(
        toolbar: _buildToolbar(),
        // Option C (owner, 2026-09-27): the invoice's actions on a bar that
        // names it, above the grid.
        selectionBar: true,
        selection: _bulkMode
            ? _bulkSummary()
            : _selected == null
            ? null
            : SelectionSummary.document(
                number: '${_selected!['invoice_number'] ?? ''}',
                party: '${_selected!['customer_name'] ?? ''}',
                status: '${_selected!['status'] ?? ''}',
                total: _selected!['grand_total'],
                onClear: () => setState(() => _selected = null),
              ),
        // Phase 2's counters are the views (4.5); a second row
        // of the same choices would repeat them.
        viewBar: Phase2Scope.of(context) ? null : _buildViewBar(),
        searchPanel: SearchFilterPanel(
          controller: _search,
          hintText: 'Search invoice number, customer, reference...',
          onSearch: (_) => _load(requestedPage: 1),
        ),
        primaryContent: !widget.hasActiveFirm
            ? const StandardEmptyState(type: EmptyStateType.noFirmSelected)
            : _error != null && !_loading
                ? WorkspaceEmptyState(
                    title: 'Sales invoices unavailable',
                    message: _error!,
                  )
                : _invoices.isEmpty && !_loading
                    ? StandardEmptyState(
                        type: _search.text.trim().isEmpty
                            ? EmptyStateType.noRecords
                            : EmptyStateType.noSearchResults,
                      )
                    : _buildInvoiceGrid(),
        // No side pane. It sat at `flex: 4` against a `flex: 3` list.
        detailsPanel: null,
        statusBar: WorkspaceStatusBar(
          total: _total,
          selected: _selected != null,
          message: _loading ? 'Loading...' : null,
        ),
      );

  Widget _buildToolbar() =>
      Phase2Scope.of(context) ? _phase2Toolbar() : _phase1Toolbar();

  /// Phase 2 (4.11): View, Edit and Refresh as icons; Print and the bill's
  /// own steps as buttons that fold into "..." when the line is short; the
  /// settings behind "..."; "+ New" last.
  Widget _phase2Toolbar() {
    final Map<String, dynamic>? selected = _selected;
    final String status = '${selected?['status'] ?? ''}';
    final bool canCreate = widget.permissions.hasPermission('SALES_CREATE');
    final bool canEdit = widget.permissions.hasPermission('SALES_UPDATE');
    return WorkspaceToolbar(
      // Period right after the search, as Sales Returns has it (owner,
      // 2026-09-27), then Columns.
      trailing: [..._listTools(), _columnsButton()],
      actions: [
        ToolbarAction.view,
        if (canEdit) ToolbarAction.edit,
        ToolbarAction.refresh,
        if (canCreate) ToolbarAction.newItem,
      ],
      isEnabled: (action) =>
          !_loading &&
          switch (action) {
            ToolbarAction.view => selected != null && !_bulkMode,
            ToolbarAction.edit =>
              selected != null && status == 'DRAFT' && !_bulkMode,
            ToolbarAction.refresh => true,
            ToolbarAction.newItem => widget.hasActiveFirm,
            _ => false,
          },
      onAction: (action) {
        switch (action) {
          case ToolbarAction.view:
            if (selected != null) unawaited(_openInvoice(selected));
          case ToolbarAction.edit:
            if (selected != null) unawaited(_editInvoice(selected));
          case ToolbarAction.refresh:
            unawaited(_load());
          case ToolbarAction.newItem:
            unawaited(_newInvoice());
          default:
            break;
        }
      },
      commands: _bulkMode
          ? _bulkCommands()
          : [
        ToolbarCommand(
          id: 'print',
          label: 'Print',
          icon: Icons.print_outlined,
          onPressed: selected == null
              ? null
              : () => unawaited(_printInvoice(selected)),
        ),
        _command(DocumentToolbarAction.approve, '/approve'),
        ToolbarCommand(
          id: 'use-points',
          label: 'Use points',
          icon: Icons.card_giftcard,
          onPressed: selected == null ||
                  _loading ||
                  !widget.permissions.hasPermission('LOYALTY_MANAGE') ||
                  const <String>{'DRAFT', 'CANCELLED'}.contains(status)
              ? null
              : () => unawaited(_redeem(selected)),
        ),
        _command(DocumentToolbarAction.cancel, '/cancel'),
        _command(DocumentToolbarAction.close, '/close'),
        ToolbarCommand(
          id: 'print-settings',
          label: 'Print settings',
          icon: Icons.tune_outlined,
          menuOnly: true,
          onPressed: () => unawaited(_openPrintSettings()),
        ),
        ToolbarCommand(
          id: 'sales-stages',
          label: 'Sales stages',
          icon: Icons.linear_scale_outlined,
          menuOnly: true,
          onPressed: () => unawaited(_openWorkflowSettings()),
        ),
              ],
    );
  }

  Widget _phase1Toolbar() => WorkspaceToolbar(
        actions: const [ToolbarAction.view, ToolbarAction.refresh],
        commands: _bulkMode ? _bulkCommands() : const [],
        isEnabled: (action) =>
            !_loading &&
            switch (action) {
              ToolbarAction.view => _selected != null && !_bulkMode,
              ToolbarAction.refresh => true,
              _ => false,
            },
        onAction: (action) {
          switch (action) {
            case ToolbarAction.view:
              final Map<String, dynamic>? selected = _selected;
              if (selected != null) unawaited(_openInvoice(selected));
            case ToolbarAction.refresh:
              unawaited(_load());
            default:
              break;
          }
        },
        trailing: [
          // First in the row, because raising a bill is the reason somebody
          // opens this screen -- and until 2026-08-23 there was no way to do
          // it from the desktop at all.
          if (widget.permissions.hasPermission('SALES_CREATE'))
            Padding(
              padding: const EdgeInsets.only(left: 8),
              child: FilledButton.icon(
                onPressed: widget.hasActiveFirm
                    ? () => unawaited(_newInvoice())
                    : null,
                icon: const Icon(Icons.add, size: 18),
                label: const Text('New Invoice'),
              ),
            ),
          // Only a draft: once approved the journal is posted and the
          // customer owes the money, so a correction is a cancellation and a
          // fresh bill rather than a quiet edit.
          if (widget.permissions.hasPermission('SALES_UPDATE'))
            Padding(
              padding: const EdgeInsets.only(left: 8),
              child: OutlinedButton.icon(
                onPressed: _selected == null ||
                        '${_selected?['status'] ?? ''}' != 'DRAFT'
                    ? null
                    : () => unawaited(_editInvoice(_selected!)),
                icon: const Icon(Icons.edit_outlined, size: 18),
                label: const Text('Edit'),
              ),
            ),
          // Printing shows nothing the screen does not, so viewing is enough;
          // what it needs is an invoice selected to print.
          Padding(
            padding: const EdgeInsets.only(left: 8),
            child: OutlinedButton.icon(
              onPressed: _selected == null
                  ? null
                  : () => unawaited(_printInvoice(_selected!)),
              icon: const Icon(Icons.print_outlined, size: 18),
              label: const Text('Print'),
            ),
          ),
          // Beside Print, because that is where somebody stands when they
          // find the copies wrong.
          IconButton(
            tooltip: 'Print settings',
            onPressed: () => unawaited(_openPrintSettings()),
            icon: const Icon(Icons.tune_outlined, size: 18),
          ),
          // The stage configuration lives here rather than on the sales-order
          // screen it belongs to by endpoint, because a firm that switches the
          // order stage off can no longer see that screen -- and would have no
          // way back to the setting that hid it. The invoice is never hidden.
          IconButton(
            tooltip: 'Sales stages',
            onPressed: () => unawaited(_openWorkflowSettings()),
            icon: const Icon(Icons.linear_scale_outlined, size: 18),
          ),
          _actionButton(DocumentToolbarAction.approve, '/approve'),
          _redeemButton(),
          _actionButton(DocumentToolbarAction.cancel, '/cancel'),
          _actionButton(DocumentToolbarAction.close, '/close'),
        ],
      );

  /// Settle part of a bill with credit the customer has earned.
  ///
  /// Here rather than on the loyalty register, because this is where the bill
  /// is -- a register is for reading what happened, not for spending.
  Widget _redeemButton() => Padding(
        padding: const EdgeInsets.only(left: 8),
        child: OutlinedButton.icon(
          onPressed: _selected == null ||
                  _loading ||
                  !widget.permissions.hasPermission('LOYALTY_MANAGE') ||
                  // Only an approved bill owes anything to settle.
                  const <String>{
                    'DRAFT',
                    'CANCELLED',
                  }.contains('${_selected?['status'] ?? ''}')
              ? null
              : () => unawaited(_redeem(_selected!)),
          icon: const Icon(Icons.card_giftcard, size: 18),
          label: const Text('Use points'),
        ),
      );

  /// Ask how many points, having first said how many there are.
  ///
  /// The balance is read before the dialog opens so nobody is asked for a
  /// number without being told the ceiling -- and `redeemable` is the
  /// server's answer, so this never offers a redemption the service refuses.
  Future<void> _redeem(Map<String, dynamic> invoice) async {
    final String? customerId = invoice['customer_id'] as String?;
    if (customerId == null) return;
    late final Json held;
    try {
      held = await widget.api.loyaltyBalance(customerId);
    } on ApiException catch (error) {
      if (!mounted) return;
      NotificationService.show(
        context,
        error.message,
        kind: AppNotificationKind.error,
      );
      return;
    }
    if (!mounted) return;
    if (held['redeemable'] != true) {
      NotificationService.show(
        context,
        '${held['customer_name'] ?? 'That customer'} holds '
        '${held['points'] ?? 0} points, which cannot be spent yet.',
        kind: AppNotificationKind.information,
      );
      return;
    }
    final String? points = await askForReason(
      context,
      title: 'Use points on ${invoice['invoice_number'] ?? ''}',
      explanation: '${held['customer_name']} holds ${held['points']} points, '
          'worth ${held['amount']}. Spending them settles the bill — the tax '
          'on it does not change.',
      label: 'Points to use',
      confirmLabel: 'Use them',
    );
    if (points == null || !mounted) return;
    try {
      await widget.api.redeemLoyalty(
        invoiceId: '${invoice['id']}',
        points: points,
      );
      if (!mounted) return;
      NotificationService.show(
        context,
        '$points points used on ${invoice['invoice_number']}.',
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

  /// Show which stages of a sale this firm types, and let the right role
  /// change them.
  Future<void> _openWorkflowSettings() => showDialog<bool>(
        context: context,
        builder: (_) => SalesWorkflowSettingsDialog(
          api: widget.api,
          permissions: widget.permissions,
        ),
      );

  /// A lifecycle button, disabled unless permission **and** the selected
  /// invoice's status allow it.
  Widget _actionButton(DocumentToolbarAction action, String suffix) => Padding(
        padding: const EdgeInsets.only(left: 8),
        child: OutlinedButton.icon(
          onPressed: _selected == null ||
                  !_mayRun(action) ||
                  !_statusAllows(action, _selected?['status'] as String?)
              ? null
              : () => unawaited(_run(action, suffix)),
          icon: Icon(action.icon, size: 18),
          label: Text(action.label),
        ),
      );

  /// A lifecycle step as a phase 2 command, enabled as its button is.
  ToolbarCommand _command(DocumentToolbarAction action, String suffix) =>
      ToolbarCommand(
        id: action.name,
        label: action.label,
        icon: action.icon,
        onPressed: _selected == null ||
                !_mayRun(action) ||
                !_statusAllows(action, _selected?['status'] as String?)
            ? null
            : () => unawaited(_run(action, suffix)),
      );

  /// The Period control (owner, 2026-09-27), right after the search on
  /// phase 2's page line. Phase 1 (frozen, never shipped) has no room for it.
  List<Widget> _listTools() => [
        DateRangeFilter(
          value: _period,
          onChanged: (period) {
            setState(() => _period = period);
            unawaited(_load(requestedPage: 1));
          },
        ),
      ];

  /// Columns sits with the list's tools, between the search and Refresh,
  /// as option C draws it.
  Widget _columnsButton() => ColumnsButton(
        onPressed: () async {
          if (await _columns.choose(context) && mounted) {
            setState(() {});
          }
        },
      );

  /// Every column the list can show; the Columns button picks among them
  /// (owner, 2026-09-27), remembered per screen on this PC.
  late final ColumnChoice<Map<String, dynamic>> _columns = ColumnChoice(
    preferences: widget.preferences,
    stateKey: 'sales-invoices.grid',
    columns: [
      ChoosableColumn(
        column: const GridColumn(key: 'number', label: 'Invoice Number'),
        cell: (item) => '${item['invoice_number'] ?? '-'}',
        required: true,
      ),
      // Whose document it is (owner, 2026-09-27); kept at any width.
      ChoosableColumn(
        column: const GridColumn(key: 'customer', label: 'Customer', priority: 1),
        cell: (item) => '${item['customer_name'] ?? ''}',
        shownByDefault: true,
      ),
      // One date: the invoice's, with the minute it was entered.
      ChoosableColumn(
        column: const GridColumn(key: 'date', label: 'Invoice Date'),
        cell: (item) => documentDateStamp(item['invoice_date'], item['created_at']),
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'due', label: 'Due Date'),
        cell: (item) => '${item['due_date'] ?? ''}',
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'terms', label: 'Payment Terms'),
        cell: (item) => '${item['payment_terms'] ?? ''}',
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'reference', label: 'Reference'),
        cell: (item) => '${item['reference_number'] ?? ''}',
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'customer_invoice', label: "Customer's Reference"),
        cell: (item) => '${item['customer_invoice_number'] ?? ''}',
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'supply', label: 'Place of Supply'),
        cell: (item) => '${item['place_of_supply'] ?? ''}',
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'status', label: 'Status'),
        cell: (item) => '${item['status'] ?? ''}',
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'subtotal', label: 'Taxable Value', numeric: true),
        cell: (item) => '${item['subtotal'] ?? ''}',
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'tax', label: 'Tax', numeric: true),
        cell: (item) => '${item['tax_total'] ?? ''}',
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'discount', label: 'Line Discounts', numeric: true),
        cell: (item) => '${item['line_discount_total'] ?? ''}',
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'freight', label: 'Freight', numeric: true),
        cell: (item) => '${item['freight_amount'] ?? ''}',
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'total', label: 'Grand Total'),
        cell: (item) => '${item['grand_total'] ?? '0'}',
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'remarks', label: 'Remarks'),
        cell: (item) => '${item['remarks'] ?? ''}',
      ),
    ],
  );

  Widget _buildInvoiceGrid() => EnterpriseDataGrid<Map<String, dynamic>>(
        columns: _columns.gridColumns,
        items: _invoices,
        id: (item) => '${item['id']}',
        selectedId: _selected == null ? null : '${_selected!['id']}',
        // Ticks, for a bulk approve or cancel. A single row is still chosen
        // by clicking it.
        selectedIds: _ticked,
        onSelectionChanged: (ticked) => setState(() => _ticked = ticked),
        cells: _columns.cells,
        onSelect: _selectInvoice,
        onOpen: (item) => unawaited(_openInvoice(item)),
        total: _total,
        pageOffset: (_page - 1) * _rowsPerPage,
        rowsPerPage: _rowsPerPage,
        onPageChanged: (offset) {
          final int next = offset ~/ _rowsPerPage + 1;
          if (next != _page) _load(requestedPage: next);
        },
      );

  Widget _card(String label, String value) =>
      SummaryCount(label: label, value: value);

  Map<String, dynamic> _unwrap(dynamic response) {
    if (response is! Map<String, dynamic>) return const <String, dynamic>{};
    final dynamic data = response['data'];
    return data is Map<String, dynamic> ? data : response;
  }
}
