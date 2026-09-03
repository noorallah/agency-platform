// Tax collected at source, on money received rather than on a bill.

import 'entities.dart';

/// One firm's 206C(1H) policy.
class TcsSettings {
  const TcsSettings({
    required this.sectionCode,
    required this.isEnabled,
    required this.thresholdAmount,
    required this.ratePercent,
    required this.rateWithoutPanPercent,
    required this.precedingYearTurnover,
    required this.sellerTurnoverThreshold,
    required this.sellerInScope,
  });

  factory TcsSettings.fromJson(Json json) => TcsSettings(
        sectionCode: stringValue(json['section_code']),
        isEnabled: json['is_enabled'] == true,
        thresholdAmount: _decimal(json['threshold_amount']),
        ratePercent: _decimal(json['rate_percent']),
        rateWithoutPanPercent: _decimal(json['rate_without_pan_percent']),
        precedingYearTurnover: _decimal(json['preceding_year_turnover']),
        sellerTurnoverThreshold: _decimal(json['seller_turnover_threshold']),
        sellerInScope: json['seller_in_scope'] == true,
      );

  final String sectionCode;
  final bool isEnabled;
  final double thresholdAmount;
  final double ratePercent;
  final double rateWithoutPanPercent;
  final double precedingYearTurnover;
  final double sellerTurnoverThreshold;

  /// Whether the firm's own stated turnover puts it in scope at all. Nothing
  /// is collected unless this and [isEnabled] are both true, which is why the
  /// screen shows them as two separate facts rather than one switch.
  final bool sellerInScope;

  bool get collecting => isEnabled && sellerInScope;
}

/// One receipt's worth of tax collected, and the figures behind it.
class TcsCollectionRecord {
  const TcsCollectionRecord({
    required this.id,
    required this.customerName,
    required this.settlementNumber,
    required this.collectedOn,
    required this.considerationAmount,
    required this.cumulativeBefore,
    required this.taxableAmount,
    required this.ratePercent,
    required this.withoutPan,
    required this.tcsAmount,
    required this.status,
  });

  factory TcsCollectionRecord.fromJson(Json json) => TcsCollectionRecord(
        id: stringValue(json['id']),
        customerName: stringValue(json['customer_name']),
        settlementNumber: stringValue(json['settlement_number']),
        collectedOn: stringValue(json['collected_on']),
        considerationAmount: _decimal(json['consideration_amount']),
        cumulativeBefore: _decimal(json['cumulative_before']),
        taxableAmount: _decimal(json['taxable_amount']),
        ratePercent: _decimal(json['rate_percent']),
        withoutPan: json['without_pan'] == true,
        tcsAmount: _decimal(json['tcs_amount']),
        status: stringValue(json['status']),
      );

  final String id;
  final String customerName;
  final String settlementNumber;
  final String collectedOn;
  final double considerationAmount;

  /// What the buyer had already paid this financial year. Shown beside the
  /// taxable part because together they are the answer to "why is this number
  /// what it is", which is the only question this list gets asked.
  final double cumulativeBefore;
  final double taxableAmount;
  final double ratePercent;
  final bool withoutPan;
  final double tcsAmount;
  final String status;

  bool get isReversed => status == 'REVERSED';
}

double _decimal(Object? value) => double.tryParse('${value ?? 0}') ?? 0;
