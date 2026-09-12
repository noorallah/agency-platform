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
