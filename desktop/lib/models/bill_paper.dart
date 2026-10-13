/// Which paper a sales bill needs, as the server judged it for this bill.
///
/// Asked just before printing: a firm on half pages keeps half sheets in the
/// tray, so a full-page bill sent there is cut off.
class BillPaper {
  const BillPaper({
    required this.firmPaper,
    required this.customerPaper,
    required this.paper,
    required this.fitsHalfPage,
    required this.mayChoose,
  });

  /// The firm's own paper: `HALF`, `A4`, `A5` or `THERMAL80`.
  final String firmPaper;

  /// The customer's own paper (`HALF` or `A4`); null unless the firm is on
  /// half pages and this customer has one.
  final String? customerPaper;

  /// What the bill prints on when nobody chooses.
  final String paper;

  /// False on a half-page firm means the bill is too long for half a page.
  final bool fitsHalfPage;

  /// True when the person printing may pick either half or full page.
  final bool mayChoose;

  factory BillPaper.fromJson(Map<String, dynamic> json) {
    final dynamic customer = json['customer_paper'];
    return BillPaper(
      firmPaper: '${json['firm_paper'] ?? ''}',
      customerPaper: customer is String && customer.isNotEmpty ? customer : null,
      paper: '${json['paper'] ?? ''}',
      fitsHalfPage: json['fits_half_page'] != false,
      mayChoose: json['may_choose'] == true,
    );
  }
}
