import 'entities.dart';

int _int(dynamic value) => value is num ? value.toInt() : 0;

/// A free-goods scheme a supplier runs: buy so many, get so many free (PG-11).
class SupplierScheme {
  const SupplierScheme({
    required this.id,
    this.vendorId = '',
    this.vendorCode = '',
    this.vendorName = '',
    this.productId = '',
    this.productCode = '',
    this.productName = '',
    this.buyQuantity = '',
    this.freeQuantity = '',
    this.freeProductId = '',
    this.freeProductCode = '',
    this.freeProductName = '',
    this.validFrom = '',
    this.validTo = '',
    this.isActive = true,
    this.notes = '',
    this.label = '',
    this.inForce = false,
    this.version = 0,
  });

  factory SupplierScheme.fromJson(Json json) => SupplierScheme(
        id: stringValue(json['id']),
        vendorId: stringValue(json['vendor_id']),
        vendorCode: stringValue(json['vendor_code']),
        vendorName: stringValue(json['vendor_name']),
        productId: stringValue(json['product_id']),
        productCode: stringValue(json['product_code']),
        productName: stringValue(json['product_name']),
        buyQuantity: stringValue(json['buy_quantity']),
        freeQuantity: stringValue(json['free_quantity']),
        freeProductId: stringValue(json['free_product_id']),
        freeProductCode: stringValue(json['free_product_code']),
        freeProductName: stringValue(json['free_product_name']),
        validFrom: stringValue(json['valid_from']),
        validTo: stringValue(json['valid_to']),
        isActive: json['is_active'] != false,
        notes: stringValue(json['notes']),
        label: stringValue(json['label']),
        inForce: json['in_force'] == true,
        version: _int(json['version']),
      );

  final String id;

  /// Empty when the scheme holds for every supplier.
  final String vendorId;
  final String vendorCode;
  final String vendorName;
  final String productId;
  final String productCode;
  final String productName;
  final String buyQuantity;
  final String freeQuantity;

  /// Empty when the free goods are the same product.
  final String freeProductId;
  final String freeProductCode;
  final String freeProductName;
  final String validFrom;

  /// Empty when the scheme is open-ended.
  final String validTo;
  final bool isActive;
  final String notes;

  /// "10+2": buy ten, get two free.
  final String label;
  final bool inForce;
  final int version;
}
