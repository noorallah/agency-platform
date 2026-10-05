import 'document_framework.dart';
import 'entities.dart';
import 'line_tax_rule.dart';

class GoodsReceiptLine {
  const GoodsReceiptLine({
    required this.id,
    required this.lineNumber,
    required this.purchaseOrderLineId,
    required this.purchaseOrderLineNumber,
    required this.productId,
    required this.description,
    required this.orderedQuantity,
    required this.previouslyReceivedQuantity,
    required this.currentReceiptQuantity,
    required this.acceptedQuantity,
    required this.unitPrice,
    required this.discountPercent,
    required this.discountAmount,
    required this.grossAmount,
    required this.taxProfileId,
    required this.taxAmount,
    required this.netAmount,
    required this.rejectedQuantity,
    required this.damagedQuantity,
    required this.freeQuantity,
    required this.packagingTypeId,
    required this.purchaseUomId,
    required this.inventoryUomId,
    required this.conversionFactor,
    required this.conversionVersion,
    required this.warehouseId,
    required this.storageNodeId,
    required this.batchNumber,
    required this.expiryDate,
    required this.manufacturingDate,
    required this.inventoryTransactionId,
    required this.remarks,
    required this.createdAt,
    required this.updatedAt,
    this.mrp = '',
    this.sellingPrice = '',
    this.ptr = '',
    this.pts = '',
    this.taxRuleCode,
    this.taxRuleVersion,
    this.schemeName = '',
    this.returnedUnbilledQuantity = '',
    this.serialTracked = false,
    this.isCapitalGoods = false,
    this.serialNumbers = const [],
  });

  /// Whether the product carries a serial per unit (PG-10).
  final bool serialTracked;

  /// Received as a fixed asset: no stock movement, and the bill raises the
  /// asset (D-BUY-40).
  final bool isCapitalGoods;

  /// The serials the line holds, in the order they were entered.
  final List<String> serialNumbers;

  /// The supplier's scheme the free goods came under; empty when none.
  final String schemeName;

  /// What went back to the supplier before any bill reached it, so is not
  /// the supplier's to bill (D-BUY-26); empty from an older server.
  final String returnedUnbilledQuantity;

  /// Per stock unit, tax included; empty when none was recorded.
  final String mrp;

  /// Per stock unit, before tax; empty when none was recorded.
  final String sellingPrice;
  final String ptr;
  final String pts;

  final String id;
  final int lineNumber;
  final String purchaseOrderLineId;
  final int purchaseOrderLineNumber;
  final String productId;
  final String description;
  final String orderedQuantity;
  final String previouslyReceivedQuantity;
  final String currentReceiptQuantity;
  final String acceptedQuantity;
  final String unitPrice;
  final String discountPercent;
  final String discountAmount;
  final String grossAmount;
  final String taxProfileId;
  final String taxAmount;
  final String netAmount;
  final String rejectedQuantity;
  final String damagedQuantity;
  final String freeQuantity;
  final String packagingTypeId;
  final String purchaseUomId;
  final String inventoryUomId;
  final String conversionFactor;
  final int? conversionVersion;
  final String warehouseId;
  final String storageNodeId;
  final String batchNumber;
  final String expiryDate;
  final String manufacturingDate;
  final String inventoryTransactionId;
  final String remarks;
  final String createdAt;
  final String updatedAt;

  /// The tax rule that decided this line's tax; null when none matched.
  final String? taxRuleCode;
  final int? taxRuleVersion;

