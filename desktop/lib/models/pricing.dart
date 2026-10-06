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
    this.vendorId = '',
    this.vendorName = '',
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

  /// A supplier's list: what they charge the firm (BUY-3).
  final String vendorId;
  final String vendorName;

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
    if (vendorId.isNotEmpty) {
      return vendorName.isEmpty ? 'One supplier' : 'Supplier: $vendorName';
    }
    return 'Everyone';
  }

  /// How many different products carry a rate. A product with quantity
  /// breaks has several rows and is still one product.
  int get productCount => items.map((i) => i.productId).toSet().length;

  /// The grid's count: products, and the rate rows too once breaks make
  /// them differ ("2 (5 rates)").
  String get itemsLabel => items.length == productCount
      ? '$productCount'
      : '$productCount (${items.length} rates)';

  /// How long it stands, read as a person would say it.
  String get windowLabel => effectiveTo.isEmpty
      ? 'from $effectiveFrom'
      : '$effectiveFrom to $effectiveTo';

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
        vendorId: stringValue(json['vendor_id']),
        vendorName: stringValue(json['vendor_name']),
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
    this.minQuantity = '0',
    this.rate = '',
  });

  final String id;
  final String productId;
  final String productCode;
  final String productName;

  /// The quantity this rate starts at. Zero is the ordinary rate; a higher
  /// figure is a break, and the highest one at or below the line's quantity
  /// wins — so a list holding 0, 50 and 200 prices a line of 120 at the 50.
  final String minQuantity;
  final String discountPercent;

  /// An optional fixed price. Blank means the item is a rate off the
  /// product's price, as before; a figure here is the price itself.
  final String rate;

  String get label =>
      productCode.isEmpty ? productId : '$productCode  $productName';

  factory PriceListItemRecord.fromJson(Json json) => PriceListItemRecord(
        id: stringValue(json['id']),
        productId: stringValue(json['product_id']),
        productCode: stringValue(json['product_code']),
        productName: stringValue(json['product_name']),
        minQuantity: stringValue(json['min_quantity']),
        discountPercent: stringValue(json['discount_percent']),
        rate: stringValue(json['rate']),
      );
}

/// A named price level -- "Dealer", "Retail" -- a customer or a customer group
/// can be put on, and a product carries one rate per level.
class PriceLevelRecord {
  const PriceLevelRecord({
    required this.id,
    required this.code,
    required this.name,
    this.sortOrder = 0,
    this.isActive = true,
    this.version = 0,
  });

  final String id;
  final String code;
  final String name;
  final int sortOrder;
  final bool isActive;
  final int version;

  String get label => name.isEmpty ? code : name;

  factory PriceLevelRecord.fromJson(Json json) => PriceLevelRecord(
        id: stringValue(json['id']),
        code: stringValue(json['code']),
        name: stringValue(json['name']),
        sortOrder: (json['sort_order'] as num?)?.toInt() ?? 0,
        isActive: json['is_active'] as bool? ?? true,
        version: (json['version'] as num?)?.toInt() ?? 0,
      );
}

/// One product's rate at one level.
class ProductLevelRate {
  const ProductLevelRate({
    required this.priceLevelId,
    required this.rate,
    this.priceLevelCode = '',
    this.priceLevelName = '',
  });

  final String priceLevelId;
  final String priceLevelCode;
  final String priceLevelName;
  final String rate;

  factory ProductLevelRate.fromJson(Json json) => ProductLevelRate(
        priceLevelId: stringValue(json['price_level_id']),
        priceLevelCode: stringValue(json['price_level_code']),
        priceLevelName: stringValue(json['price_level_name']),
        rate: stringValue(json['rate']),
      );
}

/// The price the server would charge one product for a customer, and where it
/// came from: `PRICE_LIST`, `PRICE_LEVEL` or `PRODUCT`.
class UnitPriceQuote {
  const UnitPriceQuote({
    required this.productId,
    required this.unitPrice,
    required this.source,
  });

  final String productId;
  final String unitPrice;
  final String source;

  /// How the source is worded on screen.
  String get sourceLabel => switch (source) {
        'PRICE_LIST' => 'Price list',
        'PRICE_LEVEL' => 'Dealer level',
        _ => 'Product price',
      };

