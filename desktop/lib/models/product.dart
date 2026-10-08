import 'entities.dart';

/// A stored custom-field value on any record: customers and vendors carry
/// the same shape products always did.
typedef AttributeValueRecord = ProductAttributeValueRecord;

class ProductAttributeValueRecord {
  const ProductAttributeValueRecord({
    required this.id,
    required this.attributeDefinitionId,
    required this.valueText,
    required this.valueNumber,
    required this.valueDate,
    required this.valueBoolean,
  });

  final String id;
  final String attributeDefinitionId;
  final String valueText;
  final String valueNumber;
  final String valueDate;
  final bool? valueBoolean;

  factory ProductAttributeValueRecord.fromJson(Json json) =>
      ProductAttributeValueRecord(
        id: stringValue(json['id']),
        attributeDefinitionId: stringValue(json['attribute_definition_id']),
        valueText: stringValue(json['value_text']),
        valueNumber: stringValue(json['value_number']),
        valueDate: stringValue(json['value_date']),
        valueBoolean: json['value_boolean'] is bool
            ? json['value_boolean'] as bool
            : null,
      );
}

class ProductMediaRecord {
  const ProductMediaRecord({
    required this.id,
    required this.mediaKind,
    required this.fileName,
    required this.mimeType,
    required this.storagePath,
    required this.isPrimary,
  });

  final String id;
  final String mediaKind;
  final String fileName;
  final String mimeType;
  final String storagePath;
  final bool isPrimary;

  factory ProductMediaRecord.fromJson(Json json) => ProductMediaRecord(
        id: stringValue(json['id']),
        mediaKind: stringValue(json['media_kind']),
        fileName: stringValue(json['file_name']),
        mimeType: stringValue(json['mime_type']),
        storagePath: stringValue(json['storage_path']),
        isPrimary: boolValue(json['is_primary']),
      );
}

int? _optInt(Object? v) => v is num ? v.toInt() : null;

class ProductCategoryRecord {
  const ProductCategoryRecord({
    required this.id,
    required this.code,
    required this.name,
    required this.parentId,
    required this.level,
    required this.path,
    required this.isActive,
    this.requiredLicenceTypeId = '',
    this.inspectionRequired = false,
    this.expiryStopSaleDays,
    this.expiryAlertDays,
    this.expiryReturnDays,
    this.goodsTypeId = '',
  });

  final String id;
  final String code;
  final String name;
  final String parentId;

  /// The goods type products filed here start with; empty is General, which
  /// tracks nothing.
  final String goodsTypeId;
  final int level;
  final String path;
  final bool isActive;

  /// The trade licence a product filed under this category needs, unless the
  /// product or a nearer category names its own (backlog 54). Empty means
  /// none -- a category's own is never required by inheriting nothing.
  final String requiredLicenceTypeId;

  /// Goods of this category wait in quarantine on receipt until inspected
  /// (BUY-9).
  final bool inspectionRequired;

  /// Expiry windows in days before expiry (STK-5); null takes the firm's.
  final int? expiryStopSaleDays;
  final int? expiryAlertDays;
  final int? expiryReturnDays;

  factory ProductCategoryRecord.fromJson(Json json) => ProductCategoryRecord(
        id: stringValue(json['id']),
        code: stringValue(json['code']),
        name: stringValue(json['name']),
        parentId: stringValue(json['parent_id']),
        level: (json['level'] as num?)?.toInt() ?? 0,
        path: stringValue(json['path']),
        isActive: boolValue(json['is_active'], fallback: true),
        requiredLicenceTypeId: stringValue(json['required_licence_type_id']),
        inspectionRequired: boolValue(json['inspection_required']),
        expiryStopSaleDays: _optInt(json['expiry_stop_sale_days']),
        expiryAlertDays: _optInt(json['expiry_alert_days']),
        expiryReturnDays: _optInt(json['expiry_return_days']),
        goodsTypeId: stringValue(json['goods_type_id']),
      );
}

/// A goods type -- how a line of goods is tracked (Medicine, Food, Paint...).
///
/// A row with no [firmId] is the shared catalogue: a firm may take it into use
/// and set its own defaults, but not change it.
class GoodsTypeRecord {
  const GoodsTypeRecord({
    required this.id,
    required this.firmId,
    required this.code,
    required this.name,
    required this.description,
    required this.trackBatch,
    required this.trackExpiry,
    required this.trackManufacturingDate,
    required this.trackSerial,
    required this.trackWarranty,
    required this.isActive,
    required this.inUse,
    required this.defaultHsnSac,
    required this.defaultTaxProfileGroupCode,
    required this.version,
  });

