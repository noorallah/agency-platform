/// How a stored line discount is read back into an editor.
///
/// A line stores the rate that was applied and, since 2026-09-13, where it
/// came from: `percent`/`amount` when somebody typed it, else the arrangement
/// the server resolved it from. The two look identical on the line, and an
/// editor that re-sent every stored rate as typed froze a price-list ladder
/// at its first step when the quantity moved (manual plan item 9.2). A typed
/// rate is kept when the line is reopened; a resolved one is priced afresh
/// and the editor says what it was.
library;

/// Whether a stored rate was typed rather than resolved by the server.
///
/// A line stored before the source was recorded is treated as resolved.
bool discountWasTyped(String source) =>
    source == 'percent' || source == 'amount';

/// The words for where a rate came from, for the helper under the box.
String discountSourceWords(String source) => switch (source) {
      'promotion' => 'a promotion',
      'price_list' => 'the price list',
      'customer' => "the customer's standing rate",
      'customer_group' => "the customer group's rate",
      'none' => 'no arrangement',
      _ => 'the last save',
    };

/// A stored rate without its trailing zeros: `6.7500` reads as `6.75`.
String trimDiscountRate(String rate) {
  final String text = rate.trim();
  if (!text.contains('.')) return text;
  final String trimmed = text.replaceFirst(RegExp(r'0+$'), '');
  return trimmed.endsWith('.')
      ? trimmed.substring(0, trimmed.length - 1)
      : trimmed;
}

/// What the helper says under a blank box on a reopened line.
String lastPricedHelper(String rate, String source) =>
    'Last priced at ${trimDiscountRate(rate)}% by '
    '${discountSourceWords(source)}. Blank prices it afresh.';
