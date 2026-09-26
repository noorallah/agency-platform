import '../ui/workspace/module_catalog.dart';
import '../ui/workspace/module_visibility.dart';

/// One screen in the phase 2 menu, addressed exactly as the router and the
/// catalogue address it.
///
/// The menu **names** screens; it never decides who may open them. Whether an
/// item is offered is asked of [ModuleVisibility], the same rules the phase 1
/// sidebar uses (UI_PHASE_2_DESIGN.md 4.12), so a screen hidden there is
/// hidden here and the server stays the authority either way.
class MenuItemSpec {
  const MenuItemSpec(AppModule this.module, this.tab, this.label)
      : route = null,
        gate = null;

  /// A module with no tabs of its own (Quotations, the Dashboard).
  const MenuItemSpec.module(AppModule this.module, this.label)
      : tab = null,
        route = null,
        gate = null;

  /// A screen only the phase 2 app has, with no catalogue module behind it
  /// -- Home (4.9). Offered to everybody signed in; what it shows inside is
  /// cut to the user's permissions.
  const MenuItemSpec.phase2(String this.route, this.label, {this.gate})
      : module = null,
        tab = null;

  /// For a phase 2 screen, the catalogue screen whose visibility it follows
  /// -- Customer Groups is offered to whoever may open Customers. Null
  /// offers it to everybody signed in (Home).
  final String? gate;

  /// The catalogue module, or null for a phase 2 screen.
  final AppModule? module;

  /// A phase 2 screen's address, when [module] is null.
  final String? route;

  /// The catalogue tab id, or null for a module that is one screen.
  final String? tab;

  /// What the menu says -- which is not always the catalogue's label: phase 1
  /// has four tabs called "Settings", and a menu cannot.
  final String label;

  /// The router path, which is also the identity of an open-screen tab.
  String get path =>
      route ?? (tab == null ? module!.name : '${module!.name}/$tab');
}

/// A column in an area's drop-down panel (4.3).
class MenuGroupSpec {
  const MenuGroupSpec(this.label, this.items, {this.configuration = false});

  final String label;
  final List<MenuItemSpec> items;

  /// A group of lookup lists set up once and rarely touched -- categories,
  /// types, units. The panel draws these apart, under CONFIGURATION, so the
  /// masters opened every day are not lost among them (owner, 2026-09-26).
  final bool configuration;
}

/// One entry of the menu bar (4.2), or the Settings gear (4.13).
class MenuAreaSpec {
  const MenuAreaSpec(this.id, this.label, this.groups);

  final String id;
  final String label;
  final List<MenuGroupSpec> groups;

  Iterable<MenuItemSpec> get items => groups.expand((group) => group.items);
}

/// The phase 2 menu: every phase 1 screen, placed as appendix A of
/// `docs/UI_PHASE_2_DESIGN.md` places it.
///
/// **No screen may be lost** (the owner's rule, 2026-09-25):
/// `test/menu_layout_test.dart` reads the catalogue and fails when a screen
/// appears nowhere here, or twice. Settings that phase 1 opens as dialogs
/// inside other screens (credit control, the loyalty scheme, print settings)
/// are not catalogue screens yet and join [settings] when the Settings page
/// of 4.13 is built.
abstract final class MenuLayout {
  /// Home's address: a phase 2 screen, drawn by the phase 2 shell itself.
  static const String homeRoute = 'home';

  /// Customer Groups: a phase 2 page, opened in a tab of its own.
  static const String customerGroupsRoute = 'customer-groups';

  static const MenuAreaSpec home = MenuAreaSpec('home', 'Home', [
    MenuGroupSpec('Home', [MenuItemSpec.phase2(MenuLayout.homeRoute, 'Home')]),
  ]);

  /// Catalogue screens deliberately given no place in the phase 2 menu, and
  /// why. A screen that exists only to say a feature is missing is not
  /// offered; it returns when there is something behind it.
  static const Map<String, String> notOffered = {
    'purchases/purchase-analytics':
        'a placeholder: the backend exposes no purchase analytics yet',
  };

