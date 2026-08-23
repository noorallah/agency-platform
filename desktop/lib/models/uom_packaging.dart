import 'entities.dart';

class UomRecord {
  const UomRecord({
    required this.id,
    required this.code,
    required this.name,
    required this.symbol,
    required this.dimension,
    required this.status,
    required this.isDecimalAllowed,
    this.version = 0,
  });

  final String id;
  final String code;
  final String name;
  final String symbol;
  final String dimension;
  final String status;
  final bool isDecimalAllowed;

  /// The optimistic-concurrency version this record was read at, sent back as
  /// `If-Match` on save so a concurrent edit is refused rather than silently
  /// overwritten. Zero means the server published none, and the save then
  /// carries no precondition.
  final int version;

  factory UomRecord.fromJson(Json json) => UomRecord(
        id: stringValue(json['id']),
        code: stringValue(json['code']),
        name: stringValue(json['name']),
        symbol: stringValue(json['symbol']),
        dimension: stringValue(json['dimension']),
        status: stringValue(json['status']),
        isDecimalAllowed: boolValue(json['is_decimal_allowed'], fallback: true),
        version: (json['version'] as num?)?.toInt() ?? 0,
      );
}

class UomGroupRecord {
  const UomGroupRecord({
    required this.id,
    required this.code,
    required this.name,
    required this.description,
    required this.status,
    this.version = 0,
  });

  final String id;
  final String code;
  final String name;
  final String description;
  final String status;

  /// The optimistic-concurrency version this record was read at, sent back as
  /// `If-Match` on save so a concurrent edit is refused rather than silently
  /// overwritten. Zero means the server published none, and the save then
  /// carries no precondition.
  final int version;

  factory UomGroupRecord.fromJson(Json json) => UomGroupRecord(
        id: stringValue(json['id']),
        code: stringValue(json['code']),
        name: stringValue(json['name']),
        description: stringValue(json['description']),
        status: stringValue(json['status']),
        version: (json['version'] as num?)?.toInt() ?? 0,
      );
}

class PackagingTypeRecord {
  const PackagingTypeRecord({
    required this.id,
    required this.code,
    required this.name,
    required this.description,
    required this.status,
    this.version = 0,
  });

  final String id;
  final String code;
  final String name;
  final String description;
  final String status;

  /// The optimistic-concurrency version this record was read at, sent back as
  /// `If-Match` on save so a concurrent edit is refused rather than silently
  /// overwritten. Zero means the server published none, and the save then
  /// carries no precondition.
  final int version;

  factory PackagingTypeRecord.fromJson(Json json) => PackagingTypeRecord(
        id: stringValue(json['id']),
        code: stringValue(json['code']),
        name: stringValue(json['name']),
        description: stringValue(json['description']),
        status: stringValue(json['status']),
        version: (json['version'] as num?)?.toInt() ?? 0,
      );
}

class ConversionRuleRecord {
  const ConversionRuleRecord({
    required this.id,
    required this.productId,
    required this.fromUomId,
    required this.toUomId,
    required this.conversionFactor,
    required this.versionNumber,
    required this.effectiveFrom,
    required this.effectiveTo,
    required this.status,
    this.version = 0,
  });

  final String id;
  final String productId;
  final String fromUomId;
  final String toUomId;
  final String conversionFactor;

  /// The rule's published revision -- what a document line records as the
  /// factor it converted with. Not a concurrency counter.
  final int versionNumber;
  final String effectiveFrom;
  final String effectiveTo;
  final String status;

  /// The optimistic-concurrency version this record was read at, sent back as
  /// `If-Match` on save so a concurrent edit is refused rather than silently
  /// overwritten. Zero means the server published none, and the save then
  /// carries no precondition.
  final int version;

  factory ConversionRuleRecord.fromJson(Json json) => ConversionRuleRecord(
        id: stringValue(json['id']),
        productId: stringValue(json['product_id']),
        fromUomId: stringValue(json['from_uom_id']),
        toUomId: stringValue(json['to_uom_id']),
        conversionFactor: stringValue(json['conversion_factor']),
        versionNumber:
            int.tryParse(stringValue(json['version_number'])) ?? 1,
        version: (json['version'] as num?)?.toInt() ?? 0,
        effectiveFrom: stringValue(json['effective_from']),
        effectiveTo: stringValue(json['effective_to']),
        status: stringValue(json['status']),
      );
}

class IndustryTemplateRecord {
  const IndustryTemplateRecord({
    required this.id,
    required this.code,
    required this.name,
    required this.industryType,
    required this.status,
  });

  final String id;
  final String code;
  final String name;
  final String industryType;
  final String status;

  factory IndustryTemplateRecord.fromJson(Json json) => IndustryTemplateRecord(
        id: stringValue(json['id']),
        code: stringValue(json['code']),
        name: stringValue(json['name']),
        industryType: stringValue(json['industry_type']),
        status: stringValue(json['status']),
      );
}


