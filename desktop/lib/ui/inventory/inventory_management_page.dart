import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/preferences/desktop_preferences_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/branch_warehouse.dart';
import '../../models/entities.dart';
import '../../models/inventory.dart';
import '../../models/product.dart';
import 'inventory_details_dialog.dart';
import 'inventory_import_wizard.dart';
import '../workspace/workspace_components.dart';
import '../workspace/workspace_interactions.dart';

enum InventorySection {
  inventory,
  openingStock,
  stockLedger,
  transactions,
  stockSummary,
  stockSearch,
  inventoryImport,
  inventoryExport,
  settings,
}

class InventoryManagementPage extends StatefulWidget {
  const InventoryManagementPage({
    super.key,
    required this.api,
    required this.preferences,
    required this.permissions,
    required this.hasActiveFirm,
    required this.section,
    this.onNavigateToSection,
  });

  final ApiClient api;
  final DesktopPreferencesService preferences;
  final PermissionService permissions;
  final bool hasActiveFirm;
  final InventorySection section;
  final ValueChanged<InventorySection>? onNavigateToSection;

  @override
  State<InventoryManagementPage> createState() => _InventoryManagementPageState();
}

class _InventoryManagementPageState extends State<InventoryManagementPage> {
  static const int _rowsPerPage = 20;

  final TextEditingController _search = TextEditingController();
  final FocusNode _searchFocus = FocusNode();

  bool _loading = false;
  String? _error;
  int _page = 1;
  int _total = 0;

  String? _status;
  String? _transactionType;
  String? _branchId;
  String? _warehouseId;
  String? _productId;
  bool _includeDeleted = false;
  bool _lowStockOnly = false;
  bool _outOfStockOnly = false;
  bool _negativeOnly = false;
  List<BranchRecord> _branches = const [];
  List<WarehouseRecord> _warehouses = const [];
  List<Product> _products = const [];

  List<InventoryRecord> _inventory = const [];
  InventoryRecord? _selectedInventory;

  List<InventoryTransactionRecord> _transactions = const [];
  InventoryTransactionRecord? _selectedTransaction;

  List<InventoryTransactionRecord> _ledger = const [];
  InventoryTransactionRecord? _selectedLedger;

  List<OpeningStockBatchRecord> _openingStock = const [];
  OpeningStockBatchRecord? _selectedOpeningStock;

  InventorySummaryRecord? _summary;
  List<InventoryLocationSummaryRecord> _firmSummary = const [];
  List<InventoryLocationSummaryRecord> _branchSummary = const [];
  List<InventoryLocationSummaryRecord> _warehouseSummary = const [];

  bool get _canViewInventory =>
      widget.permissions.hasPermission('INVENTORY_VIEW');
  bool get _canCreateOpeningStock =>
      widget.permissions.hasPermission('OPENING_STOCK_CREATE');
  bool get _canUpdateOpeningStock =>
      widget.permissions.hasPermission('OPENING_STOCK_UPDATE');
  bool get _canViewLedger =>
      widget.permissions.hasPermission('INVENTORY_LEDGER_VIEW');
  bool get _canExport =>
      widget.permissions.hasPermission('INVENTORY_EXPORT');
  bool get _canImport =>
      widget.permissions.hasPermission('INVENTORY_IMPORT');
  bool get _canViewTransactions =>
      widget.permissions.hasPermission('INVENTORY_TRANSACTION_VIEW');
  bool get _canAdjust =>
      widget.permissions.hasPermission('INVENTORY_ADJUST');

  @override
  void initState() {
    super.initState();
    _bootstrap();
  }

  @override
  void dispose() {
    _search.dispose();
    _searchFocus.dispose();
    super.dispose();
  }

  Future<void> _bootstrap() async {
    if (!widget.hasActiveFirm) {
      return;
    }
    await _loadLookups();
    await _load();
  }

  Future<void> _loadLookups() async {
    try {
      final List<dynamic> results = await Future.wait<dynamic>([
        widget.api.branches(page: 1, pageSize: 100),
        widget.api.warehouses(page: 1, pageSize: 100),
        widget.api.products(page: 1, pageSize: 500),
      ]);
      if (!mounted) return;
      setState(() {
        _branches = (results[0] as PagedResult<BranchRecord>).items;
        _warehouses = (results[1] as PagedResult<WarehouseRecord>).items;
        _products = (results[2] as PagedResult<Product>).items;
      });
    } on ApiException {
      // Keep inventory screens usable even if lookup metadata is partial.
    }
  }

