import 'package:flutter/material.dart';

import '../core/api/api_client.dart';
import '../core/auth/session_controller.dart';
import '../core/branding/branding_config.dart';
import '../core/navigation/workspace_router.dart';
import '../core/notifications/notification_service.dart';
import '../core/preferences/desktop_preferences_service.dart';
import '../core/security/permission_service.dart';
import '../core/theme/theme_manager.dart';
import '../models/branch_warehouse.dart';
import '../models/entities.dart';
import '../models/inventory.dart';
import '../models/product.dart';
import 'customers/customer_management_page.dart';
import 'inventory/inventory_management_page.dart';
import 'inventory/inventory_details_dialog.dart';
import 'inventory/batch_management_page.dart';
import 'delivery_notes/delivery_note_management_page.dart';
import 'goods_receipts/goods_receipt_management_page.dart';
import 'purchase_invoices/purchase_invoice_management_page.dart';
import 'purchase_returns/purchase_return_management_page.dart';
import 'sales/sales_invoice_management_page.dart';
import 'products/product_management_page.dart';
import 'purchases/purchase_management_page.dart';
import 'sales/sales_order_management_page.dart';
import 'sales/sales_territory_management_page.dart';
import 'tax/tax_configuration_page.dart';
import 'tax/tax_management_page.dart';
import 'tax/tax_rule_simulator_page.dart';
import 'tax/tax_rules_page.dart';
import 'uom/uom_management_page.dart';
import 'vendors/vendor_management_page.dart';
import 'branches/branch_warehouse_management_page.dart';
import 'dashboard_page.dart';
import 'resource_management_page.dart';
import 'theme_selector.dart';
import 'workspace/module_catalog.dart';
import 'workspace/enterprise_sidebar.dart';
import 'workspace/workspace_components.dart';
import 'workspace/global_search.dart';
import 'workspace/workspace_interactions.dart';
import 'workspace/workspace_templates.dart';

class DesktopShell extends StatefulWidget {
  const DesktopShell({
    super.key,
    required this.session,
    required this.preferences,
    required this.branding,
    required this.themes,
    required this.permissions,
  });
  final SessionController session;
  final DesktopPreferencesService preferences;
  final BrandingConfig branding;
  final ThemeManager themes;
  final PermissionService permissions;
  @override
  State<DesktopShell> createState() => _DesktopShellState();
}

class _DesktopShellState extends State<DesktopShell> {
  static const String _globalSearchPreferencesKey = 'workspace.global_search';
  static const String _recentSearchesKey = 'recent_searches';
  static const String _savedSearchesKey = 'saved_searches';
  late final WorkspaceRouter _router;
  late bool _sidebarCollapsed;
  Set<String>? _activeBusinessModuleCodes;
  int _lastFirmContextVersion = 0;

  @override
  void initState() {
    super.initState();
    _sidebarCollapsed = widget.preferences.current.sidebarCollapsed;
    _lastFirmContextVersion = widget.session.firmContextVersion;
    widget.session.addListener(_sessionChanged);
    _router = WorkspaceRouter(
      initialLocation: widget.session.lastWorkspace,
      onPersist: widget.session.saveLastWorkspace,
    )..addListener(_routeChanged);
    _refreshBusinessModules();
  }

  @override
  void dispose() {
    widget.session.removeListener(_sessionChanged);
    _router
      ..removeListener(_routeChanged)
      ..dispose();
    super.dispose();
  }

  void _routeChanged() {
    widget.session.registerActivity();
    if (mounted) setState(() {});
  }

  Future<void> _refreshBusinessModules() async {
    try {
      final List<String> moduleCodes =
          await widget.session.api.activeBusinessModuleCodes();
      if (!mounted) return;
      setState(() => _activeBusinessModuleCodes = moduleCodes.toSet());
    } on ApiException {
      if (!mounted) return;
      setState(() => _activeBusinessModuleCodes = null);
    }
  }

  void _sessionChanged() {
    final int version = widget.session.firmContextVersion;
    if (version == _lastFirmContextVersion) {
      return;
    }
    _lastFirmContextVersion = version;
    _refreshBusinessModules();
  }

  void _select(AppModule section) {
    _router.navigate(section.name);
    Navigator.of(context).maybePop();
  }

  AppModule _routeModule() => AppModule.values.firstWhere(
        (module) => module.name == _router.current.module,
        orElse: () => AppModule.dashboard,
      );

  bool _canAccess(
    List<String> permissions, {
    bool requiresAny = false,
  }) =>
      widget.permissions.canUseModule(permissions, requiresAny: requiresAny);

  List<ModuleDefinition> get _visibleModules => ModuleCatalog.modules
      .where(
        (module) => _canAccess(
          module.requiredPermissions,
          requiresAny: module.requiresAnyPermission,
        ),
      )
      .where(_isEnabledByBusinessProfile)
      .toList();

  bool _isEnabledByBusinessProfile(ModuleDefinition module) {
    final Set<String>? configured = _activeBusinessModuleCodes;
    if (configured == null) {
      return true;
    }
    final String? code = _moduleCode(module.id);
    return code == null || configured.contains(code);
  }

  String? _moduleCode(AppModule module) => switch (module) {
        AppModule.dashboard => 'DASHBOARD',
        AppModule.administration => 'ADMINISTRATION',
        AppModule.masters => 'MASTERS',
        AppModule.sales => 'SALES',
        AppModule.salesOrders => 'SALES_ORDERS',
        AppModule.deliveryNotes => 'DELIVERY_NOTES',
        AppModule.salesInvoices => 'SALES_INVOICES',
        AppModule.purchases => 'PURCHASES',
        AppModule.purchaseInvoices => 'PURCHASE_INVOICES',
        AppModule.purchaseReturns => 'PURCHASE_RETURNS',
        AppModule.goodsReceipts => 'GOODS_RECEIPTS',
        AppModule.inventory => 'INVENTORY',
        AppModule.accounting => 'ACCOUNTING',
        AppModule.reports => 'REPORTS',
        AppModule.settings => 'SETTINGS',
        AppModule.licensing => 'LICENSING',
      };

