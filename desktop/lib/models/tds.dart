/// The sections a deduction of tax at source is filed under (backlog 53.1).
///
/// The server's `app/finance/tds.py` holds the same list and refuses any
/// other code. The sections are the Income-tax Act's; rates change every
/// Finance Act, so none is held here -- the amount deducted is typed, as the
/// challan and the return will state it.
const Map<String, String> tdsSections = {
  '194Q': 'Purchase of goods',
  '194C': 'Contractors and transporters',
  '194J': 'Professional or technical fees',
  '194I': 'Rent',
  '194H': 'Commission or brokerage',
  '194A': 'Interest other than on securities',
  '194R': 'Benefits or perquisites of business',
  '194T': 'Payments by a firm to its partners',
  '192': 'Salary',
  '194O': 'E-commerce operator',
};

/// Why a deduction cannot be recorded, or null when it can.
///
/// Mirrors the server's `check_tds`, so the person is told before the save.
String? tdsProblem({
  required String amount,
  required String tdsAmount,
  required String? section,
}) {
  final double total = double.tryParse(amount.trim()) ?? 0;
  final String typed = tdsAmount.trim();
  if (typed.isEmpty) return null;
  final double? deducted = double.tryParse(typed);
  if (deducted == null || deducted < 0) {
    return 'TDS deducted must be a number, 0 or more.';
  }
  if (deducted == 0) return null;
  if (section == null || section.isEmpty) {
    return 'Choose the TDS section the deduction is filed under.';
  }
  if (deducted >= total) {
    return 'TDS deducted must be less than the amount it is deducted from.';
  }
  return null;
}
