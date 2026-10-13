import 'entities.dart';
import 'product.dart';

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
    this.city = '',
    this.area = '',
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

  /// The names behind [cityId] and [localityId], as the server read them
  /// from the geography masters. For a picker to tell two suppliers of one
  /// name apart; never sent back, the address is written by its ids.
  final String city;
  final String area;

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
        city: stringValue(json['city']),
        area: stringValue(json['area']),
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

/// One bank account money is paid into.
class VendorBankAccount {
  const VendorBankAccount({
    required this.id,
    required this.bankName,
    required this.accountName,
    required this.accountNumber,
    required this.ifsc,
    required this.branch,
    required this.upiId,
    required this.swiftCode,
    required this.isPrimary,
  });

  final String id;
  final String bankName;
  final String accountName;
  final String accountNumber;
  final String ifsc;
  final String branch;
  final String upiId;
  final String swiftCode;
  final bool isPrimary;

  factory VendorBankAccount.fromJson(Json json) => VendorBankAccount(
        id: stringValue(json['id']),
        bankName: stringValue(json['bank_name']),
        accountName: stringValue(json['account_name']),
        accountNumber: stringValue(json['account_number']),
        ifsc: stringValue(json['ifsc']),
        branch: stringValue(json['branch']),
        upiId: stringValue(json['upi_id']),
        swiftCode: stringValue(json['swift_code']),
        isPrimary: boolValue(json['is_primary']),
      );

  Json toJson() => {
        if (id.isNotEmpty) 'id': id,
        'bank_name': bankName,
        'account_name': accountName,
        'account_number': accountNumber,
        'ifsc': ifsc.isEmpty ? null : ifsc,
        'branch': branch.isEmpty ? null : branch,
        'upi_id': upiId.isEmpty ? null : upiId,
        'swift_code': swiftCode.isEmpty ? null : swiftCode,
        'is_primary': isPrimary,
      };
}

/// One set of a vendor's registrations.
///
/// The vendor record carries a `gstin` and a `pan` of its own; these rows are
/// the per-registration detail — a vendor trading from two states has two
/// GSTINs, and only one of them is primary.
class VendorTaxDetail {
  const VendorTaxDetail({
    required this.id,
    required this.gstin,
    required this.pan,
    required this.tan,
    required this.fssai,
    required this.drugLicense,
    required this.importExportCode,
    required this.isPrimary,
  });

  final String id;
  final String gstin;
  final String pan;
  final String tan;
  final String fssai;
  final String drugLicense;
  final String importExportCode;
  final bool isPrimary;

  factory VendorTaxDetail.fromJson(Json json) => VendorTaxDetail(
        id: stringValue(json['id']),
        gstin: stringValue(json['gstin']),
        pan: stringValue(json['pan']),
        tan: stringValue(json['tan']),
        fssai: stringValue(json['fssai']),
        drugLicense: stringValue(json['drug_license']),
        importExportCode: stringValue(json['import_export_code']),
        isPrimary: boolValue(json['is_primary']),
      );

  Json toJson() => {
        if (id.isNotEmpty) 'id': id,
        'gstin': gstin.isEmpty ? null : gstin,
        'pan': pan.isEmpty ? null : pan,
        'tan': tan.isEmpty ? null : tan,
        'fssai': fssai.isEmpty ? null : fssai,
        'drug_license': drugLicense.isEmpty ? null : drugLicense,
        'import_export_code':
            importExportCode.isEmpty ? null : importExportCode,
        'is_primary': isPrimary,
      };
}

/// One note kept against a vendor.
class VendorNote {
  const VendorNote({
    required this.id,
    required this.note,
    required this.noteType,
  });

  final String id;
  final String note;
  final String noteType;

  factory VendorNote.fromJson(Json json) => VendorNote(
        id: stringValue(json['id']),
        note: stringValue(json['note']),
        noteType: stringValue(json['note_type']),
      );

  Json toJson() => {
        if (id.isNotEmpty) 'id': id,
        'note': note,
        'note_type': noteType.isEmpty ? 'GENERAL' : noteType,
      };
}

/// One vendor category or type -- the two masters a vendor record points at.
///
/// The same four columns serve both, so one record does: they differ only in
/// which table they live in and which field on `vendors` names them.
class VendorClassification {
  const VendorClassification({
    required this.id,
    required this.code,
    required this.name,
    required this.description,
    required this.isActive,
  });

  final String id, code, name, description;
  final bool isActive;

  factory VendorClassification.fromJson(Json json) => VendorClassification(
        id: stringValue(json['id']),
        code: stringValue(json['code']),
        name: stringValue(json['name']),
        description: stringValue(json['description']),
        isActive: boolValue(json['is_active'], fallback: true),
      );
}

/// The GST types a supplier can be declared as (backlog 78 row 2), in the
/// order the form offers them, each with the sentence that says what it means.
const Map<String, String> vendorGstTypeLabels = {
  'REGULAR': 'Registered, charges GST',
  'COMPOSITION': 'Composition dealer: bill of supply, no GST, no credit',
  'UNREGISTERED': 'No GST registration: charges no GST',
  'OVERSEAS': 'Supplier outside India: IGST is paid at customs',
  'SEZ': 'Unit in a Special Economic Zone',
};

