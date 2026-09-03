import 'entities.dart';

/// One invoice line being credited, and the tax that comes off with it.
class CreditNoteLineRecord {
  const CreditNoteLineRecord({
    required this.id,
    required this.lineNumber,
    required this.salesInvoiceLineId,
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
  final String salesInvoiceLineId;
  final String productName;
  final String description;
  final String quantity;
  final String taxableAmount;
  final String taxAmount;
  final String totalAmount;

  /// The rate the **invoice** charged, derived from what it charged rather
  /// than read off a tax profile that may since have been edited.
  final String taxRatePercent;

  factory CreditNoteLineRecord.fromJson(Json json) => CreditNoteLineRecord(
        id: stringValue(json['id']),
        lineNumber: (json['line_number'] as num?)?.toInt() ?? 1,
        salesInvoiceLineId: stringValue(json['sales_invoice_line_id']),
        productName: stringValue(json['product_name']),
        description: stringValue(json['description']),
        quantity: stringValue(json['quantity']),
        taxableAmount: stringValue(json['taxable_amount']),
        taxAmount: stringValue(json['tax_amount']),
        totalAmount: stringValue(json['total_amount']),
        taxRatePercent: stringValue(json['tax_rate_percent']),
      );
}

/// Money credited to a customer without goods coming back.
///
/// A sales return is the other case: goods arrive, stock moves. This one
/// covers a rate agreed after invoicing, a discount given later, or a
/// shortfall nobody disputes — and it reverses the output tax the invoice
/// charged, which the bare receivable adjustment never did.
class CreditNoteRecord {
  const CreditNoteRecord({
    required this.id,
    required this.creditNoteNumber,
    required this.creditNoteDate,
    required this.customerName,
    required this.salesInvoiceNumber,
    required this.taxableAmount,
    required this.taxAmount,
    required this.totalAmount,
    this.customerId = '',
    this.salesInvoiceId = '',
    this.reason = 'OTHER',
    this.status = 'DRAFT',
    this.remarks = '',
    this.journalEntryId = '',
    this.version = 0,
    this.lines = const <CreditNoteLineRecord>[],
  });

  final String id;
  final String creditNoteNumber;
  final String creditNoteDate;
  final String customerId;
  final String customerName;
  final String salesInvoiceId;
  final String salesInvoiceNumber;
  final String reason;
  final String status;
  final String taxableAmount;
  final String taxAmount;
  final String totalAmount;
  final String remarks;
  final String journalEntryId;
  final int version;
  final List<CreditNoteLineRecord> lines;

  bool get isDraft => status == 'DRAFT';
  bool get isApproved => status == 'APPROVED';

  /// Why the customer is being credited, in the words a person would use.
  String get reasonLabel => switch (reason) {
        'RATE_DIFFERENCE' => 'Rate difference',
        'POST_SALE_DISCOUNT' => 'Discount after the sale',
        'DEFICIENCY_IN_SERVICE' => 'Deficiency',
        _ => 'Other',
      };

  factory CreditNoteRecord.fromJson(Json json) => CreditNoteRecord(
        id: stringValue(json['id']),
        creditNoteNumber: stringValue(json['credit_note_number']),
        creditNoteDate: stringValue(json['credit_note_date']),
        customerId: stringValue(json['customer_id']),
        customerName: stringValue(json['customer_name']),
        salesInvoiceId: stringValue(json['sales_invoice_id']),
        salesInvoiceNumber: stringValue(json['sales_invoice_number']),
        reason: stringValue(json['reason']).isEmpty
            ? 'OTHER'
            : stringValue(json['reason']),
        status: stringValue(json['status']).isEmpty
            ? 'DRAFT'
            : stringValue(json['status']),
        taxableAmount: stringValue(json['taxable_amount']),
        taxAmount: stringValue(json['tax_amount']),
        totalAmount: stringValue(json['total_amount']),
        remarks: stringValue(json['remarks']),
        journalEntryId: stringValue(json['journal_entry_id']),
        version: (json['version'] as num?)?.toInt() ?? 0,
        lines: [
          for (final dynamic line
              in json['lines'] is List ? json['lines'] as List : const [])
            if (line is Map)
              CreditNoteLineRecord.fromJson(Map<String, dynamic>.from(line)),
        ],
      );
}
