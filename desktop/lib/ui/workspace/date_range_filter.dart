import 'package:flutter/material.dart';

import 'workspace_components.dart';

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

  /// [kind] as it falls around [today], in a financial year that begins
  /// with [yearStartMonth] -- the firm's own, April unless it says otherwise.
  factory DatePeriod.of(
    PeriodKind kind,
    DateTime today, {
    int yearStartMonth = DateTime.april,
  }) {
    final DateTime d = _day(today);
    final int m = yearStartMonth;
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
        // Financial quarters, counted from the year's first month: Apr-Jun,
        // Jul-Sep, Oct-Dec, Jan-Mar for an April year. Today is zero, one
        // or two months into its quarter.
        final DateTime from =
            DateTime(d.year, d.month - ((d.month - m) % 12) % 3);
        return DatePeriod._(kind, from, DateTime(from.year, from.month + 3, 0));
      case PeriodKind.financialYear:
        final int year = d.month >= m ? d.year : d.year - 1;
        return DatePeriod._(kind, DateTime(year, m), DateTime(year + 1, m, 0));
      case PeriodKind.lastFinancialYear:
        final int year = (d.month >= m ? d.year : d.year - 1) - 1;
        return DatePeriod._(kind, DateTime(year, m), DateTime(year + 1, m, 0));
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
  String label(DateTime today, {int yearStartMonth = DateTime.april}) {
    if (isAll) return PeriodKind.all.label;
    if (kind != PeriodKind.custom &&
        DatePeriod.of(kind, today, yearStartMonth: yearStartMonth) == this) {
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

/// The month the firm's financial year begins with, for everything under
/// the shell that names a year or a quarter.
///
/// The working year is a filter and not a wall (the owner, 2026-10-13): all
/// of a firm's years are in one place, a list opens on the current one, and
/// an older bill is reached by widening the dates. The month comes with the
/// firm list the shell already holds, so no screen asks for it.
class FirmYearScope extends InheritedWidget {
  const FirmYearScope({
    super.key,
    required this.startMonth,
    required super.child,
  });

  final int startMonth;

  /// April where nothing above says otherwise -- a screen pumped alone in a
  /// test. Safe from `initState`: it reads without subscribing, and a change
  /// of firm rebuilds the screens under it anyway.
  static int monthOf(BuildContext context) =>
      context.getInheritedWidgetOfExactType<FirmYearScope>()?.startMonth ??
      DateTime.april;

  @override
  bool updateShouldNotify(FirmYearScope oldWidget) =>
      startMonth != oldWidget.startMonth;
}

/// What a list of documents opens on: the firm's current financial year.
/// *All dates* and the back arrow are one click away for an older bill.
DatePeriod openingPeriod(BuildContext context, {DateTime? today}) =>
    DatePeriod.of(
      PeriodKind.financialYear,
      today ?? DateTime.now(),
      yearStartMonth: FirmYearScope.monthOf(context),
    );

/// What a list says when its period holds nothing. Not "no search results":
/// nobody searched. The list opened on the year, and an older document is
/// one choice away.
class PeriodEmptyState extends StatelessWidget {
  const PeriodEmptyState({
    super.key,
    required this.period,
    required this.searching,
  });

  final DatePeriod period;

  /// A search or another filter is on, so the dates are not the only reason.
  final bool searching;

  @override
  Widget build(BuildContext context) {
    if (searching || period.isAll) {
      return const StandardEmptyState(type: EmptyStateType.noSearchResults);
    }
    return const StandardEmptyState(
      type: EmptyStateType.noSearchResults,
      title: 'Nothing in these dates',
      message: 'Step back with the arrow beside the dates, or choose '
          'All dates, to see older ones.',
    );
  }
}

/// The Period control beside a list's search: ◀, the period, ▶.
class DateRangeFilter extends StatelessWidget {
  const DateRangeFilter({
    super.key,
    required this.value,
    required this.onChanged,
    this.today,
  });

  /// The width a toolbar keeps for this control: the two arrows and the
  /// longest thing the button says, a pair of dates.
  static const double room = 300;

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
              value.label(
                _today,
                yearStartMonth: FirmYearScope.monthOf(context),
              ),
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
      onChanged(DatePeriod.of(
        kind,
        _today,
        yearStartMonth: FirmYearScope.monthOf(context),
      ));
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
