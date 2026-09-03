import 'dart:async';

import 'package:flutter/material.dart';

import '../core/api/api_client.dart';
import '../core/auth/session_controller.dart';
import '../core/branding/branding_config.dart';
import '../core/diagnostics/diagnostics_share.dart';
import '../core/navigation/workspace_router.dart';
import '../core/notifications/notification_service.dart';
import '../core/preferences/desktop_preferences_service.dart';
import '../core/security/permission_service.dart';
import '../core/theme/theme_manager.dart';
import '../models/branch_warehouse.dart';
import '../models/entities.dart';
import '../models/inventory.dart';
import '../models/uom_packaging.dart';
import '../models/product.dart';
import '../models/sales_invoice.dart';
import '../models/vendor.dart';
import 'customers/customer_management_page.dart';
import 'inventory/inventory_management_page.dart';
import 'inventory/inventory_details_dialog.dart';
import 'inventory/batch_management_page.dart';
import 'delivery_notes/delivery_note_management_page.dart';
import 'goods_receipts/goods_receipt_management_page.dart';
import 'purchase_invoices/purchase_invoice_management_page.dart';
import 'purchase_returns/purchase_return_management_page.dart';
import 'sales/beat_plan_management_page.dart';
import 'sales/call_list_page.dart';
import 'sales/geography_master_page.dart';
import 'sales/route_builder_page.dart';
import 'sales/territory_coverage_page.dart';
import 'sales/route_type_management_page.dart';
import 'sales/sales_invoice_management_page.dart';
import 'commission/commission_page.dart';
import 'commission/sales_target_page.dart';
import 'sales/credit_note_page.dart';
import 'sales/einvoice_page.dart';
import 'sales/gst_return_page.dart';
import 'pricing/price_list_page.dart';
import 'pricing/promotion_page.dart';
import 'products/product_management_page.dart';
import 'purchases/purchase_management_page.dart';
import 'quotations/quotation_management_page.dart';
import 'sales/sales_order_management_page.dart';
import 'sales_returns/sales_return_management_page.dart';
import 'sales/sales_territory_management_page.dart';
import 'tax/tax_configuration_page.dart';
import 'tax/tax_management_page.dart';
import 'tax/tax_rule_simulator_page.dart';
import 'tax/tax_rules_page.dart';
import 'uom/profile_uom_defaults_dialog.dart';
import 'uom/packaging_levels_page.dart';
import 'uom/uom_management_page.dart';
import 'vendors/vendor_management_page.dart';
import 'branches/branch_warehouse_management_page.dart';
import 'firms/firm_settings_page.dart';
import 'dashboard_page.dart';
import 'finance/finance_workspace.dart';
import 'inventory/physical_count_page.dart';
import 'reports/reports_workspace.dart';
import 'settings/financial_years_page.dart';
import 'settings/numbering_series_page.dart';
import 'settings/settings_workspace.dart';
import 'resource_management_page.dart';
import 'theme_selector.dart';
import 'workspace/module_catalog.dart';
import 'workspace/enterprise_sidebar.dart';
import 'workspace/desktop_framework.dart';

/// What each Administration screen is for, where the module's own sentence is
/// too general to help. Anything absent falls back to it.
///
/// A map rather than a `description` on `ModuleTabDefinition`: that would be
/// tidier but touches every module's catalog data, which is more than this
/// deserves.
const Map<String, String> _administrationDescriptions = {
  'users': 'Provision interactive users and control their access.',
  'roles': 'Group permissions into the roles users are assigned.',
  'permissions': 'Manage platform permissions and access capabilities.',
  'user-firms': 'Control which firms each user may work in.',
  'business-profiles':
      'Configure industry profiles that decide the modules and features a firm operates.',
  'feature-management': 'Review and enable the features profiles can grant.',
  'module-configuration': 'Review the modules profiles can switch on.',
  'attribute-definitions':
      'Define the custom fields a module carries, per business profile.',
  'profile-assignment': 'Assign a business profile to each firm.',
};

/// What the header says for one Administration screen.
class AdministrationHeader {
  const AdministrationHeader({
    required this.title,
    required this.description,
    required this.breadcrumbs,
  });

  final String title;
  final String description;
  final List<String> breadcrumbs;
}

/// Derives the header from the selected tab.
///
/// This used to be built from the module, with a `const` breadcrumb, so every
/// screen under Administration -- Users, Roles, Permissions -- rendered the same
/// heading and the same trail and nothing said which one was open.
///
/// The label comes from the catalog rather than a switch, so renaming a tab
/// cannot leave the heading behind.
AdministrationHeader administrationHeaderFor(String tabId) {
  final ModuleDefinition module = ModuleCatalog.byId(AppModule.administration);
  final String title = module.tabs
      .firstWhere(
        (tab) => tab.id == tabId,
        orElse: () => ModuleTabDefinition(id: tabId, label: module.label),
      )
      .label;
  return AdministrationHeader(
    title: title,
    description: _administrationDescriptions[tabId] ?? module.description,
    breadcrumbs: ['Workspace', 'Administration', title],
  );
}

/// Mirrors the login screen's constant so a report names the build it came from.
const String _shellBuildNumber =
    String.fromEnvironment('BUILD_NUMBER', defaultValue: 'Unknown');

