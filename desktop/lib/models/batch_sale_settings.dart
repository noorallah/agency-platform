import 'entities.dart';

/// The firm's rules for selling batches (backlog 79 row 6): what counts as
/// near expiry, what leaving such a batch costs the seller, and whether a
/// near-expiry batch may go below the price floor.
class BatchSaleSettings {
  const BatchSaleSettings({
    this.nearExpiryDays = 30,
    this.nearExpiryPolicy = 'WARN',
    this.fefoSkipPolicy = 'RECORD',
    this.nearExpiryBelowFloor = true,
    this.shelfLifePolicy = 'BLOCK',
    this.priceFromBatch = false,
    this.isConfigured = false,
  });

  /// A batch expiring within this many days is near expiry (0 to 730).
  final int nearExpiryDays;

  /// WARN or REASON: what dispatching a line that leaves a near-expiry batch
  /// behind needs.
  final String nearExpiryPolicy;

  /// RECORD or REASON: what dispatching past an earlier-expiring batch needs.
  final String fefoSkipPolicy;

  /// Whether a near-expiry batch may be sold below the price floor.
  final bool nearExpiryBelowFloor;

  /// BLOCK or WARN: what dispatching a batch short of the customer's minimum
  /// shelf life does.
  final String shelfLifePolicy;

  /// Whether a line's rate is taken from its batch's selling price.
  final bool priceFromBatch;

  /// False while the firm is still on the platform default.
  final bool isConfigured;

  factory BatchSaleSettings.fromJson(Json json) => BatchSaleSettings(
        nearExpiryDays: int.tryParse(stringValue(json['near_expiry_days'])) ??
            30,
        nearExpiryPolicy: stringValue(json['near_expiry_policy']),
        fefoSkipPolicy: stringValue(json['fefo_skip_policy']),
        nearExpiryBelowFloor: boolValue(
          json['near_expiry_below_floor'],
          fallback: true,
        ),
        shelfLifePolicy: stringValue(json['shelf_life_policy']) == 'WARN'
            ? 'WARN'
            : 'BLOCK',
        priceFromBatch: boolValue(json['price_from_batch']),
        isConfigured: boolValue(json['is_configured']),
      );

  /// Exactly the six keys the server declares; it refuses any other.
  Json toJson() => <String, dynamic>{
        'near_expiry_days': nearExpiryDays,
        'near_expiry_policy': nearExpiryPolicy,
        'fefo_skip_policy': fefoSkipPolicy,
        'near_expiry_below_floor': nearExpiryBelowFloor,
        'shelf_life_policy': shelfLifePolicy,
        'price_from_batch': priceFromBatch,
      };
}

/// One thing the batch rules have to say about a delivery note's lines.
class DispatchBatchFinding {
  const DispatchBatchFinding({
    required this.lineNumber,
    required this.kind,
    required this.message,
  });

  final String lineNumber;

  /// NEAR_EXPIRY, FEFO_SKIP or SHORT_SHELF_LIFE.
  final String kind;
  final String message;

  factory DispatchBatchFinding.fromJson(Json json) => DispatchBatchFinding(
        lineNumber: stringValue(json['line_number']),
        kind: stringValue(json['kind']),
        message: stringValue(json['message']),
      );
}

/// What the batch rules say about dispatching one delivery note
/// (`GET /delivery-notes/{id}/batch-check`).
class DispatchBatchCheck {
  const DispatchBatchCheck({
    this.findings = const [],
    this.needsReason = false,
    this.wouldBlock = false,
    this.message,
  });

  final List<DispatchBatchFinding> findings;

  /// True when a finding's rule is REASON: the dispatch needs `batch_reason`.
  final bool needsReason;

  /// True when the dispatch will be refused whatever reason is given.
  final bool wouldBlock;
  final String? message;

  factory DispatchBatchCheck.fromJson(Json json) {
    final String text = stringValue(json['message']);
    return DispatchBatchCheck(
      findings: (json['findings'] as List? ?? const [])
          .whereType<Map>()
          .map((item) =>
              DispatchBatchFinding.fromJson(Map<String, dynamic>.from(item)))
          .toList(),
      needsReason: boolValue(json['needs_reason']),
      wouldBlock: boolValue(json['would_block']),
      message: text.isEmpty ? null : text,
    );
  }
}
