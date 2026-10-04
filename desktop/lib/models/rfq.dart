import 'entities.dart';

List<T> _list<T>(dynamic raw, T Function(Json) parse) => [
      for (final dynamic item in raw is List ? raw : const [])
        if (item is Map) parse(Map<String, dynamic>.from(item)),
    ];

int? _days(dynamic value) => value is num ? value.toInt() : null;

int _int(dynamic value) => value is int ? value : 0;

/// One product asked about on a request for quotation (PG-8).
class RfqLine {
  const RfqLine({
    this.id = '',
    this.lineNumber = 0,
    required this.productId,
    this.productCode = '',
    this.productName = '',
    required this.quantity,
    this.uomId = '',
    this.notes = '',
  });

  factory RfqLine.fromJson(Json json) => RfqLine(
        id: stringValue(json['id']),
        lineNumber: _int(json['line_number']),
        productId: stringValue(json['product_id']),
        productCode: stringValue(json['product_code']),
        productName: stringValue(json['product_name']),
        quantity: stringValue(json['quantity']),
        uomId: stringValue(json['uom_id']),
        notes: stringValue(json['notes']),
      );

  final String id;
  final int lineNumber;
  final String productId;
  final String productCode;
  final String productName;
  final String quantity;
  final String uomId;
  final String notes;
}

/// A supplier invited to quote.
class RfqSupplier {
  const RfqSupplier({
    this.id = '',
    required this.vendorId,
    this.vendorCode = '',
    this.vendorName = '',
    this.quotationId = '',
    this.purchaseOrderId = '',
  });

  factory RfqSupplier.fromJson(Json json) => RfqSupplier(
        id: stringValue(json['id']),
        vendorId: stringValue(json['vendor_id']),
        vendorCode: stringValue(json['vendor_code']),
        vendorName: stringValue(json['vendor_name']),
        quotationId: stringValue(json['quotation_id']),
        purchaseOrderId: stringValue(json['purchase_order_id']),
      );

  final String id;
  final String vendorId;
  final String vendorCode;
  final String vendorName;
  final String quotationId;
  final String purchaseOrderId;
}

/// A request for quotation sent to several suppliers.
class Rfq {
  const Rfq({
    required this.id,
    this.number = '',
    this.date = '',
    this.requiredBy = '',
    this.branchId = '',
    this.warehouseId = '',
    required this.status,
    this.notes = '',
    this.cancelReason = '',
    this.version = 0,
    this.lines = const [],
    this.suppliers = const [],
  });

  factory Rfq.fromJson(Json json) => Rfq(
        id: stringValue(json['id']),
        number: stringValue(json['rfq_number']),
        date: stringValue(json['rfq_date']),
        requiredBy: stringValue(json['required_by']),
        branchId: stringValue(json['branch_id']),
        warehouseId: stringValue(json['warehouse_id']),
        status: stringValue(json['status']),
        notes: stringValue(json['notes']),
        cancelReason: stringValue(json['cancel_reason']),
        version: _int(json['version']),
        lines: _list(json['lines'], RfqLine.fromJson),
        suppliers: _list(json['suppliers'], RfqSupplier.fromJson),
      );

  final String id;
  final String number;
  final String date;
  final String requiredBy;
  final String branchId;
  final String warehouseId;
  final String status;
  final String notes;
  final String cancelReason;
  final int version;
  final List<RfqLine> lines;
  final List<RfqSupplier> suppliers;

  bool get isDraft => status == 'DRAFT';
  bool get isSent => status == 'SENT';
}

/// One supplier's price for one RFQ line.
class QuotationLine {
  const QuotationLine({
    this.id = '',
    required this.rfqLineId,
    this.rate = '',
    this.discountPercent = '',
    this.landedRate = '',
    this.leadTimeDays,
    this.notes = '',
  });

  factory QuotationLine.fromJson(Json json) => QuotationLine(
        id: stringValue(json['id']),
        rfqLineId: stringValue(json['rfq_line_id']),
        rate: stringValue(json['rate']),
        discountPercent: stringValue(json['discount_percent']),
        landedRate: stringValue(json['landed_rate']),
        leadTimeDays: _days(json['lead_time_days']),
        notes: stringValue(json['notes']),
      );

  final String id;
  final String rfqLineId;
  final String rate;
  final String discountPercent;
  final String landedRate;
  final int? leadTimeDays;
  final String notes;
}

