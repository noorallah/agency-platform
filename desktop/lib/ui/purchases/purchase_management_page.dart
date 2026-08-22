import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math' as math;

import 'package:excel/excel.dart' as xls;
import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/api/api_client.dart';
import '../../core/dialogs/app_dialogs.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/preferences/desktop_preferences_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/branch_warehouse.dart';
import '../../models/entities.dart';
import '../../models/product.dart';
import '../../models/purchase.dart';
import '../../models/tax_framework.dart';
import '../../models/vendor.dart';
import '../inventory/inventory_import_wizard.dart';
import '../document_framework/document_framework_widgets.dart';
import '../workspace/desktop_framework.dart';
import '../../models/document_framework.dart';

/// A destination in the Purchases module -- one sidebar entry each.
enum PurchaseSection {
  dashboard,
  purchaseOrders,
  analytics,
  settings,
}

/// A named view over the one purchase order list.
///
/// These were five sidebar entries of their own -- Draft, Open, Cancelled and
/// Closed Orders plus History -- and every one of them opened this same
/// workspace with a filter preset. They are views, not modules, and the
/// navigation now says so.
enum PurchaseOrderView {
  all,
  draft,
  open,
  cancelled,
  closed,
  history;

  /// The status this view filters on, or null for every status.
  String? get status => switch (this) {
        PurchaseOrderView.draft => 'DRAFT',
        PurchaseOrderView.open => 'SUBMITTED',
        PurchaseOrderView.cancelled => 'CANCELLED',
        PurchaseOrderView.closed => 'CLOSED',
        PurchaseOrderView.all || PurchaseOrderView.history => null,
      };

  /// History is a **sort**, not a status: every order, oldest document first.
  /// It is the one view here that does not narrow the list, and keeping its
  /// own ordering is what makes it worth a segment at all.
  String get sortBy =>
      this == PurchaseOrderView.history ? 'purchase_date' : 'created_at';

  String get label => switch (this) {
        PurchaseOrderView.all => 'All',
        PurchaseOrderView.draft => 'Draft',
        PurchaseOrderView.open => 'Open',
        PurchaseOrderView.cancelled => 'Cancelled',
        PurchaseOrderView.closed => 'Closed',
        PurchaseOrderView.history => 'History',
      };
}

class PurchaseManagementPage extends StatefulWidget {
  const PurchaseManagementPage({
    super.key,
    required this.api,
    required this.preferences,
    required this.permissions,
    required this.hasActiveFirm,
    required this.section,
    this.initialView = PurchaseOrderView.all,
    this.onNavigateToSection,
    this.onOpenGlobalSearch,
  });

  final ApiClient api;
  final DesktopPreferencesService preferences;
  final PermissionService permissions;
  final bool hasActiveFirm;
  final PurchaseSection section;

  /// Which segment of the status bar to open on.
  ///
  /// Normally `all`. It is a parameter so the shell can honour a stored
  /// workspace of `draft-orders` -- a tab id that no longer exists -- by
  /// opening Purchase Orders on Draft rather than dropping the user on the
  /// Dashboard.
  final PurchaseOrderView initialView;
  final ValueChanged<PurchaseSection>? onNavigateToSection;
  final Future<void> Function()? onOpenGlobalSearch;

  @override
  State<PurchaseManagementPage> createState() => _PurchaseManagementPageState();
}

class _PurchaseManagementPageState extends State<PurchaseManagementPage> {
  static const int _rowsPerPage = 20;
  static const String _preferencesKey = 'purchase_workspace';
  static const List<String> _importHeaders = <String>[
    'branchid',
    'warehouseid',
    'vendorid',
    'productid',
    'purchasedate',
    'orderedqty',
    'unitprice',
  ];

  final TextEditingController _search = TextEditingController();
  final FocusNode _searchFocus = FocusNode();
  final TextEditingController _createdFrom = TextEditingController();
  final TextEditingController _createdTo = TextEditingController();

  bool _loading = false;
  String? _error;
  int _page = 1;
  int _total = 0;
  bool _filtersExpanded = false;
  bool _includeDeleted = false;
  String? _vendorId;

  /// The status chosen in the advanced filter panel. It still wins over the
  /// view's own status, which is the behaviour the section presets had.
  String? _status;

  /// Which segment of the status bar is showing.
  late PurchaseOrderView _view = widget.initialView;
  String? _branchId;
  String? _warehouseId;
  String? _buyerId;
  String? _purchaseType;
  List<String> _recentSearches = const [];
  List<String> _savedSearches = const [];
  List<_PurchaseSavedView> _savedViews = const [];
  Map<String, bool> _visibleColumns = Map<String, bool>.from(_defaultColumns);

  List<Vendor> _vendors = const [];
  List<BranchRecord> _branches = const [];
  List<WarehouseRecord> _warehouses = const [];
  List<Product> _products = const [];
  List<PlatformUser> _buyers = const [];
  List<TaxProfileRecord> _taxProfiles = const [];
  List<StorageNodeRecord> _storageNodes = const [];

  PurchaseSummaryRecord? _summary;
  List<PurchaseOrder> _orders = const [];
  PurchaseOrder? _selected;
  Set<String> _selectedIds = <String>{};

  bool get _canView => widget.permissions.hasPermission('PURCHASE_VIEW');
  bool get _canCreate => widget.permissions.hasPermission('PURCHASE_CREATE');
  bool get _canUpdate => widget.permissions.hasPermission('PURCHASE_UPDATE');
  bool get _canDelete => widget.permissions.hasPermission('PURCHASE_DELETE');
  bool get _canRestore => widget.permissions.hasPermission('PURCHASE_RESTORE');
  bool get _canImport => widget.permissions.hasPermission('PURCHASE_IMPORT');
  bool get _canExport => widget.permissions.hasPermission('PURCHASE_EXPORT');
  /// Approving, and closing, both take `PURCHASE_APPROVE`.
  bool get _canApprove =>
      widget.permissions.hasPermission('PURCHASE_APPROVE');
  bool get _canCancel => widget.permissions.hasPermission('PURCHASE_CANCEL');

  static const Map<String, bool> _defaultColumns = <String, bool>{
    'po': true,
    'vendor': true,
    'branch': true,
    'warehouse': true,
    'buyer': true,
    'date': true,
    'delivery': true,
    'type': true,
    'priority': true,
    'status': true,
    'total': true,
  };

  @override
  void initState() {
    super.initState();
    unawaited(_bootstrap());
  }

  @override
  void didUpdateWidget(covariant PurchaseManagementPage oldWidget) {
    super.didUpdateWidget(oldWidget);
    // The sub-tabs build this class in the same slot with no key, so Flutter
    // keeps this State and `initState` never runs again. `_load` is
    // called rather than `_bootstrap`: the lookups and saved views it fetched
    // are tab-agnostic, and re-reading seven of them on every sub-tab click is
    // the cost that ruled out keying the whole page.
    if (widget.section == oldWidget.section) return;
    _resetForSection();
    unawaited(_load());
  }

  /// Switch the list to another view of itself.
  ///
  /// Deliberately not `_resetForSection`: the user is looking at one screen
  /// and narrowing it, so their search term and filters stay. The selection
  /// does not -- it drives the bulk actions, and a bulk close carried over
  /// from All could act on orders no longer on screen.
  void _selectView(PurchaseOrderView view) {
    if (view == _view) return;
    setState(() {
      _view = view;
      _page = 1;
      _selected = null;
      _selectedIds = <String>{};
    });
    unawaited(_load(requestedPage: 1));
  }

  /// Drop what belonged to the tab being left.
  ///
  /// `_selectedIds` is the important one. It drives the bulk actions, and
  /// carrying it across a sub-tab switch means a bulk close or cancel could
  /// operate on orders selected on the tab the user just left — rows that are
  /// no longer even on screen. The status and sort come from
  /// `_statusForView`, so leaving them would show the previous tab's rows
  /// under the new heading, which is worse than an empty grid because it looks
  /// right.
  void _resetForSection() {
    _search.clear();
    _createdFrom.clear();
    _createdTo.clear();
    _page = 1;
    _total = 0;
    _error = null;
    _includeDeleted = false;
    _vendorId = null;
    _branchId = null;
    _warehouseId = null;
    _buyerId = null;
    _purchaseType = null;
    _selected = null;
    _selectedIds = <String>{};
  }

  @override
  void dispose() {
    _search.dispose();
    _searchFocus.dispose();
    _createdFrom.dispose();
    _createdTo.dispose();
    super.dispose();
  }

  Future<void> _bootstrap() async {
    _loadPreferences();
    if (!widget.hasActiveFirm || !_canView) {
      return;
    }
    await _loadLookups();
    await _load();
  }

  void _loadPreferences() {
    final Map<String, dynamic> raw =
        widget.preferences.current.serverPreferences[_preferencesKey] is Map
            ? Map<String, dynamic>.from(
                widget.preferences.current.serverPreferences[_preferencesKey]
                    as Map,
              )
            : const {};
    _recentSearches = stringList(raw['recent_searches']).take(8).toList();
    _savedSearches = stringList(raw['saved_searches']).take(12).toList();
    _visibleColumns = {
      ..._defaultColumns,
      if (raw['visible_columns'] is Map)
        ...Map<String, dynamic>.from(raw['visible_columns'] as Map).map(
          (key, value) => MapEntry(key, value == true),
        ),
    };
    _savedViews = ((raw['saved_views'] as List?) ?? const [])
        .whereType<Map>()
        .map(
          (item) =>
              _PurchaseSavedView.fromJson(Map<String, dynamic>.from(item)),
        )
        .toList();
  }

  Future<void> _persistPreferences() =>
      widget.preferences.cacheServerPreferences({
        ...widget.preferences.current.serverPreferences,
        _preferencesKey: {
          'recent_searches': _recentSearches,
          'saved_searches': _savedSearches,
          'visible_columns': _visibleColumns,
          'saved_views': _savedViews.map((item) => item.toJson()).toList(),
        },
      });

  /// Read one lookup, and let it fail on its own.
  ///
  /// These used to be a single `Future.wait`, which fails fast: the first
  /// rejection abandoned the other five, so one bad request left the editor
  /// with no vendors, no branches, no warehouses, no products, no buyers and
  /// no tax profiles. The `catch` around it said it kept the workspace
  /// responsive "even if some optional lookups fail", and could not -- it
  /// never saw a partial result to keep.
  Future<List<T>> _lookup<T>(Future<List<T>> Function() read) async {
    try {
      return await read();
    } on ApiException {
      return <T>[];
    }
  }

  Future<void> _loadLookups() async {
    // Warehouses and products page through rather than asking for one
    // oversized page. `MAX_PAGE_SIZE` is 100 and it is refused rather than
    // clamped, so `pageSize: 200` and `pageSize: 500` were a 500 from every
    // real server -- and through the old `Future.wait` they took the four
    // healthy lookups down with them. That is why the New Purchase Order form
    // offered no vendor and no branch: both of those requests succeeded.
    final List<Vendor> vendors = await _lookup(
      () => fetchAllPages((page) => widget.api.vendors(page: page)),
    );
    final List<BranchRecord> branches = await _lookup(
      () => fetchAllPages(
        (page) => widget.api.branches(page: page, pageSize: maxApiPageSize),
      ),
    );
    final List<WarehouseRecord> warehouses = await _lookup(
      () => fetchAllPages(
        (page) => widget.api.warehouses(page: page, pageSize: maxApiPageSize),
      ),
    );
    final List<Product> products = await _lookup(
      () => fetchAllPages(
        (page) => widget.api.products(page: page, pageSize: maxApiPageSize),
      ),
    );
    final List<PlatformUser> buyers = await _lookup(
      () => fetchAllPages(
        (page) => widget.api
            .users(page: page, search: '', sortBy: 'email', descending: false),
      ),
    );
    final List<TaxProfileRecord> taxProfiles = await _lookup(
      () => fetchAllPages(
        (page) => widget.api.taxProfiles(
            page: page, search: '', sortBy: 'name', descending: false),
      ),
    );
    final List<StorageNodeRecord> storageNodes = [];
    for (final WarehouseRecord warehouse in warehouses) {
      try {
        storageNodes.addAll(await widget.api.storageNodes(warehouse.id));
      } on ApiException {
        // Keep the rest of the workspace available even if one warehouse fails.
      }
    }
    if (!mounted) return;
    setState(() {
      _vendors = vendors;
      _branches = branches;
      _warehouses = warehouses;
      _products = products;
      _buyers = buyers;
      _taxProfiles = taxProfiles;
      _storageNodes = storageNodes;
    });
  }

