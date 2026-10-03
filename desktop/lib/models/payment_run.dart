import 'entities.dart';

/// One supplier bill the proposal offers for a payment run (BUY-11).
class PaymentRunBill {
  const PaymentRunBill({
    required this.invoiceId,
    required this.invoiceNumber,
    required this.invoiceDate,
    required this.dueDate,
    required this.partyId,
    required this.outstandingAmount,
    this.isOpeningBill = false,
  });

  final String invoiceId;
  final String invoiceNumber;
  final String invoiceDate;
  final String dueDate;
  final String partyId;
  final String outstandingAmount;
  final bool isOpeningBill;

  factory PaymentRunBill.fromJson(Json json) => PaymentRunBill(
        invoiceId: stringValue(json['invoice_id']),
        invoiceNumber: stringValue(json['invoice_number']),
        invoiceDate: stringValue(json['invoice_date']),
        dueDate: stringValue(json['due_date']),
        partyId: stringValue(json['party_id']),
        outstandingAmount: stringValue(json['outstanding_amount']),
        isOpeningBill: boolValue(json['is_opening_bill'], fallback: false),
      );
}

/// One bill inside a saved run.
class PaymentRunLine {
  const PaymentRunLine({
    required this.id,
    required this.vendorId,
    required this.vendorName,
    required this.invoiceId,
    required this.invoiceNumber,
    required this.amount,
    this.isOpeningBill = false,
  });

  final String id;
  final String vendorId;
  final String vendorName;
  final String invoiceId;
  final String invoiceNumber;
  final String amount;
  final bool isOpeningBill;

  factory PaymentRunLine.fromJson(Json json) => PaymentRunLine(
        id: stringValue(json['id']),
        vendorId: stringValue(json['vendor_id']),
        vendorName: stringValue(json['vendor_name']),
        invoiceId: stringValue(json['invoice_id']),
        invoiceNumber: stringValue(json['invoice_number']),
        amount: stringValue(json['amount']),
        isOpeningBill: boolValue(json['is_opening_bill'], fallback: false),
      );
}

/// A batch of supplier bills paid together: a draft until it is approved, when
/// one bank payment per supplier is recorded.
class PaymentRun {
  const PaymentRun({
    required this.id,
    required this.runNumber,
    required this.paymentDate,
    required this.status,
    required this.total,
    this.dueBy = '',
    this.remarks = '',
    this.cancelReason = '',
    this.version = 0,
    this.lines = const <PaymentRunLine>[],
  });

  final String id;
  final String runNumber;
  final String paymentDate;
  final String dueBy;

  /// `DRAFT`, `APPROVED` or `CANCELLED`.
  final String status;
  final String total;
  final String remarks;
  final String cancelReason;
  final int version;
  final List<PaymentRunLine> lines;

  bool get isDraft => status == 'DRAFT';
  bool get isApproved => status == 'APPROVED';

  int get supplierCount => lines.map((line) => line.vendorId).toSet().length;

  factory PaymentRun.fromJson(Json json) => PaymentRun(
        id: stringValue(json['id']),
        runNumber: stringValue(json['run_number']),
        paymentDate: stringValue(json['payment_date']),
        dueBy: stringValue(json['due_by']),
        status: stringValue(json['status']),
        total: stringValue(json['total']),
        remarks: stringValue(json['remarks']),
        cancelReason: stringValue(json['cancel_reason']),
        version: json['version'] is int ? json['version'] as int : 0,
        lines: json['lines'] is List
            ? (json['lines'] as List)
                .whereType<Map>()
                .map((row) =>
                    PaymentRunLine.fromJson(Map<String, dynamic>.from(row)))
                .toList()
            : const <PaymentRunLine>[],
      );
}