  @override
  Widget build(BuildContext context) => AnimatedBuilder(
        animation: widget.permissions,
        builder: (context, _) {
          final List<ModuleDefinition> modules = _visibleModules;
          if (modules.isEmpty) {
            return Scaffold(
              appBar: AppBar(
                title: Text(widget.branding.appName),
                actions: [
                  ThemeSelector(manager: widget.themes),
                  const SizedBox(width: 4),
                  TextButton.icon(
                    onPressed: widget.session.logout,
                    icon: const Icon(Icons.logout),
                    label: const Text('Log off'),
                  ),
                  const SizedBox(width: 8),
                ],
              ),
              body: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  const WorkspaceEmptyState(
                    title: 'No workspace access',
                    message:
                        'Your account has no permissions for available modules.',
                  ),
                  const SizedBox(height: 16),
                  Center(
                    child: OutlinedButton.icon(
                      onPressed: widget.session.logout,
                      icon: const Icon(Icons.logout),
                      label: const Text('Log off'),
                    ),
                  ),
                ],
              ),
            );
          }
          final AppModule requestedSection = _routeModule();
          final AppModule section =
              modules.any((module) => module.id == requestedSection)
                  ? requestedSection
                  : modules.first.id;
          return WorkspaceShortcuts(
            bindings: WorkspaceShortcutBindings(
              globalSearch: _openGlobalSearch,
            ),
            child: LayoutBuilder(
              builder: (context, constraints) {
                final bool wide = constraints.maxWidth >= 1000;
                final Widget page = _page(widget.session.api, section);
                if (wide) {
                  return Scaffold(
                    body: Row(children: [
                      SizedBox(
                        width: _sidebarCollapsed ? 64 : 260,
                        child: _navigationPanel(modules, section),
                      ),
                      const VerticalDivider(width: 1),
                      Expanded(
                        child: Column(children: [
                          _applicationHeader(section),
                          const Divider(height: 1),
                          Expanded(child: page),
                          _applicationStatusBar(),
                        ]),
                      ),
                    ]),
                  );
                }
                return Scaffold(
                  appBar: AppBar(
                    title: Text(ModuleCatalog.byId(section).label),
                    actions: [
                      _firmControl(compact: true),
                      ThemeSelector(manager: widget.themes),
                    ],
                  ),
                  drawer: Drawer(
                    child: _navigationPanel(modules, section),
                  ),
                  body: page,
                );
              },
            ),
          );
        },
      );

  Widget _applicationHeader(AppModule section) => Material(
        color: Theme.of(context).colorScheme.surface,
        elevation: 1,
        child: SizedBox(
          height: 68,
          child: Padding(
            padding: const EdgeInsets.only(left: 12, right: 4),
            child: Row(children: [
              Row(
                children: [
                  Icon(
                    Icons.account_balance,
                    size: 20,
                    color: Theme.of(context).colorScheme.primary,
                  ),
                  const SizedBox(width: 8),
                  Text(
                    widget.branding.appName,
                    style: Theme.of(context).textTheme.titleSmall,
                  ),
                ],
              ),
              const SizedBox(width: 6),
              IconButton(
                tooltip: _sidebarCollapsed
                    ? 'Expand navigation'
                    : 'Collapse navigation',
                onPressed: _toggleSidebar,
                icon: Icon(
                  _sidebarCollapsed ? Icons.chevron_right : Icons.chevron_left,
                ),
              ),
              IconButton(
                tooltip: 'Back',
                onPressed: _router.canGoBack ? _router.back : null,
                icon: const Icon(Icons.arrow_back),
              ),
              IconButton(
                tooltip: 'Forward',
                onPressed: _router.canGoForward ? _router.forward : null,
                icon: const Icon(Icons.arrow_forward),
              ),
              const SizedBox(width: 8),
              Flexible(
                child: Text(
                  ModuleCatalog.byId(section).label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: Theme.of(context).textTheme.titleMedium,
                ),
              ),
              const Spacer(),
              _firmControl(),
              const SizedBox(width: 8),
              ThemeSelector(
                manager: widget.themes,
                buttonPadding: EdgeInsets.zero,
              ),
              PopupMenuButton<String>(
                tooltip: 'Profile',
                padding: EdgeInsets.zero,
                icon: const Icon(Icons.account_circle_outlined),
                onSelected: (value) {
                  if (value == 'logout') {
                    widget.session.logout();
                  }
                },
                itemBuilder: (context) => [
                  PopupMenuItem(
                    enabled: false,
                    child: Text(widget.session.attemptedUsername ?? 'User'),
                  ),
                  const PopupMenuDivider(),
                  const PopupMenuItem<String>(
                    value: 'logout',
                    child: ListTile(
                      dense: true,
                      leading: Icon(Icons.logout),
                      title: Text('Sign out'),
                    ),
                  ),
                ],
              ),
            ]),
          ),
        ),
      );

  Widget _firmControl({bool compact = false}) {
    final List<AssignedFirm> firms = widget.session.firms;
    final AssignedFirm? current = widget.session.currentFirm;
    if (firms.length <= 1) {
      return compact
          ? const SizedBox.shrink()
          : Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
              decoration: BoxDecoration(
                color: Theme.of(context).colorScheme.surfaceContainerHigh,
                border: Border.all(
                  color: Theme.of(context).dividerColor.withValues(alpha: .7),
                ),
                borderRadius: BorderRadius.circular(10),
              ),
              child: Row(mainAxisSize: MainAxisSize.min, children: [
                const Icon(Icons.business_outlined, size: 18),
                const SizedBox(width: 8),
                ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 190),
                  child: Text(
                    current?.name ?? 'No firm assigned',
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ]),
            );
    }
    return InkWell(
      borderRadius: BorderRadius.circular(8),
      onTap: _openFirmPicker,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
        decoration: BoxDecoration(
          color: Theme.of(context).colorScheme.surfaceContainerHigh,
          border: Border.all(
            color: Theme.of(context).dividerColor.withValues(alpha: .7),
          ),
          borderRadius: BorderRadius.circular(10),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.business_outlined, size: 18),
            const SizedBox(width: 8),
            if (!compact)
              Padding(
                padding: const EdgeInsets.only(right: 6),
                child: Text(
                  'Agency',
                  style: Theme.of(context).textTheme.labelMedium?.copyWith(
                        color: Theme.of(context).colorScheme.onSurfaceVariant,
                      ),
                ),
              ),
            ConstrainedBox(
              constraints: BoxConstraints(maxWidth: compact ? 90 : 210),
              child: Text(
                compact
                    ? (current?.code ?? 'No firm')
                    : (current?.name ?? 'No firm'),
                overflow: TextOverflow.ellipsis,
              ),
            ),
            const SizedBox(width: 4),
            const Icon(Icons.arrow_drop_down),
          ],
        ),
      ),
    );
  }

  Future<void> _openFirmPicker() async {
    final String? selected = await showDialog<String>(
      context: context,
      builder: (context) => _FirmSwitcherDialog(
        firms: widget.session.firms,
        activeFirmId: widget.session.currentFirm?.id,
      ),
    );
    if (selected != null) {
      await _switchFirm(selected);
    }
  }

  Future<void> _switchFirm(String firmId) async {
    try {
      await widget.session.switchFirm(firmId);
      if (!mounted) return;
      NotificationService.show(
        context,
        'Active firm changed to ${widget.session.currentFirm?.name}.',
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

  Future<void> _openGlobalSearch() => showGlobalSearch(
        context,
        executor: _executeGlobalSearch,
        initialRecentQueries: _storedSearches(_recentSearchesKey),
        initialSavedQueries: _storedSearches(_savedSearchesKey),
        onRecentQueriesChanged: (values) =>
            _saveSearches(_recentSearchesKey, values),
        onSavedQueriesChanged: (values) =>
            _saveSearches(_savedSearchesKey, values),
      );

  Future<GlobalSearchResponse> _executeGlobalSearch(
    GlobalSearchRequest request,
  ) async {
    final String category = _searchCategoryWire(request.category);
    try {
      final Map<String, dynamic> payload =
          await widget.session.api.globalSearch(
        query: request.query,
        category: category,
        page: request.page,
        pageSize: request.pageSize,
        entityTypes: request.entityTypes,
      );
      final List<dynamic> rows = payload['results'] is List
          ? payload['results'] as List<dynamic>
          : const [];
      final List<GlobalSearchResultItem> items = rows
          .whereType<Map>()
          .map((raw) => Map<String, dynamic>.from(raw))
          .map((raw) => GlobalSearchResultItem(
                id: stringValue(raw['id']),
                title: stringValue(raw['title']),
                subtitle: stringValue(raw['subtitle']),
                currentStock: '',
                availableStock: '',
                branch: '',
                warehouse: '',
                status: stringValue(raw['status']),
                productCode: '',
                inventoryId: stringValue(raw['id']),
                entityType: stringValue(raw['entity_type']),
                module: stringValue(raw['module']),
                tab: stringValue(raw['tab']).isEmpty
                    ? null
                    : stringValue(raw['tab']),
                badges: stringList(raw['badges']),
                matchedFields: stringList(raw['matched_fields']),
                navigationPath: stringValue(raw['navigation_path']),
                icon: _searchIcon(stringValue(raw['icon'])),
                onOpen: () => _openSearchResult(raw),
              ))
          .toList(growable: false);
      final int total = (payload['total'] as num?)?.toInt() ?? items.length;
      final int page = (payload['page'] as num?)?.toInt() ?? request.page;
      final int pageSize =
          (payload['page_size'] as num?)?.toInt() ?? request.pageSize;
      final String message = items.isEmpty
          ? 'No results found.'
          : '$total result${total == 1 ? '' : 's'} found.';
      return GlobalSearchResponse(
        results: items,
        message: message,
        page: page,
        pageSize: pageSize,
        total: total,
      );
    } on ApiException {
      // Fall back to inventory-focused search to preserve continuity.
    }
    if (widget.session.currentFirm == null) {
      return const GlobalSearchResponse(
        results: [],
        message: 'Select a firm before searching inventory.',
      );
    }
    final Map<String, InventoryRecord> deduped = <String, InventoryRecord>{};

    Future<void> addRecords(Future<List<InventoryRecord>> future) async {
      for (final InventoryRecord record in await future) {
        deduped.putIfAbsent(record.id, () => record);
      }
    }

    switch (request.category) {
      case GlobalSearchCategory.all:
        await Future.wait([
          addRecords(_searchInventoryDirect(request.query)),
          addRecords(_searchInventoryByProduct(request.query)),
          addRecords(_searchInventoryByWarehouse(request.query)),
          addRecords(_searchInventoryByBranch(request.query)),
        ]);
        break;
      case GlobalSearchCategory.modules:
      case GlobalSearchCategory.documents:
      case GlobalSearchCategory.transactions:
      case GlobalSearchCategory.reports:
      case GlobalSearchCategory.customers:
      case GlobalSearchCategory.vendors:
      case GlobalSearchCategory.inventory:
        await Future.wait([
          addRecords(_searchInventoryDirect(request.query)),
          addRecords(_searchInventoryByProduct(request.query)),
        ]);
        break;
      case GlobalSearchCategory.products:
        await addRecords(_searchInventoryByProduct(request.query));
        break;
      case GlobalSearchCategory.warehouses:
        await addRecords(_searchInventoryByWarehouse(request.query));
        break;
      case GlobalSearchCategory.branches:
        await addRecords(_searchInventoryByBranch(request.query));
        break;
      case GlobalSearchCategory.masters:
      case GlobalSearchCategory.tax:
      case GlobalSearchCategory.organization:
        await addRecords(_searchInventoryDirect(request.query));
        break;
    }

    final List<GlobalSearchResultItem> items =
        deduped.values.take(50).map(_toSearchResult).toList(growable: false);
    return GlobalSearchResponse(
      results: items,
      message: items.isEmpty
          ? 'No inventory results found.'
          : '${items.length} inventory result${items.length == 1 ? '' : 's'} found.',
      page: request.page,
      pageSize: request.pageSize,
      total: items.length,
    );
  }

  Future<void> _openSearchResult(Map<String, dynamic> result) async {
    final String module = stringValue(result['module']);
    final String tab = stringValue(result['tab']);
    if (module.isNotEmpty) {
      _router.navigate(module, tab: tab.isEmpty ? null : tab);
      await widget.session.saveLastWorkspace(
        tab.isEmpty ? module : '$module/$tab',
      );
    }
  }

  String _searchCategoryWire(GlobalSearchCategory category) =>
      switch (category) {
        GlobalSearchCategory.all => 'all',
        GlobalSearchCategory.modules => 'modules',
        GlobalSearchCategory.customers => 'customers',
        GlobalSearchCategory.vendors => 'vendors',
        GlobalSearchCategory.documents => 'documents',
        GlobalSearchCategory.transactions => 'transactions',
        GlobalSearchCategory.reports => 'reports',
        GlobalSearchCategory.masters => 'masters',
        GlobalSearchCategory.inventory => 'inventory',
        GlobalSearchCategory.tax => 'tax',
        GlobalSearchCategory.organization => 'organization',
        GlobalSearchCategory.products => 'masters',
        GlobalSearchCategory.warehouses => 'organization',
        GlobalSearchCategory.branches => 'organization',
      };

  IconData _searchIcon(String icon) => switch (icon) {
        'user' => Icons.person_outline,
        'shield' => Icons.shield_outlined,
        'key' => Icons.key_outlined,
        'apartment' => Icons.apartment_outlined,
        'business' => Icons.business_outlined,
        'toggle' => Icons.toggle_on_outlined,
        'groups' => Icons.groups_outlined,
        'store' => Icons.store_outlined,
        'inventory' => Icons.inventory_2_outlined,
        'point_of_sale' => Icons.point_of_sale_outlined,
        'category' => Icons.category_outlined,
        'account_balance' => Icons.account_balance_outlined,
        'receipt_long' => Icons.receipt_long_outlined,
        'request_quote' => Icons.request_quote_outlined,
        'assignment_return' => Icons.assignment_return_outlined,
        'rule' => Icons.rule_outlined,
        'straighten' => Icons.straighten_outlined,
        'inventory_2' => Icons.inventory_outlined,
        'route' => Icons.route_outlined,
        'alt_route' => Icons.alt_route_outlined,
        'account_tree' => Icons.account_tree_outlined,
        'warehouse' => Icons.warehouse_outlined,
        'shelves' => Icons.view_stream_outlined,
        'upload_file' => Icons.upload_file_outlined,
        'receipt' => Icons.receipt_outlined,
        'layers' => Icons.layers_outlined,
        'dataset' => Icons.dataset_outlined,
        'qr_code_scanner' => Icons.qr_code_scanner_outlined,
        'event_busy' => Icons.event_busy_outlined,
        'public' => Icons.public_outlined,
        'map' => Icons.map_outlined,
        'location_city' => Icons.location_city_outlined,
        'location_on' => Icons.location_on_outlined,
        'pin_drop' => Icons.pin_drop_outlined,
        'settings' => Icons.settings_outlined,
        _ => Icons.search_outlined,
      };

  List<String> _storedSearches(String key) {
    final Map<String, dynamic> preferences = _searchPreferences();
    final dynamic raw = preferences[key];
    if (raw is! List) {
      return const [];
    }
    return raw.whereType<String>().where((value) => value.isNotEmpty).toList();
  }

  Future<void> _saveSearches(String key, List<String> values) async {
    final Map<String, dynamic> preferences = _searchPreferences();
    preferences[key] = values;
    await widget.preferences.cacheServerPreferences({
      ...widget.preferences.current.serverPreferences,
      _globalSearchPreferencesKey: preferences,
    });
  }

  Map<String, dynamic> _searchPreferences() {
    final dynamic raw = widget
        .preferences.current.serverPreferences[_globalSearchPreferencesKey];
    if (raw is! Map) {
      return <String, dynamic>{};
    }
    return Map<String, dynamic>.from(raw);
  }

  Future<List<InventoryRecord>> _searchInventoryDirect(String query) async {
    final PagedResult<InventoryRecord> result =
        await widget.session.api.inventory(
      page: 1,
      pageSize: 25,
      search: query,
    );
    final List<InventoryRecord> items = [...result.items];
    if (_looksLikeUuid(query)) {
      try {
        final InventoryRecord record =
            await widget.session.api.inventoryRecord(query);
        if (!items.any((item) => item.id == record.id)) {
          items.insert(0, record);
        }
      } on ApiException {
        // Ignore exact-id misses and keep broader search results.
      }
    }
    return items;
  }

  Future<List<InventoryRecord>> _searchInventoryByProduct(String query) async {
    final PagedResult<Product> products = await widget.session.api.products(
      page: 1,
      pageSize: 15,
      search: query,
    );
    final List<Future<PagedResult<InventoryRecord>>> lookups = products.items
        .map(
          (product) => widget.session.api.inventory(
            page: 1,
            pageSize: 10,
            filters: InventoryQuery(productId: product.id),
          ),
        )
        .toList(growable: false);
    if (lookups.isEmpty) {
      return const [];
    }
    final List<PagedResult<InventoryRecord>> results =
        await Future.wait(lookups);
    return results.expand((entry) => entry.items).toList(growable: false);
  }

  Future<List<InventoryRecord>> _searchInventoryByWarehouse(
      String query) async {
    final PagedResult<WarehouseRecord> warehouses =
        await widget.session.api.warehouses(
      page: 1,
      pageSize: 15,
      search: query,
    );
    final List<Future<PagedResult<InventoryRecord>>> lookups = warehouses.items
        .map(
          (warehouse) => widget.session.api.inventory(
            page: 1,
            pageSize: 10,
            filters: InventoryQuery(warehouseId: warehouse.id),
          ),
        )
        .toList(growable: false);
    if (lookups.isEmpty) {
      return const [];
    }
    final List<PagedResult<InventoryRecord>> results =
        await Future.wait(lookups);
    return results.expand((entry) => entry.items).toList(growable: false);
  }

  Future<List<InventoryRecord>> _searchInventoryByBranch(String query) async {
    final PagedResult<BranchRecord> branches =
        await widget.session.api.branches(
      page: 1,
      pageSize: 15,
      search: query,
    );
    final List<Future<PagedResult<InventoryRecord>>> lookups = branches.items
        .map(
          (branch) => widget.session.api.inventory(
            page: 1,
            pageSize: 10,
            filters: InventoryQuery(branchId: branch.id),
          ),
        )
        .toList(growable: false);
    if (lookups.isEmpty) {
      return const [];
    }
    final List<PagedResult<InventoryRecord>> results =
        await Future.wait(lookups);
    return results.expand((entry) => entry.items).toList(growable: false);
  }

  GlobalSearchResultItem _toSearchResult(InventoryRecord record) =>
      GlobalSearchResultItem(
        id: record.id,
        title: record.productName,
        subtitle:
            '${record.productCode} • ${record.warehouseCode} • ${record.branchCode}',
        currentStock: record.currentQuantity,
        availableStock: record.availableQuantity,
        branch: record.branchName,
        warehouse: record.warehouseName,
        status: record.status,
        productCode: record.productCode,
        inventoryId: record.id,
        onOpen: () => showInventoryDetailsDialog(
          context,
          record: record,
          onOpenInventory: () =>
              _navigateInventorySearch('inventory', record.id),
          onViewLedger: () =>
              _navigateInventorySearch('stock-ledger', record.productCode),
          onViewTransactions: () =>
              _navigateInventorySearch('transactions', record.productCode),
        ),
        onAction: (action) async {
          switch (action) {
            case GlobalSearchAction.openInventory:
              await _navigateInventorySearch('inventory', record.id);
              break;
            case GlobalSearchAction.viewLedger:
              await _navigateInventorySearch(
                  'stock-ledger', record.productCode);
              break;
            case GlobalSearchAction.viewTransactions:
              await _navigateInventorySearch(
                  'transactions', record.productCode);
              break;
            case GlobalSearchAction.copyProductCode:
            case GlobalSearchAction.copyInventoryId:
              break;
          }
        },
      );

  Future<void> _navigateInventorySearch(String tab, String query) async {
    _router.navigate(AppModule.inventory.name, tab: tab);
    await widget.session.saveLastWorkspace('inventory/$tab');
    if (!mounted) {
      return;
    }
    NotificationService.show(
      context,
      'Opened Inventory > ${tab.replaceAll('-', ' ')} for $query.',
      kind: AppNotificationKind.success,
    );
  }

  bool _looksLikeUuid(String value) => RegExp(
        r'^[0-9a-fA-F]{8}\-[0-9a-fA-F]{4}\-[0-9a-fA-F]{4}\-[0-9a-fA-F]{4}\-[0-9a-fA-F]{12}$',
      ).hasMatch(value.trim());

  Widget _applicationStatusBar() => ApplicationStatusBar(
        stateText: 'Online',
        currentUser: widget.session.attemptedUsername,
        currentFirm: widget.session.currentFirm?.name ?? 'No active firm',
        backend: ConnectionStateIndicator.checking,
        database: ConnectionStateIndicator.unknown,
        environment: Uri.tryParse(widget.session.baseUrl)?.host == 'localhost'
            ? 'Development'
            : 'Configured',
        version: '${widget.branding.companyName} ${widget.branding.version}',
      );

  /// Tab ids the current user can access within [module], used to filter the
  /// unified sidebar's sub-navigation tree (see
  /// `ModuleCatalog.navigationChildren`).
  Set<String> _visibleTabIds(ModuleDefinition module) => module.tabs
      .where((tab) => tab.available)
      .where(
        (tab) => _canAccess(
          tab.requiredPermissions.isEmpty
              ? module.requiredPermissions
              : tab.requiredPermissions,
          requiresAny: tab.requiredPermissions.isEmpty
              ? module.requiresAnyPermission
              : tab.requiresAnyPermission,
        ),
      )
      .map((tab) => tab.id)
      .toSet();

  Widget _navigationPanel(
    List<ModuleDefinition> modules,
    AppModule section,
  ) =>
      EnterpriseSidebar(
        appName: widget.branding.appName,
        modules: modules,
        navigationChildren: (module) => ModuleCatalog.navigationChildren(
          module.id,
          _visibleTabIds(module),
        ),
        selectedModule: section,
        selectedPath: _router.current.tab,
        onSelectModule: _select,
        onSelectLeaf: (module, path) {
          if (module != section) {
            _router.navigate(module.name, tab: path);
          } else {
            _router.selectTab(path);
          }
          Navigator.of(context).maybePop();
        },
        collapsed: _sidebarCollapsed,
        onToggleCollapsed: _toggleSidebar,
        sections: _navigationSections(modules),
        footer: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
          child: _sidebarCollapsed
              ? IconButton(
                  tooltip: 'Sign out',
                  icon: const Icon(Icons.logout),
                  onPressed: widget.session.logout,
                )
              : Row(children: [
                  Expanded(child: ThemeSelector(manager: widget.themes)),
                  IconButton(
                    tooltip: 'Sign out',
                    icon: const Icon(Icons.logout),
                    onPressed: widget.session.logout,
                  ),
                ]),
        ),
      );

  List<EnterpriseSidebarSection> _navigationSections(
      List<ModuleDefinition> modules) {
    final Set<AppModule> available = modules.map((module) => module.id).toSet();
    List<AppModule> pick(List<AppModule> values) =>
        values.where(available.contains).toList();
    final List<EnterpriseSidebarSection> sections = [
      EnterpriseSidebarSection(
        label: 'CORE',
        moduleIds: pick([AppModule.dashboard, AppModule.administration]),
      ),
      EnterpriseSidebarSection(
        label: 'MASTERS',
        moduleIds: pick([AppModule.masters]),
      ),
      EnterpriseSidebarSection(
        label: 'TRANSACTIONS',
        moduleIds: pick([
          AppModule.purchases,
          AppModule.purchaseInvoices,
          AppModule.purchaseReturns,
          AppModule.goodsReceipts,
          AppModule.sales,
          AppModule.salesOrders,
          AppModule.deliveryNotes,
          AppModule.salesInvoices,
        ]),
      ),
      EnterpriseSidebarSection(
        label: 'INVENTORY',
        moduleIds: pick([AppModule.inventory]),
      ),
      EnterpriseSidebarSection(
        label: 'FINANCE',
        moduleIds: pick([AppModule.accounting]),
      ),
      EnterpriseSidebarSection(
        label: 'REPORTS',
        moduleIds: pick([AppModule.reports]),
      ),
      EnterpriseSidebarSection(
        label: 'SETUP',
        moduleIds: pick([AppModule.licensing, AppModule.settings]),
      ),
    ];
    return sections.where((section) => section.moduleIds.isNotEmpty).toList();
  }

  Future<void> _toggleSidebar() async {
    setState(() => _sidebarCollapsed = !_sidebarCollapsed);
    await widget.preferences.saveSidebarCollapsed(_sidebarCollapsed);
  }

  Widget _page(ApiClient api, AppModule section) => switch (section) {
        AppModule.dashboard => DashboardPage(
            key: ValueKey('dashboard-${widget.session.firmContextVersion}'),
            api: api,
            permissions: widget.permissions,
          ),
        AppModule.administration => _AdministrationWorkspace(
            key: ValueKey(
              'administration-${widget.session.firmContextVersion}',
            ),
            api: api,
            permissions: widget.permissions,
            router: _router,
          ),
        AppModule.masters => _MastersWorkspace(
            key: ValueKey('masters-${widget.session.firmContextVersion}'),
            api: api,
            permissions: widget.permissions,
            preferences: widget.preferences,
            router: _router,
          ),
        AppModule.sales => _SalesWorkspace(
            key: ValueKey('sales-${widget.session.firmContextVersion}'),
            api: api,
            permissions: widget.permissions,
            router: _router,
          ),
        AppModule.salesOrders => SalesOrderManagementPage(
            key: ValueKey('sales-orders-${widget.session.firmContextVersion}'),
            api: api,
            preferences: widget.preferences,
            permissions: widget.permissions,
            hasActiveFirm: widget.session.currentFirm != null,
            onOpenGlobalSearch: _openGlobalSearch,
          ),
        AppModule.deliveryNotes => _DeliveryNoteWorkspace(
            key:
                ValueKey('delivery-notes-${widget.session.firmContextVersion}'),
            api: api,
            preferences: widget.preferences,
            permissions: widget.permissions,
            router: _router,
            onOpenGlobalSearch: _openGlobalSearch,
          ),
        AppModule.salesInvoices => SalesInvoiceManagementPage(
            key:
                ValueKey('sales-invoices-${widget.session.firmContextVersion}'),
            api: api,
            preferences: widget.preferences,
            permissions: widget.permissions,
            hasActiveFirm: widget.session.currentFirm != null,
            onOpenGlobalSearch: _openGlobalSearch,
          ),
        AppModule.inventory => _InventoryWorkspace(
            key: ValueKey('inventory-${widget.session.firmContextVersion}'),
            api: api,
            preferences: widget.preferences,
            permissions: widget.permissions,
            router: _router,
          ),
        AppModule.purchases => _PurchaseWorkspace(
            key: ValueKey('purchases-${widget.session.firmContextVersion}'),
            api: api,
            preferences: widget.preferences,
            permissions: widget.permissions,
            router: _router,
            onOpenGlobalSearch: _openGlobalSearch,
          ),
        AppModule.purchaseInvoices => PurchaseInvoiceManagementPage(
            key: ValueKey(
              'purchase-invoices-${widget.session.firmContextVersion}',
            ),
            api: api,
            preferences: widget.preferences,
            permissions: widget.permissions,
            hasActiveFirm: widget.session.currentFirm != null,
            onOpenGlobalSearch: _openGlobalSearch,
          ),
        AppModule.purchaseReturns => PurchaseReturnManagementPage(
            key: ValueKey(
              'purchase-returns-${widget.session.firmContextVersion}',
            ),
            api: api,
            preferences: widget.preferences,
            permissions: widget.permissions,
            hasActiveFirm: widget.session.currentFirm != null,
            onOpenGlobalSearch: _openGlobalSearch,
          ),
        AppModule.goodsReceipts => _GoodsReceiptWorkspace(
            key: ValueKey(
              'goods-receipts-${widget.session.firmContextVersion}',
            ),
            api: api,
            preferences: widget.preferences,
            permissions: widget.permissions,
            router: _router,
            onOpenGlobalSearch: _openGlobalSearch,
          ),
        AppModule.accounting ||
        AppModule.reports ||
        AppModule.licensing ||
        AppModule.settings =>
          _ComingSoonModule(
            module: ModuleCatalog.byId(section),
            permissions: widget.permissions,
          ),
      };
}

class _FirmSwitcherDialog extends StatefulWidget {
  const _FirmSwitcherDialog({
    required this.firms,
    required this.activeFirmId,
  });

  final List<AssignedFirm> firms;
  final String? activeFirmId;

  @override
  State<_FirmSwitcherDialog> createState() => _FirmSwitcherDialogState();
}

class _FirmSwitcherDialogState extends State<_FirmSwitcherDialog> {
  final TextEditingController _searchController = TextEditingController();

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: const Text('Switch firm'),
        content: SizedBox(
          width: 420,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: _searchController,
                autofocus: true,
                decoration: const InputDecoration(
                  prefixIcon: Icon(Icons.search),
                  hintText: 'Search firms',
                ),
                onChanged: (_) => setState(() {}),
              ),
              const SizedBox(height: 10),
              SizedBox(
                height: 320,
                child: ListView(
                  children: _filteredFirms()
                      .map(
                        (firm) => ListTile(
                          dense: true,
                          leading: const Icon(Icons.business_outlined),
                          title: Text(firm.name),
                          subtitle: Text(firm.code),
                          trailing: firm.id == widget.activeFirmId
                              ? const Icon(Icons.check, size: 18)
                              : null,
                          onTap: () => Navigator.of(context).pop(firm.id),
                        ),
                      )
                      .toList(),
                ),
              ),
            ],
          ),
        ),
      );

  List<AssignedFirm> _filteredFirms() {
    final String query = _searchController.text.trim().toLowerCase();
    if (query.isEmpty) {
      return widget.firms;
    }
    return widget.firms
        .where(
          (firm) =>
              firm.name.toLowerCase().contains(query) ||
              firm.code.toLowerCase().contains(query),
        )
        .toList();
  }
}

