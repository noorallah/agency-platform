import 'entities.dart';

/// How goods travel, by the code the server stores (SG-5).
const Map<String, String> kTransportModes = {
  'ROAD': 'Road',
  'RAIL': 'Rail',
  'AIR': 'Air',
  'SHIP': 'Ship',
};

/// The name a person reads for a stored mode code; blank stays blank.
String transportModeLabel(String code) => kTransportModes[code] ?? code;

/// How a delivery note's freight is settled, by the code the server stores.
const Map<String, String> kFreightTerms = {
  'PAID': 'Paid',
  'TO_PAY': 'To pay',
  'TO_BE_BILLED': 'To be billed',
};

/// The name a person reads for a stored freight-terms code.
String freightTermsLabel(String code) => kFreightTerms[code] ?? code;

/// A carrier the firm dispatches with (SG-5).
class TransporterRecord {
  const TransporterRecord({
    required this.id,
    required this.name,
    required this.gstin,
    required this.transporterRef,
    required this.phone,
    required this.defaultMode,
    required this.isActive,
  });

  final String id;
  final String name;
  final String gstin;
  final String transporterRef;
  final String phone;
  final String defaultMode;
  final bool isActive;

  factory TransporterRecord.fromJson(Json json) => TransporterRecord(
        id: stringValue(json['id']),
        name: stringValue(json['name']),
        gstin: stringValue(json['gstin']),
        transporterRef: stringValue(json['transporter_ref']),
        phone: stringValue(json['phone']),
        defaultMode: stringValue(json['default_mode']),
        isActive: boolValue(json['is_active'], fallback: true),
      );
}
