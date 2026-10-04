import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../models/tax_framework.dart';
import '../../models/uom_packaging.dart';
import '../document_framework/document_line_labels.dart';
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
import '../../models/supplier_gift.dart';
import '../document_framework/document_framework_widgets.dart';
import '../trade_licences/licence_check_dialog.dart';
import '../vendors/supplier_gifts_page.dart';
import '../workspace/desktop_framework.dart';
import '../workspace/label_print_dialog.dart';
import '../document_framework/document_status_gate.dart';
import 'goods_receipt_editor_dialog.dart';
import 'goods_receipt_eway_dialog.dart';
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

  /// The view a retired sidebar entry stood for.
  ///
  /// The eight entries became one on 2026-08-16, but nothing carried the
  /// user's choice across: a stored workspace naming `pending-receipts`
  /// resolved to the Receipts tab and then opened it on All. Only three of the
  /// eight named a status the server keeps; the rest -- Partial, Rejected
  /// Items, Damaged Items -- filtered nothing even when they were tabs.
  static GoodsReceiptView fromTabId(String? tabId) => switch (tabId) {
        'pending-receipts' => GoodsReceiptView.draft,
        // History was an exact duplicate of Completed.
        'completed-receipts' || 'grn-history' => GoodsReceiptView.completed,
        _ => GoodsReceiptView.all,
      };
}

class GoodsReceiptManagementPage extends StatefulWidget {
  const GoodsReceiptManagementPage({
    super.key,
    required this.api,
    required this.preferences,
    required this.permissions,
    required this.hasActiveFirm,
    this.initialView = GoodsReceiptView.all,
    this.onOpenGlobalSearch,
  });

  final ApiClient api;
  final DesktopPreferencesService preferences;
  final PermissionService permissions;
  final bool hasActiveFirm;
  final GoodsReceiptView initialView;
  final Future<void> Function()? onOpenGlobalSearch;

  @override
  State<GoodsReceiptManagementPage> createState() =>
      _GoodsReceiptManagementPageState();
}

