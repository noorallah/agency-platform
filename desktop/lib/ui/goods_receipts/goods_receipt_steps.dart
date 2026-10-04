import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/security/permission_service.dart';
import '../../models/goods_receipt.dart';
import '../document_framework/document_status_gate.dart';
import '../document_framework/document_steps.dart';
import '../trade_licences/licence_check_dialog.dart';

/// A goods receipt's next steps: Complete, Cancel, Close -- the list
/// toolbar's commands and the receipt window's strip, from one definition
/// (D-BUY-22).
///
/// Each follows the code the server enforces (D-ROLE-3): completing is the
/// receiver's job under `PURCHASE_RECEIVE`, cancelling `PURCHASE_CANCEL`,
/// closing `PURCHASE_APPROVE`; the status gate is
/// [DocumentStatusGate.goodsReceipt].
List<DocumentStep<GoodsReceiptRecord>> goodsReceiptSteps(
  ApiClient api,
  PermissionService permissions,
) {
  bool allows(DocumentLifecycleAction action, GoodsReceiptRecord record) =>
      DocumentStatusGate.goodsReceipt.allows(action, record.status);
  return [
    DocumentStep<GoodsReceiptRecord>(
      id: 'complete',
      label: 'Complete',
      icon: Icons.check_circle_outline,
      forward: true,
      afterSave: 'Save & complete',
      permitted: permissions.hasPermission('PURCHASE_RECEIVE'),
      allows: (record) => allows(DocumentLifecycleAction.complete, record),
      // The licences the receipt needs are checked first (backlog 54): a
      // purchase only ever warns, so there is no override, just "Approve
      // anyway".
      run: (context, record) async {
        final LicenceCheckOutcome licence = await confirmLicenceCheck(
          context,
          api,
          permissions,
          document: 'GOODS_RECEIPT',
          documentId: record.id,
        );
        if (!licence.proceed) return null;
        await api.completeGoodsReceipt(record.id);
        return DocumentStepDone(
          'Goods receipt ${record.grnNumber} completed. The stock is posted.',
        );
      },
    ),
    DocumentStep<GoodsReceiptRecord>(
      id: 'cancel',
      label: 'Cancel',
      icon: Icons.cancel_outlined,
      permitted: permissions.hasPermission('PURCHASE_CANCEL'),
      allows: (record) => allows(DocumentLifecycleAction.cancel, record),
      run: (context, record) async {
        await api.cancelGoodsReceipt(record.id);
        return DocumentStepDone('Goods receipt ${record.grnNumber} cancelled.');
      },
    ),
    DocumentStep<GoodsReceiptRecord>(
      id: 'close',
      label: 'Close',
      icon: Icons.lock_outline,
      permitted: permissions.hasPermission('PURCHASE_APPROVE'),
      allows: (record) => allows(DocumentLifecycleAction.close, record),
      run: (context, record) async {
        await api.closeGoodsReceipt(record.id);
        return DocumentStepDone('Goods receipt ${record.grnNumber} closed.');
      },
    ),
  ];
}
