// Sales analysis: billed sales pivoted by one or two dimensions.

double _number(Object? value) {
  if (value is num) return value.toDouble();
  if (value is String) return double.tryParse(value) ?? 0;
  return 0;
}

/// One row or column heading of the pivot.
class AnalysisHeading {
  const AnalysisHeading({
    required this.key,
    required this.label,
    this.fromDate,
    this.toDate,
  });

  factory AnalysisHeading.fromJson(Map<String, dynamic> json) =>
      AnalysisHeading(
        key: (json['key'] ?? '').toString(),
        label: (json['label'] ?? '').toString(),
        fromDate: json['from_date']?.toString(),
        toDate: json['to_date']?.toString(),
      );

  final String key;
  final String label;
  final String? fromDate;
  final String? toDate;
}

/// The six figures every cell carries.
class AnalysisFigures {
  const AnalysisFigures({
    this.quantity = 0,
    this.taxable = 0,
    this.tax = 0,
    this.net = 0,
    this.invoices = 0,
    this.averageBill,
    this.averageRate,
    this.cost,
    this.margin,
    this.marginPercent,
  });

  factory AnalysisFigures.fromJson(Map<String, dynamic>? json) {
    if (json == null) return const AnalysisFigures();
    return AnalysisFigures(
      quantity: _number(json['quantity']),
      taxable: _number(json['taxable']),
      tax: _number(json['tax']),
      net: _number(json['net']),
      invoices: _number(json['invoices']).round(),
      averageBill:
          json['average_bill'] == null ? null : _number(json['average_bill']),
      averageRate: json['average_rate'] == null
          ? null
          : _number(json['average_rate']),
      cost: json['cost'] == null ? null : _number(json['cost']),
      margin: json['margin'] == null ? null : _number(json['margin']),
      marginPercent: json['margin_percent'] == null
          ? null
          : _number(json['margin_percent']),
    );
  }

  final double quantity;
  final double taxable;
  final double tax;
  final double net;
  final int invoices;
  final double? averageBill;

  /// Taxable value per unit; null when no quantity.
  final double? averageRate;

  /// Cost, margin and margin percent: non-null only when the caller may see
  /// cost and the basis is billed.
  final double? cost;
  final double? margin;
  final double? marginPercent;
}

class AnalysisCell {
  const AnalysisCell({
    required this.row,
    required this.column,
    required this.figures,
  });

  final String row;
  final String column;
  final AnalysisFigures figures;
}

class SalesAnalysis {
  const SalesAnalysis({
    required this.rows,
    required this.columns,
    required this.cells,
    required this.rowTotals,
    required this.columnTotals,
    required this.grandTotal,
    this.previous,
  });

  factory SalesAnalysis.fromJson(Map<String, dynamic> json) {
    List<AnalysisHeading> headings(Object? raw) => [
          for (final Object? item in (raw as List<dynamic>? ?? const []))
            AnalysisHeading.fromJson(item! as Map<String, dynamic>),
        ];
    Map<String, AnalysisFigures> totals(Object? raw) => {
          for (final MapEntry<String, dynamic> e
              in (raw as Map<String, dynamic>? ?? const {}).entries)
            e.key: AnalysisFigures.fromJson(e.value as Map<String, dynamic>?),
        };
    final List<AnalysisCell> cells = [];
    for (final Object? item in (json['cells'] as List<dynamic>? ?? const [])) {
      final Map<String, dynamic> map = item! as Map<String, dynamic>;
      cells.add(AnalysisCell(
        row: (map['row'] ?? '').toString(),
        column: (map['column'] ?? '').toString(),
        figures:
            AnalysisFigures.fromJson(map['figures'] as Map<String, dynamic>?),
      ));
    }
    return SalesAnalysis(
      rows: headings(json['rows']),
      columns: headings(json['columns']),
      cells: cells,
      rowTotals: totals(json['row_totals']),
      columnTotals: totals(json['column_totals']),
      grandTotal: AnalysisFigures.fromJson(
          json['grand_total'] as Map<String, dynamic>?),
      previous: json['previous'] is Map<String, dynamic>
          ? SalesAnalysis.fromJson(json['previous'] as Map<String, dynamic>)
          : null,
    );
  }

