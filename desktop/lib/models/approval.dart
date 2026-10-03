import 'entities.dart';

/// The four documents that can carry a chain of sign-offs (PLT-1), as the
/// server names them, with the words a person reads.
const List<(String, String)> approvalDocumentTypes = [
  ('SALES_ORDER', 'Sales order'),
  ('SALES_INVOICE', 'Sales invoice'),
  ('PURCHASE_ORDER', 'Purchase order'),
  ('PURCHASE_INVOICE', 'Purchase invoice'),
];

/// The label for a server document type, or the code when it is not known.
String approvalTypeLabel(String code) {
  for (final (String value, String label) in approvalDocumentTypes) {
    if (value == code) return label;
  }
  return code;
}

/// One level a document of a type must be signed at once its amount reaches
/// [minAmount]. Several rows at one level are alternatives.
class ApprovalRule {
  const ApprovalRule({
    required this.documentType,
    required this.level,
    required this.minAmount,
    required this.roleCode,
    this.id = '',
  });

  factory ApprovalRule.fromJson(Json json) => ApprovalRule(
        id: stringValue(json['id']),
        documentType: stringValue(json['document_type']),
        level: (json['level'] as num?)?.toInt() ?? 1,
        minAmount: stringValue(json['min_amount']),
        roleCode: stringValue(json['role_code']),
      );

  final String id;
  final String documentType;
  final int level;
  final String minAmount;
  final String roleCode;
}

/// One level of a document's chain: the roles that may sign it and, once
/// signed, who did and when.
class ApprovalStep {
  const ApprovalStep({
    required this.level,
    required this.roles,
    this.signedBy,
    this.signedAt,
  });

  factory ApprovalStep.fromJson(Json json) => ApprovalStep(
        level: (json['level'] as num?)?.toInt() ?? 1,
        roles: [
          for (final dynamic role in (json['roles'] as List?) ?? const [])
            stringValue(role),
        ],
        signedBy: json['signed_by'] as String?,
        signedAt: json['signed_at'] as String?,
      );

  final int level;
  final List<String> roles;
  final String? signedBy;
  final String? signedAt;

  bool get isSigned => signedBy != null;
}

/// Where a document stands in its chain of sign-offs.
class ApprovalStatus {
  const ApprovalStatus({
    required this.documentType,
    required this.documentId,
    required this.documentNumber,
    required this.amount,
    required this.status,
    required this.steps,
    this.nextLevel,
    this.rejectedReason,
    this.rejectedAt,
  });

  factory ApprovalStatus.fromJson(Json json) => ApprovalStatus(
        documentType: stringValue(json['document_type']),
        documentId: stringValue(json['document_id']),
        documentNumber: stringValue(json['document_number']),
        amount: stringValue(json['amount']),
        status: stringValue(json['status']),
        steps: [
          for (final dynamic step in (json['steps'] as List?) ?? const [])
            if (step is Map) ApprovalStep.fromJson(Json.from(step)),
        ],
        nextLevel: (json['next_level'] as num?)?.toInt(),
        rejectedReason: json['rejected_reason'] as String?,
        rejectedAt: json['rejected_at'] as String?,
      );

  final String documentType;
  final String documentId;
  final String documentNumber;
  final String amount;
  final String status;
  final List<ApprovalStep> steps;
  final int? nextLevel;
  final String? rejectedReason;
  final String? rejectedAt;

  /// "L1 signed, L2 awaiting FINANCE": one phrase for the grid.
  String get summary => [
        for (final ApprovalStep step in steps)
          step.isSigned
              ? 'L${step.level} signed'
              : 'L${step.level} awaiting ${step.roles.join(' or ')}',
      ].join(', ');
}
