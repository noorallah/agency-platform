// The minute a document was made, shown beside its business date.
//
// A grid sorted by order date puts every document raised today on one date,
// so the draft raised a minute ago looked like the one raised at nine. The
// stamp is what tells them apart, and it must render in the reader's own
// clock and say nothing rather than something wrong for a value it cannot
// read.

import 'package:agency_desktop/ui/workspace/created_stamp.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('an ISO instant renders as a local date and minute', () {
    final DateTime instant = DateTime.parse('2026-09-13T06:12:44.123456+00:00');
    final DateTime local = instant.toLocal();
    String two(int n) => n.toString().padLeft(2, '0');
    expect(
      createdStamp('2026-09-13T06:12:44.123456+00:00'),
      '${local.year}-${two(local.month)}-${two(local.day)} '
      '${two(local.hour)}:${two(local.minute)}',
    );
    expect(RegExp(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$')
        .hasMatch(createdStamp('2026-09-13T11:42:00+05:30')), isTrue);
  });

  test('a missing or unreadable value shows nothing, not a guess', () {
    expect(createdStamp(null), '');
    expect(createdStamp(''), '');
    expect(createdStamp('yesterday'), '');
  });
}
