import 'entities.dart';

/// One line of a claim on a principal: a scheme, free goods, an expiry or a
/// breakage (SEL-11), with the document it came from.
class PrincipalClaimLine {
  const PrincipalClaimLine({
    required this.kind,
    this.lineNumber = 0,
    this.sourceId = '',
    this.sourceNumber = '',
    this.sourceDate = '',
    this.productId = '',
    this.productName = '',
    this.quantity = '',
    this.description = '',
    this.amount = '0',
    this.batchId = '',
    this.batchNumber = '',
    this.oldRate = '',
    this.newRate = '',
    this.adjustsClaimNumber = '',
  });

  /// `SCHEME`, `FREE_GOODS`, `EXPIRY`, `BREAKAGE` or `RATE_DIFFERENCE`.
  final String kind;
  final int lineNumber;
  final String sourceId;
  final String sourceNumber;
  final String sourceDate;
  final String productId;
  final String productName;
  final String quantity;
  final String description;

  /// Negative on an adjustment: what an earlier claim held that came back.
  final String amount;

  /// Rate difference only: the batch (empty when the product has none) and
  /// the purchase rate per stock unit before and after the cut. `quantity`
  /// is then the stock on hand at the close of the day before.
  final String batchId;
  final String batchNumber;
  final String oldRate;
  final String newRate;

  /// On an adjustment, the claim whose line it takes back from.
  final String adjustsClaimNumber;

  factory PrincipalClaimLine.fromJson(Json json) => PrincipalClaimLine(
        kind: stringValue(json['kind']),
        lineNumber: (json['line_number'] as num?)?.toInt() ?? 0,
        sourceId: stringValue(json['source_id']),
        sourceNumber: stringValue(json['source_number']),
        sourceDate: stringValue(json['source_date']),
        productId: stringValue(json['product_id']),
        productName: stringValue(json['product_name']),
        quantity: stringValue(json['quantity']),
        description: stringValue(json['description']),
        amount: _amount(json['amount']),
        batchId: stringValue(json['batch_id']),
        batchNumber: stringValue(json['batch_number']),
        oldRate: stringValue(json['old_rate']),
        newRate: stringValue(json['new_rate']),
        adjustsClaimNumber: stringValue(json['adjusts_claim_number']),
      );
}

List<PrincipalClaimLine> _lines(dynamic raw) => raw is List
    ? [
        for (final dynamic row in raw)
          if (row is Map)
            PrincipalClaimLine.fromJson(Map<String, dynamic>.from(row)),
      ]
    : const <PrincipalClaimLine>[];

String _amount(dynamic raw) =>
    stringValue(raw).isEmpty ? '0' : stringValue(raw);

/// A payment received from the principal against a claim.
class PrincipalClaimReceipt {
  const PrincipalClaimReceipt({
    required this.id,
    required this.receivedOn,
    required this.amount,
    this.moneyAccountId = '',
    this.reference = '',
    this.status = 'POSTED',
  });

  final String id;
  final String receivedOn;
  final String amount;
  final String moneyAccountId;
  final String reference;

  /// `POSTED` or `REVERSED`.
  final String status;

  bool get isPosted => status == 'POSTED';

  factory PrincipalClaimReceipt.fromJson(Json json) => PrincipalClaimReceipt(
        id: stringValue(json['id']),
        receivedOn: stringValue(json['received_on']),
        amount: _amount(json['amount']),
        moneyAccountId: stringValue(json['money_account_id']),
        reference: stringValue(json['reference']),
        status: stringValue(json['status']).isEmpty
            ? 'POSTED'
            : stringValue(json['status']),
      );
}

/// What a claim would hold, before anything is raised (writes nothing).
class PrincipalClaimPreview {
  const PrincipalClaimPreview({
    required this.principalId,
    this.periodFrom = '',
    this.periodTo = '',
    this.schemeAmount = '0',
    this.freeGoodsAmount = '0',
    this.expiryAmount = '0',
    this.breakageAmount = '0',
    this.rateDifferenceAmount = '0',
    this.totalAmount = '0',
    this.adjustmentsCarriedForward = '0',
    this.lines = const <PrincipalClaimLine>[],
  });

  final String principalId;
  final String periodFrom;
  final String periodTo;
  final String schemeAmount;

  /// Free goods given on bills of the principal's products, at cost.
  final String freeGoodsAmount;
  final String expiryAmount;
  final String breakageAmount;

  /// A price cut on the stock in hand: (old rate - new rate) x quantity.
  final String rateDifferenceAmount;
  final String totalAmount;

  /// What came back after earlier claims and could not come off this one,
  /// because a claim is never negative: it comes off the next.
  final String adjustmentsCarriedForward;
  final List<PrincipalClaimLine> lines;