  Future<void> _load({int? requestedPage}) async {
    if (!widget.hasActiveFirm) {
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
      _page = requestedPage ?? _page;
    });
    try {
      switch (widget.section) {
        case InventorySection.inventory:
        case InventorySection.stockSearch:
          final PagedResult<InventoryRecord> result = await widget.api.inventory(
            page: _page,
            pageSize: _rowsPerPage,
            search: _search.text.trim(),
            sortBy: widget.section == InventorySection.stockSearch
                ? 'product_code'
                : 'updated_at',
            filters: InventoryQuery(
              status: _status,
              branchId: _branchId,
              warehouseId: _warehouseId,
              productId: _productId,
              includeDeleted: _includeDeleted,
              lowStockOnly: _lowStockOnly,
              outOfStockOnly: _outOfStockOnly,
              negativeOnly: _negativeOnly,
            ),
          );
          _inventory = result.items;
          _total = result.total;
          _selectedInventory = _keepSelection(
            _selectedInventory?.id,
            _inventory,
            (item) => item.id,
          );
          break;
        case InventorySection.transactions:
          final PagedResult<InventoryTransactionRecord> result =
              await widget.api.inventoryTransactions(
            page: _page,
            pageSize: _rowsPerPage,
            search: _search.text.trim(),
            filters: InventoryTransactionQuery(
              transactionType: _transactionType,
              branchId: _branchId,
              warehouseId: _warehouseId,
              productId: _productId,
            ),
          );
          _transactions = result.items;
          _total = result.total;
          _selectedTransaction = _keepSelection(
            _selectedTransaction?.id,
            _transactions,
            (item) => item.id,
          );
          break;
        case InventorySection.stockLedger:
          final PagedResult<InventoryTransactionRecord> result =
              await widget.api.stockLedger(
            page: _page,
            pageSize: _rowsPerPage,
            search: _search.text.trim(),
            filters: InventoryTransactionQuery(
              transactionType: _transactionType,
              branchId: _branchId,
              warehouseId: _warehouseId,
              productId: _productId,
            ),
          );
          _ledger = result.items;
          _total = result.total;
          _selectedLedger = _keepSelection(
            _selectedLedger?.transactionId,
            _ledger,
            (item) => item.transactionId,
          );
          break;
        case InventorySection.openingStock:
          final PagedResult<OpeningStockBatchRecord> result =
              await widget.api.openingStockBatches(
            page: _page,
            pageSize: _rowsPerPage,
            search: _search.text.trim(),
            filters: OpeningStockBatchQuery(
              status: _status,
              branchId: _branchId,
              warehouseId: _warehouseId,
              includeDeleted: _includeDeleted,
            ),
          );
          _openingStock = result.items;
          _total = result.total;
          _selectedOpeningStock = _keepSelection(
            _selectedOpeningStock?.id,
            _openingStock,
            (item) => item.id,
          );
          break;
        case InventorySection.stockSummary:
          final List<dynamic> results = await Future.wait<dynamic>([
            widget.api.inventorySummary(includeDeleted: _includeDeleted),
            widget.api.inventoryByFirm(),
            widget.api.inventoryByBranch(),
            widget.api.inventoryByWarehouse(),
          ]);
          _summary = results[0] as InventorySummaryRecord;
          _firmSummary = results[1] as List<InventoryLocationSummaryRecord>;
          _branchSummary = results[2] as List<InventoryLocationSummaryRecord>;
          _warehouseSummary = results[3] as List<InventoryLocationSummaryRecord>;
          _total = _summary?.totalRecords ?? 0;
          break;
        case InventorySection.inventoryImport:
        case InventorySection.inventoryExport:
        case InventorySection.settings:
          _total = 0;
          break;
      }
      if (mounted) {
        setState(() {});
      }
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() => _error = exception.message);
    } finally {
      if (mounted) {
        setState(() => _loading = false);
      }
    }
  }

  T? _keepSelection<T>(
    String? selectedId,
    List<T> items,
    String Function(T) idOf,
  ) {
    if (selectedId == null) return null;
    for (final T item in items) {
      if (idOf(item) == selectedId) {
        return item;
      }
    }
    return null;
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.hasActiveFirm) {
      return const StandardEmptyState(type: EmptyStateType.noFirmSelected);
    }
    return switch (widget.section) {
      InventorySection.stockSummary => _buildSummaryWorkspace(),
      InventorySection.inventoryImport => _buildImportWorkspace(),
      InventorySection.inventoryExport => _buildExportWorkspace(),
      InventorySection.settings => _buildSettingsWorkspace(),
      _ => _buildGridWorkspace(),
    };
  }

  Widget _buildGridWorkspace() => ManagementWorkspaceLayout(
        toolbar: _buildToolbar(),
        searchPanel: SearchFilterPanel(
          controller: _search,
          focusNode: _searchFocus,
          hintText: _searchHint,
          onSearch: (_) => _load(requestedPage: 1),
        ),
        filterPanel: _buildFilterPanel(),
        primaryContent: _buildPrimaryContent(),
        detailsPanel: _buildDetailsPanel(),
        statusBar: WorkspaceStatusBar(
          total: _total,
          selected: _selectedCount > 0,
          selectedCount: _selectedCount,
          message: _loading ? 'Loading...' : null,
        ),
      );

  Widget _buildSummaryWorkspace() {
    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_error != null) {
      return WorkspaceEmptyState(
        title: 'Unable to load stock summary',
        message: _error!,
      );
    }
    final InventorySummaryRecord summary = _summary ??
        const InventorySummaryRecord(
          totalRecords: 0,
          currentQuantity: '0',
          reservedQuantity: '0',
          availableQuantity: '0',
          blockedQuantity: '0',
          damagedQuantity: '0',
          quarantineQuantity: '0',
          inTransitQuantity: '0',
          lowStockCount: 0,
          outOfStockCount: 0,
          negativeStockCount: 0,
        );
    return WorkspaceLayout(
      title: 'Stock Summary',
      description:
          'Review current, available, reserved, blocked, damaged, quarantine, and in-transit balances.',
      breadcrumbs: const ['Workspace', 'Inventory', 'Stock Summary'],
      toolbar: Wrap(
        spacing: 8,
        children: [
          OutlinedButton.icon(
            onPressed: _load,
            icon: const Icon(Icons.refresh),
            label: const Text('Refresh'),
          ),
          if (_canExport)
            FilledButton.tonalIcon(
              onPressed: () => _exportDataset('inventory'),
              icon: const Icon(Icons.file_download_outlined),
              label: const Text('Copy Inventory CSV'),
            ),
        ],
      ),
      content: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(24, 0, 24, 24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Wrap(
              spacing: 12,
              runSpacing: 12,
              children: [
                _metricCard('Inventory records', '${summary.totalRecords}'),
                _metricCard('Current stock', summary.currentQuantity),
                _metricCard('Available stock', summary.availableQuantity),
                _metricCard('Reserved stock', summary.reservedQuantity),
                _metricCard('Blocked stock', summary.blockedQuantity),
                _metricCard('Damaged stock', summary.damagedQuantity),
                _metricCard('Quarantine stock', summary.quarantineQuantity),
                _metricCard('In transit', summary.inTransitQuantity),
                _metricCard('Low stock', '${summary.lowStockCount}'),
                _metricCard('Out of stock', '${summary.outOfStockCount}'),
                _metricCard('Negative stock', '${summary.negativeStockCount}'),
              ],
            ),
            const SizedBox(height: 24),
            _summaryTable('Firm stock', _firmSummary),
            const SizedBox(height: 16),
            _summaryTable('Branch stock', _branchSummary),
            const SizedBox(height: 16),
            _summaryTable('Warehouse stock', _warehouseSummary),
          ],
        ),
      ),
    );
  }

  Widget _buildImportWorkspace() => WorkspaceLayout(
        title: 'Inventory Import',
        description:
            'Use the desktop import wizard for CSV/XLSX preview, validation, retries, and import progress.',
        breadcrumbs: const ['Workspace', 'Inventory', 'Import'],
        headerActions: [
          if (_canCreateOpeningStock)
            FilledButton.icon(
              onPressed: _openOpeningStockDialog,
              icon: const Icon(Icons.add),
              label: const Text('Manual Entry'),
            ),
        ],
        content: Padding(
          padding: const EdgeInsets.only(bottom: 24),
          child: InventoryImportWizard(
            api: widget.api,
            preferences: widget.preferences,
            branches: _branches,
            warehouses: _warehouses,
            products: _products,
            onViewImportedRecords: (type) async {
              final InventorySection target = switch (type) {
                InventoryImportType.openingStock => InventorySection.openingStock,
                InventoryImportType.inventoryUpdate => InventorySection.inventory,
                InventoryImportType.inventoryAdjustment =>
                  InventorySection.transactions,
              };
              widget.onNavigateToSection?.call(target);
            },
          ),
        ),
      );

  Widget _buildExportWorkspace() => WorkspaceLayout(
        title: 'Inventory Export',
        description:
            'Copy inventory and stock-ledger datasets for downstream reporting or spreadsheet analysis.',
        breadcrumbs: const ['Workspace', 'Inventory', 'Export'],
        content: Padding(
          padding: const EdgeInsets.fromLTRB(24, 0, 24, 24),
          child: Row(
            children: [
              Expanded(
                child: _actionCard(
                  title: 'Inventory CSV',
                  description:
                      'Export the current inventory projection with balances and reorder thresholds.',
                  actionLabel: 'Copy inventory CSV',
                  onPressed: _canExport ? () => _exportDataset('inventory') : null,
                ),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: _actionCard(
                  title: 'Stock ledger CSV',
                  description:
                      'Export the immutable stock ledger with movement references and balances.',
                  actionLabel: 'Copy ledger CSV',
                  onPressed: _canExport ? () => _exportDataset('ledger') : null,
                ),
              ),
            ],
          ),
        ),
      );

  Widget _buildSettingsWorkspace() => WorkspaceLayout(
        title: 'Inventory Settings',
        description:
            'Review the current foundation and extension points for future inventory phases.',
        breadcrumbs: const ['Workspace', 'Inventory', 'Settings'],
        content: Padding(
          padding: const EdgeInsets.fromLTRB(24, 0, 24, 24),
          child: ListView(
            children: const [
              _InfoTile(
                icon: Icons.receipt_long_outlined,
                title: 'Transactions are the source of truth',
                message:
                    'All stock changes must be created through immutable inventory transactions.',
              ),
              _InfoTile(
                icon: Icons.history_toggle_off_outlined,
                title: 'Ledger history is immutable',
                message:
                    'Stock ledger entries are append-only and preserved for audit and reconciliation.',
              ),
              _InfoTile(
                icon: Icons.extension_outlined,
                title: 'Future phases attach here',
                message:
                    'Batch, serial, purchase, sales, and manufacturing flows must reuse this inventory layer.',
              ),
            ],
          ),
        ),
      );

  Widget _buildToolbar() => Wrap(
        spacing: 8,
        runSpacing: 8,
        children: [
          if (widget.section == InventorySection.inventory && _canAdjust)
            FilledButton.tonalIcon(
              onPressed:
                  _selectedInventory == null ? null : _editInventoryThresholds,
              icon: const Icon(Icons.edit_outlined),
              label: const Text('Edit thresholds'),
            ),
          if (widget.section == InventorySection.inventory &&
              _canAdjust &&
              _selectedInventory != null)
            OutlinedButton.icon(
              onPressed: _deleteSelectedInventory,
              icon: const Icon(Icons.delete_outline),
              label: const Text('Delete'),
            ),
          if (widget.section == InventorySection.transactions && _canAdjust)
            FilledButton.icon(
              onPressed: _openAdjustmentDialog,
              icon: const Icon(Icons.add),
              label: const Text('New adjustment'),
            ),
          if (widget.section == InventorySection.openingStock &&
              _canCreateOpeningStock)
            FilledButton.icon(
              onPressed: _openOpeningStockDialog,
              icon: const Icon(Icons.add),
              label: const Text('New opening stock'),
            ),
          if (widget.section == InventorySection.openingStock &&
              _canUpdateOpeningStock &&
              _selectedOpeningStock != null &&
              !_selectedOpeningStock!.isPosted)
            FilledButton.tonalIcon(
              onPressed: () => _openOpeningStockDialog(existing: _selectedOpeningStock),
              icon: const Icon(Icons.edit_outlined),
              label: const Text('Edit draft'),
            ),
          if (widget.section == InventorySection.openingStock &&
              _canCreateOpeningStock &&
              _selectedOpeningStock != null &&
              !_selectedOpeningStock!.isPosted)
            OutlinedButton.icon(
              onPressed: _postSelectedOpeningStock,
              icon: const Icon(Icons.publish_outlined),
              label: const Text('Post draft'),
            ),
          if ((widget.section == InventorySection.inventory ||
                  widget.section == InventorySection.stockLedger ||
                  widget.section == InventorySection.transactions ||
                  widget.section == InventorySection.openingStock) &&
              _canExport)
            OutlinedButton.icon(
              onPressed: () => _exportDataset(
                widget.section == InventorySection.stockLedger
                    ? 'ledger'
                    : 'inventory',
              ),
              icon: const Icon(Icons.file_download_outlined),
              label: const Text('Copy CSV'),
            ),
          OutlinedButton.icon(
            onPressed: _load,
            icon: const Icon(Icons.refresh),
            label: const Text('Refresh'),
          ),
        ],
      );

  Widget _buildFilterPanel() {
    final bool inventoryFilters = widget.section == InventorySection.inventory ||
        widget.section == InventorySection.stockSearch;
    final bool movementFilters = widget.section == InventorySection.transactions ||
        widget.section == InventorySection.stockLedger;
    final bool openingFilters = widget.section == InventorySection.openingStock;
    final int activeCount = [
      _status,
      _transactionType,
      _branchId,
      _warehouseId,
      _productId,
    ].where((value) => value?.isNotEmpty == true).length +
        (_includeDeleted ? 1 : 0) +
        (_lowStockOnly ? 1 : 0) +
        (_outOfStockOnly ? 1 : 0) +
        (_negativeOnly ? 1 : 0);
    return FilterPanel(
      activeFilterCount: activeCount,
      onApply: () => _load(requestedPage: 1),
      onClear: () {
        setState(() {
          _status = null;
          _transactionType = null;
          _branchId = null;
          _warehouseId = null;
          _productId = null;
          _includeDeleted = false;
          _lowStockOnly = false;
          _outOfStockOnly = false;
          _negativeOnly = false;
        });
        _load(requestedPage: 1);
      },
      children: [
        if (inventoryFilters || openingFilters)
          SizedBox(
            width: 180,
            child: DropdownButtonFormField<String>(
              initialValue: _status,
              decoration: const InputDecoration(labelText: 'Status'),
              items: const ['', 'ACTIVE', 'INACTIVE', 'ARCHIVED', 'DRAFT', 'POSTED']
                  .map(
                    (value) => DropdownMenuItem<String>(
                      value: value.isEmpty ? null : value,
                      child: Text(value.isEmpty ? 'All' : value),
                    ),
                  )
                  .toList(),
              onChanged: (value) => setState(() => _status = value),
            ),
          ),
        if (movementFilters)
          SizedBox(
            width: 220,
            child: DropdownButtonFormField<String>(
              initialValue: _transactionType,
              decoration: const InputDecoration(labelText: 'Transaction type'),
              items: const [
                '',
                'OPENING_STOCK',
                'GOODS_RECEIPT',
                'GOODS_ISSUE',
                'TRANSFER_IN',
                'TRANSFER_OUT',
                'ADJUSTMENT',
                'PHYSICAL_COUNT',
                'RESERVATION',
                'RESERVATION_RELEASE',
                'DAMAGE',
                'EXPIRY',
                'QUARANTINE',
                'RETURN',
                'CORRECTION',
              ]
                  .map(
                    (value) => DropdownMenuItem<String>(
                      value: value.isEmpty ? null : value,
                      child: Text(value.isEmpty ? 'All' : value),
                    ),
                  )
                  .toList(),
              onChanged: (value) => setState(() => _transactionType = value),
            ),
          ),
        _lookupField<BranchRecord>(
          label: 'Branch',
          value: _branchId,
          items: _branches,
          itemId: (item) => item.id,
          itemLabel: (item) => '${item.code} - ${item.name}',
          onChanged: (value) => setState(() => _branchId = value),
        ),
        _lookupField<WarehouseRecord>(
          label: 'Warehouse',
          value: _warehouseId,
          items: _filteredWarehouses,
          itemId: (item) => item.id,
          itemLabel: (item) => '${item.code} - ${item.name}',
          onChanged: (value) => setState(() => _warehouseId = value),
        ),
        _lookupField<Product>(
          label: 'Product',
          value: _productId,
          items: _products,
          itemId: (item) => item.id,
          itemLabel: (item) => '${item.code} - ${item.name}',
          onChanged: (value) => setState(() => _productId = value),
        ),
        if (inventoryFilters) ...[
          FilterChip(
            label: const Text('Low stock'),
            selected: _lowStockOnly,
            onSelected: (value) => setState(() => _lowStockOnly = value),
          ),
          FilterChip(
            label: const Text('Out of stock'),
            selected: _outOfStockOnly,
            onSelected: (value) => setState(() => _outOfStockOnly = value),
          ),
          FilterChip(
            label: const Text('Negative stock'),
            selected: _negativeOnly,
            onSelected: (value) => setState(() => _negativeOnly = value),
          ),
        ],
        FilterChip(
          label: const Text('Include deleted'),
          selected: _includeDeleted,
          onSelected: (value) => setState(() => _includeDeleted = value),
        ),
      ],
    );
  }

  Widget _buildPrimaryContent() {
    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_error != null) {
      return WorkspaceEmptyState(
        title: 'Unable to load inventory data',
        message: _error!,
      );
    }
    return switch (widget.section) {
      InventorySection.inventory || InventorySection.stockSearch =>
        _buildInventoryGrid(),
      InventorySection.transactions => _buildTransactionGrid(),
      InventorySection.stockLedger => _buildLedgerGrid(),
      InventorySection.openingStock => _buildOpeningStockGrid(),
      _ => const SizedBox.shrink(),
    };
  }

  Widget _buildInventoryGrid() {
    if (_inventory.isEmpty) {
      return StandardEmptyState(
        type: _search.text.trim().isEmpty
            ? EmptyStateType.noRecords
            : EmptyStateType.noSearchResults,
      );
    }
    return EnterpriseDataGrid<InventoryRecord>(
      items: _inventory,
      total: _total,
      pageOffset: (_page - 1) * _rowsPerPage,
      rowsPerPage: _rowsPerPage,
      columns: const [
        GridColumn(key: 'product', label: 'Product'),
        GridColumn(key: 'branch', label: 'Branch'),
        GridColumn(key: 'warehouse', label: 'Warehouse'),
        GridColumn(key: 'storage', label: 'Storage'),
        GridColumn(key: 'current', label: 'Current'),
        GridColumn(key: 'available', label: 'Available'),
        GridColumn(key: 'reserved', label: 'Reserved'),
        GridColumn(key: 'status', label: 'Status'),
      ],
      id: (item) => item.id,
      selectedId: _selectedInventory?.id,
      onOpen: _openInventoryDetails,
      cells: (item) => [
        '${item.productCode} - ${item.productName}',
        item.branchCode,
        item.warehouseCode,
        item.storageNodeCode.isEmpty ? '-' : item.storageNodeCode,
        item.currentQuantity,
        item.availableQuantity,
        item.reservedQuantity,
        item.status,
      ],
      onSelect: (item) => setState(() => _selectedInventory = item),
      onPageChanged: _handlePageChange,
    );
  }

  Widget _buildTransactionGrid() {
    if (_transactions.isEmpty) {
      return StandardEmptyState(
        type: _search.text.trim().isEmpty
            ? EmptyStateType.noRecords
            : EmptyStateType.noSearchResults,
      );
    }
    return EnterpriseDataGrid<InventoryTransactionRecord>(
      items: _transactions,
      total: _total,
      pageOffset: (_page - 1) * _rowsPerPage,
      rowsPerPage: _rowsPerPage,
      columns: const [
        GridColumn(key: 'date', label: 'Date'),
        GridColumn(key: 'type', label: 'Type'),
        GridColumn(key: 'reference', label: 'Reference'),
        GridColumn(key: 'product', label: 'Product'),
        GridColumn(key: 'warehouse', label: 'Warehouse'),
        GridColumn(key: 'quantity', label: 'Quantity'),
        GridColumn(key: 'balance', label: 'New balance'),
      ],
      id: (item) => item.id,
      selectedId: _selectedTransaction?.id,
      cells: (item) => [
        item.transactionDate,
        item.transactionType,
        item.referenceNumber,
        '${item.productCode} - ${item.productName}',
        item.warehouseCode,
        item.quantity,
        item.newCurrentQuantity,
      ],
      onSelect: (item) => setState(() => _selectedTransaction = item),
      onPageChanged: _handlePageChange,
    );
  }

  Widget _buildLedgerGrid() {
    if (_ledger.isEmpty) {
      return StandardEmptyState(
        type: _search.text.trim().isEmpty
            ? EmptyStateType.noRecords
            : EmptyStateType.noSearchResults,
      );
    }
    return EnterpriseDataGrid<InventoryTransactionRecord>(
      items: _ledger,
      total: _total,
      pageOffset: (_page - 1) * _rowsPerPage,
      rowsPerPage: _rowsPerPage,
      columns: const [
        GridColumn(key: 'date', label: 'Date'),
        GridColumn(key: 'type', label: 'Type'),
        GridColumn(key: 'reference', label: 'Reference'),
        GridColumn(key: 'product', label: 'Product'),
        GridColumn(key: 'quantity', label: 'Quantity'),
        GridColumn(key: 'balance', label: 'Balance'),
      ],
      id: (item) => item.transactionId,
      selectedId: _selectedLedger?.transactionId,
      cells: (item) => [
        item.transactionDate,
        item.transactionType,
        item.referenceNumber,
        '${item.productCode} - ${item.productName}',
        item.quantity,
        item.newCurrentQuantity,
      ],
      onSelect: (item) => setState(() => _selectedLedger = item),
      onPageChanged: _handlePageChange,
    );
  }

  Widget _buildOpeningStockGrid() {
    if (_openingStock.isEmpty) {
      return StandardEmptyState(
        type: _search.text.trim().isEmpty
            ? EmptyStateType.noRecords
            : EmptyStateType.noSearchResults,
      );
    }
    return EnterpriseDataGrid<OpeningStockBatchRecord>(
      items: _openingStock,
      total: _total,
      pageOffset: (_page - 1) * _rowsPerPage,
      rowsPerPage: _rowsPerPage,
      columns: const [
        GridColumn(key: 'reference', label: 'Reference'),
        GridColumn(key: 'posting', label: 'Posting date'),
        GridColumn(key: 'branch', label: 'Branch'),
        GridColumn(key: 'warehouse', label: 'Warehouse'),
        GridColumn(key: 'source', label: 'Source'),
        GridColumn(key: 'status', label: 'Status'),
      ],
      id: (item) => item.id,
      selectedId: _selectedOpeningStock?.id,
      cells: (item) => [
        item.referenceNumber,
        item.postingDate,
        item.branchCode,
        item.warehouseCode,
        item.sourceFormat,
        item.status,
      ],
      onSelect: (item) => setState(() => _selectedOpeningStock = item),
      onPageChanged: _handlePageChange,
    );
  }

  Widget _buildDetailsPanel() => DetailsPanel(
        title: _detailsTitle,
        lines: _detailLines,
      );

  Future<void> _openInventoryDetails(InventoryRecord record) =>
      showInventoryDetailsDialog(
        context,
        record: record,
        onOpenInventory: widget.onNavigateToSection == null
            ? null
            : () async => widget.onNavigateToSection!(InventorySection.inventory),
        onViewLedger: widget.onNavigateToSection == null
            ? null
            : () async => widget.onNavigateToSection!(InventorySection.stockLedger),
        onViewTransactions: widget.onNavigateToSection == null
            ? null
            : () async =>
                widget.onNavigateToSection!(InventorySection.transactions),
      );

  String get _detailsTitle => switch (widget.section) {
        InventorySection.inventory || InventorySection.stockSearch =>
          'Inventory details',
        InventorySection.transactions => 'Transaction details',
        InventorySection.stockLedger => 'Ledger details',
        InventorySection.openingStock => 'Opening stock details',
        _ => 'Details',
      };

  List<DetailLine> get _detailLines => switch (widget.section) {
        InventorySection.inventory || InventorySection.stockSearch =>
          _selectedInventory == null
              ? const []
              : [
                  DetailLine('Product', _selectedInventory!.productName),
                  DetailLine('Product code', _selectedInventory!.productCode),
                  DetailLine('Branch', _selectedInventory!.branchName),
                  DetailLine('Warehouse', _selectedInventory!.warehouseName),
                  DetailLine(
                    'Storage',
                    _selectedInventory!.storageNodeName.isEmpty
                        ? '-'
                        : _selectedInventory!.storageNodeName,
                  ),
                  DetailLine('Current quantity', _selectedInventory!.currentQuantity),
                  DetailLine(
                      'Available quantity', _selectedInventory!.availableQuantity),
                  DetailLine(
                      'Reserved quantity', _selectedInventory!.reservedQuantity),
                  DetailLine('Blocked quantity', _selectedInventory!.blockedQuantity),
                  DetailLine('Damaged quantity', _selectedInventory!.damagedQuantity),
                  DetailLine(
                      'Quarantine quantity', _selectedInventory!.quarantineQuantity),
                  DetailLine('In transit', _selectedInventory!.inTransitQuantity),
                  DetailLine('Minimum level', _blankable(_selectedInventory!.minimumLevel)),
                  DetailLine('Maximum level', _blankable(_selectedInventory!.maximumLevel)),
                  DetailLine('Reorder level', _blankable(_selectedInventory!.reorderLevel)),
                  DetailLine('Safety stock', _blankable(_selectedInventory!.safetyStock)),
                  DetailLine(
                    'Last transaction',
                    _blankable(_selectedInventory!.lastTransactionAt),
                  ),
                  DetailLine('Status', _selectedInventory!.status),
                ],
        InventorySection.transactions => _selectedTransaction == null
            ? const []
            : [
                DetailLine('Type', _selectedTransaction!.transactionType),
                DetailLine('Reference', _selectedTransaction!.referenceNumber),
                DetailLine('Reference type', _selectedTransaction!.referenceType),
                DetailLine('Date', _selectedTransaction!.transactionDate),
                DetailLine('Product', _selectedTransaction!.productName),
                DetailLine('Warehouse', _selectedTransaction!.warehouseName),
                DetailLine('Quantity', _selectedTransaction!.quantity),
                DetailLine('Previous current', _selectedTransaction!.previousCurrentQuantity),
                DetailLine('New current', _selectedTransaction!.newCurrentQuantity),
                DetailLine('Previous available', _selectedTransaction!.previousAvailableQuantity),
                DetailLine('New available', _selectedTransaction!.newAvailableQuantity),
                DetailLine('Remarks', _blankable(_selectedTransaction!.remarks)),
              ],
        InventorySection.stockLedger => _selectedLedger == null
            ? const []
            : [
                DetailLine('Ledger transaction', _selectedLedger!.transactionId),
                DetailLine('Type', _selectedLedger!.transactionType),
                DetailLine('Reference', _selectedLedger!.referenceNumber),
                DetailLine('Date', _selectedLedger!.transactionDate),
                DetailLine('Product', _selectedLedger!.productName),
                DetailLine('Quantity', _selectedLedger!.quantity),
                DetailLine('New balance', _selectedLedger!.newCurrentQuantity),
                DetailLine('Created at', _selectedLedger!.createdAt),
              ],
        InventorySection.openingStock => _selectedOpeningStock == null
            ? const []
            : [
                DetailLine('Reference', _selectedOpeningStock!.referenceNumber),
                DetailLine('Posting date', _selectedOpeningStock!.postingDate),
                DetailLine('Branch', _selectedOpeningStock!.branchName),
                DetailLine('Warehouse', _selectedOpeningStock!.warehouseName),
                DetailLine('Source format', _selectedOpeningStock!.sourceFormat),
                DetailLine('Status', _selectedOpeningStock!.status),
                DetailLine('Posted at', _blankable(_selectedOpeningStock!.postedAt)),
                DetailLine('Line count', '${_selectedOpeningStock!.lines.length}'),
                DetailLine('Remarks', _blankable(_selectedOpeningStock!.remarks)),
              ],
        _ => const [],
      };

  Future<void> _editInventoryThresholds() async {
    final InventoryRecord? record = _selectedInventory;
    if (record == null) return;
    final TextEditingController minimum =
        TextEditingController(text: record.minimumLevel);
    final TextEditingController maximum =
        TextEditingController(text: record.maximumLevel);
    final TextEditingController reorder =
        TextEditingController(text: record.reorderLevel);
    final TextEditingController safety =
        TextEditingController(text: record.safetyStock);
    String status = record.status;
    final bool? submitted = await showDialog<bool>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setState) => AlertDialog(
          title: const Text('Edit inventory thresholds'),
          content: SizedBox(
            width: 520,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text('${record.productCode} - ${record.productName}'),
                const SizedBox(height: 12),
                Row(
                  children: [
                    Expanded(
                      child: TextField(
                        controller: minimum,
                        decoration: const InputDecoration(labelText: 'Minimum'),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: TextField(
                        controller: maximum,
                        decoration: const InputDecoration(labelText: 'Maximum'),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                Row(
                  children: [
                    Expanded(
                      child: TextField(
                        controller: reorder,
                        decoration:
                            const InputDecoration(labelText: 'Reorder level'),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: TextField(
                        controller: safety,
                        decoration:
                            const InputDecoration(labelText: 'Safety stock'),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                DropdownButtonFormField<String>(
                  initialValue: status,
                  decoration: const InputDecoration(labelText: 'Status'),
                  items: const ['ACTIVE', 'INACTIVE', 'ARCHIVED']
                      .map(
                        (value) => DropdownMenuItem<String>(
                          value: value,
                          child: Text(value),
                        ),
                      )
                      .toList(),
                  onChanged: (value) => setState(() => status = value ?? status),
                ),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text('Save'),
            ),
          ],
        ),
      ),
    );
    if (submitted != true) return;
    try {
      await widget.api.updateInventoryRecord(record.id, {
        'branch_id': record.branchId,
        'warehouse_id': record.warehouseId,
        'storage_node_id': record.storageNodeId.isEmpty ? null : record.storageNodeId,
        'product_id': record.productId,
        'minimum_level': _nullableNumber(minimum.text),
        'maximum_level': _nullableNumber(maximum.text),
        'reorder_level': _nullableNumber(reorder.text),
        'safety_stock': _nullableNumber(safety.text),
        'status': status,
      });
      if (!mounted) return;
      NotificationService.show(
        context,
        'Inventory thresholds updated.',
        kind: AppNotificationKind.success,
      );
      await _load();
    } on ApiException catch (exception) {
      if (!mounted) return;
      NotificationService.show(
        context,
        exception.message,
        kind: AppNotificationKind.error,
      );
    }
  }

  Future<void> _deleteSelectedInventory() async {
    final InventoryRecord? record = _selectedInventory;
    if (record == null) return;
    final bool confirmed = await showWorkspaceConfirmDialog(
      context,
      title: 'Delete inventory projection',
      message:
          'Delete ${record.productCode} in ${record.warehouseCode}? This only succeeds when no stock or movement history exists.',
      confirmLabel: 'Delete',
    );
    if (!confirmed) return;
    try {
      await widget.api.deleteInventoryRecord(record.id);
      if (!mounted) return;
      NotificationService.show(
        context,
        'Inventory projection deleted.',
        kind: AppNotificationKind.success,
      );
      await _load(requestedPage: 1);
    } on ApiException catch (exception) {
      if (!mounted) return;
      NotificationService.show(
        context,
        exception.message,
        kind: AppNotificationKind.error,
      );
    }
  }

  Future<void> _openAdjustmentDialog() async {
    final _AdjustmentDraft? draft = await showDialog<_AdjustmentDraft>(
      context: context,
      builder: (context) => _AdjustmentDialog(
        branches: _branches,
        warehouses: _warehouses,
        products: _products,
        api: widget.api,
      ),
    );
    if (draft == null) return;
    try {
      await widget.api.createInventoryAdjustment(draft.toJson());
      if (!mounted) return;
      NotificationService.show(
        context,
        'Inventory adjustment posted.',
        kind: AppNotificationKind.success,
      );
      await _load(requestedPage: 1);
    } on ApiException catch (exception) {
      if (!mounted) return;
      NotificationService.show(
        context,
        exception.message,
        kind: AppNotificationKind.error,
      );
    }
  }

  Future<void> _openOpeningStockDialog({
    OpeningStockBatchRecord? existing,
  }) async {
    final _OpeningStockDraft? draft = await showDialog<_OpeningStockDraft>(
      context: context,
      builder: (context) => _OpeningStockDialog(
        api: widget.api,
        branches: _branches,
        warehouses: _warehouses,
        products: _products,
        existing: existing,
      ),
    );
    if (draft == null) return;
    try {
      OpeningStockBatchRecord batch;
      if (existing == null) {
        batch = await widget.api.createOpeningStock(draft.toJson());
      } else {
        batch = await widget.api.updateOpeningStock(existing.id, draft.toJson());
      }
      if (draft.autoPost) {
        batch = await widget.api.postOpeningStock(batch.id);
      }
      if (!mounted) return;
      NotificationService.show(
        context,
        draft.autoPost
            ? 'Opening stock posted successfully.'
            : 'Opening stock draft saved.',
        kind: AppNotificationKind.success,
      );
      _selectedOpeningStock = batch;
      await _load(requestedPage: 1);
    } on ApiException catch (exception) {
      if (!mounted) return;
      NotificationService.show(
        context,
        exception.message,
        kind: AppNotificationKind.error,
      );
    }
  }

  Future<void> _postSelectedOpeningStock() async {
    final OpeningStockBatchRecord? batch = _selectedOpeningStock;
    if (batch == null || batch.isPosted) return;
    try {
      _selectedOpeningStock = await widget.api.postOpeningStock(batch.id);
      if (!mounted) return;
      NotificationService.show(
        context,
        'Opening stock posted.',
        kind: AppNotificationKind.success,
      );
      await _load();
    } on ApiException catch (exception) {
      if (!mounted) return;
      NotificationService.show(
        context,
        exception.message,
        kind: AppNotificationKind.error,
      );
    }
  }

  Future<void> _exportDataset(String dataset) async {
    try {
      final String csv = await widget.api.exportInventory(
        search: _search.text.trim(),
        dataset: dataset,
      );
      await copyTextToClipboard(csv);
      if (!mounted) return;
      NotificationService.show(
        context,
        '${dataset == 'ledger' ? 'Ledger' : 'Inventory'} CSV copied to the clipboard.',
        kind: AppNotificationKind.success,
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

  void _handlePageChange(int rowIndex) {
    final int page = (rowIndex ~/ _rowsPerPage) + 1;
    if (page != _page) {
      _load(requestedPage: page);
    }
  }

  List<WarehouseRecord> get _filteredWarehouses => _branchId == null
      ? _warehouses
      : _warehouses.where((item) => item.branchId == _branchId).toList();

  int get _selectedCount => switch (widget.section) {
        InventorySection.inventory || InventorySection.stockSearch =>
          _selectedInventory == null ? 0 : 1,
        InventorySection.transactions =>
          _selectedTransaction == null ? 0 : 1,
        InventorySection.stockLedger => _selectedLedger == null ? 0 : 1,
        InventorySection.openingStock =>
          _selectedOpeningStock == null ? 0 : 1,
        _ => 0,
      };

  String get _searchHint => switch (widget.section) {
        InventorySection.inventory =>
          'Search by product, branch, warehouse, or storage node',
        InventorySection.stockSearch =>
          'Search current stock levels across branches and warehouses',
        InventorySection.transactions =>
          'Search by reference, product, or transaction type',
        InventorySection.stockLedger =>
          'Search immutable ledger movements',
        InventorySection.openingStock =>
          'Search by reference number or warehouse',
        _ => 'Search',
      };

  Widget _metricCard(String label, String value) => SizedBox(
        width: 180,
        child: Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(label, style: Theme.of(context).textTheme.labelLarge),
                const SizedBox(height: 8),
                Text(value, style: Theme.of(context).textTheme.headlineSmall),
              ],
            ),
          ),
        ),
      );

  Widget _summaryTable(
    String title,
    List<InventoryLocationSummaryRecord> rows,
  ) =>
      Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 12),
              if (rows.isEmpty)
                const Text('No rows available.')
              else
                DataTable(
                  columns: const [
                    DataColumn(label: Text('Code')),
                    DataColumn(label: Text('Name')),
                    DataColumn(label: Text('Current')),
                    DataColumn(label: Text('Available')),
                    DataColumn(label: Text('Reserved')),
                  ],
                  rows: rows
                      .map(
                        (row) => DataRow(
                          cells: [
                            DataCell(Text(row.scopeCode)),
                            DataCell(Text(row.scopeName)),
                            DataCell(Text(row.currentQuantity)),
                            DataCell(Text(row.availableQuantity)),
                            DataCell(Text(row.reservedQuantity)),
                          ],
                        ),
                      )
                      .toList(),
                ),
            ],
          ),
        ),
      );

  Widget _actionCard({
    required String title,
    required String description,
    required String actionLabel,
    required VoidCallback? onPressed,
  }) =>
      Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 8),
              Text(description),
              const Spacer(),
              FilledButton.icon(
                onPressed: onPressed,
                icon: const Icon(Icons.copy_all_outlined),
                label: Text(actionLabel),
              ),
            ],
          ),
        ),
      );

  Widget _lookupField<T>({
    required String label,
    required String? value,
    required List<T> items,
    required String Function(T) itemId,
    required String Function(T) itemLabel,
    required ValueChanged<String?> onChanged,
  }) =>
      SizedBox(
        width: 260,
        child: DropdownButtonFormField<String>(
          initialValue: value,
          decoration: InputDecoration(labelText: label),
          items: [
            const DropdownMenuItem<String>(value: null, child: Text('All')),
            ...items.map(
              (item) => DropdownMenuItem<String>(
                value: itemId(item),
                child: Text(itemLabel(item), overflow: TextOverflow.ellipsis),
              ),
            ),
          ],
          onChanged: onChanged,
        ),
      );
}