class _AdministrationWorkspace extends StatefulWidget {
  const _AdministrationWorkspace({
    super.key,
    required this.api,
    required this.permissions,
    required this.router,
  });
  final ApiClient api;
  final PermissionService permissions;
  final WorkspaceRouter router;

  @override
  State<_AdministrationWorkspace> createState() =>
      _AdministrationWorkspaceState();
}

class _AdministrationWorkspaceState extends State<_AdministrationWorkspace> {
  @override
  Widget build(BuildContext context) {
    final ModuleDefinition module =
        ModuleCatalog.byId(AppModule.administration);
    final List<ModuleTabDefinition> visibleTabs = module.tabs
        // A tab declared `available: false` has no workspace behind it, so
        // showing it routes the user to an unrelated screen.
        .where((tab) => tab.available)
        .where(
          (tab) => widget.permissions.canUseTab(
            tab.requiredPermissions.isEmpty
                ? module.requiredPermissions
                : tab.requiredPermissions,
            requiresAny: tab.requiredPermissions.isEmpty
                ? module.requiresAnyPermission
                : tab.requiresAnyPermission,
          ),
        )
        .toList();
    if (visibleTabs.isEmpty) {
      return const WorkspaceEmptyState(
        title: 'No administration access',
        message: 'Your account cannot access an administration workspace.',
      );
    }
    final Set<String> visibleTabIds = visibleTabs.map((tab) => tab.id).toSet();
    String firstAvailableTab() => [
          'users',
          'roles',
          'permissions',
          'user-firms',
          'business-profiles',
          'feature-management',
          'module-configuration',
          'attribute-definitions',
          'profile-assignment',
          'tax-configuration',
          'tax-rules-page',
          'tax-rule-simulator',
          'tax-execution-log',
          'tax-settings',
          'uoms',
          'uom-groups',
          'packaging-types',
          'conversion-rules',
          'industry-templates',
        ].firstWhere(
          visibleTabIds.contains,
          // Not every visible tab is listed above, so a valid permission set can
          // match none of them. Without a fallback that throws a StateError
          // instead of rendering a workspace.
          orElse: () => visibleTabs.first.id,
        );
    final String? requestedTab =
        widget.router.current.module == AppModule.administration.name
            ? widget.router.current.tab
            : null;
    final String tabId = visibleTabIds.contains(requestedTab)
        ? requestedTab!
        : firstAvailableTab();
    final Widget content = switch (tabId) {
      'users' => ResourceManagementPage<PlatformUser>(
          api: widget.api,
          definition: _userDefinition(
            widget.api,
            widget.permissions,
            showFrame: false,
          ),
        ),
      'roles' => ResourceManagementPage<Role>(
          api: widget.api,
          definition: _roleDefinition(
            widget.api,
            widget.permissions,
            showFrame: false,
          ),
        ),
      'permissions' => ResourceManagementPage<Permission>(
          api: widget.api,
          definition: _permissionDefinition(
            widget.api,
            widget.permissions,
            showFrame: false,
          ),
        ),
      'user-firms' => ResourceManagementPage<PlatformUser>(
          api: widget.api,
          definition:
              _userFirmAssignmentDefinition(widget.api, widget.permissions),
        ),
      'business-profiles' => ResourceManagementPage<BusinessProfileRecord>(
          api: widget.api,
          definition: _businessProfileDefinition(
            widget.api,
            widget.permissions,
            showFrame: false,
          ),
        ),
      'feature-management' => ResourceManagementPage<BusinessFeatureRecord>(
          api: widget.api,
          definition: _businessFeatureDefinition(
            widget.api,
            widget.permissions,
            showFrame: false,
          ),
        ),
      'module-configuration' => ResourceManagementPage<BusinessModuleRecord>(
          api: widget.api,
          definition: _businessModuleDefinition(
            widget.api,
            widget.permissions,
            showFrame: false,
          ),
        ),
      'attribute-definitions' =>
        ResourceManagementPage<AttributeDefinitionRecord>(
          api: widget.api,
          definition: _attributeDefinitionDefinition(
            widget.api,
            widget.permissions,
            showFrame: false,
          ),
        ),
      'profile-assignment' => ResourceManagementPage<Firm>(
          api: widget.api,
          definition:
              _firmProfileAssignmentDefinition(widget.api, widget.permissions),
        ),
      'tax-configuration' => TaxConfigurationPage(
          api: widget.api,
          permissions: widget.permissions,
        ),
      'tax-rules-page' => TaxRulesPage(
          api: widget.api,
          permissions: widget.permissions,
        ),
      'tax-rule-simulator' => TaxRuleSimulatorPage(
          api: widget.api,
          permissions: widget.permissions,
        ),
      'tax-execution-log' => TaxManagementPage(
          api: widget.api,
          permissions: widget.permissions,
          hasActiveFirm: widget.api.activeFirmId?.call() != null,
          section: TaxManagementSection.executionLog,
        ),
      'tax-settings' => TaxManagementPage(
          api: widget.api,
          permissions: widget.permissions,
          hasActiveFirm: widget.api.activeFirmId?.call() != null,
          section: TaxManagementSection.settings,
        ),
      'uoms' => UomManagementPage(
          api: widget.api,
          permissions: widget.permissions,
          hasActiveFirm: widget.api.activeFirmId?.call() != null,
          section: UomManagementSection.uoms,
        ),
      'uom-groups' => UomManagementPage(
          api: widget.api,
          permissions: widget.permissions,
          hasActiveFirm: widget.api.activeFirmId?.call() != null,
          section: UomManagementSection.uomGroups,
        ),
      'packaging-types' => UomManagementPage(
          api: widget.api,
          permissions: widget.permissions,
          hasActiveFirm: widget.api.activeFirmId?.call() != null,
          section: UomManagementSection.packagingTypes,
        ),
      'conversion-rules' => UomManagementPage(
          api: widget.api,
          permissions: widget.permissions,
          hasActiveFirm: widget.api.activeFirmId?.call() != null,
          section: UomManagementSection.conversionRules,
        ),
      'industry-templates' => UomManagementPage(
          api: widget.api,
          permissions: widget.permissions,
          hasActiveFirm: widget.api.activeFirmId?.call() != null,
          section: UomManagementSection.industryTemplates,
        ),
      _ => const WorkspaceEmptyState(
          title: 'User Audit is coming soon',
          message: 'Audit records are not available from the current API.',
        ),
    };
    return ConfigurationWorkspace(
      title: module.label,
      description: module.description,
      breadcrumbs: const ['Workspace', 'Administration'],
      // Sub-navigation now lives in the unified EnterpriseSidebar tree
      // (ModuleCatalog.navigationChildren), so no second panel is rendered
      // here — the workspace uses its full width for content.
      content: content,
    );
  }
}

