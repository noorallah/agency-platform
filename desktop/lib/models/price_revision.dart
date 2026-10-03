import 'entities.dart';

/// One dated set of rates for a product (MST-2). Rows are never edited: new
/// rates are a new row from a later date, and a blank price means "that price
/// is left as it is", so any of the three may be empty.
class PriceRevision {
  const PriceRevision({
    required this.id,
    required this.productId,
    required this.effectiveFrom,
    this.sellingPrice = '',
    this.purchasePrice = '',
    this.mrp = '',
    this.remarks = '',
    this.isCurrent = false,
  });

  final String id;
  final String productId;
  final String effectiveFrom;
  final String sellingPrice;
  final String purchasePrice;
  final String mrp;
  final String remarks;

  /// The row in force today.
  final bool isCurrent;

  factory PriceRevision.fromJson(Json json) => PriceRevision(
        id: stringValue(json['id']),
        productId: stringValue(json['product_id']),
        effectiveFrom: stringValue(json['effective_from']),
        sellingPrice: stringValue(json['selling_price']),
        purchasePrice: stringValue(json['purchase_price']),
        mrp: stringValue(json['mrp']),
        remarks: stringValue(json['remarks']),
        isCurrent: boolValue(json['is_current']),
      );
}
