// What would be wrong in a GST return, found before it is filed (GST-5).

import 'entities.dart';

/// One thing to fix: a check that failed on one document or on the firm.
class GstFilingCheckRow {
  const GstFilingCheckRow({
    required this.check,
    required this.severity,
    required this.documentType,
    required this.documentId,
    required this.documentNumber,
    required this.documentDate,
    required this.partyName,
    required this.message,
  });

  factory GstFilingCheckRow.fromJson(Json json) => GstFilingCheckRow(
        check: stringValue(json['check']),
        severity: stringValue(json['severity']),
        documentType: stringValue(json['document_type']),
        documentId: json['document_id'] == null
            ? null
            : stringValue(json['document_id']),
        documentNumber: stringValue(json['document_number']),
        documentDate: stringValue(json['document_date']),
        partyName: stringValue(json['party_name']),
        message: stringValue(json['message']),
      );

  final String check;
  final String severity;
  final String documentType;
  final String? documentId;
  final String documentNumber;
  final String documentDate;
  final String partyName;
  final String message;

  bool get isError => severity.toUpperCase() == 'ERROR';

  /// The check in plain words.
  String get checkLabel => switch (check) {
        'GSTIN_INVALID' => 'GSTIN invalid',
        'HSN_MISSING' => 'HSN missing',
        'HSN_SHORT' => 'HSN too short',
        'PLACE_OF_SUPPLY_MISSING' => 'No place of supply',
        'IRN_MISSING' => 'No IRN',
        'CREDIT_NOTE_LATE' => 'Credit note too late',
        'CREDIT_NOTE_ON_CANCELLED_INVOICE' => 'Credit note on cancelled bill',
        _ => check,
      };

  /// The kind of document in plain words.
  String get documentTypeLabel => switch (documentType) {
        'SALES_INVOICE' => 'Sales invoice',
        'CREDIT_NOTE' => 'Credit note',
        'CUSTOMER_DEBIT_NOTE' => 'Debit note',
        'PURCHASE_INVOICE' => 'Purchase invoice',
        'FIRM' => 'Firm',
        _ => documentType,
      };
}

/// The answer of the checks endpoint for one window.
class GstFilingChecks {
  const GstFilingChecks({
    required this.fromDate,
    required this.toDate,
    required this.requiredHsnDigits,
    required this.counts,
    required this.rows,
  });

  factory GstFilingChecks.fromJson(Json json) => GstFilingChecks(
        fromDate: stringValue(json['from_date']),
        toDate: stringValue(json['to_date']),
        requiredHsnDigits: int.tryParse(stringValue(json['required_hsn_digits'])),
        counts: {
          if (json['counts'] is Map)
            for (final MapEntry<dynamic, dynamic> e
                in (json['counts'] as Map).entries)
              '${e.key}': int.tryParse('${e.value}') ?? 0,
        },
        rows: [
          if (json['rows'] is List)
            for (final Object? row in json['rows'] as List)
              GstFilingCheckRow.fromJson(Map<String, dynamic>.from(row as Map)),
        ],
      );

  final String fromDate;
  final String toDate;
  final int? requiredHsnDigits;
  final Map<String, int> counts;
  final List<GstFilingCheckRow> rows;

  int get errors => rows.where((row) => row.isError).length;
  int get warnings => rows.length - errors;
}