/// 1 April of the financial year in progress, as `yyyy-MM-dd`.
///
/// Computed rather than hardcoded so it is still right next year without anyone
/// editing it: on or after 1 April the current year's date, before it the
/// previous year's. India runs April to March, which is also why the form asks
/// for GST and PAN.
///
/// Local calendar on purpose. This is a suggestion for the person filling the
/// form, and "today" means their today; the UTC rule governs what the server
/// persists and compares, not a prefill.
String currentFinancialYearStart({DateTime? today}) {
  final DateTime now = today ?? DateTime.now();
  final int year = now.month >= DateTime.april ? now.year : now.year - 1;
  return '$year-04-01';
}

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

  /// Which sales stages this firm types. The whole chain until told otherwise,
  /// which is both the platform default and the safe answer on a failed read.
  SalesWorkflowSettings _salesStages = SalesWorkflowSettings.wholeChain;
  int _lastFirmContextVersion = 0;

  /// How often the status bar asks whether the server is still there.
  ///
  /// Half a minute is often enough that a client left open overnight notices a
  /// server that went away, and rare enough to be invisible: two requests that
  /// touch no business data, one of which runs `SELECT 1`.
  static const Duration _healthInterval = Duration(seconds: 30);

  Timer? _healthTimer;
  HealthSnapshot _health = HealthSnapshot.checking;
  // A probe can outlive its own interval. The request timeout is 30 seconds and
  // a database that has gone does not answer 503 -- it stops answering at all,
  // so `/health/database` hangs until that timeout. Without this guard the
  // ticks would stack up, and an outage would be the moment the client starts
  // making more requests rather than fewer.
  bool _healthProbeInFlight = false;

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
    unawaited(_probeHealth());
    _healthTimer = Timer.periodic(_healthInterval, (_) => _probeHealth());
  }

  @override
  void dispose() {
    _healthTimer?.cancel();
    widget.session.removeListener(_sessionChanged);
    _router
      ..removeListener(_routeChanged)
      ..dispose();
    super.dispose();
  }

  /// Ask the server whether it, and its database, are answering.
  ///
  /// The status bar used to be passed `checking` and `unknown` as literals and
  /// nothing ever probed them, so it reported "checking" for the life of the
  /// application. A light that never changes is worse than no light, because it
  /// gets believed once. The decision itself lives in `health_probe.dart`,
  /// where it can be tested without a server.
  Future<void> _probeHealth() async {
    if (_healthProbeInFlight) return;
    _healthProbeInFlight = true;
    try {
      final HealthSnapshot snapshot = await probeHealth(widget.session.api);
      if (!mounted) return;
      setState(() => _health = snapshot);
    } finally {
      _healthProbeInFlight = false;
    }
  }

  void _routeChanged() {
    widget.session.registerActivity();
    if (mounted) setState(() {});
  }

  /// Learn which stages of a sale this firm types.
  ///
  /// Fails open to the whole chain, exactly as `_isEnabledByBusinessProfile`
  /// does: an unreachable settings endpoint must not hide screens a firm
  /// depends on. Hiding here is cosmetic either way -- the server refuses a
  /// bare bill from a firm on the whole chain regardless of what is on screen.
  Future<void> _refreshSalesStages() async {
    try {
      final SalesWorkflowSettings settings =
          await widget.session.api.salesWorkflowSettings();
      if (!mounted) return;
      setState(() => _salesStages = settings);
    } on ApiException {
      if (!mounted) return;
      setState(() => _salesStages = SalesWorkflowSettings.wholeChain);
    }
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
    _refreshSalesStages();
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
      .where(_isTypedByThisFirm)
      .toList();

  bool _isEnabledByBusinessProfile(ModuleDefinition module) {
    final Set<String>? configured = _activeBusinessModuleCodes;
    if (configured == null) {
      return true;
    }
    final String? code = ModuleCatalog.businessModuleCode(module.id);
    return code == null || configured.contains(code);
  }

  /// Hide the screens for stages this firm does not fill in by hand.
  ///
  /// All four sales documents share the single business module code `SALES`,
  /// so this cannot be expressed through the business profile -- it is its own
  /// predicate. Sales returns are never hidden: a counter sale still comes
  /// back, and a return is the only correct way to undo one.
  bool _isTypedByThisFirm(ModuleDefinition module) => switch (module.id) {
        AppModule.quotations => _salesStages.quotationStage,
        AppModule.salesOrders => _salesStages.salesOrderStage,
        AppModule.deliveryNotes => _salesStages.deliveryNoteStage,
        _ => true,
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
            // The application name, the collapse toggle and the theme
            // selector all used to sit here as well as in the sidebar, which
            // owns all three -- its header carries the name and the toggle,
            // its footer the theme. Two copies of a control are two things to
            // keep in step and one of them is always the wrong one to reach
            // for.
            //
            // The module title stays. It is the third place it appears, after
            // the selected sidebar item and the page's own header -- but only
            // seven screens render a header of their own, so removing it here
            // would leave the rest with no title at all. Back and forward stay
            // whatever else changes: they are genuinely useful and rare in an
            // ERP.
            child: Row(children: [
              const SizedBox(width: 4),
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
              PopupMenuButton<String>(
                tooltip: 'Profile',
                padding: EdgeInsets.zero,
                icon: const Icon(Icons.account_circle_outlined),
                onSelected: (value) {
                  if (value == 'logout') {
                    widget.session.logout();
                    return;
                  }
                  if (value == 'diagnostics') {
                    unawaited(
                      DiagnosticsReportDialog.show(
                        context,
                        appName: widget.branding.appName,
                        version: widget.branding.version,
                        buildNumber: _shellBuildNumber,
                        firmCode: widget.session.currentFirm?.code,
                        // No user identifier is passed: the session exposes the
                        // username, which is an email address, and a support
                        // report is not a reason to move that onto a third
                        // machine.
                        serverUrl: widget.session.baseUrl,
                      ),
                    );
                  }
                },
                itemBuilder: (context) => [
                  PopupMenuItem(
                    enabled: false,
                    child: Text(widget.session.attemptedUsername ?? 'User'),
                  ),
                  const PopupMenuDivider(),
                  const PopupMenuItem<String>(
                    value: 'diagnostics',
                    child: ListTile(
                      dense: true,
                      leading: Icon(Icons.bug_report_outlined),
                      title: Text('Diagnostics report'),
                    ),
                  ),
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
        stateText: switch (_health.backend) {
          ConnectionStateIndicator.online => 'Online',
          ConnectionStateIndicator.offline => 'Offline',
          _ => 'Connecting',
        },
        currentUser: widget.session.attemptedUsername,
        currentFirm: widget.session.currentFirm?.name ?? 'No active firm',
        backend: _health.backend,
        database: _health.database,
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
      // Documents are filed under the process they belong to. This section
      // used to carry eight top-level entries, with Sales Invoices a sibling
      // of Sales -- a document type outranking the process it belongs to, so
      // somebody hunting an invoice had to know it had been promoted rather
      // than filed where they would look first.
      //
      // Each one is still a whole module with its own page, permissions and
      // route. Only where it is drawn changed, which is why no stored
      // workspace had to be migrated and no route needed an alias.
      // Sales first. The section is ordered by how often it is opened, not by
      // the order goods move in: a distribution firm raises sales orders every
      // day and purchase orders every few weeks, so putting the weekly job
      // above the daily one costs the daily one a glance every time.
      EnterpriseSidebarSection(
        label: 'TRANSACTIONS',
        moduleIds: pick([AppModule.sales, AppModule.purchases]),
        childModuleIds: {
          AppModule.sales: pick([
            AppModule.quotations,
            AppModule.salesOrders,
            AppModule.deliveryNotes,
            AppModule.salesInvoices,
            AppModule.salesReturns,
          ]),
          AppModule.purchases: pick([
            AppModule.goodsReceipts,
            AppModule.purchaseInvoices,
            AppModule.purchaseReturns,
          ]),
        },
        // Documents follow the order they come from, so receiving reads as
        // the next step rather than as something filed after Settings.
        childModulesAfter: const {
          AppModule.sales: '',
          AppModule.purchases: 'purchase-orders',
        },
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
            // A stored workspace may still name one of the six retired
            // entries. Pending was the drafts, so honour it; the rest were
            // reports and open the list.
            initialView: SalesInvoiceView.fromTabId(
              _router.current.module == AppModule.salesInvoices.name
                  ? _router.current.tab
                  : null,
            ),
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
        AppModule.quotations => QuotationManagementPage(
            key: ValueKey('quotations-${widget.session.firmContextVersion}'),
            api: api,
            permissions: widget.permissions,
            hasActiveFirm: widget.session.currentFirm != null,
          ),
        AppModule.salesReturns => SalesReturnManagementPage(
            key: ValueKey('sales-returns-${widget.session.firmContextVersion}'),
            api: api,
            permissions: widget.permissions,
            hasActiveFirm: widget.session.currentFirm != null,
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
        // Finance is not "coming soon": thirty endpoints have been live since
        // `20260809_0042`, and every goods receipt, dispatch and invoice posts
        // to the ledger through them. The chart of accounts and the trial
        // balance are what make those postings legible; journal entries,
        // receipts and payments are still placeholders and the catalog says so.
        AppModule.accounting => FinanceWorkspace(
            key: ValueKey('finance-${widget.session.firmContextVersion}'),
            api: api,
            preferences: widget.preferences,
            permissions: widget.permissions,
            hasActiveFirm: widget.session.currentFirm != null,
            tabId: _router.current.tab ?? 'chart-of-accounts',
          ),
        AppModule.settings => SystemSettingsWorkspace(
            api: api,
            permissions: widget.permissions,
            tabId: _router.current.tab ?? 'audit-logs',
            firmLabel: widget.session.currentFirm?.name,
          ),
        AppModule.reports => ReportsWorkspace(
            api: api,
            permissions: widget.permissions,
            hasActiveFirm: widget.session.currentFirm != null,
            tabId: _router.current.tab ?? 'operational',
          ),
        AppModule.licensing => _ComingSoonModule(
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
          'category-attribute-rules',
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
          definition: permissionDefinition(
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
      'numbering-series' => NumberingSeriesPage(
          api: widget.api,
          permissions: widget.permissions,
          hasActiveFirm: widget.api.activeFirmId?.call() != null,
        ),
      'business-profiles' => ResourceManagementPage<BusinessProfileRecord>(
          api: widget.api,
          definition: _businessProfileDefinition(
            widget.api,
            widget.permissions,
            context: context,
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
      'vendor-categories' => ResourceManagementPage<VendorClassification>(
          api: widget.api,
          definition: vendorClassificationDefinition(
            widget.api,
            widget.permissions,
            categories: true,
          ),
        ),
      'vendor-types' => ResourceManagementPage<VendorClassification>(
          api: widget.api,
          definition: vendorClassificationDefinition(
            widget.api,
            widget.permissions,
            categories: false,
          ),
        ),
      'category-attribute-rules' =>
        ResourceManagementPage<CategoryAttributeRuleRecord>(
          api: widget.api,
          definition: categoryAttributeRuleDefinition(
            widget.api,
            widget.permissions,
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
      'packaging-levels' => PackagingLevelsPage(
          api: widget.api,
          permissions: widget.permissions,
          hasActiveFirm: widget.api.activeFirmId?.call() != null,
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
    final AdministrationHeader header = administrationHeaderFor(tabId);
    return ConfigurationWorkspace(
      title: header.title,
      description: header.description,
      breadcrumbs: header.breadcrumbs,
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
      'financial-years' => FinancialYearsPage(
          api: widget.api,
          permissions: widget.permissions,
          hasActiveFirm: hasActiveFirm,
        ),
      'firm-settings' => FirmSettingsPage(
          api: widget.api,
          permissions: widget.permissions,
          hasActiveFirm: hasActiveFirm,
          activeFirmId: widget.api.activeFirmId?.call(),
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
        'firm-settings' =>
          'Configure the active firm\'s business profile and related settings.',
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
      'route-types' => RouteTypeManagementPage(
          api: widget.api,
          permissions: widget.permissions,
        ),
      'beat-plans' => BeatPlanManagementPage(
          api: widget.api,
          permissions: widget.permissions,
        ),
      'call-lists' => CallListPage(
          api: widget.api,
          permissions: widget.permissions,
        ),
      'coverage' => TerritoryCoveragePage(
          api: widget.api,
          permissions: widget.permissions,
        ),
      'route-builder' => RouteBuilderPage(
          api: widget.api,
          permissions: widget.permissions,
        ),
      'geography-masters' => GeographyMasterPage(
          api: widget.api,
          permissions: widget.permissions,
        ),
      'price-lists' => PriceListPage(
          api: widget.api,
          permissions: widget.permissions,
          hasActiveFirm: widget.api.activeFirmId?.call() != null,
        ),
      'promotions' => PromotionPage(
          api: widget.api,
          permissions: widget.permissions,
          hasActiveFirm: widget.api.activeFirmId?.call() != null,
        ),
      'commission' => CommissionPage(
          api: widget.api,
          permissions: widget.permissions,
          hasActiveFirm: widget.api.activeFirmId?.call() != null,
        ),
      'targets' => SalesTargetPage(
          api: widget.api,
          permissions: widget.permissions,
          hasActiveFirm: widget.api.activeFirmId?.call() != null,
        ),
      'credit-notes' => CreditNotePage(
          api: widget.api,
          permissions: widget.permissions,
          hasActiveFirm: widget.api.activeFirmId?.call() != null,
        ),
      'einvoice' => EInvoicePage(
          api: widget.api,
          permissions: widget.permissions,
          hasActiveFirm: widget.api.activeFirmId?.call() != null,
        ),
      'gst-returns' => GstReturnPage(
          api: widget.api,
          permissions: widget.permissions,
          hasActiveFirm: widget.api.activeFirmId?.call() != null,
        ),
      _ => WorkspaceEmptyState(
          title:
              '${visibleTabs.firstWhere((tab) => tab.id == tabId).label} is coming soon',
          message:
              'The current API does not provide ${visibleTabs.firstWhere((tab) => tab.id == tabId).label.toLowerCase()} operations.',
        ),
    };

    final (String heading, String blurb) = switch (tabId) {
      'territories' => (
          'Geography Management',
          'Configure multi-level territory hierarchy, assignments, and routing foundation.',
        ),
      'route-types' => (
          'Route Types',
          'The kinds of round this firm runs — a sales beat, a collection round.',
        ),
      'beat-plans' => (
          'Beat Plans',
          'When each route runs: which day, how often, and between which dates.',
        ),
      'call-lists' => (
          'Call Lists',
          'Who is called on a given day, in the order the round walks them.',
        ),
      'coverage' => (
          'Coverage',
          'How much ground each salesperson carries, and who carries none.',
        ),
      'route-builder' => (
          'Route Builder',
          'Find outlets by pin code or street, put them on a round, and set '
              'the order they are called in.',
        ),
      'geography-masters' => (
          'Places',
          'The shared geography every address and route hangs off: country to '
              'locality.',
        ),
      'price-lists' => (
          'Price Lists',
          'What a firm has agreed to charge, and to whom: a rate off the '
              'product price, from a date.',
        ),
      'promotions' => (
          'Promotions',
          'The offers running now. Several apply to one order, in priority '
              'order, and percentages compound on what is left.',
        ),
      'targets' => (
          'Targets',
          'What the firm expects to sell, and how it went. Each target is '
              'measured over its own period, not the window above it.',
        ),
      'einvoice' => (
          'E-Invoice',
          'What the tax authority knows about this firm’s invoices and their '
              'movement. A reference marked sandbox filed nothing.',
        ),
      'gst-returns' => (
          'GST Returns',
          'What this firm declares for a period, read off what it actually '
              'sold. Nothing is stored: a cancelled invoice simply drops out.',
        ),
      'credit-notes' => (
          'Credit Notes',
          'Money credited without goods coming back — a rate agreed later, a '
              'discount given after the sale. It reverses the tax the invoice '
              'charged; a sales return is the one that moves stock.',
        ),
      'commission' => (
          'Commission',
          'What a salesman earns on the money that actually came in, and the '
              'rates that decide it.',
        ),
      _ => (module.label, module.description),
    };

    return ModuleWorkspaceFrame(
      title: heading,
      description: blurb,
      breadcrumbs: [
        'Workspace',
        'Sales',
        visibleTabs.firstWhere((tab) => tab.id == tabId).label,
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
    // A stored workspace may still name a tab that became a status view.
    // Resolve it to Purchase Orders on that view rather than letting the
    // fallback below drop the user on the Dashboard with no explanation.
    final String? aliased = ModuleCatalog.purchaseTabAliases[requestedTab];
    final PurchaseOrderView initialView = switch (requestedTab) {
      'draft-orders' => PurchaseOrderView.draft,
      'open-orders' => PurchaseOrderView.open,
      'cancelled-orders' => PurchaseOrderView.cancelled,
      'closed-orders' => PurchaseOrderView.closed,
      'purchase-history' => PurchaseOrderView.history,
      _ => PurchaseOrderView.all,
    };
    final String? resolvedTab = aliased ?? requestedTab;
    final String tabId = visibleTabs.any((tab) => tab.id == resolvedTab)
        ? resolvedTab!
        : visibleTabs.first.id;
    final bool hasActiveFirm =
        widget.api.activeFirmId?.call()?.isNotEmpty == true;
    void navigateTo(PurchaseSection section) {
      final String nextTab = switch (section) {
        PurchaseSection.dashboard => 'purchase-dashboard',
        PurchaseSection.purchaseOrders => 'purchase-orders',
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
          initialView: initialView,
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
        'purchase-analytics' => 'Purchase Analytics',
        'purchase-settings' => 'Purchase Settings',
        _ => module.label,
      },
      description: switch (tabId) {
        'purchase-dashboard' =>
          'Enterprise purchase command center with KPI cards, recent orders, and vendor spend insights.',
        'purchase-orders' =>
          'Manage purchase orders with lifecycle actions, import/export, and responsive enterprise editing.',
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
    final bool hasActiveFirm =
        widget.api.activeFirmId?.call()?.isNotEmpty == true;

    return GoodsReceiptManagementPage(
      api: widget.api,
      preferences: widget.preferences,
      permissions: widget.permissions,
      hasActiveFirm: hasActiveFirm,
      initialView: GoodsReceiptView.fromTabId(requestedTab),
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
    final bool hasActiveFirm =
        widget.api.activeFirmId?.call()?.isNotEmpty == true;

    return DeliveryNoteManagementPage(
      api: widget.api,
      preferences: widget.preferences,
      permissions: widget.permissions,
      hasActiveFirm: hasActiveFirm,
      initialView: DeliveryNoteView.fromTabId(requestedTab),
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
      'physical-counts' => PhysicalCountPage(
          api: widget.api,
          permissions: widget.permissions,
          hasActiveFirm: hasActiveFirm,
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

/// The optional HR/profile half of a user payload, sent on create and update
/// alike.
///
/// One builder because two lists drift: creation used to send none of these,
/// so the Mobile and Profile photo boxes on the create form were discarded on
/// save and the record opened blank afterwards.
Json userProfilePayload(Map<String, dynamic> values) => {
      'personal_mobile': _orNull(values['personal_mobile']),
      'alternate_mobile': _orNull(values['alternate_mobile']),
      'profile_photo_url': _orNull(values['profile_photo_url']),
      'personal_email': _orNull(values['personal_email']),
      'office_email': _orNull(values['office_email']),
      'emergency_contact_name': _orNull(values['emergency_contact_name']),
      'emergency_mobile': _orNull(values['emergency_mobile']),
      'emergency_relationship': _orNull(values['emergency_relationship']),
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
    };

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
        'Storage',
        'Status'
      ],
      sortFields: const ['code', 'name', null, null, null, null, null],
      cells: (firm) => [
        firm.code,
        firm.name,
        firm.contactEmail,
        firm.currencyCode,
        firm.country,
        // A dedicated firm cannot serve requests until its tables exist, so
        // this is the difference between "configured" and "usable".
        firm.isStorageReady ? 'Ready' : 'Not provisioned',
        firm.isActive ? 'Active' : 'Inactive',
      ],
      // A firm with no business profile silently runs as the platform default,
      // so a wholesale business can end up operating as GENERIC. The profile
      // cannot be set from here, so the next step is named instead.
      createFollowUp: (_) =>
          'Set this firm\'s business profile in Masters → Firm Settings. '
          'Until then it runs on the platform default.',
      customActions: [
        ResourceAction<Firm>(
          label: 'Provision storage',
          icon: Icons.dns_outlined,
          isVisible: (firm) => firm == null || firm.deploymentMode != 'SHARED',
          isEnabled: (firm) =>
              firm.deploymentMode != 'SHARED' && !firm.isStorageReady,
          onInvoke: (firm) => api.provisionFirmStorage(firm.id),
        ),
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
          helperText: phoneHelperText,
          section: 'Contacts',
        ),
        FieldSpec(key: 'currency_code', label: 'Currency code', required: true),
        FieldSpec(
          key: 'financial_year_start',
          label: 'Financial year start',
          helperText: 'ISO date, for example 2026-04-01.',
          required: true,
        ),
        // Storage routing is fixed at creation: the firm's data is only ever
        // provisioned once, and nothing migrates it between stores, so the
        // backend refuses a change here. Show it, do not offer to edit it.
        FieldSpec(
          key: 'deployment_mode',
          label: 'Deployment mode',
          helperText:
              'SHARED, SCHEMA, or DATABASE. Fixed once the firm exists.',
          section: 'Storage Mapping',
          readOnlyWhenEditing: true,
        ),
        FieldSpec(
          key: 'database_type',
          label: 'Database type',
          helperText: 'Use platform engine (for example postgresql).',
          section: 'Storage Mapping',
          readOnlyWhenEditing: true,
        ),
        FieldSpec(
          key: 'database_name',
          label: 'Database name',
          helperText: 'Required for SCHEMA and DATABASE modes.',
          section: 'Storage Mapping',
          readOnlyWhenEditing: true,
        ),
        FieldSpec(
          key: 'schema_name',
          label: 'Schema name',
          helperText: 'Required for SCHEMA and DATABASE modes.',
          section: 'Storage Mapping',
          readOnlyWhenEditing: true,
        ),
        FieldSpec(
          key: 'connection_profile',
          label: 'Connection profile',
          helperText: 'Name of a server configured in '
              'AGENCY_TENANCY_CONNECTION_PROFILES, e.g. REMOTE_A. Empty uses '
              'the platform server. Fixed once the firm exists.',
          section: 'Storage Mapping',
          readOnlyWhenEditing: true,
        ),
        // The business profile lives on the Firm Settings tab, not here. Its
        // catalogue is a firm-owned table with no copy in the platform schema,
        // so loading it needs a firm context that this platform-level page does
        // not have -- the dropdown answered 503 every time it was opened.
        FieldSpec(key: 'is_active', label: 'Active', boolean: true),
        FieldSpec(key: 'notes', label: 'Notes', multiline: true),
      ],
      initialValues: (firm) => firm == null
          ? {
              'is_active': true,
              'deployment_mode': 'SHARED',
              'database_type': 'postgresql',
              // Defaults, not decisions -- every one of these stays editable.
              // The form already asks for GST and PAN, which are Indian
              // registrations, so the country and currency are not a guess.
              'country': 'IN',
              'currency_code': 'INR',
              'financial_year_start': currentFinancialYearStart(),
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
              'connection_profile': firm.connectionProfile,
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
              // The create form shows these, so it has to send them. It used
              // to send only the six above, which meant a mobile number or a
              // photo typed at creation was silently dropped and the record
              // opened blank afterwards.
              ...userProfilePayload(values),
            }
          : {
              'full_name': values['full_name'],
              'is_active': values['is_active'],
              'expires_at': _orNull(values['expires_at']),
              'unlock': values['unlock'],
              ...userProfilePayload(values),
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
      // Same blindness as the profile assignment: the form is a firm picker
      // and nothing in it says whose access is being changed.
      dialogSubtitle: (user) => <String>[
        if (user.fullName.isNotEmpty) user.fullName,
        user.email,
        user.isActive ? 'Active' : 'Inactive',
      ].join('  ·  '),
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
      // The permission picker is long enough to scroll the role's own name
      // out of view, and granting the wrong role is not visible afterwards.
      dialogSubtitle: (role) => <String>[
        '${role.code} — ${role.name}',
        role.isSystem ? 'System role' : 'Custom role',
      ].join('  ·  '),
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

ResourceDefinition<Permission> permissionDefinition(
  ApiClient api,
  PermissionService permissions, {
  bool showFrame = true,
}) =>
    ResourceDefinition(
      title: 'Permissions',
      resource: 'permissions',
      showFrame: showFrame,
      description: 'Manage platform permissions and access capabilities.',
      // Readable name first, technical code second. An administrator scanning
      // this list is looking for "Journal Posting", not JOURNAL_POST -- the
      // code matters once they have found the row, not while finding it.
      //
      // Module and Action columns are deliberately absent: the permissions API
      // returns neither, and inventing them by splitting the code would be a
      // guess displayed as fact. The grid takes them the moment the API does.
      headers: const ['Permission', 'Code', 'Status'],
      sortFields: const ['name', 'code', null],
      cells: (permission) => [
        permission.name,
        permission.code,
        permission.isActive ? 'Active' : 'Inactive',
      ],
      id: (permission) => permission.id,
      load: api.permissions,
      // Carries the chosen page size into the request, so 25/50/100 changes
      // what the server returns rather than only what the table thinks.
      loadPage: ({
        int page = 1,
        int pageSize = 25,
        String search = '',
        String sortBy = 'created_at',
        bool descending = true,
        Map<String, String> filters = const {},
      }) =>
          api.permissions(
        page: page,
        pageSize: pageSize,
        search: search,
        sortBy: sortBy,
        descending: descending,
      ),
      searchHint: 'Search permissions by name or code',
      // No filter bar: /api/v1/permissions accepts only page, page_size,
      // search, sort_by and sort_direction, and inventing client-side filtering
      // would disagree with the record count and the paging. The bar appears
      // for a module the moment its endpoint can honour one.
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
  BuildContext? context,
  bool showFrame = true,
}) =>
    ResourceDefinition(
      title: 'Business Profiles',
      resource: 'business-framework/profiles',
      showFrame: showFrame,
      // Default units are not fields on the profile: the profile is
      // platform-wide while units are firm-owned, so they have their own
      // endpoint. The action lives here because this is the only screen that
      // lists profiles, and it is where someone configuring one looks for
      // them.
      customActions: [
        if (context != null)
          ResourceAction<BusinessProfileRecord>(
            label: 'Default units',
            icon: Icons.straighten_outlined,
            isVisible: (_) => permissions.hasPermission('UOM_VIEW'),
            onInvoke: (profile) async {
              if (!context.mounted) return '';
              await showDialog<BusinessProfileUomDefaults>(
                context: context,
                builder: (_) => ProfileUomDefaultsDialog(
                  api: api,
                  permissions: permissions,
                  profileId: profile.id,
                  profileName: profile.name,
                ),
              );
              // The dialog announces its own result; saying anything here
              // would also congratulate someone who just closed it.
              return '';
            },
          ),
      ],
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

/// One vendor master, as a screen. Categories and types differ only in name.
///
/// `vendors.category_id` and `vendors.type_id` have been columns from the
/// start and `VendorWrite` has always accepted both, but nothing in the
/// desktop could create a category to point at, and the vendor form offered
/// neither field -- so both columns were unreachable and stayed NULL for every
/// vendor anybody has ever created here.
ResourceDefinition<VendorClassification> vendorClassificationDefinition(
  ApiClient api,
  PermissionService permissions, {
  required bool categories,
}) {
  final String noun = categories ? 'Category' : 'Type';
  return ResourceDefinition(
    title: 'Vendor ${noun}s',
    resource: categories ? 'vendors/categories' : 'vendors/types',
    description: categories
        ? 'Group vendors by what they supply.'
        : 'Classify vendors by the kind of supplier they are.',
    headers: const ['Code', 'Name', 'Description', 'Active'],
    cells: (VendorClassification row) => [
      row.code,
      row.name,
      row.description,
      row.isActive ? 'Yes' : 'No',
    ],
    id: (VendorClassification row) => row.id,
    load: categories ? api.vendorCategories : api.vendorTypes,
    canUseAction: (action, _) => _canUseResourceAction(
      permissions,
      action,
      view: const ['VENDOR_VIEW'],
      create: const ['VENDOR_CREATE'],
      update: const ['VENDOR_UPDATE'],
      delete: const ['VENDOR_DELETE'],
    ),
    fields: [
      FieldSpec(
        key: 'code',
        label: '$noun code',
        required: true,
        // The server upper-cases and validates the pattern; editing a code a
        // vendor already points at is a rename of the thing, not a new one.
        readOnlyWhenEditing: true,
        helperText: '2-50 characters: A-Z, 0-9, underscore or hyphen.',
      ),
      FieldSpec(key: 'name', label: 'Name', required: true),
      FieldSpec(key: 'description', label: 'Description', multiline: true),
      const FieldSpec(key: 'is_active', label: 'Active', boolean: true),
    ],
    initialValues: (VendorClassification? row) => row == null
        ? <String, dynamic>{'is_active': true}
        : <String, dynamic>{
            'code': row.code,
            'name': row.name,
            'description': row.description,
            'is_active': row.isActive,
          },
    payload: (values, isCreating) => {
      'code': values['code'],
      'name': values['name'],
      'description': _blankToNull(values['description']),
      'is_active': values['is_active'],
    },
  );
}

/// The rules that make an attribute mandatory for a product category.
///
/// An `AttributeDefinition` can be marked mandatory outright, and until
/// `20260815_0087` four of them were -- which asked a pharmacy for an IMEI and
/// an electronics distributor for an expiry date, and `AttributeService`
/// refuses the write, so product creation was blocked outright on a freshly
/// migrated database. That migration cleared the flags on the understanding
/// that a requirement would be stated here instead: scoped to a category, and
/// optionally to one industry. Nothing in the desktop could state one, so for
/// a week no attribute could be made mandatory by anybody.
/// Public so `test/category_attribute_rule_test.dart` can drive the real
/// definition rather than a copy of its field list -- the copy is what let the
/// attribute definition form and its test disagree about four columns.
ResourceDefinition<CategoryAttributeRuleRecord> categoryAttributeRuleDefinition(
  ApiClient api,
  PermissionService permissions,
) {
  // `validation_override` has no editor; the record being edited is held so
  // the update can echo it back rather than clearing it. Same reason, and the
  // same shape, as `validation_rule` on the attribute definition below.
  CategoryAttributeRuleRecord? editing;
  return ResourceDefinition(
    title: 'Mandatory Attributes',
    resource: 'business-framework/category-attribute-rules',
    description:
        'Say which attribute a product category must carry, for one industry '
        'or for all of them.',
    headers: const ['Category', 'Attribute', 'Business profile', 'Required'],
    sortFields: const ['category_code', null, null, null],
    cells: (rule) => [
      rule.categoryCode,
      rule.attributeName.isEmpty ? rule.attributeCode : rule.attributeName,
      rule.businessProfileCode.isEmpty
          ? 'Every industry'
          : rule.businessProfileCode,
      rule.isMandatory ? 'Yes' : 'No',
    ],
    id: (rule) => rule.id,
    load: api.categoryAttributeRules,
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
        key: 'category_code',
        label: 'Product category',
        required: true,
        optionsResource: 'products/categories',
        singleSelection: true,
        // Matched against the category's code, not its id -- an id stored
        // here matches no category and the rule silently never applies.
        submitsCode: true,
        helperText: 'Which category of product this requirement is about.',
      ),
      FieldSpec(
        key: 'attribute_definition_id',
        label: 'Attribute',
        required: true,
        optionsResource: 'business-framework/attribute-definitions',
        singleSelection: true,
        helperText: 'The field that must be filled in. Define it first under '
            'Dynamic Attributes.',
      ),
      FieldSpec(
        key: 'business_profile_id',
        label: 'Limit to business profile',
        optionsResource: 'business-framework/profiles',
        singleSelection: true,
        section: 'Where it applies',
        helperText: 'Leave empty and the requirement holds for every industry.',
      ),
      FieldSpec(
        key: 'is_mandatory',
        label: 'Required',
        boolean: true,
        section: 'Where it applies',
        helperText: 'Off records the pairing without enforcing it.',
      ),
    ],
    initialValues: (rule) {
      editing = rule;
      return rule == null
          ? {'is_mandatory': true}
          : {
              'category_code': rule.categoryCode,
              'attribute_definition_id': rule.attributeDefinitionId,
              'business_profile_id': rule.businessProfileId,
              'is_mandatory': rule.isMandatory,
            };
    },
    payload: (values, isCreating) => {
      'category_code': values['category_code'],
      'attribute_definition_id': values['attribute_definition_id'],
      'business_profile_id': _blankToNull(values['business_profile_id']),
      'is_mandatory': values['is_mandatory'],
      // Round-tripped, not edited. Omitting it would null an override the
      // form never showed.
      if (!isCreating && editing?.validationOverride != null)
        'validation_override': editing!.validationOverride,
    },
  );
}

ResourceDefinition<AttributeDefinitionRecord> _attributeDefinitionDefinition(
  ApiClient api,
  PermissionService permissions, {
  bool showFrame = true,
}) {
  // The update endpoint replaces the whole record, so anything the form does
  // not send is reset. `validation_rule` has no editor, so the record being
  // edited is held here and its rule echoed back rather than dropped.
  // `initialValues` always runs before `payload` for the same dialog, and a
  // create passes null, which clears it.
  AttributeDefinitionRecord? editing;
  return ResourceDefinition(
      title: 'Attribute Definitions',
      resource: 'business-framework/attribute-definitions',
      showFrame: showFrame,
      description:
          'Define reusable attribute metadata for future product and inventory modules.',
      headers: const ['Code', 'Applies to', 'Name', 'Data type', 'Category'],
      sortFields: const ['code', null, 'name', null, null],
      cells: (attribute) => [
        attribute.code,
        attribute.entityType,
        attribute.name,
        attribute.dataType,
        attribute.applicableCategory,
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
        FieldSpec(
          key: 'entity_type',
          label: 'Applies to',
          required: true,
          choices: [
            'PRODUCT',
            'CUSTOMER',
            'VENDOR',
            'BRANCH',
            'WAREHOUSE',
            'TAX_PROFILE',
            'UOM',
          ],
          helperText: 'Which record carries this field.',
        ),
        FieldSpec(
          key: 'data_type',
          label: 'Data type',
          required: true,
          choices: ['TEXT', 'NUMBER', 'DATE', 'BOOLEAN'],
          helperText: 'Decides which column stores the value, and how it is '
              'validated and reported on.',
        ),
        FieldSpec(key: 'description', label: 'Description', multiline: true),
        FieldSpec(key: 'default_value', label: 'Default value'),
        FieldSpec(
          key: 'mandatory',
          label: 'Mandatory',
          boolean: true,
        ),
        FieldSpec(key: 'is_active', label: 'Active', boolean: true),
        FieldSpec(
          key: 'applicable_business_profile_id',
          label: 'Limit to business profile',
          optionsResource: 'business-framework/profiles',
          singleSelection: true,
          section: 'Where it applies',
          helperText: 'Leave empty to offer this field to every industry.',
        ),
        FieldSpec(
          key: 'applicable_category',
          label: 'Limit to product category',
          optionsResource: 'products/categories',
          singleSelection: true,
          // Matched against the category's code, not its id.
          submitsCode: true,
          section: 'Where it applies',
          helperText: 'Leave empty to offer this field in every category.',
        ),
      ],
      initialValues: (attribute) {
        editing = attribute;
        return attribute == null
          ? {
              'mandatory': false,
              'is_active': true,
              'entity_type': 'PRODUCT',
              'data_type': 'TEXT',
            }
          : {
              'code': attribute.code,
              'name': attribute.name,
              'entity_type': attribute.entityType,
              'data_type': attribute.dataType,
              'applicable_category': attribute.applicableCategory,
              'applicable_business_profile_id':
                  attribute.applicableBusinessProfileId,
              'mandatory': attribute.mandatory,
              'description': attribute.description,
              'default_value': attribute.defaultValue,
              'is_active': attribute.isActive,
            };
      },
      payload: (values, isCreating) => {
        'code': values['code'],
        'name': values['name'],
        'entity_type': values['entity_type'],
        'data_type': values['data_type'],
        'applicable_category': _blankToNull(values['applicable_category']),
        'applicable_business_profile_id':
            _blankToNull(values['applicable_business_profile_id']),
        'mandatory': values['mandatory'],
        'description': _blankToNull(values['description']),
        'default_value': _blankToNull(values['default_value']),
        'is_active': values['is_active'],
        // Round-tripped, not edited. Omitting it would null a rule the form
        // never showed.
        if (!isCreating && editing?.validationRule != null)
          'validation_rule': editing!.validationRule,
      },
    );
}

/// Send null rather than an empty string for an optional column.
///
/// A blank text box means "not set"; storing `''` makes
/// `applicable_category` a category code no product has, which silently stops
/// the definition applying anywhere.
Object? _blankToNull(Object? value) {
  final String text = (value ?? '').toString().trim();
  return text.isEmpty ? null : text;
}

ResourceDefinition<Firm> _firmProfileAssignmentDefinition(
  ApiClient api,
  PermissionService permissions,
) {
  // Filled by `load` on every fetch, including the refresh that follows a
  // save, so the column cannot show what was true before the assignment
  // changed. `cells` is synchronous, so the join has to be prepared first
  // rather than awaited per row.
  final Map<String, FirmProfileAssignment> assigned =
      <String, FirmProfileAssignment>{};
  return ResourceDefinition(
      title: 'Profile Assignment',
      resource: 'firms',
      showFrame: false,
      description: 'Assign one active business profile to each firm.',
      // The form is a profile dropdown, a switch and a notes box — nothing in
      // it names the firm being assigned to. Without this the dialog reads
      // "Profile Assignment / Edit existing record" and the user has to
      // remember which row they opened, which is exactly the moment to get it
      // wrong: a profile decides which features and modules a firm operates.
      dialogSubtitle: (firm) => <String>[
        '${firm.code} — ${firm.name}',
        if (firm.city.isNotEmpty) firm.city,
        if (firm.country.isNotEmpty) firm.country,
        if (firm.currencyCode.isNotEmpty) firm.currencyCode,
        firm.isActive ? 'Active' : 'Inactive',
      ].join('  ·  '),
      headers: const ['Code', 'Name', 'Business profile', 'Country', 'Status'],
      sortFields: const ['code', 'name', null, null, null],
      cells: (firm) => [
        firm.code,
        firm.name,
        // Never blank. An unassigned firm, one whose store cannot be read and
        // one that simply has not loaded are three different situations, and
        // an empty cell reads as "nothing to do here" for all of them.
        assigned[firm.id]?.label ?? 'Not assigned',
        firm.country,
        firm.isActive ? 'Active' : 'Inactive',
      ],
      id: (firm) => firm.id,
      load: ({
        int page = 1,
        String search = '',
        String sortBy = 'created_at',
        bool descending = true,
      }) async {
        final PagedResult<Firm> firms = await api.firms(
          page: page,
          search: search,
          sortBy: sortBy,
          descending: descending,
        );
        // A failure here must not take the whole grid down: the firms are the
        // record being administered and the profile is a column on them, so a
        // store that cannot be reached should cost that cell, not the page.
        try {
          assigned
            ..clear()
            ..addAll(await api.firmProfileAssignments());
        } on ApiException {
          assigned.clear();
        }
        return firms;
      },
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
}
