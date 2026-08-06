import 'entities.dart';

class VendorContact {
  const VendorContact({
    required this.id,
    required this.name,
    required this.department,
    required this.designation,
    required this.phone,
    required this.mobile,
    required this.email,
    required this.isPrimary,
    required this.status,
  });

  final String id;
  final String name;
  final String department;
  final String designation;
  final String phone;
  final String mobile;
  final String email;
  final bool isPrimary;
  final String status;

  factory VendorContact.fromJson(Json json) => VendorContact(
        id: stringValue(json['id']),
        name: stringValue(json['name']),
        department: stringValue(json['department']),
        designation: stringValue(json['designation']),
        phone: stringValue(json['phone']),
        mobile: stringValue(json['mobile']),
        email: stringValue(json['email']),
        isPrimary: boolValue(json['is_primary']),
        status: stringValue(json['status']),
      );

  Json toJson() => {
        if (id.isNotEmpty) 'id': id,
        'name': name,
        'department': department,
        'designation': designation,
        'phone': phone,
        'mobile': mobile,
        'email': email,
        'is_primary': isPrimary,
        'status': status,
      };
}

class VendorAddress {
  const VendorAddress({
    required this.id,
    required this.addressType,
    required this.addressLine1,
    required this.addressLine2,
    required this.countryId,
    required this.stateId,
    required this.districtId,
    required this.cityId,
    required this.postalCodeId,
    required this.localityId,
    required this.isPrimary,
  });

  final String id;
  final String addressType;
  final String addressLine1;
  final String addressLine2;
  final String countryId;
  final String stateId;
  final String districtId;
  final String cityId;
  final String postalCodeId;
  final String localityId;
  final bool isPrimary;

  factory VendorAddress.fromJson(Json json) => VendorAddress(
        id: stringValue(json['id']),
        addressType: stringValue(json['address_type']),
        addressLine1: stringValue(json['address_line1']),
        addressLine2: stringValue(json['address_line2']),
        countryId: stringValue(json['country_id']),
        stateId: stringValue(json['state_id']),
        districtId: stringValue(json['district_id']),
        cityId: stringValue(json['city_id']),
        postalCodeId: stringValue(json['postal_code_id']),
        localityId: stringValue(json['locality_id']),
        isPrimary: boolValue(json['is_primary']),
      );

  Json toJson() => {
        if (id.isNotEmpty) 'id': id,
        'address_type': addressType,
        'address_line1': addressLine1,
        'address_line2': addressLine2,
        if (countryId.isNotEmpty) 'country_id': countryId,
        if (stateId.isNotEmpty) 'state_id': stateId,
        if (districtId.isNotEmpty) 'district_id': districtId,
        if (cityId.isNotEmpty) 'city_id': cityId,
        if (postalCodeId.isNotEmpty) 'postal_code_id': postalCodeId,
        if (localityId.isNotEmpty) 'locality_id': localityId,
        'is_primary': isPrimary,
      };
}

class Vendor {
  const Vendor({
    required this.id,
    required this.firmId,
    required this.code,
    required this.name,
    required this.legalName,
    required this.displayName,
    required this.categoryId,
    required this.typeId,
    required this.status,
    required this.businessProfileId,
    required this.gstRegistration,
    required this.gstin,
    required this.pan,
    required this.licenseNumber,
    required this.registrationNumber,
    required this.website,
    required this.email,
    required this.phone,
    required this.mobile,
    required this.remarks,
    required this.businessAttributes,
    required this.createdAt,
    required this.updatedAt,
    required this.isDeleted,
    required this.contacts,
    required this.addresses,
  });

  final String id;
  final String firmId;
  final String code;
  final String name;
  final String legalName;
  final String displayName;
  final String categoryId;
  final String typeId;
  final String status;
  final String businessProfileId;
  final bool gstRegistration;
  final String gstin;
  final String pan;
  final String licenseNumber;
  final String registrationNumber;
  final String website;
  final String email;
  final String phone;
  final String mobile;
  final String remarks;
  final Json businessAttributes;
  final String createdAt;
  final String updatedAt;
  final bool isDeleted;
  final List<VendorContact> contacts;
  final List<VendorAddress> addresses;

  factory Vendor.fromJson(Json json) => Vendor(
        id: stringValue(json['id']),
        firmId: stringValue(json['firm_id']),
        code: stringValue(json['code']),
        name: stringValue(json['name']),
        legalName: stringValue(json['legal_name']),
        displayName: stringValue(json['display_name']),
        categoryId: stringValue(json['category_id']),
        typeId: stringValue(json['type_id']),
        status: stringValue(json['status']),
        businessProfileId: stringValue(json['business_profile_id']),
        gstRegistration: boolValue(json['gst_registration']),
        gstin: stringValue(json['gstin']),
        pan: stringValue(json['pan']),
        licenseNumber: stringValue(json['license_number']),
        registrationNumber: stringValue(json['registration_number']),
        website: stringValue(json['website']),
        email: stringValue(json['email']),
        phone: stringValue(json['phone']),
        mobile: stringValue(json['mobile']),
        remarks: stringValue(json['remarks']),
        businessAttributes: json['business_attributes'] is Map
            ? Map<String, dynamic>.from(json['business_attributes'] as Map)
            : const {},
        createdAt: stringValue(json['created_at']),
        updatedAt: stringValue(json['updated_at']),
        isDeleted: boolValue(json['is_deleted']),
        contacts:
            _objects(json['contacts']).map(VendorContact.fromJson).toList(),
        addresses:
            _objects(json['addresses']).map(VendorAddress.fromJson).toList(),
      );
}

class VendorQuery {
  const VendorQuery({
    this.status,
    this.categoryId,
    this.typeId,
    this.businessProfileId,
    this.includeDeleted = false,
  });

  final String? status;
  final String? categoryId;
  final String? typeId;
  final String? businessProfileId;
  final bool includeDeleted;

  Map<String, String> toQuery() => {
        if (status?.isNotEmpty == true) 'status': status!,
        if (categoryId?.isNotEmpty == true) 'category_id': categoryId!,
        if (typeId?.isNotEmpty == true) 'type_id': typeId!,
        if (businessProfileId?.isNotEmpty == true)
          'business_profile_id': businessProfileId!,
        if (includeDeleted) 'include_deleted': 'true',
      };
}

List<Json> _objects(dynamic value) => value is List
    ? value
        .whereType<Map>()
        .map((item) => Map<String, dynamic>.from(item))
        .toList()
    : const [];
