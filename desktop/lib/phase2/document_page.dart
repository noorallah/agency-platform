import 'package:flutter/material.dart';

import '../core/design/design_tokens.dart';
import '../models/customer.dart';
import '../models/line_tax_rule.dart';
import '../ui/workspace/copy_value_button.dart';
import '../ui/workspace/workspace_components.dart';
import 'display_dates.dart';
import 'indian_format.dart';

/// The pieces of a phase 2 sales document screen, as the owner approved it
/// for the quotation (wireframe view 7, 2026-09-26) and asked for on orders
/// and invoices too: one line at the top, a header of small labelled boxes,
/// the lines as a table, the terms, the totals at the foot, and a side panel
/// for the line being typed. Each editor keeps its own state and rules and
/// lays itself out with these, so the three screens cannot drift apart.

/// The top line: the title, what the document is (its number, "Draft"),
/// the keys, and the buttons with the filled one last.
///
/// On a window too narrow for every button -- the 800x600 test window with a
/// document's full set of steps -- the buttons scroll sideways in their own
/// strip, the filled one last and in view, rather than running off the band;
/// the title keeps at least [minTitleWidth].
class DocumentPageBand extends StatefulWidget {
  const DocumentPageBand({
    super.key,
    required this.title,
    this.chips = const [],
    this.hint = '',
    this.actions = const [],
    this.number = '',
  });

  final String title;
  final List<String> chips;
  final String hint;
  final List<Widget> actions;

  /// What the title and chips keep before the buttons start to scroll.
  static const double minTitleWidth = 160;

  /// The saved document's own number, shown first among the chips with a
  /// copy icon beside it (backlog 83). Left empty for a number that is only
  /// a preview -- "(new)" is not a number anybody can quote yet.
  final String number;

  @override
  State<DocumentPageBand> createState() => _DocumentPageBandState();
}

class _DocumentPageBandState extends State<DocumentPageBand> {
  final ScrollController _sideways = ScrollController();

  String get title => widget.title;
  List<String> get chips => widget.chips;
  String get hint => widget.hint;
  List<Widget> get actions => widget.actions;
  String get number => widget.number;

  @override
  void dispose() {
    _sideways.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => LayoutBuilder(
        builder: (context, constraints) => _band(
          context,
          // The band's padding and the gap before the buttons come off too.
          constraints.hasBoundedWidth
              ? constraints.maxWidth - 24 - 12 - DocumentPageBand.minTitleWidth
              : double.infinity,
        ),
      );

  Widget _band(BuildContext context, double actionsWidth) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
    return DecoratedBox(
      decoration: BoxDecoration(
        color: scheme.surfaceContainerLowest,
        border: Border(bottom: BorderSide(color: scheme.outlineVariant)),
      ),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 6, 12, 6),
        child: Row(children: [
          // The title and chips shorten before the buttons are pushed off a
          // narrow window.
          Flexible(
            flex: 3,
            child: Row(mainAxisSize: MainAxisSize.min, children: [
              Flexible(
                child: Text(
                  title,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: theme.textTheme.titleMedium
                      ?.copyWith(fontWeight: FontWeight.w700),
                ),
              ),
              const SizedBox(width: 12),
              if (number.isNotEmpty) ...[
                Flexible(
                  child: Text(
                    number,
                    key: const ValueKey('document-number'),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: theme.textTheme.bodyMedium?.copyWith(
                      fontSize: 13,
                      fontWeight: FontWeight.w600,
                      color: scheme.onSurfaceVariant,
                    ),
                  ),
                ),
                CopyValueButton(
                  key: const ValueKey('document-number-copy'),
                  value: number,
                ),
                const SizedBox(width: 8),
              ],
              for (final String chip in chips)
                Flexible(
                  child: Padding(
                    padding: const EdgeInsets.only(right: 8),
                    child: Text(
                      chip,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: theme.textTheme.bodyMedium?.copyWith(
                        fontSize: 13,
                        color: scheme.onSurfaceVariant,
                      ),
                    ),
                  ),
                ),
            ]),
          ),
          // The key hints give way first on a narrow window.
          Expanded(
            child: Align(
              alignment: Alignment.centerRight,
              child: Text(
                hint,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: theme.textTheme.bodySmall
                    ?.copyWith(color: scheme.onSurfaceVariant),
              ),
            ),
          ),
          const SizedBox(width: 12),
          ConstrainedBox(
            constraints: BoxConstraints(
              maxWidth: actionsWidth < 0 ? 0 : actionsWidth,
            ),
            child: Scrollbar(
              controller: _sideways,
              child: SingleChildScrollView(
                key: const ValueKey('document-band-actions'),
                controller: _sideways,
                scrollDirection: Axis.horizontal,
                // Starts at the end: the filled button is the one in view.
                reverse: true,
                child: Phase2ButtonTheme(
                  child: Row(children: [
                    for (int i = 0; i < actions.length; i++) ...[
                      if (i > 0) const SizedBox(width: 6),
                      actions[i],
                    ],
                  ]),
                ),
              ),
            ),
          ),
        ]),
      ),
    );
  }
}