/// A type as one word: Regular, Composition, Unregistered, Overseas, SEZ.
String vendorGstTypeName(String type) =>
    type == 'SEZ' ? 'SEZ' : type[0] + type.substring(1).toLowerCase();

/// What a blank type reads as: not a declaration, so it changes no tax.
const String vendorGstTypeNotSet = 'Not set (read from the GSTIN)';

/// The types whose bills carry no GST, so the bill editor can say so.
const Set<String> vendorGstTypesChargingNoGst = {
  'COMPOSITION',
  'UNREGISTERED',
  'OVERSEAS',
};

/// Currencies a supplier is commonly billed in; any other ISO code is typed.
const List<String> commonCurrencyCodes = [
  'USD',
  'EUR',
  'GBP',
  'AED',
  'SGD',
  'JPY',
  'CNY',
  'AUD',
];

class Vendor {
  const Vendor({
    required this.id,
    this.version = 0,
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
    this.gstRegistrationType,
    required this.gstin,
    required this.pan,
    this.blockedReason = '',
    this.paymentTermsDays = 0,
    this.currencyCode = '',
    this.standingDiscountPercent = 0,
    this.udyamNumber = '',
    this.msmeCategory = '',
    this.defaultTdsSection = '',
    this.tdsIndividualHuf,
    this.tdsTechnicalServices = false,
    this.tdsApplicable = true,
    this.msmeWrittenAgreement = false,
    this.issuesEInvoices = false,
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
    this.bankAccounts = const [],
    this.taxDetails = const [],
    this.notes = const [],
    this.attributes = const [],
    this.parentVendorId,
    this.parentCode,
    this.parentName,
    this.branchCount = 0,
    this.gstinFromParent = false,
  });

  final String id;

  /// True when [gstin] is the main office's, copied by the server.
  final bool gstinFromParent;

  /// The main office this supplier is a branch of, or null for a supplier on
  /// its own.
  final String? parentVendorId;
  final String? parentCode;
  final String? parentName;

  /// How many live branches sit under this supplier.
  final int branchCount;

  /// The optimistic-concurrency version this record was read at, sent back
  /// as `If-Match` on save so a concurrent edit is refused rather than
  /// silently overwritten. Zero means the server published none, and the
  /// save then carries no precondition.
  final int version;
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

  /// ISO code the supplier bills in; blank is rupees.
  final String currencyCode;

  /// REGULAR, COMPOSITION, UNREGISTERED, OVERSEAS, SEZ, or null when nobody
  /// declared one. Null is read off the GSTIN for display only and changes
  /// no tax (backlog 78 row 2).
  final String? gstRegistrationType;

  /// The type for display: the declared one, or what the GSTIN implies.
  String get gstTypeLabel {
    final String? type = gstRegistrationType;
    if (type != null && type.isNotEmpty) {
      return vendorGstTypeLabels[type] ?? type;
    }
    return gstin.trim().isNotEmpty
        ? 'Regular (from GSTIN)'
        : 'Unregistered (from GSTIN)';
  }

  /// One word for a list column.
  String get gstTypeShort {
    final String? type = gstRegistrationType;
    if (type == null || type.isEmpty) return gstTypeLabel;
    return vendorGstTypeName(type);
  }

  /// True when a declared type means this supplier's bills carry no GST.
  bool get chargesNoGst =>
      vendorGstTypesChargingNoGst.contains(gstRegistrationType);

  /// Why the supplier is BLOCKED (backlog 69 row 4); empty otherwise.
  final String blockedReason;

  /// Days of credit; a bill's due date defaults from it (backlog 68 row 1).
  final int paymentTermsDays;

  /// Taken off every purchase line that names no discount of its own.
  final double standingDiscountPercent;

  /// Udyam registration and MSME category (MICRO, SMALL, MEDIUM or empty),
  /// and whether a written agreement allows up to 45 days (backlog 68 row 2).
  final String udyamNumber;
  final String msmeCategory;

  /// The TDS section their payments usually come under (ACC-7); empty when
  /// none is set. Prefills a payment's section, never forces it.
  final String defaultTdsSection;

  /// Whether they are an individual or HUF for 194C/194J rates (PG-5); null
  /// reads it from the fourth letter of their PAN.
  final bool? tdsIndividualHuf;

  /// 194J at the 2% rate for technical services rather than the 10% one.
  final bool tdsTechnicalServices;

  /// The firm deducts TDS from this supplier; off, nothing is proposed.
  final bool tdsApplicable;
  final bool msmeWrittenAgreement;

  /// Whether their bills carry an IRN (backlog 78 row 5); a bill from one
  /// without it is warned about.
  final bool issuesEInvoices;
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
  final List<VendorBankAccount> bankAccounts;
  final List<VendorTaxDetail> taxDetails;
  final List<VendorNote> notes;

  /// The stored custom-field values, one per definition the firm defines.
  final List<AttributeValueRecord> attributes;

