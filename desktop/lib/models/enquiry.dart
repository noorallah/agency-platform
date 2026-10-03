import 'entities.dart';

/// Why an enquiry was lost, as the server spells it (SEL-10).
const List<(String, String)> enquiryLostReasons = [
  ('PRICE', 'Price'),
  ('COMPETITOR', 'Went to a competitor'),
  ('NO_STOCK', 'No stock'),
  ('NO_RESPONSE', 'No response'),
  ('NOT_NEEDED', 'No longer needed'),
  ('OTHER', 'Other'),
];

/// Where an enquiry came from, as the server spells it.
const List<(String, String)> enquirySources = [
  ('WALK_IN', 'Walk-in'),
  ('PHONE', 'Phone'),
  ('WHATSAPP', 'WhatsApp'),
  ('REFERRAL', 'Referral'),
  ('EXHIBITION', 'Exhibition'),
  ('WEBSITE', 'Website'),
  ('OTHER', 'Other'),
];

String? _nullable(dynamic raw) {
  final String text = stringValue(raw);
  return text.isEmpty ? null : text;
}

String _number(dynamic raw) =>
    stringValue(raw).isEmpty ? '0' : stringValue(raw);

/// One line of what the prospect asked about.
class EnquiryLine {
  const EnquiryLine({
    this.lineNumber = 0,
    this.productId,
    this.productName = '',
    this.description = '',
    this.quantity = '0',
    this.expectedPrice,
  });

  final int lineNumber;
  final String? productId;
  final String productName;
  final String description;
  final String quantity;
  final String? expectedPrice;

  /// What to show for the line: the product, else what was typed.
  String get label =>
      productName.isNotEmpty ? productName : description;

  factory EnquiryLine.fromJson(Json json) => EnquiryLine(
        lineNumber: (json['line_number'] as num?)?.toInt() ?? 0,
        productId: _nullable(json['product_id']),
        productName: stringValue(json['product_name']),
        description: stringValue(json['description']),
        quantity: _number(json['quantity']),
        expectedPrice: _nullable(json['expected_price']),
      );
}

/// One contact logged against an enquiry.
class EnquiryFollowUp {
  const EnquiryFollowUp({
    required this.id,
    required this.followedOn,
    this.note = '',
    this.nextFollowUpOn,
  });

  final String id;
  final String followedOn;
  final String note;
  final String? nextFollowUpOn;

  factory EnquiryFollowUp.fromJson(Json json) => EnquiryFollowUp(
        id: stringValue(json['id']),
        followedOn: stringValue(json['followed_on']),
        note: stringValue(json['note']),
        nextFollowUpOn: _nullable(json['next_follow_up_on']),
      );
}

/// An enquiry or lead before the quotation (SEL-10).
class Enquiry {
  const Enquiry({
    required this.id,
    required this.enquiryNumber,
    required this.enquiryDate,
    this.branchId,
    this.customerId,
    this.customerName = '',
    this.prospectName = '',
    this.prospectCompany = '',
    this.prospectPhone = '',
    this.prospectEmail = '',
    this.prospectCity = '',
    this.source = 'OTHER',
    this.salesmanId,
    this.expectedValue = '0',
    this.expectedCloseOn,
    this.nextFollowUpOn,
    this.status = 'OPEN',
    this.lostReason,
    this.lostRemarks = '',
    this.quotationId,
    this.remarks = '',
    this.version = 0,
    this.lines = const [],
    this.followUps = const [],
  });

  final String id;
  final String enquiryNumber;
  final String enquiryDate;
  final String? branchId;
  final String? customerId;
  final String customerName;
  final String prospectName;
  final String prospectCompany;
  final String prospectPhone;
  final String prospectEmail;
  final String prospectCity;
  final String source;
  final String? salesmanId;
  final String expectedValue;
  final String? expectedCloseOn;
  final String? nextFollowUpOn;

  /// `OPEN`, `QUOTED`, `WON` or `LOST`.
  final String status;
  final String? lostReason;
  final String lostRemarks;
  final String? quotationId;
  final String remarks;
  final int version;
  final List<EnquiryLine> lines;
  final List<EnquiryFollowUp> followUps;

  bool get isOpen => status == 'OPEN';

  /// Still being worked: neither won nor lost.
  bool get isLive => status == 'OPEN' || status == 'QUOTED';

  /// The existing customer, else the prospect's company, else their name.
  String get buyer {
    if (customerName.isNotEmpty) return customerName;
    if (prospectCompany.isNotEmpty) return prospectCompany;
    return prospectName;
  }

  factory Enquiry.fromJson(Json json) => Enquiry(
        id: stringValue(json['id']),
        enquiryNumber: stringValue(json['enquiry_number']),
        enquiryDate: stringValue(json['enquiry_date']),
        branchId: _nullable(json['branch_id']),
        customerId: _nullable(json['customer_id']),
        customerName: stringValue(json['customer_name']),
        prospectName: stringValue(json['prospect_name']),
        prospectCompany: stringValue(json['prospect_company']),
        prospectPhone: stringValue(json['prospect_phone']),
        prospectEmail: stringValue(json['prospect_email']),
        prospectCity: stringValue(json['prospect_city']),
        source: stringValue(json['source']),
        salesmanId: _nullable(json['salesman_id']),
        expectedValue: _number(json['expected_value']),
        expectedCloseOn: _nullable(json['expected_close_on']),
        nextFollowUpOn: _nullable(json['next_follow_up_on']),
        status: stringValue(json['status']),
        lostReason: _nullable(json['lost_reason']),
        lostRemarks: stringValue(json['lost_remarks']),
        quotationId: _nullable(json['quotation_id']),
        remarks: stringValue(json['remarks']),
        version: (json['version'] as num?)?.toInt() ?? 0,
        lines: json['lines'] is List
            ? [
                for (final dynamic row in json['lines'] as List)
                  if (row is Map)
                    EnquiryLine.fromJson(Map<String, dynamic>.from(row)),
              ]
            : const <EnquiryLine>[],
        followUps: json['follow_ups'] is List
            ? [
                for (final dynamic row in json['follow_ups'] as List)
                  if (row is Map)
                    EnquiryFollowUp.fromJson(Map<String, dynamic>.from(row)),
              ]
            : const <EnquiryFollowUp>[],
      );
}

/// One row of the lost-enquiries report: a reason, how many, how much.
class EnquiryLostRow {
  const EnquiryLostRow({
    required this.reason,
    required this.count,
    required this.expectedValue,
  });

  final String reason;
  final int count;
  final String expectedValue;

  factory EnquiryLostRow.fromJson(Json json) => EnquiryLostRow(
        reason: stringValue(json['reason']),
        count: (json['count'] as num?)?.toInt() ?? 0,
        expectedValue: _number(json['expected_value']),
      );
}