class _MastersWorkspace extends StatefulWidget {
  const _MastersWorkspace({
    super.key,
    required this.api,
    required this.permissions,
    required this.preferences,
    required this.router,
  });
  final ApiClient api;
  final PermissionService permissions;
  final DesktopPreferencesService preferences;
  final WorkspaceRouter router;

  @override
  State<_MastersWorkspace> createState() => _MastersWorkspaceState();
}

class _MastersWorkspaceState extends State<_MastersWorkspace> {
  @override
  Widget build(BuildContext context) {
    final ModuleDefinition module = ModuleCatalog.byId(AppModule.masters);
    final List<ModuleTabDefinition> visibleTabs = module.tabs
        // A tab declared `available: false` has no workspace behind it, so
        // showing it routes the user to an unrelated screen.
        .where((tab) => tab.available)
        .where(
          (tab) => widget.permissions.canUseTab(
            tab.requiredPermissions.isEmpty
                ? module.requiredPermissions
                : tab.requiredPermissions,
            requiresAny: tab.requiredPermissions.isEmpty
                ? module.requiresAnyPermission
                : tab.requiresAnyPermission,
          ),
        )
        .toList();
    final String? requestedTab =
        widget.router.current.module == AppModule.masters.name
            ? widget.router.current.tab
            : null;
    final String tabId = visibleTabs.any((tab) => tab.id == requestedTab)
        ? requestedTab!
        : visibleTabs.first.id;
    final bool hasActiveFirm = widget.api.activeFirmId?.call() != null;
    final Widget content = switch (tabId) {
      'firms' => ResourceManagementPage<Firm>(
          api: widget.api,
          definition: firmDefinition(
            widget.api,
            widget.permissions,
            showFrame: false,
          ),
        ),
      'customers' => CustomerManagementPage(
          api: widget.api,
          permissions: widget.permissions,
          hasActiveFirm: hasActiveFirm,
        ),
      'products' => ProductManagementPage(
          api: widget.api,
          permissions: widget.permissions,
          preferences: widget.preferences,
          hasActiveFirm: hasActiveFirm,
        ),
      'vendors' => VendorManagementPage(
          api: widget.api,
          permissions: widget.permissions,
          hasActiveFirm: hasActiveFirm,
        ),
      'branches' => BranchWarehouseManagementPage(
          api: widget.api,
          permissions: widget.permissions,
          hasActiveFirm: hasActiveFirm,
          section: BranchWarehouseSection.branches,
        ),
      'warehouses' => BranchWarehouseManagementPage(
          api: widget.api,
          permissions: widget.permissions,
          hasActiveFirm: hasActiveFirm,
          section: BranchWarehouseSection.warehouses,
        ),
      'storage-areas' => BranchWarehouseManagementPage(
          api: widget.api,
          permissions: widget.permissions,
          hasActiveFirm: hasActiveFirm,
          section: BranchWarehouseSection.storageAreas,
        ),
      'warehouse-types' => BranchWarehouseManagementPage(
          api: widget.api,
          permissions: widget.permissions,
          hasActiveFirm: hasActiveFirm,
          section: BranchWarehouseSection.warehouseTypes,
        ),
      'branch-types' => BranchWarehouseManagementPage(
          api: widget.api,
          permissions: widget.permissions,
          hasActiveFirm: hasActiveFirm,
          section: BranchWarehouseSection.branchTypes,
        ),
      'branch-warehouse-settings' => BranchWarehouseManagementPage(
          api: widget.api,
          permissions: widget.permissions,
          hasActiveFirm: hasActiveFirm,
          section: BranchWarehouseSection.settings,
        ),
      _ => WorkspaceEmptyState(
          title:
              '${visibleTabs.firstWhere((tab) => tab.id == tabId).label} is coming soon',
          message:
              'The current API does not provide ${visibleTabs.firstWhere((tab) => tab.id == tabId).label.toLowerCase()} operations.',
        ),
    };
    return ModuleWorkspaceFrame(
      title: switch (tabId) {
        'customers' => 'Customer Management',
        'products' => 'Product Management',
        'vendors' => 'Vendor Management',
        'branches' => 'Branch Management',
        'warehouses' => 'Warehouse Management',
        'storage-areas' => 'Storage Area Management',
        'warehouse-types' => 'Warehouse Type Management',
        'branch-types' => 'Branch Type Management',
        'branch-warehouse-settings' => 'Branch & Warehouse Settings',
        _ => 'Firm Management',
      },
      description: switch (tabId) {
        'customers' =>
          'Manage firm-scoped customer masters, addresses, and contacts.',
        'products' =>
          'Manage profile-driven product masters with dynamic attributes.',
        'vendors' =>
          'Manage enterprise vendor masters with contacts, addresses, banking, and tax details.',
        'branches' =>
          'Manage branch hierarchy, managers, and operational status.',
        'warehouses' =>
          'Manage warehouses by branch with capacity and control settings.',
        'storage-areas' =>
          'Manage configurable warehouse storage structures and nodes.',
        'warehouse-types' => 'Manage reusable warehouse type masters.',
        'branch-types' => 'Manage reusable branch type masters.',
        'branch-warehouse-settings' =>
          'Configure future-ready branch and warehouse defaults.',
        _ => 'Manage organization records and future firm configuration.',
      },
      breadcrumbs: [
        'Workspace',
        'Masters',
        switch (tabId) {
          'customers' => 'Customer Management',
          'products' => 'Product Management',
          'vendors' => 'Vendor Management',
          'branches' => 'Branch Management',
          'warehouses' => 'Warehouse Management',
          'storage-areas' => 'Storage Area Management',
          'warehouse-types' => 'Warehouse Type Management',
          'branch-types' => 'Branch Type Management',
          'branch-warehouse-settings' => 'Branch & Warehouse Settings',
          _ => 'Firm Management',
        },
      ],
      child: content,
    );
  }
}

class _SalesWorkspace extends StatefulWidget {
  const _SalesWorkspace({
    super.key,
    required this.api,
    required this.permissions,
    required this.router,
  });

  final ApiClient api;
  final PermissionService permissions;
  final WorkspaceRouter router;

  @override
  State<_SalesWorkspace> createState() => _SalesWorkspaceState();
}

class _SalesWorkspaceState extends State<_SalesWorkspace> {
  @override
  Widget build(BuildContext context) {
    final ModuleDefinition module = ModuleCatalog.byId(AppModule.sales);
    final List<ModuleTabDefinition> visibleTabs = module.tabs
        // A tab declared `available: false` has no workspace behind it, so
        // showing it routes the user to an unrelated screen.
        .where((tab) => tab.available)
        .where(
          (tab) => widget.permissions.canUseTab(
            tab.requiredPermissions.isEmpty
                ? module.requiredPermissions
                : tab.requiredPermissions,
            requiresAny: tab.requiredPermissions.isEmpty
                ? module.requiresAnyPermission
                : tab.requiresAnyPermission,
          ),
        )
        .toList();
    if (visibleTabs.isEmpty) {
      return const WorkspaceEmptyState(
        title: 'No sales access',
        message: 'Your account cannot access a sales workspace.',
      );
    }
    final String? requestedTab =
        widget.router.current.module == AppModule.sales.name
            ? widget.router.current.tab
            : null;
    final String tabId = visibleTabs.any((tab) => tab.id == requestedTab)
        ? requestedTab!
        : visibleTabs.first.id;

    final Widget content = switch (tabId) {
      'territories' => SalesTerritoryManagementPage(
          api: widget.api,
          permissions: widget.permissions,
        ),
      _ => WorkspaceEmptyState(
          title:
              '${visibleTabs.firstWhere((tab) => tab.id == tabId).label} is coming soon',
          message:
              'The current API does not provide ${visibleTabs.firstWhere((tab) => tab.id == tabId).label.toLowerCase()} operations.',
        ),
    };

    return ModuleWorkspaceFrame(
      title: tabId == 'territories' ? 'Geography Management' : module.label,
      description: tabId == 'territories'
          ? 'Configure multi-level territory hierarchy, assignments, and routing foundation.'
          : module.description,
      breadcrumbs: [
        'Workspace',
        'Sales',
        if (tabId == 'territories') 'Geography',
      ],
      child: content,
    );
  }
}

class _PurchaseWorkspace extends StatefulWidget {
  const _PurchaseWorkspace({
    super.key,
    required this.api,
    required this.preferences,
    required this.permissions,
    required this.router,
    required this.onOpenGlobalSearch,
  });

  final ApiClient api;
  final DesktopPreferencesService preferences;
  final PermissionService permissions;
  final WorkspaceRouter router;
  final Future<void> Function() onOpenGlobalSearch;

  @override
  State<_PurchaseWorkspace> createState() => _PurchaseWorkspaceState();
}

