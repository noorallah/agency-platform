import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/business/business_features.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/preferences/desktop_preferences_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/branch_warehouse.dart';
import '../../models/document_framework.dart';
import '../../models/entities.dart';
import '../../models/product.dart';
import '../document_framework/document_framework_widgets.dart';
import '../document_framework/document_status_gate.dart';
import '../document_framework/document_view_dialog.dart';
import '../workspace/desktop_framework.dart';
import '../workspace/printed_document.dart';
import '../workspace/print_settings_dialog.dart';
import 'delivery_note_editor_dialog.dart';

/// A named view over the one delivery note list.
///
/// These were six sidebar entries -- Pending and Partial Deliveries, Delivered
/// by Route, by Salesman and by Warehouse, and History. The three "delivered
/// by" entries opened this list with no filter whatsoever, so they were three
/// menu items that did nothing; the reports they are named after are real, and
/// live under Reports where they work.
enum DeliveryNoteView {
  all,
  draft,
  approved,
  dispatched,
  completed,
  cancelled;

  /// The status this view filters on, or null for every status.
  String? get status => switch (this) {
        DeliveryNoteView.draft => 'DRAFT',
        DeliveryNoteView.approved => 'APPROVED',
        DeliveryNoteView.dispatched => 'DISPATCHED',
        DeliveryNoteView.completed => 'COMPLETED',
        DeliveryNoteView.cancelled => 'CANCELLED',
        DeliveryNoteView.all => null,
      };

  /// The query the list is asked for.
  Map<String, String> get query =>
      status == null ? const {} : {'status': status!};

  String get label => switch (this) {
        DeliveryNoteView.all => 'All',
        DeliveryNoteView.draft => 'Draft',
        DeliveryNoteView.approved => 'Approved',
        DeliveryNoteView.dispatched => 'Dispatched',
        DeliveryNoteView.completed => 'Completed',
        DeliveryNoteView.cancelled => 'Cancelled',
      };

  /// The view a retired sidebar entry stood for.
  ///
  /// A stored workspace still names one of them -- the last tab is persisted
  /// -- so landing on the list is not enough: the user asked for Pending
  /// Deliveries and should get the approved-but-undispatched ones.
  static DeliveryNoteView fromTabId(String? tabId) => switch (tabId) {
        'pending-deliveries' => DeliveryNoteView.approved,
        'partial-deliveries' => DeliveryNoteView.dispatched,
        'delivery-history' => DeliveryNoteView.completed,
        _ => DeliveryNoteView.all,
      };
}

class DeliveryNoteManagementPage extends StatefulWidget {
  const DeliveryNoteManagementPage({
    super.key,
    required this.api,
    required this.preferences,
    required this.permissions,
    required this.hasActiveFirm,
    this.initialView = DeliveryNoteView.all,
    this.onOpenGlobalSearch,
  });

  final ApiClient api;
  final DesktopPreferencesService preferences;
  final PermissionService permissions;
  final bool hasActiveFirm;
  final DeliveryNoteView initialView;
  final Future<void> Function()? onOpenGlobalSearch;

  @override
  State<DeliveryNoteManagementPage> createState() => _DeliveryNoteManagementPageState();
}

class _DeliveryNoteManagementPageState extends State<DeliveryNoteManagementPage> {
  static const int _rowsPerPage = 20;
  final TextEditingController _search = TextEditingController();
  late DeliveryNoteView _view = widget.initialView;
  bool _loading = false;
  String? _error;
  int _page = 1;
  int _total = 0;
  Json _summary = const {};
  List<_DeliveryNoteRecord> _notes = const [];
  _DeliveryNoteRecord? _selected;
  // Reference data the editor needs, loaded once with the workspace.
  List<Json> _deliverableOrders = const [];
  List<WarehouseRecord> _warehouses = const [];
  List<Product> _products = const [];
  // Unknown until the call returns, and unknown means every field is offered.
  BusinessFeatures _features = const BusinessFeatures.unknown();

  bool get _canCreate => widget.permissions.hasPermission('SALES_CREATE');

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

