import 'entities.dart';

int _intValue(dynamic value) {
  if (value == null) return 0;
  if (value is int) return value;
  return int.tryParse(value.toString()) ?? 0;
}

class BatchRecord {
  const BatchRecord({
    required this.id,
    required this.firmId,
    required this.productId,
    required this.productCode,
    required this.productName,
    required this.warehouseId,
    required this.warehouseCode,
    required this.warehouseName,
    required this.branchId,
    required this.branchCode,
    required this.branchName,
    required this.batchNumber,
    required this.supplierBatch,
    required this.internalBatch,
    required this.manufacturingDate,
    required this.expiryDate,
    required this.bestBeforeDate,
    required this.status,
    required this.quantity,
    required this.availableQuantity,
    required this.reservedQuantity,
    required this.blockedQuantity,
    required this.damagedQuantity,
    required this.quarantineQuantity,
    required this.shelfLifeDays,
    required this.remarks,
    required this.isDeleted,
    required this.createdAt,
    required this.updatedAt,
  });

  final String id;
  final String firmId;
  final String productId;
  final String productCode;
  final String productName;
  final String warehouseId;
  final String warehouseCode;
  final String warehouseName;
  final String branchId;
  final String branchCode;
  final String branchName;
  final String batchNumber;
  final String supplierBatch;
  final String internalBatch;
  final String manufacturingDate;
  final String expiryDate;
  final String bestBeforeDate;
  final String status;
  final String quantity;
  final String availableQuantity;
  final String reservedQuantity;
  final String blockedQuantity;
  final String damagedQuantity;
  final String quarantineQuantity;
  final int? shelfLifeDays;
  final String remarks;
  final bool isDeleted;
  final String createdAt;
  final String updatedAt;

  factory BatchRecord.fromJson(Json json) {
    final Json d = json.containsKey('data') ? Map<String, dynamic>.from(json['data'] as Map) : json;
    return BatchRecord(
      id: stringValue(d['id']),
      firmId: stringValue(d['firm_id']),
      productId: stringValue(d['product_id']),
      productCode: stringValue(d['product_code']),
      productName: stringValue(d['product_name']),
      warehouseId: stringValue(d['warehouse_id']),
      warehouseCode: stringValue(d['warehouse_code']),
      warehouseName: stringValue(d['warehouse_name']),
      branchId: stringValue(d['branch_id']),
      branchCode: stringValue(d['branch_code']),
      branchName: stringValue(d['branch_name']),
      batchNumber: stringValue(d['batch_number']),
      supplierBatch: stringValue(d['supplier_batch']),
      internalBatch: stringValue(d['internal_batch']),
      manufacturingDate: stringValue(d['manufacturing_date']),
      expiryDate: stringValue(d['expiry_date']),
      bestBeforeDate: stringValue(d['best_before_date']),
      status: stringValue(d['status']),
      quantity: stringValue(d['quantity']),
      availableQuantity: stringValue(d['available_quantity']),
      reservedQuantity: stringValue(d['reserved_quantity']),
      blockedQuantity: stringValue(d['blocked_quantity']),
      damagedQuantity: stringValue(d['damaged_quantity']),
      quarantineQuantity: stringValue(d['quarantine_quantity']),
      shelfLifeDays: d['shelf_life_days'] as int?,
      remarks: stringValue(d['remarks']),
      isDeleted: boolValue(d['is_deleted']),
      createdAt: stringValue(d['created_at']),
      updatedAt: stringValue(d['updated_at']),
    );
  }
}

class LotRecord {
  const LotRecord({
    required this.id,
    required this.firmId,
    required this.productId,
    required this.productCode,
    required this.productName,
    required this.warehouseId,
    required this.warehouseCode,
    required this.warehouseName,
    required this.branchId,
    required this.branchCode,
    required this.branchName,
    required this.lotNumber,
    required this.lotType,
    required this.status,
    required this.quantity,
    required this.availableQuantity,
    required this.productionDate,
    required this.expiryDate,
    required this.parentLotId,
    required this.remarks,
    required this.isDeleted,
    required this.createdAt,
    required this.updatedAt,
  });

