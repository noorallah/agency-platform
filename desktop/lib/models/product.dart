import 'entities.dart';

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

class ProductCategoryRecord {
  const ProductCategoryRecord({
    required this.id,
    required this.code,
    required this.name,
    required this.parentId,
    required this.level,
    required this.path,
    required this.isActive,
  });

  final String id;
  final String code;
  final String name;
  final String parentId;
  final int level;
  final String path;
  final bool isActive;

  factory ProductCategoryRecord.fromJson(Json json) => ProductCategoryRecord(
        id: stringValue(json['id']),
        code: stringValue(json['code']),
        name: stringValue(json['name']),
        parentId: stringValue(json['parent_id']),
        level: (json['level'] as num?)?.toInt() ?? 0,
        path: stringValue(json['path']),
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
    required this.label,
    required this.taxSystemId,
  });

  final String id;
  final String code;
  final String label;
  final String taxSystemId;

  factory ProductTaxProfileRecord.fromJson(Json json) =>
      ProductTaxProfileRecord(
        id: stringValue(json['id']),
        code: stringValue(json['code']),
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
  });

  final String profileCode;
  final List<ProductFeatureState> features;
  final List<ProductCategoryRecord> categories;
  final List<ProductTaxProfileRecord> taxProfiles;
  final List<String> requiredAttributeDefinitionIds;
  final List<String> optionalAttributeDefinitionIds;

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
      );
}

class Product {
  const Product({
    required this.id,
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
    required this.unit,
    required this.brand,
    required this.model,
    required this.hsnSac,
    required this.taxProfileId,
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
    required this.mrp,
    required this.status,
    required this.remarks,
    required this.isDeleted,
    required this.createdAt,
    required this.updatedAt,
    required this.attributes,
    required this.media,
  });

  final String id;
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
  final String unit;
  final String brand;
  final String model;
  final String hsnSac;
  final String taxProfileId;
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
  final String mrp;
  final String status;
  final String remarks;
  final bool isDeleted;
  final String createdAt;
  final String updatedAt;
  final List<ProductAttributeValueRecord> attributes;
  final List<ProductMediaRecord> media;

  factory Product.fromJson(Json json) => Product(
        id: stringValue(json['id']),
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
        unit: stringValue(json['unit']),
        brand: stringValue(json['brand']),
        model: stringValue(json['model']),
        hsnSac: stringValue(json['hsn_sac']),
        taxProfileId: stringValue(json['tax_profile_id']),
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
        mrp: stringValue(json['mrp']),
        status: stringValue(json['status']),
        remarks: stringValue(json['remarks']),
        isDeleted: boolValue(json['is_deleted']),
        createdAt: stringValue(json['created_at']),
        updatedAt: stringValue(json['updated_at']),
        attributes: _objects(json['attributes'])
            .map(ProductAttributeValueRecord.fromJson)
            .toList(),
        media:
            _objects(json['media']).map(ProductMediaRecord.fromJson).toList(),
      );
}

class ProductQuery {
  const ProductQuery({
    this.status,
    this.productType,
    this.categoryId,
    this.taxProfileId,
    this.brand,
    this.hsnSac,
    this.attributeQuery,
    this.includeDeleted = false,
  });

  final String? status;
  final String? productType;
  final String? categoryId;
  final String? taxProfileId;
  final String? brand;
  final String? hsnSac;
  final String? attributeQuery;
  final bool includeDeleted;

  Map<String, String> toQuery() => {
        if (status?.isNotEmpty == true) 'status': status!,
        if (productType?.isNotEmpty == true) 'product_type': productType!,
        if (categoryId?.isNotEmpty == true) 'category_id': categoryId!,
        if (taxProfileId?.isNotEmpty == true) 'tax_profile_id': taxProfileId!,
        if (brand?.isNotEmpty == true) 'brand': brand!,
        if (hsnSac?.isNotEmpty == true) 'hsn_sac': hsnSac!,
        if (attributeQuery?.isNotEmpty == true)
          'attribute_query': attributeQuery!,
        if (includeDeleted) 'include_deleted': 'true',
      };
}

List<Json> _objects(dynamic value) => value is List
    ? value
        .whereType<Map>()
        .map((item) => Map<String, dynamic>.from(item))
        .toList()
    : const [];
