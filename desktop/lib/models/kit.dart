import 'entities.dart';

/// One component of a kit or combo pack (STK-15): a product and how many of
/// it go into one kit.
class KitComponent {
  const KitComponent({
    required this.componentProductId,
    this.componentCode = '',
    this.componentName = '',
    this.quantity = '',
  });

  final String componentProductId;
  final String componentCode;
  final String componentName;
  final String quantity;

  String get label =>
      componentCode.isEmpty ? componentName : '$componentCode - $componentName';

  factory KitComponent.fromJson(Json json) => KitComponent(
        componentProductId: stringValue(json['component_product_id']),
        componentCode: stringValue(json['component_code']),
        componentName: stringValue(json['component_name']),
        quantity: stringValue(json['quantity']),
      );
}
