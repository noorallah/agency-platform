import 'entities.dart';

/// One step of a customer rebate's ladder: from [threshold] of turnover the
/// firm gives [ratePercent] back on all of it (SG-9).
class CustomerRebateSlab {
  const CustomerRebateSlab({
    required this.threshold,
    required this.ratePercent,
    this.id = '',
    this.lineNumber = 0,
  });

  final String id;
  final int lineNumber;
  final String threshold;
  final String ratePercent;

  factory CustomerRebateSlab.fromJson(Json json) => CustomerRebateSlab(
        id: stringValue(json['id']),
        lineNumber: (json['line_number'] as num?)?.toInt() ?? 0,
        threshold: stringValue(json['threshold']),
        ratePercent: stringValue(json['rate_percent']),
      );
}

/// A turnover rebate the firm gives one customer, or one customer group, for a
/// period, as the register shows it: how far sales have got up the ladder and
/// what is earned so far.
class CustomerRebate {
  const CustomerRebate({
    required this.id,
    required this.code,
    required this.name,
    required this.periodFrom,
    required this.periodTo,
    required this.status,
    this.customerId = '',
    this.customerName = '',
    this.customerGroupId = '',
    this.customerGroupName = '',
    this.agreedBeforeSale = false,
    this.notes = '',
    this.slabs = const <CustomerRebateSlab>[],
    this.turnover = '0',
    this.ratePercent = '0',
    this.earned = '0',
    this.nextThreshold = '',
    this.nextRatePercent = '',
    this.toNext = '',
    this.accruedAmount = '',
    this.accrualJournalId = '',
    this.accruedAt = '',
    this.settled = '0',
    this.toSettle = '0',
    this.version = 0,
  });

  final String id;
  final String customerId;
  final String customerName;
  final String customerGroupId;
  final String customerGroupName;
  final String code;
  final String name;
  final String periodFrom;
  final String periodTo;

  /// `ACTIVE`, `ACCRUED` or `CANCELLED`.
  final String status;

  /// Whether it was promised before the sales it rewards. Only informs the
  /// firm's CA when deciding on a GST credit note.
  final bool agreedBeforeSale;
  final String notes;
  final List<CustomerRebateSlab> slabs;
  final String turnover;
  final String ratePercent;
  final String earned;
  final String nextThreshold;
  final String nextRatePercent;
  final String toNext;
  final String accruedAmount;
  final String accrualJournalId;
  final String accruedAt;
  final String settled;
  final String toSettle;
  final int version;

  bool get isActive => status == 'ACTIVE';
  bool get isAccrued => status == 'ACCRUED';
  bool get isGroup => customerGroupId.isNotEmpty;

  /// The customer's name, or the group's.
  String get partyName => isGroup ? customerGroupName : customerName;

  /// What is left to take off the customer's account.
  double get toSettleAmount => double.tryParse(toSettle) ?? 0;

  /// Accruing is refused until the period is over; the server decides, this
  /// only keeps the button honest. [today] is a date, `YYYY-MM-DD`.
  bool periodEnded(String today) =>
      periodTo.isNotEmpty && periodTo.compareTo(today) < 0;

  factory CustomerRebate.fromJson(Json json) => CustomerRebate(
        id: stringValue(json['id']),
        customerId: stringValue(json['customer_id']),
        customerName: stringValue(json['customer_name']),
        customerGroupId: stringValue(json['customer_group_id']),
        customerGroupName: stringValue(json['customer_group_name']),
        code: stringValue(json['code']),
        name: stringValue(json['name']),
        periodFrom: stringValue(json['period_from']),
        periodTo: stringValue(json['period_to']),
        status: stringValue(json['status']),
        agreedBeforeSale: json['agreed_before_sale'] == true,
        notes: stringValue(json['notes']),
        slabs: [
          for (final dynamic row
              in json['slabs'] is List ? json['slabs'] as List : const [])
            if (row is Map)
              CustomerRebateSlab.fromJson(Map<String, dynamic>.from(row)),
        ],
        turnover: _orZero(json['turnover']),
        ratePercent: _orZero(json['rate_percent']),
        earned: _orZero(json['earned']),
        nextThreshold: stringValue(json['next_threshold']),
        nextRatePercent: stringValue(json['next_rate_percent']),
        toNext: stringValue(json['to_next']),
        accruedAmount: stringValue(json['accrued_amount']),
        accrualJournalId: stringValue(json['accrual_journal_id']),
        accruedAt: stringValue(json['accrued_at']),
        settled: _orZero(json['settled']),
        toSettle: _orZero(json['to_settle']),
        version: (json['version'] as num?)?.toInt() ?? 0,
      );
}

