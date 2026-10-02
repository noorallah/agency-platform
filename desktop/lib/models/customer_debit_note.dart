import 'entities.dart';

/// One invoice line being debited, and the output tax that goes on with it.
class CustomerDebitNoteLineRecord {
  const CustomerDebitNoteLineRecord({
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

  factory CustomerDebitNoteLineRecord.fromJson(Json json) => CustomerDebitNoteLineRecord(
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

/// More charged to a customer on a sale already invoiced.
///
/// A price raised after billing, a line under-billed, a charge added later.
/// It is owed on the invoice it names, taxed at that invoice line's rate.
/// Unlike a credit note nothing caps it: a line takes any positive amount.
class CustomerDebitNoteRecord {
  const CustomerDebitNoteRecord({
    required this.id,
    required this.debitNoteNumber,
    required this.debitNoteDate,
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
    this.lines = const <CustomerDebitNoteLineRecord>[],
  });

  final String id;
  final String debitNoteNumber;
  final String debitNoteDate;
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
  final List<CustomerDebitNoteLineRecord> lines;

  bool get isDraft => status == 'DRAFT';
  bool get isApproved => status == 'APPROVED';

  /// Why the customer is being debited, in the words a person would use.
  String get reasonLabel => switch (reason) {
        'PRICE_INCREASE' => 'Price increase',
        'SHORT_BILLED' => 'Short billed',
        'ADDITIONAL_CHARGES' => 'Additional charges',
        _ => 'Other',
      };

  factory CustomerDebitNoteRecord.fromJson(Json json) => CustomerDebitNoteRecord(
        id: stringValue(json['id']),
        debitNoteNumber: stringValue(json['debit_note_number']),
        debitNoteDate: stringValue(json['debit_note_date']),
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
              CustomerDebitNoteLineRecord.fromJson(Map<String, dynamic>.from(line)),
        ],
      );
}