class _PurchaseWorkspaceState extends State<_PurchaseWorkspace> {
  @override
  Widget build(BuildContext context) {
    final ModuleDefinition module = ModuleCatalog.byId(AppModule.purchases);
    final List<ModuleTabDefinition> visibleTabs = module.tabs
        // A tab declared `available: false` has no workspace behind it, so
        // showing it routes the user to an unrelated screen.
        .where((tab) => tab.available)
        .where(
          (tab) => widget.permissions.canUseTab(
            tab.requiredPermissions.isEmpty
                ? module.requiredPermissions
                : tab.requiredPermissions,
            requiresAny: tab.requiredPermissions.isEmpty
                ? module.requiresAnyPermission
                : tab.requiresAnyPermission,
          ),
        )
        .toList();
    if (visibleTabs.isEmpty) {
      return const WorkspaceEmptyState(
        title: 'No purchase access',
        message: 'Your account cannot access a purchase workspace.',
      );
    }
    final String? requestedTab =
        widget.router.current.module == AppModule.purchases.name
            ? widget.router.current.tab
            : null;
    final String tabId = visibleTabs.any((tab) => tab.id == requestedTab)
        ? requestedTab!
        : visibleTabs.first.id;
    final bool hasActiveFirm =
        widget.api.activeFirmId?.call()?.isNotEmpty == true;
    void navigateTo(PurchaseSection section) {
      final String nextTab = switch (section) {
        PurchaseSection.dashboard => 'purchase-dashboard',
        PurchaseSection.purchaseOrders => 'purchase-orders',
        PurchaseSection.rfqs => 'purchase-rfqs',
        PurchaseSection.vendorQuotations => 'vendor-quotations',
        PurchaseSection.draftOrders => 'draft-orders',
        PurchaseSection.openOrders => 'open-orders',
        PurchaseSection.cancelledOrders => 'cancelled-orders',
        PurchaseSection.closedOrders => 'closed-orders',
        PurchaseSection.history => 'purchase-history',
        PurchaseSection.analytics => 'purchase-analytics',
        PurchaseSection.settings => 'purchase-settings',
      };
      widget.router.selectTab(nextTab);
    }

    final Widget content = switch (tabId) {
      'purchase-dashboard' => PurchaseManagementPage(
          api: widget.api,
          preferences: widget.preferences,
          permissions: widget.permissions,
          hasActiveFirm: hasActiveFirm,
          section: PurchaseSection.dashboard,
          onNavigateToSection: navigateTo,
          onOpenGlobalSearch: widget.onOpenGlobalSearch,
        ),
      'purchase-orders' => PurchaseManagementPage(
          api: widget.api,
          preferences: widget.preferences,
          permissions: widget.permissions,
          hasActiveFirm: hasActiveFirm,
          section: PurchaseSection.purchaseOrders,
          onNavigateToSection: navigateTo,
          onOpenGlobalSearch: widget.onOpenGlobalSearch,
        ),
      'purchase-rfqs' => PurchaseManagementPage(
          api: widget.api,
          preferences: widget.preferences,
          permissions: widget.permissions,
          hasActiveFirm: hasActiveFirm,
          section: PurchaseSection.rfqs,
          onNavigateToSection: navigateTo,
          onOpenGlobalSearch: widget.onOpenGlobalSearch,
        ),
      'vendor-quotations' => PurchaseManagementPage(
          api: widget.api,
          preferences: widget.preferences,
          permissions: widget.permissions,
          hasActiveFirm: hasActiveFirm,
          section: PurchaseSection.vendorQuotations,
          onNavigateToSection: navigateTo,
          onOpenGlobalSearch: widget.onOpenGlobalSearch,
        ),
      'draft-orders' => PurchaseManagementPage(
          api: widget.api,
          preferences: widget.preferences,
          permissions: widget.permissions,
          hasActiveFirm: hasActiveFirm,
          section: PurchaseSection.draftOrders,
          onNavigateToSection: navigateTo,
          onOpenGlobalSearch: widget.onOpenGlobalSearch,
        ),
      'open-orders' => PurchaseManagementPage(
          api: widget.api,
          preferences: widget.preferences,
          permissions: widget.permissions,
          hasActiveFirm: hasActiveFirm,
          section: PurchaseSection.openOrders,
          onNavigateToSection: navigateTo,
          onOpenGlobalSearch: widget.onOpenGlobalSearch,
        ),
      'cancelled-orders' => PurchaseManagementPage(
          api: widget.api,
          preferences: widget.preferences,
          permissions: widget.permissions,
          hasActiveFirm: hasActiveFirm,
          section: PurchaseSection.cancelledOrders,
          onNavigateToSection: navigateTo,
          onOpenGlobalSearch: widget.onOpenGlobalSearch,
        ),
      'closed-orders' => PurchaseManagementPage(
          api: widget.api,
          preferences: widget.preferences,
          permissions: widget.permissions,
          hasActiveFirm: hasActiveFirm,
          section: PurchaseSection.closedOrders,
          onNavigateToSection: navigateTo,
          onOpenGlobalSearch: widget.onOpenGlobalSearch,
        ),
      'purchase-history' => PurchaseManagementPage(
          api: widget.api,
          preferences: widget.preferences,
          permissions: widget.permissions,
          hasActiveFirm: hasActiveFirm,
          section: PurchaseSection.history,
          onNavigateToSection: navigateTo,
          onOpenGlobalSearch: widget.onOpenGlobalSearch,
        ),
      'purchase-analytics' => PurchaseManagementPage(
          api: widget.api,
          preferences: widget.preferences,
          permissions: widget.permissions,
          hasActiveFirm: hasActiveFirm,
          section: PurchaseSection.analytics,
          onNavigateToSection: navigateTo,
          onOpenGlobalSearch: widget.onOpenGlobalSearch,
        ),
      'purchase-settings' => PurchaseManagementPage(
          api: widget.api,
          preferences: widget.preferences,
          permissions: widget.permissions,
          hasActiveFirm: hasActiveFirm,
          section: PurchaseSection.settings,
          onNavigateToSection: navigateTo,
          onOpenGlobalSearch: widget.onOpenGlobalSearch,
        ),
      _ => const WorkspaceEmptyState(
          title: 'Purchase workspace unavailable',
          message: 'The selected purchase workspace is not available.',
        ),
    };

    return ModuleWorkspaceFrame(
      title: switch (tabId) {
        'purchase-dashboard' => 'Purchase Dashboard',
        'purchase-orders' => 'Purchase Orders',
        'purchase-rfqs' => 'Request for Quotations',
        'vendor-quotations' => 'Vendor Quotations',
        'draft-orders' => 'Draft Purchase Orders',
        'open-orders' => 'Open Purchase Orders',
        'cancelled-orders' => 'Cancelled Purchase Orders',
        'closed-orders' => 'Closed Purchase Orders',
        'purchase-history' => 'Purchase History',
        'purchase-analytics' => 'Purchase Analytics',
        'purchase-settings' => 'Purchase Settings',
        _ => module.label,
      },
      description: switch (tabId) {
        'purchase-dashboard' =>
          'Enterprise purchase command center with KPI cards, recent orders, and vendor spend insights.',
        'purchase-orders' =>
          'Manage purchase orders with lifecycle actions, import/export, and responsive enterprise editing.',
        'purchase-rfqs' =>
          'RFQ extension point reserved for the next backend purchase phase.',
        'vendor-quotations' =>
          'Vendor quotation extension point reserved for the next backend purchase phase.',
        'draft-orders' =>
          'Review and complete purchase orders that remain in draft state.',
        'open-orders' =>
          'Monitor active purchase orders pending execution and delivery.',
        'cancelled-orders' =>
          'Audit cancelled purchase orders and restoration candidates.',
        'closed-orders' => 'Review completed and closed purchase lifecycles.',
        'purchase-history' =>
          'Inspect history timelines from the purchase history backend API.',
        'purchase-analytics' =>
          'Analytics shell ready for backend reporting expansion.',
        'purchase-settings' =>
          'Manage purchase grid views and enterprise workspace defaults.',
        _ => module.description,
      },
      breadcrumbs: [
        'Workspace',
        'Purchases',
        if (tabId != 'purchase-dashboard')
          visibleTabs.firstWhere((tab) => tab.id == tabId).label,
      ],
      child: content,
    );
  }
}

class _GoodsReceiptWorkspace extends StatefulWidget {
  const _GoodsReceiptWorkspace({
    super.key,
    required this.api,
    required this.preferences,
    required this.permissions,
    required this.router,
    required this.onOpenGlobalSearch,
  });

  final ApiClient api;
  final DesktopPreferencesService preferences;
  final PermissionService permissions;
  final WorkspaceRouter router;
  final Future<void> Function() onOpenGlobalSearch;

  @override
  State<_GoodsReceiptWorkspace> createState() => _GoodsReceiptWorkspaceState();
}

class _GoodsReceiptWorkspaceState extends State<_GoodsReceiptWorkspace> {
  @override
  Widget build(BuildContext context) {
    final ModuleDefinition module = ModuleCatalog.byId(AppModule.goodsReceipts);
    final List<ModuleTabDefinition> visibleTabs = module.tabs
        // A tab declared `available: false` has no workspace behind it, so
        // showing it routes the user to an unrelated screen.
        .where((tab) => tab.available)
        .where(
          (tab) => widget.permissions.canUseTab(
            tab.requiredPermissions.isEmpty
                ? module.requiredPermissions
                : tab.requiredPermissions,
            requiresAny: tab.requiredPermissions.isEmpty
                ? module.requiresAnyPermission
                : tab.requiresAnyPermission,
          ),
        )
        .toList();
    if (visibleTabs.isEmpty) {
      return const WorkspaceEmptyState(
        title: 'No goods receipt access',
        message: 'Your account cannot access a goods receipt workspace.',
      );
    }
    final String? requestedTab =
        widget.router.current.module == AppModule.goodsReceipts.name
            ? widget.router.current.tab
            : null;
    final String tabId = visibleTabs.any((tab) => tab.id == requestedTab)
        ? requestedTab!
        : visibleTabs.first.id;
    final bool hasActiveFirm =
        widget.api.activeFirmId?.call()?.isNotEmpty == true;

    return GoodsReceiptManagementPage(
      api: widget.api,
      preferences: widget.preferences,
      permissions: widget.permissions,
      hasActiveFirm: hasActiveFirm,
      tabId: tabId,
      onNavigateToTab: (nextTab) => widget.router.selectTab(nextTab),
      onOpenGlobalSearch: widget.onOpenGlobalSearch,
    );
  }
}

class _DeliveryNoteWorkspace extends StatefulWidget {
  const _DeliveryNoteWorkspace({
    super.key,
    required this.api,
    required this.preferences,
    required this.permissions,
    required this.router,
    required this.onOpenGlobalSearch,
  });

  final ApiClient api;
  final DesktopPreferencesService preferences;
  final PermissionService permissions;
  final WorkspaceRouter router;
  final Future<void> Function() onOpenGlobalSearch;

  @override
  State<_DeliveryNoteWorkspace> createState() => _DeliveryNoteWorkspaceState();
}

class _DeliveryNoteWorkspaceState extends State<_DeliveryNoteWorkspace> {
  @override
  Widget build(BuildContext context) {
    final ModuleDefinition module = ModuleCatalog.byId(AppModule.deliveryNotes);
    final List<ModuleTabDefinition> visibleTabs = module.tabs
        // A tab declared `available: false` has no workspace behind it, so
        // showing it routes the user to an unrelated screen.
        .where((tab) => tab.available)
        .where(
          (tab) => widget.permissions.canUseTab(
            tab.requiredPermissions.isEmpty
                ? module.requiredPermissions
                : tab.requiredPermissions,
            requiresAny: tab.requiredPermissions.isEmpty
                ? module.requiresAnyPermission
                : tab.requiresAnyPermission,
          ),
        )
        .toList();
    if (visibleTabs.isEmpty) {
      return const WorkspaceEmptyState(
        title: 'No delivery note access',
        message: 'Your account cannot access a delivery note workspace.',
      );
    }
    final String? requestedTab =
        widget.router.current.module == AppModule.deliveryNotes.name
            ? widget.router.current.tab
            : null;
    final String tabId = visibleTabs.any((tab) => tab.id == requestedTab)
        ? requestedTab!
        : visibleTabs.first.id;
    final bool hasActiveFirm =
        widget.api.activeFirmId?.call()?.isNotEmpty == true;

    return DeliveryNoteManagementPage(
      api: widget.api,
      preferences: widget.preferences,
      permissions: widget.permissions,
      hasActiveFirm: hasActiveFirm,
      tabId: tabId,
      onNavigateToTab: (nextTab) => widget.router.selectTab(nextTab),
      onOpenGlobalSearch: widget.onOpenGlobalSearch,
    );
  }
}

class _InventoryWorkspace extends StatefulWidget {
  const _InventoryWorkspace({
    super.key,
    required this.api,
    required this.preferences,
    required this.permissions,
    required this.router,
  });

  final ApiClient api;
  final DesktopPreferencesService preferences;
  final PermissionService permissions;
  final WorkspaceRouter router;

  @override
  State<_InventoryWorkspace> createState() => _InventoryWorkspaceState();
}

