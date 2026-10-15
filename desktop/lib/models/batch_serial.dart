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
    this.version = 0,
    this.mrp = '',
    this.sellingPrice = '',
    this.ptr = '',
    this.pts = '',
    this.retailMarginPercent = '',
    this.wholesaleMarginPercent = '',
    this.mrpWarning = '',
    this.packSize = '',
    this.packUnitCode = '',
  });

  /// L5 step 11: how many pieces the item's box holds today, and the box's
  /// unit, where the firm types boxes and pieces; empty otherwise. What
  /// *Show boxes* splits the quantities by; never sent back.
  final String packSize;
  final String packUnitCode;

  /// Per stock unit; empty when none is recorded (BATCH_PTR_PTS). For a firm
  /// costing by lot, the lot's retail and wholesale prices.
  final String ptr;
  final String pts;

  /// The mark-ups the lot was priced at (L3); read-only, empty where none.
  final String retailMarginPercent;
  final String wholesaleMarginPercent;

  /// A sentence naming a price that bills above the MRP once tax is added: a
  /// warning, never a refusal. Empty where none.
  final String mrpWarning;

  /// Per stock unit, tax included; empty when none is recorded.
  final String mrp;

  /// Per stock unit, before tax; empty when none is recorded.
  final String sellingPrice;

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

  /// The optimistic-concurrency version this record was read at, sent back
  /// as `If-Match` on save so a concurrent edit is refused rather than
  /// silently overwritten. Zero means the server published none.
  final int version;

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
  version: (d['version'] as num?)?.toInt() ?? 0,
      mrp: stringValue(d['mrp']),
      sellingPrice: stringValue(d['selling_price']),
      ptr: stringValue(d['ptr']),
      pts: stringValue(d['pts']),
      retailMarginPercent: stringValue(d['retail_margin_percent']),
      wholesaleMarginPercent: stringValue(d['wholesale_margin_percent']),
      mrpWarning: stringValue(d['mrp_warning']),
      packSize: stringValue(d['pack_size']),
      packUnitCode: stringValue(d['pack_unit_code']),
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
    this.version = 0,
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

  /// The optimistic-concurrency version this record was read at, sent back
  /// as `If-Match` on save so a concurrent edit is refused rather than
  /// silently overwritten. Zero means the server published none.
  final int version;

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
  version: (d['version'] as num?)?.toInt() ?? 0,
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
    this.version = 0,
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

  /// The optimistic-concurrency version this record was read at, sent back
  /// as `If-Match` on save so a concurrent edit is refused rather than
  /// silently overwritten. Zero means the server published none.
  final int version;

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
  version: (d['version'] as num?)?.toInt() ?? 0,
    );
  }
}

/// One batch of a product on a shelf, as the delivery note's batch picker
/// shows it (`GET /batch-serial/batches/availability`). Quantities are in
/// stock units; [availableToLine] counts the order line's own reservation as
/// its own, and [fefo] is the earliest-expiry-first share of the quantity
/// asked about.
class BatchAvailabilityRecord {
  const BatchAvailabilityRecord({
    required this.batchId,
    required this.batchNumber,
    required this.manufacturingDate,
    required this.expiryDate,
    required this.daysToExpiry,
    required this.onHand,
    required this.reserved,
    required this.available,
    required this.availableToLine,
    required this.expired,
    required this.nearExpiry,
    required this.fefo,
    this.shortForCustomer = false,
    this.mrp,
    this.sellingPrice,
    this.ptr,
    this.pts,
    this.lotReference,
    this.receivedOn = '',
    this.hasPrintedBatch = true,
    this.pickGroup,
    this.unitCost,
  });

  /// The lot (L2 step 4): our own reference and the day it arrived. Where
  /// [hasPrintedBatch] is false the goods carry no printed batch and
  /// [batchNumber] is only that reference, so no screen shows it as one.
  final String? lotReference;
  final String receivedOn;
  final bool hasPrintedBatch;

  /// For a firm costing by lot: lots sharing this key agree on batch,
  /// expiry, MRP and selling prices and are one row in the picker, taken in
  /// the order the server listed them. Null for a firm on Average.
  final String? pickGroup;

  /// What one stock unit of the lot cost; sent only to somebody allowed to
  /// see cost, and only for a firm costing by lot.
  final double? unitCost;

