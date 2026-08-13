import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/api/api_client.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/preferences/desktop_preferences_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/batch_serial.dart';
import '../../models/entities.dart';
import '../workspace/desktop_framework.dart';

enum BatchSerialSection {
  batches,
  lots,
  serials,
  expiryMonitor,
}

class BatchManagementPage extends StatefulWidget {
  const BatchManagementPage({
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
  final BatchSerialSection section;
  final ValueChanged<BatchSerialSection>? onNavigateToSection;

  @override
  State<BatchManagementPage> createState() => _BatchManagementPageState();
}

class _BatchManagementPageState extends State<BatchManagementPage> {
  static const int _rowsPerPage = 20;

  final TextEditingController _search = TextEditingController();
  final FocusNode _searchFocus = FocusNode();

  bool _loading = false;
  String? _error;
  int _page = 1;
  int _total = 0;

  String? _statusFilter;

  List<BatchRecord> _batches = const [];
  BatchRecord? _selectedBatch;

  List<LotRecord> _lots = const [];
  LotRecord? _selectedLot;

  List<SerialRecord> _serials = const [];
  SerialRecord? _selectedSerial;

  BatchSummaryRecord? _batchSummary;
  ExpiryDashboardRecord? _expiryDashboard;

  bool get _canViewBatch => widget.permissions.hasPermission('BATCH_VIEW');
  bool get _canCreateBatch => widget.permissions.hasPermission('BATCH_CREATE');
  bool get _canEditBatch => widget.permissions.hasPermission('BATCH_UPDATE');
  bool get _canDeleteBatch => widget.permissions.hasPermission('BATCH_DELETE');
  bool get _canCreateSerial => widget.permissions.hasPermission('SERIAL_CREATE');
  bool get _canEditSerial => widget.permissions.hasPermission('SERIAL_UPDATE');
  bool get _canDeleteSerial => widget.permissions.hasPermission('SERIAL_DELETE');

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
    if (!widget.hasActiveFirm) return;
    await _load();
  }

  Future<void> _load({int? requestedPage}) async {
    if (!widget.hasActiveFirm) return;
    setState(() {
      _loading = true;
      _error = null;
      _page = requestedPage ?? _page;
    });
    try {
      switch (widget.section) {
        case BatchSerialSection.batches:
          final PagedResult<BatchRecord> result = await widget.api.batches(
            page: _page,
            pageSize: _rowsPerPage,
            search: _search.text.trim(),
            filters: BatchQuery(status: _statusFilter),
          );
          _batches = result.items;
          _total = result.total;
          _selectedBatch = _keepSelection(_selectedBatch?.id, _batches, (b) => b.id);
          try {
            _batchSummary = await widget.api.batchSummary();
          } on ApiException {
            // non-critical
          }
          break;

        case BatchSerialSection.lots:
          final PagedResult<LotRecord> result = await widget.api.lots(
            page: _page,
            pageSize: _rowsPerPage,
            search: _search.text.trim(),
            filters: LotQuery(status: _statusFilter),
          );
          _lots = result.items;
          _total = result.total;
          _selectedLot = _keepSelection(_selectedLot?.id, _lots, (l) => l.id);
          break;

        case BatchSerialSection.serials:
          final PagedResult<SerialRecord> result = await widget.api.serials(
            page: _page,
            pageSize: _rowsPerPage,
            search: _search.text.trim(),
            filters: SerialQuery(status: _statusFilter),
          );
          _serials = result.items;
          _total = result.total;
          _selectedSerial =
              _keepSelection(_selectedSerial?.id, _serials, (s) => s.id);
          break;

        case BatchSerialSection.expiryMonitor:
          try {
            _expiryDashboard = await widget.api.expiryDashboard();
          } on ApiException {
            // handled below
          }
          final PagedResult<BatchRecord> nearExpiry = await widget.api.batches(
            page: _page,
            pageSize: _rowsPerPage,
          );
          _batches = nearExpiry.items;
          _total = nearExpiry.total;
          break;
      }
      if (mounted) setState(() {});
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() => _error = exception.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  T? _keepSelection<T>(String? id, List<T> items, String Function(T) idOf) {
    if (id == null) return null;
    for (final T item in items) {
      if (idOf(item) == id) return item;
    }
    return null;
  }

  void _handlePageChange(int offset) {
    final int newPage = (offset ~/ _rowsPerPage) + 1;
    if (newPage != _page) _load(requestedPage: newPage);
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.hasActiveFirm) {
      return const StandardEmptyState(type: EmptyStateType.noFirmSelected);
    }
    return switch (widget.section) {
      BatchSerialSection.expiryMonitor => _buildExpiryDashboard(),
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
        // Selecting a row selects it; opening one is what double-click and
        // the row's eye icon are for. The panel re-read a record the user had
        // only pointed at, and took ~300px of the grid to do it.
        detailsPanel: null,
        statusBar: WorkspaceStatusBar(
          total: _total,
          selected: _selectedCount > 0,
          selectedCount: _selectedCount,
          message: _loading ? 'Loading...' : null,
        ),
      );

  String get _searchHint => switch (widget.section) {
        BatchSerialSection.batches => 'Search batch number, product…',
        BatchSerialSection.lots => 'Search lot number, product…',
        BatchSerialSection.serials => 'Search serial number, product…',
        BatchSerialSection.expiryMonitor => 'Search expiring batches…',
      };

  int get _selectedCount => switch (widget.section) {
        BatchSerialSection.batches => _selectedBatch == null ? 0 : 1,
        BatchSerialSection.lots => _selectedLot == null ? 0 : 1,
        BatchSerialSection.serials => _selectedSerial == null ? 0 : 1,
        BatchSerialSection.expiryMonitor => 0,
      };

  Widget _buildToolbar() => Wrap(
        spacing: 8,
        children: [
          if (widget.section == BatchSerialSection.batches && _canCreateBatch)
            FilledButton.icon(
              onPressed: _openCreateBatchDialog,
              icon: const Icon(Icons.add),
              label: const Text('Add Batch'),
            ),
          if (widget.section == BatchSerialSection.lots && _canCreateBatch)
            FilledButton.icon(
              onPressed: _openCreateLotDialog,
              icon: const Icon(Icons.add),
              label: const Text('Add Lot'),
            ),
          if (widget.section == BatchSerialSection.serials && _canCreateSerial)
            FilledButton.icon(
              onPressed: _openCreateSerialDialog,
              icon: const Icon(Icons.add),
              label: const Text('Add Serial'),
            ),
          OutlinedButton.icon(
            onPressed: _load,
            icon: const Icon(Icons.refresh),
            label: const Text('Refresh'),
          ),
        ],
      );

  Widget _buildFilterPanel() {
    final List<String> statuses = switch (widget.section) {
      BatchSerialSection.batches || BatchSerialSection.expiryMonitor => [
          'AVAILABLE',
          'RESERVED',
          'BLOCKED',
          'QUARANTINE',
          'EXPIRED',
          'DAMAGED',
          'RECALLED',
          'RETURNED',
          'DESTROYED',
        ],
      BatchSerialSection.lots => ['ACTIVE', 'CLOSED', 'CANCELLED'],
      BatchSerialSection.serials => [
          'AVAILABLE',
          'RESERVED',
          'SOLD',
          'INSTALLED',
          'RETURNED',
          'REPAIRED',
          'SCRAPPED',
          'LOST',
        ],
    };

    return FilterPanel(
      onApply: () => _load(requestedPage: 1),
      onClear: () {
        setState(() => _statusFilter = null);
        _load(requestedPage: 1);
      },
      children: [
        SizedBox(
          width: 180,
          child: DropdownButtonFormField<String>(
            initialValue: _statusFilter,
            decoration: const InputDecoration(labelText: 'Status'),
            items: [
              const DropdownMenuItem<String>(
                  value: null, child: Text('All statuses')),
              ...statuses.map(
                (s) => DropdownMenuItem<String>(value: s, child: Text(s)),
              ),
            ],
            onChanged: (value) => setState(() => _statusFilter = value),
          ),
        ),
      ],
    );
  }

  Widget _buildPrimaryContent() {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_error != null) {
      return WorkspaceEmptyState(
          title: 'Unable to load data', message: _error!);
    }
    return switch (widget.section) {
      BatchSerialSection.batches => _buildBatchGrid(),
      BatchSerialSection.lots => _buildLotGrid(),
      BatchSerialSection.serials => _buildSerialGrid(),
      BatchSerialSection.expiryMonitor => _buildBatchGrid(),
    };
  }

  /// The batch counts the list already fetches on every load.
  ///
  /// `batchSummary()` was called each time the batch section loaded and the
  /// result thrown away, so the screen paid for the request and showed none of
  /// it. The expired count is worth surfacing in particular: it is derived from
  /// the expiry date rather than from a status nothing ever sets.
  Widget _buildBatchSummary() {
    final BatchSummaryRecord? summary = _batchSummary;
    if (summary == null) {
      return const SizedBox.shrink();
    }
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Row(
        children: [
          Expanded(
            child: _expiryMetricCard(
                'Total Batches', '${summary.totalBatches}', Colors.blueGrey),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: _expiryMetricCard(
                'Near Expiry', '${summary.nearExpiry}', Colors.orange),
          ),
          const SizedBox(width: 12),
          Expanded(
            child:
                _expiryMetricCard('Expired', '${summary.expired}', Colors.red),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: _expiryMetricCard(
                'Quarantine', '${summary.quarantine}', Colors.purple),
          ),
        ],
      ),
    );
  }

  Widget _buildBatchGrid() {
    if (_batches.isEmpty) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _buildBatchSummary(),
          Expanded(
            child: StandardEmptyState(
              type: _search.text.trim().isEmpty
                  ? EmptyStateType.noRecords
                  : EmptyStateType.noSearchResults,
            ),
          ),
        ],
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _buildBatchSummary(),
        Expanded(child: _buildBatchTable()),
      ],
    );
  }

  Widget _buildBatchTable() {
    return EnterpriseDataGrid<BatchRecord>(
      items: _batches,
      total: _total,
      pageOffset: (_page - 1) * _rowsPerPage,
      rowsPerPage: _rowsPerPage,
      columns: const [
        GridColumn(key: 'batch_number', label: 'Batch #'),
        GridColumn(key: 'product', label: 'Product'),
        GridColumn(key: 'status', label: 'Status'),
        GridColumn(key: 'quantity', label: 'Qty'),
        GridColumn(key: 'available', label: 'Available'),
        GridColumn(key: 'expiry', label: 'Expiry Date'),
        GridColumn(key: 'warehouse', label: 'Warehouse'),
      ],
      id: (b) => b.id,
      selectedId: _selectedBatch?.id,
      cells: (b) => [
        b.batchNumber,
        // A product whose code and name are both missing -- soft-deleted, or
        // an older record -- would otherwise render as a bare " - ".
        _productLabel(b),
        b.status,
        b.quantity,
        b.availableQuantity,
        b.expiryDate.isNotEmpty ? b.expiryDate : '—',
        b.warehouseName.isNotEmpty ? b.warehouseName : '—',
      ],
      onSelect: (b) => setState(() => _selectedBatch = b),
      onPageChanged: _handlePageChange,
      onOpen: _canViewBatch ? (b) => _openBatchDetailsDialog(b) : null,
      contextActions: [
        WorkspaceContextAction.view,
        if (_canEditBatch) WorkspaceContextAction.edit,
        WorkspaceContextAction.copy,
        if (_canDeleteBatch) WorkspaceContextAction.delete,
      ],
      onContextAction: (action, b) {
        switch (action) {
          case WorkspaceContextAction.view:
            _openBatchDetailsDialog(b);
          case WorkspaceContextAction.edit:
            _openEditBatchDialog(b);
          case WorkspaceContextAction.copy:
            _copyToClipboard(b.batchNumber, 'Batch number');
          case WorkspaceContextAction.delete:
            _deleteBatch(b);
          default:
            break;
        }
      },
    );
  }

  Widget _buildLotGrid() {
    if (_lots.isEmpty) {
      return StandardEmptyState(
        type: _search.text.trim().isEmpty
            ? EmptyStateType.noRecords
            : EmptyStateType.noSearchResults,
      );
    }
    return EnterpriseDataGrid<LotRecord>(
      items: _lots,
      total: _total,
      pageOffset: (_page - 1) * _rowsPerPage,
      rowsPerPage: _rowsPerPage,
      columns: const [
        GridColumn(key: 'lot_number', label: 'Lot #'),
        GridColumn(key: 'product', label: 'Product'),
        GridColumn(key: 'type', label: 'Type'),
        GridColumn(key: 'status', label: 'Status'),
        GridColumn(key: 'quantity', label: 'Qty'),
        GridColumn(key: 'expiry', label: 'Expiry Date'),
      ],
      id: (l) => l.id,
      selectedId: _selectedLot?.id,
      cells: (l) => [
        l.lotNumber,
        '${l.productCode} - ${l.productName}',
        l.lotType,
        l.status,
        l.quantity,
        l.expiryDate.isNotEmpty ? l.expiryDate : '—',
      ],
      onSelect: (l) => setState(() => _selectedLot = l),
      onPageChanged: _handlePageChange,
      onOpen: _canViewBatch ? (l) => _openLotDetailsDialog(l) : null,
      contextActions: [
        WorkspaceContextAction.view,
        if (_canEditBatch) WorkspaceContextAction.edit,
        WorkspaceContextAction.copy,
        if (_canDeleteBatch) WorkspaceContextAction.delete,
      ],
      onContextAction: (action, l) {
        switch (action) {
          case WorkspaceContextAction.view:
            _openLotDetailsDialog(l);
          case WorkspaceContextAction.edit:
            _openEditLotDialog(l);
          case WorkspaceContextAction.copy:
            _copyToClipboard(l.lotNumber, 'Lot number');
          case WorkspaceContextAction.delete:
            _deleteLot(l);
          default:
            break;
        }
      },
    );
  }

  Widget _buildSerialGrid() {
    if (_serials.isEmpty) {
      return StandardEmptyState(
        type: _search.text.trim().isEmpty
            ? EmptyStateType.noRecords
            : EmptyStateType.noSearchResults,
      );
    }
    return EnterpriseDataGrid<SerialRecord>(
      items: _serials,
      total: _total,
      pageOffset: (_page - 1) * _rowsPerPage,
      rowsPerPage: _rowsPerPage,
      columns: const [
        GridColumn(key: 'serial', label: 'Serial #'),
        GridColumn(key: 'product', label: 'Product'),
        GridColumn(key: 'status', label: 'Status'),
        GridColumn(key: 'warranty_end', label: 'Warranty End'),
        GridColumn(key: 'batch', label: 'Batch'),
        GridColumn(key: 'warehouse', label: 'Warehouse'),
      ],
      id: (s) => s.id,
      selectedId: _selectedSerial?.id,
      cells: (s) => [
        s.serialNumber,
        '${s.productCode} - ${s.productName}',
        s.status,
        s.warrantyEnd.isNotEmpty ? s.warrantyEnd : '—',
        s.batchNumber.isNotEmpty ? s.batchNumber : '—',
        s.warehouseName.isNotEmpty ? s.warehouseName : '—',
      ],
      onSelect: (s) => setState(() => _selectedSerial = s),
      onPageChanged: _handlePageChange,
      onOpen: _canCreateSerial ? (s) => _openSerialDetailsDialog(s) : null,
      contextActions: [
        WorkspaceContextAction.view,
        if (_canEditSerial) WorkspaceContextAction.edit,
        WorkspaceContextAction.copy,
        if (_canDeleteSerial) WorkspaceContextAction.delete,
      ],
      onContextAction: (action, s) {
        switch (action) {
          case WorkspaceContextAction.view:
            _openSerialDetailsDialog(s);
          case WorkspaceContextAction.edit:
            _openEditSerialDialog(s);
          case WorkspaceContextAction.copy:
            _copyToClipboard(s.serialNumber, 'Serial number');
          case WorkspaceContextAction.delete:
            _deleteSerial(s);
          default:
            break;
        }
      },
    );
  }

  /// Name the product a batch holds, however much of it the server knew.
  String _productLabel(BatchRecord batch) {
    if (batch.productCode.isEmpty && batch.productName.isEmpty) return '—';
    if (batch.productCode.isEmpty) return batch.productName;
    if (batch.productName.isEmpty) return batch.productCode;
    return '${batch.productCode} - ${batch.productName}';
  }

  /// What a batche's details are, in one place.
  ///
  /// The dialog renders these; they were the selection panel's lines before it
  /// was removed, so opening a row shows what pointing at one used to.
  List<DetailLine> _batchLines(BatchRecord batch) =>
      [
                DetailLine('Batch #', batch.batchNumber),
                DetailLine('Product', batch.productName),
                DetailLine('Status', batch.status),
                DetailLine('Quantity', batch.quantity),
                DetailLine('Available', batch.availableQuantity),
                DetailLine('Reserved', batch.reservedQuantity),
                if (batch.expiryDate.isNotEmpty)
                  DetailLine('Expiry', batch.expiryDate),
                if (batch.manufacturingDate.isNotEmpty)
                  DetailLine('Mfg Date', batch.manufacturingDate),
                if (batch.warehouseName.isNotEmpty)
                  DetailLine('Warehouse', batch.warehouseName),
                if (batch.branchName.isNotEmpty)
                  DetailLine('Branch', batch.branchName),
                if (batch.supplierBatch.isNotEmpty)
                  DetailLine('Supplier Batch', batch.supplierBatch),
                if (batch.shelfLifeDays != null)
                  DetailLine(
                      'Shelf Life', '${batch.shelfLifeDays} days'),
                if (batch.remarks.isNotEmpty)
                  DetailLine('Remarks', batch.remarks),
                DetailLine('Created', batch.createdAt),
              ];

  /// What a lot's details are, in one place.
  ///
  /// The dialog renders these; they were the selection panel's lines before it
  /// was removed, so opening a row shows what pointing at one used to.
  List<DetailLine> _lotLines(LotRecord lot) =>
      [
                DetailLine('Lot #', lot.lotNumber),
                DetailLine('Product', lot.productName),
                DetailLine('Type', lot.lotType),
                DetailLine('Status', lot.status),
                DetailLine('Quantity', lot.quantity),
                if (lot.expiryDate.isNotEmpty)
                  DetailLine('Expiry', lot.expiryDate),
                if (lot.productionDate.isNotEmpty)
                  DetailLine('Production Date', lot.productionDate),
                if (lot.warehouseName.isNotEmpty)
                  DetailLine('Warehouse', lot.warehouseName),
                if (lot.remarks.isNotEmpty)
                  DetailLine('Remarks', lot.remarks),
                DetailLine('Created', lot.createdAt),
              ];

  /// What a serial's details are, in one place.
  List<DetailLine> _serialLines(SerialRecord serial) =>
      [
                DetailLine('Serial #', serial.serialNumber),
                DetailLine('Product', serial.productName),
                DetailLine('Status', serial.status),
                if (serial.batchNumber.isNotEmpty)
                  DetailLine('Batch', serial.batchNumber),
                if (serial.warrantyStart.isNotEmpty)
                  DetailLine('Warranty Start', serial.warrantyStart),
                if (serial.warrantyEnd.isNotEmpty)
                  DetailLine('Warranty End', serial.warrantyEnd),
                if (serial.manufacturedDate.isNotEmpty)
                  DetailLine('Manufactured', serial.manufacturedDate),
                if (serial.warehouseName.isNotEmpty)
                  DetailLine('Warehouse', serial.warehouseName),
                if (serial.currentOwner.isNotEmpty)
                  DetailLine('Owner', serial.currentOwner),
                if (serial.assetReference.isNotEmpty)
                  DetailLine('Asset Ref', serial.assetReference),
                if (serial.remarks.isNotEmpty)
                  DetailLine('Remarks', serial.remarks),
                DetailLine('Created', serial.createdAt),
              ];

  Widget _buildExpiryDashboard() {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_error != null) {
      return WorkspaceEmptyState(
          title: 'Failed to load expiry data', message: _error!);
    }
    final ExpiryDashboardRecord dash = _expiryDashboard ??
        const ExpiryDashboardRecord(
          expiredToday: 0,
          expireIn7Days: 0,
          expireIn30Days: 0,
          totalExpired: 0,
          quarantine: 0,
          recalled: 0,
        );
    return WorkspaceLayout(
      title: 'Expiry Monitor',
      description:
          'Track expiring, expired, quarantined, and recalled stock at a glance.',
      breadcrumbs: const ['Workspace', 'Inventory', 'Expiry Monitor'],
      toolbar: OutlinedButton.icon(
        onPressed: _load,
        icon: const Icon(Icons.refresh),
        label: const Text('Refresh'),
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
                _expiryMetricCard('Expired Today', '${dash.expiredToday}',
                    Colors.red),
                _expiryMetricCard('Expire in 7 Days', '${dash.expireIn7Days}',
                    Colors.orange),
                _expiryMetricCard('Expire in 30 Days',
                    '${dash.expireIn30Days}', Colors.amber),
                _expiryMetricCard(
                    'Total Expired', '${dash.totalExpired}', Colors.red),
                _expiryMetricCard(
                    'Quarantine', '${dash.quarantine}', Colors.purple),
                _expiryMetricCard(
                    'Recalled', '${dash.recalled}', Colors.deepOrange),
              ],
            ),
            const SizedBox(height: 24),
            const Text(
              'All Batches',
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: 12),
            if (_batches.isEmpty)
              const Center(child: Text('No batch data available.'))
            else
              _buildBatchGrid(),
          ],
        ),
      ),
    );
  }

  Widget _expiryMetricCard(String label, String value, Color color) => Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(label,
                  style: const TextStyle(fontSize: 12, color: Colors.grey)),
              const SizedBox(height: 4),
              Text(
                value,
                style: TextStyle(
                    fontSize: 28,
                    fontWeight: FontWeight.bold,
                    color: color),
              ),
            ],
          ),
        ),
      );

  void _copyToClipboard(String value, String label) {
    Clipboard.setData(ClipboardData(text: value));
    NotificationService.show(
      context,
      '$label copied to clipboard.',
      kind: AppNotificationKind.success,
    );
  }

  // ── Batch dialogs ────────────────────────────────────────────────────────

  void _openBatchDetailsDialog(BatchRecord batch) {
    showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        icon: const Icon(Icons.inventory_2_outlined),
        title: Text('Batch: ${batch.batchNumber}'),
        content: SizedBox(
          width: 520,
          child: SingleChildScrollView(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                for (final DetailLine line in _batchLines(batch))
                  _infoRow(line.label, line.value),
              ],
            ),
          ),
        ),
        actions: [
          if (_canEditBatch)
            TextButton(
              onPressed: () {
                Navigator.pop(context);
                _openEditBatchDialog(batch);
              },
              child: const Text('Edit'),
            ),
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Close'),
          ),
        ],
      ),
    );
  }

  void _openCreateBatchDialog() {
    showDialog<bool>(
      context: context,
      builder: (_) => _BatchFormDialog(api: widget.api),
    ).then((created) {
      if (created == true) _load();
    });
  }

  void _openEditBatchDialog(BatchRecord batch) {
    showDialog<bool>(
      context: context,
      builder: (_) => _BatchFormDialog(api: widget.api, existing: batch),
    ).then((updated) {
      if (updated == true) _load();
    });
  }

  Future<void> _deleteBatch(BatchRecord batch) async {
    final bool? confirmed = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Delete batch?'),
        content:
            Text('Delete batch "${batch.batchNumber}"? This cannot be undone.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('Cancel')),
          FilledButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text('Delete')),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    try {
      await widget.api.deleteBatch(batch.id);
      if (!mounted) return;
      NotificationService.show(context, 'Batch deleted.',
          kind: AppNotificationKind.success);
      await _load();
    } on ApiException catch (exception) {
      if (!mounted) return;
      NotificationService.show(context, exception.message,
          kind: AppNotificationKind.error);
    }
  }

  // ── Lot dialogs ──────────────────────────────────────────────────────────

  void _openLotDetailsDialog(LotRecord lot) {
    showDetailLinesDialog(
      context,
      title: 'Lot: ${lot.lotNumber}',
      lines: _lotLines(lot),
      icon: Icons.layers_outlined,
    );
  }

  void _openCreateLotDialog() {
    showDialog<bool>(
      context: context,
      builder: (_) => _LotFormDialog(api: widget.api),
    ).then((created) {
      if (created == true) _load();
    });
  }

  void _openEditLotDialog(LotRecord lot) {
    showDialog<bool>(
      context: context,
      builder: (_) => _LotFormDialog(api: widget.api, existing: lot),
    ).then((updated) {
      if (updated == true) _load();
    });
  }

  Future<void> _deleteLot(LotRecord lot) async {
    final bool? confirmed = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Delete lot?'),
        content: Text('Delete lot "${lot.lotNumber}"?'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('Cancel')),
          FilledButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text('Delete')),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    try {
      await widget.api.deleteLot(lot.id);
      if (!mounted) return;
      NotificationService.show(context, 'Lot deleted.',
          kind: AppNotificationKind.success);
      await _load();
    } on ApiException catch (exception) {
      if (!mounted) return;
      NotificationService.show(context, exception.message,
          kind: AppNotificationKind.error);
    }
  }

  // ── Serial dialogs ───────────────────────────────────────────────────────

  void _openSerialDetailsDialog(SerialRecord serial) {
    showDetailLinesDialog(
      context,
      title: 'Serial: ${serial.serialNumber}',
      lines: _serialLines(serial),
      icon: Icons.qr_code_2_outlined,
    );
  }

  void _openCreateSerialDialog() {
    showDialog<bool>(
      context: context,
      builder: (_) => _SerialFormDialog(api: widget.api),
    ).then((created) {
      if (created == true) _load();
    });
  }

  void _openEditSerialDialog(SerialRecord serial) {
    showDialog<bool>(
      context: context,
      builder: (_) => _SerialFormDialog(api: widget.api, existing: serial),
    ).then((updated) {
      if (updated == true) _load();
    });
  }

  Future<void> _deleteSerial(SerialRecord serial) async {
    final bool? confirmed = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Delete serial number?'),
        content: Text('Delete serial "${serial.serialNumber}"?'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('Cancel')),
          FilledButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text('Delete')),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    try {
      await widget.api.deleteSerial(serial.id);
      if (!mounted) return;
      NotificationService.show(context, 'Serial deleted.',
          kind: AppNotificationKind.success);
      await _load();
    } on ApiException catch (exception) {
      if (!mounted) return;
      NotificationService.show(context, exception.message,
          kind: AppNotificationKind.error);
    }
  }

  Widget _infoRow(String label, String value) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 3),
        child: Row(
          children: [
            SizedBox(
              width: 130,
              child: Text(label,
                  style: const TextStyle(fontWeight: FontWeight.w500)),
            ),
            Expanded(child: SelectableText(value)),
          ],
        ),
      );
}

