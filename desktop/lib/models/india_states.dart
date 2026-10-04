/// The Indian states and union territories, with the numeric code GST gives
/// each (the first two digits of a GSTIN).
///
/// The firm form picks its state from this list (backlog 81) and stores the
/// state's NAME, so firms saved before read unchanged. The names are the ones
/// the geography masters seed into every firm store (migration
/// `20260917_0137`); `tests/unit/test_firm_state_list.py` fails the build if
/// the two lists drift. It lives here rather than being fetched because the
/// firm form is a platform screen, and the platform store holds no geography
/// tables (they are pruned from it, as every firm-owned table is).
class IndiaState {
  const IndiaState(this.gstCode, this.name);

  /// The two-digit GST state code, for example `33`.
  final String gstCode;
  final String name;
}

const List<IndiaState> indiaStates = <IndiaState>[
  IndiaState('37', 'Andhra Pradesh'),
  IndiaState('12', 'Arunachal Pradesh'),
  IndiaState('18', 'Assam'),
  IndiaState('10', 'Bihar'),
  IndiaState('22', 'Chhattisgarh'),
  IndiaState('30', 'Goa'),
  IndiaState('24', 'Gujarat'),
  IndiaState('06', 'Haryana'),
  IndiaState('02', 'Himachal Pradesh'),
  IndiaState('20', 'Jharkhand'),
  IndiaState('29', 'Karnataka'),
  IndiaState('32', 'Kerala'),
  IndiaState('23', 'Madhya Pradesh'),
  IndiaState('27', 'Maharashtra'),
  IndiaState('14', 'Manipur'),
  IndiaState('17', 'Meghalaya'),
  IndiaState('15', 'Mizoram'),
  IndiaState('13', 'Nagaland'),
  IndiaState('21', 'Odisha'),
  IndiaState('03', 'Punjab'),
  IndiaState('08', 'Rajasthan'),
  IndiaState('11', 'Sikkim'),
  IndiaState('33', 'Tamil Nadu'),
  IndiaState('36', 'Telangana'),
  IndiaState('16', 'Tripura'),
  IndiaState('09', 'Uttar Pradesh'),
  IndiaState('05', 'Uttarakhand'),
  IndiaState('19', 'West Bengal'),
  IndiaState('35', 'Andaman and Nicobar Islands'),
  IndiaState('04', 'Chandigarh'),
  IndiaState('26', 'Dadra and Nagar Haveli and Daman and Diu'),
  IndiaState('07', 'Delhi'),
  IndiaState('01', 'Jammu and Kashmir'),
  IndiaState('38', 'Ladakh'),
  IndiaState('31', 'Lakshadweep'),
  IndiaState('34', 'Puducherry'),
];

/// The state a GSTIN is registered in, from its first two digits, or null when
/// the text is not yet that long or names no state. `25` was Daman and Diu
/// before it merged with Dadra and Nagar Haveli (`26`), and older numbers
/// still carry it.
IndiaState? indiaStateForGstin(String gstin) {
  final String text = gstin.trim();
  if (text.length < 2) return null;
  String code = text.substring(0, 2);
  if (code == '25') code = '26';
  for (final IndiaState state in indiaStates) {
    if (state.gstCode == code) return state;
  }
  return null;
}

/// A state name reduced to what makes two spellings the same place:
/// `Tamilnadu`, `Tamil Nadu` and `TAMIL NADU` compare equal, and `&` reads as
/// `and`.
String indiaStateKey(String name) => name
    .toLowerCase()
    .replaceAll('&', 'and')
    .replaceAll(RegExp(r'[^a-z]'), '')
    .replaceAll('and', '');
