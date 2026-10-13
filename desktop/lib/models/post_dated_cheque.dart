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
    this.paidToKind = '',
    this.payeeName = '',
    this.bankAccountId = '',
    this.bankAccountName = '',
    this.expenseId = '',
    this.expenseNumber = '',
    this.journalEntryId = '',
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

  /// Who one of the firm's own cheques pays: `SUPPLIER`, `CUSTOMER`,
  /// `EXPENSE` or `ACCOUNT`. Blank on a customer's cheque, and on an old
  /// issued one, which is to a supplier.
  final String paidToKind;

  /// The name written on the firm's cheque.
  final String payeeName;

  /// The firm's bank account an issued cheque is drawn on.
  final String bankAccountId;
  final String bankAccountName;

  /// The expense, or the payment voucher, presenting the cheque raised.
  final String expenseId;
  final String expenseNumber;
  final String journalEntryId;
  final int version;

  bool get isHeld => status == 'HELD';
  bool get isDeposited => status == 'DEPOSITED';

  /// Who an issued cheque pays, in a word.
  String get paidToWords => switch (paidToKind) {
        'CUSTOMER' => 'Customer',
        'EXPENSE' => 'Expense',
        'ACCOUNT' => 'Account',
        'SUPPLIER' => 'Supplier',
        _ => direction == 'ISSUED' ? 'Supplier' : '',
      };

  /// What presenting the cheque turned it into, or blank before that.
  String get becameLabel => settlementNumber.isNotEmpty
      ? settlementNumber
      : expenseNumber.isNotEmpty
          ? expenseNumber
          : journalEntryId.isNotEmpty
              ? 'Payment voucher'
              : '';

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
        paidToKind: stringValue(json['paid_to_kind']),
        payeeName: stringValue(json['payee_name']),
        bankAccountId: stringValue(json['bank_account_id']),
        bankAccountName: stringValue(json['bank_account_name']),
        expenseId: stringValue(json['expense_id']),
        expenseNumber: stringValue(json['expense_number']),
        journalEntryId: stringValue(json['journal_entry_id']),
        version: (json['version'] as num?)?.toInt() ?? 0,
      );
}

/// One ledger account *Write a cheque* offers.
class ChequeAccount {
  const ChequeAccount({
    required this.id,
    required this.code,
    required this.name,
  });

  final String id;
  final String code;
  final String name;

  String get label => code.isEmpty ? name : '$code  $name';

  factory ChequeAccount.fromJson(Json json) => ChequeAccount(
        id: stringValue(json['id']),
        code: stringValue(json['code']),
        name: stringValue(json['name']),
      );
}

/// The accounts *Write a cheque* offers: what a cheque is drawn on, and the
/// expense and other accounts it can pay besides a supplier or a customer.
class ChequeAccountChoices {
  const ChequeAccountChoices({
    this.bankAccounts = const [],
    this.expenseAccounts = const [],
    this.otherAccounts = const [],
  });

  final List<ChequeAccount> bankAccounts;
  final List<ChequeAccount> expenseAccounts;
  final List<ChequeAccount> otherAccounts;

  factory ChequeAccountChoices.fromJson(Json json) {
    List<ChequeAccount> read(String key) {
      final dynamic raw = json[key];
      return raw is List
          ? raw
              .whereType<Map>()
              .map((item) =>
                  ChequeAccount.fromJson(Map<String, dynamic>.from(item)))
              .toList()
          : const [];
    }

    return ChequeAccountChoices(
      bankAccounts: read('bank_accounts'),
      expenseAccounts: read('expense_accounts'),
      otherAccounts: read('other_accounts'),
    );
  }
}
