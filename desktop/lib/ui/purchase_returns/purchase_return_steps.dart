import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/security/permission_service.dart';
import '../document_framework/document_status_gate.dart';
import '../document_framework/document_steps.dart';

/// A purchase return's next steps -- Approve, Complete, Cancel, Close -- for
/// the list toolbar and the return's own windows alike (D-BUY-22).
///
/// The server gates approve, complete and close on `PURCHASE_APPROVE` and
/// cancel on `PURCHASE_CANCEL`; the status gate is
/// [DocumentStatusGate.purchaseReturn]. Completing is what takes the stock
/// off, which is why it is never named after Close.
List<DocumentStep<DocumentRef>> purchaseReturnSteps(
  ApiClient api,
  PermissionService permissions,
) {
  bool allows(DocumentLifecycleAction action, DocumentRef row) =>
      DocumentStatusGate.purchaseReturn.allows(action, row.status);
  final bool approver = permissions.hasPermission('PURCHASE_APPROVE');
  DocumentStep<DocumentRef> step(
    String id,
    String label,
    IconData icon,
    DocumentLifecycleAction action, {
    required bool permitted,
    required String said,
    bool forward = false,
    String? afterSave,
  }) =>
      DocumentStep<DocumentRef>(
        id: id,
        label: label,
        icon: icon,
        forward: forward,
        afterSave: afterSave,
        permitted: permitted,
        allows: (row) => allows(action, row),
        run: (context, row) async {
          await api.documentAction('purchase-returns', row.id, '/$id');
          return DocumentStepDone('${row.number} $said');
        },
      );
  return [
    step(
      'approve',
      'Approve',
      Icons.thumb_up_outlined,
      DocumentLifecycleAction.approve,
      permitted: approver,
      forward: true,
      afterSave: 'Save & approve',
      said: 'approved. Completing it is what takes the stock off.',
    ),
    step(
      'complete',
      'Complete',
      Icons.check_circle_outline,
      DocumentLifecycleAction.complete,
      permitted: approver,
      forward: true,
      said: 'completed. The stock has gone back to the supplier.',
    ),
    step(
      'cancel',
      'Cancel',
      Icons.cancel_outlined,
      DocumentLifecycleAction.cancel,
      permitted: permissions.hasPermission('PURCHASE_CANCEL'),
      said: 'cancelled.',
    ),
    step(
      'close',
      'Close',
      Icons.lock_outline,
      DocumentLifecycleAction.close,
      permitted: approver,
      said: 'closed.',
    ),
  ];
}
