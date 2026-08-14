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

/// One account's balance as at a period end.
class BalanceSheetLine {
  const BalanceSheetLine({
    required this.ledgerAccountId,
    required this.accountCode,
    required this.accountName,
    required this.accountType,
    required this.amount,
  });

  final String ledgerAccountId;
  final String accountCode;
  final String accountName;
  final String accountType;
  final String amount;

  factory BalanceSheetLine.fromJson(Json json) => BalanceSheetLine(
        ledgerAccountId: stringValue(json['ledger_account_id']),
        accountCode: stringValue(json['account_code']),
        accountName: stringValue(json['account_name']),
        accountType: stringValue(json['account_type']),
        amount: stringValue(json['amount']),
      );
}

/// The balance sheet as at one period end.
///
/// The two earnings figures are computed rather than accounts: nothing in this
/// ledger posts a year-end closing entry, so income and expense accounts
/// accumulate and their net is the firm's earnings. Both are already inside
/// [totalEquity].
class BalanceSheetReport {
  const BalanceSheetReport({
    required this.accountingPeriodId,
    required this.financialYearId,
    required this.generatedAt,
    required this.assets,
    required this.liabilities,
    required this.equity,
    required this.totalAssets,
    required this.totalLiabilities,
    required this.totalEquity,
    required this.retainedEarningsBroughtForward,
    required this.resultForTheYear,
    required this.isBalanced,
  });

  final String accountingPeriodId;
  final String financialYearId;
  final String generatedAt;
  final List<BalanceSheetLine> assets;
  final List<BalanceSheetLine> liabilities;
  final List<BalanceSheetLine> equity;
  final String totalAssets;
  final String totalLiabilities;
  final String totalEquity;
  final String retainedEarningsBroughtForward;
  final String resultForTheYear;

  /// Whether the sheet balances, as the server reported it.
  ///
  /// Carried through rather than recomputed, for the same reason the trial
  /// balance's verdict is.
  final bool isBalanced;

  bool get isEmpty => assets.isEmpty && liabilities.isEmpty && equity.isEmpty;

  factory BalanceSheetReport.fromJson(Json json) {
    final Json d =
        json.containsKey('data') ? Map<String, dynamic>.from(json['data'] as Map) : json;
    List<BalanceSheetLine> section(String key) {
      final dynamic value = d[key];
      return [
        for (final dynamic line in value is List ? value : const [])
          if (line is Map) BalanceSheetLine.fromJson(Map<String, dynamic>.from(line)),
      ];
    }

    return BalanceSheetReport(
      accountingPeriodId: stringValue(d['accounting_period_id']),
      financialYearId: stringValue(d['financial_year_id']),
      generatedAt: stringValue(d['generated_at']),
      assets: section('assets'),
      liabilities: section('liabilities'),
      equity: section('equity'),
      totalAssets: stringValue(d['total_assets']),
      totalLiabilities: stringValue(d['total_liabilities']),
      totalEquity: stringValue(d['total_equity']),
      retainedEarningsBroughtForward:
          stringValue(d['retained_earnings_brought_forward']),
      resultForTheYear: stringValue(d['result_for_the_year']),
      isBalanced: boolValue(d['is_balanced']),
    );
  }

  static const BalanceSheetReport empty = BalanceSheetReport(
    accountingPeriodId: '',
    financialYearId: '',
    generatedAt: '',
    assets: [],
    liabilities: [],
    equity: [],
    totalAssets: '0.00',
    totalLiabilities: '0.00',
    totalEquity: '0.00',
    retainedEarningsBroughtForward: '0.00',
    resultForTheYear: '0.00',
    isBalanced: true,
  );
}

/// One income or expense account's contribution to the result.
///
/// Both figures are the account's own movement in its natural direction, so a
/// positive number always means "this much income" or "this much cost",
/// whichever section the line is in. A contra account such as sales returns
/// runs the other way and reports negative, which is what it does to the
/// result.
class ProfitLossLine {
  const ProfitLossLine({
    required this.ledgerAccountId,
    required this.accountCode,
    required this.accountName,
    required this.accountType,
    required this.periodAmount,
    required this.yearToDateAmount,
  });

  final String ledgerAccountId;
  final String accountCode;
  final String accountName;
  final String accountType;
  final String periodAmount;
  final String yearToDateAmount;

  factory ProfitLossLine.fromJson(Json json) => ProfitLossLine(
        ledgerAccountId: stringValue(json['ledger_account_id']),
        accountCode: stringValue(json['account_code']),
        accountName: stringValue(json['account_name']),
        accountType: stringValue(json['account_type']),
        periodAmount: stringValue(json['period_amount']),
        yearToDateAmount: stringValue(json['year_to_date_amount']),
      );
}