  Future<void> _load({int? requestedPage}) async {
    if (!widget.hasActiveFirm || !_canView) {
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
      _page = requestedPage ?? _page;
    });
    try {
      final PurchaseQuery filters = _effectiveFilters();
      final List<dynamic> results = await Future.wait<dynamic>([
        widget.api.purchaseSummary(),
        widget.api.purchases(
          page: _page,
          pageSize: _rowsPerPage,
          search: _search.text.trim(),
          sortBy: _sortByForView(),
          descending: true,
          filters: filters,
        ),
      ]);
      final PurchaseSummaryRecord summary = results[0] as PurchaseSummaryRecord;
      final PagedResult<PurchaseOrder> orders =
          results[1] as PagedResult<PurchaseOrder>;
      PurchaseOrder? selected = _selected;
      if (selected != null) {
        selected =
            orders.items.where((item) => item.id == selected!.id).firstOrNull;
      }
      if (selected == null && orders.items.isNotEmpty) {
        selected = orders.items.first;
      }
      if (!mounted) return;
      setState(() {
        _summary = summary;
        _orders = orders.items;
        _total = orders.total;
        _selected = selected;
        _selectedIds = _selectedIds
            .where((id) => orders.items.any((item) => item.id == id))
            .toSet();
      });
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() {
        _error = exception.isForbidden
            ? 'You are not authorized to access purchase management.'
            : exception.message;
        _orders = const [];
        _summary = null;
        _total = 0;
        _selected = null;
        _selectedIds = <String>{};
        });
    } finally {
      if (mounted) {
        setState(() => _loading = false);
      }
    }
  }

  PurchaseQuery _effectiveFilters() => PurchaseQuery(
        vendorId: _vendorId,
        status: _status ?? _statusForView(),
        branchId: _branchId,
        warehouseId: _warehouseId,
        buyerId: _buyerId,
        purchaseType: _purchaseType,
        createdFrom: _createdFrom.text.trim(),
        createdTo: _createdTo.text.trim(),
        includeDeleted: _includeDeleted,
      );

  /// The status the current view asks for. The advanced filter panel's own
  /// Status still overrides it, which is what the old section presets did.
  ///
  /// Only the Purchase Orders workspace has views; every other section reads
  /// the whole list.
  String? _statusForView() =>
      widget.section == PurchaseSection.purchaseOrders ? _view.status : null;

  String _sortByForView() {
    if (widget.section == PurchaseSection.dashboard) return 'purchase_date';
    return widget.section == PurchaseSection.purchaseOrders
        ? _view.sortBy
        : 'created_at';
  }

  Future<void> _runSearch([String? value]) async {
    final String query = (value ?? _search.text).trim();
    if (query.isNotEmpty) {
      _recentSearches = [
        query,
        ..._recentSearches.where((item) => item != query),
      ].take(8).toList();
      await _persistPreferences();
    }
    await _load(requestedPage: 1);
  }

  Future<void> _saveSearch() async {
    final String query = _search.text.trim();
    if (query.isEmpty) return;
    setState(() {
      _savedSearches = [query, ..._savedSearches.where((item) => item != query)]
          .take(12)
          .toList();
    });
    await _persistPreferences();
    if (!mounted) return;
    NotificationService.show(
      context,
      'Saved search "$query".',
      kind: AppNotificationKind.success,
    );
  }

  /// Select a row.
  ///
  /// This used to fetch that order's whole history as well, on every click,
  /// to fill one "Latest Activity" line in the details panel. The view dialog
  /// loads its own history, so with the panel gone the request went with it.
  void _selectOrder(PurchaseOrder order) {
    setState(() => _selected = order);
  }

  /// Whether this order may be edited, saying why when it may not.
  ///
  /// Approving is a statement about a particular document, so the server
  /// withdraws the approval when the document changes. That has to be said
  /// before the editor opens rather than discovered afterwards -- somebody
  /// correcting a typo on an approved order is entitled to know it will need
  /// approving again.
  Future<bool> _mayEdit(PurchaseOrder order) async {
    final String? refusal = order.editRefusal;
    if (refusal != null) {
      NotificationService.show(
        context,
        refusal,
        kind: AppNotificationKind.warning,
      );
      return false;
    }
    if (!order.isApproved) return true;
    return showWorkspaceConfirmDialog(
      context,
      title: 'Editing withdraws the approval',
      message: '${order.poNumber} has been approved. Changing it returns the '
          'order to Draft, and it will need submitting and approving again.',
      confirmLabel: 'Edit anyway',
      type: ConfirmationType.custom,
    );
  }

  Future<void> _openEditor(PurchaseDialogMode mode,
      [PurchaseOrder? seed]) async {
    if (mode == PurchaseDialogMode.create && !_canCreate) return;
    if (mode == PurchaseDialogMode.edit && (!_canUpdate || seed == null)) {
      return;
    }
    if (mode == PurchaseDialogMode.edit && !await _mayEdit(seed!)) {
      return;
    }
    if ((mode == PurchaseDialogMode.view ||
            mode == PurchaseDialogMode.duplicate) &&
        seed == null) {
      return;
    }
    PurchaseOrder? order = seed;
    if (seed != null) {
      try {
        order = await widget.api.purchaseOrder(seed.id, includeDeleted: true);
      } on ApiException {
        order = seed;
      }
    }
    if (!mounted) return;
    final PurchaseEditorOutcome? outcome =
        await showDialog<PurchaseEditorOutcome>(
      context: context,
      barrierDismissible: false,
      builder: (_) => PurchaseOrderEditorDialog(
        api: widget.api,
        mode: mode,
        order: order,
        vendors: _vendors,
        branches: _branches,
        warehouses: _warehouses,
        products: _products,
        buyers: _buyers,
        taxProfiles: _taxProfiles,
        storageNodes: _storageNodes,
        canSubmit: _canUpdate,
        canApprove: _canApprove,
      ),
    );
    if (outcome == null) return;
    if (!mounted) return;
    // Only a save created or updated anything. A submit or approve run
    // from inside the dialog has already said what it did, where it
    // happened.
    if (outcome.saved) {
      NotificationService.show(
        context,
        'Purchase order ${mode == PurchaseDialogMode.create || mode == PurchaseDialogMode.duplicate ? 'created' : 'updated'}.',
        kind: AppNotificationKind.success,
      );
    }
    await _load();
    _selectOrder(outcome.order);
  }

  Future<void> _deleteSelected() async {
    final List<String> ids = _selectedIds.isNotEmpty
        ? _selectedIds.toList(growable: false)
        : (_selected == null ? const [] : <String>[_selected!.id]);
    if (ids.isEmpty || !_canDelete) return;
    final bool accepted = await showWorkspaceConfirmDialog(
      context,
      title:
          ids.length == 1 ? 'Delete purchase order' : 'Delete purchase orders',
      message: ids.length == 1
          ? 'The selected purchase order will be soft-deleted and can be restored later.'
          : '${ids.length} purchase orders will be soft-deleted and can be restored later.',
      confirmLabel: 'Delete',
      type: ConfirmationType.delete,
    );
    if (!accepted) return;
    if (!mounted) return;
    await AppDialogs.whileLoading(
      context,
      Future.wait(ids.map(widget.api.deletePurchaseOrder)),
      message: 'Deleting purchase order records...',
    );
    if (!mounted) return;
    NotificationService.show(
      context,
      '${ids.length} purchase order${ids.length == 1 ? '' : 's'} deleted.',
      kind: AppNotificationKind.success,
    );
    await _load();
  }

  Future<void> _restoreSelected() async {
    final PurchaseOrder? selected = _selected;
    if (selected == null || !_canRestore || !selected.isDeleted) return;
    final PurchaseOrder restored = await AppDialogs.whileLoading(
      context,
      widget.api.restorePurchaseOrder(selected.id),
      message: 'Restoring purchase order...',
    );
    if (!mounted) return;
    NotificationService.show(
      context,
      'Purchase order restored.',
      kind: AppNotificationKind.success,
    );
    setState(() => _selected = restored);
    await _load();
  }

  Future<void> _requestStatusAction({
    required String title,
    required Future<PurchaseOrder> Function(String reason) action,
    required String successMessage,
  }) async {
    final PurchaseOrder? selected = _selected;
    if (selected == null) return;
    final String? reason = await showDialog<String>(
      context: context,
      builder: (_) => _ReasonDialog(title: title),
    );
    if (reason == null) return;
    if (!mounted) return;
    final PurchaseOrder result = await AppDialogs.whileLoading(
      context,
      action(reason),
      message: '$title...',
    );
    if (!mounted) return;
    NotificationService.show(
      context,
      successMessage,
      kind: AppNotificationKind.success,
    );
    setState(() => _selected = result);
    await _load();
  }

  Future<void> _openImportWizard() async {
    if (!_canImport) return;
    final bool? imported = await showDialog<bool>(
      context: context,
      barrierDismissible: false,
      builder: (_) => Dialog(
        insetPadding: const EdgeInsets.all(24),
        clipBehavior: Clip.antiAlias,
        child: SizedBox(
          width: 960,
          height: 720,
          child: PurchaseImportWizard(
            api: widget.api,
            requiredHeaders: _importHeaders,
            onImported: () async {
              if (mounted) Navigator.of(context).pop(true);
            },
          ),
        ),
      ),
    );
    if (imported == true) {
      await _load();
    }
  }

  Future<void> _openExport() async {
    if (!_canExport) return;
    final _PurchaseExportRequest? request =
        await showDialog<_PurchaseExportRequest>(
      context: context,
      builder: (_) => _PurchaseExportDialog(
        hasSelection: _selectedIds.isNotEmpty,
      ),
    );
    if (request == null) return;
    final List<PurchaseOrder> scoped = switch (request.scope) {
      _PurchaseExportScope.selected => _orders
          .where((item) => _selectedIds.contains(item.id))
          .toList(growable: false),
      _PurchaseExportScope.currentView ||
      _PurchaseExportScope.filteredView =>
        _orders,
    };
    final List<int> bytes = request.format == 'xlsx'
        ? _ordersToXlsx(scoped)
        : utf8.encode(_ordersToCsv(scoped));
    final FileSaveLocation? location = await getSaveLocation(
      suggestedName:
          'purchase_orders_${request.scope.name}.${request.format == 'xlsx' ? 'xlsx' : 'csv'}',
    );
    if (location == null) return;
    if (request.format == 'xlsx') {
      await File(location.path).writeAsBytes(bytes, flush: true);
    } else {
      await File(location.path).writeAsString(utf8.decode(bytes), flush: true);
    }
    if (!mounted) return;
    NotificationService.show(
      context,
      'Purchase export saved.',
      kind: AppNotificationKind.success,
    );
  }

  List<int> _ordersToXlsx(List<PurchaseOrder> items) {
    final xls.Excel workbook = xls.Excel.createExcel();
    final xls.Sheet sheet = workbook['PurchaseOrders'];
    sheet.appendRow(_exportHeaders.map(xls.TextCellValue.new).toList());
    for (final PurchaseOrder item in items) {
      sheet.appendRow(
        [
          xls.TextCellValue(item.poNumber),
          xls.TextCellValue(_labelForVendor(item.vendorId)),
          xls.TextCellValue(_labelForBranch(item.branchId)),
          xls.TextCellValue(_labelForWarehouse(item.warehouseId)),
          xls.TextCellValue(item.purchaseDate),
          xls.TextCellValue(item.expectedDeliveryDate),
          xls.TextCellValue(item.purchaseType),
          xls.TextCellValue(item.priority),
          xls.TextCellValue(item.status),
          xls.TextCellValue(item.grandTotal),
        ],
      );
    }
    return workbook.encode() ?? const <int>[];
  }

  String _ordersToCsv(List<PurchaseOrder> items) => [
        _exportHeaders,
        ...items.map(
          (item) => [
            item.poNumber,
            _labelForVendor(item.vendorId),
            _labelForBranch(item.branchId),
            _labelForWarehouse(item.warehouseId),
            item.purchaseDate,
            item.expectedDeliveryDate,
            item.purchaseType,
            item.priority,
            item.status,
            item.grandTotal,
          ],
        ),
      ].map((row) => row.map(_csvValue).join(',')).join('\n');

  List<String> get _exportHeaders => const <String>[
        'PO Number',
        'Vendor',
        'Branch',
        'Warehouse',
        'Purchase Date',
        'Expected Delivery',
        'Purchase Type',
        'Priority',
        'Status',
        'Grand Total',
      ];

  Future<void> _openColumnChooser() async {
    final _PurchaseSavedViewSelection? selection =
        await showDialog<_PurchaseSavedViewSelection>(
      context: context,
      builder: (_) => _ColumnChooserDialog(
        visibleColumns: _visibleColumns,
      ),
    );
    if (selection == null) return;
    setState(() {
      _visibleColumns = selection.columns;
      if (selection.viewName.trim().isNotEmpty) {
        _savedViews = [
          _PurchaseSavedView(
            name: selection.viewName.trim(),
            visibleColumns: selection.columns,
          ),
          ..._savedViews.where(
            (item) =>
                item.name.toLowerCase() !=
                selection.viewName.trim().toLowerCase(),
          ),
        ].take(10).toList();
      }
    });
    await _persistPreferences();
  }

  void _applySavedView(_PurchaseSavedView view) {
    setState(() => _visibleColumns = view.visibleColumns);
    unawaited(_persistPreferences());
  }

  Future<void> _copySelectedRow() async {
    final PurchaseOrder? selected = _selected;
    if (selected == null) return;
    await copyTextToClipboard(
      [
        selected.poNumber,
        _labelForVendor(selected.vendorId),
        _labelForBranch(selected.branchId),
        _labelForWarehouse(selected.warehouseId),
        selected.status,
        selected.grandTotal,
      ].join('\t'),
    );
    if (!mounted) return;
    NotificationService.show(
      context,
      'Purchase order row copied.',
      kind: AppNotificationKind.success,
    );
  }

  String _labelForVendor(String id) => _vendors
      .firstWhere(
        (item) => item.id == id,
        orElse: () => const Vendor(
          id: '',
          firmId: '',
          code: '',
          name: '',
          legalName: '',
          displayName: '',
          categoryId: '',
          typeId: '',
          status: '',
          businessProfileId: '',
          gstRegistration: false,
          gstin: '',
          pan: '',
          licenseNumber: '',
          registrationNumber: '',
          website: '',
          email: '',
          phone: '',
          mobile: '',
          remarks: '',
          businessAttributes: {},
          createdAt: '',
          updatedAt: '',
          isDeleted: false,
          contacts: [],
          addresses: [],
        ),
      )
      .displayName
      .ifEmpty(id);

  String _labelForBranch(String id) => _branches
      .firstWhere(
        (item) => item.id == id,
        orElse: () => const BranchRecord(
          id: '',
          firmId: '',
          code: '',
          name: '',
          displayName: '',
          description: '',
          branchTypeId: '',
          branchManagerId: '',
          businessProfileId: '',
          email: '',
          phone: '',
          mobile: '',
          cityId: '',
          stateId: '',
          countryId: '',
          currencyCode: '',
          status: '',
          isDefault: false,
          isDeleted: false,
          warehouseCount: 0,
          createdAt: '',
        ),
      )
      .displayName
      .ifEmpty(id);

  String _labelForWarehouse(String id) => _warehouses
      .firstWhere(
        (item) => item.id == id,
        orElse: () => const WarehouseRecord(
          id: '',
          firmId: '',
          branchId: '',
          code: '',
          name: '',
          displayName: '',
          warehouseTypeId: '',
          businessProfileId: '',
          capacity: '',
          capacityUnit: '',
          status: '',
          isDefault: false,
          temperatureControlled: false,
          coldStorage: false,
          hazardousStorage: false,
          isDeleted: false,
          createdAt: '',
        ),
      )
      .displayName
      .ifEmpty(id);

  String _labelForBuyer(String id) => _buyers
      .firstWhere(
        (item) => item.id == id,
        orElse: () => const PlatformUser(
          id: '',
          email: '',
          fullName: '',
          isActive: true,
          forcePasswordChange: false,
          expiresAt: '',
        ),
      )
      .fullName
      .ifEmpty(id);



  List<PurchaseOrder> get _dashboardRecentOrders => _orders.take(5).toList();

  List<_VendorSpend> get _topVendors {
    final Map<String, double> totals = <String, double>{};
    for (final PurchaseOrder item in _orders) {
      totals.update(
        item.vendorId,
        (value) => value + _parseNumber(item.grandTotal),
        ifAbsent: () => _parseNumber(item.grandTotal),
      );
    }
    final List<_VendorSpend> values = totals.entries
        .map((entry) => _VendorSpend(entry.key, entry.value))
        .toList();
    values.sort((a, b) => b.total.compareTo(a.total));
    return values.take(5).toList();
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
        title: 'Purchase workspace unavailable',
        message: _error!,
        action: FilledButton.icon(
          onPressed: _load,
          icon: const Icon(Icons.refresh),
          label: const Text('Retry'),
        ),
      );
    }
    return WorkspaceShortcuts(
      bindings: WorkspaceShortcutBindings(
        create:
            _canCreate ? () => _openEditor(PurchaseDialogMode.create) : null,
        focusSearch: () => _searchFocus.requestFocus(),
        refresh: _loading ? null : _load,
        delete: _canDelete ? _deleteSelected : null,
        globalSearch: widget.onOpenGlobalSearch,
        edit: _canUpdate && (_selected?.isEditable ?? false)
            ? () => _openEditor(PurchaseDialogMode.edit, _selected)
            : null,
        export: _canExport ? _openExport : null,
        copyRow: _selected != null ? _copySelectedRow : null,
        cancel: () => Navigator.of(context, rootNavigator: true).maybePop(),
      ),
      child: switch (widget.section) {
        PurchaseSection.dashboard => _buildDashboard(),
        PurchaseSection.analytics => _buildPlaceholderSection(),
        PurchaseSection.settings => _buildSettings(),
        _ => _buildGridWorkspace(),
      },
    );
  }

  Widget _buildDashboard() {
    final PurchaseSummaryRecord summary = _summary ??
        const PurchaseSummaryRecord(
          total: 0,
          draft: 0,
          open: 0,
          cancelled: 0,
          closed: 0,
          totalValue: '0',
          overdueDelivery: 0,
        );
    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(24, 8, 24, 24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Wrap(
            spacing: 12,
            runSpacing: 12,
            children: [
              SummaryMetricCard(
                label: 'Draft Orders',
                value: '${summary.draft}',
                icon: Icons.edit_note_outlined,
              ),
              SummaryMetricCard(
                label: 'Open Orders',
                value: '${summary.open}',
                icon: Icons.shopping_bag_outlined,
              ),
              SummaryMetricCard(
                label: 'Orders Today',
                value:
                    '${_orders.where((item) => item.purchaseDate == _today()).length}',
                icon: Icons.today_outlined,
              ),
              SummaryMetricCard(
                label: 'Pending Delivery',
                value: '${summary.overdueDelivery}',
                icon: Icons.local_shipping_outlined,
              ),
              SummaryMetricCard(
                label: 'Cancelled',
                value: '${summary.cancelled}',
                icon: Icons.cancel_outlined,
              ),
              SummaryMetricCard(
                label: 'Closed',
                value: '${summary.closed}',
                icon: Icons.task_alt_outlined,
              ),
              SummaryMetricCard(
                label: 'Purchase Value',
                value: summary.totalValue,
                icon: Icons.currency_rupee_outlined,
              ),
            ],
          ),
          const SizedBox(height: 16),
          SizedBox(
            height: 320,
            child: Row(
              children: [
                Expanded(
                  child: QuickSummaryPanel(
                    title: 'Top Vendors',
                    lines: _topVendors
                        .map(
                          (item) => DetailLine(
                            _labelForVendor(item.vendorId),
                            item.total.toStringAsFixed(2),
                          ),
                        )
                        .toList(),
                    onView: widget.onNavigateToSection == null
                        ? null
                        : () => widget.onNavigateToSection!(
                              PurchaseSection.purchaseOrders,
                            ),
                  ),
                ),
                const SizedBox(width: 16),
                Expanded(
                  child: QuickSummaryPanel(
                    title: 'Recent Orders',
                    lines: _dashboardRecentOrders
                        .map(
                          (item) => DetailLine(
                            item.poNumber,
                            '${_labelForVendor(item.vendorId)} • ${item.grandTotal}',
                          ),
                        )
                        .toList(),
                    onView: widget.onNavigateToSection == null
                        ? null
                        : () => widget.onNavigateToSection!(
                              PurchaseSection.purchaseOrders,
                            ),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          SizedBox(
            height: 420,
            child: _buildOrdersGrid(showStatusOnly: false),
          ),
        ],
      ),
    );
  }

  Widget _buildGridWorkspace() => ManagementWorkspaceLayout(
        toolbar: _buildToolbar(),
        searchPanel: _buildSearchPanel(),
        filterPanel: _buildFilterPanel(),
        viewBar: widget.section == PurchaseSection.purchaseOrders
            ? _buildViewBar()
            : null,
        primaryContent: _loading
            ? const Center(child: CircularProgressIndicator())
            : _orders.isEmpty
                ? StandardEmptyState(
                    type: _search.text.trim().isEmpty && _activeFilterCount == 0
                        ? EmptyStateType.noRecords
                        : EmptyStateType.noSearchResults,
                  )
                : _buildOrdersGrid(),
        // No details panel. It repeated columns the grid already shows and
        // took a third of the width to do it, squeezing a fifteen-column
        // table. Double-click a row for the full document instead.
        statusBar: WorkspaceStatusBar(
          total: _total,
          selected: _selected != null || _selectedIds.isNotEmpty,
          selectedCount: _selectedIds.isNotEmpty ? _selectedIds.length : null,
          message: _statusBarMessage,
        ),
      );

  /// The status bar: All / Draft / Open / Cancelled / Closed / History.
  ///
  /// Scrollable because six segments do not fit a narrow window, and a
  /// segmented button clips rather than wraps.
  Widget _buildViewBar() => SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: SegmentedButton<PurchaseOrderView>(
          segments: [
            for (final PurchaseOrderView view in PurchaseOrderView.values)
              ButtonSegment<PurchaseOrderView>(
                value: view,
                label: Text(view.label),
              ),
          ],
          selected: <PurchaseOrderView>{_view},
          onSelectionChanged:
              _loading ? null : (selection) => _selectView(selection.first),
          showSelectedIcon: false,
        ),
      );

  Widget _buildPlaceholderSection() {
    final String label = switch (widget.section) {
      PurchaseSection.analytics => 'Analytics',
      _ => 'Workspace',
    };
    return WorkspaceEmptyState(
      title: '$label ready for backend extension',
      message:
          'This desktop workspace is wired into purchase management, but the current backend does not yet expose $label APIs. The shell keeps the section available as the Phase 17B extension point.',
      action: widget.onNavigateToSection == null
          ? null
          : FilledButton.tonalIcon(
              onPressed: () => widget.onNavigateToSection!(
                PurchaseSection.purchaseOrders,
              ),
              icon: const Icon(Icons.shopping_cart_outlined),
              label: const Text('Open Purchase Orders'),
            ),
    );
  }

  Widget _buildSettings() => Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const SectionHeader(
              title: 'Purchase workspace settings',
              description:
                  'Manage saved views, grid columns, and enterprise workspace defaults.',
            ),
            const SizedBox(height: 16),
            Card(
              child: ListTile(
                leading: const Icon(Icons.view_column_outlined),
                title: const Text('Column chooser'),
                subtitle: const Text(
                  'Show or hide purchase grid columns and save the layout as a reusable view.',
                ),
                trailing: FilledButton.tonal(
                  onPressed: _openColumnChooser,
                  child: const Text('Configure'),
                ),
              ),
            ),
            const SizedBox(height: 12),
            Expanded(
              child: Card(
                clipBehavior: Clip.antiAlias,
                child: _savedViews.isEmpty
                    ? const Center(
                        child: Text('No saved purchase views.'),
                      )
                    : ListView.separated(
                        itemCount: _savedViews.length,
                        separatorBuilder: (_, __) => const Divider(height: 1),
                        itemBuilder: (context, index) {
                          final _PurchaseSavedView view = _savedViews[index];
                          return ListTile(
                            title: Text(view.name),
                            subtitle: Text(
                              view.visibleColumns.entries
                                  .where((entry) => entry.value)
                                  .map((entry) => entry.key)
                                  .join(', '),
                            ),
                            trailing: Wrap(
                              spacing: 8,
                              children: [
                                OutlinedButton(
                                  onPressed: () => _applySavedView(view),
                                  child: const Text('Apply'),
                                ),
                                IconButton(
                                  tooltip: 'Remove view',
                                  onPressed: () async {
                                    setState(() {
                                      _savedViews = _savedViews
                                          .where(
                                              (item) => item.name != view.name)
                                          .toList();
                                    });
                                    await _persistPreferences();
                                  },
                                  icon: const Icon(Icons.delete_outline),
                                ),
                              ],
                            ),
                          );
                        },
                      ),
              ),
            ),
          ],
        ),
      );

  /// Send the selected draft for approval.
  Future<void> _submitSelected(PurchaseOrder order) async {
    await _runOrderAction(
      () => widget.api.submitPurchaseOrder(order.id),
      done: '${order.poNumber} submitted for approval.',
    );
  }

  /// Approve the selected submitted order.
  ///
  /// Takes `PURCHASE_APPROVE`, which `SALES_MANAGER`-style roles hold and the
  /// raiser may not — the point of the two steps is that the person who
  /// raises an order need not be the person who commits the firm to it.
  Future<void> _approveSelected(PurchaseOrder order) async {
    await _runOrderAction(
      () => widget.api.approvePurchaseOrder(order.id),
      done: '${order.poNumber} approved.',
    );
  }

  Future<void> _runOrderAction(
    Future<PurchaseOrder> Function() action, {
    required String done,
  }) async {
    try {
      await action();
      if (!mounted) return;
      NotificationService.show(context, done,
          kind: AppNotificationKind.success);
      await _load();
    } on ApiException catch (exception) {
      if (!mounted) return;
      NotificationService.show(context, exception.message,
          kind: AppNotificationKind.error);
    }
  }

  Widget _buildToolbar() {
    final PurchaseOrder? selected = _selected;
    // Mirrors `PurchaseService._assert_order_editable`: a received, cancelled
    // or closed order refuses an edit, so the button must not offer one.
    final bool canEditSelected =
        selected != null && selected.isEditable && _canUpdate;
    final bool canDeleteSelected =
        (_selectedIds.isNotEmpty || selected != null) &&
            !(_selected?.isDeleted ?? false) &&
            _canDelete;
    final bool canRestoreSelected =
        selected != null && selected.isDeleted && _canRestore;
    // A purchase order is raised, sent for approval, then approved. Until
    // 2026-08-16 nothing performed those steps: the status was whatever the
    // creator typed, so SUBMITTED could not be reached and the Open Orders
    // tab was empty for every firm.
    final bool canSubmitSelected =
        selected != null && !selected.isDeleted && selected.isDraft && _canUpdate;
    final bool canApproveSelected = selected != null &&
        !selected.isDeleted &&
        selected.isSubmitted &&
        _canApprove;
    return Wrap(
      spacing: 6,
      runSpacing: 6,
      children: [
        FilledButton.icon(
          onPressed:
              _canCreate ? () => _openEditor(PurchaseDialogMode.create) : null,
          icon: const Icon(Icons.add),
          label: const Text('New'),
        ),
        if (canSubmitSelected)
          FilledButton.tonalIcon(
            onPressed: () => unawaited(_submitSelected(selected)),
            icon: const Icon(Icons.outbox_outlined),
            label: const Text('Submit'),
          ),
        if (canApproveSelected)
          FilledButton.tonalIcon(
            onPressed: () => unawaited(_approveSelected(selected)),
            icon: const Icon(Icons.check_circle_outline),
            label: const Text('Approve'),
          ),
        IconButton(
          tooltip: 'View',
          onPressed: selected == null
              ? null
              : () => _openEditor(PurchaseDialogMode.view, selected),
          icon: const Icon(Icons.visibility_outlined),
        ),
        IconButton(
          tooltip: 'Edit',
          onPressed: canEditSelected
              ? () => _openEditor(PurchaseDialogMode.edit, selected)
              : null,
          icon: const Icon(Icons.edit_outlined),
        ),
        IconButton(
          tooltip: 'Duplicate',
          onPressed: selected == null || !_canCreate
              ? null
              : () => _openEditor(PurchaseDialogMode.duplicate, selected),
          icon: const Icon(Icons.copy_outlined),
        ),
        IconButton(
          tooltip: 'Delete',
          onPressed: canDeleteSelected ? _deleteSelected : null,
          icon: const Icon(Icons.delete_outline),
        ),
        IconButton(
          tooltip: 'Restore',
          onPressed: canRestoreSelected ? _restoreSelected : null,
          icon: const Icon(Icons.restore_from_trash_outlined),
        ),
        IconButton(
          tooltip: 'Cancel',
          onPressed: selected == null ||
                  !_canCancel ||
                  selected.isDeleted ||
                  selected.status == 'CANCELLED' ||
                  selected.status == 'CLOSED'
              ? null
              : () => _requestStatusAction(
                    title: 'Cancel purchase order',
                    action: (reason) => widget.api
                        .cancelPurchaseOrder(selected.id, reason: reason),
                    successMessage: 'Purchase order cancelled.',
                  ),
          icon: const Icon(Icons.cancel_outlined),
        ),
        IconButton(
          tooltip: 'Close',
          onPressed: selected == null ||
                  !_canApprove ||
                  selected.isDeleted ||
                  selected.status == 'CANCELLED' ||
                  selected.status == 'CLOSED'
              ? null
              : () => _requestStatusAction(
                    title: 'Close purchase order',
                    action: (reason) => widget.api
                        .closePurchaseOrder(selected.id, reason: reason),
                    successMessage: 'Purchase order closed.',
                  ),
          icon: const Icon(Icons.task_alt_outlined),
        ),
        IconButton(
          tooltip: 'Import',
          onPressed: _canImport ? _openImportWizard : null,
          icon: const Icon(Icons.file_upload_outlined),
        ),
        IconButton(
          tooltip: 'Export',
          onPressed: _canExport && _orders.isNotEmpty ? _openExport : null,
          icon: const Icon(Icons.file_download_outlined),
        ),
        IconButton(
          tooltip: 'Refresh',
          onPressed: _loading ? null : _load,
          icon: const Icon(Icons.refresh),
        ),
        IconButton(
          tooltip: 'Print',
          onPressed: () {
            NotificationService.show(
              context,
              'Print is reserved for the next transactional phase.',
            );
          },
          icon: const Icon(Icons.print_outlined),
        ),
        IconButton(
          tooltip: 'Saved views',
          onPressed: _savedViews.isEmpty
              ? null
              : () async {
                  final _PurchaseSavedView? view =
                      await showMenu<_PurchaseSavedView>(
                    context: context,
                    position: const RelativeRect.fromLTRB(100, 100, 0, 0),
                    items: _savedViews
                        .map(
                          (item) => PopupMenuItem<_PurchaseSavedView>(
                            value: item,
                            child: Text(item.name),
                          ),
                        )
                        .toList(),
                  );
                  if (view != null) {
                    _applySavedView(view);
                  }
                },
          icon: const Icon(Icons.grid_view_outlined),
        ),
        IconButton(
          tooltip: 'Column chooser',
          onPressed: _openColumnChooser,
          icon: const Icon(Icons.view_column_outlined),
        ),
      ],
    );
  }

  Widget _buildSearchPanel() => SearchFilterPanel(
        controller: _search,
        focusNode: _searchFocus,
        hintText: 'Search PO number, remarks, vendor notes, or reference',
        onSearch: _runSearch,
        filters: [
          if (_recentSearches.isNotEmpty)
            PopupMenuButton<String>(
              tooltip: 'Recent searches',
              onSelected: (value) {
                _search.text = value;
                _runSearch(value);
              },
              itemBuilder: (_) => _recentSearches
                  .map(
                    (entry) => PopupMenuItem<String>(
                      value: entry,
                      child: Text(entry),
                    ),
                  )
                  .toList(),
              child: const Icon(Icons.history),
            ),
          PopupMenuButton<String>(
            tooltip: 'Saved searches',
            onSelected: (value) {
              _search.text = value;
              _runSearch(value);
            },
            itemBuilder: (_) => _savedSearches.isEmpty
                ? const [
                    PopupMenuItem<String>(
                      enabled: false,
                      child: Text('No saved searches'),
                    ),
                  ]
                : _savedSearches
                    .map(
                      (entry) => PopupMenuItem<String>(
                        value: entry,
                        child: Text(entry),
                      ),
                    )
                    .toList(),
            child: const Icon(Icons.bookmark_outline),
          ),
          IconButton(
            tooltip: 'Save search',
            onPressed: _saveSearch,
            icon: const Icon(Icons.bookmark_add_outlined),
          ),
          IconButton(
            tooltip: 'Advanced filters',
            onPressed: () => setState(() => _filtersExpanded = true),
            icon: const Icon(Icons.filter_alt_outlined),
          ),
        ],
      );

  Widget _buildFilterPanel() => Padding(
        padding: const EdgeInsets.symmetric(horizontal: 24),
        child: FilterPanel(
          expanded: _filtersExpanded,
          activeFilterCount: _activeFilterCount,
          onExpandedChanged: (value) =>
              setState(() => _filtersExpanded = value),
          onClear: () {
            setState(() {
              _vendorId = null;
              _status = null;
              _branchId = null;
              _warehouseId = null;
              _buyerId = null;
              _purchaseType = null;
              _includeDeleted = false;
              _createdFrom.clear();
              _createdTo.clear();
            });
            _load(requestedPage: 1);
          },
          onApply: () => _load(requestedPage: 1),
          children: [
            _buildOptionField(
              label: 'Vendor',
              value: _vendorId,
              items: _vendors
                  .map((item) => DropdownMenuItem<String>(
                        value: item.id,
                        child: Text(item.displayName.ifEmpty(item.name)),
                      ))
                  .toList(),
              onChanged: (value) => setState(() => _vendorId = value),
            ),
            _buildOptionField(
              label: 'Status',
              value: _status,
              items: _purchaseStatuses
                  .map(
                    (item) => DropdownMenuItem<String>(
                      value: item,
                      child: Text(item.replaceAll('_', ' ')),
                    ),
                  )
                  .toList(),
              onChanged: (value) => setState(() => _status = value),
            ),
            _buildOptionField(
              label: 'Branch',
              value: _branchId,
              items: _branches
                  .map((item) => DropdownMenuItem<String>(
                        value: item.id,
                        child: Text(item.displayName.ifEmpty(item.name)),
                      ))
                  .toList(),
              onChanged: (value) => setState(() => _branchId = value),
            ),
            _buildOptionField(
              label: 'Warehouse',
              value: _warehouseId,
              items: _warehouses
                  .map((item) => DropdownMenuItem<String>(
                        value: item.id,
                        child: Text(item.displayName.ifEmpty(item.name)),
                      ))
                  .toList(),
              onChanged: (value) => setState(() => _warehouseId = value),
            ),
            _buildOptionField(
              label: 'Buyer',
              value: _buyerId,
              items: _buyers
                  .map((item) => DropdownMenuItem<String>(
                        value: item.id,
                        child: Text(item.fullName.ifEmpty(item.email)),
                      ))
                  .toList(),
              onChanged: (value) => setState(() => _buyerId = value),
            ),
            _buildOptionField(
              label: 'Purchase Type',
              value: _purchaseType,
              items: _purchaseTypes
                  .map(
                    (item) => DropdownMenuItem<String>(
                      value: item,
                      child: Text(item.replaceAll('_', ' ')),
                    ),
                  )
                  .toList(),
              onChanged: (value) => setState(() => _purchaseType = value),
            ),
            _buildTextField(_createdFrom, 'Created From (YYYY-MM-DD)'),
            _buildTextField(_createdTo, 'Created To (YYYY-MM-DD)'),
            SizedBox(
              width: 240,
              child: SwitchListTile(
                dense: true,
                contentPadding: EdgeInsets.zero,
                title: const Text('Include deleted'),
                value: _includeDeleted,
                onChanged: (value) => setState(() => _includeDeleted = value),
              ),
            ),
          ],
        ),
      );

  Widget _buildOrdersGrid({bool showStatusOnly = true}) {
    final List<GridColumn> columns = [
      GridColumn(
        key: 'po',
        label: 'PO Number',
        visible: _visibleColumns['po'] ?? true,
      ),
      GridColumn(
        key: 'vendor',
        label: 'Vendor',
        visible: _visibleColumns['vendor'] ?? true,
      ),
      GridColumn(
        key: 'branch',
        label: 'Branch',
        visible: _visibleColumns['branch'] ?? true,
      ),
      GridColumn(
        key: 'warehouse',
        label: 'Warehouse',
        visible: _visibleColumns['warehouse'] ?? true,
      ),
      GridColumn(
        key: 'buyer',
        label: 'Buyer',
        visible: _visibleColumns['buyer'] ?? true,
      ),
      GridColumn(
        key: 'date',
        label: 'Purchase Date',
        visible: _visibleColumns['date'] ?? true,
      ),
      GridColumn(
        key: 'delivery',
        label: 'Expected Delivery',
        visible: _visibleColumns['delivery'] ?? true,
      ),
      GridColumn(
        key: 'type',
        label: 'Purchase Type',
        visible: _visibleColumns['type'] ?? true,
      ),
      GridColumn(
        key: 'priority',
        label: 'Priority',
        visible: _visibleColumns['priority'] ?? true,
      ),
      GridColumn(
        key: 'status',
        label: 'Status',
        visible: _visibleColumns['status'] ?? true,
      ),
      GridColumn(
        key: 'total',
        label: 'Grand Total',
        visible: _visibleColumns['total'] ?? true,
      ),
    ];
    return EnterpriseDataGrid<PurchaseOrder>(
      items: _orders,
      total: _total,
      pageOffset: (_page - 1) * _rowsPerPage,
      rowsPerPage: _rowsPerPage,
      showRowNumbers: true,
      columns: columns,
      id: (item) => item.id,
      selectedId: _selected?.id,
      selectedIds: _selectedIds,
      onSelectionChanged: (value) => setState(() => _selectedIds = value),
      cells: (item) => [
        item.poNumber,
        _labelForVendor(item.vendorId),
        _labelForBranch(item.branchId),
        _labelForWarehouse(item.warehouseId),
        _labelForBuyer(item.buyerId),
        item.purchaseDate,
        item.expectedDeliveryDate,
        item.purchaseType.replaceAll('_', ' '),
        item.priority,
        item.status,
        item.grandTotal,
      ],
      onSelect: _selectOrder,
      onOpen: (item) => _openEditor(PurchaseDialogMode.view, item),
      onPageChanged: (offset) {
        final int next = offset ~/ _rowsPerPage + 1;
        if (next != _page) {
          _load(requestedPage: next);
        }
      },
      contextActionsFor: (item) => [
        WorkspaceContextAction.view,
        if (_canUpdate && !item.isDeleted) WorkspaceContextAction.edit,
        if (_canDelete && !item.isDeleted) WorkspaceContextAction.delete,
        if (_canRestore && item.isDeleted) WorkspaceContextAction.restore,
        WorkspaceContextAction.copy,
      ],
      onContextAction: (action, item) {
        switch (action) {
          case WorkspaceContextAction.view:
            _openEditor(PurchaseDialogMode.view, item);
            break;
          case WorkspaceContextAction.edit:
            _openEditor(PurchaseDialogMode.edit, item);
            break;
          case WorkspaceContextAction.delete:
            setState(() {
              _selected = item;
              _selectedIds = <String>{item.id};
            });
            _deleteSelected();
            break;
          case WorkspaceContextAction.restore:
            setState(() => _selected = item);
            _restoreSelected();
            break;
          case WorkspaceContextAction.copy:
            setState(() => _selected = item);
            _copySelectedRow();
            break;
          case WorkspaceContextAction.refresh:
          case WorkspaceContextAction.export:
            break;
        }
      },
      cellBuilder: (columnIndex, value, item) {
        if (showStatusOnly && columns[columnIndex].key == 'status') {
          return Align(
            alignment: Alignment.centerLeft,
            child: _purchaseStatusBadge(item.status),
          );
        }
        if (!showStatusOnly && columns[columnIndex].key == 'status') {
          return _purchaseStatusBadge(item.status);
        }
        if (columns[columnIndex].key == 'priority') {
          return StatusBadge(
            label: value,
            tone: value == 'HIGH' || value == 'URGENT'
                ? StatusBadgeTone.warning
                : StatusBadgeTone.neutral,
          );
        }
        return Tooltip(
          message: value,
          child: SizedBox(
            width: double.infinity,
            child: Text(value, overflow: TextOverflow.ellipsis),
          ),
        );
      },
    );
  }

  Widget _purchaseStatusBadge(String status) {
    final StatusBadgeTone tone = switch (status.toUpperCase()) {
      'DRAFT' => StatusBadgeTone.warning,
      'SUBMITTED' ||
      'APPROVED' ||
      'ORDERED' ||
      'RECEIVED' =>
        StatusBadgeTone.success,
      'PARTIALLY_ORDERED' || 'PARTIALLY_RECEIVED' => StatusBadgeTone.info,
      'CANCELLED' || 'CLOSED' => StatusBadgeTone.danger,
      _ => StatusBadgeTone.neutral,
    };
    return StatusBadge(label: status.replaceAll('_', ' '), tone: tone);
  }

  int get _activeFilterCount => [
        _vendorId,
        _status,
        _branchId,
        _warehouseId,
        _buyerId,
        _purchaseType,
        if (_createdFrom.text.trim().isNotEmpty) _createdFrom.text.trim(),
        if (_createdTo.text.trim().isNotEmpty) _createdTo.text.trim(),
        if (_includeDeleted) 'deleted',
      ].where((value) => value != null && value.toString().isNotEmpty).length;

  String get _statusBarMessage {
    if (widget.section != PurchaseSection.purchaseOrders) {
      return 'Purchase workspace';
    }
    return switch (_view) {
      PurchaseOrderView.all => 'Showing all purchase orders',
      PurchaseOrderView.draft => 'Showing draft orders',
      // Named for what it filters rather than for the segment: the Dashboard's
      // "Open Orders" card counts five statuses, and the list endpoint takes
      // one, so the two figures do not agree. Saying SUBMITTED here is the
      // only honest thing this screen can do until the API accepts a set.
      PurchaseOrderView.open => 'Showing orders awaiting approval (SUBMITTED)',
      PurchaseOrderView.cancelled => 'Showing cancelled orders',
      PurchaseOrderView.closed => 'Showing closed orders',
      PurchaseOrderView.history => 'Showing every order, oldest document first',
    };
  }

  Widget _buildOptionField({
    required String label,
    required String? value,
    required List<DropdownMenuItem<String>> items,
    required ValueChanged<String?> onChanged,
  }) =>
      SizedBox(
        width: 240,
        child: DropdownButtonFormField<String>(
          initialValue: value?.isNotEmpty == true ? value : '',
          decoration: InputDecoration(labelText: label),
          items: [
            const DropdownMenuItem<String>(value: '', child: Text('All')),
            ...items,
          ],
          onChanged: (next) =>
              onChanged(next == null || next.isEmpty ? null : next),
        ),
      );

  Widget _buildTextField(TextEditingController controller, String label) =>
      SizedBox(
        width: 240,
        child: TextField(
          controller: controller,
          decoration: InputDecoration(labelText: label),
        ),
      );

  static const List<String> _purchaseStatuses = <String>[
    'DRAFT',
    'SUBMITTED',
    'APPROVED',
    'PARTIALLY_ORDERED',
    'ORDERED',
    'PARTIALLY_RECEIVED',
    'RECEIVED',
    'CANCELLED',
    'CLOSED',
  ];

  static const List<String> _purchaseTypes = <String>[
    'STANDARD_PURCHASE',
    'LOCAL_PURCHASE',
    'IMPORT_PURCHASE',
    'CONSIGNMENT',
    'INTER_BRANCH',
    'INTER_COMPANY',
    'CAPITAL_GOODS',
    'SERVICES',
  ];
}

