import 'entities.dart';
import 'line_tax_rule.dart';
import 'product.dart' show AttributeValueRecord, ProductAttributeValueRecord;

/// The largest purchase order one role may approve (backlog 68 row 4): the
/// order's grand total, tax included.
class RolePurchaseApprovalLimit {
  const RolePurchaseApprovalLimit({
    required this.roleCode,
    required this.maxOrderAmount,
  });

  final String roleCode;

  /// An amount, as the server states it.
  final String maxOrderAmount;

  factory RolePurchaseApprovalLimit.fromJson(Json json) =>
      RolePurchaseApprovalLimit(
        roleCode: stringValue(json['role_code']),
        maxOrderAmount: stringValue(json['max_order_amount']),
      );

  Json toJson() => <String, dynamic>{
        'role_code': roleCode,
        'max_order_amount': maxOrderAmount,
      };
}

/// One month's purchase budget and how much of it is spent (BUY-14). A row
/// with neither branch nor category is the firm-wide budget for the month.
class PurchaseBudget {
  const PurchaseBudget({
    required this.id,
    required this.budgetMonth,
    required this.branchId,
    required this.productCategoryId,
    required this.label,
    required this.amount,
    required this.used,
    required this.available,
    this.version = 0,
  });

  final String id;

  /// The first day of the month, `YYYY-MM-DD`.
  final String budgetMonth;
  final String? branchId;
  final String? productCategoryId;
  final String label;
  final String amount;
  final String used;
  final String available;
  final int version;

  factory PurchaseBudget.fromJson(Json json) => PurchaseBudget(
        id: stringValue(json['id']),
        budgetMonth: stringValue(json['budget_month']),
        branchId: _idOrNull(json['branch_id']),
        productCategoryId: _idOrNull(json['product_category_id']),
        label: stringValue(json['label']),
        amount: stringValue(json['amount']),
        used: stringValue(json['used']),
        available: stringValue(json['available']),
        version: _revisionInt(json['version']),
      );
}

/// A budget as one order stands against it (BUY-14).
class PurchaseOrderBudgetRow {
  const PurchaseOrderBudgetRow({
    required this.budgetId,
    required this.label,
    required this.amount,
    required this.used,
    required this.thisOrder,
    required this.available,
    required this.exceeded,
  });

  final String budgetId;
  final String label;
  final String amount;
  final String used;
  final String thisOrder;
  final String available;
  final bool exceeded;

  factory PurchaseOrderBudgetRow.fromJson(Json json) => PurchaseOrderBudgetRow(
        budgetId: stringValue(json['budget_id']),
        label: stringValue(json['label']),
        amount: stringValue(json['amount']),
        used: stringValue(json['used']),
        thisOrder: stringValue(json['this_order']),
        available: stringValue(json['available']),
        exceeded: boolValue(json['exceeded']),
      );
}

class PurchaseOrderLine {
  const PurchaseOrderLine({
    required this.id,
    required this.lineNumber,
    required this.productId,
    required this.description,
    required this.vendorProductCode,
    required this.purchaseUomId,
    required this.inventoryUomId,
    required this.conversionFactor,
    required this.conversionVersion,
    required this.orderedQuantity,
    required this.freeQuantity,
    required this.baseQuantity,
    required this.unitPrice,
    required this.discountPercent,
    required this.discountAmount,
    required this.grossAmount,
    required this.taxProfileId,
    required this.taxAmount,
    required this.netAmount,
    required this.batchRequired,
    required this.expiryRequired,
    required this.serialRequired,
    required this.manufacturingDate,
    required this.expiryDate,
    required this.warehouseId,
    required this.storageNodeId,
    required this.remarks,
    required this.status,
    required this.createdAt,
    required this.updatedAt,
    this.receivedQuantity = '',
    this.acceptedQuantity = '',
    this.rejectedQuantity = '',
    this.damagedQuantity = '',
    this.returnedQuantity = '',
    this.invoicedQuantity = '',
    this.pendingReceiptQuantity = '',
    this.toInvoiceQuantity = '',
    this.taxRuleCode,
    this.taxRuleVersion,
    this.rateSource,
    this.rateContractLineId = '',
    this.schemeId = '',
    this.schemeName = '',
    this.isCapitalGoods = false,
  });

  /// A fixed asset rather than stock: received without entering stock, and
  /// the bill raises the asset (D-BUY-40).
  final bool isCapitalGoods;

  final String id;
  final int lineNumber;
  final String productId;
  final String description;
  final String vendorProductCode;
  final String purchaseUomId;
  final String inventoryUomId;
  final String conversionFactor;
  final int? conversionVersion;
  final String orderedQuantity;
  final String freeQuantity;
  final String baseQuantity;
  final String unitPrice;
  final String discountPercent;
  final String discountAmount;
  final String grossAmount;
  final String taxProfileId;
  final String taxAmount;
  final String netAmount;
  final bool batchRequired;
  final bool expiryRequired;
  final bool serialRequired;
  final String manufacturingDate;
  final String expiryDate;
  final String warehouseId;
  final String storageNodeId;
  final String remarks;
  final String status;
  final String createdAt;
  final String updatedAt;

  /// What has happened to the line since it was ordered (backlog 69 row 5).
  /// Read-only: the server derives them and forbids them in a write, so
  /// `toWriteJson` never names them. Empty on a line the server has not sent.
  final String receivedQuantity;
  final String acceptedQuantity;
  final String rejectedQuantity;
  final String damagedQuantity;
  final String returnedQuantity;
  final String invoicedQuantity;
  final String pendingReceiptQuantity;
  final String toInvoiceQuantity;

  /// The tax rule that decided this line's tax; null when none matched.
  final String? taxRuleCode;
  final int? taxRuleVersion;

