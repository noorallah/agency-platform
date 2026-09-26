// Which accounting period a statement opens on (2026-09-26).
//
// Opening the books creates all twelve periods at once, so the trial
// balance, P&L, balance sheet and ledger -- which opened on the newest --
// all showed March, months ahead and empty. They open on today's period.

import 'package:agency_desktop/models/finance.dart';
import 'package:flutter_test/flutter_test.dart';

AccountingPeriod _month(int number, String starts, String ends) =>
    AccountingPeriod(
      id: 'p$number',
      financialYearId: 'fy',
      periodNumber: number,
      code: 'P$number',
      name: 'Period $number',
      startsOn: starts,
      endsOn: ends,
      status: 'OPEN',
    );

final List<AccountingPeriod> _year = [
  _month(12, '2027-03-01', '2027-03-31'),
  _month(6, '2026-09-01', '2026-09-30'),
  _month(5, '2026-08-01', '2026-08-31'),
  _month(1, '2026-04-01', '2026-04-30'),
];

void main() {
  test('a statement opens on the period today falls in', () {
    expect(currentPeriod(_year, today: DateTime(2026, 9, 26))?.id, 'p6');
  });

  test('in a gap, the latest period that has started', () {
    // No period holds July here; August has not begun, April has.
    expect(currentPeriod(_year, today: DateTime(2026, 7, 10))?.id, 'p1');
  });

  test('before the year begins, the first listed', () {
    expect(currentPeriod(_year, today: DateTime(2025, 1, 1))?.id, 'p12');
  });

  test('no periods, no period', () {
    expect(currentPeriod(const []), isNull);
  });
}
