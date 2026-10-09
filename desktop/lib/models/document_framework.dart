import 'entities.dart';

/// What a document header shows for a record it knows only by [id]: the name
/// [lookup] gives, or nothing. A lookup that does not know the id hands it
/// back, and an id is never shown to a person (D-UI-87): a blank field says
/// "not known" honestly, a UUID says nothing.
String namedOrBlank(String Function(String id)? lookup, String id) {
  if (lookup == null || id.isEmpty) return '';
  final String name = lookup(id);
  return name == id ? '' : name;
}

/// Who raised a document, read from its [history]: the actor of the event
/// that created it. Empty when the history does not say.
String historyCreatedBy(List<DocumentTimelineSnapshot> history) {
  for (final DocumentTimelineSnapshot entry in history) {
    if (_historyAction(entry) == 'CREATED') return entry.actor;
  }
  return '';
}

/// An event's action as one upper-case word: a purchase order's own history
/// writes `purchase.approved` where the shared history writes `APPROVED`.
String _historyAction(DocumentTimelineSnapshot entry) =>
    entry.action.trim().split('.').last.toUpperCase();

/// Who approved a document, read from its [history]: the actor of the latest
/// event that approved it -- or completed or posted it, which is what
/// approval is called on a document with no separate approve step (a goods
/// receipt). Empty while nobody has, and empty again once an approval is
/// withdrawn.
String historyApprovedBy(List<DocumentTimelineSnapshot> history) {
  DocumentTimelineSnapshot? latest;
  for (final DocumentTimelineSnapshot entry in history) {
    final String action = _historyAction(entry);
    if (!_approvingActions.contains(action) &&
        action != _approvalWithdrawn) {
      continue;
    }
    if (latest == null || entry.occurredAt.compareTo(latest.occurredAt) > 0) {
      latest = entry;
    }
  }
  if (latest == null || _historyAction(latest) == _approvalWithdrawn) {
    return '';
  }
  return latest.actor;
}

const String _approvalWithdrawn = 'APPROVAL_WITHDRAWN';

const Set<String> _approvingActions = <String>{
  'APPROVED',
  'COMPLETED',
  'POSTED',
};

class DocumentHeaderSnapshot {
  const DocumentHeaderSnapshot({
    required this.documentTypeCode,
    required this.documentTypeName,
    required this.documentNumber,
    required this.documentDate,
    required this.status,
    this.party = '',
    this.partyLabel = 'Party',
    this.reference = '',
    this.coupon = '',
    this.branch = '',
    this.warehouse = '',
    this.firm = '',
    this.currency = '',
    this.exchangeRate = '',
    this.remarks = '',
    this.createdBy = '',
    this.approvedBy = '',
    this.more = const <String, String>{},
  });

  final String documentTypeCode;
  final String documentTypeName;
  final String documentNumber;
  final String documentDate;
  //: The other party -- the customer on a sale, the vendor on a purchase --
  //: named for display. Empty on documents not yet wired to carry it, and
  //: the header hides the field when it is empty.
  final String party;
  final String partyLabel;
  final String reference;

  /// The coupon presented on the document, where its type takes one.
  final String coupon;
  final String branch;
  final String warehouse;
  final String firm;
  final String currency;
  final String exchangeRate;
  final String status;
  final String remarks;
  final String createdBy;
  final String approvedBy;

  /// What only this kind of document records, by the label it is shown
  /// under -- a goods receipt's e-way bill, say. One with nothing in it is
  /// not shown.
  final Map<String, String> more;

  factory DocumentHeaderSnapshot.fromJson(Json json) => DocumentHeaderSnapshot(
        documentTypeCode: stringValue(json['document_type_code']),
        documentTypeName: stringValue(json['document_type_name']),
        documentNumber: stringValue(json['document_number']),
        documentDate: stringValue(json['document_date']),
        party: stringValue(json['party']),
        partyLabel: stringValue(json['party_label']).isEmpty
            ? 'Party'
            : stringValue(json['party_label']),
        reference: stringValue(json['reference']),
        coupon: stringValue(json['coupon']),
        branch: stringValue(json['branch']),
        warehouse: stringValue(json['warehouse']),
        firm: stringValue(json['firm']),
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
    this.discountPercent = '',
    this.taxProfile = '',
    this.amount = '',
    this.netAmount = '',
    this.remarks = '',
    this.itcEligibility = '',
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

  /// The rate the server resolved, beside the amount it came to. Empty or
  /// zero where no rate applied.
  final String discountPercent;
  final String taxProfile;
  final String amount;
  final String netAmount;
  final String remarks;

  /// A purchase bill line's resolved input credit status; empty on every
  /// document that has none. Only a line that is not ELIGIBLE is flagged.
  final String itcEligibility;

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
        discountPercent: stringValue(json['discount_percent']),
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
        // The server sends the person as `actor_id`. Only `actor` was read,
        // so no timeline row and no header could say who (D-UI-88).
        actor: stringValue(json['actor']).isNotEmpty
            ? stringValue(json['actor'])
            : stringValue(json['actor_id']),
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
/// A kind of document a numbering series can be attached to.
///
/// The series is what a firm names its own documents; the type is the
/// platform's definition of what kind of document it is. Only the first is
/// editable from the firm's side, which is why this model carries nothing but
/// what a picker needs.
class DocumentTypeRecord {
  const DocumentTypeRecord({
    required this.id,
    required this.code,
    required this.name,
  });

  final String id;
  final String code;
  final String name;

  factory DocumentTypeRecord.fromJson(Json json) => DocumentTypeRecord(
        id: stringValue(json['id']),
        code: stringValue(json['code']),
        name: stringValue(json['name']),
      );
}

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
    this.shortFinancialYear = false,
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

  /// The year prints as 26-27 rather than 2026-2027 (GST-2).
  final bool shortFinancialYear;
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
      if (includeFinancialYear)
        shortFinancialYear ? 'year (26-27)' : 'financial year',
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
        shortFinancialYear: boolValue(json['short_financial_year']),
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
