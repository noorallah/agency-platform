/// An amount the Indian way: lakh and crore for the large figures a glance
/// reads ("1.84 L", "2.10 Cr"), Indian digit grouping otherwise
/// ("62,400", "1,12,050.00" when [full]).
String indianAmount(double value, {bool full = false}) {
  final double magnitude = value.abs();
  final String sign = value < 0 ? '-' : '';
  if (!full && magnitude >= 10000000) {
    return '$sign${(magnitude / 10000000).toStringAsFixed(2)} Cr';
  }
  if (!full && magnitude >= 100000) {
    return '$sign${(magnitude / 100000).toStringAsFixed(2)} L';
  }
  final String fixed = magnitude.toStringAsFixed(full ? 2 : 0);
  final List<String> parts = fixed.split('.');
  final String digits = parts.first;
  String grouped;
  if (digits.length <= 3) {
    grouped = digits;
  } else {
    final String last3 = digits.substring(digits.length - 3);
    String rest = digits.substring(0, digits.length - 3);
    final List<String> pairs = [];
    while (rest.length > 2) {
      pairs.insert(0, rest.substring(rest.length - 2));
      rest = rest.substring(0, rest.length - 2);
    }
    if (rest.isNotEmpty) pairs.insert(0, rest);
    grouped = '${pairs.join(',')},$last3';
  }
  return '$sign$grouped${parts.length > 1 ? '.${parts[1]}' : ''}';
}
