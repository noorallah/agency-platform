import 'package:flutter/material.dart';

import '../../models/line_margin.dart';
import '../../phase2/indian_format.dart';

/// The Cost cell of a saved line: the amount, "est." where it is worked out
/// rather than recorded, blank where there is none (L3 step 5). Screen only.
Widget lineCostCell(LineMargin? margin, TextStyle? style, {Key? key}) {
  final double? cost = margin?.cost;
  return Text(
    cost == null
        ? ''
        : '${indianAmount(cost, full: true)}'
            '${margin!.costIsEstimate ? ' est.' : ''}',
    key: key,
    overflow: TextOverflow.ellipsis,
    style: style,
  );
}

/// The Margin cell of a saved line: the amount and the percentage of cost.
Widget lineMarginCell(LineMargin? margin, TextStyle? style, {Key? key}) {
  final double? amount = margin?.margin;
  final double? percent = margin?.marginPercent;
  return Text(
    amount == null
        ? ''
        : '${indianAmount(amount, full: true)}'
            '${percent == null ? '' : ' · ${percent.toStringAsFixed(1)}%'}',
    key: key,
    overflow: TextOverflow.ellipsis,
    style: style,
  );
}

/// The saved document's cost and margin in total, a quiet line above the
/// totals. [current] false says a line has been changed since the save, so
/// the figures are the saved ones until it is saved again.
class DocumentMarginStrip extends StatelessWidget {
  const DocumentMarginStrip({
    super.key,
    required this.margin,
    required this.current,
  });

  final DocumentMargin margin;
  final bool current;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final TextStyle? style = theme.textTheme.bodySmall?.copyWith(
      fontSize: 12,
      color: theme.colorScheme.onSurfaceVariant,
    );
    final double? percent = margin.percent;
    return Padding(
      padding: const EdgeInsets.fromLTRB(14, 4, 14, 2),
      child: Align(
        alignment: Alignment.centerRight,
        child: Text(
          [
            if (margin.cost != null)
              'Cost ${indianAmount(margin.cost!, full: true)}',
            if (margin.margin != null)
              'Margin ${indianAmount(margin.margin!, full: true)}'
                  '${percent == null ? '' : ' (${percent.toStringAsFixed(1)}%)'}',
            if (!current) 'as last saved',
          ].join('   ·   '),
          key: const ValueKey('document-margin-total'),
          overflow: TextOverflow.ellipsis,
          style: style,
        ),
      ),
    );
  }
}
