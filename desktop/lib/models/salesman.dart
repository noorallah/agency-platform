import 'entities.dart';

/// One entry of the firm's own list of salesmen (P2).
///
/// Read from `GET /api/v1/salesmen`, whose only gate is membership of the
/// firm, like `GET /api/v1/firm-members`: whoever makes a bill must be able
/// to fill its Salesman box. Every `salesman_id` on an order, a bill, a
/// round, a target, a commission rule, a customer's account manager and a
/// promotion holds one of these ids -- **not** a user id. An entry may be
/// tied to a user account ([userId]) or stand alone, for a salesman who
/// never signs in.
class Salesman {
  const Salesman({
    required this.id,
    required this.name,
    this.version = 0,
    this.code = '',
    this.userId = '',
    this.phone = '',
    this.earnsCommission = true,
    this.isActive = true,
    this.notes = '',
  });

  final String id;
  final int version;
  final String code;
  final String name;

  /// The user account this entry stands for; empty for one tied to nobody.
  final String userId;
  final String phone;
  final bool earnsCommission;
  final bool isActive;
  final String notes;

  /// What to show when there is a row to label.
  String get label => name.isEmpty ? (code.isEmpty ? id : code) : name;

  factory Salesman.fromJson(Json json) => Salesman(
        id: stringValue(json['id']),
        version: (json['version'] as num?)?.toInt() ?? 0,
        code: stringValue(json['code']),
        name: stringValue(json['name']),
        userId: stringValue(json['user_id']),
        phone: stringValue(json['phone']),
        earnsCommission: boolValue(json['earns_commission'], fallback: true),
        isActive: boolValue(json['is_active'], fallback: true),
        notes: stringValue(json['notes']),
      );
}

/// What a new document's Salesman box starts on, and why
/// (`GET /api/v1/salesmen/starting-choice`).
///
/// [source] is `USER` (the entry tied to the signed-in user),
/// `ACCOUNT_MANAGER` (the customer's own), `ROUND` (the primary salesman of
/// the customer's round) or `NONE`, with [salesmanId] empty.
class SalesmanStartingChoice {
  const SalesmanStartingChoice({
    this.salesmanId = '',
    this.name = '',
    this.source = 'NONE',
  });

  final String salesmanId;
  final String name;
  final String source;

  /// Whether the answer names anybody.
  bool get isSomebody => salesmanId.isNotEmpty;

  factory SalesmanStartingChoice.fromJson(Json json) => SalesmanStartingChoice(
        salesmanId: stringValue(json['salesman_id']),
        name: stringValue(json['name']),
        source: stringValue(json['source']).isEmpty
            ? 'NONE'
            : stringValue(json['source']),
      );
}
