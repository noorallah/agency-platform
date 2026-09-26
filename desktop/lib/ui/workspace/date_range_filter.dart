import 'package:flutter/material.dart';

/// The kinds of period a list can be narrowed to.
enum PeriodKind {
  all('All dates'),
  today('Today'),
  yesterday('Yesterday'),
  week('This week'),
  month('This month'),
  lastMonth('Last month'),
  quarter('This quarter'),
  financialYear('This financial year'),
  lastFinancialYear('Last financial year'),
  custom('Custom range…');

  const PeriodKind(this.label);

  final String label;
}

/// A span of document dates, both ends included; [from] and [to] are null
/// for every date.
///
/// The owner asked for the sales lists to be filtered by a date or between
/// two, and to adjust the dates (2026-09-27). Busy, Tally and Vyapar offer
/// the same: named periods -- the Indian financial year runs April to March
/// and its quarters with it -- a custom range, and arrows that step the
/// period back or forward.
@immutable
class DatePeriod {
  const DatePeriod._(this.kind, this.from, this.to);

  const DatePeriod.all() : this._(PeriodKind.all, null, null);

  factory DatePeriod.custom(DateTime from, DateTime to) =>
      DatePeriod._(PeriodKind.custom, _day(from), _day(to));

  /// [kind] as it falls around [today].
  factory DatePeriod.of(PeriodKind kind, DateTime today) {
    final DateTime d = _day(today);
    switch (kind) {
      case PeriodKind.all:
        return const DatePeriod.all();
      case PeriodKind.today:
        return DatePeriod._(kind, d, d);
      case PeriodKind.yesterday:
        final DateTime y = d.subtract(const Duration(days: 1));
        return DatePeriod._(kind, y, y);
      case PeriodKind.week:
        final DateTime monday = d.subtract(Duration(days: d.weekday - 1));
        return DatePeriod._(kind, monday, monday.add(const Duration(days: 6)));
      case PeriodKind.month:
        return DatePeriod._(
            kind, DateTime(d.year, d.month), DateTime(d.year, d.month + 1, 0));
      case PeriodKind.lastMonth:
        return DatePeriod._(
            kind, DateTime(d.year, d.month - 1), DateTime(d.year, d.month, 0));
      case PeriodKind.quarter:
        // Financial quarters: Apr-Jun, Jul-Sep, Oct-Dec, Jan-Mar.
        // The quarter's first month is never after today's, so it is in
        // this calendar year: 4, 7, 10 or 13 (January).
        final int start = ((d.month - 4) % 12) ~/ 3 * 3 + 4;
        final DateTime from = DateTime(d.year, start > 12 ? start - 12 : start);
        return DatePeriod._(kind, from, DateTime(from.year, from.month + 3, 0));
      case PeriodKind.financialYear:
        final int year = d.month >= 4 ? d.year : d.year - 1;
        return DatePeriod._(kind, DateTime(year, 4), DateTime(year + 1, 4, 0));
      case PeriodKind.lastFinancialYear:
        final int year = (d.month >= 4 ? d.year : d.year - 1) - 1;
        return DatePeriod._(kind, DateTime(year, 4), DateTime(year + 1, 4, 0));
      case PeriodKind.custom:
        return DatePeriod._(kind, d, d);
    }
  }

  final PeriodKind kind;
  final DateTime? from;
  final DateTime? to;

  bool get isAll => from == null && to == null;

  /// The same span moved [steps] periods back (negative) or forward: a month
  /// by a month, a quarter by three, a year by twelve, a day or a custom
  /// range by its own length.
  DatePeriod shifted(int steps) {
    final DateTime? a = from;
    final DateTime? b = to;
    if (a == null || b == null) return this;
    int months = 0;
    switch (kind) {
      case PeriodKind.month:
      case PeriodKind.lastMonth:
        months = 1;
      case PeriodKind.quarter:
        months = 3;
      case PeriodKind.financialYear:
      case PeriodKind.lastFinancialYear:
        months = 12;
      default:
        months = 0;
    }
    if (months > 0) {
      final DateTime start = DateTime(a.year, a.month + months * steps);
      return DatePeriod._(
          kind, start, DateTime(start.year, start.month + months, 0));
    }
    final int days = b.difference(a).inDays + 1;
    return DatePeriod._(
      // A stepped Today is no longer today: it reads as its dates.
      kind == PeriodKind.week ? kind : PeriodKind.custom,
      a.add(Duration(days: days * steps)),
      b.add(Duration(days: days * steps)),
    );
  }