  factory UnitPriceQuote.fromJson(Json json) => UnitPriceQuote(
        productId: stringValue(json['product_id']),
        unitPrice: stringValue(json['unit_price']),
        source: stringValue(json['source']),
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
    this.requiresCoupon = false,
    this.maxRedemptions,
    this.maxRedemptionsPerCustomer,
    this.maxBenefitAmount = '',
    this.remainingBenefitAmount = '',
    this.benefitAmountClaimed = '',
    this.maxFreeQuantity = '',
    this.remainingFreeQuantity = '',
    this.freeQuantityClaimed = '',
    this.effectiveFrom = '',
    this.effectiveTo = '',
    this.versionNumber = 1,
    this.principalId = '',
    this.principalSharePercent = '100',
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

  /// True when the offer applies only to a customer who presents a coupon.
  final bool requiresCoupon;

  /// Null is no limit, which is a different answer from zero.
  final int? maxRedemptions;
  final int? maxRedemptionsPerCustomer;

  /// The scheme's budget in money and in free units, over every revision of
  /// the offer, with what has been claimed and what is left. Empty is no
  /// budget (the `remaining_*` figures are null with it).
  final String maxBenefitAmount;
  final String remainingBenefitAmount;
  final String benefitAmountClaimed;
  final String maxFreeQuantity;
  final String remainingFreeQuantity;
  final String freeQuantityClaimed;
  final String effectiveFrom;
  final String effectiveTo;

  /// The offer's published revision, which is not the concurrency counter.
  final int versionNumber;

  /// The principal funding the scheme (SEL-11); empty for the firm's own
  /// offer. [principalSharePercent] is the part of the cost they bear.
  final String principalId;
  final String principalSharePercent;
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
        requiresCoupon: boolValue(json['requires_coupon']),
        maxRedemptions: (json['max_redemptions'] as num?)?.toInt(),
        maxRedemptionsPerCustomer:
            (json['max_redemptions_per_customer'] as num?)?.toInt(),
        maxBenefitAmount: stringValue(json['max_benefit_amount']),
        remainingBenefitAmount: stringValue(json['remaining_benefit_amount']),
        benefitAmountClaimed: stringValue(json['benefit_amount_claimed']),
        maxFreeQuantity: stringValue(json['max_free_quantity']),
        remainingFreeQuantity: stringValue(json['remaining_free_quantity']),
        freeQuantityClaimed: stringValue(json['free_quantity_claimed']),
        effectiveFrom: stringValue(json['effective_from']),
        effectiveTo: stringValue(json['effective_to']),
        versionNumber: (json['version_number'] as num?)?.toInt() ?? 1,
        principalId: stringValue(json['principal_id']),
        principalSharePercent: stringValue(json['principal_share_percent']).isEmpty
            ? '100'
            : stringValue(json['principal_share_percent']),
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
    this.valueDate = '',
    this.valueList = const <String>[],
    this.valueLabel = '',
  });

  final String id;
  final int sequence;
  final String fieldKey;
  final String operator;
  final String valueText;
  final String valueNumber;

  /// `YYYY-MM-DD`, for a condition on the transaction date.
  final String valueDate;

  /// The values of an `IN` / `NOT_IN` (any number) or a `BETWEEN` (exactly
  /// two, low then high): the server's `value_json`.
  final List<String> valueList;

  /// What the id in [valueText] names ("MILK — Milk"), as the server resolved
  /// it; empty for a field that is not an id or an id that did not resolve.
  final String valueLabel;

  factory PromotionConditionRecord.fromJson(Json json) =>
      PromotionConditionRecord(
        id: stringValue(json['id']),
        sequence: (json['sequence'] as num?)?.toInt() ?? 1,
        fieldKey: stringValue(json['field_key']),
        operator: stringValue(json['operator']),
        valueText: stringValue(json['value_text']),
        valueNumber: stringValue(json['value_number']),
        valueDate: stringValue(json['value_date']),
        valueList: json['value_json'] is List
            ? (json['value_json'] as List)
                .map((item) => stringValue(item))
                .toList()
            : const <String>[],
        valueLabel: stringValue(json['value_label']),
      );

  /// Sends exactly the value the operator reads and nothing else: a list for
  /// `IN`/`NOT_IN`/`BETWEEN` (`value_json`), none for `EXISTS`/`NOT_EXISTS`,
  /// otherwise the one typed value that is filled in. The server refuses an
  /// `IN` with no list and a `BETWEEN` without two bounds.
  Json toJson() {
    final Json body = <String, dynamic>{
      'sequence': sequence,
      'field_key': fieldKey,
      'operator': operator,
    };
    if (promotionUnaryOperators.contains(operator)) return body;
    if (promotionListOperators.contains(operator) || operator == 'BETWEEN') {
      body['value_json'] = <Object>[
        for (final String item in valueList)
          operator == 'BETWEEN' ? (num.tryParse(item.trim()) ?? item) : item,
      ];
      return body;
    }
    if (valueText.trim().isNotEmpty) body['value_text'] = valueText.trim();
    if (valueNumber.trim().isNotEmpty) {
      body['value_number'] = valueNumber.trim();
    }
    if (valueDate.trim().isNotEmpty) body['value_date'] = valueDate.trim();
    return body;
  }
}