  /// Where the server took the rate from (RATE_CONTRACT, PRICE_LIST,
  /// CATALOGUE, PRICE_REVISION, PRODUCT, TYPED); null when it says nothing.
  /// Read-only: the server sets it and `toWriteJson` never names it (PG-9).
  final String? rateSource;

  /// The rate-contract line that priced this one; empty when none did.
  final String rateContractLineId;

  bool get isRateContract => rateSource == 'RATE_CONTRACT';

  /// The supplier scheme that gave this line its free goods, or a gift line
  /// its reason to exist (PG-11); empty when none did.
  final String schemeId;
  final String schemeName;

  factory PurchaseOrderLine.fromJson(Json json) => PurchaseOrderLine(
        id: stringValue(json['id']),
        lineNumber: (json['line_number'] as num?)?.toInt() ?? 0,
        productId: stringValue(json['product_id']),
        description: stringValue(json['description']),
        vendorProductCode: stringValue(json['vendor_product_code']),
        purchaseUomId: stringValue(json['purchase_uom_id']),
        inventoryUomId: stringValue(json['inventory_uom_id']),
        conversionFactor: stringValue(json['conversion_factor']),
        conversionVersion: (json['conversion_version'] as num?)?.toInt(),
        orderedQuantity: stringValue(json['ordered_quantity']),
        freeQuantity: stringValue(json['free_quantity']),
        baseQuantity: stringValue(json['base_quantity']),
        unitPrice: stringValue(json['unit_price']),
        discountPercent: stringValue(json['discount_percent']),
        discountAmount: stringValue(json['discount_amount']),
        grossAmount: stringValue(json['gross_amount']),
        taxProfileId: stringValue(json['tax_profile_id']),
        taxAmount: stringValue(json['tax_amount']),
        netAmount: stringValue(json['net_amount']),
        batchRequired: boolValue(json['batch_required']),
        expiryRequired: boolValue(json['expiry_required']),
        serialRequired: boolValue(json['serial_required']),
        manufacturingDate: stringValue(json['manufacturing_date']),
        expiryDate: stringValue(json['expiry_date']),
        warehouseId: stringValue(json['warehouse_id']),
        storageNodeId: stringValue(json['storage_node_id']),
        remarks: stringValue(json['remarks']),
        status: stringValue(json['status']),
        createdAt: stringValue(json['created_at']),
        updatedAt: stringValue(json['updated_at']),
        receivedQuantity: stringValue(json['received_quantity']),
        acceptedQuantity: stringValue(json['accepted_quantity']),
        rejectedQuantity: stringValue(json['rejected_quantity']),
        damagedQuantity: stringValue(json['damaged_quantity']),
        returnedQuantity: stringValue(json['returned_quantity']),
        invoicedQuantity: stringValue(json['invoiced_quantity']),
        pendingReceiptQuantity: stringValue(json['pending_receipt_quantity']),
        toInvoiceQuantity: stringValue(json['to_invoice_quantity']),
        taxRuleCode: LineTaxRule.fromJson(json).code,
        taxRuleVersion: LineTaxRule.fromJson(json).version,
        rateSource: json['rate_source'] is String
            ? json['rate_source'] as String
            : null,
        rateContractLineId: stringValue(json['rate_contract_line_id']),
        schemeId: stringValue(json['scheme_id']),
        schemeName: stringValue(json['scheme_name']),
        isCapitalGoods: boolValue(json['is_capital_goods']),
      );

  PurchaseOrderLine copyWith({
    String? id,
    int? lineNumber,
    String? productId,
    String? description,
    String? vendorProductCode,
    String? purchaseUomId,
    String? inventoryUomId,
    String? orderedQuantity,
    String? freeQuantity,
    String? unitPrice,
    String? discountPercent,
    String? discountAmount,
    String? taxProfileId,
    bool? batchRequired,
    bool? expiryRequired,
    bool? serialRequired,
    String? manufacturingDate,
    String? expiryDate,
    String? warehouseId,
    String? storageNodeId,
    String? remarks,
    String? schemeId,
    String? schemeName,
    bool? isCapitalGoods,
  }) =>
      PurchaseOrderLine(
        id: id ?? this.id,
        lineNumber: lineNumber ?? this.lineNumber,
        productId: productId ?? this.productId,
        description: description ?? this.description,
        vendorProductCode: vendorProductCode ?? this.vendorProductCode,
        purchaseUomId: purchaseUomId ?? this.purchaseUomId,
        inventoryUomId: inventoryUomId ?? this.inventoryUomId,
        conversionFactor: conversionFactor,
        conversionVersion: conversionVersion,
        orderedQuantity: orderedQuantity ?? this.orderedQuantity,
        freeQuantity: freeQuantity ?? this.freeQuantity,
        baseQuantity: baseQuantity,
        unitPrice: unitPrice ?? this.unitPrice,
        discountPercent: discountPercent ?? this.discountPercent,
        discountAmount: discountAmount ?? this.discountAmount,
        grossAmount: grossAmount,
        taxProfileId: taxProfileId ?? this.taxProfileId,
        taxAmount: taxAmount,
        netAmount: netAmount,
        batchRequired: batchRequired ?? this.batchRequired,
        expiryRequired: expiryRequired ?? this.expiryRequired,
        serialRequired: serialRequired ?? this.serialRequired,
        manufacturingDate: manufacturingDate ?? this.manufacturingDate,
        expiryDate: expiryDate ?? this.expiryDate,
        warehouseId: warehouseId ?? this.warehouseId,
        storageNodeId: storageNodeId ?? this.storageNodeId,
        remarks: remarks ?? this.remarks,
        status: status,
        createdAt: createdAt,
        updatedAt: updatedAt,
        receivedQuantity: receivedQuantity,
        acceptedQuantity: acceptedQuantity,
        rejectedQuantity: rejectedQuantity,
        damagedQuantity: damagedQuantity,
        returnedQuantity: returnedQuantity,
        invoicedQuantity: invoicedQuantity,
        pendingReceiptQuantity: pendingReceiptQuantity,
        toInvoiceQuantity: toInvoiceQuantity,
        taxRuleCode: taxRuleCode,
        taxRuleVersion: taxRuleVersion,
        rateSource: rateSource,
        rateContractLineId: rateContractLineId,
        schemeId: schemeId ?? this.schemeId,
        schemeName: schemeName ?? this.schemeName,
        isCapitalGoods: isCapitalGoods ?? this.isCapitalGoods,
      );