/// A small labelled box, as the wireframe's header draws them; "auto" in
/// green when the screen filled it.
class DocumentField extends StatelessWidget {
  const DocumentField({
    super.key,
    required this.label,
    required this.child,
    this.auto = false,
    this.width = 200,
    this.below,
  });

  final String label;
  final Widget child;
  final bool auto;
  final double width;
  final Widget? below;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return SizedBox(
      width: width,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(children: [
            Flexible(
              child: Text(
                label,
                overflow: TextOverflow.ellipsis,
                style: theme.textTheme.bodySmall?.copyWith(
                  fontSize: 11,
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
            ),
            if (auto) ...[
              const SizedBox(width: 4),
              Text(
                'auto',
                style: theme.textTheme.bodySmall?.copyWith(
                  fontSize: 10,
                  color: context.semanticColors.success,
                ),
              ),
            ],
          ]),
          const SizedBox(height: 3),
          child,
          if (below != null) ...[const SizedBox(height: 3), below!],
        ],
      ),
    );
  }
}

/// A box's look inside a document screen: small, white, a light edge.
InputDecoration documentBoxDecoration(BuildContext context, {String? hint}) {
  final ColorScheme scheme = Theme.of(context).colorScheme;
  final OutlineInputBorder edge = OutlineInputBorder(
    borderRadius: BorderRadius.circular(5),
    borderSide: BorderSide(color: scheme.outlineVariant),
  );
  return InputDecoration(
    isDense: true,
    hintText: hint,
    filled: true,
    fillColor: scheme.surfaceContainerLowest,
    contentPadding: const EdgeInsets.symmetric(horizontal: 8, vertical: 9),
    border: edge,
    enabledBorder: edge,
    focusedBorder: edge.copyWith(
      borderSide: BorderSide(color: scheme.primary, width: 1.5),
    ),
  );
}

/// A box inside a table cell: right-aligned figures, no room for an error
/// line (the row is fixed height; the box's red edge says it).
InputDecoration documentCellDecoration(BuildContext context, {String? hint}) =>
    documentBoxDecoration(context, hint: hint).copyWith(
      contentPadding: const EdgeInsets.symmetric(horizontal: 6, vertical: 7),
      errorStyle: const TextStyle(height: 0, fontSize: 0),
    );

/// The header band of labelled boxes, wrapping onto a second row as the
/// window narrows.
class DocumentHeader extends StatelessWidget {
  const DocumentHeader({super.key, required this.children});

  final List<Widget> children;

  @override
  Widget build(BuildContext context) => DecoratedBox(
        decoration: BoxDecoration(
          border: Border(
            bottom:
                BorderSide(color: Theme.of(context).colorScheme.outlineVariant),
          ),
        ),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(12, 10, 12, 10),
          child: Wrap(spacing: 14, runSpacing: 8, children: children),
        ),
      );
}

/// One column of the lines table: its heading, width (0 takes what is
/// left) and whether it holds figures.
class DocumentColumn {
  const DocumentColumn(this.label, this.width, {this.numeric = false});

  final String label;
  final double width;
  final bool numeric;
}

