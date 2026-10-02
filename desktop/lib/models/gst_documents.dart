import 'entities.dart';

/// Why goods leave on a delivery note (backlog 77.1): the six reasons the
/// server accepts, in the order the editor offers them. The first is the
/// default.
const List<(String, String)> challanReasons = <(String, String)>[
  ('SALE', 'Sale'),
  ('ROUTE_SALE', 'Van or route sale'),
  ('ON_APPROVAL', 'Supply on approval'),
  ('QUANTITY_UNKNOWN', 'Quantity not known at removal'),
  ('JOB_WORK', 'Job work'),
  ('OTHER', 'Other'),
];

/// The words for a reason code, or the code itself when it is not known.
String challanReasonLabel(String code) {
  for (final (String value, String label) in challanReasons) {
    if (value == code) return label;
  }
  return code;
}

/// What the server says about dispatching one delivery note before it has an
/// invoice (`GET /delivery-notes/{id}/dispatch-check`).
class DispatchCheck {
  const DispatchCheck({
    required this.enforcement,
    required this.message,
    required this.wouldBlock,
  });

  /// OFF, WARN or BLOCK.
  final String enforcement;

  /// Non-null when the note is a sale that has no invoice yet.
  final String? message;
  final bool wouldBlock;

  factory DispatchCheck.fromJson(Json json) {
    final String text = stringValue(json['message']);
    return DispatchCheck(
      enforcement: stringValue(json['enforcement']),
      message: text.isEmpty ? null : text,
      wouldBlock: boolValue(json['would_block']),
    );
  }
}

/// The firm's GST document policy (backlog 77.1): when e-invoicing and the
/// 30-day reporting limit start to apply, and what dispatching a sale before
/// its invoice does.
class GstComplianceSettings {
  const GstComplianceSettings({
    required this.einvoiceApplicableFrom,
    required this.thirtyDayRuleFrom,
    required this.dispatchWithoutInvoice,
    required this.routeSaleNeedsInvoice,
    this.isConfigured = false,
    this.itcClaimBasis = 'ALL',
    this.gstr2bTolerance = '1.00',
    this.ewayBillLimit = '50000',
    this.rule37Mode = 'REPORT',
  });

  /// ISO dates (`2026-04-01`), or null when not set.
  final String? einvoiceApplicableFrom;
  final String? thirtyDayRuleFrom;

  /// OFF, WARN or BLOCK.
  final String dispatchWithoutInvoice;
  final bool routeSaleNeedsInvoice;

  /// False while the firm is still on the platform default.
  final bool isConfigured;

  /// ALL, or MATCHED_ONLY: claim only bills GSTR-2B shows (backlog 78 row 3).
  final String itcClaimBasis;

  /// Rupees a bill may differ from 2B and still count as matched.
  final String gstr2bTolerance;

  /// Above this a consignment needs an e-way bill (backlog 77 row 10).
  final String ewayBillLimit;

  /// OFF, REPORT or POST: what happens to credit on bills unpaid 180 days
  /// (backlog 78 row 4).
  final String rule37Mode;

  factory GstComplianceSettings.fromJson(Json json) {
    String? date(dynamic value) {
      final String text = stringValue(value);
      return text.isEmpty ? null : text;
    }

    return GstComplianceSettings(
      einvoiceApplicableFrom: date(json['einvoice_applicable_from']),
      thirtyDayRuleFrom: date(json['thirty_day_rule_from']),
      dispatchWithoutInvoice: stringValue(json['dispatch_without_invoice']),
      routeSaleNeedsInvoice: boolValue(json['route_sale_needs_invoice']),
      isConfigured: boolValue(json['is_configured']),
      itcClaimBasis: stringValue(json['itc_claim_basis']).isEmpty
          ? 'ALL'
          : stringValue(json['itc_claim_basis']),
      gstr2bTolerance: stringValue(json['gstr2b_tolerance']).isEmpty
          ? '1.00'
          : stringValue(json['gstr2b_tolerance']),
      ewayBillLimit: stringValue(json['eway_bill_limit']).isEmpty
          ? '50000'
          : stringValue(json['eway_bill_limit']),
      rule37Mode: stringValue(json['rule37_mode']).isEmpty
          ? 'REPORT'
          : stringValue(json['rule37_mode']),
    );
  }

  /// Exactly the eight keys the server declares; it refuses any other.
  Json toJson() => <String, dynamic>{
        'einvoice_applicable_from': einvoiceApplicableFrom,
        'thirty_day_rule_from': thirtyDayRuleFrom,
        'dispatch_without_invoice': dispatchWithoutInvoice,
        'route_sale_needs_invoice': routeSaleNeedsInvoice,
        'itc_claim_basis': itcClaimBasis,
        'gstr2b_tolerance': gstr2bTolerance,
        'eway_bill_limit': ewayBillLimit,
        'rule37_mode': rule37Mode,
      };
}
