import 'entities.dart';

/// One rung of a commission ladder: a band of value, and its rate.
///
/// `toAmount` empty is the open-ended top rung. The rungs must start at zero
/// and meet exactly — the server refuses a ladder with a gap, because a gap is
/// an amount the rule cannot answer for.
class CommissionSlabRecord {
  const CommissionSlabRecord({
    required this.fromAmount,
    required this.percentage,
    this.toAmount = '',
    this.sequence = 1,
  });

  final int sequence;
  final String fromAmount;
  final String toAmount;
  final String percentage;

  String get bandLabel =>
      toAmount.isEmpty ? '$fromAmount and above' : '$fromAmount to $toAmount';

  Json toJson() => <String, dynamic>{
        'from_amount': fromAmount,
        if (toAmount.isNotEmpty) 'to_amount': toAmount,
        'percentage': percentage,
      };

  factory CommissionSlabRecord.fromJson(Json json) => CommissionSlabRecord(
        sequence: (json['sequence'] as num?)?.toInt() ?? 1,
        fromAmount: stringValue(json['from_amount']),
        toAmount: stringValue(json['to_amount']),
        percentage: stringValue(json['percentage']),
      );
}

/// A rate a salesman earns, from a date.
///
/// A rule with no salesman is the firm-wide default: what anybody with no rule
/// of their own earns.
class CommissionRuleRecord {
  const CommissionRuleRecord({
    required this.id,
    required this.percentage,
    required this.effectiveFrom,
    this.version = 0,
    this.salesmanId = '',
    this.salesmanName = '',
    this.effectiveTo = '',
    this.status = 'ACTIVE',
    this.basis = 'COLLECTED',
    this.slabMode = 'MARGINAL',
    this.maxCommissionAmount = '',
    this.slabs = const <CommissionSlabRecord>[],
  });

  final String id;

  /// The version this record was read at, sent back as `If-Match`.
  final int version;

  /// Empty for the firm-wide default, which belongs to nobody in particular.
  final String salesmanId;
  final String salesmanName;

  final String percentage;
  final String effectiveFrom;
  final String effectiveTo;
  final String status;

  /// COLLECTED or INVOICED — what the rate is a percentage *of*.
  final String basis;

  /// MARGINAL or WHOLE_AMOUNT. Only means anything when there are slabs.
  final String slabMode;

  /// The most this rule pays one person for one period. Empty is no ceiling.
  final String maxCommissionAmount;

  /// Empty means the flat [percentage] is the arrangement, which is every
  /// rule agreed before ladders existed.
  final List<CommissionSlabRecord> slabs;

  /// What the rule pays, in one line a person can read off a list.
  String get rateLabel {
    if (slabs.isEmpty) return '$percentage%';
    final String shape =
        slabMode == 'WHOLE_AMOUNT' ? 'whole amount' : 'marginal';
    return '${slabs.length} slabs ($shape)';
  }

  /// Who it applies to, in the words a person would use.
  String get whoLabel =>
      salesmanId.isEmpty ? 'Everyone (default)' : (salesmanName.isEmpty ? salesmanId : salesmanName);

  String get windowLabel =>
      effectiveTo.isEmpty ? 'from $effectiveFrom' : '$effectiveFrom to $effectiveTo';

  factory CommissionRuleRecord.fromJson(Json json) => CommissionRuleRecord(
        id: stringValue(json['id']),
        version: (json['version'] as num?)?.toInt() ?? 0,
        salesmanId: stringValue(json['salesman_id']),
        salesmanName: stringValue(json['salesman_name']),
        percentage: stringValue(json['percentage']),
        effectiveFrom: stringValue(json['effective_from']),
        effectiveTo: stringValue(json['effective_to']),
        status: stringValue(json['status']).isEmpty
            ? 'ACTIVE'
            : stringValue(json['status']),
        basis: stringValue(json['basis']).isEmpty
            ? 'COLLECTED'
            : stringValue(json['basis']),
        slabMode: stringValue(json['slab_mode']).isEmpty
            ? 'MARGINAL'
            : stringValue(json['slab_mode']),
        maxCommissionAmount: stringValue(json['max_commission_amount']),
        slabs: [
          for (final dynamic slab
              in json['slabs'] is List ? json['slabs'] as List : const [])
            if (slab is Map)
              CommissionSlabRecord.fromJson(Map<String, dynamic>.from(slab)),
        ],
      );
}

/// What one salesman collected in a period, and what it earned them.
class CommissionRow {
  const CommissionRow({
    required this.salesmanName,
    required this.collectedAmount,
    required this.commissionAmount,
    required this.invoiceCount,
    this.salesmanId = '',
    this.invoicedAmount = '0.00',
    this.basis = '',
  });