/// One cell, sized and aligned as its column says, with a gap after it so
/// neighbouring headings never run together.
Widget documentCell(DocumentColumn column, Widget child) {
  final Widget spaced = Padding(
    padding: const EdgeInsets.only(right: 8),
    child: Align(
      alignment: column.numeric ? Alignment.centerRight : Alignment.centerLeft,
      child: child,
    ),
  );
  return column.width == 0
      ? Expanded(child: spaced)
      : SizedBox(width: column.width + 8, child: spaced);
}

/// The lines as a table: the heading row, the rows, and a last row that adds
/// one.
///
/// On a window too narrow for every column -- the 800x600 test window, or a
/// screen with many figures -- the table scrolls sideways inside itself
/// rather than running off the window: the fixed columns keep their widths
/// and the one that takes what is left (the product) keeps at least
/// [minFlexWidth].
class DocumentLineTable extends StatefulWidget {
  const DocumentLineTable({
    super.key,
    required this.columns,
    required this.rows,
    this.addLabel,
    this.onAdd,
  });

  final List<DocumentColumn> columns;
  final List<Widget> rows;

  /// The last row's words, e.g. "4   + add a product (Ctrl+Enter)"; no row
  /// when null.
  final String? addLabel;
  final VoidCallback? onAdd;

  /// The least the column with no fixed width is squeezed to before the
  /// table scrolls sideways instead.
  static const double minFlexWidth = 120;

  /// The width every column needs: each fixed column and its gap, the
  /// flexible one at [minFlexWidth], the row's side padding and its 3-pixel
  /// current-line edge.
  static double minimumWidth(List<DocumentColumn> columns) {
    double width = 24 + 3;
    for (final DocumentColumn column in columns) {
      width += (column.width == 0 ? minFlexWidth : column.width) + 8;
    }
    return width;
  }

  @override
  State<DocumentLineTable> createState() => _DocumentLineTableState();
}

class _DocumentLineTableState extends State<DocumentLineTable> {
  final ScrollController _sideways = ScrollController();

  @override
  void dispose() {
    _sideways.dispose();
    super.dispose();
  }

  Widget _table(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
    final TextStyle? heading = theme.textTheme.labelMedium?.copyWith(
      fontSize: 12,
      fontWeight: FontWeight.w600,
      color: scheme.onSurfaceVariant,
    );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Container(
          height: 34,
          padding: const EdgeInsets.symmetric(horizontal: 12),
          decoration: BoxDecoration(
            color: scheme.surfaceContainerLow,
            border: Border(bottom: BorderSide(color: scheme.outlineVariant)),
          ),
          child: Row(children: [
            for (final DocumentColumn column in widget.columns)
              documentCell(column, Text(column.label, style: heading)),
          ]),
        ),
        Expanded(
          child: ListView(
            children: [
              ...widget.rows,
              if (widget.addLabel != null)
                InkWell(
                  key: const ValueKey('document-add-line'),
                  onTap: widget.onAdd,
                  child: Container(
                    height: 36,
                    padding: const EdgeInsets.symmetric(horizontal: 12),
                    alignment: Alignment.centerLeft,
                    child: Text(
                      widget.addLabel!,
                      style: theme.textTheme.bodyMedium?.copyWith(
                        fontSize: 13,
                        fontStyle: FontStyle.italic,
                        color: scheme.onSurfaceVariant,
                      ),
                    ),
                  ),
                ),
            ],
          ),
        ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) => LayoutBuilder(
        builder: (context, constraints) {
          final double needed = DocumentLineTable.minimumWidth(widget.columns);
          if (!constraints.hasBoundedWidth || constraints.maxWidth >= needed) {
            return _table(context);
          }
          return Scrollbar(
            key: const ValueKey('document-lines-sideways'),
            controller: _sideways,
            thumbVisibility: true,
            child: SingleChildScrollView(
              controller: _sideways,
              scrollDirection: Axis.horizontal,
              child: SizedBox(width: needed, child: _table(context)),
            ),
          );
        },
      );
}

/// One row of the lines table: the line being typed is tinted and marked on
/// its left edge, as a selected grid row.
class DocumentLineRow extends StatelessWidget {
  const DocumentLineRow({
    super.key,
    required this.columns,
    required this.cells,
    required this.current,
    required this.onTap,
    this.height = 52,
  });

