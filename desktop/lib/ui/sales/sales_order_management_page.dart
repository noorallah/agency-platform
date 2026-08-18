import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/preferences/desktop_preferences_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/document_framework.dart';
import '../document_framework/document_framework_widgets.dart';
import '../document_framework/document_status_gate.dart';
import '../document_framework/document_view_dialog.dart';
import '../workspace/desktop_framework.dart';
import 'credit_notice.dart';

class SalesOrderManagementPage extends StatefulWidget {
  const SalesOrderManagementPage({
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
  State<SalesOrderManagementPage> createState() => _SalesOrderManagementPageState();
}

class _SalesOrderManagementPageState extends State<SalesOrderManagementPage> {
  final TextEditingController _search = TextEditingController();
  bool _loading = false;
  static const int _rowsPerPage = 50;
  int _page = 1;
  int _total = 0;
  String? _error;
  List<Map<String, dynamic>> _orders = const [];
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
    return DocumentStatusGate.salesOrder.allows(lifecycle, status);
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
        widget.api.documentSummary('sales-orders'),
        widget.api.documentPage(
          'sales-orders',
          page: _page,
          pageSize: _rowsPerPage,
          search: _search.text.trim(),
          sortBy: 'order_date',
          descending: true,
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
      // The timeline is no longer fetched here. It filled a pane that was on
      // screen whether or not anybody wanted it; the dialog reads it when the
      // document is actually opened.
      if (!mounted) return;
      setState(() {
        _summary = summary;
        _orders = rows;
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
    await widget.api.documentAction('sales-orders', selected['id'] as String, suffix);
    await _load();
  }

  /// Warn before approving, because approval is where credit is committed.
  ///
  /// The check has to run *before* the call: once the order is approved the
  /// exposure already includes it, and asking afterwards with the same amount
  /// would count the order twice.
  Future<void> _warnOnCredit(Map<String, dynamic> order) => warnOnCreditExposure(
        context,
        widget.api,
        customerId: order['customer_id'] as String?,
        amount: '${order['grand_total'] ?? '0'}',
      );

  DocumentHeaderSnapshot _headerFor(Map<String, dynamic> row) =>
      DocumentHeaderSnapshot(
        documentTypeCode: 'SALES_ORDER',
        documentTypeName: 'Sales Order',
        documentNumber: '${row['order_number'] ?? '-'}',
        documentDate: '${row['order_date'] ?? '-'}',
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
          uom: '${item['sales_uom_id'] ?? ''}',
          packaging: '${item['packaging_type_id'] ?? ''}',
          quantity: '${item['quantity'] ?? '0'}',
          freeQuantity: '${item['free_quantity'] ?? '0'}',
          unitPrice: '${item['unit_price'] ?? '0'}',
          discount: '${item['discount_amount'] ?? '0'}',
          taxProfile: '${item['tax_profile_id'] ?? ''}',
          amount: '${item['gross_amount'] ?? '0'}',
          netAmount: '${item['net_amount'] ?? '0'}',
          remarks: 'Avail: ${item['available_stock'] ?? '0'} | '
              'Res: ${item['reserved_stock'] ?? '0'} ${item['remarks'] ?? ''}',
        );
      }).toList(growable: false);

  /// Select a row.
  ///
  /// This used to call `_load()`, which refetched the whole list, the summary
  /// **and** the selected order's timeline -- three requests to fill a preview
  /// pane, on every click. With the pane gone the timeline is read only when
  /// the document is opened.
  void _selectOrder(Map<String, dynamic> row) {
    setState(() => _selected = row);
  }

  /// Show one order: header, lines, totals and timeline.
  Future<void> _openOrder(Map<String, dynamic> row) async {
    setState(() => _selected = row);
    List<DocumentTimelineSnapshot> history = const [];
    try {
      final Map<String, dynamic> timeline = _unwrap(
        await widget.api.documentHistory('sales-orders', row['id']),
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
        title: '${row['order_number'] ?? '-'}',
        subtitle: 'Sales order dated ${row['order_date'] ?? '-'}',
        icon: Icons.point_of_sale_outlined,
        header: _headerFor(row),
        lines: _linesFor(row),
        totals: _totalsFor(row),
        history: history,
      ),
    );
  }

  @override
  Widget build(BuildContext context) => EnterpriseWorkspace(
        title: 'Sales Orders',
        description: 'Manage customer sales orders and inventory reservations.',
        breadcrumbs: const ['Workspace', 'Sales Orders'],
        content: Column(
          children: [
            if (_loading) const LinearProgressIndicator(minHeight: 2),
            Padding(
              padding: const EdgeInsets.fromLTRB(24, 0, 24, 12),
              child: SummaryCards(children: [
                _card('Total', '${_summary['total'] ?? 0}'),
                _card('Draft', '${_summary['draft'] ?? 0}'),
                _card('Approved', '${_summary['approved'] ?? 0}'),
                _card('Cancelled', '${_summary['cancelled'] ?? 0}'),
                _card('Closed', '${_summary['closed'] ?? 0}'),
              ]),
            ),
            // Bounded, so the layout below has a height to divide.
            Expanded(child: _buildGridWorkspace()),
          ],
        ),
      );

  Widget _buildGridWorkspace() => ManagementWorkspaceLayout(
        toolbar: _buildToolbar(),
        searchPanel: SearchFilterPanel(
          controller: _search,
          hintText: 'Search order number, customer reference...',
          onSearch: (_) => _load(requestedPage: 1),
        ),
        primaryContent: !widget.hasActiveFirm
            ? const StandardEmptyState(type: EmptyStateType.noFirmSelected)
            : _error != null && !_loading
                ? WorkspaceEmptyState(
                    title: 'Sales orders unavailable',
                    message: _error!,
                  )
                : _orders.isEmpty && !_loading
                    ? StandardEmptyState(
                        type: _search.text.trim().isEmpty
                            ? EmptyStateType.noRecords
                            : EmptyStateType.noSearchResults,
                      )
                    : _buildOrderGrid(),
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
              if (selected != null) unawaited(_openOrder(selected));
            case ToolbarAction.refresh:
              unawaited(_load());
            default:
              break;
          }
        },
        // Only the three the backend has. The pane offered seven, and four --
        // new, print, export and email -- fell through to a notification
        // saying the action was a placeholder.
        trailing: [
          _actionButton(DocumentToolbarAction.approve, '/approve'),
          _actionButton(DocumentToolbarAction.cancel, '/cancel'),
          _actionButton(DocumentToolbarAction.close, '/close'),
        ],
      );