/// What the editor dialog hands back when it closes.
///
/// A save and a lifecycle action both have to reload the grid -- otherwise the
/// row behind an approved order still reads DRAFT -- but only one of them
/// edited the document, and the workspace announces "created"/"updated" on
/// anything it gets back. `saved` is what keeps that message honest.
class PurchaseEditorOutcome {
  const PurchaseEditorOutcome({required this.order, required this.saved});

  final PurchaseOrder order;

  /// True when the document itself was written; false when only its status
  /// moved.
  final bool saved;
}

class PurchaseOrderEditorDialog extends StatefulWidget {
  const PurchaseOrderEditorDialog({
    super.key,
    required this.api,
    required this.mode,
    required this.order,
    required this.vendors,
    required this.branches,
    required this.warehouses,
    required this.products,
    required this.buyers,
    required this.taxProfiles,
    required this.storageNodes,
    required this.canSubmit,
    required this.canApprove,
  });

  final ApiClient api;
  final PurchaseDialogMode mode;
  final PurchaseOrder? order;
  final List<Vendor> vendors;
  final List<BranchRecord> branches;
  final List<WarehouseRecord> warehouses;
  final List<Product> products;
  final List<PlatformUser> buyers;
  final List<TaxProfileRecord> taxProfiles;
  final List<StorageNodeRecord> storageNodes;

