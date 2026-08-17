// A module may only name a `business_modules` code that exists.
//
// The shell hides any module whose code is absent from the firm's active set.
// The desktop named nine codes the backend has never had — `QUOTATIONS`,
// `SALES_ORDERS`, `DELIVERY_NOTES`, `SALES_INVOICES`, `SALES_RETURNS`,
// `GOODS_RECEIPTS`, `PURCHASE_INVOICES`, `PURCHASE_RETURNS` — and a code that
// is absent can never be in the active set, so **all eight document modules
// were hidden in every firm**. A firm could raise and approve a purchase order
// and then have nowhere to receive it; the whole sales document chain was
// unreachable the same way.
//
// `business_modules` is seeded by `20260809_0046` and holds *process* modules.
// A document belongs to the process that owns it: a goods receipt is part of
// PURCHASES, a delivery note part of SALES.

import 'package:agency_desktop/ui/workspace/module_catalog.dart';
import 'package:flutter_test/flutter_test.dart';

/// Every code `20260809_0046_populate_profile_capabilities.py` seeds.
const Set<String> _seededModuleCodes = <String>{
  // _CORE_MODULES
  'DASHBOARD',
  'ADMINISTRATION',
  'SETTINGS',
  'MASTERS',
  'PRODUCTS',
  'PURCHASES',
  'SALES',
  'INVENTORY',
  'REPORTS',
  'ACCOUNTING',
  // PROFILE_MODULES, for the industries that operate them.
  'KITCHEN',
  'RECIPES',
  'PROJECTS',
  'CONTRACTS',
};

/// Modules deliberately gated on a code that does not exist, and so never
/// shown. Licensing has no implementation and is deferred; hiding it is the
/// intent, and it is listed here so it reads as a decision rather than the
/// defect above.
const Set<AppModule> _deliberatelyHidden = <AppModule>{AppModule.licensing};

void main() {
  test('every module names a code the backend actually seeds', () {
    final Map<AppModule, String> unknown = <AppModule, String>{};
    for (final AppModule module in AppModule.values) {
      if (_deliberatelyHidden.contains(module)) continue;
      final String? code = ModuleCatalog.businessModuleCode(module);
      if (code != null && !_seededModuleCodes.contains(code)) {
        unknown[module] = code;
      }
    }

    expect(
      unknown,
      isEmpty,
      reason: 'a code the catalogue does not contain hides the module in '
          'every firm, because it can never be in the active set',
    );
  });

  test('a purchase document is gated by Purchases', () {
    // The chain the user walks: approve an order, then receive it.
    for (final AppModule module in <AppModule>[
      AppModule.purchases,
      AppModule.goodsReceipts,
      AppModule.purchaseInvoices,
      AppModule.purchaseReturns,
    ]) {
      expect(ModuleCatalog.businessModuleCode(module), 'PURCHASES');
    }
  });

  test('a sales document is gated by Sales', () {
    for (final AppModule module in <AppModule>[
      AppModule.sales,
      AppModule.quotations,
      AppModule.salesOrders,
      AppModule.deliveryNotes,
      AppModule.salesInvoices,
      AppModule.salesReturns,
    ]) {
      expect(ModuleCatalog.businessModuleCode(module), 'SALES');
    }
  });

  test('turning a process off still turns its documents off', () {
    // The gate has to keep working, not just stop hiding things. A firm that
    // does not buy should not be offered goods receipts.
    const Set<String> active = <String>{'SALES', 'DASHBOARD'};

    bool offered(AppModule module) {
      final String? code = ModuleCatalog.businessModuleCode(module);
      return code == null || active.contains(code);
    }

    expect(offered(AppModule.goodsReceipts), isFalse);
    expect(offered(AppModule.purchaseInvoices), isFalse);
    expect(offered(AppModule.deliveryNotes), isTrue);
    expect(offered(AppModule.salesReturns), isTrue);
  });
}