// ── Form dialogs ─────────────────────────────────────────────────────────────

class _BatchFormDialog extends StatefulWidget {
  const _BatchFormDialog({required this.api, this.existing});
  final ApiClient api;
  final BatchRecord? existing;

  @override
  State<_BatchFormDialog> createState() => _BatchFormDialogState();
}

class _BatchFormDialogState extends State<_BatchFormDialog> {
  final _formKey = GlobalKey<FormState>();
  final _batchNumber = TextEditingController();
  final _supplierBatch = TextEditingController();
  final _expiryDate = TextEditingController();
  final _manufacturingDate = TextEditingController();
  final _remarks = TextEditingController();
  String _status = 'AVAILABLE';
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    if (widget.existing case final BatchRecord b) {
      _batchNumber.text = b.batchNumber;
      _supplierBatch.text = b.supplierBatch;
      _expiryDate.text = b.expiryDate;
      _manufacturingDate.text = b.manufacturingDate;
      _remarks.text = b.remarks;
      _status = b.status;
    }
  }

  @override
  void dispose() {
    _batchNumber.dispose();
    _supplierBatch.dispose();
    _expiryDate.dispose();
    _manufacturingDate.dispose();
    _remarks.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    setState(() => _saving = true);
    try {
      final Json data = {
        'batch_number': _batchNumber.text.trim(),
        if (_supplierBatch.text.isNotEmpty)
          'supplier_batch': _supplierBatch.text.trim(),
        if (_expiryDate.text.isNotEmpty) 'expiry_date': _expiryDate.text.trim(),
        if (_manufacturingDate.text.isNotEmpty)
          'manufacturing_date': _manufacturingDate.text.trim(),
        'status': _status,
        if (_remarks.text.isNotEmpty) 'remarks': _remarks.text.trim(),
      };
      if (widget.existing != null) {
        await widget.api.updateBatch(widget.existing!.id, data);
      } else {
        await widget.api.createBatch(data);
      }
      if (!mounted) return;
      Navigator.pop(context, true);
    } on ApiException catch (exception) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(exception.message)));
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: Text(widget.existing == null ? 'Add Batch' : 'Edit Batch'),
        content: SizedBox(
          width: 480,
          child: Form(
            key: _formKey,
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  TextFormField(
                    controller: _batchNumber,
                    decoration:
                        const InputDecoration(labelText: 'Batch Number *'),
                    validator: (v) =>
                        v == null || v.trim().isEmpty ? 'Required' : null,
                  ),
                  const SizedBox(height: 12),
                  TextFormField(
                    controller: _supplierBatch,
                    decoration:
                        const InputDecoration(labelText: 'Supplier Batch'),
                  ),
                  // Quantity is not editable here. What a batch holds comes
                  // from the movements that put it there -- a goods receipt,
                  // a dispatch, an adjustment -- so typing it would create
                  // stock the ledger cannot explain.
                  if (widget.existing case final BatchRecord b) ...[
                    const SizedBox(height: 12),
                    Align(
                      alignment: Alignment.centerLeft,
                      child: Text(
                        'In stock: ${b.quantity} '
                        '(${b.availableQuantity} available) — from stock movements',
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                    ),
                  ],
                  const SizedBox(height: 12),
                  TextFormField(
                    controller: _manufacturingDate,
                    decoration: const InputDecoration(
                        labelText: 'Manufacturing Date (YYYY-MM-DD)'),
                  ),
                  const SizedBox(height: 12),
                  TextFormField(
                    controller: _expiryDate,
                    decoration: const InputDecoration(
                        labelText: 'Expiry Date (YYYY-MM-DD)'),
                  ),
                  const SizedBox(height: 12),
                  DropdownButtonFormField<String>(
                    initialValue: _status,
                    decoration: const InputDecoration(labelText: 'Status'),
                    items: const [
                      DropdownMenuItem(
                          value: 'AVAILABLE', child: Text('Available')),
                      DropdownMenuItem(
                          value: 'BLOCKED', child: Text('Blocked')),
                      DropdownMenuItem(
                          value: 'QUARANTINE', child: Text('Quarantine')),
                    ],
                    onChanged: (v) => setState(() => _status = v ?? _status),
                  ),
                  const SizedBox(height: 12),
                  TextFormField(
                    controller: _remarks,
                    decoration: const InputDecoration(labelText: 'Remarks'),
                    maxLines: 2,
                  ),
                ],
              ),
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: _saving ? null : () => Navigator.pop(context, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: _saving ? null : _save,
            child: _saving
                ? const SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(strokeWidth: 2))
                : Text(widget.existing == null ? 'Create' : 'Save'),
          ),
        ],
      );
}

