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

