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
    required this.isActive,
    required this.notes,
    required this.createdAt,
    required this.updatedAt,
  });

  final String id, code, name, gstNumber, panNumber;
  final String addressLine1, addressLine2, city, state, postalCode, country;
  final String contactName, contactEmail, contactPhone;
  final String currencyCode, financialYearStart, notes, createdAt, updatedAt;
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
  });
  final String id, email, fullName;
  final bool isActive, forcePasswordChange;
  final String expiresAt;

  factory PlatformUser.fromJson(Json json) => PlatformUser(
        id: stringValue(json['id']),
        email: stringValue(json['email']),
        fullName: stringValue(json['full_name']),
        isActive: boolValue(json['is_active'], fallback: true),
        forcePasswordChange: boolValue(json['force_password_change']),
        expiresAt: stringValue(json['expires_at']),
      );

  Json toJson({String? password}) => {
        'email': email,
        'full_name': fullName,
        'is_active': isActive,
        'force_password_change': forcePasswordChange,
        if (expiresAt.isNotEmpty) 'expires_at': expiresAt,
        if (password != null && password.isNotEmpty) 'password': password,
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
