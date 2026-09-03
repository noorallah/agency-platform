import 'entities.dart';

/// One invoice a settlement cleared, and by how much.
class SettlementAllocation {
  const SettlementAllocation({
    required this.id,
    required this.invoiceId,
    required this.invoiceNumber,
    required this.invoiceDate,
    required this.invoiceTotal,
    required this.amount,
  });

  final String id;
  final String invoiceId;
  final String invoiceNumber;
  final String invoiceDate;
  final String invoiceTotal;
  final String amount;

  factory SettlementAllocation.fromJson(Json json) => SettlementAllocation(
        id: stringValue(json['id']),
        invoiceId: stringValue(json['invoice_id']),
        invoiceNumber: stringValue(json['invoice_number']),
        invoiceDate: stringValue(json['invoice_date']),
        invoiceTotal: stringValue(json['invoice_total']),
        amount: stringValue(json['amount']),
      );
}

/// Money that arrived from a customer, or went out to a vendor.
class Settlement {
  const Settlement({
    required this.id,
    required this.direction,
    required this.partyId,
    required this.partyCode,
    required this.partyName,
    required this.settlementNumber,
    required this.settlementDate,
    required this.amount,
    required this.allocatedAmount,
    required this.unallocatedAmount,
    required this.method,
    required this.ledgerAccountName,
    required this.instrumentReference,
    required this.narration,
    required this.status,
    required this.journalEntryId,
    required this.reversalReason,
    required this.allocations,
    this.salesOrderNumber = '',
  });

  final String id;
  final String direction;
  final String partyId;
  final String partyCode;
  final String partyName;
  final String settlementNumber;
  final String settlementDate;
  final String amount;
  final String allocatedAmount;

  /// Money not tied to any invoice. It still reached the ledger and still
  /// reduced what the party owes in total; what it did not do is claim to have
  /// settled a particular document.
  final String unallocatedAmount;
  final String method;
  final String ledgerAccountName;
  final String instrumentReference;
  final String narration;
  final String status;

  /// The journal this wrote. Every settlement has one -- a settlement that did
  /// not reach the ledger is the thing the module exists to prevent.
  final String journalEntryId;
  final String reversalReason;
  final List<SettlementAllocation> allocations;

  /// The order this money came in against, where it came in against one. A
  /// note about why it arrived, not a ring-fence: cancelling the order does
  /// not make the deposit vanish.
  final String salesOrderNumber;

  /// Taken back. The original stays and a mirror journal cancels it, so a
  /// reversed settlement is still a record of money that arrived and was then
  /// unrecorded -- not an absence.
  bool get isReversed => status == 'REVERSED';

  bool get isOnAccount =>
      !isReversed && (double.tryParse(unallocatedAmount) ?? 0) > 0;

  factory Settlement.fromJson(Json json) {
    final Json d =
        json.containsKey('data') ? Map<String, dynamic>.from(json['data'] as Map) : json;
    final dynamic rows = d['allocations'];
    return Settlement(
      id: stringValue(d['id']),
      direction: stringValue(d['direction']),
      partyId: stringValue(d['party_id']),
      partyCode: stringValue(d['party_code']),
      partyName: stringValue(d['party_name']),
      settlementNumber: stringValue(d['settlement_number']),
      settlementDate: stringValue(d['settlement_date']),
      salesOrderNumber: stringValue(d['sales_order_number']),
      amount: stringValue(d['amount']),
      allocatedAmount: stringValue(d['allocated_amount']),
      unallocatedAmount: stringValue(d['unallocated_amount']),
      method: stringValue(d['method']),
      ledgerAccountName: stringValue(d['ledger_account_name']),
      instrumentReference: stringValue(d['instrument_reference']),
      narration: stringValue(d['narration']),
      status: stringValue(d['status']),
      journalEntryId: stringValue(d['journal_entry_id']),
      reversalReason: stringValue(d['reversal_reason']),
      allocations: [
        for (final dynamic row in rows is List ? rows : const [])
          if (row is Map)
            SettlementAllocation.fromJson(Map<String, dynamic>.from(row)),
      ],
    );
  }
}

/// One invoice with what is still owed on it.
class OutstandingInvoice {
  const OutstandingInvoice({
    required this.invoiceId,
    required this.invoiceNumber,
    required this.invoiceDate,
    required this.invoiceTotal,
    required this.allocatedAmount,
    required this.outstandingAmount,
  });

  final String invoiceId;
  final String invoiceNumber;
  final String invoiceDate;
  final String invoiceTotal;
  final String allocatedAmount;
  final String outstandingAmount;

  double get outstanding => double.tryParse(outstandingAmount) ?? 0;

  factory OutstandingInvoice.fromJson(Json json) => OutstandingInvoice(
        invoiceId: stringValue(json['invoice_id']),
        invoiceNumber: stringValue(json['invoice_number']),
        invoiceDate: stringValue(json['invoice_date']),
        invoiceTotal: stringValue(json['invoice_total']),
        allocatedAmount: stringValue(json['allocated_amount']),
        outstandingAmount: stringValue(json['outstanding_amount']),
      );
}

/// Spread an amount across invoices, oldest first.
///
/// This is what a cashier does by hand with a stack of invoices and a cheque,
/// and getting it wrong is tedious rather than interesting. Anything left over
/// when the invoices run out stays on account, which is a real outcome rather
/// than an error: a customer may well pay more than they currently owe.
Map<String, String> allocateOldestFirst(
  List<OutstandingInvoice> invoices,
  String amount,
) {
  double remaining = double.tryParse(amount) ?? 0;
  final Map<String, String> allocation = {};
  for (final OutstandingInvoice invoice in invoices) {
    if (remaining <= 0) break;
    final double take =
        remaining >= invoice.outstanding ? invoice.outstanding : remaining;
    if (take <= 0) continue;
    allocation[invoice.invoiceId] = take.toStringAsFixed(2);
    remaining -= take;
  }
  return allocation;
}
