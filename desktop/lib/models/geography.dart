import 'entities.dart';

/// One rung of the shared geography ladder.
///
/// Six near-identical masters — country, state, district, city, postal code,
/// locality — each with its own endpoint, its own parent, and very nearly the
/// same fields. Modelling them as data rather than as six screens keeps the
/// browser to one page and one dialog; the only real differences are which
/// field carries the label and which extra fields a country has.
enum GeoLevel {
  country(
    path: 'countries',
    label: 'Country',
    plural: 'Countries',
    parentQuery: null,
    parentField: null,
  ),
  state(
    path: 'states',
    label: 'State',
    plural: 'States',
    parentQuery: 'country_id',
    parentField: 'country_id',
  ),
  district(
    path: 'districts',
    label: 'District',
    plural: 'Districts',
    parentQuery: 'state_id',
    parentField: 'state_id',
  ),
  city(
    path: 'cities',
    label: 'City',
    plural: 'Cities',
    parentQuery: 'district_id',
    parentField: 'district_id',
  ),
  postalCode(
    path: 'postal-codes',
    label: 'Postal code',
    plural: 'Postal codes',
    parentQuery: 'city_id',
    parentField: 'city_id',
  ),
  locality(
    path: 'localities',
    label: 'Locality',
    plural: 'Localities',
    parentQuery: 'postal_code_id',
    parentField: 'postal_code_id',
  );

  const GeoLevel({
    required this.path,
    required this.label,
    required this.plural,
    required this.parentQuery,
    required this.parentField,
  });

  /// The URL segment under `/geo/`.
  final String path;
  final String label;
  final String plural;

  /// The query parameter that filters this level by its parent, if it has one.
  final String? parentQuery;

  /// The body field naming this row's parent, if it has one.
  final String? parentField;

  /// The level below this one, or null at the bottom of the ladder.
  GeoLevel? get child {
    final int next = index + 1;
    return next < GeoLevel.values.length ? GeoLevel.values[next] : null;
  }

  /// The level above this one, or null at the top.
  GeoLevel? get parent => index == 0 ? null : GeoLevel.values[index - 1];

  /// Whether rows at this level carry a `code` distinct from their name.
  ///
  /// A postal code *is* its code and a locality has only a name, so neither
  /// takes a separate one — the form would otherwise ask for a code and the
  /// API would refuse the field.
  bool get hasCode => switch (this) {
        GeoLevel.country ||
        GeoLevel.state ||
        GeoLevel.district ||
        GeoLevel.city =>
          true,
        GeoLevel.postalCode || GeoLevel.locality => false,
      };

  /// Whether rows carry the ISO and phone fields only a country has.
  bool get hasIsoFields => this == GeoLevel.country;
}

/// One row at any level of the geography ladder.
class GeoPlaceRecord {
  const GeoPlaceRecord({
    required this.level,
    required this.id,
    required this.code,
    required this.name,
    required this.parentId,
    required this.isActive,
    this.iso2 = '',
    this.iso3 = '',
    this.phoneCode = '',
    this.version = 0,
  });

  final GeoLevel level;
  final String id;

  /// Empty for a locality, and the postal code itself for a postal code.
  final String code;

  /// What the row is called. A postal code has no separate name, so this
  /// repeats the code — the grid then has something to show in every row.
  final String name;
  final String parentId;
  final bool isActive;
  final String iso2;
  final String iso3;
  final String phoneCode;

  /// The optimistic-concurrency version this row was read at, sent back as
  /// `If-Match` on save so a concurrent edit is refused rather than silently
  /// overwritten. Zero means the server published none.
  final int version;

  factory GeoPlaceRecord.fromJson(GeoLevel level, Json json) {
    final String postal = stringValue(json['postal_code']);
    final String name = stringValue(json['name']);
    return GeoPlaceRecord(
      level: level,
      id: stringValue(json['id']),
      code: level == GeoLevel.postalCode ? postal : stringValue(json['code']),
      name: name.isNotEmpty ? name : postal,
      parentId: level.parentField == null
          ? ''
          : stringValue(json[level.parentField!]),
      isActive: json['is_active'] != false,
      iso2: stringValue(json['iso2']),
      iso3: stringValue(json['iso3']),
      phoneCode: stringValue(json['phone_code']),
      version: (json['version'] as num?)?.toInt() ?? 0,
    );
  }

  /// The request body for a create or update at this level.
  Json toJson({String parentId = ''}) => <String, dynamic>{
        if (level.parentField != null)
          level.parentField!: parentId.isEmpty ? this.parentId : parentId,
        if (level == GeoLevel.postalCode)
          'postal_code': code
        else if (level == GeoLevel.locality)
          'name': name
        else ...<String, dynamic>{'code': code, 'name': name},
        'is_active': isActive,
        if (level.hasIsoFields) ...<String, dynamic>{
          'iso2': iso2.isEmpty ? null : iso2,
          'iso3': iso3.isEmpty ? null : iso3,
          'phone_code': phoneCode.isEmpty ? null : phoneCode,
        },
      };
}

/// One state in the India Post places pack the server ships with
/// (`GET /sales-territories/geo/places-pack`).
class PlacesPackState {
  const PlacesPackState({
    required this.code,
    required this.name,
    required this.available,
    required this.postOffices,
    required this.postalCodes,
    required this.districts,
    required this.districtsHeld,
    required this.isDefault,
  });

  factory PlacesPackState.fromJson(Map<String, dynamic> json) =>
      PlacesPackState(
        code: (json['code'] ?? '').toString(),
        name: (json['name'] ?? '').toString(),
        available: json['available'] != false,
        postOffices: _packInt(json['post_offices']),
        postalCodes: _packInt(json['postal_codes']),
        districts: _packInt(json['districts']),
        districtsHeld: _packInt(json['districts_held']),
        isDefault: json['default'] == true,
      );

  final String code;
  final String name;

  /// False when this store has no such state to hang places under.
  final bool available;
  final int postOffices;
  final int postalCodes;
  final int districts;

  /// Districts this store already holds for the state.
  final int districtsHeld;

  /// Pre-ticked in the load dialog.
  final bool isDefault;
}

/// What loading the pack did for one state.
class PlacesPackResult {
  const PlacesPackResult({
    required this.code,
    required this.name,
    required this.districts,
    required this.cities,
    required this.postalCodes,
    required this.localities,
    required this.skipped,
    required this.note,
  });

  factory PlacesPackResult.fromJson(Map<String, dynamic> json) =>
      PlacesPackResult(
        code: (json['code'] ?? '').toString(),
        name: (json['name'] ?? '').toString(),
        districts: _packInt(json['districts']),
        cities: _packInt(json['cities']),
        postalCodes: _packInt(json['postal_codes']),
        localities: _packInt(json['localities']),
        skipped: _packInt(json['skipped']),
        note: (json['note'] ?? '').toString(),
      );

  final String code;
  final String name;
  final int districts;
  final int cities;
  final int postalCodes;
  final int localities;
  final int skipped;
  final String note;
}

int _packInt(dynamic value) =>
    value is num ? value.toInt() : int.tryParse('$value') ?? 0;
