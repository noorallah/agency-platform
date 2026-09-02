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


/// One offer a firm runs: who it is for, what it gives, and when.
///
/// Unlike a price list, promotions **stack**. Several can apply to one order,
/// in priority order, and each says whether it lets the ones behind it apply
/// too. Percentages compound on what is left, so two ten percent offers take
/// nineteen percent rather than twenty.
class PromotionRecord {
  const PromotionRecord({
    required this.id,
    required this.code,
    required this.name,
    this.version = 0,
    this.description = '',
    this.priority = 100,
    this.status = 'DRAFT',
    this.allowStacking = true,
    this.effectiveFrom = '',
    this.effectiveTo = '',
    this.versionNumber = 1,
    this.conditions = const <PromotionConditionRecord>[],
    this.actions = const <PromotionActionRecord>[],
  });

  final String id;

  /// The concurrency version this was read at, sent back as `If-Match`.
  final int version;

  final String code;
  final String name;
  final String description;

  /// Lowest applies first. Ties break on code, so the order never wobbles.
  final int priority;
  final String status;

  /// False ends the stack: the offers behind this one do not apply.
  final bool allowStacking;
  final String effectiveFrom;
  final String effectiveTo;

  /// The offer's published revision, which is not the concurrency counter.
  final int versionNumber;
  final List<PromotionConditionRecord> conditions;
  final List<PromotionActionRecord> actions;

  factory PromotionRecord.fromJson(Json json) => PromotionRecord(
        id: stringValue(json['id']),
        version: (json['version'] as num?)?.toInt() ?? 0,
        code: stringValue(json['code']),
        name: stringValue(json['name']),
        description: stringValue(json['description']),
        priority: (json['priority'] as num?)?.toInt() ?? 100,
        status: stringValue(json['status']),
        allowStacking: boolValue(json['allow_stacking'], fallback: true),
        effectiveFrom: stringValue(json['effective_from']),
        effectiveTo: stringValue(json['effective_to']),
        versionNumber: (json['version_number'] as num?)?.toInt() ?? 1,
        conditions: json['conditions'] is List
            ? (json['conditions'] as List)
                .whereType<Map>()
                .map((item) => PromotionConditionRecord.fromJson(
                    Map<String, dynamic>.from(item)))
                .toList()
            : const <PromotionConditionRecord>[],
        actions: json['actions'] is List
            ? (json['actions'] as List)
                .whereType<Map>()
                .map((item) => PromotionActionRecord.fromJson(
                    Map<String, dynamic>.from(item)))
                .toList()
            : const <PromotionActionRecord>[],
      );
}

/// One test an order must pass for its promotion to apply.
class PromotionConditionRecord {
  const PromotionConditionRecord({
    required this.fieldKey,
    required this.operator,
    this.id = '',
    this.sequence = 1,
    this.valueText = '',
    this.valueNumber = '',
  });

  final String id;
  final int sequence;
  final String fieldKey;
  final String operator;
  final String valueText;
  final String valueNumber;

  factory PromotionConditionRecord.fromJson(Json json) =>
      PromotionConditionRecord(
        id: stringValue(json['id']),
        sequence: (json['sequence'] as num?)?.toInt() ?? 1,
        fieldKey: stringValue(json['field_key']),
        operator: stringValue(json['operator']),
        valueText: stringValue(json['value_text']),
        valueNumber: stringValue(json['value_number']),
      );

  Json toJson() => <String, dynamic>{
        'sequence': sequence,
        'field_key': fieldKey,
        'operator': operator,
        if (valueText.trim().isNotEmpty) 'value_text': valueText.trim(),
        if (valueNumber.trim().isNotEmpty) 'value_number': valueNumber.trim(),
      };
}

/// One benefit a promotion gives when it applies.
class PromotionActionRecord {
  const PromotionActionRecord({
    required this.actionType,
    this.id = '',
    this.sequence = 1,
    this.percent = '',
    this.amount = '',
    this.buyQuantity = '',
    this.freeQuantity = '',
  });

