import 'entities.dart';

/// What a firm prints around a document of one type.
///
/// The statutory spine of a tax invoice is not in here: both parties' GSTINs,
/// the HSN per line, the rate and amount of each tax component, the summary and
/// the total in words are what make it a tax invoice, and a firm that could
/// switch them off could configure itself out of compliance. What a firm owns
/// is the letterhead, the bank block, the terms, the optional columns, how many
/// copies to print and on what paper.
class PrintTemplate {
  const PrintTemplate({
    required this.documentType,
    this.titleText = 'TAX INVOICE',
    this.accentColor = '#0B3D6B',
    this.showBankDetails = true,
    this.bankDetails = '',
    this.terms = '',
    this.declaration = '',
    this.jurisdiction = '',
    this.footerNote = '',
    this.signatoryText = '',
    this.showDiscountColumn = true,
    this.showBatchColumn = false,
    this.showExpiryColumn = false,
    this.copyLabels = const <String>[],
    this.pageSize = 'A4',
    this.marginMm = '12',
    this.isCustomised = false,
  });

  final String documentType;
  final String titleText;
  final String accentColor;
  final bool showBankDetails;
  final String bankDetails;
  final String terms;
  final String declaration;
  final String jurisdiction;
  final String footerNote;
  final String signatoryText;
  final bool showDiscountColumn;
  final bool showBatchColumn;
  final bool showExpiryColumn;

  /// One label per copy, in print order. Empty prints the original alone.
  final List<String> copyLabels;

  final String pageSize;
  final String marginMm;

  /// False where the firm has saved nothing and these are platform defaults.
  final bool isCustomised;

  /// How many copies a print run produces. No labels still means one copy.
  int get copyCount => copyLabels.isEmpty ? 1 : copyLabels.length;

  factory PrintTemplate.fromJson(Json json) => PrintTemplate(
        documentType: stringValue(json['document_type']),
        titleText: stringValue(json['title_text']),
        accentColor: stringValue(json['accent_color']),
        showBankDetails: boolValue(json['show_bank_details'], fallback: true),
        bankDetails: stringValue(json['bank_details']),
        terms: stringValue(json['terms']),
        declaration: stringValue(json['declaration']),
        jurisdiction: stringValue(json['jurisdiction']),
        footerNote: stringValue(json['footer_note']),
        signatoryText: stringValue(json['signatory_text']),
        showDiscountColumn:
            boolValue(json['show_discount_column'], fallback: true),
        showBatchColumn: boolValue(json['show_batch_column']),
        showExpiryColumn: boolValue(json['show_expiry_column']),
        copyLabels: json['copy_labels'] is List
            ? <String>[
                for (final dynamic item in json['copy_labels'] as List)
                  stringValue(item),
              ]
            : const <String>[],
        pageSize: stringValue(json['page_size']).isEmpty
            ? 'A4'
            : stringValue(json['page_size']),
        marginMm: stringValue(json['margin_mm']).isEmpty
            ? '12'
            : stringValue(json['margin_mm']),
        isCustomised: boolValue(json['is_customised']),
      );

  Json toJson() => <String, dynamic>{
        'title_text': titleText,
        'accent_color': accentColor,
        'show_bank_details': showBankDetails,
        'bank_details': bankDetails.isEmpty ? null : bankDetails,
        'terms': terms.isEmpty ? null : terms,
        'declaration': declaration.isEmpty ? null : declaration,
        'jurisdiction': jurisdiction.isEmpty ? null : jurisdiction,
        'footer_note': footerNote.isEmpty ? null : footerNote,
        'signatory_text': signatoryText.isEmpty ? null : signatoryText,
        'show_discount_column': showDiscountColumn,
        'show_batch_column': showBatchColumn,
        'show_expiry_column': showExpiryColumn,
        'copy_labels': copyLabels,
        'page_size': pageSize,
        'margin_mm': marginMm,
      };

  PrintTemplate copyWith({
    String? titleText,
    bool? showBankDetails,
    String? bankDetails,
    String? terms,
    String? declaration,
    String? jurisdiction,
    String? footerNote,
    String? signatoryText,
    bool? showDiscountColumn,
    bool? showBatchColumn,
    bool? showExpiryColumn,
    List<String>? copyLabels,
    String? pageSize,
    String? marginMm,
  }) =>
      PrintTemplate(
        documentType: documentType,
        titleText: titleText ?? this.titleText,
        accentColor: accentColor,
        showBankDetails: showBankDetails ?? this.showBankDetails,
        bankDetails: bankDetails ?? this.bankDetails,
        terms: terms ?? this.terms,
        declaration: declaration ?? this.declaration,
        jurisdiction: jurisdiction ?? this.jurisdiction,
        footerNote: footerNote ?? this.footerNote,
        signatoryText: signatoryText ?? this.signatoryText,
        showDiscountColumn: showDiscountColumn ?? this.showDiscountColumn,
        showBatchColumn: showBatchColumn ?? this.showBatchColumn,
        showExpiryColumn: showExpiryColumn ?? this.showExpiryColumn,
        copyLabels: copyLabels ?? this.copyLabels,
        pageSize: pageSize ?? this.pageSize,
        marginMm: marginMm ?? this.marginMm,
        isCustomised: isCustomised,
      );
}

/// What each copy of an Indian tax invoice is conventionally called.
///
/// A firm can name them anything, but nobody should have to type these to get
/// the ordinary three-copy set.
const List<String> defaultCopyLabels = <String>[
  'ORIGINAL FOR RECIPIENT',
  'DUPLICATE FOR TRANSPORTER',
  'TRIPLICATE FOR SUPPLIER',
  'EXTRA COPY',
];
