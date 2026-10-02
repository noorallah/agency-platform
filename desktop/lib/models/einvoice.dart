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
    this.invoiceNumber = '',
    this.customerName = '',
    required this.mode,
    required this.status,
    this.irn = '',
    this.acknowledgementNumber = '',
    this.signedQrCode = '',
    this.errorCode = '',
    this.errorMessage = '',
    this.attempts = 0,
    this.cancellationReason = '',
    this.provider = '',
  });

  final String id;
  final String salesInvoiceId;

  /// How it reaches the portal: SANDBOX or OFFLINE (A42).
  final String provider;

  /// What the row is about, so a reference can be matched to a bill.
  final String invoiceNumber;
  final String customerName;

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

  /// The portal refused it; no IRN was issued, so it can be sent again.
  bool get isFailed => status == 'FAILED';
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
        invoiceNumber: stringValue(json['invoice_number']),
        customerName: stringValue(json['customer_name']),
        mode: stringValue(json['mode']),
        status: stringValue(json['status']),
        irn: stringValue(json['irn']),
        acknowledgementNumber: stringValue(json['acknowledgement_number']),
        signedQrCode: stringValue(json['signed_qr_code']),
        errorCode: stringValue(json['error_code']),
        errorMessage: stringValue(json['error_message']),
        attempts: (json['attempts'] as num?)?.toInt() ?? 0,
        cancellationReason: stringValue(json['cancellation_reason']),
        provider: stringValue(json['provider']),
      );
}

/// How a firm's e-invoices reach the portal, and what the server offers.
class EInvoiceSettings {
  const EInvoiceSettings({required this.provider, required this.available});

  final String provider;
  final List<String> available;

  bool get isOffline => provider == 'OFFLINE';

  factory EInvoiceSettings.fromJson(Json json) => EInvoiceSettings(
        provider: stringValue(json['provider']),
        available: json['available'] is List
            ? (json['available'] as List).map((e) => '$e').toList()
            : const <String>[],
      );
}

/// What importing the portal's result file did.
class OfflineEInvoiceImport {
  const OfflineEInvoiceImport({
    this.registered = const [],
    this.failed = const [],
    this.unmatched = const [],
    this.already = const [],
  });

  final List<String> registered;
  final List<String> failed;
  final List<String> unmatched;
  final List<String> already;

  factory OfflineEInvoiceImport.fromJson(Json json) {
    List<String> list(String key) => json[key] is List
        ? (json[key] as List).map((e) => '$e').toList()
        : const <String>[];
    return OfflineEInvoiceImport(
      registered: list('registered'),
      failed: list('failed'),
      unmatched: list('unmatched'),
      already: list('already'),
    );
  }
}

/// What the authority knows about one consignment.
class EWayBillRecord {
  const EWayBillRecord({
    required this.id,
    required this.salesInvoiceId,
    required this.mode,
    required this.status,
    this.deliveryNoteId = '',
    this.enteredByHand = false,
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

  /// Empty where the bill rides on a delivery note no invoice bills.
  final String salesInvoiceId;
  final String deliveryNoteId;

  /// Raised on the portal by hand and only recorded here (A42).
  final bool enteredByHand;
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
    final String suffix = enteredByHand
        ? '  (recorded by hand)'
        : isSandbox
            ? '  (sandbox — nothing filed)'
            : '';
    return validUntil.isEmpty
        ? '$ewayBillNumber$suffix'
        : '$ewayBillNumber  ·  valid to $validUntil$suffix';
  }

  factory EWayBillRecord.fromJson(Json json) => EWayBillRecord(
        id: stringValue(json['id']),
        salesInvoiceId: stringValue(json['sales_invoice_id']),
        deliveryNoteId: stringValue(json['delivery_note_id']),
        enteredByHand: boolValue(json['entered_by_hand']),
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

/// One consignment above the firm's e-way bill limit that has none (77.10).
class EWayBillDue {
  const EWayBillDue({
    required this.documentType,
    required this.documentId,
    required this.number,
    required this.on,
    required this.value,
  });

  /// SALES_INVOICE or DELIVERY_NOTE.
  final String documentType;
  final String documentId;
  final String number;
  final String on;
  final String value;

  bool get isNote => documentType == 'DELIVERY_NOTE';

  String get typeLabel => isNote ? 'Delivery note' : 'Sales invoice';

  factory EWayBillDue.fromJson(Json json) => EWayBillDue(
        documentType: stringValue(json['document_type']),
        documentId: stringValue(json['document_id']),
        number: stringValue(json['number']),
        on: stringValue(json['on']),
        value: stringValue(json['value']),
      );
}

/// The firm's limit, and what is above it without an e-way bill.
class EWayBillDueList {
  const EWayBillDueList({required this.limit, required this.items});

  final String limit;
  final List<EWayBillDue> items;

  factory EWayBillDueList.fromJson(Json json) => EWayBillDueList(
        limit: stringValue(json['limit']),
        items: json['items'] is List
            ? (json['items'] as List)
                .whereType<Map>()
                .map((row) => EWayBillDue.fromJson(Map<String, dynamic>.from(row)))
                .toList()
            : const <EWayBillDue>[],
      );
}