  /// A line that only gives goods: nothing is paid for, a scheme says why.
  factory PurchaseOrderLine.gift({
    required int lineNumber,
    required String productId,
    required String freeQuantity,
    required String schemeId,
    String schemeName = '',
    String warehouseId = '',
    String uomId = '',
  }) =>
      PurchaseOrderLine(
        id: '',
        lineNumber: lineNumber,
        productId: productId,
        description: '',
        vendorProductCode: '',
        purchaseUomId: uomId,
        inventoryUomId: uomId,
        conversionFactor: '1',
        conversionVersion: null,
        orderedQuantity: '0',
        freeQuantity: freeQuantity,
        baseQuantity: '0',
        unitPrice: '',
        discountPercent: '',
        discountAmount: '0',
        grossAmount: '0',
        taxProfileId: '',
        taxAmount: '0',
        netAmount: '0',
        batchRequired: false,
        expiryRequired: false,
        serialRequired: false,
        manufacturingDate: '',
        expiryDate: '',
        warehouseId: warehouseId,
        storageNodeId: '',
        remarks: '',
        status: 'ACTIVE',
        createdAt: '',
        updatedAt: '',
        schemeId: schemeId,
        schemeName: schemeName,
      );

  bool get _isGift => (double.tryParse(orderedQuantity.trim()) ?? 0) == 0;

  Json toWriteJson() => {
        'product_id': productId,
        if (description.isNotEmpty) 'description': description,
        if (vendorProductCode.isNotEmpty)
          'vendor_product_code': vendorProductCode,
        if (purchaseUomId.isNotEmpty) 'purchase_uom_id': purchaseUomId,
        if (inventoryUomId.isNotEmpty) 'inventory_uom_id': inventoryUomId,
        'ordered_quantity': orderedQuantity.isEmpty ? '0' : orderedQuantity,
        // Blank is null, not zero: silence takes a same-product supplier
        // scheme and a typed 0 refuses it (PG-11).
        'free_quantity': freeQuantity.trim().isEmpty ? null : freeQuantity,
        // Named only on a gift line (nothing paid for) that a scheme added.
        if (schemeId.isNotEmpty && _isGift) 'scheme_id': schemeId,
        // Blank is null, not zero: the server then takes the supplier's list
        // or the product's price, and the supplier's discount (BUY-3).
        'unit_price': unitPrice.trim().isEmpty ? null : unitPrice,
        'discount_percent':
            discountPercent.trim().isEmpty ? null : discountPercent,
        'discount_amount': discountAmount.isEmpty ? '0' : discountAmount,
        if (taxProfileId.isNotEmpty) 'tax_profile_id': taxProfileId,
        'batch_required': batchRequired,
        'expiry_required': expiryRequired,
        'serial_required': serialRequired,
        if (manufacturingDate.isNotEmpty)
          'manufacturing_date': manufacturingDate,
        if (expiryDate.isNotEmpty) 'expiry_date': expiryDate,
        if (warehouseId.isNotEmpty) 'warehouse_id': warehouseId,
        if (storageNodeId.isNotEmpty) 'storage_node_id': storageNodeId,
        if (remarks.isNotEmpty) 'remarks': remarks,
        // Named only when ticked: silence is stock.
        if (isCapitalGoods) 'is_capital_goods': true,
      };
}

class PurchaseDeliverySchedule {
  const PurchaseDeliverySchedule({
    required this.id,
    required this.purchaseOrderLineId,
    required this.lineNumber,
    required this.deliveryDate,
    required this.quantity,
    required this.status,
    required this.remarks,
    required this.createdAt,
    required this.updatedAt,
  });

  final String id;
  final String purchaseOrderLineId;
  final int lineNumber;
  final String deliveryDate;
  final String quantity;
  final String status;
  final String remarks;
  final String createdAt;
  final String updatedAt;

  factory PurchaseDeliverySchedule.fromJson(Json json) =>
      PurchaseDeliverySchedule(
        id: stringValue(json['id']),
        purchaseOrderLineId: stringValue(json['purchase_order_line_id']),
        lineNumber: (json['line_number'] as num?)?.toInt() ?? 0,
        deliveryDate: stringValue(json['delivery_date']),
        quantity: stringValue(json['quantity']),
        status: stringValue(json['status']),
        remarks: stringValue(json['remarks']),
        createdAt: stringValue(json['created_at']),
        updatedAt: stringValue(json['updated_at']),
      );

  PurchaseDeliverySchedule copyWith({
    String? id,
    int? lineNumber,
    String? deliveryDate,
    String? quantity,
    String? remarks,
  }) =>
      PurchaseDeliverySchedule(
        id: id ?? this.id,
        purchaseOrderLineId: purchaseOrderLineId,
        lineNumber: lineNumber ?? this.lineNumber,
        deliveryDate: deliveryDate ?? this.deliveryDate,
        quantity: quantity ?? this.quantity,
        status: status,
        remarks: remarks ?? this.remarks,
        createdAt: createdAt,
        updatedAt: updatedAt,
      );

  Json toWriteJson() => {
        'line_number': lineNumber,
        'delivery_date': deliveryDate,
        'quantity': quantity.isEmpty ? '0' : quantity,
        if (remarks.isNotEmpty) 'remarks': remarks,
      };
}

class PurchaseAttachment {
  const PurchaseAttachment({
    required this.id,
    required this.fileName,
    required this.mimeType,
    required this.filePath,
    required this.attachmentKind,
    required this.createdAt,
    required this.updatedAt,
  });

