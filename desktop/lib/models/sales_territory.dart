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
    this.version = 0,
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

  /// The optimistic-concurrency version this record was read at, sent back
  /// as `If-Match` on save so a concurrent edit is refused rather than
  /// silently overwritten. Zero means the server published none.
  final int version;

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
      version: (json['version'] as num?)?.toInt() ?? 0,
    );
}

/// A kind of round the firm runs: a sales beat, a collection round.
class TerritoryRouteTypeRecord {
  const TerritoryRouteTypeRecord({
    required this.id,
    required this.code,
    required this.name,
    this.description = '',
    required this.isActive,
    this.version = 0,
  });

  final String id;
  final String code;
  final String name;
  final String description;
  final bool isActive;

  /// The optimistic-concurrency version this record was read at, sent back
  /// as `If-Match` on save so a concurrent edit is refused rather than
  /// silently overwritten. Zero means the server published none.
  final int version;

  String get label => '$code  $name';

  factory TerritoryRouteTypeRecord.fromJson(Json json) =>
      TerritoryRouteTypeRecord(
        id: stringValue(json['id']),
        code: stringValue(json['code']),
        name: stringValue(json['name']),
        description: stringValue(json['description']),
        isActive: json['is_active'] as bool? ?? true,
      version: (json['version'] as num?)?.toInt() ?? 0,
    );
}

/// One customer's place on a round.
class TerritoryCustomerAssignmentRecord {
  const TerritoryCustomerAssignmentRecord({
    required this.customerId,
    required this.isPrimary,
    required this.visitSequence,
    required this.isPotential,
  });

  final String customerId;
  final bool isPrimary;

  /// Where this customer falls in the call order. Null means nobody has placed
  /// them yet, and the server sorts those to the end of the round.
  final int? visitSequence;
  final bool isPotential;

  factory TerritoryCustomerAssignmentRecord.fromJson(Json json) =>
      TerritoryCustomerAssignmentRecord(
        customerId: stringValue(json['customer_id']),
        isPrimary: json['is_primary'] == true,
        visitSequence: json['visit_sequence'] is num
            ? (json['visit_sequence'] as num).toInt()
            : null,
        isPotential: json['is_potential'] == true,
      );

  /// Deliberately without `is_primary`.
  ///
  /// The server treats an absent flag as "leave it alone", which is what keeps
  /// a re-save from demoting the round somebody chose as primary — and the
  /// primary round is the one a sale is filed under. Sending it back would
  /// also collide with the one-primary-per-customer key the moment a shop is
  /// put on a second round, which is exactly what the Route Builder does.
  /// Deliberately without `is_primary`, and `is_potential` only when it is
  /// being changed.
  ///
  /// The server treats an absent flag as "leave it alone". That is what keeps
  /// a re-save from demoting the round somebody chose as primary — and what
  /// stops every save wiping the potential flag, which is displayed on the
  /// call order dialog and counted on the grid and could only ever read zero
  /// while three screens sent a hardcoded `false`.
  Json toJson({bool includePotential = false}) => <String, dynamic>{
        'customer_id': customerId,
        'visit_sequence': visitSequence,
        if (includePotential) 'is_potential': isPotential,
      };

  TerritoryCustomerAssignmentRecord withSequence(int? sequence) =>
      TerritoryCustomerAssignmentRecord(
        customerId: customerId,
        isPrimary: isPrimary,
        visitSequence: sequence,
        isPotential: isPotential,
      );
}

/// A recurring round: which route runs, and on which days.
class BeatPlanRecord {
  const BeatPlanRecord({
    required this.id,
    required this.territoryId,
    required this.code,
    required this.name,
    required this.planType,
    required this.weekday,
    required this.weekOfMonth,
    required this.startsOn,
    required this.endsOn,
    required this.isActive,
    required this.notes,
    required this.stops,
    this.version = 0,
  });

  final String id;
  final String territoryId;
  final String code;
  final String name;

  /// WEEKLY, FORTNIGHTLY, MONTHLY or CUSTOM.
  final String planType;

  /// ISO weekday 1-7. Meaningful for every plan type except CUSTOM.
  final int? weekday;

  /// Which week of the month, for a MONTHLY plan.
  final int? weekOfMonth;
  final String startsOn;
  final String endsOn;
  final bool isActive;
  final String notes;
  final List<BeatPlanStopRecord> stops;

