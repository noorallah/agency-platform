import 'entities.dart';

/// What the tax authority knows about one invoice.
///
/// [mode] is never absent. A SANDBOX registration is a rehearsal: nothing was
/// filed, and the reference means nothing outside this database. Every screen
/// that shows a reference has to show the mode beside it, or somebody
/// eventually presents a rehearsal at a check post.
class EInvoiceRegistrationRecord {
  const EInvoiceRegistrationRecord({
    required this.id,
    required this.salesInvoiceId,
    required this.mode,
    required this.status,
    this.irn = '',
    this.acknowledgementNumber = '',
    this.signedQrCode = '',
    this.errorCode = '',
    this.errorMessage = '',
    this.attempts = 0,
    this.cancellationReason = '',
  });

  final String id;
  final String salesInvoiceId;

  /// SANDBOX or LIVE.
  final String mode;
  final String status;
  final String irn;
  final String acknowledgementNumber;
  final String signedQrCode;
  final String errorCode;
  final String errorMessage;
  final int attempts;
  final String cancellationReason;

  bool get isRegistered => status == 'REGISTERED';
  bool get isSandbox => mode == 'SANDBOX';

  /// What to show where the reference goes, mode included.
  String get referenceLabel {
    if (!isRegistered) return status;
    return isSandbox ? '$irn  (sandbox — nothing filed)' : irn;
  }

  factory EInvoiceRegistrationRecord.fromJson(Json json) =>
      EInvoiceRegistrationRecord(
        id: stringValue(json['id']),
        salesInvoiceId: stringValue(json['sales_invoice_id']),
        mode: stringValue(json['mode']),
        status: stringValue(json['status']),
        irn: stringValue(json['irn']),
        acknowledgementNumber: stringValue(json['acknowledgement_number']),
        signedQrCode: stringValue(json['signed_qr_code']),
        errorCode: stringValue(json['error_code']),
        errorMessage: stringValue(json['error_message']),
        attempts: (json['attempts'] as num?)?.toInt() ?? 0,
        cancellationReason: stringValue(json['cancellation_reason']),
      );
}

/// What the authority knows about one consignment.
class EWayBillRecord {
  const EWayBillRecord({
    required this.id,
    required this.salesInvoiceId,
    required this.mode,
    required this.status,
    this.ewayBillNumber = '',
    this.validUntil = '',
    this.distanceKm = '0',
    this.transportMode = 'ROAD',
    this.transporterId = '',
    this.transporterName = '',
    this.vehicleNumber = '',
    this.errorCode = '',
    this.errorMessage = '',
  });

  final String id;
  final String salesInvoiceId;
  final String mode;
  final String status;
  final String ewayBillNumber;

  /// When the bill stops being valid. The authority decides it from the
  /// distance, so it is shown as given rather than recomputed here.
  final String validUntil;
  final String distanceKm;
  final String transportMode;
  final String transporterId;
  final String transporterName;
  final String vehicleNumber;
  final String errorCode;
  final String errorMessage;

  bool get isGenerated => status == 'GENERATED';
  bool get isSandbox => mode == 'SANDBOX';

  String get referenceLabel {
    if (!isGenerated) return status;
    final String suffix = isSandbox ? '  (sandbox — nothing filed)' : '';
    return validUntil.isEmpty
        ? '$ewayBillNumber$suffix'
        : '$ewayBillNumber  ·  valid to $validUntil$suffix';
  }

  factory EWayBillRecord.fromJson(Json json) => EWayBillRecord(
        id: stringValue(json['id']),
        salesInvoiceId: stringValue(json['sales_invoice_id']),
        mode: stringValue(json['mode']),
        status: stringValue(json['status']),
        ewayBillNumber: stringValue(json['eway_bill_number']),
        validUntil: stringValue(json['valid_until']),
        distanceKm: stringValue(json['distance_km']),
        transportMode: stringValue(json['transport_mode']),
        transporterId: stringValue(json['transporter_id']),
        transporterName: stringValue(json['transporter_name']),
        vehicleNumber: stringValue(json['vehicle_number']),
        errorCode: stringValue(json['error_code']),
        errorMessage: stringValue(json['error_message']),
      );
}