  final String id;

  /// Empty for a shared type.
  final String firmId;
  final String code;
  final String name;
  final String description;
  final bool trackBatch;
  final bool trackExpiry;
  final bool trackManufacturingDate;
  final bool trackSerial;
  final bool trackWarranty;
  final bool isActive;

  /// Whether this firm has taken the type into use.
  final bool inUse;
  final String defaultHsnSac;
  final String defaultTaxProfileGroupCode;
  final int version;

  bool get isShared => firmId.isEmpty;

  /// The tracking switches in words, for the grid.
  String get tracks {
    final List<String> parts = <String>[
      if (trackBatch) 'Batch',
      if (trackExpiry) 'expiry',
      if (trackManufacturingDate) 'manufacturing date',
      if (trackSerial) 'serial numbers',
      if (trackWarranty) 'warranty',
    ];
    return parts.isEmpty ? 'Nothing' : parts.join(', ');
  }

  factory GoodsTypeRecord.fromJson(Json json) => GoodsTypeRecord(
        id: stringValue(json['id']),
        firmId: stringValue(json['firm_id']),
        code: stringValue(json['code']),
        name: stringValue(json['name']),
        description: stringValue(json['description']),
        trackBatch: boolValue(json['track_batch']),
        trackExpiry: boolValue(json['track_expiry']),
        trackManufacturingDate: boolValue(json['track_manufacturing_date']),
        trackSerial: boolValue(json['track_serial']),
        trackWarranty: boolValue(json['track_warranty']),
        isActive: boolValue(json['is_active'], fallback: true),
        inUse: boolValue(json['in_use']),
        defaultHsnSac: stringValue(json['default_hsn_sac']),
        defaultTaxProfileGroupCode:
            stringValue(json['default_tax_profile_group_code']),
        version: (json['version'] as num?)?.toInt() ?? 0,
      );
}

/// A principal -- the company whose brands the firm distributes (MST-1).
class PrincipalRecord {
  const PrincipalRecord({
    required this.id,
    required this.code,
    required this.name,
    required this.vendorId,
    required this.isActive,
  });

  final String id;
  final String code;
  final String name;

  /// The supplier this principal is bought through; empty when none.
  final String vendorId;
  final bool isActive;

  factory PrincipalRecord.fromJson(Json json) => PrincipalRecord(
        id: stringValue(json['id']),
        code: stringValue(json['code']),
        name: stringValue(json['name']),
        vendorId: stringValue(json['vendor_id']),
        isActive: boolValue(json['is_active'], fallback: true),
      );
}

/// A brand a product can carry, optionally filed under a principal (MST-1).
class BrandRecord {
  const BrandRecord({
    required this.id,
    required this.name,
    required this.principalId,
    required this.principalName,
    required this.isActive,
  });

  final String id;
  final String name;
  final String principalId;
  final String principalName;
  final bool isActive;

  factory BrandRecord.fromJson(Json json) => BrandRecord(
        id: stringValue(json['id']),
        name: stringValue(json['name']),
        principalId: stringValue(json['principal_id']),
        principalName: stringValue(json['principal_name']),
        isActive: boolValue(json['is_active'], fallback: true),
      );
}

class ProductFeatureState {
  const ProductFeatureState({required this.code, required this.enabled});

  final String code;
  final bool enabled;

  factory ProductFeatureState.fromJson(Json json) => ProductFeatureState(
        code: stringValue(json['code']),
        enabled: boolValue(json['enabled']),
      );
}

class ProductTaxProfileRecord {
  const ProductTaxProfileRecord({
    required this.id,
    required this.code,
    required this.groupCode,
    required this.label,
    required this.taxSystemId,
  });

  final String id;
  final String code;
  final String groupCode;
  final String label;
  final String taxSystemId;

  factory ProductTaxProfileRecord.fromJson(Json json) =>
      ProductTaxProfileRecord(
        id: stringValue(json['id']),
        code: stringValue(json['code']),
        groupCode: stringValue(json['group_code']),
        label: stringValue(json['label']),
        taxSystemId: stringValue(json['tax_system_id']),
      );
}