class _InventoryWorkspaceState extends State<_InventoryWorkspace> {
  @override
  Widget build(BuildContext context) {
    final ModuleDefinition module = ModuleCatalog.byId(AppModule.inventory);
    final List<ModuleTabDefinition> visibleTabs = module.tabs
        // A tab declared `available: false` has no workspace behind it, so
        // showing it routes the user to an unrelated screen.
        .where((tab) => tab.available)
        .where(
          (tab) => widget.permissions.canUseTab(
            tab.requiredPermissions.isEmpty
                ? module.requiredPermissions
                : tab.requiredPermissions,
            requiresAny: tab.requiredPermissions.isEmpty
                ? module.requiresAnyPermission
                : tab.requiresAnyPermission,
          ),
        )
        .toList();
    if (visibleTabs.isEmpty) {
      return const WorkspaceEmptyState(
        title: 'No inventory access',
        message: 'Your account cannot access an inventory workspace.',
      );
    }
    final String? requestedTab =
        widget.router.current.module == AppModule.inventory.name
            ? widget.router.current.tab
            : null;
    final String tabId = visibleTabs.any((tab) => tab.id == requestedTab)
        ? requestedTab!
        : visibleTabs.first.id;
    final bool hasActiveFirm =
        widget.api.activeFirmId?.call()?.isNotEmpty == true;
    void navigateTo(InventorySection section) {
      final String tabId = switch (section) {
        InventorySection.inventory => 'inventory',
        InventorySection.openingStock => 'opening-stock',
        InventorySection.stockLedger => 'stock-ledger',
        InventorySection.transactions => 'transactions',
        InventorySection.stockSummary => 'stock-summary',
        InventorySection.stockSearch => 'stock-search',
        InventorySection.inventoryImport => 'inventory-import',
        InventorySection.inventoryExport => 'inventory-export',
        InventorySection.settings => 'inventory-settings',
      };
      widget.router.selectTab(tabId);
    }

    final Widget content = switch (tabId) {
      'inventory' => InventoryManagementPage(
          api: widget.api,
          preferences: widget.preferences,
          permissions: widget.permissions,
          hasActiveFirm: hasActiveFirm,
          section: InventorySection.inventory,
          onNavigateToSection: navigateTo,
        ),
      'opening-stock' => InventoryManagementPage(
          api: widget.api,
          preferences: widget.preferences,
          permissions: widget.permissions,
          hasActiveFirm: hasActiveFirm,
          section: InventorySection.openingStock,
          onNavigateToSection: navigateTo,
        ),
      'stock-ledger' => InventoryManagementPage(
          api: widget.api,
          preferences: widget.preferences,
          permissions: widget.permissions,
          hasActiveFirm: hasActiveFirm,
          section: InventorySection.stockLedger,
          onNavigateToSection: navigateTo,
        ),
      'transactions' => InventoryManagementPage(
          api: widget.api,
          preferences: widget.preferences,
          permissions: widget.permissions,
          hasActiveFirm: hasActiveFirm,
          section: InventorySection.transactions,
          onNavigateToSection: navigateTo,
        ),
      'stock-summary' => InventoryManagementPage(
          api: widget.api,
          preferences: widget.preferences,
          permissions: widget.permissions,
          hasActiveFirm: hasActiveFirm,
          section: InventorySection.stockSummary,
          onNavigateToSection: navigateTo,
        ),
      'stock-search' => InventoryManagementPage(
          api: widget.api,
          preferences: widget.preferences,
          permissions: widget.permissions,
          hasActiveFirm: hasActiveFirm,
          section: InventorySection.stockSearch,
          onNavigateToSection: navigateTo,
        ),
      'inventory-import' => InventoryManagementPage(
          api: widget.api,
          preferences: widget.preferences,
          permissions: widget.permissions,
          hasActiveFirm: hasActiveFirm,
          section: InventorySection.inventoryImport,
          onNavigateToSection: navigateTo,
        ),
      'inventory-export' => InventoryManagementPage(
          api: widget.api,
          preferences: widget.preferences,
          permissions: widget.permissions,
          hasActiveFirm: hasActiveFirm,
          section: InventorySection.inventoryExport,
          onNavigateToSection: navigateTo,
        ),
      'inventory-settings' => InventoryManagementPage(
          api: widget.api,
          preferences: widget.preferences,
          permissions: widget.permissions,
          hasActiveFirm: hasActiveFirm,
          section: InventorySection.settings,
          onNavigateToSection: navigateTo,
        ),
      'batches' => BatchManagementPage(
          api: widget.api,
          preferences: widget.preferences,
          permissions: widget.permissions,
          hasActiveFirm: hasActiveFirm,
          section: BatchSerialSection.batches,
        ),
      'lots' => BatchManagementPage(
          api: widget.api,
          preferences: widget.preferences,
          permissions: widget.permissions,
          hasActiveFirm: hasActiveFirm,
          section: BatchSerialSection.lots,
        ),
      'serials' => BatchManagementPage(
          api: widget.api,
          preferences: widget.preferences,
          permissions: widget.permissions,
          hasActiveFirm: hasActiveFirm,
          section: BatchSerialSection.serials,
        ),
      'expiry-monitor' => BatchManagementPage(
          api: widget.api,
          preferences: widget.preferences,
          permissions: widget.permissions,
          hasActiveFirm: hasActiveFirm,
          section: BatchSerialSection.expiryMonitor,
        ),
      _ => const WorkspaceEmptyState(
          title: 'Inventory workspace unavailable',
          message: 'The selected inventory workspace is not available.',
        ),
    };

    return ModuleWorkspaceFrame(
      title: switch (tabId) {
        'inventory' => 'Inventory Management',
        'opening-stock' => 'Opening Stock',
        'stock-ledger' => 'Stock Ledger',
        'transactions' => 'Inventory Transactions',
        'stock-summary' => 'Stock Summary',
        'stock-search' => 'Stock Search',
        'inventory-import' => 'Inventory Import',
        'inventory-export' => 'Inventory Export',
        'inventory-settings' => 'Inventory Settings',
        'batches' => 'Batch Management',
        'lots' => 'Lot Management',
        'serials' => 'Serial Number Management',
        'expiry-monitor' => 'Expiry Monitor',
        _ => module.label,
      },
      description: switch (tabId) {
        'inventory' =>
          'Review inventory balances and maintain stock thresholds by product and warehouse.',
        'opening-stock' =>
          'Create, edit, and post opening stock batches that generate immutable inventory transactions.',
        'stock-ledger' =>
          'Review the permanent stock ledger for audit and reconciliation.',
        'transactions' =>
          'Review all inventory transactions and create controlled adjustments.',
        'stock-summary' =>
          'Monitor current, reserved, available, blocked, damaged, quarantine, and in-transit stock.',
        'stock-search' =>
          'Search stock balances across products, warehouses, and branches.',
        'inventory-import' =>
          'Create opening stock batches from structured import payloads.',
        'inventory-export' =>
          'Copy inventory and ledger exports for reporting and analysis.',
        'inventory-settings' =>
          'Review inventory foundation settings and future extension points.',
        'batches' =>
          'Manage product batches with expiry tracking, quantities, and status.',
        'lots' =>
          'Manage production lots with traceability and lifecycle tracking.',
        'serials' =>
          'Manage individual serialized units with warranty and movement history.',
        'expiry-monitor' =>
          'Monitor batches nearing expiry, expired stock, quarantine, and recalls.',
        _ => module.description,
      },
      breadcrumbs: [
        'Workspace',
        'Inventory',
        visibleTabs.firstWhere((tab) => tab.id == tabId).label,
      ],
      child: content,
    );
  }
}

class _ComingSoonModule extends StatelessWidget {
  const _ComingSoonModule({
    required this.module,
    required this.permissions,
  });
  final ModuleDefinition module;
  final PermissionService permissions;

  @override
  Widget build(BuildContext context) => ModuleWorkspaceFrame(
        title: module.label,
        description: module.description,
        breadcrumbs: ['Workspace', module.label],
        child: WorkspaceEmptyState(
          title: '${module.label} is coming soon',
          message: 'No ${module.label.toLowerCase()} API is available yet.',
          icon: module.icon,
        ),
      );
}

List<String> _ids(dynamic value) => value
    .toString()
    .split(',')
    .map((id) => id.trim())
    .where((id) => id.isNotEmpty)
    .toList();

/// Normalizes an optional text field's blank value to `null` so partial
/// updates clear the field server-side instead of persisting empty strings.
dynamic _orNull(dynamic value) =>
    value == null || value.toString().trim().isEmpty ? null : value;

bool _canUseResourceAction(
  PermissionService permissions,
  ToolbarAction action, {
  required List<String> view,
  required List<String> create,
  required List<String> update,
  required List<String> delete,
}) =>
    switch (action) {
      ToolbarAction.newItem => permissions.canUseAction(create),
      ToolbarAction.edit => permissions.canUseAction(update),
      ToolbarAction.delete => permissions.canUseAction(delete),
      ToolbarAction.view ||
      ToolbarAction.refresh =>
        permissions.canUseAction(view),
      ToolbarAction.import ||
      ToolbarAction.export ||
      ToolbarAction.print ||
      ToolbarAction.settings =>
        false,
    };

ResourceDefinition<Firm> firmDefinition(
  ApiClient api,
  PermissionService permissions, {
  bool showFrame = true,
}) =>
    ResourceDefinition(
      title: 'Firms',
      resource: 'firms',
      showFrame: showFrame,
      description: 'Maintain organization firm records.',
      headers: const [
        'Code',
        'Name',
        'Contact',
        'Currency',
        'Country',
        'Status'
      ],
      sortFields: const ['code', 'name', null, null, null, null],
      cells: (firm) => [
        firm.code,
        firm.name,
        firm.contactEmail,
        firm.currencyCode,
        firm.country,
        firm.isActive ? 'Active' : 'Inactive',
      ],
      id: (firm) => firm.id,
      load: api.firms,
      canUseAction: (action, _) => _canUseResourceAction(
        permissions,
        action,
        view: const ['FIRM_VIEW'],
        create: const ['FIRM_CREATE'],
        update: const ['FIRM_UPDATE'],
        delete: const ['FIRM_DELETE'],
      ),
      fields: const [
        FieldSpec(key: 'code', label: 'Firm code', required: true),
        FieldSpec(key: 'name', label: 'Display name', required: true),
        FieldSpec(key: 'gst_number', label: 'GST number'),
        FieldSpec(key: 'pan_number', label: 'PAN number'),
        FieldSpec(
          key: 'address_line1',
          label: 'Address line 1',
          section: 'Address',
        ),
        FieldSpec(
          key: 'address_line2',
          label: 'Address line 2',
          section: 'Address',
        ),
        FieldSpec(key: 'city', label: 'City', section: 'Address'),
        FieldSpec(
          key: 'state',
          label: 'State / province',
          section: 'Address',
        ),
        FieldSpec(
          key: 'postal_code',
          label: 'Postal code',
          section: 'Address',
        ),
        FieldSpec(
          key: 'country',
          label: 'Country',
          required: true,
          section: 'Address',
        ),
        FieldSpec(
          key: 'contact_name',
          label: 'Contact name',
          section: 'Contacts',
        ),
        FieldSpec(
          key: 'contact_email',
          label: 'Contact email',
          section: 'Contacts',
        ),
        FieldSpec(
          key: 'contact_phone',
          label: 'Contact phone',
          section: 'Contacts',
        ),
        FieldSpec(key: 'currency_code', label: 'Currency code', required: true),
        FieldSpec(
          key: 'financial_year_start',
          label: 'Financial year start',
          helperText: 'ISO date, for example 2026-04-01.',
          required: true,
        ),
        FieldSpec(
          key: 'deployment_mode',
          label: 'Deployment mode',
          helperText: 'SHARED, SCHEMA, or DATABASE.',
          section: 'Storage Mapping',
        ),
        FieldSpec(
          key: 'database_type',
          label: 'Database type',
          helperText: 'Use platform engine (for example postgresql).',
          section: 'Storage Mapping',
        ),
        FieldSpec(
          key: 'database_name',
          label: 'Database name',
          helperText: 'Required for SCHEMA and DATABASE modes.',
          section: 'Storage Mapping',
        ),
        FieldSpec(
          key: 'schema_name',
          label: 'Schema name',
          helperText: 'Required for SCHEMA and DATABASE modes.',
          section: 'Storage Mapping',
        ),
        FieldSpec(
          key: 'business_profile_id',
          label: 'Business profile',
          optionsResource: 'business-framework/profiles',
          singleSelection: true,
          requiredOnCreate: true,
          helperText: 'Decides which features and modules this firm operates. '
              'A firm without one falls back to the platform default.',
        ),
        FieldSpec(key: 'is_active', label: 'Active', boolean: true),
        FieldSpec(key: 'notes', label: 'Notes', multiline: true),
      ],
      loadAssignments: api.firmBusinessProfileAssignmentValues,
      saveAssignments: (id, values) async {
        final String profileId =
            stringValue(values['business_profile_id']).split(',').first.trim();
        if (profileId.isEmpty) return;
        await api.assignBusinessProfileToFirm(id, profileId);
      },
      initialValues: (firm) => firm == null
          ? {
              'is_active': true,
              'deployment_mode': 'SHARED',
              'database_type': 'postgresql',
            }
          : {
              'code': firm.code,
              'name': firm.name,
              'gst_number': firm.gstNumber,
              'pan_number': firm.panNumber,
              'address_line1': firm.addressLine1,
              'address_line2': firm.addressLine2,
              'city': firm.city,
              'state': firm.state,
              'postal_code': firm.postalCode,
              'country': firm.country,
              'contact_name': firm.contactName,
              'contact_email': firm.contactEmail,
              'contact_phone': firm.contactPhone,
              'currency_code': firm.currencyCode,
              'financial_year_start': firm.financialYearStart,
              'deployment_mode': firm.deploymentMode,
              'database_type': firm.databaseType,
              'database_name': firm.databaseName,
              'schema_name': firm.schemaName,
              'is_active': firm.isActive,
              'notes': firm.notes,
            },
      payload: (values, _) {
        final String mode =
            stringValue(values['deployment_mode']).toUpperCase();
        final String normalizedMode = mode.isEmpty ? 'SHARED' : mode;
        final bool shared = normalizedMode == 'SHARED';
        final Map<String, dynamic> body = {
          ...values,
          'deployment_mode': normalizedMode,
          'database_type': stringValue(values['database_type']).toLowerCase(),
          'database_name': shared ? null : _orNull(values['database_name']),
          'schema_name': shared ? null : _orNull(values['schema_name']),
        };
        // The profile lives in the firm-owned schema and is assigned through the
        // business-framework API. /api/v1/firms forbids unknown fields, so it
        // must not travel in the firm body.
        body.remove('business_profile_id');
        return body;
      },
    );

