/// Which way money moved, and who with.
///
/// Three directions rather than a money-in flag: a refund is money out like a
/// payment and about a customer like a receipt, so no single boolean describes
/// it. Every screen and request that differs between them differs here, in one
/// place, rather than in a condition repeated per call site.
enum SettlementDirection {
  /// Money in, from a customer.
  receipt,

  /// Money out, to a vendor.
  payment,

  /// Money back, to a customer who paid in advance.
  refund;

  /// The API path segment this direction posts to and lists from.
  String get path => switch (this) {
        SettlementDirection.receipt => 'receipts',
        SettlementDirection.payment => 'payments',
        SettlementDirection.refund => 'refunds',
      };

  /// Whether the other party is a customer rather than a vendor.
  bool get isCustomer => this != SettlementDirection.payment;

  /// Whether this settles invoices. A refund returns money held on account,
  /// which is the opposite of settling a document, so it allocates to nothing.
  bool get allocates => this != SettlementDirection.refund;

  /// The query parameter naming the party when filtering a list.
  String get partyParameter => isCustomer ? 'customer_id' : 'vendor_id';

  /// What one of these is called, in the middle of a sentence.
  String get noun => switch (this) {
        SettlementDirection.receipt => 'receipt',
        SettlementDirection.payment => 'payment',
        SettlementDirection.refund => 'refund',
      };

  /// What the tab is called.
  String get title => switch (this) {
        SettlementDirection.receipt => 'Receipts',
        SettlementDirection.payment => 'Payments',
        SettlementDirection.refund => 'Refunds',
      };

  /// The permission that lets somebody see these.
  ///
  /// A refund is money leaving, so it takes the money-out grants rather than
  /// the receipt ones: the person trusted to collect is not automatically the
  /// person trusted to hand money back. The server enforces the same split.
  String get viewPermission =>
      this == SettlementDirection.receipt ? 'RECEIPT_VIEW' : 'PAYMENT_VIEW';

  /// The permission that lets somebody record one.
  String get createPermission =>
      this == SettlementDirection.receipt ? 'RECEIPT_CREATE' : 'PAYMENT_CREATE';
}