class ProductMetadataRecord {
  const ProductMetadataRecord({
    required this.profileCode,
    required this.features,
    required this.categories,
    required this.taxProfiles,
    required this.requiredAttributeDefinitionIds,
    required this.optionalAttributeDefinitionIds,
    this.goodsTypes = const [],
    this.goodsTypeId = '',
    this.unitSets = const [],
  });

  final String profileCode;
  final List<ProductFeatureState> features;
  final List<ProductCategoryRecord> categories;
  final List<ProductTaxProfileRecord> taxProfiles;
  final List<String> requiredAttributeDefinitionIds;
  final List<String> optionalAttributeDefinitionIds;

  /// Every goods type the firm can see, with what a new product of the type
  /// starts with. Empty from an older server.
  final List<ProductGoodsTypeOption> goodsTypes;

  /// The type a product filed under the asked category takes; empty is
  /// General (also empty when no category was asked).
  final String goodsTypeId;

  /// The active unit sets the firm may pick (shared and its own), by name.
  /// Empty from an older server.
  final List<ProductUnitSetOption> unitSets;

  ProductUnitSetOption? unitSetById(String id) {
    if (id.isEmpty) return null;
    for (final ProductUnitSetOption set in unitSets) {
      if (set.id == id) return set;
    }
    return null;
  }

  ProductGoodsTypeOption? goodsTypeById(String id) {
    if (id.isEmpty) return null;
    for (final ProductGoodsTypeOption type in goodsTypes) {
      if (type.id == id) return type;
    }
    return null;
  }

  bool featureEnabled(String code) =>
      features.any((item) => item.code.toUpperCase() == code && item.enabled);

  factory ProductMetadataRecord.fromJson(Json json) => ProductMetadataRecord(
        profileCode: stringValue(json['profile_code']),
        features: _objects(json['features'])
            .map(ProductFeatureState.fromJson)
            .toList(),
        categories: _objects(json['categories'])
            .map(ProductCategoryRecord.fromJson)
            .toList(),
        taxProfiles: _objects(json['tax_profiles'])
            .map(ProductTaxProfileRecord.fromJson)
            .toList(),
        requiredAttributeDefinitionIds:
            stringList(json['required_attribute_definition_ids']),
        optionalAttributeDefinitionIds:
            stringList(json['optional_attribute_definition_ids']),
        goodsTypes: _objects(json['goods_types'])
            .map(ProductGoodsTypeOption.fromJson)
            .toList(),
        goodsTypeId: stringValue(json['goods_type_id']),
        unitSets: _objects(json['unit_sets'])
            .map(ProductUnitSetOption.fromJson)
            .toList(),
      );
}

/// A unit set as the product form reads it from the metadata call. An empty
/// unit id is a slot the set leaves alone; empty [goodsTypeIds] means the set
/// is offered to every product.
class ProductUnitSetOption {
  const ProductUnitSetOption({
    required this.id,
    required this.name,
    this.baseUomId = '',
    this.inventoryUomId = '',
    this.purchaseUomId = '',
    this.salesUomId = '',
    this.minimumSalesUomId = '',
    this.defaultReceivingUomId = '',
    this.defaultDispatchUomId = '',
    this.allowDecimal = true,
    this.conversionFactor = '',
    this.goodsTypeIds = const [],
  });

  final String id;
  final String name;
  final String baseUomId;
  final String inventoryUomId;
  final String purchaseUomId;
  final String salesUomId;
  final String minimumSalesUomId;
  final String defaultReceivingUomId;
  final String defaultDispatchUomId;
  final bool allowDecimal;

  /// "1 purchase unit = N stock units"; empty when the set carries none.
  final String conversionFactor;
  final List<String> goodsTypeIds;

  factory ProductUnitSetOption.fromJson(Json json) => ProductUnitSetOption(
        id: stringValue(json['id']),
        name: stringValue(json['name']),
        baseUomId: stringValue(json['base_uom_id']),
        inventoryUomId: stringValue(json['inventory_uom_id']),
        purchaseUomId: stringValue(json['purchase_uom_id']),
        salesUomId: stringValue(json['sales_uom_id']),
        minimumSalesUomId: stringValue(json['minimum_sales_uom_id']),
        defaultReceivingUomId: stringValue(json['default_receiving_uom_id']),
        defaultDispatchUomId: stringValue(json['default_dispatch_uom_id']),
        allowDecimal: boolValue(json['allow_decimal'], fallback: true),
        conversionFactor: stringValue(json['conversion_factor']),
        goodsTypeIds: stringList(json['goods_type_ids']),
      );
}

