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
        gate = null,
        requiredPermission = null,
        permission = null,
        needsFirm = true;

  /// A module with no tabs of its own (Quotations, the Dashboard).
  const MenuItemSpec.module(AppModule this.module, this.label)
      : tab = null,
        route = null,
        gate = null,
        requiredPermission = null,
        permission = null,
        needsFirm = true;

  /// A screen only the phase 2 app has, with no catalogue module behind it
  /// -- Home (4.9). Offered to everybody signed in; what it shows inside is
  /// cut to the user's permissions.
  const MenuItemSpec.phase2(String this.route, this.label,
      {this.gate, this.requiredPermission})
      : module = null,
        tab = null,
        permission = null,
        needsFirm = true;

  /// A setting that is a dialog rather than a screen (sales stages, credit
  /// control, the loyalty scheme, TCS): the Settings gear opens the same
  /// dialog the owning screen's "..." menu does, and no tab is added.
  /// Offered only with a firm chosen and [permission] held -- the code its
  /// owning screen already asks to read it; each dialog is read-only for
  /// somebody who may not change it.
  const MenuItemSpec.setting(String this.route, this.label,
      {String this.permission = noPermission, this.needsFirm = true})
      : module = null,
        tab = null,
        requiredPermission = null,
        gate = null;

  /// The [permission] of a setting that every member of a firm may open
  /// (their own preferences), so no code is asked.
  static const String noPermission = '';

  /// For a [MenuItemSpec.setting], the permission that offers it.
  final String? permission;

  /// For a setting, whether it is offered only with a firm chosen. False for
  /// what is the person's own wherever they are (My preferences), which a
  /// platform administrator with no firm open must reach too.
  final bool needsFirm;

  /// Whether this item opens a dialog rather than a screen.
  bool get isSetting => permission != null;

  /// For a phase 2 screen, the catalogue screen whose visibility it follows
  /// -- Customer Groups is offered to whoever may open Customers. Null
  /// offers it to everybody signed in (Home).
  final String? gate;

  /// For a phase 2 screen with no catalogue screen to follow, the permission
  /// code that offers it (Backups: `SYSTEM_BACKUP`, which only the platform
  /// tier holds). Asked in addition to [gate]; the server stays the authority.
  final String? requiredPermission;

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

/// A column in an area's drop-down panel (4.3), or a section of Settings.
class MenuGroupSpec {
  const MenuGroupSpec(this.label, this.items, {this.part = MenuPart.settings});

  final String label;
  final List<MenuItemSpec> items;

  /// For a section of Settings, which part of its list it stands in. Ignored
  /// in a drop-down.
  final MenuPart part;
}

/// The three parts of the Settings page's list (backlog 72): the firm's
/// settings as they always were, the lists set up once that the menus used
/// to carry, and what the Admin area held.
enum MenuPart {
  settings('Settings', 'Firm settings.'),
  setUp('Set up', 'Moved here from the menus: set up once, changed rarely.'),
  platform('Platform', 'Moved here from the Admin menu.');

  const MenuPart(this.label, this.note);

  final String label;

  /// Said under a section's heading on the Settings page.
  final String note;
}

/// A column of an area's light drop-down: what is opened every day, named by
/// path. [MenuLayout.returnsAndNotes] stands for the area's short list.
class MenuDailyGroup {
  const MenuDailyGroup(this.label, this.paths);

  final String label;
  final List<String> paths;
}

/// One entry of the menu bar (4.2), or the Settings gear (4.13).
class MenuAreaSpec {
  const MenuAreaSpec(
    this.id,
    this.label,
    this.groups, {
    this.daily = const [],
    this.shortList = const [],
    this.setUp = const [],
  });

  final String id;
  final String label;
  final List<MenuGroupSpec> groups;

  /// The light menu (backlog 72, owner 2026-10-03): the columns the
  /// drop-down shows until "All ... screens" is chosen. Empty shows every
  /// group at once (Home, Reports).
  final List<MenuDailyGroup> daily;

  /// What "Returns & notes" opens beside the daily list.
  final List<String> shortList;

  /// The Settings sections that hold this area's set-up lists, linked from
  /// the foot of its drop-down.
  final List<String> setUp;

  Iterable<MenuItemSpec> get items => groups.expand((group) => group.items);