  static const List<MenuAreaSpec> areas = [
    home,
    MenuAreaSpec('sell', 'Sell', [
      MenuGroupSpec('Documents', [
        MenuItemSpec.module(AppModule.quotations, 'Quotations'),
        MenuItemSpec.module(AppModule.salesOrders, 'Sales Orders'),
        MenuItemSpec(
            AppModule.deliveryNotes, 'delivery-notes', 'Delivery Notes'),
        MenuItemSpec(
            AppModule.salesInvoices, 'sales-invoices', 'Sales Invoices'),
        MenuItemSpec.module(AppModule.salesReturns, 'Sales Returns'),
        MenuItemSpec(AppModule.sales, 'proforma-invoices', 'Proforma'),
        MenuItemSpec(AppModule.sales, 'credit-notes', 'Credit Notes'),
      ]),
      MenuGroupSpec('Money', [
        MenuItemSpec(AppModule.accounting, 'receipts', 'Receipts'),
        MenuItemSpec(AppModule.accounting, 'refunds', 'Refunds'),
        MenuItemSpec(
            AppModule.masters, 'customer-statements', 'Customer Statements'),
      ]),
      MenuGroupSpec('Incentives', [
        MenuItemSpec(AppModule.sales, 'commission', 'Commission'),
        MenuItemSpec(AppModule.sales, 'targets', 'Targets'),
      ]),
      MenuGroupSpec('Field sales', [
        MenuItemSpec(AppModule.sales, 'beat-plans', 'Beat Plans'),
        MenuItemSpec(AppModule.sales, 'call-lists', 'Call Lists'),
        MenuItemSpec(AppModule.sales, 'coverage', 'Coverage'),
      ]),
      // Set up once and revisited now and then: drawn apart, under
      // CONFIGURATION, as in Masters (owner, 2026-09-26).
      MenuGroupSpec(
        'Pricing',
        [
          MenuItemSpec(AppModule.sales, 'price-lists', 'Price Lists'),
          MenuItemSpec(AppModule.sales, 'promotions', 'Promotions'),
          MenuItemSpec(AppModule.masters, 'loyalty', 'Loyalty'),
        ],
        configuration: true,
      ),
      MenuGroupSpec(
        'Territories & routes',
        [
          MenuItemSpec(AppModule.sales, 'territories', 'Territories'),
          MenuItemSpec(AppModule.sales, 'route-types', 'Route Types'),
          MenuItemSpec(AppModule.sales, 'route-builder', 'Route Builder'),
        ],
        configuration: true,
      ),
    ]),
    MenuAreaSpec('buy', 'Buy', [
      MenuGroupSpec('Documents', [
        MenuItemSpec(AppModule.purchases, 'purchase-orders', 'Purchase Orders'),
        MenuItemSpec(AppModule.goodsReceipts, 'receipts', 'Goods Receipts'),
        MenuItemSpec.module(AppModule.purchaseInvoices, 'Purchase Invoices'),
        MenuItemSpec.module(AppModule.purchaseReturns, 'Purchase Returns'),
      ]),
      MenuGroupSpec('Money', [
        MenuItemSpec(AppModule.accounting, 'payments', 'Payments'),
      ]),
      MenuGroupSpec('Insight', [
        MenuItemSpec(
            AppModule.purchases, 'purchase-dashboard', 'Purchase Dashboard'),
        // Purchase Analytics is left out: its screen only says the backend
        // has no analytics yet (MenuLayout.notOffered).
      ]),
    ]),
    MenuAreaSpec('stock', 'Stock', [
      MenuGroupSpec('Stock', [
        MenuItemSpec(AppModule.inventory, 'inventory', 'Inventory'),
        MenuItemSpec(AppModule.inventory, 'stock-summary', 'Stock Summary'),
        MenuItemSpec(AppModule.inventory, 'stock-search', 'Stock Search'),
        MenuItemSpec(AppModule.inventory, 'stock-ledger', 'Stock Ledger'),
        MenuItemSpec(AppModule.inventory, 'transactions', 'Transactions'),
      ]),
      MenuGroupSpec('Movements', [
        MenuItemSpec(AppModule.inventory, 'opening-stock', 'Opening Stock'),
        MenuItemSpec(AppModule.inventory, 'physical-counts', 'Physical Count'),
      ]),
      MenuGroupSpec('Tracking', [
        MenuItemSpec(AppModule.inventory, 'batches', 'Batches'),
        MenuItemSpec(AppModule.inventory, 'lots', 'Lots'),
        MenuItemSpec(AppModule.inventory, 'serials', 'Serial Numbers'),
        MenuItemSpec(AppModule.inventory, 'expiry-monitor', 'Expiry Monitor'),
      ]),
      MenuGroupSpec('Data', [
        MenuItemSpec(AppModule.inventory, 'inventory-import', 'Import'),
        MenuItemSpec(AppModule.inventory, 'inventory-export', 'Export'),
      ]),
    ]),
    MenuAreaSpec('accounts', 'Accounts', [
      MenuGroupSpec('Books', [
        MenuItemSpec(
            AppModule.accounting, 'chart-of-accounts', 'Chart of Accounts'),
        MenuItemSpec(
            AppModule.accounting, 'journal-entries', 'Journal Entries'),
        MenuItemSpec(AppModule.accounting, 'ledgers', 'Ledgers'),
      ]),
      MenuGroupSpec('Statements', [
        MenuItemSpec(AppModule.accounting, 'trial-balance', 'Trial Balance'),
        MenuItemSpec(AppModule.accounting, 'profit-loss', 'Profit & Loss'),
        MenuItemSpec(AppModule.accounting, 'balance-sheet', 'Balance Sheet'),
      ]),
      MenuGroupSpec('Tax filing', [
        MenuItemSpec(AppModule.sales, 'gst-returns', 'GST Returns'),
        MenuItemSpec(AppModule.sales, 'einvoice', 'E-Invoice'),
        MenuItemSpec(AppModule.sales, 'tcs', 'TCS'),
      ]),
      MenuGroupSpec(
        'Structure',
        [
          MenuItemSpec(
              AppModule.accounting, 'control-accounts', 'Control Accounts'),
          MenuItemSpec(AppModule.accounting, 'cost-centers', 'Cost Centres'),
          MenuItemSpec(
              AppModule.accounting, 'profit-centers', 'Profit Centres'),
        ],
        configuration: true,
      ),
    ]),
    MenuAreaSpec('masters', 'Masters', [
      // Opened every day.
      MenuGroupSpec('Parties', [
        MenuItemSpec(AppModule.masters, 'customers', 'Customers'),
        MenuItemSpec(AppModule.masters, 'vendors', 'Vendors'),
      ]),
      MenuGroupSpec('Items', [
        MenuItemSpec(AppModule.masters, 'products', 'Products'),
      ]),
      MenuGroupSpec('Organisation', [
        MenuItemSpec(AppModule.masters, 'branches', 'Branches'),
        MenuItemSpec(AppModule.masters, 'warehouses', 'Warehouses'),
      ]),
      // Set up once, rarely touched: drawn apart, under CONFIGURATION.
      MenuGroupSpec(
        'Parties',
        [
          // Master data like vendor categories, not a button on the
          // Customers screen (owner, 2026-09-26).
          MenuItemSpec.phase2(customerGroupsRoute, 'Customer Groups',
              gate: 'masters/customers'),
          MenuItemSpec(
              AppModule.masters, 'vendor-categories', 'Vendor Categories'),
          MenuItemSpec(AppModule.masters, 'vendor-types', 'Vendor Types'),
        ],
        configuration: true,
      ),
      MenuGroupSpec(
        'Items',
        [
          MenuItemSpec(
              AppModule.masters, 'product-categories', 'Product Categories'),
          MenuItemSpec(AppModule.administration, 'uoms', 'Units of Measure'),
          MenuItemSpec(AppModule.administration, 'uom-groups', 'UOM Groups'),
          MenuItemSpec(
              AppModule.administration, 'packaging-types', 'Packaging Types'),
          MenuItemSpec(
              AppModule.administration, 'packaging-levels', 'Packaging Levels'),
          MenuItemSpec(
              AppModule.administration, 'conversion-rules', 'Conversion Rules'),
        ],
        configuration: true,
      ),
      MenuGroupSpec(
        'Locations',
        [
          MenuItemSpec(AppModule.masters, 'storage-areas', 'Storage Areas'),
          MenuItemSpec(AppModule.masters, 'branch-types', 'Branch Types'),
          MenuItemSpec(AppModule.masters, 'warehouse-types', 'Warehouse Types'),
          MenuItemSpec(AppModule.masters, 'geography-masters', 'Places'),
        ],
        configuration: true,
      ),
    ]),
    MenuAreaSpec('reports', 'Reports', [
      MenuGroupSpec('Reports', [
        MenuItemSpec(AppModule.reports, 'operational', 'Operational'),
        MenuItemSpec(AppModule.reports, 'financial', 'Financial'),
      ]),
    ]),
    MenuAreaSpec('admin', 'Admin', [
      MenuGroupSpec('People', [
        MenuItemSpec(AppModule.administration, 'users', 'Users'),
        MenuItemSpec(AppModule.administration, 'roles', 'Roles'),
        MenuItemSpec(AppModule.administration, 'permissions', 'Permissions'),
        MenuItemSpec(
            AppModule.administration, 'user-templates', 'User Templates'),
        MenuItemSpec(
            AppModule.administration, 'user-firms', 'User-Firm Assignments'),
      ]),
      MenuGroupSpec('Firms', [
        MenuItemSpec(AppModule.administration, 'firms', 'Firms'),
        MenuItemSpec(
            AppModule.administration, 'business-profiles', 'Business Profiles'),
      ]),
      MenuGroupSpec('System', [
        MenuItemSpec(AppModule.settings, 'audit-logs', 'Audit Logs'),
        MenuItemSpec(AppModule.settings, 'diagnostics', 'Diagnostics'),
        MenuItemSpec.module(AppModule.licensing, 'Licensing'),
        // Phase 1's Dashboard: platform-wide counts of firms, users and
        // roles, for a platform administrator. Home is everybody's (4.9).
        MenuItemSpec.module(AppModule.dashboard, 'Platform Dashboard'),
      ]),
    ]),
  ];