/// A goods type as the product form reads it from the metadata call.
class ProductGoodsTypeOption {
  const ProductGoodsTypeOption({
    required this.id,
    required this.code,
    required this.name,
    this.switches = const {},
    this.defaultHsnSac = '',
    this.defaultTaxProfileGroupCode = '',
  });

  final String id;
  final String code;
  final String name;

  /// What a new product of this type starts with, applied verbatim.
  final Map<String, bool> switches;
  final String defaultHsnSac;
  final String defaultTaxProfileGroupCode;

  factory ProductGoodsTypeOption.fromJson(Json json) {
    final Object? raw = json['switches'];
    return ProductGoodsTypeOption(
      id: stringValue(json['id']),
      code: stringValue(json['code']),
      name: stringValue(json['name']),
      switches: raw is Map
          ? {
              for (final MapEntry<dynamic, dynamic> entry in raw.entries)
                entry.key.toString(): entry.value == true,
            }
          : const {},
      defaultHsnSac: stringValue(json['default_hsn_sac']),
      defaultTaxProfileGroupCode:
          stringValue(json['default_tax_profile_group_code']),
    );
  }
}

class Product {
  const Product({
    required this.id,
    this.version = 0,
    required this.firmId,
    required this.code,
    required this.barcode,
    required this.qrCode,
    required this.name,
    required this.shortName,
    required this.description,
    required this.productType,
    required this.categoryId,
    required this.subCategoryId,
    this.requiredLicenceTypeId = '',
    this.preferredVendorId = '',
    required this.unit,
    required this.brand,
    this.brandId = '',
    required this.model,
    required this.hsnSac,
    this.taxProfileGroupCode = '',
    this.itcEligibility = 'ELIGIBLE',
    String? taxProfileId,
    this.baseUomId = '',
    this.inventoryUomId = '',
    this.purchaseUomId = '',
    this.salesUomId = '',
    this.defaultReceivingUomId = '',
    this.defaultDispatchUomId = '',
    this.minimumSalesUomId = '',
    this.weight = '',
    this.volume = '',
    this.length = '',
    this.width = '',
    this.height = '',
    this.allowFraction = false,
    this.allowDecimal = true,
    required this.purchasePrice,
    required this.sellingPrice,
    this.minimumSellingPrice = '',
    required this.mrp,
    this.purchasePriceInForce = '',
    this.sellingPriceInForce = '',
    this.mrpInForce = '',
    required this.status,
    required this.remarks,
    this.trackBatch = false,
    this.trackLot = false,
    this.trackSerial = false,
    this.trackExpiry = false,
    this.trackManufacturingDate = false,
    this.trackWarranty = false,
    this.notForSale = false,
    this.freeIssueOnly = false,
    this.inspectionRequired = false,
    this.shelfLifeDays,
    this.expiryStopSaleDays,
    this.expiryAlertDays,
    this.expiryReturnDays,
    this.issueRule = '',
    this.allowNegativeStock = false,
    this.requireBatchOnReceipt = false,
    this.requireBatchOnIssue = false,
    this.requireSerialOnReceipt = false,
    this.requireSerialOnIssue = false,
    required this.isDeleted,
    required this.createdAt,
    required this.updatedAt,
    required this.attributes,
    required this.media,
    this.stockOnHand = '',
    this.lowStock = false,
    this.packCodes = const <String>[],
    this.goodsTypeId = '',
    this.unitSetId = '',
  });

  final String id;

  /// The unit set the product's units were filled from when it was created
  /// (read-only; never sent on an update). Empty when none.
  final String unitSetId;

  /// The goods type the product stores (read-only here; it changes only by
  /// moving the product to another category). Empty is General.
  final String goodsTypeId;

  /// The optimistic-concurrency version this record was read at, sent back
  /// as `If-Match` on save so a concurrent edit is refused rather than
  /// silently overwritten. Zero means the server published none, and the
  /// save then carries no precondition.
  final int version;
  final String firmId;
  final String code;
  final String barcode;
  final String qrCode;
  final String name;
  final String shortName;
  final String description;
  final String productType;
  final String categoryId;
  final String subCategoryId;

