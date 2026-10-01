import 'entities.dart';

/// One head of a month's GST settlement (backlog 63).
class GstHeadRow {
  const GstHeadRow({
    required this.head,
    required this.liability,
    required this.creditBroughtForward,
    required this.creditAvailable,
    required this.paidByCredit,
    required this.cash,
    required this.creditUsed,
    required this.carriedForward,
    this.reverseCharge = '0',
  });

  final String head;
  final String liability;
  final String creditBroughtForward;
  final String creditAvailable;
  final String paidByCredit;
  final String cash;
  final String creditUsed;
  final String carriedForward;

  /// Reverse charge on inward supplies (3.1(d)): paid in cash only, on top
  /// of [cash], never by credit (backlog 68 row 8).
  final String reverseCharge;

  factory GstHeadRow.fromJson(Json json) => GstHeadRow(
        head: stringValue(json['head']),
        liability: stringValue(json['liability']),
        creditBroughtForward: stringValue(json['credit_brought_forward']),
        creditAvailable: stringValue(json['credit_available']),
        paidByCredit: stringValue(json['paid_by_credit']),
        cash: stringValue(json['cash']),
        creditUsed: stringValue(json['credit_used']),
        carriedForward: stringValue(json['carried_forward']),
        reverseCharge: json['reverse_charge'] == null
            ? '0'
            : stringValue(json['reverse_charge']),
      );
}

List<GstHeadRow> _heads(dynamic value) => [
      for (final dynamic row in value is List ? value : const [])
        if (row is Map) GstHeadRow.fromJson(Map<String, dynamic>.from(row)),
    ];

/// What a month owes, what its credit pays, and what is left in cash.
class GstPaymentPreview {
  const GstPaymentPreview({
    required this.returnPeriod,
    required this.dueDate,
    required this.previousSettled,
    required this.daysLate,
    required this.suggestedInterest,
    required this.cashTotal,
    required this.heads,
    required this.utilisation,
  });

  final String returnPeriod;
  final String dueDate;

  /// False on a firm's first month here: the credit brought forward is what
  /// was stated as the opening credit (the portal's credit ledger).
  final bool previousSettled;
  final int daysLate;
  final String suggestedInterest;
  final String cashTotal;
  final List<GstHeadRow> heads;

  /// "IGST credit -> CGST: 3000.00", the way the portal's table reads.
  final List<String> utilisation;

  factory GstPaymentPreview.fromJson(Json json) {
    final Json d = json.containsKey('data')
        ? Map<String, dynamic>.from(json['data'] as Map)
        : json;
    return GstPaymentPreview(
      returnPeriod: stringValue(d['return_period']),
      dueDate: stringValue(d['due_date']),
      previousSettled: d['previous_settled'] == true,
      daysLate: (d['days_late'] as num?)?.toInt() ?? 0,
      suggestedInterest: stringValue(d['suggested_interest']),
      cashTotal: stringValue(d['cash_total']),
      heads: _heads(d['heads']),
      utilisation: [
        for (final dynamic row
            in d['utilisation'] is List ? d['utilisation'] as List : const [])
          if (row is Map)
            '${row['credit_head']} credit -> ${row['liability_head']}: '
                '${stringValue(row['amount'])}',
      ],
    );
  }
}

/// One recorded month's settlement.
class GstPaymentRecord {
  const GstPaymentRecord({
    required this.id,
    required this.returnPeriod,
    required this.paymentDate,
    required this.status,
    required this.challanCpin,
    required this.cashTotal,
    required this.interestAmount,
    required this.lateFeeAmount,
    required this.heads,
  });

  final String id;
  final String returnPeriod;
  final String paymentDate;
  final String status;
  final String challanCpin;
  final String cashTotal;
  final String interestAmount;
  final String lateFeeAmount;
  final List<GstHeadRow> heads;

  bool get isReversed => status == 'REVERSED';

  factory GstPaymentRecord.fromJson(Json json) {
    final Json d = json.containsKey('data') && json['data'] is Map
        ? Map<String, dynamic>.from(json['data'] as Map)
        : json;
    return GstPaymentRecord(
      id: stringValue(d['id']),
      returnPeriod: stringValue(d['return_period']),
      paymentDate: stringValue(d['payment_date']),
      status: stringValue(d['status']),
      challanCpin: stringValue(d['challan_cpin']),
      cashTotal: stringValue(d['cash_total']),
      interestAmount: stringValue(d['interest_amount']),
      lateFeeAmount: stringValue(d['late_fee_amount']),
      heads: _heads(d['heads']),
    );
  }
}
