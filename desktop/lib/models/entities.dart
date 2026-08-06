typedef Json = Map<String, dynamic>;

String stringValue(dynamic value) => value?.toString() ?? '';
bool boolValue(dynamic value, {bool fallback = false}) =>
    value is bool ? value : fallback;
List<String> stringList(dynamic value) => value is List
    ? value.map(stringValue).where((entry) => entry.isNotEmpty).toList()
    : const [];

class PagedResult<T> {
  const PagedResult({required this.items, required this.total});
  final List<T> items;
  final int total;
}

class AssignmentOption {
  const AssignmentOption({required this.id, required this.label});
  final String id, label;
}

class AssignedFirm {
  const AssignedFirm({
    required this.id,
    required this.code,
    required this.name,
    required this.isPrimary,
  });

  final String id, code, name;
  final bool isPrimary;

  factory AssignedFirm.fromJson(Json json) => AssignedFirm(
        id: stringValue(json['id']),
        code: stringValue(json['code']),
        name: stringValue(json['name']),
        isPrimary: boolValue(json['is_primary']),
      );
}

class Firm {
  const Firm({
    required this.id,
    required this.code,
    required this.name,
    required this.gstNumber,
    required this.panNumber,
    required this.addressLine1,
    required this.addressLine2,
    required this.city,
    required this.state,
    required this.postalCode,
    required this.country,
    required this.contactName,
    required this.contactEmail,
    required this.contactPhone,
    required this.currencyCode,
    required this.financialYearStart,
    required this.deploymentMode,
    required this.databaseType,
    required this.databaseName,
    required this.schemaName,
    required this.isActive,
    required this.notes,
    required this.createdAt,
    required this.updatedAt,
  });

  final String id, code, name, gstNumber, panNumber;
  final String addressLine1, addressLine2, city, state, postalCode, country;
  final String contactName, contactEmail, contactPhone;
  final String currencyCode, financialYearStart;
  final String deploymentMode, databaseType, databaseName, schemaName;
  final String notes, createdAt, updatedAt;
  final bool isActive;

  factory Firm.fromJson(Json json) => Firm(
        id: stringValue(json['id']),
        code: stringValue(json['code']),
        name: stringValue(json['name']),
        gstNumber: stringValue(json['gst_number']),
        panNumber: stringValue(json['pan_number']),
        addressLine1: stringValue(json['address_line1']),
        addressLine2: stringValue(json['address_line2']),
        city: stringValue(json['city']),
        state: stringValue(json['state']),
        postalCode: stringValue(json['postal_code']),
        country: stringValue(json['country']),
        contactName: stringValue(json['contact_name']),
        contactEmail: stringValue(json['contact_email']),
        contactPhone: stringValue(json['contact_phone']),
        currencyCode: stringValue(json['currency_code']),
        financialYearStart: stringValue(json['financial_year_start']),
        deploymentMode: stringValue(json['deployment_mode']),
        databaseType: stringValue(json['database_type']),
        databaseName: stringValue(json['database_name']),
        schemaName: stringValue(json['schema_name']),
        isActive: boolValue(json['is_active'], fallback: true),
        notes: stringValue(json['notes']),
        createdAt: stringValue(json['created_at']),
        updatedAt: stringValue(json['updated_at']),
      );

  Json toJson() => {
        'code': code,
        'name': name,
        'gst_number': gstNumber,
        'pan_number': panNumber,
        'address_line1': addressLine1,
        'address_line2': addressLine2,
        'city': city,
        'state': state,
        'postal_code': postalCode,
        'country': country,
        'contact_name': contactName,
        'contact_email': contactEmail,
        'contact_phone': contactPhone,
        'currency_code': currencyCode,
        'financial_year_start': financialYearStart,
        'deployment_mode': deploymentMode,
        'database_type': databaseType,
        'database_name': databaseName,
        'schema_name': schemaName,
        'is_active': isActive,
        'notes': notes,
      };
}