  /// The trade licence this product needs, overriding its category's; empty
  /// takes the category's (backlog 54).
  final String requiredLicenceTypeId;

  /// The supplier reorder orders this from; empty falls back to the supplier
  /// last billed (A18). The server sends the id only, not the name.
  final String preferredVendorId;
  final String unit;
  final String brand;

  /// The brand master the product is filed under (MST-1); empty for a
  /// product that only carries the free-text [brand].
  final String brandId;
  final String model;
  final String hsnSac;
  final String taxProfileGroupCode;

  /// Whether the GST on buying this can be claimed as input credit:
  /// ELIGIBLE, BLOCKED (s.17(5)) or INELIGIBLE (backlog 78 row 1).
  final String itcEligibility;
  final String baseUomId;
  final String inventoryUomId;
  final String purchaseUomId;
  final String salesUomId;
  final String defaultReceivingUomId;
  final String defaultDispatchUomId;
  final String minimumSalesUomId;
  final String weight;
  final String volume;
  final String length;
  final String width;
  final String height;
  final bool allowFraction;
  final bool allowDecimal;
  final String purchasePrice;
  final String sellingPrice;

  /// The price floor, per stock unit; empty when the product has none.
  final String minimumSellingPrice;
  final String mrp;

  /// The three prices as they stand today, after any dated revision that has
  /// started (D-PRC-15); the figures above are the product's own card. Empty
  /// from an older server.
  final String purchasePriceInForce;
  final String sellingPriceInForce;
  final String mrpInForce;

  static String _differing(String card, String inForce) {
    final double? now = double.tryParse(inForce);
    if (now == null || now == double.tryParse(card)) return '';
    return inForce;
  }

  /// What a document dated today takes, where it is not the card price; empty
  /// when the two agree or the server did not say.
  String get purchaseInForceNow =>
      _differing(purchasePrice, purchasePriceInForce);
  String get sellingInForceNow => _differing(sellingPrice, sellingPriceInForce);
  String get mrpInForceNow => _differing(mrp, mrpInForce);
  final String status;
  final String remarks;
  final bool trackBatch;
  final bool trackLot;
  final bool trackSerial;
  final bool trackExpiry;
  final bool trackManufacturingDate;
  final bool trackWarranty;

  /// Bought and stocked but never sold -- packing material, consumables
  /// (STK-17). The server refuses it on every new sales line.
  final bool notForSale;

  /// Received goods wait in quarantine until passed (BUY-9).
  /// Promotional stock: given away, never sold at a price (BUY-1).
  final bool freeIssueOnly;
  final bool inspectionRequired;

  /// Days from manufacture to expiry (STK-18): a receipt typed with only a
  /// manufacturing date gets its expiry from it. Null fills nothing.
  final int? shelfLifeDays;

  /// Expiry windows in days before expiry (STK-5); null inherits the
  /// category's, then the firm's.
  final int? expiryStopSaleDays;
  final int? expiryAlertDays;
  final int? expiryReturnDays;

  /// FEFO, FIFO or PICK (STK-11); empty is earliest expiry.
  final String issueRule;
  final bool allowNegativeStock;
  final bool requireBatchOnReceipt;
  final bool requireBatchOnIssue;
  final bool requireSerialOnReceipt;
  final bool requireSerialOnIssue;
  final bool isDeleted;
  final String createdAt;
  final String updatedAt;
  final List<ProductAttributeValueRecord> attributes;
  final List<ProductMediaRecord> media;

  /// The quantity on hand across every warehouse; empty when no warehouse
  /// has ever held the product, which is not a stock of zero.
  final String stockOnHand;

  /// Held at or below its reorder level somewhere -- shown in red.
  final bool lowStock;

  /// Every barcode, GTIN, EAN and UPC a pack of this product carries, so a
  /// product box finds it by a carton's code as by its own (backlog 89).
  final List<String> packCodes;

