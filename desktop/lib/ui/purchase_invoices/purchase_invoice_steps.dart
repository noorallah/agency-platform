import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/security/permission_service.dart';
import '../../models/entities.dart';
import '../document_framework/document_status_gate.dart';
import '../document_framework/document_steps.dart';
import 'approve_bill_dialog.dart';

/// The TDS the server would deduct on this bill (PG-5), or null where the
/// bill names no supplier. Reads the bill, then the supplier's proposal for it.
Future<Json?> _tdsProposal(ApiClient api, String billId) async {
  final Json invoice = await api.purchaseInvoiceDetail(billId);
  final Object? data = invoice['data'];
  final Json bill = data is Map ? Map<String, dynamic>.from(data) : invoice;
  final String vendorId = '${bill['vendor_id'] ?? ''}';
  if (vendorId.isEmpty) return null;
  final String date = '${bill['invoice_date'] ?? ''}';
  return api.tdsSupplierProposal(
    vendorId,
    on: date.length >= 10
        ? date.substring(0, 10)
        : DateTime.now().toIso8601String().substring(0, 10),
    billAmount: '${bill['subtotal'] ?? '0'}',
    billTotal: '${bill['grand_total'] ?? '0'}',
    invoiceId: billId,
  );
}

/// The currency the bill is in, blank for rupees or when it cannot be read.
Future<String> _billCurrency(ApiClient api, String billId) async {
  try {
    final Json invoice = await api.purchaseInvoiceDetail(billId);
    final Object? data = invoice['data'];
    final Json bill = data is Map ? Map<String, dynamic>.from(data) : invoice;
    final String code = '${bill['currency_code'] ?? ''}'.toUpperCase();
    return code == 'NULL' || code == 'INR' ? '' : code;
  } catch (_) {
    return '';
  }
}

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
        // PG-3 and PG-5: the dialog approves, so a refusal stays inside it,
        // and it carries the paid-now block and the TDS override.
        final String currency = await _billCurrency(api, bill.id);
        if (!context.mounted) return null;
        final Json? done = await showDialog<Json>(
          context: context,
          builder: (_) => ApproveBillDialog(
            number: bill.number,
            canPay: canPay,
            currencyCode: currency,
            loadProposal:
                currency.isEmpty ? () => _tdsProposal(api, bill.id) : null,
            onApprove: (body) => api.documentAction(
              'purchase-invoices',
              bill.id,
              '/approve',
              body: body,
            ),
          ),
        );
        if (done == null) return null;
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
