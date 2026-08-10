import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/dialogs/app_dialogs.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/branch_warehouse.dart';
import '../../models/entities.dart';
import '../workspace/desktop_framework.dart';
import 'branch_warehouse_import_dialog.dart';

enum BranchWarehouseSection {
  branches,
  warehouses,
  storageAreas,
  warehouseTypes,
  branchTypes,
  settings,
}

class BranchWarehouseManagementPage extends StatefulWidget {
  const BranchWarehouseManagementPage({
    super.key,
    required this.api,
    required this.permissions,
    required this.hasActiveFirm,
    required this.section,
  });

  final ApiClient api;
  final PermissionService permissions;
  final bool hasActiveFirm;
  final BranchWarehouseSection section;

  @override
  State<BranchWarehouseManagementPage> createState() =>
      _BranchWarehouseManagementPageState();
}

class _BranchWarehouseManagementPageState
    extends State<BranchWarehouseManagementPage> {
  static const int _rowsPerPage = 20;
  final TextEditingController _search = TextEditingController();
  final FocusNode _searchFocus = FocusNode();
  bool _loading = false;
  String? _error;
  int _page = 1;
  int _total = 0;
  bool _includeDeleted = false;
  String _sortBy = 'created_at';
  bool _descending = true;
  String? _status;

  List<BranchRecord> _branches = const [];
  BranchRecord? _selectedBranch;
  List<WarehouseRecord> _warehouses = const [];
  WarehouseRecord? _selectedWarehouse;
  List<TypeRecord> _types = const [];
  TypeRecord? _selectedType;
  List<StorageNodeRecord> _storageNodes = const [];
  StorageNodeRecord? _selectedStorageNode;

  bool get _canBranchCreate =>
      widget.hasActiveFirm && widget.permissions.hasPermission('BRANCH_CREATE');
  bool get _canBranchEdit => widget.permissions.hasPermission('BRANCH_UPDATE');
  bool get _canBranchDelete =>
      widget.permissions.hasPermission('BRANCH_DELETE');
  bool get _canBranchRestore =>
      widget.permissions.hasPermission('BRANCH_RESTORE');
  bool get _canWarehouseCreate =>
      widget.hasActiveFirm &&
      widget.permissions.hasPermission('WAREHOUSE_CREATE');
  bool get _canWarehouseEdit =>
      widget.permissions.hasPermission('WAREHOUSE_UPDATE');
  bool get _canWarehouseDelete =>
      widget.permissions.hasPermission('WAREHOUSE_DELETE');
  bool get _canWarehouseRestore =>
      widget.permissions.hasPermission('WAREHOUSE_RESTORE');
  bool get _canStorageManage =>
      widget.permissions.hasPermission('STORAGE_AREA_MANAGE');
  bool get _canExport =>
      widget.permissions.hasPermission('BRANCH_WAREHOUSE_EXPORT');

  /// Import is offered only on the two sections the server accepts a batch for.
  bool get _canImport =>
      widget.hasActiveFirm &&
      widget.permissions.hasPermission('BRANCH_WAREHOUSE_IMPORT') &&
      _importTarget != null;

  BranchImportTarget? get _importTarget => switch (widget.section) {
        BranchWarehouseSection.branches => BranchImportTarget.branches,
        BranchWarehouseSection.warehouses => BranchImportTarget.warehouses,
        _ => null,
      };

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _search.dispose();
    _searchFocus.dispose();
    super.dispose();
  }

  Future<void> _load({int? requestedPage}) async {
    setState(() {
      _loading = true;
      _error = null;
      _page = requestedPage ?? _page;
    });
    try {
      switch (widget.section) {
        case BranchWarehouseSection.branches:
          final result = await widget.api.branches(
            page: _page,
            search: _search.text.trim(),
            sortBy: _sortBy,
            descending: _descending,
            filters: BranchQuery(
              status: _status,
              includeDeleted: _includeDeleted,
            ),
          );
          _branches = result.items;
          _total = result.total;
          _selectedBranch = _keepSelected(
            _selectedBranch?.id,
            _branches,
            (item) => item.id,
          );
          break;
        case BranchWarehouseSection.warehouses:
          final result = await widget.api.warehouses(
            page: _page,
            search: _search.text.trim(),
            sortBy: _sortBy,
            descending: _descending,
            filters: WarehouseQuery(
              status: _status,
              includeDeleted: _includeDeleted,
            ),
          );
          _warehouses = result.items;
          _total = result.total;
          _selectedWarehouse = _keepSelected(
            _selectedWarehouse?.id,
            _warehouses,
            (item) => item.id,
          );
          break;
        case BranchWarehouseSection.branchTypes:
          _types =
              await widget.api.branchTypes(includeDeleted: _includeDeleted);
          _total = _types.length;
          _selectedType =
              _keepSelected(_selectedType?.id, _types, (item) => item.id);
          break;
        case BranchWarehouseSection.warehouseTypes:
          _types =
              await widget.api.warehouseTypes(includeDeleted: _includeDeleted);
          _total = _types.length;
          _selectedType =
              _keepSelected(_selectedType?.id, _types, (item) => item.id);
          break;
        case BranchWarehouseSection.storageAreas:
          final warehouses = await widget.api.warehouses(
            page: 1,
          );
          final firstWarehouse =
              warehouses.items.isEmpty ? null : warehouses.items.first;
          if (_selectedWarehouse == null && firstWarehouse != null) {
            _selectedWarehouse = firstWarehouse;
          }
          if (_selectedWarehouse != null) {
            _storageNodes = await widget.api.storageNodes(
              _selectedWarehouse!.id,
              includeDeleted: _includeDeleted,
            );
          } else {
            _storageNodes = const [];
          }
          _total = _storageNodes.length;
          _selectedStorageNode = _keepSelected(
            _selectedStorageNode?.id,
            _storageNodes,
            (item) => item.id,
          );
          break;
        case BranchWarehouseSection.settings:
          _total = 0;
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

  T? _keepSelected<T>(
    String? selectedId,
    List<T> items,
    String Function(T) idOf,
  ) {
    if (selectedId == null) return null;
    for (final item in items) {
      if (idOf(item) == selectedId) return item;
    }
    return null;
  }

  @override
  Widget build(BuildContext context) {
    final Widget content = _buildContent();
    final Widget toolbar = _buildToolbar();
    return WorkspaceShortcuts(
      bindings: WorkspaceShortcutBindings(
        create: _canCreateCurrent ? _openCreate : null,
        focusSearch: _searchFocus.requestFocus,
        refresh: _load,
        delete: _canDeleteCurrent ? _deleteSelected : null,
      ),
      child: ManagementWorkspaceLayout(
        toolbar: toolbar,
        searchPanel: SearchFilterPanel(
          controller: _search,
          focusNode: _searchFocus,
          hintText: _searchHint,
          onSearch: (_) => _load(requestedPage: 1),
        ),
        filterPanel: FilterPanel(
          activeFilterCount:
              (_status == null ? 0 : 1) + (_includeDeleted ? 1 : 0),
          onApply: () => _load(requestedPage: 1),
          onClear: () {
            setState(() {
              _status = null;
              _includeDeleted = false;
            });
            _load(requestedPage: 1);
          },
          children: [
            if (_supportsStatus)
              SizedBox(
                width: 220,
                child: DropdownButtonFormField<String>(
                  initialValue: _status,
                  decoration: const InputDecoration(labelText: 'Status'),
                  items: const ['DRAFT', 'ACTIVE', 'INACTIVE', 'ARCHIVED']
                      .map(
                        (item) => DropdownMenuItem<String>(
                            value: item, child: Text(item)),
                      )
                      .toList(),
                  onChanged: (value) => setState(() => _status = value),
                ),
              ),
            FilterChip(
              label: const Text('Include deleted'),
              selected: _includeDeleted,
              onSelected: (value) => setState(() => _includeDeleted = value),
            ),
          ],
        ),
        primaryContent: content,
        detailsPanel: _hasSelection ? _summaryPanel() : null,
        statusBar: WorkspaceStatusBar(
          total: _total,
          selected: _hasSelection,
          message: _loading ? 'Refreshing...' : 'Ready',
        ),
      ),
    );
  }

  bool get _supportsStatus =>
      widget.section == BranchWarehouseSection.branches ||
      widget.section == BranchWarehouseSection.warehouses;

  bool get _canCreateCurrent => switch (widget.section) {
        BranchWarehouseSection.branches => _canBranchCreate,
        BranchWarehouseSection.warehouses => _canWarehouseCreate,
        BranchWarehouseSection.storageAreas => _canStorageManage,
        BranchWarehouseSection.branchTypes => _canBranchEdit,
        BranchWarehouseSection.warehouseTypes => _canWarehouseEdit,
        BranchWarehouseSection.settings => false,
      };

  bool get _canDeleteCurrent => switch (widget.section) {
        BranchWarehouseSection.branches => _canBranchDelete &&
            _selectedBranch != null &&
            !_selectedBranch!.isDeleted,
        BranchWarehouseSection.warehouses => _canWarehouseDelete &&
            _selectedWarehouse != null &&
            !_selectedWarehouse!.isDeleted,
        BranchWarehouseSection.storageAreas =>
          _canStorageManage && _selectedStorageNode != null,
        BranchWarehouseSection.branchTypes =>
          _canBranchDelete && _selectedType != null,
        BranchWarehouseSection.warehouseTypes =>
          _canWarehouseDelete && _selectedType != null,
        BranchWarehouseSection.settings => false,
      };

  bool get _hasSelection => switch (widget.section) {
        BranchWarehouseSection.branches => _selectedBranch != null,
        BranchWarehouseSection.warehouses => _selectedWarehouse != null,
        BranchWarehouseSection.storageAreas => _selectedStorageNode != null,
        BranchWarehouseSection.branchTypes => _selectedType != null,
        BranchWarehouseSection.warehouseTypes => _selectedType != null,
        BranchWarehouseSection.settings => false,
      };

  String get _searchHint => switch (widget.section) {
        BranchWarehouseSection.branches =>
          'Search branch code, name, manager, city, state, country',
        BranchWarehouseSection.warehouses =>
          'Search warehouse code, name, branch, type, city, state, country',
        BranchWarehouseSection.storageAreas =>
          'Search storage area/rack/shelf/bin by code or name',
        BranchWarehouseSection.branchTypes => 'Search branch types',
        BranchWarehouseSection.warehouseTypes => 'Search warehouse types',
        BranchWarehouseSection.settings => 'No search available in settings',
      };

  Widget _buildToolbar() => WorkspaceToolbar(
        actions: const [
          ToolbarAction.newItem,
          ToolbarAction.delete,
          ToolbarAction.refresh,
          ToolbarAction.import,
          ToolbarAction.export,
        ],
        isVisible: (action) => switch (action) {
          ToolbarAction.newItem => _canCreateCurrent,
          ToolbarAction.delete => _canDeleteCurrent,
          ToolbarAction.import => _canImport,
          ToolbarAction.export => _canExport,
          _ => true,
        },
        isEnabled: (action) =>
            !_loading &&
            switch (action) {
              ToolbarAction.newItem => _canCreateCurrent,
              ToolbarAction.delete => _canDeleteCurrent,
              ToolbarAction.refresh => true,
              ToolbarAction.import => _canImport,
              ToolbarAction.export => _canExport,
              _ => false,
            },
        onAction: (action) {
          switch (action) {
            case ToolbarAction.newItem:
              _openCreate();
              break;
            case ToolbarAction.delete:
              _deleteSelected();
              break;
            case ToolbarAction.refresh:
              _load();
              break;
            case ToolbarAction.export:
              _export();
              break;
            case ToolbarAction.import:
              _openImport();
              break;
            default:
              break;
          }
        },
      );

  Widget _buildContent() {
    if (_error != null) {
      return WorkspaceErrorState(message: _error!, onRetry: _load);
    }
    if (_loading && _total == 0) return const TableLoadingSkeleton();
    return switch (widget.section) {
      BranchWarehouseSection.branches => _branchGrid(),
      BranchWarehouseSection.warehouses => _warehouseGrid(),
      BranchWarehouseSection.storageAreas => _storageGrid(),
      BranchWarehouseSection.branchTypes ||
      BranchWarehouseSection.warehouseTypes =>
        _typeGrid(),
      BranchWarehouseSection.settings => _settingsView(),
    };
  }

  Widget _branchGrid() {
    if (_branches.isEmpty) {
      return const StandardEmptyState(type: EmptyStateType.noRecords);
    }
    return LoadingOverlay(
      loading: _loading,
      child: EnterpriseDataGrid<BranchRecord>(
        items: _branches,
        total: _total,
        pageOffset: (_page - 1) * _rowsPerPage,
        rowsPerPage: _rowsPerPage,
        columns: [
          _column('code', 'Code'),
          _column('name', 'Name'),
          const GridColumn(key: 'status', label: 'Status'),
          const GridColumn(key: 'warehouses', label: 'Warehouses'),
          const GridColumn(key: 'phone', label: 'Phone'),
        ],
        id: (item) => item.id,
        cells: (item) => [
          item.code,
          item.displayName,
          item.isDeleted ? 'DELETED' : item.status,
          '${item.warehouseCount}',
          item.mobile.isNotEmpty ? item.mobile : item.phone,
        ],
        selectedId: _selectedBranch?.id,
        onSelect: (item) => setState(() => _selectedBranch = item),
        onOpen: _openBranchEdit,
        contextActionsFor: (item) => [
          if (_canBranchEdit && !item.isDeleted) WorkspaceContextAction.edit,
          if (_canBranchDelete && !item.isDeleted)
            WorkspaceContextAction.delete,
          if (_canBranchRestore && item.isDeleted)
            WorkspaceContextAction.restore,
          WorkspaceContextAction.refresh,
        ],
        onContextAction: (action, item) {
          switch (action) {
            case WorkspaceContextAction.edit:
              _openBranchEdit(item);
              break;
            case WorkspaceContextAction.delete:
              _deleteBranch(item);
              break;
            case WorkspaceContextAction.restore:
              _restoreBranch(item);
              break;
            case WorkspaceContextAction.refresh:
              _load();
              break;
            default:
              break;
          }
        },
        onPageChanged: (offset) =>
            _load(requestedPage: offset ~/ _rowsPerPage + 1),
      ),
    );
  }

  Widget _warehouseGrid() {
    if (_warehouses.isEmpty) {
      return const StandardEmptyState(type: EmptyStateType.noRecords);
    }
    return LoadingOverlay(
      loading: _loading,
      child: EnterpriseDataGrid<WarehouseRecord>(
        items: _warehouses,
        total: _total,
        pageOffset: (_page - 1) * _rowsPerPage,
        rowsPerPage: _rowsPerPage,
        columns: [
          _column('code', 'Code'),
          _column('name', 'Name'),
          const GridColumn(key: 'status', label: 'Status'),
          const GridColumn(key: 'capacity', label: 'Capacity'),
          const GridColumn(key: 'cold_storage', label: 'Cold Storage'),
        ],
        id: (item) => item.id,
        cells: (item) => [
          item.code,
          item.displayName,
          item.isDeleted ? 'DELETED' : item.status,
          '${item.capacity} ${item.capacityUnit}',
          item.coldStorage ? 'Yes' : 'No',
        ],
        selectedId: _selectedWarehouse?.id,
        onSelect: (item) => setState(() => _selectedWarehouse = item),
        onOpen: _openWarehouseEdit,
        contextActionsFor: (item) => [
          if (_canWarehouseEdit && !item.isDeleted) WorkspaceContextAction.edit,
          if (_canWarehouseDelete && !item.isDeleted)
            WorkspaceContextAction.delete,
          if (_canWarehouseRestore && item.isDeleted)
            WorkspaceContextAction.restore,
          WorkspaceContextAction.refresh,
        ],
        onContextAction: (action, item) {
          switch (action) {
            case WorkspaceContextAction.edit:
              _openWarehouseEdit(item);
              break;
            case WorkspaceContextAction.delete:
              _deleteWarehouse(item);
              break;
            case WorkspaceContextAction.restore:
              _restoreWarehouse(item);
              break;
            case WorkspaceContextAction.refresh:
              _load();
              break;
            default:
              break;
          }
        },
        onPageChanged: (offset) =>
            _load(requestedPage: offset ~/ _rowsPerPage + 1),
      ),
    );
  }

  Widget _typeGrid() {
    if (_types.isEmpty) {
      return const StandardEmptyState(type: EmptyStateType.noRecords);
    }
    return LoadingOverlay(
      loading: _loading,
      child: EnterpriseDataGrid<TypeRecord>(
        items: _types,
        total: _types.length,
        pageOffset: 0,
        rowsPerPage: _types.length,
        columns: const [
          GridColumn(key: 'code', label: 'Code'),
          GridColumn(key: 'name', label: 'Name'),
          GridColumn(key: 'status', label: 'Status'),
        ],
        id: (item) => item.id,
        cells: (item) => [
          item.code,
          item.name,
          item.isDeleted ? 'DELETED' : (item.isActive ? 'ACTIVE' : 'INACTIVE')
        ],
        selectedId: _selectedType?.id,
        onSelect: (item) => setState(() => _selectedType = item),
        onOpen: _openTypeEdit,
        onPageChanged: (_) {},
      ),
    );
  }

  Widget _storageGrid() {
    if (_selectedWarehouse == null) {
      return const StandardEmptyState(
        type: EmptyStateType.noRecords,
        title: 'No warehouse available',
        message: 'Create a warehouse first to configure storage structure.',
      );
    }
    if (_storageNodes.isEmpty) {
      return const StandardEmptyState(type: EmptyStateType.noRecords);
    }
    return LoadingOverlay(
      loading: _loading,
      child: EnterpriseDataGrid<StorageNodeRecord>(
        items: _storageNodes,
        total: _storageNodes.length,
        pageOffset: 0,
        rowsPerPage: _storageNodes.length,
        columns: const [
          GridColumn(key: 'code', label: 'Code'),
          GridColumn(key: 'name', label: 'Name'),
          GridColumn(key: 'type', label: 'Type'),
          GridColumn(key: 'path', label: 'Path'),
        ],
        id: (item) => item.id,
        cells: (item) => [item.code, item.name, item.nodeType, item.path],
        selectedId: _selectedStorageNode?.id,
        onSelect: (item) => setState(() => _selectedStorageNode = item),
        onOpen: _openStorageEdit,
        onPageChanged: (_) {},
      ),
    );
  }

  Widget _settingsView() => const StandardEmptyState(
        type: EmptyStateType.noRecords,
        title: 'Branch & Warehouse settings',
        message:
            'Future inventory integrations are enabled by architecture and backend extension points.',
      );

  Widget _summaryPanel() {
    return switch (widget.section) {
      BranchWarehouseSection.branches => QuickSummaryPanel(
          title: _selectedBranch?.displayName ?? 'No branch selected',
          lines: _selectedBranch == null
              ? const []
              : [
                  DetailLine('Code', _selectedBranch!.code),
                  DetailLine(
                      'Status',
                      _selectedBranch!.isDeleted
                          ? 'DELETED'
                          : _selectedBranch!.status),
                  DetailLine(
                      'Warehouses', '${_selectedBranch!.warehouseCount}'),
                  DetailLine(
                      'Phone',
                      _selectedBranch!.mobile.isNotEmpty
                          ? _selectedBranch!.mobile
                          : _selectedBranch!.phone),
                ],
        ),
      BranchWarehouseSection.warehouses => QuickSummaryPanel(
          title: _selectedWarehouse?.displayName ?? 'No warehouse selected',
          lines: _selectedWarehouse == null
              ? const []
              : [
                  DetailLine('Code', _selectedWarehouse!.code),
                  DetailLine(
                      'Status',
                      _selectedWarehouse!.isDeleted
                          ? 'DELETED'
                          : _selectedWarehouse!.status),
                  DetailLine('Capacity',
                      '${_selectedWarehouse!.capacity} ${_selectedWarehouse!.capacityUnit}'),
                  DetailLine('Cold Storage',
                      _selectedWarehouse!.coldStorage ? 'Yes' : 'No'),
                ],
        ),
      BranchWarehouseSection.storageAreas => QuickSummaryPanel(
          title: _selectedStorageNode?.name ?? 'No storage node selected',
          lines: _selectedStorageNode == null
              ? const []
              : [
                  DetailLine('Code', _selectedStorageNode!.code),
                  DetailLine('Type', _selectedStorageNode!.nodeType),
                  DetailLine('Path', _selectedStorageNode!.path),
                ],
        ),
      BranchWarehouseSection.branchTypes ||
      BranchWarehouseSection.warehouseTypes =>
        QuickSummaryPanel(
          title: _selectedType?.name ?? 'No type selected',
          lines: _selectedType == null
              ? const []
              : [
                  DetailLine('Code', _selectedType!.code),
                  DetailLine(
                      'Status',
                      _selectedType!.isDeleted
                          ? 'DELETED'
                          : (_selectedType!.isActive ? 'ACTIVE' : 'INACTIVE')),
                ],
        ),
      BranchWarehouseSection.settings =>
        const QuickSummaryPanel(title: 'Settings', lines: []),
    };
  }

  GridColumn _column(String key, String label) => GridColumn(
        key: key,
        label: label,
        onSort: (ascending) {
          setState(() {
            _sortBy = key;
            _descending = !ascending;
          });
          _load(requestedPage: 1);
        },
      );

  Future<void> _openCreate() async {
    switch (widget.section) {
      case BranchWarehouseSection.branches:
        await _openBranchEdit(null);
        break;
      case BranchWarehouseSection.warehouses:
        await _openWarehouseEdit(null);
        break;
      case BranchWarehouseSection.storageAreas:
        await _openStorageEdit(null);
        break;
      case BranchWarehouseSection.branchTypes:
      case BranchWarehouseSection.warehouseTypes:
        await _openTypeEdit(null);
        break;
      case BranchWarehouseSection.settings:
        break;
    }
  }

  Future<void> _deleteSelected() async {
    switch (widget.section) {
      case BranchWarehouseSection.branches:
        if (_selectedBranch != null) await _deleteBranch(_selectedBranch!);
        break;
      case BranchWarehouseSection.warehouses:
        if (_selectedWarehouse != null) {
          await _deleteWarehouse(_selectedWarehouse!);
        }
        break;
      case BranchWarehouseSection.storageAreas:
        if (_selectedStorageNode != null) {
          await widget.api.deleteStorageNode(_selectedStorageNode!.id);
          await _load();
        }
        break;
      case BranchWarehouseSection.branchTypes:
        if (_selectedType != null) {
          await widget.api.deleteBranchType(_selectedType!.id);
          await _load();
        }
        break;
      case BranchWarehouseSection.warehouseTypes:
        if (_selectedType != null) {
          await widget.api.deleteWarehouseType(_selectedType!.id);
          await _load();
        }
        break;
      case BranchWarehouseSection.settings:
        break;
    }
  }

  /// Load a batch of branches or warehouses from a spreadsheet.
  Future<void> _openImport() async {
    final BranchImportTarget? target = _importTarget;
    if (target == null) return;
    final bool? imported = await showDialog<bool>(
      context: context,
      barrierDismissible: false,
      builder: (_) => BranchWarehouseImportDialog(
        api: widget.api,
        target: target,
      ),
    );
    if (imported == true && mounted) {
      await _load();
    }
  }

  Future<void> _export() async {
    if (!_canExport) return;
    try {
      switch (widget.section) {
        case BranchWarehouseSection.branches:
          await widget.api.exportBranches(search: _search.text.trim());
          break;
        case BranchWarehouseSection.warehouses:
          await widget.api.exportWarehouses(search: _search.text.trim());
          break;
        default:
          return;
      }
      if (!mounted) return;
      NotificationService.show(
        context,
        'Export completed.',
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

  Future<void> _openBranchEdit(BranchRecord? current) async {
    final payload = await showDialog<Json>(
      context: context,
      builder: (context) => _BranchDialog(current: current),
    );
    if (payload == null || !mounted) return;
    try {
      if (current == null) {
        await widget.api.createBranch(payload);
      } else {
        await widget.api.updateBranch(current.id, payload);
      }
      await _load();
    } on ApiException catch (exception) {
      if (!mounted) return;
      NotificationService.show(context, exception.message,
          kind: AppNotificationKind.error);
    }
  }

  Future<void> _openWarehouseEdit(WarehouseRecord? current) async {
    final branches = await widget.api.branches(page: 1);
    if (!mounted) return;
    final payload = await showDialog<Json>(
      context: context,
      builder: (context) => _WarehouseDialog(
        current: current,
        branches: branches.items,
      ),
    );
    if (payload == null || !mounted) return;
    try {
      if (current == null) {
        await widget.api.createWarehouse(payload);
      } else {
        await widget.api.updateWarehouse(current.id, payload);
      }
      await _load();
    } on ApiException catch (exception) {
      if (!mounted) return;
      NotificationService.show(context, exception.message,
          kind: AppNotificationKind.error);
    }
  }

  Future<void> _openTypeEdit(TypeRecord? current) async {
    final payload = await showDialog<Json>(
      context: context,
      builder: (context) => _TypeDialog(current: current),
    );
    if (payload == null || !mounted) return;
    try {
      if (widget.section == BranchWarehouseSection.branchTypes) {
        if (current == null) {
          await widget.api.createBranchType(payload);
        } else {
          await widget.api.updateBranchType(current.id, payload);
        }
      } else {
        if (current == null) {
          await widget.api.createWarehouseType(payload);
        } else {
          await widget.api.updateWarehouseType(current.id, payload);
        }
      }
      await _load();
    } on ApiException catch (exception) {
      if (!mounted) return;
      NotificationService.show(context, exception.message,
          kind: AppNotificationKind.error);
    }
  }

  Future<void> _openStorageEdit(StorageNodeRecord? current) async {
    if (_selectedWarehouse == null) return;
    final payload = await showDialog<Json>(
      context: context,
      builder: (context) => _StorageNodeDialog(
        current: current,
        warehouseId: _selectedWarehouse!.id,
        availableParents: _storageNodes,
      ),
    );
    if (payload == null || !mounted) return;
    try {
      if (current == null) {
        await widget.api.createStorageNode(payload);
      } else {
        await widget.api.updateStorageNode(current.id, payload);
      }
      await _load();
    } on ApiException catch (exception) {
      if (!mounted) return;
      NotificationService.show(context, exception.message,
          kind: AppNotificationKind.error);
    }
  }

  Future<void> _deleteBranch(BranchRecord branch) async {
    final confirmed = await showWorkspaceConfirmDialog(
      context,
      title: 'Delete branch?',
      message: 'This branch will be soft deleted.',
      confirmLabel: 'Delete',
      type: ConfirmationType.delete,
    );
    if (!confirmed || !mounted) return;
    await widget.api.deleteBranch(branch.id);
    await _load();
  }

  Future<void> _restoreBranch(BranchRecord branch) async {
    await widget.api.restoreBranch(branch.id);
    await _load();
  }

  Future<void> _deleteWarehouse(WarehouseRecord warehouse) async {
    final confirmed = await showWorkspaceConfirmDialog(
      context,
      title: 'Delete warehouse?',
      message: 'This warehouse will be soft deleted.',
      confirmLabel: 'Delete',
      type: ConfirmationType.delete,
    );
    if (!confirmed || !mounted) return;
    await widget.api.deleteWarehouse(warehouse.id);
    await _load();
  }

  Future<void> _restoreWarehouse(WarehouseRecord warehouse) async {
    await widget.api.restoreWarehouse(warehouse.id);
    await _load();
  }
}

class _BranchDialog extends StatefulWidget {
  const _BranchDialog({this.current});
  final BranchRecord? current;

  @override
  State<_BranchDialog> createState() => _BranchDialogState();
}

class _BranchDialogState extends State<_BranchDialog> {
  late final TextEditingController _code =
      TextEditingController(text: widget.current?.code ?? '');
  late final TextEditingController _name =
      TextEditingController(text: widget.current?.name ?? '');
  late final TextEditingController _displayName =
      TextEditingController(text: widget.current?.displayName ?? '');
  late final TextEditingController _email =
      TextEditingController(text: widget.current?.email ?? '');
  late final TextEditingController _phone =
      TextEditingController(text: widget.current?.phone ?? '');
  late final TextEditingController _mobile =
      TextEditingController(text: widget.current?.mobile ?? '');
  late final TextEditingController _currency =
      TextEditingController(text: widget.current?.currencyCode ?? 'INR');
  String _status = 'ACTIVE';

  @override
  void initState() {
    super.initState();
    _status = widget.current?.status.isNotEmpty == true
        ? widget.current!.status
        : 'ACTIVE';
  }

  @override
  void dispose() {
    _code.dispose();
    _name.dispose();
    _displayName.dispose();
    _email.dispose();
    _phone.dispose();
    _mobile.dispose();
    _currency.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: Text(widget.current == null ? 'Create Branch' : 'Edit Branch'),
        content: SizedBox(
          width: 700,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Row(
                children: [
                  Expanded(child: _field(_code, 'Branch Code')),
                  const SizedBox(width: 12),
                  Expanded(child: _field(_name, 'Branch Name')),
                ],
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(child: _field(_displayName, 'Display Name')),
                  const SizedBox(width: 12),
                  Expanded(child: _field(_currency, 'Currency')),
                ],
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(child: _field(_email, 'Email')),
                  const SizedBox(width: 12),
                  Expanded(child: _field(_phone, 'Phone')),
                  const SizedBox(width: 12),
                  Expanded(child: _field(_mobile, 'Mobile')),
                ],
              ),
              const SizedBox(height: 12),
              DropdownButtonFormField<String>(
                initialValue: _status,
                decoration: const InputDecoration(labelText: 'Status'),
                items: const ['DRAFT', 'ACTIVE', 'INACTIVE', 'ARCHIVED']
                    .map((item) =>
                        DropdownMenuItem(value: item, child: Text(item)))
                    .toList(),
                onChanged: (value) =>
                    setState(() => _status = value ?? 'ACTIVE'),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Cancel')),
          FilledButton(
            onPressed: () => Navigator.pop(context, {
              'code': _code.text.trim().toUpperCase(),
              'name': _name.text.trim(),
              'display_name': _displayName.text.trim().isEmpty
                  ? _name.text.trim()
                  : _displayName.text.trim(),
              'email': _email.text.trim(),
              'phone': _phone.text.trim(),
              'mobile': _mobile.text.trim(),
              'currency_code': _currency.text.trim().toUpperCase(),
              'status': _status,
              'working_hours': const {'start': '09:00', 'end': '18:00'},
              'gst_registration': false,
              'is_default': false,
            }),
            child: const Text('Save'),
          ),
        ],
      );

  Widget _field(TextEditingController controller, String label) => TextField(
        controller: controller,
        decoration: InputDecoration(labelText: label),
      );
}

class _WarehouseDialog extends StatefulWidget {
  const _WarehouseDialog({
    required this.current,
    required this.branches,
  });
  final WarehouseRecord? current;
  final List<BranchRecord> branches;

  @override
  State<_WarehouseDialog> createState() => _WarehouseDialogState();
}

class _WarehouseDialogState extends State<_WarehouseDialog> {
  late final TextEditingController _code =
      TextEditingController(text: widget.current?.code ?? '');
  late final TextEditingController _name =
      TextEditingController(text: widget.current?.name ?? '');
  late final TextEditingController _displayName =
      TextEditingController(text: widget.current?.displayName ?? '');
  late final TextEditingController _capacity =
      TextEditingController(text: widget.current?.capacity ?? '');
  late final TextEditingController _capacityUnit =
      TextEditingController(text: widget.current?.capacityUnit ?? 'KG');
  String _status = 'ACTIVE';
  String? _branchId;

  @override
  void initState() {
    super.initState();
    _status = widget.current?.status.isNotEmpty == true
        ? widget.current!.status
        : 'ACTIVE';
    _branchId = widget.current?.branchId ??
        (widget.branches.isNotEmpty ? widget.branches.first.id : null);
  }

  @override
  void dispose() {
    _code.dispose();
    _name.dispose();
    _displayName.dispose();
    _capacity.dispose();
    _capacityUnit.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: Text(
            widget.current == null ? 'Create Warehouse' : 'Edit Warehouse'),
        content: SizedBox(
          width: 760,
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
                        child: Text('${item.code} - ${item.displayName}'),
                      ),
                    )
                    .toList(),
                onChanged: (value) => setState(() => _branchId = value),
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(child: _field(_code, 'Warehouse Code')),
                  const SizedBox(width: 12),
                  Expanded(child: _field(_name, 'Warehouse Name')),
                ],
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(child: _field(_displayName, 'Display Name')),
                  const SizedBox(width: 12),
                  Expanded(child: _field(_capacity, 'Capacity')),
                  const SizedBox(width: 12),
                  Expanded(child: _field(_capacityUnit, 'Capacity Unit')),
                ],
              ),
              const SizedBox(height: 12),
              DropdownButtonFormField<String>(
                initialValue: _status,
                decoration: const InputDecoration(labelText: 'Status'),
                items: const ['DRAFT', 'ACTIVE', 'INACTIVE', 'ARCHIVED']
                    .map((item) =>
                        DropdownMenuItem(value: item, child: Text(item)))
                    .toList(),
                onChanged: (value) =>
                    setState(() => _status = value ?? 'ACTIVE'),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Cancel')),
          FilledButton(
            onPressed: _branchId == null
                ? null
                : () => Navigator.pop(context, {
                      'branch_id': _branchId,
                      'code': _code.text.trim().toUpperCase(),
                      'name': _name.text.trim(),
                      'display_name': _displayName.text.trim().isEmpty
                          ? _name.text.trim()
                          : _displayName.text.trim(),
                      'capacity': _capacity.text.trim(),
                      'capacity_unit': _capacityUnit.text.trim().toUpperCase(),
                      'status': _status,
                      'is_default': false,
                      'temperature_controlled': false,
                      'cold_storage': false,
                      'hazardous_storage': false,
                      'has_receiving_area': true,
                      'has_dispatch_area': true,
                      'has_returns_area': false,
                      'has_inspection_area': false,
                      'has_packing_area': false,
                      'has_loading_dock': false,
                    }),
            child: const Text('Save'),
          ),
        ],
      );

  Widget _field(TextEditingController controller, String label) => TextField(
        controller: controller,
        decoration: InputDecoration(labelText: label),
      );
}

