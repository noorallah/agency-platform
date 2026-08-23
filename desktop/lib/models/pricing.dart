import 'entities.dart';

/// One arrangement a firm has agreed: who pays less, on what, and from when.
///
/// A list holds **rates off the product's price**, not prices of its own, so a
/// firm revises a product's price once and every arrangement built on it
/// follows.
class PriceListRecord {
  const PriceListRecord({
    required this.id,
    required this.code,
    required this.name,
    required this.effectiveFrom,
    this.version = 0,
    this.description = '',
    this.customerId = '',
    this.customerName = '',
    this.territoryId = '',
    this.territoryName = '',
    this.effectiveTo = '',
    this.status = 'ACTIVE',
    this.items = const <PriceListItemRecord>[],
  });

  final String id;

  /// The optimistic-concurrency version this record was read at, sent back as
  /// `If-Match` on save. The rates are replaced by what is sent, so a lost
  /// race costs every rate somebody entered.
  final int version;

  final String code;
  final String name;
  final String description;

  /// One shop. Empty with [territoryId] empty means the whole firm.
  final String customerId;
  final String customerName;

  /// Everyone on a round.
  final String territoryId;
  final String territoryName;

  final String effectiveFrom;
  final String effectiveTo;
  final String status;
  final List<PriceListItemRecord> items;

  /// Who the arrangement is with, in the words a person would use.
  String get scopeLabel {
    if (customerId.isNotEmpty) {
      return customerName.isEmpty ? 'One customer' : customerName;
    }
    if (territoryId.isNotEmpty) {
      return territoryName.isEmpty ? 'One territory' : territoryName;
    }
    return 'Everyone';
  }

  /// How long it stands, read as a person would say it.
  String get windowLabel =>
      effectiveTo.isEmpty ? 'from $effectiveFrom' : '$effectiveFrom to $effectiveTo';

  factory PriceListRecord.fromJson(Json json) => PriceListRecord(
        id: stringValue(json['id']),
        version: (json['version'] as num?)?.toInt() ?? 0,
        code: stringValue(json['code']),
        name: stringValue(json['name']),
        description: stringValue(json['description']),
        customerId: stringValue(json['customer_id']),
        customerName: stringValue(json['customer_name']),
        territoryId: stringValue(json['territory_id']),
        territoryName: stringValue(json['territory_name']),
        effectiveFrom: stringValue(json['effective_from']),
        effectiveTo: stringValue(json['effective_to']),
        status: stringValue(json['status']).isEmpty
            ? 'ACTIVE'
            : stringValue(json['status']),
        items: [
          for (final dynamic item
              in json['items'] is List ? json['items'] as List : const [])
            if (item is Map)
              PriceListItemRecord.fromJson(Map<String, dynamic>.from(item)),
        ],
      );
}

/// One product's rate on a list.
class PriceListItemRecord {
  const PriceListItemRecord({
    required this.productId,
    required this.discountPercent,
    this.id = '',
    this.productCode = '',
    this.productName = '',
  });

  final String id;
  final String productId;
  final String productCode;
  final String productName;
  final String discountPercent;

  String get label =>
      productCode.isEmpty ? productId : '$productCode  $productName';

  factory PriceListItemRecord.fromJson(Json json) => PriceListItemRecord(
        id: stringValue(json['id']),
        productId: stringValue(json['product_id']),
        productCode: stringValue(json['product_code']),
        productName: stringValue(json['product_name']),
        discountPercent: stringValue(json['discount_percent']),
      );
}
