import 'entities.dart';

/// One component of a kit or combo pack (STK-15): a product and how many of
/// it go into one kit.
class KitComponent {
  const KitComponent({
    required this.componentProductId,
    this.componentCode = '',
    this.componentName = '',
    this.quantity = '',
    this.trackBatch = false,
  });

  final String componentProductId;
  final String componentCode;
  final String componentName;
  final String quantity;

  /// Kept in batches: breaking a kit puts it back into one (D-UI-85).
  final bool trackBatch;

  String get label =>
      componentCode.isEmpty ? componentName : '$componentCode - $componentName';

  factory KitComponent.fromJson(Json json) => KitComponent(
        componentProductId: stringValue(json['component_product_id']),
        componentCode: stringValue(json['component_code']),
        componentName: stringValue(json['component_name']),
        quantity: stringValue(json['quantity']),
        trackBatch: json['track_batch'] == true,
      );
}