  final String id;
  final String fileName;
  final String mimeType;
  final String filePath;
  final String attachmentKind;
  final String createdAt;
  final String updatedAt;

  factory PurchaseAttachment.fromJson(Json json) => PurchaseAttachment(
        id: stringValue(json['id']),
        fileName: stringValue(json['file_name']),
        mimeType: stringValue(json['mime_type']),
        filePath: stringValue(json['file_path']),
        attachmentKind: stringValue(json['attachment_kind']),
        createdAt: stringValue(json['created_at']),
        updatedAt: stringValue(json['updated_at']),
      );

  PurchaseAttachment copyWith({
    String? id,
    String? fileName,
    String? mimeType,
    String? filePath,
    String? attachmentKind,
  }) =>
      PurchaseAttachment(
        id: id ?? this.id,
        fileName: fileName ?? this.fileName,
        mimeType: mimeType ?? this.mimeType,
        filePath: filePath ?? this.filePath,
        attachmentKind: attachmentKind ?? this.attachmentKind,
        createdAt: createdAt,
        updatedAt: updatedAt,
      );

  Json toWriteJson() => {
        'file_name': fileName,
        if (mimeType.isNotEmpty) 'mime_type': mimeType,
        'file_path': filePath,
        'attachment_kind':
            attachmentKind.isEmpty ? 'PURCHASE_FILE' : attachmentKind,
      };
}

