import 'entities.dart';

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
  });

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
      );

  Json toWriteJson() => {
        'product_id': productId,
        if (description.isNotEmpty) 'description': description,
        if (vendorProductCode.isNotEmpty)
          'vendor_product_code': vendorProductCode,
        if (purchaseUomId.isNotEmpty) 'purchase_uom_id': purchaseUomId,
        if (inventoryUomId.isNotEmpty) 'inventory_uom_id': inventoryUomId,
        'ordered_quantity': orderedQuantity.isEmpty ? '0' : orderedQuantity,
        'free_quantity': freeQuantity.isEmpty ? '0' : freeQuantity,
        'unit_price': unitPrice.isEmpty ? '0' : unitPrice,
        'discount_percent': discountPercent.isEmpty ? '0' : discountPercent,
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
    required this.isDeleted,
    required this.createdAt,
    required this.updatedAt,
    required this.lines,
    required this.deliverySchedules,
    required this.attachments,
    required this.notes,
  });

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
  }) =>
      PurchaseOrder(
        id: id ?? this.id,
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
        if (currencyCode.isNotEmpty) 'currency_code': currencyCode,
        if (exchangeRate.isNotEmpty) 'exchange_rate': exchangeRate,
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
    return body;
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