class _GoodsReceiptManagementPageState
    extends State<GoodsReceiptManagementPage> {
  static const int _rowsPerPage = 20;
  final TextEditingController _search = TextEditingController();

  /// The document dates the list is narrowed to (owner, 2026-09-27).
  DatePeriod _period = const DatePeriod.all();
  bool _loading = false;
  String? _error;
  int _page = 1;
  int _total = 0;
  Json _summary = const {};
  List<GoodsReceiptRecord> _receipts = const [];
  GoodsReceiptRecord? _selected;

  /// Which segment of the status bar is showing.
  late GoodsReceiptView _view = widget.initialView;
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

  /// Raising, editing and completing a receipt take `PURCHASE_RECEIVE`
  /// (D-ROLE-3): the job of whoever counts the goods in -- Purchasing and
  /// Warehouse -- not of whoever orders or approves.
  bool get _canCreate => widget.permissions.hasPermission('PURCHASE_RECEIVE');

  /// The receipts are read by the purchase module's readers and by whoever
  /// receives: Warehouse holds `PURCHASE_RECEIVE` and not `PURCHASE_VIEW`.
  bool get _canView => widget.permissions
      .hasAnyPermission(const ['PURCHASE_VIEW', 'PURCHASE_RECEIVE']);

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

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  Future<void> _load({int? requestedPage}) async {
    // Read before any await: whether to pick the first row (phase 1 only).
    // Phase 2 (option C, owner 2026-09-27): nothing is picked for the user --
    // the selection bar opens when somebody clicks a row, and stays with it.
    final bool pickFirst =
        context.getInheritedWidgetOfExactType<Phase2Scope>() == null;
    if (!widget.hasActiveFirm ||
        !_canView) {
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
      if (selected == null && pickFirst && receipts.items.isNotEmpty) {
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
  Future<void> _createReceipt({GoodsReceiptRecord? existing}) async {
    final GoodsReceiptRecord? saved = await showDocument<GoodsReceiptRecord>(
      context,
      title: existing == null ? 'New goods receipt' : 'Edit goods receipt',
      builder: (_) => GoodsReceiptEditorDialog(
        api: widget.api,
        purchaseOrders: _receivableOrders,
        warehouses: _warehouses,
        products: _products,
        existing: existing,
        features: _features,
      ),
    );
    if (saved == null || !mounted) return;
    await _load();
    if (!mounted) return;
    setState(() => _selected = saved);
    final String ewayWarning = saved.ewayBillWarning;
    NotificationService.show(
      context,
      'Goods receipt ${saved.grnNumber} created as a draft. Complete it to '
      'post the stock.${ewayWarning.isEmpty ? '' : ' $ewayWarning'}',
      kind: ewayWarning.isEmpty
          ? AppNotificationKind.success
          : AppNotificationKind.warning,
    );
  }

  /// Record the supplier's e-way bill on the selected receipt. A completed
  /// receipt's editor is closed, so this is how the number gets onto it
  /// (backlog 78 row 6); any receipt that is not cancelled takes it.
  ToolbarCommand _recordEwayBillCommand() => ToolbarCommand(
        id: 'record-eway-bill',
        label: 'Record e-way bill',
        icon: Icons.local_shipping_outlined,
        onPressed: _selected == null ||
                _selected!.status == 'CANCELLED' ||
                !_canCreate
            ? null
            : () => unawaited(_recordEwayBill()),
      );

  /// A supplier's gift that came with this delivery (BUY-2): the same dialog
  /// as the Supplier Gifts screen, with the supplier and receipt filled in.
  ToolbarCommand _recordGiftCommand() => ToolbarCommand(
        id: 'record-gift',
        label: 'Record gift from this delivery',
        icon: Icons.card_giftcard_outlined,
        onPressed: _selected == null ||
                _selected!.status == 'CANCELLED' ||
                !widget.permissions.hasPermission('SUPPLIER_GIFT_MANAGE')
            ? null
            : () => unawaited(_recordGift()),
      );

  Future<void> _recordGift() async {
    final GoodsReceiptRecord? selected = _selected;
    if (selected == null) return;
    final SupplierGift? saved = await showDialog<SupplierGift>(
      context: context,
      barrierDismissible: false,
      builder: (_) => RecordSupplierGiftDialog(
        api: widget.api,
        vendorId: selected.vendorId,
        vendorName: selected.vendorName,
        goodsReceiptId: selected.id,
      ),
    );
    if (saved == null || !mounted) return;
    NotificationService.show(
      context,
      'Gift ${saved.giftNumber} recorded against ${selected.grnNumber}.',
      kind: AppNotificationKind.success,
    );
  }

  Future<void> _recordEwayBill() async {
    final GoodsReceiptRecord? selected = _selected;
    if (selected == null) return;
    final Object? saved = await askForEwayBill(
      context,
      receiptNumber: selected.grnNumber,
      currentNumber: selected.ewayBillNumber,
      currentDate: selected.ewayBillDate,
      save: (number, date) =>
          widget.api.setGoodsReceiptEwayBill(selected.id, number, date),
    );
    if (saved is! GoodsReceiptRecord || !mounted) return;
    await _load();
    if (!mounted) return;
    NotificationService.show(
      context,
      saved.ewayBillWarning.isNotEmpty
          ? saved.ewayBillWarning
          : saved.ewayBillNumber.isEmpty
              ? 'E-way bill cleared on ${selected.grnNumber}.'
              : 'E-way bill recorded on ${selected.grnNumber}.',
      kind: saved.ewayBillWarning.isNotEmpty
          ? AppNotificationKind.warning
          : AppNotificationKind.success,
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
    // The button follows the code the server enforces (D-ROLE-3): it used to
    // be offered to everybody and refused after the press.
    final String code = switch (lifecycle) {
      DocumentLifecycleAction.complete => 'PURCHASE_RECEIVE',
      DocumentLifecycleAction.cancel => 'PURCHASE_CANCEL',
      _ => 'PURCHASE_APPROVE',
    };
    if (!widget.permissions.hasPermission(code)) return false;
    return DocumentStatusGate.goodsReceipt.allows(lifecycle, _selected?.status);
  }

  /// Run a lifecycle action against the selected receipt and reload.
  ///
  /// Completing checks the licences it needs first (backlog 54), before the
  /// call: a purchase only ever warns, so there is no override, just
  /// "Approve anyway".
  Future<void> _runReceiptAction(DocumentToolbarAction action) async {
    final GoodsReceiptRecord? selected = _selected;
    if (selected == null || !_isReceiptActionAllowed(action)) return;
    if (action == DocumentToolbarAction.requestApproval) {
      final LicenceCheckOutcome licence = await confirmLicenceCheck(
        context,
        widget.api,
        widget.permissions,
        document: 'GOODS_RECEIPT',
        documentId: selected.id,
      );
      if (!licence.proceed || !mounted) return;
    }
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
  /// Phase 2 (UI_PHASE_2_DESIGN.md 4.5): one counter per view with its
  /// count, and clicking one is choosing that view -- click it again for
  /// all. The summary endpoint counts every status the views filter on.
  List<Widget> _viewCounters() => [
        for (final GoodsReceiptView view in GoodsReceiptView.values)
          SummaryCount(
            key: ValueKey('view-counter-${view.name}'),
            label: view.label,
            value: '${_summary[view.status?.toLowerCase() ?? 'total'] ?? 0}',
            selected: _view == view,
            onTap: _loading
                ? null
                : () => _selectView(
                      _view == view ? GoodsReceiptView.all : view,
                    ),
          ),
      ];

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
    if (!_canView) {
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
            // Phase 2 draws the figures on the page's one line, so the gap
            // their row of cards needed goes with it.
            padding: Phase2Scope.of(context)
                ? EdgeInsets.zero
                : const EdgeInsets.fromLTRB(24, 0, 24, 12),
            child: SummaryCards(
              children: Phase2Scope.of(context)
                  ? _viewCounters()
                  : [
                      _summaryCard('Total', '${_summary['total'] ?? 0}'),
                      _summaryCard('Draft', '${_summary['draft'] ?? 0}'),
                      _summaryCard(
                          'Completed', '${_summary['completed'] ?? 0}'),
                      _summaryCard(
                          'Cancelled', '${_summary['cancelled'] ?? 0}'),
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
          hintText: 'Search GRN number, purchase order or supplier',
          onSearch: (_) => _load(requestedPage: 1),
        ),
        // Option C (owner, 2026-09-27): the receipt's actions on a bar that
        // names it and its supplier, above the grid.
        selectionBar: true,
        selection: _selected == null
            ? null
            : SelectionSummary.document(
                number: _selected!.grnNumber,
                party: _selected!.vendorName,
                status: _selected!.status,
                total: _selected!.grandTotal,
                onClear: () => setState(() => _selected = null),
              ),
        // Phase 2's counters are the views (4.5); a second row
        // of the same choices would repeat them.
        viewBar: Phase2Scope.of(context) ? null : _buildViewBar(),
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
          ToolbarAction.edit,
          ToolbarAction.refresh,
        ],
        isVisible: (action) => switch (action) {
          ToolbarAction.newItem || ToolbarAction.edit => _canCreate,
          _ => true,
        },
        isEnabled: (action) =>
            !_loading &&
            switch (action) {
              // Nothing to receive against means nothing to raise: a goods
              // receipt line requires a purchase order line, so an empty order
              // list is a disabled button and not an empty dialog.
              ToolbarAction.newItem =>
                _canCreate && _receivableOrders.isNotEmpty,
              ToolbarAction.view => _selected != null,
              // Only a draft: once a receipt is completed its lines are what
              // stock was posted at, and the service refuses the edit.
              ToolbarAction.edit =>
                _canCreate && _selected != null && _selected!.status == 'DRAFT',
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
            case ToolbarAction.edit:
              final GoodsReceiptRecord? draft = _selected;
              if (draft != null) unawaited(_createReceipt(existing: draft));
            case ToolbarAction.refresh:
              unawaited(_load());
            default:
              break;
          }
        },
        // Phase 2 (4.11): the same steps as commands, folded into "..."
        // when the line is short.
        commands: Phase2Scope.of(context)
            ? [
                // The action that posts stock. It was labelled "Request approval" --
                // there is no approval step on a receipt, and calling the thing that
                // moves inventory something else is how somebody completes one
                // without meaning to.
                _command(
                  'Complete',
                  Icons.check_circle_outline,
                  DocumentToolbarAction.requestApproval,
                ),
                _command(
                  'Cancel',
                  Icons.cancel_outlined,
                  DocumentToolbarAction.cancel,
                ),
                _command(
                  'Close',
                  Icons.lock_outline,
                  DocumentToolbarAction.close,
                ),
                _recordEwayBillCommand(),
                _recordGiftCommand(),
                // One label per piece received (STK-16); nothing to label on
                // a cancelled receipt.
                ToolbarCommand(
                  id: 'labels',
                  label: 'Print labels',
                  icon: Icons.label_outline,
                  onPressed: _selected == null || _selected!.status == 'CANCELLED'
                      ? null
                      : _printLabels,
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

  Future<void> _printLabels() async {
    final GoodsReceiptRecord? receipt = _selected;
    if (receipt == null) return;
    await showDialog<Object>(
      context: context,
      builder: (context) => LabelPrintDialog(
        api: widget.api,
        subtitle: receipt.grnNumber,
        receiptId: receipt.id,
      ),
    );
  }

  /// The same step as a phase 2 command, enabled as its button is.
  ToolbarCommand _command(
    String label,
    IconData icon,
    DocumentToolbarAction action,
  ) =>
      ToolbarCommand(
        id: label.toLowerCase(),
        label: label,
        icon: icon,
        onPressed: _isReceiptActionAllowed(action)
            ? () => _runReceiptAction(action)
            : null,
      );

  /// Every column the grid can show; Columns picks among them, remembered
  /// per screen on this PC (owner, 2026-09-27).
  late final ColumnChoice<GoodsReceiptRecord> _columns = ColumnChoice(
    preferences: widget.preferences,
    stateKey: 'goods-receipts.grid',
    columns: [
      ChoosableColumn(
        column: const GridColumn(key: 'grn', label: 'GRN Number'),
        cell: (item) => item.grnNumber,
        required: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'vendor', label: 'Supplier', priority: 1),
        cell: (item) => item.vendorName,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'po', label: 'Purchase Order'),
        cell: (item) => item.purchaseOrderNumber,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'date', label: 'Receipt Date'),
        cell: (item) => documentDateStamp(item.receiptDate, item.createdAt),
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'invoice', label: 'Supplier Invoice'),
        cell: (item) => item.invoiceReference,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'vehicle', label: 'Vehicle'),
        cell: (item) => item.vehicleNumber,
      ),
      ChoosableColumn(
        column: const GridColumn(
            key: 'accepted', label: 'Quantity Accepted', numeric: true),
        cell: (item) => item.totalAcceptedQuantity,
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

  Widget _buildReceiptGrid() => EnterpriseDataGrid<GoodsReceiptRecord>(
        columns: _columns.gridColumns,
        items: _receipts,
        id: (item) => item.id,
        selectedId: _selected?.id,
        cells: _columns.cells,
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
        labels: _labels,
      ),
    );
  }

  Widget _summaryCard(String label, String value) =>
      SummaryCount(label: label, value: value);

  Map<String, String> _filtersForView() {
    final String? status = _view.status;
    return {
      if (status != null) 'status': status,
      // The server's created_from/to bound the receipt date.
      if (_period.from != null) 'created_from': DatePeriod.iso(_period.from!),
      if (_period.to != null) 'created_to': DatePeriod.iso(_period.to!),
    };
  }
}
