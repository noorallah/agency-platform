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

/// A document's one Date cell: its business [date], with the minute it was
/// entered when that was the same day, and the day it was entered when it
/// was backdated -- `2026-09-27 10:42`, `2026-09-20 (entered 2026-09-27 10:42)`.
///
/// The grids carried a Date and a Created column side by side; the owner
/// asked why two (2026-09-27), and Busy, Tally and Vyapar show one. The
/// business date leads because it is the one printed and filed; the time is
/// what tells today's documents apart.
String documentDateStamp(Object? date, Object? createdIso) {
  final String day = date == null ? '' : '$date';
  final String made = createdStamp(createdIso);
  if (made.isEmpty) return day.isEmpty ? '-' : day;
  if (day.isEmpty) return made;
  // createdStamp is `yyyy-mm-dd hh:mm`; its first ten characters are the day.
  if (made.startsWith(day)) return made;
  return '$day (entered $made)';
}
