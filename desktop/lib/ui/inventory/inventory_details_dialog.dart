import 'package:flutter/material.dart';

import '../../models/inventory.dart';
import '../workspace/workspace_interactions.dart';

Future<void> showInventoryDetailsDialog(
  BuildContext context, {
  required InventoryRecord record,
  Future<void> Function()? onOpenInventory,
  Future<void> Function()? onViewLedger,
  Future<void> Function()? onViewTransactions,
}) =>
    showDialog<void>(
      context: context,
      builder: (context) => _InventoryDetailsDialog(
        record: record,
        onOpenInventory: onOpenInventory,
        onViewLedger: onViewLedger,
        onViewTransactions: onViewTransactions,
      ),
    );

class _InventoryDetailsDialog extends StatelessWidget {
  const _InventoryDetailsDialog({
    required this.record,
    this.onOpenInventory,
    this.onViewLedger,
    this.onViewTransactions,
  });

  final InventoryRecord record;
  final Future<void> Function()? onOpenInventory;
  final Future<void> Function()? onViewLedger;
  final Future<void> Function()? onViewTransactions;

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: Row(
          children: [
            const Icon(Icons.inventory_2_outlined),
            const SizedBox(width: 12),
            Expanded(
              child: Text(
                record.productName,
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ],
        ),
        content: SizedBox(
          width: 640,
          child: SingleChildScrollView(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _detailRow('Inventory ID', record.id),
                _detailRow('Product code', record.productCode),
                _detailRow('Branch', '${record.branchCode} - ${record.branchName}'),
                _detailRow(
                  'Warehouse',
                  '${record.warehouseCode} - ${record.warehouseName}',
                ),
                _detailRow(
                  'Storage',
                  record.storageNodeCode.isEmpty
                      ? '-'
                      : '${record.storageNodeCode} - ${record.storageNodeName}',
                ),
                _detailRow('Business profile', _blank(record.businessProfileCode)),
                const Divider(),
                _detailRow('Current stock', record.currentQuantity),
                _detailRow('Available stock', record.availableQuantity),
                _detailRow('Reserved stock', record.reservedQuantity),
                _detailRow('Blocked stock', record.blockedQuantity),
                _detailRow('Damaged stock', record.damagedQuantity),
                _detailRow('Quarantine stock', record.quarantineQuantity),
                _detailRow('In transit stock', record.inTransitQuantity),
                const Divider(),
                _detailRow('Minimum level', _blank(record.minimumLevel)),
                _detailRow('Maximum level', _blank(record.maximumLevel)),
                _detailRow('Reorder level', _blank(record.reorderLevel)),
                _detailRow('Safety stock', _blank(record.safetyStock)),
                _detailRow('Last transaction', _blank(record.lastTransactionAt)),
                _detailRow('Status', record.status),
              ],
            ),
          ),
        ),
        actions: [
          TextButton.icon(
            onPressed: () => copyTextToClipboard(record.productCode),
            icon: const Icon(Icons.copy_outlined),
            label: const Text('Copy Product Code'),
          ),
          TextButton.icon(
            onPressed: () => copyTextToClipboard(record.id),
            icon: const Icon(Icons.copy_outlined),
            label: const Text('Copy Inventory ID'),
          ),
          if (onViewTransactions != null)
            TextButton.icon(
              onPressed: () async {
                Navigator.of(context).pop();
                await onViewTransactions!();
              },
              icon: const Icon(Icons.swap_horiz_outlined),
              label: const Text('View Transactions'),
            ),
          if (onViewLedger != null)
            TextButton.icon(
              onPressed: () async {
                Navigator.of(context).pop();
                await onViewLedger!();
              },
              icon: const Icon(Icons.receipt_long_outlined),
              label: const Text('View Ledger'),
            ),
          if (onOpenInventory != null)
            FilledButton.icon(
              onPressed: () async {
                Navigator.of(context).pop();
                await onOpenInventory!();
              },
              icon: const Icon(Icons.open_in_new),
              label: const Text('Open Inventory'),
            )
          else
            FilledButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('Close'),
            ),
        ],
      );

  Widget _detailRow(String label, String value) => Padding(
        padding: const EdgeInsets.only(bottom: 10),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              label,
              style: const TextStyle(fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: 2),
            SelectableText(value),
          ],
        ),
      );
}

String _blank(String value) => value.isEmpty ? '-' : value;