  /// Whether this user may send a draft for approval
  /// (`PURCHASE_UPDATE`).
  final bool canSubmit;

  /// Whether this user may approve a submitted order
  /// (`PURCHASE_APPROVE`).
  final bool canApprove;

  bool get isReadOnly => mode == PurchaseDialogMode.view;
  bool get isCreating =>
      mode == PurchaseDialogMode.create ||
      mode == PurchaseDialogMode.duplicate;

  @override
  State<PurchaseOrderEditorDialog> createState() =>
      _PurchaseOrderEditorDialogState();
}

class _PurchaseOrderEditorDialogState extends State<PurchaseOrderEditorDialog> {
  late PurchaseOrder _draft = widget.mode == PurchaseDialogMode.duplicate
      ? _duplicateDraft(widget.order!)
      : (widget.order ?? _blankOrder());
  bool _saving = false;
  String? _error;

  /// True once a lifecycle action moved this document, so the grid behind is
  /// out of date even though nothing was edited.
  bool _acted = false;

  /// Held in state rather than built in `build`. It used to be constructed
  /// inline in the `FutureBuilder`, which re-issued the request on every
  /// rebuild -- every keystroke while editing -- and left no way to refresh it
  /// on purpose once an action had added an entry.
  Future<List<PurchaseOrderHistoryRecord>>? _historyFuture;

  @override
  void initState() {
    super.initState();
    _historyFuture = _loadHistory();
  }

  Future<List<PurchaseOrderHistoryRecord>>? _loadHistory() =>
      _draft.id.isEmpty ? null : widget.api.purchaseOrderHistory(_draft.id);

