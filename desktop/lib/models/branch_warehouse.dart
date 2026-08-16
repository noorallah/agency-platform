import 'entities.dart';

class BranchRecord {
  const BranchRecord({
    required this.id,
    this.version = 0,
    required this.firmId,
    required this.code,
    required this.name,
    required this.displayName,
    required this.description,
    required this.branchTypeId,
    required this.branchManagerId,
    required this.businessProfileId,
    required this.email,
    required this.phone,
    required this.mobile,
    this.addressLine1 = '',
    this.addressLine2 = '',
    this.countryId = '',
    this.stateId = '',
    this.districtId = '',
    this.cityId = '',
    this.postalCodeId = '',
    this.localityId = '',
    required this.currencyCode,
    this.gstRegistration = false,
    required this.status,
    required this.isDefault,
    required this.isDeleted,
    required this.warehouseCount,
    required this.createdAt,
  });

  final String id;

  /// The optimistic-concurrency version this record was read at, sent back
  /// as `If-Match` on save so a concurrent edit is refused rather than
  /// silently overwritten. Zero means the server published none, and the
  /// save then carries no precondition.
  final int version;
  final String firmId;
  final String code;
  final String name;
  final String displayName;
  final String description;
  final String branchTypeId;
  final String branchManagerId;
  final String businessProfileId;
  final String email;
  final String phone;
  final String mobile;
  final String addressLine1;
  final String addressLine2;

  /// Where the branch is, as ids into the shared geography masters. There is
  /// no free-text city on this table — these keys are the only way to say it.
  final String countryId;
  final String stateId;
  final String districtId;
  final String cityId;
  final String postalCodeId;
  final String localityId;
  final String currencyCode;
  final bool gstRegistration;
  final String status;
  final bool isDefault;
  final bool isDeleted;
  final int warehouseCount;
  final String createdAt;

  factory BranchRecord.fromJson(Json json) => BranchRecord(
        id: stringValue(json['id']),
        version: (json['version'] as num?)?.toInt() ?? 0,
        firmId: stringValue(json['firm_id']),
        code: stringValue(json['code']),
        name: stringValue(json['name']),
        displayName: stringValue(json['display_name']),
        description: stringValue(json['description']),
        branchTypeId: stringValue(json['branch_type_id']),
        branchManagerId: stringValue(json['branch_manager_id']),
        businessProfileId: stringValue(json['business_profile_id']),
        email: stringValue(json['email']),
        phone: stringValue(json['phone']),
        mobile: stringValue(json['mobile']),
        addressLine1: stringValue(json['address_line1']),
        addressLine2: stringValue(json['address_line2']),
        countryId: stringValue(json['country_id']),
        stateId: stringValue(json['state_id']),
        districtId: stringValue(json['district_id']),
        cityId: stringValue(json['city_id']),
        postalCodeId: stringValue(json['postal_code_id']),
        localityId: stringValue(json['locality_id']),
        currencyCode: stringValue(json['currency_code']),
        gstRegistration: boolValue(json['gst_registration']),
        status: stringValue(json['status']),
        isDefault: boolValue(json['is_default']),
        isDeleted: boolValue(json['is_deleted']),
        warehouseCount: (json['warehouse_count'] as num?)?.toInt() ?? 0,
        createdAt: stringValue(json['created_at']),
      );
}

class WarehouseRecord {
  const WarehouseRecord({
    required this.id,
    this.version = 0,
    required this.firmId,
    required this.branchId,
    required this.code,
    required this.name,
    required this.displayName,
    required this.warehouseTypeId,
    required this.businessProfileId,
    this.addressLine1 = '',
    this.addressLine2 = '',
    this.countryId = '',
    this.stateId = '',
    this.districtId = '',
    this.cityId = '',
    this.postalCodeId = '',
    this.localityId = '',
    required this.capacity,
    required this.capacityUnit,
    required this.status,
    required this.isDefault,
    required this.temperatureControlled,
    required this.coldStorage,
    required this.hazardousStorage,
    this.hasReceivingArea = false,
    this.hasDispatchArea = false,
    this.hasReturnsArea = false,
    this.hasInspectionArea = false,
    this.hasPackingArea = false,
    this.hasLoadingDock = false,
    required this.isDeleted,
    required this.createdAt,
  });

  final String id;

  /// The optimistic-concurrency version this record was read at, sent back
  /// as `If-Match` on save so a concurrent edit is refused rather than
  /// silently overwritten. Zero means the server published none, and the
  /// save then carries no precondition.
  final int version;
  final String firmId;
  final String branchId;
  final String code;
  final String name;
  final String displayName;
  final String warehouseTypeId;
  final String businessProfileId;
  final String addressLine1;
  final String addressLine2;

  /// Where the warehouse is. Same geography masters the branch uses.
  final String countryId;
  final String stateId;
  final String districtId;
  final String cityId;
  final String postalCodeId;
  final String localityId;
  final String capacity;
  final String capacityUnit;
  final String status;
  final bool isDefault;
  final bool temperatureControlled;
  final bool coldStorage;
  final bool hazardousStorage;
  final bool hasReceivingArea;
  final bool hasDispatchArea;
  final bool hasReturnsArea;
  final bool hasInspectionArea;
  final bool hasPackingArea;
  final bool hasLoadingDock;
  final bool isDeleted;
  final String createdAt;