String _blankable(String value) => value.isEmpty ? '-' : value;

num? _nullableNumber(String value) {
  final String text = value.trim();
  if (text.isEmpty) {
    return null;
  }
  return num.parse(text);
}

class _InfoTile extends StatelessWidget {
  const _InfoTile({
    required this.icon,
    required this.title,
    required this.message,
  });

  final IconData icon;
  final String title;
  final String message;

  @override
  Widget build(BuildContext context) => Card(
        child: ListTile(
          leading: Icon(icon),
          title: Text(title),
          subtitle: Text(message),
        ),
      );
}

class _AdjustmentDraft {
  const _AdjustmentDraft({
    required this.branchId,
    required this.warehouseId,
    required this.storageNodeId,
    required this.productId,
    required this.quantity,
    required this.referenceNumber,
    required this.transactionDate,
    required this.remarks,
  });

  final String branchId;
  final String warehouseId;
  final String? storageNodeId;
  final String productId;
  final String quantity;
  final String referenceNumber;
  final String transactionDate;
  final String remarks;

  Json toJson() => {
        'branch_id': branchId,
        'warehouse_id': warehouseId,
        'storage_node_id': storageNodeId,
        'product_id': productId,
        'quantity': num.parse(quantity),
        'reference_number': referenceNumber,
        'reference_type': 'ADJUSTMENT',
        'transaction_date': transactionDate,
        if (remarks.trim().isNotEmpty) 'remarks': remarks.trim(),
      };
}

