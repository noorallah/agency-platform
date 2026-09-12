import '../../core/api/api_client.dart';

/// The sentence a refused request should show: the server's message, and
/// beneath it every field the refusal names.
///
/// A validation refusal arrives as "The request validation failed." with the
/// detail in `details` -- `body.lines.0.unit_price` and a message -- which is
/// the one part the person needs and which every editor used to drop. A row
/// index becomes a row number as a spreadsheet counts them; the `body.`
/// prefix is noise and goes.
String refusalMessage(ApiException error) {
  final Object? details = error.details;
  final List<String> lines = <String>[];
  if (details is List) {
    for (final Object? item in details) {
      if (item is! Map) continue;
      final String field = '${item['field'] ?? ''}'.replaceFirst(
        RegExp(r'^body\.'),
        '',
      );
      final String message = '${item['message'] ?? ''}';
      if (message.isEmpty) continue;
      final RegExpMatch? indexed =
          RegExp(r'^([a-z_]+)\.(\d+)(?:\.(.+))?$').firstMatch(field);
      if (indexed != null) {
        final int row = int.parse(indexed.group(2)!) + 1;
        final String? name = indexed.group(3);
        lines.add(name == null
            ? '${indexed.group(1)} $row: $message'
            : '${indexed.group(1)} $row, $name: $message');
      } else {
        lines.add(field.isEmpty ? message : '$field: $message');
      }
    }
  }
  if (lines.isEmpty) return error.message;
  return '${error.message}\n${lines.join('\n')}';
}
