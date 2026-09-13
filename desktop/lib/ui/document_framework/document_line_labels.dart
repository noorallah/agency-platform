import '../../core/api/api_client.dart';
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
  });

  final List<Product> products;
  final List<UomRecord> units;
  final List<TaxProfileRecord> taxProfiles;

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
    return DocumentLineLabels(
      products: products,
      units: units,
      taxProfiles: profiles,
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

  /// The tax profile's code for a known profile; the id as given otherwise.
  String taxProfile(String id) {
    if (id.isEmpty) return '';
    for (final TaxProfileRecord profile in taxProfiles) {
      if (profile.id == id) return profile.code;
    }
    return id;
  }
}