  factory GoodsReceiptLine.fromJson(Json json) => GoodsReceiptLine(
        id: stringValue(json['id']),
        lineNumber: (json['line_number'] as num?)?.toInt() ?? 0,
        purchaseOrderLineId: stringValue(json['purchase_order_line_id']),
        purchaseOrderLineNumber:
            (json['purchase_order_line_number'] as num?)?.toInt() ?? 0,
        productId: stringValue(json['product_id']),
        description: stringValue(json['description']),
        orderedQuantity: stringValue(json['ordered_quantity']),
        previouslyReceivedQuantity:
            stringValue(json['previously_received_quantity']),
        currentReceiptQuantity: stringValue(json['current_receipt_quantity']),
        acceptedQuantity: stringValue(json['accepted_quantity']),
        unitPrice: stringValue(json['unit_price']),
        discountPercent: stringValue(json['discount_percent']),
        discountAmount: stringValue(json['discount_amount']),
        grossAmount: stringValue(json['gross_amount']),
        taxProfileId: stringValue(json['tax_profile_id']),
        taxAmount: stringValue(json['tax_amount']),
        netAmount: stringValue(json['net_amount']),
        rejectedQuantity: stringValue(json['rejected_quantity']),
        damagedQuantity: stringValue(json['damaged_quantity']),
        freeQuantity: stringValue(json['free_quantity']),
        packagingTypeId: stringValue(json['packaging_type_id']),
        purchaseUomId: stringValue(json['purchase_uom_id']),
        inventoryUomId: stringValue(json['inventory_uom_id']),
        conversionFactor: stringValue(json['conversion_factor']),
        conversionVersion: (json['conversion_version'] as num?)?.toInt(),
        warehouseId: stringValue(json['warehouse_id']),
        storageNodeId: stringValue(json['storage_node_id']),
        batchNumber: stringValue(json['batch_number']),
        expiryDate: stringValue(json['expiry_date']),
        manufacturingDate: stringValue(json['manufacturing_date']),
        inventoryTransactionId: stringValue(json['inventory_transaction_id']),
        remarks: stringValue(json['remarks']),
        createdAt: stringValue(json['created_at']),
        updatedAt: stringValue(json['updated_at']),
        mrp: stringValue(json['mrp']),
        sellingPrice: stringValue(json['selling_price']),
        ptr: stringValue(json['ptr']),
        pts: stringValue(json['pts']),
        schemeName: stringValue(json['scheme_name']),
        returnedUnbilledQuantity:
            stringValue(json['returned_unbilled_quantity']),
        serialTracked: json['serial_tracked'] == true,
        isCapitalGoods: json['is_capital_goods'] == true,
        serialNumbers: [
          for (final dynamic item
              in (json['serial_numbers'] as List<dynamic>? ?? const []))
            stringValue(item),
        ],
        taxRuleCode: LineTaxRule.fromJson(json).code,
        taxRuleVersion: LineTaxRule.fromJson(json).version,
      );

  Json toJson() => {
        'line_number': lineNumber,
        'purchase_order_line_id': purchaseOrderLineId,
        'description': description,
        'current_receipt_quantity': currentReceiptQuantity,
        'rejected_quantity': rejectedQuantity,
        'damaged_quantity': damagedQuantity,
        'free_quantity': freeQuantity,
        'unit_price': unitPrice,
        'discount_percent': discountPercent,
        'discount_amount': discountAmount,
        'tax_profile_id': taxProfileId,
        'packaging_type_id': packagingTypeId,
        'purchase_uom_id': purchaseUomId,
        'inventory_uom_id': inventoryUomId,
        'warehouse_id': warehouseId,
        'storage_node_id': storageNodeId,
        'batch_number': batchNumber,
        'expiry_date': expiryDate,
        'manufacturing_date': manufacturingDate,
        'remarks': remarks,
        if (schemeName.trim().isNotEmpty) 'scheme_name': schemeName.trim(),
      };
}

class GoodsReceiptAttachment {
  const GoodsReceiptAttachment({
    required this.id,
    required this.goodsReceiptId,
    required this.fileName,
    required this.mimeType,
    required this.filePath,
    required this.attachmentKind,
    required this.createdAt,
    required this.updatedAt,
  });

  final String id;
  final String goodsReceiptId;
  final String fileName;
  final String mimeType;
  final String filePath;
  final String attachmentKind;
  final String createdAt;
  final String updatedAt;

  factory GoodsReceiptAttachment.fromJson(Json json) => GoodsReceiptAttachment(
        id: stringValue(json['id']),
        goodsReceiptId: stringValue(json['goods_receipt_id']),
        fileName: stringValue(json['file_name']),
        mimeType: stringValue(json['mime_type']),
        filePath: stringValue(json['file_path']),
        attachmentKind: stringValue(json['attachment_kind']),
        createdAt: stringValue(json['created_at']),
        updatedAt: stringValue(json['updated_at']),
      );
}

class GoodsReceiptNote {
  const GoodsReceiptNote({
    required this.id,
    required this.noteType,
    required this.note,
    required this.createdAt,
    required this.updatedAt,
  });

  final String id;
  final String noteType;
  final String note;
  final String createdAt;
  final String updatedAt;

