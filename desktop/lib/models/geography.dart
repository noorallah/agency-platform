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
