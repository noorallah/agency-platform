import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../models/batch_serial.dart';
import '../../phase2/document_page.dart' show documentDate;
import '../../phase2/indian_format.dart';

/// Every document one lot passed through, its arrival first (L2 step 11):
/// the lot's own facts on top, then each receipt, bill, dispatch, return and
/// correction with what it moved. Read-only.
///
/// **Server calls: one `GET /batch-serial/batches/{id}/trail` on opening.**
/// Cost shows only where the server sent it -- a firm costing by lot, to
/// somebody allowed to see cost.
class LotTrailDialog extends StatefulWidget {
  const LotTrailDialog({
    super.key,
    required this.api,
    required this.batchId,
    this.title = '',
  });

  final ApiClient api;
  final String batchId;

  /// What the list called the lot, shown while the trail is read.
  final String title;

  @override
  State<LotTrailDialog> createState() => _LotTrailDialogState();
}

/// The document types in plain words.
String lotTrailDocumentLabel(String type) => switch (type) {
      'GOODS_RECEIPT' => 'Goods received',
      'OPENING_STOCK' => 'Opening stock',
      'PURCHASE_INVOICE' => 'Purchase bill',
      'DELIVERY_NOTE' => 'Delivery note',
      'SALES_INVOICE' => 'Sales bill',
      'SALES_RETURN' => 'Sales return',
      'PURCHASE_RETURN' => 'Purchase return',
      'STOCK_TRANSFER' => 'Stock transfer',
      'ADJUSTMENT' => 'Stock adjustment',
      'REPACK' => 'Repack',
      'COST_CORRECTION' => 'Cost correction',
      'OTHER' || '' => 'Other',
      _ => type
          .toLowerCase()
          .split('_')
          .join(' ')
          .replaceFirstMapped(RegExp('^.'), (m) => m[0]!.toUpperCase()),
    };

String _trimmed(double value) =>
    value == value.roundToDouble() ? value.toStringAsFixed(0) : '$value';

String _day(String value) {
  if (value.isEmpty) return '-';
  final DateTime? day = DateTime.tryParse(value);
  return day == null ? value : documentDate(day);
}

String _dash(String value) => value.isEmpty ? '-' : value;

