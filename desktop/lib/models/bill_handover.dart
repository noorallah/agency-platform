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
    this.returnId,
    this.returnOutcome,
    this.returnAmount,
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

  /// Today's end-of-day line on this bill (M6); null where there is none.
  final String? returnId;
  final String? returnOutcome;
  final String? returnAmount;

  /// True when the collector has already stated today's line.
  bool get hasLine => returnId != null;

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
        returnId: json['return_id'] as String?,
        returnOutcome: json['return_outcome'] as String?,
        returnAmount: json['return_amount'] == null
            ? null
            : stringValue(json['return_amount']),
      );
}

/// The four things a collector can say about a bill at the end of the day.
const List<String> returnOutcomes = [
  'COLLECTED',
  'PART',
  'PROMISED',
  'NOT_COLLECTED',
];

/// An outcome in plain words.
String returnOutcomeWords(String? outcome) => switch (outcome) {
      'COLLECTED' => 'Collected',
      'PART' => 'Part collected',
      'PROMISED' => 'Promised',
      'NOT_COLLECTED' => 'Not collected',
      _ => outcome ?? '',
    };

/// One end-of-day line on a bill handed to a collector (M6).
///
/// Read from `/api/v1/collections/my-bills/returns` and `/returns`. The line
/// states what the collector took; the money enters the books as a receipt.
class CollectionReturnLine {
  const CollectionReturnLine({
    required this.id,
    this.handoverId = '',
    this.returnDate = '',
    this.outcome = '',
    this.invoiceId = '',
    this.invoiceNumber = '',
    this.isOpeningBill = false,
    this.customerId = '',
    this.customerCode = '',
    this.customerName = '',
    this.collectorId = '',
    this.collectorName = '',
    this.outstandingBefore = '',
    this.amountCollected = '',
    this.paymentMode,
    this.instrumentReference,
    this.settlementId,
    this.settlementNumber,
    this.receiptAmount = '',
    this.receiptReversed = false,
    this.paymentPromiseId,
    this.promisedOn,
    this.promisedAmount,
    this.note,
    this.recordedBy = '',
    this.recordedByName = '',
    this.cancelledAt,
    this.cancelReason,
    this.version = 0,
  });

  final String id;
  final String handoverId;
  final String returnDate;
  final String outcome;
  final String invoiceId;
  final String invoiceNumber;
  final bool isOpeningBill;
  final String customerId;
  final String customerCode;
  final String customerName;
  final String collectorId;
  final String collectorName;
  final String outstandingBefore;
  final String amountCollected;
  final String? paymentMode;
  final String? instrumentReference;
  final String? settlementId;
  final String? settlementNumber;
  final String receiptAmount;
  final bool receiptReversed;
  final String? paymentPromiseId;
  final String? promisedOn;
  final String? promisedAmount;
  final String? note;
  final String recordedBy;
  final String recordedByName;
  final String? cancelledAt;
  final String? cancelReason;
  final int version;

  /// The money the line states, as a number.
  double get stated => double.tryParse(amountCollected) ?? 0;

  /// True while the line states money that no live receipt covers.
  bool get needsReceipt =>
      stated > 0 && (settlementId == null || receiptReversed);

  factory CollectionReturnLine.fromJson(Json json) => CollectionReturnLine(
        id: stringValue(json['id']),
        handoverId: stringValue(json['handover_id']),
        returnDate: stringValue(json['return_date']),
        outcome: stringValue(json['outcome']),
        invoiceId: stringValue(json['invoice_id']),
        invoiceNumber: stringValue(json['invoice_number']),
        isOpeningBill: boolValue(json['is_opening_bill']),
        customerId: stringValue(json['customer_id']),
        customerCode: stringValue(json['customer_code']),
        customerName: stringValue(json['customer_name']),
        collectorId: stringValue(json['collector_id']),
        collectorName: stringValue(json['collector_name']),
        outstandingBefore: stringValue(json['outstanding_before']),
        amountCollected: stringValue(json['amount_collected']),
        paymentMode: json['payment_mode'] as String?,
        instrumentReference: json['instrument_reference'] as String?,
        settlementId: json['settlement_id'] as String?,
        settlementNumber: json['settlement_number'] as String?,
        receiptAmount: stringValue(json['receipt_amount']),
        receiptReversed: boolValue(json['receipt_reversed']),
        paymentPromiseId: json['payment_promise_id'] as String?,
        promisedOn: json['promised_on'] as String?,
        promisedAmount: json['promised_amount'] == null
            ? null
            : stringValue(json['promised_amount']),
        note: json['note'] as String?,
        recordedBy: stringValue(json['recorded_by']),
        recordedByName: stringValue(json['recorded_by_name']),
        cancelledAt: json['cancelled_at'] as String?,
        cancelReason: json['cancel_reason'] as String?,
        version: (json['version'] as num?)?.toInt() ?? 0,
      );
}

/// A day's lines for one collector or for all, and whether the money stated
/// matches the money in receipts (M6).
class CollectionDaySheet {
  const CollectionDaySheet({
    this.day = '',
    this.collectorId,
    this.collectorName,
    this.collectorRecordsReceipt = false,
    this.rows = const [],
    this.collectedBills = 0,
    this.partBills = 0,
    this.promisedBills = 0,
    this.notCollectedBills = 0,
    this.billsWithoutALine = 0,
    this.amountStated = '0.00',
    this.amountReceipted = '0.00',
    this.amountNotReceipted = '0.00',
    this.addsUp = true,
  });

  final String day;
  final String? collectorId;
  final String? collectorName;
  final bool collectorRecordsReceipt;
  final List<CollectionReturnLine> rows;
  final int collectedBills;
  final int partBills;
  final int promisedBills;
  final int notCollectedBills;
  final int billsWithoutALine;
  final String amountStated;
  final String amountReceipted;
  final String amountNotReceipted;
  final bool addsUp;

  double get stated => double.tryParse(amountStated) ?? 0;
  double get receipted => double.tryParse(amountReceipted) ?? 0;
  double get notReceipted => double.tryParse(amountNotReceipted) ?? 0;

  factory CollectionDaySheet.fromJson(Json json) => CollectionDaySheet(
        day: stringValue(json['day']),
        collectorId: json['collector_id'] as String?,
        collectorName: json['collector_name'] as String?,
        collectorRecordsReceipt: boolValue(json['collector_records_receipt']),
        rows: [
          for (final dynamic item in (json['rows'] as List? ?? const []))
            if (item is Map)
              CollectionReturnLine.fromJson(Map<String, dynamic>.from(item)),
        ],
        collectedBills: (json['collected_bills'] as num?)?.toInt() ?? 0,
        partBills: (json['part_bills'] as num?)?.toInt() ?? 0,
        promisedBills: (json['promised_bills'] as num?)?.toInt() ?? 0,
        notCollectedBills: (json['not_collected_bills'] as num?)?.toInt() ?? 0,
        billsWithoutALine: (json['bills_without_a_line'] as num?)?.toInt() ?? 0,
        amountStated: stringValue(json['amount_stated']),
        amountReceipted: stringValue(json['amount_receipted']),
        amountNotReceipted: stringValue(json['amount_not_receipted']),
        addsUp: json['adds_up'] == null ? true : boolValue(json['adds_up']),
      );
}