class PlatformUser {
  const PlatformUser({
    required this.id,
    required this.email,
    required this.fullName,
    required this.isActive,
    required this.forcePasswordChange,
    required this.expiresAt,
    this.personalMobile = '',
    this.alternateMobile = '',
    this.personalEmail = '',
    this.officeEmail = '',
    this.emergencyContactName = '',
    this.emergencyMobile = '',
    this.emergencyRelationship = '',
    this.employeeCode = '',
    this.joiningDate = '',
    this.leavingDate = '',
    this.department = '',
    this.designation = '',
    this.reportingManager = '',
    this.employmentType = '',
    this.costCenter = '',
    this.profilePhotoUrl = '',
    this.profileAddresses = const [],
    this.profileDocuments = const [],
    this.failedLoginAttempts = 0,
    this.lastLoginAt = '',
    this.createdAt = '',
    this.updatedAt = '',
  });
  final String id, email, fullName;
  final bool isActive, forcePasswordChange;
  final String expiresAt;

  // Optional HR/profile enrichment (Phase 9). Never consulted for
  // authentication/authorization — those continue to rely solely on
  // email/password/roles.
  final String personalMobile,
      alternateMobile,
      personalEmail,
      officeEmail,
      emergencyContactName,
      emergencyMobile,
      emergencyRelationship,
      employeeCode,
      joiningDate,
      leavingDate,
      department,
      designation,
      reportingManager,
      employmentType,
      costCenter,
      profilePhotoUrl;
  final List<Json> profileAddresses;
  final List<Json> profileDocuments;

  // Read-only audit trail data already exposed by the backend.
  final int failedLoginAttempts;
  final String lastLoginAt, createdAt, updatedAt;

  factory PlatformUser.fromJson(Json json) => PlatformUser(
        id: stringValue(json['id']),
        email: stringValue(json['email']),
        fullName: stringValue(json['full_name']),
        isActive: boolValue(json['is_active'], fallback: true),
        forcePasswordChange: boolValue(json['force_password_change']),
        expiresAt: stringValue(json['expires_at']),
        personalMobile: stringValue(json['personal_mobile']),
        alternateMobile: stringValue(json['alternate_mobile']),
        personalEmail: stringValue(json['personal_email']),
        officeEmail: stringValue(json['office_email']),
        emergencyContactName: stringValue(json['emergency_contact_name']),
        emergencyMobile: stringValue(json['emergency_mobile']),
        emergencyRelationship: stringValue(json['emergency_relationship']),
        employeeCode: stringValue(json['employee_code']),
        joiningDate: stringValue(json['joining_date']),
        leavingDate: stringValue(json['leaving_date']),
        department: stringValue(json['department']),
        designation: stringValue(json['designation']),
        reportingManager: stringValue(json['reporting_manager']),
        employmentType: stringValue(json['employment_type']),
        costCenter: stringValue(json['cost_center']),
        profilePhotoUrl: stringValue(json['profile_photo_url']),
        profileAddresses: (json['profile_addresses'] as List?)
                ?.whereType<Map>()
                .map((item) => Map<String, dynamic>.from(item))
                .toList() ??
            const [],
        profileDocuments: (json['profile_documents'] as List?)
                ?.whereType<Map>()
                .map((item) => Map<String, dynamic>.from(item))
                .toList() ??
            const [],
        failedLoginAttempts: json['failed_login_attempts'] is int
            ? json['failed_login_attempts'] as int
            : int.tryParse(stringValue(json['failed_login_attempts'])) ?? 0,
        lastLoginAt: stringValue(json['last_login_at']),
        createdAt: stringValue(json['created_at']),
        updatedAt: stringValue(json['updated_at']),
      );

  Json toJson({String? password}) => {
        'email': email,
        'full_name': fullName,
        'is_active': isActive,
        'force_password_change': forcePasswordChange,
        if (expiresAt.isNotEmpty) 'expires_at': expiresAt,
        if (password != null && password.isNotEmpty) 'password': password,
        'personal_mobile': personalMobile,
        'alternate_mobile': alternateMobile,
        'personal_email': personalEmail,
        'office_email': officeEmail,
        'emergency_contact_name': emergencyContactName,
        'emergency_mobile': emergencyMobile,
        'emergency_relationship': emergencyRelationship,
        'employee_code': employeeCode,
        if (joiningDate.isNotEmpty) 'joining_date': joiningDate,
        if (leavingDate.isNotEmpty) 'leaving_date': leavingDate,
        'department': department,
        'designation': designation,
        'reporting_manager': reportingManager,
        'employment_type': employmentType,
        'cost_center': costCenter,
        'profile_photo_url': profilePhotoUrl,
        'profile_addresses': profileAddresses,
        'profile_documents': profileDocuments,
      };
}

