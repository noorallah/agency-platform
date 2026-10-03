import 'entities.dart';

/// The tax rule that decided one document line's tax (GST-8), read off a
/// line's JSON. Both keys are absent or null when no rule matched, and are
/// never sent back: the server forbids unknown keys on a write.
class LineTaxRule {
  const LineTaxRule({this.code, this.version});

  final String? code;
  final int? version;

  factory LineTaxRule.fromJson(Json? json) {
    final String code = stringValue(json?['tax_rule_code']);
    return LineTaxRule(
      code: code.isEmpty ? null : code,
      version: (json?['tax_rule_version'] as num?)?.toInt(),
    );
  }

  /// `Tax rule: GST18 (v2)`; empty when no rule is recorded.
  String get label => code == null
      ? ''
      : 'Tax rule: $code${version == null ? '' : ' (v$version)'}';
}
