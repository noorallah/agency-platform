import 'entities.dart';

class DocumentHeaderSnapshot {
  const DocumentHeaderSnapshot({
    required this.documentTypeCode,
    required this.documentTypeName,
    required this.documentNumber,
    required this.documentDate,
    required this.status,
    this.reference = '',
    this.branch = '',
    this.warehouse = '',
    this.firm = '',
    this.businessProfile = '',
    this.currency = '',
    this.exchangeRate = '',
    this.remarks = '',
    this.createdBy = '',
    this.approvedBy = '',
  });

  final String documentTypeCode;
  final String documentTypeName;
  final String documentNumber;
  final String documentDate;
  final String reference;
  final String branch;
  final String warehouse;
  final String firm;
  final String businessProfile;
  final String currency;
  final String exchangeRate;
  final String status;
  final String remarks;
  final String createdBy;
  final String approvedBy;

  factory DocumentHeaderSnapshot.fromJson(Json json) => DocumentHeaderSnapshot(
        documentTypeCode: stringValue(json['document_type_code']),
        documentTypeName: stringValue(json['document_type_name']),
        documentNumber: stringValue(json['document_number']),
        documentDate: stringValue(json['document_date']),
        reference: stringValue(json['reference']),
        branch: stringValue(json['branch']),
        warehouse: stringValue(json['warehouse']),
        firm: stringValue(json['firm']),
        businessProfile: stringValue(json['business_profile']),
        currency: stringValue(json['currency']),
        exchangeRate: stringValue(json['exchange_rate']),
        status: stringValue(json['status']),
        remarks: stringValue(json['remarks']),
        createdBy: stringValue(json['created_by']),
        approvedBy: stringValue(json['approved_by']),
      );
}

class DocumentLineSnapshot {
  const DocumentLineSnapshot({
    required this.lineNumber,
    this.product = '',
    this.description = '',
    this.uom = '',
    this.packaging = '',
    this.quantity = '',
    this.freeQuantity = '',
    this.unitPrice = '',
    this.discount = '',
    this.taxProfile = '',
    this.amount = '',
    this.netAmount = '',
    this.remarks = '',
  });

  final int lineNumber;
  final String product;
  final String description;
  final String uom;
  final String packaging;
  final String quantity;
  final String freeQuantity;
  final String unitPrice;
  final String discount;
  final String taxProfile;
  final String amount;
  final String netAmount;
  final String remarks;

  factory DocumentLineSnapshot.fromJson(Json json) => DocumentLineSnapshot(
        lineNumber: (json['line_number'] as num?)?.toInt() ?? 0,
        product: stringValue(json['product']),
        description: stringValue(json['description']),
        uom: stringValue(json['uom']),
        packaging: stringValue(json['packaging']),
        quantity: stringValue(json['quantity']),
        freeQuantity: stringValue(json['free_quantity']),
        unitPrice: stringValue(json['unit_price']),
        discount: stringValue(json['discount']),
        taxProfile: stringValue(json['tax_profile']),
        amount: stringValue(json['amount']),
        netAmount: stringValue(json['net_amount']),
        remarks: stringValue(json['remarks']),
      );
}

class DocumentTotalsSnapshot {
  const DocumentTotalsSnapshot({
    required this.subtotal,
    required this.discount,
    required this.tax,
    required this.charges,
    required this.roundOff,
    required this.grandTotal,
  });

  final String subtotal;
  final String discount;
  final String tax;
  final String charges;
  final String roundOff;
  final String grandTotal;

  factory DocumentTotalsSnapshot.fromJson(Json json) => DocumentTotalsSnapshot(
        subtotal: stringValue(json['subtotal']),
        discount: stringValue(json['discount']),
        tax: stringValue(json['tax']),
        charges: stringValue(json['charges']),
        roundOff: stringValue(json['round_off']),
        grandTotal: stringValue(json['grand_total']),
      );
}

class DocumentTimelineSnapshot {
  const DocumentTimelineSnapshot({
    required this.occurredAt,
    required this.action,
    this.fromState = '',
    this.toState = '',
    this.actor = '',
    this.remarks = '',
    this.details = const <String, dynamic>{},
  });

  final String occurredAt;
  final String action;
  final String fromState;
  final String toState;
  final String actor;
  final String remarks;
  final Json details;

  factory DocumentTimelineSnapshot.fromJson(Json json) =>
      DocumentTimelineSnapshot(
        occurredAt: stringValue(json['occurred_at']),
        action: stringValue(json['action']),
        fromState: stringValue(json['from_state']),
        toState: stringValue(json['to_state']),
        actor: stringValue(json['actor']),
        remarks: stringValue(json['remarks']),
        details: json['details'] is Map
            ? Map<String, dynamic>.from(json['details'] as Map)
            : const <String, dynamic>{},
      );
}

/// How one document type's numbers are built.
///
/// The rule behind every `SI-2026-2027-000008` in the system. It had endpoints
/// and no screen, so "what will the next invoice be called" was a question
/// only the database could answer.
class NumberingRule {
  const NumberingRule({
    required this.id,
    required this.documentTypeId,
    required this.code,
    required this.name,
    required this.prefix,
    required this.suffix,
    required this.separator,
    required this.includeFinancialYear,
    required this.includeBranchCode,
    required this.includeCompanyCode,
    required this.sequencePadding,
    required this.nextSequence,
    required this.autoReset,
    required this.manualAllowed,
    required this.isDefault,
    required this.isActive,
  });

  final String id;
  final String documentTypeId;
  final String code;
  final String name;
  final String prefix;
  final String suffix;
  final String separator;
  final bool includeFinancialYear;
  final bool includeBranchCode;
  final bool includeCompanyCode;
  final int sequencePadding;

  /// The number the next document will take. The single most useful figure
  /// here, and the one nobody could see.
  final int nextSequence;
  final bool autoReset;
  final bool manualAllowed;
  final bool isDefault;
  final bool isActive;

  /// What the rule says, in words rather than in flags.
  String get shape {
    final List<String> parts = [
      if (prefix.isNotEmpty) prefix,
      if (includeCompanyCode) 'company',
      if (includeBranchCode) 'branch',
      if (includeFinancialYear) 'financial year',
      '#' * (sequencePadding == 0 ? 6 : sequencePadding),
      if (suffix.isNotEmpty) suffix,
    ];
    return parts.join(separator.isEmpty ? '-' : separator);
  }

  factory NumberingRule.fromJson(Json json) => NumberingRule(
        id: stringValue(json['id']),
        documentTypeId: stringValue(json['document_type_id']),
        code: stringValue(json['code']),
        name: stringValue(json['name']),
        prefix: stringValue(json['prefix']),
        suffix: stringValue(json['suffix']),
        separator: stringValue(json['separator']),
        includeFinancialYear: boolValue(json['include_financial_year']),
        includeBranchCode: boolValue(json['include_branch_code']),
        includeCompanyCode: boolValue(json['include_company_code']),
        sequencePadding: (json['sequence_padding'] as num?)?.toInt() ?? 0,
        nextSequence: (json['next_sequence'] as num?)?.toInt() ?? 0,
        autoReset: boolValue(json['auto_reset']),
        manualAllowed: boolValue(json['manual_allowed']),
        isDefault: boolValue(json['is_default']),
        isActive: boolValue(json['is_active']),
      );
}
