import 'package:flutter/material.dart';

import '../core/api/api_client.dart';
import '../core/auth/session_controller.dart';
import '../models/entities.dart';
import 'dashboard_page.dart';
import 'resource_management_page.dart';

enum AppSection { dashboard, firms, users, roles, permissions }

extension AppSectionDetails on AppSection {
  String get label => switch (this) {
        AppSection.dashboard => 'Dashboard',
        AppSection.firms => 'Firm Management',
        AppSection.users => 'User Management',
        AppSection.roles => 'Role Management',
        AppSection.permissions => 'Permission Management',
      };

  IconData get icon => switch (this) {
        AppSection.dashboard => Icons.space_dashboard_outlined,
        AppSection.firms => Icons.business_outlined,
        AppSection.users => Icons.people_outline,
        AppSection.roles => Icons.badge_outlined,
        AppSection.permissions => Icons.key_outlined,
      };
}

class DesktopShell extends StatefulWidget {
  const DesktopShell({super.key, required this.session});
  final SessionController session;
  @override
  State<DesktopShell> createState() => _DesktopShellState();
}

class _DesktopShellState extends State<DesktopShell> {
  AppSection _section = AppSection.dashboard;

  void _select(AppSection section) {
    setState(() => _section = section);
    Navigator.of(context).maybePop();
  }

  @override
  Widget build(BuildContext context) => LayoutBuilder(
        builder: (context, constraints) {
          final bool wide = constraints.maxWidth >= 840;
          final Widget page = _page(widget.session.api);
          if (wide) {
            return Scaffold(
              body: Row(children: [
                NavigationRail(
                  selectedIndex: _section.index,
                  labelType: NavigationRailLabelType.all,
                  leading: const Padding(
                    padding: EdgeInsets.symmetric(vertical: 18),
                    child: Icon(Icons.account_balance, size: 30),
                  ),
                  destinations: _destinations,
                  onDestinationSelected: (index) => _select(AppSection.values[index]),
                  trailing: Expanded(
                    child: Align(
                      alignment: Alignment.bottomCenter,
                      child: IconButton(
                        tooltip: 'Sign out',
                        icon: const Icon(Icons.logout),
                        onPressed: widget.session.logout,
                      ),
                    ),
                  ),
                ),
                const VerticalDivider(width: 1),
                Expanded(child: page),
              ]),
            );
          }
          return Scaffold(
            appBar: AppBar(title: Text(_section.label)),
            drawer: Drawer(
              child: SafeArea(
                child: Column(children: [
                  const ListTile(
                    leading: Icon(Icons.account_balance),
                    title: Text('Agency Platform'),
                  ),
                  const Divider(),
                  ...AppSection.values.map(
                    (section) => ListTile(
                      selected: section == _section,
                      leading: Icon(section.icon),
                      title: Text(section.label),
                      onTap: () => _select(section),
                    ),
                  ),
                  const Spacer(),
                  ListTile(
                    leading: const Icon(Icons.logout),
                    title: const Text('Sign out'),
                    onTap: widget.session.logout,
                  ),
                ]),
              ),
            ),
            body: page,
          );
        },
      );

  List<NavigationRailDestination> get _destinations => AppSection.values
      .map((section) => NavigationRailDestination(
            icon: Icon(section.icon),
            label: Text(section.label.replaceFirst(' Management', '')),
          ))
      .toList();

  Widget _page(ApiClient api) => switch (_section) {
        AppSection.dashboard => DashboardPage(api: api),
        AppSection.firms => ResourceManagementPage<Firm>(
            api: api, definition: _firmDefinition(api)),
        AppSection.users => ResourceManagementPage<PlatformUser>(
            api: api, definition: _userDefinition(api)),
        AppSection.roles => ResourceManagementPage<Role>(
            api: api, definition: _roleDefinition(api)),
        AppSection.permissions => ResourceManagementPage<Permission>(
            api: api, definition: _permissionDefinition(api)),
      };
}

List<String> _ids(dynamic value) => value
    .toString()
    .split(',')
    .map((id) => id.trim())
    .where((id) => id.isNotEmpty)
    .toList();

ResourceDefinition<Firm> _firmDefinition(ApiClient api) => ResourceDefinition(
      title: 'Firms',
      resource: 'firms',
      headers: const ['Code', 'Name', 'Contact', 'Currency', 'Country', 'Status'],
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
      fields: const [
        FieldSpec(key: 'code', label: 'Firm code', required: true),
        FieldSpec(key: 'name', label: 'Display name', required: true),
        FieldSpec(key: 'gst_number', label: 'GST number'),
        FieldSpec(key: 'pan_number', label: 'PAN number'),
        FieldSpec(key: 'address_line1', label: 'Address line 1'),
        FieldSpec(key: 'address_line2', label: 'Address line 2'),
        FieldSpec(key: 'city', label: 'City'),
        FieldSpec(key: 'state', label: 'State / province'),
        FieldSpec(key: 'postal_code', label: 'Postal code'),
        FieldSpec(key: 'country', label: 'Country', required: true),
        FieldSpec(key: 'contact_name', label: 'Contact name'),
        FieldSpec(key: 'contact_email', label: 'Contact email'),
        FieldSpec(key: 'contact_phone', label: 'Contact phone'),
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

ResourceDefinition<PlatformUser> _userDefinition(ApiClient api) =>
    ResourceDefinition(
      title: 'Users',
      resource: 'users',
      headers: const ['Email', 'Name', 'Assignments', 'Status'],
      cells: (user) => [
        user.email,
        user.fullName,
        'Manage in editor',
        user.isActive ? 'Active' : 'Inactive',
      ],
      id: (user) => user.id,
      load: api.users,
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
        ),
        FieldSpec(
          key: 'role_ids',
          label: 'Roles',
          helperText: 'Select one or more roles.',
          optionsResource: 'roles',
        ),
        FieldSpec(
          key: 'firm_ids',
          label: 'Firms',
          helperText: 'Select one or more firms.',
          optionsResource: 'firms',
        ),
        FieldSpec(
          key: 'primary_firm_id',
          label: 'Primary firm',
          helperText: 'Optional; must also be selected above.',
          optionsResource: 'firms',
          singleSelection: true,
        ),
        FieldSpec(
          key: 'force_password_change',
          label: 'Require password change',
          boolean: true,
          createOnly: true,
        ),
        FieldSpec(key: 'is_active', label: 'Active', boolean: true),
        FieldSpec(
          key: 'expires_at',
          label: 'Expires at',
          helperText: 'Optional ISO timestamp.',
        ),
        FieldSpec(
          key: 'unlock',
          label: 'Clear login lock',
          boolean: true,
          editOnly: true,
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

ResourceDefinition<Role> _roleDefinition(ApiClient api) => ResourceDefinition(
      title: 'Roles',
      resource: 'roles',
      headers: const ['Code', 'Name', 'Assignments', 'Status'],
      cells: (role) => [
        role.code,
        role.name,
        'Manage in editor',
        role.isActive ? 'Active' : 'Inactive',
      ],
      id: (role) => role.id,
      load: api.roles,
      canEdit: (role) => !role.isSystem,
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

ResourceDefinition<Permission> _permissionDefinition(ApiClient api) =>
    ResourceDefinition(
      title: 'Permissions',
      resource: 'permissions',
      headers: const ['Code', 'Name', 'Status'],
      cells: (permission) => [
        permission.code,
        permission.name,
        permission.isActive ? 'Active' : 'Inactive',
      ],
      id: (permission) => permission.id,
      load: api.permissions,
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