  final String id;
  final String firmId;
  final String productId;
  final String productCode;
  final String productName;
  final String warehouseId;
  final String warehouseCode;
  final String warehouseName;
  final String branchId;
  final String branchCode;
  final String branchName;
  final String lotNumber;
  final String lotType;
  final String status;
  final String quantity;
  final String availableQuantity;
  final String productionDate;
  final String expiryDate;
  final String parentLotId;
  final String remarks;
  final bool isDeleted;
  final String createdAt;
  final String updatedAt;

  factory LotRecord.fromJson(Json json) {
    final Json d = json.containsKey('data') ? Map<String, dynamic>.from(json['data'] as Map) : json;
    return LotRecord(
      id: stringValue(d['id']),
      firmId: stringValue(d['firm_id']),
      productId: stringValue(d['product_id']),
      productCode: stringValue(d['product_code']),
      productName: stringValue(d['product_name']),
      warehouseId: stringValue(d['warehouse_id']),
      warehouseCode: stringValue(d['warehouse_code']),
      warehouseName: stringValue(d['warehouse_name']),
      branchId: stringValue(d['branch_id']),
      branchCode: stringValue(d['branch_code']),
      branchName: stringValue(d['branch_name']),
      lotNumber: stringValue(d['lot_number']),
      lotType: stringValue(d['lot_type']),
      status: stringValue(d['status']),
      quantity: stringValue(d['quantity']),
      availableQuantity: stringValue(d['available_quantity']),
      productionDate: stringValue(d['production_date']),
      expiryDate: stringValue(d['expiry_date']),
      parentLotId: stringValue(d['parent_lot_id']),
      remarks: stringValue(d['remarks']),
      isDeleted: boolValue(d['is_deleted']),
      createdAt: stringValue(d['created_at']),
      updatedAt: stringValue(d['updated_at']),
    );
  }
}

class SerialRecord {
  const SerialRecord({
    required this.id,
    required this.firmId,
    required this.productId,
    required this.productCode,
    required this.productName,
    required this.inventoryId,
    required this.warehouseId,
    required this.warehouseCode,
    required this.warehouseName,
    required this.branchId,
    required this.branchCode,
    required this.branchName,
    required this.batchId,
    required this.batchNumber,
    required this.serialNumber,
    required this.status,
    required this.manufacturedDate,
    required this.warrantyStart,
    required this.warrantyEnd,
    required this.currentOwner,
    required this.assetReference,
    required this.remarks,
    required this.isDeleted,
    required this.createdAt,
    required this.updatedAt,
  });

  final String id;
  final String firmId;
  final String productId;
  final String productCode;
  final String productName;
  final String inventoryId;
  final String warehouseId;
  final String warehouseCode;
  final String warehouseName;
  final String branchId;
  final String branchCode;
  final String branchName;
  final String batchId;
  final String batchNumber;
  final String serialNumber;
  final String status;
  final String manufacturedDate;
  final String warrantyStart;
  final String warrantyEnd;
  final String currentOwner;
  final String assetReference;
  final String remarks;
  final bool isDeleted;
  final String createdAt;
  final String updatedAt;

  factory SerialRecord.fromJson(Json json) {
    final Json d = json.containsKey('data') ? Map<String, dynamic>.from(json['data'] as Map) : json;
    return SerialRecord(
      id: stringValue(d['id']),
      firmId: stringValue(d['firm_id']),
      productId: stringValue(d['product_id']),
      productCode: stringValue(d['product_code']),
      productName: stringValue(d['product_name']),
      inventoryId: stringValue(d['inventory_id']),
      warehouseId: stringValue(d['warehouse_id']),
      warehouseCode: stringValue(d['warehouse_code']),
      warehouseName: stringValue(d['warehouse_name']),
      branchId: stringValue(d['branch_id']),
      branchCode: stringValue(d['branch_code']),
      branchName: stringValue(d['branch_name']),
      batchId: stringValue(d['batch_id']),
      batchNumber: stringValue(d['batch_number']),
      serialNumber: stringValue(d['serial_number']),
      status: stringValue(d['status']),
      manufacturedDate: stringValue(d['manufactured_date']),
      warrantyStart: stringValue(d['warranty_start']),
      warrantyEnd: stringValue(d['warranty_end']),
      currentOwner: stringValue(d['current_owner']),
      assetReference: stringValue(d['asset_reference']),
      remarks: stringValue(d['remarks']),
      isDeleted: boolValue(d['is_deleted']),
      createdAt: stringValue(d['created_at']),
      updatedAt: stringValue(d['updated_at']),
    );
  }
}

