import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/security/permission_service.dart';
import '../../models/entities.dart';
import '../document_framework/document_status_gate.dart';
import '../document_framework/document_steps.dart';
import 'approve_bill_dialog.dart';

/// A purchase invoice's next steps -- Approve, Cancel, Close -- for the list
/// toolbar and the bill's own windows alike (D-BUY-22).
///
/// The server gates approve and close on `PURCHASE_APPROVE` and cancel on
/// `PURCHASE_CANCEL`; the status gate is [DocumentStatusGate.purchaseInvoice].
List<DocumentStep<DocumentRef>> purchaseInvoiceSteps(
  ApiClient api,
  PermissionService permissions,
) {
  bool allows(DocumentLifecycleAction action, DocumentRef bill) =>
      DocumentStatusGate.purchaseInvoice.allows(action, bill.status);
  Future<Json> act(DocumentRef bill, String suffix) =>
      api.documentAction('purchase-invoices', bill.id, suffix);
  // Paying with the approval needs PAYMENT_CREATE as well (PG-3).
  final bool canPay = permissions.hasPermission('PAYMENT_CREATE');
  final bool approver = permissions.hasPermission('PURCHASE_APPROVE');
  return [
    DocumentStep<DocumentRef>(
      id: 'approve',
      label: 'Approve',
      icon: Icons.check_circle_outline,
      forward: true,
      afterSave: 'Save & approve',
      permitted: approver,
      allows: (bill) => allows(DocumentLifecycleAction.approve, bill),
      run: (context, bill) async {
        final Json? done;
        if (canPay) {
          // PG-3: the dialog approves, so a refusal stays inside it.
          done = await showDialog<Json>(
            context: context,
            builder: (_) => ApproveBillDialog(
              number: bill.number,
              onApprove: (body) => api.documentAction(
                'purchase-invoices',
                bill.id,
                '/approve',
                body: body,
              ),
            ),
          );
          if (done == null) return null;
        } else {
          done = await act(bill, '/approve');
        }
        // Past 30 November after the supplier's year the credit is lost
        // (s.16(4), GST-3): said on the approval, when the credit is taken.
        final Object? data = done['data'];
        final String late =
            '${(data is Map ? data : done)['credit_time_limit_warning'] ?? ''}';
        return DocumentStepDone(
          '${bill.number} approved and posted to the books.'
          '${late.isEmpty ? '' : ' $late'}',
          warning: late.isNotEmpty,
        );
      },
    ),
    DocumentStep<DocumentRef>(
      id: 'cancel',
      label: 'Cancel',
      icon: Icons.cancel_outlined,
      permitted: permissions.hasPermission('PURCHASE_CANCEL'),
      allows: (bill) => allows(DocumentLifecycleAction.cancel, bill),
      run: (context, bill) async {
        await act(bill, '/cancel');
        return DocumentStepDone('${bill.number} cancelled.');
      },
    ),
    DocumentStep<DocumentRef>(
      id: 'close',
      label: 'Close',
      icon: Icons.lock_outline,
      permitted: approver,
      allows: (bill) => allows(DocumentLifecycleAction.close, bill),
      run: (context, bill) async {
        await act(bill, '/close');
        return DocumentStepDone('${bill.number} closed.');
      },
    ),
  ];
}
