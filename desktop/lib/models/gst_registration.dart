import 'entities.dart';

/// One GSTIN the firm files returns under: its own, or a branch's.
class GstRegistration {
  const GstRegistration({
    required this.gstin,
    required this.stateCode,
    required this.isFirm,
    this.branchNames = const [],
  });

  final String gstin;
  final String stateCode;
  final bool isFirm;
  final List<String> branchNames;

  /// How the picker names it: the firm's own, or the branches it covers.
  String get label {
    if (isFirm) return '$gstin (firm)';
    return branchNames.isEmpty ? gstin : '$gstin (${branchNames.join(', ')})';
  }

  factory GstRegistration.fromJson(Json json) => GstRegistration(
        gstin: stringValue(json['gstin']),
        stateCode: stringValue(json['state_code']),
        isFirm: boolValue(json['is_firm']),
        branchNames: stringList(json['branch_names']),
      );
}