  PurchaseOrder _blankOrder() => PurchaseOrder(
        id: '',
        firmId: '',
        branchId: widget.branches.firstOrNull?.id ?? '',
        warehouseId: widget.warehouses.firstOrNull?.id ?? '',
        vendorId: widget.vendors.firstOrNull?.id ?? '',
        buyerId: widget.buyers.firstOrNull?.id ?? '',
        taxProfileId: '',
        poNumber: '',
        vendorContact: '',
        vendorAddress: '',
        department: '',
        purchaseType: 'STANDARD_PURCHASE',
        purchaseCategory: '',
        purchaseDate: _today(),
        expectedDeliveryDate: '',
        paymentTerms: '',
        deliveryTerms: '',
        currencyCode: '',
        exchangeRate: '',
        referenceNumber: '',
        externalReference: '',
        priority: 'NORMAL',
        remarks: '',
        status: 'DRAFT',
        subtotal: '0',
        lineDiscountTotal: '0',
        headerDiscountAmount: '0',
        taxTotal: '0',
        additionalCharges: '0',
        roundOff: '0',
        grandTotal: '0',
        closeReason: '',
        cancelReason: '',
        isDeleted: false,
        createdAt: '',
        updatedAt: '',
        lines: [
          PurchaseOrderLine(
            id: '',
            lineNumber: 1,
            productId: widget.products.firstOrNull?.id ?? '',
            description: '',
            vendorProductCode: '',
            purchaseUomId: '',
            inventoryUomId: '',
            conversionFactor: '1',
            conversionVersion: null,
            orderedQuantity: '1',
            freeQuantity: '0',
            baseQuantity: '1',
            unitPrice: '0',
            discountPercent: '0',
            discountAmount: '0',
            grossAmount: '0',
            taxProfileId: '',
            taxAmount: '0',
            netAmount: '0',
            batchRequired: false,
            expiryRequired: false,
            serialRequired: false,
            manufacturingDate: '',
            expiryDate: '',
            warehouseId: '',
            storageNodeId: '',
            remarks: '',
            status: 'ACTIVE',
            createdAt: '',
            updatedAt: '',
          ),
        ],
        deliverySchedules: const [],
        attachments: const [],
        notes: const [],
      );

  PurchaseOrder _duplicateDraft(PurchaseOrder source) => source.copyWith(
        id: '',
        poNumber: '',
        status: 'DRAFT',
        lines: source.lines
            .asMap()
            .entries
            .map(
              (entry) => entry.value.copyWith(
                id: '',
                lineNumber: entry.key + 1,
              ),
            )
            .toList(),
        deliverySchedules: source.deliverySchedules
            .map((item) => item.copyWith(id: ''))
            .toList(),
        attachments:
            source.attachments.map((item) => item.copyWith(id: '')).toList(),
        notes: source.notes.map((item) => item.copyWith(id: '')).toList(),
      );

