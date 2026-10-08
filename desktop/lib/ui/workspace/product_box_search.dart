// A document line's product box finds a product by a pack's code (backlog
// 89, market gap 3). The box filters the entries it was given on their
// label, which holds the product's name, code and own barcode -- so a carton
// label scanned into it matched nothing. These two callbacks keep the
// label match and add the codes of the product's packs, and put the
// highlight on the one product a pack's code leaves, so the Enter a scanner
// sends picks it.

import 'package:flutter/material.dart';

import '../../models/product.dart';

/// The entries whose label holds [filter], and those of a product one of
/// whose packs carries a code holding it. Entries are keyed by product id.
List<DropdownMenuEntry<String>> productEntriesMatching(
  List<DropdownMenuEntry<String>> entries,
  String filter,
  Iterable<Product> products,
) {
  final String wanted = filter.trim().toLowerCase();
  if (wanted.isEmpty) return entries;
  final Set<String> byPack = <String>{
    for (final Product item in products)
      if (item.packCodes.any((code) => code.toLowerCase().contains(wanted)))
        item.id,
  };
  return <DropdownMenuEntry<String>>[
    for (final DropdownMenuEntry<String> entry in entries)
      if (entry.label.toLowerCase().contains(wanted) ||
          byPack.contains(entry.value))
        entry,
  ];
}

/// Which of the filtered [entries] Enter picks: the first whose label holds
/// [query], as the box does by itself, else the first one a pack's code
/// left in the list.
int? productEntryToHighlight(
  List<DropdownMenuEntry<String>> entries,
  String query,
) {
  final String wanted = query.trim().toLowerCase();
  if (wanted.isEmpty || entries.isEmpty) return null;
  final int index =
      entries.indexWhere((entry) => entry.label.toLowerCase().contains(wanted));
  return index < 0 ? 0 : index;
}