class _AdjustmentDialog extends StatefulWidget {
  const _AdjustmentDialog({
    required this.branches,
    required this.warehouses,
    required this.products,
    required this.api,
  });

  final List<BranchRecord> branches;
  final List<WarehouseRecord> warehouses;
  final List<Product> products;
  final ApiClient api;

  @override
  State<_AdjustmentDialog> createState() => _AdjustmentDialogState();
}

class _AdjustmentDialogState extends State<_AdjustmentDialog> {
  late String? _branchId = widget.branches.isEmpty ? null : widget.branches.first.id;
  late String? _warehouseId = _filteredWarehouses.isEmpty ? null : _filteredWarehouses.first.id;
  String? _storageNodeId;
  late String? _productId = widget.products.isEmpty ? null : widget.products.first.id;
  final TextEditingController _quantity = TextEditingController();
  final TextEditingController _reference = TextEditingController(text: 'ADJ-001');
  final TextEditingController _date = TextEditingController(text: DateTime.now().toIso8601String().split('T').first);
  final TextEditingController _remarks = TextEditingController();
  List<StorageNodeRecord> _storageNodes = const [];

  List<WarehouseRecord> get _filteredWarehouses => _branchId == null
      ? widget.warehouses
      : widget.warehouses.where((item) => item.branchId == _branchId).toList();

