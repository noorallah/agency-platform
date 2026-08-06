import 'entities.dart';

List<Json> _objects(dynamic value) => value is List
    ? value.whereType<Map>().map((item) => Map<String, dynamic>.from(item)).toList()
    : const [];

String _numberValue(dynamic value) {
  if (value == null) {
    return '0';
  }
  return value.toString();
}

class InventoryRecord {
  const InventoryRecord({
    required this.id,
    required this.firmId,
    required this.branchId,
    required this.branchCode,
    required this.branchName,
    required this.warehouseId,
    required this.warehouseCode,
    required this.warehouseName,
    required this.storageNodeId,
    required this.storageNodeCode,
    required this.storageNodeName,
    required this.productId,
    required this.productCode,
    required this.productName,
    required this.businessProfileId,
    required this.businessProfileCode,
    required this.currentQuantity,
    required this.reservedQuantity,
    required this.availableQuantity,
    required this.blockedQuantity,
    required this.damagedQuantity,
    required this.quarantineQuantity,
    required this.inTransitQuantity,
    required this.minimumLevel,
    required this.maximumLevel,
    required this.reorderLevel,
    required this.safetyStock,
    required this.lastTransactionAt,
    required this.status,
    required this.isDeleted,
    required this.createdAt,
    required this.updatedAt,
  });

  final String id;
  final String firmId;
  final String branchId;
  final String branchCode;
  final String branchName;
  final String warehouseId;
  final String warehouseCode;
  final String warehouseName;
  final String storageNodeId;
  final String storageNodeCode;
  final String storageNodeName;
  final String productId;
  final String productCode;
  final String productName;
  final String businessProfileId;
  final String businessProfileCode;
  final String currentQuantity;
  final String reservedQuantity;
  final String availableQuantity;
  final String blockedQuantity;
  final String damagedQuantity;
  final String quarantineQuantity;
  final String inTransitQuantity;
  final String minimumLevel;
  final String maximumLevel;
  final String reorderLevel;
  final String safetyStock;
  final String lastTransactionAt;
  final String status;
  final bool isDeleted;
  final String createdAt;
  final String updatedAt;

  factory InventoryRecord.fromJson(Json json) => InventoryRecord(
        id: stringValue(json['id']),
        firmId: stringValue(json['firm_id']),
        branchId: stringValue(json['branch_id']),
        branchCode: stringValue(json['branch_code']),
        branchName: stringValue(json['branch_name']),
        warehouseId: stringValue(json['warehouse_id']),
        warehouseCode: stringValue(json['warehouse_code']),
        warehouseName: stringValue(json['warehouse_name']),
        storageNodeId: stringValue(json['storage_node_id']),
        storageNodeCode: stringValue(json['storage_node_code']),
        storageNodeName: stringValue(json['storage_node_name']),
        productId: stringValue(json['product_id']),
        productCode: stringValue(json['product_code']),
        productName: stringValue(json['product_name']),
        businessProfileId: stringValue(json['business_profile_id']),
        businessProfileCode: stringValue(json['business_profile_code']),
        currentQuantity: _numberValue(json['current_quantity']),
        reservedQuantity: _numberValue(json['reserved_quantity']),
        availableQuantity: _numberValue(json['available_quantity']),
        blockedQuantity: _numberValue(json['blocked_quantity']),
        damagedQuantity: _numberValue(json['damaged_quantity']),
        quarantineQuantity: _numberValue(json['quarantine_quantity']),
        inTransitQuantity: _numberValue(json['in_transit_quantity']),
        minimumLevel: stringValue(json['minimum_level']),
        maximumLevel: stringValue(json['maximum_level']),
        reorderLevel: stringValue(json['reorder_level']),
        safetyStock: stringValue(json['safety_stock']),
        lastTransactionAt: stringValue(json['last_transaction_at']),
        status: stringValue(json['status']),
        isDeleted: boolValue(json['is_deleted']),
        createdAt: stringValue(json['created_at']),
        updatedAt: stringValue(json['updated_at']),
      );
}

