import 'entities.dart';

List<T> _listOf<T>(dynamic value, T Function(Json) fromJson) => value is List
    ? value
        .whereType<Map>()
        .map((item) => fromJson(Map<String, dynamic>.from(item)))
        .toList(growable: false)
    : const [];

/// One bank ledger account a statement can be imported against.
class ReconBankAccount {
  const ReconBankAccount({
    required this.id,
    required this.code,
    required this.name,
    required this.unmatchedLines,
    required this.lastStatementDate,
  });

  final String id;
  final String code;
  final String name;
  final int unmatchedLines;
  final String lastStatementDate;

  String get label => code.isEmpty ? name : '$code · $name';

  factory ReconBankAccount.fromJson(Json json) => ReconBankAccount(
        id: stringValue(json['id']),
        code: stringValue(json['code']),
        name: stringValue(json['name']),
        unmatchedLines: (json['unmatched_lines'] as num?)?.toInt() ?? 0,
        lastStatementDate: stringValue(json['last_statement_date']),
      );
}

/// One imported statement.
class BankStatement {
  const BankStatement({
    required this.id,
    required this.name,
    required this.fromDate,
    required this.toDate,
    required this.lineCount,
    required this.matchedCount,
    this.version = 0,
  });

  final String id;
  final String name;
  final String fromDate;
  final String toDate;
  final int lineCount;
  final int matchedCount;
  final int version;

  String get label => '$name ($fromDate to $toDate)';

  factory BankStatement.fromJson(Json json) => BankStatement(
        id: stringValue(json['id']),
        name: stringValue(json['name']),
        fromDate: stringValue(json['from_date']),
        toDate: stringValue(json['to_date']),
        lineCount: (json['line_count'] as num?)?.toInt() ?? 0,
        matchedCount: (json['matched_count'] as num?)?.toInt() ?? 0,
        version: (json['version'] as num?)?.toInt() ?? 0,
      );
}

/// One posting a statement line accounts for.
class MatchedPosting {
  const MatchedPosting({
    required this.glPostingId,
    required this.journalDate,
    required this.referenceNumber,
    required this.description,
    required this.amount,
    required this.matchedHow,
  });

  final String glPostingId;
  final String journalDate;
  final String referenceNumber;
  final String description;
  final String amount;
  final String matchedHow;

  factory MatchedPosting.fromJson(Json json) => MatchedPosting(
        glPostingId: stringValue(json['gl_posting_id']),
        journalDate: stringValue(json['journal_date']),
        referenceNumber: stringValue(json['reference_number']),
        description: stringValue(json['description']),
        amount: stringValue(json['amount']),
        matchedHow: stringValue(json['matched_how']),
      );
}

/// One statement line and what it was matched to.
class BankStatementLine {
  const BankStatementLine({
    required this.id,
    required this.lineNumber,
    required this.lineDate,
    required this.description,
    required this.reference,
    required this.withdrawal,
    required this.deposit,
    required this.balance,
    required this.status,
    required this.matches,
  });

  final String id;
  final int lineNumber;
  final String lineDate;
  final String description;
  final String reference;
  final String withdrawal;
  final String deposit;
  final String balance;

  /// `UNMATCHED` or `MATCHED`.
  final String status;
  final List<MatchedPosting> matches;

  bool get isMatched => status == 'MATCHED';

  /// Money into the bank is positive, money out negative.
  double get signedAmount =>
      (double.tryParse(deposit) ?? 0) - (double.tryParse(withdrawal) ?? 0);

  factory BankStatementLine.fromJson(Json json) => BankStatementLine(
        id: stringValue(json['id']),
        lineNumber: (json['line_number'] as num?)?.toInt() ?? 0,
        lineDate: stringValue(json['line_date']),
        description: stringValue(json['description']),
        reference: stringValue(json['reference']),
        withdrawal: stringValue(json['withdrawal']),
        deposit: stringValue(json['deposit']),
        balance: stringValue(json['balance']),
        status: stringValue(json['status']),
        matches: _listOf(json['matches'], MatchedPosting.fromJson),
      );
}