  @override
  void initState() {
    super.initState();
    _loadStorageNodes();
  }

  @override
  void dispose() {
    _quantity.dispose();
    _reference.dispose();
    _date.dispose();
    _remarks.dispose();
    super.dispose();
  }

  Future<void> _loadStorageNodes() async {
    final String? warehouseId = _warehouseId;
    if (warehouseId == null) return;
    try {
      final List<StorageNodeRecord> rows = await widget.api.storageNodes(warehouseId);
      if (!mounted) return;
      setState(() {
        _storageNodes = rows;
        _storageNodeId = rows.isEmpty ? null : rows.first.id;
      });
    } on ApiException {
      if (!mounted) return;
      setState(() => _storageNodes = const []);
    }
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: const Text('New inventory adjustment'),
        content: SizedBox(
          width: 620,
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                DropdownButtonFormField<String>(
                  initialValue: _branchId,
                  decoration: const InputDecoration(labelText: 'Branch'),
                  items: widget.branches
                      .map(
                        (item) => DropdownMenuItem<String>(
                          value: item.id,
                          child: Text('${item.code} - ${item.name}'),
                        ),
                      )
                      .toList(),
                  onChanged: (value) {
                    setState(() {
                      _branchId = value;
                      _warehouseId = _filteredWarehouses.isEmpty
                          ? null
                          : _filteredWarehouses.first.id;
                    });
                    _loadStorageNodes();
                  },
                ),
                const SizedBox(height: 12),
                DropdownButtonFormField<String>(
                  initialValue: _warehouseId,
                  decoration: const InputDecoration(labelText: 'Warehouse'),
                  items: _filteredWarehouses
                      .map(
                        (item) => DropdownMenuItem<String>(
                          value: item.id,
                          child: Text('${item.code} - ${item.name}'),
                        ),
                      )
                      .toList(),
                  onChanged: (value) {
                    setState(() => _warehouseId = value);
                    _loadStorageNodes();
                  },
                ),
                const SizedBox(height: 12),
                DropdownButtonFormField<String>(
                  initialValue: _storageNodeId,
                  decoration: const InputDecoration(labelText: 'Storage node'),
                  items: [
                    const DropdownMenuItem<String>(
                      value: null,
                      child: Text('None'),
                    ),
                    ..._storageNodes.map(
                      (item) => DropdownMenuItem<String>(
                        value: item.id,
                        child: Text('${item.code} - ${item.name}'),
                      ),
                    ),
                  ],
                  onChanged: (value) => setState(() => _storageNodeId = value),
                ),
                const SizedBox(height: 12),
                DropdownButtonFormField<String>(
                  initialValue: _productId,
                  decoration: const InputDecoration(labelText: 'Product'),
                  items: widget.products
                      .map(
                        (item) => DropdownMenuItem<String>(
                          value: item.id,
                          child: Text('${item.code} - ${item.name}'),
                        ),
                      )
                      .toList(),
                  onChanged: (value) => setState(() => _productId = value),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _quantity,
                  decoration:
                      const InputDecoration(labelText: 'Quantity (+ or - value)'),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _reference,
                  decoration: const InputDecoration(labelText: 'Reference'),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _date,
                  decoration: const InputDecoration(labelText: 'Transaction date'),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _remarks,
                  decoration: const InputDecoration(labelText: 'Remarks'),
                  maxLines: 2,
                ),
              ],
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () {
              if (_branchId == null ||
                  _warehouseId == null ||
                  _productId == null ||
                  _quantity.text.trim().isEmpty ||
                  _reference.text.trim().isEmpty ||
                  _date.text.trim().isEmpty) {
                return;
              }
              Navigator.pop(
                context,
                _AdjustmentDraft(
                  branchId: _branchId!,
                  warehouseId: _warehouseId!,
                  storageNodeId: _storageNodeId,
                  productId: _productId!,
                  quantity: _quantity.text.trim(),
                  referenceNumber: _reference.text.trim(),
                  transactionDate: _date.text.trim(),
                  remarks: _remarks.text.trim(),
                ),
              );
            },
            child: const Text('Post adjustment'),
          ),
        ],
      );
}