  final List<DocumentColumn> columns;
  final List<Widget> cells;
  final bool current;
  final VoidCallback onTap;
  final double height;

  @override
  Widget build(BuildContext context) {
    final ColorScheme scheme = Theme.of(context).colorScheme;
    return InkWell(
      onTap: onTap,
      child: Container(
        height: height,
        padding: const EdgeInsets.symmetric(horizontal: 12),
        decoration: BoxDecoration(
          color: current
              ? Color.alphaBlend(
                  scheme.primary.withValues(alpha: .10),
                  scheme.surfaceContainerLowest,
                )
              : scheme.surfaceContainerLowest,
          border: Border(
            bottom: BorderSide(color: scheme.surfaceContainerHighest),
            left: BorderSide(
              color: current ? scheme.primary : Colors.transparent,
              width: 3,
            ),
          ),
        ),
        child: Row(children: [
          for (int i = 0; i < columns.length && i < cells.length; i++)
            documentCell(columns[i], cells[i]),
        ]),
      ),
    );
  }
}

/// The terms under the lines: small labelled boxes in a wrapping row.
class DocumentTerms extends StatelessWidget {
  const DocumentTerms({super.key, required this.children});

  final List<Widget> children;

  @override
  Widget build(BuildContext context) => DecoratedBox(
        decoration: BoxDecoration(
          border: Border(
            top:
                BorderSide(color: Theme.of(context).colorScheme.outlineVariant),
          ),
        ),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(12, 8, 12, 8),
          // Scrolls rather than squeezing the lines out on a short window,
          // where a tender split or a long note makes the terms tall.
          child: ConstrainedBox(
            constraints: BoxConstraints(
              maxHeight: MediaQuery.sizeOf(context).height * 0.25,
            ),
            child: SingleChildScrollView(
              child: Wrap(spacing: 14, runSpacing: 8, children: children),
            ),
          ),
        ),
      );
}

/// What a priced line was taxed on, or null while it has no price.
///
/// The server's `net_amount` on a quotation, order or invoice line is what
/// the line comes to **with** its tax, so the taxable value is that less
/// `tax_amount`. Read as the taxable value itself it showed 582.40 for ten
/// at 52.00 with 12% GST, a rate of 10.7% and an amount of 644.80 (D-UI-95).
double? documentLineTaxable(Object? netAmount, Object? taxAmount) {
  final double? net = double.tryParse('${netAmount ?? ''}');
  if (net == null) return null;
  return net - (double.tryParse('${taxAmount ?? ''}') ?? 0);
}

/// The totals at the foot: the amount in words at the left (or [note] until
/// there is one), the figures at the right, the total largest.
class DocumentTotalsBar extends StatelessWidget {
  const DocumentTotalsBar({
    super.key,
    required this.figures,
    this.total,
    this.note = '',
    this.warn = false,
  });

  /// Each figure's label and value, in order; the last is the total.
  final List<(String, double)> figures;

  /// The total in words is written from this; [note] shows while it is null.
  final double? total;
  final String note;

  /// Whether [note] is something the person must do before anything is
  /// priced -- choose a customer -- and so is drawn as a warning label, where
  /// grey words at the foot were not noticed (D-UI-94).
  final bool warn;

