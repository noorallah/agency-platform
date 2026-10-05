import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../models/batch_serial.dart';
import '../../phase2/document_page.dart';
import 'desktop_framework.dart';

String _trimmed(double value) =>
    value == value.roundToDouble() ? value.toStringAsFixed(0) : '$value';

/// The batch picker of a line that ships goods (backlog 79): every batch of
/// the product in the warehouse with what it can give, earliest expiry first
/// as the default, and the person's own split reported through [onChanged].
///
/// Used by the delivery note and by the counter bill, which raises its own
/// note. The split itself is the caller's -- [picks] null means nobody has
/// chosen (send nothing), an empty map means "back to earliest expiry" (send
/// `[]`), anything else is the person's own split. Quantities are in stock
/// units. Availability is asked of the server a moment after what it depends
/// on settles, so typing a quantity is not a request per key.
class BatchPickerPanel extends StatefulWidget {
  const BatchPickerPanel({
    super.key,
    required this.api,
    required this.lineId,
    required this.productId,
    required this.warehouseId,
    required this.asOf,
    required this.quantity,
    required this.picks,
    required this.onChanged,
    required this.enabled,
    this.salesOrderLineId,
    this.customerId,
    this.comparable = true,
    this.showPtrPts = false,
    this.onBatchPrice,
    this.keyPrefix = 'delivery-note',
    this.unreadableNote = 'could not read the batches; they will go earliest '
        'expiry first when the note is dispatched',
    this.noWarehouseNote = 'choose the warehouse to see its batches',
    this.mismatchNote = 'The batches do not add up to what this line '
        'delivers; dispatch will be refused.',
  });

  final ApiClient api;

  /// Names the line in the boxes' keys.
  final String lineId;
  final String productId;
  final String warehouseId;

  /// The document's date, `yyyy-mm-dd`; anything else is not sent.
  final String asOf;

  /// What the line ships, in stock units.
  final double quantity;
  final String? salesOrderLineId;

  /// The customer the goods go to, so a batch too short for their minimum
  /// shelf life is flagged. Null when the caller does not know one.
  final String? customerId;
  final Map<String, double>? picks;
  final ValueChanged<Map<String, double>> onChanged;
  final bool enabled;

  /// False when the line is in another unit than stock, so the editor cannot
  /// say whether the split adds up.
  final bool comparable;

  /// Show each batch's PTR and PTS beside its MRP (BATCH_PTR_PTS). Display
  /// only: the line's price is never filled from them here, the server does
  /// that when the price is left blank.
  final bool showPtrPts;

  /// Told the selling price of the one batch the line ships from, once the
  /// batches are read and whenever the split changes: null when it ships
  /// from several, or its batch carries no price (backlog 79 row 7).
  final ValueChanged<double?>? onBatchPrice;
  final String keyPrefix;
  final String unreadableNote;
  final String noWarehouseNote;
  final String mismatchNote;

  @override
  State<BatchPickerPanel> createState() => _BatchPickerPanelState();
}

class _BatchPickerPanelState extends State<BatchPickerPanel> {
  List<BatchAvailabilityRecord>? _rows;
  bool _failed = false;
  String? _asked;
  Timer? _timer;

  /// Bumped when the boxes are reset, so they are rebuilt.
  int _epoch = 0;

  @override
  void initState() {
    super.initState();
    _watch();
  }