class _OpeningStockDraft {
  const _OpeningStockDraft({
    required this.branchId,
    required this.warehouseId,
    required this.referenceNumber,
    required this.postingDate,
    required this.remarks,
    required this.autoPost,
    required this.lines,
  });

  final String branchId;
  final String warehouseId;
  final String referenceNumber;
  final String postingDate;
  final String remarks;
  final bool autoPost;
  final List<_OpeningStockLineDraft> lines;

  Json toJson() => {
        'branch_id': branchId,
        'warehouse_id': warehouseId,
        'reference_number': referenceNumber,
        'posting_date': postingDate,
        if (remarks.trim().isNotEmpty) 'remarks': remarks.trim(),
        'lines': lines.map((line) => line.toJson()).toList(),
      };
}

class _OpeningStockLineDraft {
  _OpeningStockLineDraft({
    this.productId,
    this.storageNodeId,
    this.quantity = '',
    this.minimumLevel = '',
    this.maximumLevel = '',
    this.reorderLevel = '',
    this.safetyStock = '',
    this.remarks = '',
  });

  String? productId;
  String? storageNodeId;
  String quantity;
  String minimumLevel;
  String maximumLevel;
  String reorderLevel;
  String safetyStock;
  String remarks;

  factory _OpeningStockLineDraft.fromRecord(OpeningStockLineRecord record) =>
      _OpeningStockLineDraft(
        productId: record.productId,
        storageNodeId: record.storageNodeId.isEmpty ? null : record.storageNodeId,
        quantity: record.quantity,
        minimumLevel: record.minimumLevel,
        maximumLevel: record.maximumLevel,
        reorderLevel: record.reorderLevel,
        safetyStock: record.safetyStock,
        remarks: record.remarks,
      );

