// A lifecycle button knows the status it is acting on.
//
// The purchase document toolbars enabled Approve, Cancel and Close whenever a
// row was selected and the user held the permission. So Approve was live on an
// already-approved invoice, Close on a closed one, and Cancel on a document
// nothing could cancel — and pressing any of them produced a refusal from the
// server that the screen could have predicted:
//
//   "Only draft purchase invoices can be approved."
//
// Each expectation below names the service guard it mirrors, so a rule that
// changes on the server has a test here pointing at it.

import 'package:agency_desktop/ui/document_framework/document_status_gate.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('purchase invoice', () {
    const DocumentStatusGate gate = DocumentStatusGate.purchaseInvoice;

    test('only a draft can be approved', () {
      // approve_invoice: status != DRAFT -> "Only draft purchase invoices can
      // be approved." Approval also posts the journal.
      expect(gate.allows(DocumentLifecycleAction.approve, 'DRAFT'), isTrue);
      for (final String status in <String>['APPROVED', 'CANCELLED', 'CLOSED']) {
        expect(gate.allows(DocumentLifecycleAction.approve, status), isFalse);
      }
    });

    test('a cancelled or closed invoice can no longer be cancelled', () {
      // cancel_invoice refuses exactly those two.
      expect(gate.allows(DocumentLifecycleAction.cancel, 'DRAFT'), isTrue);
      expect(gate.allows(DocumentLifecycleAction.cancel, 'APPROVED'), isTrue);
      expect(gate.allows(DocumentLifecycleAction.cancel, 'CANCELLED'), isFalse);
      expect(gate.allows(DocumentLifecycleAction.cancel, 'CLOSED'), isFalse);
    });

    test('a closed invoice cannot be closed again', () {
      expect(gate.allows(DocumentLifecycleAction.close, 'APPROVED'), isTrue);
      expect(gate.allows(DocumentLifecycleAction.close, 'CLOSED'), isFalse);
    });

    test('an invoice has no complete step', () {
      for (final String status in <String>['DRAFT', 'APPROVED']) {
        expect(gate.allows(DocumentLifecycleAction.complete, status), isFalse);
      }
    });
  });

  group('purchase return', () {
    const DocumentStatusGate gate = DocumentStatusGate.purchaseReturn;

    test('only an approved return can be completed', () {
      // complete_return: status != APPROVED -> "Only approved purchase returns
      // can be completed." This is the step that takes the stock off.
      expect(gate.allows(DocumentLifecycleAction.complete, 'APPROVED'), isTrue);
      for (final String status in <String>[
        'DRAFT',
        'COMPLETED',
        'CANCELLED',
        'CLOSED',
      ]) {
        expect(gate.allows(DocumentLifecycleAction.complete, status), isFalse);
      }
    });

    test('only a draft can be approved', () {
      expect(gate.allows(DocumentLifecycleAction.approve, 'DRAFT'), isTrue);
      expect(gate.allows(DocumentLifecycleAction.approve, 'APPROVED'), isFalse);
    });

    test('a completed return can still be cancelled', () {
      // cancel_return refuses only CANCELLED and CLOSED, and cancelling a
      // completed return is what puts the stock back.
      expect(gate.allows(DocumentLifecycleAction.cancel, 'COMPLETED'), isTrue);
      expect(gate.allows(DocumentLifecycleAction.cancel, 'CLOSED'), isFalse);
    });
  });

  group('goods receipt', () {
    const DocumentStatusGate gate = DocumentStatusGate.goodsReceipt;

    test('only a draft can be completed', () {
      expect(gate.allows(DocumentLifecycleAction.complete, 'DRAFT'), isTrue);
      expect(gate.allows(DocumentLifecycleAction.complete, 'COMPLETED'), isFalse);
    });

    test('a completed receipt can still be cancelled', () {
      // Cancelling a completed receipt reverses the posted stock, so it has to
      // stay available after completion.
      expect(gate.allows(DocumentLifecycleAction.cancel, 'COMPLETED'), isTrue);
      expect(gate.allows(DocumentLifecycleAction.cancel, 'CANCELLED'), isFalse);
    });

    test('a receipt has no approval step', () {
      for (final String status in <String>['DRAFT', 'COMPLETED']) {
        expect(gate.allows(DocumentLifecycleAction.approve, status), isFalse);
      }
    });
  });

  group('nothing selected, nothing offered', () {
    test('a null or blank status permits nothing', () {
      for (final DocumentLifecycleAction action
          in DocumentLifecycleAction.values) {
        expect(
          DocumentStatusGate.purchaseInvoice.allows(action, null),
          isFalse,
        );
        expect(DocumentStatusGate.purchaseInvoice.allows(action, '  '), isFalse);
      }
    });

    test('a status is matched however it is cased or padded', () {
      // It arrives as a string from JSON; a stray space should not enable the
      // wrong button — nor disable the right one.
      expect(
        DocumentStatusGate.purchaseInvoice
            .allows(DocumentLifecycleAction.approve, ' draft '),
        isTrue,
      );
    });

    test('an unknown status permits nothing', () {
      // The reason each action lists what it allows rather than what it
      // blocks: a status added later is disabled until somebody decides it
      // belongs, instead of becoming legal everywhere by omission.
      expect(
        DocumentStatusGate.purchaseReturn
            .allows(DocumentLifecycleAction.complete, 'PARTIALLY_RETURNED'),
        isFalse,
      );
    });
  });

  group('sales order', () {
    const DocumentStatusGate gate = DocumentStatusGate.salesOrder;

    test('only a draft can be approved', () {
      // approve_order: "Only draft sales orders can be approved." Approval is
      // also where the credit check runs and stock is reserved.
      expect(gate.allows(DocumentLifecycleAction.approve, 'DRAFT'), isTrue);
      expect(gate.allows(DocumentLifecycleAction.approve, 'APPROVED'), isFalse);
    });

    test('a cancelled or closed order is closed for updates', () {
      // Both cancel_order and close_order refuse those two with the same
      // message, so both gates read the same.
      for (final DocumentLifecycleAction action in <DocumentLifecycleAction>[
        DocumentLifecycleAction.cancel,
        DocumentLifecycleAction.close,
      ]) {
        expect(gate.allows(action, 'APPROVED'), isTrue);
        expect(gate.allows(action, 'CANCELLED'), isFalse);
        expect(gate.allows(action, 'CLOSED'), isFalse);
      }
    });
  });

  group('sales invoice', () {
    const DocumentStatusGate gate = DocumentStatusGate.salesInvoice;

    test('it mirrors the purchase invoice', () {
      // The same document one direction over, and the services agree.
      for (final DocumentLifecycleAction action in DocumentLifecycleAction.values) {
        for (final String status in <String>[
          'DRAFT',
          'APPROVED',
          'CANCELLED',
          'CLOSED',
        ]) {
          expect(
            gate.allows(action, status),
            DocumentStatusGate.purchaseInvoice.allows(action, status),
            reason: '$action on $status',
          );
        }
      }
    });
  });

  group('delivery note', () {
    const DocumentStatusGate gate = DocumentStatusGate.deliveryNote;

    test('only an approved note can be dispatched', () {
      // "Only approved delivery notes can be dispatched." Dispatching moves
      // the stock, which is why it is its own action.
      expect(gate.allows(DocumentLifecycleAction.dispatch, 'APPROVED'), isTrue);
      for (final String status in <String>['DRAFT', 'DISPATCHED', 'COMPLETED']) {
        expect(gate.allows(DocumentLifecycleAction.dispatch, status), isFalse);
      }
    });

    test('a dispatched note can no longer be cancelled', () {
      // cancel_note refuses DISPATCHED as well as COMPLETED, CANCELLED and
      // CLOSED: the goods have gone.
      expect(gate.allows(DocumentLifecycleAction.cancel, 'APPROVED'), isTrue);
      expect(gate.allows(DocumentLifecycleAction.cancel, 'DISPATCHED'), isFalse);
    });

    test('a draft cannot be closed', () {
      // "Draft delivery notes cannot be closed" -- the only gate here that
      // forbids a draft, and the reason these are read off the service rather
      // than assumed to match each other.
      expect(gate.allows(DocumentLifecycleAction.close, 'DRAFT'), isFalse);
      expect(gate.allows(DocumentLifecycleAction.close, 'DISPATCHED'), isTrue);
    });
  });

  group('sales return', () {
    const DocumentStatusGate gate = DocumentStatusGate.salesReturn;

    test('only an approved return can be completed', () {
      expect(gate.allows(DocumentLifecycleAction.complete, 'APPROVED'), isTrue);
      expect(gate.allows(DocumentLifecycleAction.complete, 'DRAFT'), isFalse);
    });

    test('only a completed return can be closed', () {
      // "Only completed sales returns can be closed" -- stricter than the
      // purchase side, which closes a draft happily.
      expect(gate.allows(DocumentLifecycleAction.close, 'COMPLETED'), isTrue);
      expect(gate.allows(DocumentLifecycleAction.close, 'DRAFT'), isFalse);
      expect(
        DocumentStatusGate.purchaseReturn
            .allows(DocumentLifecycleAction.close, 'DRAFT'),
        isTrue,
        reason: 'the two returns really do differ here',
      );
    });
  });
}