  /// Load what the editor needs: the orders that can still be delivered
  /// against, the bays goods leave from, and product names.
  ///
  /// Failing here leaves the create action disabled rather than taking the
  /// workspace down; the list of notes is still readable without it.
  Future<void> _loadReferenceData() async {
    if (!widget.hasActiveFirm || !_canCreate) return;
    try {
      final List<dynamic> results = await Future.wait<dynamic>([
        widget.api.documentPage(
          'sales-orders',
          page: 1,
          pageSize: 100,
          sortBy: 'order_date',
          descending: true,
          additionalQuery: const {'status': 'APPROVED'},
        ),
        widget.api.warehouses(page: 1, pageSize: 100),
        widget.api.products(page: 1, pageSize: 100),
        widget.api.activeBusinessFeatureCodes(),
      ]);
      // A paginated body carries a list under `data`, so `_unwrap` returns the
      // envelope rather than the payload here.
      final dynamic data = (results[0] as Json)['data'];
      if (!mounted) return;
      setState(() {
        _deliverableOrders = [
          for (final dynamic order in data is List ? data : const [])
            if (order is Map) Map<String, dynamic>.from(order),
        ];
        _warehouses = (results[1] as PagedResult<WarehouseRecord>).items;
        _products = (results[2] as PagedResult<Product>).items;
        _features = BusinessFeatures((results[3] as List<String>).toSet());
      });
    } on ApiException {
      if (!mounted) return;
      setState(() => _deliverableOrders = const []);
    }
  }

