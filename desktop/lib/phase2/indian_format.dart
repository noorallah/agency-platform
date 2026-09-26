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

/// An amount in words, the Indian way, as a bill prints it: "Six thousand
/// one hundred only", "One lakh twelve thousand fifty and forty paise only".
String indianAmountInWords(double value) {
  const List<String> ones = [
    '',
    'one',
    'two',
    'three',
    'four',
    'five',
    'six',
    'seven',
    'eight',
    'nine',
    'ten',
    'eleven',
    'twelve',
    'thirteen',
    'fourteen',
    'fifteen',
    'sixteen',
    'seventeen',
    'eighteen',
    'nineteen',
  ];
  const List<String> tens = [
    '',
    '',
    'twenty',
    'thirty',
    'forty',
    'fifty',
    'sixty',
    'seventy',
    'eighty',
    'ninety',
  ];
  String below100(int n) => n < 20
      ? ones[n]
      : '${tens[n ~/ 10]}${n % 10 == 0 ? '' : ' ${ones[n % 10]}'}';
  String below1000(int n) {
    final int hundreds = n ~/ 100;
    final int rest = n % 100;
    return [
      if (hundreds > 0) '${ones[hundreds]} hundred',
      if (rest > 0) below100(rest),
    ].join(' ');
  }

  final int paise = ((value.abs() * 100).round()) % 100;
  int rupees = (value.abs() * 100).round() ~/ 100;
  if (rupees == 0 && paise == 0) return 'Zero only';
  final List<String> parts = [];
  for (final (int size, String name) in const [
    (10000000, 'crore'),
    (100000, 'lakh'),
    (1000, 'thousand'),
  ]) {
    final int count = rupees ~/ size;
    if (count > 0) {
      parts.add('${count >= 100 ? below1000(count) : below100(count)} $name');
      rupees %= size;
    }
  }
  if (rupees > 0) parts.add(below1000(rupees));
  String words = parts.join(' ');
  if (paise > 0) {
    words = words.isEmpty
        ? '${below100(paise)} paise'
        : '$words and ${below100(paise)} paise';
  }
  return '${words[0].toUpperCase()}${words.substring(1)} only';
}
