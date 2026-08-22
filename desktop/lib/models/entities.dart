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
  const AssignmentOption({required this.id, required this.label, this.group});
  final String id, label;

  /// The heading this option belongs under, when the API names one.
  ///
  /// Business features carry a category; permissions and most other catalogues
  /// do not, and fall back to being grouped by the leading word of their code.
  final String? group;
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
    required this.connectionProfile,
    required this.provisionedAt,
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
  final String connectionProfile, provisionedAt;
  final String notes, createdAt, updatedAt;
  final bool isActive;

  /// Whether this firm's storage has been built and can serve requests.
  ///
  /// Shared firms live in the platform store and are ready the moment they
  /// exist; dedicated firms are not usable until the provisioning action has
  /// created their database, schema and tables.
  bool get isStorageReady =>
      deploymentMode == 'SHARED' || provisionedAt.isNotEmpty;

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
        connectionProfile: stringValue(json['connection_profile']),
        provisionedAt: stringValue(json['provisioned_at']),
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
        'connection_profile': connectionProfile,
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

/// One firm and the business profile it is assigned.
///
/// Assignments live in each firm's own store, so this cannot be read with a
/// single query — the server iterates the stores and returns one row per firm.
class FirmProfileAssignment {
  const FirmProfileAssignment({
    required this.firmId,
    required this.profileCode,
    required this.profileName,
    required this.isActive,
    required this.unavailableReason,
  });

  final String firmId;
  final String profileCode;
  final String profileName;
  final bool isActive;

  /// Why this firm's assignment could not be read, if it could not be. An
  /// unprovisioned firm and a firm with no profile are different facts and
  /// must not render identically — one is a setup step, the other a choice.
  final String unavailableReason;

  bool get isUnavailable => unavailableReason.isNotEmpty;
  bool get hasProfile => profileCode.isNotEmpty;

  /// What the grid shows: the profile, why it is unknown, or that there is
  /// none. Never an empty cell, which reads as "nothing here to do".
  String get label {
    if (isUnavailable) return 'Unavailable';
    if (!hasProfile) return 'Not assigned';
    return isActive ? profileCode : '$profileCode (inactive)';
  }

  factory FirmProfileAssignment.fromJson(Json json) => FirmProfileAssignment(
        firmId: stringValue(json['firm_id']),
        profileCode: stringValue(json['business_profile_code']),
        profileName: stringValue(json['business_profile_name']),
        isActive: json['is_active'] as bool? ?? false,
        unavailableReason: stringValue(json['unavailable_reason']),
      );
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
    required this.isImplemented,
  });

  final String id, code, name, category;
  final bool defaultEnabled, isActive;

  /// False for catalogue entries that name a subsystem nothing has built.
  ///
  /// They are listed so the roadmap is visible, but the server refuses to
  /// enable one, so a UI must show them as unavailable rather than switchable.
  final bool isImplemented;

  factory BusinessFeatureRecord.fromJson(Json json) => BusinessFeatureRecord(
        id: stringValue(json['id']),
        code: stringValue(json['code']),
        name: stringValue(json['name']),
        category: stringValue(json['category']),
        defaultEnabled: boolValue(json['default_enabled']),
        isActive: boolValue(json['is_active'], fallback: true),
        // Older servers omit the field; assume a feature works rather than
        // hiding a real one behind a flag they never sent.
        isImplemented: boolValue(json['is_implemented'], fallback: true),
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

/// One configurable field definition, carrying **every** column the API sends.
///
/// The update endpoint replaces the whole record, so a column missing here is
/// a column the edit form silently resets: description and default value were
/// wiped on every save, `entity_type` reverted to PRODUCT, and a definition
/// scoped to one business profile was quietly un-scoped to all of them.
/// One rule saying an attribute is required for a product category.
///
/// `AttributeService.required_attribute_ids` reads these, so a rule here is
/// what makes a field mandatory for a pharmacy's medicines and optional for
/// everybody else. `20260815_0087` cleared the blanket `mandatory` flags that
/// asked an electronics distributor for an expiry date, on the understanding
/// that a firm would say what it needs *here* instead -- and then nothing in
/// the desktop could write one, so from 2026-08-15 to 2026-08-22 no attribute
/// could be made mandatory at all.
class CategoryAttributeRuleRecord {
  const CategoryAttributeRuleRecord({
    required this.id,
    required this.categoryCode,
    required this.attributeDefinitionId,
    required this.attributeCode,
    required this.attributeName,
    required this.businessProfileId,
    required this.businessProfileCode,
    required this.isMandatory,
    this.validationOverride,
  });

  final String id, categoryCode, attributeDefinitionId, businessProfileId;

  /// Resolved server-side: a grid of raw ids tells the reader nothing, and
  /// looking them up here would mean loading the whole catalogue per page.
  final String attributeCode, attributeName, businessProfileCode;

  final bool isMandatory;

  /// Round-tripped untouched: the form cannot edit it, so it must not drop it.
  final Map<String, dynamic>? validationOverride;

  factory CategoryAttributeRuleRecord.fromJson(Json json) =>
      CategoryAttributeRuleRecord(
        id: stringValue(json['id']),
        categoryCode: stringValue(json['category_code']),
        attributeDefinitionId: stringValue(json['attribute_definition_id']),
        attributeCode: stringValue(json['attribute_code']),
        attributeName: stringValue(json['attribute_name']),
        businessProfileId: stringValue(json['business_profile_id']),
        businessProfileCode: stringValue(json['business_profile_code']),
        isMandatory: boolValue(json['is_mandatory'], fallback: true),
        validationOverride: json['validation_override'] is Map
            ? Map<String, dynamic>.from(json['validation_override'] as Map)
            : null,
      );
}

class AttributeDefinitionRecord {
  const AttributeDefinitionRecord({
    required this.id,
    required this.code,
    required this.name,
    required this.dataType,
    required this.entityType,
    required this.mandatory,
    required this.isActive,
    required this.applicableCategory,
    required this.description,
    required this.defaultValue,
    required this.applicableBusinessProfileId,
    this.validationRule,
  });

  final String id, code, name, dataType, applicableCategory;
  final String entityType, description, defaultValue;

  /// The business profile this field is limited to, or empty for every one.
  final String applicableBusinessProfileId;

  /// Round-tripped untouched: the form cannot edit it, so it must not drop it.
  final Map<String, dynamic>? validationRule;

  final bool mandatory, isActive;

  String get _type => dataType.toUpperCase();

  bool get isNumber => _type == 'NUMBER';
  bool get isDate => _type == 'DATE';
  bool get isBoolean => _type == 'BOOLEAN';

  factory AttributeDefinitionRecord.fromJson(Json json) =>
      AttributeDefinitionRecord(
        id: stringValue(json['id']),
        code: stringValue(json['code']),
        name: stringValue(json['name']),
        dataType: stringValue(json['data_type']),
        entityType: stringValue(json['entity_type']),
        mandatory: boolValue(json['mandatory']),
        isActive: boolValue(json['is_active'], fallback: true),
        applicableCategory: stringValue(json['applicable_category']),
        description: stringValue(json['description']),
        defaultValue: stringValue(json['default_value']),
        applicableBusinessProfileId:
            stringValue(json['applicable_business_profile_id']),
        validationRule: json['validation_rule'] is Map
            ? Map<String, dynamic>.from(json['validation_rule'] as Map)
            : null,
      );
}
