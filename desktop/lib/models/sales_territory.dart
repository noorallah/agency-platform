import 'entities.dart';

class TerritoryHierarchyLevelRecord {
  const TerritoryHierarchyLevelRecord({
    required this.id,
    required this.levelOrder,
    required this.levelCode,
    required this.displayName,
    required this.description,
    required this.isMandatory,
    required this.isEnabled,
  });

  final String id;
  final int levelOrder;
  final String levelCode;
  final String displayName;
  final String description;
  final bool isMandatory;
  final bool isEnabled;

  factory TerritoryHierarchyLevelRecord.fromJson(Json json) =>
      TerritoryHierarchyLevelRecord(
        id: stringValue(json['id']),
        levelOrder: (json['level_order'] as num?)?.toInt() ?? 0,
        levelCode: stringValue(json['level_code']),
        displayName: stringValue(json['display_name']),
        description: stringValue(json['description']),
        isMandatory: boolValue(json['is_mandatory']),
        isEnabled: boolValue(json['is_enabled']),
      );
}

class TerritoryHierarchyRecord {
  const TerritoryHierarchyRecord({
    required this.configId,
    required this.firmId,
    required this.businessProfileId,
    required this.maxLevels,
    required this.allowMultiRoutePerSalesman,
    required this.allowMultiSalesmanPerRoute,
    required this.enforceCustomerLeafAssignment,
    required this.levels,
  });

  final String configId;
  final String firmId;
  final String businessProfileId;
  final int maxLevels;
  final bool allowMultiRoutePerSalesman;
  final bool allowMultiSalesmanPerRoute;
  final bool enforceCustomerLeafAssignment;
  final List<TerritoryHierarchyLevelRecord> levels;

  factory TerritoryHierarchyRecord.fromJson(Json json) =>
      TerritoryHierarchyRecord(
        configId: stringValue(json['config_id']),
        firmId: stringValue(json['firm_id']),
        businessProfileId: stringValue(json['business_profile_id']),
        maxLevels: (json['max_levels'] as num?)?.toInt() ?? 0,
        allowMultiRoutePerSalesman:
            boolValue(json['allow_multi_route_per_salesman']),
        allowMultiSalesmanPerRoute:
            boolValue(json['allow_multi_salesman_per_route']),
        enforceCustomerLeafAssignment:
            boolValue(json['enforce_customer_leaf_assignment']),
        levels: _objects(json['levels'])
            .map(TerritoryHierarchyLevelRecord.fromJson)
            .toList(),
      );
}

class SalesTerritory {
  const SalesTerritory({
    required this.id,
    required this.firmId,
    required this.businessProfileId,
    required this.hierarchyLevelId,
    required this.hierarchyLevelName,
    required this.parentId,
    required this.code,
    required this.name,
    required this.description,
    required this.status,
    required this.path,
    required this.sortOrder,
    required this.customerCount,
    required this.activeCustomerCount,
    required this.inactiveCustomerCount,
    required this.newCustomerCount,
    required this.potentialCustomerCount,
    required this.salesmanCount,
    required this.routeProfile,
    required this.isDeleted,
    required this.createdAt,
    required this.updatedAt,
  });

  final String id;
  final String firmId;
  final String businessProfileId;
  final String hierarchyLevelId;
  final String hierarchyLevelName;
  final String parentId;
  final String code;
  final String name;
  final String description;
  final String status;
  final String path;
  final int sortOrder;
  final int customerCount;
  final int activeCustomerCount;
  final int inactiveCustomerCount;
  final int newCustomerCount;
  final int potentialCustomerCount;
  final int salesmanCount;
  final TerritoryRouteProfileRecord? routeProfile;
  final bool isDeleted;
  final String createdAt;
  final String updatedAt;

