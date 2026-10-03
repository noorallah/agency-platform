import 'entities.dart';
import 'settlement.dart';

/// One open bill an adjustment clears, and by how much.
class PartyAdjustmentAllocation {
  const PartyAdjustmentAllocation({
    required this.id,
    required this.side,
    required this.billId,
    required this.billNumber,
    required this.amount,
    this.billDate = '',
  });

  final String id;

  /// `CUSTOMER` (a sales bill) or `SUPPLIER` (a purchase bill).
  final String side;
  final String billId;
  final String billNumber;
  final String billDate;
  final String amount;

  bool get isCustomerSide => side == 'CUSTOMER';

  factory PartyAdjustmentAllocation.fromJson(Json json) =>
      PartyAdjustmentAllocation(
        id: stringValue(json['id']),
        side: stringValue(json['side']),
        billId: stringValue(json['bill_id']),
        billNumber: stringValue(json['bill_number']),
        billDate: stringValue(json['bill_date']),
        amount: stringValue(json['amount']),
      );
}

/// A balance cleared with no money moving: a customer's bad debt written
/// off, a supplier's balance written back, or one set against the other.
class PartyAdjustment {
  const PartyAdjustment({
    required this.id,
    required this.adjustmentNumber,
    required this.adjustmentDate,
    required this.kind,
    required this.amount,
    this.status = 'DRAFT',
    this.customerId = '',
    this.customerName = '',
    this.vendorId = '',
    this.vendorName = '',
    this.reason = '',
    this.customerAllocated = '0',
    this.supplierAllocated = '0',
    this.needsSecondApprover = false,
    this.journalEntryId = '',
    this.cancelReason = '',
    this.rebateAgreementId = '',
    this.version = 0,
    this.allocations = const <PartyAdjustmentAllocation>[],
  });

  final String id;
  final String adjustmentNumber;
  final String adjustmentDate;

  /// `CUSTOMER_WRITE_OFF`, `SUPPLIER_WRITE_BACK`, `SET_OFF` or
  /// `SUPPLIER_REBATE` (BUY-13, started from the rebate screen).
  final String kind;

  /// The supplier rebate a `SUPPLIER_REBATE` adjustment settles; empty for
  /// every other kind.
  final String rebateAgreementId;
  final String status;
  final String customerId;
  final String customerName;
  final String vendorId;
  final String vendorName;
  final String amount;
  final String reason;
  final String customerAllocated;
  final String supplierAllocated;

  /// The amount is above the firm's limit, so approving needs a second
  /// person. The server enforces it; the screen only says so.
  final bool needsSecondApprover;
  final String journalEntryId;
  final String cancelReason;
  final int version;
  final List<PartyAdjustmentAllocation> allocations;

  bool get isDraft => status == 'DRAFT';
  bool get isApproved => status == 'APPROVED';
  bool get isSetOff => kind == 'SET_OFF';

  /// The party or parties, as one line for a grid.
  String get partyLabel => [
        if (customerName.isNotEmpty) customerName,
        if (vendorName.isNotEmpty) vendorName,
      ].join(' / ');

  String get kindLabel => partyAdjustmentKindLabel(kind);

  factory PartyAdjustment.fromJson(Json json) => PartyAdjustment(
        id: stringValue(json['id']),
        adjustmentNumber: stringValue(json['adjustment_number']),
        adjustmentDate: stringValue(json['adjustment_date']),
        kind: stringValue(json['kind']),
        status: stringValue(json['status']).isEmpty
            ? 'DRAFT'
            : stringValue(json['status']),
        customerId: stringValue(json['customer_id']),
        customerName: stringValue(json['customer_name']),
        vendorId: stringValue(json['vendor_id']),
        vendorName: stringValue(json['vendor_name']),
        amount: stringValue(json['amount']),
        reason: stringValue(json['reason']),
        customerAllocated: stringValue(json['customer_allocated']).isEmpty
            ? '0'
            : stringValue(json['customer_allocated']),
        supplierAllocated: stringValue(json['supplier_allocated']).isEmpty
            ? '0'
            : stringValue(json['supplier_allocated']),
        needsSecondApprover: json['needs_second_approver'] == true,
        journalEntryId: stringValue(json['journal_entry_id']),
        cancelReason: stringValue(json['cancel_reason']),
        rebateAgreementId: stringValue(json['rebate_agreement_id']),
        version: (json['version'] as num?)?.toInt() ?? 0,
        allocations: [
          for (final dynamic row
              in json['allocations'] is List ? json['allocations'] as List : const [])
            if (row is Map)
              PartyAdjustmentAllocation.fromJson(Map<String, dynamic>.from(row)),
        ],
      );
}

/// The kind in the words a person uses for it.
String partyAdjustmentKindLabel(String kind) => switch (kind) {
      'CUSTOMER_WRITE_OFF' => 'Write-off (bad debt)',
      'SUPPLIER_WRITE_BACK' => 'Written back',
      'SET_OFF' => 'Set-off',
      'SUPPLIER_REBATE' => 'Rebate settlement',
      _ => kind,
    };

/// The bills an adjustment can clear, for each party it names.
class PartyAdjustmentOpenBills {
  const PartyAdjustmentOpenBills({
    this.customerBills = const <OutstandingInvoice>[],
    this.supplierBills = const <OutstandingInvoice>[],
    this.customerBalance,
    this.supplierOutstanding,
  });

  final List<OutstandingInvoice> customerBills;
  final List<OutstandingInvoice> supplierBills;

  /// What the customer owes, and what the supplier's open bills add up to:
  /// the most a write-off, write-back or set-off can move.
  final double? customerBalance;
  final double? supplierOutstanding;

  factory PartyAdjustmentOpenBills.fromJson(Json json) =>
      PartyAdjustmentOpenBills(
        customerBills: [
          for (final dynamic row
              in json['customer_bills'] is List ? json['customer_bills'] as List : const [])
            if (row is Map)
              OutstandingInvoice.fromJson(Map<String, dynamic>.from(row)),
        ],
        supplierBills: [
          for (final dynamic row
              in json['supplier_bills'] is List ? json['supplier_bills'] as List : const [])
            if (row is Map)
              OutstandingInvoice.fromJson(Map<String, dynamic>.from(row)),
        ],
        customerBalance: double.tryParse(stringValue(json['customer_balance'])),
        supplierOutstanding:
            double.tryParse(stringValue(json['supplier_outstanding'])),
      );
}

/// A firm's limits on clearing a balance without money.
class PartyAdjustmentSettings {
  const PartyAdjustmentSettings({
    required this.approvalThreshold,
    required this.roundingLimit,
    this.isDefault = false,
  });

  final String approvalThreshold;
  final String roundingLimit;
  final bool isDefault;

  factory PartyAdjustmentSettings.fromJson(Json json) =>
      PartyAdjustmentSettings(
        approvalThreshold: stringValue(json['approval_threshold']),
        roundingLimit: stringValue(json['rounding_limit']),
        isDefault: json['is_default'] == true,
      );
}
