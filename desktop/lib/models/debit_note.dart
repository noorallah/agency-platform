import 'entities.dart';

/// One bill line being claimed on, and the tax that comes off with it.
class DebitNoteLineRecord {
  const DebitNoteLineRecord({
    required this.id,
    required this.lineNumber,
    required this.purchaseInvoiceLineId,
    required this.productName,
    required this.taxableAmount,
    required this.taxAmount,
    required this.totalAmount,
    this.quantity = '0',
    this.taxRatePercent = '0',
    this.description = '',
  });

  final String id;
  final int lineNumber;
  final String purchaseInvoiceLineId;
  final String productName;
  final String description;
  final String quantity;
  final String taxableAmount;
  final String taxAmount;
  final String totalAmount;

  /// The rate the **bill** charged, not today's rate for the product.
  final String taxRatePercent;

  factory DebitNoteLineRecord.fromJson(Json json) => DebitNoteLineRecord(
        id: stringValue(json['id']),
        lineNumber: (json['line_number'] as num?)?.toInt() ?? 1,
        purchaseInvoiceLineId: stringValue(json['purchase_invoice_line_id']),
        productName: stringValue(json['product_name']),
        description: stringValue(json['description']),
        quantity: stringValue(json['quantity']),
        taxableAmount: stringValue(json['taxable_amount']),
        taxAmount: stringValue(json['tax_amount']),
        totalAmount: stringValue(json['total_amount']),
        taxRatePercent: stringValue(json['tax_rate_percent']),
      );
}

/// A line of a bill and how much of it can still be claimed on.
class DebitNoteClaimableLine {
  const DebitNoteClaimableLine({
    required this.purchaseInvoiceLineId,
    required this.lineNumber,
    required this.productName,
    this.quantity = '0',
    this.unitPrice = '0',
    this.billedTaxable = '0',
    this.alreadyClaimed = '0',
    this.alreadyReturned = '0',
    this.claimable = '0',
    this.taxRatePercent = '0',
  });

  final String purchaseInvoiceLineId;
  final int lineNumber;
  final String productName;
  final String quantity;
  final String unitPrice;
  final String billedTaxable;
  final String alreadyClaimed;
  final String alreadyReturned;

  /// What a note may still claim on this line, before tax.
  final String claimable;
  final String taxRatePercent;

  factory DebitNoteClaimableLine.fromJson(Json json) => DebitNoteClaimableLine(
        purchaseInvoiceLineId: stringValue(json['purchase_invoice_line_id']),
        lineNumber: (json['line_number'] as num?)?.toInt() ?? 1,
        productName: stringValue(json['product_name']),
        quantity: stringValue(json['quantity']),
        unitPrice: stringValue(json['unit_price']),
        billedTaxable: stringValue(json['billed_taxable']),
        alreadyClaimed: stringValue(json['already_claimed']),
        alreadyReturned: stringValue(json['already_returned']),
        claimable: stringValue(json['claimable']),
        taxRatePercent: stringValue(json['tax_rate_percent']),
      );
}

/// A claim on a supplier for a price difference or a short supply, with no
/// goods going back. A purchase return is the other case: goods leave and
/// stock moves. This one reduces what is owed to the supplier and the input
/// tax claimed on the bill.
class DebitNoteRecord {
  const DebitNoteRecord({
    required this.id,
    required this.debitNoteNumber,
    required this.debitNoteDate,
    required this.vendorName,
    required this.purchaseInvoiceNumber,
    required this.taxableAmount,
    required this.taxAmount,
    required this.totalAmount,
    this.vendorId = '',
    this.purchaseInvoiceId = '',
    this.supplierInvoiceNumber = '',
    this.reason = 'OTHER',
    this.status = 'DRAFT',
    this.referenceNumber = '',
    this.supplierCreditNoteNumber = '',
    this.supplierCreditNoteDate = '',
    this.remarks = '',
    this.cancelReason = '',
    this.journalEntryId = '',
    this.version = 0,
    this.lines = const <DebitNoteLineRecord>[],
  });

  final String id;
  final String debitNoteNumber;
  final String debitNoteDate;
  final String vendorId;
  final String vendorName;
  final String purchaseInvoiceId;
  final String purchaseInvoiceNumber;
  final String supplierInvoiceNumber;
  final String reason;
  final String status;
  final String taxableAmount;
  final String taxAmount;
  final String totalAmount;
  final String referenceNumber;

  /// The supplier's own credit note this note records, when it is one the
  /// supplier issued (backlog 68 row 10); empty for a claim the firm raised.
  final String supplierCreditNoteNumber;
  final String supplierCreditNoteDate;
  final String remarks;
  final String cancelReason;
  final String journalEntryId;
  final int version;
  final List<DebitNoteLineRecord> lines;

  bool get isDraft => status == 'DRAFT';
  bool get isApproved => status == 'APPROVED';

  /// Why the supplier is being claimed on, in the words a person would use.
  String get reasonLabel => switch (reason) {
        'PRICE_DIFFERENCE' => 'Price difference',
        'SHORT_SUPPLY' => 'Short supply',
        'DISCOUNT' => 'Discount after billing',
        _ => 'Other',
      };

  factory DebitNoteRecord.fromJson(Json json) => DebitNoteRecord(
        id: stringValue(json['id']),
        debitNoteNumber: stringValue(json['debit_note_number']),
        debitNoteDate: stringValue(json['debit_note_date']),
        vendorId: stringValue(json['vendor_id']),
        vendorName: stringValue(json['vendor_name']),
        purchaseInvoiceId: stringValue(json['purchase_invoice_id']),
        purchaseInvoiceNumber: stringValue(json['purchase_invoice_number']),
        supplierInvoiceNumber: stringValue(json['supplier_invoice_number']),
        reason: stringValue(json['reason']).isEmpty
            ? 'OTHER'
            : stringValue(json['reason']),
        status: stringValue(json['status']).isEmpty
            ? 'DRAFT'
            : stringValue(json['status']),
        taxableAmount: stringValue(json['taxable_amount']),
        taxAmount: stringValue(json['tax_amount']),
        totalAmount: stringValue(json['total_amount']),
        referenceNumber: stringValue(json['reference_number']),
        supplierCreditNoteNumber:
            stringValue(json['supplier_credit_note_number']),
        supplierCreditNoteDate: stringValue(json['supplier_credit_note_date']),
        remarks: stringValue(json['remarks']),
        cancelReason: stringValue(json['cancel_reason']),
        journalEntryId: stringValue(json['journal_entry_id']),
        version: (json['version'] as num?)?.toInt() ?? 0,
        lines: [
          for (final dynamic line
              in json['lines'] is List ? json['lines'] as List : const [])
            if (line is Map)
              DebitNoteLineRecord.fromJson(Map<String, dynamic>.from(line)),
        ],
      );
}
