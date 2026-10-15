import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/preferences/desktop_preferences_service.dart';
import '../../phase2/document_page.dart';

/// Boxes and loose pieces on one line (L5, `BOX_AND_PIECE_LINE_DESIGN` 3.4
/// and 4): the one implementation of the sum every editor draws its cells
/// with.
///
/// The quantity stays one figure in pieces -- what the line sends in its
/// `quantity` and `free_quantity` -- and the two cells are only a way of
/// typing it: full boxes of [packSize] and the pieces left over. Nothing is
/// rounded, and nothing here is stored.

/// A pack size as a number, or null where the item has no pack. A pack of
/// one is no pack: the server refuses it as a line's pack size.
double? packOf(String packSize) {
  final double? value = double.tryParse(packSize.trim());
  return value == null || value <= 1 ? null : value;
}

/// A figure without trailing zeros: 12, 1.5.
String boxPieceFigure(double value) {
  if (value == value.roundToDouble()) return value.round().toString();
  return documentQuantity(value.toStringAsFixed(4));
}

/// [total] pieces as full boxes of [pack] and the pieces left over.
({int boxes, double pieces}) splitPieces(double total, double pack) {
  // A hair under a whole box is still that box: 0.1 * 3 is not 0.3.
  final int boxes = ((total + 1e-9) / pack).floor();
  final double pieces =
      double.parse((total - boxes * pack).toStringAsFixed(4)).abs();
  return (boxes: boxes, pieces: pieces);
}

/// [boxes] boxes of [pack] and [pieces] loose, in pieces.
double addBoxesAndPieces(double boxes, double pieces, double? pack) =>
    double.parse((boxes * (pack ?? 0) + pieces).toStringAsFixed(4));

/// "1 box", "3 boxes".
String boxWords(int boxes) => boxes == 1 ? '1 box' : '$boxes boxes';

/// A quantity in pieces read as boxes: "3 x 12 + 5", "2 x 12", or the plain
/// figure where the item has no pack or the quantity is under a box.
String boxesAndPieces(String total, String packSize) {
  final double? value = double.tryParse(total.trim());
  final double? pack = packOf(packSize);
  if (value == null) return total.trim();
  if (pack == null) return boxPieceFigure(value);
  final ({int boxes, double pieces}) split = splitPieces(value, pack);
  if (split.boxes == 0) return boxPieceFigure(split.pieces);
  final String head = '${split.boxes} x ${boxPieceFigure(pack)}';
  return split.pieces == 0 ? head : '$head + ${boxPieceFigure(split.pieces)}';
}

/// "3 boxes + 5 pcs", "2 pcs", "1 box".
String boxPieceWords(double total, double pack) {
  final ({int boxes, double pieces}) split = splitPieces(total, pack);
  if (split.boxes == 0) return '${boxPieceFigure(split.pieces)} pcs';
  if (split.pieces == 0) return boxWords(split.boxes);
  return '${boxWords(split.boxes)} + ${boxPieceFigure(split.pieces)} pcs';
}

/// The side panel's line for the line being typed: "Box of 12. 3 boxes +
/// 5 pcs = 41 pcs. Free 2 pcs. Rate of a box 120.00." Empty where the item
/// has no pack.
String boxPieceSummary({
  required String packSize,
  required String quantity,
  required String free,
  required String rate,
}) {
  final double? pack = packOf(packSize);
  if (pack == null) return '';
  final double total = double.tryParse(quantity.trim()) ?? 0;
  final double freeTotal = double.tryParse(free.trim()) ?? 0;
  final double? price = double.tryParse(rate.trim());
  return [
    'Box of ${boxPieceFigure(pack)}.',
    '${boxPieceWords(total, pack)} = ${boxPieceFigure(total)} pcs.',
    if (freeTotal > 0) 'Free ${boxPieceWords(freeTotal, pack)}.',
    if (price != null) 'Rate of a box ${(price * pack).toStringAsFixed(2)}.',
  ].join(' ');
}

/// The four columns that take the place of Qty and Free.
const List<DocumentColumn> boxPieceColumns = [
  DocumentColumn('Box', 46, numeric: true),
  DocumentColumn('Pcs', 56, numeric: true),
  DocumentColumn('Free box', 58, numeric: true),
  DocumentColumn('Free pcs', 58, numeric: true),
];

