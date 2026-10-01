import 'package:flutter/material.dart';

import '../../models/customer.dart';
import '../../phase2/document_page.dart';

/// One address as the Ship to picker shows it: line one, city and state on a
/// line (backlog 67 row 3).
String shipToSummary(CustomerAddress address) => [
      address.addressLine1,
      address.city,
      address.state,
    ].where((part) => part.trim().isNotEmpty).join(', ');

/// The address a document ships to when nobody picks one: the customer's
/// default shipping address, else the first SHIPPING address, else null.
///
/// Mirrors what the server takes for a null `shipping_address_id`, so the
/// box can be preselected with the answer it would give.
String? defaultShipToId(List<CustomerAddress> addresses) {
  for (final CustomerAddress address in addresses) {
    if (address.isDefaultShipping && address.id.isNotEmpty) return address.id;
  }
  for (final CustomerAddress address in addresses) {
    if (address.addressType.toUpperCase() == 'SHIPPING' &&
        address.id.isNotEmpty) {
      return address.id;
    }
  }
  return null;
}

/// The "Ship to" picker on a sales document: the customer's own addresses,
/// the default marked.
///
/// [blankLabel] adds a first entry meaning "no choice made" (null) -- the
/// invoice's "(as delivered)", where the server inherits the address from
/// the notes billed. [scope] changes whenever the addresses belong to
/// another customer, which is what makes the box start afresh.
class ShipToField extends StatelessWidget {
  const ShipToField({
    super.key,
    required this.scope,
    required this.addresses,
    required this.value,
    required this.onChanged,
    this.enabled = true,
    this.blankLabel,
    this.width = 300,
  });

  final String scope;
  final List<CustomerAddress> addresses;
  final String? value;
  final ValueChanged<String?> onChanged;
  final bool enabled;
  final String? blankLabel;
  final double width;

  @override
  Widget build(BuildContext context) {
    final bool listed = value == null ||
        addresses.any((CustomerAddress address) => address.id == value);
    return DocumentField(
      label: 'Ship to',
      width: width,
      child: DropdownButtonFormField<String?>(
        key: ValueKey<String>('ship-to-$scope-${addresses.length}-$value'),
        initialValue: value,
        isExpanded: true,
        isDense: true,
        decoration: documentBoxDecoration(context),
        items: [
          if (blankLabel != null)
            DropdownMenuItem<String?>(
              value: null,
              child: Text(blankLabel!, overflow: TextOverflow.ellipsis),
            ),
          for (final CustomerAddress address in addresses)
            DropdownMenuItem<String?>(
              value: address.id,
              child: Text(
                '${shipToSummary(address)}'
                '${address.isDefaultShipping ? '  (default)' : ''}',
                overflow: TextOverflow.ellipsis,
              ),
            ),
          if (!listed)
            DropdownMenuItem<String?>(
              value: value,
              child: const Text(
                'On the document, no longer listed',
                overflow: TextOverflow.ellipsis,
              ),
            ),
        ],
        onChanged: enabled ? onChanged : null,
      ),
    );
  }
}
