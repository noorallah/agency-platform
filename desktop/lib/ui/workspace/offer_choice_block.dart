import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/design/design_tokens.dart';
import '../../models/offer_candidate.dart';
import '../../phase2/document_page.dart';

/// The side panel's block of offers and discounts for the line the cursor
/// is on (L7 step 8, `docs/design/OFFERS_ON_THE_BILL_LINE_DESIGN.md`
/// section 4).
///
/// It shows what the last preview listed and holds **no rule about what
/// combines**: a tick builds the line's `offer_choice` from the keys that
/// show ticked and asks the editor to price the document again, on the
/// editor's own preview timer. The server answers what stands.
///
/// Keys: the editor moves focus here with F6; the arrows move, Space ticks,
/// Enter hands focus back to the line ([onReturn]).
class OfferChoiceBlock extends StatefulWidget {
  const OfferChoiceBlock({
    super.key,
    required this.candidates,
    required this.choice,
    required this.mayChoose,
    required this.onChanged,
    this.refused,
    this.savedOffers = const <dynamic>[],
    this.lockedNote,
    this.onPartShare,
    this.focusNode,
    this.onReturn,
    this.keyPrefix = 'offer-choice',
  });

  /// What the last preview listed for the line.
  final List<OfferCandidate> candidates;

  /// The line's own choice, changed in place by a tick.
  final LineOfferChoice choice;

  /// Whether the person holds SALES_OFFER_CHOOSE and the line can still
  /// change; without it the block is read-only.
  final bool mayChoose;

  /// Why the server did not take the choice sent on this line.
  final String? refused;

  /// The saved line's `offers` rows (L7 step 9): what was applied and what
  /// a person's choice passed over. Shown, read-only, while there are no
  /// [candidates] for the line -- a saved document opened, or one that is
  /// no longer priced afresh because it is approved.
  final List<dynamic> savedOffers;

  /// Why nothing can be ticked on this line although the person may choose
  /// (a discount typed on the line is the other answer).
  final String? lockedNote;

  /// A tick changed [choice]: redraw and price again.
  final VoidCallback onChanged;

  /// "Part share" on a row: the editor sets the quantity to what is charged.
  final void Function(OfferCandidate candidate)? onPartShare;

  final FocusNode? focusNode;
  final VoidCallback? onReturn;
  final String keyPrefix;

  @override
  State<OfferChoiceBlock> createState() => _OfferChoiceBlockState();
}

class _OfferChoiceBlockState extends State<OfferChoiceBlock> {
  int _highlight = 0;

  bool get _enabled => widget.mayChoose && widget.lockedNote == null;

  /// The rows a tick can reach: the available ones.
  List<int> get _tickable => <int>[
        for (int at = 0; at < widget.candidates.length; at += 1)
          if (widget.candidates[at].available) at,
      ];

  void _tick(OfferCandidate candidate) {
    if (!_enabled || !candidate.available) return;
    widget.choice.toggle(widget.candidates, candidate);
    widget.onChanged();
  }

