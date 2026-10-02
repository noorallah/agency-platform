import 'entities.dart';

/// One bank account held against a customer (MST-4). The number arrives
/// masked (`XXXXXXXX6666`, [masked] true) for anybody who does not hold
/// `CUSTOMER_MANAGE_BANK_DETAILS`.
class CustomerBankAccount {
  const CustomerBankAccount({
    required this.id,
    required this.bankName,
    required this.accountName,
    required this.accountNumber,
    this.ifsc = '',
    this.branch = '',
    this.upiId = '',
    this.isPrimary = false,
    this.masked = false,
  });

  factory CustomerBankAccount.fromJson(Json json) => CustomerBankAccount(
        id: stringValue(json['id']),
        bankName: stringValue(json['bank_name']),
        accountName: stringValue(json['account_name']),
        accountNumber: stringValue(json['account_number']),
        ifsc: stringValue(json['ifsc']),
        branch: stringValue(json['branch']),
        upiId: stringValue(json['upi_id']),
        isPrimary: boolValue(json['is_primary']),
        masked: boolValue(json['masked']),
      );

  final String id;
  final String bankName;
  final String accountName;
  final String accountNumber;
  final String ifsc;
  final String branch;
  final String upiId;
  final bool isPrimary;
  final bool masked;
}

/// A file kept with a customer (MST-4): referenced by path, not uploaded.
class CustomerAttachment {
  const CustomerAttachment({
    required this.id,
    required this.fileName,
    required this.filePath,
    required this.createdAt,
    this.mimeType,
    this.caption,
  });

  factory CustomerAttachment.fromJson(Json json) => CustomerAttachment(
        id: stringValue(json['id']),
        fileName: stringValue(json['file_name']),
        mimeType: json['mime_type']?.toString(),
        filePath: stringValue(json['file_path']),
        caption: json['caption']?.toString(),
        createdAt: stringValue(json['created_at']),
      );

  final String id;
  final String fileName;
  final String? mimeType;
  final String filePath;
  final String? caption;
  final String createdAt;
}