  /// The item at [path] in this area, or null.
  MenuItemSpec? item(String path) {
    for (final MenuItemSpec item in items) {
      if (item.path == path) return item;
    }
    return null;
  }
}

/// The phase 2 menu: every phase 1 screen, placed as appendix A of
/// `docs/UI_PHASE_2_DESIGN.md` places it.
///
/// **The light menu** (backlog 72, owner 2026-10-03): each drop-down shows
/// only the area's [MenuAreaSpec.daily] list, with "All ... screens" one
/// click away; the lists set up once and the Admin area live on the Settings
/// page behind the gear, under SET UP and PLATFORM. None of it asks the
/// server anything: it is this catalogue cut by the permissions held since
/// sign-in.
///
/// **No screen may be lost** (the owner's rule, 2026-09-25):
/// `test/menu_layout_test.dart` reads the catalogue and fails when a screen
/// appears nowhere here, or twice. Settings that phase 1 opens as dialogs
/// inside other screens (sales stages, credit control, the loyalty scheme, TCS)
/// are not catalogue screens, so the Settings gear lists them as
/// [MenuItemSpec.setting] entries under Selling; each stays in its own
/// screen's "..." menu as well.
abstract final class MenuLayout {
  /// Home's address: a phase 2 screen, drawn by the phase 2 shell itself.
  static const String homeRoute = 'home';

  /// Customer Groups: a phase 2 page, opened in a tab of its own.
  static const String customerGroupsRoute = 'customer-groups';

  /// Payables by supplier and month, checked against control account 2100
  /// (PG-2): a phase 2 page, offered under Buy > Money (a screen sits in one place only).
  static const String payablesRoute = 'payables-by-month';

  /// Backups: a phase 2 page for the platform tier.
  static const String backupsRoute = 'backups';

  /// Branding: the agency's name, tagline and logo (backlog 71, U7), for
  /// whoever holds `PLATFORM_SETTINGS`.
  static const String brandingRoute = 'branding';

  /// The Settings page the gear opens: every section of [settings] in a list,
  /// its items as cards, and a search across them (backlog 72).
  static const String setUpRoute = 'setup';

  /// The Settings page as an item, so its tab has a label and a path.
  static const MenuItemSpec setUpPage =
      MenuItemSpec.phase2(setUpRoute, 'Settings');

  /// In a [MenuDailyGroup], the place of "Returns & notes", which opens the
  /// area's [MenuAreaSpec.shortList] beside the daily list.
  static const String returnsAndNotes = '#returns-and-notes';

  /// The Selling settings behind the gear: dialogs, not screens.
  static const String salesStagesRoute = 'settings/sales-stages';
  static const String creditControlRoute = 'settings/credit-control';
  static const String priceFloorRoute = 'settings/price-floor';
  static const String discountLimitsRoute = 'settings/discount-limits';

  /// Approval in up to three levels by amount (PLT-1). A dialog, under Firm,
  /// because it covers sales and purchase documents alike.
  static const String approvalRulesRoute = 'settings/approval-rules';

  /// Batch rules (backlog 79 row 6): near-expiry window, what dispatch needs
  /// when a batch is left behind or skipped, and the below-floor allowance. A
  /// dialog, under Stock.
  static const String batchRulesRoute = 'settings/batch-rules';

  /// The largest stock adjustment or write-off each role may post directly
  /// (STK-8). A dialog, under Stock.
  static const String adjustmentLimitsRoute = 'settings/adjustment-limits';
  static const String loyaltySchemeRoute = 'settings/loyalty-scheme';
  static const String tcsSettingsRoute = 'settings/tcs';

  /// TDS on purchases under 194Q (ACC-8). A dialog, under Tax.
  static const String tds194qSettingsRoute = 'settings/tds-194q';

  /// The Buying setting behind the gear: the largest order each role may
  /// approve (backlog 68 row 4). A dialog, like the Selling ones.
  static const String approvalLimitsRoute = 'settings/purchase-approval-limits';

  /// Monthly purchase budgets (BUY-14). A dialog, under Buying.
  static const String purchaseBudgetsRoute = 'settings/purchase-budgets';

  /// GST documents (backlog 77.1): e-invoicing dates and the rule for
  /// dispatching a sale before its invoice. A dialog, under Tax.
  static const String gstDocumentsRoute = 'settings/gst-documents';

