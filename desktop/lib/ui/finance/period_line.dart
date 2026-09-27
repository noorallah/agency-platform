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
  });

  final List<AccountingPeriod> periods;
  final AccountingPeriod? value;
  final ValueChanged<AccountingPeriod> onChanged;
  final VoidCallback? onRefresh;
  final String hint;

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
        ...trailing,
        Phase2Refresh(onPressed: onRefresh, child: const SizedBox.shrink()),
      ]);
}