  factory SalesTerritory.fromJson(Json json) => SalesTerritory(
        id: stringValue(json['id']),
        firmId: stringValue(json['firm_id']),
        businessProfileId: stringValue(json['business_profile_id']),
        hierarchyLevelId: stringValue(json['hierarchy_level_id']),
        hierarchyLevelName: stringValue(json['hierarchy_level_name']),
        parentId: stringValue(json['parent_id']),
        code: stringValue(json['code']),
        name: stringValue(json['name']),
        description: stringValue(json['description']),
        status: stringValue(json['status']),
        path: stringValue(json['path']),
        sortOrder: (json['sort_order'] as num?)?.toInt() ?? 0,
        customerCount: (json['customer_count'] as num?)?.toInt() ?? 0,
        activeCustomerCount:
            (json['active_customer_count'] as num?)?.toInt() ?? 0,
        inactiveCustomerCount:
            (json['inactive_customer_count'] as num?)?.toInt() ?? 0,
        newCustomerCount: (json['new_customer_count'] as num?)?.toInt() ?? 0,
        potentialCustomerCount:
            (json['potential_customer_count'] as num?)?.toInt() ?? 0,
        salesmanCount: (json['salesman_count'] as num?)?.toInt() ?? 0,
        routeProfile: json['route_profile'] is Map
            ? TerritoryRouteProfileRecord.fromJson(
                Map<String, dynamic>.from(json['route_profile'] as Map),
              )
            : null,
        isDeleted: boolValue(json['is_deleted']),
        createdAt: stringValue(json['created_at']),
        updatedAt: stringValue(json['updated_at']),
      );
}

class TerritoryRouteProfileRecord {
  const TerritoryRouteProfileRecord({
    required this.routeTypeId,
    required this.routeTypeName,
    required this.visitFrequency,
    required this.effectiveFrom,
    required this.effectiveTo,
    required this.cityId,
    required this.postalCodeId,
    required this.localityId,
    required this.workingDays,
  });

  final String routeTypeId;
  final String routeTypeName;
  final String visitFrequency;
  final String effectiveFrom;
  final String effectiveTo;
  final String cityId;
  final String postalCodeId;
  final String localityId;
  final List<int> workingDays;

  factory TerritoryRouteProfileRecord.fromJson(Json json) =>
      TerritoryRouteProfileRecord(
        routeTypeId: stringValue(json['route_type_id']),
        routeTypeName: stringValue(json['route_type_name']),
        visitFrequency: stringValue(json['visit_frequency']),
        effectiveFrom: stringValue(json['effective_from']),
        effectiveTo: stringValue(json['effective_to']),
        cityId: stringValue(json['city_id']),
        postalCodeId: stringValue(json['postal_code_id']),
        localityId: stringValue(json['locality_id']),
        workingDays: (json['working_days'] is List)
            ? (json['working_days'] as List)
                .map((item) => (item as num?)?.toInt() ?? 0)
                .where((item) => item > 0)
                .toList()
            : const [],
      );
}

class TerritoryTreeNodeRecord {
  const TerritoryTreeNodeRecord({
    required this.id,
    required this.parentId,
    required this.hierarchyLevelId,
    required this.hierarchyLevelName,
    required this.code,
    required this.name,
    required this.status,
    required this.path,
    required this.children,
  });

  final String id;
  final String parentId;
  final String hierarchyLevelId;
  final String hierarchyLevelName;
  final String code;
  final String name;
  final String status;
  final String path;
  final List<TerritoryTreeNodeRecord> children;

  factory TerritoryTreeNodeRecord.fromJson(Json json) =>
      TerritoryTreeNodeRecord(
        id: stringValue(json['id']),
        parentId: stringValue(json['parent_id']),
        hierarchyLevelId: stringValue(json['hierarchy_level_id']),
        hierarchyLevelName: stringValue(json['hierarchy_level_name']),
        code: stringValue(json['code']),
        name: stringValue(json['name']),
        status: stringValue(json['status']),
        path: stringValue(json['path']),
        children: _objects(json['children'])
            .map(TerritoryTreeNodeRecord.fromJson)
            .toList(),
      );
}

class TerritoryQuery {
  const TerritoryQuery({
    this.hierarchyLevelId,
    this.parentId,
    this.status,
    this.salesmanId,
    this.cityId,
    this.localityId,
    this.routeTypeId,
    this.businessProfileId,
    this.includeDeleted = false,
  });

  final String? hierarchyLevelId;
  final String? parentId;
  final String? status;
  final String? salesmanId;
  final String? cityId;
  final String? localityId;
  final String? routeTypeId;
  final String? businessProfileId;
  final bool includeDeleted;

  Map<String, String> toQuery() => {
        if (hierarchyLevelId?.isNotEmpty == true)
          'hierarchy_level_id': hierarchyLevelId!,
        if (parentId?.isNotEmpty == true) 'parent_id': parentId!,
        if (status?.isNotEmpty == true) 'status': status!,
        if (salesmanId?.isNotEmpty == true) 'salesman_id': salesmanId!,
        if (cityId?.isNotEmpty == true) 'city_id': cityId!,
        if (localityId?.isNotEmpty == true) 'locality_id': localityId!,
        if (routeTypeId?.isNotEmpty == true) 'route_type_id': routeTypeId!,
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