  @override
  Widget build(BuildContext context) {
    final Size window = MediaQuery.sizeOf(context);
    return Dialog(
      insetPadding: const EdgeInsets.all(24),
      clipBehavior: Clip.antiAlias,
      child: SizedBox(
        width: window.width * .88,
        height: window.height * .88,
        child: CallbackShortcuts(
          bindings: {
            const SingleActivator(LogicalKeyboardKey.escape): _close,
            if (!widget.isReadOnly)
              const SingleActivator(LogicalKeyboardKey.keyS, control: true):
                  _save,
          },
          child: Focus(
            autofocus: true,
            child: Column(
              children: [
                _DialogHeader(
                  title: switch (widget.mode) {
                    PurchaseDialogMode.create => 'New Purchase Order',
                    PurchaseDialogMode.view => 'Purchase Order',
                    PurchaseDialogMode.edit => 'Edit Purchase Order',
                    PurchaseDialogMode.duplicate => 'Duplicate Purchase Order',
                  },
                  subtitle: _draft.poNumber.ifEmpty('Draft workspace'),
                  onClose: _saving ? null : _close,
                ),
                if (_error != null)
                  MaterialBanner(
                    content: Text(_error!),
                    actions: [
                      TextButton(
                        onPressed: () => setState(() => _error = null),
                        child: const Text('Dismiss'),
                      ),
                    ],
                  ),
                Padding(
                  padding: const EdgeInsets.fromLTRB(24, 12, 24, 0),
                  child: EnterpriseDocumentToolbar(
                    onAction: _handleToolbarAction,
                    isEnabled: (action) => _toolbarActionEnabled(action),
                    // Permission decides whether the button is here at
                    // all; status decides whether it does anything. That is
                    // what "someone who can approve can see that they can"
                    // means.
                    actions: [
                      DocumentToolbarAction.save,
                      if (widget.canSubmit && !widget.isCreating)
                        DocumentToolbarAction.requestApproval,
                      if (widget.canApprove && !widget.isCreating)
                        DocumentToolbarAction.approve,
                      DocumentToolbarAction.printDocument,
                      DocumentToolbarAction.exportDocument,
                      DocumentToolbarAction.emailDocument,
                      DocumentToolbarAction.close,
                    ],
                  ),
                ),
                Expanded(
                  child: SingleChildScrollView(
                    padding: const EdgeInsets.all(24),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        EnterpriseDocumentHeader(
                          header: _documentHeaderSnapshot(),
                        ),
                        const SizedBox(height: 16),
                        EnterpriseApprovalPanel(
                          status: _draft.status,
                          message: _approvalMessage(),
                        ),
                        const SizedBox(height: 16),
                        const SectionHeader(
                          title: 'Document Header',
                          description:
                              'Vendor, branch, warehouse, numbering, and purchase header details.',
                        ),
                        _buildGeneralTab(),
                        const SizedBox(height: 16),
                        const SectionHeader(
                          title: 'Line Items',
                          description:
                              'Purchase lines reuse the enterprise document line framework.',
                        ),
                        _buildItemsTab(),
                        const SizedBox(height: 16),
                        const SectionHeader(
                          title: 'Delivery Information',
                          description:
                              'Expected delivery schedule and partial delivery plan.',
                        ),
                        _buildDeliveryTab(),
                        const SizedBox(height: 16),
                        const SectionHeader(
                          title: 'Charges and Taxes',
                          description:
                              'Calculated totals and tax impact for the document.',
                        ),
                        _buildTaxesTab(),
                        const SizedBox(height: 16),
                        const SectionHeader(
                          title: 'Attachments',
                          description:
                              'Document attachments are kept in the shared attachment framework.',
                        ),
                        _buildAttachmentsTab(),
                        const SizedBox(height: 16),
                        const SectionHeader(
                          title: 'Notes',
                          description:
                              'Reusable notes are captured directly on the document.',
                        ),
                        _buildNotesTab(),
                        const SizedBox(height: 16),
                        const SectionHeader(
                          title: 'History',
                          description:
                              'Lifecycle history is sourced from the enterprise document event stream.',
                        ),
                        _buildHistoryTab(),
                        const SizedBox(height: 16),
                        const SectionHeader(
                          title: 'Audit',
                          description:
                              'Audit entries are produced by the backend and kept separate from the editor.',
                        ),
                        _buildAuditTab(),
                      ],
                    ),
                  ),
                ),
                Padding(
                  padding: const EdgeInsets.fromLTRB(24, 12, 24, 24),
                  child: Row(
                    children: [
                      OutlinedButton(
                        onPressed: _saving ? null : _close,
                        child: const Text('Close'),
                      ),
                      const Spacer(),
                      if (!widget.isReadOnly)
                        FilledButton.icon(
                          onPressed: _saving ? null : _save,
                          icon: _saving
                              ? const SizedBox(
                                  width: 16,
                                  height: 16,
                                  child:
                                      CircularProgressIndicator(strokeWidth: 2),
                                )
                              : const Icon(Icons.save_outlined),
                          label: Text(_saving ? 'Saving...' : 'Save'),
                        ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildGeneralTab() => Wrap(
          spacing: 16,
          runSpacing: 16,
          children: [
            _dropdownField(
              label: 'Vendor',
              value: _draft.vendorId,
              readOnly: widget.isReadOnly,
              items: widget.vendors
                  .map((item) => DropdownMenuItem<String>(
                        value: item.id,
                        child: Text(item.displayName.ifEmpty(item.name)),
                      ))
                  .toList(),
              onChanged: (value) =>
                  setState(() => _draft = _draft.copyWith(vendorId: value)),
            ),
            _dropdownField(
              label: 'Branch',
              value: _draft.branchId,
              readOnly: widget.isReadOnly,
              items: widget.branches
                  .map((item) => DropdownMenuItem<String>(
                        value: item.id,
                        child: Text(item.displayName.ifEmpty(item.name)),
                      ))
                  .toList(),
              onChanged: (value) =>
                  setState(() => _draft = _draft.copyWith(branchId: value)),
            ),
            _dropdownField(
              label: 'Warehouse',
              value: _draft.warehouseId,
              readOnly: widget.isReadOnly,
              items: widget.warehouses
                  .map((item) => DropdownMenuItem<String>(
                        value: item.id,
                        child: Text(item.displayName.ifEmpty(item.name)),
                      ))
                  .toList(),
              onChanged: (value) =>
                  setState(() => _draft = _draft.copyWith(warehouseId: value)),
            ),
            _dropdownField(
              label: 'Buyer',
              value: _draft.buyerId,
              readOnly: widget.isReadOnly,
              items: widget.buyers
                  .map((item) => DropdownMenuItem<String>(
                        value: item.id,
                        child: Text(item.fullName.ifEmpty(item.email)),
                      ))
                  .toList(),
              onChanged: (value) =>
                  setState(() => _draft = _draft.copyWith(buyerId: value)),
            ),
            _dropdownField(
              label: 'Purchase Type',
              value: _draft.purchaseType,
              readOnly: widget.isReadOnly,
              items: _PurchaseManagementPageState._purchaseTypes
                  .map((item) => DropdownMenuItem<String>(
                        value: item,
                        child: Text(item.replaceAll('_', ' ')),
                      ))
                  .toList(),
              onChanged: (value) =>
                  setState(() => _draft = _draft.copyWith(purchaseType: value)),
            ),
            _textField(
              label: 'Reference Number',
              value: _draft.referenceNumber,
              readOnly: widget.isReadOnly,
              onChanged: (value) => setState(
                  () => _draft = _draft.copyWith(referenceNumber: value)),
            ),
            _textField(
              label: 'Purchase Date',
              value: _draft.purchaseDate,
              readOnly: widget.isReadOnly,
              onChanged: (value) =>
                  setState(() => _draft = _draft.copyWith(purchaseDate: value)),
            ),
            _textField(
              label: 'Expected Delivery',
              value: _draft.expectedDeliveryDate,
              readOnly: widget.isReadOnly,
              onChanged: (value) => setState(
                () => _draft = _draft.copyWith(expectedDeliveryDate: value),
              ),
            ),
            _dropdownField(
              label: 'Priority',
              value: _draft.priority,
              readOnly: widget.isReadOnly,
              items: const [
                DropdownMenuItem(value: 'LOW', child: Text('LOW')),
                DropdownMenuItem(value: 'NORMAL', child: Text('NORMAL')),
                DropdownMenuItem(value: 'HIGH', child: Text('HIGH')),
                DropdownMenuItem(value: 'URGENT', child: Text('URGENT')),
              ],
              onChanged: (value) =>
                  setState(() => _draft = _draft.copyWith(priority: value)),
            ),
            _textField(
              label: 'Vendor Contact',
              value: _draft.vendorContact,
              readOnly: widget.isReadOnly,
              onChanged: (value) => setState(
                  () => _draft = _draft.copyWith(vendorContact: value)),
            ),
            _textField(
              label: 'Vendor Address',
              value: _draft.vendorAddress,
              readOnly: widget.isReadOnly,
              maxLines: 3,
              onChanged: (value) => setState(
                  () => _draft = _draft.copyWith(vendorAddress: value)),
            ),
            _textField(
              label: 'Remarks',
              value: _draft.remarks,
              readOnly: widget.isReadOnly,
              maxLines: 3,
              onChanged: (value) =>
                  setState(() => _draft = _draft.copyWith(remarks: value)),
            ),
          ],
        );

  Widget _buildItemsTab() => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const SectionHeader(
                title: 'Purchase Items',
                description:
                    'Edit item-level quantity, pricing, warehouse, storage, and tax settings.',
              ),
              const Spacer(),
              if (!widget.isReadOnly)
                FilledButton.tonalIcon(
                  onPressed: _addLine,
                  icon: const Icon(Icons.add),
                  label: const Text('Add Line'),
                ),
            ],
          ),
          const SizedBox(height: 12),
          EnterpriseDocumentLines(
            lines: _documentLineSnapshots(),
            readOnly: widget.isReadOnly,
            onAddLine: widget.isReadOnly ? null : _addLine,
            onRemoveLine: widget.isReadOnly
                ? null
                : (line) {
                    final int index = _draft.lines.indexWhere(
                      (item) => item.lineNumber == line.lineNumber,
                    );
                    if (index >= 0 && _draft.lines.length > 1) {
                      _removeLine(index);
                    }
                  },
          ),
          const SizedBox(height: 16),
          ListView.separated(
            itemCount: _draft.lines.length,
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            separatorBuilder: (_, __) => const SizedBox(height: 12),
            itemBuilder: (context, index) {
                final PurchaseOrderLine line = _draft.lines[index];
                return Card(
                  clipBehavior: Clip.antiAlias,
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Text(
                              'Line ${index + 1}',
                              style: Theme.of(context).textTheme.titleMedium,
                            ),
                            const Spacer(),
                            if (!widget.isReadOnly)
                              IconButton(
                                tooltip: 'Remove line',
                                onPressed: _draft.lines.length == 1
                                    ? null
                                    : () => _removeLine(index),
                                icon: const Icon(Icons.delete_outline),
                              ),
                          ],
                        ),
                        const SizedBox(height: 12),
                        Wrap(
                          spacing: 16,
                          runSpacing: 16,
                          children: [
                            _dropdownField(
                              label: 'Product',
                              value: line.productId,
                              readOnly: widget.isReadOnly,
                              items: widget.products
                                  .map((item) => DropdownMenuItem<String>(
                                        value: item.id,
                                        child: Text(item.name),
                                      ))
                                  .toList(),
                              onChanged: (value) => _updateLine(
                                index,
                                line.copyWith(productId: value),
                              ),
                            ),
                            _textField(
                              label: 'Description',
                              value: line.description,
                              readOnly: widget.isReadOnly,
                              onChanged: (value) =>
                                  _updateLine(index, line.copyWith(description: value)),
                            ),
                            _textField(
                              label: 'Purchase UOM ID',
                              value: line.purchaseUomId,
                              readOnly: widget.isReadOnly,
                              onChanged: (value) =>
                                  _updateLine(index, line.copyWith(purchaseUomId: value)),
                            ),
                            _textField(
                              label: 'Inventory UOM ID',
                              value: line.inventoryUomId,
                              readOnly: widget.isReadOnly,
                              onChanged: (value) =>
                                  _updateLine(index, line.copyWith(inventoryUomId: value)),
                            ),
                            _textField(
                              label: 'Quantity',
                              value: line.orderedQuantity,
                              readOnly: widget.isReadOnly,
                              onChanged: (value) =>
                                  _updateLine(index, line.copyWith(orderedQuantity: value)),
                            ),
                            _textField(
                              label: 'Free Quantity',
                              value: line.freeQuantity,
                              readOnly: widget.isReadOnly,
                              onChanged: (value) =>
                                  _updateLine(index, line.copyWith(freeQuantity: value)),
                            ),
                            _textField(
                              label: 'Unit Price',
                              value: line.unitPrice,
                              readOnly: widget.isReadOnly,
                              onChanged: (value) =>
                                  _updateLine(index, line.copyWith(unitPrice: value)),
                            ),
                            _textField(
                              label: 'Discount %',
                              value: line.discountPercent,
                              readOnly: widget.isReadOnly,
                              onChanged: (value) => _updateLine(
                                index,
                                line.copyWith(discountPercent: value),
                              ),
                            ),
                            _textField(
                              label: 'Discount Amount',
                              value: line.discountAmount,
                              readOnly: widget.isReadOnly,
                              onChanged: (value) => _updateLine(
                                index,
                                line.copyWith(discountAmount: value),
                              ),
                            ),
                            _dropdownField(
                              label: 'Tax Profile',
                              value: line.taxProfileId,
                              readOnly: widget.isReadOnly,
                              items: widget.taxProfiles
                                  .map((item) => DropdownMenuItem<String>(
                                        value: item.id,
                                        child: Text(item.label.ifEmpty(item.name)),
                                      ))
                                  .toList(),
                              onChanged: (value) =>
                                  _updateLine(index, line.copyWith(taxProfileId: value)),
                            ),
                            _dropdownField(
                              label: 'Warehouse',
                              value: line.warehouseId.ifEmpty(_draft.warehouseId),
                              readOnly: widget.isReadOnly,
                              items: widget.warehouses
                                  .map((item) => DropdownMenuItem<String>(
                                        value: item.id,
                                        child: Text(item.displayName.ifEmpty(item.name)),
                                      ))
                                  .toList(),
                              onChanged: (value) =>
                                  _updateLine(index, line.copyWith(warehouseId: value)),
                            ),
                            _dropdownField(
                              label: 'Storage Area',
                              value: line.storageNodeId,
                              readOnly: widget.isReadOnly,
                              items: widget.storageNodes
                                  .where(
                                    (item) =>
                                        item.warehouseId ==
                                        line.warehouseId.ifEmpty(_draft.warehouseId),
                                  )
                                  .map((item) => DropdownMenuItem<String>(
                                        value: item.id,
                                        child: Text(item.path.ifEmpty(item.name)),
                                      ))
                                  .toList(),
                              onChanged: (value) =>
                                  _updateLine(index, line.copyWith(storageNodeId: value)),
                            ),
                            _textField(
                              label: 'Remarks',
                              value: line.remarks,
                              readOnly: widget.isReadOnly,
                              onChanged: (value) =>
                                  _updateLine(index, line.copyWith(remarks: value)),
                            ),
                          ],
                        ),
                        const SizedBox(height: 12),
                        Wrap(
                          spacing: 12,
                          children: [
                            _switchTile(
                              label: 'Batch Required',
                              value: line.batchRequired,
                              enabled: !widget.isReadOnly,
                              onChanged: (value) => _updateLine(
                                index,
                                line.copyWith(batchRequired: value),
                              ),
                            ),
                            _switchTile(
                              label: 'Expiry Required',
                              value: line.expiryRequired,
                              enabled: !widget.isReadOnly,
                              onChanged: (value) => _updateLine(
                                index,
                                line.copyWith(expiryRequired: value),
                              ),
                            ),
                            _switchTile(
                              label: 'Serial Required',
                              value: line.serialRequired,
                              enabled: !widget.isReadOnly,
                              onChanged: (value) => _updateLine(
                                index,
                                line.copyWith(serialRequired: value),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 12),
                        Wrap(
                          spacing: 24,
                          runSpacing: 8,
                          children: [
                            Text('Gross: ${line.grossAmount.ifEmpty('-')}'),
                            Text('Tax: ${line.taxAmount.ifEmpty('-')}'),
                            Text('Net: ${line.netAmount.ifEmpty('-')}'),
                            Text('Base Qty: ${line.baseQuantity.ifEmpty('-')}'),
                          ],
                        ),
                      ],
                    ),
                  ),
                );
            },
          ),
        ],
      );

  Widget _buildDeliveryTab() => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const SectionHeader(
                title: 'Delivery Schedules',
                description:
                    'Manage partial deliveries and expected arrival dates.',
              ),
              const Spacer(),
              if (!widget.isReadOnly)
                FilledButton.tonalIcon(
                  onPressed: _addSchedule,
                  icon: const Icon(Icons.add),
                  label: const Text('Add Schedule'),
                ),
            ],
          ),
          const SizedBox(height: 12),
          _draft.deliverySchedules.isEmpty
              ? const StandardEmptyState(
                  type: EmptyStateType.noRecords,
                  title: 'No delivery schedules',
                  message:
                      'Add schedule rows when the order uses staged delivery.',
                )
              : ListView.separated(
                  itemCount: _draft.deliverySchedules.length,
                  shrinkWrap: true,
                  physics: const NeverScrollableScrollPhysics(),
                  separatorBuilder: (_, __) => const SizedBox(height: 12),
                  itemBuilder: (context, index) {
                    final PurchaseDeliverySchedule schedule =
                        _draft.deliverySchedules[index];
                    return Card(
                      child: Padding(
                        padding: const EdgeInsets.all(16),
                        child: Wrap(
                          spacing: 16,
                          runSpacing: 16,
                          crossAxisAlignment: WrapCrossAlignment.center,
                          children: [
                            _textField(
                              label: 'Line Number',
                              value: '${schedule.lineNumber}',
                              readOnly: widget.isReadOnly,
                              onChanged: (value) => _updateSchedule(
                                index,
                                schedule.copyWith(
                                  lineNumber: int.tryParse(value.trim()) ??
                                      schedule.lineNumber,
                                ),
                              ),
                            ),
                            _textField(
                              label: 'Delivery Date',
                              value: schedule.deliveryDate,
                              readOnly: widget.isReadOnly,
                              onChanged: (value) =>
                                  _updateSchedule(index, schedule.copyWith(deliveryDate: value)),
                            ),
                            _textField(
                              label: 'Quantity',
                              value: schedule.quantity,
                              readOnly: widget.isReadOnly,
                              onChanged: (value) =>
                                  _updateSchedule(index, schedule.copyWith(quantity: value)),
                            ),
                            _textField(
                              label: 'Remarks',
                              value: schedule.remarks,
                              readOnly: widget.isReadOnly,
                              onChanged: (value) =>
                                  _updateSchedule(index, schedule.copyWith(remarks: value)),
                            ),
                            if (!widget.isReadOnly)
                              IconButton(
                                tooltip: 'Remove schedule',
                                onPressed: () => _removeSchedule(index),
                                icon: const Icon(Icons.delete_outline),
                              ),
                          ],
                        ),
                      ),
                    );
                  },
                ),
        ],
      );

  Widget _buildTaxesTab() => SingleChildScrollView(
        child: Card(
          clipBehavior: Clip.antiAlias,
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const SectionHeader(
                  title: 'Read-only totals',
                  description:
                      'Tax and total values are supplied by the existing backend calculation engine.',
                ),
                const SizedBox(height: 16),
                EnterpriseTotalsPanel(
                  totals: _documentTotalsSnapshot(),
                ),
                const SizedBox(height: 16),
                Wrap(
                  spacing: 24,
                  runSpacing: 16,
                  children: [
                    DetailLine('Tax Profile',
                            _labelForTaxProfile(_draft.taxProfileId))
                        .toWidget(),
                  ],
                ),
                const SizedBox(height: 20),
                for (final PurchaseOrderLine line in _draft.lines)
                  ListTile(
                    leading: const Icon(Icons.receipt_long_outlined),
                    title: Text(_labelForProduct(line.productId)),
                    subtitle: Text(
                      'Tax profile: ${_labelForTaxProfile(line.taxProfileId)} • Tax: ${line.taxAmount} • Net: ${line.netAmount}',
                    ),
                  ),
              ],
            ),
          ),
        ),
      );

  Widget _buildAttachmentsTab() => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const SectionHeader(
                title: 'Attachments',
                description:
                    'Attach quotation, vendor documents, images, PDF, and spreadsheet references.',
              ),
              const Spacer(),
              if (!widget.isReadOnly)
                FilledButton.tonalIcon(
                  onPressed: _pickAttachment,
                  icon: const Icon(Icons.attach_file),
                  label: const Text('Add Attachment'),
                ),
            ],
          ),
          const SizedBox(height: 12),
          _draft.attachments.isEmpty
              ? const StandardEmptyState(
                  type: EmptyStateType.noRecords,
                  title: 'No attachments',
                  message:
                      'Use this tab to register quotation sheets, PDFs, or vendor files with the purchase order.',
                )
              : ListView.separated(
                  itemCount: _draft.attachments.length,
                  shrinkWrap: true,
                  physics: const NeverScrollableScrollPhysics(),
                  separatorBuilder: (_, __) => const Divider(height: 1),
                  itemBuilder: (context, index) {
                    final PurchaseAttachment attachment =
                        _draft.attachments[index];
                    return ListTile(
                      leading: const Icon(Icons.insert_drive_file_outlined),
                      title: Text(attachment.fileName),
                      subtitle: Text(
                        '${attachment.attachmentKind} • ${attachment.filePath}',
                      ),
                      trailing: Wrap(
                        spacing: 8,
                        children: [
                          IconButton(
                            tooltip: 'Preview',
                            onPressed: () => showDialog<void>(
                              context: context,
                              builder: (_) => AlertDialog(
                                title: Text(attachment.fileName),
                                content: SelectableText(
                                  'Path: ${attachment.filePath}\nType: ${attachment.mimeType.ifEmpty('Unknown')}',
                                ),
                                actions: [
                                  FilledButton(
                                    onPressed: () => Navigator.of(context).pop(),
                                    child: const Text('Close'),
                                  ),
                                ],
                              ),
                            ),
                            icon: const Icon(Icons.preview_outlined),
                          ),
                          if (!widget.isReadOnly)
                            IconButton(
                              tooltip: 'Remove',
                              onPressed: () => _removeAttachment(index),
                              icon: const Icon(Icons.delete_outline),
                            ),
                        ],
                      ),
                    );
                  },
                ),
        ],
      );

  Widget _buildNotesTab() => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const SectionHeader(
                title: 'Notes',
                description:
                    'Capture internal, vendor, and system note streams in one place.',
              ),
              const Spacer(),
              if (!widget.isReadOnly)
                FilledButton.tonalIcon(
                  onPressed: _addNote,
                  icon: const Icon(Icons.note_add_outlined),
                  label: const Text('Add Note'),
                ),
            ],
          ),
          const SizedBox(height: 12),
          _draft.notes.isEmpty
              ? const StandardEmptyState(
                  type: EmptyStateType.noRecords,
                  title: 'No notes',
                  message:
                      'Add internal, vendor, or system notes for collaboration.',
                )
              : ListView.separated(
                  itemCount: _draft.notes.length,
                  shrinkWrap: true,
                  physics: const NeverScrollableScrollPhysics(),
                  separatorBuilder: (_, __) => const SizedBox(height: 12),
                  itemBuilder: (context, index) {
                    final PurchaseNote note = _draft.notes[index];
                    return Card(
                      child: ListTile(
                        leading: StatusBadge(label: note.noteType),
                        title: Text(note.note),
                        subtitle: Text(note.createdAt.ifEmpty('Unsaved note')),
                        trailing: !widget.isReadOnly
                            ? IconButton(
                                tooltip: 'Remove note',
                                onPressed: () => _removeNote(index),
                                icon: const Icon(Icons.delete_outline),
                              )
                            : null,
                      ),
                    );
                  },
                ),
        ],
      );

  /// What this order is waiting for, in the words of the buttons above it.
  ///
  /// This read "Approval workflow is wired through the enterprise document
  /// framework", which describes the plumbing to somebody who wants to know
  /// whose turn it is.
  String _approvalMessage() {
    if (_draft.id.isEmpty) {
      return 'Save the order before it can be sent for approval.';
    }
    if (_draft.isDraft) {
      return widget.canSubmit
          ? 'Submit this draft to send it for approval.'
          : 'This draft has to be submitted before anyone can approve it.';
    }
    if (_draft.isSubmitted) {
      return widget.canApprove
          ? 'Approve this order to commit the firm to it.'
          : 'Waiting for someone who holds purchase approval.';
    }
    return 'No approval step is outstanding.';
  }

  Widget _buildHistoryTab() => _historyFuture == null
      ? const StandardEmptyState(
          type: EmptyStateType.noRecords,
          title: 'No history yet',
          message:
              'History becomes available after the purchase order is saved.',
        )
      : FutureBuilder<List<PurchaseOrderHistoryRecord>>(
          future: _historyFuture,
          builder: (context, snapshot) {
            final List<PurchaseOrderHistoryRecord> rows =
                snapshot.data ?? const [];
            if (snapshot.connectionState == ConnectionState.waiting) {
              return const Center(child: CircularProgressIndicator());
            }
            final List<DocumentTimelineSnapshot> entries = rows
                .map(
                  (row) => DocumentTimelineSnapshot(
                    occurredAt: row.createdAt,
                    action: row.action,
                    fromState: row.fromStatus,
                    toState: row.toStatus,
                    actor: row.createdBy,
                    remarks: row.remarks,
                    details: _decodeHistoryDetails(row.detailsJson),
                  ),
                )
                .toList();
            return EnterpriseTimeline(
              entries: entries,
              emptyMessage:
                  'The backend history timeline will appear here after lifecycle changes.',
            );
          },
        );

  Widget _buildAuditTab() => const WorkspaceEmptyState(
        title: 'Audit timeline available through audit API',
        message:
            'Purchase mutations already generate audit events in the backend. The desktop keeps this tab reserved until a purchase-scoped audit-read endpoint is exposed.',
      );

  Future<void> _save() async {
    if (_draft.vendorId.isEmpty ||
        _draft.branchId.isEmpty ||
        _draft.warehouseId.isEmpty ||
        _draft.purchaseDate.isEmpty ||
        _draft.lines.isEmpty ||
        _draft.lines.any(
          (line) =>
              line.productId.isEmpty ||
              line.orderedQuantity.trim().isEmpty ||
              line.unitPrice.trim().isEmpty,
        )) {
      setState(() {
        _error =
            'Vendor, branch, warehouse, purchase date, and at least one complete line are required.';
      });
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final PurchaseOrder saved = widget.isCreating
          ? await widget.api.createPurchaseOrder(_draft)
          : await widget.api.updatePurchaseOrder(_draft);
      if (!mounted) return;
      Navigator.of(context)
          .pop(PurchaseEditorOutcome(order: saved, saved: true));
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() => _error = exception.message);
    } finally {
      if (mounted) {
        setState(() => _saving = false);
      }
    }
  }

  void _addLine() {
    final List<PurchaseOrderLine> lines = [..._draft.lines];
    lines.add(
      PurchaseOrderLine(
        id: '',
        lineNumber: lines.length + 1,
        productId: widget.products.firstOrNull?.id ?? '',
        description: '',
        vendorProductCode: '',
        purchaseUomId: '',
        inventoryUomId: '',
        conversionFactor: '1',
        conversionVersion: null,
        orderedQuantity: '1',
        freeQuantity: '0',
        baseQuantity: '0',
        unitPrice: '0',
        discountPercent: '0',
        discountAmount: '0',
        grossAmount: '0',
        taxProfileId: '',
        taxAmount: '0',
        netAmount: '0',
        batchRequired: false,
        expiryRequired: false,
        serialRequired: false,
        manufacturingDate: '',
        expiryDate: '',
        warehouseId: _draft.warehouseId,
        storageNodeId: '',
        remarks: '',
        status: 'ACTIVE',
        createdAt: '',
        updatedAt: '',
      ),
    );
    setState(() => _draft = _draft.copyWith(lines: lines));
  }

  void _removeLine(int index) {
    final List<PurchaseOrderLine> lines = [..._draft.lines]..removeAt(index);
    setState(
      () => _draft = _draft.copyWith(
        lines: lines
            .asMap()
            .entries
            .map(
              (entry) => entry.value.copyWith(lineNumber: entry.key + 1),
            )
            .toList(),
      ),
    );
  }

  void _updateLine(int index, PurchaseOrderLine line) {
    final List<PurchaseOrderLine> lines = [..._draft.lines];
    lines[index] = line;
    setState(() => _draft = _draft.copyWith(lines: lines));
  }

  void _addSchedule() {
    final List<PurchaseDeliverySchedule> rows = [..._draft.deliverySchedules];
    rows.add(
      PurchaseDeliverySchedule(
        id: '',
        purchaseOrderLineId: '',
        lineNumber: 1,
        deliveryDate: _draft.expectedDeliveryDate.ifEmpty(_today()),
        quantity: '0',
        status: 'PLANNED',
        remarks: '',
        createdAt: '',
        updatedAt: '',
      ),
    );
    setState(() => _draft = _draft.copyWith(deliverySchedules: rows));
  }

  void _updateSchedule(int index, PurchaseDeliverySchedule schedule) {
    final List<PurchaseDeliverySchedule> rows = [..._draft.deliverySchedules];
    rows[index] = schedule;
    setState(() => _draft = _draft.copyWith(deliverySchedules: rows));
  }

  void _removeSchedule(int index) {
    final List<PurchaseDeliverySchedule> rows = [..._draft.deliverySchedules]
      ..removeAt(index);
    setState(() => _draft = _draft.copyWith(deliverySchedules: rows));
  }

  Future<void> _pickAttachment() async {
    final XFile? file = await openFile();
    if (file == null) return;
    final String lower = file.name.toLowerCase();
    String mimeType = 'application/octet-stream';
    if (lower.endsWith('.pdf')) {
      mimeType = 'application/pdf';
    } else if (lower.endsWith('.png')) {
      mimeType = 'image/png';
    } else if (lower.endsWith('.jpg') || lower.endsWith('.jpeg')) {
      mimeType = 'image/jpeg';
    } else if (lower.endsWith('.xlsx')) {
      mimeType =
          'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
    }
    setState(
      () => _draft = _draft.copyWith(
        attachments: [
          ..._draft.attachments,
          PurchaseAttachment(
            id: '',
            fileName: file.name,
            mimeType: mimeType,
            filePath: file.path,
            attachmentKind: 'PURCHASE_FILE',
            createdAt: '',
            updatedAt: '',
          ),
        ],
      ),
    );
  }

  void _removeAttachment(int index) {
    final List<PurchaseAttachment> rows = [..._draft.attachments]
      ..removeAt(index);
    setState(() => _draft = _draft.copyWith(attachments: rows));
  }

  Future<void> _addNote() async {
    final _NoteDraft? draft = await showDialog<_NoteDraft>(
      context: context,
      builder: (_) => const _NoteDialog(),
    );
    if (draft == null) return;
    setState(
      () => _draft = _draft.copyWith(
        notes: [
          ..._draft.notes,
          PurchaseNote(
            id: '',
            noteType: draft.type,
            note: draft.note,
            createdAt: '',
            updatedAt: '',
          ),
        ],
      ),
    );
  }

  void _removeNote(int index) {
    final List<PurchaseNote> rows = [..._draft.notes]..removeAt(index);
    setState(() => _draft = _draft.copyWith(notes: rows));
  }

  Widget _dropdownField({
    required String label,
    required String value,
    required List<DropdownMenuItem<String>> items,
    required ValueChanged<String> onChanged,
    required bool readOnly,
  }) =>
      LayoutBuilder(
        builder: (context, constraints) {
          final double fieldWidth = constraints.hasBoundedWidth
              ? math.min(260, constraints.maxWidth)
              : 260;
          return SizedBox(
            width: fieldWidth,
            child: DropdownButtonFormField<String>(
              isExpanded: true,
              initialValue: items.any((item) => item.value == value)
                  ? value
                  : items.firstOrNull?.value,
              decoration: InputDecoration(labelText: label),
              items: items,
              onChanged: readOnly
                  ? null
                  : (next) {
                      if (next != null) {
                        onChanged(next);
                      }
                    },
            ),
          );
        },
      );

  Widget _textField({
    required String label,
    required String value,
    required ValueChanged<String> onChanged,
    bool readOnly = false,
    int maxLines = 1,
  }) =>
      LayoutBuilder(
        builder: (context, constraints) {
          final double fieldWidth = constraints.hasBoundedWidth
              ? math.min(260, constraints.maxWidth)
              : 260;
          return SizedBox(
            width: fieldWidth,
            child: TextFormField(
              initialValue: value,
              maxLines: maxLines,
              readOnly: readOnly,
              decoration: InputDecoration(labelText: label),
              onChanged: onChanged,
            ),
          );
        },
      );

  Widget _switchTile({
    required String label,
    required bool value,
    required bool enabled,
    required ValueChanged<bool> onChanged,
  }) =>
      SizedBox(
        width: 220,
        child: SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: Text(label),
          value: value,
          onChanged: enabled ? onChanged : null,
        ),
      );

  String _labelForTaxProfile(String id) => widget.taxProfiles
      .firstWhere(
        (item) => item.id == id,
        orElse: () => const TaxProfileRecord(
          id: '',
          taxSystemId: '',
          code: '',
          name: '',
          label: '',
          status: '',
          isHistorical: false,
          isDeleted: false,
          components: [],
        ),
      )
      .label
      .ifEmpty(id);

  String _labelForProduct(String id) => widget.products
      .firstWhere(
        (item) => item.id == id,
        orElse: () => const Product(
          id: '',
          firmId: '',
          code: '',
          barcode: '',
          qrCode: '',
          name: '',
          shortName: '',
          description: '',
          productType: '',
          categoryId: '',
          subCategoryId: '',
          unit: '',
          brand: '',
          model: '',
          hsnSac: '',
          taxProfileId: '',
          purchasePrice: '',
          sellingPrice: '',
          mrp: '',
          status: '',
          remarks: '',
          isDeleted: false,
          createdAt: '',
          updatedAt: '',
          attributes: [],
          media: [],
        ),
      )
      .name
      .ifEmpty(id);

  DocumentHeaderSnapshot _documentHeaderSnapshot() => DocumentHeaderSnapshot(
        documentTypeCode: 'PURCHASE_ORDER',
        documentTypeName: 'Purchase Order',
        documentNumber: _draft.poNumber.ifEmpty('Draft'),
        documentDate: _draft.purchaseDate.ifEmpty(_today()),
        reference: _draft.referenceNumber.ifEmpty(_draft.externalReference),
        branch: _branchLabel(_draft.branchId),
        warehouse: _warehouseLabel(_draft.warehouseId),
        firm: '',
        businessProfile: '',
        currency: _draft.currencyCode.ifEmpty(''),
        exchangeRate: _draft.exchangeRate.ifEmpty(''),
        status: _draft.status,
        remarks: _draft.remarks,
        createdBy: '',
        approvedBy: '',
      );

  List<DocumentLineSnapshot> _documentLineSnapshots() => _draft.lines
      .map(
        (line) => DocumentLineSnapshot(
          lineNumber: line.lineNumber,
          product: _productLabel(line.productId),
          description: line.description,
          uom: line.purchaseUomId,
          packaging: line.vendorProductCode,
          quantity: line.orderedQuantity,
          freeQuantity: line.freeQuantity,
          unitPrice: line.unitPrice,
          discount: line.discountAmount,
          taxProfile: _taxProfileLabel(line.taxProfileId),
          amount: line.grossAmount,
          netAmount: line.netAmount,
          remarks: line.remarks,
        ),
      )
      .toList();

  DocumentTotalsSnapshot _documentTotalsSnapshot() => DocumentTotalsSnapshot(
        subtotal: _draft.subtotal,
        discount: _draft.lineDiscountTotal,
        tax: _draft.taxTotal,
        charges: _draft.additionalCharges,
        roundOff: _draft.roundOff,
        grandTotal: _draft.grandTotal,
      );

  Json _decodeHistoryDetails(String value) {
    try {
      final Object? decoded = jsonDecode(value);
      if (decoded is Map) {
        return Map<String, dynamic>.from(decoded);
      }
    } on FormatException {
      return const <String, dynamic>{};
    }
    return const <String, dynamic>{};
  }

  String _branchLabel(String id) => widget.branches
          .where((item) => item.id == id)
          .map((item) => item.displayName.ifEmpty(item.name))
          .toList()
          .isNotEmpty
      ? widget.branches
          .where((item) => item.id == id)
          .map((item) => item.displayName.ifEmpty(item.name))
          .first
      : id;

  String _warehouseLabel(String id) => widget.warehouses
          .where((item) => item.id == id)
          .map((item) => item.displayName.ifEmpty(item.name))
          .toList()
          .isNotEmpty
      ? widget.warehouses
          .where((item) => item.id == id)
          .map((item) => item.displayName.ifEmpty(item.name))
          .first
      : id;

  String _productLabel(String id) => widget.products
          .where((item) => item.id == id)
          .map((item) => item.name)
          .toList()
          .isNotEmpty
      ? widget.products.where((item) => item.id == id).map((item) => item.name).first
      : id;

  String _taxProfileLabel(String id) => widget.taxProfiles
          .where((item) => item.id == id)
          .map((item) => item.label)
          .toList()
          .isNotEmpty
      ? widget.taxProfiles.where((item) => item.id == id).map((item) => item.label).first
      : id;

  bool _toolbarActionEnabled(DocumentToolbarAction action) => switch (action) {
        DocumentToolbarAction.save => !widget.isReadOnly && !_saving,
        DocumentToolbarAction.close => !_saving,
        // The same `isDraft` / `isSubmitted` getters the workspace toolbar
        // gates on, so the two routes to one action cannot disagree about one
        // order. An empty id is an order that has never been saved.
        DocumentToolbarAction.requestApproval => widget.canSubmit &&
            !_saving &&
            _draft.id.isNotEmpty &&
            !_draft.isDeleted &&
            _draft.isDraft,
        DocumentToolbarAction.approve => widget.canApprove &&
            !_saving &&
            _draft.id.isNotEmpty &&
            !_draft.isDeleted &&
            _draft.isSubmitted,
        _ => false,
      };

  /// Move the document along without closing it.
  ///
  /// The dialog then holds the **returned** order, so the status chip, the
  /// approval note and both buttons re-gate the moment the server answers --
  /// which is what makes offering these here as well as on the grid safe:
  /// Submit stops being pressable the instant the order stops being a draft.
  ///
  /// A refusal goes to the banner this dialog already shows rather than to a
  /// toast, which is easy to miss behind a modal, and is how `_save` reports.
  Future<void> _runLifecycle(
    Future<PurchaseOrder> Function() action, {
    required String done,
  }) async {
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final PurchaseOrder updated = await action();
      if (!mounted) return;
      setState(() {
        _draft = updated;
        _acted = true;
        _historyFuture = _loadHistory();
      });
      NotificationService.show(
        context,
        done,
        kind: AppNotificationKind.success,
      );
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() => _error = exception.message);
    } finally {
      if (mounted) {
        setState(() => _saving = false);
      }
    }
  }

  void _handleToolbarAction(DocumentToolbarAction action) {
    switch (action) {
      case DocumentToolbarAction.save:
        if (!widget.isReadOnly) {
          unawaited(_save());
        }
        break;
      case DocumentToolbarAction.close:
        _close();
        break;
      case DocumentToolbarAction.requestApproval:
        if (_toolbarActionEnabled(action)) {
          unawaited(
            _runLifecycle(
              () => widget.api.submitPurchaseOrder(_draft.id),
              done: '${_draft.poNumber} submitted for approval.',
            ),
          );
        }
        break;
      case DocumentToolbarAction.approve:
        if (_toolbarActionEnabled(action)) {
          unawaited(
            _runLifecycle(
              () => widget.api.approvePurchaseOrder(_draft.id),
              done: '${_draft.poNumber} approved.',
            ),
          );
        }
        break;
      case DocumentToolbarAction.newDocument:
      case DocumentToolbarAction.printDocument:
      case DocumentToolbarAction.exportDocument:
      case DocumentToolbarAction.emailDocument:
      case DocumentToolbarAction.dispatch:
      case DocumentToolbarAction.complete:
      case DocumentToolbarAction.reject:
      case DocumentToolbarAction.cancel:
      case DocumentToolbarAction.archive:
        break;
    }
  }

  /// Close, telling the workspace whether anything moved.
  ///
  /// `null` means nothing happened and the grid can be left alone.
  void _close() => Navigator.of(context).pop(
        _acted ? PurchaseEditorOutcome(order: _draft, saved: false) : null,
      );
}

