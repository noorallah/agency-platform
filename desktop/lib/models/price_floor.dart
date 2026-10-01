import 'entities.dart';

/// The firm's price-floor policy (backlog 64 row 2): what happens when a sale
/// is priced below a product's minimum selling price, or below its cost.
class PriceFloorSettings {
  const PriceFloorSettings({
    required this.enforcement,
    required this.includeCost,
    required this.isConfigured,
  });

  /// OFF, WARN or BLOCK.
  final String enforcement;

  /// Whether cost is a floor as well as the product's own minimum.
  final bool includeCost;

  /// False while the firm is still on the platform default.
  final bool isConfigured;

  factory PriceFloorSettings.fromJson(Json json) => PriceFloorSettings(
        enforcement: stringValue(json['enforcement']),
        includeCost: boolValue(json['include_cost']),
        isConfigured: boolValue(json['is_configured']),
      );

  Json toJson() => <String, dynamic>{
        'enforcement': enforcement,
        'include_cost': includeCost,
      };
}

/// One line of a document sold below its floor.
class PriceFloorFinding {
  const PriceFloorFinding({
    required this.lineNumber,
    required this.productCode,
    required this.productName,
    required this.netRate,
    required this.floor,
    required this.minimumPrice,
    required this.message,
  });

  final String lineNumber;
  final String productCode;
  final String productName;
  final String netRate;

  /// `minimum` or `cost` -- which floor the line is under.
  final String floor;
  final String minimumPrice;
  final String message;

  factory PriceFloorFinding.fromJson(Json json) => PriceFloorFinding(
        lineNumber: stringValue(json['line_number']),
        productCode: stringValue(json['product_code']),
        productName: stringValue(json['product_name']),
        netRate: stringValue(json['net_rate']),
        floor: stringValue(json['floor']),
        minimumPrice: stringValue(json['minimum_price']),
        message: stringValue(json['message']),
      );
}

/// What the server says about a document's prices before it is approved.
class PriceFloorCheck {
  const PriceFloorCheck({
    required this.enforcement,
    required this.wouldBlock,
    required this.message,
    required this.findings,
  });

  final String enforcement;

  /// True when the firm's policy refuses the document as it stands.
  final bool wouldBlock;
  final String? message;
  final List<PriceFloorFinding> findings;

  factory PriceFloorCheck.fromJson(Json json) => PriceFloorCheck(
        enforcement: stringValue(json['enforcement']),
        wouldBlock: boolValue(json['would_block']),
        message:
            json['message'] == null ? null : stringValue(json['message']),
        findings: (json['findings'] as List? ?? const [])
            .whereType<Map>()
            .map((item) =>
                PriceFloorFinding.fromJson(Map<String, dynamic>.from(item)))
            .toList(),
      );
}

/// One role's ceiling on a discount typed by hand (backlog 64 row 3).
class RoleDiscountLimit {
  const RoleDiscountLimit({
    required this.roleCode,
    required this.maxDiscountPercent,
  });

  final String roleCode;

  /// Percent, 0 to 100, as the server states it.
  final String maxDiscountPercent;

  factory RoleDiscountLimit.fromJson(Json json) => RoleDiscountLimit(
        roleCode: stringValue(json['role_code']),
        maxDiscountPercent: stringValue(json['max_discount_percent']),
      );

  Json toJson() => <String, dynamic>{
        'role_code': roleCode,
        'max_discount_percent': maxDiscountPercent,
      };
}
