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

/// One person a firm can agree a rate with.
///
/// Read from `GET /api/v1/commission/salesmen`, which exists because `users`
/// lives only in the platform schema behind `USER_VIEW` and the territory
/// module's twin of this list is gated on `TERRITORY_ASSIGN_SALESMEN` --
/// neither of which whoever sets commission holds.
class CommissionSalesman {
  const CommissionSalesman({
    required this.id,
    required this.name,
    this.email = '',
  });

  final String id;
  final String name;
  final String email;

  factory CommissionSalesman.fromJson(Json json) => CommissionSalesman(
        id: stringValue(json['user_id']),
        name: stringValue(json['full_name']),
        email: stringValue(json['email']),
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