  /// The optimistic-concurrency version this record was read at, sent back
  /// as `If-Match` on save so a concurrent edit is refused rather than
  /// silently overwritten. Zero means the server published none.
  final int version;

  factory BeatPlanRecord.fromJson(Json json) => BeatPlanRecord(
        id: stringValue(json['id']),
        territoryId: stringValue(json['territory_id']),
        code: stringValue(json['code']),
        name: stringValue(json['name']),
        planType: stringValue(json['plan_type']),
        weekday:
            json['weekday'] is num ? (json['weekday'] as num).toInt() : null,
        weekOfMonth: json['week_of_month'] is num
            ? (json['week_of_month'] as num).toInt()
            : null,
        startsOn: stringValue(json['starts_on']),
        endsOn: stringValue(json['ends_on']),
        isActive: json['is_active'] != false,
        notes: stringValue(json['notes']),
        stops: <BeatPlanStopRecord>[
          for (final dynamic row in (json['stops'] as List? ?? const []))
            if (row is Map)
              BeatPlanStopRecord.fromJson(Map<String, dynamic>.from(row)),
        ],
      version: (json['version'] as num?)?.toInt() ?? 0,
    );
}

/// One leg of a beat plan. A stop is a territory, not an outlet — the outlets
/// are whoever is assigned to that territory, in their call order.
class BeatPlanStopRecord {
  const BeatPlanStopRecord({
    required this.id,
    required this.territoryId,
    required this.stopOrder,
    required this.plannedDurationMinutes,
  });

  final String id;
  final String territoryId;
  final int stopOrder;
  final int? plannedDurationMinutes;

  factory BeatPlanStopRecord.fromJson(Json json) => BeatPlanStopRecord(
        id: stringValue(json['id']),
        territoryId: stringValue(json['territory_id']),
        stopOrder:
            json['stop_order'] is num ? (json['stop_order'] as num).toInt() : 0,
        plannedDurationMinutes: json['planned_duration_minutes'] is num
            ? (json['planned_duration_minutes'] as num).toInt()
            : null,
      );
}

/// One outlet on a call list, in the order the round walks it.
class CallListStopRecord {
  const CallListStopRecord({
    required this.customerId,
    required this.customerCode,
    required this.customerName,
    required this.stopOrder,
    required this.plannedDurationMinutes,
  });

  final String customerId;
  final String customerCode;
  final String customerName;
  final int stopOrder;
  final int? plannedDurationMinutes;

  factory CallListStopRecord.fromJson(Json json) => CallListStopRecord(
        customerId: stringValue(json['customer_id']),
        customerCode: stringValue(json['customer_code']),
        customerName: stringValue(json['customer_name']),
        stopOrder:
            json['stop_order'] is num ? (json['stop_order'] as num).toInt() : 0,
        plannedDurationMinutes: json['planned_duration_minutes'] is num
            ? (json['planned_duration_minutes'] as num).toInt()
            : null,
      );
}

/// What one beat plan asks for on one date.
///
/// [occurs] is answered even when false and [reason] says why, because "this
/// round does not run today" and "this plan cannot be computed" are different
/// answers — a screen that shows an empty list for both misreports one of them.
class CallListEntryRecord {
  const CallListEntryRecord({
    required this.beatPlanId,
    required this.beatPlanCode,
    required this.beatPlanName,
    required this.territoryId,
    required this.territoryCode,
    required this.territoryName,
    required this.salesmanId,
    required this.occurs,
    required this.reason,
    required this.stops,
  });

  final String beatPlanId;
  final String beatPlanCode;
  final String beatPlanName;
  final String territoryId;
  final String territoryCode;
  final String territoryName;
  final String salesmanId;
  final bool occurs;
  final String reason;
  final List<CallListStopRecord> stops;

  factory CallListEntryRecord.fromJson(Json json) => CallListEntryRecord(
        beatPlanId: stringValue(json['beat_plan_id']),
        beatPlanCode: stringValue(json['beat_plan_code']),
        beatPlanName: stringValue(json['beat_plan_name']),
        territoryId: stringValue(json['territory_id']),
        territoryCode: stringValue(json['territory_code']),
        territoryName: stringValue(json['territory_name']),
        salesmanId: stringValue(json['salesman_id']),
        occurs: json['occurs'] == true,
        reason: stringValue(json['reason']),
        stops: <CallListStopRecord>[
          for (final dynamic row in (json['stops'] as List? ?? const []))
            if (row is Map)
              CallListStopRecord.fromJson(Map<String, dynamic>.from(row)),
        ],
      );
}