  @override
  void didUpdateWidget(BatchPickerPanel oldWidget) {
    super.didUpdateWidget(oldWidget);
    _watch();
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  String get _key => [
        widget.productId,
        widget.warehouseId,
        widget.asOf,
        _trimmed(widget.quantity),
        widget.customerId ?? '',
      ].join('|');

  void _watch() {
    if (widget.warehouseId.isEmpty) return;
    final String key = _key;
    if (_asked == key) return;
    _asked = key;
    _timer?.cancel();
    _timer = Timer(
      const Duration(milliseconds: 350),
      () => unawaited(_load(key)),
    );
  }

  Future<void> _load(String key) async {
    try {
      final List<BatchAvailabilityRecord> rows =
          await widget.api.batchAvailability(
        productId: widget.productId,
        warehouseId: widget.warehouseId,
        asOf: DateTime.tryParse(widget.asOf) == null ? null : widget.asOf,
        quantity: widget.quantity > 0 ? widget.quantity : null,
        salesOrderLineId: widget.salesOrderLineId,
        customerId: widget.customerId,
      );
      if (!mounted || _asked != key) return;
      setState(() {
        _rows = rows;
        _failed = false;
      });
      _reportPrice(rows, widget.picks);
    } on Object {
      // The picker is a courtesy: without it the server still goes earliest
      // expiry first at dispatch.
      if (!mounted || _asked != key) return;
      setState(() => _failed = true);
    }
  }

  String _dayOf(String value) {
    final DateTime? day = DateTime.tryParse(value);
    return day == null ? value : documentDate(day);
  }

  double _number(String value) => double.tryParse(value.trim()) ?? 0;

  /// What a batch's box shows: the person's own figure once they have made a
  /// choice, otherwise the earliest-expiry-first share the server suggests.
  double _shown(BatchAvailabilityRecord batch) {
    if (batch.expired) return 0;
    final Map<String, double>? picks = widget.picks;
    if (picks != null && picks.isNotEmpty) return picks[batch.batchId] ?? 0;
    return batch.fefo;
  }

  /// The selling price of the single batch the split takes from, if any.
  void _reportPrice(
    List<BatchAvailabilityRecord> batches,
    Map<String, double>? picks,
  ) {
    final ValueChanged<double?>? report = widget.onBatchPrice;
    if (report == null) return;
    final List<BatchAvailabilityRecord> taking = [
      for (final BatchAvailabilityRecord batch in batches)
        if (!batch.expired &&
            ((picks != null && picks.isNotEmpty)
                    ? picks[batch.batchId] ?? 0
                    : batch.fefo) >
                0)
          batch,
    ];
    report(taking.length == 1 ? taking.single.sellingPrice : null);
  }

  void _pick(
    List<BatchAvailabilityRecord> batches,
    BatchAvailabilityRecord edited,
    String text,
  ) {
    // The first edit makes the whole split the person's own, starting from
    // what the boxes were showing.
    final Map<String, double> next = {
      for (final BatchAvailabilityRecord batch in batches)
        if (!batch.expired) batch.batchId: _shown(batch),
    };
    next[edited.batchId] = _number(text);
    widget.onChanged(next);
    _reportPrice(batches, next);
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
    final TextStyle? small = theme.textTheme.bodySmall?.copyWith(fontSize: 11);
    final TextStyle? quiet = small?.copyWith(color: scheme.onSurfaceVariant);
    final String id = widget.lineId;
    final List<BatchAvailabilityRecord>? batches = _rows;
    final Map<String, double>? picks = widget.picks;
    final bool explicit = picks != null && picks.isNotEmpty;
    final double shipping = widget.quantity;
    if (batches == null) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const DocumentSideHeading('Batches'),
          DocumentSideNote(_failed
              ? widget.unreadableNote
              : widget.warehouseId.isEmpty
                  ? widget.noWarehouseNote
                  : 'reading the batches...'),
        ],
      );
    }
    if (batches.isEmpty) {
      return const Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          DocumentSideHeading('Batches'),
          DocumentSideNote('no stock of this product in that warehouse'),
        ],
      );
    }
    double chosen = 0;
    for (final BatchAvailabilityRecord batch in batches) {
      chosen += _shown(batch);
    }
    final bool mismatch = widget.comparable &&
        shipping > 0 &&
        (chosen - shipping).abs() > 0.0005;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const DocumentSideHeading('Batches'),
        Column(
          key: ValueKey<String>('${widget.keyPrefix}-batch-picker'),
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            for (final BatchAvailabilityRecord batch in batches)
              Padding(
                padding: const EdgeInsets.only(bottom: 4),
                child: Opacity(
                  opacity: batch.expired ? 0.5 : 1,
                  child: Row(children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            batch.batchNumber.isEmpty
                                ? 'untracked stock'
                                : batch.batchNumber,
                            overflow: TextOverflow.ellipsis,
                            style:
                                small?.copyWith(fontWeight: FontWeight.w600),
                          ),
                          Text(
                            [
                              if (batch.expiryDate.isNotEmpty)
                                'exp ${_dayOf(batch.expiryDate)}'
                              else
                                'no expiry',
                              if (batch.daysToExpiry != null && !batch.expired)
                                '${batch.daysToExpiry}d left',
                              'can take ${_trimmed(batch.availableToLine)}',
                              if (batch.mrp != null)
                                'MRP ${batch.mrp!.toStringAsFixed(2)}',
                              if (widget.showPtrPts && batch.ptr != null)
                                'PTR ${batch.ptr!.toStringAsFixed(2)}',
                              if (widget.showPtrPts && batch.pts != null)
                                'PTS ${batch.pts!.toStringAsFixed(2)}',
                              if (batch.sellingPrice != null)
                                'price ${batch.sellingPrice!.toStringAsFixed(2)}',
                            ].join(' · '),
                            overflow: TextOverflow.ellipsis,
                            style: quiet,
                          ),
                          if (batch.shortForCustomer && !batch.expired)
                            const Padding(
                              padding: EdgeInsets.only(top: 2),
                              child: StatusBadge(
                                label: 'Too short for customer',
                                tone: StatusBadgeTone.warning,
                              ),
                            ),
                          if (batch.expired || batch.nearExpiry)
                            Padding(
                              padding: const EdgeInsets.only(top: 2),
                              child: StatusBadge(
                                label:
                                    batch.expired ? 'Expired' : 'Near expiry',
                                tone: batch.expired
                                    ? StatusBadgeTone.danger
                                    : StatusBadgeTone.warning,
                              ),
                            ),
                        ],
                      ),
                    ),
                    const SizedBox(width: 6),
                    SizedBox(
                      width: 64,
                      child: KeyedSubtree(
                        key: ValueKey<String>(
                          'batch-pick-box-$id-${batch.batchId}-$_epoch-'
                          '${_trimmed(batch.fefo)}',
                        ),
                        child: TextFormField(
                          key: ValueKey<String>(
                              'batch-pick-$id-${batch.batchId}'),
                          initialValue: _trimmed(_shown(batch)),
                          enabled: !batch.expired,
                          readOnly: !widget.enabled,
                          textAlign: TextAlign.right,
                          keyboardType: TextInputType.number,
                          style: theme.textTheme.bodyMedium?.copyWith(
                            fontSize: 13,
                            color: _shown(batch) > batch.availableToLine
                                ? scheme.error
                                : null,
                          ),
                          decoration: documentCellDecoration(context),
                          onChanged: (value) => _pick(batches, batch, value),
                        ),
                      ),
                    ),
                  ]),
                ),
              ),
            DocumentSidePair(
              'Chosen ${_trimmed(chosen)} of ${_trimmed(shipping)}',
              explicit ? 'your choice' : 'earliest expiry',
              bold: true,
              tone: mismatch ? scheme.error : null,
            ),
            if (mismatch)
              Text(
                widget.mismatchNote,
                style: small?.copyWith(color: scheme.error),
              ),
            if (picks != null)
              Align(
                alignment: Alignment.centerLeft,
                child: TextButton(
                  key: ValueKey<String>('${widget.keyPrefix}-batch-reset'),
                  onPressed: !widget.enabled
                      ? null
                      : () {
                          setState(() => _epoch++);
                          widget.onChanged(<String, double>{});
                          _reportPrice(batches, null);
                        },
                  child: const Text('Use earliest expiry'),
                ),
              ),
          ],
        ),
      ],
    );
  }
}