ResourceDefinition<PlatformUser> _userDefinition(
  ApiClient api,
  PermissionService permissions, {
  bool showFrame = true,
}) =>
    ResourceDefinition(
      title: 'Users',
      resource: 'users',
      showFrame: showFrame,
      description: 'Manage platform user accounts and assignments.',
      headers: const ['Email', 'Name', 'Assignments', 'Status'],
      sortFields: const ['email', 'full_name', null, null],
      cells: (user) => [
        user.email,
        user.fullName,
        'Manage in editor',
        user.isActive ? 'Active' : 'Inactive',
      ],
      id: (user) => user.id,
      load: api.users,
      canUseAction: (action, _) => _canUseResourceAction(
        permissions,
        action,
        view: const ['USER_VIEW'],
        create: const [
          'USER_CREATE',
          'ROLE_ASSIGN',
          'ROLE_VIEW',
          'USER_UPDATE',
          'FIRM_VIEW',
        ],
        update: const [
          'USER_UPDATE',
          'ROLE_ASSIGN',
          'ROLE_VIEW',
          'FIRM_VIEW',
        ],
        delete: const ['USER_DELETE'],
      ),
      fields: const [
        FieldSpec(
          key: 'email',
          label: 'Username (Email)',
          required: true,
          readOnlyWhenEditing: true,
          helperText: 'Used to sign in. This system has no separate username.',
          section: 'General Information',
          sectionIcon: Icons.badge_outlined,
        ),
        FieldSpec(
          key: 'full_name',
          label: 'Full name',
          required: true,
          section: 'General Information',
        ),
        FieldSpec(
          key: 'personal_mobile',
          label: 'Mobile',
          section: 'General Information',
        ),
        FieldSpec(
          key: 'alternate_mobile',
          label: 'Alternate mobile',
          section: 'General Information',
        ),
        FieldSpec(
          key: 'profile_photo_url',
          label: 'Profile photo URL',
          helperText: 'Link to a hosted photo.',
          section: 'General Information',
        ),
        FieldSpec(
          key: 'is_active',
          label: 'Status (Active)',
          boolean: true,
          section: 'General Information',
        ),
        FieldSpec(
          key: 'firm_ids',
          label: 'Firms',
          helperText: 'Select one or more firms.',
          optionsResource: 'firms',
          section: 'Organization',
          sectionIcon: Icons.apartment_outlined,
        ),
        FieldSpec(
          key: 'primary_firm_id',
          label: 'Primary firm',
          helperText: 'Optional; must also be selected above.',
          optionsResource: 'firms',
          singleSelection: true,
          section: 'Organization',
        ),
        FieldSpec(
          key: 'password',
          label: 'Initial password',
          requiredOnCreate: true,
          createOnly: true,
          section: 'Security',
          sectionIcon: Icons.lock_outline,
        ),
        FieldSpec(
          key: 'force_password_change',
          label: 'Require password change',
          boolean: true,
          createOnly: true,
          section: 'Security',
        ),
        FieldSpec(
          key: 'role_ids',
          label: 'Roles',
          helperText: 'Select one or more roles.',
          optionsResource: 'roles',
          section: 'Security',
        ),
        FieldSpec(
          key: 'expires_at',
          label: 'Expires at',
          helperText: 'Optional ISO timestamp.',
          section: 'Security',
        ),
        FieldSpec(
          key: 'unlock',
          label: 'Clear login lock (Account Lock)',
          boolean: true,
          editOnly: true,
          section: 'Security',
        ),
        FieldSpec(
          key: 'personal_email',
          label: 'Personal email',
          section: 'Contact Information',
          sectionIcon: Icons.contact_mail_outlined,
        ),
        FieldSpec(
          key: 'office_email',
          label: 'Office email',
          section: 'Contact Information',
        ),
        FieldSpec(
          key: 'emergency_contact_name',
          label: 'Emergency contact name',
          section: 'Contact Information',
        ),
        FieldSpec(
          key: 'emergency_mobile',
          label: 'Emergency contact mobile',
          section: 'Contact Information',
        ),
        FieldSpec(
          key: 'emergency_relationship',
          label: 'Relationship',
          section: 'Contact Information',
        ),
        FieldSpec(
          key: 'profile_addresses',
          label: 'Addresses',
          kind: FieldKind.addressList,
          section: 'Address',
          sectionIcon: Icons.location_on_outlined,
        ),
        FieldSpec(
          key: 'employee_code',
          label: 'Employee code',
          section: 'Employment',
          sectionIcon: Icons.work_outline,
        ),
        FieldSpec(
          key: 'joining_date',
          label: 'Joining date',
          kind: FieldKind.date,
          section: 'Employment',
        ),
        FieldSpec(
          key: 'leaving_date',
          label: 'Leaving date',
          kind: FieldKind.date,
          section: 'Employment',
        ),
        FieldSpec(
          key: 'department',
          label: 'Department',
          section: 'Employment',
        ),
        FieldSpec(
          key: 'designation',
          label: 'Designation',
          section: 'Employment',
        ),
        FieldSpec(
          key: 'reporting_manager',
          label: 'Reporting manager',
          section: 'Employment',
        ),
        FieldSpec(
          key: 'employment_type',
          label: 'Employment type',
          section: 'Employment',
        ),
        FieldSpec(
          key: 'cost_center',
          label: 'Cost center',
          section: 'Employment',
        ),
        FieldSpec(
          key: 'profile_documents',
          label: 'Documents',
          kind: FieldKind.documentList,
          section: 'Documents',
          sectionIcon: Icons.folder_outlined,
        ),
        FieldSpec(
          key: 'created_at',
          label: 'Created on',
          alwaysReadOnly: true,
          section: 'Audit Information',
          sectionIcon: Icons.history_outlined,
        ),
        FieldSpec(
          key: 'updated_at',
          label: 'Last modified on',
          alwaysReadOnly: true,
          section: 'Audit Information',
        ),
        FieldSpec(
          key: 'last_login_at',
          label: 'Last login',
          alwaysReadOnly: true,
          section: 'Audit Information',
        ),
        FieldSpec(
          key: 'failed_login_attempts',
          label: 'Failed login attempts',
          alwaysReadOnly: true,
          section: 'Audit Information',
        ),
      ],
      initialValues: (user) => user == null
          ? {
              'is_active': true,
              'force_password_change': true,
              'profile_addresses': const [],
              'profile_documents': const [],
            }
          : {
              'email': user.email,
              'full_name': user.fullName,
              'force_password_change': user.forcePasswordChange,
              'is_active': user.isActive,
              'expires_at': user.expiresAt,
              'unlock': false,
              'personal_mobile': user.personalMobile,
              'alternate_mobile': user.alternateMobile,
              'profile_photo_url': user.profilePhotoUrl,
              'personal_email': user.personalEmail,
              'office_email': user.officeEmail,
              'emergency_contact_name': user.emergencyContactName,
              'emergency_mobile': user.emergencyMobile,
              'emergency_relationship': user.emergencyRelationship,
              'employee_code': user.employeeCode,
              'joining_date': user.joiningDate,
              'leaving_date': user.leavingDate,
              'department': user.department,
              'designation': user.designation,
              'reporting_manager': user.reportingManager,
              'employment_type': user.employmentType,
              'cost_center': user.costCenter,
              'profile_addresses': user.profileAddresses,
              'profile_documents': user.profileDocuments,
              'created_at': user.createdAt,
              'updated_at': user.updatedAt,
              'last_login_at': user.lastLoginAt,
              'failed_login_attempts': user.failedLoginAttempts.toString(),
            },
      payload: (values, isCreating) => isCreating
          ? {
              'email': values['email'],
              'full_name': values['full_name'],
              'password': values['password'],
              'is_active': values['is_active'],
              'force_password_change': values['force_password_change'],
              if (values['expires_at'].toString().isNotEmpty)
                'expires_at': values['expires_at'],
            }
          : {
              'full_name': values['full_name'],
              'is_active': values['is_active'],
              'expires_at': _orNull(values['expires_at']),
              'unlock': values['unlock'],
              'personal_mobile': _orNull(values['personal_mobile']),
              'alternate_mobile': _orNull(values['alternate_mobile']),
              'profile_photo_url': _orNull(values['profile_photo_url']),
              'personal_email': _orNull(values['personal_email']),
              'office_email': _orNull(values['office_email']),
              'emergency_contact_name':
                  _orNull(values['emergency_contact_name']),
              'emergency_mobile': _orNull(values['emergency_mobile']),
              'emergency_relationship':
                  _orNull(values['emergency_relationship']),
              'employee_code': _orNull(values['employee_code']),
              'joining_date': _orNull(values['joining_date']),
              'leaving_date': _orNull(values['leaving_date']),
              'department': _orNull(values['department']),
              'designation': _orNull(values['designation']),
              'reporting_manager': _orNull(values['reporting_manager']),
              'employment_type': _orNull(values['employment_type']),
              'cost_center': _orNull(values['cost_center']),
              'profile_addresses': values['profile_addresses'] ?? const [],
              'profile_documents': values['profile_documents'] ?? const [],
            },
      partialUpdate: true,
      loadAssignments: api.userAssignmentValues,
      saveAssignments: (id, values) async {
        await api.setUserRoles(id, _ids(values['role_ids']));
        await api.setUserFirms(
          id,
          _ids(values['firm_ids']),
          values['primary_firm_id'].toString(),
        );
      },
    );

ResourceDefinition<PlatformUser> _userFirmAssignmentDefinition(
  ApiClient api,
  PermissionService permissions,
) =>
    ResourceDefinition(
      title: 'User-Firm Assignments',
      resource: 'users',
      showFrame: false,
      description: 'Assign users to one or more firms using the current API.',
      headers: const ['Email', 'Name', 'Status'],
      sortFields: const ['email', 'full_name', null],
      cells: (user) => [
        user.email,
        user.fullName,
        user.isActive ? 'Active' : 'Inactive',
      ],
      id: (user) => user.id,
      load: api.users,
      canUseAction: (action, _) => _canUseResourceAction(
        permissions,
        action,
        view: const ['USER_VIEW', 'USER_UPDATE', 'FIRM_VIEW'],
        create: const [],
        update: const ['USER_VIEW', 'USER_UPDATE', 'FIRM_VIEW'],
        delete: const [],
      ),
      fields: const [
        FieldSpec(
          key: 'firm_ids',
          label: 'Firms',
          helperText: 'Select one or more firms for this user.',
          optionsResource: 'firms',
        ),
        FieldSpec(
          key: 'primary_firm_id',
          label: 'Primary firm',
          helperText: 'Optional; it must also be selected above.',
          optionsResource: 'firms',
          singleSelection: true,
        ),
      ],
      initialValues: (_) => {},
      payload: (_, __) => {},
      canCreate: false,
      canDelete: false,
      updateEntity: false,
      loadAssignments: api.userFirmAssignmentValues,
      saveAssignments: (id, values) => api.setUserFirms(
        id,
        _ids(values['firm_ids']),
        values['primary_firm_id'].toString(),
      ),
    );

ResourceDefinition<Role> _roleDefinition(
  ApiClient api,
  PermissionService permissions, {
  bool showFrame = true,
}) =>
    ResourceDefinition(
      title: 'Roles',
      resource: 'roles',
      showFrame: showFrame,
      description: 'Manage access role definitions and permissions.',
      headers: const ['Code', 'Name', 'Assignments', 'Status'],
      sortFields: const ['code', 'name', null, null],
      cells: (role) => [
        role.code,
        role.name,
        'Manage in editor',
        role.isActive ? 'Active' : 'Inactive',
      ],
      id: (role) => role.id,
      load: api.roles,
      canEdit: (role) => !role.isSystem,
      canUseAction: (action, _) => _canUseResourceAction(
        permissions,
        action,
        view: const ['ROLE_VIEW'],
        create: const ['ROLE_CREATE', 'ROLE_ASSIGN', 'PERMISSION_VIEW'],
        update: const [
          'ROLE_UPDATE',
          'ROLE_ASSIGN',
          'PERMISSION_ASSIGN',
          'PERMISSION_VIEW',
        ],
        delete: const ['ROLE_DELETE'],
      ),
      fields: const [
        FieldSpec(
          key: 'code',
          label: 'Role code',
          required: true,
          readOnlyWhenEditing: true,
        ),
        FieldSpec(key: 'name', label: 'Name', required: true),
        FieldSpec(key: 'description', label: 'Description', multiline: true),
        FieldSpec(
          key: 'permission_ids',
          label: 'Permissions',
          helperText: 'Select one or more permissions.',
          optionsResource: 'permissions',
          section: 'Permissions',
        ),
        FieldSpec(key: 'is_active', label: 'Active', boolean: true),
      ],
      initialValues: (role) => role == null
          ? {'is_active': true}
          : {
              'code': role.code,
              'name': role.name,
              'description': role.description,
              'is_active': role.isActive,
            },
      payload: (values, isCreating) => {
        if (isCreating) 'code': values['code'],
        'name': values['name'],
        'description': values['description'],
        'is_active': values['is_active'],
      },
      partialUpdate: true,
      loadAssignments: api.roleAssignmentValues,
      saveAssignments: (id, values) =>
          api.setRolePermissions(id, _ids(values['permission_ids'])),
    );

