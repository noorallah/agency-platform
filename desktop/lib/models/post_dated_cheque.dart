import 'entities.dart';

/// A cheque dated after the day it was handed over (ACC-2). Received from a
/// customer or issued to a supplier; the register follows it from held to
/// banked and then cleared, returned or cancelled.
class PostDatedCheque {
  const PostDatedCheque({
    required this.id,
    required this.direction,
    required this.partyId,
    required this.partyCode,
    required this.partyName,
    required this.chequeNumber,
    required this.chequeDate,
    required this.amount,
    this.drawnOnBank = '',
    this.receivedOn = '',
    this.narration = '',
    this.status = 'HELD',
    this.isDue = false,
    this.settlementId = '',
    this.settlementNumber = '',
    this.depositedOn = '',
    this.clearedOn = '',
    this.bouncedOn = '',
    this.bounceReason = '',
    this.bankChargesAmount = '',
    this.customerChargeAmount = '',
    this.cancelReason = '',
    this.version = 0,
  });

  final String id;

  /// `RECEIVED` or `ISSUED`.
  final String direction;
  final String partyId;
  final String partyCode;
  final String partyName;
  final String chequeNumber;
  final String chequeDate;
  final String drawnOnBank;
  final String amount;
  final String receivedOn;
  final String narration;

  /// `HELD`, `DEPOSITED`, `CLEARED`, `BOUNCED` or `CANCELLED`.
  final String status;

  /// Held, and its date has come.
  final bool isDue;

  /// The receipt or payment banking the cheque raised.
  final String settlementId;
  final String settlementNumber;
  final String depositedOn;
  final String clearedOn;
  final String bouncedOn;
  final String bounceReason;
  final String bankChargesAmount;
  final String customerChargeAmount;
  final String cancelReason;
  final int version;

  bool get isHeld => status == 'HELD';
  bool get isDeposited => status == 'DEPOSITED';

  String get partyLabel =>
      partyCode.isEmpty ? partyName : '$partyCode · $partyName';

  factory PostDatedCheque.fromJson(Json json) => PostDatedCheque(
        id: stringValue(json['id']),
        direction: stringValue(json['direction']),
        partyId: stringValue(json['party_id']),
        partyCode: stringValue(json['party_code']),
        partyName: stringValue(json['party_name']),
        chequeNumber: stringValue(json['cheque_number']),
        chequeDate: stringValue(json['cheque_date']),
        drawnOnBank: stringValue(json['drawn_on_bank']),
        amount: stringValue(json['amount']),
        receivedOn: stringValue(json['received_on']),
        narration: stringValue(json['narration']),
        status: stringValue(json['status']).isEmpty
            ? 'HELD'
            : stringValue(json['status']),
        isDue: boolValue(json['is_due']),
        settlementId: stringValue(json['settlement_id']),
        settlementNumber: stringValue(json['settlement_number']),
        depositedOn: stringValue(json['deposited_on']),
        clearedOn: stringValue(json['cleared_on']),
        bouncedOn: stringValue(json['bounced_on']),
        bounceReason: stringValue(json['bounce_reason']),
        bankChargesAmount: stringValue(json['bank_charges_amount']),
        customerChargeAmount: stringValue(json['customer_charge_amount']),
        cancelReason: stringValue(json['cancel_reason']),
        version: (json['version'] as num?)?.toInt() ?? 0,
      );
}
