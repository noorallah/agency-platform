/// The agency's own name, tagline, colour and logo, as the server holds them.
///
/// This is the **customer's** branding, set once by an administrator and read
/// before anybody signs in. The product's own identity is the package's
/// `branding.json` (`BrandingConfig`), which a customer does not edit.
class AgencyBranding {
  const AgencyBranding({
    required this.isSet,
    this.agencyName = '',
    this.tagline = '',
    this.accentColor = '',
    this.hasLogo = false,
    this.version,
  });

  /// False until somebody has given the branding; every other field is then
  /// empty and the screens keep the package's own identity.
  final bool isSet;
  final String agencyName;
  final String tagline;

  /// `#RRGGBB`, or empty when the agency has not chosen one.
  final String accentColor;
  final bool hasLogo;

  /// Changes on every save, including a new logo; sent back as `If-Match`.
  final int? version;

  static const AgencyBranding notSet = AgencyBranding(isSet: false);

  factory AgencyBranding.fromJson(Map<String, dynamic> json) {
    String text(String key) {
      final dynamic raw = json[key];
      return raw is String ? raw.trim() : '';
    }

    final dynamic version = json['version'];
    return AgencyBranding(
      isSet: json['is_set'] == true,
      agencyName: text('agency_name'),
      tagline: text('tagline'),
      accentColor: text('accent_color'),
      hasLogo: json['has_logo'] == true,
      version: version is num ? version.toInt() : null,
    );
  }
}
