import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/security/permission_service.dart';
import '../../models/entities.dart';
import '../../models/price_floor.dart';
import '../document_framework/document_status_gate.dart';
import '../document_framework/document_steps.dart';
import '../trade_licences/licence_check_dialog.dart';
import '../workspace/reason_prompt.dart';
import 'credit_notice.dart';
import 'price_floor_check_dialog.dart';

// The next steps of a sales order and a sales invoice, for the list
// toolbars and the documents' own windows alike (D-BUY-22). Both are read
// off the server's JSON, which is what the two lists hold.
//
// The server gates approve and close (and hold, release and reserving
// again) on `SALES_APPROVE` and cancel on `SALES_CANCEL`.

/// Approve a sale, asking first what approval decides.
///
/// Credit is warned of **before** the call: once approved the document is in
/// the exposure it is checked against, and asking afterwards would count it
/// twice. A warning, never a block -- the server refuses when the firm's
/// policy says Block. Then the licences its lines need (backlog 54) and the
/// price floors (backlog 64 row 2), each of which may carry the reason of
/// whoever overrides it.
Future<DocumentStepDone?> _approveSale(
  BuildContext context,
  ApiClient api,
  PermissionService permissions, {
  required Json row,
  required String resource,
  required String document,
  required Future<PriceFloorCheck> Function() priceCheck,
}) async {
  await warnOnCreditExposure(
    context,
    api,
    customerId: row['customer_id'] as String?,
    amount: '${row['grand_total'] ?? '0'}',
  );
  if (!context.mounted) return null;
  final LicenceCheckOutcome licence = await confirmLicenceCheck(
    context,
    api,
    permissions,
    document: document,
    documentId: '${row['id']}',
  );
  if (!licence.proceed || !context.mounted) return null;
  final PriceFloorOutcome price =
      await confirmPriceFloor(context, permissions, check: priceCheck);
  if (!price.proceed) return null;
  final String? overrideReason = licence.overrideReason;
  final String? priceOverrideReason = price.overrideReason;
  await api.documentAction(
    resource,
    '${row['id']}',
    '/approve',
    query: overrideReason == null && priceOverrideReason == null
        ? null
        : {
            if (overrideReason != null)
              'licence_override_reason': overrideReason,
            if (priceOverrideReason != null)
              'price_override_reason': priceOverrideReason,
          },
  );
  // Said by the list once it reads itself again, and only by the status:
  // a message here would cover the credit warning shown before the call.
  return const DocumentStepDone('', step: 'approve');
}

/// The steps of one sale whose lifecycle actions are plain
/// `POST /<resource>/{id}/<step>` calls.
DocumentStep<Json> _plainStep(
  ApiClient api, {
  required String resource,
  required String numberKey,
  required DocumentStatusGate gate,
  required String id,
  required String label,
  required IconData icon,
  required DocumentLifecycleAction action,
  required bool permitted,
  required String said,
}) =>
    DocumentStep<Json>(
      id: id,
      label: label,
      icon: icon,
      permitted: permitted,
      allows: (row) => gate.allows(action, '${row['status'] ?? ''}'),
      run: (context, row) async {
        await api.documentAction(resource, '${row['id']}', '/$id');
        return DocumentStepDone('${row[numberKey] ?? ''} $said', step: id);
      },
    );

bool _held(Json row) => row['is_on_hold'] == true;

