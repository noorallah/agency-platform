// The Period filter on the sales lists (owner, 2026-09-27): named periods
// fall where an Indian business expects them, the arrows step them, and the
// list is asked for exactly those dates.

import 'package:agency_desktop/ui/workspace/desktop_framework.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _span(DatePeriod p) =>
    '${DatePeriod.iso(p.from!)}..${DatePeriod.iso(p.to!)}';

void main() {
  final DateTime today = DateTime(2026, 9, 27);

  test('named periods, with the financial year from April', () {
    expect(_span(DatePeriod.of(PeriodKind.today, today)),
        '2026-09-27..2026-09-27');
    expect(_span(DatePeriod.of(PeriodKind.week, today)),
        '2026-09-21..2026-09-27');
    expect(_span(DatePeriod.of(PeriodKind.month, today)),
        '2026-09-01..2026-09-30');
    expect(_span(DatePeriod.of(PeriodKind.lastMonth, today)),
        '2026-08-01..2026-08-31');
    expect(_span(DatePeriod.of(PeriodKind.quarter, today)),
        '2026-07-01..2026-09-30');
    expect(_span(DatePeriod.of(PeriodKind.quarter, DateTime(2027, 2, 10))),
        '2027-01-01..2027-03-31');
    expect(_span(DatePeriod.of(PeriodKind.financialYear, today)),
        '2026-04-01..2027-03-31');
    expect(_span(DatePeriod.of(PeriodKind.financialYear, DateTime(2027, 3, 5))),
        '2026-04-01..2027-03-31');
    expect(_span(DatePeriod.of(PeriodKind.lastFinancialYear, today)),
        '2025-04-01..2026-03-31');
    expect(const DatePeriod.all().query('from', 'to'), isEmpty);
  });

  test('the arrows step a period by its own length', () {
    final DatePeriod month = DatePeriod.of(PeriodKind.month, today);
    expect(_span(month.shifted(-1)), '2026-08-01..2026-08-31');
    expect(_span(month.shifted(1)), '2026-10-01..2026-10-31');
    expect(_span(DatePeriod.of(PeriodKind.quarter, today).shifted(1)),
        '2026-10-01..2026-12-31');
    expect(_span(DatePeriod.of(PeriodKind.financialYear, today).shifted(-1)),
        '2025-04-01..2026-03-31');
    expect(_span(DatePeriod.of(PeriodKind.today, today).shifted(-1)),
        '2026-09-26..2026-09-26');
    final DatePeriod custom =
        DatePeriod.custom(DateTime(2026, 9, 1), DateTime(2026, 9, 10));
    expect(_span(custom.shifted(1)), '2026-09-11..2026-09-20');
  });

  test('the button names the period, or its dates once moved', () {
    final DatePeriod month = DatePeriod.of(PeriodKind.month, today);
    expect(month.label(today), 'This month');
    expect(month.shifted(-1).label(today), '01-08-2026 – 31-08-2026');
    expect(const DatePeriod.all().label(today), 'All dates');
    expect(month.query('order_from', 'order_to'),
        {'order_from': '2026-09-01', 'order_to': '2026-09-30'});
  });

  testWidgets('choosing a period reports it; the arrows appear with it',
      (tester) async {
    DatePeriod value = const DatePeriod.all();
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: StatefulBuilder(
          builder: (context, setState) => DateRangeFilter(
            value: value,
            today: today,
            onChanged: (next) => setState(() => value = next),
          ),
        ),
      ),
    ));
    expect(find.byKey(const ValueKey('period-back')), findsNothing);

    await tester.tap(find.byKey(const ValueKey('period-button')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('period-month')));
    await tester.pumpAndSettle();
    expect(find.text('This month'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('period-back')));
    await tester.pumpAndSettle();
    expect(find.text('01-08-2026 – 31-08-2026'), findsOneWidget);
  });
}
