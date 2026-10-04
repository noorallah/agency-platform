import 'entities.dart';

int _int(dynamic value) => value is num ? value.toInt() : 0;

/// A supplier bill the imported goods came on (PG-12 part B).
class BoeInvoiceLink {
  const BoeInvoiceLink({
    required this.id,
    this.invoiceNumber = '',
    this.supplierInvoiceNumber = '',
    this.invoiceDate = '',
    this.status = '',
    this.currencyCode = '',
    this.exchangeRate = '',
    this.grandTotal = '',
    this.baseGrandTotal = '',
  });

  factory BoeInvoiceLink.fromJson(Json json) => BoeInvoiceLink(
        id: stringValue(json['purchase_invoice_id']),
        invoiceNumber: stringValue(json['invoice_number']),
        supplierInvoiceNumber: stringValue(json['supplier_invoice_number']),
        invoiceDate: stringValue(json['invoice_date']),
        status: stringValue(json['status']),
        currencyCode: stringValue(json['currency_code']),
        exchangeRate: stringValue(json['exchange_rate']),
        grandTotal: stringValue(json['grand_total']),
        baseGrandTotal: stringValue(json['base_grand_total']),
      );

  final String id;
  final String invoiceNumber;
  final String supplierInvoiceNumber;
  final String invoiceDate;
  final String status;
  final String currencyCode;
  final String exchangeRate;
  final String grandTotal;
  final String baseGrandTotal;
}

/// A goods receipt the imported goods arrived on.
class BoeReceiptLink {
  const BoeReceiptLink({
    required this.id,
    this.grnNumber = '',
    this.receiptDate = '',
    this.status = '',
    this.viaInvoice = false,
  });

  factory BoeReceiptLink.fromJson(Json json) => BoeReceiptLink(
        id: stringValue(json['goods_receipt_id']),
        grnNumber: stringValue(json['grn_number']),
        receiptDate: stringValue(json['receipt_date']),
        status: stringValue(json['status']),
        viaInvoice: json['via_invoice'] == true,
      );

  final String id;
  final String grnNumber;
  final String receiptDate;
  final String status;

  /// Linked through a bill it was raised for, rather than named itself.
  final bool viaInvoice;
}

/// One item of a Bill of Entry: what was typed, and what the server worked
/// out from it.
class BoeLine {
  const BoeLine({
    required this.id,
    this.lineNumber = 0,
    this.productId = '',
    this.productCode = '',
    this.productName = '',
    this.quantity = '',
    this.assessableValue = '',
    this.bcdRate = '',
    this.bcdAmount = '',
    this.swsRate = '',
    this.swsAmount = '',
    this.igstRate = '',
    this.igstAmount = '',
    this.cessAmount = '',
    this.igstBase = '',
    this.totalDuty = '',
    this.inventoryAmount = '',
    this.cogsAmount = '',
    this.expenseAmount = '',
  });

  factory BoeLine.fromJson(Json json) => BoeLine(
        id: stringValue(json['id']),
        lineNumber: _int(json['line_number']),
        productId: stringValue(json['product_id']),
        productCode: stringValue(json['product_code']),
        productName: stringValue(json['product_name']),
        quantity: stringValue(json['quantity']),
        assessableValue: stringValue(json['assessable_value']),
        bcdRate: stringValue(json['bcd_rate']),
        bcdAmount: stringValue(json['bcd_amount']),
        swsRate: stringValue(json['sws_rate']),
        swsAmount: stringValue(json['sws_amount']),
        igstRate: stringValue(json['igst_rate']),
        igstAmount: stringValue(json['igst_amount']),
        cessAmount: stringValue(json['cess_amount']),
        igstBase: stringValue(json['igst_base']),
        totalDuty: stringValue(json['total_duty']),
        inventoryAmount: stringValue(json['inventory_amount']),
        cogsAmount: stringValue(json['cogs_amount']),
        expenseAmount: stringValue(json['expense_amount']),
      );

  final String id;
  final int lineNumber;
  final String productId;
  final String productCode;
  final String productName;
  final String quantity;
  final String assessableValue;
  final String bcdRate;
  final String bcdAmount;
  final String swsRate;
  final String swsAmount;
  final String igstRate;
  final String igstAmount;
  final String cessAmount;

  /// Worked out by the server: read only.
  final String igstBase;
  final String totalDuty;
  final String inventoryAmount;
  final String cogsAmount;
  final String expenseAmount;
}

