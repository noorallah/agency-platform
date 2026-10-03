import 'entities.dart';

/// The bank particulars the firm keeps for one of its asset ledger accounts
/// (ACC-4). The one marked [printOnDocuments] prints on its bills.
class BankAccountDetails {
  const BankAccountDetails({
    required this.id,
    required this.ledgerAccountId,
    required this.ledgerAccountCode,
    required this.ledgerAccountName,
    required this.bankName,
    required this.accountName,
    required this.accountNumber,
    required this.masked,
    required this.ifsc,
    required this.branch,
    required this.accountKind,
    required this.swiftCode,
    required this.upiId,
    required this.printOnDocuments,
    required this.version,
  });

  final String id;
  final String ledgerAccountId;
  final String ledgerAccountCode;
  final String ledgerAccountName;
  final String bankName;
  final String accountName;

  /// The full number, or only its last four when [masked].
  final String accountNumber;

  /// True when the server showed only the last four digits; such a number
  /// must never be sent back.
  final bool masked;
  final String ifsc;
  final String branch;

  /// Empty when the kind is not recorded.
  final String accountKind;
  final String swiftCode;
  final String upiId;
  final bool printOnDocuments;
  final int version;

  factory BankAccountDetails.fromJson(Json json) => BankAccountDetails(
        id: stringValue(json['id']),
        ledgerAccountId: stringValue(json['ledger_account_id']),
        ledgerAccountCode: stringValue(json['ledger_account_code']),
        ledgerAccountName: stringValue(json['ledger_account_name']),
        bankName: stringValue(json['bank_name']),
        accountName: stringValue(json['account_name']),
        accountNumber: stringValue(json['account_number']),
        masked: boolValue(json['masked']),
        ifsc: stringValue(json['ifsc']),
        branch: stringValue(json['branch']),
        accountKind: stringValue(json['account_kind']),
        swiftCode: stringValue(json['swift_code']),
        upiId: stringValue(json['upi_id']),
        printOnDocuments: boolValue(json['print_on_documents']),
        version: json['version'] is int
            ? json['version'] as int
            : int.tryParse(stringValue(json['version'])) ?? 0,
      );
}

/// The body of the PUT: exactly the keys the server declares, since it
/// refuses any other. Empty optional text is sent as null.
Json bankDetailsWriteJson({
  required String bankName,
  required String accountName,
  required String accountNumber,
  String ifsc = '',
  String branch = '',
  String? accountKind,
  String swiftCode = '',
  String upiId = '',
  required bool printOnDocuments,
}) {
  String? text(String value) => value.trim().isEmpty ? null : value.trim();
  return <String, dynamic>{
    'bank_name': bankName.trim(),
    'account_name': accountName.trim(),
    'account_number': accountNumber.trim(),
    'ifsc': text(ifsc)?.toUpperCase(),
    'branch': text(branch),
    'account_kind': accountKind,
    'swift_code': text(swiftCode),
    'upi_id': text(upiId),
    'print_on_documents': printOnDocuments,
  };
}
