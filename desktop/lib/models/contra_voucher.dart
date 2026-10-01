import 'entities.dart';

/// One cash or bank account a contra voucher may move money between.
class MoneyAccount {
  const MoneyAccount({
    required this.id,
    required this.code,
    required this.name,
    required this.kind,
  });

  final String id;
  final String code;
  final String name;

  /// `CASH` or `BANK`.
  final String kind;

  bool get isCash => kind == 'CASH';

  String get label => code.isEmpty ? name : '$code · $name';

  factory MoneyAccount.fromJson(Json json) => MoneyAccount(
        id: stringValue(json['id']),
        code: stringValue(json['code']),
        name: stringValue(json['name']),
        kind: stringValue(json['kind']),
      );
}

/// Money moved between the firm's own cash and bank accounts.
class ContraVoucher {
  const ContraVoucher({
    required this.id,
    required this.voucherNumber,
    required this.voucherDate,
    required this.kind,
    required this.amount,
    this.status = 'POSTED',
    this.fromAccountId = '',
    this.fromAccountName = '',
    this.toAccountId = '',
    this.toAccountName = '',
    this.reference = '',
    this.remarks = '',
    this.cancelReason = '',
    this.balanceWarning = '',
    this.version = 0,
  });

  final String id;
  final String voucherNumber;
  final String voucherDate;

  /// `DEPOSIT`, `WITHDRAWAL`, `BANK_TRANSFER` or `CASH_TRANSFER`; the server
  /// derives it from the two accounts.
  final String kind;

  /// `POSTED` or `CANCELLED`.
  final String status;
  final String fromAccountId;
  final String fromAccountName;
  final String toAccountId;
  final String toAccountName;
  final String amount;
  final String reference;
  final String remarks;
  final String cancelReason;

  /// Set when the From account would go below zero on the voucher date. The
  /// voucher is saved all the same; this is only said.
  final String balanceWarning;
  final int version;

  bool get isPosted => status == 'POSTED';

  String get kindLabel => contraKindLabel(kind);

  factory ContraVoucher.fromJson(Json json) => ContraVoucher(
        id: stringValue(json['id']),
        voucherNumber: stringValue(json['voucher_number']),
        voucherDate: stringValue(json['voucher_date']),
        kind: stringValue(json['kind']),
        status: stringValue(json['status']).isEmpty
            ? 'POSTED'
            : stringValue(json['status']),
        fromAccountId: stringValue(json['from_account_id']),
        fromAccountName: stringValue(json['from_account_name']),
        toAccountId: stringValue(json['to_account_id']),
        toAccountName: stringValue(json['to_account_name']),
        amount: stringValue(json['amount']),
        reference: stringValue(json['reference']),
        remarks: stringValue(json['remarks']),
        cancelReason: stringValue(json['cancel_reason']),
        balanceWarning: stringValue(json['balance_warning']),
        version: (json['version'] as num?)?.toInt() ?? 0,
      );
}

/// The kind in the words a person uses for it.
String contraKindLabel(String kind) => switch (kind) {
      'DEPOSIT' => 'Deposit (cash to bank)',
      'WITHDRAWAL' => 'Withdrawal (bank to cash)',
      'BANK_TRANSFER' => 'Bank transfer',
      'CASH_TRANSFER' => 'Cash transfer',
      _ => kind,
    };

/// What two accounts' kinds will make of a voucher, for a live hint; empty
/// until both are picked.
String contraKindHint(MoneyAccount? from, MoneyAccount? to) {
  if (from == null || to == null) return '';
  if (from.isCash && !to.isCash) return contraKindLabel('DEPOSIT');
  if (!from.isCash && to.isCash) return contraKindLabel('WITHDRAWAL');
  return contraKindLabel(from.isCash ? 'CASH_TRANSFER' : 'BANK_TRANSFER');
}
