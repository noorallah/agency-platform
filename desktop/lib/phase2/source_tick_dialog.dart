import 'dart:math' as math;

import 'package:flutter/material.dart';

/// One document a bill could be raised from, as the tick list shows it.
class SourceTickRow {
  const SourceTickRow({
    required this.id,
    required this.number,
    required this.date,
    this.order = '',
    this.amount = '',
  });

  final String id;
  final String number;
  final String date;
  final String order;
  final String amount;
}

/// Why [candidateId] cannot share a bill with the documents already ticked,
/// or null where it can.
typedef SourceClash = String? Function(String candidateId, Set<String> ticked);

/// The tick list of SEL-1 (backlog 58 items 2 and 4): the customer's or the
/// supplier's documents with something left to bill, any number of them
/// ticked onto one bill.
///
/// A document that cannot share the bill with those already ticked -- another
/// branch, another salesman, territory or route -- cannot be ticked, and says
/// which field and which document it clashes with, so the mix is refused here
/// rather than by the server on save. Answers the ticked ids in list order, or
/// null when dismissed.
Future<List<String>?> showSourceTickDialog(
  BuildContext context, {
  required String title,
  required String keyPrefix,
  required List<SourceTickRow> rows,
  required Set<String> initial,
  required SourceClash clashFor,
  String numberLabel = 'Number',
  String amountLabel = 'Value left',
  String confirmNoun = 'note',
}) {
  return showDialog<List<String>>(
    context: context,
    builder: (context) => _SourceTickDialog(
      title: title,
      keyPrefix: keyPrefix,
      rows: rows,
      initial: initial,
      clashFor: clashFor,
      numberLabel: numberLabel,
      amountLabel: amountLabel,
      confirmNoun: confirmNoun,
    ),
  );
}

class _SourceTickDialog extends StatefulWidget {
  const _SourceTickDialog({
    required this.title,
    required this.keyPrefix,
    required this.rows,
    required this.initial,
    required this.clashFor,
    required this.numberLabel,
    required this.amountLabel,
    required this.confirmNoun,
  });

  final String title;
  final String keyPrefix;
  final List<SourceTickRow> rows;
  final Set<String> initial;
  final SourceClash clashFor;
  final String numberLabel;
  final String amountLabel;
  final String confirmNoun;

  @override
  State<_SourceTickDialog> createState() => _SourceTickDialogState();
}

class _SourceTickDialogState extends State<_SourceTickDialog> {
  late final Set<String> _ticked = <String>{...widget.initial};

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final TextStyle? head = theme.textTheme.labelSmall
        ?.copyWith(color: theme.colorScheme.onSurfaceVariant);
    final int count = _ticked.length;
    return AlertDialog(
      title: Text(widget.title),
      // Wide enough that a document number with its firm and branch codes
      // (`GRN-QA01-HO-2026-2027-000003`, and longer seeded ones) prints
      // whole: at 620 the number and order columns cut them to "GRN-QA01-H…"
      // and the receipts could only be told apart by their amounts
      // (D-UI-7). Narrower screens still get the whole dialog.
      content: SizedBox(
        width: math.min(900, MediaQuery.sizeOf(context).width - 120),
        height: 380,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Padding(
              padding: const EdgeInsets.only(left: 48, bottom: 4),
              child: Row(
                children: [
                  Expanded(flex: 5, child: Text(widget.numberLabel, style: head)),
                  Expanded(flex: 2, child: Text('Date', style: head)),
                  Expanded(flex: 5, child: Text('Order', style: head)),
                  Expanded(
                    flex: 2,
                    child: Text(widget.amountLabel,
                        style: head, textAlign: TextAlign.right),
                  ),
                ],
              ),
            ),
            const Divider(height: 1),
            Expanded(
              child: ListView(
                children: [
                  for (final SourceTickRow row in widget.rows)
                    _row(context, row),
                ],
              ),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
        FilledButton(
          key: ValueKey<String>('${widget.keyPrefix}-tick-done'),
          onPressed: count == 0
              ? null
              : () => Navigator.of(context).pop(<String>[
                    for (final SourceTickRow row in widget.rows)
                      if (_ticked.contains(row.id)) row.id,
                  ]),
          child: Text(count == 1
              ? 'Bill 1 ${widget.confirmNoun}'
              : 'Bill $count ${widget.confirmNoun}s'),
        ),
      ],
    );
  }

  Widget _row(BuildContext context, SourceTickRow row) {
    final ThemeData theme = Theme.of(context);
    final bool ticked = _ticked.contains(row.id);
    final String? clash = ticked
        ? null
        : widget.clashFor(row.id, Set<String>.unmodifiable(_ticked));
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Checkbox(
                key: ValueKey<String>('${widget.keyPrefix}-tick-${row.id}'),
                value: ticked,
                onChanged: clash != null
                    ? null
                    : (value) => setState(() {
                          if (value ?? false) {
                            _ticked.add(row.id);
                          } else {
                            _ticked.remove(row.id);
                          }
                        }),
              ),
              const SizedBox(width: 8),
              Expanded(
                flex: 5,
                child: Text(row.number, overflow: TextOverflow.ellipsis),
              ),
              Expanded(flex: 2, child: Text(row.date)),
              Expanded(
                flex: 5,
                child: Text(row.order.isEmpty ? '—' : row.order,
                    overflow: TextOverflow.ellipsis),
              ),
              Expanded(
                flex: 2,
                child: Text(row.amount, textAlign: TextAlign.right),
              ),
            ],
          ),
          if (clash != null)
            Padding(
              padding: const EdgeInsets.only(left: 48, bottom: 2),
              child: Text(
                clash,
                key: ValueKey<String>('${widget.keyPrefix}-clash-${row.id}'),
                style: theme.textTheme.bodySmall?.copyWith(
                  fontSize: 11,
                  color: theme.colorScheme.error,
                ),
              ),
            ),
        ],
      ),
    );
  }
}