class Role {
  const Role({
    required this.id,
    required this.code,
    required this.name,
    required this.description,
    required this.isActive,
    required this.isSystem,
  });
  final String id, code, name, description;
  final bool isActive, isSystem;

  factory Role.fromJson(Json json) => Role(
        id: stringValue(json['id']),
        code: stringValue(json['code']),
        name: stringValue(json['name']),
        description: stringValue(json['description']),
        isActive: boolValue(json['is_active'], fallback: true),
        isSystem: boolValue(json['is_system']),
      );

  Json toJson() => {
        'code': code,
        'name': name,
        'description': description,
        'is_active': isActive,
      };
}

class Permission {
  const Permission({
    required this.id,
    required this.code,
    required this.name,
    required this.description,
    required this.isActive,
  });
  final String id, code, name, description;
  final bool isActive;

  factory Permission.fromJson(Json json) => Permission(
        id: stringValue(json['id']),
        code: stringValue(json['code']),
        name: stringValue(json['name']),
        description: stringValue(json['description']),
        isActive: boolValue(json['is_active'], fallback: true),
      );

  Json toJson() => {
        'code': code,
        'name': name,
        'description': description,
        'is_active': isActive,
      };
}

class BusinessProfileRecord {
  const BusinessProfileRecord({
    required this.id,
    required this.code,
    required this.name,
    required this.industryType,
    required this.status,
    required this.isDefault,
    required this.description,
  });

  final String id, code, name, industryType, status, description;
  final bool isDefault;

  factory BusinessProfileRecord.fromJson(Json json) => BusinessProfileRecord(
        id: stringValue(json['id']),
        code: stringValue(json['code']),
        name: stringValue(json['name']),
        industryType: stringValue(json['industry_type']),
        status: stringValue(json['status']),
        isDefault: boolValue(json['is_default']),
        description: stringValue(json['description']),
      );
}

class BusinessFeatureRecord {
  const BusinessFeatureRecord({
    required this.id,
    required this.code,
    required this.name,
    required this.category,
    required this.defaultEnabled,
    required this.isActive,
  });

  final String id, code, name, category;
  final bool defaultEnabled, isActive;

  factory BusinessFeatureRecord.fromJson(Json json) => BusinessFeatureRecord(
        id: stringValue(json['id']),
        code: stringValue(json['code']),
        name: stringValue(json['name']),
        category: stringValue(json['category']),
        defaultEnabled: boolValue(json['default_enabled']),
        isActive: boolValue(json['is_active'], fallback: true),
      );
}

class BusinessModuleRecord {
  const BusinessModuleRecord({
    required this.id,
    required this.code,
    required this.name,
    required this.uiRoute,
    required this.defaultEnabled,
    required this.isActive,
  });

  final String id, code, name, uiRoute;
  final bool defaultEnabled, isActive;

  factory BusinessModuleRecord.fromJson(Json json) => BusinessModuleRecord(
        id: stringValue(json['id']),
        code: stringValue(json['code']),
        name: stringValue(json['name']),
        uiRoute: stringValue(json['ui_route']),
        defaultEnabled: boolValue(json['default_enabled'], fallback: true),
        isActive: boolValue(json['is_active'], fallback: true),
      );
}

class AttributeDefinitionRecord {
  const AttributeDefinitionRecord({
    required this.id,
    required this.code,
    required this.name,
    required this.dataType,
    required this.mandatory,
    required this.isActive,
    required this.applicableCategory,
  });

  final String id, code, name, dataType, applicableCategory;
  final bool mandatory, isActive;

  factory AttributeDefinitionRecord.fromJson(Json json) =>
      AttributeDefinitionRecord(
        id: stringValue(json['id']),
        code: stringValue(json['code']),
        name: stringValue(json['name']),
        dataType: stringValue(json['data_type']),
        mandatory: boolValue(json['mandatory']),
        isActive: boolValue(json['is_active'], fallback: true),
        applicableCategory: stringValue(json['applicable_category']),
      );
}