class _TypeDialog extends StatefulWidget {
  const _TypeDialog({this.current});
  final TypeRecord? current;

  @override
  State<_TypeDialog> createState() => _TypeDialogState();
}

class _TypeDialogState extends State<_TypeDialog> {
  late final TextEditingController _code =
      TextEditingController(text: widget.current?.code ?? '');
  late final TextEditingController _name =
      TextEditingController(text: widget.current?.name ?? '');
  late final TextEditingController _description =
      TextEditingController(text: widget.current?.description ?? '');
  bool _active = true;

  @override
  void initState() {
    super.initState();
    _active = widget.current?.isActive ?? true;
  }

  @override
  void dispose() {
    _code.dispose();
    _name.dispose();
    _description.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: Text(widget.current == null ? 'Create Type' : 'Edit Type'),
        content: SizedBox(
          width: 560,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                  controller: _code,
                  decoration: const InputDecoration(labelText: 'Code')),
              const SizedBox(height: 12),
              TextField(
                  controller: _name,
                  decoration: const InputDecoration(labelText: 'Name')),
              const SizedBox(height: 12),
              TextField(
                controller: _description,
                decoration: const InputDecoration(labelText: 'Description'),
              ),
              const SizedBox(height: 12),
              SwitchListTile(
                title: const Text('Active'),
                value: _active,
                onChanged: (value) => setState(() => _active = value),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Cancel')),
          FilledButton(
            onPressed: () => Navigator.pop(context, {
              'code': _code.text.trim().toUpperCase(),
              'name': _name.text.trim(),
              'description': _description.text.trim(),
              'is_active': _active,
            }),
            child: const Text('Save'),
          ),
        ],
      );
}