class InventorySummaryRecord {
  const InventorySummaryRecord({
    required this.totalRecords,
    required this.currentQuantity,
    required this.reservedQuantity,
    required this.availableQuantity,
    required this.blockedQuantity,
    required this.damagedQuantity,
    required this.quarantineQuantity,
    required this.inTransitQuantity,
    required this.lowStockCount,
    required this.outOfStockCount,
    required this.negativeStockCount,
  });

  final int totalRecords;
  final String currentQuantity;
  final String reservedQuantity;
  final String availableQuantity;
  final String blockedQuantity;
  final String damagedQuantity;
  final String quarantineQuantity;
  final String inTransitQuantity;
  final int lowStockCount;
  final int outOfStockCount;
  final int negativeStockCount;

  factory InventorySummaryRecord.fromJson(Json json) => InventorySummaryRecord(
        totalRecords: (json['total_records'] as num?)?.toInt() ?? 0,
        currentQuantity: _numberValue(json['current_quantity']),
        reservedQuantity: _numberValue(json['reserved_quantity']),
        availableQuantity: _numberValue(json['available_quantity']),
        blockedQuantity: _numberValue(json['blocked_quantity']),
        damagedQuantity: _numberValue(json['damaged_quantity']),
        quarantineQuantity: _numberValue(json['quarantine_quantity']),
        inTransitQuantity: _numberValue(json['in_transit_quantity']),
        lowStockCount: (json['low_stock_count'] as num?)?.toInt() ?? 0,
        outOfStockCount: (json['out_of_stock_count'] as num?)?.toInt() ?? 0,
        negativeStockCount: (json['negative_stock_count'] as num?)?.toInt() ?? 0,
      );
}

class InventoryLocationSummaryRecord {
  const InventoryLocationSummaryRecord({
    required this.scopeId,
    required this.scopeCode,
    required this.scopeName,
    required this.currentQuantity,
    required this.reservedQuantity,
    required this.availableQuantity,
    required this.blockedQuantity,
    required this.damagedQuantity,
    required this.quarantineQuantity,
    required this.inTransitQuantity,
  });

  final String scopeId;
  final String scopeCode;
  final String scopeName;
  final String currentQuantity;
  final String reservedQuantity;
  final String availableQuantity;
  final String blockedQuantity;
  final String damagedQuantity;
  final String quarantineQuantity;
  final String inTransitQuantity;

  factory InventoryLocationSummaryRecord.fromJson(Json json) =>
      InventoryLocationSummaryRecord(
        scopeId: stringValue(json['scope_id']),
        scopeCode: stringValue(json['scope_code']),
        scopeName: stringValue(json['scope_name']),
        currentQuantity: _numberValue(json['current_quantity']),
        reservedQuantity: _numberValue(json['reserved_quantity']),
        availableQuantity: _numberValue(json['available_quantity']),
        blockedQuantity: _numberValue(json['blocked_quantity']),
        damagedQuantity: _numberValue(json['damaged_quantity']),
        quarantineQuantity: _numberValue(json['quarantine_quantity']),
        inTransitQuantity: _numberValue(json['in_transit_quantity']),
      );
}

class InventoryTransactionRecord {
  const InventoryTransactionRecord({
    required this.id,
    required this.inventoryId,
    required this.firmId,
    required this.branchId,
    required this.branchCode,
    required this.branchName,
    required this.warehouseId,
    required this.warehouseCode,
    required this.warehouseName,
    required this.storageNodeId,
    required this.storageNodeCode,
    required this.storageNodeName,
    required this.productId,
    required this.productCode,
    required this.productName,
    required this.businessProfileId,
    required this.transactionType,
    required this.referenceNumber,
    required this.referenceType,
    required this.transactionDate,
    required this.quantity,
    required this.currentQuantityDelta,
    required this.reservedQuantityDelta,
    required this.blockedQuantityDelta,
    required this.damagedQuantityDelta,
    required this.quarantineQuantityDelta,
    required this.inTransitQuantityDelta,
    required this.previousCurrentQuantity,
    required this.newCurrentQuantity,
    required this.previousReservedQuantity,
    required this.newReservedQuantity,
    required this.previousAvailableQuantity,
    required this.newAvailableQuantity,
    required this.previousBlockedQuantity,
    required this.newBlockedQuantity,
    required this.previousDamagedQuantity,
    required this.newDamagedQuantity,
    required this.previousQuarantineQuantity,
    required this.newQuarantineQuantity,
    required this.previousInTransitQuantity,
    required this.newInTransitQuantity,
    required this.remarks,
    required this.createdAt,
    required this.transactionId,
  });

