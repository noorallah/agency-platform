// Write a cheque (F13): one of the firm's own cheques, to a supplier, to a
// customer being refunded, to an expense or to any other account.
//
// Dated today or before it is recorded at once as the payment it is; dated
// ahead it is held and posts nothing until it is presented. Phase 2 only.

import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/security/permission_service.dart';
import '../../models/post_dated_cheque.dart';
import '../../models/settlement.dart';
import '../../models/settlement_direction.dart';
import '../workspace/save_in_dialog.dart';
import 'post_dated_cheque_page.dart' show ChequeDateField;

const String _supplier = 'SUPPLIER';
const String _customer = 'CUSTOMER';
const String _expense = 'EXPENSE';
const String _account = 'ACCOUNT';

/// The right that lets somebody write a cheque to each kind of payee.
const Map<String, String> _writeRight = {
  _supplier: 'PAYMENT_CREATE',
  _customer: 'PAYMENT_CREATE',
  _expense: 'EXPENSE_CREATE',
  _account: 'JOURNAL_POST',
};

const Map<String, String> _kindWords = {
  _supplier: 'Supplier',
  _customer: 'Customer (a refund)',
  _expense: 'Expense account',
  _account: 'Other account',
};

const Map<String, String> _payeeLabels = {
  _supplier: 'Supplier',
  _customer: 'Customer',
  _expense: 'Expense account',
  _account: 'Account',
};

/// What a cheque dated today or before is recorded as, by kind of payee.
const Map<String, String> _recordedAs = {
  _supplier: 'a payment to the supplier',
  _customer: 'a refund to the customer',
  _expense: 'an expense',
  _account: 'a payment voucher',
};

/// Whether [permissions] lets somebody write a cheque to [kind] of payee.
bool mayWriteChequeTo(PermissionService permissions, String kind) =>
    permissions.hasPermission(_writeRight[kind] ?? '');

/// Who a cheque can pay, whichever list the name came from.
class _Payee {
  const _Payee({required this.id, required this.code, required this.name});

  final String id;
  final String code;
  final String name;

  String get label => code.isEmpty ? name : '$code  $name';
}

String _isoDate(DateTime date) => date.toIso8601String().substring(0, 10);

/// Write a cheque. Pops the saved [PostDatedCheque]; stays open with the
/// server's message when it is refused.
class WriteChequeDialog extends StatefulWidget {
  const WriteChequeDialog({
    super.key,
    required this.api,
    required this.permissions,
  });

  final ApiClient api;
  final PermissionService permissions;

  @override
  State<WriteChequeDialog> createState() => _WriteChequeDialogState();
}