  /// Behind the gear, by topic (4.13).
  static const MenuAreaSpec settings = MenuAreaSpec('settings', 'Settings', [
    MenuGroupSpec('Firm', [
      MenuItemSpec(AppModule.masters, 'firm-settings', 'Firm Settings'),
      MenuItemSpec(AppModule.masters, 'financial-years', 'Financial Years'),
      MenuItemSpec(
          AppModule.administration, 'numbering-series', 'Numbering Series'),
    ]),
    MenuGroupSpec('Buying', [
      MenuItemSpec(
          AppModule.purchases, 'purchase-settings', 'Purchase Settings'),
    ]),
    MenuGroupSpec('Stock', [
      MenuItemSpec(
          AppModule.inventory, 'inventory-settings', 'Inventory Settings'),
      MenuItemSpec(AppModule.masters, 'branch-warehouse-settings',
          'Branch & Warehouse Settings'),
    ]),
    MenuGroupSpec('Tax', [
      MenuItemSpec(
          AppModule.administration, 'tax-configuration', 'Tax Configuration'),
      MenuItemSpec(AppModule.administration, 'tax-rules-page', 'Tax Rules'),
      MenuItemSpec(
          AppModule.administration, 'tax-rule-simulator', 'Rule Simulator'),
      MenuItemSpec(
          AppModule.administration, 'tax-execution-log', 'Execution Log'),
      MenuItemSpec(AppModule.administration, 'tax-settings', 'Tax Settings'),
    ]),
    MenuGroupSpec('Business profile', [
      MenuItemSpec(
          AppModule.administration, 'feature-management', 'Feature Management'),
      MenuItemSpec(AppModule.administration, 'module-configuration',
          'Module Configuration'),
      MenuItemSpec(AppModule.administration, 'attribute-definitions',
          'Attribute Definitions'),
      MenuItemSpec(AppModule.administration, 'category-attribute-rules',
          'Mandatory Attributes'),
      MenuItemSpec(
          AppModule.administration, 'profile-assignment', 'Profile Assignment'),
      MenuItemSpec(
          AppModule.administration, 'industry-templates', 'Industry Templates'),
    ]),
  ]);

