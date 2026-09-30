import 'entities.dart';

/// One row of a bulk request: the document and, when the list row carried one,
/// the version the person was looking at.
typedef BulkRow = ({String id, int? version});

/// What the server did with one row of a bulk approve or cancel.
class BulkRowResult {
  const BulkRowResult({
    required this.id,
    required this.number,
    required this.done,
    required this.message,
  });

  factory BulkRowResult.fromJson(Json json) => BulkRowResult(
        id: stringValue(json['id']),
        number: json['number'] as String?,
        done: json['outcome'] == 'DONE',
        message: json['message'] as String?,
      );

  final String id;
  final String? number;
  final bool done;
  final String? message;
}

/// The answer to a bulk approve or cancel. Rows are acted on one by one, so
/// some can be refused while the rest succeed.
class BulkActionResult {
  const BulkActionResult({
    required this.done,
    required this.refused,
    required this.results,
  });

  factory BulkActionResult.fromJson(Json json) => BulkActionResult(
        done: (json['done'] as num?)?.toInt() ?? 0,
        refused: (json['refused'] as num?)?.toInt() ?? 0,
        results: [
          for (final dynamic row in (json['results'] as List?) ?? const [])
            if (row is Map) BulkRowResult.fromJson(Json.from(row)),
        ],
      );

  final int done;
  final int refused;
  final List<BulkRowResult> results;

  /// The rows the server refused, for the result dialog and for a retry.
  List<BulkRowResult> get refusedRows =>
      results.where((row) => !row.done).toList(growable: false);
}
