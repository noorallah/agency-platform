import 'entities.dart';

int _int(dynamic value) => value is num ? value.toInt() : 0;

String _nullable(dynamic value) => value == null ? '' : value.toString();

/// A kind of fixed asset and how it is depreciated (PG-13).
class AssetClass {
  const AssetClass({
    required this.id,
    this.code = '',
    this.name = '',
    this.depreciationMethod = 'SLM',
    this.ratePercent = '',
    this.usefulLifeYears = '',
    this.residualPercent = '5',
    this.itBlockRatePercent = '0',
    this.assetAccountId = '',
    this.accumulatedDepreciationAccountId = '',
    this.depreciationExpenseAccountId = '',
    this.isActive = true,
    this.description = '',
    this.version = 0,
  });

  factory AssetClass.fromJson(Json json) => AssetClass(
        id: stringValue(json['id']),
        code: stringValue(json['code']),
        name: stringValue(json['name']),
        depreciationMethod: stringValue(json['depreciation_method']).isEmpty
            ? 'SLM'
            : stringValue(json['depreciation_method']),
        ratePercent: _nullable(json['rate_percent']),
        usefulLifeYears: _nullable(json['useful_life_years']),
        residualPercent: _nullable(json['residual_percent']),
        itBlockRatePercent: _nullable(json['it_block_rate_percent']),
        assetAccountId: _nullable(json['asset_account_id']),
        accumulatedDepreciationAccountId:
            _nullable(json['accumulated_depreciation_account_id']),
        depreciationExpenseAccountId:
            _nullable(json['depreciation_expense_account_id']),
        isActive: boolValue(json['is_active'], fallback: true),
        description: _nullable(json['description']),
        version: _int(json['version']),
      );

  final String id;
  final String code;
  final String name;

  /// SLM (straight line) or WDV (written down value).
  final String depreciationMethod;
  final String ratePercent;
  final String usefulLifeYears;
  final String residualPercent;
  final String itBlockRatePercent;
  final String assetAccountId;
  final String accumulatedDepreciationAccountId;
  final String depreciationExpenseAccountId;
  final bool isActive;
  final String description;
  final int version;
}

/// One asset on the register (PG-13).
class FixedAsset {
  const FixedAsset({
    required this.id,
    this.assetNumber = '',
    this.name = '',
    this.assetClassId = '',
    this.assetClassCode = '',
    this.assetClassName = '',
    this.purchaseInvoiceNumber = '',
    this.vendorId = '',
    this.acquisitionDate = '',
    this.putToUseDate = '',
    this.quantity = '',
    this.cost = '',
    this.residualValue = '',
    this.openingAccumulatedDepreciation = '',
    this.openingAsOf = '',
    this.openingItWdv = '',
    this.accumulatedDepreciation = '',
    this.netBookValue = '',
    this.depreciatedTo = '',
    this.branchId = '',
    this.location = '',
    this.status = 'ACTIVE',
    this.disposedOn = '',
    this.saleAmount = '',
    this.disposalMethod = '',
    this.disposalReason = '',
    this.disposalGainLoss = '',
    this.remarks = '',
    this.version = 0,
  });

  factory FixedAsset.fromJson(Json json) => FixedAsset(
        id: stringValue(json['id']),
        assetNumber: stringValue(json['asset_number']),
        name: stringValue(json['name']),
        assetClassId: stringValue(json['asset_class_id']),
        assetClassCode: stringValue(json['asset_class_code']),
        assetClassName: stringValue(json['asset_class_name']),
        purchaseInvoiceNumber: _nullable(json['purchase_invoice_number']),
        vendorId: _nullable(json['vendor_id']),
        acquisitionDate: stringValue(json['acquisition_date']),
        putToUseDate: stringValue(json['put_to_use_date']),
        quantity: stringValue(json['quantity']),
        cost: stringValue(json['cost']),
        residualValue: stringValue(json['residual_value']),
        openingAccumulatedDepreciation:
            stringValue(json['opening_accumulated_depreciation']),
        openingAsOf: _nullable(json['opening_as_of']),
        openingItWdv: _nullable(json['opening_it_wdv']),
        accumulatedDepreciation: stringValue(json['accumulated_depreciation']),
        netBookValue: stringValue(json['net_book_value']),
        depreciatedTo: _nullable(json['depreciated_to']),
        branchId: _nullable(json['branch_id']),
        location: _nullable(json['location']),
        status: stringValue(json['status']).isEmpty
            ? 'ACTIVE'
            : stringValue(json['status']),
        disposedOn: _nullable(json['disposed_on']),
        saleAmount: _nullable(json['sale_amount']),
        disposalMethod: _nullable(json['disposal_method']),
        disposalReason: _nullable(json['disposal_reason']),
        disposalGainLoss: _nullable(json['disposal_gain_loss']),
        remarks: _nullable(json['remarks']),
        version: _int(json['version']),
      );

