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
    this.allocatedOn = '',
  });

  final String id;
  final String invoiceId;
  final String invoiceNumber;
  final String invoiceDate;
  final String invoiceTotal;
  final String amount;

  /// The day the money met the bill: the bill's date, or the settlement's
  /// where that came later (D-TER-19).
  final String allocatedOn;

  factory SettlementAllocation.fromJson(Json json) => SettlementAllocation(
        id: stringValue(json['id']),
        invoiceId: stringValue(json['invoice_id']),
        invoiceNumber: stringValue(json['invoice_number']),
        invoiceDate: stringValue(json['invoice_date']),
        invoiceTotal: stringValue(json['invoice_total']),
        amount: stringValue(json['amount']),
        allocatedOn: stringValue(json['allocated_on']),
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
    this.paymentMode = '',
    this.instrumentDate = '',
    this.salesOrderNumber = '',
    this.tdsAmount = '0',
    this.tdsSection = '',
    this.roundingAmount = '0',
    this.bankChargesAmount = '0',
    this.discountAmount = '0',
    this.reportedCashAmount = '',
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

  /// How the money moved within its method (ACC-3): CASH, CHEQUE, UPI,
  /// BANK_TRANSFER, CARD, DEMAND_DRAFT or OTHER; empty on a bank settlement
  /// recorded before the mode was asked for.
  final String paymentMode;

  /// The cheque's or draft's own date.
  final String instrumentDate;

  /// The mode in words, or the method where no mode was recorded.
  String get modeLabel =>
      paymentModeLabels[paymentMode] ?? method;
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

  /// Tax deducted at source out of [amount] (backlog 53.1), and the section
  /// it is filed under. [amount] settles the party; the cash or bank moved
  /// [cashAmount].
  final String tdsAmount;
  final String tdsSection;

  /// What else came off [amount] before the money moved: a rounding or short
  /// payment, bank charges (receipts only) and a discount allowed or
  /// received. Like TDS they settle the party without being cash.
  final String roundingAmount;
  final String bankChargesAmount;
  final String discountAmount;

  /// The money moved as the server states it; blank on an older answer.
  final String reportedCashAmount;

  double get tdsValue => double.tryParse(tdsAmount) ?? 0;
  double get roundingValue => double.tryParse(roundingAmount) ?? 0;
  double get bankChargesValue => double.tryParse(bankChargesAmount) ?? 0;
  double get discountValue => double.tryParse(discountAmount) ?? 0;

  /// Whether anything but TDS came off the amount.
  bool get hasDeductions =>
      roundingValue > 0 || bankChargesValue > 0 || discountValue > 0;

  /// The money that actually moved: the amount less everything deducted.
  String get cashAmount => reportedCashAmount.isNotEmpty
      ? (double.tryParse(reportedCashAmount) ?? 0).toStringAsFixed(2)
      : ((double.tryParse(amount) ?? 0) -
              tdsValue -
              roundingValue -
              bankChargesValue -
              discountValue)
          .toStringAsFixed(2);

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
      tdsAmount: stringValue(d['tds_amount']).isEmpty
          ? '0'
          : stringValue(d['tds_amount']),
      tdsSection: stringValue(d['tds_section']),
      roundingAmount: stringValue(d['rounding_amount']).isEmpty
          ? '0'
          : stringValue(d['rounding_amount']),
      bankChargesAmount: stringValue(d['bank_charges_amount']).isEmpty
          ? '0'
          : stringValue(d['bank_charges_amount']),
      discountAmount: stringValue(d['discount_amount']).isEmpty
          ? '0'
          : stringValue(d['discount_amount']),
      reportedCashAmount: stringValue(d['cash_amount']),
      amount: stringValue(d['amount']),
      allocatedAmount: stringValue(d['allocated_amount']),
      unallocatedAmount: stringValue(d['unallocated_amount']),
      method: stringValue(d['method']),
      ledgerAccountName: stringValue(d['ledger_account_name']),
      instrumentReference: stringValue(d['instrument_reference']),
      paymentMode: stringValue(d['payment_mode']),
      instrumentDate: stringValue(d['instrument_date']),
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
    this.isOpeningBill = false,
  });

  final String invoiceId;
  final String invoiceNumber;
  final String invoiceDate;
  final String invoiceTotal;
  final String allocatedAmount;
  final String outstandingAmount;

  /// A bill the party owed, or was owed, before the firm started here --
  /// a customer's or a supplier's opening bill -- rather than a sales or
  /// purchase invoice. It is settled the same way here, but it is not an
  /// invoice and this screen must never try to open it as one.
  final bool isOpeningBill;

  double get outstanding => double.tryParse(outstandingAmount) ?? 0;

  factory OutstandingInvoice.fromJson(Json json) => OutstandingInvoice(
        invoiceId: stringValue(json['invoice_id']),
        invoiceNumber: stringValue(json['invoice_number']),
        invoiceDate: stringValue(json['invoice_date']),
        invoiceTotal: stringValue(json['invoice_total']),
        allocatedAmount: stringValue(json['allocated_amount']),
        outstandingAmount: stringValue(json['outstanding_amount']),
        isOpeningBill: boolValue(json['is_opening_bill'], fallback: false),
      );
}

