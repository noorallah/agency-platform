import 'package:flutter/material.dart';

enum AppModule {
  dashboard,
  administration,
  masters,
  sales,
  purchases,
  inventory,
  accounting,
  reports,
  licensing,
  settings,
}

class ModuleTabDefinition {
  const ModuleTabDefinition({
    required this.id,
    required this.label,
    this.available = true,
    this.requiredPermissions = const [],
    this.requiresAnyPermission = false,
  });

  final String id;
  final String label;
  final bool available;
  final List<String> requiredPermissions;
  final bool requiresAnyPermission;
}

class ModuleDefinition {
  const ModuleDefinition({
    required this.id,
    required this.label,
    required this.icon,
    required this.description,
    this.tabs = const [],
    this.requiredPermissions = const [],
    this.requiresAnyPermission = false,
  });

  final AppModule id;
  final String label;
  final IconData icon;
  final String description;
  final List<ModuleTabDefinition> tabs;
  final List<String> requiredPermissions;
  final bool requiresAnyPermission;
}

abstract final class ModuleCatalog {
  static const List<ModuleDefinition> modules = [
    ModuleDefinition(
      id: AppModule.dashboard,
      label: 'Dashboard',
      icon: Icons.space_dashboard_outlined,
      description: 'Platform administration at a glance.',
      requiredPermissions: [
        'FIRM_VIEW',
        'USER_VIEW',
        'ROLE_VIEW',
        'PERMISSION_VIEW'
      ],
      requiresAnyPermission: true,
    ),
    ModuleDefinition(
      id: AppModule.administration,
      label: 'Administration',
      icon: Icons.admin_panel_settings_outlined,
      description: 'Manage platform access and user assignments.',
      requiredPermissions: ['USER_VIEW', 'ROLE_VIEW', 'PERMISSION_VIEW'],
      requiresAnyPermission: true,
      tabs: [
        ModuleTabDefinition(
            id: 'users', label: 'Users', requiredPermissions: ['USER_VIEW']),
        ModuleTabDefinition(
            id: 'roles', label: 'Roles', requiredPermissions: ['ROLE_VIEW']),
        ModuleTabDefinition(
          id: 'permissions',
          label: 'Permissions',
          requiredPermissions: ['PERMISSION_VIEW'],
        ),
        ModuleTabDefinition(
          id: 'user-firms',
          label: 'User-Firm Assignments',
          requiredPermissions: ['USER_VIEW', 'USER_UPDATE', 'FIRM_VIEW'],
        ),
        ModuleTabDefinition(
          id: 'user-audit',
          label: 'User Audit',
          available: false,
        ),
      ],
    ),
    ModuleDefinition(
      id: AppModule.masters,
      label: 'Masters',
      icon: Icons.business_center_outlined,
      description: 'Manage organization and master-data workspaces.',
      requiredPermissions: ['FIRM_VIEW'],
      tabs: [
        ModuleTabDefinition(
            id: 'firms', label: 'Firms', requiredPermissions: ['FIRM_VIEW']),
        ModuleTabDefinition(
          id: 'financial-years',
          label: 'Financial Years',
          available: false,
        ),
        ModuleTabDefinition(
          id: 'firm-settings',
          label: 'Firm Settings',
          available: false,
        ),
        ModuleTabDefinition(
          id: 'branches-departments',
          label: 'Branches / Departments',
          available: false,
        ),
      ],
    ),
    ModuleDefinition(
      id: AppModule.sales,
      label: 'Sales',
      icon: Icons.point_of_sale_outlined,
      description: 'Sales operations workspace.',
      requiredPermissions: ['SALES_VIEW'],
      tabs: [
        ModuleTabDefinition(
            id: 'quotations', label: 'Quotations', available: false),
        ModuleTabDefinition(
            id: 'sales-orders', label: 'Sales Orders', available: false),
        ModuleTabDefinition(
            id: 'delivery-notes', label: 'Delivery Notes', available: false),
        ModuleTabDefinition(
            id: 'sales-invoices', label: 'Sales Invoices', available: false),
        ModuleTabDefinition(id: 'returns', label: 'Returns', available: false),
      ],
    ),
    ModuleDefinition(
      id: AppModule.purchases,
      label: 'Purchases',
      icon: Icons.shopping_cart_outlined,
      description: 'Purchasing operations workspace.',
      requiredPermissions: ['PURCHASE_VIEW'],
      tabs: [
        ModuleTabDefinition(
            id: 'purchase-requests',
            label: 'Purchase Requests',
            available: false),
        ModuleTabDefinition(
            id: 'purchase-orders', label: 'Purchase Orders', available: false),
        ModuleTabDefinition(
            id: 'goods-receipt', label: 'Goods Receipt', available: false),
        ModuleTabDefinition(
            id: 'purchase-bills', label: 'Purchase Bills', available: false),
        ModuleTabDefinition(id: 'returns', label: 'Returns', available: false),
      ],
    ),
    ModuleDefinition(
      id: AppModule.inventory,
      label: 'Inventory',
      icon: Icons.inventory_2_outlined,
      description: 'Inventory operations workspace.',
      requiredPermissions: ['STOCK_VIEW'],
      tabs: [
        ModuleTabDefinition(id: 'stock', label: 'Stock', available: false),
        ModuleTabDefinition(
            id: 'warehouses', label: 'Warehouses', available: false),
        ModuleTabDefinition(
            id: 'stock-transfer', label: 'Stock Transfer', available: false),
        ModuleTabDefinition(
            id: 'stock-adjustment',
            label: 'Stock Adjustment',
            available: false),
        ModuleTabDefinition(
            id: 'stock-audit', label: 'Stock Audit', available: false),
      ],
    ),
    ModuleDefinition(
      id: AppModule.accounting,
      label: 'Accounting',
      icon: Icons.account_balance_outlined,
      description: 'Accounting operations workspace.',
      requiredPermissions: ['ACCOUNT_VIEW'],
      tabs: [
        ModuleTabDefinition(
            id: 'chart-of-accounts',
            label: 'Chart of Accounts',
            available: false),
        ModuleTabDefinition(
            id: 'journal-entries', label: 'Journal Entries', available: false),
        ModuleTabDefinition(
            id: 'receipts', label: 'Receipts', available: false),
        ModuleTabDefinition(
            id: 'payments', label: 'Payments', available: false),
        ModuleTabDefinition(id: 'ledgers', label: 'Ledgers', available: false),
        ModuleTabDefinition(
            id: 'trial-balance', label: 'Trial Balance', available: false),
        ModuleTabDefinition(
            id: 'profit-loss', label: 'Profit & Loss', available: false),
        ModuleTabDefinition(
            id: 'balance-sheet', label: 'Balance Sheet', available: false),
      ],
    ),
    ModuleDefinition(
      id: AppModule.reports,
      label: 'Reports',
      icon: Icons.bar_chart_outlined,
      description: 'Reporting workspace.',
      requiredPermissions: ['REPORT_VIEW'],
      tabs: [
        ModuleTabDefinition(
            id: 'dashboard', label: 'Dashboard', available: false),
        ModuleTabDefinition(
            id: 'operational', label: 'Operational Reports', available: false),
        ModuleTabDefinition(
            id: 'financial', label: 'Financial Reports', available: false),
        ModuleTabDefinition(id: 'gst', label: 'GST Reports', available: false),
        ModuleTabDefinition(
            id: 'audit', label: 'Audit Reports', available: false),
      ],
    ),
    ModuleDefinition(
      id: AppModule.licensing,
      label: 'Licensing',
      icon: Icons.verified_outlined,
      description: 'Licensing workspace.',
      requiredPermissions: ['LICENSE_MANAGE'],
      tabs: [
        ModuleTabDefinition(
            id: 'licenses', label: 'Licenses', available: false),
        ModuleTabDefinition(
            id: 'activations', label: 'Activations', available: false),
        ModuleTabDefinition(
            id: 'machines', label: 'Machine Registrations', available: false),
        ModuleTabDefinition(
            id: 'history', label: 'License History', available: false),
      ],
    ),
    ModuleDefinition(
      id: AppModule.settings,
      label: 'Settings',
      icon: Icons.settings_outlined,
      description: 'Application settings workspace.',
      requiredPermissions: ['SETTINGS_VIEW'],
      tabs: [
        ModuleTabDefinition(
            id: 'audit-logs', label: 'Audit Logs', available: false),
        ModuleTabDefinition(
            id: 'background-jobs', label: 'Background Jobs', available: false),
        ModuleTabDefinition(
            id: 'system-settings', label: 'System Settings', available: false),
        ModuleTabDefinition(
            id: 'api-monitoring', label: 'API Monitoring', available: false),
      ],
    ),
  ];

  static ModuleDefinition byId(AppModule id) =>
      modules.firstWhere((module) => module.id == id);
}