  Widget _warning(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final Color colour = context.semanticColors.warning;
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        key: const ValueKey('document-totals-warning'),
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
        decoration: BoxDecoration(
          color: colour.withValues(alpha: .14),
          border: Border.all(color: colour),
          borderRadius: BorderRadius.circular(6),
        ),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          Icon(Icons.warning_amber_rounded, size: 18, color: colour),
          const SizedBox(width: 6),
          Flexible(
            child: Text(
              note,
              overflow: TextOverflow.ellipsis,
              style: theme.textTheme.bodyMedium
                  ?.copyWith(color: colour, fontWeight: FontWeight.w700),
            ),
          ),
        ]),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
    return Container(
      padding: const EdgeInsets.fromLTRB(14, 8, 14, 8),
      decoration: BoxDecoration(
        color: scheme.surfaceContainerLowest,
        border: Border(top: BorderSide(color: scheme.onSurface, width: 2)),
      ),
      child: Row(children: [
        Expanded(
          child: total == null && warn
              ? _warning(context)
              : Text(
                  total == null ? note : indianAmountInWords(total!),
                  overflow: TextOverflow.ellipsis,
                  style: theme.textTheme.bodyMedium
                      ?.copyWith(color: scheme.onSurfaceVariant),
                ),
        ),
        // Scaled down rather than pushed off a narrow window.
        Flexible(
          child: FittedBox(
            fit: BoxFit.scaleDown,
            alignment: Alignment.centerRight,
            child: Row(mainAxisSize: MainAxisSize.min, children: [
              for (int i = 0; i < figures.length; i++)
                Padding(
                  padding: const EdgeInsets.only(left: 24),
                  child: Text.rich(TextSpan(children: [
                    TextSpan(
                      text: '${figures[i].$1}  ',
                      style:
                          theme.textTheme.bodyMedium?.copyWith(fontSize: 13),
                    ),
                    TextSpan(
                      text: indianAmount(figures[i].$2, full: true),
                      style: theme.textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.w700,
                        fontSize: i == figures.length - 1 ? 18 : 16,
                      ),
                    ),
                  ])),
                ),
            ]),
          ),
        ),
      ]),
    );
  }
}

/// The side panel for the line being typed.
class DocumentSidePanel extends StatelessWidget {
  const DocumentSidePanel({super.key, required this.children});

  final List<Widget> children;

  /// Wide enough for the panel beside the lines; narrower windows drop it
  /// first (4.11).
  static const double showFrom = 1150;
  static const double width = 290;

  @override
  Widget build(BuildContext context) {
    final ColorScheme scheme = Theme.of(context).colorScheme;
    return Container(
      key: const ValueKey('document-side-panel'),
      width: width,
      decoration: BoxDecoration(
        color: scheme.surfaceContainerLow,
        border: Border(left: BorderSide(color: scheme.outlineVariant)),
      ),
      child: ListView(
        padding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
        children: children,
      ),
    );
  }
}

/// A section heading in the side panel.
class DocumentSideHeading extends StatelessWidget {
  const DocumentSideHeading(this.text, {super.key});

  final String text;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.fromLTRB(0, 12, 0, 6),
      child: Text(
        text.toUpperCase(),
        style: theme.textTheme.labelSmall?.copyWith(
          letterSpacing: .8,
          fontWeight: FontWeight.w700,
          color: theme.colorScheme.onSurfaceVariant,
        ),
      ),
    );
  }
}

/// A label and its value in the side panel.
class DocumentSidePair extends StatelessWidget {
  const DocumentSidePair(
    this.label,
    this.value, {
    super.key,
    this.bold = false,
    this.tone,
  });

  final String label;
  final String value;
  final bool bold;
  final Color? tone;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(children: [
        Expanded(
          child: Text(
            label,
            style: theme.textTheme.bodyMedium?.copyWith(
              fontSize: 13,
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
        ),
        const SizedBox(width: 8),
        // A long value (a bank and its IFSC, a GSTIN) wraps at a width of its
        // own rather than running off the panel; a short one keeps to the
        // right edge and leaves the label the rest of the line.
        ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 150),
          child: Text(
            value,
            textAlign: TextAlign.right,
            style: theme.textTheme.bodyMedium?.copyWith(
              fontSize: 13,
              fontWeight: bold ? FontWeight.w700 : null,
              color: tone,
            ),
          ),
        ),
      ]),
    );
  }
}

/// A small grey note under a side-panel line: where a figure came from.
class DocumentSideNote extends StatelessWidget {
  const DocumentSideNote(this.text, {super.key});

  final String text;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Text(
      text,
      style: theme.textTheme.bodySmall?.copyWith(
        fontSize: 11,
        color: theme.colorScheme.onSurfaceVariant,
      ),
    );
  }
}

