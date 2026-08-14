/// Which optional fields the firm's business profile turns on.
///
/// The server refuses a gated field it has not enabled -- a receipt carrying an
/// expiry date at a firm without `EXPIRY_TRACKING` comes back 403 naming the
/// feature -- and until now the client offered the field anyway, so the first
/// anybody heard of it was a refusal on save.
///
/// **Unknown means allowed.** The set is null before the answer arrives and
/// after a failed call, and every gate reads that as "show it": a configuration
/// gap is not a decision, and hiding fields because a request failed would take
/// working screens away from firms that are entitled to them. This mirrors the
/// rule the module menu already follows.
///
/// It is cosmetic, and deliberately so. The server is the boundary; this only
/// stops somebody typing into a field that cannot be saved.
///
/// **The product form does not use this, on purpose.** It reads the same
/// feature set out of `ProductMetadataRecord`, which it already fetches for
/// categories and attributes in one call. Both come from `resolve_capabilities`
/// firm-wide -- the category only affects which attributes apply, not which
/// features are on -- so the two cannot disagree, and moving the product form
/// onto this class would add an HTTP call to reach the same answer.
class BusinessFeatures {
  const BusinessFeatures(this._codes);

  /// Nothing known yet: everything is offered.
  const BusinessFeatures.unknown() : _codes = null;

  final Set<String>? _codes;

  /// Whether the firm has this feature, defaulting to yes when unknown.
  bool isEnabled(String code) {
    final Set<String>? codes = _codes;
    if (codes == null) return true;
    return codes.contains(code.toUpperCase());
  }

  /// Whether the answer has arrived, for a caller that wants to wait.
  bool get isResolved => _codes != null;

  /// The one-line explanation a disabled field carries.
  ///
  /// It names the feature, because "disabled" without saying by what leaves
  /// somebody guessing at their own configuration.
  String explain(String code) =>
      '$code is not enabled for this firm, so this field cannot be saved.';
}
