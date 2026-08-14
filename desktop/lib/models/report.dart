import 'entities.dart';

/// One column of a report grid.
class ReportColumn {
  const ReportColumn({required this.key, required this.label, this.numeric = false});

  final String key;
  final String label;
  final bool numeric;
}

/// Which part of the business a report belongs to, and therefore which tab it
/// appears under.
enum ReportArea {
  /// What is moving: orders, dispatches, receipts, returns.
  operational,

  /// What is owed and what it is worth.
  financial,
}

/// One report the server can produce.
///
/// A definition rather than a screen. Every report endpoint answers with flat
/// rows in the standard envelope, so the difference between them is a path, a
/// name and which columns are worth showing -- which is data, not code. Thirty
/// four hand-written screens would be thirty four places for the same grid to
/// drift.
class ReportDefinition {
  const ReportDefinition({
    required this.id,
    required this.label,
    required this.description,
    required this.path,
    required this.area,
    this.columns = const [],
  });

  final String id;
  final String label;

  /// What question this report answers, shown above the grid. A report called
  /// "Reconciliation" tells nobody what it reconciles.
  final String description;
  final String path;
  final ReportArea area;

  /// The columns worth showing, when the defaults are not enough. Left empty,
  /// the grid derives them from the rows themselves.
  final List<ReportColumn> columns;
}

/// Work out which columns to show for a set of rows.
///
/// Identifiers are dropped: a report that leads with `invoice_id` shows a
/// reader a UUID where they wanted an invoice number, and every one of these
/// records carries the readable field beside the key. Nested values go too --
/// several of these endpoints answer with whole documents, whose `lines` and
/// `attachments` have no meaning as one cell. A definition can still name its
/// columns explicitly, which the document-shaped reports do because forty
/// derived columns is not a report.
List<ReportColumn> columnsFor(
  ReportDefinition definition,
  List<Json> rows,
) {
  if (definition.columns.isNotEmpty) return definition.columns;
  if (rows.isEmpty) return const [];
  return [
    for (final MapEntry<String, dynamic> entry in rows.first.entries)
      if (!_isIdentifier(entry.key) && entry.value is! List && entry.value is! Map)
        ReportColumn(
          key: entry.key,
          label: _humanise(entry.key),
          numeric: _looksNumeric(entry.value),
        ),
  ];
}

/// Whether a key names a record rather than describing one.
bool _isIdentifier(String key) => key == 'id' || key.endsWith('_id');

/// Turn `grand_total` into `Grand total`.
String _humanise(String key) {
  final String spaced = key.replaceAll('_', ' ');
  return spaced.isEmpty ? spaced : spaced[0].toUpperCase() + spaced.substring(1);
}

/// Whether a value should sit against the right edge like money does.
///
/// Decimals arrive as strings so they keep their precision, so the type alone
/// does not say: a value that parses as a number and is not a date is one.
bool _looksNumeric(dynamic value) {
  if (value is num) return true;
  if (value is! String) return false;
  if (value.contains('-') || value.contains(':')) return false;
  return double.tryParse(value) != null;
}

/// Render one cell, keeping empty distinguishable from zero.
String cellValue(Json row, String key) {
  final dynamic value = row[key];
  if (value == null) return '—';
  return '$value';
}
