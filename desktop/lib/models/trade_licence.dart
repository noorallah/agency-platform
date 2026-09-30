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

/// The firm's licence-check policy (backlog 54): what a missing or lapsed
/// licence does to a sale, and to a purchase.
///
/// `GET`/`PUT /api/v1/trade-licences/settings`. A purchase only ever warns --
/// the goods a receipt records have already arrived -- so `purchaseEnforcement`
/// is never `BLOCK`; the server refuses a write that tries.
class TradeLicenceSettingsRecord {
  const TradeLicenceSettingsRecord({
    required this.saleEnforcement,
    required this.purchaseEnforcement,
    required this.isConfigured,
  });

  /// OFF, WARN or BLOCK.
  final String saleEnforcement;

  /// OFF or WARN.
  final String purchaseEnforcement;

  /// False until the firm has ever saved this; the values are then the
  /// server's own default of warn on both sides.
  final bool isConfigured;

  factory TradeLicenceSettingsRecord.fromJson(Json json) {
    final String sale = stringValue(json['sale_enforcement']);
    final String purchase = stringValue(json['purchase_enforcement']);
    return TradeLicenceSettingsRecord(
      saleEnforcement: sale.isEmpty ? 'WARN' : sale,
      purchaseEnforcement: purchase.isEmpty ? 'WARN' : purchase,
      isConfigured: boolValue(json['is_configured']),
    );
  }

  Json toJson() => {
        'sale_enforcement': saleEnforcement,
        'purchase_enforcement': purchaseEnforcement,
      };

  TradeLicenceSettingsRecord copyWith({
    String? saleEnforcement,
    String? purchaseEnforcement,
  }) =>
      TradeLicenceSettingsRecord(
        saleEnforcement: saleEnforcement ?? this.saleEnforcement,
        purchaseEnforcement: purchaseEnforcement ?? this.purchaseEnforcement,
        isConfigured: isConfigured,
      );
}

/// One licence a document's lines need and a party does not hold.
class LicenceFindingRecord {
  const LicenceFindingRecord({
    required this.party,
    required this.partyName,
    required this.licenceTypeId,
    required this.licenceTypeName,
    required this.shortfall,
    required this.licenceNumber,
    required this.validFrom,
    required this.validTo,
    required this.lineNumbers,
    required this.productNames,
    required this.message,
  });

  /// CUSTOMER, SELLER or VENDOR.
  final String party;
  final String partyName;
  final String licenceTypeId;
  final String licenceTypeName;

  /// MISSING, EXPIRED or NOT_YET_VALID.
  final String shortfall;

  /// The latest licence of the type the party does hold, where it has one.
  final String licenceNumber;
  final String validFrom;
  final String validTo;
  final List<int> lineNumbers;
  final List<String> productNames;
  final String message;

  factory LicenceFindingRecord.fromJson(Json json) => LicenceFindingRecord(
        party: stringValue(json['party']),
        partyName: stringValue(json['party_name']),
        licenceTypeId: stringValue(json['licence_type_id']),
        licenceTypeName: stringValue(json['licence_type_name']),
        shortfall: stringValue(json['shortfall']),
        licenceNumber: stringValue(json['licence_number']),
        validFrom: stringValue(json['valid_from']),
        validTo: stringValue(json['valid_to']),
        lineNumbers: (json['line_numbers'] as List? ?? const [])
            .map((item) => (item as num).toInt())
            .toList(),
        productNames: stringList(json['product_names']),
        message: stringValue(json['message']),
      );
}

/// What a document's lines need, and what its parties do not hold --
/// `GET /api/v1/trade-licences/check/{document}/{document_id}` (backlog 54).
///
/// The same judgement the approve endpoint makes itself, on the document's
/// own date, so a screen can show it before the call that would be refused.
class LicenceCheckRecord {
  const LicenceCheckRecord({
    required this.direction,
    required this.enforcement,
    required this.on,
    required this.findings,
    required this.wouldBlock,
    required this.message,
  });

  /// SALE or PURCHASE.
  final String direction;

  /// OFF, WARN or BLOCK -- the policy actually applied.
  final String enforcement;

  /// The date the check was judged on.
  final String on;
  final List<LicenceFindingRecord> findings;

  /// True when the firm's policy refuses the document as it stands.
  final bool wouldBlock;

  /// Every finding in one paragraph, or null when there are none.
  final String? message;

  factory LicenceCheckRecord.fromJson(Json json) => LicenceCheckRecord(
        direction: stringValue(json['direction']),
        enforcement: stringValue(json['enforcement']),
        on: stringValue(json['on']),
        findings: (json['findings'] as List? ?? const [])
            .whereType<Map>()
            .map(
              (item) => LicenceFindingRecord.fromJson(
                Map<String, dynamic>.from(item),
              ),
            )
            .toList(),
        wouldBlock: boolValue(json['would_block']),
        message:
            json['message'] == null ? null : stringValue(json['message']),
      );
}
