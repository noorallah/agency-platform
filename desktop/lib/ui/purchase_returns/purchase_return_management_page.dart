import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/preferences/desktop_preferences_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/entities.dart';
import '../../models/document_framework.dart';
import '../../models/goods_receipt.dart';
import '../../models/product.dart';
import '../document_framework/document_framework_widgets.dart';
import '../document_framework/document_view_dialog.dart';
import '../workspace/desktop_framework.dart';
import 'purchase_return_editor_dialog.dart';

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

class _PurchaseReturnManagementPageState extends State<PurchaseReturnManagementPage> {
  static const int _rowsPerPage = 20;
  final TextEditingController _search = TextEditingController();
  bool _loading = false;
  String? _error;
  int _page = 1;
  int _total = 0;
  Map<String, dynamic> _summary = const {};
  List<_PurchaseReturnRecord> _returns = const [];
  _PurchaseReturnRecord? _selected;
  List<DocumentTimelineSnapshot> _history = const [];
  // Reference data the editor needs, loaded once with the workspace.
  List<GoodsReceiptRecord> _returnableReceipts = const [];
  List<Product> _products = const [];

  bool get _canCreate => widget.permissions.hasPermission('PURCHASE_CREATE');

  @override
  void initState() {
    super.initState();
    unawaited(_load());
    unawaited(_loadReferenceData());
  }

  /// Load the receipts that can be sent back and the products they name.
  ///
  /// Failing here leaves the create action disabled rather than taking the
  /// workspace down; the list of returns is still readable without it.
  Future<void> _loadReferenceData() async {
    if (!widget.hasActiveFirm || !_canCreate) return;
    try {
      final List<dynamic> results = await Future.wait<dynamic>([
        widget.api.goodsReceipts(
          page: 1,
          pageSize: 100,
          sortBy: 'receipt_date',
          descending: true,
          filters: const {'status': 'COMPLETED'},
        ),
        widget.api.products(page: 1, pageSize: 100),
      ]);
      if (!mounted) return;
      setState(() {
        _returnableReceipts =
            (results[0] as PagedResult<GoodsReceiptRecord>).items;
        _products = (results[1] as PagedResult<Product>).items;
      });
    } on ApiException {
      if (!mounted) return;
      setState(() => _returnableReceipts = const []);
    }
  }

