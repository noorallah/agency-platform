import 'entities.dart';

/// One unpaid bill, as listed for handing to a collector (backlog 122).
///
/// Read from `GET /api/v1/collections/handovers/bills`. [handoverId] is null
/// while the bill is in the office.
class HandoverBill {
  const HandoverBill({
    required this.invoiceId,
    this.invoiceNumber = '',
    this.invoiceDate = '',
    this.dueDate = '',
    this.daysOverdue = 0,
    this.isOpeningBill = false,
    this.customerId = '',
    this.customerCode = '',
    this.customerName = '',
    this.customerPlace = '',
    this.invoiceTotal = '',
    this.outstanding = '',
    this.handoverId,
    this.collectorId,
    this.collectorName = '',
    this.handedOn = '',
  });

  final String invoiceId;
  final String invoiceNumber;
  final String invoiceDate;
  final String dueDate;
  final int daysOverdue;
  final bool isOpeningBill;
  final String customerId;
  final String customerCode;
  final String customerName;
  final String customerPlace;
  final String invoiceTotal;
  final String outstanding;
  final String? handoverId;
  final String? collectorId;
  final String collectorName;
  final String handedOn;

  /// True while somebody is carrying the bill.
  bool get isOut => handoverId != null;

  /// The customer's name, with "· place" after it when there is one.
  String get customerLabel =>
      customerPlace.isEmpty ? customerName : '$customerName · $customerPlace';

  factory HandoverBill.fromJson(Json json) => HandoverBill(
        invoiceId: stringValue(json['invoice_id']),
        invoiceNumber: stringValue(json['invoice_number']),
        invoiceDate: stringValue(json['invoice_date']),
        dueDate: stringValue(json['due_date']),
        daysOverdue: (json['days_overdue'] as num?)?.toInt() ?? 0,
        isOpeningBill: boolValue(json['is_opening_bill']),
        customerId: stringValue(json['customer_id']),
        customerCode: stringValue(json['customer_code']),
        customerName: stringValue(json['customer_name']),
        customerPlace: stringValue(json['customer_place']),
        invoiceTotal: stringValue(json['invoice_total']),
        outstanding: stringValue(json['outstanding']),
        handoverId: json['handover_id'] as String?,
        collectorId: json['collector_id'] as String?,
        collectorName: stringValue(json['collector_name']),
        handedOn: stringValue(json['handed_on']),
      );
}

/// One handing-over on record: out with a collector, or taken back.
///
/// Read from `GET /api/v1/collections/handovers`.
class BillHandover {
  const BillHandover({
    required this.id,
    this.state = '',
    this.invoiceId = '',
    this.invoiceNumber = '',
    this.invoiceDate = '',
    this.isOpeningBill = false,
    this.customerId = '',
    this.customerCode = '',
    this.customerName = '',
    this.customerPlace = '',
    this.collectorId = '',
    this.collectorName = '',
    this.handedOn = '',
    this.handedByName = '',
    this.outstandingAtHandover = '',
    this.outstanding = '',
    this.returnedAt = '',
    this.returnedByName = '',
    this.returnNote = '',
    this.version = 0,
  });

  final String id;
  final String state;
  final String invoiceId;
  final String invoiceNumber;
  final String invoiceDate;
  final bool isOpeningBill;
  final String customerId;
  final String customerCode;
  final String customerName;
  final String customerPlace;
  final String collectorId;
  final String collectorName;
  final String handedOn;
  final String handedByName;
  final String outstandingAtHandover;
  final String outstanding;
  final String returnedAt;
  final String returnedByName;
  final String returnNote;
  final int version;

  bool get isOut => state == 'OUT';

  String get customerLabel =>
      customerPlace.isEmpty ? customerName : '$customerName · $customerPlace';

  factory BillHandover.fromJson(Json json) => BillHandover(
        id: stringValue(json['id']),
        state: stringValue(json['state']),
        invoiceId: stringValue(json['invoice_id']),
        invoiceNumber: stringValue(json['invoice_number']),
        invoiceDate: stringValue(json['invoice_date']),
        isOpeningBill: boolValue(json['is_opening_bill']),
        customerId: stringValue(json['customer_id']),
        customerCode: stringValue(json['customer_code']),
        customerName: stringValue(json['customer_name']),
        customerPlace: stringValue(json['customer_place']),
        collectorId: stringValue(json['collector_id']),
        collectorName: stringValue(json['collector_name']),
        handedOn: stringValue(json['handed_on']),
        handedByName: stringValue(json['handed_by_name']),
        outstandingAtHandover: stringValue(json['outstanding_at_handover']),
        outstanding: stringValue(json['outstanding']),
        returnedAt: stringValue(json['returned_at']),
        returnedByName: stringValue(json['returned_by_name']),
        returnNote: stringValue(json['return_note']),
        version: (json['version'] as num?)?.toInt() ?? 0,
      );
}

/// One unpaid bill on the collector's own list (backlog 123).
///
/// Read from `GET /api/v1/collections/my-bills`. A bill with [handedToMe] is
/// one the office gave to the signed-in person; the others are further unpaid
/// bills of the same customers, listed beside them.
class MyBill {
  const MyBill({
    required this.invoiceId,
    this.invoiceNumber = '',
    this.invoiceDate = '',
    this.dueDate = '',
    this.daysOverdue = 0,
    this.isOpeningBill = false,
    this.customerId = '',
    this.customerCode = '',
    this.customerName = '',
    this.customerPlace = '',
    this.invoiceTotal = '',
    this.outstanding = '',
    this.handedToMe = false,
    this.handoverId,
    this.handedOn = '',
  });

  final String invoiceId;
  final String invoiceNumber;
  final String invoiceDate;
  final String dueDate;
  final int daysOverdue;
  final bool isOpeningBill;
  final String customerId;
  final String customerCode;
  final String customerName;
  final String customerPlace;
  final String invoiceTotal;
  final String outstanding;
  final bool handedToMe;
  final String? handoverId;
  final String handedOn;

  /// What is still owed, as a number for the totals.
  double get owed => double.tryParse(outstanding) ?? 0;

  /// The customer's name, with "· place" after it when there is one.
  String get customerLabel =>
      customerPlace.isEmpty ? customerName : '$customerName · $customerPlace';

  factory MyBill.fromJson(Json json) => MyBill(
        invoiceId: stringValue(json['invoice_id']),
        invoiceNumber: stringValue(json['invoice_number']),
        invoiceDate: stringValue(json['invoice_date']),
        dueDate: stringValue(json['due_date']),
        daysOverdue: (json['days_overdue'] as num?)?.toInt() ?? 0,
        isOpeningBill: boolValue(json['is_opening_bill']),
        customerId: stringValue(json['customer_id']),
        customerCode: stringValue(json['customer_code']),
        customerName: stringValue(json['customer_name']),
        customerPlace: stringValue(json['customer_place']),
        invoiceTotal: stringValue(json['invoice_total']),
        outstanding: stringValue(json['outstanding']),
        handedToMe: boolValue(json['handed_to_me']),
        handoverId: json['handover_id'] as String?,
        handedOn: stringValue(json['handed_on']),
      );
}