  factory GoodsReceiptNote.fromJson(Json json) => GoodsReceiptNote(
        id: stringValue(json['id']),
        noteType: stringValue(json['note_type']),
        note: stringValue(json['note']),
        createdAt: stringValue(json['created_at']),
        updatedAt: stringValue(json['updated_at']),
      );
}

class GoodsReceiptRecord {
  const GoodsReceiptRecord({
    required this.id,
    this.version = 0,
    required this.firmId,
    required this.purchaseOrderId,
    required this.purchaseOrderNumber,
    required this.vendorId,
    this.vendorName = '',
    this.vendorCode = '',
    required this.branchId,
    required this.warehouseId,
    required this.receivedById,
    required this.grnNumber,
    required this.receiptDate,
    required this.transportDetails,
    required this.vehicleNumber,
    required this.invoiceReference,
    required this.remarks,
    required this.status,
    required this.totalOrderedQuantity,
    this.attachedFileCount = 0,
    required this.totalPreviousReceivedQuantity,
    required this.totalCurrentReceiptQuantity,
    required this.totalAcceptedQuantity,
    required this.totalRejectedQuantity,
    required this.totalDamagedQuantity,
    required this.totalFreeQuantity,
    required this.lineDiscountTotal,
    required this.subtotal,
    required this.taxTotal,
    required this.additionalCharges,
    required this.roundOff,
    required this.grandTotal,
    required this.completedAt,
    required this.closedReason,
    required this.cancelReason,
    required this.isDeleted,
    required this.createdAt,
    required this.updatedAt,
    required this.lines,
    required this.attachments,
    required this.notes,
    required this.duplicateWarning,
    this.ewayBillNumber = '',
    this.ewayBillDate = '',
    this.ewayBillWarning = '',
    this.leftToBillQuantity = '',
    this.leftToBillAmount = '',
  });

  final String id;

  /// The optimistic-concurrency version this record was read at, sent back
  /// as `If-Match` on save so a concurrent edit is refused rather than
  /// silently overwritten. Zero means the server published none, and the
  /// save then carries no precondition.
  final int version;
  final String firmId;
  final String purchaseOrderId;
  final String purchaseOrderNumber;
  final String vendorId;

  /// Whose receipt it is, so the list can say so (owner, 2026-09-27).
  final String vendorName;
  final String vendorCode;
  final String branchId;
  final String warehouseId;
  final String receivedById;
  final String grnNumber;
  final String receiptDate;
  final String transportDetails;
  final String vehicleNumber;
  final String invoiceReference;
  final String remarks;
  final String status;
  final String totalOrderedQuantity;
  final int attachedFileCount;
  final String totalPreviousReceivedQuantity;
  final String totalCurrentReceiptQuantity;
  final String totalAcceptedQuantity;
  final String totalRejectedQuantity;
  final String totalDamagedQuantity;
  final String totalFreeQuantity;
  final String lineDiscountTotal;
  final String subtotal;
  final String taxTotal;
  final String additionalCharges;
  final String roundOff;
  final String grandTotal;
  final String completedAt;
  final String closedReason;
  final String cancelReason;
  final bool isDeleted;
  final String createdAt;
  final String updatedAt;
  final List<GoodsReceiptLine> lines;
  final List<GoodsReceiptAttachment> attachments;
  final List<GoodsReceiptNote> notes;
  final String duplicateWarning;

  /// The 12-digit e-way bill the supplier raised for the goods; empty when
  /// none is on file (backlog 78 row 6).
  final String ewayBillNumber;
  final String ewayBillDate;

  /// What the supplier may still bill on the receipt, goods sent back before
  /// billing taken off (D-BUY-27). Empty when the server published none.
  final String leftToBillQuantity;
  final String leftToBillAmount;

  /// False only when the server says nothing is left to bill; a record that
  /// carries no figure is offered rather than hidden.
  bool get hasLeftToBill =>
      leftToBillQuantity.isEmpty ||
      (double.tryParse(leftToBillQuantity) ?? 0) > 0;

  /// The value to show beside the receipt on a bill: what is left to bill,
  /// or the receipt's total where the server published no figure.
  String get billableAmount =>
      leftToBillAmount.isEmpty ? grandTotal : leftToBillAmount;

  /// Set when the goods are worth more than the e-way bill limit and no
  /// number is recorded.
  final String ewayBillWarning;