/// Operators that compare against a list of values.
const Set<String> promotionListOperators = <String>{'IN', 'NOT_IN'};

/// Operators that take no value at all.
const Set<String> promotionUnaryOperators = <String>{'EXISTS', 'NOT_EXISTS'};

/// The two documents that ask for promotions, and so the only values a
/// `transaction_type` condition can ever match.
const Map<String, String> promotionTransactionTypeLabels = <String, String>{
  'SALES_ORDER': 'Sales order',
  'SALES_QUOTATION': 'Quotation',
};

/// What each condition field is called on a screen.
const Map<String, String> promotionFieldLabels = <String, String>{
  'product_id': 'Product',
  'product_category_id': 'Product category',
  'product_type': 'Product type',
  'customer_id': 'Customer',
  'territory_id': 'Territory',
  'route_id': 'Route',
  'customer_group_id': 'Customer group',
  'branch_id': 'Branch',
  'salesman_id': 'Salesman',
  'transaction_type': 'Document type',
  'transaction_date': 'Document date',
  'line_quantity': 'Quantity on the line',
  'line_gross': 'Line value',
  'document_gross': 'Order value',
  'weekday': 'Days of the week',
  'time_of_day': 'Time of day',
  'customer_order_count': "Customer's approved orders so far",
  'days_since_last_order': "Days since the customer's last order",
};

/// ISO weekday numbers (1 Monday .. 7 Sunday) and their short names.
const Map<int, String> promotionWeekdayNames = <int, String>{
  1: 'Mon',
  2: 'Tue',
  3: 'Wed',
  4: 'Thu',
  5: 'Fri',
  6: 'Sat',
  7: 'Sun',
};

/// Minutes after midnight as `HH:MM` (1440 reads `24:00`).
String promotionClock(int minutes) =>
    '${(minutes ~/ 60).toString().padLeft(2, '0')}:'
    '${(minutes % 60).toString().padLeft(2, '0')}';

/// `HH:MM` (24-hour) as minutes after midnight, or null when it is not a time.
/// `24:00` is accepted so a window can run to the end of the day.
int? parsePromotionClock(String text) {
  final Match? match = RegExp(r'^(\d{1,2}):(\d{2})$').firstMatch(text.trim());
  if (match == null) return null;
  final int hours = int.parse(match.group(1)!);
  final int minutes = int.parse(match.group(2)!);
  if (minutes > 59 || hours > 24 || (hours == 24 && minutes != 0)) return null;
  return hours * 60 + minutes;
}

/// What each comparison is called on a screen.
const Map<String, String> promotionOperatorLabels = <String, String>{
  'EQUALS': 'is',
  'NOT_EQUALS': 'is not',
  'IN': 'is one of',
  'NOT_IN': 'is none of',
  'BETWEEN': 'is between',
  'EXISTS': 'is set',
  'NOT_EXISTS': 'is not set',
  'GREATER_OR_EQUAL': 'is at least',
  'GREATER_THAN': 'is more than',
  'LESS_OR_EQUAL': 'is at most',
  'LESS_THAN': 'is less than',
};

/// "Quantity on the line is at least 25", not
/// `line_quantity GREATER_OR_EQUAL 25` (BL-31.15). A condition on a product,
/// customer, territory or route shows the name the server resolved
/// ("Product is MILK — Milk"), and the id only when nothing resolved it.
String describePromotionCondition(PromotionConditionRecord condition) {
  final String field =
      promotionFieldLabels[condition.fieldKey] ?? condition.fieldKey;
  final String test =
      promotionOperatorLabels[condition.operator] ?? condition.operator;
  if (promotionUnaryOperators.contains(condition.operator)) {
    return '$field $test';
  }
  final String? eligibility = _eligibilitySummary(condition);
  if (eligibility != null) return eligibility;
  if (condition.fieldKey == 'weekday' && condition.valueList.isNotEmpty) {
    final List<int> days = <int>[
      for (final String item in condition.valueList)
        if (num.tryParse(item) != null) num.parse(item).toInt(),
    ]..sort();
    final String names =
        days.map((day) => promotionWeekdayNames[day] ?? '$day').join(', ');
    return 'Days: $names';
  }
  if (condition.fieldKey == 'time_of_day' &&
      condition.operator == 'BETWEEN' &&
      condition.valueList.length == 2) {
    final num? from = num.tryParse(condition.valueList[0]);
    final num? to = num.tryParse(condition.valueList[1]);
    if (from != null && to != null) {
      return 'Time: ${promotionClock(from.toInt())}-'
          '${promotionClock(to.toInt() + 1)}';
    }
  }
  if (condition.operator == 'BETWEEN' && condition.valueList.length == 2) {
    return '$field $test ${_plainNumber(condition.valueList[0])} and '
        '${_plainNumber(condition.valueList[1])}';
  }
  if (promotionListOperators.contains(condition.operator)) {
    return '$field $test ${condition.valueList.join(', ')}';
  }
  final String value = condition.valueLabel.isNotEmpty
      ? condition.valueLabel
      : condition.valueText.isNotEmpty
          ? (promotionTransactionTypeLabels[condition.valueText] ??
              condition.valueText)
          : condition.valueDate.isNotEmpty
              ? condition.valueDate
              : _plainNumber(condition.valueNumber);
  return '$field $test $value';
}

