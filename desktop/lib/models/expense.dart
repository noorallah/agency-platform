import 'entities.dart';

/// Money the firm spent that no document raised: rent, fuel, salaries.
///
/// Recorded after the money left, so it is posted when it is saved; a mistake
/// is cancelled -- a mirror journal takes it back -- rather than edited.
class Expense {
  const Expense({
    required this.id,
    required this.expenseNumber,
    required this.expenseDate,
    required this.expenseAccountCode,
    required this.expenseAccountName,
    required this.paidFromAccountName,
    required this.amount,
    required this.payee,
    required this.reference,
    required this.narration,
    required this.status,
    required this.journalEntryId,
    required this.cancelReason,
    required this.version,
  });

  final String id;
  final String expenseNumber;
  final String expenseDate;
  final String expenseAccountCode;
  final String expenseAccountName;
  final String paidFromAccountName;
  final String amount;
  final String payee;
  final String reference;
  final String narration;
  final String status;

  /// The journal this wrote. Every expense has one: recording and posting
  /// are one act.
  final String journalEntryId;
  final String cancelReason;

  /// Sent back as `If-Match` on a cancel, so one made from a stale row is
  /// refused rather than applied to a record somebody changed since.
  final int version;

  bool get isCancelled => status == 'CANCELLED';

  /// The expense account as the grid names it: code and name.
  String get expenseAccount => '$expenseAccountCode $expenseAccountName'.trim();

  factory Expense.fromJson(Json json) {
    final Json d = json.containsKey('data') && json['data'] is Map
        ? Map<String, dynamic>.from(json['data'] as Map)
        : json;
    return Expense(
      id: stringValue(d['id']),
      expenseNumber: stringValue(d['expense_number']),
      expenseDate: stringValue(d['expense_date']),
      expenseAccountCode: stringValue(d['expense_account_code']),
      expenseAccountName: stringValue(d['expense_account_name']),
      paidFromAccountName: stringValue(d['paid_from_account_name']),
      amount: stringValue(d['amount']),
      payee: stringValue(d['payee']),
      reference: stringValue(d['reference']),
      narration: stringValue(d['narration']),
      status: stringValue(d['status']),
      journalEntryId: stringValue(d['journal_entry_id']),
      cancelReason: stringValue(d['cancel_reason']),
      version: int.tryParse(stringValue(d['version'])) ?? 0,
    );
  }
}

/// One ledger account the expense form offers.
class ExpenseAccountOption {
  const ExpenseAccountOption({
    required this.id,
    required this.code,
    required this.name,
  });

  final String id;
  final String code;
  final String name;

  String get label => '$code $name'.trim();

  factory ExpenseAccountOption.fromJson(Json json) => ExpenseAccountOption(
        id: stringValue(json['id']),
        code: stringValue(json['code']),
        name: stringValue(json['name']),
      );
}

/// What the expense form offers: what the money was spent on, and where it
/// came from.
class ExpenseAccountChoices {
  const ExpenseAccountChoices({
    required this.expenseAccounts,
    required this.paidFromAccounts,
  });

  final List<ExpenseAccountOption> expenseAccounts;
  final List<ExpenseAccountOption> paidFromAccounts;

  factory ExpenseAccountChoices.fromJson(Json json) {
    List<ExpenseAccountOption> read(dynamic rows) => [
          for (final dynamic row in rows is List ? rows : const [])
            if (row is Map)
              ExpenseAccountOption.fromJson(Map<String, dynamic>.from(row)),
        ];
    return ExpenseAccountChoices(
      expenseAccounts: read(json['expense_accounts']),
      paidFromAccounts: read(json['paid_from_accounts']),
    );
  }
}