  double get carriedForward => double.tryParse(adjustmentsCarriedForward) ?? 0;

  factory PrincipalClaimPreview.fromJson(Json json) => PrincipalClaimPreview(
        principalId: stringValue(json['principal_id']),
        periodFrom: stringValue(json['period_from']),
        periodTo: stringValue(json['period_to']),
        schemeAmount: _amount(json['scheme_amount']),
        freeGoodsAmount: _amount(json['free_goods_amount']),
        expiryAmount: _amount(json['expiry_amount']),
        breakageAmount: _amount(json['breakage_amount']),
        rateDifferenceAmount: _amount(json['rate_difference_amount']),
        totalAmount: _amount(json['total_amount']),
        adjustmentsCarriedForward: _amount(json['adjustments_carried_forward']),
        lines: _lines(json['lines']),
      );
}

/// A claim raised on a principal for scheme cost, expiry and breakage
/// (SEL-11), settled by their credit note or by a payment.
class PrincipalClaim {
  const PrincipalClaim({
    required this.id,
    required this.claimNumber,
    required this.principalId,
    required this.principalName,
    this.claimDate = '',
    this.vendorId = '',
    this.periodFrom = '',
    this.periodTo = '',
    this.schemeAmount = '0',
    this.freeGoodsAmount = '0',
    this.expiryAmount = '0',
    this.breakageAmount = '0',
    this.rateDifferenceAmount = '0',
    this.totalAmount = '0',
    this.settledByCreditNote = '0',
    this.settledByPayment = '0',
    this.outstanding = '0',
    this.status = 'RAISED',
    this.remarks = '',
    this.cancelReason = '',
    this.version = 0,
    this.lines = const <PrincipalClaimLine>[],
    this.receipts = const <PrincipalClaimReceipt>[],
  });

  final String id;
  final String claimNumber;
  final String claimDate;
  final String principalId;
  final String principalName;

  /// The supplier the principal is bought through; empty when none, which
  /// leaves a credit-note settlement unavailable.
  final String vendorId;
  final String periodFrom;
  final String periodTo;
  final String schemeAmount;

  /// Free goods given on bills of the principal's products, at cost.
  final String freeGoodsAmount;
  final String expiryAmount;
  final String breakageAmount;

  /// A price cut on the stock in hand: (old rate - new rate) x quantity.
  final String rateDifferenceAmount;
  final String totalAmount;
  final String settledByCreditNote;
  final String settledByPayment;
  final String outstanding;

  /// `RAISED`, `PART_SETTLED`, `SETTLED` or `CANCELLED`.
  final String status;
  final String remarks;
  final String cancelReason;
  final int version;
  final List<PrincipalClaimLine> lines;
  final List<PrincipalClaimReceipt> receipts;

  double get outstandingAmount => double.tryParse(outstanding) ?? 0;
  bool get isCancelled => status == 'CANCELLED';
  bool get isOpen => status == 'RAISED' || status == 'PART_SETTLED';
  bool get canSettleByCreditNote =>
      vendorId.isNotEmpty && outstandingAmount > 0 && !isCancelled;

  factory PrincipalClaim.fromJson(Json json) => PrincipalClaim(
        id: stringValue(json['id']),
        claimNumber: stringValue(json['claim_number']),
        claimDate: stringValue(json['claim_date']),
        principalId: stringValue(json['principal_id']),
        principalName: stringValue(json['principal_name']),
        vendorId: stringValue(json['vendor_id']),
        periodFrom: stringValue(json['period_from']),
        periodTo: stringValue(json['period_to']),
        schemeAmount: _amount(json['scheme_amount']),
        freeGoodsAmount: _amount(json['free_goods_amount']),
        expiryAmount: _amount(json['expiry_amount']),
        breakageAmount: _amount(json['breakage_amount']),
        rateDifferenceAmount: _amount(json['rate_difference_amount']),
        totalAmount: _amount(json['total_amount']),
        settledByCreditNote: _amount(json['settled_by_credit_note']),
        settledByPayment: _amount(json['settled_by_payment']),
        outstanding: _amount(json['outstanding']),
        status: stringValue(json['status']).isEmpty
            ? 'RAISED'
            : stringValue(json['status']),
        remarks: stringValue(json['remarks']),
        cancelReason: stringValue(json['cancel_reason']),
        version: (json['version'] as num?)?.toInt() ?? 0,
        lines: _lines(json['lines']),
        receipts: json['receipts'] is List
            ? [
                for (final dynamic row in json['receipts'] as List)
                  if (row is Map)
                    PrincipalClaimReceipt.fromJson(
                        Map<String, dynamic>.from(row)),
              ]
            : const <PrincipalClaimReceipt>[],
      );
}
