import '../../models/customer.dart';
import '../../models/vendor.dart';

/// Where a customer or a supplier is, in the two words that tell two shops
/// of one name apart: the area and the city (first customer, S3).
///
/// **For screens only.** A picker and a list show it beside the name; a
/// print, an export and anything sent to the party never do -- there the
/// address is printed whole or not at all.

/// "Area, City", leaving out what is blank and never saying a place twice.
String placeText(String area, String city) {
  final List<String> parts = [
    for (final String part in [area.trim(), city.trim()])
      if (part.isNotEmpty) part,
  ];
  if (parts.length == 2 && parts[0].toLowerCase() == parts[1].toLowerCase()) {
    return parts[0];
  }
  return parts.join(', ');
}

/// The customer's place: the default billing address, or the first one.
String customerPlace(Customer customer) {
  if (customer.addresses.isEmpty) return '';
  final CustomerAddress address = customer.addresses.firstWhere(
    (item) => item.isDefaultBilling,
    orElse: () => customer.addresses.first,
  );
  return placeText(address.area, address.city);
}

/// The supplier's place: the primary address, or the first one. The names
/// are the server's, read from the geography masters behind the ids.
String vendorPlace(Vendor vendor) {
  if (vendor.addresses.isEmpty) return '';
  final VendorAddress address = vendor.addresses.firstWhere(
    (item) => item.isPrimary,
    orElse: () => vendor.addresses.first,
  );
  return placeText(address.area, address.city);
}

/// A picker's line with the place after it; the line alone where the party
/// has no address, so nothing dangles.
String withPlace(String label, String place) =>
    place.isEmpty ? label : '$label · $place';