  /// Every area, the gear included -- what the command box searches.
  static Iterable<MenuAreaSpec> get all => [...areas, settings];

  /// The item a router path names, for an open-screen tab's label.
  static MenuItemSpec? itemFor(String path) {
    for (final MenuAreaSpec area in all) {
      for (final MenuItemSpec item in area.items) {
        if (item.path == path) return item;
      }
    }
    return null;
  }

  /// The area an item belongs to, so the menu bar can mark where you are.
  static MenuAreaSpec? areaOf(String path) {
    for (final MenuAreaSpec area in all) {
      if (area.items.any((item) => item.path == path)) return area;
    }
    return null;
  }

  /// [area] cut down to what [visibility] allows: items the user may open,
  /// groups left with at least one item. An area that ends up empty is not
  /// shown at all (4.12).
  static MenuAreaSpec? visible(MenuAreaSpec area, ModuleVisibility visibility) {
    final Map<AppModule, ModuleDefinition> allowed = {
      for (final ModuleDefinition module in visibility.modules)
        module.id: module,
    };
    final Map<AppModule, Set<String>> tabs = {};
    bool offered(MenuItemSpec item) {
      if (item.module == null) {
        final MenuItemSpec? gate =
            item.gate == null ? null : itemFor(item.gate!);
        return item.gate == null || (gate != null && offered(gate));
      }
      final ModuleDefinition? module = allowed[item.module];
      if (module == null) return false;
      if (item.tab == null) return true;
      return tabs
          .putIfAbsent(item.module!, () => visibility.tabIds(module))
          .contains(item.tab);
    }

    final List<MenuGroupSpec> groups = [
      for (final MenuGroupSpec group in area.groups)
        if (group.items.where(offered).isNotEmpty)
          MenuGroupSpec(
            group.label,
            group.items.where(offered).toList(),
            configuration: group.configuration,
          ),
    ];
    return groups.isEmpty ? null : MenuAreaSpec(area.id, area.label, groups);
  }
}
