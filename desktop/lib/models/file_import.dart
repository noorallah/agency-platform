import 'entities.dart';

int _count(dynamic value) => (value as num?)?.toInt() ?? 0;

/// One problem the server found in a import file.
class FileImportIssue {
  const FileImportIssue({
    required this.row,
    required this.message,
    required this.text,
    this.code,
    this.column,
  });

  factory FileImportIssue.fromJson(Json json) => FileImportIssue(
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

/// What the server made of a import file, checked or applied.
class FileImportReport {
  const FileImportReport({
    required this.rows,
    required this.toCreate,
    required this.toUpdate,
    required this.skippedBlank,
    required this.columnsUsed,
    required this.columnsIgnored,
    required this.issues,
    required this.imported,
  });

  factory FileImportReport.fromJson(Json json) => FileImportReport(
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
                    FileImportIssue.fromJson(Map<String, dynamic>.from(item)))
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
  final List<FileImportIssue> issues;

  /// True only when the whole file was written.
  final bool imported;

  bool get isClean => issues.isEmpty;
}

/// One column of an import's template, as the mapping step lists it.
class ImportColumn {
  const ImportColumn({
    required this.heading,
    required this.required,
    required this.takes,
    required this.example,
  });

  factory ImportColumn.fromJson(Json json) => ImportColumn(
        heading: stringValue(json['heading']),
        required: json['required'] == true,
        takes: stringValue(json['takes']),
        example: stringValue(json['example']),
      );

  final String heading;
  final bool required;
  final String takes;
  final String example;
}

Map<String, String?> _mappingOf(dynamic value) => value is Map
    ? <String, String?>{
        for (final MapEntry<dynamic, dynamic> entry in value.entries)
          entry.key.toString(): entry.value?.toString(),
      }
    : <String, String?>{};

/// What a file holds and how the server would read it today (B3).
class ImportPreview {
  const ImportPreview({
    required this.fileHeadings,
    required this.columns,
    required this.suggested,
    required this.sampleRows,
  });

  factory ImportPreview.fromJson(Json json) => ImportPreview(
        fileHeadings: stringList(json['file_headings']),
        columns: json['columns'] is List
            ? (json['columns'] as List)
                .whereType<Map>()
                .map((item) =>
                    ImportColumn.fromJson(Map<String, dynamic>.from(item)))
                .toList()
            : const [],
        suggested: _mappingOf(json['suggested']),
        sampleRows: json['sample_rows'] is List
            ? (json['sample_rows'] as List)
                .whereType<List>()
                .map((row) => row.map((cell) => cell?.toString() ?? '').toList())
                .toList()
            : const [],
      );

  final List<String> fileHeadings;
  final List<ImportColumn> columns;

  /// File heading to template column, or null where it would be left out.
  final Map<String, String?> suggested;
  final List<List<String>> sampleRows;
}

/// A mapping saved under a name for one kind of import.
class ImportMapping {
  const ImportMapping({
    required this.id,
    required this.kind,
    required this.name,
    required this.mapping,
  });

  factory ImportMapping.fromJson(Json json) => ImportMapping(
        id: stringValue(json['id']),
        kind: stringValue(json['kind']),
        name: stringValue(json['name']),
        mapping: _mappingOf(json['mapping']),
      );

  final String id;
  final String kind;
  final String name;
  final Map<String, String?> mapping;
}