/// SEL-6: "first order only" / "not billed in 60 days" for the two customer
/// history fields, in the two shapes the presets save; null for anything else.
String? _eligibilitySummary(PromotionConditionRecord condition) {
  final double? value = double.tryParse(condition.valueNumber);
  if (condition.fieldKey == 'customer_order_count' &&
      condition.operator == 'EQUALS' &&
      value == 0) {
    return 'First order only';
  }
  if (condition.fieldKey == 'days_since_last_order' &&
      condition.operator == 'GREATER_OR_EQUAL' &&
      value != null) {
    return 'Not billed in ${_plainNumber(condition.valueNumber)} days';
  }
  return null;
}

/// `25.0000` as `25`, `12.50` as `12.5`: the server's four decimals, trimmed.
String _plainNumber(String value) {
  final double? parsed = double.tryParse(value);
  if (parsed == null) return value;
  final String fixed = parsed.toStringAsFixed(4);
  return fixed.contains('.')
      ? fixed.replaceFirst(RegExp(r'0+$'), '').replaceFirst(RegExp(r'\.$'), '')
      : fixed;
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
    this.freeProductId = '',
    this.maxAmount = '',
    this.multiplier = '',
    this.comboItems = const <ComboItemRecord>[],
  });

  final String id;
  final int sequence;
  final String actionType;

  /// For `COMBO_PRICE`: the products of one set and how many of each. The
  /// price of the set is [amount].
  final List<ComboItemRecord> comboItems;

  /// For `LOYALTY_MULTIPLIER`: how many times the usual points a bill earns
  /// (2 = double). Applied when the bill is approved, not on the document.
  final String multiplier;
  final String percent;

  /// For a percent benefit: the most it may take off the whole document --
  /// "20% off, up to 500" (backlog 60 item 1). Blank is no cap.
  final String maxAmount;
  final String amount;
  final String buyQuantity;
  final String freeQuantity;

  /// For `FREE_PRODUCT`: the product given away.
  final String freeProductId;

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

    final bool isCombo = stringValue(json['action_type']) == 'COMBO_PRICE';
    final Object? rawItems = params['items'];
    return PromotionActionRecord(
      comboItems: isCombo && rawItems is List
          ? <ComboItemRecord>[
              for (final Object? item in rawItems)
                if (item is Map)
                  ComboItemRecord(
                    productId: stringValue(item['product_id']),
                    quantity: stringValue(item['quantity']),
                  ),
            ]
          : const <ComboItemRecord>[],
      id: stringValue(json['id']),
      sequence: (json['sequence'] as num?)?.toInt() ?? 1,
      actionType: stringValue(json['action_type']),
      percent: read('percent'),
      amount: isCombo ? read('price') : read('amount'),
      buyQuantity: read('buy_quantity'),
      freeQuantity: read('free_quantity'),
      freeProductId: read('free_product_id'),
      maxAmount: read('max_amount'),
      multiplier: read('multiplier'),
    );
  }

  Json toJson() => <String, dynamic>{
        'sequence': sequence,
        'action_type': actionType,
        if (percent.trim().isNotEmpty) 'percent': percent.trim(),
        if (amount.trim().isNotEmpty) 'amount': amount.trim(),
        if (buyQuantity.trim().isNotEmpty) 'buy_quantity': buyQuantity.trim(),
        if (freeQuantity.trim().isNotEmpty)
          'free_quantity': freeQuantity.trim(),
        if (freeProductId.trim().isNotEmpty)
          'free_product_id': freeProductId.trim(),
        if (maxAmount.trim().isNotEmpty) 'max_amount': maxAmount.trim(),
        if (multiplier.trim().isNotEmpty) 'multiplier': multiplier.trim(),
        if (actionType == 'COMBO_PRICE')
          'combo_items': [
            for (final ComboItemRecord item in comboItems)
              <String, dynamic>{
                'product_id': item.productId,
                'quantity': item.quantity.trim(),
              },
          ],
      };
}