class BatchSummaryRecord {
  const BatchSummaryRecord({
    required this.totalBatches,
    required this.nearExpiry,
    required this.expired,
    required this.quarantine,
  });

  final int totalBatches;
  final int nearExpiry;
  final int expired;
  final int quarantine;

  factory BatchSummaryRecord.fromJson(Json json) {
    final Json d = json.containsKey('data') ? Map<String, dynamic>.from(json['data'] as Map) : json;
    return BatchSummaryRecord(
      totalBatches: _intValue(d['total_batches']),
      nearExpiry: _intValue(d['near_expiry']),
      expired: _intValue(d['expired']),
      quarantine: _intValue(d['quarantine']),
    );
  }
}

class ExpiryDashboardRecord {
  const ExpiryDashboardRecord({
    required this.expiredToday,
    required this.expireIn7Days,
    required this.expireIn30Days,
    required this.totalExpired,
    required this.quarantine,
    required this.recalled,
  });

  final int expiredToday;
  final int expireIn7Days;
  final int expireIn30Days;
  final int totalExpired;
  final int quarantine;
  final int recalled;

  factory ExpiryDashboardRecord.fromJson(Json json) {
    final Json d = json.containsKey('data') ? Map<String, dynamic>.from(json['data'] as Map) : json;
    return ExpiryDashboardRecord(
      expiredToday: _intValue(d['expired_today']),
      expireIn7Days: _intValue(d['expire_in_7_days']),
      expireIn30Days: _intValue(d['expire_in_30_days']),
      totalExpired: _intValue(d['total_expired']),
      quarantine: _intValue(d['quarantine']),
      recalled: _intValue(d['recalled']),
    );
  }
}

class BatchQuery {
  const BatchQuery({
    this.productId,
    this.warehouseId,
    this.branchId,
    this.status,
    this.expiryBefore,
    this.expiryAfter,
    this.includeDeleted = false,
  });

  final String? productId;
  final String? warehouseId;
  final String? branchId;
  final String? status;
  final String? expiryBefore;
  final String? expiryAfter;
  final bool includeDeleted;

  Map<String, String> toQueryParams() => {
        if (productId != null) 'product_id': productId!,
        if (warehouseId != null) 'warehouse_id': warehouseId!,
        if (branchId != null) 'branch_id': branchId!,
        if (status != null) 'status': status!,
        if (expiryBefore != null) 'expiry_before': expiryBefore!,
        if (expiryAfter != null) 'expiry_after': expiryAfter!,
        if (includeDeleted) 'include_deleted': 'true',
      };
}

class LotQuery {
  const LotQuery({
    this.productId,
    this.warehouseId,
    this.branchId,
    this.status,
    this.includeDeleted = false,
  });

  final String? productId;
  final String? warehouseId;
  final String? branchId;
  final String? status;
  final bool includeDeleted;

  Map<String, String> toQueryParams() => {
        if (productId != null) 'product_id': productId!,
        if (warehouseId != null) 'warehouse_id': warehouseId!,
        if (branchId != null) 'branch_id': branchId!,
        if (status != null) 'status': status!,
        if (includeDeleted) 'include_deleted': 'true',
      };
}

class SerialQuery {
  const SerialQuery({
    this.productId,
    this.warehouseId,
    this.branchId,
    this.batchId,
    this.status,
    this.includeDeleted = false,
  });

  final String? productId;
  final String? warehouseId;
  final String? branchId;
  final String? batchId;
  final String? status;
  final bool includeDeleted;

  Map<String, String> toQueryParams() => {
        if (productId != null) 'product_id': productId!,
        if (warehouseId != null) 'warehouse_id': warehouseId!,
        if (branchId != null) 'branch_id': branchId!,
        if (batchId != null) 'batch_id': batchId!,
        if (status != null) 'status': status!,
        if (includeDeleted) 'include_deleted': 'true',
      };
}
