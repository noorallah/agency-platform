import 'package:flutter/material.dart';

import '../../models/finance.dart';
import '../workspace/desktop_framework.dart';

/// Phase 2's page line for a statement read over one accounting period --
/// trial balance, profit and loss, balance sheet, a ledger.
///
/// Each drew its own band above the table: a wide period dropdown, a chip
/// and a refresh button. 4.5 allows nothing above the grid but the page line
/// (review, 2026-09-27), so the picker, anything the screen adds beside it
/// and the line's refresh icon go there.
class AccountingPeriodLine extends StatelessWidget {
  const AccountingPeriodLine({
    super.key,
    required this.periods,
    required this.value,
    required this.onChanged,
    required this.onRefresh,
    this.hint = 'Accounting period',
    this.leading = const [],
    this.trailing = const [],
    this.toValue,
    this.onToChanged,
  });

  final List<AccountingPeriod> periods;
  final AccountingPeriod? value;
  final ValueChanged<AccountingPeriod> onChanged;
  final VoidCallback? onRefresh;
  final String hint;

  /// The last month of a run of months (backlog 50 item 5); null is the
  /// chosen month on its own. Offered only where [onToChanged] is given --
  /// the trial balance and a ledger -- and only months of the chosen
  /// month's own financial year from it onwards, because the server refuses
  /// a span across two years or a backwards one.
  final AccountingPeriod? toValue;
  final ValueChanged<AccountingPeriod?>? onToChanged;

  List<AccountingPeriod> get _laterInYear {
    final AccountingPeriod? from = value;
    if (from == null) return const [];
    return [
      for (final AccountingPeriod period in periods)
        if (period.financialYearId == from.financialYearId &&
            period.startsOn.compareTo(from.startsOn) > 0)
          period,
    ]..sort((a, b) => a.startsOn.compareTo(b.startsOn));
  }

  /// Pickers before the period (a ledger's account).
  final List<Widget> leading;

  /// What follows the period (a Balanced chip).
  final List<Widget> trailing;

  @override
  Widget build(BuildContext context) => Phase2LineTools(children: [
        ...leading,
        SizedBox(
          width: 240,
          child: DropdownButtonFormField<String>(
            key: const ValueKey('period-line'),
            initialValue: value?.id,
            isExpanded: true,
            decoration: InputDecoration(isDense: true, hintText: hint),
            items: [
              for (final AccountingPeriod period in periods)
                DropdownMenuItem<String>(
                  value: period.id,
                  child: Text(period.label, overflow: TextOverflow.ellipsis),
                ),
            ],
            onChanged: (id) {
              final AccountingPeriod? match =
                  periods.where((period) => period.id == id).firstOrNull;
              if (match != null) onChanged(match);
            },
          ),
        ),
        if (onToChanged != null)
          SizedBox(
            width: 200,
            child: DropdownButtonFormField<String>(
              // Keyed on the first month, so choosing another one starts the
              // list again rather than keeping a month it no longer offers.
              key: ValueKey('period-line-to-${value?.id}'),
              initialValue: toValue?.id ?? '',
              isExpanded: true,
              decoration: const InputDecoration(isDense: true, prefixText: 'to  '),
              items: [
                const DropdownMenuItem<String>(
                  value: '',
                  child: Text('the same month'),
                ),
                for (final AccountingPeriod period in _laterInYear)
                  DropdownMenuItem<String>(
                    value: period.id,
                    child: Text(period.label, overflow: TextOverflow.ellipsis),
                  ),
              ],
              onChanged: (id) => onToChanged!(
                  periods.where((period) => period.id == id).firstOrNull),
            ),
          ),
        ...trailing,
        Phase2Refresh(onPressed: onRefresh, child: const SizedBox.shrink()),
      ]);
}