/// What one line's four cells hold. The line's own quantity and free boxes
/// stay the figures sent; [quantityText] and [freeText] are what the cells
/// add up to, for the editor to write back after each change.
class BoxPieceEntry {
  final TextEditingController box = TextEditingController();
  final TextEditingController pcs = TextEditingController();
  final TextEditingController freeBox = TextEditingController();
  final TextEditingController freePcs = TextEditingController();

  /// Said once after a cell is left with a box's worth of pieces in it,
  /// e.g. "17 pcs is 1 box + 5". Cleared by the next figure typed.
  String note = '';

  /// Fill the cells from the line's figures in pieces. A blank figure leaves
  /// both cells blank: for the free goods, that is "take the offer".
  void load({
    required String quantity,
    required String free,
    required double? pack,
  }) {
    _fill(box, pcs, quantity, pack);
    _fill(freeBox, freePcs, free, pack);
    note = '';
  }

  static void _fill(
    TextEditingController boxes,
    TextEditingController pieces,
    String total,
    double? pack,
  ) {
    final double? value = double.tryParse(total.trim());
    if (value == null) {
      boxes.text = '';
      pieces.text = total.trim();
      return;
    }
    if (pack == null) {
      boxes.text = '';
      pieces.text = boxPieceFigure(value);
      return;
    }
    final ({int boxes, double pieces}) split = splitPieces(value, pack);
    boxes.text = split.boxes == 0 ? '' : '${split.boxes}';
    pieces.text =
        split.boxes > 0 && split.pieces == 0 ? '' : boxPieceFigure(split.pieces);
  }

  /// What the charged cells add up to, in pieces.
  String quantityText(double? pack) => _total(box, pcs, pack);

  /// What the free cells add up to: blank when both are blank (the offer
  /// stands), '0' when a zero was typed (the offer is refused).
  String freeText(double? pack) => _total(freeBox, freePcs, pack);

  static String _total(
    TextEditingController boxes,
    TextEditingController pieces,
    double? pack,
  ) {
    final String typedBoxes = pack == null ? '' : boxes.text.trim();
    final String typedPieces = pieces.text.trim();
    if (typedBoxes.isEmpty && typedPieces.isEmpty) return '';
    final double? b = typedBoxes.isEmpty ? 0 : double.tryParse(typedBoxes);
    final double? p = typedPieces.isEmpty ? 0 : double.tryParse(typedPieces);
    // Not a figure: passed on as typed, so the line's own check names it.
    if (b == null) return typedBoxes;
    if (p == null) return typedPieces;
    return boxPieceFigure(addBoxesAndPieces(b, p, pack));
  }

  /// Move pieces past a full box into the box cell, for both pairs. True
  /// when a cell changed; [note] then says how, once.
  bool normalise(double? pack) {
    if (pack == null) return false;
    final String charged = _normalisePair(box, pcs, pack);
    final String free = _normalisePair(freeBox, freePcs, pack);
    final String said = charged.isNotEmpty ? charged : free;
    if (said.isEmpty) return false;
    note = said;
    return true;
  }

  static String _normalisePair(
    TextEditingController boxes,
    TextEditingController pieces,
    double pack,
  ) {
    final double? b =
        boxes.text.trim().isEmpty ? 0 : double.tryParse(boxes.text.trim());
    final double? p =
        pieces.text.trim().isEmpty ? 0 : double.tryParse(pieces.text.trim());
    if (b == null || p == null || b < 0 || p < 0) return '';
    final bool partBox = b != b.roundToDouble();
    if (p < pack && !partBox) return '';
    final ({int boxes, double pieces}) moved = splitPieces(p, pack);
    final ({int boxes, double pieces}) whole =
        splitPieces(addBoxesAndPieces(b, p, pack), pack);
    boxes.text = '${whole.boxes}';
    pieces.text = boxPieceFigure(whole.pieces);
    return partBox
        ? '${boxPieceFigure(b)} boxes is ${boxPieceWords(b * pack, pack)}'
        : '${boxPieceFigure(p)} pcs is ${boxWords(moved.boxes)} + '
            '${boxPieceFigure(moved.pieces)}';
  }