  final String id;
  final String inventoryId;
  final String firmId;
  final String branchId;
  final String branchCode;
  final String branchName;
  final String warehouseId;
  final String warehouseCode;
  final String warehouseName;
  final String storageNodeId;
  final String storageNodeCode;
  final String storageNodeName;
  final String productId;
  final String productCode;
  final String productName;
  final String businessProfileId;
  final String transactionType;
  final String referenceNumber;
  final String referenceType;
  final String transactionDate;
  final String quantity;
  final String currentQuantityDelta;
  final String reservedQuantityDelta;
  final String blockedQuantityDelta;
  final String damagedQuantityDelta;
  final String quarantineQuantityDelta;
  final String inTransitQuantityDelta;
  final String previousCurrentQuantity;
  final String newCurrentQuantity;
  final String previousReservedQuantity;
  final String newReservedQuantity;
  final String previousAvailableQuantity;
  final String newAvailableQuantity;
  final String previousBlockedQuantity;
  final String newBlockedQuantity;
  final String previousDamagedQuantity;
  final String newDamagedQuantity;
  final String previousQuarantineQuantity;
  final String newQuarantineQuantity;
  final String previousInTransitQuantity;
  final String newInTransitQuantity;
  final String remarks;
  final String createdAt;
  final String transactionId;

  factory InventoryTransactionRecord.fromJson(Json json) =>
      InventoryTransactionRecord(
        id: stringValue(json['id']),
        inventoryId: stringValue(json['inventory_id']),
        firmId: stringValue(json['firm_id']),
        branchId: stringValue(json['branch_id']),
        branchCode: stringValue(json['branch_code']),
        branchName: stringValue(json['branch_name']),
        warehouseId: stringValue(json['warehouse_id']),
        warehouseCode: stringValue(json['warehouse_code']),
        warehouseName: stringValue(json['warehouse_name']),
        storageNodeId: stringValue(json['storage_node_id']),
        storageNodeCode: stringValue(json['storage_node_code']),
        storageNodeName: stringValue(json['storage_node_name']),
        productId: stringValue(json['product_id']),
        productCode: stringValue(json['product_code']),
        productName: stringValue(json['product_name']),
        businessProfileId: stringValue(json['business_profile_id']),
        transactionType: stringValue(json['transaction_type']),
        referenceNumber: stringValue(json['reference_number']),
        referenceType: stringValue(json['reference_type']),
        transactionDate: stringValue(json['transaction_date']),
        quantity: _numberValue(json['quantity']),
        currentQuantityDelta: _numberValue(json['current_quantity_delta']),
        reservedQuantityDelta: _numberValue(json['reserved_quantity_delta']),
        blockedQuantityDelta: _numberValue(json['blocked_quantity_delta']),
        damagedQuantityDelta: _numberValue(json['damaged_quantity_delta']),
        quarantineQuantityDelta: _numberValue(json['quarantine_quantity_delta']),
        inTransitQuantityDelta: _numberValue(json['in_transit_quantity_delta']),
        previousCurrentQuantity: _numberValue(json['previous_current_quantity']),
        newCurrentQuantity: _numberValue(json['new_current_quantity']),
        previousReservedQuantity: _numberValue(json['previous_reserved_quantity']),
        newReservedQuantity: _numberValue(json['new_reserved_quantity']),
        previousAvailableQuantity: _numberValue(json['previous_available_quantity']),
        newAvailableQuantity: _numberValue(json['new_available_quantity']),
        previousBlockedQuantity: _numberValue(json['previous_blocked_quantity']),
        newBlockedQuantity: _numberValue(json['new_blocked_quantity']),
        previousDamagedQuantity: _numberValue(json['previous_damaged_quantity']),
        newDamagedQuantity: _numberValue(json['new_damaged_quantity']),
        previousQuarantineQuantity: _numberValue(json['previous_quarantine_quantity']),
        newQuarantineQuantity: _numberValue(json['new_quarantine_quantity']),
        previousInTransitQuantity: _numberValue(json['previous_in_transit_quantity']),
        newInTransitQuantity: _numberValue(json['new_in_transit_quantity']),
        remarks: stringValue(json['remarks']),
        createdAt: stringValue(json['created_at']),
        transactionId: stringValue(json['transaction_id'] ?? json['id']),
      );
}

