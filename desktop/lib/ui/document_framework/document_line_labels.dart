import '../../core/api/api_client.dart';
import '../../models/branch_warehouse.dart';
import '../../models/product.dart';
import '../../models/tax_framework.dart';
import '../../models/uom_packaging.dart';

/// What a document view prints for the ids a line carries.
///
/// A line response names its product, unit and tax profile by id, and the
/// document views printed those ids -- a goods receipt read as a column of
/// UUIDs. Every workspace already reads the firm's products for its editor;
/// this resolves each id against those lists, and falls back to the id
/// itself for one the lists do not hold, so a stale list never blanks a
/// line. Shared by every document view rather than written per screen.
class DocumentLineLabels {
  const DocumentLineLabels({
    this.products = const <Product>[],
    this.units = const <UomRecord>[],
    this.taxProfiles = const <TaxProfileRecord>[],
    this.branches = const <BranchRecord>[],
    this.warehouses = const <WarehouseRecord>[],
  });

  final List<Product> products;
  final List<UomRecord> units;
  final List<TaxProfileRecord> taxProfiles;

  /// For the header: where the document was raised and ships from. The
  /// sales order view printed '-' under Warehouse for every order because it
  /// was never told, which read as an order with no warehouse (D-QA-17).
  final List<BranchRecord> branches;
  final List<WarehouseRecord> warehouses;

  /// Read the three lists a view resolves ids against.
  ///
  /// Each is read on its own and a failure costs only that list's names --
  /// the line then prints the id, never nothing. The sales order and sales
  /// invoice views never loaded these at all and printed a column of UUIDs
  /// (plan section 9, 2026-09-13).
  static Future<DocumentLineLabels> load(ApiClient api) async {
    List<Product> products = const <Product>[];
    List<UomRecord> units = const <UomRecord>[];
    List<TaxProfileRecord> profiles = const <TaxProfileRecord>[];
    List<BranchRecord> branches = const <BranchRecord>[];
    List<WarehouseRecord> warehouses = const <WarehouseRecord>[];
    try {
      products = (await api.products(page: 1, pageSize: 100)).items;
    } on ApiException {
      // A name falls back to its id.
    }
    try {
      units = await api.uoms(includeInactive: true);
    } on ApiException {
      // As above.
    }
    try {
      profiles = (await api.taxProfiles(page: 1, pageSize: 100)).items;
    } on ApiException {
      // As above.
    }
    try {
      branches = (await api.branches(page: 1, pageSize: 100)).items;
    } on ApiException {
      // As above.
    }
    try {
      warehouses = (await api.warehouses(page: 1, pageSize: 100)).items;
    } on ApiException {
      // As above.
    }
    return DocumentLineLabels(
      products: products,
      units: units,
      taxProfiles: profiles,
      branches: branches,
      warehouses: warehouses,
    );
  }

  /// `CODE — Name` for a known product; the id as given otherwise.
  String product(String id) {
    if (id.isEmpty) return '';
    for (final Product product in products) {
      if (product.id == id) return '${product.code} — ${product.name}';
    }
    return id;
  }

  /// The unit's code for a known unit; the id as given otherwise.
  String unit(String id) {
    if (id.isEmpty) return '';
    for (final UomRecord unit in units) {
      if (unit.id == id) return unit.code;
    }
    return id;
  }

  /// The unit a line is in: its own where it names one, else its product's.
  ///
  /// A sales line names a unit only when it was typed in a unit other than
  /// the product's own, so an ordinary line carries none and the views
  /// printed '-' under Unit for every sales order, delivery note and bill
  /// (D-UI-98). The product's selling unit is the one it was sold in; its
  /// stock unit, then its base unit, then the unit typed on the product as
  /// words stand in where no selling unit is set.
  String unitOf(String lineUnitId, String productId) {
    if (lineUnitId.isNotEmpty) return unit(lineUnitId);
    for (final Product product in products) {
      if (product.id != productId) continue;
      for (final String id in <String>[
        product.salesUomId,
        product.inventoryUomId,
        product.baseUomId,
      ]) {
        if (id.isNotEmpty) return unit(id);
      }
      return product.displayUnit;
    }
    return '';
  }

  /// The tax profile's code for a known profile; the id as given otherwise.
  String taxProfile(String id) {
    if (id.isEmpty) return '';
    for (final TaxProfileRecord profile in taxProfiles) {
      if (profile.id == id) return profile.code;
    }
    return id;
  }

  /// `CODE - Name` for a known branch; the id as given otherwise.
  String branch(String id) {
    if (id.isEmpty) return '';
    for (final BranchRecord branch in branches) {
      if (branch.id == id) return '${branch.code} - ${branch.displayName}';
    }
    return id;
  }

  /// `CODE - Name` for a known warehouse; the id as given otherwise.
  String warehouse(String id) {
    if (id.isEmpty) return '';
    for (final WarehouseRecord warehouse in warehouses) {
      if (warehouse.id == id) {
        return '${warehouse.code} - ${warehouse.displayName}';
      }
    }
    return id;
  }
}