/// The profit and loss for one period, and for the year it belongs to.
///
/// Two columns, because one on its own is the wrong answer half the time: a
/// month is what somebody asks about, and the year to date is what tells them
/// whether the month was normal. June 2026 in the seeded firm is exactly that
/// case -- a loss of 2,657.46 inside a year that is 5,086.46 ahead.
class ProfitLossReport {
  const ProfitLossReport({
    required this.accountingPeriodId,
    required this.financialYearId,
    required this.generatedAt,
    required this.income,
    required this.expenses,
    required this.totalIncome,
    required this.totalExpense,
    required this.netProfit,
    required this.yearToDateIncome,
    required this.yearToDateExpense,
    required this.yearToDateNetProfit,
  });

  final String accountingPeriodId;
  final String financialYearId;
  final String generatedAt;
  final List<ProfitLossLine> income;
  final List<ProfitLossLine> expenses;
  final String totalIncome;
  final String totalExpense;
  final String netProfit;
  final String yearToDateIncome;
  final String yearToDateExpense;
  final String yearToDateNetProfit;

  bool get isEmpty => income.isEmpty && expenses.isEmpty;

  factory ProfitLossReport.fromJson(Json json) {
    final Json d =
        json.containsKey('data') ? Map<String, dynamic>.from(json['data'] as Map) : json;
    List<ProfitLossLine> section(String key) {
      final dynamic value = d[key];
      return [
        for (final dynamic line in value is List ? value : const [])
          if (line is Map) ProfitLossLine.fromJson(Map<String, dynamic>.from(line)),
      ];
    }

    return ProfitLossReport(
      accountingPeriodId: stringValue(d['accounting_period_id']),
      financialYearId: stringValue(d['financial_year_id']),
      generatedAt: stringValue(d['generated_at']),
      income: section('income'),
      expenses: section('expenses'),
      totalIncome: stringValue(d['total_income']),
      totalExpense: stringValue(d['total_expense']),
      netProfit: stringValue(d['net_profit']),
      yearToDateIncome: stringValue(d['year_to_date_income']),
      yearToDateExpense: stringValue(d['year_to_date_expense']),
      yearToDateNetProfit: stringValue(d['year_to_date_net_profit']),
    );
  }

  static const ProfitLossReport empty = ProfitLossReport(
    accountingPeriodId: '',
    financialYearId: '',
    generatedAt: '',
    income: [],
    expenses: [],
    totalIncome: '0.00',
    totalExpense: '0.00',
    netProfit: '0.00',
    yearToDateIncome: '0.00',
    yearToDateExpense: '0.00',
    yearToDateNetProfit: '0.00',
  );
}

/// One movement on an account statement, with the balance it left behind.
class GeneralLedgerLine {
  const GeneralLedgerLine({
    required this.journalEntryId,
    required this.journalDate,
    required this.referenceNumber,
    required this.description,
    required this.debitAmount,
    required this.creditAmount,
    required this.runningBalance,
  });

  final String journalEntryId;
  final String journalDate;
  final String referenceNumber;
  final String description;
  final String debitAmount;
  final String creditAmount;

  /// The balance after this movement, as the server ran it.
  ///
  /// Accumulated there rather than here because it starts from the opening
  /// balance and depends on which side the account increases on -- a client
  /// adding the column up itself is a second opinion about the ledger.
  final String runningBalance;

  factory GeneralLedgerLine.fromJson(Json json) => GeneralLedgerLine(
        journalEntryId: stringValue(json['journal_entry_id']),
        journalDate: stringValue(json['journal_date']),
        referenceNumber: stringValue(json['reference_number']),
        description: stringValue(json['description']),
        debitAmount: stringValue(json['debit_amount']),
        creditAmount: stringValue(json['credit_amount']),
        runningBalance: stringValue(json['running_balance']),
      );
}

/// One account's statement for one period: what it opened at, what moved it,
/// and what it closed at.
class GeneralLedgerReport {
  const GeneralLedgerReport({
    required this.ledgerAccountId,
    required this.accountCode,
    required this.accountName,
    required this.accountType,
    required this.accountingPeriodId,
    required this.openingBalance,
    required this.totalDebit,
    required this.totalCredit,
    required this.closingBalance,
    required this.lines,
  });

  final String ledgerAccountId;
  final String accountCode;
  final String accountName;
  final String accountType;
  final String accountingPeriodId;
  final String openingBalance;
  final String totalDebit;
  final String totalCredit;
  final String closingBalance;
  final List<GeneralLedgerLine> lines;

  /// Whether the account was quiet rather than empty.
  ///
  /// The difference matters on screen: no movement and no balance means there
  /// is nothing to see, while no movement against a carried balance means the
  /// account sat still holding money.
  bool get carriesABalance =>
      lines.isEmpty && (double.tryParse(openingBalance) ?? 0) != 0;