class _LotTrailDialogState extends State<LotTrailDialog> {
  LotTrail? _trail;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final LotTrail trail = await widget.api.lotTrail(widget.batchId);
      if (!mounted) return;
      setState(() => _trail = trail);
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() => _error = error.message);
    }
  }

  Widget _fact(ThemeData theme, String label, String value, String key) =>
      Padding(
        padding: const EdgeInsets.only(bottom: AppSpacing.xs),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SizedBox(
              width: 140,
              child: Text(
                label,
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
            ),
            Expanded(
              child: Text(
                value,
                key: ValueKey<String>('lot-trail-$key'),
                style: theme.textTheme.bodyMedium,
              ),
            ),
          ],
        ),
      );

  List<Widget> _facts(ThemeData theme, LotTrail trail) {
    final BatchRecord batch = trail.batch;
    final String item = [
      if (batch.productCode.isNotEmpty) batch.productCode,
      if (batch.productName.isNotEmpty) batch.productName,
    ].join(' - ');
    final String reference = trail.lotReference.isNotEmpty
        ? trail.lotReference
        : trail.hasPrintedBatch
            ? ''
            : batch.batchNumber;
    return [
      _fact(theme, 'Item', _dash(item), 'item'),
      _fact(theme, 'Our reference', _dash(reference), 'reference'),
      // Where the goods carry no printed batch the batch number is only our
      // own reference, and is never shown as a batch.
      _fact(
        theme,
        'Printed batch',
        trail.hasPrintedBatch ? _dash(batch.batchNumber) : '-',
        'printed-batch',
      ),
      _fact(theme, 'Received', _day(trail.receivedOn), 'received'),
      _fact(theme, 'Expiry', _day(batch.expiryDate), 'expiry'),
      _fact(theme, 'MRP', _dash(batch.mrp), 'mrp'),
      _fact(theme, 'Quantity held', _dash(batch.quantity), 'quantity'),
      if (trail.unitCost != null)
        _fact(theme, 'Unit cost', indianAmount(trail.unitCost!, full: true),
            'unit-cost'),
    ];
  }

  Widget _events(ThemeData theme, List<LotTrailEvent> events) {
    if (events.isEmpty) {
      return Text(
        'Nothing has moved this lot yet.',
        key: const ValueKey('lot-trail-empty'),
        style: theme.textTheme.bodySmall,
      );
    }
    final bool showCost = events.any((event) => event.costAmount != null);
    final TextStyle? head = theme.textTheme.labelMedium?.copyWith(
      fontWeight: FontWeight.w600,
    );
    final TextStyle? cell = theme.textTheme.bodySmall;
    Widget text(String value, {TextStyle? style, bool right = false}) =>
        Padding(
          padding: const EdgeInsets.symmetric(
            vertical: AppSpacing.xs,
            horizontal: AppSpacing.xs,
          ),
          child: Text(
            value,
            textAlign: right ? TextAlign.right : TextAlign.left,
            style: style ?? cell,
          ),
        );
    return Table(
      key: const ValueKey('lot-trail-events'),
      columnWidths: <int, TableColumnWidth>{
        0: const FlexColumnWidth(1.3),
        1: const FlexColumnWidth(1.2),
        2: const FlexColumnWidth(1),
        3: const FlexColumnWidth(1.5),
        4: const FlexColumnWidth(0.7),
        5: const FlexColumnWidth(0.7),
        if (showCost) 6: const FlexColumnWidth(0.9),
      },
      border: TableBorder(
        horizontalInside: BorderSide(color: theme.dividerColor),
      ),
      children: [
        TableRow(children: [
          text('Document', style: head),
          text('Number', style: head),
          text('Date', style: head),
          text('Party', style: head),
          text('In', style: head, right: true),
          text('Out', style: head, right: true),
          if (showCost) text('Cost', style: head, right: true),
        ]),
        for (int i = 0; i < events.length; i++)
          TableRow(
            key: ValueKey<String>('lot-trail-event-$i'),
            children: [
              text(lotTrailDocumentLabel(events[i].documentType)),
              text(_dash(events[i].documentNumber)),
              text(_day(events[i].documentDate)),
              text(_dash(events[i].partyName)),
              text(
                events[i].quantity > 0 ? _trimmed(events[i].quantity) : '',
                right: true,
              ),
              text(
                events[i].quantity < 0 ? _trimmed(-events[i].quantity) : '',
                right: true,
              ),
              if (showCost)
                text(
                  events[i].costAmount == null
                      ? ''
                      : indianAmount(events[i].costAmount!, full: true),
                  right: true,
                ),
            ],
          ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final LotTrail? trail = _trail;
    return AlertDialog(
      scrollable: true,
      icon: const Icon(Icons.timeline_outlined),
      title: Text(widget.title.isEmpty ? 'Lot trail' : 'Lot: ${widget.title}'),
      content: SizedBox(
        width: 720,
        child: _error != null
            ? Text(
                _error!,
                key: const ValueKey('lot-trail-error'),
                style: theme.textTheme.bodySmall
                    ?.copyWith(color: theme.colorScheme.error),
              )
            : trail == null
                ? const Padding(
                    padding: EdgeInsets.all(AppSpacing.xl),
                    child: Center(child: CircularProgressIndicator()),
                  )
                : Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      ..._facts(theme, trail),
                      const SizedBox(height: AppSpacing.lg),
                      Text('What it went through',
                          style: theme.textTheme.titleSmall),
                      const SizedBox(height: AppSpacing.sm),
                      _events(theme, trail.events),
                    ],
                  ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Close'),
        ),
      ],
    );
  }
}
