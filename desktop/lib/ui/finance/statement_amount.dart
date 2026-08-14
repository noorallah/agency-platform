/// Write a figure the way a statement writes it: negatives in parentheses.
///
/// A minus sign in a column of money is easy to miss and easy to mistake for a
/// hyphen, and the accounting reports have several places where a negative is
/// meaningful and normal -- a loss, a contra account that reduces income
/// rather than costing anything, an overdrawn bank account.
String presentAmount(String amount) {
  final String trimmed = amount.trim();
  if (!trimmed.startsWith('-')) return trimmed;
  return '(${trimmed.substring(1)})';
}