class PurchaseImportWizard extends StatefulWidget {
  const PurchaseImportWizard({
    super.key,
    required this.api,
    required this.requiredHeaders,
    required this.onImported,
    this.initialFileName,
    this.initialFileBytes,
  });

  final ApiClient api;
  final List<String> requiredHeaders;
  final Future<void> Function() onImported;
  final String? initialFileName;
  final List<int>? initialFileBytes;

  @override
  State<PurchaseImportWizard> createState() => _PurchaseImportWizardState();
}

class _PurchaseImportWizardState extends State<PurchaseImportWizard> {
  _ImportFileSelection? _file;
  _PurchaseImportPreview? _preview;
  bool _loading = false;
  bool _importing = false;
  String? _error;
  int _step = 0;

  @override
  void initState() {
    super.initState();
    if (widget.initialFileName?.trim().isNotEmpty == true &&
        widget.initialFileBytes != null) {
      unawaited(
        _setFile(
          widget.initialFileName!.trim(),
          widget.initialFileBytes!,
        ),
      );
    }
  }

  Future<void> _pickFile() async {
    final XFile? file = await openFile(
      acceptedTypeGroups: const [
        XTypeGroup(label: 'Purchase imports', extensions: ['csv', 'xlsx']),
      ],
      confirmButtonText: 'Select Import File',
    );
    if (file == null) return;
    await _setFile(file.name, await file.readAsBytes());
  }