class OpeningStockLineRecord {
  const OpeningStockLineRecord({
    required this.id,
    required this.lineNumber,
    required this.productId,
    required this.productCode,
    required this.productName,
    required this.storageNodeId,
    required this.storageNodeCode,
    required this.storageNodeName,
    required this.businessProfileId,
    required this.quantity,
    required this.minimumLevel,
    required this.maximumLevel,
    required this.reorderLevel,
    required this.safetyStock,
    required this.remarks,
    required this.transactionId,
  });

  final String id;
  final int lineNumber;
  final String productId;
  final String productCode;
  final String productName;
  final String storageNodeId;
  final String storageNodeCode;
  final String storageNodeName;
  final String businessProfileId;
  final String quantity;
  final String minimumLevel;
  final String maximumLevel;
  final String reorderLevel;
  final String safetyStock;
  final String remarks;
  final String transactionId;

  factory OpeningStockLineRecord.fromJson(Json json) => OpeningStockLineRecord(
        id: stringValue(json['id']),
        lineNumber: (json['line_number'] as num?)?.toInt() ?? 0,
        productId: stringValue(json['product_id']),
        productCode: stringValue(json['product_code']),
        productName: stringValue(json['product_name']),
        storageNodeId: stringValue(json['storage_node_id']),
        storageNodeCode: stringValue(json['storage_node_code']),
        storageNodeName: stringValue(json['storage_node_name']),
        businessProfileId: stringValue(json['business_profile_id']),
        quantity: _numberValue(json['quantity']),
        minimumLevel: stringValue(json['minimum_level']),
        maximumLevel: stringValue(json['maximum_level']),
        reorderLevel: stringValue(json['reorder_level']),
        safetyStock: stringValue(json['safety_stock']),
        remarks: stringValue(json['remarks']),
        transactionId: stringValue(json['transaction_id']),
      );
}

class OpeningStockBatchRecord {
  const OpeningStockBatchRecord({
    required this.id,
    required this.firmId,
    required this.branchId,
    required this.branchCode,
    required this.branchName,
    required this.warehouseId,
    required this.warehouseCode,
    required this.warehouseName,
    required this.referenceNumber,
    required this.postingDate,
    required this.sourceFormat,
    required this.status,
    required this.remarks,
    required this.postedAt,
    required this.lines,
    required this.createdAt,
    required this.updatedAt,
  });

  final String id;
  final String firmId;
  final String branchId;
  final String branchCode;
  final String branchName;
  final String warehouseId;
  final String warehouseCode;
  final String warehouseName;
  final String referenceNumber;
  final String postingDate;
  final String sourceFormat;
  final String status;
  final String remarks;
  final String postedAt;
  final List<OpeningStockLineRecord> lines;
  final String createdAt;
  final String updatedAt;

  bool get isPosted => status.toUpperCase() == 'POSTED';

  factory OpeningStockBatchRecord.fromJson(Json json) => OpeningStockBatchRecord(
        id: stringValue(json['id']),
        firmId: stringValue(json['firm_id']),
        branchId: stringValue(json['branch_id']),
        branchCode: stringValue(json['branch_code']),
        branchName: stringValue(json['branch_name']),
        warehouseId: stringValue(json['warehouse_id']),
        warehouseCode: stringValue(json['warehouse_code']),
        warehouseName: stringValue(json['warehouse_name']),
        referenceNumber: stringValue(json['reference_number']),
        postingDate: stringValue(json['posting_date']),
        sourceFormat: stringValue(json['source_format']),
        status: stringValue(json['status']),
        remarks: stringValue(json['remarks']),
        postedAt: stringValue(json['posted_at']),
        lines: _objects(json['lines']).map(OpeningStockLineRecord.fromJson).toList(),
        createdAt: stringValue(json['created_at']),
        updatedAt: stringValue(json['updated_at']),
      );
}

