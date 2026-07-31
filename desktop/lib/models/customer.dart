import 'entities.dart';

class CustomerAddress {
  const CustomerAddress({
    required this.id,
    required this.addressType,
    required this.addressLine1,
    required this.addressLine2,
    required this.area,
    required this.city,
    required this.district,
    required this.state,
    required this.country,
    required this.postalCode,
    required this.isDefaultBilling,
    required this.isDefaultShipping,
  });

  final String id;
  final String addressType;
  final String addressLine1;
  final String addressLine2;
  final String area;
  final String city;
  final String district;
  final String state;
  final String country;
  final String postalCode;
  final bool isDefaultBilling;
  final bool isDefaultShipping;

  factory CustomerAddress.fromJson(Json json) => CustomerAddress(
        id: stringValue(json['id']),
        addressType: stringValue(json['address_type']),
        addressLine1: stringValue(json['address_line1']),
        addressLine2: stringValue(json['address_line2']),
        area: stringValue(json['area']),
        city: stringValue(json['city']),
        district: stringValue(json['district']),
        state: stringValue(json['state']),
        country: stringValue(json['country']),
        postalCode: stringValue(json['postal_code']),
        isDefaultBilling: boolValue(json['is_default_billing']),
        isDefaultShipping: boolValue(json['is_default_shipping']),
      );

  Json toJson() => {
        if (id.isNotEmpty) 'id': id,
        'address_type': addressType,
        'address_line1': addressLine1,
        'address_line2': addressLine2,
        'area': area,
        'city': city,
        'district': district,
        'state': state,
        'country': country,
        'postal_code': postalCode,
        'is_default_billing': isDefaultBilling,
        'is_default_shipping': isDefaultShipping,
      };
}

class CustomerContact {
  const CustomerContact({
    required this.id,
    required this.name,
    required this.designation,
    required this.mobile,
    required this.email,
    required this.department,
    required this.isPrimary,
  });

  final String id;
  final String name;
  final String designation;
  final String mobile;
  final String email;
  final String department;
  final bool isPrimary;

  factory CustomerContact.fromJson(Json json) => CustomerContact(
        id: stringValue(json['id']),
        name: stringValue(json['name']),
        designation: stringValue(json['designation']),
        mobile: stringValue(json['mobile']),
        email: stringValue(json['email']),
        department: stringValue(json['department']),
        isPrimary: boolValue(json['is_primary']),
      );

  Json toJson() => {
        if (id.isNotEmpty) 'id': id,
        'name': name,
        'designation': designation,
        'mobile': mobile,
        'email': email,
        'department': department,
        'is_primary': isPrimary,
      };
}

class Customer {
  const Customer({
    required this.id,
    required this.firmId,
    required this.code,
    required this.customerType,
    required this.name,
    required this.displayName,
    required this.gstNumber,
    required this.panNumber,
    required this.email,
    required this.phone,
    required this.alternatePhone,
    required this.website,
    required this.creditLimit,
    required this.openingBalance,
    required this.paymentTermsDays,
    required this.currencyCode,
    required this.status,
    required this.notes,
    required this.createdBy,
    required this.createdAt,
    required this.updatedBy,
    required this.updatedAt,
    required this.isDeleted,
    required this.addresses,
    required this.contacts,
  });

  final String id;
  final String firmId;
  final String code;
  final String customerType;
  final String name;
  final String displayName;
  final String gstNumber;
  final String panNumber;
  final String email;
  final String phone;
  final String alternatePhone;
  final String website;
  final String creditLimit;
  final String openingBalance;
  final int paymentTermsDays;
  final String currencyCode;
  final String status;
  final String notes;
  final String createdBy;
  final String createdAt;
  final String updatedBy;
  final String updatedAt;
  final bool isDeleted;
  final List<CustomerAddress> addresses;
  final List<CustomerContact> contacts;

  String get city {
    final Iterable<CustomerAddress> defaults =
        addresses.where((address) => address.isDefaultBilling);
    if (defaults.isNotEmpty) return defaults.first.city;
    return addresses.isEmpty ? '' : addresses.first.city;
  }

  factory Customer.fromJson(Json json) => Customer(
        id: stringValue(json['id']),
        firmId: stringValue(json['firm_id']),
        code: stringValue(json['code']),
        customerType: stringValue(json['customer_type']),
        name: stringValue(json['name']),
        displayName: stringValue(json['display_name']),
        gstNumber: stringValue(json['gst_number']),
        panNumber: stringValue(json['pan_number']),
        email: stringValue(json['email']),
        phone: stringValue(json['phone']),
        alternatePhone: stringValue(json['alternate_phone']),
        website: stringValue(json['website']),
        creditLimit: stringValue(json['credit_limit']).isEmpty
            ? '0.00'
            : stringValue(json['credit_limit']),
        openingBalance: stringValue(json['opening_balance']).isEmpty
            ? '0.00'
            : stringValue(json['opening_balance']),
        paymentTermsDays: (json['payment_terms_days'] as num?)?.toInt() ?? 0,
        currencyCode: stringValue(json['currency_code']),
        status: stringValue(json['status']),
        notes: stringValue(json['notes']),
        createdBy: stringValue(json['created_by']),
        createdAt: stringValue(json['created_at']),
        updatedBy: stringValue(json['updated_by']),
        updatedAt: stringValue(json['updated_at']),
        isDeleted: boolValue(json['is_deleted']),
        addresses:
            _objects(json['addresses']).map(CustomerAddress.fromJson).toList(),
        contacts:
            _objects(json['contacts']).map(CustomerContact.fromJson).toList(),
      );
}

List<Json> _objects(dynamic value) => value is List
    ? value
        .whereType<Map>()
        .map((item) => Map<String, dynamic>.from(item))
        .toList()
    : const [];

class CustomerQuery {
  const CustomerQuery({
    this.status,
    this.customerType,
    this.city,
    this.state,
    this.createdFrom,
    this.createdTo,
    this.includeDeleted = false,
  });

  final String? status;
  final String? customerType;
  final String? city;
  final String? state;
  final String? createdFrom;
  final String? createdTo;
  final bool includeDeleted;

  Map<String, String> toQuery() => {
        if (status?.isNotEmpty == true) 'status': status!,
        if (customerType?.isNotEmpty == true) 'customer_type': customerType!,
        if (city?.isNotEmpty == true) 'city': city!,
        if (state?.isNotEmpty == true) 'state': state!,
        if (createdFrom?.isNotEmpty == true) 'created_from': createdFrom!,
        if (createdTo?.isNotEmpty == true) 'created_to': createdTo!,
        if (includeDeleted) 'include_deleted': 'true',
      };
}