  Future<void> _setFile(String name, List<int> bytes) async {
    setState(() {
      _loading = true;
      _error = null;
      _preview = null;
      _file = _ImportFileSelection(
        name: name,
        bytes: bytes,
        extension: _extension(name),
      );
    });
    try {
      final List<Map<String, String>> rows =
          InventoryImportFileParser.parseBytes(
        fileName: name,
        bytes: bytes,
      );
      final _PurchaseImportPreview preview = _PurchaseImportPreview.build(
        rows: rows,
        requiredHeaders: widget.requiredHeaders,
      );
      if (!mounted) return;
      setState(() {
        _preview = preview;
        _step = 1;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = 'Unable to read the selected file: $error');
    } finally {
      if (mounted) {
        setState(() => _loading = false);
      }
    }
  }

  Future<void> _runImport() async {
    final _ImportFileSelection? file = _file;
    final _PurchaseImportPreview? preview = _preview;
    if (file == null || preview == null || !preview.canImport) return;
    setState(() {
      _importing = true;
      _error = null;
      _step = 2;
    });
    try {
      await widget.api.importPurchaseOrdersFile(
        format: file.extension == 'xlsx' ? 'xlsx' : 'csv',
        fileName: file.name,
        bytes: file.bytes,
      );
      if (!mounted) return;
      setState(() => _step = 3);
      await widget.onImported();
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() {
        _error = exception.message;
        _step = 1;
      });
    } finally {
      if (mounted) {
        setState(() => _importing = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) => Column(
        children: [
          _DialogHeader(
            title: 'Purchase Import Wizard',
            subtitle: 'CSV and Excel purchase order imports',
            onClose: _importing ? null : () => Navigator.of(context).pop(),
          ),
          Expanded(
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (_error != null) ...[
                    _ErrorCard(message: _error!),
                    const SizedBox(height: 16),
                  ],
                  Wrap(
                    spacing: 12,
                    runSpacing: 12,
                    children: [
                      _WizardMetricCard(
                        label: 'Step',
                        value: '${_step + 1}/4',
                        icon: Icons.alt_route_outlined,
                      ),
                      _WizardMetricCard(
                        label: 'Total Records',
                        value: '${_preview?.total ?? 0}',
                        icon: Icons.table_rows_outlined,
                      ),
                      _WizardMetricCard(
                        label: 'Valid Records',
                        value: '${_preview?.valid ?? 0}',
                        icon: Icons.verified_outlined,
                      ),
                      _WizardMetricCard(
                        label: 'Issues',
                        value: '${_preview?.issues.length ?? 0}',
                        icon: Icons.warning_amber_outlined,
                      ),
                    ],
                  ),
                  const SizedBox(height: 16),
                  Row(
                    children: [
                      FilledButton.icon(
                        onPressed: _loading || _importing ? null : _pickFile,
                        icon: const Icon(Icons.upload_file_outlined),
                        label: const Text('Preview File'),
                      ),
                      const SizedBox(width: 12),
                      OutlinedButton.icon(
                        onPressed: _preview?.canImport == true && !_importing
                            ? _runImport
                            : null,
                        icon: _importing
                            ? const SizedBox(
                                width: 16,
                                height: 16,
                                child:
                                    CircularProgressIndicator(strokeWidth: 2),
                              )
                            : const Icon(Icons.play_arrow_outlined),
                        label: Text(
                            _error == null ? 'Start Import' : 'Retry Import'),
                      ),
                    ],
                  ),
                  const SizedBox(height: 16),
                  Expanded(
                    child: Card(
                      clipBehavior: Clip.antiAlias,
                      child: _preview == null
                          ? const Center(
                              child: Text(
                                  'Select a purchase import file to preview.'),
                            )
                          : ListView(
                              padding: const EdgeInsets.all(16),
                              children: [
                                Text(
                                  _file?.name ?? '',
                                  style:
                                      Theme.of(context).textTheme.titleMedium,
                                ),
                                const SizedBox(height: 12),
                                if (_preview!.issues.isNotEmpty) ...[
                                  Text(
                                    'Validation',
                                    style:
                                        Theme.of(context).textTheme.titleSmall,
                                  ),
                                  const SizedBox(height: 8),
                                  for (final String issue in _preview!.issues)
                                    Padding(
                                      padding: const EdgeInsets.only(bottom: 8),
                                      child: Text('• $issue'),
                                    ),
                                  const Divider(),
                                ],
                                Text(
                                  'Preview',
                                  style: Theme.of(context).textTheme.titleSmall,
                                ),
                                const SizedBox(height: 8),
                                SingleChildScrollView(
                                  scrollDirection: Axis.horizontal,
                                  child: DataTable(
                                    columns: _preview!.headers
                                        .map((header) =>
                                            DataColumn(label: Text(header)))
                                        .toList(),
                                    rows: _preview!.rows
                                        .take(5)
                                        .map(
                                          (row) => DataRow(
                                            cells: _preview!.headers
                                                .map(
                                                  (header) => DataCell(
                                                    Text(row[header] ?? ''),
                                                  ),
                                                )
                                                .toList(),
                                          ),
                                        )
                                        .toList(),
                                  ),
                                ),
                              ],
                            ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      );
}

class _ReasonDialog extends StatefulWidget {
  const _ReasonDialog({required this.title});

  final String title;

  @override
  State<_ReasonDialog> createState() => _ReasonDialogState();
}

class _ReasonDialogState extends State<_ReasonDialog> {
  final TextEditingController _controller = TextEditingController();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: Text(widget.title),
        content: TextField(
          controller: _controller,
          maxLines: 4,
          decoration: const InputDecoration(
            labelText: 'Reason',
            hintText: 'Optional remarks for the lifecycle action',
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(_controller.text.trim()),
            child: const Text('Confirm'),
          ),
        ],
      );
}

class _NoteDialog extends StatefulWidget {
  const _NoteDialog();

  @override
  State<_NoteDialog> createState() => _NoteDialogState();
}

class _NoteDialogState extends State<_NoteDialog> {
  final TextEditingController _controller = TextEditingController();
  String _type = 'INTERNAL';

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: const Text('Add Note'),
        content: SizedBox(
          width: 420,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              DropdownButtonFormField<String>(
                initialValue: _type,
                decoration: const InputDecoration(labelText: 'Note Type'),
                items: const [
                  DropdownMenuItem(value: 'INTERNAL', child: Text('Internal')),
                  DropdownMenuItem(value: 'VENDOR', child: Text('Vendor')),
                  DropdownMenuItem(value: 'SYSTEM', child: Text('System')),
                ],
                onChanged: (value) => setState(() => _type = value ?? _type),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _controller,
                maxLines: 4,
                decoration: const InputDecoration(labelText: 'Note'),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () {
              if (_controller.text.trim().isEmpty) return;
              Navigator.of(context).pop(
                _NoteDraft(type: _type, note: _controller.text.trim()),
              );
            },
            child: const Text('Add'),
          ),
        ],
      );
}

class _ColumnChooserDialog extends StatefulWidget {
  const _ColumnChooserDialog({required this.visibleColumns});

  final Map<String, bool> visibleColumns;

  @override
  State<_ColumnChooserDialog> createState() => _ColumnChooserDialogState();
}

class _ColumnChooserDialogState extends State<_ColumnChooserDialog> {
  late final Map<String, bool> _columns =
      Map<String, bool>.from(widget.visibleColumns);
  final TextEditingController _viewName = TextEditingController();

  @override
  void dispose() {
    _viewName.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: const Text('Column Chooser'),
        content: SizedBox(
          width: 420,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Flexible(
                child: ListView(
                  shrinkWrap: true,
                  children: _columns.entries
                      .map(
                        (entry) => CheckboxListTile(
                          value: entry.value,
                          title: Text(entry.key.toUpperCase()),
                          onChanged: (value) => setState(
                            () => _columns[entry.key] = value ?? false,
                          ),
                        ),
                      )
                      .toList(),
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _viewName,
                decoration: const InputDecoration(
                  labelText: 'Save as view',
                  hintText: 'Optional view name',
                ),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(
              _PurchaseSavedViewSelection(
                columns: _columns,
                viewName: _viewName.text.trim(),
              ),
            ),
            child: const Text('Apply'),
          ),
        ],
      );
}

class _PurchaseExportDialog extends StatefulWidget {
  const _PurchaseExportDialog({required this.hasSelection});

  final bool hasSelection;

  @override
  State<_PurchaseExportDialog> createState() => _PurchaseExportDialogState();
}

class _PurchaseExportDialogState extends State<_PurchaseExportDialog> {
  _PurchaseExportScope _scope = _PurchaseExportScope.currentView;
  String _format = 'csv';

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: const Text('Export Purchase Orders'),
        content: SizedBox(
          width: 360,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              DropdownButtonFormField<_PurchaseExportScope>(
                initialValue: _scope,
                decoration: const InputDecoration(labelText: 'Scope'),
                items: [
                  if (widget.hasSelection)
                    const DropdownMenuItem(
                      value: _PurchaseExportScope.selected,
                      child: Text('Selected rows'),
                    ),
                  const DropdownMenuItem(
                    value: _PurchaseExportScope.currentView,
                    child: Text('Current view'),
                  ),
                  const DropdownMenuItem(
                    value: _PurchaseExportScope.filteredView,
                    child: Text('Filtered view'),
                  ),
                ],
                onChanged: (value) => setState(() => _scope = value ?? _scope),
              ),
              const SizedBox(height: 12),
              DropdownButtonFormField<String>(
                initialValue: _format,
                decoration: const InputDecoration(labelText: 'Format'),
                items: const [
                  DropdownMenuItem(value: 'csv', child: Text('CSV')),
                  DropdownMenuItem(value: 'xlsx', child: Text('Excel')),
                ],
                onChanged: (value) =>
                    setState(() => _format = value ?? _format),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(
              _PurchaseExportRequest(scope: _scope, format: _format),
            ),
            child: const Text('Export'),
          ),
        ],
      );
}

class _DialogHeader extends StatelessWidget {
  const _DialogHeader({
    required this.title,
    required this.subtitle,
    required this.onClose,
  });

  final String title;
  final String subtitle;
  final VoidCallback? onClose;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.fromLTRB(24, 20, 16, 8),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title, style: Theme.of(context).textTheme.headlineSmall),
                  const SizedBox(height: 4),
                  Text(subtitle, style: Theme.of(context).textTheme.bodyMedium),
                ],
              ),
            ),
            IconButton(
              tooltip: 'Close',
              onPressed: onClose,
              icon: const Icon(Icons.close),
            ),
          ],
        ),
      );
}

class _WizardMetricCard extends StatelessWidget {
  const _WizardMetricCard({
    required this.label,
    required this.value,
    required this.icon,
  });

  final String label;
  final String value;
  final IconData icon;

  @override
  Widget build(BuildContext context) => SizedBox(
        width: 180,
        child: Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(icon, color: Theme.of(context).colorScheme.primary),
                const SizedBox(height: 12),
                Text(value, style: Theme.of(context).textTheme.titleLarge),
                const SizedBox(height: 4),
                Text(label),
              ],
            ),
          ),
        ),
      );
}

class _ErrorCard extends StatelessWidget {
  const _ErrorCard({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) => Card(
        color: Theme.of(context).colorScheme.errorContainer,
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Row(
            children: [
              const Icon(Icons.error_outline),
              const SizedBox(width: 12),
              Expanded(child: Text(message)),
            ],
          ),
        ),
      );
}

class _ImportFileSelection {
  const _ImportFileSelection({
    required this.name,
    required this.bytes,
    required this.extension,
  });

  final String name;
  final List<int> bytes;
  final String extension;
}

class _PurchaseImportPreview {
  const _PurchaseImportPreview({
    required this.headers,
    required this.rows,
    required this.issues,
    required this.total,
    required this.valid,
  });

  final List<String> headers;
  final List<Map<String, String>> rows;
  final List<String> issues;
  final int total;
  final int valid;

  bool get canImport => total > 0 && issues.isEmpty && valid > 0;

  factory _PurchaseImportPreview.build({
    required List<Map<String, String>> rows,
    required List<String> requiredHeaders,
  }) {
    final List<String> headers =
        rows.isEmpty ? const [] : rows.first.keys.toList(growable: false);
    final Set<String> normalizedHeaders =
        headers.map((header) => header.toLowerCase()).toSet();
    final List<String> issues = [
      for (final String header in requiredHeaders)
        if (!normalizedHeaders.contains(header))
          'Missing required column: $header',
    ];
    int valid = 0;
    for (final Map<String, String> row in rows) {
      final bool complete = requiredHeaders.every(
        (header) => (row[header] ?? '').trim().isNotEmpty,
      );
      if (complete) {
        valid++;
      }
    }
    if (rows.isEmpty) {
      issues.add('The selected file does not contain any purchase records.');
    }
    return _PurchaseImportPreview(
      headers: headers,
      rows: rows,
      issues: issues,
      total: rows.length,
      valid: valid,
    );
  }
}

class _PurchaseSavedView {
  const _PurchaseSavedView({
    required this.name,
    required this.visibleColumns,
  });

  final String name;
  final Map<String, bool> visibleColumns;

  factory _PurchaseSavedView.fromJson(Json json) => _PurchaseSavedView(
        name: stringValue(json['name']),
        visibleColumns:
            (json['visible_columns'] as Map? ?? const {}).map<String, bool>(
          (key, value) => MapEntry(key.toString(), value == true),
        ),
      );

  Json toJson() => {
        'name': name,
        'visible_columns': visibleColumns,
      };
}

class _PurchaseSavedViewSelection {
  const _PurchaseSavedViewSelection({
    required this.columns,
    required this.viewName,
  });

  final Map<String, bool> columns;
  final String viewName;
}

class _PurchaseExportRequest {
  const _PurchaseExportRequest({
    required this.scope,
    required this.format,
  });

  final _PurchaseExportScope scope;
  final String format;
}

class _NoteDraft {
  const _NoteDraft({required this.type, required this.note});

  final String type;
  final String note;
}

class _VendorSpend {
  const _VendorSpend(this.vendorId, this.total);

  final String vendorId;
  final double total;
}

enum PurchaseDialogMode { create, view, edit, duplicate }

enum _PurchaseExportScope { selected, currentView, filteredView }

String _extension(String name) {
  final int dot = name.lastIndexOf('.');
  return dot == -1 ? 'csv' : name.substring(dot + 1).toLowerCase();
}

double _parseNumber(String value) => double.tryParse(value.trim()) ?? 0;

String _today() => DateTime.now().toIso8601String().split('T').first;

String _csvValue(Object? value) {
  final String text = '${value ?? ''}';
  if (!text.contains(',') && !text.contains('"') && !text.contains('\n')) {
    return text;
  }
  return '"${text.replaceAll('"', '""')}"';
}

extension on String {
  String ifEmpty(String fallback) => trim().isEmpty ? fallback : this;
}

extension<T> on Iterable<T> {
  T? get firstOrNull => isEmpty ? null : first;
}

extension on DetailLine {
  Widget toWidget() => Builder(
        builder: (context) => SizedBox(
          width: 220,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(label, style: Theme.of(context).textTheme.labelMedium),
              const SizedBox(height: 2),
              SelectableText(value),
            ],
          ),
        ),
      );
}