  /// Messaging (backlog 51): the firm's switch, accounts, events and log.
  static const String messagingRoute = 'settings/messaging';

  /// The person's own usual branch and warehouse (backlog 44): a dialog, and
  /// open to every member of a firm.
  static const String workDefaultsRoute = 'settings/my-branch-warehouse';

  /// My preferences (backlog 73): also on the user menu, and open to
  /// everybody signed in, with or without a firm.
  static const String myPreferencesRoute = 'settings/my-preferences';

  static const MenuAreaSpec home = MenuAreaSpec('home', 'Home', [
    MenuGroupSpec('Home', [MenuItemSpec.phase2(MenuLayout.homeRoute, 'Home')]),
  ]);

  /// Catalogue screens deliberately given no place in the phase 2 menu, and
  /// why. A screen that exists only to say a feature is missing is not
  /// offered; it returns when there is something behind it.
  static const Map<String, String> notOffered = {
    'purchases/purchase-analytics':
        'a placeholder: the backend exposes no purchase analytics yet',
    'masters/branch-warehouse-settings':
        'a placeholder: there are no branch or warehouse settings to change',
  };

  static const List<MenuAreaSpec> areas = [
    home,
    MenuAreaSpec('sell', 'Sell', [
      MenuGroupSpec('Documents', [
        MenuItemSpec(AppModule.sales, 'enquiries', 'Enquiries'),
        MenuItemSpec.module(AppModule.quotations, 'Quotations'),
        MenuItemSpec.module(AppModule.salesOrders, 'Sales Orders'),
        MenuItemSpec(
            AppModule.deliveryNotes, 'delivery-notes', 'Delivery Notes'),
        MenuItemSpec(
            AppModule.salesInvoices, 'sales-invoices', 'Sales Invoices'),
        MenuItemSpec.module(AppModule.salesReturns, 'Sales Returns'),
        MenuItemSpec(AppModule.sales, 'proforma-invoices', 'Proforma'),
        MenuItemSpec(AppModule.sales, 'approvals', 'Approvals'),
        MenuItemSpec(AppModule.sales, 'credit-notes', 'Credit Notes'),
        MenuItemSpec(AppModule.sales, 'customer-debit-notes', 'Debit Notes'),
      ]),
      MenuGroupSpec('Money', [
        MenuItemSpec(AppModule.accounting, 'receipts', 'Receipts'),
        MenuItemSpec(
            AppModule.accounting, 'pdc-received', 'Post-dated Cheques'),
        MenuItemSpec(AppModule.accounting, 'refunds', 'Refunds'),
        MenuItemSpec(
            AppModule.masters, 'customer-statements', 'Customer Statements'),
      ]),
      MenuGroupSpec('Incentives', [
        MenuItemSpec(AppModule.sales, 'commission', 'Commission'),
        MenuItemSpec(AppModule.sales, 'targets', 'Targets'),
      ]),
      MenuGroupSpec('Insight', [
        MenuItemSpec(AppModule.sales, 'sales-analysis', 'Sales Analysis'),
      ]),
      MenuGroupSpec('Field sales', [
        MenuItemSpec(AppModule.sales, 'beat-plans', 'Beat Plans'),
        MenuItemSpec(AppModule.sales, 'call-lists', 'Call Lists'),
        MenuItemSpec(AppModule.sales, 'coverage', 'Coverage'),
      ]),
    ], daily: [
      MenuDailyGroup('Sell', [
        'quotations',
        'salesOrders',
        'deliveryNotes/delivery-notes',
        'salesInvoices/sales-invoices',
        returnsAndNotes,
      ]),
      MenuDailyGroup('Money', [
        'accounting/receipts',
        'masters/customer-statements',
      ]),
    ], shortList: [
      'salesReturns',
      'sales/credit-notes',
      'sales/customer-debit-notes',
    ], setUp: [
      'Pricing',
      'Territories & routes',
    ]),
    MenuAreaSpec('buy', 'Buy', [
      MenuGroupSpec('Documents', [
        MenuItemSpec(
            AppModule.purchases, 'purchase-requisitions', 'Requisitions'),
        MenuItemSpec(AppModule.purchases, 'rfqs', 'Requests for quotation'),
        MenuItemSpec(AppModule.purchases, 'rate-contracts', 'Rate contracts'),
        MenuItemSpec(AppModule.purchases, 'purchase-orders', 'Purchase Orders'),
        MenuItemSpec(AppModule.goodsReceipts, 'receipts', 'Goods Receipts'),
        MenuItemSpec.module(AppModule.purchaseInvoices, 'Purchase Invoices'),
        MenuItemSpec.module(AppModule.purchaseReturns, 'Purchase Returns'),
        MenuItemSpec(AppModule.purchases, 'approvals', 'Approvals'),
        MenuItemSpec(AppModule.purchases, 'debit-notes', 'Debit Notes'),
        MenuItemSpec(
            AppModule.purchases, 'quality-inspection', 'Quality Inspection'),
      ]),
      MenuGroupSpec('Money', [
        MenuItemSpec(AppModule.accounting, 'payments', 'Payments'),
        MenuItemSpec(AppModule.accounting, 'payment-runs', 'Payment Runs'),
        MenuItemSpec.phase2(payablesRoute, 'Payables by Month',
            gate: 'purchaseInvoices'),
        MenuItemSpec(AppModule.accounting, 'pdc-issued', 'Post-dated Cheques'),
        MenuItemSpec(
            AppModule.masters, 'supplier-statements', 'Supplier Statements'),
        MenuItemSpec(AppModule.masters, 'supplier-gifts', 'Supplier Gifts'),
        MenuItemSpec(
            AppModule.purchases, 'supplier-rebates', 'Supplier Rebates'),
        MenuItemSpec(
            AppModule.purchases, 'principal-claims', 'Principal Claims'),
        MenuItemSpec(AppModule.purchases, 'landed-costs', 'Landed Costs'),
      ]),
      MenuGroupSpec('Insight', [
        MenuItemSpec(
            AppModule.purchases, 'purchase-dashboard', 'Purchase Dashboard'),
        MenuItemSpec(
            AppModule.purchases, 'purchase-analysis', 'Purchase Analysis'),
        MenuItemSpec(AppModule.purchases, 'purchase-rate-trend', 'Rate Trend'),
        // Purchase Analytics is left out: its screen only says the backend
        // has no analytics yet (MenuLayout.notOffered).
      ]),
    ], daily: [
      MenuDailyGroup('Buy', [
        'purchases/purchase-orders',
        'goodsReceipts/receipts',
        'purchaseInvoices',
        returnsAndNotes,
      ]),
      MenuDailyGroup('Money', [
        'accounting/payments',
        'masters/supplier-statements',
      ]),
    ], shortList: [
      'purchaseReturns',
      'purchases/debit-notes',
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
        MenuItemSpec(
            AppModule.inventory, 'adjustment-approvals', 'Adjustment Approvals'),
        MenuItemSpec(AppModule.inventory, 'repacking', 'Repacking'),
        MenuItemSpec(AppModule.inventory, 'stock-transfers', 'Stock Transfers'),
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
    ], daily: [
      MenuDailyGroup('Stock', [
        'inventory/stock-summary',
        'inventory/stock-ledger',
        'inventory/stock-transfers',
        'inventory/physical-counts',
      ]),
      MenuDailyGroup('Tracking', [
        'inventory/batches',
        'inventory/expiry-monitor',
      ]),
    ]),
    MenuAreaSpec('accounts', 'Accounts', [
      MenuGroupSpec('Books', [
        MenuItemSpec(
            AppModule.accounting, 'chart-of-accounts', 'Chart of Accounts'),
        MenuItemSpec(
            AppModule.accounting, 'journal-entries', 'Journal Entries'),
        MenuItemSpec(AppModule.accounting, 'expenses', 'Expenses'),
        MenuItemSpec(
            AppModule.accounting, 'opening-balances', 'Opening Balances'),
        MenuItemSpec(AppModule.accounting, 'ledgers', 'Ledgers'),
        MenuItemSpec(
            AppModule.accounting, 'party-adjustments', 'Party Adjustments'),
        MenuItemSpec(
            AppModule.accounting, 'contra-vouchers', 'Contra Vouchers'),
        MenuItemSpec(
            AppModule.accounting, 'bank-reconciliation', 'Bank Reconciliation'),
        MenuItemSpec(AppModule.accounting, 'tally-export', 'Export to Tally'),
      ]),
      MenuGroupSpec('Statements', [
        MenuItemSpec(AppModule.accounting, 'trial-balance', 'Trial Balance'),
        MenuItemSpec(AppModule.accounting, 'profit-loss', 'Profit & Loss'),
        MenuItemSpec(AppModule.accounting, 'cash-flow', 'Cash Flow'),
        MenuItemSpec(AppModule.accounting, 'balance-sheet', 'Balance Sheet'),
      ]),
      MenuGroupSpec('Tax filing', [
        MenuItemSpec(AppModule.sales, 'gst-returns', 'GST Returns'),
        MenuItemSpec(AppModule.sales, 'gstr2b', 'GSTR-2B Reconciliation'),
        MenuItemSpec(AppModule.sales, 'rule37', 'Rule 37 (180 days)'),
        MenuItemSpec(AppModule.sales, 'rule42', 'Rule 42'),
        MenuItemSpec(AppModule.sales, 'gst-checks', 'GST checks'),
        MenuItemSpec(AppModule.sales, 'gst-payment', 'GST Payment'),
        MenuItemSpec(AppModule.sales, 'gst-deposits', 'PMT-06 deposits'),
        MenuItemSpec(AppModule.sales, 'einvoice', 'E-Invoice'),
        MenuItemSpec(AppModule.sales, 'tcs', 'TCS'),
        MenuItemSpec(AppModule.accounting, 'tds-challans', 'TDS Challans'),
        MenuItemSpec(AppModule.accounting, 'bank-details', 'Bank Details'),
      ]),
    ], daily: [
      MenuDailyGroup('Books', [
        'accounting/journal-entries',
        'accounting/expenses',
        'accounting/ledgers',
        'accounting/bank-reconciliation',
      ]),
      MenuDailyGroup('Statements', [
        'accounting/trial-balance',
        'accounting/profit-loss',
        'accounting/balance-sheet',
      ]),
      MenuDailyGroup('Tax', ['sales/gst-returns']),
    ], setUp: [
      'Account structure',
    ]),
    MenuAreaSpec('masters', 'Masters', [
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
      MenuGroupSpec('Compliance', [
        MenuItemSpec(AppModule.masters, 'trade-licences', 'Trade Licences'),
      ]),
    ], daily: [
      MenuDailyGroup('Masters', [
        'masters/customers',
        'masters/vendors',
        'masters/products',
      ]),
      MenuDailyGroup('Organisation', [
        'masters/branches',
        'masters/warehouses',
      ]),
    ], setUp: [
      'Party lists',
      'Item lists',
      'Locations',
    ]),
    MenuAreaSpec('reports', 'Reports', [
      MenuGroupSpec('Reports', [
        MenuItemSpec(AppModule.reports, 'operational', 'Operational'),
        MenuItemSpec(AppModule.reports, 'financial', 'Financial'),
      ]),
    ]),
  ];