/// A Bill of Entry: the customs document that carries the duty on imported
/// goods into the landed cost (PG-12 part B).
class BillOfEntry {
  const BillOfEntry({
    required this.id,
    this.documentNumber = '',
    this.boeNumber = '',
    this.boeDate = '',
    this.portCode = '',
    this.vendorId = '',
    this.vendorCode = '',
    this.vendorName = '',
    this.branchId = '',
    this.currencyCode = '',
    this.exchangeRate = '',
    this.assessableValue = '',
    this.basicCustomsDuty = '',
    this.socialWelfareSurcharge = '',
    this.customsDuty = '',
    this.igstAmount = '',
    this.cessAmount = '',
    this.totalDuty = '',
    this.inventoryAmount = '',
    this.cogsAmount = '',
    this.expenseAmount = '',
    this.status = 'DRAFT',
    this.postedAt = '',
    this.journalEntryId = '',
    this.remarks = '',
    this.cancelReason = '',
    this.version = 0,
    this.invoices = const [],
    this.receipts = const [],
    this.lines = const [],
  });

  factory BillOfEntry.fromJson(Json json) => BillOfEntry(
        id: stringValue(json['id']),
        documentNumber: stringValue(json['document_number']),
        boeNumber: stringValue(json['boe_number']),
        boeDate: stringValue(json['boe_date']),
        portCode: stringValue(json['port_code']),
        vendorId: stringValue(json['vendor_id']),
        vendorCode: stringValue(json['vendor_code']),
        vendorName: stringValue(json['vendor_name']),
        branchId: stringValue(json['branch_id']),
        currencyCode: stringValue(json['currency_code']),
        exchangeRate: stringValue(json['exchange_rate']),
        assessableValue: stringValue(json['assessable_value']),
        basicCustomsDuty: stringValue(json['basic_customs_duty']),
        socialWelfareSurcharge: stringValue(json['social_welfare_surcharge']),
        customsDuty: stringValue(json['customs_duty']),
        igstAmount: stringValue(json['igst_amount']),
        cessAmount: stringValue(json['cess_amount']),
        totalDuty: stringValue(json['total_duty']),
        inventoryAmount: stringValue(json['inventory_amount']),
        cogsAmount: stringValue(json['cogs_amount']),
        expenseAmount: stringValue(json['expense_amount']),
        status: stringValue(json['status']).isEmpty
            ? 'DRAFT'
            : stringValue(json['status']),
        postedAt: stringValue(json['posted_at']),
        journalEntryId: stringValue(json['journal_entry_id']),
        remarks: stringValue(json['remarks']),
        cancelReason: stringValue(json['cancel_reason']),
        version: _int(json['version']),
        invoices: [
          for (final Object? row
              in json['purchase_invoices'] as List? ?? const [])
            if (row is Map)
              BoeInvoiceLink.fromJson(Map<String, dynamic>.from(row)),
        ],
        receipts: [
          for (final Object? row in json['goods_receipts'] as List? ?? const [])
            if (row is Map)
              BoeReceiptLink.fromJson(Map<String, dynamic>.from(row)),
        ],
        lines: [
          for (final Object? row in json['lines'] as List? ?? const [])
            if (row is Map) BoeLine.fromJson(Map<String, dynamic>.from(row)),
        ],
      );

  final String id;
  final String documentNumber;
  final String boeNumber;
  final String boeDate;
  final String portCode;
  final String vendorId;
  final String vendorCode;
  final String vendorName;
  final String branchId;
  final String currencyCode;
  final String exchangeRate;
  final String assessableValue;
  final String basicCustomsDuty;
  final String socialWelfareSurcharge;
  final String customsDuty;
  final String igstAmount;
  final String cessAmount;
  final String totalDuty;
  final String inventoryAmount;
  final String cogsAmount;
  final String expenseAmount;
  final String status;
  final String postedAt;
  final String journalEntryId;
  final String remarks;
  final String cancelReason;
  final int version;
  final List<BoeInvoiceLink> invoices;
  final List<BoeReceiptLink> receipts;
  final List<BoeLine> lines;

  bool get isDraft => status == 'DRAFT';
  bool get isPosted => status == 'POSTED';
  bool get isCancelled => status == 'CANCELLED';

  /// The number people know it by.
  String get label => documentNumber.isEmpty ? boeNumber : documentNumber;
}