/// What a purchase return raised from the goods receipt left on a
/// supplier's account: a credit the supplier owes the firm until it is set
/// against one of their bills (D-FIN-19).
class SupplierCredit {
  const SupplierCredit({
    required this.sourceId,
    this.sourceType = 'PURCHASE_RETURN',
    this.purchaseReturnId,
    this.debitNoteId,
    required this.returnNumber,
    required this.returnDate,
    required this.creditAmount,
    required this.appliedAmount,
    required this.availableAmount,
    required this.appliedTo,
    this.refundedAmount = '0.00',
    this.outcome = 'CREDIT',
  });

  /// The id every apply and refund call names: a purchase return's or a
  /// debit note's, whichever raised the credit (A4).
  final String sourceId;

  /// PURCHASE_RETURN or DEBIT_NOTE.
  final String sourceType;
  final String? purchaseReturnId;
  final String? debitNoteId;

  /// The source document's number and date, whichever kind it is.
  final String returnNumber;
  final String returnDate;
  final String creditAmount;
  final String appliedAmount;
  final String availableAmount;
  final List<String> appliedTo;

  /// Money the supplier handed back against this credit, and what the return
  /// came back as: CREDIT, REPLACEMENT or REFUND. `availableAmount` already
  /// nets the refunds.
  final String refundedAmount;
  final String outcome;

  bool get isDebitNote => sourceType == 'DEBIT_NOTE';

  /// "Return PR-1" or "Debit note DN-1", so the two kinds can be told apart.
  String get label => '${isDebitNote ? 'Debit note' : 'Return'} $returnNumber';

  /// Only a return that comes back as a refund can be refunded; a debit
  /// note's credit may always be.
  bool get isRefundOutcome => isDebitNote || outcome == 'REFUND';

  double get available => double.tryParse(availableAmount) ?? 0;

  factory SupplierCredit.fromJson(Json json) => SupplierCredit(
        sourceId: stringValue(json['source_id']).isEmpty
            ? stringValue(json['purchase_return_id'])
            : stringValue(json['source_id']),
        sourceType: stringValue(json['source_type']).isEmpty
            ? 'PURCHASE_RETURN'
            : stringValue(json['source_type']),
        purchaseReturnId: json['purchase_return_id'] == null
            ? null
            : stringValue(json['purchase_return_id']),
        debitNoteId: json['debit_note_id'] == null
            ? null
            : stringValue(json['debit_note_id']),
        returnNumber: stringValue(json['return_number']),
        returnDate: stringValue(json['return_date']),
        creditAmount: stringValue(json['credit_amount']),
        appliedAmount: stringValue(json['applied_amount']),
        availableAmount: stringValue(json['available_amount']),
        refundedAmount: stringValue(json['refunded_amount']).isEmpty
            ? '0.00'
            : stringValue(json['refunded_amount']),
        outcome: stringValue(json['outcome']).isEmpty
            ? 'CREDIT'
            : stringValue(json['outcome']),
        appliedTo: [
          for (final dynamic number
              in json['applied_to'] is List ? json['applied_to'] : const [])
            stringValue(number),
        ],
      );
}