  /// Behind the gear, by topic (4.13).
  static const MenuAreaSpec settings = MenuAreaSpec('settings', 'Settings', [
    MenuGroupSpec('This PC and me', [
      MenuItemSpec.setting(myPreferencesRoute, 'My Preferences',
          needsFirm: false),
    ]),
    MenuGroupSpec('Firm', [
      MenuItemSpec(AppModule.masters, 'firm-settings', 'Firm Settings'),
      MenuItemSpec(AppModule.masters, 'financial-years', 'Financial Years'),
      MenuItemSpec(
          AppModule.administration, 'numbering-series', 'Numbering Series'),
      MenuItemSpec(
          AppModule.administration, 'firm-custom-fields', 'Custom Fields'),
      MenuItemSpec(AppModule.administration, 'firm-custom-field-rules',
          'Custom Field Rules'),
      MenuItemSpec.setting(workDefaultsRoute, 'My Branch and Warehouse'),
      MenuItemSpec.setting(messagingRoute, 'Messaging',
          permission: 'SETTINGS_VIEW'),
      MenuItemSpec.setting(approvalRulesRoute, 'Approval Levels',
          permission: 'SETTINGS_VIEW'),
    ]),
    MenuGroupSpec('Selling', [
      MenuItemSpec.setting(salesStagesRoute, 'Sales Stages',
          permission: 'SALES_VIEW'),
      MenuItemSpec.setting(creditControlRoute, 'Credit Control',
          permission: 'CUSTOMER_VIEW'),
      MenuItemSpec.setting(priceFloorRoute, 'Price Floor',
          permission: 'SALES_VIEW'),
      MenuItemSpec.setting(discountLimitsRoute, 'Discount Limits',
          permission: 'SALES_VIEW'),
      MenuItemSpec.setting(loyaltySchemeRoute, 'Loyalty Scheme',
          permission: 'LOYALTY_VIEW'),
      MenuItemSpec.setting(tcsSettingsRoute, 'TCS Settings',
          permission: 'TCS_MANAGE'),
    ]),
    MenuGroupSpec('Buying', [
      MenuItemSpec(
          AppModule.purchases, 'purchase-settings', 'Purchase Settings'),
      MenuItemSpec.setting(approvalLimitsRoute, 'Approval Limits',
          permission: 'PURCHASE_VIEW'),
      MenuItemSpec.setting(purchaseBudgetsRoute, 'Purchase Budgets',
          permission: 'PURCHASE_VIEW'),
    ]),
    MenuGroupSpec('Stock', [
      MenuItemSpec(
          AppModule.inventory, 'inventory-settings', 'Inventory Settings'),
      MenuItemSpec(
          AppModule.inventory, 'adjustment-reasons', 'Adjustment Reasons'),
      MenuItemSpec.setting(adjustmentLimitsRoute, 'Adjustment Limits',
          permission: 'INVENTORY_VIEW'),
      MenuItemSpec.setting(batchRulesRoute, 'Batch Rules',
          permission: 'INVENTORY_VIEW'),
      // Branch & Warehouse Settings is left out (MenuLayout.notOffered).
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
      MenuItemSpec.setting(gstDocumentsRoute, 'GST Documents',
          permission: 'TAX_VIEW'),
      MenuItemSpec.setting(
          tds194qSettingsRoute, 'TDS on purchases (194Q, 194C, 194J)',
          permission: 'ACCOUNT_VIEW'),
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
    // SET UP: the lists the menus carried under CONFIGURATION until the
    // light menu (backlog 72), each section exactly one of those groups.
    MenuGroupSpec('Pricing', [
      MenuItemSpec(AppModule.sales, 'price-lists', 'Price Lists'),
      MenuItemSpec(AppModule.sales, 'price-levels', 'Price Levels'),
      MenuItemSpec(AppModule.sales, 'promotions', 'Promotions'),
      MenuItemSpec(AppModule.masters, 'loyalty', 'Loyalty'),
    ], part: MenuPart.setUp),
    MenuGroupSpec('Territories & routes', [
      MenuItemSpec(AppModule.sales, 'territories', 'Territories'),
      MenuItemSpec(AppModule.sales, 'route-types', 'Route Types'),
      MenuItemSpec(AppModule.sales, 'route-builder', 'Route Builder'),
    ], part: MenuPart.setUp),
    MenuGroupSpec('Account structure', [
      MenuItemSpec(
          AppModule.accounting, 'control-accounts', 'Control Accounts'),
      MenuItemSpec(AppModule.accounting, 'cost-centers', 'Cost Centres'),
      MenuItemSpec(AppModule.accounting, 'profit-centers', 'Profit Centres'),
    ], part: MenuPart.setUp),
    MenuGroupSpec('Party lists', [
      // Master data like vendor categories, not a button on the Customers
      // screen (owner, 2026-09-26).
      MenuItemSpec.phase2(customerGroupsRoute, 'Customer Groups',
          gate: 'masters/customers'),
      MenuItemSpec(AppModule.masters, 'vendor-categories', 'Vendor Categories'),
      MenuItemSpec(AppModule.masters, 'vendor-types', 'Vendor Types'),
      MenuItemSpec(AppModule.masters, 'licence-types', 'Licence Types'),
      MenuItemSpec(
          AppModule.masters, 'licence-check-settings', 'Licence Check'),
    ], part: MenuPart.setUp),
    MenuGroupSpec('Item lists', [
      MenuItemSpec(
          AppModule.masters, 'product-categories', 'Product Categories'),
      MenuItemSpec(AppModule.masters, 'principals', 'Principals'),
      MenuItemSpec(AppModule.masters, 'brands', 'Brands'),
      MenuItemSpec(AppModule.administration, 'uoms', 'Units of Measure'),
      MenuItemSpec(AppModule.administration, 'uom-groups', 'UOM Groups'),
      MenuItemSpec(
          AppModule.administration, 'packaging-types', 'Packaging Types'),
      MenuItemSpec(
          AppModule.administration, 'packaging-levels', 'Packaging Levels'),
      MenuItemSpec(
          AppModule.administration, 'conversion-rules', 'Conversion Rules'),
    ], part: MenuPart.setUp),
    MenuGroupSpec('Locations', [
      MenuItemSpec(AppModule.masters, 'storage-areas', 'Storage Areas'),
      MenuItemSpec(AppModule.masters, 'branch-types', 'Branch Types'),
      MenuItemSpec(AppModule.masters, 'warehouse-types', 'Warehouse Types'),
      MenuItemSpec(AppModule.masters, 'geography-masters', 'Places'),
    ], part: MenuPart.setUp),
    // PLATFORM: what the Admin area held before it left the bar.
    MenuGroupSpec('People', [
      MenuItemSpec(AppModule.administration, 'users', 'Users'),
      MenuItemSpec(AppModule.administration, 'roles', 'Roles'),
      MenuItemSpec(AppModule.administration, 'permissions', 'Permissions'),
      MenuItemSpec(
          AppModule.administration, 'user-templates', 'User Templates'),
      MenuItemSpec(
          AppModule.administration, 'user-firms', 'User-Firm Assignments'),
    ], part: MenuPart.platform),
    MenuGroupSpec('Firms', [
      MenuItemSpec(AppModule.administration, 'firms', 'Firms'),
      MenuItemSpec(
          AppModule.administration, 'business-profiles', 'Business Profiles'),
    ], part: MenuPart.platform),
    MenuGroupSpec('Agency', [
      // The agency's own name, tagline and logo. The permission is the whole
      // gate and it needs no firm: branding belongs to the installation.
      MenuItemSpec.phase2(brandingRoute, 'Branding',
          requiredPermission: 'PLATFORM_SETTINGS'),
    ], part: MenuPart.platform),
    MenuGroupSpec('System', [
      MenuItemSpec(AppModule.settings, 'audit-logs', 'Audit Logs'),
      MenuItemSpec(AppModule.settings, 'diagnostics', 'Diagnostics'),
      MenuItemSpec.module(AppModule.licensing, 'Licensing'),
      // Platform tier only: the permission is the whole gate, and it needs
      // no firm (a backup is of the installation, not of one firm).
      MenuItemSpec.phase2(backupsRoute, 'Backups',
          requiredPermission: 'SYSTEM_BACKUP'),
      // Phase 1's Dashboard: platform-wide counts of firms, users and
      // roles, for a platform administrator. Home is everybody's (4.9).
      MenuItemSpec.module(AppModule.dashboard, 'Platform Dashboard'),
    ], part: MenuPart.platform),
  ]);

  /// Every area, the gear included -- what the command box searches.
  static Iterable<MenuAreaSpec> get all => [...areas, settings];

  /// The item a router path names, for an open-screen tab's label.
  static MenuItemSpec? itemFor(String path) {
    if (path == setUpRoute) return setUpPage;
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
      if (item.isSetting) {
        return (visibility.hasActiveFirm || !item.needsFirm) &&
            (item.permission == MenuItemSpec.noPermission ||
                visibility.permissions.hasPermission(item.permission!));
      }
      if (item.module == null) {
        if (item.requiredPermission != null &&
            !visibility.permissions.hasPermission(item.requiredPermission!)) {
          return false;
        }
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
            part: group.part,
          ),
    ];
    if (groups.isEmpty) return null;
    final Set<String> kept = {
      for (final MenuGroupSpec group in groups)
        for (final MenuItemSpec item in group.items) item.path,
    };
    final List<String> shortList = area.shortList.where(kept.contains).toList();
    bool shown(String path) =>
        path == returnsAndNotes ? shortList.isNotEmpty : kept.contains(path);
    return MenuAreaSpec(
      area.id,
      area.label,
      groups,
      daily: [
        for (final MenuDailyGroup group in area.daily)
          if (group.paths.any(shown))
            MenuDailyGroup(group.label, group.paths.where(shown).toList()),
      ],
      shortList: shortList,
      setUp: area.setUp,
    );
  }
}