  void dispose() {
    box.dispose();
    pcs.dispose();
    freeBox.dispose();
    freePcs.dispose();
  }
}

/// The four cells for one line, in the order of [boxPieceColumns]: Box,
/// Pcs, Free box, Free pcs. For an item with no pack the two box cells are
/// closed and the cursor passes over them. [onChanged] runs after a figure
/// is typed and after a cell is left and its pieces moved into boxes; the
/// editor writes [BoxPieceEntry.quantityText] and [BoxPieceEntry.freeText]
/// back onto the line there. [freeHint] is what the blank free cells take.
List<Widget> boxPieceCells(
  BuildContext context, {
  required BoxPieceEntry entry,
  required double? pack,
  required bool readOnly,
  required String keyPrefix,
  required VoidCallback onChanged,
  String? freeHint,
  bool chargedRequired = true,
}) {
  String? chargedCheck(String? _) {
    final String? figure = _figureCheck(entry.box.text, entry.pcs.text);
    if (figure != null) return figure;
    final double total = double.tryParse(entry.quantityText(pack)) ?? 0;
    return chargedRequired && total <= 0 ? 'Enter the quantity.' : null;
  }

  String? freeCheck(String? _) =>
      _figureCheck(entry.freeBox.text, entry.freePcs.text);

  Widget cell(
    String name,
    TextEditingController controller,
    String? Function(String?) validator, {
    String? hint,
  }) =>
      _BoxPieceCell(
        key: ValueKey<String>('$keyPrefix-$name'),
        controller: controller,
        readOnly: readOnly,
        hint: hint,
        validator: validator,
        onTyped: () {
          entry.note = '';
          onChanged();
        },
        onLeft: () {
          if (entry.normalise(pack)) onChanged();
        },
      );

  return [
    if (pack == null)
      _ClosedCell(key: ValueKey<String>('$keyPrefix-box-closed'))
    else
      cell('box', entry.box, chargedCheck),
    cell('pcs', entry.pcs, chargedCheck),
    if (pack == null)
      _ClosedCell(key: ValueKey<String>('$keyPrefix-free-box-closed'))
    else
      cell('free-box', entry.freeBox, freeCheck),
    // What a blank pair takes from the offer, in pieces.
    cell('free-pcs', entry.freePcs, freeCheck, hint: freeHint),
  ];
}

/// Blank, or a figure not below zero, in each of the two cells.
String? _figureCheck(String boxes, String pieces) {
  for (final String text in [boxes, pieces]) {
    if (text.trim().isEmpty) continue;
    final double? value = double.tryParse(text.trim());
    if (value == null || value < 0) return 'Enter a figure, or leave it blank.';
  }
  return null;
}

/// The toggle above the lines, *Boxes and pieces / Pieces only*, drawn in
/// the lines' heading row beside [label] (the product column's heading) so
/// it takes no row of its own on a narrow window. It changes how the lines
/// are typed and shown, never a quantity.
class BoxPieceToggle extends StatelessWidget {
  const BoxPieceToggle({
    super.key,
    required this.label,
    required this.value,
    required this.onChanged,
  });

  final String label;
  final bool value;