/// What one supplier answered.
class SupplierQuotation {
  const SupplierQuotation({
    this.id = '',
    this.rfqId = '',
    required this.vendorId,
    this.vendorName = '',
    this.quoteRef = '',
    this.quoteDate = '',
    this.validUntil = '',
    this.notes = '',
    this.version = 0,
    this.lines = const [],
  });

  factory SupplierQuotation.fromJson(Json json) => SupplierQuotation(
        id: stringValue(json['id']),
        rfqId: stringValue(json['rfq_id']),
        vendorId: stringValue(json['vendor_id']),
        vendorName: stringValue(json['vendor_name']),
        quoteRef: stringValue(json['quote_ref']),
        quoteDate: stringValue(json['quote_date']),
        validUntil: stringValue(json['valid_until']),
        notes: stringValue(json['notes']),
        version: _int(json['version']),
        lines: _list(json['lines'], QuotationLine.fromJson),
      );

  final String id;
  final String rfqId;
  final String vendorId;
  final String vendorName;
  final String quoteRef;
  final String quoteDate;
  final String validUntil;
  final String notes;
  final int version;
  final List<QuotationLine> lines;
}

/// One supplier's cell in the comparison grid.
class ComparisonQuote {
  const ComparisonQuote({
    required this.quotationId,
    required this.quotationLineId,
    required this.vendorId,
    this.vendorName = '',
    this.rate = '',
    this.discountPercent = '',
    this.landedRate = '',
    this.leadTimeDays,
    this.validUntil = '',
    this.notes = '',
    this.isLowest = false,
  });

  factory ComparisonQuote.fromJson(Json json) => ComparisonQuote(
        quotationId: stringValue(json['quotation_id']),
        quotationLineId: stringValue(json['quotation_line_id']),
        vendorId: stringValue(json['vendor_id']),
        vendorName: stringValue(json['vendor_name']),
        rate: stringValue(json['rate']),
        discountPercent: stringValue(json['discount_percent']),
        landedRate: stringValue(json['landed_rate']),
        leadTimeDays: _days(json['lead_time_days']),
        validUntil: stringValue(json['valid_until']),
        notes: stringValue(json['notes']),
        isLowest: json['is_lowest'] == true,
      );

  final String quotationId;
  final String quotationLineId;
  final String vendorId;
  final String vendorName;
  final String rate;
  final String discountPercent;
  final String landedRate;
  final int? leadTimeDays;
  final String validUntil;
  final String notes;
  final bool isLowest;
}

/// One RFQ line with every quote it drew, cheapest first.
class ComparisonLine {
  const ComparisonLine({
    required this.rfqLineId,
    this.lineNumber = 0,
    this.productCode = '',
    this.productName = '',
    this.quantity = '',
    this.lowestQuotationLineId = '',
    this.selectedQuotationLineId = '',
    this.selectionReason = '',
    this.quotes = const [],
  });

  factory ComparisonLine.fromJson(Json json) => ComparisonLine(
        rfqLineId: stringValue(json['rfq_line_id']),
        lineNumber: _int(json['line_number']),
        productCode: stringValue(json['product_code']),
        productName: stringValue(json['product_name']),
        quantity: stringValue(json['quantity']),
        lowestQuotationLineId: stringValue(json['lowest_quotation_line_id']),
        selectedQuotationLineId:
            stringValue(json['selected_quotation_line_id']),
        selectionReason: stringValue(json['selection_reason']),
        quotes: _list(json['quotes'], ComparisonQuote.fromJson),
      );

  final String rfqLineId;
  final int lineNumber;
  final String productCode;
  final String productName;
  final String quantity;
  final String lowestQuotationLineId;
  final String selectedQuotationLineId;
  final String selectionReason;
  final List<ComparisonQuote> quotes;
}

/// The side-by-side comparison of an RFQ's quotes.
class RfqComparison {
  const RfqComparison({
    required this.rfqId,
    this.number = '',
    this.status = '',
    this.version = 0,
    this.lines = const [],
  });

  factory RfqComparison.fromJson(Json json) => RfqComparison(
        rfqId: stringValue(json['rfq_id']),
        number: stringValue(json['rfq_number']),
        status: stringValue(json['status']),
        version: _int(json['version']),
        lines: _list(json['lines'], ComparisonLine.fromJson),
      );

  final String rfqId;
  final String number;
  final String status;
  final int version;
  final List<ComparisonLine> lines;
}
