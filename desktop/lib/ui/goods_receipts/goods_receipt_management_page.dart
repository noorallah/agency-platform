import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/business/business_features.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/preferences/desktop_preferences_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/branch_warehouse.dart';
import '../../models/entities.dart';
import '../../models/document_framework.dart';
import '../../models/goods_receipt.dart';
import '../../models/product.dart';
import '../../models/purchase.dart';
import '../document_framework/document_framework_widgets.dart';
import '../workspace/desktop_framework.dart';
import '../document_framework/document_status_gate.dart';
import 'goods_receipt_editor_dialog.dart';
import 'goods_receipt_view_dialog.dart';

/// A named view over the one goods receipt list.
///
/// These were menu items: Pending, Partial and Completed Receipts, Rejected
/// and Damaged Items, and History -- six entries under a group called
/// "Reports" that all opened this same screen. Four of them filtered nothing
/// at all, and History was an exact duplicate of Completed. A receipt's status
/// is a view of the list, not a module.
enum GoodsReceiptView {
  all,
  draft,
  completed,
  cancelled,
  closed;

  /// The status this view filters on, or null for every status.
  String? get status => switch (this) {
        GoodsReceiptView.draft => 'DRAFT',
        GoodsReceiptView.completed => 'COMPLETED',
        GoodsReceiptView.cancelled => 'CANCELLED',
        GoodsReceiptView.closed => 'CLOSED',
        GoodsReceiptView.all => null,
      };

  String get label => switch (this) {
        GoodsReceiptView.all => 'All',
        // "Draft" rather than "Pending": it is the status the server stores,
        // and a receipt sits there until it is completed.
        GoodsReceiptView.draft => 'Draft',
        GoodsReceiptView.completed => 'Completed',
        GoodsReceiptView.cancelled => 'Cancelled',
        GoodsReceiptView.closed => 'Closed',
      };
}

class GoodsReceiptManagementPage extends StatefulWidget {
  const GoodsReceiptManagementPage({
    super.key,
    required this.api,
    required this.preferences,
    required this.permissions,
    required this.hasActiveFirm,
    required this.tabId,
    this.onNavigateToTab,
    this.onOpenGlobalSearch,
  });

  final ApiClient api;
  final DesktopPreferencesService preferences;
  final PermissionService permissions;
  final bool hasActiveFirm;
  final String tabId;
  final ValueChanged<String>? onNavigateToTab;
  final Future<void> Function()? onOpenGlobalSearch;

  @override
  State<GoodsReceiptManagementPage> createState() =>
      _GoodsReceiptManagementPageState();
}

class _GoodsReceiptManagementPageState extends State<GoodsReceiptManagementPage> {
  static const int _rowsPerPage = 20;
  final TextEditingController _search = TextEditingController();
  bool _loading = false;
  String? _error;
  int _page = 1;
  int _total = 0;
  Json _summary = const {};
  List<GoodsReceiptRecord> _receipts = const [];
  GoodsReceiptRecord? _selected;

  /// Which segment of the status bar is showing.
  GoodsReceiptView _view = GoodsReceiptView.all;
  List<DocumentTimelineSnapshot> _history = const [];
  // Reference data the receipt editor needs. Loaded once when the workspace
  // opens rather than each time the dialog does, so choosing an order is
  // immediate.
  List<PurchaseOrder> _receivableOrders = const [];
  List<WarehouseRecord> _warehouses = const [];
  List<Product> _products = const [];
  // Unknown until the call returns, and unknown means every field is offered:
  // taking fields away because a request failed is worse than the refusal on
  // save that this avoids.
  BusinessFeatures _features = const BusinessFeatures.unknown();

  bool get _canCreate => widget.permissions.hasPermission('PURCHASE_CREATE');

