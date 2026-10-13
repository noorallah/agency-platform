// Backlog 129 (M11): the product box on a buying or selling document can be
// narrowed to a supplier's brands, to one brand or to one company's brands.
// It is only a filter on what the box offers -- nothing is stored on the
// document, no payload changes and nothing is refused.

import 'package:flutter/material.dart';

import '../../models/product.dart';
import '../../phase2/document_page.dart';

/// The products of [brandIds], plus every product whose id is in [keepIds].
///
/// [keepIds] is the products already on the document's lines: a
/// `DropdownMenu` whose `initialSelection` is not among its entries shows
/// blank, so a line already typed must never lose its product when the
/// filter changes.
List<Product> productsOfBrands(
  List<Product> products,
  Set<String> brandIds, {
  Set<String> keepIds = const <String>{},
}) =>
    <Product>[
      for (final Product item in products)
        if (keepIds.contains(item.id) || brandIds.contains(item.brandId)) item,
    ];

/// The distinct brands the [products] carry, as (id, name), by name. A
/// product with no brand adds none.
List<(String, String)> brandsOfProducts(Iterable<Product> products) {
  final Map<String, String> found = <String, String>{};
  for (final Product item in products) {
    if (item.brandId.isEmpty) continue;
    found.putIfAbsent(
      item.brandId,
      () => item.brand.isEmpty ? item.brandId : item.brand,
    );
  }
  final List<(String, String)> out = <(String, String)>[
    for (final MapEntry<String, String> entry in found.entries)
      (entry.key, entry.value),
  ]..sort((a, b) => a.$2.toLowerCase().compareTo(b.$2.toLowerCase()));
  return out;
}

/// A compact dropdown labelled "Brand" for a document's header. [options]
/// are (value, words); [value] must be one of them.
class BrandFilterBox extends StatelessWidget {
  const BrandFilterBox({
    super.key,
    required this.options,
    required this.value,
    required this.onChanged,
    this.enabled = true,
    this.width = 240,
  });

  final List<(String, String)> options;
  final String value;
  final ValueChanged<String> onChanged;
  final bool enabled;
  final double width;

  @override
  Widget build(BuildContext context) => DocumentField(
        label: 'Brand',
        width: width,
        child: DropdownButtonFormField<String>(
          // Built again when the options change: the field reads its value
          // only once.
          key: ValueKey<String>('brand-filter-box-${options.length}-$value'),
          isExpanded: true,
          isDense: true,
          initialValue: options.any((item) => item.$1 == value) ? value : null,
          decoration: documentBoxDecoration(context),
          items: [
            for (final (String id, String label) in options)
              DropdownMenuItem<String>(
                value: id,
                child: Text(label, overflow: TextOverflow.ellipsis),
              ),
          ],
          onChanged: enabled
              ? (next) {
                  if (next != null) onChanged(next);
                }
              : null,
        ),
      );
}

/// The Brand box's value for "Every product" on a buying document: the
/// supplier's limit lifted.
const String everyProductChoice = '*';

/// The value of the Brand box's company entries on a sales document.
const String companyChoicePrefix = 'company:';

/// The Brand box's options on a sales document: all products, then one entry
/// per company (a company name, then "(all its brands)"), then each brand. Only a brand
/// or company that at least one of the [products] carries is offered. With no
/// [brands] read there are no company entries and the brands come from the
/// products themselves.
List<(String, String)> salesBrandOptions(
  List<Product> products,
  List<BrandRecord> brands,
) {
  final List<(String, String)> own = brandsOfProducts(products);
  final Set<String> carried = <String>{for (final (String id, _) in own) id};
  final Map<String, String> companies = <String, String>{};
  for (final BrandRecord brand in brands) {
    if (brand.principalId.isEmpty || !carried.contains(brand.id)) continue;
    companies.putIfAbsent(
      brand.principalId,
      () => brand.principalName.isEmpty
          ? brand.principalId
          : brand.principalName,
    );
  }
  final List<MapEntry<String, String>> ordered = companies.entries.toList()
    ..sort((a, b) => a.value.toLowerCase().compareTo(b.value.toLowerCase()));
  return <(String, String)>[
    ('', 'All products'),
    for (final MapEntry<String, String> company in ordered)
      (
        '$companyChoicePrefix${company.key}',
        '${company.value} (all its brands)',
      ),
    ...own,
  ];
}

/// The [products] a sales document's product box offers for [choice] (blank
/// is every product, `company:` and a company id, its brands, anything else one
/// brand's id). [keepIds] are the products already on a line.
List<Product> productsForSalesChoice(
  String choice,
  List<Product> products,
  List<BrandRecord> brands, {
  Set<String> keepIds = const <String>{},
}) {
  if (choice.isEmpty) return products;
  final Set<String> brandIds = choice.startsWith(companyChoicePrefix)
      ? <String>{
          for (final BrandRecord brand in brands)
            if (brand.principalId ==
                choice.substring(companyChoicePrefix.length))
              brand.id,
        }
      : <String>{choice};
  return productsOfBrands(products, brandIds, keepIds: keepIds);
}
