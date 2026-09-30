import 'entities.dart';

/// One bill a supplier was owed on the firm's first day here -- entered once,
/// at cutover, so the supplier's balance here matches the old books without
/// re-keying every historical purchase invoice.
///
/// `paidAmount` and `outstandingAmount` are derived by the server on every
/// read from `settlement_allocations`, never stored, so nothing here writes
/// them back.
class VendorOpeningBill {
  const VendorOpeningBill({
    required this.id,
    required this.version,
    required this.vendorId,
    required this.vendorCode,
    required this.vendorName,
    required this.billNumber,
    required this.referenceNumber,
    required this.billDate,
    required this.dueDate,
    required this.postingDate,
    required this.amount,
    required this.paidAmount,
    required this.outstandingAmount,
    required this.narration,
    required this.status,
    required this.cancellationReason,
  });

  final String id;
  final int version;
  final String vendorId;
  final String vendorCode;
  final String vendorName;

  /// The series this module's own numbering minted -- "OB-00001" -- separate
  /// from a purchase invoice number, because this is not one.
  final String billNumber;

  /// The supplier's own bill number, as the old books held it.
  final String referenceNumber;
  final String billDate;
  final String dueDate;

  /// The day the firm's books here start -- the cutover day.
  final String postingDate;

  /// What was still owed on the bill at cutover.
  final String amount;
  final String paidAmount;
  final String outstandingAmount;
  final String narration;

  /// POSTED or CANCELLED.
  final String status;
  final String cancellationReason;

  bool get isCancelled => status == 'CANCELLED';

  double get outstanding => double.tryParse(outstandingAmount) ?? 0;
  double get paid => double.tryParse(paidAmount) ?? 0;

  /// A cancellation is refused server-side once anything has been paid
  /// against the bill, so the action is offered here on the same condition.
  bool get canCancel => !isCancelled && paid <= 0;

  factory VendorOpeningBill.fromJson(Json json) => VendorOpeningBill(
        id: stringValue(json['id']),
        version: (json['version'] as num?)?.toInt() ?? 0,
        vendorId: stringValue(json['vendor_id']),
        vendorCode: stringValue(json['vendor_code']),
        vendorName: stringValue(json['vendor_name']),
        billNumber: stringValue(json['bill_number']),
        referenceNumber: stringValue(json['reference_number']),
        billDate: stringValue(json['bill_date']),
        dueDate: stringValue(json['due_date']),
        postingDate: stringValue(json['posting_date']),
        amount: stringValue(json['amount']),
        paidAmount: stringValue(json['paid_amount']),
        outstandingAmount: stringValue(json['outstanding_amount']),
        narration: stringValue(json['narration']),
        status: stringValue(json['status']),
        cancellationReason: stringValue(json['cancellation_reason']),
      );
}