  KeyEventResult _onKey(FocusNode node, KeyEvent event) {
    if (event is! KeyDownEvent && event is! KeyRepeatEvent) {
      return KeyEventResult.ignored;
    }
    final List<int> rows = _tickable;
    final LogicalKeyboardKey key = event.logicalKey;
    if (key == LogicalKeyboardKey.enter ||
        key == LogicalKeyboardKey.numpadEnter) {
      widget.onReturn?.call();
      return KeyEventResult.handled;
    }
    if (rows.isEmpty) return KeyEventResult.ignored;
    final int place = rows.indexOf(_highlight).clamp(0, rows.length - 1);
    if (key == LogicalKeyboardKey.arrowDown) {
      setState(() => _highlight = rows[(place + 1).clamp(0, rows.length - 1)]);
      return KeyEventResult.handled;
    }
    if (key == LogicalKeyboardKey.arrowUp) {
      setState(() => _highlight = rows[(place - 1).clamp(0, rows.length - 1)]);
      return KeyEventResult.handled;
    }
    if (key == LogicalKeyboardKey.space) {
      _tick(widget.candidates[rows[place]]);
      return KeyEventResult.handled;
    }
    return KeyEventResult.ignored;
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
    final bool focused = widget.focusNode?.hasFocus ?? false;
    final String refused = (widget.refused ?? '').isNotEmpty
        ? widget.refused!
        : widget.choice.refused;
    final TextStyle? small = theme.textTheme.bodySmall?.copyWith(
      fontSize: 11,
      color: scheme.onSurfaceVariant,
    );
    final List<Map<String, dynamic>> saved = savedOfferRows(
      widget.savedOffers,
    );
    return Focus(
      focusNode: widget.focusNode,
      onKeyEvent: _onKey,
      onFocusChange: (_) => setState(() {}),
      child: Column(
        key: ValueKey<String>('${widget.keyPrefix}-block'),
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(children: [
            const Expanded(child: DocumentSideHeading('Offers and discounts')),
            Padding(
              padding: const EdgeInsets.only(top: AppSpacing.md),
              child: Text('GIVES', style: small),
            ),
          ]),
          if (widget.candidates.isEmpty && saved.isEmpty)
            const DocumentSideNote('No offer or arrangement for this line.'),
          if (widget.candidates.isEmpty)
            ...savedOfferTexts(context, saved, keyPrefix: widget.keyPrefix),
          for (int at = 0; at < widget.candidates.length; at += 1)
            _row(context, at, highlighted: focused && at == _highlight),
          if (widget.choice.partShareNote.isNotEmpty)
            DocumentSideNote(
              widget.choice.partShareNote,
              key: ValueKey<String>('${widget.keyPrefix}-part-share-note'),
            ),
          if (refused.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: AppSpacing.xs),
              child: Text(
                refused,
                key: ValueKey<String>('${widget.keyPrefix}-refused'),
                style: theme.textTheme.bodySmall?.copyWith(
                  fontSize: 11,
                  color: scheme.error,
                ),
              ),
            ),
          if (widget.candidates.isNotEmpty && !widget.mayChoose)
            const DocumentSideNote('Read only: choosing needs the right to '
                'choose offers.'),
          if (widget.candidates.isNotEmpty && widget.lockedNote != null)
            DocumentSideNote(widget.lockedNote!),
        ],
      ),
    );
  }

  Widget _row(BuildContext context, int at, {required bool highlighted}) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
    final OfferCandidate candidate = widget.candidates[at];
    final bool ticked = widget.choice.isTicked(candidate);
    final TextStyle? body =
        theme.textTheme.bodyMedium?.copyWith(fontSize: 13);
    final TextStyle? small = theme.textTheme.bodySmall?.copyWith(
      fontSize: 11,
      color: scheme.onSurfaceVariant,
    );
    final String status = !candidate.available && candidate.hint.isNotEmpty
        ? candidate.hint
        : ticked
            ? 'applied'
            : candidate.reason ?? '';
    final String gives = candidate.gives.discounts
        ? documentMoney(candidate.worth)
        : candidate.gives.freeQuantity != null
            ? '${plainOfferQuantity(candidate.gives.freeQuantity!)} free'
            : '';
    final String rowKey = '${widget.keyPrefix}-${candidate.key}';
    return Container(
      key: ValueKey<String>(rowKey),
      padding: const EdgeInsets.symmetric(vertical: 2),
      decoration: BoxDecoration(
        color: highlighted ? scheme.primary.withValues(alpha: .10) : null,
        borderRadius: AppRadius.small,
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 28,
            height: 24,
            child: candidate.available
                ? Checkbox(
                    key: ValueKey<String>('$rowKey-tick'),
                    value: ticked,
                    visualDensity: VisualDensity.compact,
                    materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                    onChanged:
                        _enabled ? (_) => _tick(candidate) : null,
                  )
                : null,
          ),
          const SizedBox(width: AppSpacing.xs),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(candidate.label, style: body),
                if (status.isNotEmpty) Text(status, style: small),
                if (candidate.fundedBy != null)
                  Text('funded by ${candidate.fundedBy}', style: small),
                if (candidate.partShare != null &&
                    widget.onPartShare != null &&
                    _enabled)
                  TextButton(
                    key: ValueKey<String>('$rowKey-part-share'),
                    style: TextButton.styleFrom(
                      padding: EdgeInsets.zero,
                      minimumSize: const Size(0, 24),
                      tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                      visualDensity: VisualDensity.compact,
                    ),
                    onPressed: () {
                      widget.choice
                          .takePartShare(widget.candidates, candidate);
                      widget.onPartShare!(candidate);
                    },
                    child: Text(
                      'Part share: '
                      '${plainOfferQuantity(candidate.partShare!.chargedQuantity)}'
                      ' + ${plainOfferQuantity(candidate.partShare!.freeQuantity)}'
                      ' free',
                    ),
                  ),
              ],
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          Text(gives, style: body),
        ],
      ),
    );
  }
}

/// A saved line's `offers` rows that carry something to say, in the order
/// the server weighed them (`sequence`).
List<Map<String, dynamic>> savedOfferRows(Object? offers) {
  final List<Map<String, dynamic>> rows = <Map<String, dynamic>>[
    for (final dynamic row in offers is List ? offers : const <dynamic>[])
      if (row is Map)
        if ('${row['state']}' == 'APPLIED' || '${row['state']}' == 'REFUSED')
          Map<String, dynamic>.from(row),
  ];
  int sequence(Map<String, dynamic> row) =>
      int.tryParse('${row['sequence']}') ?? 0;
  rows.sort((Map<String, dynamic> a, Map<String, dynamic> b) =>
      sequence(a).compareTo(sequence(b)));
  return rows;
}

/// A saved line's offers, read-only, for a line no pricing lists afresh: a
/// bill line continuing a note (L7 step 9). Nothing where the line has none.
class SavedOffersBlock extends StatelessWidget {
  const SavedOffersBlock({
    super.key,
    required this.offers,
    this.keyPrefix = 'offer-choice',
  });

