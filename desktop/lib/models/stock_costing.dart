import 'entities.dart';

/// How a firm costs its stock (L2 step 9): at the running average, or each
/// purchase by its own lot from [switchedOn] onwards. The switch is one way.
class LotSettings {
  const LotSettings({
    required this.costingMethod,
    this.switchedOn,
    this.allowBillingWithoutStock = false,
    this.version = 0,
  });

  factory LotSettings.fromJson(Json json) => LotSettings(
        costingMethod: stringValue(json['costing_method']),
        switchedOn: json['switched_on'] == null
            ? null
            : stringValue(json['switched_on']),
        allowBillingWithoutStock:
            boolValue(json['allow_billing_without_stock']),
        version: json['version'] is int ? json['version'] as int : 0,
      );

  /// `AVERAGE` or `BY_LOT`.
  final String costingMethod;

  /// The day the firm went by lot, `YYYY-MM-DD`; null while on Average.
  final String? switchedOn;

  /// Whether a bill may go out when no lot holds the stock; only meaningful
  /// by lot.
  final bool allowBillingWithoutStock;
  final int version;

  bool get byLot => costingMethod == 'BY_LOT';
}

/// What switching to by lot on [on] would do, before it is done: the lots it
/// would make from the stock on hand, and every reason it would be refused.
class LotSwitchPreview {
  const LotSwitchPreview({
    required this.on,
    required this.suggestedOn,
    required this.items,
    required this.lots,
    required this.quantity,
    required this.stockValue,
    required this.refusals,
  });

  factory LotSwitchPreview.fromJson(Json json) => LotSwitchPreview(
        on: stringValue(json['on']),
        suggestedOn: stringValue(json['suggested_on']),
        items: json['items'] is int ? json['items'] as int : 0,
        lots: json['lots'] is int ? json['lots'] as int : 0,
        quantity: stringValue(json['quantity']),
        stockValue: stringValue(json['stock_value']),
        refusals: stringList(json['refusals']),
      );

  final String on;

  /// The first day of the current financial year, where a switch is cleanest.
  final String suggestedOn;
  final int items;
  final int lots;

  /// Decimals, as the server states them.
  final String quantity;
  final String stockValue;
  final List<String> refusals;
}
