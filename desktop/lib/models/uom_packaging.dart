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

/// A named template of units that fills a new product's unit fields in one
/// choice. `firmId` empty is the shared catalogue, read-only to a firm.
///
/// `goodsTypeIds` empty means the set is offered to every product. The
/// conversion is "1 purchase unit = [conversionFactor] stock units".
class UnitSet {
  const UnitSet({
    required this.id,
    required this.firmId,
    required this.name,
    required this.description,
    required this.baseUomId,
    required this.inventoryUomId,
    required this.purchaseUomId,
    required this.salesUomId,
    required this.minimumSalesUomId,
    required this.defaultReceivingUomId,
    required this.defaultDispatchUomId,
    required this.allowDecimal,
    required this.conversionFactor,
    required this.isActive,
    required this.goodsTypeIds,
    required this.version,
  });

  final String id;
  final String firmId;
  final String name;
  final String description;
  final String baseUomId;
  final String inventoryUomId;
  final String purchaseUomId;
  final String salesUomId;
  final String minimumSalesUomId;
  final String defaultReceivingUomId;
  final String defaultDispatchUomId;
  final bool allowDecimal;

  /// Empty when the set carries no conversion.
  final String conversionFactor;
  final bool isActive;
  final List<String> goodsTypeIds;
  final int version;

  bool get isShared => firmId.isEmpty;

  factory UnitSet.fromJson(Json json) => UnitSet(
        id: stringValue(json['id']),
        firmId: stringValue(json['firm_id']),
        name: stringValue(json['name']),
        description: stringValue(json['description']),
        baseUomId: stringValue(json['base_uom_id']),
        inventoryUomId: stringValue(json['inventory_uom_id']),
        purchaseUomId: stringValue(json['purchase_uom_id']),
        salesUomId: stringValue(json['sales_uom_id']),
        minimumSalesUomId: stringValue(json['minimum_sales_uom_id']),
        defaultReceivingUomId: stringValue(json['default_receiving_uom_id']),
        defaultDispatchUomId: stringValue(json['default_dispatch_uom_id']),
        allowDecimal: boolValue(json['allow_decimal'], fallback: true),
        conversionFactor: stringValue(json['conversion_factor']),
        isActive: boolValue(json['is_active'], fallback: true),
        goodsTypeIds: json['goods_type_ids'] is List
            ? <String>[
                for (final dynamic id in json['goods_type_ids'] as List)
                  stringValue(id),
              ]
            : const <String>[],
        version: (json['version'] as num?)?.toInt() ?? 0,
      );
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
    this.uomCode = '',
    this.stockUomCode = '',
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

  /// The unit the pack is recorded in (BOX); empty where it names none.
  final String uomCode;

  /// The product's stock unit: what [baseQuantity] counts in, and the unit of
  /// a document line that names none.
  final String stockUomCode;

  factory BarcodeLookup.fromJson(Json json) => BarcodeLookup(
        code: stringValue(json['code']),
        productId: stringValue(json['product_id']),
        productCode: stringValue(json['product_code']),
        productName: stringValue(json['product_name']),
        baseQuantity: stringValue(json['base_quantity']),
        packagingLevelId: stringValue(json['packaging_level_id']),
        levelName: stringValue(json['level_name']),
        matchedField: stringValue(json['matched_field']),
        uomCode: stringValue(json['uom_code']),
        stockUomCode: stringValue(json['stock_uom_code']),
      );
}
