/// Which statuses let a lifecycle action run.
///
/// The toolbars offered Approve, Cancel and Close whenever a row was selected
/// and the user held the permission — so Approve was live on an
/// already-approved invoice, Close on a closed one, and Cancel on a document
/// nothing could cancel. Pressing them produced a refusal from the server that
/// the screen could have predicted: *"Only draft purchase invoices can be
/// approved."*
///
/// A gate is the same rule the service enforces, stated once on the client so
/// the button is disabled instead. It is **not** a substitute for the server's
/// check — the server stays authoritative, because another client exists and
/// state moves between a page load and a click.
///
/// ### Allowed, not blocked
///
/// Each action lists the statuses that permit it rather than the ones that
/// forbid it. Both express today's rules; only one fails safe. A status added
/// later is disabled until somebody decides it belongs, instead of silently
/// becoming legal everywhere.
library;

/// A lifecycle action a document toolbar can offer.
enum DocumentLifecycleAction { approve, complete, cancel, close }

/// The statuses that permit each action, for one kind of document.
class DocumentStatusGate {
  const DocumentStatusGate(this._allowed);

  final Map<DocumentLifecycleAction, Set<String>> _allowed;

  /// Whether [action] may run against [status].
  ///
  /// A null or empty status means nothing is selected, which permits nothing.
  /// Comparison is upper-cased and trimmed: the value arrives as a string from
  /// JSON, and a stray space should disable a button rather than enable the
  /// wrong one.
  bool allows(DocumentLifecycleAction action, String? status) {
    final String value = (status ?? '').trim().toUpperCase();
    if (value.isEmpty) return false;
    return _allowed[action]?.contains(value) ?? false;
  }

  /// Purchase invoice — `approve_invoice`, `cancel_invoice`, `close_invoice`.
  static const DocumentStatusGate purchaseInvoice = DocumentStatusGate({
    // "Only draft purchase invoices can be approved." Approval also posts the
    // journal, so this is the one that matters most.
    DocumentLifecycleAction.approve: {'DRAFT'},
    // "This purchase invoice can no longer be cancelled."
    DocumentLifecycleAction.cancel: {'DRAFT', 'APPROVED'},
    // "This purchase invoice is already closed."
    DocumentLifecycleAction.close: {'DRAFT', 'APPROVED', 'CANCELLED'},
  });

  /// Purchase return — approve, complete, cancel, close.
  static const DocumentStatusGate purchaseReturn = DocumentStatusGate({
    // "Only draft purchase returns can be approved."
    DocumentLifecycleAction.approve: {'DRAFT'},
    // "Only approved purchase returns can be completed." Completing is what
    // takes the stock off.
    DocumentLifecycleAction.complete: {'APPROVED'},
    // "This purchase return can no longer be cancelled."
    DocumentLifecycleAction.cancel: {'DRAFT', 'APPROVED', 'COMPLETED'},
    // "This purchase return is already closed."
    DocumentLifecycleAction.close: {'DRAFT', 'APPROVED', 'COMPLETED', 'CANCELLED'},
  });

  /// Goods receipt — complete, cancel, close.
  ///
  /// Completing posts the stock; cancelling a completed one reverses it, which
  /// is why cancel stays available after completion.
  static const DocumentStatusGate goodsReceipt = DocumentStatusGate({
    DocumentLifecycleAction.complete: {'DRAFT'},
    DocumentLifecycleAction.cancel: {'DRAFT', 'COMPLETED'},
    DocumentLifecycleAction.close: {'DRAFT', 'COMPLETED', 'CANCELLED'},
  });
}