  /// Null when the document can no longer be changed.
  final ValueChanged<bool>? onChanged;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
    final TextStyle? style = theme.textTheme.labelMedium?.copyWith(
      fontSize: 12,
      fontWeight: FontWeight.w600,
      color: scheme.onSurfaceVariant,
    );
    Widget side(String words, bool means, String key) {
      final bool chosen = value == means;
      return InkWell(
        key: ValueKey<String>(key),
        onTap: onChanged == null || chosen ? null : () => onChanged!(means),
        borderRadius: BorderRadius.circular(4),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
          decoration: BoxDecoration(
            color: chosen ? scheme.secondaryContainer : null,
            borderRadius: BorderRadius.circular(4),
          ),
          child: Text(
            words,
            maxLines: 1,
            style: style?.copyWith(
              color: chosen ? scheme.onSecondaryContainer : null,
            ),
          ),
        ),
      );
    }

    // The heading gives way first; the toggle shrinks only on a column too
    // narrow for it.
    return LayoutBuilder(
      builder: (context, constraints) => Row(
        children: [
          Expanded(
            child: Text(label,
                maxLines: 1, overflow: TextOverflow.ellipsis, style: style),
          ),
          const SizedBox(width: 8),
          ConstrainedBox(
            constraints: BoxConstraints(
              maxWidth: constraints.hasBoundedWidth
                  ? constraints.maxWidth * .85
                  : double.infinity,
            ),
            child: FittedBox(
              fit: BoxFit.scaleDown,
              child: Row(
                children: [
                  side('Boxes and pieces', true, 'box-piece-toggle-on'),
                  Text(' / ', style: style),
                  side('Pieces only', false, 'box-piece-toggle-off'),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _BoxPieceCell extends StatefulWidget {
  const _BoxPieceCell({
    super.key,
    required this.controller,
    required this.readOnly,
    required this.validator,
    required this.onTyped,
    required this.onLeft,
    this.hint,
  });

  final TextEditingController controller;
  final bool readOnly;
  final String? Function(String?) validator;
  final VoidCallback onTyped;
  final VoidCallback onLeft;
  final String? hint;

  @override
  State<_BoxPieceCell> createState() => _BoxPieceCellState();
}

class _BoxPieceCellState extends State<_BoxPieceCell> {
  final FocusNode _focus = FocusNode();

  @override
  void initState() {
    super.initState();
    _focus.addListener(_focusMoved);
  }

  void _focusMoved() {
    if (!_focus.hasFocus && !widget.readOnly) widget.onLeft();
  }

  @override
  void dispose() {
    _focus
      ..removeListener(_focusMoved)
      ..dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => TextFormField(
        controller: widget.controller,
        focusNode: _focus,
        readOnly: widget.readOnly,
        textAlign: TextAlign.right,
        keyboardType: TextInputType.number,
        // Enter moves on, as Tab does.
        textInputAction: TextInputAction.next,
        style: Theme.of(context).textTheme.bodyMedium?.copyWith(fontSize: 13),
        decoration: documentCellDecoration(context, hint: widget.hint),
        autovalidateMode: AutovalidateMode.onUserInteraction,
        validator: widget.validator,
        onChanged: (_) => widget.onTyped(),
      );
}

// -- Show boxes (L5 step 11, `BOX_AND_PIECE_LINE_DESIGN` 4, "Stock, shown
// as boxes and pieces") ------------------------------------------------------
//
// A way of showing stock and nothing more: every figure stays the one the
// screen read, in pieces, and the split is worked out here from the item's
// pack size today, which the server puts on each stock row only where the
// firm has a box switch on. No call is added and nothing is stored but the
// person's choice, on this PC.

/// Whether a screen offers *Show boxes*: where at least one row it read
/// carries a pack, which is how it knows one of the firm's switches is on.
bool offersShowBoxes(Iterable<String> packSizes) =>
    packSizes.any((size) => packOf(size) != null);

/// A stock quantity in pieces read as boxes with the pieces kept beside it:
/// "7 x 12 + 5 (89)", "-1 x 12 + 2 (-14)". [beside] is the figure as the
/// screen shows it without boxes; it defaults to the plain figure. A
/// quantity under one box, or of an item with no pack, reads as [beside]
/// (or the quantity as given) does today.
String stockInBoxes(String quantity, String packSize, {String? beside}) {
  final double? value = double.tryParse(quantity.trim());
  final double? pack = packOf(packSize);
  final String plain = beside ?? quantity;
  if (value == null || pack == null) return plain;
  final ({int boxes, double pieces}) split = splitPieces(value.abs(), pack);
  if (split.boxes == 0) return plain;
  final String head = '${value < 0 ? '-' : ''}${split.boxes} x '
      '${boxPieceFigure(pack)}';
  final String boxes = split.pieces == 0
      ? head
      : '$head + ${boxPieceFigure(split.pieces)}';
  return '$boxes (${beside ?? boxPieceFigure(value)})';
}

/// A stock quantity as the three number columns a download writes with
/// *Show boxes* on: boxes, pieces, total. An item with no pack has no box
/// figure and its pieces are the whole; text that is not a figure goes in
/// the total as it stands.
List<Object?> stockBoxColumns(String quantity, String packSize) {
  final double? value = double.tryParse(quantity.trim());
  if (value == null) {
    return <Object?>[null, null, quantity.trim().isEmpty ? null : quantity];
  }
  final double? pack = packOf(packSize);
  if (pack == null) return <Object?>[null, value, value];
  final ({int boxes, double pieces}) split = splitPieces(value.abs(), pack);
  final int sign = value < 0 ? -1 : 1;
  return <Object?>[sign * split.boxes, sign * split.pieces, value];
}

/// The three headings [stockBoxColumns] fills, after [label].
List<String> stockBoxHeadings(String label) =>
    <String>['$label boxes', '$label pieces', '$label total'];

/// The person's *Show boxes* choice, kept on this PC per signed-in user in
/// the desktop preferences' workspace state (the local file is per Windows
/// account, not per user). One choice serves every stock screen. Nothing
/// is asked of the server.
class ShowBoxesChoice {
  ShowBoxesChoice({this.preferences, String? userId})
      : userId = userId ?? '',
        on = _read(preferences, userId ?? '');

  final DesktopPreferencesService? preferences;
  final String userId;

  /// Whether the person last turned it on. Off to start.
  bool on;

  /// The workspace-state key the choice is kept under for [userId].
  static String keyFor(String userId) => 'show_boxes.$userId';

  static bool _read(DesktopPreferencesService? preferences, String userId) =>
      preferences?.workspaceState(keyFor(userId))['on'] == true;

  /// Turn it on or off, and remember that for next time.
  void choose(bool value) {
    on = value;
    final DesktopPreferencesService? store = preferences;
    if (store == null) return;
    unawaited(store.saveWorkspaceState(
        keyFor(userId), <String, dynamic>{'on': value}));
  }
}

/// The *Show boxes* switch on a stock screen's line. Changes how quantities
/// read, never a quantity.
class ShowBoxesToggle extends StatelessWidget {
  const ShowBoxesToggle({
    super.key = const ValueKey<String>('show-boxes'),
    required this.value,
    required this.onChanged,
  });

  final bool value;
  final ValueChanged<bool> onChanged;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
    // A tick box and two words, about 110 px: inside the room a toolbar
    // keeps for a tool it cannot measure (120), on and off alike.
    return Tooltip(
      message: 'Read quantities of an item with a box as boxes and pieces, '
          'with the pieces beside them',
      child: Semantics(
        button: true,
        toggled: value,
        child: InkWell(
          onTap: () => onChanged(!value),
          borderRadius: BorderRadius.circular(5),
          child: Container(
            height: 32,
            padding: const EdgeInsets.symmetric(horizontal: 8),
            decoration: BoxDecoration(
              color: value ? scheme.secondaryContainer : null,
              border: Border.all(color: scheme.outlineVariant),
              borderRadius: BorderRadius.circular(5),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  value ? Icons.check_box : Icons.check_box_outline_blank,
                  size: 16,
                  color: value ? scheme.onSecondaryContainer : null,
                ),
                const SizedBox(width: 4),
                Text(
                  'Show boxes',
                  maxLines: 1,
                  style: theme.textTheme.bodyMedium?.copyWith(
                    fontSize: 13,
                    color: value ? scheme.onSecondaryContainer : null,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// A box cell for an item with no pack: drawn, closed, and never focused.
class _ClosedCell extends StatelessWidget {
  const _ClosedCell({super.key});

  @override
  Widget build(BuildContext context) {
    final ColorScheme scheme = Theme.of(context).colorScheme;
    return Container(
      height: 30,
      alignment: Alignment.centerRight,
      padding: const EdgeInsets.symmetric(horizontal: 6),
      decoration: BoxDecoration(
        color: scheme.surfaceContainerHigh,
        borderRadius: BorderRadius.circular(4),
      ),
      child: Text('–', style: TextStyle(color: scheme.onSurfaceVariant)),
    );
  }
}
