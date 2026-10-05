import 'entities.dart';

/// What a customer promised to pay, and by when (backlog 87 #8, SG-8).
///
/// Read from `GET /api/v1/collections/promises`. [status] is derived on the
/// server from what has been received since: PENDING, DUE_TODAY, KEPT, BROKEN
/// or WITHDRAWN.
class PaymentPromise {
  const PaymentPromise({
    required this.id,
    required this.customerId,
    required this.customerName,
    this.salesInvoiceId,
    this.invoiceNumber = '',
    required this.promisedOn,
    required this.amount,
    this.receivedAmount = '0',
    required this.status,
    this.note = '',
    this.recordedOn = '',
    this.recordedByName = '',
    this.collectorId,
    this.collectorName = '',
    this.cancelReason = '',
    this.version = 0,
  });

  final String id;
  final String customerId;
  final String customerName;

  /// Null for a promise made on the account rather than on one bill.
  final String? salesInvoiceId;
  final String invoiceNumber;
  final String promisedOn;
  final String amount;
  final String receivedAmount;
  final String status;
  final String note;
  final String recordedOn;
  final String recordedByName;
  final String? collectorId;
  final String collectorName;
  final String cancelReason;
  final int version;

  /// A withdrawn or kept promise has nothing left to take back.
  bool get isOpen => status != 'WITHDRAWN' && status != 'KEPT';

  factory PaymentPromise.fromJson(Json json) => PaymentPromise(
        id: stringValue(json['id']),
        customerId: stringValue(json['customer_id']),
        customerName: stringValue(json['customer_name']),
        salesInvoiceId: json['sales_invoice_id'] as String?,
        invoiceNumber: stringValue(json['invoice_number']),
        promisedOn: stringValue(json['promised_on']),
        amount: stringValue(json['amount']),
        receivedAmount: stringValue(json['received_amount']),
        status: stringValue(json['status']),
        note: stringValue(json['note']),
        recordedOn: stringValue(json['recorded_on']),
        recordedByName: stringValue(json['recorded_by_name']),
        collectorId: json['collector_id'] as String?,
        collectorName: stringValue(json['collector_name']),
        cancelReason: stringValue(json['cancel_reason']),
        version: (json['version'] as num?)?.toInt() ?? 0,
      );
}

/// One line of the collection sheet: a bill still owing, with the promise
/// standing against it if there is one.
class CollectionSheetRow {
  const CollectionSheetRow({
    this.collectorId,
    this.collectorName = '',
    required this.customerId,
    this.customerCode = '',
    required this.customerName,
    this.customerPhone = '',
    this.invoiceId,
    this.invoiceNumber = '',
    this.invoiceDate = '',
    this.dueDate = '',
    this.daysOverdue = 0,
    this.invoiceTotal = '0',
    this.outstanding = '0',
    this.promiseId,
    this.promisedOn = '',
    this.promisedAmount = '',
    this.promiseStatus = '',
    this.promiseNote = '',
  });

  final String? collectorId;
  final String collectorName;
  final String customerId;
  final String customerCode;
  final String customerName;
  final String customerPhone;
  final String? invoiceId;
  final String invoiceNumber;
  final String invoiceDate;
  final String dueDate;
  final int daysOverdue;
  final String invoiceTotal;
  final String outstanding;
  final String? promiseId;
  final String promisedOn;
  final String promisedAmount;
  final String promiseStatus;
  final String promiseNote;

  /// Unique enough to select a row by: a customer's account-level line has no
  /// bill, so the bill id alone is not.
  String get rowId => '$customerId/${invoiceId ?? ''}/${promiseId ?? ''}';

  factory CollectionSheetRow.fromJson(Json json) => CollectionSheetRow(
        collectorId: json['collector_id'] as String?,
        collectorName: stringValue(json['collector_name']),
        customerId: stringValue(json['customer_id']),
        customerCode: stringValue(json['customer_code']),
        customerName: stringValue(json['customer_name']),
        customerPhone: stringValue(json['customer_phone']),
        invoiceId: json['invoice_id'] as String?,
        invoiceNumber: stringValue(json['invoice_number']),
        invoiceDate: stringValue(json['invoice_date']),
        dueDate: stringValue(json['due_date']),
        daysOverdue: (json['days_overdue'] as num?)?.toInt() ?? 0,
        invoiceTotal: stringValue(json['invoice_total']),
        outstanding: stringValue(json['outstanding']),
        promiseId: json['promise_id'] as String?,
        promisedOn: stringValue(json['promised_on']),
        promisedAmount: stringValue(json['promised_amount']),
        promiseStatus: stringValue(json['promise_status']),
        promiseNote: stringValue(json['promise_note']),
      );
}
