import 'package:flutter/material.dart';

import '../core/api/api_client.dart';
import '../core/auth/session_controller.dart';
import '../core/branding/branding_config.dart';
import '../core/navigation/workspace_router.dart';
import '../core/notifications/notification_service.dart';
import '../core/preferences/desktop_preferences_service.dart';
import '../core/security/permission_service.dart';
import '../core/theme/theme_manager.dart';
import '../models/entities.dart';
import 'customers/customer_management_page.dart';
import 'dashboard_page.dart';
import 'resource_management_page.dart';
import 'theme_selector.dart';
import 'workspace/module_catalog.dart';
import 'workspace/workspace_components.dart';
import 'workspace/global_search.dart';
import 'workspace/workspace_interactions.dart';

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
  late final WorkspaceRouter _router;
  late bool _sidebarCollapsed;

  @override
  void initState() {
    super.initState();
    _sidebarCollapsed = widget.preferences.current.sidebarCollapsed;
    _router = WorkspaceRouter(
      initialLocation: widget.session.lastWorkspace,
      onPersist: widget.session.saveLastWorkspace,
    )..addListener(_routeChanged);
  }

  @override
  void dispose() {
    _router
      ..removeListener(_routeChanged)
      ..dispose();
    super.dispose();
  }

  void _routeChanged() {
    widget.session.registerActivity();
    if (mounted) setState(() {});
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
      .toList();

  @override
  Widget build(BuildContext context) => AnimatedBuilder(
        animation: widget.permissions,
        builder: (context, _) {
          final List<ModuleDefinition> modules = _visibleModules;
          if (modules.isEmpty) {
            return Scaffold(
              appBar: AppBar(
                title: Text(widget.branding.appName),
                actions: [ThemeSelector(manager: widget.themes)],
              ),
              body: WorkspaceEmptyState(
                title: 'No workspace access',
                message:
                    'Your account has no permissions for available modules.',
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
              globalSearch: () => showGlobalSearch(context),
            ),
            child: LayoutBuilder(
              builder: (context, constraints) {
                final bool wide = constraints.maxWidth >= 1000;
                final Widget page = _page(widget.session.api, section);
                if (wide) {
                  return Scaffold(
                    body: Row(children: [
                      SizedBox(
                        width: _sidebarCollapsed ? 72 : 248,
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
        child: SizedBox(
          height: 64,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Row(children: [
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
              Text(
                ModuleCatalog.byId(section).label,
                style: Theme.of(context).textTheme.titleLarge,
              ),
              const Spacer(),
              _firmControl(),
              if (widget.session.notice != null)
                IconButton(
                  tooltip: widget.session.notice,
                  onPressed: () => NotificationService.show(
                    context,
                    widget.session.notice!,
                    kind: AppNotificationKind.warning,
                  ),
                  icon: const Icon(Icons.notifications_active_outlined),
                )
              else
                const Icon(Icons.notifications_none_outlined),
              const SizedBox(width: 8),
              ThemeSelector(manager: widget.themes),
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
          : Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12),
              child: Row(children: [
                const Icon(Icons.business_outlined, size: 18),
                const SizedBox(width: 8),
                Text(current?.name ?? 'No firm assigned'),
              ]),
            );
    }
    return DropdownButtonHideUnderline(
      child: DropdownButton<String>(
        value: current?.id,
        hint: const Text('Select firm'),
        icon: const Icon(Icons.swap_horiz),
        items: firms
            .map(
              (firm) => DropdownMenuItem(
                value: firm.id,
                child: Text(compact ? firm.code : firm.name),
              ),
            )
            .toList(),
        onChanged: (firmId) {
          if (firmId != null) _switchFirm(firmId);
        },
      ),
    );
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

  Widget _applicationStatusBar() => ApplicationStatusBar(
        currentUser: widget.session.attemptedUsername,
        currentFirm: widget.session.currentFirm?.name ?? 'No active firm',
        backend: ConnectionStateIndicator.checking,
        database: ConnectionStateIndicator.unknown,
        environment: Uri.tryParse(widget.session.baseUrl)?.host == 'localhost'
            ? 'Development'
            : 'Configured',
        version: '${widget.branding.companyName} ${widget.branding.version}',
      );

  Widget _navigationPanel(
    List<ModuleDefinition> modules,
    AppModule section,
  ) =>
      SafeArea(
        child: Column(children: [
          if (_sidebarCollapsed)
            IconButton(
              tooltip: 'Expand sidebar',
              onPressed: _toggleSidebar,
              icon: const Icon(Icons.account_balance, size: 30),
            )
          else
            ListTile(
              contentPadding: const EdgeInsets.symmetric(horizontal: 20),
              leading: const Icon(Icons.account_balance, size: 30),
              title: Text(
                widget.branding.appName,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
              trailing: IconButton(
                tooltip: 'Collapse sidebar',
                onPressed: _toggleSidebar,
                icon: const Icon(Icons.chevron_left),
              ),
            ),
          const Divider(height: 1),
          Expanded(
            child: ListView(
              padding: const EdgeInsets.symmetric(vertical: 8),
              children: modules
                  .map(
                    (module) => Tooltip(
                      message: module.label,
                      child: ListTile(
                        selected: module.id == section,
                        leading: Icon(module.icon),
                        title: _sidebarCollapsed ? null : Text(module.label),
                        onTap: () => _select(module.id),
                      ),
                    ),
                  )
                  .toList(),
            ),
          ),
          const Divider(height: 1),
          Padding(
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
        ]),
      );

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
            router: _router,
          ),
        AppModule.sales ||
        AppModule.purchases ||
        AppModule.inventory ||
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
    final String? requestedTab =
        widget.router.current.module == AppModule.administration.name
            ? widget.router.current.tab
            : null;
    final String tabId = visibleTabs.any((tab) => tab.id == requestedTab)
        ? requestedTab!
        : visibleTabs.first.id;
    final List<WorkspaceTab> tabs = visibleTabs
        .map(
          (tab) => WorkspaceTab(
            label: tab.available ? tab.label : '${tab.label} (Coming soon)',
            available: tab.available,
          ),
        )
        .toList();
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
      _ => const WorkspaceEmptyState(
          title: 'User Audit is coming soon',
          message: 'Audit records are not available from the current API.',
        ),
    };
    return ModuleWorkspaceFrame(
      title: module.label,
      description: module.description,
      breadcrumbs: const ['Workspace', 'Administration'],
      tabs: tabs,
      selectedTab: visibleTabs.indexWhere((tab) => tab.id == tabId),
      onTabChanged: (index) => widget.router.selectTab(visibleTabs[index].id),
      child: content,
    );
  }
}

class _MastersWorkspace extends StatefulWidget {
  const _MastersWorkspace({
    super.key,
    required this.api,
    required this.permissions,
    required this.router,
  });
  final ApiClient api;
  final PermissionService permissions;
  final WorkspaceRouter router;

  @override
  State<_MastersWorkspace> createState() => _MastersWorkspaceState();
}

class _MastersWorkspaceState extends State<_MastersWorkspace> {
  @override
  Widget build(BuildContext context) {
    final ModuleDefinition module = ModuleCatalog.byId(AppModule.masters);
    final List<ModuleTabDefinition> visibleTabs = module.tabs
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
    final Widget content = tabId == 'firms'
        ? ResourceManagementPage<Firm>(
            api: widget.api,
            definition: _firmDefinition(
              widget.api,
              widget.permissions,
              showFrame: false,
            ),
          )
        : tabId == 'customers'
            ? CustomerManagementPage(
                api: widget.api,
                permissions: widget.permissions,
                hasActiveFirm: widget.api.activeFirmId?.call() != null,
              )
            : WorkspaceEmptyState(
                title:
                    '${visibleTabs.firstWhere((tab) => tab.id == tabId).label} is coming soon',
                message:
                    'The current API does not provide ${visibleTabs.firstWhere((tab) => tab.id == tabId).label.toLowerCase()} operations.',
              );
    return ModuleWorkspaceFrame(
      title: tabId == 'customers' ? 'Customer Management' : 'Firm Management',
      description: tabId == 'customers'
          ? 'Manage firm-scoped customer masters, addresses, and contacts.'
          : 'Manage organization records and future firm configuration.',
      breadcrumbs: [
        'Workspace',
        'Masters',
        tabId == 'customers' ? 'Customer Management' : 'Firm Management',
      ],
      tabs: visibleTabs
          .map(
              (tab) => WorkspaceTab(label: tab.label, available: tab.available))
          .toList(),
      selectedTab: visibleTabs.indexWhere((tab) => tab.id == tabId),
      onTabChanged: (index) => widget.router.selectTab(visibleTabs[index].id),
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
        tabs: module.tabs
            .where(
              (tab) => permissions.canUseTab(
                tab.requiredPermissions.isEmpty
                    ? module.requiredPermissions
                    : tab.requiredPermissions,
                requiresAny: tab.requiredPermissions.isEmpty
                    ? module.requiresAnyPermission
                    : tab.requiresAnyPermission,
              ),
            )
            .map((tab) =>
                WorkspaceTab(label: tab.label, available: tab.available))
            .toList(),
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

ResourceDefinition<Firm> _firmDefinition(
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
        FieldSpec(key: 'is_active', label: 'Active', boolean: true),
        FieldSpec(key: 'notes', label: 'Notes', multiline: true),
      ],
      initialValues: (firm) => firm == null
          ? {'is_active': true}
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
              'is_active': firm.isActive,
              'notes': firm.notes,
            },
      payload: (values, _) => values,
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
          label: 'Email address',
          required: true,
          readOnlyWhenEditing: true,
        ),
        FieldSpec(key: 'full_name', label: 'Full name', required: true),
        FieldSpec(
          key: 'password',
          label: 'Initial password',
          requiredOnCreate: true,
          createOnly: true,
          section: 'Security',
        ),
        FieldSpec(
          key: 'role_ids',
          label: 'Roles',
          helperText: 'Select one or more roles.',
          optionsResource: 'roles',
          section: 'Organization',
        ),
        FieldSpec(
          key: 'firm_ids',
          label: 'Firms',
          helperText: 'Select one or more firms.',
          optionsResource: 'firms',
          section: 'Organization',
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
          key: 'force_password_change',
          label: 'Require password change',
          boolean: true,
          createOnly: true,
          section: 'Security',
        ),
        FieldSpec(
          key: 'is_active',
          label: 'Active',
          boolean: true,
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
          label: 'Clear login lock',
          boolean: true,
          editOnly: true,
          section: 'Security',
        ),
      ],
      initialValues: (user) => user == null
          ? {'is_active': true, 'force_password_change': true}
          : {
              'email': user.email,
              'full_name': user.fullName,
              'force_password_change': user.forcePasswordChange,
              'is_active': user.isActive,
              'expires_at': user.expiresAt,
              'unlock': false,
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
              'expires_at': values['expires_at'].toString().isEmpty
                  ? null
                  : values['expires_at'],
              'unlock': values['unlock'],
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