/// The tax part of a side panel: taxable, the split (CGST + SGST within a
/// state, IGST across), and the line total.
List<Widget> documentTaxLines({
  required double taxable,
  required double tax,
  required bool? interstate,
  LineTaxRule? taxRule,
}) {
  final double rate = taxable > 0 ? tax / taxable * 100 : 0;
  String percent(double value) {
    final String fixed = value.toStringAsFixed(2);
    return fixed.endsWith('.00')
        ? fixed.substring(0, fixed.length - 3)
        : fixed.replaceFirst(RegExp(r'0$'), '');
  }

  return [
    DocumentSideHeading(interstate == null
        ? 'Tax'
        : interstate
            ? 'Tax (inter-state)'
            : 'Tax (intra-state)'),
    DocumentSidePair('Taxable', indianAmount(taxable, full: true)),
    if (interstate ?? false)
      DocumentSidePair('IGST ${percent(rate)}%', indianAmount(tax, full: true))
    else ...[
      DocumentSidePair(
          'CGST ${percent(rate / 2)}%', indianAmount(tax / 2, full: true)),
      DocumentSidePair(
          'SGST ${percent(rate / 2)}%', indianAmount(tax / 2, full: true)),
    ],
    const Divider(height: 12),
    DocumentSidePair('Line total', indianAmount(taxable + tax, full: true),
        bold: true),
    if (taxRule != null && taxRule.code != null)
      DocumentSideNote(taxRule.label),
  ];
}

/// A date as the screens write it: 26-09-2026, or in the format the person
/// chose in My preferences ([DisplayDates]).
String documentDate(DateTime day) => DisplayDates.write(day);

/// Which bill a line's last rate came from, and the discount it carried:
/// `SI-12 on 09-03-2026 · 5% off` (backlog 55 G6). Said, never filled in --
/// a discount box prefilled from history would become an override.
String documentLastBilled(String number, String day, String discountPercent) {
  final DateTime? parsed = DateTime.tryParse(day);
  final String rate = documentQuantity(discountPercent);
  final bool discounted = (double.tryParse(rate) ?? 0) > 0;
  return '$number on ${parsed == null ? day : documentDate(parsed)}'
      '${discounted ? ' · $rate% off' : ''}';
}

/// A figure as money in Indian digits, or as it came when it is not one.
String documentMoney(String value) {
  final double? number = double.tryParse(value.trim());
  return number == null ? value : indianAmount(number, full: true);
}

/// A quantity without the store's trailing zeros.
String documentQuantity(String value) {
  if (!value.contains('.')) return value;
  final String trimmed = value.replaceFirst(RegExp(r'0+$'), '');
  return trimmed.endsWith('.')
      ? trimmed.substring(0, trimmed.length - 1)
      : trimmed;
}

/// Where a customer is, from their billing address, else their first.
String documentCustomerPlace(Customer customer) {
  if (customer.addresses.isEmpty) return '';
  final CustomerAddress address = customer.addresses.firstWhere(
    (item) => item.isDefaultBilling,
    orElse: () => customer.addresses.first,
  );
  return [address.city, address.state]
      .where((part) => part.trim().isNotEmpty)
      .join(', ');
}

/// The line under a document's customer: GSTIN, place, and what they owe
/// against their limit -- in the alert colour from 80% of it.
class DocumentCustomerLine extends StatelessWidget {
  const DocumentCustomerLine(this.customer, {super.key});

  final Customer customer;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final double balance = double.tryParse(customer.currentOutstanding) ?? 0;
    final double limit = double.tryParse(customer.creditLimit) ?? 0;
    final bool high = limit > 0 && balance >= limit * .8;
    final String place = documentCustomerPlace(customer);
    final TextStyle? style = theme.textTheme.bodySmall?.copyWith(fontSize: 11);
    // The GSTIN with a copy icon beside it (backlog 83), then the rest.
    if (customer.gstNumber.isNotEmpty) {
      return Row(children: [
        Text.rich(
          TextSpan(style: style, children: [
            const TextSpan(text: 'GSTIN '),
            TextSpan(
              text: customer.gstNumber,
              style: const TextStyle(fontWeight: FontWeight.w600),
            ),
          ]),
        ),
        CopyValueButton(
          key: const ValueKey('document-gstin-copy'),
          value: customer.gstNumber,
          what: 'GSTIN',
          size: 11,
        ),
        Flexible(
          child: Text.rich(
            _customerRest(theme, place, balance, limit, high, lead: '·  '),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
        ),
      ]);
    }
    return Text.rich(_customerRest(theme, place, balance, limit, high));
  }

