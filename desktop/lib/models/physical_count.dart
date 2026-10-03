import 'entities.dart';

/// One product's line on a count sheet.
class PhysicalCountLine {
  const PhysicalCountLine({
    required this.id,
    required this.lineNumber,
    required this.productId,
    this.productCode = '',
    this.productName = '',
    required this.batchId,
    this.storageNodeId = '',
    this.storageNodeCode = '',
    this.storageNodeName = '',
    required this.expectedQuantity,
    required this.countedQuantity,
    required this.varianceQuantity,
    required this.transactionId,
    required this.remarks,
  });

  final String id;
  final int lineNumber;
  final String productId;
  final String productCode;
  final String productName;
  final String batchId;

  /// The storage location (bin, shelf...) the line counts; empty for the
  /// warehouse's unlocated stock. Part of what the line is: the same product
  /// in two bins is two lines, each corrected in its own bin (D-STK-13).
  final String storageNodeId;
  final String storageNodeCode;
  final String storageNodeName;

  /// Where the counter looks: the location's code and name, or "Unlocated"
  /// for stock held in the warehouse without a bin.
  String get locationLabel {
    if (storageNodeId.isEmpty) return 'Unlocated';
    final String label = [storageNodeCode, storageNodeName]
        .where((part) => part.isNotEmpty)
        .join(' - ');
    return label.isEmpty ? storageNodeId : label;
  }

  /// How the line names its product on the sheet: code and name, the id
  /// only when the server sent neither.
  String get productLabel {
    final String label = [productCode, productName]
        .where((part) => part.isNotEmpty)
        .join(' - ');
    return label.isEmpty ? productId : label;
  }

  /// What the system thought when the sheet was drawn up.
  ///
  /// Kept for the person reading it afterwards, and deliberately not what the
  /// variance is computed from: stock moves while a warehouse is counted, so
  /// the difference is measured when the sheet is posted.
  ///
  /// Empty on a blind draft sheet: the server withholds it from the counter
  /// until the sheet is posted (STK-6).
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
        productCode: stringValue(json['product_code']),
        productName: stringValue(json['product_name']),
        batchId: stringValue(json['batch_id']),
        storageNodeId: stringValue(json['storage_node_id']),
        storageNodeCode: stringValue(json['storage_node_code']),
        storageNodeName: stringValue(json['storage_node_name']),
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
    this.warehouseName = '',
    required this.countNumber,
    required this.countDate,
    required this.status,
    required this.remarks,
    required this.postedAt,
    required this.lines,
    this.isBlind = false,
    this.countPlanId = '',
  });

  final String id;
  final String branchId;
  final String warehouseId;

  /// Which warehouse was counted (owner, 2026-09-27).
  final String warehouseName;
  final String countNumber;
  final String countDate;
  final String status;
  final String remarks;
  final String postedAt;
  final List<PhysicalCountLine> lines;

  /// A blind count hides the system quantity until the sheet is posted, so the
  /// counter writes down what is there rather than what is expected.
  final bool isBlind;
  final String countPlanId;

  /// True while the system quantity is being withheld from the counter.
  bool get hidesExpected => isBlind && isDraft;

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
      warehouseName: stringValue(d['warehouse_name']),
      countNumber: stringValue(d['count_number']),
      countDate: stringValue(d['count_date']),
      status: stringValue(d['status']),
      remarks: stringValue(d['remarks']),
      postedAt: stringValue(d['posted_at']),
      isBlind: boolValue(d['is_blind']),
      countPlanId: stringValue(d['count_plan_id']),
      lines: [
        for (final dynamic row in rows is List ? rows : const [])
          if (row is Map) PhysicalCountLine.fromJson(Map<String, dynamic>.from(row)),
      ],
    );
  }
}

/// A standing plan for cycle counting: which stock, how often, blind or not.
class CountPlan {
  const CountPlan({
    required this.id,
    required this.name,
    required this.branchId,
    required this.warehouseId,
    required this.abcClass,
    required this.storageNodeId,
    required this.frequencyDays,
    required this.blind,
    required this.isActive,
    required this.lastCountedOn,
    required this.nextDueOn,
    required this.isDue,
    required this.version,
  });

  final String id;
  final String name;
  final String branchId;
  final String warehouseId;

  /// A, B or C, or empty for every product.
  final String abcClass;
  final String storageNodeId;
  final int frequencyDays;
  final bool blind;
  final bool isActive;
  final String lastCountedOn;
  final String nextDueOn;
  final bool isDue;
  final int version;

  factory CountPlan.fromJson(Json json) => CountPlan(
        id: stringValue(json['id']),
        name: stringValue(json['name']),
        branchId: stringValue(json['branch_id']),
        warehouseId: stringValue(json['warehouse_id']),
        abcClass: stringValue(json['abc_class']),
        storageNodeId: stringValue(json['storage_node_id']),
        frequencyDays: (json['frequency_days'] as num?)?.toInt() ?? 0,
        blind: boolValue(json['blind']),
        isActive: boolValue(json['is_active'], fallback: true),
        lastCountedOn: stringValue(json['last_counted_on']),
        nextDueOn: stringValue(json['next_due_on']),
        isDue: boolValue(json['is_due']),
        version: (json['version'] as num?)?.toInt() ?? 0,
      );
}