class _StorageNodeDialog extends StatefulWidget {
  const _StorageNodeDialog({
    required this.current,
    required this.warehouseId,
    required this.availableParents,
  });
  final StorageNodeRecord? current;
  final String warehouseId;
  final List<StorageNodeRecord> availableParents;

  @override
  State<_StorageNodeDialog> createState() => _StorageNodeDialogState();
}

class _StorageNodeDialogState extends State<_StorageNodeDialog> {
  late final TextEditingController _code =
      TextEditingController(text: widget.current?.code ?? '');
  late final TextEditingController _name =
      TextEditingController(text: widget.current?.name ?? '');
  String _type = 'STORAGE_AREA';
  String? _parentId;

  @override
  void initState() {
    super.initState();
    _type = widget.current?.nodeType.isNotEmpty == true
        ? widget.current!.nodeType
        : 'STORAGE_AREA';
    _parentId = widget.current?.parentId.isNotEmpty == true
        ? widget.current!.parentId
        : null;
  }

  @override
  void dispose() {
    _code.dispose();
    _name.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: Text(widget.current == null
            ? 'Create Storage Node'
            : 'Edit Storage Node'),
        content: SizedBox(
          width: 560,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              DropdownButtonFormField<String>(
                initialValue: _type,
                decoration: const InputDecoration(labelText: 'Type'),
                items: const [
                  'STORAGE_AREA',
                  'RACK',
                  'SHELF',
                  'BIN',
                  'RECEIVING_AREA',
                ]
                    .map((item) =>
                        DropdownMenuItem(value: item, child: Text(item)))
                    .toList(),
                onChanged: (value) =>
                    setState(() => _type = value ?? 'STORAGE_AREA'),
              ),
              const SizedBox(height: 12),
              DropdownButtonFormField<String>(
                initialValue: _parentId,
                decoration:
                    const InputDecoration(labelText: 'Parent (Optional)'),
                items: [
                  const DropdownMenuItem<String>(
                      value: null, child: Text('Root')),
                  ...widget.availableParents
                      .where((item) => item.id != widget.current?.id)
                      .map(
                        (item) => DropdownMenuItem<String>(
                          value: item.id,
                          child: Text('${item.code} - ${item.name}'),
                        ),
                      ),
                ],
                onChanged: (value) => setState(() => _parentId = value),
              ),
              const SizedBox(height: 12),
              TextField(
                  controller: _code,
                  decoration: const InputDecoration(labelText: 'Code')),
              const SizedBox(height: 12),
              TextField(
                  controller: _name,
                  decoration: const InputDecoration(labelText: 'Name')),
            ],
          ),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Cancel')),
          FilledButton(
            onPressed: () => Navigator.pop(context, {
              'warehouse_id': widget.warehouseId,
              'parent_id': _parentId,
              'node_type': _type,
              'code': _code.text.trim().toUpperCase(),
              'name': _name.text.trim(),
              'sort_order': 0,
              'is_active': true,
            }),
            child: const Text('Save'),
          ),
        ],
      );
}
