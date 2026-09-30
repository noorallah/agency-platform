import 'entities.dart';

/// One licence type a firm trades under -- Drug Licence, FSSAI, Shop Act and
/// the like. Firm-scoped, so two firms may shape the same trade differently.
class TradeLicenceTypeRecord {
  const TradeLicenceTypeRecord({
    required this.id,
    required this.version,
    required this.code,
    required this.name,
    required this.formNumbers,
    required this.expires,
    required this.isActive,
    required this.description,
  });

  final String id;
  final int version;
  final String code;
  final String name;
  final String formNumbers;
  final bool expires;
  final bool isActive;
  final String description;

  factory TradeLicenceTypeRecord.fromJson(Json json) => TradeLicenceTypeRecord(
        id: stringValue(json['id']),
        version: (json['version'] as num?)?.toInt() ?? 0,
        code: stringValue(json['code']),
        name: stringValue(json['name']),
        formNumbers: stringValue(json['form_numbers']),
        expires: boolValue(json['expires'], fallback: true),
        isActive: boolValue(json['is_active'], fallback: true),
        description: stringValue(json['description']),
      );
}

/// One recorded licence -- the firm's own, or one held by a customer or a
/// vendor -- with where it stands today.
///
/// `standing` and `daysToExpiry` are derived by the server on every read and
/// never stored, so nothing here writes them back.
class TradeLicenceRecord {
  const TradeLicenceRecord({
    required this.id,
    required this.version,
    required this.licenceTypeId,
    required this.licenceTypeCode,
    required this.licenceTypeName,
    required this.holderType,
    required this.branchId,
    required this.customerId,
    required this.vendorId,
    required this.holderName,
    required this.licenceNumber,
    required this.issuedBy,
    required this.validFrom,
    required this.validTo,
    required this.premises,
    required this.remarks,
    required this.standing,
    required this.daysToExpiry,
  });

  final String id;
  final int version;
  final String licenceTypeId;
  final String licenceTypeCode;
  final String licenceTypeName;

  /// FIRM, CUSTOMER or VENDOR.
  final String holderType;
  final String branchId;
  final String customerId;
  final String vendorId;

  /// The branch (or "Firm"), customer or vendor this licence belongs to,
  /// named once by the server so a list across holders needs no second
  /// lookup.
  final String holderName;
  final String licenceNumber;
  final String issuedBy;

  /// ISO dates ('' when not recorded), matching `FieldKind.date`'s format.
  final String validFrom;
  final String validTo;
  final String premises;
  final String remarks;

  /// VALID, EXPIRING, EXPIRED, NOT_YET_VALID or NO_EXPIRY_RECORDED --
  /// `LicenceStanding` on the server.
  final String standing;

  /// Negative once a licence has run out; null with no valid-to recorded.
  final int? daysToExpiry;

  factory TradeLicenceRecord.fromJson(Json json) => TradeLicenceRecord(
        id: stringValue(json['id']),
        version: (json['version'] as num?)?.toInt() ?? 0,
        licenceTypeId: stringValue(json['licence_type_id']),
        licenceTypeCode: stringValue(json['licence_type_code']),
        licenceTypeName: stringValue(json['licence_type_name']),
        holderType: stringValue(json['holder_type']),
        branchId: stringValue(json['branch_id']),
        customerId: stringValue(json['customer_id']),
        vendorId: stringValue(json['vendor_id']),
        holderName: stringValue(json['holder_name']),
        licenceNumber: stringValue(json['licence_number']),
        issuedBy: stringValue(json['issued_by']),
        validFrom: stringValue(json['valid_from']),
        validTo: stringValue(json['valid_to']),
        premises: stringValue(json['premises']),
        remarks: stringValue(json['remarks']),
        standing: stringValue(json['standing']),
        daysToExpiry: (json['days_to_expiry'] as num?)?.toInt(),
      );
}
