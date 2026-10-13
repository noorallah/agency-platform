// Backlog 131 (M13): the Price level box on a sales order and on a sales bill
// typed directly. One switch on the document reprices the whole document; the
// blank entry, "Customer's usual", leaves the choice to the customer's own
// level (his, else his group's). The box is drawn only when the firm has
// price levels to choose from.

import 'package:flutter/material.dart';

import '../../models/pricing.dart';
import '../../phase2/document_page.dart';

/// The value of the "Customer's usual" entry; it is sent as null.
const String usualPriceLevelChoice = '';

/// The levels the box offers: the active ones, plus the document's own saved
/// level when that has since been switched off, so a saved choice never
/// shows blank.
List<PriceLevelRecord> offeredPriceLevels(
  List<PriceLevelRecord> all,
  String savedId,
) =>
    <PriceLevelRecord>[
      for (final PriceLevelRecord level in all)
        if (level.isActive || level.id == savedId) level,
    ];

/// What the customer's usual level is, in words, or null while it is not
/// known. [usualId] null or empty is a customer with no level at all.
String? priceLevelHelper(
  List<PriceLevelRecord> all, {
  required bool known,
  String? usualId,
}) {
  if (!known) return null;
  if (usualId == null || usualId.isEmpty) {
    return "This customer has no price level: the product's price";
  }
  for (final PriceLevelRecord level in all) {
    if (level.id == usualId) return 'Usual for this customer: ${level.label}';
  }
  return 'Usual for this customer: a price level';
}

/// `100.0000` as `100.00`: the server's scale, kept to two places unless the
/// price really has more.
String plainQuotedPrice(String value) {
  final String text = value.trim();
  if (!text.contains('.')) return text;
  String trimmed = text.replaceAll(RegExp(r'0+$'), '');
  final int decimals = trimmed.length - trimmed.indexOf('.') - 1;
  if (decimals < 2) {
    trimmed = trimmed.padRight(trimmed.length + 2 - decimals, '0');
  }
  return trimmed;
}

/// A compact dropdown labelled "Price level" for a document's header.
/// [fieldKey] goes on the dropdown itself, so a test can tap it; the box is
/// built again when the choice is set from code, because the dropdown reads
/// its value only once.
class PriceLevelBox extends StatelessWidget {
  const PriceLevelBox({
    super.key,
    required this.fieldKey,
    required this.levels,
    required this.value,
    required this.onChanged,
    this.helper,
    this.enabled = true,
    this.width = 240,
  });

  final Key fieldKey;
  final List<PriceLevelRecord> levels;

  /// A level id, or [usualPriceLevelChoice].
  final String value;
  final ValueChanged<String> onChanged;
  final String? helper;
  final bool enabled;
  final double width;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final String shown = levels.any((level) => level.id == value)
        ? value
        : usualPriceLevelChoice;
    return DocumentField(
      label: 'Price level',
      width: width,
      below: helper == null
          ? null
          : Text(
              helper!,
              key: const ValueKey('price-level-helper'),
              style: theme.textTheme.bodySmall?.copyWith(
                fontSize: 11,
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
      child: KeyedSubtree(
        key: ValueKey<String>('price-level-box-${levels.length}-$shown'),
        child: DropdownButtonFormField<String>(
          key: fieldKey,
          isExpanded: true,
          isDense: true,
          initialValue: shown,
          decoration: documentBoxDecoration(context),
          items: [
            const DropdownMenuItem<String>(
              value: usualPriceLevelChoice,
              child: Text("Customer's usual", overflow: TextOverflow.ellipsis),
            ),
            for (final PriceLevelRecord level in levels)
              DropdownMenuItem<String>(
                value: level.id,
                child: Text(level.label, overflow: TextOverflow.ellipsis),
              ),
          ],
          onChanged: enabled
              ? (next) {
                  if (next != null && next != shown) onChanged(next);
                }
              : null,
        ),
      ),
    );
  }
}
