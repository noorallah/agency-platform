import 'entities.dart';

/// One bill a customer owed the firm on its first day here -- entered once,
/// at cutover, so receipts can be set against the old bills and the ageing
/// counts each from its own due date. The receivable twin of
/// `VendorOpeningBill`.
///
/// `receivedAmount` and `outstandingAmount` are derived by the server on
/// every read from `settlement_allocations`, never stored, so nothing here
/// writes them back.
class CustomerOpeningBill {
  const CustomerOpeningBill({
    required this.id,
    required this.version,
    required this.customerId,
    required this.customerCode,
    required this.customerName,
    required this.billNumber,
    required this.referenceNumber,
    required this.billDate,
    required this.dueDate,
    required this.postingDate,
    required this.amount,
    required this.receivedAmount,
    required this.outstandingAmount,
    required this.narration,
    required this.status,
    required this.cancellationReason,
  });

  final String id;
  final int version;
  final String customerId;
  final String customerCode;
  final String customerName;

  /// This module's own series -- "OBC-00001" -- separate from a sales invoice
  /// number, because this is not one.
  final String billNumber;

  /// The bill's number as the old books held it.
  final String referenceNumber;
  final String billDate;

  /// Given, or the bill date plus the customer's payment terms.
  final String dueDate;

  /// The day the firm's books here start -- the cutover day.
  final String postingDate;

  /// What was still owed on the bill at cutover.
  final String amount;
  final String receivedAmount;
  final String outstandingAmount;
  final String narration;

  /// POSTED or CANCELLED.
  final String status;
  final String cancellationReason;

  bool get isCancelled => status == 'CANCELLED';

  double get outstanding => double.tryParse(outstandingAmount) ?? 0;
  double get received => double.tryParse(receivedAmount) ?? 0;

  /// A cancellation is refused server-side once anything has been received
  /// against the bill, so the action is offered here on the same condition.
  bool get canCancel => !isCancelled && received <= 0;

  factory CustomerOpeningBill.fromJson(Json json) => CustomerOpeningBill(
        id: stringValue(json['id']),
        version: (json['version'] as num?)?.toInt() ?? 0,
        customerId: stringValue(json['customer_id']),
        customerCode: stringValue(json['customer_code']),
        customerName: stringValue(json['customer_name']),
        billNumber: stringValue(json['bill_number']),
        referenceNumber: stringValue(json['reference_number']),
        billDate: stringValue(json['bill_date']),
        dueDate: stringValue(json['due_date']),
        postingDate: stringValue(json['posting_date']),
        amount: stringValue(json['amount']),
        receivedAmount: stringValue(json['received_amount']),
        outstandingAmount: stringValue(json['outstanding_amount']),
        narration: stringValue(json['narration']),
        status: stringValue(json['status']),
        cancellationReason: stringValue(json['cancellation_reason']),
      );
}
