import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../models/document_framework.dart';
import '../../models/goods_receipt.dart';
import '../document_framework/document_framework_widgets.dart';
import '../document_framework/document_line_labels.dart';
import '../document_framework/document_steps.dart';
import '../workspace/desktop_framework.dart';
import 'serial_entry_dialog.dart';

/// One goods receipt: its header, its lines, its totals and its timeline.
///
/// This was a pane pinned permanently beside the list, taking 57% of the
/// width — more than the list it sat next to — to show a document the user had
/// only pointed at. It is a dialog now, opened by double-click or the View
/// action, which gives the table the whole width and the document room to be
/// read.
///
/// Nothing on it is typed, but the receipt's next steps -- Complete, Cancel,
/// Close -- are on it (D-BUY-22), from the same definitions as the list
/// toolbar's, so both re-gate on one receipt alike. A step that succeeds
/// closes the window with a [DocumentStepDone] for the list to read itself
/// again.
class GoodsReceiptViewDialog extends StatelessWidget {
  const GoodsReceiptViewDialog({
    super.key,
    required this.receipt,
    required this.history,
    this.labels = const DocumentLineLabels(),
    this.steps = const [],
    this.api,
  });

  /// Needed to read a unit's trail; without it the serials are not offered.
  final ApiClient? api;

  final GoodsReceiptRecord receipt;
  final List<DocumentTimelineSnapshot> history;

  /// Names for the ids a line carries; without them the view shows the ids.
  final DocumentLineLabels labels;

  /// The receipt's next steps; only those it allows are shown.
  final List<DocumentStep<GoodsReceiptRecord>> steps;

  @override
  Widget build(BuildContext context) {
    final DocumentHeaderSnapshot header = receipt.toHeader(
      branchName: labels.branch,
      warehouseName: labels.warehouse,
    );
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
            if (steps.isNotEmpty)
              Align(
                alignment: Alignment.centerRight,
                child: DocumentStepStrip<GoodsReceiptRecord>(
                  record: receipt,
                  steps: steps,
                ),
              ),
            EnterpriseDocumentHeader(header: header),
            const SizedBox(height: 12),
            EnterpriseDocumentLines(
              lines: [
                for (final GoodsReceiptLine line in receipt.lines)
                  DocumentLineSnapshot(
                    lineNumber: line.lineNumber,
                    product: labels.product(line.productId),
                    description: line.description,
                    uom: labels.unit(line.inventoryUomId),
                    packaging: line.packagingTypeId,
                    quantity: line.currentReceiptQuantity,
                    freeQuantity: line.freeQuantity,
                    unitPrice: line.unitPrice,
                    discount: line.discountAmount,
                    taxProfile: labels.taxProfile(line.taxProfileId),
                    amount: line.grossAmount,
                    netAmount: line.netAmount,
                    remarks: line.remarks,
                  ),
              ],
            ),
            if (api != null)
              for (final GoodsReceiptLine line in receipt.lines)
                if (line.serialTracked && line.serialNumbers.isNotEmpty)
                  Align(
                    alignment: Alignment.centerLeft,
                    child: TextButton.icon(
                      key: ValueKey<String>('view-serials-${line.lineNumber}'),
                      icon: const Icon(Icons.qr_code_2, size: 16),
                      label: Text(
                        'Line ${line.lineNumber}: '
                        '${line.serialNumbers.length} serial numbers',
                      ),
                      onPressed: () => showSerialEntryDialog(
                        context,
                        api: api!,
                        title: 'Serial numbers · line ${line.lineNumber}',
                        needed: line.serialNumbers.length,
                        initial: line.serialNumbers,
                        productId: line.productId,
                        readOnly: true,
                      ),
                    ),
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
