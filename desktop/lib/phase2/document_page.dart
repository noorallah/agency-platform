import 'package:flutter/material.dart';

import '../core/design/design_tokens.dart';
import '../models/customer.dart';
import '../ui/workspace/workspace_components.dart';
import 'indian_format.dart';

/// The pieces of a phase 2 sales document screen, as the owner approved it
/// for the quotation (wireframe view 7, 2026-09-26) and asked for on orders
/// and invoices too: one line at the top, a header of small labelled boxes,
/// the lines as a table, the terms, the totals at the foot, and a side panel
/// for the line being typed. Each editor keeps its own state and rules and
/// lays itself out with these, so the three screens cannot drift apart.

/// The top line: the title, what the document is (its number, "Draft"),
/// the keys, and the buttons with the filled one last.
class DocumentPageBand extends StatelessWidget {
  const DocumentPageBand({
    super.key,
    required this.title,
    this.chips = const [],
    this.hint = '',
    this.actions = const [],
  });

  final String title;
  final List<String> chips;
  final String hint;
  final List<Widget> actions;

  @override
  Widget build(BuildContext context) {
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
          Text(
            title,
            style: theme.textTheme.titleMedium
                ?.copyWith(fontWeight: FontWeight.w700),
          ),
          const SizedBox(width: 12),
          for (final String chip in chips)
            Padding(
              padding: const EdgeInsets.only(right: 8),
              child: Text(
                chip,
                style: theme.textTheme.bodyMedium?.copyWith(
                  fontSize: 13,
                  color: scheme.onSurfaceVariant,
                ),
              ),
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
          Phase2ButtonTheme(
            child: Row(children: [
              for (int i = 0; i < actions.length; i++) ...[
                if (i > 0) const SizedBox(width: 6),
                actions[i],
              ],
            ]),
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
class DocumentLineTable extends StatelessWidget {
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

  @override
  Widget build(BuildContext context) {
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
            for (final DocumentColumn column in columns)
              documentCell(column, Text(column.label, style: heading)),
          ]),
        ),
        Expanded(
          child: ListView(
            children: [
              ...rows,
              if (addLabel != null)
                InkWell(
                  key: const ValueKey('document-add-line'),
                  onTap: onAdd,
                  child: Container(
                    height: 36,
                    padding: const EdgeInsets.symmetric(horizontal: 12),
                    alignment: Alignment.centerLeft,
                    child: Text(
                      addLabel!,
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
          child: Wrap(spacing: 14, runSpacing: 8, children: children),
        ),
      );
}

/// The totals at the foot: the amount in words at the left (or [note] until
/// there is one), the figures at the right, the total largest.
class DocumentTotalsBar extends StatelessWidget {
  const DocumentTotalsBar({
    super.key,
    required this.figures,
    this.total,
    this.note = '',
  });

  /// Each figure's label and value, in order; the last is the total.
  final List<(String, double)> figures;

  /// The total in words is written from this; [note] shows while it is null.
  final double? total;
  final String note;

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
          child: Text(
            total == null ? note : indianAmountInWords(total!),
            overflow: TextOverflow.ellipsis,
            style: theme.textTheme.bodyMedium
                ?.copyWith(color: scheme.onSurfaceVariant),
          ),
        ),
        for (int i = 0; i < figures.length; i++)
          Padding(
            padding: const EdgeInsets.only(left: 24),
            child: Text.rich(TextSpan(children: [
              TextSpan(
                text: '${figures[i].$1}  ',
                style: theme.textTheme.bodyMedium?.copyWith(fontSize: 13),
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
        Text(
          value,
          style: theme.textTheme.bodyMedium?.copyWith(
            fontSize: 13,
            fontWeight: bold ? FontWeight.w700 : null,
            color: tone,
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
  ];
}

/// A date as the screens write it: 26-09-2026.
String documentDate(DateTime day) => '${day.day.toString().padLeft(2, '0')}-'
    '${day.month.toString().padLeft(2, '0')}-${day.year}';

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
    return Text.rich(
      TextSpan(
        style: theme.textTheme.bodySmall?.copyWith(fontSize: 11),
        children: [
          if (customer.gstNumber.isNotEmpty) ...[
            const TextSpan(text: 'GSTIN '),
            TextSpan(
              text: customer.gstNumber,
              style: const TextStyle(fontWeight: FontWeight.w600),
            ),
            const TextSpan(text: '  ·  '),
          ],
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
      ),
    );
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