  final String id;
  final String assetNumber;
  final String name;
  final String assetClassId;
  final String assetClassCode;
  final String assetClassName;
  final String purchaseInvoiceNumber;
  final String vendorId;
  final String acquisitionDate;
  final String putToUseDate;
  final String quantity;
  final String cost;
  final String residualValue;
  final String openingAccumulatedDepreciation;
  final String openingAsOf;
  final String openingItWdv;
  final String accumulatedDepreciation;
  final String netBookValue;
  final String depreciatedTo;
  final String branchId;
  final String location;
  final String status;
  final String disposedOn;
  final String saleAmount;
  final String disposalMethod;
  final String disposalReason;
  final String disposalGainLoss;
  final String remarks;
  final int version;

  bool get isActive => status == 'ACTIVE';
  bool get isDisposed => status == 'DISPOSED';
}

/// One span of an asset's depreciation: charged, or projected.
class AssetScheduleEntry {
  const AssetScheduleEntry({
    this.fromDate = '',
    this.toDate = '',
    this.days = 0,
    this.openingBookValue = '',
    this.amount = '',
    this.accumulatedDepreciation = '',
    this.closingBookValue = '',
    this.runNumber = '',
    this.projected = false,
  });

  factory AssetScheduleEntry.fromJson(Json json) => AssetScheduleEntry(
        fromDate: stringValue(json['from_date']),
        toDate: stringValue(json['to_date']),
        days: _int(json['days']),
        openingBookValue: stringValue(json['opening_book_value']),
        amount: stringValue(json['amount']),
        accumulatedDepreciation: stringValue(json['accumulated_depreciation']),
        closingBookValue: stringValue(json['closing_book_value']),
        runNumber: _nullable(json['run_number']),
        projected: json['projected'] == true,
      );

  final String fromDate;
  final String toDate;
  final int days;
  final String openingBookValue;
  final String amount;
  final String accumulatedDepreciation;
  final String closingBookValue;
  final String runNumber;
  final bool projected;
}

/// What has been charged on an asset and what is still to come.
class AssetSchedule {
  const AssetSchedule({
    this.assetNumber = '',
    this.depreciationMethod = '',
    this.cost = '',
    this.residualValue = '',
    this.charged = const [],
    this.projected = const [],
  });

  factory AssetSchedule.fromJson(Json json) => AssetSchedule(
        assetNumber: stringValue(json['asset_number']),
        depreciationMethod: stringValue(json['depreciation_method']),
        cost: stringValue(json['cost']),
        residualValue: stringValue(json['residual_value']),
        charged: _entries(json['charged']),
        projected: _entries(json['projected']),
      );

  static List<AssetScheduleEntry> _entries(dynamic raw) => [
        for (final Object? row in raw as List? ?? const [])
          if (row is Map)
            AssetScheduleEntry.fromJson(Map<String, dynamic>.from(row)),
      ];

  final String assetNumber;
  final String depreciationMethod;
  final String cost;
  final String residualValue;
  final List<AssetScheduleEntry> charged;
  final List<AssetScheduleEntry> projected;
}

