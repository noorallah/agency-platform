import '../../core/security/permission_service.dart';
import '../../models/sales_invoice.dart';
import 'module_catalog.dart';

/// Who is offered which modules and tabs, as a pure function.
///
/// This lived inside `DesktopShell` as a chain of `.where` clauses over
/// private fields, which meant **nothing could test it**: no test in the suite
/// instantiates the shell, so each predicate was spot-checked in isolation for
/// one or two modules while the composed answer across 18 modules and 86 tabs
/// was never exercised. That is how a firm administrator came to be offered a
/// Dashboard the server refuses, on the page the app lands on.
///
/// Pulling it out changes no behaviour. It makes the rules addressable, so a
/// test can ask "what does a sales executive see" and get the same answer the
/// running application gives.
///
/// **The four module gates are not interchangeable and the order matters for
/// the explanation, not the result:** a platform-admin module is refused for a
/// reason no permission list can express, so it is asked first and its denial
/// reads correctly.
class ModuleVisibility {
  const ModuleVisibility({
    required this.permissions,
    this.activeBusinessModules,
    this.salesStages = SalesWorkflowSettings.wholeChain,
  });

  final PermissionService permissions;

  /// Business module codes this firm has switched on, or null while unknown.
  ///
  /// Null is **show everything**, deliberately: the codes are fetched from the
  /// server, and a failed fetch must not empty the sidebar. Hiding a firm's
  /// whole application because one request timed out is worse than briefly
  /// offering a module it has turned off.
  final Set<String>? activeBusinessModules;

  /// Which stages of a sale this firm types by hand.
  final SalesWorkflowSettings salesStages;

  /// Every module this user may open, in catalogue order.
  List<ModuleDefinition> get modules =>
      ModuleCatalog.modules.where(allows).toList();

  /// Whether one module is offered, and nothing about why.
  bool allows(ModuleDefinition module) => denial(module) == null;

  /// Why a module is not offered, or null when it is.
  ///
  /// Returned as a sentence rather than a bool so a test, a report or a
  /// support conversation can say which gate refused it. "Finance is missing"
  /// and "Finance needs ACCOUNT_VIEW, which this role does not hold" are very
  /// different pieces of information.
  String? denial(ModuleDefinition module) {
    if (module.requiresPlatformAdmin && !permissions.isPlatformAdmin) {
      return 'platform administrators only';
    }
    if (!permissions.canUseModule(
      module.requiredPermissions,
      requiresAny: module.requiresAnyPermission,
    )) {
      final List<String> missing = module.requiredPermissions
          .where((code) => !permissions.hasPermission(code))
          .toList();
      final String how =
          module.requiresAnyPermission ? 'needs any of' : 'needs all of';
      return '$how ${missing.join(', ')}';
    }
    if (!_enabledByBusinessProfile(module)) {
      return 'this firm has switched the module off';
    }
    if (!_typedByThisFirm(module)) {
      return 'this firm does not type this stage of a sale';
    }
    return null;
  }

  /// The tabs of one module this user may open.
  ///
  /// A tab naming no permissions **inherits the module's list and its any/all
  /// flag**, which is why a module gate is not enough on its own.
  ///
  /// The platform-admin gate is applied here too. It was not, and while that
  /// is harmless today -- the only such module has no tabs -- the next one
  /// with tabs would have leaked every one of them to anybody who satisfied
  /// the module's permission list.
  Set<String> tabIds(ModuleDefinition module) {
    if (!allows(module)) {
      return const {};
    }
    return module.tabs
        .where((tab) => tab.available)
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
        .map((tab) => tab.id)
        .toSet();
  }

  bool _enabledByBusinessProfile(ModuleDefinition module) {
    final Set<String>? configured = activeBusinessModules;
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
  bool _typedByThisFirm(ModuleDefinition module) => switch (module.id) {
        AppModule.quotations => salesStages.quotationStage,
        AppModule.salesOrders => salesStages.salesOrderStage,
        AppModule.deliveryNotes => salesStages.deliveryNoteStage,
        _ => true,
      };
}