/// A business profile's default unit behaviour, as the calling firm sees it.
///
/// `firmId` is what tells the two cases apart: null means this is the
/// profile-wide default every firm on the profile inherits, a value means this
/// firm has its own override. Saving always writes the firm's own row — the
/// profile-wide one is seeded and is not editable through the API.
class BusinessProfileUomDefaults {
  const BusinessProfileUomDefaults({
    required this.businessProfileId,
    required this.firmId,
    required this.baseUomId,
    required this.inventoryUomId,
    required this.purchaseUomId,
    required this.salesUomId,
    required this.allowFraction,
    required this.allowDecimal,
  });

  final String businessProfileId;
  final String? firmId;
  final String? baseUomId;
  final String? inventoryUomId;
  final String? purchaseUomId;
  final String? salesUomId;
  final bool allowFraction;
  final bool allowDecimal;

  /// True when these values come from the profile rather than this firm.
  bool get isInherited => firmId == null;

  factory BusinessProfileUomDefaults.fromJson(Json json) =>
      BusinessProfileUomDefaults(
        businessProfileId: stringValue(json['business_profile_id']),
        firmId: _orNull(json['firm_id']),
        baseUomId: _orNull(json['base_uom_id']),
        inventoryUomId: _orNull(json['inventory_uom_id']),
        purchaseUomId: _orNull(json['purchase_uom_id']),
        salesUomId: _orNull(json['sales_uom_id']),
        allowFraction: boolValue(json['allow_fraction']),
        allowDecimal: boolValue(json['allow_decimal'], fallback: true),
      );

  static String? _orNull(dynamic value) {
    final String text = stringValue(value);
    return text.isEmpty ? null : text;
  }

  Json toJson() => <String, dynamic>{
        'base_uom_id': baseUomId,
        'inventory_uom_id': inventoryUomId,
        'purchase_uom_id': purchaseUomId,
        'sales_uom_id': salesUomId,
        'allow_fraction': allowFraction,
        'allow_decimal': allowDecimal,
      };
}


/// One rung of a product's physical packaging hierarchy.
///
/// A piece goes in a box, a box in a carton, a carton on a pallet, and each
/// rung carries its own barcode so a scanner reading a carton label knows it
/// is holding 120 pieces. `conversionToBaseFactor` is how many base units one
/// of these is.
///
/// Deliberately not the same thing as a conversion rule: rules are what
/// documents convert with and are effective-dated; levels describe the
/// physical packaging and carry the codes printed on it.
class PackagingLevelRecord {
  const PackagingLevelRecord({
    required this.id,
    required this.productId,
    required this.levelName,
    required this.conversionToBaseFactor,
    this.parentLevelId = '',
    this.packagingTypeId = '',
    this.uomId = '',
    this.barcode = '',
    this.gtin = '',
    this.ean = '',
    this.upc = '',
    this.status = 'ACTIVE',
    this.displayOrder = 0,
    this.version = 0,
  });

  final String id;
  final String productId;
  final String levelName;

  /// How many base units one of these holds.
  final String conversionToBaseFactor;

  final String parentLevelId;
  final String packagingTypeId;
  final String uomId;
  final String barcode;
  final String gtin;
  final String ean;
  final String upc;
  final String status;
  final int displayOrder;

  /// The optimistic-concurrency version this record was read at, sent back as
  /// `If-Match` on save. Zero means the server published none.
  final int version;

  factory PackagingLevelRecord.fromJson(Json json) => PackagingLevelRecord(
        id: stringValue(json['id']),
        productId: stringValue(json['product_id']),
        levelName: stringValue(json['level_name']),
        conversionToBaseFactor:
            stringValue(json['conversion_to_base_factor']).isEmpty
                ? '1'
                : stringValue(json['conversion_to_base_factor']),
        parentLevelId: stringValue(json['parent_level_id']),
        packagingTypeId: stringValue(json['packaging_type_id']),
        uomId: stringValue(json['uom_id']),
        barcode: stringValue(json['barcode']),
        gtin: stringValue(json['gtin']),
        ean: stringValue(json['ean']),
        upc: stringValue(json['upc']),
        status: stringValue(json['status']).isEmpty
            ? 'ACTIVE'
            : stringValue(json['status']),
        displayOrder: (json['display_order'] as num?)?.toInt() ?? 0,
        version: (json['version'] as num?)?.toInt() ?? 0,
      );
}

/// What one scanned code turned out to be.
class BarcodeLookup {
  const BarcodeLookup({
    required this.code,
    required this.productId,
    required this.productCode,
    required this.productName,
    required this.baseQuantity,
    this.packagingLevelId = '',
    this.levelName = '',
    this.matchedField = '',
  });

  final String code;
  final String productId;
  final String productCode;
  final String productName;

  /// How many base units one scan of this code represents.
  final String baseQuantity;

  /// Empty where the code is the product's own barcode, which is one unit.
  final String packagingLevelId;
  final String levelName;

  /// `barcode`, `gtin`, `ean`, `upc`, or `product`.
  final String matchedField;

  factory BarcodeLookup.fromJson(Json json) => BarcodeLookup(
        code: stringValue(json['code']),
        productId: stringValue(json['product_id']),
        productCode: stringValue(json['product_code']),
        productName: stringValue(json['product_name']),
        baseQuantity: stringValue(json['base_quantity']),
        packagingLevelId: stringValue(json['packaging_level_id']),
        levelName: stringValue(json['level_name']),
        matchedField: stringValue(json['matched_field']),
      );
}
