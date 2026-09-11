import '../workspace/import_sample.dart';

/// The sample file for the purchase order importer.
///
/// The server owns the parsing (`PurchaseService.import_orders_csv`), so the
/// headings are spelled the way it reads them -- the client lower-cases them
/// for its own preview, the file itself must not.
/// `tests/unit/test_import_samples_match_the_server.py` on the backend fails
/// the build if the two lists ever disagree.
///
/// Four of the columns are ids rather than codes, which the sample can only
/// point at; that is a limitation of the importer, recorded in the backlog,
/// not something a sample can paper over.
const ImportSample purchaseImportSample = ImportSample(
  fileName: 'purchase_orders_sample.csv',
  columns: [
    'BranchId',
    'WarehouseId',
    'VendorId',
    'ProductId',
    'PurchaseDate',
    'OrderedQty',
    'UnitPrice',
    'PoNumber',
    'Remarks',
    'PurchaseUomId',
    'InventoryUomId',
    'TaxProfileId',
    'ExpectedDeliveryDate',
    'Status',
  ],
  example: [
    '<id of an existing branch>',
    '<id of an existing warehouse>',
    '<id of an existing vendor>',
    '<id of an existing product>',
    '2026-09-01',
    '10',
    '250.00',
    // Blank: the server numbers the order from its own series.
    '',
    'Sample order',
    '',
    '',
    '',
    '2026-09-15',
    'DRAFT',
  ],
);
