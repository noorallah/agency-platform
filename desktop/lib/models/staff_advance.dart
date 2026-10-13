import 'entities.dart';

/// One employee's account under Staff Advances, and what he still owes.
///
/// The money fields are kept as the server wrote them (decimal strings), the
/// way the expense models keep theirs.
class StaffEmployee {
  const StaffEmployee({
    required this.accountId,
    required this.code,
    required this.name,
    required this.isActive,
    required this.advanced,
    required this.recovered,
    required this.owes,
  });

  final String accountId;
  final String code;
  final String name;
  final bool isActive;
  final String advanced;
  final String recovered;
  final String owes;

  /// What he owes as a number, for totals and for checking a recovery.
  double get owesValue => double.tryParse(owes) ?? 0;

  /// The name as the list writes it.
  String get label => isActive ? name : '$name (switched off)';

  factory StaffEmployee.fromJson(Json json) => StaffEmployee(
        accountId: stringValue(json['account_id']),
        code: stringValue(json['code']),
        name: stringValue(json['name']),
        isActive: boolValue(json['is_active'], fallback: true),
        advanced: stringValue(json['advanced']),
        recovered: stringValue(json['recovered']),
        owes: stringValue(json['owes']),
      );
}

/// One advance given to an employee, or one recovery from him.
class StaffAdvanceEntry {
  const StaffAdvanceEntry({
    required this.id,
    required this.entryNumber,
    required this.entryDate,
    required this.kind,
    required this.employeeAccountId,
    required this.employeeName,
    required this.otherAccountId,
    required this.otherAccountName,
    required this.otherSide,
    required this.amount,
    required this.narration,
    required this.status,
    required this.cancelReason,
    required this.version,
  });

  final String id;
  final String entryNumber;
  final String entryDate;

  /// `ADVANCE` or `RECOVERY`.
  final String kind;
  final String employeeAccountId;
  final String employeeName;
  final String otherAccountId;
  final String otherAccountName;

  /// `SALARY` or `MONEY`.
  final String otherSide;
  final String amount;
  final String narration;

  /// `POSTED` or `CANCELLED`.
  final String status;
  final String cancelReason;

  /// Sent back as `If-Match` on a cancel.
  final int version;

  bool get isCancelled => status == 'CANCELLED';

  /// What the entry was, in words.
  String get what {
    if (kind == 'ADVANCE') return 'Advance';
    return otherSide == 'SALARY'
        ? 'Recovery from salary'
        : 'Recovery paid back';
  }

  factory StaffAdvanceEntry.fromJson(Json json) => StaffAdvanceEntry(
        id: stringValue(json['id']),
        entryNumber: stringValue(json['entry_number']),
        entryDate: stringValue(json['entry_date']),
        kind: stringValue(json['kind']),
        employeeAccountId: stringValue(json['employee_account_id']),
        employeeName: stringValue(json['employee_name']),
        otherAccountId: stringValue(json['other_account_id']),
        otherAccountName: stringValue(json['other_account_name']),
        otherSide: stringValue(json['other_side']),
        amount: stringValue(json['amount']),
        narration: stringValue(json['narration']),
        status: stringValue(json['status']),
        cancelReason: stringValue(json['cancel_reason']),
        version: int.tryParse(stringValue(json['version'])) ?? 0,
      );
}

/// One ledger account a staff advance form offers.
class StaffAdvanceAccount {
  const StaffAdvanceAccount({
    required this.id,
    required this.code,
    required this.name,
    required this.kind,
  });

  final String id;
  final String code;
  final String name;

  /// `CASH` or `BANK` for a money account; empty for a salary account.
  final String kind;

  String get label => '$code $name'.trim();

  factory StaffAdvanceAccount.fromJson(Json json) => StaffAdvanceAccount(
        id: stringValue(json['id']),
        code: stringValue(json['code']),
        name: stringValue(json['name']),
        kind: stringValue(json['kind']),
      );
}

/// What the forms offer: where money is paid from or paid back into, and the
/// salary accounts a recovery out of salary is charged to.
class StaffAdvanceAccountChoices {
  const StaffAdvanceAccountChoices({
    required this.moneyAccounts,
    required this.salaryAccounts,
  });

  final List<StaffAdvanceAccount> moneyAccounts;
  final List<StaffAdvanceAccount> salaryAccounts;

  factory StaffAdvanceAccountChoices.fromJson(Json json) {
    List<StaffAdvanceAccount> read(dynamic rows) => [
          for (final dynamic row in rows is List ? rows : const [])
            if (row is Map)
              StaffAdvanceAccount.fromJson(Map<String, dynamic>.from(row)),
        ];
    return StaffAdvanceAccountChoices(
      moneyAccounts: read(json['money_accounts']),
      salaryAccounts: read(json['salary_accounts']),
    );
  }
}
