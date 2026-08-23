import 'entities.dart';

/// One person who belongs to the firm the request is scoped to.
///
/// Read from `GET /api/v1/firm-members`, whose only gate is membership of the
/// firm. Three screens needed this list and no two could share one: assigning
/// a route read it behind `TERRITORY_ASSIGN_SALESMEN`, agreeing a commission
/// rate behind `COMMISSION_VIEW`, and the sales-order form -- which records
/// which salesman took a phone order -- holds neither. A firm's own directory
/// of names is not a privilege; acting on a person is what needs one.
class FirmMember {
  const FirmMember({
    required this.userId,
    required this.fullName,
    this.email = '',
  });

  final String userId;
  final String fullName;
  final String email;

  /// What to show when there is a row to label.
  String get label => fullName.isEmpty ? (email.isEmpty ? userId : email) : fullName;

  factory FirmMember.fromJson(Json json) => FirmMember(
        userId: stringValue(json['user_id']),
        fullName: stringValue(json['full_name']),
        email: stringValue(json['email']),
      );
}