  /// Empty is the Unassigned bucket — money collected against invoices that
  /// carried no salesman. It belongs to nobody and is shown rather than
  /// dropped, because a total that silently omits it cannot be reconciled.
  final String salesmanId;
  final String salesmanName;
  final String collectedAmount;

  /// Approved invoice value raised in the period. Shown whatever the
  /// arrangement, because a firm paying on collections still wants to see what
  /// was billed — and a row on an INVOICED rule would otherwise show an
  /// earning with nothing behind it.
  final String invoicedAmount;

  /// COLLECTED, INVOICED, or MIXED where a rate change moved the arrangement
  /// mid-period. Empty for the Unassigned bucket, which no rule governs.
  final String basis;
  final String commissionAmount;
  final int invoiceCount;

  factory CommissionRow.fromJson(Json json) => CommissionRow(
        salesmanId: stringValue(json['salesman_id']),
        salesmanName: stringValue(json['salesman_name']),
        collectedAmount: stringValue(json['collected_amount']),
        invoicedAmount: stringValue(json['invoiced_amount']),
        basis: stringValue(json['basis']),
        commissionAmount: stringValue(json['commission_amount']),
        invoiceCount: (json['invoice_count'] as num?)?.toInt() ?? 0,
      );
}

/// Commission earned across a period, by salesman.
class CommissionReport {
  const CommissionReport({
    required this.fromDate,
    required this.toDate,
    required this.totalCollectedAmount,
    required this.totalCommissionAmount,
    this.totalInvoicedAmount = '0.00',
    this.rows = const <CommissionRow>[],
  });

  final String fromDate;
  final String toDate;
  final String totalCollectedAmount;
  final String totalInvoicedAmount;
  final String totalCommissionAmount;
  final List<CommissionRow> rows;

  factory CommissionReport.fromJson(Json json) => CommissionReport(
        fromDate: stringValue(json['from_date']),
        toDate: stringValue(json['to_date']),
        totalCollectedAmount: stringValue(json['total_collected_amount']),
        totalInvoicedAmount: stringValue(json['total_invoiced_amount']),
        totalCommissionAmount: stringValue(json['total_commission_amount']),
        rows: [
          for (final dynamic row
              in json['rows'] is List ? json['rows'] as List : const [])
            if (row is Map) CommissionRow.fromJson(Map<String, dynamic>.from(row)),
        ],
      );
}


/// What a firm expects a salesman or a round to sell, over a period.
class SalesTargetRecord {
  const SalesTargetRecord({
    required this.id,
    required this.periodStart,
    required this.periodEnd,
    required this.targetAmount,
    this.salesmanId = '',
    this.salesmanName = '',
    this.territoryId = '',
    this.periodType = 'MONTHLY',
    this.basis = 'INVOICED',
    this.notes = '',
    this.status = 'ACTIVE',
    this.version = 0,
  });

  final String id;
  final String salesmanId;
  final String salesmanName;
  final String territoryId;
  final String periodStart;
  final String periodEnd;
  final String periodType;

  /// INVOICED or COLLECTED — what this firm counts as having been sold.
  final String basis;
  final String targetAmount;
  final String notes;
  final String status;
  final int version;

  /// Who the target is for. Neither a salesman nor a round means the firm.
  String get scopeLabel =>
      salesmanName.isNotEmpty ? salesmanName : 'Whole firm';

  factory SalesTargetRecord.fromJson(Json json) => SalesTargetRecord(
        id: stringValue(json['id']),
        salesmanId: stringValue(json['salesman_id']),
        salesmanName: stringValue(json['salesman_name']),
        territoryId: stringValue(json['territory_id']),
        periodStart: stringValue(json['period_start']),
        periodEnd: stringValue(json['period_end']),
        periodType: stringValue(json['period_type']),
        basis: stringValue(json['basis']),
        targetAmount: stringValue(json['target_amount']),
        notes: stringValue(json['notes']),
        status: stringValue(json['status']),
        version: (json['version'] as num?)?.toInt() ?? 0,
      );
}

/// One target, and what actually happened against it.
class SalesTargetAchievementRecord {
  const SalesTargetAchievementRecord({
    required this.targetId,
    required this.salesmanName,
    required this.periodStart,
    required this.periodEnd,
    required this.targetAmount,
    required this.achievedAmount,
    required this.shortfallAmount,
    required this.achievedPercent,
    this.basis = 'INVOICED',
    this.periodType = 'MONTHLY',
  });

  final String targetId;
  final String salesmanName;
  final String periodStart;
  final String periodEnd;
  final String periodType;
  final String basis;
  final String targetAmount;
  final String achievedAmount;

  /// What is left to sell, floored at zero: a target beaten is not a
  /// shortfall of a negative amount.
  final String shortfallAmount;
  final String achievedPercent;