  /// Open the editor and reload if it saved a return.
  Future<void> _createReturn() async {
    final Json? saved = await showDialog<Json>(
      context: context,
      barrierDismissible: false,
      builder: (_) => PurchaseReturnEditorDialog(
        api: widget.api,
        receipts: _returnableReceipts,
        products: _products,
      ),
    );
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

  bool _mayRun(DocumentToolbarAction action) => switch (action) {
        DocumentToolbarAction.approve ||
        DocumentToolbarAction.close ||
        DocumentToolbarAction.archive ||
        DocumentToolbarAction.requestApproval =>
          _mayApprove(),
        DocumentToolbarAction.cancel || DocumentToolbarAction.reject =>
          widget.permissions.hasPermission('PURCHASE_CANCEL'),
        DocumentToolbarAction.newDocument =>
          widget.permissions.hasPermission('PURCHASE_CREATE'),
        DocumentToolbarAction.save =>
          widget.permissions.hasPermission('PURCHASE_UPDATE'),
        DocumentToolbarAction.exportDocument =>
          widget.permissions.hasPermission('PURCHASE_EXPORT'),
        _ => true,
      };

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
      final List<dynamic> responses = await Future.wait<dynamic>([
        widget.api.documentSummary('purchase-returns'),
        widget.api.documentPage(
          'purchase-returns',
          page: _page,
          pageSize: _rowsPerPage,
          search: _search.text.trim(),
          sortBy: 'return_date',
          descending: true,
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
      if (selected == null && returns.isNotEmpty) {
        selected = returns.first;
      }
      List<DocumentTimelineSnapshot> history = const [];
      if (selected != null) {
        try {
          final Map<String, dynamic> timeline = _unwrap(await widget.api.documentHistory('purchase-returns', selected.id));
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
        _total = page['pagination'] is Map
            ? (page['pagination']['total'] as num?)?.toInt() ?? returns.length
            : returns.length;
        _selected = selected;
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
            padding: const EdgeInsets.fromLTRB(24, 0, 24, 12),
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

  Widget _buildGridWorkspace() => ManagementWorkspaceLayout(
        toolbar: _buildToolbar(),
        searchPanel: SearchFilterPanel(
          controller: _search,
          hintText: 'Search return number, supplier return...',
          onSearch: (_) => _load(requestedPage: 1),
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
              ToolbarAction.view => _selected != null,
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
        trailing: [
          _actionButton(
            'Approve',
            Icons.thumb_up_outlined,
            DocumentToolbarAction.approve,
            '/approve',
          ),
          _actionButton(
            'Complete',
            Icons.check_circle_outline,
            DocumentToolbarAction.approve,
            '/complete',
          ),
          _actionButton(
            'Cancel',
            Icons.cancel_outlined,
            DocumentToolbarAction.cancel,
            '/cancel',
          ),
          _actionButton(
            'Close',
            Icons.lock_outline,
            DocumentToolbarAction.close,
            '/close',
          ),
        ],
      );

  Widget _actionButton(
    String label,
    IconData icon,
    DocumentToolbarAction action,
    String suffix,
  ) =>
      Padding(
        padding: const EdgeInsets.only(left: 8),
        child: OutlinedButton.icon(
          onPressed: _selected == null || !_mayRun(action)
              ? null
              : () => unawaited(_act(suffix)),
          icon: Icon(icon, size: 18),
          label: Text(label),
        ),
      );

  Widget _buildReturnGrid() => EnterpriseDataGrid<_PurchaseReturnRecord>(
        columns: const [
          GridColumn(key: 'number', label: 'Return Number'),
          GridColumn(key: 'supplier', label: 'Supplier Return'),
          GridColumn(key: 'date', label: 'Return Date'),
          GridColumn(key: 'status', label: 'Status'),
          GridColumn(key: 'total', label: 'Grand Total'),
        ],
        items: _returns,
        id: (item) => item.id,
        selectedId: _selected?.id,
        cells: (item) => [
          item.returnNumber,
          item.supplierReturnNumber,
          item.returnDate,
          item.status,
          item.grandTotal,
        ],
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
    await showDialog<void>(
      context: context,
      builder: (_) => DocumentViewDialog(
        title: record.returnNumber,
        subtitle: 'Supplier return ${record.supplierReturnNumber}',
        icon: Icons.assignment_return_outlined,
        header: record.toHeader(),
        lines: [
          for (final _PurchaseReturnLine line in record.lines)
            DocumentLineSnapshot(
              lineNumber: line.lineNumber,
              product: line.productId,
              description: line.description,
              uom: line.returnUomId,
              packaging: line.packagingTypeId,
              quantity: line.currentReturnQuantity,
              unitPrice: line.unitPrice,
              discount: line.discountAmount,
              taxProfile: line.taxProfileId,
              amount: line.grossAmount,
              netAmount: line.netAmount,
              remarks: line.remarks,
            ),
        ],
        totals: record.toTotals(),
        history: _history,
      ),
    );
  }

  Future<void> _act(String suffix) async {
    final _PurchaseReturnRecord? selected = _selected;
    if (selected == null) {
      return;
    }
    try {
      await widget.api.documentAction('purchase-returns', selected.id, suffix);
      await _load();
    } on ApiException catch (error) {
      if (!mounted) {
        return;
      }
      NotificationService.show(
        context,
        error.message,
        kind: AppNotificationKind.error,
      );
    }
  }

  Future<void> _selectReturn(_PurchaseReturnRecord row) async {
    setState(() => _selected = row);
    try {
      final Map<String, dynamic> timeline = _unwrap(await widget.api.documentHistory('purchase-returns', row.id));
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

  List<_PurchaseReturnRecord> _recordsFromResponse(Map<String, dynamic> response) {
    final dynamic data = response['data'];
    if (data is! List) {
      return const [];
    }
    return data
        .whereType<Map>()
        .map((item) => _PurchaseReturnRecord.fromJson(Map<String, dynamic>.from(item)))
        .toList();
  }

  List<DocumentTimelineSnapshot> _timelineFromResponse(Map<String, dynamic> response) {
    final dynamic data = response['data'];
    if (data is! List) {
      return const [];
    }
    return data
        .whereType<Map>()
        .map((item) => DocumentTimelineSnapshot.fromJson(Map<String, dynamic>.from(item)))
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
            .map((item) => _PurchaseReturnLine.fromJson(Map<String, dynamic>.from(item)))
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
      currencyCode: stringValue(json['currency_code']),
      exchangeRate: stringValue(json['exchange_rate']),
      paymentTerms: stringValue(json['payment_terms']),
      remarks: stringValue(json['remarks']),
      lines: lines,
      sources: (json['sources'] is List)
          ? (json['sources'] as List).whereType<Map>().map((item) => Map<String, dynamic>.from(item)).toList()
          : const [],
    );
  }

  DocumentHeaderSnapshot toHeader() => DocumentHeaderSnapshot(
        documentTypeCode: 'PURCHASE_RETURN',
        documentTypeName: 'Purchase Return',
        documentNumber: returnNumber,
        documentDate: returnDate,
        reference: supplierReturnNumber,
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
  });

  final int lineNumber;
  final String productId;
  final String description;
  final String returnUomId;
  final String packagingTypeId;
  final String currentReturnQuantity;
  final String unitPrice;
  final String discountAmount;
  final String taxProfileId;
  final String grossAmount;
  final String netAmount;
  final String remarks;

  factory _PurchaseReturnLine.fromJson(Map<String, dynamic> json) => _PurchaseReturnLine(
        lineNumber: (json['line_number'] as num?)?.toInt() ?? 0,
        productId: stringValue(json['product_id']),
        description: stringValue(json['description']),
        returnUomId: stringValue(json['return_uom_id']),
        packagingTypeId: stringValue(json['packaging_type_id']),
        currentReturnQuantity: stringValue(json['current_return_quantity']),
        unitPrice: stringValue(json['unit_price']),
        discountAmount: stringValue(json['discount_amount']),
        taxProfileId: stringValue(json['tax_profile_id']),
        grossAmount: stringValue(json['gross_amount']),
        netAmount: stringValue(json['net_amount']),
        remarks: stringValue(json['remarks']),
      );
}