class _LotFormDialog extends StatefulWidget {
  const _LotFormDialog({required this.api, this.existing});
  final ApiClient api;
  final LotRecord? existing;

  @override
  State<_LotFormDialog> createState() => _LotFormDialogState();
}

class _LotFormDialogState extends State<_LotFormDialog> {
  final _formKey = GlobalKey<FormState>();
  final _lotNumber = TextEditingController();
  final _quantity = TextEditingController();
  final _expiryDate = TextEditingController();
  final _productionDate = TextEditingController();
  final _remarks = TextEditingController();
  String _lotType = 'PRODUCTION';
  String _status = 'ACTIVE';
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    if (widget.existing case final LotRecord l) {
      _lotNumber.text = l.lotNumber;
      _quantity.text = l.quantity;
      _expiryDate.text = l.expiryDate;
      _productionDate.text = l.productionDate;
      _remarks.text = l.remarks;
      _lotType = l.lotType;
      _status = l.status;
    }
  }

  @override
  void dispose() {
    _lotNumber.dispose();
    _quantity.dispose();
    _expiryDate.dispose();
    _productionDate.dispose();
    _remarks.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    setState(() => _saving = true);
    try {
      final Json data = {
        'lot_number': _lotNumber.text.trim(),
        'quantity': double.tryParse(_quantity.text.trim()) ?? 0,
        'lot_type': _lotType,
        'status': _status,
        if (_expiryDate.text.isNotEmpty) 'expiry_date': _expiryDate.text.trim(),
        if (_productionDate.text.isNotEmpty)
          'production_date': _productionDate.text.trim(),
        if (_remarks.text.isNotEmpty) 'remarks': _remarks.text.trim(),
      };
      if (widget.existing != null) {
        await widget.api.updateLot(widget.existing!.id, data);
      } else {
        await widget.api.createLot(data);
      }
      if (!mounted) return;
      Navigator.pop(context, true);
    } on ApiException catch (exception) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(exception.message)));
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: Text(widget.existing == null ? 'Add Lot' : 'Edit Lot'),
        content: SizedBox(
          width: 480,
          child: Form(
            key: _formKey,
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  TextFormField(
                    controller: _lotNumber,
                    decoration:
                        const InputDecoration(labelText: 'Lot Number *'),
                    validator: (v) =>
                        v == null || v.trim().isEmpty ? 'Required' : null,
                  ),
                  const SizedBox(height: 12),
                  DropdownButtonFormField<String>(
                    initialValue: _lotType,
                    decoration: const InputDecoration(labelText: 'Type'),
                    items: const [
                      DropdownMenuItem(
                          value: 'PRODUCTION', child: Text('Production')),
                      DropdownMenuItem(value: 'MIXING', child: Text('Mixing')),
                      DropdownMenuItem(
                          value: 'MANUFACTURING', child: Text('Manufacturing')),
                    ],
                    onChanged: (v) => setState(() => _lotType = v ?? _lotType),
                  ),
                  const SizedBox(height: 12),
                  TextFormField(
                    controller: _quantity,
                    decoration: const InputDecoration(labelText: 'Quantity'),
                    keyboardType: TextInputType.number,
                  ),
                  const SizedBox(height: 12),
                  TextFormField(
                    controller: _productionDate,
                    decoration: const InputDecoration(
                        labelText: 'Production Date (YYYY-MM-DD)'),
                  ),
                  const SizedBox(height: 12),
                  TextFormField(
                    controller: _expiryDate,
                    decoration: const InputDecoration(
                        labelText: 'Expiry Date (YYYY-MM-DD)'),
                  ),
                  const SizedBox(height: 12),
                  TextFormField(
                    controller: _remarks,
                    decoration: const InputDecoration(labelText: 'Remarks'),
                    maxLines: 2,
                  ),
                ],
              ),
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: _saving ? null : () => Navigator.pop(context, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: _saving ? null : _save,
            child: _saving
                ? const SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(strokeWidth: 2))
                : Text(widget.existing == null ? 'Create' : 'Save'),
          ),
        ],
      );
}