  factory SalesTargetAchievementRecord.fromJson(Json json) =>
      SalesTargetAchievementRecord(
        targetId: stringValue(json['target_id']),
        salesmanName: stringValue(json['salesman_name']),
        periodStart: stringValue(json['period_start']),
        periodEnd: stringValue(json['period_end']),
        periodType: stringValue(json['period_type']),
        basis: stringValue(json['basis']),
        targetAmount: stringValue(json['target_amount']),
        achievedAmount: stringValue(json['achieved_amount']),
        shortfallAmount: stringValue(json['shortfall_amount']),
        achievedPercent: stringValue(json['achieved_percent']),
      );
}


/// What a firm owes one salesman for one period, and how far it has got.
///
/// The amounts are what the report said **when it was accrued**. Nothing
/// re-reads them: the report walks live documents, so asking it again in
/// September would answer differently than it did in April, and a payout that
/// changed after it was approved is one nobody can reconcile against the
/// journal behind it.
class CommissionPayoutRecord {
  const CommissionPayoutRecord({
    required this.id,
    required this.salesmanId,
    required this.salesmanName,
    required this.periodStart,
    required this.periodEnd,
    required this.earnedAmount,
    required this.payableAmount,
    this.basis = 'COLLECTED',
    this.measuredAmount = '0.00',
    this.adjustmentAmount = '0.00',
    this.adjustmentReason = '',
    this.status = 'DRAFT',
    this.accruedOn = '',
    this.paidOn = '',
    this.moneyAccountId = '',
    this.journalEntryId = '',
    this.paymentJournalEntryId = '',
    this.notes = '',
    this.version = 0,
  });

  final String id;
  final String salesmanId;
  final String salesmanName;
  final String periodStart;
  final String periodEnd;
  final String basis;

  /// The money the rate was applied to — collected or invoiced, per [basis].
  final String measuredAmount;
  final String earnedAmount;
  final String adjustmentAmount;
  final String adjustmentReason;

  /// Earned plus the adjustment: what is actually owed, and what posted.
  final String payableAmount;
  final String status;
  final String accruedOn;
  final String paidOn;
  final String moneyAccountId;
  final String journalEntryId;
  final String paymentJournalEntryId;
  final String notes;
  final int version;

  /// The period, named the way a person would say it.
  ///
  /// Almost every payout covers one calendar month, and "2026-04-01 to
  /// 2026-04-30" is both harder to read and wide enough to push the row's
  /// actions off a 1366-wide window. The full range is still shown for a
  /// period that is not a whole month, because there it is the only honest
  /// description.
  String get periodLabel {
    const List<String> months = [
      'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
      'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
    ];
    if (periodStart.length == 10 && periodEnd.length == 10) {
      final String startMonth = periodStart.substring(0, 7);
      final bool wholeMonth = startMonth == periodEnd.substring(0, 7) &&
          periodStart.endsWith('-01') &&
          _isLastOfMonth(periodEnd);
      if (wholeMonth) {
        final int index = int.tryParse(startMonth.substring(5, 7)) ?? 0;
        if (index >= 1 && index <= 12) {
          return '${months[index - 1]} ${startMonth.substring(0, 4)}';
        }
      }
    }
    return '$periodStart to $periodEnd';
  }

  static bool _isLastOfMonth(String iso) {
    final DateTime? day = DateTime.tryParse(iso);
    if (day == null) return false;
    return DateTime(day.year, day.month + 1, 0).day == day.day;
  }

  bool get isDraft => status == 'DRAFT';
  bool get isApproved => status == 'APPROVED';

  factory CommissionPayoutRecord.fromJson(Json json) => CommissionPayoutRecord(
        id: stringValue(json['id']),
        salesmanId: stringValue(json['salesman_id']),
        salesmanName: stringValue(json['salesman_name']),
        periodStart: stringValue(json['period_start']),
        periodEnd: stringValue(json['period_end']),
        basis: stringValue(json['basis']),
        measuredAmount: stringValue(json['measured_amount']),
        earnedAmount: stringValue(json['earned_amount']),
        adjustmentAmount: stringValue(json['adjustment_amount']),
        adjustmentReason: stringValue(json['adjustment_reason']),
        payableAmount: stringValue(json['payable_amount']),
        status: stringValue(json['status']).isEmpty
            ? 'DRAFT'
            : stringValue(json['status']),
        accruedOn: stringValue(json['accrued_on']),
        paidOn: stringValue(json['paid_on']),
        moneyAccountId: stringValue(json['money_account_id']),
        journalEntryId: stringValue(json['journal_entry_id']),
        paymentJournalEntryId: stringValue(json['payment_journal_entry_id']),
        notes: stringValue(json['notes']),
        version: (json['version'] as num?)?.toInt() ?? 0,
      );
}
