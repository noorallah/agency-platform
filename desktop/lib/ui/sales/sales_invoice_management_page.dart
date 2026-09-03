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
import '../../models/entities.dart';
import '../workspace/desktop_framework.dart';
import '../workspace/reason_prompt.dart';
import 'sales_invoice_editor_dialog.dart';
import '../workspace/print_settings_dialog.dart';
import '../workspace/printed_document.dart';
import 'credit_notice.dart';
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

  /// Raise an invoice against a delivery note that still has something to bill.
  Future<void> _newInvoice() async {
    final bool? created = await showDialog<bool>(
      context: context,
      builder: (_) => SalesInvoiceEditorDialog(
        api: widget.api,
        today: DateTime.now(),
      ),
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
    final bool? saved = await showDialog<bool>(
      context: context,
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
      await printDocument(
        context,
        bytes: pdf,
        documentName: number,
      );
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
          // First in the row, because raising a bill is the reason somebody
          // opens this screen -- and until 2026-08-23 there was no way to do
          // it from the desktop at all.
          if (widget.permissions.hasPermission('SALES_CREATE'))
            Padding(
              padding: const EdgeInsets.only(left: 8),
              child: FilledButton.icon(
                onPressed:
                    widget.hasActiveFirm ? () => unawaited(_newInvoice()) : null,
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
                  const <String>{'DRAFT', 'CANCELLED'}
                      .contains('${_selected?['status'] ?? ''}')
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
      NotificationService.show(context, error.message,
          kind: AppNotificationKind.error);
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
      NotificationService.show(context, error.message,
          kind: AppNotificationKind.error);
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