  /// Retailer / stockist rate per stock unit; null when the batch has none.
  final double? ptr;
  final double? pts;

  /// Per stock unit, tax included; null when the batch has none.
  final double? mrp;

  /// Per stock unit, before tax; null when the batch has none.
  final double? sellingPrice;

  final String batchId;
  final String batchNumber;
  final String manufacturingDate;
  final String expiryDate;
  final int? daysToExpiry;
  final double onHand;
  final double reserved;
  final double available;
  final double availableToLine;
  final bool expired;
  final bool nearExpiry;
  final double fefo;

  /// Has less shelf life left than the customer's minimum. Never pre-filled
  /// into a pick; the server judges what is dispatched.
  final bool shortForCustomer;

  static double _num(dynamic value) =>
      value is num ? value.toDouble() : double.tryParse('${value ?? ''}') ?? 0;

  factory BatchAvailabilityRecord.fromJson(Json json) =>
      BatchAvailabilityRecord(
        batchId: stringValue(json['batch_id']),
        batchNumber: stringValue(json['batch_number']),
        manufacturingDate: stringValue(json['manufacturing_date']),
        expiryDate: stringValue(json['expiry_date']),
        daysToExpiry: json['days_to_expiry'] == null
            ? null
            : _intValue(json['days_to_expiry']),
        onHand: _num(json['on_hand']),
        reserved: _num(json['reserved']),
        available: _num(json['available']),
        availableToLine: _num(json['available_to_line']),
        expired: json['expired'] == true,
        nearExpiry: json['near_expiry'] == true,
        fefo: _num(json['fefo']),
        shortForCustomer: json['short_for_customer'] == true,
        mrp: json['mrp'] == null ? null : _num(json['mrp']),
        sellingPrice:
            json['selling_price'] == null ? null : _num(json['selling_price']),
        ptr: json['ptr'] == null ? null : _num(json['ptr']),
        pts: json['pts'] == null ? null : _num(json['pts']),
        lotReference: json['lot_reference'] == null
            ? null
            : stringValue(json['lot_reference']),
        receivedOn: stringValue(json['received_on']),
        hasPrintedBatch: json['has_printed_batch'] != false,
        pickGroup: json['pick_group'] == null ||
                stringValue(json['pick_group']).isEmpty
            ? null
            : stringValue(json['pick_group']),
        unitCost: json['unit_cost'] == null ? null : _num(json['unit_cost']),
      );
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

/// A batch inside its product's return-to-supplier window (STK-5).
class ReturnDueRecord {
  const ReturnDueRecord({
    required this.batchId,
    required this.batchNumber,
    required this.productId,
    required this.productCode,
    required this.productName,
    required this.vendorId,
    required this.expiryDate,
    required this.daysToExpiry,
    required this.quantity,
  });

  final String batchId;
  final String batchNumber;
  final String productId;
  final String productCode;
  final String productName;
  final String vendorId;
  final String expiryDate;
  final int daysToExpiry;
  final String quantity;

  factory ReturnDueRecord.fromJson(Json json) => ReturnDueRecord(
        batchId: stringValue(json['batch_id']),
        batchNumber: stringValue(json['batch_number']),
        productId: stringValue(json['product_id']),
        productCode: stringValue(json['product_code']),
        productName: stringValue(json['product_name']),
        vendorId: stringValue(json['vendor_id']),
        expiryDate: stringValue(json['expiry_date']),
        daysToExpiry: _intValue(json['days_to_expiry']),
        quantity: stringValue(json['quantity']),
      );
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

/// One serialised unit a document line names.
///
/// A delivery note line for a serial-tracked product names the units going
/// out, and a sales return line the units coming back; the server marks them
/// SOLD at dispatch and AVAILABLE again when the return completes (D-STK-4).
class PickedSerial {
  const PickedSerial({
    required this.id,
    required this.serialNumber,
    this.status = '',
  });

  /// The serial's own id -- what a line sends back in `serial_ids`.
  final String id;
  final String serialNumber;
  final String status;

  factory PickedSerial.fromJson(Json json) => PickedSerial(
        id: stringValue(json['serial_id']),
        serialNumber: stringValue(json['serial_number']),
        status: stringValue(json['status']),
      );