/// Every plan's call list for one date.
class CallListRecord {
  const CallListRecord({required this.onDate, required this.entries});

  final String onDate;
  final List<CallListEntryRecord> entries;

  factory CallListRecord.fromJson(Json json) => CallListRecord(
        onDate: stringValue(json['on_date']),
        entries: <CallListEntryRecord>[
          for (final dynamic row in (json['entries'] as List? ?? const []))
            if (row is Map)
              CallListEntryRecord.fromJson(Map<String, dynamic>.from(row)),
        ],
      );
}

/// One outlet a round could call, with enough address to find it by.
///
/// The customer list cannot answer "which shops on this pin code are not on a
/// round yet" — it filters on city and state and nothing finer, and knows
/// nothing about territory assignment.
class AssignableCustomerRecord {
  const AssignableCustomerRecord({
    required this.customerId,
    required this.code,
    required this.name,
    required this.addressLine,
    required this.area,
    required this.city,
    required this.postalCode,
    required this.onThisRoute,
    required this.visitSequence,
    required this.otherRoutes,
    this.isPotential = false,
  });

  final String customerId;
  final String code;
  final String name;
  final String addressLine;
  final String area;
  final String city;
  final String postalCode;

  /// Already on the round being built, and where in its order.
  final bool onThisRoute;
  final int? visitSequence;

  /// Other rounds already calling this shop. Information, not a warning — a
  /// distributor calls the same outlet on a sales beat and a collection round.
  final List<String> otherRoutes;

  /// A prospect on this round rather than a buyer.
  final bool isPotential;

  factory AssignableCustomerRecord.fromJson(Json json) =>
      AssignableCustomerRecord(
        customerId: stringValue(json['customer_id']),
        code: stringValue(json['code']),
        name: stringValue(json['name']),
        addressLine: stringValue(json['address_line']),
        area: stringValue(json['area']),
        city: stringValue(json['city']),
        postalCode: stringValue(json['postal_code']),
        onThisRoute: json['on_this_route'] == true,
        visitSequence: json['visit_sequence'] is num
            ? (json['visit_sequence'] as num).toInt()
            : null,
        otherRoutes: <String>[
          for (final dynamic row in (json['other_routes'] as List? ?? const []))
            stringValue(row),
        ],
        isPotential: json['is_potential'] == true,
      );
}

/// How much of the firm's ground one salesperson covers.
class TerritoryCoverageRecord {
  const TerritoryCoverageRecord({
    required this.userId,
    required this.assignedTerritories,
    required this.assignedRoutes,
    required this.customerCount,
    required this.coveragePercent,
  });

  final String userId;
  final int assignedTerritories;
  final int assignedRoutes;
  final int customerCount;

  /// Share of the firm's assigned customers this person is responsible for.
  final double coveragePercent;

  factory TerritoryCoverageRecord.fromJson(Json json) => TerritoryCoverageRecord(
        userId: stringValue(json['user_id']),
        assignedTerritories: json['assigned_territories'] is num
            ? (json['assigned_territories'] as num).toInt()
            : 0,
        assignedRoutes: json['assigned_routes'] is num
            ? (json['assigned_routes'] as num).toInt()
            : 0,
        customerCount: json['customer_count'] is num
            ? (json['customer_count'] as num).toInt()
            : 0,
        coveragePercent: json['coverage_percent'] is num
            ? (json['coverage_percent'] as num).toDouble()
            : 0,
      );
}

/// One round that calls a given shop, and where in it.
class CustomerRouteRecord {
  const CustomerRouteRecord({
    required this.territoryId,
    required this.code,
    required this.name,
    required this.path,
    required this.isRoute,
    required this.isPrimary,
    required this.visitSequence,
  });

  final String territoryId;
  final String code;
  final String name;
  final String path;
  final bool isRoute;

  /// The round a sale for this shop is filed under.
  final bool isPrimary;
  final int? visitSequence;

  factory CustomerRouteRecord.fromJson(Json json) => CustomerRouteRecord(
        territoryId: stringValue(json['territory_id']),
        code: stringValue(json['code']),
        name: stringValue(json['name']),
        path: stringValue(json['path']),
        isRoute: json['is_route'] == true,
        isPrimary: json['is_primary'] == true,
        visitSequence: json['visit_sequence'] is num
            ? (json['visit_sequence'] as num).toInt()
            : null,
      );
}

/// Somebody the firm can put on a route.
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
