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
  });

  final String id;
  final String code;
  final String name;
  final String symbol;
  final String dimension;
  final String status;
  final bool isDecimalAllowed;

  factory UomRecord.fromJson(Json json) => UomRecord(
        id: stringValue(json['id']),
        code: stringValue(json['code']),
        name: stringValue(json['name']),
        symbol: stringValue(json['symbol']),
        dimension: stringValue(json['dimension']),
        status: stringValue(json['status']),
        isDecimalAllowed: boolValue(json['is_decimal_allowed'], fallback: true),
      );
}

class UomGroupRecord {
  const UomGroupRecord({
    required this.id,
    required this.code,
    required this.name,
    required this.description,
    required this.status,
  });

  final String id;
  final String code;
  final String name;
  final String description;
  final String status;

  factory UomGroupRecord.fromJson(Json json) => UomGroupRecord(
        id: stringValue(json['id']),
        code: stringValue(json['code']),
        name: stringValue(json['name']),
        description: stringValue(json['description']),
        status: stringValue(json['status']),
      );
}

class PackagingTypeRecord {
  const PackagingTypeRecord({
    required this.id,
    required this.code,
    required this.name,
    required this.description,
    required this.status,
  });

  final String id;
  final String code;
  final String name;
  final String description;
  final String status;

  factory PackagingTypeRecord.fromJson(Json json) => PackagingTypeRecord(
        id: stringValue(json['id']),
        code: stringValue(json['code']),
        name: stringValue(json['name']),
        description: stringValue(json['description']),
        status: stringValue(json['status']),
      );
}

class ConversionRuleRecord {
  const ConversionRuleRecord({
    required this.id,
    required this.productId,
    required this.fromUomId,
    required this.toUomId,
    required this.conversionFactor,
    required this.version,
    required this.effectiveFrom,
    required this.effectiveTo,
    required this.status,
  });

  final String id;
  final String productId;
  final String fromUomId;
  final String toUomId;
  final String conversionFactor;
  final int version;
  final String effectiveFrom;
  final String effectiveTo;
  final String status;

  factory ConversionRuleRecord.fromJson(Json json) => ConversionRuleRecord(
        id: stringValue(json['id']),
        productId: stringValue(json['product_id']),
        fromUomId: stringValue(json['from_uom_id']),
        toUomId: stringValue(json['to_uom_id']),
        conversionFactor: stringValue(json['conversion_factor']),
        version: int.tryParse(stringValue(json['version'])) ?? 1,
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