/// One asset's charge inside a depreciation run.
class DepreciationRunLine {
  const DepreciationRunLine({
    this.assetNumber = '',
    this.assetName = '',
    this.fromDate = '',
    this.toDate = '',
    this.days = 0,
    this.openingBookValue = '',
    this.amount = '',
  });

  factory DepreciationRunLine.fromJson(Json json) => DepreciationRunLine(
        assetNumber: stringValue(json['asset_number']),
        assetName: stringValue(json['asset_name']),
        fromDate: stringValue(json['from_date']),
        toDate: stringValue(json['to_date']),
        days: _int(json['days']),
        openingBookValue: stringValue(json['opening_book_value']),
        amount: stringValue(json['amount']),
      );

  final String assetNumber;
  final String assetName;
  final String fromDate;
  final String toDate;
  final int days;
  final String openingBookValue;
  final String amount;
}

/// A depreciation run: one journal for a period's charges (PG-13).
class DepreciationRun {
  const DepreciationRun({
    required this.id,
    this.runNumber = '',
    this.runType = 'PERIODIC',
    this.book = 'COMPANIES_ACT',
    this.periodFrom = '',
    this.periodTo = '',
    this.status = 'POSTED',
    this.totalAmount = '',
    this.postedAt = '',
    this.remarks = '',
    this.cancelReason = '',
    this.version = 0,
    this.lines = const [],
  });

  factory DepreciationRun.fromJson(Json json) => DepreciationRun(
        id: stringValue(json['id']),
        runNumber: stringValue(json['run_number']),
        runType: stringValue(json['run_type']).isEmpty
            ? 'PERIODIC'
            : stringValue(json['run_type']),
        book: stringValue(json['book']),
        periodFrom: stringValue(json['period_from']),
        periodTo: stringValue(json['period_to']),
        status: stringValue(json['status']).isEmpty
            ? 'POSTED'
            : stringValue(json['status']),
        totalAmount: stringValue(json['total_amount']),
        postedAt: _nullable(json['posted_at']),
        remarks: _nullable(json['remarks']),
        cancelReason: _nullable(json['cancel_reason']),
        version: _int(json['version']),
        lines: [
          for (final Object? row in json['lines'] as List? ?? const [])
            if (row is Map)
              DepreciationRunLine.fromJson(Map<String, dynamic>.from(row)),
        ],
      );

  final String id;
  final String runNumber;

  /// PERIODIC, or DISPOSAL for the charge a disposal raises.
  final String runType;
  final String book;
  final String periodFrom;
  final String periodTo;

  /// POSTED or CANCELLED.
  final String status;
  final String totalAmount;
  final String postedAt;
  final String remarks;
  final String cancelReason;
  final int version;
  final List<DepreciationRunLine> lines;

  bool get isPosted => status == 'POSTED';
  bool get isCancelled => status == 'CANCELLED';
}

/// One Income-tax block of the schedule.
class ItBlockRow {
  const ItBlockRow({
    this.blockRate = '',
    this.classNames = const [],
    this.openingWdv = '',
    this.additionsFullRate = '',
    this.additionsHalfRate = '',
    this.disposals = '',
    this.depreciation = '',
    this.closingWdv = '',
    this.shortTermCapitalGain = '',
  });

  factory ItBlockRow.fromJson(Json json) => ItBlockRow(
        blockRate: stringValue(json['block_rate']),
        classNames: stringList(json['class_names']),
        openingWdv: stringValue(json['opening_wdv']),
        additionsFullRate: stringValue(json['additions_full_rate']),
        additionsHalfRate: stringValue(json['additions_half_rate']),
        disposals: stringValue(json['disposals']),
        depreciation: stringValue(json['depreciation']),
        closingWdv: stringValue(json['closing_wdv']),
        shortTermCapitalGain: stringValue(json['short_term_capital_gain']),
      );

  final String blockRate;
  final List<String> classNames;
  final String openingWdv;
  final String additionsFullRate;
  final String additionsHalfRate;
  final String disposals;
  final String depreciation;
  final String closingWdv;
  final String shortTermCapitalGain;
}
