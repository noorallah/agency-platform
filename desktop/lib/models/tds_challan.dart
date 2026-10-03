import 'entities.dart';

/// One deduction of tax at source that no live challan has paid yet: a posted
/// payment or expense that held tax back (ACC-7).
class TdsOpenDeduction {
  const TdsOpenDeduction({
    required this.kind,
    required this.id,
    required this.documentNumber,
    required this.documentDate,
    required this.partyName,
    required this.pan,
    required this.section,
    required this.grossAmount,
    required this.tdsAmount,
    required this.dueDate,
  });

  /// `PAYMENT` or `EXPENSE`.
  final String kind;
  final String id;
  final String documentNumber;
  final String documentDate;
  final String partyName;
  final String pan;
  final String section;
  final String grossAmount;
  final String tdsAmount;

  /// The day the tax is due at the bank; empty when the server gave none.
  final String dueDate;

  double get tax => double.tryParse(tdsAmount) ?? 0;

  /// What a ticked box says about this row.
  String get key => '$kind:$id';

  factory TdsOpenDeduction.fromJson(Json json) => TdsOpenDeduction(
        kind: stringValue(json['kind']),
        id: stringValue(json['id']),
        documentNumber: stringValue(json['document_number']),
        documentDate: stringValue(json['document_date']),
        partyName: stringValue(json['party_name']),
        pan: stringValue(json['pan']),
        section: stringValue(json['section']),
        grossAmount: stringValue(json['gross_amount']),
        tdsAmount: stringValue(json['tds_amount']),
        dueDate: stringValue(json['due_date']),
      );
}

/// One deduction a challan paid.
class TdsChallanItem {
  const TdsChallanItem({
    required this.kind,
    required this.documentId,
    required this.documentNumber,
    required this.documentDate,
    required this.partyName,
    required this.pan,
    required this.tdsAmount,
  });

  final String kind;
  final String documentId;
  final String documentNumber;
  final String documentDate;
  final String partyName;
  final String pan;
  final String tdsAmount;

  factory TdsChallanItem.fromJson(Json json) => TdsChallanItem(
        kind: stringValue(json['kind']),
        documentId: stringValue(json['document_id']),
        documentNumber: stringValue(json['document_number']),
        documentDate: stringValue(json['document_date']),
        partyName: stringValue(json['party_name']),
        pan: stringValue(json['pan']),
        tdsAmount: stringValue(json['tds_amount']),
      );
}

/// A deposit of tax deducted at source (ITNS 281), and the deductions it paid.
class TdsChallan {
  const TdsChallan({
    required this.id,
    required this.challanNumber,
    required this.depositedOn,
    required this.bsrCode,
    required this.challanSerial,
    required this.cin,
    required this.section,
    required this.sectionName,
    required this.taxAmount,
    required this.interestAmount,
    required this.feeAmount,
    required this.totalAmount,
    this.paidFromAccountId = '',
    this.paidFromAccountCode = '',
    this.paidFromAccountName = '',
    this.remarks = '',
    this.status = 'POSTED',
    this.cancelReason = '',
    this.isLate = false,
    this.items = const [],
    this.version = 0,
  });

  final String id;
  final String challanNumber;
  final String depositedOn;
  final String bsrCode;
  final String challanSerial;
  final String cin;
  final String section;
  final String sectionName;
  final String taxAmount;
  final String interestAmount;
  final String feeAmount;
  final String totalAmount;
  final String paidFromAccountId;
  final String paidFromAccountCode;
  final String paidFromAccountName;
  final String remarks;

  /// `POSTED` or `CANCELLED`.
  final String status;
  final String cancelReason;

  /// Deposited after the day some deduction on it was due.
  final bool isLate;
  final List<TdsChallanItem> items;
  final int version;

  bool get isPosted => status == 'POSTED';

  /// Interest and fee together, the one column the grid shows.
  double get interestAndFee =>
      (double.tryParse(interestAmount) ?? 0) + (double.tryParse(feeAmount) ?? 0);

  String get paidFromLabel => paidFromAccountCode.isEmpty
      ? paidFromAccountName
      : '$paidFromAccountCode · $paidFromAccountName';

  factory TdsChallan.fromJson(Json json) => TdsChallan(
        id: stringValue(json['id']),
        challanNumber: stringValue(json['challan_number']),
        depositedOn: stringValue(json['deposited_on']),
        bsrCode: stringValue(json['bsr_code']),
        challanSerial: stringValue(json['challan_serial']),
        cin: stringValue(json['cin']),
        section: stringValue(json['section']),
        sectionName: stringValue(json['section_name']),
        taxAmount: stringValue(json['tax_amount']),
        interestAmount: stringValue(json['interest_amount']),
        feeAmount: stringValue(json['fee_amount']),
        totalAmount: stringValue(json['total_amount']),
        paidFromAccountId: stringValue(json['paid_from_account_id']),
        paidFromAccountCode: stringValue(json['paid_from_account_code']),
        paidFromAccountName: stringValue(json['paid_from_account_name']),
        remarks: stringValue(json['remarks']),
        status: stringValue(json['status']).isEmpty
            ? 'POSTED'
            : stringValue(json['status']),
        cancelReason: stringValue(json['cancel_reason']),
        isLate: boolValue(json['is_late']),
        items: json['items'] is List
            ? (json['items'] as List)
                .whereType<Map>()
                .map((item) =>
                    TdsChallanItem.fromJson(Map<String, dynamic>.from(item)))
                .toList()
            : const [],
        version: (json['version'] as num?)?.toInt() ?? 0,
      );
}