/// Money a supplier handed back against a purchase return's credit.
class SupplierRefund {
  const SupplierRefund({
    required this.id,
    required this.purchaseReturnId,
    this.debitNoteId,
    required this.refundedOn,
    required this.amount,
    required this.method,
    required this.reference,
    required this.remarks,
    required this.status,
    required this.reversalReason,
  });

  final String id;
  final String? purchaseReturnId;
  final String? debitNoteId;
  final String refundedOn;
  final String amount;
  final String method;
  final String reference;
  final String remarks;

  /// POSTED, or REVERSED once taken back.
  final String status;
  final String reversalReason;

  bool get isReversed => status == 'REVERSED';

  factory SupplierRefund.fromJson(Json json) => SupplierRefund(
        id: stringValue(json['id']),
        purchaseReturnId: json['purchase_return_id'] == null
            ? null
            : stringValue(json['purchase_return_id']),
        debitNoteId: json['debit_note_id'] == null
            ? null
            : stringValue(json['debit_note_id']),
        refundedOn: stringValue(json['refunded_on']),
        amount: stringValue(json['amount']),
        method: stringValue(json['method']),
        reference: stringValue(json['reference']),
        remarks: stringValue(json['remarks']),
        status: stringValue(json['status']),
        reversalReason: stringValue(json['reversal_reason']),
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

/// A customer or vendor, reduced to a name somebody can choose from.
///
/// In `models/` rather than beside the dialog that renders it, because
/// `ApiClient` builds these now: the money screens have their own party list
/// (`/api/v1/{receipts,payments,refunds}/parties`) instead of reading the
/// customer or vendor master. Those masters are gated on `CUSTOMER_VIEW` and
/// `VENDOR_VIEW`, which `CASHIER` does not hold, so reading them made the
/// wrong permission the gate on recording a receipt.
class PartyOption {
  const PartyOption({
    required this.id,
    required this.code,
    required this.name,
    this.defaultTdsSection = '',
  });

  final String id;
  final String code;
  final String name;

  /// The supplier's usual TDS section, when the list carries it (ACC-7).
  final String defaultTdsSection;

  String get label => '$code  $name';
}

/// How money can move, in the words the screens use (ACC-3). Cash is the
/// cash method; every other mode goes through a bank.
const Map<String, String> paymentModeLabels = {
  'CASH': 'Cash',
  'CHEQUE': 'Cheque',
  'UPI': 'UPI',
  'BANK_TRANSFER': 'Bank transfer',
  'CARD': 'Card',
  'DEMAND_DRAFT': 'Demand draft',
  'OTHER': 'Other',
};

/// How far one bank's cheque leaf prints off the standard positions (ACC-12).
/// Offsets are millimetres, one decimal; negative moves left or up.
class ChequeLayout {
  const ChequeLayout({
    required this.ledgerAccountId,
    this.offsetXMm = '0.0',
    this.offsetYMm = '0.0',
    this.printAcPayee = true,
    this.version = 0,
  });

  final String ledgerAccountId;
  final String offsetXMm;
  final String offsetYMm;
  final bool printAcPayee;
  final int version;

  factory ChequeLayout.fromJson(Json json) {
    final Json d =
        json.containsKey('data') ? Map<String, dynamic>.from(json['data'] as Map) : json;
    String mm(dynamic value) =>
        stringValue(value).isEmpty ? '0.0' : stringValue(value);
    return ChequeLayout(
      ledgerAccountId: stringValue(d['ledger_account_id']),
      offsetXMm: mm(d['offset_x_mm']),
      offsetYMm: mm(d['offset_y_mm']),
      printAcPayee: d['print_ac_payee'] != false,
      version: d['version'] is int ? d['version'] as int : 0,
    );
  }
}
