import '../workspace/import_sample.dart';

/// The sample file for the territory importer.
///
/// The server owns the parsing here (`TerritoryService.import_csv`), so the
/// headings are spelled the way it reads them, and
/// `tests/unit/test_import_samples_match_the_server.py` on the backend fails
/// the build if the two lists ever disagree.
const ImportSample territoryImportSample = ImportSample(
  fileName: 'territories_sample.csv',
  columns: [
    'Code',
    'Name',
    'Level',
    'ParentCode',
    'Status',
    'CustomerCodes',
  ],
  example: [
    'SOUTH',
    'South Zone',
    // The display name of one of this firm's hierarchy levels.
    'Zone',
    // Blank for a top-level node; otherwise a code that exists or appears
    // earlier in the file.
    '',
    'ACTIVE',
    // Optional: the shops on this round, by customer code.
    'CUST001,CUST002',
  ],
);
