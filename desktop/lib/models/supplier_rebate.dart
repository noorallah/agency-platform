import 'entities.dart';

/// One step of a rebate's ladder: from [threshold] of purchases the supplier
/// gives [ratePercent] back (BUY-13).
class SupplierRebateSlab {
  const SupplierRebateSlab({
    required this.threshold,
    required this.ratePercent,
    this.id = '',
    this.lineNumber = 0,
  });

  final String id;
  final int lineNumber;
  final String threshold;
  final String ratePercent;

  factory SupplierRebateSlab.fromJson(Json json) => SupplierRebateSlab(
        id: stringValue(json['id']),
        lineNumber: (json['line_number'] as num?)?.toInt() ?? 0,
        threshold: stringValue(json['threshold']),
        ratePercent: stringValue(json['rate_percent']),
      );
}

/// A volume rebate agreed with a supplier for a period, as the register shows
/// it: how far purchases have got up the ladder and what is earned so far.
class SupplierRebate {
  const SupplierRebate({
    required this.id,
    required this.vendorId,
    required this.vendorName,
    required this.code,
    required this.name,
    required this.periodFrom,
    required this.periodTo,
    required this.status,
    this.notes = '',
    this.slabs = const <SupplierRebateSlab>[],
    this.volume = '0',
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
  final String vendorId;
  final String vendorName;
  final String code;
  final String name;
  final String periodFrom;
  final String periodTo;

  /// `ACTIVE`, `ACCRUED` or `CANCELLED`.
  final String status;
  final String notes;
  final List<SupplierRebateSlab> slabs;
  final String volume;
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

  /// What is left to take off the supplier's bills.
  double get toSettleAmount => double.tryParse(toSettle) ?? 0;

  factory SupplierRebate.fromJson(Json json) => SupplierRebate(
        id: stringValue(json['id']),
        vendorId: stringValue(json['vendor_id']),
        vendorName: stringValue(json['vendor_name']),
        code: stringValue(json['code']),
        name: stringValue(json['name']),
        periodFrom: stringValue(json['period_from']),
        periodTo: stringValue(json['period_to']),
        status: stringValue(json['status']),
        notes: stringValue(json['notes']),
        slabs: [
          for (final dynamic row
              in json['slabs'] is List ? json['slabs'] as List : const [])
            if (row is Map)
              SupplierRebateSlab.fromJson(Map<String, dynamic>.from(row)),
        ],
        volume: _orZero(json['volume']),
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

String _orZero(dynamic value) {
  final String text = stringValue(value);
  return text.isEmpty ? '0' : text;
}