  factory WarehouseRecord.fromJson(Json json) => WarehouseRecord(
        id: stringValue(json['id']),
        version: (json['version'] as num?)?.toInt() ?? 0,
        firmId: stringValue(json['firm_id']),
        branchId: stringValue(json['branch_id']),
        code: stringValue(json['code']),
        name: stringValue(json['name']),
        displayName: stringValue(json['display_name']),
        warehouseTypeId: stringValue(json['warehouse_type_id']),
        businessProfileId: stringValue(json['business_profile_id']),
        addressLine1: stringValue(json['address_line1']),
        addressLine2: stringValue(json['address_line2']),
        countryId: stringValue(json['country_id']),
        stateId: stringValue(json['state_id']),
        districtId: stringValue(json['district_id']),
        cityId: stringValue(json['city_id']),
        postalCodeId: stringValue(json['postal_code_id']),
        localityId: stringValue(json['locality_id']),
        capacity: stringValue(json['capacity']),
        capacityUnit: stringValue(json['capacity_unit']),
        status: stringValue(json['status']),
        isDefault: boolValue(json['is_default']),
        temperatureControlled: boolValue(json['temperature_controlled']),
        coldStorage: boolValue(json['cold_storage']),
        hazardousStorage: boolValue(json['hazardous_storage']),
        hasReceivingArea: boolValue(json['has_receiving_area']),
        hasDispatchArea: boolValue(json['has_dispatch_area']),
        hasReturnsArea: boolValue(json['has_returns_area']),
        hasInspectionArea: boolValue(json['has_inspection_area']),
        hasPackingArea: boolValue(json['has_packing_area']),
        hasLoadingDock: boolValue(json['has_loading_dock']),
        isDeleted: boolValue(json['is_deleted']),
        createdAt: stringValue(json['created_at']),
      );
}

class TypeRecord {
  const TypeRecord({
    required this.id,
    required this.code,
    required this.name,
    required this.description,
    required this.isActive,
    required this.isDeleted,
  });

  final String id;
  final String code;
  final String name;
  final String description;
  final bool isActive;
  final bool isDeleted;

  factory TypeRecord.fromJson(Json json) => TypeRecord(
        id: stringValue(json['id']),
        code: stringValue(json['code']),
        name: stringValue(json['name']),
        description: stringValue(json['description']),
        isActive: boolValue(json['is_active'], fallback: true),
        isDeleted: boolValue(json['is_deleted']),
      );
}

class StorageNodeRecord {
  const StorageNodeRecord({
    required this.id,
    required this.warehouseId,
    required this.parentId,
    required this.nodeType,
    required this.code,
    required this.name,
    required this.path,
    required this.sortOrder,
    required this.isActive,
    required this.isDeleted,
  });

  final String id;
  final String warehouseId;
  final String parentId;
  final String nodeType;
  final String code;
  final String name;
  final String path;
  final int sortOrder;
  final bool isActive;
  final bool isDeleted;

  factory StorageNodeRecord.fromJson(Json json) => StorageNodeRecord(
        id: stringValue(json['id']),
        warehouseId: stringValue(json['warehouse_id']),
        parentId: stringValue(json['parent_id']),
        nodeType: stringValue(json['node_type']),
        code: stringValue(json['code']),
        name: stringValue(json['name']),
        path: stringValue(json['path']),
        sortOrder: (json['sort_order'] as num?)?.toInt() ?? 0,
        isActive: boolValue(json['is_active'], fallback: true),
        isDeleted: boolValue(json['is_deleted']),
      );
}

class BranchQuery {
  const BranchQuery({
    this.status,
    this.branchTypeId,
    this.managerId,
    this.businessProfileId,
    this.cityId,
    this.stateId,
    this.countryId,
    this.includeDeleted = false,
  });

  final String? status;
  final String? branchTypeId;
  final String? managerId;
  final String? businessProfileId;
  final String? cityId;
  final String? stateId;
  final String? countryId;
  final bool includeDeleted;

  Map<String, String> toQuery() => {
        if (status?.isNotEmpty == true) 'status': status!,
        if (branchTypeId?.isNotEmpty == true) 'branch_type_id': branchTypeId!,
        if (managerId?.isNotEmpty == true) 'manager_id': managerId!,
        if (businessProfileId?.isNotEmpty == true)
          'business_profile_id': businessProfileId!,
        if (cityId?.isNotEmpty == true) 'city_id': cityId!,
        if (stateId?.isNotEmpty == true) 'state_id': stateId!,
        if (countryId?.isNotEmpty == true) 'country_id': countryId!,
        if (includeDeleted) 'include_deleted': 'true',
      };
}

class WarehouseQuery {
  const WarehouseQuery({
    this.status,
    this.branchId,
    this.warehouseTypeId,
    this.managerId,
    this.businessProfileId,
    this.cityId,
    this.stateId,
    this.countryId,
    this.includeDeleted = false,
  });

  final String? status;
  final String? branchId;
  final String? warehouseTypeId;
  final String? managerId;
  final String? businessProfileId;
  final String? cityId;
  final String? stateId;
  final String? countryId;
  final bool includeDeleted;

  Map<String, String> toQuery() => {
        if (status?.isNotEmpty == true) 'status': status!,
        if (branchId?.isNotEmpty == true) 'branch_id': branchId!,
        if (warehouseTypeId?.isNotEmpty == true)
          'warehouse_type_id': warehouseTypeId!,
        if (managerId?.isNotEmpty == true) 'manager_id': managerId!,
        if (businessProfileId?.isNotEmpty == true)
          'business_profile_id': businessProfileId!,
        if (cityId?.isNotEmpty == true) 'city_id': cityId!,
        if (stateId?.isNotEmpty == true) 'state_id': stateId!,
        if (countryId?.isNotEmpty == true) 'country_id': countryId!,
        if (includeDeleted) 'include_deleted': 'true',
      };
}