  /// Open the editor and reload if it saved a note.
  Future<void> _createNote() async {
    final Json? saved = await showDialog<Json>(
      context: context,
      barrierDismissible: false,
      builder: (_) => DeliveryNoteEditorDialog(
        api: widget.api,
        salesOrders: _deliverableOrders,
        warehouses: _warehouses,
        products: _products,
        features: _features,
      ),
    );
    if (saved == null || !mounted) return;
    await _load();
    if (!mounted) return;
    NotificationService.show(
      context,
      'Delivery note ${stringValue(saved['delivery_note_number'])} created as '
      'a draft. Dispatching it is what moves the stock.',
      kind: AppNotificationKind.success,
    );
  }

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
    return DocumentStatusGate.deliveryNote.allows(lifecycle, status);
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
        widget.api.documentSummary('delivery-notes'),
        widget.api.documentPage(
          'delivery-notes',
          page: _page,
          pageSize: _rowsPerPage,
          search: _search.text.trim(),
          sortBy: 'delivery_date',
          descending: true,
          additionalQuery: _view.query,
        ),
      ]);
      final Json summary = _unwrap(responses[0]);
      final Json page = _unwrap(responses[1]);
      final List<_DeliveryNoteRecord> notes = _recordsFromResponse(page);
      _DeliveryNoteRecord? selected = _selected;
      if (selected != null) {
        final List<_DeliveryNoteRecord> matches = notes.where((item) => item.id == selected!.id).toList();
        selected = matches.isEmpty ? null : matches.first;
      }
      if (selected == null && notes.isNotEmpty) {
        selected = notes.first;
      }
      // The timeline is no longer fetched on every list load. It filled a
      // pane that was on screen whether or not anybody wanted it; the dialog
      // reads it when the document is opened.
      if (!mounted) return;
      setState(() {
        _summary = summary;
        _notes = notes;
        _total = page['pagination'] is Map ? (page['pagination']['total'] as num?)?.toInt() ?? notes.length : notes.length;
        _selected = selected;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.toString();
        _notes = const [];
        _selected = null;
        _total = 0;
      });
    } finally {
      if (mounted) {
        setState(() => _loading = false);
      }
    }
  }

  /// Select a row.
  ///
  /// This used to fetch the note's timeline on every click, to fill a pane
  /// that was on screen whether or not anybody wanted it. The dialog reads it
  /// when the document is actually opened.
  void _selectNote(_DeliveryNoteRecord row) {
    setState(() => _selected = row);
  }

  /// Show one note: header, lines, totals and timeline.
  Future<void> _openNote(_DeliveryNoteRecord row) async {
    setState(() => _selected = row);
    List<DocumentTimelineSnapshot> history = const [];
    try {
      final Json timeline =
          _unwrap(await widget.api.documentHistory('delivery-notes', row.id));
      history = _timelineFromResponse(timeline);
    } on ApiException {
      history = const [];
    }
    if (!mounted) return;
    await showDialog<void>(
      context: context,
      builder: (_) => DocumentViewDialog(
        title: row.deliveryNoteNumber,
        subtitle: 'Against ${row.salesOrderReference}',
        icon: Icons.local_shipping_outlined,
        header: row.toHeader(),
        lines: [
          for (final _DeliveryNoteLine line in row.lines)
            DocumentLineSnapshot(
              lineNumber: line.lineNumber,
              product: line.productId,
              uom: line.salesUomId,
              quantity: line.currentDeliveryQuantity,
              unitPrice: line.unitPrice,
              amount: line.grossAmount,
              netAmount: line.netAmount,
              remarks: line.remarks,
            ),
        ],
        totals: row.toTotals(),
        history: history,
      ),
    );
  }

  @override
  Widget build(BuildContext context) => ModuleWorkspaceFrame(
        title: 'Delivery Notes',
        description: 'Deliver against approved sales orders. Dispatching a '
            'note is what moves the stock.',
        breadcrumbs: const ['Workspace', 'Sales', 'Delivery Notes'],
        child: Column(
          children: [
            if (_loading) const LinearProgressIndicator(minHeight: 2),
            Padding(
              padding: const EdgeInsets.fromLTRB(24, 0, 24, 12),
              child: SummaryCards(
                children: [
                  _summaryCard('Total', '${_summary['total'] ?? 0}'),
                  _summaryCard('Draft', '${_summary['draft'] ?? 0}'),
                  _summaryCard('Approved', '${_summary['approved'] ?? 0}'),
                  _summaryCard('Dispatched', '${_summary['dispatched'] ?? 0}'),
                  _summaryCard('Completed', '${_summary['completed'] ?? 0}'),
                  _summaryCard('Cancelled', '${_summary['cancelled'] ?? 0}'),
                ],
              ),
            ),
            // Bounded, so the layout below has a height to divide.
            Expanded(child: _buildGridWorkspace()),
          ],
        ),
      );

  Widget _buildGridWorkspace() => ManagementWorkspaceLayout(
        toolbar: _buildToolbar(),
        viewBar: _buildViewBar(),
        searchPanel: SearchFilterPanel(
          controller: _search,
          hintText: 'Search note number, sales order...',
          onSearch: (_) => _load(requestedPage: 1),
        ),
        primaryContent: !widget.hasActiveFirm
            ? const StandardEmptyState(type: EmptyStateType.noFirmSelected)
            : _error != null && !_loading
                ? WorkspaceEmptyState(
                    title: 'Delivery notes unavailable',
                    message: _error!,
                  )
                : _notes.isEmpty && !_loading
                    ? StandardEmptyState(
                        type: _search.text.trim().isEmpty
                            ? EmptyStateType.noRecords
                            : EmptyStateType.noSearchResults,
                      )
                    : _buildNoteGrid(),
        // No side pane. It sat at `flex: 4` against a `flex: 3` list.
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
        isVisible: (action) =>
            action != ToolbarAction.newItem || _canCreate,
        isEnabled: (action) =>
            !_loading &&
            switch (action) {
              // A delivery note line needs an approved sales order line
              // behind it, so nothing to deliver against is a disabled button
              // rather than an empty dialog.
              ToolbarAction.newItem =>
                _canCreate && _deliverableOrders.isNotEmpty,
              ToolbarAction.view => _selected != null,
              ToolbarAction.refresh => true,
              _ => false,
            },
        onAction: (action) {
          switch (action) {
            case ToolbarAction.newItem:
              unawaited(_createNote());
            case ToolbarAction.view:
              final _DeliveryNoteRecord? selected = _selected;
              if (selected != null) unawaited(_openNote(selected));
            case ToolbarAction.refresh:
              unawaited(_load());
            default:
              break;
          }
        },
        // Dispatch and Complete are separate buttons. They used to share
        // `requestApproval`, which dispatched an approved note and completed
        // anything else -- under a label reading "Request approval", while
        // dispatching is the step that moves the stock.
        trailing: [
          // First, because a challan is what somebody is waiting for when a
          // lorry is at the gate. Enabled on any saved note: paperwork is
          // often printed before the dispatch is confirmed on screen.
          Padding(
            padding: const EdgeInsets.only(left: 8),
            child: OutlinedButton.icon(
              onPressed: _selected == null
                  ? null
                  : () => unawaited(_printChallan(_selected!)),
              icon: const Icon(Icons.print_outlined, size: 18),
              label: const Text('Print challan'),
            ),
          ),
          IconButton(
            tooltip: 'Print settings',
            onPressed: () => unawaited(_openPrintSettings()),
            icon: const Icon(Icons.tune_outlined, size: 18),
          ),
          _actionButton(DocumentToolbarAction.approve, '/approve'),
          _actionButton(DocumentToolbarAction.dispatch, '/dispatch'),
          _actionButton(DocumentToolbarAction.complete, '/complete'),
          _actionButton(DocumentToolbarAction.cancel, '/cancel'),
          _actionButton(DocumentToolbarAction.close, '/close'),
        ],
      );

  /// Render the challan and hand it to whatever prints on this machine.
  Future<void> _printChallan(_DeliveryNoteRecord note) async {
    try {
      final List<int> pdf = await widget.api.deliveryChallanPdf(note.id);
      if (!mounted) return;
      await printDocument(
        context,
        bytes: pdf,
        documentName: note.deliveryNoteNumber,
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

  /// How this firm prints its challans: copies, letterhead, terms, paper.
  Future<void> _openPrintSettings() async {
    await showDialog<bool>(
      context: context,
      builder: (_) => PrintSettingsDialog(
        api: widget.api,
        permissions: widget.permissions,
        documentType: 'DELIVERY_NOTE',
        documentLabel: 'delivery challan',
      ),
    );
  }

  /// A lifecycle button, disabled unless permission **and** the selected
  /// note's status allow it.
  Widget _actionButton(DocumentToolbarAction action, String suffix) => Padding(
        padding: const EdgeInsets.only(left: 8),
        child: OutlinedButton.icon(
          onPressed: _selected == null ||
                  !_mayRun(action) ||
                  !_statusAllows(action, _selected?.status)
              ? null
              : () => unawaited(_act(suffix)),
          icon: Icon(action.icon, size: 18),
          label: Text(action.label),
        ),
      );

  /// Run a lifecycle action against the selected note and reload.
  ///
  /// The try/catch used to sit around the toolbar's `onAction` switch; it
  /// lives here now that each button calls this directly, so a refusal still
  /// reaches the user instead of becoming an unhandled exception.
  Future<void> _act(String suffix) async {
    final _DeliveryNoteRecord? selected = _selected;
    if (selected == null) return;
    try {
      await widget.api.documentAction('delivery-notes', selected.id, suffix);
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

  Widget _buildNoteGrid() => EnterpriseDataGrid<_DeliveryNoteRecord>(
        columns: const [
          GridColumn(key: 'number', label: 'Note Number'),
          GridColumn(key: 'order', label: 'Sales Order'),
          GridColumn(key: 'date', label: 'Delivery Date'),
          GridColumn(key: 'status', label: 'Status'),
          GridColumn(key: 'total', label: 'Grand Total'),
        ],
        items: _notes,
        id: (item) => item.id,
        selectedId: _selected?.id,
        cells: (item) => [
          item.deliveryNoteNumber,
          item.salesOrderReference,
          item.deliveryDate,
          item.status,
          item.grandTotal,
        ],
        onSelect: _selectNote,
        onOpen: (item) => unawaited(_openNote(item)),
        total: _total,
        pageOffset: (_page - 1) * _rowsPerPage,
        rowsPerPage: _rowsPerPage,
        onPageChanged: (offset) {
          final int next = offset ~/ _rowsPerPage + 1;
          if (next != _page) _load(requestedPage: next);
        },
      );

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

  void _selectView(DeliveryNoteView view) {
    if (view == _view) return;
    setState(() {
      _view = view;
      _page = 1;
      _selected = null;
    });
    unawaited(_load(requestedPage: 1));
  }

  /// The status bar: All / Draft / Approved / Dispatched / Completed /
  /// Cancelled.
  ///
  /// Scrollable because six segments do not fit a narrow window, and a
  /// segmented button clips rather than wraps.
  Widget _buildViewBar() => SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: SegmentedButton<DeliveryNoteView>(
          segments: [
            for (final DeliveryNoteView view in DeliveryNoteView.values)
              ButtonSegment<DeliveryNoteView>(
                value: view,
                label: Text(view.label),
              ),
          ],
          selected: <DeliveryNoteView>{_view},
          onSelectionChanged:
              _loading ? null : (selection) => _selectView(selection.first),
          showSelectedIcon: false,
        ),
      );

  Json _unwrap(dynamic response) {
    if (response is! Json) return const {};
    final dynamic data = response['data'];
    return data is Json ? data : response;
  }

  List<_DeliveryNoteRecord> _recordsFromResponse(Json response) {
    final dynamic data = response['data'];
    if (data is! List) return const [];
    return data
        .whereType<Map>()
        .map((item) => _DeliveryNoteRecord.fromJson(Map<String, dynamic>.from(item)))
        .toList(growable: false);
  }

  List<DocumentTimelineSnapshot> _timelineFromResponse(Json response) {
    final dynamic data = response['data'];
    if (data is! List) return const [];
    return data
        .whereType<Map>()
        .map((item) => DocumentTimelineSnapshot.fromJson(Map<String, dynamic>.from(item)))
        .toList(growable: false);
  }
}

class _DeliveryNoteRecord {
  const _DeliveryNoteRecord({
    required this.id,
    required this.deliveryNoteNumber,
    required this.deliveryDate,
    required this.salesOrderReference,
    required this.status,
    required this.subtotal,
    required this.taxTotal,
    required this.additionalCharges,
    required this.roundOff,
    required this.grandTotal,
    required this.branchId,
    required this.warehouseId,
    required this.remarks,
    required this.lines,
  });

  final String id;
  final String deliveryNoteNumber;
  final String deliveryDate;
  final String salesOrderReference;
  final String status;
  final String subtotal;
  final String taxTotal;
  final String additionalCharges;
  final String roundOff;
  final String grandTotal;
  final String branchId;
  final String warehouseId;
  final String remarks;
  final List<_DeliveryNoteLine> lines;

  factory _DeliveryNoteRecord.fromJson(Json json) {
    final List<_DeliveryNoteLine> lines = (json['lines'] is List)
        ? (json['lines'] as List)
            .whereType<Map>()
            .map((item) => _DeliveryNoteLine.fromJson(Map<String, dynamic>.from(item)))
            .toList()
        : const [];
    return _DeliveryNoteRecord(
      id: stringValue(json['id']),
      deliveryNoteNumber: stringValue(json['delivery_note_number']),
      deliveryDate: stringValue(json['delivery_date']),
      salesOrderReference: stringValue(json['sales_order_reference']),
      status: stringValue(json['status']),
      subtotal: stringValue(json['subtotal']),
      taxTotal: stringValue(json['tax_total']),
      additionalCharges: stringValue(json['additional_charges']),
      roundOff: stringValue(json['round_off']),
      grandTotal: stringValue(json['grand_total']),
      branchId: stringValue(json['branch_id']),
      warehouseId: stringValue(json['warehouse_id']),
      remarks: stringValue(json['remarks']),
      lines: lines,
    );
  }

  DocumentHeaderSnapshot toHeader() => DocumentHeaderSnapshot(
        documentTypeCode: 'DELIVERY_NOTE',
        documentTypeName: 'Delivery Note',
        documentNumber: deliveryNoteNumber,
        documentDate: deliveryDate,
        reference: salesOrderReference,
        branch: branchId,
        warehouse: warehouseId,
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

class _DeliveryNoteLine {
  const _DeliveryNoteLine({
    required this.lineNumber,
    required this.productId,
    required this.description,
    required this.salesUomId,
    required this.packagingTypeId,
    required this.currentDeliveryQuantity,
    required this.freeQuantity,
    required this.unitPrice,
    required this.discountAmount,
    required this.taxProfileId,
    required this.grossAmount,
    required this.netAmount,
    required this.remarks,
  });

  final int lineNumber;
  final String productId;
  final String description;
  final String salesUomId;
  final String packagingTypeId;
  final String currentDeliveryQuantity;
  final String freeQuantity;
  final String unitPrice;
  final String discountAmount;
  final String taxProfileId;
  final String grossAmount;
  final String netAmount;
  final String remarks;

  factory _DeliveryNoteLine.fromJson(Json json) => _DeliveryNoteLine(
        lineNumber: (json['line_number'] as num?)?.toInt() ?? 0,
        productId: stringValue(json['product_id']),
        description: stringValue(json['description']),
        salesUomId: stringValue(json['sales_uom_id']),
        packagingTypeId: stringValue(json['packaging_type_id']),
        currentDeliveryQuantity: stringValue(json['current_delivery_quantity']),
        freeQuantity: stringValue(json['free_quantity']),
        unitPrice: stringValue(json['unit_price']),
        discountAmount: stringValue(json['discount_amount']),
        taxProfileId: stringValue(json['tax_profile_id']),
        grossAmount: stringValue(json['gross_amount']),
        netAmount: stringValue(json['net_amount']),
        remarks: stringValue(json['remarks']),
      );
}