class _SerialFormDialog extends StatefulWidget {
  const _SerialFormDialog({required this.api, this.existing});
  final ApiClient api;
  final SerialRecord? existing;

  @override
  State<_SerialFormDialog> createState() => _SerialFormDialogState();
}

class _SerialFormDialogState extends State<_SerialFormDialog> {
  final _formKey = GlobalKey<FormState>();
  final _serialNumber = TextEditingController();
  final _warrantyStart = TextEditingController();
  final _warrantyEnd = TextEditingController();
  final _manufacturedDate = TextEditingController();
  final _currentOwner = TextEditingController();
  final _assetReference = TextEditingController();
  final _remarks = TextEditingController();
  String _status = 'AVAILABLE';
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    if (widget.existing case final SerialRecord s) {
      _serialNumber.text = s.serialNumber;
      _warrantyStart.text = s.warrantyStart;
      _warrantyEnd.text = s.warrantyEnd;
      _manufacturedDate.text = s.manufacturedDate;
      _currentOwner.text = s.currentOwner;
      _assetReference.text = s.assetReference;
      _remarks.text = s.remarks;
      _status = s.status;
    }
  }

  @override
  void dispose() {
    _serialNumber.dispose();
    _warrantyStart.dispose();
    _warrantyEnd.dispose();
    _manufacturedDate.dispose();
    _currentOwner.dispose();
    _assetReference.dispose();
    _remarks.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    setState(() => _saving = true);
    try {
      final Json data = {
        'serial_number': _serialNumber.text.trim(),
        'status': _status,
        if (_warrantyStart.text.isNotEmpty)
          'warranty_start': _warrantyStart.text.trim(),
        if (_warrantyEnd.text.isNotEmpty)
          'warranty_end': _warrantyEnd.text.trim(),
        if (_manufacturedDate.text.isNotEmpty)
          'manufactured_date': _manufacturedDate.text.trim(),
        if (_currentOwner.text.isNotEmpty)
          'current_owner': _currentOwner.text.trim(),
        if (_assetReference.text.isNotEmpty)
          'asset_reference': _assetReference.text.trim(),
        if (_remarks.text.isNotEmpty) 'remarks': _remarks.text.trim(),
      };
      if (widget.existing != null) {
        await widget.api.updateSerial(widget.existing!.id, data);
      } else {
        await widget.api.createSerial(data);
      }
      if (!mounted) return;
      Navigator.pop(context, true);
    } on ApiException catch (exception) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(exception.message)));
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: Text(
            widget.existing == null ? 'Add Serial Number' : 'Edit Serial Number'),
        content: SizedBox(
          width: 480,
          child: Form(
            key: _formKey,
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  TextFormField(
                    controller: _serialNumber,
                    decoration:
                        const InputDecoration(labelText: 'Serial Number *'),
                    validator: (v) =>
                        v == null || v.trim().isEmpty ? 'Required' : null,
                  ),
                  const SizedBox(height: 12),
                  DropdownButtonFormField<String>(
                    initialValue: _status,
                    decoration: const InputDecoration(labelText: 'Status'),
                    items: const [
                      DropdownMenuItem(
                          value: 'AVAILABLE', child: Text('Available')),
                      DropdownMenuItem(
                          value: 'RESERVED', child: Text('Reserved')),
                      DropdownMenuItem(value: 'SOLD', child: Text('Sold')),
                      DropdownMenuItem(
                          value: 'INSTALLED', child: Text('Installed')),
                    ],
                    onChanged: (v) => setState(() => _status = v ?? _status),
                  ),
                  const SizedBox(height: 12),
                  TextFormField(
                    controller: _manufacturedDate,
                    decoration: const InputDecoration(
                        labelText: 'Manufactured Date (YYYY-MM-DD)'),
                  ),
                  const SizedBox(height: 12),
                  TextFormField(
                    controller: _warrantyStart,
                    decoration: const InputDecoration(
                        labelText: 'Warranty Start (YYYY-MM-DD)'),
                  ),
                  const SizedBox(height: 12),
                  TextFormField(
                    controller: _warrantyEnd,
                    decoration: const InputDecoration(
                        labelText: 'Warranty End (YYYY-MM-DD)'),
                  ),
                  const SizedBox(height: 12),
                  TextFormField(
                    controller: _currentOwner,
                    decoration:
                        const InputDecoration(labelText: 'Current Owner'),
                  ),
                  const SizedBox(height: 12),
                  TextFormField(
                    controller: _assetReference,
                    decoration:
                        const InputDecoration(labelText: 'Asset Reference'),
                  ),
                  const SizedBox(height: 12),
                  TextFormField(
                    controller: _remarks,
                    decoration: const InputDecoration(labelText: 'Remarks'),
                    maxLines: 2,
                  ),
                ],
              ),
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: _saving ? null : () => Navigator.pop(context, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: _saving ? null : _save,
            child: _saving
                ? const SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(strokeWidth: 2))
                : Text(widget.existing == null ? 'Create' : 'Save'),
          ),
        ],
      );
}
