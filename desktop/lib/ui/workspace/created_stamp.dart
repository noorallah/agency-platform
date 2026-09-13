/// When a record was made, in the reader's own clock, to the minute.
///
/// A document grid sorted by its business date puts every document raised
/// today on one date, and the one raised a minute ago was indistinguishable
/// from the one raised at nine -- the owner could not find the draft they had
/// just made (plan section 9, 2026-09-13). The server's `created_at` is an
/// ISO instant with an offset; this renders it as `2026-09-13 11:42` in local
/// time, and nothing for a value that is missing or unreadable.
String createdStamp(Object? iso) {
  if (iso == null) return '';
  final DateTime? instant = DateTime.tryParse('$iso');
  if (instant == null) return '';
  final DateTime local = instant.toLocal();
  String two(int n) => n.toString().padLeft(2, '0');
  return '${local.year}-${two(local.month)}-${two(local.day)} '
      '${two(local.hour)}:${two(local.minute)}';
}