  static const SalesAnalysis empty = SalesAnalysis(
    rows: [],
    columns: [],
    cells: [],
    rowTotals: {},
    columnTotals: {},
    grandTotal: AnalysisFigures(),
  );

  final List<AnalysisHeading> rows;
  final List<AnalysisHeading> columns;
  final List<AnalysisCell> cells;
  final Map<String, AnalysisFigures> rowTotals;
  final Map<String, AnalysisFigures> columnTotals;
  final AnalysisFigures grandTotal;

  /// The year before, keyed under this year's keys; null when not asked.
  final SalesAnalysis? previous;

  bool get isEmpty => rows.isEmpty;

  AnalysisFigures? cell(String row, String column) {
    for (final AnalysisCell c in cells) {
      if (c.row == row && c.column == column) return c.figures;
    }
    return null;
  }
}

/// An invoice behind a cell.
class AnalysisInvoice {
  const AnalysisInvoice({
    required this.id,
    required this.invoiceNumber,
    required this.invoiceDate,
    required this.customerId,
    required this.net,
  });

  factory AnalysisInvoice.fromJson(Map<String, dynamic> json) =>
      AnalysisInvoice(
        id: (json['id'] ?? '').toString(),
        invoiceNumber: (json['invoice_number'] ?? '').toString(),
        invoiceDate: (json['invoice_date'] ?? '').toString(),
        customerId: (json['customer_id'] ?? '').toString(),
        net: _number(json['net']),
      );

  final String id;
  final String invoiceNumber;
  final String invoiceDate;
  final String customerId;
  final double net;
}

/// A purchase bill behind a cell of the purchase analysis.
class AnalysisBill {
  const AnalysisBill({
    required this.id,
    required this.invoiceNumber,
    required this.invoiceDate,
    required this.vendorId,
    required this.net,
  });

  factory AnalysisBill.fromJson(Map<String, dynamic> json) => AnalysisBill(
        id: (json['id'] ?? '').toString(),
        invoiceNumber: (json['invoice_number'] ?? '').toString(),
        invoiceDate: (json['invoice_date'] ?? '').toString(),
        vendorId: (json['vendor_id'] ?? '').toString(),
        net: _number(json['net']),
      );

  final String id;
  final String invoiceNumber;
  final String invoiceDate;
  final String vendorId;
  final double net;
}

/// A saved arrangement of a report. `settings` is owned by the desktop.
class ReportLayout {
  const ReportLayout({
    required this.id,
    required this.reportCode,
    required this.name,
    required this.settings,
    this.version = 0,
  });

  factory ReportLayout.fromJson(Map<String, dynamic> json) => ReportLayout(
        id: (json['id'] ?? '').toString(),
        reportCode: (json['report_code'] ?? '').toString(),
        name: (json['name'] ?? '').toString(),
        settings: json['settings'] is Map
            ? Map<String, dynamic>.from(json['settings'] as Map)
            : <String, dynamic>{},
        version: _number(json['version']).round(),
      );

  final String id;
  final String reportCode;
  final String name;
  final Map<String, dynamic> settings;
  final int version;
}

/// One bill's rate for a product, a point of the rate trend.
class RateTrendPoint {
  const RateTrendPoint({
    required this.billId,
    required this.billNumber,
    required this.billDate,
    required this.supplierId,
    required this.supplierName,
    required this.quantity,
    required this.rate,
  });

  factory RateTrendPoint.fromJson(Map<String, dynamic> json) => RateTrendPoint(
        billId: (json['bill_id'] ?? '').toString(),
        billNumber: (json['bill_number'] ?? '').toString(),
        billDate: (json['bill_date'] ?? '').toString(),
        supplierId: (json['supplier_id'] ?? '').toString(),
        supplierName: (json['supplier_name'] ?? '').toString(),
        quantity: _number(json['quantity']),
        rate: _number(json['rate']),
      );

  final String billId;
  final String billNumber;
  final String billDate;
  final String supplierId;
  final String supplierName;
  final double quantity;
  final double rate;
}
