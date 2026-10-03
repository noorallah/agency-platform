import 'entities.dart';

/// One line of what a supplier sells and at what price (BUY-4). Rows are never
/// edited: a change is a new row from a later date, so `effectiveFrom` is part
/// of the row's identity and `isCurrent` says whether it is in force today.
class SupplierCatalogueRow {
  const SupplierCatalogueRow({
    required this.id,
    required this.vendorId,
    required this.productId,
    required this.productCode,
    required this.productName,
    required this.supplierProductCode,
    required this.supplierProductName,
    required this.unitPrice,
    required this.packSize,
    required this.minimumOrderQuantity,
    required this.leadTimeDays,
    required this.effectiveFrom,
    required this.remarks,
    required this.isCurrent,
  });

  final String id;
  final String vendorId;
  final String productId;
  final String productCode;
  final String productName;
  final String supplierProductCode;
  final String supplierProductName;
  final String unitPrice;
  final String packSize;
  final String minimumOrderQuantity;
  final String leadTimeDays;
  final String effectiveFrom;
  final String remarks;
  final bool isCurrent;

  factory SupplierCatalogueRow.fromJson(Json json) => SupplierCatalogueRow(
        id: stringValue(json['id']),
        vendorId: stringValue(json['vendor_id']),
        productId: stringValue(json['product_id']),
        productCode: stringValue(json['product_code']),
        productName: stringValue(json['product_name']),
        supplierProductCode: stringValue(json['supplier_product_code']),
        supplierProductName: stringValue(json['supplier_product_name']),
        unitPrice: stringValue(json['unit_price']),
        packSize: stringValue(json['pack_size']),
        minimumOrderQuantity: stringValue(json['minimum_order_quantity']),
        leadTimeDays: stringValue(json['lead_time_days']),
        effectiveFrom: stringValue(json['effective_from']),
        remarks: stringValue(json['remarks']),
        isCurrent: boolValue(json['is_current'], fallback: true),
      );
}
