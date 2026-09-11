import '../workspace/import_sample.dart';
import 'inventory_import_wizard.dart' show InventoryImportType;

/// The sample file for each kind of inventory import.
///
/// The wizard reads these files itself and resolves codes against the firm's
/// masters before anything is sent, so the headings are the wizard's own. It
/// normalises a heading to lower-case letters and digits, which is why the
/// samples can use readable ones: `Product Code` and `productcode` are the
/// same column to it. `inventory_import_samples_test.dart` opens each sample
/// in the wizard and asserts it reports no missing column.
ImportSample inventoryImportSample(InventoryImportType type) => switch (type) {
      InventoryImportType.openingStock => const ImportSample(
          fileName: 'opening_stock_sample.csv',
          columns: [
            'Product Code',
            'Branch Code',
            'Warehouse Code',
            'Storage Code',
            'Quantity',
            'Posting Date',
            'Remarks',
          ],
          example: [
            'DETER1K',
            'HO',
            'MAIN',
            '',
            '100',
            '2026-09-01',
            'Opening stock',
          ],
        ),
      InventoryImportType.inventoryUpdate => const ImportSample(
          fileName: 'inventory_update_sample.csv',
          columns: [
            'Product Code',
            'Branch Code',
            'Warehouse Code',
            'Storage Code',
            'Minimum Level',
            'Maximum Level',
            'Reorder Level',
            'Safety Stock',
            'Status',
          ],
          example: [
            'DETER1K',
            'HO',
            'MAIN',
            '',
            '10',
            '500',
            '50',
            '20',
            'ACTIVE',
          ],
        ),
      InventoryImportType.inventoryAdjustment => const ImportSample(
          fileName: 'inventory_adjustment_sample.csv',
          columns: [
            'Product Code',
            'Branch Code',
            'Warehouse Code',
            'Storage Code',
            'Quantity',
            'Reference Number',
            'Transaction Date',
            'Remarks',
          ],
          example: [
            'DETER1K',
            'HO',
            'MAIN',
            '',
            // Negative takes stock off; positive adds it.
            '-5',
            'ADJ-0001',
            '2026-09-01',
            'Damaged in transit',
          ],
        ),
    };
