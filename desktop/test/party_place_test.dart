import 'package:agency_desktop/models/customer.dart';
import 'package:agency_desktop/models/settlement.dart';
import 'package:agency_desktop/models/vendor.dart';
import 'package:agency_desktop/ui/workspace/party_place.dart';
import 'package:flutter_test/flutter_test.dart';

/// Two shops of one name are told apart by their area and city wherever a
/// customer or a supplier is picked (first customer, S3).
void main() {
  Customer customer(List<Map<String, dynamic>> addresses) => Customer.fromJson({
        'id': 'c-1',
        'code': 'C001',
        'name': 'Sri Balaji Medicals',
        'display_name': 'Sri Balaji Medicals',
        'addresses': addresses,
      });

  Vendor vendor(List<Map<String, dynamic>> addresses) => Vendor.fromJson({
        'id': 'v-1',
        'code': 'V001',
        'name': 'Sri Balaji Agencies',
        'display_name': 'Sri Balaji Agencies',
        'addresses': addresses,
      });

  test('a place is the area and the city, with nothing blank or twice', () {
    expect(placeText('Abids', 'Hyderabad'), 'Abids, Hyderabad');
    expect(placeText('', 'Hyderabad'), 'Hyderabad');
    expect(placeText(' Abids ', ''), 'Abids');
    expect(placeText('Guntur', 'guntur'), 'Guntur');
    expect(placeText('', ''), '');
  });

  test('a line carries its place, and stands alone without one', () {
    expect(withPlace('Sri Balaji — C001', 'Abids, Hyderabad'),
        'Sri Balaji — C001 · Abids, Hyderabad');
    expect(withPlace('Sri Balaji — C001', ''), 'Sri Balaji — C001');
  });

  test('a customer is placed by the default billing address', () {
    expect(customerPlace(customer(const [])), '');
    expect(
      customerPlace(customer([
        {'id': 'a-1', 'area': 'Koti', 'city': 'Hyderabad'},
        {
          'id': 'a-2',
          'area': 'Abids',
          'city': 'Hyderabad',
          'is_default_billing': true,
        },
      ])),
      'Abids, Hyderabad',
    );
    expect(
      customerPlace(customer([
        {'id': 'a-1', 'area': null, 'city': 'Vijayawada'},
      ])),
      'Vijayawada',
    );
  });

  test('a supplier is placed by the names the server sends', () {
    expect(vendorPlace(vendor(const [])), '');
    final Vendor placed = vendor([
      {'id': 'a-1', 'address_line1': 'x', 'city_id': 'city-9'},
      {
        'id': 'a-2',
        'address_line1': 'y',
        'city_id': 'city-1',
        'locality_id': 'loc-1',
        'city': 'Secunderabad',
        'area': 'Kavadiguda',
        'is_primary': true,
      },
    ]);
    expect(vendorPlace(placed), 'Kavadiguda, Secunderabad');
    // Ids alone name nothing: no place rather than an id on the screen.
    expect(
      vendorPlace(vendor([
        {'id': 'a-1', 'address_line1': 'x', 'city_id': 'city-9'},
      ])),
      '',
    );
  });

  test('the names are never sent back with a supplier address', () {
    final VendorAddress address = VendorAddress.fromJson({
      'id': 'a-2',
      'address_type': 'BILLING',
      'address_line1': 'y',
      'city_id': 'city-1',
      'city': 'Secunderabad',
      'area': 'Kavadiguda',
    });
    expect(address.city, 'Secunderabad');
    // The server forbids unknown fields; one stray key fails the save.
    expect(address.toJson().keys, isNot(contains('city')));
    expect(address.toJson().keys, isNot(contains('area')));
  });

  test('the money picker says the place after the code and the name', () {
    const PartyOption bare =
        PartyOption(id: '1', code: 'C001', name: 'Sri Balaji Medicals');
    const PartyOption placed = PartyOption(
      id: '2',
      code: 'C002',
      name: 'Sri Balaji Medicals',
      place: 'Abids, Hyderabad',
    );
    expect(bare.label, 'C001  Sri Balaji Medicals');
    expect(placed.label, 'C002  Sri Balaji Medicals · Abids, Hyderabad');
  });
}