  factory Product.fromJson(Json json) => Product(
        id: stringValue(json['id']),
        version: (json['version'] as num?)?.toInt() ?? 0,
        firmId: stringValue(json['firm_id']),
        code: stringValue(json['code']),
        barcode: stringValue(json['barcode']),
        qrCode: stringValue(json['qr_code']),
        name: stringValue(json['name']),
        shortName: stringValue(json['short_name']),
        description: stringValue(json['description']),
        productType: stringValue(json['product_type']),
        categoryId: stringValue(json['category_id']),
        subCategoryId: stringValue(json['sub_category_id']),
        requiredLicenceTypeId: stringValue(json['required_licence_type_id']),
        preferredVendorId: stringValue(json['preferred_vendor_id']),
        unit: stringValue(json['unit']),
        brand: stringValue(json['brand']),
        brandId: stringValue(json['brand_id']),
        model: stringValue(json['model']),
        hsnSac: stringValue(json['hsn_sac']),
        taxProfileGroupCode:
            stringValue(json['tax_profile_group_code']).isNotEmpty
                ? stringValue(json['tax_profile_group_code'])
                : stringValue(json['tax_profile_id']),
        itcEligibility: stringValue(json['itc_eligibility']).isNotEmpty
            ? stringValue(json['itc_eligibility'])
            : 'ELIGIBLE',
        baseUomId: stringValue(json['base_uom_id']),
        inventoryUomId: stringValue(json['inventory_uom_id']),
        purchaseUomId: stringValue(json['purchase_uom_id']),
        salesUomId: stringValue(json['sales_uom_id']),
        defaultReceivingUomId: stringValue(json['default_receiving_uom_id']),
        defaultDispatchUomId: stringValue(json['default_dispatch_uom_id']),
        minimumSalesUomId: stringValue(json['minimum_sales_uom_id']),
        weight: stringValue(json['weight']),
        volume: stringValue(json['volume']),
        length: stringValue(json['length']),
        width: stringValue(json['width']),
        height: stringValue(json['height']),
        allowFraction: boolValue(json['allow_fraction']),
        allowDecimal: boolValue(json['allow_decimal'], fallback: true),
        purchasePrice: stringValue(json['purchase_price']),
        sellingPrice: stringValue(json['selling_price']),
        minimumSellingPrice: stringValue(json['minimum_selling_price']),
        mrp: stringValue(json['mrp']),
        purchasePriceInForce: stringValue(json['purchase_price_in_force']),
        sellingPriceInForce: stringValue(json['selling_price_in_force']),
        mrpInForce: stringValue(json['mrp_in_force']),
        status: stringValue(json['status']),
        remarks: stringValue(json['remarks']),
        trackBatch: boolValue(json['track_batch']),
        trackLot: boolValue(json['track_lot']),
        trackSerial: boolValue(json['track_serial']),
        trackExpiry: boolValue(json['track_expiry']),
        trackManufacturingDate: boolValue(json['track_manufacturing_date']),
        trackWarranty: boolValue(json['track_warranty']),
        notForSale: boolValue(json['not_for_sale']),
        inspectionRequired: boolValue(json['inspection_required']),
        freeIssueOnly: boolValue(json['free_issue_only']),
        issueRule: stringValue(json['issue_rule']),
        shelfLifeDays: json['shelf_life_days'] is num
            ? (json['shelf_life_days'] as num).toInt()
            : null,
        expiryStopSaleDays: _optInt(json['expiry_stop_sale_days']),
        expiryAlertDays: _optInt(json['expiry_alert_days']),
        expiryReturnDays: _optInt(json['expiry_return_days']),
        allowNegativeStock: boolValue(json['allow_negative_stock']),
        requireBatchOnReceipt: boolValue(json['require_batch_on_receipt']),
        requireBatchOnIssue: boolValue(json['require_batch_on_issue']),
        requireSerialOnReceipt: boolValue(json['require_serial_on_receipt']),
        requireSerialOnIssue: boolValue(json['require_serial_on_issue']),
        isDeleted: boolValue(json['is_deleted']),
        createdAt: stringValue(json['created_at']),
        updatedAt: stringValue(json['updated_at']),
        attributes: _objects(json['attributes'])
            .map(ProductAttributeValueRecord.fromJson)
            .toList(),
        media:
            _objects(json['media']).map(ProductMediaRecord.fromJson).toList(),
        stockOnHand: stringValue(json['stock_on_hand']),
        lowStock: boolValue(json['low_stock']),
        packCodes: <String>[
          for (final Object? code
              in json['pack_codes'] as List<dynamic>? ?? const <dynamic>[])
            if (stringValue(code).isNotEmpty) stringValue(code),
        ],
        goodsTypeId: stringValue(json['goods_type_id']),
        unitSetId: stringValue(json['unit_set_id']),
      );
}