/// One posting on the bank account the bank has not yet shown.
class BookEntry {
  const BookEntry({
    required this.glPostingId,
    required this.journalDate,
    required this.referenceNumber,
    required this.instrumentReference,
    required this.description,
    required this.amount,
  });

  final String glPostingId;
  final String journalDate;
  final String referenceNumber;
  final String instrumentReference;
  final String description;

  /// Money into the bank is positive, money out negative.
  final String amount;

  double get amountValue => double.tryParse(amount) ?? 0;

  factory BookEntry.fromJson(Json json) => BookEntry(
        glPostingId: stringValue(json['gl_posting_id']),
        journalDate: stringValue(json['journal_date']),
        referenceNumber: stringValue(json['reference_number']),
        instrumentReference: stringValue(json['instrument_reference']),
        description: stringValue(json['description']),
        amount: stringValue(json['amount']),
      );
}

/// What the matcher did.
class AutoMatchResult {
  const AutoMatchResult({required this.matched, required this.leftUnmatched});

  final int matched;
  final int leftUnmatched;

  String get message => '$matched matched; $leftUnmatched left to match.';

  factory AutoMatchResult.fromJson(Json json) => AutoMatchResult(
        matched: (json['matched'] as num?)?.toInt() ?? 0,
        leftUnmatched: (json['left_unmatched'] as num?)?.toInt() ?? 0,
      );
}

/// One item between the books and the bank on the date.
class ReconcilingItem {
  const ReconcilingItem({
    required this.on,
    required this.reference,
    required this.description,
    required this.amount,
  });

  final String on;
  final String reference;
  final String description;
  final String amount;

  factory ReconcilingItem.fromJson(Json json) => ReconcilingItem(
        on: stringValue(json['on']),
        reference: stringValue(json['reference']),
        description: stringValue(json['description']),
        amount: stringValue(json['amount']),
      );
}

/// The bank reconciliation statement as on one date.
class BankReconciliationStatement {
  const BankReconciliationStatement({
    required this.asOn,
    required this.reconciledFrom,
    required this.bookBalance,
    required this.depositsNotCleared,
    required this.depositsNotClearedTotal,
    required this.paymentsNotPresented,
    required this.paymentsNotPresentedTotal,
    required this.bankOnly,
    required this.bankOnlyNet,
    required this.bankBalancePerBooks,
    required this.statementBalance,
    required this.difference,
  });

  final String asOn;
  final String reconciledFrom;
  final String bookBalance;
  final List<ReconcilingItem> depositsNotCleared;
  final String depositsNotClearedTotal;
  final List<ReconcilingItem> paymentsNotPresented;
  final String paymentsNotPresentedTotal;
  final List<ReconcilingItem> bankOnly;
  final String bankOnlyNet;
  final String bankBalancePerBooks;

  /// Empty when no statement balance was printed on or before the date.
  final String statementBalance;

  /// Empty when there is no statement balance to compare with.
  final String difference;

  bool get hasDifference => difference.isNotEmpty;

  /// True when there is a figure to compare and it is not zero.
  bool get isOut => (double.tryParse(difference) ?? 0) != 0;

  factory BankReconciliationStatement.fromJson(Json json) =>
      BankReconciliationStatement(
        asOn: stringValue(json['as_on']),
        reconciledFrom: stringValue(json['reconciled_from']),
        bookBalance: stringValue(json['book_balance']),
        depositsNotCleared:
            _listOf(json['deposits_not_cleared'], ReconcilingItem.fromJson),
        depositsNotClearedTotal:
            stringValue(json['deposits_not_cleared_total']),
        paymentsNotPresented:
            _listOf(json['payments_not_presented'], ReconcilingItem.fromJson),
        paymentsNotPresentedTotal:
            stringValue(json['payments_not_presented_total']),
        bankOnly: _listOf(json['bank_only'], ReconcilingItem.fromJson),
        bankOnlyNet: stringValue(json['bank_only_net']),
        bankBalancePerBooks: stringValue(json['bank_balance_per_books']),
        statementBalance: stringValue(json['statement_balance']),
        difference: stringValue(json['difference']),
      );
}