/// One customer's part of an agreement's turnover, by kind of document.
class CustomerRebateTurnoverRow {
  const CustomerRebateTurnoverRow({
    required this.customerId,
    required this.customerName,
    this.invoiced = '0',
    this.returned = '0',
    this.creditNotes = '0',
    this.debitNotes = '0',
    this.turnover = '0',
  });

  final String customerId;
  final String customerName;
  final String invoiced;
  final String returned;
  final String creditNotes;
  final String debitNotes;
  final String turnover;

  factory CustomerRebateTurnoverRow.fromJson(Json json) =>
      CustomerRebateTurnoverRow(
        customerId: stringValue(json['customer_id']),
        customerName: stringValue(json['customer_name']),
        invoiced: _orZero(json['invoiced']),
        returned: _orZero(json['returned']),
        creditNotes: _orZero(json['credit_notes']),
        debitNotes: _orZero(json['debit_notes']),
        turnover: _orZero(json['turnover']),
      );
}

/// One settlement raised against the agreement.
class CustomerRebateSettlementRow {
  const CustomerRebateSettlementRow({
    required this.adjustmentNumber,
    required this.adjustmentDate,
    required this.customerName,
    required this.amount,
    required this.status,
  });

  final String adjustmentNumber;
  final String adjustmentDate;
  final String customerName;
  final String amount;
  final String status;

  factory CustomerRebateSettlementRow.fromJson(Json json) =>
      CustomerRebateSettlementRow(
        adjustmentNumber: stringValue(json['adjustment_number']),
        adjustmentDate: stringValue(json['adjustment_date']),
        customerName: stringValue(json['customer_name']),
        amount: _orZero(json['amount']),
        status: stringValue(json['status']),
      );
}

/// What an agreement's turnover is made of, the settlements, and the note on
/// GST for the firm's CA.
class CustomerRebateStatement {
  const CustomerRebateStatement({
    required this.agreement,
    this.customers = const <CustomerRebateTurnoverRow>[],
    this.invoiced = '0',
    this.returned = '0',
    this.creditNotes = '0',
    this.debitNotes = '0',
    this.turnoverToday = '0',
    this.settlements = const <CustomerRebateSettlementRow>[],
    this.gstNote = '',
  });

  final CustomerRebate agreement;
  final List<CustomerRebateTurnoverRow> customers;
  final String invoiced;
  final String returned;
  final String creditNotes;
  final String debitNotes;
  final String turnoverToday;
  final List<CustomerRebateSettlementRow> settlements;
  final String gstNote;

  factory CustomerRebateStatement.fromJson(Json json) =>
      CustomerRebateStatement(
        agreement: CustomerRebate.fromJson(
            Map<String, dynamic>.from(json['agreement'] as Map)),
        customers: [
          for (final dynamic row in json['customers'] is List
              ? json['customers'] as List
              : const [])
            if (row is Map)
              CustomerRebateTurnoverRow.fromJson(
                  Map<String, dynamic>.from(row)),
        ],
        invoiced: _orZero(json['invoiced']),
        returned: _orZero(json['returned']),
        creditNotes: _orZero(json['credit_notes']),
        debitNotes: _orZero(json['debit_notes']),
        turnoverToday: _orZero(json['turnover_today']),
        settlements: [
          for (final dynamic row in json['settlements'] is List
              ? json['settlements'] as List
              : const [])
            if (row is Map)
              CustomerRebateSettlementRow.fromJson(
                  Map<String, dynamic>.from(row)),
        ],
        gstNote: stringValue(json['gst_note']),
      );
}

String _orZero(dynamic value) {
  final String text = stringValue(value);
  return text.isEmpty ? '0' : text;
}