class _WriteChequeDialogState extends State<WriteChequeDialog>
    with SaveInDialog {
  final TextEditingController _name = TextEditingController();
  final TextEditingController _amount = TextEditingController();
  final TextEditingController _number = TextEditingController();
  final TextEditingController _narration = TextEditingController();
  DateTime _date = DateTime.now();
  ChequeAccountChoices _choices = const ChequeAccountChoices();
  List<PartyOption>? _suppliers;
  List<PartyOption>? _customers;
  String? _bankId;
  String? _kind;
  _Payee? _payee;

  /// True once the user has typed in the name box, so picking another payee
  /// no longer overwrites it.
  bool _nameTyped = false;
  bool _loading = true;
  bool _loadingParties = false;
  String? _problem;

  List<String> get _kinds => [
        for (final String kind in _kindWords.keys)
          if (mayWriteChequeTo(widget.permissions, kind)) kind,
      ];

  @override
  void initState() {
    super.initState();
    _kind = _kinds.firstOrNull;
    unawaited(_readChoices());
  }

  @override
  void dispose() {
    _name.dispose();
    _amount.dispose();
    _number.dispose();
    _narration.dispose();
    super.dispose();
  }

  Future<void> _readChoices() async {
    try {
      final ChequeAccountChoices choices = await widget.api.chequeAccountChoices();
      if (!mounted) return;
      setState(() {
        _choices = choices;
        if (choices.bankAccounts.length == 1) {
          _bankId = choices.bankAccounts.single.id;
        }
        _loading = false;
      });
      await _readParties();
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        saveError = error.message;
        _loading = false;
      });
    }
  }

  /// Suppliers and customers are read the first time that kind is chosen,
  /// and once.
  Future<void> _readParties() async {
    final String? kind = _kind;
    if (kind != _supplier && kind != _customer) return;
    if ((kind == _supplier ? _suppliers : _customers) != null) return;
    setState(() => _loadingParties = true);
    try {
      final List<PartyOption> parties = await widget.api.settlementParties(
        direction: kind == _supplier
            ? SettlementDirection.payment
            : SettlementDirection.receipt,
      );
      if (!mounted) return;
      setState(() {
        if (kind == _supplier) {
          _suppliers = parties;
        } else {
          _customers = parties;
        }
        _loadingParties = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        saveError = error.message;
        _loadingParties = false;
      });
    }
  }

  /// The people or accounts the chosen kind can pay.
  List<_Payee> get _payees {
    List<_Payee> fromParties(List<PartyOption>? parties) => [
          for (final PartyOption party in parties ?? const <PartyOption>[])
            _Payee(id: party.id, code: party.code, name: party.name),
        ];
    List<_Payee> fromAccounts(List<ChequeAccount> accounts) => [
          for (final ChequeAccount account in accounts)
            _Payee(id: account.id, code: account.code, name: account.name),
        ];
    return switch (_kind) {
      _supplier => fromParties(_suppliers),
      _customer => fromParties(_customers),
      _expense => fromAccounts(_choices.expenseAccounts),
      _account => fromAccounts(_choices.otherAccounts),
      _ => const [],
    };
  }

  void _chooseKind(String? kind) {
    if (kind == null || kind == _kind) return;
    setState(() {
      _kind = kind;
      _payee = null;
      if (!_nameTyped) _name.clear();
    });
    unawaited(_readParties());
  }

  void _choosePayee(_Payee payee) {
    setState(() {
      _payee = payee;
      if (!_nameTyped) _name.text = payee.name;
    });
  }

  bool get _datedAhead => _isoDate(_date).compareTo(_isoDate(DateTime.now())) > 0;

  String get _whatHappens => _datedAhead
      ? 'Dated ahead: it is held and posts nothing until you present it.'
      : 'Dated today or before: it is recorded now as '
          '${_recordedAs[_kind] ?? 'a payment'}.';

  void _save() {
    final String number = _number.text.trim();
    final String amount = _amount.text.trim();
    final double? value = double.tryParse(amount);
    String? problem;
    if (_bankId == null) {
      problem = 'Choose the bank account the cheque is drawn on.';
    } else if (_payee == null) {
      problem = 'Choose who the cheque pays.';
    } else if (number.isEmpty || number.length > 30) {
      problem = 'The cheque number is one to thirty characters.';
    } else if (value == null || value <= 0) {
      problem = 'The amount must be more than zero.';
    }
    setState(() => _problem = problem);
    if (problem != null) return;
    final String payeeKey = switch (_kind) {
      _supplier => 'supplier_id',
      _customer => 'customer_id',
      _ => 'account_id',
    };
    final String name = _name.text.trim();
    final String narration = _narration.text.trim();
    unawaited(saveAndClose<PostDatedCheque>(
      () => widget.api.writeCheque(
        body: <String, dynamic>{
          'bank_account_id': _bankId,
          payeeKey: _payee!.id,
          if (name.isNotEmpty) 'payee_name': name,
          'amount': amount,
          'cheque_number': number,
          'cheque_date': _isoDate(_date),
          if (narration.isNotEmpty) 'narration': narration,
        },
      ),
    ));
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final List<String> kinds = _kinds;
    final bool noBank = !_loading && _choices.bankAccounts.isEmpty;
    return AlertDialog(
      title: const Text('Write a cheque'),
      content: SizedBox(
        width: 560,
        child: _loading
            ? const SizedBox(
                height: 80,
                child: Center(child: CircularProgressIndicator()),
              )
            : SingleChildScrollView(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    saveErrorBanner(),
                    if (_problem != null)
                      Padding(
                        padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                        child: Text(
                          _problem!,
                          key: const ValueKey('cheque-problem'),
                          style: TextStyle(color: theme.colorScheme.error),
                        ),
                      ),
                    if (kinds.isEmpty)
                      const Text(
                        'Writing a cheque needs the right to record a '
                        'payment, an expense or a journal.',
                        key: ValueKey('cheque-no-rights'),
                      )
                    else ...[
                      if (noBank)
                        Padding(
                          padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                          child: Text(
                            'The firm has no bank account to draw a cheque on.',
                            key: const ValueKey('cheque-no-bank'),
                            style: TextStyle(color: theme.colorScheme.error),
                          ),
                        ),
                      DropdownButtonFormField<String>(
                        key: const ValueKey('cheque-bank'),
                        initialValue: _bankId,
                        isExpanded: true,
                        decoration:
                            const InputDecoration(labelText: 'Drawn on'),
                        items: [
                          for (final ChequeAccount bank
                              in _choices.bankAccounts)
                            DropdownMenuItem<String>(
                              value: bank.id,
                              child: Text(bank.label,
                                  overflow: TextOverflow.ellipsis),
                            ),
                        ],
                        onChanged:
                            saving ? null : (id) => setState(() => _bankId = id),
                      ),
                      const SizedBox(height: AppSpacing.md),
                      DropdownButtonFormField<String>(
                        key: const ValueKey('cheque-pays'),
                        initialValue: _kind,
                        isExpanded: true,
                        decoration: const InputDecoration(labelText: 'Pays'),
                        items: [
                          for (final String kind in kinds)
                            DropdownMenuItem<String>(
                              value: kind,
                              child: Text(_kindWords[kind]!),
                            ),
                        ],
                        onChanged: saving ? null : _chooseKind,
                      ),
                      const SizedBox(height: AppSpacing.md),
                      Autocomplete<_Payee>(
                        key: ValueKey('cheque-payee-$_kind'),
                        displayStringForOption: (payee) => payee.label,
                        optionsBuilder: (value) {
                          final String query = value.text.trim().toLowerCase();
                          return _payees.where((payee) =>
                              payee.code.toLowerCase().contains(query) ||
                              payee.name.toLowerCase().contains(query));
                        },
                        onSelected: _choosePayee,
                        fieldViewBuilder: (context, field, node, submit) =>
                            TextFormField(
                          key: const ValueKey('cheque-payee-account'),
                          controller: field,
                          focusNode: node,
                          enabled: !saving,
                          onChanged: (_) {
                            if (_payee != null) setState(() => _payee = null);
                          },
                          decoration: InputDecoration(
                            labelText: _payeeLabels[_kind] ?? 'Pays',
                            helperText: _loadingParties
                                ? 'Reading the list...'
                                : 'Type a code or a name to narrow the list.',
                            prefixIcon: const Icon(Icons.search),
                          ),
                        ),
                      ),
                      const SizedBox(height: AppSpacing.md),
                      TextField(
                        key: const ValueKey('cheque-payee-name'),
                        controller: _name,
                        enabled: !saving,
                        maxLength: 200,
                        onChanged: (_) => _nameTyped = true,
                        decoration: const InputDecoration(
                          labelText: 'Name on the cheque',
                          helperText: 'Blank prints the name of the account paid.',
                        ),
                      ),
                      Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Expanded(
                            child: TextField(
                              key: const ValueKey('cheque-number'),
                              controller: _number,
                              enabled: !saving,
                              decoration: const InputDecoration(
                                  labelText: 'Cheque number'),
                            ),
                          ),
                          const SizedBox(width: AppSpacing.md),
                          Expanded(
                            child: TextField(
                              key: const ValueKey('cheque-amount'),
                              controller: _amount,
                              enabled: !saving,
                              keyboardType:
                                  const TextInputType.numberWithOptions(
                                      decimal: true),
                              decoration:
                                  const InputDecoration(labelText: 'Amount'),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: AppSpacing.md),
                      ChequeDateField(
                        key: const ValueKey('cheque-date'),
                        label: 'Cheque date',
                        value: _date,
                        enabled: !saving,
                        onChanged: (date) => setState(() => _date = date),
                      ),
                      const SizedBox(height: AppSpacing.xs),
                      Text(
                        _whatHappens,
                        key: const ValueKey('cheque-what-happens'),
                        style: theme.textTheme.bodySmall,
                      ),
                      const SizedBox(height: AppSpacing.md),
                      TextField(
                        key: const ValueKey('cheque-narration'),
                        controller: _narration,
                        enabled: !saving,
                        decoration: const InputDecoration(labelText: 'Note'),
                      ),
                    ],
                  ],
                ),
              ),
      ),
      actions: [
        TextButton(onPressed: cancelHandler, child: const Text('Cancel')),
        FilledButton(
          key: const ValueKey('cheque-save'),
          onPressed: saving || _loading || kinds.isEmpty ? null : _save,
          child: Text(saving ? 'Saving…' : 'Write cheque'),
        ),
      ],
    );
  }
}