class InventoryQuery {
  const InventoryQuery({
    this.status,
    this.branchId,
    this.warehouseId,
    this.storageNodeId,
    this.productId,
    this.businessProfileId,
    this.lowStockOnly = false,
    this.outOfStockOnly = false,
    this.negativeOnly = false,
    this.includeDeleted = false,
  });

  final String? status;
  final String? branchId;
  final String? warehouseId;
  final String? storageNodeId;
  final String? productId;
  final String? businessProfileId;
  final bool lowStockOnly;
  final bool outOfStockOnly;
  final bool negativeOnly;
  final bool includeDeleted;

  Map<String, String> toQuery() => {
        if (status?.isNotEmpty == true) 'status': status!,
        if (branchId?.isNotEmpty == true) 'branch_id': branchId!,
        if (warehouseId?.isNotEmpty == true) 'warehouse_id': warehouseId!,
        if (storageNodeId?.isNotEmpty == true) 'storage_node_id': storageNodeId!,
        if (productId?.isNotEmpty == true) 'product_id': productId!,
        if (businessProfileId?.isNotEmpty == true)
          'business_profile_id': businessProfileId!,
        if (lowStockOnly) 'low_stock_only': 'true',
        if (outOfStockOnly) 'out_of_stock_only': 'true',
        if (negativeOnly) 'negative_only': 'true',
        if (includeDeleted) 'include_deleted': 'true',
      };
}

class InventoryTransactionQuery {
  const InventoryTransactionQuery({
    this.transactionType,
    this.branchId,
    this.warehouseId,
    this.storageNodeId,
    this.productId,
    this.referenceNumber,
    this.referenceType,
    this.transactionFrom,
    this.transactionTo,
  });

  final String? transactionType;
  final String? branchId;
  final String? warehouseId;
  final String? storageNodeId;
  final String? productId;
  final String? referenceNumber;
  final String? referenceType;
  final String? transactionFrom;
  final String? transactionTo;

  Map<String, String> toQuery() => {
        if (transactionType?.isNotEmpty == true) 'transaction_type': transactionType!,
        if (branchId?.isNotEmpty == true) 'branch_id': branchId!,
        if (warehouseId?.isNotEmpty == true) 'warehouse_id': warehouseId!,
        if (storageNodeId?.isNotEmpty == true) 'storage_node_id': storageNodeId!,
        if (productId?.isNotEmpty == true) 'product_id': productId!,
        if (referenceNumber?.isNotEmpty == true) 'reference_number': referenceNumber!,
        if (referenceType?.isNotEmpty == true) 'reference_type': referenceType!,
        if (transactionFrom?.isNotEmpty == true) 'transaction_from': transactionFrom!,
        if (transactionTo?.isNotEmpty == true) 'transaction_to': transactionTo!,
      };
}

class OpeningStockBatchQuery {
  const OpeningStockBatchQuery({
    this.status,
    this.branchId,
    this.warehouseId,
    this.postingFrom,
    this.postingTo,
    this.includeDeleted = false,
  });

  final String? status;
  final String? branchId;
  final String? warehouseId;
  final String? postingFrom;
  final String? postingTo;
  final bool includeDeleted;

  Map<String, String> toQuery() => {
        if (status?.isNotEmpty == true) 'status': status!,
        if (branchId?.isNotEmpty == true) 'branch_id': branchId!,
        if (warehouseId?.isNotEmpty == true) 'warehouse_id': warehouseId!,
        if (postingFrom?.isNotEmpty == true) 'posting_from': postingFrom!,
        if (postingTo?.isNotEmpty == true) 'posting_to': postingTo!,
        if (includeDeleted) 'include_deleted': 'true',
      };
}
