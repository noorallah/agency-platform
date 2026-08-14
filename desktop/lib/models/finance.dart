import 'entities.dart';

/// One account in the firm's chart of accounts.
class LedgerAccount {
  const LedgerAccount({
    required this.id,
    required this.firmId,
    required this.accountGroupId,
    required this.code,
    required this.name,
    required this.accountType,
    required this.description,
    required this.isBalanceSheet,
    required this.isProfitLoss,
    required this.requiresCostCenter,
    required this.requiresProfitCenter,
    required this.isActive,
  });

  final String id;
  final String firmId;
  final String accountGroupId;
  final String code;
  final String name;
  final String accountType;
  final String description;
  final bool isBalanceSheet;
  final bool isProfitLoss;
  final bool requiresCostCenter;
  final bool requiresProfitCenter;
  final bool isActive;

  factory LedgerAccount.fromJson(Json json) {
    final Json d =
        json.containsKey('data') ? Map<String, dynamic>.from(json['data'] as Map) : json;
    return LedgerAccount(
      id: stringValue(d['id']),
      firmId: stringValue(d['firm_id']),
      accountGroupId: stringValue(d['account_group_id']),
      code: stringValue(d['code']),
      name: stringValue(d['name']),
      accountType: stringValue(d['account_type']),
      description: stringValue(d['description']),
      isBalanceSheet: boolValue(d['is_balance_sheet']),
      isProfitLoss: boolValue(d['is_profit_loss']),
      requiresCostCenter: boolValue(d['requires_cost_center']),
      requiresProfitCenter: boolValue(d['requires_profit_center']),
      isActive: boolValue(d['is_active']),
    );
  }
}

/// A group the chart of accounts hangs accounts from.
class AccountGroup {
  const AccountGroup({
    required this.id,
    required this.code,
    required this.name,
    required this.accountType,
    required this.isActive,
  });

  final String id;
  final String code;
  final String name;
  final String accountType;
  final bool isActive;

  factory AccountGroup.fromJson(Json json) => AccountGroup(
        id: stringValue(json['id']),
        code: stringValue(json['code']),
        name: stringValue(json['name']),
        accountType: stringValue(json['account_type']),
        isActive: boolValue(json['is_active']),
      );
}

/// One accounting period, which is what a trial balance is drawn for.
class AccountingPeriod {
  const AccountingPeriod({
    required this.id,
    required this.financialYearId,
    required this.periodNumber,
    required this.code,
    required this.name,
    required this.startsOn,
    required this.endsOn,
    required this.status,
  });

  final String id;
  final String financialYearId;
  final int periodNumber;
  final String code;
  final String name;
  final String startsOn;
  final String endsOn;
  final String status;

  String get label => '$name  ($startsOn to $endsOn)';

  factory AccountingPeriod.fromJson(Json json) => AccountingPeriod(
        id: stringValue(json['id']),
        financialYearId: stringValue(json['financial_year_id']),
        periodNumber: (json['period_number'] as num?)?.toInt() ?? 0,
        code: stringValue(json['code']),
        name: stringValue(json['name']),
        startsOn: stringValue(json['starts_on']),
        endsOn: stringValue(json['ends_on']),
        status: stringValue(json['status']),
      );
}

/// One account's movement across a period.
class TrialBalanceLine {
  const TrialBalanceLine({
    required this.ledgerAccountId,
    required this.accountCode,
    required this.accountName,
    required this.accountType,
    required this.openingBalance,
    required this.periodDebit,
    required this.periodCredit,
    required this.closingBalance,
  });

  final String ledgerAccountId;
  final String accountCode;
  final String accountName;
  final String accountType;
  final String openingBalance;
  final String periodDebit;
  final String periodCredit;
  final String closingBalance;

  factory TrialBalanceLine.fromJson(Json json) => TrialBalanceLine(
        ledgerAccountId: stringValue(json['ledger_account_id']),
        accountCode: stringValue(json['account_code']),
        accountName: stringValue(json['account_name']),
        accountType: stringValue(json['account_type']),
        openingBalance: stringValue(json['opening_balance']),
        periodDebit: stringValue(json['period_debit']),
        periodCredit: stringValue(json['period_credit']),
        closingBalance: stringValue(json['closing_balance']),
      );
}

/// The trial balance for one period.
///
/// [isBalanced] is the server's own answer, not something recomputed here.
/// Two places deciding whether the books balance is two places that can
/// disagree, and the one with the ledger in front of it should win.
class TrialBalanceReport {
  const TrialBalanceReport({
    required this.accountingPeriodId,
    required this.generatedAt,
    required this.lines,
    required this.totalDebit,
    required this.totalCredit,
    required this.isBalanced,
  });

  final String accountingPeriodId;
  final String generatedAt;
  final List<TrialBalanceLine> lines;
  final String totalDebit;
  final String totalCredit;
  final bool isBalanced;

  factory TrialBalanceReport.fromJson(Json json) {
    final Json d =
        json.containsKey('data') ? Map<String, dynamic>.from(json['data'] as Map) : json;
    final dynamic lines = d['lines'];
    return TrialBalanceReport(
      accountingPeriodId: stringValue(d['accounting_period_id']),
      generatedAt: stringValue(d['generated_at']),
      lines: [
        for (final dynamic line in lines is List ? lines : const [])
          if (line is Map) TrialBalanceLine.fromJson(Map<String, dynamic>.from(line)),
      ],
      totalDebit: stringValue(d['total_debit']),
      totalCredit: stringValue(d['total_credit']),
      isBalanced: boolValue(d['is_balanced']),
    );
  }

  static const TrialBalanceReport empty = TrialBalanceReport(
    accountingPeriodId: '',
    generatedAt: '',
    lines: [],
    totalDebit: '0',
    totalCredit: '0',
    isBalanced: true,
  );
}