class ProductQuery {
  const ProductQuery({
    this.status,
    this.productType,
    this.categoryId,
    this.goodsTypeId,
    this.generalGoods = false,
    this.taxProfileGroupCode,
    this.brand,
    this.hsnSac,
    this.attributeQuery,
    this.includeDeleted = false,
    this.lowStock = false,
    this.noPrice = false,
  });

  final String? status;
  final String? productType;
  final String? categoryId;

  /// Only products of this goods type (backlog 89).
  final String? goodsTypeId;

  /// Only products with no goods type -- General.
  final bool generalGoods;
  final String? taxProfileGroupCode;
  final String? brand;
  final String? hsnSac;
  final String? attributeQuery;
  final bool includeDeleted;

  /// Only products some warehouse holds at or below its reorder level.
  final bool lowStock;

  /// Only products with no selling price.
  final bool noPrice;

  Map<String, String> toQuery() => {
        if (status?.isNotEmpty == true) 'status': status!,
        if (productType?.isNotEmpty == true) 'product_type': productType!,
        if (categoryId?.isNotEmpty == true) 'category_id': categoryId!,
        if (goodsTypeId?.isNotEmpty == true) 'goods_type_id': goodsTypeId!,
        if (generalGoods) 'general_goods': 'true',
        if (taxProfileGroupCode?.isNotEmpty == true)
          'tax_profile_group_code': taxProfileGroupCode!,
        if (brand?.isNotEmpty == true) 'brand': brand!,
        if (hsnSac?.isNotEmpty == true) 'hsn_sac': hsnSac!,
        if (attributeQuery?.isNotEmpty == true)
          'attribute_query': attributeQuery!,
        if (includeDeleted) 'include_deleted': 'true',
        if (lowStock) 'low_stock': 'true',
        if (noPrice) 'no_price': 'true',
      };
}

List<Json> _objects(dynamic value) => value is List
    ? value
        .whereType<Map>()
        .map((item) => Map<String, dynamic>.from(item))
        .toList()
    : const [];

/// The custom fields a form should offer for one entity type, from
/// `GET /business-framework/attribute-definitions/applicable`.
class ApplicableAttributesRecord {
  const ApplicableAttributesRecord({
    required this.entityType,
    required this.definitions,
    required this.mandatoryIds,
    this.kindRules = const [],
  });

  final String entityType;
  final List<AttributeDefinitionRecord> definitions;

  /// Fields required whatever the kind of record.
  final List<String> mandatoryIds;

  /// The rules tying a field to a goods type, customer group or supplier type.
  final List<KindRuleRecord> kindRules;

  factory ApplicableAttributesRecord.fromJson(Json json) =>
      ApplicableAttributesRecord(
        entityType: stringValue(json['entity_type']),
        definitions: (json['definitions'] as List? ?? const [])
            .whereType<Map>()
            .map((item) => AttributeDefinitionRecord.fromJson(
                Map<String, dynamic>.from(item)))
            .toList(),
        mandatoryIds: (json['mandatory_ids'] as List? ?? const [])
            .map((item) => stringValue(item))
            .toList(),
        kindRules: (json['kind_rules'] as List? ?? const [])
            .whereType<Map>()
            .map((item) => KindRuleRecord.fromJson(
                Map<String, dynamic>.from(item)))
            .toList(),
      );
}

/// One rule tying a custom field to a kind of record: the field is shown only
/// on records of the kinds its rules name, and [isMandatory] says whether it
/// must be filled there. Exactly one of the three ids is set.
class KindRuleRecord {
  const KindRuleRecord({
    required this.attributeDefinitionId,
    this.goodsTypeId = '',
    this.customerGroupId = '',
    this.vendorTypeId = '',
    this.isMandatory = false,
  });

  final String attributeDefinitionId, goodsTypeId, customerGroupId, vendorTypeId;
  final bool isMandatory;

  factory KindRuleRecord.fromJson(Json json) => KindRuleRecord(
        attributeDefinitionId: stringValue(json['attribute_definition_id']),
        goodsTypeId: stringValue(json['goods_type_id']),
        customerGroupId: stringValue(json['customer_group_id']),
        vendorTypeId: stringValue(json['vendor_type_id']),
        isMandatory: boolValue(json['is_mandatory']),
      );
}