  factory GoodsReceiptRecord.fromJson(Json json) => GoodsReceiptRecord(
        id: stringValue(json['id']),
        version: (json['version'] as num?)?.toInt() ?? 0,
        firmId: stringValue(json['firm_id']),
        purchaseOrderId: stringValue(json['purchase_order_id']),
        purchaseOrderNumber: stringValue(json['purchase_order_number']),
        vendorId: stringValue(json['vendor_id']),
        vendorName: stringValue(json['vendor_name']),
        vendorCode: stringValue(json['vendor_code']),
        branchId: stringValue(json['branch_id']),
        warehouseId: stringValue(json['warehouse_id']),
        receivedById: stringValue(json['received_by_id']),
        grnNumber: stringValue(json['grn_number']),
        receiptDate: stringValue(json['receipt_date']),
        transportDetails: stringValue(json['transport_details']),
        vehicleNumber: stringValue(json['vehicle_number']),
        invoiceReference: stringValue(json['invoice_reference']),
        remarks: stringValue(json['remarks']),
        status: stringValue(json['status']),
        totalOrderedQuantity: stringValue(json['total_ordered_quantity']),
        attachedFileCount:
            int.tryParse(stringValue(json['attached_file_count'])) ?? 0,
        totalPreviousReceivedQuantity:
            stringValue(json['total_previous_received_quantity']),
        totalCurrentReceiptQuantity:
            stringValue(json['total_current_receipt_quantity']),
        totalAcceptedQuantity: stringValue(json['total_accepted_quantity']),
        totalRejectedQuantity: stringValue(json['total_rejected_quantity']),
        totalDamagedQuantity: stringValue(json['total_damaged_quantity']),
        totalFreeQuantity: stringValue(json['total_free_quantity']),
        lineDiscountTotal: stringValue(json['line_discount_total']),
        subtotal: stringValue(json['subtotal']),
        taxTotal: stringValue(json['tax_total']),
        additionalCharges: stringValue(json['additional_charges']),
        roundOff: stringValue(json['round_off']),
        grandTotal: stringValue(json['grand_total']),
        completedAt: stringValue(json['completed_at']),
        closedReason: stringValue(json['closed_reason']),
        cancelReason: stringValue(json['cancel_reason']),
        isDeleted: boolValue(json['is_deleted']),
        createdAt: stringValue(json['created_at']),
        updatedAt: stringValue(json['updated_at']),
        lines: (json['lines'] as List? ?? const [])
            .whereType<Map>()
            .map((item) =>
                GoodsReceiptLine.fromJson(Map<String, dynamic>.from(item)))
            .toList(growable: false),
        attachments: (json['attachments'] as List? ?? const [])
            .whereType<Map>()
            .map((item) => GoodsReceiptAttachment.fromJson(
                Map<String, dynamic>.from(item)))
            .toList(growable: false),
        notes: (json['notes'] as List? ?? const [])
            .whereType<Map>()
            .map((item) =>
                GoodsReceiptNote.fromJson(Map<String, dynamic>.from(item)))
            .toList(growable: false),
        duplicateWarning: stringValue(json['duplicate_warning']),
        ewayBillNumber: stringValue(json['eway_bill_number']),
        ewayBillDate: stringValue(json['eway_bill_date']),
        ewayBillWarning: stringValue(json['eway_bill_warning']),
        leftToBillQuantity: stringValue(json['left_to_bill_quantity']),
        leftToBillAmount: stringValue(json['left_to_bill_amount']),
      );

  DocumentHeaderSnapshot toHeader() => DocumentHeaderSnapshot(
        documentTypeCode: 'GOODS_RECEIPT_NOTE',
        documentTypeName: 'Goods Receipt Note',
        documentNumber: grnNumber,
        documentDate: receiptDate,
        reference: purchaseOrderNumber,
        branch: branchId,
        warehouse: warehouseId,
        firm: firmId,
        businessProfile: '',
        currency: '',
        exchangeRate: '',
        status: status,
        remarks: remarks,
        createdBy: '',
        approvedBy: '',
      );

  DocumentTotalsSnapshot toTotals() => DocumentTotalsSnapshot(
        subtotal: subtotal,
        discount: lineDiscountTotal,
        tax: taxTotal,
        charges: additionalCharges,
        roundOff: roundOff,
        grandTotal: grandTotal,
      );
}
