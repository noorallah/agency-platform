import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:flutter_test/flutter_test.dart';

/// A paged screen's total is `pagination.total_records`, the field the server
/// sends.
///
/// Delivery Notes, Purchase Invoices and Purchase Returns read
/// `pagination.total`, which is never sent, and showed the rows on one page as
/// the whole count -- 20 of FOOD01's 49 delivery notes, with no second page
/// (manual plan item 13.9c3, 2026-09-15).
void main() {
  test('the total is read from total_records', () {
    expect(
      pagedTotal(
        {
          'data': const [],
          'pagination': {'page': 1, 'page_size': 20, 'total_records': 49},
        },
        fallback: 20,
      ),
      49,
    );
  });

  test('without pagination the rows on the page are all there is', () {
    expect(pagedTotal({'data': const []}, fallback: 7), 7);
  });

  test('no screen reads the total from a field the server does not send', () {
    final List<String> offenders = [
      for (final FileSystemEntity file
          in Directory('lib').listSync(recursive: true))
        if (file is File &&
            file.path.endsWith('.dart') &&
            file.readAsStringSync().contains("['pagination']['total']"))
          file.path,
    ];
    expect(offenders, isEmpty);
  });
}