/// A sales order's next steps: Approve, Hold or Release, Reserve again,
/// Cancel, Close.
List<DocumentStep<Json>> salesOrderSteps(
  ApiClient api,
  PermissionService permissions,
) {
  final bool approver = permissions.hasPermission('SALES_APPROVE');
  String number(Json row) => '${row['order_number'] ?? ''}';
  bool finished(Json row) => const {'CANCELLED', 'CLOSED'}
      .contains('${row['status'] ?? ''}'.toUpperCase());
  return [
    DocumentStep<Json>(
      id: 'approve',
      label: 'Approve',
      icon: Icons.check_circle_outline,
      forward: true,
      afterSave: 'Save & approve',
      permitted: approver,
      allows: (row) => DocumentStatusGate.salesOrder
          .allows(DocumentLifecycleAction.approve, '${row['status'] ?? ''}'),
      run: (context, row) => _approveSale(
        context,
        api,
        permissions,
        row: row,
        resource: 'sales-orders',
        document: 'SALES_ORDER',
        priceCheck: () => api.salesOrderPriceCheck('${row['id']}'),
      ),
    ),
    // A hold is a flag, not a status: the order keeps where it had got to
    // and its stock stays reserved. The reason is required -- whoever hits
    // the refusal downstream has to know why.
    DocumentStep<Json>(
      id: 'hold',
      label: 'Hold',
      icon: Icons.pause_outlined,
      permitted: approver,
      allows: (row) => !_held(row) && !finished(row),
      run: (context, row) async {
        final String? reason = await askForReason(
          context,
          title: 'Hold ${number(row)}',
          explanation: 'Nothing is unwound. The order keeps its status and '
              'its stock stays reserved — a hold says "not yet", not '
              '"never". It cannot be dispatched until it is released.',
          confirmLabel: 'Hold',
        );
        if (reason == null) return null;
        await api.holdSalesOrder('${row['id']}', reason: reason);
        return DocumentStepDone('${number(row)} is on hold.', step: 'hold');
      },
    ),
    DocumentStep<Json>(
      id: 'release',
      label: 'Release',
      icon: Icons.play_arrow_outlined,
      forward: true,
      permitted: approver,
      allows: _held,
      run: (context, row) async {
        await api.releaseSalesOrder('${row['id']}');
        return DocumentStepDone('${number(row)} released.', step: 'release');
      },
    ),
    // STK-12: the order's stock hold lapsed unshipped.
    DocumentStep<Json>(
      id: 'reserve-again',
      label: 'Reserve again',
      icon: Icons.inventory_2_outlined,
      permitted: approver,
      allows: (row) => '${row['reservation_lapsed_at'] ?? ''}'.isNotEmpty,
      run: (context, row) async {
        await api.reserveSalesOrderAgain('${row['id']}');
        return DocumentStepDone(
          'Stock is held again for ${number(row)}.',
          step: 'reserve-again',
        );
      },
    ),
    _plainStep(
      api,
      resource: 'sales-orders',
      numberKey: 'order_number',
      gate: DocumentStatusGate.salesOrder,
      id: 'cancel',
      label: 'Cancel',
      icon: Icons.cancel_outlined,
      action: DocumentLifecycleAction.cancel,
      permitted: permissions.hasPermission('SALES_CANCEL'),
      said: 'cancelled. Its stock is released.',
    ),
    _plainStep(
      api,
      resource: 'sales-orders',
      numberKey: 'order_number',
      gate: DocumentStatusGate.salesOrder,
      id: 'close',
      label: 'Close',
      icon: Icons.lock_outline,
      action: DocumentLifecycleAction.close,
      permitted: approver,
      said: 'closed.',
    ),
  ];
}

/// A sales invoice's next steps: Approve, Cancel, Close.
List<DocumentStep<Json>> salesInvoiceSteps(
  ApiClient api,
  PermissionService permissions,
) {
  final bool approver = permissions.hasPermission('SALES_APPROVE');
  return [
    DocumentStep<Json>(
      id: 'approve',
      label: 'Approve',
      icon: Icons.check_circle_outline,
      forward: true,
      afterSave: 'Save & approve',
      permitted: approver,
      allows: (row) => DocumentStatusGate.salesInvoice
          .allows(DocumentLifecycleAction.approve, '${row['status'] ?? ''}'),
      run: (context, row) => _approveSale(
        context,
        api,
        permissions,
        row: row,
        resource: 'sales-invoices',
        document: 'SALES_INVOICE',
        priceCheck: () => api.salesInvoicePriceCheck('${row['id']}'),
      ),
    ),
    _plainStep(
      api,
      resource: 'sales-invoices',
      numberKey: 'invoice_number',
      gate: DocumentStatusGate.salesInvoice,
      id: 'cancel',
      label: 'Cancel',
      icon: Icons.cancel_outlined,
      action: DocumentLifecycleAction.cancel,
      permitted: permissions.hasPermission('SALES_CANCEL'),
      said: 'cancelled.',
    ),
    _plainStep(
      api,
      resource: 'sales-invoices',
      numberKey: 'invoice_number',
      gate: DocumentStatusGate.salesInvoice,
      id: 'close',
      label: 'Close',
      icon: Icons.lock_outline,
      action: DocumentLifecycleAction.close,
      permitted: approver,
      said: 'closed.',
    ),
  ];
}
