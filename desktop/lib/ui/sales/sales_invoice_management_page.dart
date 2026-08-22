import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/preferences/desktop_preferences_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/document_framework.dart';
import '../document_framework/document_framework_widgets.dart';
import '../document_framework/document_status_gate.dart';
import '../document_framework/document_view_dialog.dart';
import '../workspace/desktop_framework.dart';
import 'credit_notice.dart';

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
  State<SalesInvoiceManagementPage> createState() => _SalesInvoiceManagementPageState();
}

class _SalesInvoiceManagementPageState extends State<SalesInvoiceManagementPage> {
  final TextEditingController _search = TextEditingController();
  late SalesInvoiceView _view = widget.initialView;
  bool _loading = false;
  static const int _rowsPerPage = 50;
  int _page = 1;
  int _total = 0;
  String? _error;
  List<Map<String, dynamic>> _invoices = const [];
  Map<String, dynamic>? _selected;
  Map<String, dynamic> _summary = const {};

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
        DocumentToolbarAction.cancel || DocumentToolbarAction.reject =>
          widget.permissions.hasPermission('SALES_CANCEL'),
        DocumentToolbarAction.newDocument =>
          widget.permissions.hasPermission('SALES_CREATE'),
        DocumentToolbarAction.save =>
          widget.permissions.hasPermission('SALES_UPDATE'),
        DocumentToolbarAction.exportDocument =>
          widget.permissions.hasPermission('SALES_EXPORT'),
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
    if (!widget.hasActiveFirm || !widget.permissions.hasPermission('SALES_VIEW')) {
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
          additionalQuery: _view.query,
        ),
      ]);
      final Map<String, dynamic> summary = _unwrap(responses[0]);
      final Map<String, dynamic> page = _unwrap(responses[1]);
      final List<Map<String, dynamic>> rows = ((page['data'] as List?) ?? const [])
          .whereType<Map>()
          .map((item) => Map<String, dynamic>.from(item))
          .toList(growable: false);
      final Object? pagination = page['pagination'];
      final int total = pagination is Map
          ? (pagination['total_records'] as num?)?.toInt() ?? rows.length
          : rows.length;
      final Map<String, dynamic>? selected = rows.isEmpty
          ? null
          : (_selected == null
              ? rows.first
              : rows.firstWhere(
                  (item) => item['id'] == _selected!['id'],
                  orElse: () => rows.first,
                ));
      if (!mounted) return;
      setState(() {
        _summary = summary;
        _invoices = rows;
        _total = total;
        _selected = selected;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() => _error = error.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _act(String suffix) async {
    final Map<String, dynamic>? selected = _selected;
    if (selected == null) return;
    try {
      await widget.api.documentAction('sales-invoices', selected['id'] as String, suffix);
      await _load();
    } on ApiException catch (error) {
      if (!mounted) return;
      NotificationService.show(context, error.message, kind: AppNotificationKind.error);
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

  DocumentHeaderSnapshot _headerFor(Map<String, dynamic> row) =>
      DocumentHeaderSnapshot(
        documentTypeCode: 'SALES_INVOICE',
        documentTypeName: 'Sales Invoice',
        documentNumber: '${row['invoice_number'] ?? '-'}',
        documentDate: '${row['invoice_date'] ?? '-'}',
        status: '${row['status'] ?? 'DRAFT'}',
        reference: (row['reference_number'] as String?) ?? '',
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
          product: '${item['product_id'] ?? ''}',
          description: (item['description'] as String?) ?? '',
          uom: '${item['invoice_uom_id'] ?? ''}',
          packaging: '${item['packaging_type_id'] ?? ''}',
          quantity: '${item['current_invoice_quantity'] ?? '0'}',
          unitPrice: '${item['unit_price'] ?? '0'}',
          discount: '${item['discount_amount'] ?? '0'}',
          taxProfile: '${item['tax_profile_id'] ?? ''}',
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
          .map((item) =>
              DocumentTimelineSnapshot.fromJson(Map<String, dynamic>.from(item)))
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
              padding: const EdgeInsets.fromLTRB(24, 0, 24, 12),
              child: SummaryCards(children: [
                _card('Total', '${_summary['total'] ?? 0}'),
                _card('Draft', '${_summary['draft'] ?? 0}'),
                _card('Approved', '${_summary['approved'] ?? 0}'),
                _card('Pending', '${_summary['pending_invoices'] ?? 0}'),
                _card('Overdue', '${_summary['overdue_invoices'] ?? 0}'),
              ]),
            ),
            // Bounded, so the layout below has a height to divide.
            Expanded(child: _buildGridWorkspace()),
          ],
        ),
      );

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
                value: view,
                label: Text(view.label),
              ),
          ],
          selected: <SalesInvoiceView>{_view},
          onSelectionChanged:
              _loading ? null : (selection) => _selectView(selection.first),
          showSelectedIcon: false,
        ),
      );

  Widget _buildGridWorkspace() => ManagementWorkspaceLayout(
        toolbar: _buildToolbar(),
        viewBar: _buildViewBar(),
        searchPanel: SearchFilterPanel(
          controller: _search,
          hintText: 'Search invoice number, reference...',
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

  Widget _buildToolbar() => WorkspaceToolbar(
        actions: const [ToolbarAction.view, ToolbarAction.refresh],
        isEnabled: (action) =>
            !_loading &&
            switch (action) {
              ToolbarAction.view => _selected != null,
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
          _actionButton(DocumentToolbarAction.approve, '/approve'),
          _actionButton(DocumentToolbarAction.cancel, '/cancel'),
          _actionButton(DocumentToolbarAction.close, '/close'),
        ],
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

  Widget _buildInvoiceGrid() => EnterpriseDataGrid<Map<String, dynamic>>(
        columns: const [
          GridColumn(key: 'number', label: 'Invoice Number'),
          GridColumn(key: 'date', label: 'Invoice Date'),
          GridColumn(key: 'reference', label: 'Reference'),
          GridColumn(key: 'status', label: 'Status'),
          GridColumn(key: 'total', label: 'Grand Total'),
        ],
        items: _invoices,
        id: (item) => '${item['id']}',
        selectedId: _selected == null ? null : '${_selected!['id']}',
        cells: (item) => [
          '${item['invoice_number'] ?? '-'}',
          '${item['invoice_date'] ?? '-'}',
          '${item['reference_number'] ?? ''}',
          '${item['status'] ?? ''}',
          '${item['grand_total'] ?? '0'}',
        ],
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

  Widget _card(String label, String value) => Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(label, style: Theme.of(context).textTheme.labelMedium),
              const SizedBox(height: 8),
              Text(value, style: Theme.of(context).textTheme.headlineSmall),
            ],
          ),
        ),
      );

  Map<String, dynamic> _unwrap(dynamic response) {
    if (response is! Map<String, dynamic>) return const <String, dynamic>{};
    final dynamic data = response['data'];
    return data is Map<String, dynamic> ? data : response;
  }
}