  factory Vendor.fromJson(Json json) => Vendor(
        id: stringValue(json['id']),
        version: (json['version'] as num?)?.toInt() ?? 0,
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
        gstRegistrationType: json['gst_registration_type'] is String &&
                (json['gst_registration_type'] as String).isNotEmpty
            ? json['gst_registration_type'] as String
            : null,
        gstin: stringValue(json['gstin']),
        pan: stringValue(json['pan']),
        blockedReason: stringValue(json['blocked_reason']),
        paymentTermsDays: (json['payment_terms_days'] as num?)?.toInt() ?? 0,
        currencyCode: stringValue(json['currency_code']),
        standingDiscountPercent:
            double.tryParse('${json['standing_discount_percent'] ?? 0}') ?? 0,
        udyamNumber: stringValue(json['udyam_number']),
        msmeCategory: stringValue(json['msme_category']),
        defaultTdsSection: stringValue(json['default_tds_section']),
        tdsIndividualHuf: json['tds_individual_huf'] is bool
            ? json['tds_individual_huf'] as bool
            : null,
        tdsTechnicalServices: boolValue(json['tds_technical_services']),
        tdsApplicable: json['tds_applicable'] != false,
        msmeWrittenAgreement: boolValue(json['msme_written_agreement']),
        issuesEInvoices: boolValue(json['issues_e_invoices']),
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
        bankAccounts: _objects(json['bank_accounts'])
            .map(VendorBankAccount.fromJson)
            .toList(),
        taxDetails:
            _objects(json['tax_details']).map(VendorTaxDetail.fromJson).toList(),
        notes: _objects(json['notes']).map(VendorNote.fromJson).toList(),
        attributes: _objects(json['attributes'])
            .map(ProductAttributeValueRecord.fromJson)
            .toList(),
        parentVendorId: json['parent_vendor_id'] as String?,
        parentCode: json['parent_code'] as String?,
        parentName: json['parent_name'] as String?,
        branchCount: (json['branch_count'] as num?)?.toInt() ?? 0,
        gstinFromParent: boolValue(json['gstin_from_parent']),
      );
}

/// One office of a supplier company: the main office or one of its branches.
class VendorFamilyMember {
  const VendorFamilyMember({
    required this.id,
    required this.code,
    required this.name,
    required this.isParent,
    required this.gstin,
    required this.status,
    required this.place,
    required this.balance,
    this.gstinFromParent = false,
  });

  final String id;
  final String code;
  final String name;
  final bool isParent;
  final String gstin;

  /// True when [gstin] is the main office's, copied by the server.
  final bool gstinFromParent;
  final String status;

  /// "Area, City", or empty.
  final String place;

  /// What the firm owes this office; negative when paid ahead.
  final String balance;

  factory VendorFamilyMember.fromJson(Json json) => VendorFamilyMember(
        id: stringValue(json['id']),
        code: stringValue(json['code']),
        name: stringValue(json['name']),
        isParent: boolValue(json['is_parent']),
        gstin: stringValue(json['gstin']),
        gstinFromParent: boolValue(json['gstin_from_parent']),
        status: stringValue(json['status']),
        place: stringValue(json['place']),
        balance: stringValue(json['balance']).isEmpty
            ? '0.00'
            : stringValue(json['balance']),
      );
}

/// A supplier company as `GET /vendors/{id}/family` answers: the same family
/// whichever office is asked about, the main office first.
class VendorFamily {
  const VendorFamily({
    required this.parentId,
    required this.members,
    required this.totalBalance,
  });

  final String parentId;
  final List<VendorFamilyMember> members;
  final String totalBalance;

  factory VendorFamily.fromJson(Json json) => VendorFamily(
        parentId: stringValue(json['parent_id']),
        members:
            _objects(json['members']).map(VendorFamilyMember.fromJson).toList(),
        totalBalance: stringValue(json['total_balance']).isEmpty
            ? '0.00'
            : stringValue(json['total_balance']),
      );
}

/// The main office of a supplier company as its family answers it.
VendorFamilyMember mainOfficeOf(VendorFamily family) {
  for (final VendorFamilyMember member in family.members) {
    if (member.isParent) return member;
  }
  return family.members.first;
}

/// A supplier company with a branch just saved added to it, for a document
/// that added the branch itself: no second read of the family is needed to
/// offer it. A branch already listed is left as it is.
VendorFamily familyWithBranch(VendorFamily family, Vendor branch) {
  if (family.members.any((member) => member.id == branch.id)) return family;
  return VendorFamily(
    parentId: family.parentId,
    totalBalance: family.totalBalance,
    members: [...family.members, officeFrom(branch, isParent: false)],
  );
}

/// One office of a supplier company, from the supplier's own row: what a
/// document needs to offer it, with no balance read.
VendorFamilyMember officeFrom(Vendor vendor, {required bool isParent}) =>
    VendorFamilyMember(
      id: vendor.id,
      code: vendor.code,
      name: vendor.name,
      isParent: isParent,
      gstin: vendor.gstin,
      gstinFromParent: vendor.gstinFromParent,
      status: vendor.status,
      place: '',
      balance: '0.00',
    );

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