  TextSpan _customerRest(
    ThemeData theme,
    String place,
    double balance,
    double limit,
    bool high, {
    String lead = '',
  }) =>
      TextSpan(
        style: theme.textTheme.bodySmall?.copyWith(fontSize: 11),
        children: [
          if (lead.isNotEmpty) TextSpan(text: lead),
          if (place.isNotEmpty) TextSpan(text: '$place  ·  '),
          const TextSpan(text: 'bal '),
          TextSpan(
            text: indianAmount(balance, full: true),
            style: TextStyle(
              fontWeight: FontWeight.w600,
              color: high ? theme.colorScheme.error : null,
            ),
          ),
          if (limit > 0)
            TextSpan(text: ' / limit ${indianAmount(limit, full: true)}'),
        ],
      );
}

/// A party's line under its picker -- its code, "GSTIN ..." with a copy
/// icon beside the number (backlog 83), and what follows -- in the quiet
/// small type of the document header.
class DocumentGstinLine extends StatelessWidget {
  const DocumentGstinLine({
    super.key,
    required this.gstin,
    this.leading = const [],
    this.trailing = const [],
    this.unregistered = '',
  });

  final String gstin;

  /// What comes before the GSTIN, e.g. the party's code.
  final List<String> leading;

  /// What comes after it, e.g. a phone number.
  final List<String> trailing;

  /// Said in the GSTIN's place when there is none; nothing when empty.
  final String unregistered;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final TextStyle? style = theme.textTheme.bodySmall?.copyWith(
      fontSize: 11,
      color: theme.colorScheme.onSurfaceVariant,
    );
    final String head = [
      for (final String part in leading)
        if (part.isNotEmpty) part,
      if (gstin.isNotEmpty)
        'GSTIN $gstin'
      else if (unregistered.isNotEmpty)
        unregistered,
    ].join('  ·  ');
    final String tail = [
      for (final String part in trailing)
        if (part.isNotEmpty) part,
    ].join('  ·  ');
    return Row(children: [
      Flexible(
        child: Text(head, overflow: TextOverflow.ellipsis, style: style),
      ),
      if (gstin.isNotEmpty)
        CopyValueButton(
          key: const ValueKey('document-gstin-copy'),
          value: gstin,
          what: 'GSTIN',
          size: 11,
        ),
      if (tail.isNotEmpty)
        Flexible(
          child: Text(
            gstin.isEmpty ? '  ·  $tail' : '·  $tail',
            overflow: TextOverflow.ellipsis,
            style: style,
          ),
        ),
    ]);
  }
}

/// The customer part of a side panel: what they owe, and what they would
/// owe once this document is billed.
List<Widget> documentCustomerLines(
  BuildContext context,
  Customer customer, {
  double? thisDocument,
  String afterLabel = 'If it becomes an order',
  String note = '',
}) {
  final double balance = double.tryParse(customer.currentOutstanding) ?? 0;
  final double limit = double.tryParse(customer.creditLimit) ?? 0;
  return [
    const DocumentSideHeading('Customer'),
    DocumentSidePair(
      'Outstanding',
      indianAmount(balance, full: true),
      tone: limit > 0 && balance >= limit * .8
          ? Theme.of(context).colorScheme.error
          : null,
    ),
    if (thisDocument != null)
      DocumentSidePair(
          afterLabel, indianAmount(balance + thisDocument, full: true)),
    DocumentSideNote([
      if (limit > 0) 'credit limit ${indianAmount(limit, full: true)}',
      if (note.isNotEmpty) note,
    ].join(' · ')),
  ];
}