  /// Read the `serials` a document line carries.
  static List<PickedSerial> listFrom(dynamic value) => [
        for (final dynamic item in value is List ? value : const [])
          if (item is Map)
            PickedSerial.fromJson(Map<String, dynamic>.from(item)),
      ];
}

/// The units a return line against one source line may name.
class ReturnableSerials {
  const ReturnableSerials({
    required this.serialTracked,
    required this.serials,
  });

  /// False for a product nobody tracks by serial: its return names none.
  final bool serialTracked;
  final List<PickedSerial> serials;

  static const ReturnableSerials untracked =
      ReturnableSerials(serialTracked: false, serials: []);

  factory ReturnableSerials.fromJson(Json json) => ReturnableSerials(
        serialTracked: json['serial_tracked'] == true,
        serials: PickedSerial.listFrom(json['serials']),
      );
}

/// One document a serialised unit passed through (`/serials/{id}/trail`).
class SerialTrailEvent {
  const SerialTrailEvent({
    required this.documentType,
    required this.documentNumber,
    required this.documentDate,
    required this.partyName,
    required this.lineNumber,
    required this.movedAt,
  });

  final String documentType;
  final String documentNumber;
  final String documentDate;
  final String partyName;
  final int lineNumber;
  final String movedAt;

  factory SerialTrailEvent.fromJson(Json json) => SerialTrailEvent(
        documentType: stringValue(json['document_type']),
        documentNumber: stringValue(json['document_number']),
        documentDate: stringValue(json['document_date']),
        partyName: stringValue(json['party_name']),
        lineNumber: (json['line_number'] as num?)?.toInt() ?? 0,
        movedAt: stringValue(json['moved_at']),
      );
}

double? _optionalNumber(dynamic value) {
  if (value == null) return null;
  if (value is num) return value.toDouble();
  return double.tryParse('$value');
}

/// One document a lot passed through (`/batches/{id}/trail`, L2 step 11).
/// [quantity] is signed -- in positive, out negative, zero for a bill that
/// moved no goods; [costAmount] is null where the server sent no cost.
class LotTrailEvent {
  const LotTrailEvent({
    required this.documentType,
    required this.documentId,
    required this.documentNumber,
    required this.documentDate,
    required this.partyName,
    required this.quantity,
    required this.costAmount,
    required this.lineNumber,
  });

  final String documentType;
  final String documentId;
  final String documentNumber;
  final String documentDate;
  final String partyName;
  final double quantity;
  final double? costAmount;
  final int? lineNumber;

  factory LotTrailEvent.fromJson(Json json) => LotTrailEvent(
        documentType: stringValue(json['document_type']),
        documentId: stringValue(json['document_id']),
        documentNumber: stringValue(json['document_number']),
        documentDate: stringValue(json['document_date']),
        partyName: stringValue(json['party_name']),
        quantity: _optionalNumber(json['quantity']) ?? 0,
        costAmount: _optionalNumber(json['cost_amount']),
        lineNumber: json['line_number'] == null
            ? null
            : _intValue(json['line_number']),
      );
}

/// A lot and every document it passed through, its arrival first
/// (`GET /batch-serial/batches/{id}/trail`, L2 step 11). Where
/// [hasPrintedBatch] is false the batch number is only our own reference and
/// is never shown as a batch.
class LotTrail {
  const LotTrail({
    required this.batch,
    required this.lotReference,
    required this.hasPrintedBatch,
    required this.receivedOn,
    required this.sourceType,
    required this.unitCost,
    required this.events,
  });

  final BatchRecord batch;
  final String lotReference;
  final bool hasPrintedBatch;
  final String receivedOn;
  final String sourceType;

  /// Null where the server sent no cost.
  final double? unitCost;
  final List<LotTrailEvent> events;

  factory LotTrail.fromJson(Json json) {
    final dynamic batch = json['batch'];
    final dynamic events = json['events'];
    return LotTrail(
      batch: BatchRecord.fromJson(
          batch is Map ? Map<String, dynamic>.from(batch) : <String, dynamic>{}),
      lotReference: stringValue(json['lot_reference']),
      hasPrintedBatch: json['has_printed_batch'] != false,
      receivedOn: stringValue(json['received_on']),
      sourceType: stringValue(json['source_type']),
      unitCost: _optionalNumber(json['unit_cost']),
      events: [
        if (events is List)
          for (final dynamic item in events)
            if (item is Map)
              LotTrailEvent.fromJson(Map<String, dynamic>.from(item)),
      ],
    );
  }
}