  Json toJson() => {
        'product_id': productId,
        'storage_node_id': storageNodeId,
        'quantity': num.parse(quantity),
        if (minimumLevel.trim().isNotEmpty)
          'minimum_level': num.parse(minimumLevel.trim()),
        if (maximumLevel.trim().isNotEmpty)
          'maximum_level': num.parse(maximumLevel.trim()),
        if (reorderLevel.trim().isNotEmpty)
          'reorder_level': num.parse(reorderLevel.trim()),
        if (safetyStock.trim().isNotEmpty)
          'safety_stock': num.parse(safetyStock.trim()),
        if (remarks.trim().isNotEmpty) 'remarks': remarks.trim(),
      };
}

class _OpeningStockDialog extends StatefulWidget {
  const _OpeningStockDialog({
    required this.api,
    required this.branches,
    required this.warehouses,
    required this.products,
    this.existing,
  });

  final ApiClient api;
  final List<BranchRecord> branches;
  final List<WarehouseRecord> warehouses;
  final List<Product> products;
  final OpeningStockBatchRecord? existing;

  @override
  State<_OpeningStockDialog> createState() => _OpeningStockDialogState();
}

class _OpeningStockDialogState extends State<_OpeningStockDialog> {
  late String? _branchId =
      widget.existing?.branchId ?? (widget.branches.isEmpty ? null : widget.branches.first.id);
  late String? _warehouseId = widget.existing?.warehouseId ??
      (_filteredWarehouses.isEmpty ? null : _filteredWarehouses.first.id);
  late final TextEditingController _reference = TextEditingController(
    text: widget.existing?.referenceNumber ?? 'OPEN-001',
  );
  late final TextEditingController _postingDate = TextEditingController(
    text: widget.existing?.postingDate ??
        DateTime.now().toIso8601String().split('T').first,
  );
  late final TextEditingController _remarks = TextEditingController(
    text: widget.existing?.remarks ?? '',
  );
  late bool _autoPost = widget.existing?.isPosted ?? false;
  late final List<_OpeningStockLineDraft> _lines =
      widget.existing?.lines.map(_OpeningStockLineDraft.fromRecord).toList() ??
          <_OpeningStockLineDraft>[_OpeningStockLineDraft()];
  List<StorageNodeRecord> _storageNodes = const [];