  /// What the button says: the period's name while it is the named one,
  /// else its dates.
  String label(DateTime today) {
    if (isAll) return PeriodKind.all.label;
    if (kind != PeriodKind.custom && DatePeriod.of(kind, today) == this) {
      return kind.label;
    }
    return from == to ? show(from!) : '${show(from!)} – ${show(to!)}';
  }

  /// `from`/`to` query values under the list's own parameter names.
  Map<String, String> query(String fromKey, String toKey) => {
        if (from != null) fromKey: iso(from!),
        if (to != null) toKey: iso(to!),
      };

  static DateTime _day(DateTime value) =>
      DateTime(value.year, value.month, value.day);

  static String _two(int n) => n.toString().padLeft(2, '0');

  /// `2026-09-27`, as the server reads a date.
  static String iso(DateTime d) => '${d.year}-${_two(d.month)}-${_two(d.day)}';

  /// `27-09-2026`, as India writes one.
  static String show(DateTime d) => '${_two(d.day)}-${_two(d.month)}-${d.year}';

  @override
  bool operator ==(Object other) =>
      other is DatePeriod && other.from == from && other.to == to;

  @override
  int get hashCode => Object.hash(from, to);
}

/// The Period control beside a list's search: ◀, the period, ▶.
class DateRangeFilter extends StatelessWidget {
  const DateRangeFilter({
    super.key,
    required this.value,
    required this.onChanged,
    this.today,
  });

  final DatePeriod value;
  final ValueChanged<DatePeriod> onChanged;

  /// For tests; the clock otherwise.
  final DateTime? today;

  DateTime get _today => today ?? DateTime.now();

  @override
  Widget build(BuildContext context) {
    final bool steps = !value.isAll;
    return Row(mainAxisSize: MainAxisSize.min, children: [
      if (steps)
        IconButton(
          key: const ValueKey('period-back'),
          tooltip: 'Previous period',
          visualDensity: VisualDensity.compact,
          icon: const Icon(Icons.chevron_left),
          onPressed: () => onChanged(value.shifted(-1)),
        ),
      // Shrinks with an ellipsis rather than overflow a narrow line.
      Flexible(
        child: MenuAnchor(
          menuChildren: [
            for (final PeriodKind kind in PeriodKind.values)
              MenuItemButton(
                key: ValueKey('period-${kind.name}'),
                onPressed: () => _choose(context, kind),
                child: Text(kind.label),
              ),
          ],
          builder: (context, controller, _) => OutlinedButton.icon(
            key: const ValueKey('period-button'),
            onPressed: () =>
                controller.isOpen ? controller.close() : controller.open(),
            icon: const Icon(Icons.calendar_month_outlined, size: 18),
            label: Text(
              value.label(_today),
              overflow: TextOverflow.ellipsis,
              maxLines: 1,
            ),
          ),
        ),
      ),
      if (steps)
        IconButton(
          key: const ValueKey('period-forward'),
          tooltip: 'Next period',
          visualDensity: VisualDensity.compact,
          icon: const Icon(Icons.chevron_right),
          onPressed: () => onChanged(value.shifted(1)),
        ),
    ]);
  }

  Future<void> _choose(BuildContext context, PeriodKind kind) async {
    if (kind != PeriodKind.custom) {
      onChanged(DatePeriod.of(kind, _today));
      return;
    }
    final DateTime now = _today;
    final DateTimeRange? range = await showDateRangePicker(
      context: context,
      firstDate: DateTime(2000),
      lastDate: DateTime(now.year + 5),
      initialDateRange: value.isAll
          ? DateTimeRange(start: DateTime(now.year, now.month), end: now)
          : DateTimeRange(start: value.from!, end: value.to!),
      helpText: 'Documents dated between',
    );
    if (range != null) onChanged(DatePeriod.custom(range.start, range.end));
  }
}