  @override
  void initState() {
    super.initState();
    unawaited(_load());
    unawaited(_loadReferenceData());
  }

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  Future<void> _load({int? requestedPage}) async {
    if (!widget.hasActiveFirm || !widget.permissions.hasPermission('PURCHASE_VIEW')) {
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
      final List<dynamic> results = await Future.wait<dynamic>([
        widget.api.goodsReceiptSummary(),
        widget.api.goodsReceipts(
          page: _page,
          pageSize: _rowsPerPage,
          search: _search.text.trim(),
          sortBy: 'receipt_date',
          descending: true,
          filters: _filtersForView(),
        ),
      ]);
      final Json summary = results[0] as Json;
      final PagedResult<GoodsReceiptRecord> receipts =
          results[1] as PagedResult<GoodsReceiptRecord>;
      GoodsReceiptRecord? selected = _selected;
      if (selected != null) {
        final List<GoodsReceiptRecord> matches =
            receipts.items.where((item) => item.id == selected!.id).toList();
        selected = matches.isEmpty ? null : matches.first;
      }
      if (selected == null && receipts.items.isNotEmpty) {
        selected = receipts.items.first;
      }
      List<DocumentTimelineSnapshot> history = const [];
      if (selected != null) {
        try {
          history = await widget.api.goodsReceiptHistory(selected.id);
        } on ApiException {
          history = const [];
        }
      }
      if (!mounted) return;
      setState(() {
        _summary = summary;
        _receipts = receipts.items;
        _total = receipts.total;
        _selected = selected;
        _history = history;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.toString();
        _receipts = const [];
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

  /// Load what the editor needs to seed a receipt: the orders that can still
  /// be received against, the bays goods can go to, and product names.
  ///
  /// Failure here is not fatal to the workspace -- the list of receipts is
  /// still readable -- so it leaves the create action disabled rather than
  /// taking the page down with it.
  Future<void> _loadReferenceData() async {
    if (!widget.hasActiveFirm || !_canCreate) return;
    try {
      final List<dynamic> results = await Future.wait<dynamic>([
        // Both states an order can still be received against. Asking only
        // for APPROVED was right while nothing ever moved an order off it;
        // now that a receipt advances the order, a partly delivered one is
        // PARTIALLY_RECEIVED, and filtering it out would make the **second**
        // receipt of a split delivery impossible to raise.
        //
        // Two requests because the list endpoint takes one status per call.
        widget.api.purchases(
          page: 1,
          pageSize: maxApiPageSize,
          sortBy: 'purchase_date',
          descending: true,
          filters: const PurchaseQuery(status: 'APPROVED'),
        ),
        widget.api.purchases(
          page: 1,
          pageSize: maxApiPageSize,
          sortBy: 'purchase_date',
          descending: true,
          filters: const PurchaseQuery(status: 'PARTIALLY_RECEIVED'),
        ),
        widget.api.warehouses(page: 1, pageSize: 100),
        widget.api.products(page: 1, pageSize: 100),
        widget.api.activeBusinessFeatureCodes(),
      ]);
      if (!mounted) return;
      setState(() {
        _receivableOrders = [
          ...(results[0] as PagedResult<PurchaseOrder>).items,
          ...(results[1] as PagedResult<PurchaseOrder>).items,
        ];
        _warehouses = (results[2] as PagedResult<WarehouseRecord>).items;
        _products = (results[3] as PagedResult<Product>).items;
        _features = BusinessFeatures((results[4] as List<String>).toSet());
      });
    } on ApiException {
      if (!mounted) return;
      setState(() {
        _receivableOrders = const [];
      });
    }
  }

  /// Open the receipt editor and reload if it saved one.
  Future<void> _createReceipt() async {
    final GoodsReceiptRecord? saved = await showDialog<GoodsReceiptRecord>(
      context: context,
      barrierDismissible: false,
      builder: (_) => GoodsReceiptEditorDialog(
        api: widget.api,
        purchaseOrders: _receivableOrders,
        warehouses: _warehouses,
        products: _products,
        features: _features,
      ),
    );
    if (saved == null || !mounted) return;
    await _load();
    if (!mounted) return;
    setState(() => _selected = saved);
    NotificationService.show(
      context,
      'Goods receipt ${saved.grnNumber} created as a draft. Complete it to '
      'post the stock.',
      kind: AppNotificationKind.success,
    );
  }

  /// Whether [action] is valid for the selected receipt's current status.
  /// Whether the selected receipt's status allows [action].
  ///
  /// Delegated to the shared gate so this screen, purchase invoices and
  /// purchase returns state the rule the same way. It used to list the
  /// statuses that *forbid* each action; the gate lists the ones that permit
  /// it, so a status added later is disabled until somebody decides it
  /// belongs.
  bool _isReceiptActionAllowed(DocumentToolbarAction action) {
    final DocumentLifecycleAction? lifecycle = switch (action) {
      // The toolbar's Complete button. `requestApproval` is the enum value it
      // arrived with; a goods receipt has no approval step.
      DocumentToolbarAction.requestApproval => DocumentLifecycleAction.complete,
      DocumentToolbarAction.cancel => DocumentLifecycleAction.cancel,
      DocumentToolbarAction.close => DocumentLifecycleAction.close,
      _ => null,
    };
    if (lifecycle == null) return false;
    return DocumentStatusGate.goodsReceipt.allows(lifecycle, _selected?.status);
  }

  /// Run a lifecycle action against the selected receipt and reload.
  Future<void> _runReceiptAction(DocumentToolbarAction action) async {
    final GoodsReceiptRecord? selected = _selected;
    if (selected == null || !_isReceiptActionAllowed(action)) return;
    try {
      switch (action) {
        case DocumentToolbarAction.requestApproval:
          await widget.api.completeGoodsReceipt(selected.id);
        case DocumentToolbarAction.cancel:
          await widget.api.cancelGoodsReceipt(selected.id);
        case DocumentToolbarAction.close:
          await widget.api.closeGoodsReceipt(selected.id);
        default:
          return;
      }
      await _load();
      if (!mounted) return;
      NotificationService.show(
        context,
        'Goods receipt ${selected.grnNumber} updated.',
        kind: AppNotificationKind.success,
      );
    } on ApiException catch (error) {
      if (!mounted) return;
      NotificationService.show(
        context,
        error.message,
        kind: AppNotificationKind.error,
      );
    }
  }

  /// Switch the list to another view of itself.
  void _selectView(GoodsReceiptView view) {
    if (view == _view) return;
    setState(() {
      _view = view;
      _page = 1;
      _selected = null;
      _history = const [];
    });
    unawaited(_load(requestedPage: 1));
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.hasActiveFirm) {
      return const StandardEmptyState(type: EmptyStateType.noFirmSelected);
    }
    if (!widget.permissions.hasPermission('PURCHASE_VIEW')) {
      return const StandardEmptyState(type: EmptyStateType.noPermissions);
    }
    if (_error != null && !_loading) {
      return WorkspaceEmptyState(
        title: 'Goods receipts unavailable',
        message: _error!,
      );
    }
    return ModuleWorkspaceFrame(
      title: 'Goods Receipts',
      description:
          'Receive against approved purchase orders. Completing a receipt is '
          'what posts the stock.',
      breadcrumbs: const ['Workspace', 'Purchases', 'Goods Receipts'],
      child: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(24, 0, 24, 12),
            child: SummaryCards(
              children: [
                _summaryCard('Total', '${_summary['total'] ?? 0}'),
                _summaryCard('Draft', '${_summary['draft'] ?? 0}'),
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

  Widget _buildGridWorkspace() => ManagementWorkspaceLayout(
        toolbar: _buildToolbar(),
        searchPanel: SearchFilterPanel(
          controller: _search,
          hintText: 'Search GRN number, purchase order...',
          onSearch: (_) => _load(requestedPage: 1),
        ),
        viewBar: _buildViewBar(),
        primaryContent: _loading
            ? const Center(child: CircularProgressIndicator())
            : _receipts.isEmpty
                ? StandardEmptyState(
                    type: _search.text.trim().isEmpty
                        ? EmptyStateType.noRecords
                        : EmptyStateType.noSearchResults,
                  )
                : _buildReceiptGrid(),
        // No side pane. It took 57% of the width -- more than the list it sat
        // beside -- to show a document the user had only pointed at.
        // Double-click opens it instead.
        detailsPanel: null,
        statusBar: WorkspaceStatusBar(
          total: _total,
          selected: _selected != null,
          message: _loading ? 'Loading...' : null,
        ),
      );

  /// The status bar: All / Draft / Completed / Cancelled / Closed.
  Widget _buildViewBar() => SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: SegmentedButton<GoodsReceiptView>(
          segments: [
            for (final GoodsReceiptView view in GoodsReceiptView.values)
              ButtonSegment<GoodsReceiptView>(
                value: view,
                label: Text(view.label),
              ),
          ],
          selected: <GoodsReceiptView>{_view},
          onSelectionChanged:
              _loading ? null : (selection) => _selectView(selection.first),
          showSelectedIcon: false,
        ),
      );

  Widget _buildToolbar() => WorkspaceToolbar(
        actions: const [
          ToolbarAction.newItem,
          ToolbarAction.view,
          ToolbarAction.refresh,
        ],
        isVisible: (action) =>
            action != ToolbarAction.newItem || _canCreate,
        isEnabled: (action) =>
            !_loading &&
            switch (action) {
              // Nothing to receive against means nothing to raise: a goods
              // receipt line requires a purchase order line, so an empty order
              // list is a disabled button and not an empty dialog.
              ToolbarAction.newItem =>
                _canCreate && _receivableOrders.isNotEmpty,
              ToolbarAction.view => _selected != null,
              ToolbarAction.refresh => true,
              _ => false,
            },
        onAction: (action) {
          switch (action) {
            case ToolbarAction.newItem:
              unawaited(_createReceipt());
            case ToolbarAction.view:
              final GoodsReceiptRecord? selected = _selected;
              if (selected != null) unawaited(_openReceipt(selected));
            case ToolbarAction.refresh:
              unawaited(_load());
            default:
              break;
          }
        },
        trailing: [
          // The action that posts stock. It was labelled "Request approval" --
          // there is no approval step on a receipt, and calling the thing that
          // moves inventory something else is how somebody completes one
          // without meaning to.
          _actionButton(
            'Complete',
            Icons.check_circle_outline,
            DocumentToolbarAction.requestApproval,
          ),
          _actionButton(
            'Cancel',
            Icons.cancel_outlined,
            DocumentToolbarAction.cancel,
          ),
          _actionButton(
            'Close',
            Icons.lock_outline,
            DocumentToolbarAction.close,
          ),
        ],
      );

  Widget _actionButton(
    String label,
    IconData icon,
    DocumentToolbarAction action,
  ) =>
      Padding(
        padding: const EdgeInsets.only(left: 8),
        child: OutlinedButton.icon(
          onPressed: _isReceiptActionAllowed(action)
              ? () => _runReceiptAction(action)
              : null,
          icon: Icon(icon, size: 18),
          label: Text(label),
        ),
      );

  Widget _buildReceiptGrid() => EnterpriseDataGrid<GoodsReceiptRecord>(
        columns: const [
          GridColumn(key: 'grn', label: 'GRN Number'),
          GridColumn(key: 'po', label: 'Purchase Order'),
          GridColumn(key: 'date', label: 'Receipt Date'),
          GridColumn(key: 'status', label: 'Status'),
          GridColumn(key: 'total', label: 'Grand Total'),
        ],
        items: _receipts,
        id: (item) => item.id,
        selectedId: _selected?.id,
        cells: (item) => [
          item.grnNumber,
          item.purchaseOrderNumber,
          item.receiptDate,
          item.status,
          item.grandTotal,
        ],
        onSelect: _selectReceipt,
        onOpen: _openReceipt,
        total: _total,
        pageOffset: (_page - 1) * _rowsPerPage,
        rowsPerPage: _rowsPerPage,
        onPageChanged: (offset) {
          final int next = offset ~/ _rowsPerPage + 1;
          if (next != _page) _load(requestedPage: next);
        },
      );

  void _selectReceipt(GoodsReceiptRecord record) {
    setState(() => _selected = record);
    unawaited(_loadHistory(record));
  }

  Future<void> _loadHistory(GoodsReceiptRecord record) async {
    try {
      final List<DocumentTimelineSnapshot> history =
          await widget.api.goodsReceiptHistory(record.id);
      if (!mounted) return;
      setState(() => _history = history);
    } on ApiException {
      if (!mounted) return;
      setState(() => _history = const []);
    }
  }

  /// Show one receipt: its header, its lines and its timeline.
  ///
  /// This is what the pinned side pane held. It is a dialog now, so the table
  /// keeps the whole width and the document gets room to be read.
  Future<void> _openReceipt(GoodsReceiptRecord record) async {
    setState(() => _selected = record);
    await _loadHistory(record);
    if (!mounted) return;
    await showDialog<void>(
      context: context,
      builder: (_) => GoodsReceiptViewDialog(
        receipt: record,
        history: _history,
      ),
    );
  }

  Widget _summaryCard(String label, String value) => Card(
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

  Map<String, String> _filtersForView() {
    final String? status = _view.status;
    return status == null ? const {} : {'status': status};
  }
}