  List<WarehouseRecord> get _filteredWarehouses => _branchId == null
      ? widget.warehouses
      : widget.warehouses.where((item) => item.branchId == _branchId).toList();

  @override
  void initState() {
    super.initState();
    _loadStorageNodes();
  }

  @override
  void dispose() {
    _reference.dispose();
    _postingDate.dispose();
    _remarks.dispose();
    super.dispose();
  }

  Future<void> _loadStorageNodes() async {
    final String? warehouseId = _warehouseId;
    if (warehouseId == null) return;
    try {
      final List<StorageNodeRecord> nodes =
          await widget.api.storageNodes(warehouseId);
      if (!mounted) return;
      setState(() => _storageNodes = nodes);
    } on ApiException {
      if (!mounted) return;
      setState(() => _storageNodes = const []);
    }
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: Text(widget.existing == null
            ? 'New opening stock'
            : 'Edit opening stock draft'),
        content: SizedBox(
          width: 900,
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: DropdownButtonFormField<String>(
                        initialValue: _branchId,
                        decoration: const InputDecoration(labelText: 'Branch'),
                        items: widget.branches
                            .map(
                              (item) => DropdownMenuItem<String>(
                                value: item.id,
                                child: Text('${item.code} - ${item.name}'),
                              ),
                            )
                            .toList(),
                        onChanged: (value) {
                          setState(() {
                            _branchId = value;
                            _warehouseId = _filteredWarehouses.isEmpty
                                ? null
                                : _filteredWarehouses.first.id;
                          });
                          _loadStorageNodes();
                        },
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: DropdownButtonFormField<String>(
                        initialValue: _warehouseId,
                        decoration:
                            const InputDecoration(labelText: 'Warehouse'),
                        items: _filteredWarehouses
                            .map(
                              (item) => DropdownMenuItem<String>(
                                value: item.id,
                                child: Text('${item.code} - ${item.name}'),
                              ),
                            )
                            .toList(),
                        onChanged: (value) {
                          setState(() => _warehouseId = value);
                          _loadStorageNodes();
                        },
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                Row(
                  children: [
                    Expanded(
                      child: TextField(
                        controller: _reference,
                        decoration:
                            const InputDecoration(labelText: 'Reference'),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: TextField(
                        controller: _postingDate,
                        decoration:
                            const InputDecoration(labelText: 'Posting date'),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _remarks,
                  decoration: const InputDecoration(labelText: 'Remarks'),
                  maxLines: 2,
                ),
                const SizedBox(height: 12),
                FilterChip(
                  label: const Text('Post after save'),
                  selected: _autoPost,
                  onSelected: (value) => setState(() => _autoPost = value),
                ),
                const SizedBox(height: 12),
                for (int index = 0; index < _lines.length; index++) ...[
                  _OpeningStockLineEditor(
                    index: index,
                    line: _lines[index],
                    products: widget.products,
                    storageNodes: _storageNodes,
                    onRemove: _lines.length == 1
                        ? null
                        : () => setState(() => _lines.removeAt(index)),
                  ),
                  const SizedBox(height: 12),
                ],
                Align(
                  alignment: Alignment.centerLeft,
                  child: OutlinedButton.icon(
                    onPressed: () => setState(
                      () => _lines.add(_OpeningStockLineDraft()),
                    ),
                    icon: const Icon(Icons.add),
                    label: const Text('Add line'),
                  ),
                ),
              ],
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () {
              if (_branchId == null ||
                  _warehouseId == null ||
                  _reference.text.trim().isEmpty ||
                  _postingDate.text.trim().isEmpty ||
                  _lines.any((line) =>
                      line.productId == null || line.quantity.trim().isEmpty)) {
                return;
              }
              Navigator.pop(
                context,
                _OpeningStockDraft(
                  branchId: _branchId!,
                  warehouseId: _warehouseId!,
                  referenceNumber: _reference.text.trim(),
                  postingDate: _postingDate.text.trim(),
                  remarks: _remarks.text.trim(),
                  autoPost: _autoPost,
                  lines: _lines,
                ),
              );
            },
            child: Text(widget.existing == null ? 'Save' : 'Update'),
          ),
        ],
      );
}

class _OpeningStockLineEditor extends StatefulWidget {
  const _OpeningStockLineEditor({
    required this.index,
    required this.line,
    required this.products,
    required this.storageNodes,
    this.onRemove,
  });

  final int index;
  final _OpeningStockLineDraft line;
  final List<Product> products;
  final List<StorageNodeRecord> storageNodes;
  final VoidCallback? onRemove;

  @override
  State<_OpeningStockLineEditor> createState() => _OpeningStockLineEditorState();
}

class _OpeningStockLineEditorState extends State<_OpeningStockLineEditor> {
  late final TextEditingController _quantity =
      TextEditingController(text: widget.line.quantity);
  late final TextEditingController _minimum =
      TextEditingController(text: widget.line.minimumLevel);
  late final TextEditingController _maximum =
      TextEditingController(text: widget.line.maximumLevel);
  late final TextEditingController _reorder =
      TextEditingController(text: widget.line.reorderLevel);
  late final TextEditingController _safety =
      TextEditingController(text: widget.line.safetyStock);
  late final TextEditingController _remarks =
      TextEditingController(text: widget.line.remarks);

  @override
  void dispose() {
    _quantity.dispose();
    _minimum.dispose();
    _maximum.dispose();
    _reorder.dispose();
    _safety.dispose();
    _remarks.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Card(
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Text(
                    'Line ${widget.index + 1}',
                    style: Theme.of(context).textTheme.titleSmall,
                  ),
                  const Spacer(),
                  if (widget.onRemove != null)
                    IconButton(
                      onPressed: widget.onRemove,
                      icon: const Icon(Icons.delete_outline),
                    ),
                ],
              ),
              const SizedBox(height: 8),
              DropdownButtonFormField<String>(
                initialValue: widget.line.productId,
                decoration: const InputDecoration(labelText: 'Product'),
                items: widget.products
                    .map(
                      (item) => DropdownMenuItem<String>(
                        value: item.id,
                        child: Text('${item.code} - ${item.name}'),
                      ),
                    )
                    .toList(),
                onChanged: (value) => widget.line.productId = value,
              ),
              const SizedBox(height: 12),
              DropdownButtonFormField<String>(
                initialValue: widget.line.storageNodeId,
                decoration: const InputDecoration(labelText: 'Storage node'),
                items: [
                  const DropdownMenuItem<String>(
                    value: null,
                    child: Text('None'),
                  ),
                  ...widget.storageNodes.map(
                    (item) => DropdownMenuItem<String>(
                      value: item.id,
                      child: Text('${item.code} - ${item.name}'),
                    ),
                  ),
                ],
                onChanged: (value) => widget.line.storageNodeId = value,
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: _quantity,
                      decoration: const InputDecoration(labelText: 'Quantity'),
                      onChanged: (value) => widget.line.quantity = value,
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: TextField(
                      controller: _minimum,
                      decoration: const InputDecoration(labelText: 'Minimum'),
                      onChanged: (value) => widget.line.minimumLevel = value,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: _maximum,
                      decoration: const InputDecoration(labelText: 'Maximum'),
                      onChanged: (value) => widget.line.maximumLevel = value,
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: TextField(
                      controller: _reorder,
                      decoration:
                          const InputDecoration(labelText: 'Reorder level'),
                      onChanged: (value) => widget.line.reorderLevel = value,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: _safety,
                      decoration:
                          const InputDecoration(labelText: 'Safety stock'),
                      onChanged: (value) => widget.line.safetyStock = value,
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: TextField(
                      controller: _remarks,
                      decoration: const InputDecoration(labelText: 'Remarks'),
                      onChanged: (value) => widget.line.remarks = value,
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      );
}