  /// A lifecycle button, disabled unless permission **and** the selected
  /// order's status allow it.
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

  /// Run a lifecycle action, warning first where the firm's credit policy
  /// says to.
  ///
  /// The warning has to come **before** the approval, or the document is
  /// counted twice in the exposure it is being checked against. It is a
  /// warning and never a block: the server refuses when the firm's policy is
  /// set to Block, and a client that blocked on its own would enforce a rule
  /// the firm may not have chosen.
  Future<void> _run(DocumentToolbarAction action, String suffix) async {
    final Map<String, dynamic>? selected = _selected;
    if (selected == null) return;
    if (action == DocumentToolbarAction.approve) {
      await _warnOnCredit(selected);
    }
    await _act(suffix);
  }

  Widget _buildOrderGrid() => EnterpriseDataGrid<Map<String, dynamic>>(
        columns: const [
          GridColumn(key: 'number', label: 'Order Number'),
          GridColumn(key: 'date', label: 'Order Date'),
          GridColumn(key: 'reference', label: 'Reference'),
          GridColumn(key: 'status', label: 'Status'),
          GridColumn(key: 'total', label: 'Grand Total'),
        ],
        items: _orders,
        id: (item) => '${item['id']}',
        selectedId: _selected == null ? null : '${_selected!['id']}',
        cells: (item) => [
          '${item['order_number'] ?? '-'}',
          '${item['order_date'] ?? '-'}',
          '${item['reference_number'] ?? ''}',
          '${item['status'] ?? ''}',
          '${item['grand_total'] ?? '0'}',
        ],
        onSelect: _selectOrder,
        onOpen: (item) => unawaited(_openOrder(item)),
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