  final String id;
  final int sequence;
  final String actionType;
  final String percent;
  final String amount;
  final String buyQuantity;
  final String freeQuantity;

  factory PromotionActionRecord.fromJson(Json json) {
    final Map<String, dynamic> params = json['parameters'] is Map
        ? Map<String, dynamic>.from(json['parameters'] as Map)
        : <String, dynamic>{};
    // The server stores every parameter as text, and a value it never set
    // reads back as the string "None" rather than as an absent key.
    String read(String key) {
      final String value = stringValue(params[key]);
      return value == 'None' ? '' : value;
    }

    return PromotionActionRecord(
      id: stringValue(json['id']),
      sequence: (json['sequence'] as num?)?.toInt() ?? 1,
      actionType: stringValue(json['action_type']),
      percent: read('percent'),
      amount: read('amount'),
      buyQuantity: read('buy_quantity'),
      freeQuantity: read('free_quantity'),
    );
  }

  Json toJson() => <String, dynamic>{
        'sequence': sequence,
        'action_type': actionType,
        if (percent.trim().isNotEmpty) 'percent': percent.trim(),
        if (amount.trim().isNotEmpty) 'amount': amount.trim(),
        if (buyQuantity.trim().isNotEmpty) 'buy_quantity': buyQuantity.trim(),
        if (freeQuantity.trim().isNotEmpty) 'free_quantity': freeQuantity.trim(),
      };
}


/// A code a customer presents to claim an offer.
///
/// The benefit, the conditions and the stacking rule all live on the promotion
/// the coupon names. What a coupon adds is that the offer applies only when
/// somebody asks for it by name -- and a limit on how often.
class PromotionCouponRecord {
  const PromotionCouponRecord({
    required this.id,
    required this.promotionId,
    required this.code,
    this.promotionCode = '',
    this.version = 0,
    this.description = '',
    this.status = 'ACTIVE',
    this.maxRedemptions,
    this.maxRedemptionsPerCustomer,
    this.effectiveFrom = '',
    this.effectiveTo = '',
    this.redemptionCount = 0,
  });

  final String id;
  final String promotionId;
  final String promotionCode;
  final String code;
  final String description;
  final String status;
  final int version;

  /// Null is no limit, which is a different answer from zero.
  final int? maxRedemptions;
  final int? maxRedemptionsPerCustomer;
  final String effectiveFrom;
  final String effectiveTo;

  /// What has actually been claimed, so a screen can say how much is left
  /// rather than only what was allowed.
  final int redemptionCount;

  /// How the count reads beside the limit, or just the count when unlimited.
  String get usageLabel => maxRedemptions == null
      ? '$redemptionCount used'
      : '$redemptionCount of $maxRedemptions used';

  factory PromotionCouponRecord.fromJson(Json json) => PromotionCouponRecord(
        id: stringValue(json['id']),
        promotionId: stringValue(json['promotion_id']),
        promotionCode: stringValue(json['promotion_code']),
        code: stringValue(json['code']),
        description: stringValue(json['description']),
        status: stringValue(json['status']),
        version: (json['version'] as num?)?.toInt() ?? 0,
        maxRedemptions: (json['max_redemptions'] as num?)?.toInt(),
        maxRedemptionsPerCustomer:
            (json['max_redemptions_per_customer'] as num?)?.toInt(),
        effectiveFrom: stringValue(json['effective_from']),
        effectiveTo: stringValue(json['effective_to']),
        redemptionCount: (json['redemption_count'] as num?)?.toInt() ?? 0,
      );

  Json toJson() => <String, dynamic>{
        'promotion_id': promotionId,
        'code': code,
        if (description.isNotEmpty) 'description': description,
        'status': status,
        'max_redemptions': maxRedemptions,
        'max_redemptions_per_customer': maxRedemptionsPerCustomer,
        if (effectiveFrom.isNotEmpty) 'effective_from': effectiveFrom,
        if (effectiveTo.isNotEmpty) 'effective_to': effectiveTo,
      };
}
