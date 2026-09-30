import 'entities.dart';

int _count(dynamic value) => (value as num?)?.toInt() ?? 0;

/// One problem the server found in a product import file.
class ProductImportIssue {
  const ProductImportIssue({
    required this.row,
    required this.message,
    required this.text,
    this.code,
    this.column,
  });

  factory ProductImportIssue.fromJson(Json json) => ProductImportIssue(
        row: _count(json['row']),
        code: json['code'] == null ? null : stringValue(json['code']),
        column: json['column'] == null ? null : stringValue(json['column']),
        message: stringValue(json['message']),
        text: stringValue(json['text']),
      );

  /// The spreadsheet row, the header being row 1.
  final int row;
  final String? code;
  final String? column;
  final String message;

  /// The sentence to show a person.
  final String text;
}

/// What the server made of a product import file, checked or applied.
class ProductImportReport {
  const ProductImportReport({
    required this.rows,
    required this.toCreate,
    required this.toUpdate,
    required this.skippedBlank,
    required this.columnsUsed,
    required this.columnsIgnored,
    required this.issues,
    required this.imported,
  });

  factory ProductImportReport.fromJson(Json json) => ProductImportReport(
        rows: _count(json['rows']),
        toCreate: _count(json['to_create']),
        toUpdate: _count(json['to_update']),
        skippedBlank: _count(json['skipped_blank']),
        columnsUsed: stringList(json['columns_used']),
        columnsIgnored: stringList(json['columns_ignored']),
        issues: json['issues'] is List
            ? (json['issues'] as List)
                .whereType<Map>()
                .map((item) =>
                    ProductImportIssue.fromJson(Map<String, dynamic>.from(item)))
                .toList()
            : const [],
        imported: json['imported'] == true,
      );

  final int rows;
  final int toCreate;
  final int toUpdate;
  final int skippedBlank;
  final List<String> columnsUsed;
  final List<String> columnsIgnored;
  final List<ProductImportIssue> issues;

  /// True only when the whole file was written.
  final bool imported;

  bool get isClean => issues.isEmpty;
}
