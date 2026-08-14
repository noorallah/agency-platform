import 'entities.dart';

/// One product's line on a count sheet.
class PhysicalCountLine {
  const PhysicalCountLine({
    required this.id,
    required this.lineNumber,
    required this.productId,
    required this.batchId,
    required this.expectedQuantity,
    required this.countedQuantity,
    required this.varianceQuantity,
    required this.transactionId,
    required this.remarks,
  });

  final String id;
  final int lineNumber;
  final String productId;
  final String batchId;

  /// What the system thought when the sheet was drawn up.
  ///
  /// Kept for the person reading it afterwards, and deliberately not what the
  /// variance is computed from: stock moves while a warehouse is counted, so
  /// the difference is measured when the sheet is posted.
  final String expectedQuantity;

  /// What was on the shelf. Empty until somebody walks the line, which is how
  /// a half-finished sheet is told apart from one that found nothing.
  final String countedQuantity;
  final String varianceQuantity;
  final String transactionId;
  final String remarks;

  bool get isCounted => countedQuantity.isNotEmpty;

  /// What the count would move, as it stands. Shown while the sheet is still
  /// being filled in, so a fat-fingered digit is visible before it posts.
  String get draftVariance {
    if (!isCounted) return '';
    final double counted = double.tryParse(countedQuantity) ?? 0;
    final double expected = double.tryParse(expectedQuantity) ?? 0;
    final double difference = counted - expected;
    if (difference == 0) return '';
    return difference > 0
        ? '+${difference.toStringAsFixed(4)}'
        : difference.toStringAsFixed(4);
  }

  factory PhysicalCountLine.fromJson(Json json) => PhysicalCountLine(
        id: stringValue(json['id']),
        lineNumber: (json['line_number'] as num?)?.toInt() ?? 0,
        productId: stringValue(json['product_id']),
        batchId: stringValue(json['batch_id']),
        expectedQuantity: stringValue(json['expected_quantity']),
        countedQuantity: stringValue(json['counted_quantity']),
        varianceQuantity: stringValue(json['variance_quantity']),
        transactionId: stringValue(json['transaction_id']),
        remarks: stringValue(json['remarks']),
      );
}

/// A count sheet for one warehouse.
class PhysicalCountSheet {
  const PhysicalCountSheet({
    required this.id,
    required this.branchId,
    required this.warehouseId,
    required this.countNumber,
    required this.countDate,
    required this.status,
    required this.remarks,
    required this.postedAt,
    required this.lines,
  });

  final String id;
  final String branchId;
  final String warehouseId;
  final String countNumber;
  final String countDate;
  final String status;
  final String remarks;
  final String postedAt;
  final List<PhysicalCountLine> lines;

  bool get isDraft => status == 'DRAFT';
  bool get isPosted => status == 'POSTED';

  /// How much of the sheet has been walked, which is what somebody managing a
  /// count actually wants to know.
  int get countedLines => lines.where((line) => line.isCounted).length;

  factory PhysicalCountSheet.fromJson(Json json) {
    final Json d =
        json.containsKey('data') ? Map<String, dynamic>.from(json['data'] as Map) : json;
    final dynamic rows = d['lines'];
    return PhysicalCountSheet(
      id: stringValue(d['id']),
      branchId: stringValue(d['branch_id']),
      warehouseId: stringValue(d['warehouse_id']),
      countNumber: stringValue(d['count_number']),
      countDate: stringValue(d['count_date']),
      status: stringValue(d['status']),
      remarks: stringValue(d['remarks']),
      postedAt: stringValue(d['posted_at']),
      lines: [
        for (final dynamic row in rows is List ? rows : const [])
          if (row is Map) PhysicalCountLine.fromJson(Map<String, dynamic>.from(row)),
      ],
    );
  }
}
