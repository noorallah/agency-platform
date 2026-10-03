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
    this.paidFromDeposits = '0',
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

  /// Cash already deposited by PMT-06 for this head (quarterly filers).
  final String paidFromDeposits;

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
        paidFromDeposits: json['paid_from_deposits'] == null
            ? '0'
            : stringValue(json['paid_from_deposits']),
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
    this.periodFrom,
    this.depositsTotal = '0',
    this.bankTotal = '',
  });

  final String returnPeriod;
  final String dueDate;

  /// First day covered when the settlement spans a quarter, else null.
  final String? periodFrom;

  /// Paid from PMT-06 deposits, and what is left to pay from the bank.
  final String depositsTotal;
  final String bankTotal;

  bool get hasDeposits => (double.tryParse(depositsTotal) ?? 0) > 0;

  /// The quarter covered, e.g. "Jul-Sep 2026", when it is not one month.
  String? get quarterLabel {
    final String? from = periodFrom;
    if (from == null || from.length < 7 || returnPeriod.length < 7) return null;
    if (from.substring(0, 7) == returnPeriod.substring(0, 7)) return null;
    const List<String> names = [
      'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
      'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
    ];
    final int a = (int.tryParse(from.substring(5, 7)) ?? 1) - 1;
    final int b = (int.tryParse(returnPeriod.substring(5, 7)) ?? 1) - 1;
    if (a < 0 || a > 11 || b < 0 || b > 11) return null;
    return '${names[a]}-${names[b]} ${returnPeriod.substring(0, 4)}';
  }

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
      periodFrom:
          d['period_from'] == null ? null : stringValue(d['period_from']),
      depositsTotal: d['deposits_total'] == null
          ? '0'
          : stringValue(d['deposits_total']),
      bankTotal:
          d['bank_total'] == null ? '' : stringValue(d['bank_total']),
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