ResourceDefinition<Permission> _permissionDefinition(
  ApiClient api,
  PermissionService permissions, {
  bool showFrame = true,
}) =>
    ResourceDefinition(
      title: 'Permissions',
      resource: 'permissions',
      showFrame: showFrame,
      description: 'Manage platform permission definitions.',
      headers: const ['Code', 'Name', 'Status'],
      sortFields: const ['code', 'name', null],
      cells: (permission) => [
        permission.code,
        permission.name,
        permission.isActive ? 'Active' : 'Inactive',
      ],
      id: (permission) => permission.id,
      load: api.permissions,
      canUseAction: (action, _) => _canUseResourceAction(
        permissions,
        action,
        view: const ['PERMISSION_VIEW'],
        create: const ['PERMISSION_CREATE'],
        update: const ['PERMISSION_UPDATE'],
        delete: const ['PERMISSION_DELETE'],
      ),
      fields: const [
        FieldSpec(
          key: 'code',
          label: 'Permission code',
          required: true,
          readOnlyWhenEditing: true,
        ),
        FieldSpec(key: 'name', label: 'Name', required: true),
        FieldSpec(key: 'description', label: 'Description', multiline: true),
        FieldSpec(key: 'is_active', label: 'Active', boolean: true),
      ],
      initialValues: (permission) => permission == null
          ? {'is_active': true}
          : {
              'code': permission.code,
              'name': permission.name,
              'description': permission.description,
              'is_active': permission.isActive,
            },
      payload: (values, isCreating) => {
        if (isCreating) 'code': values['code'],
        'name': values['name'],
        'description': values['description'],
        'is_active': values['is_active'],
      },
      partialUpdate: true,
    );

ResourceDefinition<BusinessProfileRecord> _businessProfileDefinition(
  ApiClient api,
  PermissionService permissions, {
  bool showFrame = true,
}) =>
    ResourceDefinition(
      title: 'Business Profiles',
      resource: 'business-framework/profiles',
      showFrame: showFrame,
      description:
          'Configure industry profiles that control modules, feature flags, and validations.',
      headers: const ['Code', 'Name', 'Industry', 'Status', 'Default'],
      sortFields: const ['code', 'name', 'industry_type', 'status', null],
      cells: (profile) => [
        profile.code,
        profile.name,
        profile.industryType,
        profile.status,
        profile.isDefault ? 'Yes' : 'No',
      ],
      id: (profile) => profile.id,
      load: api.businessProfiles,
      canUseAction: (action, _) => _canUseResourceAction(
        permissions,
        action,
        view: const ['PLATFORM_VIEW'],
        create: const ['PLATFORM_SETTINGS'],
        update: const ['PLATFORM_SETTINGS'],
        delete: const ['PLATFORM_SETTINGS'],
      ),
      fields: const [
        FieldSpec(
          key: 'code',
          label: 'Profile code',
          required: true,
          readOnlyWhenEditing: true,
        ),
        FieldSpec(key: 'name', label: 'Name', required: true),
        FieldSpec(
          key: 'industry_type',
          label: 'Industry type',
          required: true,
        ),
        FieldSpec(key: 'status', label: 'Status', required: true),
        FieldSpec(
          key: 'description',
          label: 'Description',
          multiline: true,
        ),
        FieldSpec(
          key: 'is_default',
          label: 'Default profile',
          boolean: true,
          section: 'Configuration',
        ),
        FieldSpec(
          key: 'feature_ids',
          label: 'Enabled features',
          optionsResource: 'business-framework/features',
          section: 'Configuration',
        ),
        FieldSpec(
          key: 'module_ids',
          label: 'Enabled modules',
          optionsResource: 'business-framework/modules',
          section: 'Configuration',
        ),
      ],
      initialValues: (profile) => profile == null
          ? {'status': 'ACTIVE', 'is_default': false}
          : {
              'code': profile.code,
              'name': profile.name,
              'industry_type': profile.industryType,
              'status': profile.status,
              'description': profile.description,
              'is_default': profile.isDefault,
            },
      payload: (values, _) => {
        'code': values['code'],
        'name': values['name'],
        'industry_type': values['industry_type'],
        'status': values['status'],
        'description': values['description'],
        'is_default': values['is_default'],
      },
      loadAssignments: api.businessProfileConfigurationValues,
      saveAssignments: (id, values) async {
        await api.setBusinessProfileFeatures(id, _ids(values['feature_ids']));
        await api.setBusinessProfileModules(id, _ids(values['module_ids']));
      },
    );

ResourceDefinition<BusinessFeatureRecord> _businessFeatureDefinition(
  ApiClient api,
  PermissionService permissions, {
  bool showFrame = true,
}) =>
    ResourceDefinition(
      title: 'Feature Management',
      resource: 'business-framework/features',
      showFrame: showFrame,
      description: 'Maintain configurable feature flags for industry profiles.',
      headers: const ['Code', 'Name', 'Category', 'Default', 'Status'],
      sortFields: const ['code', 'name', 'category', null, null],
      cells: (feature) => [
        feature.code,
        feature.name,
        feature.category,
        feature.defaultEnabled ? 'Enabled' : 'Disabled',
        feature.isActive ? 'Active' : 'Inactive',
      ],
      id: (feature) => feature.id,
      load: api.businessFeatures,
      canUseAction: (action, _) => _canUseResourceAction(
        permissions,
        action,
        view: const ['PLATFORM_VIEW'],
        create: const ['PLATFORM_SETTINGS'],
        update: const ['PLATFORM_SETTINGS'],
        delete: const ['PLATFORM_SETTINGS'],
      ),
      fields: const [
        FieldSpec(
          key: 'code',
          label: 'Feature code',
          required: true,
          readOnlyWhenEditing: true,
        ),
        FieldSpec(key: 'name', label: 'Name', required: true),
        FieldSpec(key: 'category', label: 'Category'),
        FieldSpec(key: 'description', label: 'Description', multiline: true),
        FieldSpec(
          key: 'default_enabled',
          label: 'Default enabled',
          boolean: true,
        ),
        FieldSpec(key: 'is_active', label: 'Active', boolean: true),
      ],
      initialValues: (feature) => feature == null
          ? {'default_enabled': false, 'is_active': true}
          : {
              'code': feature.code,
              'name': feature.name,
              'category': feature.category,
              'description': '',
              'default_enabled': feature.defaultEnabled,
              'is_active': feature.isActive,
            },
      payload: (values, _) => {
        'code': values['code'],
        'name': values['name'],
        'category': values['category'],
        'description': values['description'],
        'default_enabled': values['default_enabled'],
        'is_active': values['is_active'],
      },
    );

ResourceDefinition<BusinessModuleRecord> _businessModuleDefinition(
  ApiClient api,
  PermissionService permissions, {
  bool showFrame = true,
}) =>
    ResourceDefinition(
      title: 'Module Configuration',
      resource: 'business-framework/modules',
      showFrame: showFrame,
      description:
          'Maintain module catalog entries for profile-based visibility.',
      headers: const ['Code', 'Name', 'Route', 'Default', 'Status'],
      sortFields: const ['code', 'name', null, null, null],
      cells: (module) => [
        module.code,
        module.name,
        module.uiRoute,
        module.defaultEnabled ? 'Enabled' : 'Disabled',
        module.isActive ? 'Active' : 'Inactive',
      ],
      id: (module) => module.id,
      load: api.businessModules,
      canUseAction: (action, _) => _canUseResourceAction(
        permissions,
        action,
        view: const ['PLATFORM_VIEW'],
        create: const ['PLATFORM_SETTINGS'],
        update: const ['PLATFORM_SETTINGS'],
        delete: const ['PLATFORM_SETTINGS'],
      ),
      fields: const [
        FieldSpec(
          key: 'code',
          label: 'Module code',
          required: true,
          readOnlyWhenEditing: true,
        ),
        FieldSpec(key: 'name', label: 'Name', required: true),
        FieldSpec(key: 'ui_route', label: 'UI route'),
        FieldSpec(key: 'description', label: 'Description', multiline: true),
        FieldSpec(
          key: 'default_enabled',
          label: 'Default enabled',
          boolean: true,
        ),
        FieldSpec(key: 'is_active', label: 'Active', boolean: true),
      ],
      initialValues: (module) => module == null
          ? {'default_enabled': true, 'is_active': true}
          : {
              'code': module.code,
              'name': module.name,
              'ui_route': module.uiRoute,
              'description': '',
              'default_enabled': module.defaultEnabled,
              'is_active': module.isActive,
            },
      payload: (values, _) => {
        'code': values['code'],
        'name': values['name'],
        'ui_route': values['ui_route'],
        'description': values['description'],
        'default_enabled': values['default_enabled'],
        'is_active': values['is_active'],
      },
    );

ResourceDefinition<AttributeDefinitionRecord> _attributeDefinitionDefinition(
  ApiClient api,
  PermissionService permissions, {
  bool showFrame = true,
}) =>
    ResourceDefinition(
      title: 'Attribute Definitions',
      resource: 'business-framework/attribute-definitions',
      showFrame: showFrame,
      description:
          'Define reusable attribute metadata for future product and inventory modules.',
      headers: const ['Code', 'Name', 'Data type', 'Category', 'Mandatory'],
      sortFields: const ['code', 'name', null, null, null],
      cells: (attribute) => [
        attribute.code,
        attribute.name,
        attribute.dataType,
        attribute.applicableCategory,
        attribute.mandatory ? 'Yes' : 'No',
      ],
      id: (attribute) => attribute.id,
      load: api.attributeDefinitions,
      canUseAction: (action, _) => _canUseResourceAction(
        permissions,
        action,
        view: const ['PLATFORM_VIEW'],
        create: const ['PLATFORM_SETTINGS'],
        update: const ['PLATFORM_SETTINGS'],
        delete: const ['PLATFORM_SETTINGS'],
      ),
      fields: const [
        FieldSpec(
          key: 'code',
          label: 'Attribute code',
          required: true,
          readOnlyWhenEditing: true,
        ),
        FieldSpec(key: 'name', label: 'Name', required: true),
        FieldSpec(key: 'data_type', label: 'Data type', required: true),
        FieldSpec(key: 'applicable_category', label: 'Applicable category'),
        FieldSpec(
          key: 'mandatory',
          label: 'Mandatory',
          boolean: true,
        ),
        FieldSpec(key: 'description', label: 'Description', multiline: true),
        FieldSpec(key: 'default_value', label: 'Default value'),
        FieldSpec(key: 'is_active', label: 'Active', boolean: true),
      ],
      initialValues: (attribute) => attribute == null
          ? {'mandatory': false, 'is_active': true}
          : {
              'code': attribute.code,
              'name': attribute.name,
              'data_type': attribute.dataType,
              'applicable_category': attribute.applicableCategory,
              'mandatory': attribute.mandatory,
              'description': '',
              'default_value': '',
              'is_active': attribute.isActive,
            },
      payload: (values, _) => {
        'code': values['code'],
        'name': values['name'],
        'data_type': values['data_type'],
        'applicable_category': values['applicable_category'],
        'mandatory': values['mandatory'],
        'description': values['description'],
        'default_value': values['default_value'],
        'is_active': values['is_active'],
      },
    );

ResourceDefinition<Firm> _firmProfileAssignmentDefinition(
  ApiClient api,
  PermissionService permissions,
) =>
    ResourceDefinition(
      title: 'Profile Assignment',
      resource: 'firms',
      showFrame: false,
      description: 'Assign one active business profile to each firm.',
      headers: const ['Code', 'Name', 'Country', 'Status'],
      sortFields: const ['code', 'name', null, null],
      cells: (firm) => [
        firm.code,
        firm.name,
        firm.country,
        firm.isActive ? 'Active' : 'Inactive',
      ],
      id: (firm) => firm.id,
      load: api.firms,
      canUseAction: (action, _) => _canUseResourceAction(
        permissions,
        action,
        view: const ['FIRM_VIEW', 'PLATFORM_VIEW'],
        create: const [],
        update: const ['FIRM_VIEW', 'PLATFORM_VIEW', 'PLATFORM_SETTINGS'],
        delete: const [],
      ),
      fields: const [
        FieldSpec(
          key: 'business_profile_id',
          label: 'Business profile',
          optionsResource: 'business-framework/profiles',
          singleSelection: true,
          required: true,
        ),
        FieldSpec(key: 'is_active', label: 'Active', boolean: true),
        FieldSpec(key: 'notes', label: 'Notes', multiline: true),
      ],
      initialValues: (_) => {'is_active': true},
      payload: (_, __) => {},
      canCreate: false,
      canDelete: false,
      updateEntity: false,
      loadAssignments: api.firmBusinessProfileAssignmentValues,
      saveAssignments: (firmId, values) => api.assignBusinessProfileToFirm(
        firmId,
        values['business_profile_id'].toString(),
        isActive: values['is_active'] as bool? ?? true,
        notes: values['notes'].toString(),
      ),
    );