  /// The line's `offers` as the server answered them.
  final Object? offers;
  final String keyPrefix;

  @override
  Widget build(BuildContext context) {
    final List<Map<String, dynamic>> saved = savedOfferRows(offers);
    if (saved.isEmpty) return const SizedBox.shrink();
    return Column(
      key: ValueKey<String>('$keyPrefix-saved-block'),
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const DocumentSideHeading('Offers and discounts'),
        ...savedOfferTexts(context, saved, keyPrefix: keyPrefix),
      ],
    );
  }
}

/// One line of text per saved row, keyed `<prefix>-saved-<n>`.
List<Widget> savedOfferTexts(
  BuildContext context,
  List<Map<String, dynamic>> saved, {
  required String keyPrefix,
}) {
  final TextStyle? body =
      Theme.of(context).textTheme.bodyMedium?.copyWith(fontSize: 13);
  return <Widget>[
    for (int at = 0; at < saved.length; at += 1)
      Text(
        savedOfferWords(saved[at]),
        key: ValueKey<String>('$keyPrefix-saved-$at'),
        style: body,
      ),
  ];
}

/// How a saved document's view words one of a line's `offers` rows (L7
/// step 9, design section 4: "what was applied and 'chosen by'").
///
/// An applied row says what it gave and who decided it -- "TEA-5 · 55.00
/// off · applied", "TEA-11 · 1 free · part share · chosen by a person"; a
/// refused row is an offer the start would have applied that a person's
/// choice passed over -- "TEA-11 · passed over". A price list reads
/// "Price list CITY", the customer's own rate "Standing rate" and the
/// group's "Group rate".
String savedOfferWords(Map<String, dynamic> row) {
  final String source = '${row['source'] ?? ''}';
  final String code = '${row['code'] ?? ''}'.trim();
  final String name = switch (source) {
    'price_list' => code.isEmpty ? 'Price list' : 'Price list $code',
    'customer' => 'Standing rate',
    'customer_group' => 'Group rate',
    _ => code.isNotEmpty ? code : '${row['name'] ?? 'Offer'}',
  };
  if ('${row['state']}' == 'REFUSED') return '$name · passed over';
  final double off = double.tryParse('${row['discount_amount']}') ?? 0;
  final double free = double.tryParse('${row['free_quantity']}') ?? 0;
  final List<String> parts = <String>[
    name,
    if (off > 0) '${documentMoney('${row['discount_amount']}')} off',
    if (free > 0) '${plainOfferQuantity('${row['free_quantity']}')} free',
    if (row['part_share'] == true) 'part share',
    row['chosen'] == true ? 'chosen by a person' : 'applied',
  ];
  return parts.join(' · ');
}

/// The bill's own offers, read-only under the totals: what applies to the
/// whole document rather than to one line.
class BillOffersNote extends StatelessWidget {
  const BillOffersNote({super.key, required this.candidates});

  final List<OfferCandidate> candidates;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    if (candidates.isEmpty) return const SizedBox.shrink();
    final TextStyle? small = theme.textTheme.bodySmall?.copyWith(
      fontSize: 11,
      color: theme.colorScheme.onSurfaceVariant,
    );
    return Padding(
      key: const ValueKey('bill-offers'),
      padding: const EdgeInsets.fromLTRB(
          AppSpacing.md, AppSpacing.xs, AppSpacing.md, AppSpacing.xs),
      child: Wrap(
        spacing: AppSpacing.md,
        runSpacing: 2,
        children: [
          Text('Offers on the bill:', style: small),
          for (final OfferCandidate item in candidates)
            Text(
              '${item.label} · '
              '${item.applied ? 'applied' : item.reason ?? (item.hint.isEmpty ? 'not applied' : item.hint)}',
              style: small,
            ),
        ],
      ),
    );
  }
}

/// The hint shown under a line's quantity: "2 more: 1 free", from the first
/// candidate that has one; empty where none does.
String offerQuantityHint(List<OfferCandidate> candidates) {
  for (final OfferCandidate item in candidates) {
    if (item.shortHint.isNotEmpty) return item.shortHint;
  }
  return '';
}

/// A line's quantity cell with [hint] in small type under it ("2 more: 1
/// free"); the cell alone where there is no hint, so the table is unchanged.
Widget documentQuantityWithHint(
  BuildContext context,
  Widget cell, {
  required String hint,
  Key? key,
}) {
  if (hint.isEmpty) return cell;
  final ThemeData theme = Theme.of(context);
  return Column(
    mainAxisSize: MainAxisSize.min,
    mainAxisAlignment: MainAxisAlignment.center,
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      cell,
      Text(
        hint,
        key: key,
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        textAlign: TextAlign.right,
        style: theme.textTheme.bodySmall?.copyWith(
          fontSize: 10,
          height: 1.1,
          color: theme.colorScheme.primary,
        ),
      ),
    ],
  );
}