class PurchaseNote {
  const PurchaseNote({
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

  factory PurchaseNote.fromJson(Json json) => PurchaseNote(
        id: stringValue(json['id']),
        noteType: stringValue(json['note_type']),
        note: stringValue(json['note']),
        createdAt: stringValue(json['created_at']),
        updatedAt: stringValue(json['updated_at']),
      );

  PurchaseNote copyWith({String? id, String? noteType, String? note}) =>
      PurchaseNote(
        id: id ?? this.id,
        noteType: noteType ?? this.noteType,
        note: note ?? this.note,
        createdAt: createdAt,
        updatedAt: updatedAt,
      );

  Json toWriteJson() => {
        'note_type': noteType.isEmpty ? 'INTERNAL' : noteType,
        'note': note,
      };
}

class PurchaseOrderHistoryRecord {
  const PurchaseOrderHistoryRecord({
    required this.id,
    required this.action,
    required this.fromStatus,
    required this.toStatus,
    required this.remarks,
    required this.detailsJson,
    required this.createdBy,
    required this.createdAt,
  });

  final String id;
  final String action;
  final String fromStatus;
  final String toStatus;
  final String remarks;
  final String detailsJson;
  final String createdBy;
  final String createdAt;

  factory PurchaseOrderHistoryRecord.fromJson(Json json) =>
      PurchaseOrderHistoryRecord(
        id: stringValue(json['id']),
        action: stringValue(json['action']),
        fromStatus: stringValue(json['from_status']),
        toStatus: stringValue(json['to_status']),
        remarks: stringValue(json['remarks']),
        detailsJson: stringValue(json['details_json']),
        createdBy: stringValue(json['created_by']),
        createdAt: stringValue(json['created_at']),
      );
}

/// An earlier version of an amended order (BUY-8), as it stood before the
/// amendment named by [revisionNumber] replaced it.
class PurchaseOrderRevision {
  const PurchaseOrderRevision({
    required this.id,
    required this.revisionNumber,
    required this.grandTotal,
    required this.reason,
    required this.amendedBy,
    required this.amendedAt,
    required this.snapshot,
  });

  final String id;
  final int revisionNumber;
  final String grandTotal;
  final String reason;
  final String amendedBy;
  final String amendedAt;
  final Json snapshot;

  factory PurchaseOrderRevision.fromJson(Json json) => PurchaseOrderRevision(
        id: stringValue(json['id']),
        revisionNumber: _revisionInt(json['revision_number']),
        grandTotal: stringValue(json['grand_total']),
        reason: stringValue(json['reason']),
        amendedBy: stringValue(json['amended_by']),
        amendedAt: stringValue(json['amended_at']),
        snapshot: json['snapshot'] is Map
            ? Map<String, dynamic>.from(json['snapshot'] as Map)
            : const <String, dynamic>{},
      );

  /// The snapshot's lines, as plain maps.
  List<Json> get lines => [
        if (snapshot['lines'] is List)
          for (final dynamic line in snapshot['lines'] as List)
            if (line is Map) Map<String, dynamic>.from(line),
      ];
}

class PurchaseOrder {
  const PurchaseOrder({
    required this.id,
    required this.firmId,
    required this.branchId,
    required this.warehouseId,
    required this.vendorId,
    required this.buyerId,
    required this.taxProfileId,
    required this.poNumber,
    required this.vendorContact,
    required this.vendorAddress,
    required this.department,
    required this.purchaseType,
    required this.purchaseCategory,
    required this.purchaseDate,
    required this.expectedDeliveryDate,
    required this.paymentTerms,
    required this.deliveryTerms,
    required this.currencyCode,
    required this.exchangeRate,
    required this.referenceNumber,
    required this.externalReference,
    required this.priority,
    required this.remarks,
    required this.status,
    required this.subtotal,
    required this.lineDiscountTotal,
    required this.headerDiscountAmount,
    required this.taxTotal,
    required this.additionalCharges,
    required this.roundOff,
    required this.grandTotal,
    required this.closeReason,
    required this.cancelReason,
    this.sentAt = '',
    this.sentVia = '',
    this.revisionNumber = 0,
    this.billingStatus = '',
    this.isComplete = false,
    required this.isDeleted,
    required this.createdAt,
    required this.updatedAt,
    required this.lines,
    required this.deliverySchedules,
    required this.attachments,
    required this.notes,
    this.attributes = const [],
    this.attributeInputs,
    this.rateContractWarning,
    this.savedCurrencyCode,
    this.savedExchangeRate,
  });

  /// The currency and rate the server held when this order was read; null on
  /// an order that has not been saved. An update sends the two keys only when
  /// they differ from these, because a key left out keeps what the order
  /// holds (D-BUY-39).
  final String? savedCurrencyCode;
  final String? savedExchangeRate;

  /// An over-draw warning from a rate contract; never blocks (PG-9).
  final String? rateContractWarning;

  /// The firm's own fields on this order as stored (MST-6); empty on a
  /// response from before they existed.
  final List<AttributeValueRecord> attributes;

  /// The `attributes` to send on a save, set by the editor only once the
  /// firm's definitions have been read. Null means "leave the stored values
  /// alone"; an empty list would clear them.
  final List<Json>? attributeInputs;

  final String id;
  final String firmId;
  final String branchId;
  final String warehouseId;
  final String vendorId;
  final String buyerId;
  final String taxProfileId;
  final String poNumber;
  final String vendorContact;
  final String vendorAddress;
  final String department;
  final String purchaseType;
  final String purchaseCategory;
  final String purchaseDate;
  final String expectedDeliveryDate;
  final String paymentTerms;
  final String deliveryTerms;
  final String currencyCode;
  final String exchangeRate;
  final String referenceNumber;
  final String externalReference;
  final String priority;
  final String remarks;
  final String status;

  /// Raised but not yet sent for approval.
  bool get isDraft => status == 'DRAFT';

  /// Sent for approval and waiting on it. Reachable since 2026-08-16: before
  /// that nothing performed the transition, so no order was ever in this
  /// state and the Open Orders tab it feeds was empty for every firm.
  bool get isSubmitted => status == 'SUBMITTED';

  /// Committed to. Editing one withdraws the approval server-side.
  bool get isApproved => status == 'APPROVED';

  /// Some or all of it has arrived, so its lines are what stock was posted
  /// at and the server refuses to change them.
  bool get hasReceipts =>
      status == 'PARTIALLY_RECEIVED' || status == 'RECEIVED';

  /// Finished with, either way.
  bool get isTerminal => status == 'CANCELLED' || status == 'CLOSED';

  /// Whether the server will accept an edit at all.
  ///
  /// Mirrors `PurchaseService._assert_order_editable`. A button that offers
  /// what the server refuses is a round trip whose only outcome is an error
  /// message.
  bool get isEditable => !isDeleted && !hasReceipts && !isTerminal;

  /// Why an edit is refused, or null when it is not.
  String? get editRefusal {
    if (isDeleted) return 'This purchase order is deleted. Restore it first.';
    if (hasReceipts) {
      return 'Goods have been received against this order, so its lines '
          'cannot be changed. Cancel the receipt first, or raise a purchase '
          'return.';
    }
    if (status == 'CANCELLED') {
      return 'Cancelled purchase orders cannot be changed.';
    }
    if (status == 'CLOSED') return 'Closed purchase orders cannot be changed.';
    return null;
  }

  final String subtotal;
  final String lineDiscountTotal;
  final String headerDiscountAmount;
  final String taxTotal;
  final String additionalCharges;
  final String roundOff;
  final String grandTotal;
  final String closeReason;
  final String cancelReason;

  /// When and how (EMAIL, PRINT, WHATSAPP, OTHER) the approved order reached
  /// the supplier (backlog 69 row 6); empty when it never has.
  final String sentAt;
  final String sentVia;

  /// 0 for an order never amended after approval (BUY-8).
  final int revisionNumber;

  /// The number as lists show it, with the amendment beside it.
  String get numberLabel =>
      revisionNumber > 0 ? '$poNumber (Amendment $revisionNumber)' : poNumber;

  /// Whether the amend action applies: approved or later, and not finished.
  bool get isAmendable =>
      !isDeleted &&
      const {'APPROVED', 'PARTIALLY_RECEIVED', 'RECEIVED'}.contains(status);

  /// NOT_INVOICED, PARTIALLY_INVOICED or INVOICED, beside the lifecycle
  /// status and never instead of it (backlog 69 row 5). Read-only.
  final String billingStatus;
  final bool isComplete;

  /// Approved and not yet finished: a promise the supplier can be sent.
  bool get isSendable =>
      !isDeleted &&
      const {'APPROVED', 'PARTIALLY_ORDERED', 'ORDERED', 'PARTIALLY_RECEIVED'}
          .contains(status);
  final bool isDeleted;
  final String createdAt;
  final String updatedAt;
  final List<PurchaseOrderLine> lines;
  final List<PurchaseDeliverySchedule> deliverySchedules;
  final List<PurchaseAttachment> attachments;
  final List<PurchaseNote> notes;

  factory PurchaseOrder.fromJson(Json json) => PurchaseOrder(
        id: stringValue(json['id']),
        firmId: stringValue(json['firm_id']),
        branchId: stringValue(json['branch_id']),
        warehouseId: stringValue(json['warehouse_id']),
        vendorId: stringValue(json['vendor_id']),
        buyerId: stringValue(json['buyer_id']),
        taxProfileId: stringValue(json['tax_profile_id']),
        poNumber: stringValue(json['po_number']),
        vendorContact: stringValue(json['vendor_contact']),
        vendorAddress: stringValue(json['vendor_address']),
        department: stringValue(json['department']),
        purchaseType: stringValue(json['purchase_type']),
        purchaseCategory: stringValue(json['purchase_category']),
        purchaseDate: stringValue(json['purchase_date']),
        expectedDeliveryDate: stringValue(json['expected_delivery_date']),
        paymentTerms: stringValue(json['payment_terms']),
        deliveryTerms: stringValue(json['delivery_terms']),
        currencyCode: stringValue(json['currency_code']),
        exchangeRate: stringValue(json['exchange_rate']),
        referenceNumber: stringValue(json['reference_number']),
        externalReference: stringValue(json['external_reference']),
        priority: stringValue(json['priority']),
        remarks: stringValue(json['remarks']),
        status: stringValue(json['status']),
        subtotal: stringValue(json['subtotal']),
        lineDiscountTotal: stringValue(json['line_discount_total']),
        headerDiscountAmount: stringValue(json['header_discount_amount']),
        taxTotal: stringValue(json['tax_total']),
        additionalCharges: stringValue(json['additional_charges']),
        roundOff: stringValue(json['round_off']),
        grandTotal: stringValue(json['grand_total']),
        closeReason: stringValue(json['close_reason']),
        cancelReason: stringValue(json['cancel_reason']),
        sentAt: stringValue(json['sent_at']),
        sentVia: stringValue(json['sent_via']),
        revisionNumber: _revisionInt(json['revision_number']),
        billingStatus: stringValue(json['billing_status']),
        isComplete: boolValue(json['is_complete']),
        isDeleted: boolValue(json['is_deleted']),
        createdAt: stringValue(json['created_at']),
        updatedAt: stringValue(json['updated_at']),
        lines: _objects(json['lines']).map(PurchaseOrderLine.fromJson).toList(),
        deliverySchedules: _objects(json['delivery_schedules'])
            .map(PurchaseDeliverySchedule.fromJson)
            .toList(),
        attachments: _objects(json['attachments'])
            .map(PurchaseAttachment.fromJson)
            .toList(),
        notes: _objects(json['notes']).map(PurchaseNote.fromJson).toList(),
        attributes: _objects(json['attributes'])
            .map(ProductAttributeValueRecord.fromJson)
            .toList(),
        rateContractWarning: json['rate_contract_warning'] is String &&
                (json['rate_contract_warning'] as String).isNotEmpty
            ? json['rate_contract_warning'] as String
            : null,
        savedCurrencyCode: stringValue(json['currency_code']),
        savedExchangeRate: stringValue(json['exchange_rate']),
      );

  PurchaseOrder copyWith({
    String? id,
    String? branchId,
    String? warehouseId,
    String? vendorId,
    String? buyerId,
    String? taxProfileId,
    String? poNumber,
    String? vendorContact,
    String? vendorAddress,
    String? department,
    String? purchaseType,
    String? purchaseCategory,
    String? purchaseDate,
    String? expectedDeliveryDate,
    String? paymentTerms,
    String? deliveryTerms,
    String? currencyCode,
    String? exchangeRate,
    String? referenceNumber,
    String? externalReference,
    String? priority,
    String? remarks,
    String? status,
    String? headerDiscountAmount,
    String? additionalCharges,
    String? roundOff,
    List<PurchaseOrderLine>? lines,
    List<PurchaseDeliverySchedule>? deliverySchedules,
    List<PurchaseAttachment>? attachments,
    List<PurchaseNote>? notes,
    List<Json>? attributeInputs,
  }) =>
      PurchaseOrder(
        id: id ?? this.id,
        attributes: attributes,
        attributeInputs: attributeInputs ?? this.attributeInputs,
        rateContractWarning: rateContractWarning,
        savedCurrencyCode: savedCurrencyCode,
        savedExchangeRate: savedExchangeRate,
        firmId: firmId,
        branchId: branchId ?? this.branchId,
        warehouseId: warehouseId ?? this.warehouseId,
        vendorId: vendorId ?? this.vendorId,
        buyerId: buyerId ?? this.buyerId,
        taxProfileId: taxProfileId ?? this.taxProfileId,
        poNumber: poNumber ?? this.poNumber,
        vendorContact: vendorContact ?? this.vendorContact,
        vendorAddress: vendorAddress ?? this.vendorAddress,
        department: department ?? this.department,
        purchaseType: purchaseType ?? this.purchaseType,
        purchaseCategory: purchaseCategory ?? this.purchaseCategory,
        purchaseDate: purchaseDate ?? this.purchaseDate,
        expectedDeliveryDate: expectedDeliveryDate ?? this.expectedDeliveryDate,
        paymentTerms: paymentTerms ?? this.paymentTerms,
        deliveryTerms: deliveryTerms ?? this.deliveryTerms,
        currencyCode: currencyCode ?? this.currencyCode,
        exchangeRate: exchangeRate ?? this.exchangeRate,
        referenceNumber: referenceNumber ?? this.referenceNumber,
        externalReference: externalReference ?? this.externalReference,
        priority: priority ?? this.priority,
        remarks: remarks ?? this.remarks,
        status: status ?? this.status,
        subtotal: subtotal,
        lineDiscountTotal: lineDiscountTotal,
        headerDiscountAmount: headerDiscountAmount ?? this.headerDiscountAmount,
        taxTotal: taxTotal,
        additionalCharges: additionalCharges ?? this.additionalCharges,
        roundOff: roundOff ?? this.roundOff,
        grandTotal: grandTotal,
        closeReason: closeReason,
        cancelReason: cancelReason,
        sentAt: sentAt,
        sentVia: sentVia,
        revisionNumber: revisionNumber,
        billingStatus: billingStatus,
        isComplete: isComplete,
        isDeleted: isDeleted,
        createdAt: createdAt,
        updatedAt: updatedAt,
        lines: lines ?? this.lines,
        deliverySchedules: deliverySchedules ?? this.deliverySchedules,
        attachments: attachments ?? this.attachments,
        notes: notes ?? this.notes,
      );

  Json toCreateJson() => {
        if (poNumber.trim().isNotEmpty) 'po_number': poNumber.trim(),
        'branch_id': branchId,
        'warehouse_id': warehouseId,
        'vendor_id': vendorId,
        if (buyerId.isNotEmpty) 'buyer_id': buyerId,
        if (taxProfileId.isNotEmpty) 'tax_profile_id': taxProfileId,
        if (vendorContact.isNotEmpty) 'vendor_contact': vendorContact,
        if (vendorAddress.isNotEmpty) 'vendor_address': vendorAddress,
        if (department.isNotEmpty) 'department': department,
        'purchase_type':
            purchaseType.isEmpty ? 'STANDARD_PURCHASE' : purchaseType,
        if (purchaseCategory.isNotEmpty) 'purchase_category': purchaseCategory,
        'purchase_date': purchaseDate,
        if (expectedDeliveryDate.isNotEmpty)
          'expected_delivery_date': expectedDeliveryDate,
        if (paymentTerms.isNotEmpty) 'payment_terms': paymentTerms,
        if (deliveryTerms.isNotEmpty) 'delivery_terms': deliveryTerms,
        // Rupees, blank or INR, send neither key; a foreign order sends both
        // (D-BUY-39).
        if (_foreignCurrency(currencyCode)) 'currency_code': currencyCode,
        if (_foreignCurrency(currencyCode) && exchangeRate.isNotEmpty)
          'exchange_rate': exchangeRate,
        if (referenceNumber.isNotEmpty) 'reference_number': referenceNumber,
        if (externalReference.isNotEmpty)
          'external_reference': externalReference,
        'priority': priority.isEmpty ? 'NORMAL' : priority,
        if (remarks.isNotEmpty) 'remarks': remarks,
        'status': status.isEmpty ? 'DRAFT' : status,
        'header_discount_amount':
            headerDiscountAmount.isEmpty ? '0' : headerDiscountAmount,
        'additional_charges':
            additionalCharges.isEmpty ? '0' : additionalCharges,
        'round_off': roundOff.isEmpty ? '0' : roundOff,
        'lines': lines.map((item) => item.toWriteJson()).toList(),
        'delivery_schedules':
            deliverySchedules.map((item) => item.toWriteJson()).toList(),
        'attachments': attachments.map((item) => item.toWriteJson()).toList(),
        'notes': notes.map((item) => item.toWriteJson()).toList(),
        if (attributeInputs != null) 'attributes': attributeInputs,
      };

  /// The same body as a create, without the status.
  ///
  /// The server owns the status through its lifecycle endpoints and ignores
  /// what an update says about it. Sending the value we last read is what hid
  /// the defect underneath: the server's own default for the field is DRAFT,
  /// so any client that stayed quiet silently reset an approved order, while
  /// this one echoed the status back and so let an approved order be edited to
  /// any amount and stay approved.
  Json toUpdateJson() {
    final Json body = toCreateJson();
    body.remove('status');
    // The number is the server's: PurchaseOrderCreate takes one, so a client
    // can carry an old system's numbering in, but PurchaseOrderUpdate does
    // not, and the server forbids unknown fields. A saved order always has
    // its number, so every edit of one was refused with "The request
    // validation failed." -- seven times on the day it was found, with the
    // editor showing only that sentence.
    body.remove('po_number');
    // A key left out keeps what the order holds and an explicit null clears
    // it, so the two travel only when they changed from what was read.
    body.remove('currency_code');
    body.remove('exchange_rate');
    final String now = _foreignCurrency(currencyCode)
        ? currencyCode.trim().toUpperCase()
        : '';
    final String was = _foreignCurrency(savedCurrencyCode ?? '')
        ? (savedCurrencyCode ?? '').trim().toUpperCase()
        : '';
    final String nowRate = now.isEmpty ? '' : exchangeRate.trim();
    final String wasRate = was.isEmpty ? '' : (savedExchangeRate ?? '').trim();
    if (now != was) body['currency_code'] = now.isEmpty ? null : now;
    if (!_sameRate(nowRate, wasRate)) {
      body['exchange_rate'] = nowRate.isEmpty ? null : nowRate;
    }
    return body;
  }

  static bool _foreignCurrency(String code) {
    final String upper = code.trim().toUpperCase();
    return upper.isNotEmpty && upper != 'INR';
  }

  static bool _sameRate(String a, String b) {
    if (a == b) return true;
    final double? x = double.tryParse(a);
    final double? y = double.tryParse(b);
    return x != null && y != null && x == y;
  }
}

class PurchaseSummaryRecord {
  const PurchaseSummaryRecord({
    required this.total,
    required this.draft,
    required this.open,
    required this.cancelled,
    required this.closed,
    required this.totalValue,
    required this.overdueDelivery,
  });

  final int total;
  final int draft;
  final int open;
  final int cancelled;
  final int closed;
  final String totalValue;
  final int overdueDelivery;

  factory PurchaseSummaryRecord.fromJson(Json json) => PurchaseSummaryRecord(
        total: (json['total'] as num?)?.toInt() ?? 0,
        draft: (json['draft'] as num?)?.toInt() ?? 0,
        open: (json['open'] as num?)?.toInt() ?? 0,
        cancelled: (json['cancelled'] as num?)?.toInt() ?? 0,
        closed: (json['closed'] as num?)?.toInt() ?? 0,
        totalValue: stringValue(json['total_value']),
        overdueDelivery: (json['overdue_delivery'] as num?)?.toInt() ?? 0,
      );
}

class PurchaseQuery {
  const PurchaseQuery({
    this.vendorId,
    this.status,
    this.branchId,
    this.warehouseId,
    this.buyerId,
    this.purchaseType,
    this.createdFrom,
    this.createdTo,
    this.includeDeleted = false,
  });

  final String? vendorId;
  final String? status;
  final String? branchId;
  final String? warehouseId;
  final String? buyerId;
  final String? purchaseType;
  final String? createdFrom;
  final String? createdTo;
  final bool includeDeleted;

  Map<String, String> toQuery() => {
        if (vendorId?.isNotEmpty == true) 'vendor_id': vendorId!,
        if (status?.isNotEmpty == true) 'status': status!,
        if (branchId?.isNotEmpty == true) 'branch_id': branchId!,
        if (warehouseId?.isNotEmpty == true) 'warehouse_id': warehouseId!,
        if (buyerId?.isNotEmpty == true) 'buyer_id': buyerId!,
        if (purchaseType?.isNotEmpty == true) 'purchase_type': purchaseType!,
        if (createdFrom?.isNotEmpty == true) 'created_from': createdFrom!,
        if (createdTo?.isNotEmpty == true) 'created_to': createdTo!,
        if (includeDeleted) 'include_deleted': 'true',
      };
}

List<Json> _objects(dynamic value) => value is List
    ? value
        .whereType<Map>()
        .map((item) => Map<String, dynamic>.from(item))
        .toList()
    : const [];

/// Which stages of buying this firm fills in by hand.
///
/// The chain is purchase order, goods receipt, bill. A stage that is off is
/// still raised -- by the server, as part of saving the bill -- so this
/// decides which screens a firm sees, never whether the documents exist.
class PurchaseWorkflowSettings {
  const PurchaseWorkflowSettings({
    required this.purchaseOrderStage,
    required this.goodsReceiptStage,
    required this.isConfigured,
    this.defaultBranchId,
    this.defaultWarehouseId,
    this.billPriceTolerancePercent,
    this.billToleranceAmount,
    this.orderQuantityPolicy = 'WARN',
    this.budgetPolicy = 'WARN',
  });

  final bool purchaseOrderStage;
  final bool goodsReceiptStage;
  final String? defaultBranchId;
  final String? defaultWarehouseId;

  /// How far a bill's rate may exceed its order's, in percent (BUY-10). Null
  /// means no check.
  final double? billPriceTolerancePercent;

  /// How far a whole bill may exceed its order's total, as an amount. Null
  /// means no check.
  final double? billToleranceAmount;

  /// What an order off the supplier's minimum or multiple does (BUY-5):
  /// `WARN` (default) or `REFUSE`.
  final String orderQuantityPolicy;

  /// What approving past a purchase budget does (BUY-14): `WARN` (default) or
  /// `NEEDS_APPROVAL`.
  final String budgetPolicy;

  /// False while the firm is still on the platform default: the whole chain.
  final bool isConfigured;

  /// What a firm gets before anybody configures anything, and what the client
  /// falls back to when the settings cannot be read -- failing open, so an
  /// unreachable endpoint never hides screens a firm depends on.
  static const PurchaseWorkflowSettings wholeChain = PurchaseWorkflowSettings(
    purchaseOrderStage: true,
    goodsReceiptStage: true,
    isConfigured: false,
  );

  /// True when the bill is the only buying document its user types, so a
  /// bill names products rather than a receipt.
  bool get billsDirectly => !goodsReceiptStage;

  /// A stage the answer does not mention is taken as typed: failing open, as
  /// [wholeChain] does, since reading "off" hides screens and changes what a
  /// bill names.
  factory PurchaseWorkflowSettings.fromJson(Json json) =>
      PurchaseWorkflowSettings(
        purchaseOrderStage:
            boolValue(json['purchase_order_stage'], fallback: true),
        goodsReceiptStage:
            boolValue(json['goods_receipt_stage'], fallback: true),
        defaultBranchId: _idOrNull(json['default_branch_id']),
        defaultWarehouseId: _idOrNull(json['default_warehouse_id']),
        isConfigured: boolValue(json['is_configured']),
        billPriceTolerancePercent:
            double.tryParse(stringValue(json['bill_price_tolerance_percent'])),
        billToleranceAmount:
            double.tryParse(stringValue(json['bill_tolerance_amount'])),
        orderQuantityPolicy:
            stringValue(json['order_quantity_policy']) == 'REFUSE'
                ? 'REFUSE'
                : 'WARN',
        budgetPolicy: stringValue(json['budget_policy']) == 'NEEDS_APPROVAL'
            ? 'NEEDS_APPROVAL'
            : 'WARN',
      );

  /// The two switches and the two bill tolerances. The server leaves an
  /// omitted default as it is, so a save cannot clear one (the rule D-CFG-14
  /// taught sales); an explicit null tolerance switches that check off.
  Json toJson() => <String, dynamic>{
        'purchase_order_stage': purchaseOrderStage,
        'goods_receipt_stage': goodsReceiptStage,
        'bill_price_tolerance_percent': billPriceTolerancePercent,
        'bill_tolerance_amount': billToleranceAmount,
        'order_quantity_policy': orderQuantityPolicy,
        'budget_policy': budgetPolicy,
      };

  /// [clearPercent] / [clearAmount] switch a tolerance off, which a null
  /// argument cannot say.
  PurchaseWorkflowSettings copyWith({
    bool? purchaseOrderStage,
    bool? goodsReceiptStage,
    double? billPriceTolerancePercent,
    bool clearPercent = false,
    double? billToleranceAmount,
    bool clearAmount = false,
    String? orderQuantityPolicy,
    String? budgetPolicy,
  }) =>
      PurchaseWorkflowSettings(
        purchaseOrderStage: purchaseOrderStage ?? this.purchaseOrderStage,
        goodsReceiptStage: goodsReceiptStage ?? this.goodsReceiptStage,
        defaultBranchId: defaultBranchId,
        defaultWarehouseId: defaultWarehouseId,
        isConfigured: isConfigured,
        billPriceTolerancePercent: clearPercent
            ? null
            : billPriceTolerancePercent ?? this.billPriceTolerancePercent,
        billToleranceAmount: clearAmount
            ? null
            : billToleranceAmount ?? this.billToleranceAmount,
        orderQuantityPolicy: orderQuantityPolicy ?? this.orderQuantityPolicy,
        budgetPolicy: budgetPolicy ?? this.budgetPolicy,
      );
}

String? _idOrNull(dynamic value) {
  final String text = stringValue(value);
  return text.isEmpty ? null : text;
}

int _revisionInt(dynamic value) =>
    value is num ? value.toInt() : int.tryParse('${value ?? ''}') ?? 0;