/// "2x loyalty points" for a bonus-points benefit (`2.00` reads as `2x`).
String bonusPointsLabel(String multiplier) =>
    '${_plainNumber(multiplier)}x loyalty points';

/// One product of a `COMBO_PRICE` set.
class ComboItemRecord {
  const ComboItemRecord({required this.productId, required this.quantity});

  final String productId;
  final String quantity;
}

/// "2 products for 120.00" for a `COMBO_PRICE` benefit.
String comboPriceLabel(int products, String price) =>
    '$products products for $price';

/// "Buy 1, get 1 at 50% off" for a `BUY_X_GET_Y_DISCOUNT` benefit.
String buyXGetYDiscountLabel(String buy, String get, String percent) =>
    'Buy ${_plainNumber(buy)}, get ${_plainNumber(get)} at '
    '${_plainNumber(percent)}% off';

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

/// What one line of a tried document earned.
class PromotionTryLine {
  const PromotionTryLine({
    required this.lineNumber,
    required this.discountAmount,
    required this.freeQuantity,
    required this.offerCodes,
  });

  factory PromotionTryLine.fromJson(Map<String, dynamic> json) =>
      PromotionTryLine(
        lineNumber: (json['line_number'] as num?)?.toInt() ?? 0,
        discountAmount: stringValue(json['discount_amount']),
        freeQuantity: stringValue(json['free_quantity']),
        offerCodes: stringList(json['applied_promotion_codes']),
      );

  final int lineNumber;
  final String discountAmount;
  final String freeQuantity;
  final List<String> offerCodes;
}

/// Goods an offer adds to the document.
class PromotionTryGift {
  const PromotionTryGift({
    required this.productId,
    required this.quantity,
    required this.offerCode,
  });

  factory PromotionTryGift.fromJson(Map<String, dynamic> json) =>
      PromotionTryGift(
        productId: stringValue(json['product_id']),
        quantity: stringValue(json['quantity']),
        offerCode: stringValue(json['promotion_code']),
      );

  final String productId;
  final String quantity;
  final String offerCode;
}

/// Why one offer did or did not apply to the tried document.
class PromotionTryDecision {
  const PromotionTryDecision({
    required this.code,
    required this.priority,
    required this.applied,
    required this.reason,
  });

  factory PromotionTryDecision.fromJson(Map<String, dynamic> json) =>
      PromotionTryDecision(
        code: stringValue(json['code']),
        priority: (json['priority'] as num?)?.toInt() ?? 0,
        applied: json['matched'] == true,
        reason: stringValue(json['reason']),
      );

  final String code;
  final int priority;
  final bool applied;
  final String reason;
}

/// The answer to `POST /api/v1/promotions/simulate`: what a document would
/// earn, and why. Nothing is saved or claimed by asking.
class PromotionTryResult {
  const PromotionTryResult({
    required this.lines,
    required this.billDiscount,
    required this.freightWaived,
    required this.gifts,
    required this.decisions,
  });

  factory PromotionTryResult.fromJson(Map<String, dynamic> json) {
    List<Map<String, dynamic>> maps(String key) => [
          for (final dynamic item in (json[key] as List<dynamic>? ?? const []))
            Map<String, dynamic>.from(item as Map),
        ];
    return PromotionTryResult(
      lines: maps('lines').map(PromotionTryLine.fromJson).toList(),
      billDiscount: stringValue(json['bill_discount_amount']),
      freightWaived: stringValue(json['freight_waived']),
      gifts: maps('gifts').map(PromotionTryGift.fromJson).toList(),
      decisions: maps('decisions').map(PromotionTryDecision.fromJson).toList(),
    );
  }

  final List<PromotionTryLine> lines;
  final String billDiscount;
  final String freightWaived;
  final List<PromotionTryGift> gifts;
  final List<PromotionTryDecision> decisions;

  /// Line discounts, the bill discount and the delivery waived, together.
  double get totalSaved =>
      lines.fold<double>(
          0, (sum, line) => sum + (double.tryParse(line.discountAmount) ?? 0)) +
      (double.tryParse(billDiscount) ?? 0) +
      (double.tryParse(freightWaived) ?? 0);
}
