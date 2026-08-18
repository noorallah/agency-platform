import 'package:flutter/material.dart';

import '../../models/document_framework.dart';
import '../../models/goods_receipt.dart';
import '../document_framework/document_framework_widgets.dart';
import '../workspace/desktop_framework.dart';

/// One goods receipt: its header, its lines, its totals and its timeline.
///
/// This was a pane pinned permanently beside the list, taking 57% of the
/// width — more than the list it sat next to — to show a document the user had
/// only pointed at. It is a dialog now, opened by double-click or the View
/// action, which gives the table the whole width and the document room to be
/// read.
///
/// Read-only on purpose. Complete, Cancel and Close act on the selected row
/// from the workspace toolbar, the same place a purchase order is submitted
/// and approved from; a document that can be acted on from two places is a
/// document somebody acts on twice.
class GoodsReceiptViewDialog extends StatelessWidget {
  const GoodsReceiptViewDialog({
    super.key,
    required this.receipt,
    required this.history,
  });

  final GoodsReceiptRecord receipt;
  final List<DocumentTimelineSnapshot> history;

  @override
  Widget build(BuildContext context) {
    final DocumentHeaderSnapshot header = receipt.toHeader();
    final DocumentTotalsSnapshot totals = receipt.toTotals();
    return WorkspaceDialog(
      title: receipt.grnNumber,
      subtitle: 'Goods receipt against ${receipt.purchaseOrderNumber}',
      icon: Icons.inventory_2_outlined,
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            EnterpriseDocumentHeader(header: header),
            const SizedBox(height: 12),
            EnterpriseDocumentLines(
              lines: [
                for (final GoodsReceiptLine line in receipt.lines)
                  DocumentLineSnapshot(
                    lineNumber: line.lineNumber,
                    product: line.productId,
                    description: line.description,
                    uom: line.inventoryUomId,
                    packaging: line.packagingTypeId,
                    quantity: line.currentReceiptQuantity,
                    freeQuantity: line.freeQuantity,
                    unitPrice: line.unitPrice,
                    discount: line.discountAmount,
                    taxProfile: line.taxProfileId,
                    amount: line.grossAmount,
                    netAmount: line.netAmount,
                    remarks: line.remarks,
                  ),
              ],
            ),
            const SizedBox(height: 12),
            EnterpriseTotalsPanel(totals: totals),
            const SizedBox(height: 12),
            EnterpriseTimeline(entries: history),
          ],
        ),
      ),
      onClose: () => Navigator.of(context).pop(),
    );
  }
}
