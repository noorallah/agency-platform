import 'entities.dart';

/// One gift a supplier gave the firm, as the register shows it (BUY-2).
class SupplierGift {
  const SupplierGift({
    required this.id,
    required this.giftNumber,
    required this.giftDate,
    required this.vendorId,
    required this.vendorName,
    required this.item,
    required this.value,
    required this.keptBy,
    required this.status,
    this.debitAccountId = '',
    this.goodsReceiptId = '',
    this.schemeName = '',
    this.tds194rAmount = '0',
    this.journalEntryId = '',
    this.remarks = '',
    this.cancelReason = '',
    this.version = 0,
  });

  final String id;
  final String giftNumber;
  final String giftDate;
  final String vendorId;
  final String vendorName;
  final String item;
  final String value;

  /// `ASSET`, `EXPENSE` or `OWNER`.
  final String keptBy;
  final String status;
  final String debitAccountId;
  final String goodsReceiptId;
  final String schemeName;
  final String tds194rAmount;
  final String journalEntryId;
  final String remarks;
  final String cancelReason;
  final int version;

  bool get isPosted => status == 'POSTED';

  factory SupplierGift.fromJson(Json json) => SupplierGift(
        id: stringValue(json['id']),
        giftNumber: stringValue(json['gift_number']),
        giftDate: stringValue(json['gift_date']),
        vendorId: stringValue(json['vendor_id']),
        vendorName: stringValue(json['vendor_name']),
        item: stringValue(json['item']),
        value: stringValue(json['value']),
        keptBy: stringValue(json['kept_by']),
        status: stringValue(json['status']),
        debitAccountId: stringValue(json['debit_account_id']),
        goodsReceiptId: stringValue(json['goods_receipt_id']),
        schemeName: stringValue(json['scheme_name']),
        tds194rAmount: stringValue(json['tds_194r_amount']),
        journalEntryId: stringValue(json['journal_entry_id']),
        remarks: stringValue(json['remarks']),
        cancelReason: stringValue(json['cancel_reason']),
        version: json['version'] is int ? json['version'] as int : 0,
      );
}

/// One supplier's year of gifts against the 194R threshold.
class SupplierGiftSummary {
  const SupplierGiftSummary({
    required this.vendorId,
    required this.vendorName,
    required this.gifts,
    required this.totalValue,
    required this.tdsDeducted,
    required this.overThreshold,
    required this.yearFrom,
    required this.yearTo,
  });

  final String vendorId;
  final String vendorName;
  final int gifts;
  final String totalValue;
  final String tdsDeducted;
  final bool overThreshold;
  final String yearFrom;
  final String yearTo;

  factory SupplierGiftSummary.fromJson(Json json) => SupplierGiftSummary(
        vendorId: stringValue(json['vendor_id']),
        vendorName: stringValue(json['vendor_name']),
        gifts: json['gifts'] is int ? json['gifts'] as int : 0,
        totalValue: stringValue(json['total_value']),
        tdsDeducted: stringValue(json['tds_deducted']),
        overThreshold: boolValue(json['over_threshold'], fallback: false),
        yearFrom: stringValue(json['year_from']),
        yearTo: stringValue(json['year_to']),
      );
}