  factory GeneralLedgerReport.fromJson(Json json) {
    final Json d =
        json.containsKey('data') ? Map<String, dynamic>.from(json['data'] as Map) : json;
    final dynamic lines = d['lines'];
    return GeneralLedgerReport(
      ledgerAccountId: stringValue(d['ledger_account_id']),
      accountCode: stringValue(d['account_code']),
      accountName: stringValue(d['account_name']),
      accountType: stringValue(d['account_type']),
      accountingPeriodId: stringValue(d['accounting_period_id']),
      openingBalance: stringValue(d['opening_balance']),
      totalDebit: stringValue(d['total_debit']),
      totalCredit: stringValue(d['total_credit']),
      closingBalance: stringValue(d['closing_balance']),
      lines: [
        for (final dynamic line in lines is List ? lines : const [])
          if (line is Map) GeneralLedgerLine.fromJson(Map<String, dynamic>.from(line)),
      ],
    );
  }

  static const GeneralLedgerReport empty = GeneralLedgerReport(
    ledgerAccountId: '',
    accountCode: '',
    accountName: '',
    accountType: '',
    accountingPeriodId: '',
    openingBalance: '0.00',
    totalDebit: '0.00',
    totalCredit: '0.00',
    closingBalance: '0.00',
    lines: [],
  );
}

/// One line of a journal entry: an amount on one side of one account.
class JournalLine {
  const JournalLine({
    required this.ledgerAccountId,
    required this.lineNumber,
    required this.debitAmount,
    required this.creditAmount,
    required this.description,
  });

  final String ledgerAccountId;
  final int lineNumber;
  final String debitAmount;
  final String creditAmount;
  final String description;

  factory JournalLine.fromJson(Json json) => JournalLine(
        ledgerAccountId: stringValue(json['ledger_account_id']),
        lineNumber: (json['line_number'] as num?)?.toInt() ?? 0,
        debitAmount: stringValue(json['debit_amount']),
        creditAmount: stringValue(json['credit_amount']),
        description: stringValue(json['description']),
      );
}

/// A journal entry, drafted or posted.
class JournalEntry {
  const JournalEntry({
    required this.id,
    required this.journalTypeId,
    required this.voucherTypeId,
    required this.accountingPeriodId,
    required this.journalDate,
    required this.referenceNumber,
    required this.description,
    required this.status,
    required this.postedAt,
    required this.totalDebit,
    required this.totalCredit,
    required this.isBalanced,
    required this.sourceModule,
    required this.reversalOfId,
    required this.lines,
  });

  final String id;
  final String journalTypeId;
  final String voucherTypeId;
  final String accountingPeriodId;
  final String journalDate;
  final String referenceNumber;
  final String description;
  final String status;
  final String postedAt;
  final String totalDebit;
  final String totalCredit;
  final bool isBalanced;

  /// Which module raised it, when a document did rather than a person.
  final String sourceModule;
  final String reversalOfId;
  final List<JournalLine> lines;

  bool get isDraft => status == 'DRAFT';
  bool get isPosted => status == 'POSTED';

  /// Whether a person wrote it. Entries a document posted are not editable
  /// here, and saying which raised it is more use than hiding the fact.
  bool get isManual => sourceModule.isEmpty;

  factory JournalEntry.fromJson(Json json) {
    final Json d =
        json.containsKey('data') ? Map<String, dynamic>.from(json['data'] as Map) : json;
    final dynamic lines = d['lines'];
    return JournalEntry(
      id: stringValue(d['id']),
      journalTypeId: stringValue(d['journal_type_id']),
      voucherTypeId: stringValue(d['voucher_type_id']),
      accountingPeriodId: stringValue(d['accounting_period_id']),
      journalDate: stringValue(d['journal_date']),
      referenceNumber: stringValue(d['reference_number']),
      description: stringValue(d['description']),
      status: stringValue(d['status']),
      postedAt: stringValue(d['posted_at']),
      totalDebit: stringValue(d['total_debit']),
      totalCredit: stringValue(d['total_credit']),
      isBalanced: boolValue(d['is_balanced']),
      sourceModule: stringValue(d['source_module']),
      reversalOfId: stringValue(d['reversal_of_id']),
      lines: [
        for (final dynamic line in lines is List ? lines : const [])
          if (line is Map) JournalLine.fromJson(Map<String, dynamic>.from(line)),
      ],
    );
  }
}

/// A journal or voucher type, which every entry has to name.
class FinanceTypeRef {
  const FinanceTypeRef({required this.id, required this.code, required this.name});

  final String id;
  final String code;
  final String name;

  String get label => code.isEmpty ? name : '$code — $name';

  factory FinanceTypeRef.fromJson(Json json) => FinanceTypeRef(
        id: stringValue(json['id']),
        code: stringValue(json['code']),
        name: stringValue(json['name']),
      );
}
