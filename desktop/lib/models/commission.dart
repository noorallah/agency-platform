import 'entities.dart';

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
  });

  /// Empty is the Unassigned bucket — money collected against invoices that
  /// carried no salesman. It belongs to nobody and is shown rather than
  /// dropped, because a total that silently omits it cannot be reconciled.
  final String salesmanId;
  final String salesmanName;
  final String collectedAmount;
  final String commissionAmount;
  final int invoiceCount;

  factory CommissionRow.fromJson(Json json) => CommissionRow(
        salesmanId: stringValue(json['salesman_id']),
        salesmanName: stringValue(json['salesman_name']),
        collectedAmount: stringValue(json['collected_amount']),
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
    this.rows = const <CommissionRow>[],
  });

  final String fromDate;
  final String toDate;
  final String totalCollectedAmount;
  final String totalCommissionAmount;
  final List<CommissionRow> rows;

  factory CommissionReport.fromJson(Json json) => CommissionReport(
        fromDate: stringValue(json['from_date']),
        toDate: stringValue(json['to_date']),
        totalCollectedAmount: stringValue(json['total_collected_amount']),
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
