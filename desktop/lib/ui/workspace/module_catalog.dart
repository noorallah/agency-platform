import 'package:flutter/material.dart';

import 'workspace_templates.dart';

enum AppModule {
  dashboard,
  administration,
  masters,
  sales,
  quotations,
  salesOrders,
  deliveryNotes,
  salesInvoices,
  salesReturns,
  purchases,
  purchaseInvoices,
  purchaseReturns,
  goodsReceipts,
  inventory,
  accounting,
  reports,
  licensing,
  settings,
}

enum WorkspaceTemplateType {
  dashboard,
  masterManagement,
  configuration,
  transaction,
  report,
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
    required this.workspaceTemplate,
    this.tabs = const [],
    this.requiredPermissions = const [],
    this.requiresAnyPermission = false,
  });

  final AppModule id;
  final String label;
  final IconData icon;
  final String description;
  final WorkspaceTemplateType workspaceTemplate;
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
      workspaceTemplate: WorkspaceTemplateType.dashboard,
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
      workspaceTemplate: WorkspaceTemplateType.configuration,
      requiredPermissions: [
        'USER_VIEW',
        'ROLE_VIEW',
        'PERMISSION_VIEW',
        'TAX_VIEW',
        'TAX_RULE_VIEW',
        'TAX_SIMULATE',
        'UOM_VIEW',
        'UOM_MANAGE',
        'PACKAGING_MANAGE',
        'CONVERSION_RULE_MANAGE',
      ],
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
          id: 'numbering-series',
          label: 'Numbering Series',
          requiredPermissions: ['SETTINGS_VIEW'],
        ),
        ModuleTabDefinition(
          id: 'business-profiles',
          label: 'Business Profiles',
          requiredPermissions: ['PLATFORM_VIEW'],
        ),
        ModuleTabDefinition(
          id: 'feature-management',
          label: 'Feature Management',
          requiredPermissions: ['PLATFORM_VIEW'],
        ),
        ModuleTabDefinition(
          id: 'module-configuration',
          label: 'Module Configuration',
          requiredPermissions: ['PLATFORM_VIEW'],
        ),
        ModuleTabDefinition(
          id: 'attribute-definitions',
          label: 'Attribute Definitions',
          requiredPermissions: ['PLATFORM_VIEW'],
        ),
        ModuleTabDefinition(
          id: 'profile-assignment',
          label: 'Profile Assignment',
          requiredPermissions: ['FIRM_VIEW', 'PLATFORM_VIEW'],
        ),
        ModuleTabDefinition(
          id: 'tax-configuration',
          label: 'Tax Configuration',
          requiredPermissions: ['TAX_VIEW'],
        ),
        ModuleTabDefinition(
          id: 'tax-rules-page',
          label: 'Tax Rules',
          requiredPermissions: ['TAX_RULE_VIEW'],
        ),
        ModuleTabDefinition(
          id: 'tax-rule-simulator',
          label: 'Rule Simulator',
          requiredPermissions: ['TAX_SIMULATE'],
        ),
        ModuleTabDefinition(
          id: 'tax-execution-log',
          label: 'Execution Log',
          requiredPermissions: ['TAX_RULE_VIEW'],
        ),
        ModuleTabDefinition(
          id: 'tax-settings',
          label: 'Settings',
          requiredPermissions: ['TAX_MANAGE_SETTINGS'],
        ),
        ModuleTabDefinition(
          id: 'uoms',
          label: 'Units of Measure',
          requiredPermissions: ['UOM_VIEW'],
        ),
        ModuleTabDefinition(
          id: 'uom-groups',
          label: 'UOM Groups',
          requiredPermissions: ['UOM_VIEW'],
        ),
        ModuleTabDefinition(
          id: 'packaging-types',
          label: 'Packaging Types',
          requiredPermissions: ['PACKAGING_MANAGE'],
        ),
        ModuleTabDefinition(
          id: 'conversion-rules',
          label: 'Conversion Rules',
          requiredPermissions: ['CONVERSION_RULE_MANAGE'],
        ),
        ModuleTabDefinition(
          id: 'industry-templates',
          label: 'Industry Templates',
          requiredPermissions: ['UOM_VIEW'],
        ),
      ],
    ),
    ModuleDefinition(
      id: AppModule.masters,
      label: 'Masters',
      icon: Icons.business_center_outlined,
      description: 'Manage organization and master-data workspaces.',
      workspaceTemplate: WorkspaceTemplateType.masterManagement,
      requiredPermissions: [
        'FIRM_VIEW',
        'CUSTOMER_VIEW',
        'PRODUCT_VIEW',
        'VENDOR_VIEW',
        'BRANCH_VIEW',
        'WAREHOUSE_VIEW',
      ],
      requiresAnyPermission: true,
      tabs: [
        ModuleTabDefinition(
            id: 'firms', label: 'Firms', requiredPermissions: ['FIRM_VIEW']),
        ModuleTabDefinition(
          id: 'customers',
          label: 'Customers',
          requiredPermissions: ['CUSTOMER_VIEW'],
        ),
        ModuleTabDefinition(
          id: 'products',
          label: 'Products',
          requiredPermissions: ['PRODUCT_VIEW'],
        ),
        ModuleTabDefinition(
          id: 'vendors',
          label: 'Vendors',
          requiredPermissions: ['VENDOR_VIEW'],
        ),
        ModuleTabDefinition(
          id: 'branches',
          label: 'Branches',
          requiredPermissions: ['BRANCH_VIEW'],
        ),
        ModuleTabDefinition(
          id: 'warehouses',
          label: 'Warehouses',
          requiredPermissions: ['WAREHOUSE_VIEW'],
        ),
        ModuleTabDefinition(
          id: 'storage-areas',
          label: 'Storage Areas',
          requiredPermissions: ['STORAGE_AREA_MANAGE'],
        ),
        ModuleTabDefinition(
          id: 'warehouse-types',
          label: 'Warehouse Types',
          requiredPermissions: ['WAREHOUSE_VIEW'],
        ),
        ModuleTabDefinition(
          id: 'branch-types',
          label: 'Branch Types',
          requiredPermissions: ['BRANCH_VIEW'],
        ),
        ModuleTabDefinition(
          id: 'branch-warehouse-settings',
          label: 'Settings',
          requiredPermissions: ['BRANCH_VIEW', 'WAREHOUSE_VIEW'],
          requiresAnyPermission: true,
        ),
        ModuleTabDefinition(id: 'financial-years', label: 'Financial Years'),
        ModuleTabDefinition(
          id: 'firm-settings',
          label: 'Firm Settings',
          requiredPermissions: ['FIRM_VIEW'],
        ),
      ],
    ),
    ModuleDefinition(
      id: AppModule.sales,
      label: 'Sales',
      icon: Icons.point_of_sale_outlined,
      description: 'Sales operations workspace.',
      workspaceTemplate: WorkspaceTemplateType.transaction,
      requiredPermissions: ['SALES_VIEW', 'TERRITORY_VIEW'],
      requiresAnyPermission: true,
      tabs: [
        ModuleTabDefinition(
          id: 'territories',
          label: 'Geography',
          requiredPermissions: ['TERRITORY_VIEW'],
        ),
        ModuleTabDefinition(
          id: 'route-types',
          label: 'Route Types',
          requiredPermissions: ['TERRITORY_VIEW'],
        ),
        ModuleTabDefinition(
          id: 'beat-plans',
          label: 'Beat Plans',
          requiredPermissions: ['TERRITORY_VIEW'],
        ),
        ModuleTabDefinition(
          id: 'call-lists',
          label: 'Call Lists',
          requiredPermissions: ['TERRITORY_VIEW'],
        ),
        ModuleTabDefinition(
          id: 'coverage',
          label: 'Coverage',
          requiredPermissions: ['TERRITORY_VIEW'],
        ),
        ModuleTabDefinition(
          id: 'route-builder',
          label: 'Route Builder',
          requiredPermissions: ['TERRITORY_VIEW'],
        ),
        ModuleTabDefinition(
          id: 'geography-masters',
          label: 'Places',
          requiredPermissions: ['TERRITORY_VIEW'],
        ),
      ],
    ),
    ModuleDefinition(
      id: AppModule.quotations,
      label: 'Quotations',
      icon: Icons.request_quote_outlined,
      description: 'Prices offered before anything is sold.',
      workspaceTemplate: WorkspaceTemplateType.transaction,
      requiredPermissions: [
        'SALES_VIEW',
        'SALES_QUOTATION_CREATE',
        'SALES_APPROVE',
        'SALES_CANCEL',
      ],
      requiresAnyPermission: true,
    ),
    ModuleDefinition(
      id: AppModule.salesOrders,
      label: 'Sales Orders',
      icon: Icons.shopping_bag_outlined,
      description: 'Customer sales order workspace.',
      workspaceTemplate: WorkspaceTemplateType.transaction,
      requiredPermissions: [
        'SALES_VIEW',
        'SALES_CREATE',
        'SALES_UPDATE',
        'SALES_IMPORT',
        'SALES_EXPORT',
        'SALES_APPROVE',
        'SALES_CANCEL',
      ],
      requiresAnyPermission: true,
    ),
    ModuleDefinition(
      id: AppModule.deliveryNotes,
      label: 'Delivery Notes',
      icon: Icons.local_shipping_outlined,
      description: 'Goods dispatch and inventory deduction workspace.',
      workspaceTemplate: WorkspaceTemplateType.transaction,
      requiredPermissions: [
        'SALES_VIEW',
        'SALES_CREATE',
        'SALES_UPDATE',
        'SALES_IMPORT',
        'SALES_EXPORT',
        'SALES_APPROVE',
        'SALES_CANCEL',
      ],
      requiresAnyPermission: true,
      tabs: [
        ModuleTabDefinition(
          id: 'delivery-notes',
          label: 'Delivery Notes',
          requiredPermissions: ['SALES_VIEW'],
        ),
        ModuleTabDefinition(
          id: 'pending-deliveries',
          label: 'Pending Deliveries',
          requiredPermissions: ['SALES_VIEW'],
        ),
        ModuleTabDefinition(
          id: 'partial-deliveries',
          label: 'Partial Deliveries',
          requiredPermissions: ['SALES_VIEW'],
        ),
        ModuleTabDefinition(
          id: 'delivered-by-route',
          label: 'Delivered by Route',
          requiredPermissions: ['SALES_VIEW'],
        ),
        ModuleTabDefinition(
          id: 'delivered-by-salesman',
          label: 'Delivered by Salesman',
          requiredPermissions: ['SALES_VIEW'],
        ),
        ModuleTabDefinition(
          id: 'delivered-by-warehouse',
          label: 'Delivered by Warehouse',
          requiredPermissions: ['SALES_VIEW'],
        ),
        ModuleTabDefinition(
          id: 'delivery-history',
          label: 'History',
          requiredPermissions: ['SALES_VIEW'],
        ),
      ],
    ),
    ModuleDefinition(
      id: AppModule.salesInvoices,
      label: 'Sales Invoices',
      icon: Icons.receipt_long_outlined,
      description: 'Customer invoice billing and accounting workspace.',
      workspaceTemplate: WorkspaceTemplateType.transaction,
      requiredPermissions: [
        'SALES_VIEW',
        'SALES_CREATE',
        'SALES_UPDATE',
        'SALES_IMPORT',
        'SALES_EXPORT',
        'SALES_APPROVE',
        'SALES_CANCEL',
      ],
      requiresAnyPermission: true,
      tabs: [
        ModuleTabDefinition(
          id: 'sales-invoices',
          label: 'Sales Invoices',
          requiredPermissions: ['SALES_VIEW'],
        ),
        ModuleTabDefinition(
          id: 'pending-invoices',
          label: 'Pending Invoices',
          requiredPermissions: ['SALES_VIEW'],
        ),
        ModuleTabDefinition(
          id: 'overdue-invoices',
          label: 'Overdue Invoices',
          requiredPermissions: ['SALES_VIEW'],
        ),
        ModuleTabDefinition(
          id: 'invoice-register',
          label: 'Invoice Register',
          requiredPermissions: ['SALES_VIEW'],
        ),
        ModuleTabDefinition(
          id: 'invoice-reconciliation',
          label: 'Invoice vs Delivery',
          requiredPermissions: ['SALES_VIEW'],
        ),
        ModuleTabDefinition(
          id: 'customer-outstanding',
          label: 'Customer Outstanding',
          requiredPermissions: ['SALES_VIEW'],
        ),
        ModuleTabDefinition(
          id: 'invoice-history',
          label: 'History',
          requiredPermissions: ['SALES_VIEW'],
        ),
      ],
    ),
    ModuleDefinition(
      id: AppModule.salesReturns,
      label: 'Sales Returns',
      icon: Icons.keyboard_return_outlined,
      description: 'Goods coming back from a customer.',
      workspaceTemplate: WorkspaceTemplateType.transaction,
      requiredPermissions: [
        'SALES_VIEW',
        'SALES_RETURN',
        'SALES_UPDATE',
        'SALES_APPROVE',
        'SALES_CANCEL',
      ],
      requiresAnyPermission: true,
    ),
    ModuleDefinition(
      id: AppModule.purchases,
      label: 'Purchases',
      icon: Icons.shopping_cart_outlined,
      description: 'Purchasing operations workspace.',
      workspaceTemplate: WorkspaceTemplateType.transaction,
      requiredPermissions: [
        'PURCHASE_VIEW',
        'PURCHASE_CREATE',
        'PURCHASE_UPDATE',
        'PURCHASE_DELETE',
        'PURCHASE_RESTORE',
        'PURCHASE_IMPORT',
        'PURCHASE_EXPORT',
        'PURCHASE_APPROVE',
        'PURCHASE_CANCEL',
      ],
      requiresAnyPermission: true,
      tabs: [
        ModuleTabDefinition(
          id: 'purchase-dashboard',
          label: 'Dashboard',
          requiredPermissions: ['PURCHASE_VIEW'],
        ),
        ModuleTabDefinition(
          id: 'purchase-orders',
          label: 'Purchase Orders',
          requiredPermissions: ['PURCHASE_VIEW'],
        ),
        ModuleTabDefinition(
          id: 'purchase-rfqs',
          label: 'RFQs',
          requiredPermissions: ['PURCHASE_VIEW'],
        ),
        ModuleTabDefinition(
          id: 'vendor-quotations',
          label: 'Vendor Quotations',
          requiredPermissions: ['PURCHASE_VIEW'],
        ),
        // `draft-orders`, `open-orders`, `cancelled-orders`, `closed-orders`
        // and `purchase-history` used to be tabs of their own. Each opened the
        // same workspace with one filter preset, so five sidebar entries led to
        // one screen. They are now the status bar inside Purchase Orders --
        // see `PurchaseOrderView`. `purchaseTabAliases` keeps their ids
        // resolvable so a stored workspace still opens where it left off.
        ModuleTabDefinition(
          id: 'purchase-analytics',
          label: 'Analytics',
          requiredPermissions: ['PURCHASE_VIEW'],
        ),
        ModuleTabDefinition(
          id: 'purchase-settings',
          label: 'Settings',
          requiredPermissions: ['PURCHASE_VIEW'],
        ),
      ],
    ),
    ModuleDefinition(
      id: AppModule.purchaseInvoices,
      label: 'Purchase Invoices',
      icon: Icons.request_quote_outlined,
      description: 'Supplier invoice workspace.',
      workspaceTemplate: WorkspaceTemplateType.transaction,
      requiredPermissions: [
        'PURCHASE_VIEW',
        'PURCHASE_CREATE',
        'PURCHASE_UPDATE',
        'PURCHASE_IMPORT',
        'PURCHASE_EXPORT',
        'PURCHASE_APPROVE',
        'PURCHASE_CANCEL',
      ],
      requiresAnyPermission: true,
    ),
    ModuleDefinition(
      id: AppModule.purchaseReturns,
      label: 'Purchase Returns',
      icon: Icons.assignment_return_outlined,
      description: 'Supplier return workspace.',
      workspaceTemplate: WorkspaceTemplateType.transaction,
      requiredPermissions: [
        'PURCHASE_VIEW',
        'PURCHASE_CREATE',
        'PURCHASE_UPDATE',
        'PURCHASE_IMPORT',
        'PURCHASE_EXPORT',
        'PURCHASE_APPROVE',
        'PURCHASE_CANCEL',
      ],
      requiresAnyPermission: true,
    ),
    ModuleDefinition(
      id: AppModule.goodsReceipts,
      label: 'Goods Receipts',
      icon: Icons.receipt_long_outlined,
      description: 'Goods receipt note workspace.',
      workspaceTemplate: WorkspaceTemplateType.transaction,
      requiredPermissions: [
        'PURCHASE_VIEW',
        'PURCHASE_CREATE',
        'PURCHASE_UPDATE',
        'PURCHASE_IMPORT',
        'PURCHASE_EXPORT',
        'PURCHASE_APPROVE',
        'PURCHASE_CANCEL',
      ],
      requiresAnyPermission: true,
      tabs: [
        ModuleTabDefinition(
          id: 'receipts',
          label: 'Receipts',
          requiredPermissions: ['PURCHASE_VIEW'],
        ),
        ModuleTabDefinition(
          id: 'pending-receipts',
          label: 'Pending Receipts',
          requiredPermissions: ['PURCHASE_VIEW'],
        ),
        ModuleTabDefinition(
          id: 'partial-receipts',
          label: 'Partial Receipts',
          requiredPermissions: ['PURCHASE_VIEW'],
        ),
        ModuleTabDefinition(
          id: 'completed-receipts',
          label: 'Completed Receipts',
          requiredPermissions: ['PURCHASE_VIEW'],
        ),
        ModuleTabDefinition(
          id: 'rejected-items',
          label: 'Rejected Items',
          requiredPermissions: ['PURCHASE_VIEW'],
        ),
        ModuleTabDefinition(
          id: 'damaged-items',
          label: 'Damaged Items',
          requiredPermissions: ['PURCHASE_VIEW'],
        ),
        ModuleTabDefinition(
          id: 'grn-history',
          label: 'History',
          requiredPermissions: ['PURCHASE_VIEW'],
        ),
        ModuleTabDefinition(
          id: 'grn-settings',
          label: 'Settings',
          requiredPermissions: ['PURCHASE_VIEW'],
        ),
      ],
    ),
    ModuleDefinition(
      id: AppModule.inventory,
      label: 'Inventory',
      icon: Icons.inventory_2_outlined,
      description: 'Inventory foundation workspace.',
      workspaceTemplate: WorkspaceTemplateType.transaction,
      requiredPermissions: [
        'INVENTORY_VIEW',
        'OPENING_STOCK_CREATE',
        'OPENING_STOCK_UPDATE',
        'INVENTORY_LEDGER_VIEW',
        'INVENTORY_EXPORT',
        'INVENTORY_IMPORT',
        'INVENTORY_TRANSACTION_VIEW',
        'INVENTORY_ADJUST',
        'BATCH_VIEW',
        'SERIAL_VIEW',
      ],
      requiresAnyPermission: true,
      tabs: [
        ModuleTabDefinition(
          id: 'inventory',
          label: 'Inventory',
          requiredPermissions: ['INVENTORY_VIEW'],
        ),
        ModuleTabDefinition(
          id: 'transactions',
          label: 'Transactions',
          requiredPermissions: ['INVENTORY_TRANSACTION_VIEW'],
        ),
        ModuleTabDefinition(
          id: 'stock-ledger',
          label: 'Stock Ledger',
          requiredPermissions: ['INVENTORY_LEDGER_VIEW'],
        ),
        ModuleTabDefinition(
          id: 'opening-stock',
          label: 'Opening Stock',
          requiredPermissions: ['INVENTORY_VIEW'],
        ),
        ModuleTabDefinition(
          id: 'physical-counts',
          label: 'Physical Count',
          requiredPermissions: ['INVENTORY_VIEW'],
        ),
        ModuleTabDefinition(
          id: 'stock-summary',
          label: 'Stock Summary',
          requiredPermissions: ['INVENTORY_VIEW'],
        ),
        ModuleTabDefinition(
          id: 'stock-search',
          label: 'Stock Search',
          requiredPermissions: ['INVENTORY_VIEW'],
        ),
        ModuleTabDefinition(
          id: 'inventory-import',
          label: 'Import',
          requiredPermissions: ['INVENTORY_IMPORT'],
        ),
        ModuleTabDefinition(
          id: 'inventory-export',
          label: 'Export',
          requiredPermissions: ['INVENTORY_EXPORT'],
        ),
        ModuleTabDefinition(
          id: 'inventory-settings',
          label: 'Settings',
          requiredPermissions: ['INVENTORY_VIEW'],
        ),
        ModuleTabDefinition(
          id: 'batches',
          label: 'Batches',
          requiredPermissions: ['BATCH_VIEW'],
        ),
        ModuleTabDefinition(
          id: 'lots',
          label: 'Lots',
          requiredPermissions: ['BATCH_VIEW'],
        ),
        ModuleTabDefinition(
          id: 'serials',
          label: 'Serial Numbers',
          requiredPermissions: ['SERIAL_VIEW'],
        ),
        ModuleTabDefinition(
          id: 'expiry-monitor',
          label: 'Expiry Monitor',
          requiredPermissions: ['BATCH_VIEW'],
        ),
      ],
    ),
    ModuleDefinition(
      id: AppModule.accounting,
      label: 'Finance',
      icon: Icons.account_balance_outlined,
      description: 'Accounting operations workspace.',
      workspaceTemplate: WorkspaceTemplateType.configuration,
      requiredPermissions: ['ACCOUNT_VIEW'],
      tabs: [
        ModuleTabDefinition(
            id: 'chart-of-accounts', label: 'Chart of Accounts'),
        ModuleTabDefinition(id: 'journal-entries', label: 'Journal Entries'),
        ModuleTabDefinition(id: 'receipts', label: 'Receipts'),
        ModuleTabDefinition(id: 'payments', label: 'Payments'),
        ModuleTabDefinition(id: 'refunds', label: 'Refunds'),
        ModuleTabDefinition(id: 'ledgers', label: 'Ledgers'),
        ModuleTabDefinition(id: 'trial-balance', label: 'Trial Balance'),
        ModuleTabDefinition(id: 'profit-loss', label: 'Profit & Loss'),
        ModuleTabDefinition(id: 'balance-sheet', label: 'Balance Sheet'),
      ],
    ),
    ModuleDefinition(
      id: AppModule.reports,
      label: 'Reports',
      icon: Icons.bar_chart_outlined,
      description: 'Reporting workspace.',
      workspaceTemplate: WorkspaceTemplateType.report,
      requiredPermissions: ['REPORT_VIEW'],
      tabs: [
        ModuleTabDefinition(id: 'operational', label: 'Operational Reports'),
        ModuleTabDefinition(id: 'financial', label: 'Financial Reports'),
      ],
    ),
    ModuleDefinition(
      id: AppModule.licensing,
      label: 'Licensing',
      icon: Icons.verified_outlined,
      description: 'Licensing workspace.',
      workspaceTemplate: WorkspaceTemplateType.configuration,
      requiredPermissions: ['LICENSE_MANAGE'],
      tabs: [],
    ),
    ModuleDefinition(
      id: AppModule.settings,
      label: 'Settings',
      icon: Icons.settings_outlined,
      description: 'Application settings workspace.',
      workspaceTemplate: WorkspaceTemplateType.settings,
      requiredPermissions: ['SETTINGS_VIEW'],
      tabs: [
        ModuleTabDefinition(id: 'audit-logs', label: 'Audit Logs'),
      ],
    ),
  ];

  /// The `business_modules` code that decides whether [module] is offered.
  ///
  /// Null means the module is never gated this way.
  ///
  /// **A document is gated by the process that owns it.** `business_modules`
  /// holds process modules -- DASHBOARD, ADMINISTRATION, SETTINGS, MASTERS,
  /// PRODUCTS, PURCHASES, SALES, INVENTORY, REPORTS, ACCOUNTING, plus a few
  /// industry ones -- and has never held `SALES_ORDERS` or `GOODS_RECEIPTS`.
  /// Naming a code the catalogue does not contain hid that module in **every
  /// firm**, because a code that is absent can never be in the active set.
  static String? businessModuleCode(AppModule module) => switch (module) {
        AppModule.dashboard => 'DASHBOARD',
        AppModule.administration => 'ADMINISTRATION',
        AppModule.masters => 'MASTERS',
        // A document is gated by the process that owns it, not by a code of
        // its own. `business_modules` holds process modules -- DASHBOARD,
        // MASTERS, PRODUCTS, PURCHASES, SALES, INVENTORY, REPORTS,
        // ACCOUNTING, plus a few industry ones -- and has never held
        // `SALES_ORDERS` or `GOODS_RECEIPTS`. Naming a code the catalogue does
        // not contain hid the module in **every firm**: a firm could raise a
        // purchase order and then had nowhere to receive it, and the whole
        // sales document chain was unreachable the same way.
        AppModule.sales => 'SALES',
        AppModule.quotations => 'SALES',
        AppModule.salesOrders => 'SALES',
        AppModule.deliveryNotes => 'SALES',
        AppModule.salesInvoices => 'SALES',
        AppModule.salesReturns => 'SALES',
        AppModule.purchases => 'PURCHASES',
        AppModule.purchaseInvoices => 'PURCHASES',
        AppModule.purchaseReturns => 'PURCHASES',
        AppModule.goodsReceipts => 'PURCHASES',
        AppModule.inventory => 'INVENTORY',
        AppModule.accounting => 'ACCOUNTING',
        AppModule.reports => 'REPORTS',
        AppModule.settings => 'SETTINGS',
        AppModule.licensing => 'LICENSING',
      };

  static ModuleDefinition byId(AppModule id) =>
      modules.firstWhere((module) => module.id == id);

  /// Purchase tab ids that no longer exist, and where they now live.
  ///
  /// Draft, Open, Cancelled, Closed and History were separate tabs until they
  /// became the status bar inside Purchase Orders. The last workspace a user
  /// was on is persisted (`session.saveLastWorkspace`), so without this an
  /// upgrade would drop anybody who left the app on Draft Orders back to the
  /// Dashboard, with nothing to explain why.
  static const Map<String, String> purchaseTabAliases = <String, String>{
    'draft-orders': 'purchase-orders',
    'open-orders': 'purchase-orders',
    'cancelled-orders': 'purchase-orders',
    'closed-orders': 'purchase-orders',
    'purchase-history': 'purchase-orders',
  };

  /// Builds the hierarchical sub-navigation nodes for [id], filtered to the
  /// tab ids the current user can access ([visibleTabIds]).
  ///
  /// This is the single source of truth for module sub-navigation: it feeds
  /// both the unified `EnterpriseSidebar` tree and (for collapsed sidebars)
  /// the flyout menu. No workspace should hard-code its own navigation tree.
  static List<WorkspaceNavigationNode> navigationChildren(
    AppModule id,
    Set<String> visibleTabIds,
  ) {
    switch (id) {
      case AppModule.administration:
        return _administrationNavigation(visibleTabIds);
      case AppModule.masters:
        return _mastersNavigation(visibleTabIds);
      case AppModule.purchases:
        return _purchasesNavigation(visibleTabIds);
      case AppModule.goodsReceipts:
        return _goodsReceiptsNavigation(visibleTabIds);
      case AppModule.deliveryNotes:
        return _deliveryNotesNavigation(visibleTabIds);
      case AppModule.inventory:
        return _inventoryNavigation(visibleTabIds);
      default:
        return byId(id)
            .tabs
            .where((tab) => visibleTabIds.contains(tab.id))
            .map(
              (tab) => WorkspaceNavigationNode(
                label: tab.label,
                path: tab.id,
                available: tab.available,
              ),
            )
            .toList();
    }
  }

  static List<WorkspaceNavigationNode> _administrationNavigation(
    Set<String> visibleTabIds,
  ) {
    bool hasAny(List<String> ids) => ids.any(visibleTabIds.contains);
    return [
      if (visibleTabIds.contains('users'))
        const WorkspaceNavigationNode(
          label: 'Users',
          path: 'users',
          icon: Icons.person_outline,
        ),
      if (visibleTabIds.contains('roles'))
        const WorkspaceNavigationNode(
          label: 'Roles',
          path: 'roles',
          icon: Icons.badge_outlined,
        ),
      if (visibleTabIds.contains('permissions'))
        const WorkspaceNavigationNode(
          label: 'Permissions',
          path: 'permissions',
          icon: Icons.key_outlined,
        ),
      if (visibleTabIds.contains('user-firms'))
        const WorkspaceNavigationNode(
          label: 'User-Firm Assignments',
          path: 'user-firms',
          icon: Icons.swap_horiz,
        ),
      // Gated on the real tab id. This node used to be unconditional with
      // path 'audit', which matches no tab and no route, so selecting Audit
      // silently rendered the Users workspace instead.
      if (visibleTabIds.contains('user-audit'))
        const WorkspaceNavigationNode(
          label: 'Audit',
          path: 'user-audit',
          icon: Icons.history_outlined,
        ),
      WorkspaceNavigationNode(
        label: 'Configuration',
        icon: Icons.tune_outlined,
        children: [
          if (hasAny([
            'business-profiles',
            'feature-management',
            'module-configuration',
            'attribute-definitions',
            'profile-assignment',
          ]))
            WorkspaceNavigationNode(
              label: 'Business Profiles',
              icon: Icons.business_outlined,
              children: [
                if (visibleTabIds.contains('business-profiles'))
                  const WorkspaceNavigationNode(
                    label: 'Profiles',
                    path: 'business-profiles',
                  ),
                if (visibleTabIds.contains('feature-management'))
                  const WorkspaceNavigationNode(
                    label: 'Feature Flags',
                    path: 'feature-management',
                  ),
                if (visibleTabIds.contains('module-configuration'))
                  const WorkspaceNavigationNode(
                    label: 'Business Modules',
                    path: 'module-configuration',
                  ),
                if (visibleTabIds.contains('attribute-definitions'))
                  const WorkspaceNavigationNode(
                    label: 'Dynamic Attributes',
                    path: 'attribute-definitions',
                  ),
                if (visibleTabIds.contains('profile-assignment'))
                  const WorkspaceNavigationNode(
                    label: 'Profile Assignment',
                    path: 'profile-assignment',
                  ),
              ],
            ),
          if (hasAny([
            'tax-configuration',
            'tax-rules-page',
            'tax-rule-simulator',
            'tax-execution-log',
            'tax-settings',
          ]))
            WorkspaceNavigationNode(
              label: 'Tax Configuration',
              icon: Icons.receipt_long_outlined,
              children: [
                if (visibleTabIds.contains('tax-configuration'))
                  const WorkspaceNavigationNode(
                    label: 'Systems & Profiles',
                    path: 'tax-configuration',
                  ),
                if (visibleTabIds.contains('tax-rules-page'))
                  const WorkspaceNavigationNode(
                    label: 'Tax Rules',
                    path: 'tax-rules-page',
                  ),
                if (visibleTabIds.contains('tax-rule-simulator'))
                  const WorkspaceNavigationNode(
                    label: 'Rule Simulator',
                    path: 'tax-rule-simulator',
                  ),
                if (visibleTabIds.contains('tax-execution-log'))
                  const WorkspaceNavigationNode(
                    label: 'Execution Log',
                    path: 'tax-execution-log',
                  ),
                if (visibleTabIds.contains('tax-settings'))
                  const WorkspaceNavigationNode(
                    label: 'Settings',
                    path: 'tax-settings',
                  ),
              ],
            ),
          if (hasAny([
            'uoms',
            'uom-groups',
            'packaging-types',
            'conversion-rules',
            'industry-templates',
          ]))
            WorkspaceNavigationNode(
              label: 'UOM & Packaging',
              icon: Icons.straighten_outlined,
              children: [
                if (visibleTabIds.contains('uoms'))
                  const WorkspaceNavigationNode(
                    label: 'Units of Measure',
                    path: 'uoms',
                  ),
                if (visibleTabIds.contains('uom-groups'))
                  const WorkspaceNavigationNode(
                    label: 'UOM Groups',
                    path: 'uom-groups',
                  ),
                if (visibleTabIds.contains('packaging-types'))
                  const WorkspaceNavigationNode(
                    label: 'Packaging Types',
                    path: 'packaging-types',
                  ),
                if (visibleTabIds.contains('conversion-rules'))
                  const WorkspaceNavigationNode(
                    label: 'Conversion Rules',
                    path: 'conversion-rules',
                  ),
                if (visibleTabIds.contains('industry-templates'))
                  const WorkspaceNavigationNode(
                    label: 'Industry Templates',
                    path: 'industry-templates',
                  ),
              ],
            ),
          const WorkspaceNavigationNode(
            label: 'Numbering Series',
            path: 'numbering-series',
            icon: Icons.confirmation_number_outlined,
          ),
        ],
      ),
    ];
  }

  static List<WorkspaceNavigationNode> _mastersNavigation(
    Set<String> visibleTabIds,
  ) {
    bool hasAny(List<String> ids) => ids.any(visibleTabIds.contains);
    return [
      if (visibleTabIds.contains('firms'))
        const WorkspaceNavigationNode(
          label: 'Firms',
          path: 'firms',
          icon: Icons.apartment_outlined,
        ),
      if (visibleTabIds.contains('customers'))
        const WorkspaceNavigationNode(
          label: 'Customers',
          path: 'customers',
          icon: Icons.groups_outlined,
        ),
      if (visibleTabIds.contains('products'))
        const WorkspaceNavigationNode(
          label: 'Products',
          path: 'products',
          icon: Icons.inventory_2_outlined,
        ),
      if (visibleTabIds.contains('vendors'))
        const WorkspaceNavigationNode(
          label: 'Vendors',
          path: 'vendors',
          icon: Icons.local_shipping_outlined,
        ),
      if (hasAny([
        'branches',
        'warehouses',
        'storage-areas',
        'warehouse-types',
        'branch-types',
        'branch-warehouse-settings',
      ]))
        WorkspaceNavigationNode(
          label: 'Branch & Warehouse',
          icon: Icons.store_outlined,
          children: [
            if (visibleTabIds.contains('branches'))
              const WorkspaceNavigationNode(
                label: 'Branches',
                path: 'branches',
              ),
            if (visibleTabIds.contains('warehouses'))
              const WorkspaceNavigationNode(
                label: 'Warehouses',
                path: 'warehouses',
              ),
            if (visibleTabIds.contains('storage-areas'))
              const WorkspaceNavigationNode(
                label: 'Storage Areas',
                path: 'storage-areas',
              ),
            if (visibleTabIds.contains('warehouse-types'))
              const WorkspaceNavigationNode(
                label: 'Warehouse Types',
                path: 'warehouse-types',
              ),
            if (visibleTabIds.contains('branch-types'))
              const WorkspaceNavigationNode(
                label: 'Branch Types',
                path: 'branch-types',
              ),
            if (visibleTabIds.contains('branch-warehouse-settings'))
              const WorkspaceNavigationNode(
                label: 'Settings',
                path: 'branch-warehouse-settings',
              ),
          ],
        ),
      // Configuration in one place, the way Administration already groups
      // its own. These three sat loose at the bottom of Masters, level with
      // Customers and Products -- so a module of master data ended in three
      // entries that are not master data, and somebody looking for a setting
      // had to know it had been left there.
      //
      // Grouping only. Every path is unchanged, so a stored workspace still
      // resolves and no permission moved.
      if (hasAny(['financial-years', 'firm-settings']))
        WorkspaceNavigationNode(
          label: 'Configuration',
          icon: Icons.tune_outlined,
          children: [
            if (visibleTabIds.contains('firm-settings'))
              const WorkspaceNavigationNode(
                label: 'Firm Settings',
                path: 'firm-settings',
                icon: Icons.settings_applications_outlined,
              ),
            if (visibleTabIds.contains('financial-years'))
              const WorkspaceNavigationNode(
                label: 'Financial Years',
                path: 'financial-years',
                icon: Icons.event_note_outlined,
              ),
          ],
        ),
    ];
  }

  static List<WorkspaceNavigationNode> _purchasesNavigation(
    Set<String> visibleTabIds,
  ) {
    bool hasAny(List<String> ids) => ids.any(visibleTabIds.contains);
    return [
      if (visibleTabIds.contains('purchase-dashboard'))
        const WorkspaceNavigationNode(
          label: 'Dashboard',
          path: 'purchase-dashboard',
          icon: Icons.dashboard_outlined,
        ),
      // One entry, not seven. The group this replaces was labelled "Orders",
      // which in an application that also sells says nothing about whose
      // orders; and five of its children were this same workspace with a
      // status preset.
      if (visibleTabIds.contains('purchase-orders'))
        const WorkspaceNavigationNode(
          label: 'Purchase Orders',
          path: 'purchase-orders',
          icon: Icons.receipt_long_outlined,
        ),
      // The procurement lifecycle begins before a purchase order. Neither
      // child has a backend yet, so both open the placeholder — the group
      // exists so that when they arrive the navigation does not change again.
      if (hasAny(['purchase-rfqs', 'vendor-quotations']))
        WorkspaceNavigationNode(
          label: 'Sourcing',
          icon: Icons.request_quote_outlined,
          children: [
            if (visibleTabIds.contains('purchase-rfqs'))
              const WorkspaceNavigationNode(
                label: 'RFQs',
                path: 'purchase-rfqs',
              ),
            if (visibleTabIds.contains('vendor-quotations'))
              const WorkspaceNavigationNode(
                label: 'Vendor Quotations',
                path: 'vendor-quotations',
              ),
          ],
        ),
      if (visibleTabIds.contains('purchase-analytics'))
        const WorkspaceNavigationNode(
          label: 'Analytics',
          path: 'purchase-analytics',
          icon: Icons.query_stats_outlined,
        ),
      if (visibleTabIds.contains('purchase-settings'))
        const WorkspaceNavigationNode(
          label: 'Settings',
          path: 'purchase-settings',
          icon: Icons.settings_outlined,
        ),
    ];
  }

  static List<WorkspaceNavigationNode> _goodsReceiptsNavigation(
    Set<String> visibleTabIds,
  ) {
    bool hasAny(List<String> ids) => ids.any(visibleTabIds.contains);
    return [
      if (visibleTabIds.contains('receipts'))
        const WorkspaceNavigationNode(
          label: 'Receipts',
          path: 'receipts',
          icon: Icons.receipt_long_outlined,
        ),
      if (hasAny([
        'pending-receipts',
        'partial-receipts',
        'completed-receipts',
        'rejected-items',
        'damaged-items',
      ]))
        WorkspaceNavigationNode(
          label: 'Reports',
          icon: Icons.analytics_outlined,
          children: [
            if (visibleTabIds.contains('pending-receipts'))
              const WorkspaceNavigationNode(
                label: 'Pending Receipts',
                path: 'pending-receipts',
              ),
            if (visibleTabIds.contains('partial-receipts'))
              const WorkspaceNavigationNode(
                label: 'Partial Receipts',
                path: 'partial-receipts',
              ),
            if (visibleTabIds.contains('completed-receipts'))
              const WorkspaceNavigationNode(
                label: 'Completed Receipts',
                path: 'completed-receipts',
              ),
            if (visibleTabIds.contains('rejected-items'))
              const WorkspaceNavigationNode(
                label: 'Rejected Items',
                path: 'rejected-items',
              ),
            if (visibleTabIds.contains('damaged-items'))
              const WorkspaceNavigationNode(
                label: 'Damaged Items',
                path: 'damaged-items',
              ),
          ],
        ),
      if (visibleTabIds.contains('grn-history'))
        const WorkspaceNavigationNode(
          label: 'History',
          path: 'grn-history',
          icon: Icons.history_outlined,
        ),
      if (visibleTabIds.contains('grn-settings'))
        const WorkspaceNavigationNode(
          label: 'Settings',
          path: 'grn-settings',
          icon: Icons.settings_outlined,
        ),
    ];
  }

  static List<WorkspaceNavigationNode> _deliveryNotesNavigation(
    Set<String> visibleTabIds,
  ) {
    bool hasAny(List<String> ids) => ids.any(visibleTabIds.contains);
    return [
      if (visibleTabIds.contains('delivery-notes'))
        const WorkspaceNavigationNode(
          label: 'Delivery Notes',
          path: 'delivery-notes',
          icon: Icons.local_shipping_outlined,
        ),
      if (hasAny([
        'pending-deliveries',
        'partial-deliveries',
        'delivered-by-route',
        'delivered-by-salesman',
        'delivered-by-warehouse',
      ]))
        WorkspaceNavigationNode(
          label: 'Reports',
          icon: Icons.analytics_outlined,
          children: [
            if (visibleTabIds.contains('pending-deliveries'))
              const WorkspaceNavigationNode(
                label: 'Pending Deliveries',
                path: 'pending-deliveries',
              ),
            if (visibleTabIds.contains('partial-deliveries'))
              const WorkspaceNavigationNode(
                label: 'Partial Deliveries',
                path: 'partial-deliveries',
              ),
            if (visibleTabIds.contains('delivered-by-route'))
              const WorkspaceNavigationNode(
                label: 'Delivered by Route',
                path: 'delivered-by-route',
              ),
            if (visibleTabIds.contains('delivered-by-salesman'))
              const WorkspaceNavigationNode(
                label: 'Delivered by Salesman',
                path: 'delivered-by-salesman',
              ),
            if (visibleTabIds.contains('delivered-by-warehouse'))
              const WorkspaceNavigationNode(
                label: 'Delivered by Warehouse',
                path: 'delivered-by-warehouse',
              ),
          ],
        ),
      if (visibleTabIds.contains('delivery-history'))
        const WorkspaceNavigationNode(
          label: 'History',
          path: 'delivery-history',
          icon: Icons.history_outlined,
        ),
    ];
  }

  static List<WorkspaceNavigationNode> _inventoryNavigation(
    Set<String> visibleTabIds,
  ) {
    bool hasAny(List<String> ids) => ids.any(visibleTabIds.contains);
    return [
      if (hasAny([
        'inventory',
        'opening-stock',
        'stock-ledger',
        'transactions',
        'stock-summary',
        'stock-search',
      ]))
        WorkspaceNavigationNode(
          label: 'Stock',
          icon: Icons.inventory_2_outlined,
          children: [
            if (visibleTabIds.contains('inventory'))
              const WorkspaceNavigationNode(
                label: 'Inventory',
                path: 'inventory',
              ),
            if (visibleTabIds.contains('opening-stock'))
              const WorkspaceNavigationNode(
                label: 'Opening Stock',
                path: 'opening-stock',
              ),
            if (visibleTabIds.contains('stock-ledger'))
              const WorkspaceNavigationNode(
                label: 'Stock Ledger',
                path: 'stock-ledger',
              ),
            if (visibleTabIds.contains('transactions'))
              const WorkspaceNavigationNode(
                label: 'Transactions',
                path: 'transactions',
              ),
            if (visibleTabIds.contains('stock-summary'))
              const WorkspaceNavigationNode(
                label: 'Stock Summary',
                path: 'stock-summary',
              ),
            if (visibleTabIds.contains('stock-search'))
              const WorkspaceNavigationNode(
                label: 'Stock Search',
                path: 'stock-search',
              ),
          ],
        ),
      if (hasAny(['batches', 'lots', 'serials', 'expiry-monitor']))
        WorkspaceNavigationNode(
          label: 'Batch & Serial',
          icon: Icons.qr_code_2_outlined,
          children: [
            if (visibleTabIds.contains('batches'))
              const WorkspaceNavigationNode(
                label: 'Batches',
                path: 'batches',
              ),
            if (visibleTabIds.contains('lots'))
              const WorkspaceNavigationNode(label: 'Lots', path: 'lots'),
            if (visibleTabIds.contains('serials'))
              const WorkspaceNavigationNode(
                label: 'Serial Numbers',
                path: 'serials',
              ),
            if (visibleTabIds.contains('expiry-monitor'))
              const WorkspaceNavigationNode(
                label: 'Expiry Monitor',
                path: 'expiry-monitor',
              ),
          ],
        ),
      if (visibleTabIds.contains('inventory-import'))
        const WorkspaceNavigationNode(
          label: 'Import',
          path: 'inventory-import',
          icon: Icons.file_upload_outlined,
        ),
      if (visibleTabIds.contains('inventory-export'))
        const WorkspaceNavigationNode(
          label: 'Export',
          path: 'inventory-export',
          icon: Icons.file_download_outlined,
        ),
      if (visibleTabIds.contains('inventory-settings'))
        const WorkspaceNavigationNode(
          label: 'Settings',
          path: 'inventory-settings',
          icon: Icons.settings_outlined,
        ),
    ];
  }
}
