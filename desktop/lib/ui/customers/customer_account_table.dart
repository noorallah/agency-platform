// A customer's account as rows, with a row to add a receipt to it (backlog
// 121, M3).
//
// The last few entries, oldest first, ending in one row that is not an entry
// yet: a date, what the money is against, an amount, how it came, a reference
// and Add. Add posts one receipt through the same route the Receipts screen
// uses, so it closes the bill it names and appears in the ledger like any other.
// A saved row is never edited here; a receipt is reversed from the Receipts
// screen.
//
// Calls: opening it reads the account and, for someone who may record a
// receipt, the unpaid bills. Changing how many entries show reads the account
// again. Adding posts once and reads both again. Nothing else is requested.

import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/entities.dart';
import '../../models/settlement.dart';
import '../../models/settlement_direction.dart';
import '../../phase2/indian_format.dart';
import '../workspace/desktop_framework.dart';

/// How many entries the chooser offers; the first is the default.
const List<int> accountEntryChoices = <int>[20, 50, 100];

/// One customer's account. Keyed by the customer on the page that holds it,
/// so a different customer is a new state and never shows the last one's rows.
class CustomerAccountTable extends StatefulWidget {
  const CustomerAccountTable({
    super.key,
    required this.api,
    required this.permissions,
    required this.customerId,
  });

  final ApiClient api;
  final PermissionService permissions;
  final String customerId;

  @override
  State<CustomerAccountTable> createState() => _CustomerAccountTableState();
}

class _CustomerAccountTableState extends State<CustomerAccountTable> {
  /// The table is never narrower than this; a narrower window scrolls it
  /// sideways rather than squeezing the row's fields.
  static const double _minWidth = 860;

  late final TextEditingController _date =
      TextEditingController(text: _iso(DateTime.now()));
  final TextEditingController _amount = TextEditingController();
  final TextEditingController _reference = TextEditingController();

  Json? _account;
  List<OutstandingInvoice> _bills = const [];
  int _last = accountEntryChoices.first;
  String _against = '';
  String _mode = 'BANK_TRANSFER';
  String? _error;
  String? _rowError;
  bool _loading = true;
  bool _posting = false;

  /// The rows scroll; a fresh read ends scrolled to the bottom, where the
  /// row that adds a receipt is.
  final ScrollController _scroll = ScrollController();
  bool _toEnd = false;

  /// Only the newest read is kept, so a slow answer for an earlier choice
  /// cannot overwrite a later one.
  int _ask = 0;

  bool get _mayReceive => widget.permissions.hasPermission('RECEIPT_CREATE');

  static String _iso(DateTime value) =>
      '${value.year.toString().padLeft(4, '0')}-'
      '${value.month.toString().padLeft(2, '0')}-'
      '${value.day.toString().padLeft(2, '0')}';

  @override
  void initState() {
    super.initState();
    unawaited(_load(withBills: true));
  }

  @override
  void dispose() {
    _date.dispose();
    _amount.dispose();
    _reference.dispose();
    _scroll.dispose();
    super.dispose();
  }

  /// Read the account, and the unpaid bills when asked and allowed. The pane
  /// is emptied first so nothing stale stays under the customer's name.
  Future<void> _load({required bool withBills}) async {
    final int ask = ++_ask;
    setState(() {
      _loading = true;
      _error = null;
      _account = null;
    });
    try {
      final Json account =
          await widget.api.customerAccount(widget.customerId, last: _last);
      List<OutstandingInvoice>? bills;
      if (withBills && _mayReceive) {
        try {
          bills = await widget.api.outstandingInvoices(
            direction: SettlementDirection.receipt,
            partyId: widget.customerId,
          );
        } on ApiException {
          // Advice for the Against list, not a gate: a receipt on account
          // can still be added without it.
          bills = const [];
        }
      }
      if (!mounted || ask != _ask) return;
      setState(() {
        _account = account;
        if (bills != null) _bills = bills;
        _loading = false;
        _toEnd = true;
      });
    } on ApiException catch (exception) {
      if (!mounted || ask != _ask) return;
      setState(() {
        _error = exception.message;
        _loading = false;
      });
    }
  }

  OutstandingInvoice? get _chosenBill {
    for (final OutstandingInvoice bill in _bills) {
      if (bill.invoiceId == _against) return bill;
    }
    return null;
  }

  static String _full(Object? value) =>
      indianAmount(double.tryParse('${value ?? 0}') ?? 0, full: true);

  static String _plain(Object? value) {
    final double? parsed = double.tryParse('${value ?? 0}');
    return parsed == null ? '${value ?? ''}' : parsed.toStringAsFixed(2);
  }

  /// What is cheap to say before a request, and nothing the server decides.
  String? _problem() {
    final DateTime? day = DateTime.tryParse(_date.text.trim());
    if (day == null || _date.text.trim().length != 10) {
      return 'Enter the date as YYYY-MM-DD.';
    }
    final double amount = double.tryParse(_amount.text.trim()) ?? -1;
    if (amount <= 0) return 'Enter how much was received.';
    final OutstandingInvoice? bill = _chosenBill;
    if (bill != null && amount - bill.outstanding > 0.005) {
      return '${bill.invoiceNumber} owes ${_full(bill.outstanding)}, so '
          '${_full(amount)} cannot be applied to it.';
    }
    return null;
  }

  Future<void> _add() async {
    if (_posting) return;
    final String? problem = _problem();
    if (problem != null) {
      setState(() => _rowError = problem);
      return;
    }
    setState(() {
      _posting = true;
      _rowError = null;
    });
    try {
      final Settlement saved = await widget.api.recordSettlement(
        direction: SettlementDirection.receipt,
        data: <String, dynamic>{
          'party_id': widget.customerId,
          'settlement_date': _date.text.trim(),
          'amount': _amount.text.trim(),
          'method': _mode == 'CASH' ? 'CASH' : 'BANK',
          'payment_mode': _mode,
          if (_reference.text.trim().isNotEmpty)
            'instrument_reference': _reference.text.trim(),
          // None for "On account": the money is held as an advance.
          'allocations': [
            if (_chosenBill != null)
              {
                'invoice_id': _against,
                'amount': _amount.text.trim(),
              },
          ],
        },
      );
      if (!mounted) return;
      NotificationService.show(
        context,
        'Receipt ${saved.settlementNumber} recorded.',
        kind: AppNotificationKind.success,
      );
      setState(() {
        _amount.clear();
        _reference.clear();
        _date.text = _iso(DateTime.now());
        _against = '';
        _mode = 'BANK_TRANSFER';
        _posting = false;
      });
      await _load(withBills: true);
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() {
        _rowError = exception.message;
        _posting = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const Center(child: CircularProgressIndicator());
    final Json? account = _account;
    if (_error != null || account == null) {
      return WorkspaceEmptyState(
        icon: Icons.error_outline,
        title: 'Nothing could be read',
        message: _error ?? 'The account could not be read.',
      );
    }
    final List<dynamic> lines =
        account['lines'] as List<dynamic>? ?? const <dynamic>[];
    final int total = int.tryParse('${account['total_entries'] ?? ''}') ??
        lines.length;
    final ThemeData theme = Theme.of(context);
    if (_toEnd) {
      _toEnd = false;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (_scroll.hasClients) {
          _scroll.jumpTo(_scroll.position.maxScrollExtent);
        }
      });
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Padding(
          padding: const EdgeInsets.all(AppSpacing.md),
          child: Row(
            children: [
              Expanded(
                child: Text(
                  '${stringValue(account['customer_name'])}  •  '
                  '${_caption(lines.length, total)}',
                  style: theme.textTheme.titleSmall,
                ),
              ),
              DropdownButton<int>(
                key: const ValueKey('account-last-chooser'),
                value: _last,
                items: [
                  for (final int choice in accountEntryChoices)
                    DropdownMenuItem<int>(
                      value: choice,
                      child: Text('Show $choice'),
                    ),
                ],
                onChanged: (value) {
                  if (value == null || value == _last) return;
                  _last = value;
                  unawaited(_load(withBills: false));
                },
              ),
            ],
          ),
        ),
        Expanded(
          child: LayoutBuilder(
            builder: (context, box) => SingleChildScrollView(
              controller: _scroll,
              child: SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                child: SizedBox(
                  width: box.maxWidth < _minWidth ? _minWidth : box.maxWidth,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      _table(account, lines, total, theme),
                      if (_rowError != null)
                        Padding(
                          padding: const EdgeInsets.all(AppSpacing.md),
                          child: Text(
                            _rowError!,
                            key: const ValueKey('account-row-error'),
                            style: theme.textTheme.bodyMedium
                                ?.copyWith(color: theme.colorScheme.error),
                          ),
                        ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
        Padding(
          padding: const EdgeInsets.all(AppSpacing.md),
          child: Text(
            _mayReceive
                ? 'A saved entry is never edited here. The last row adds a '
                    'receipt; to undo one, reverse it from Receipts.'
                : 'A saved entry is never edited here. To undo a receipt, '
                    'reverse it from Receipts.',
            style: theme.textTheme.bodySmall,
          ),
        ),
      ],
    );
  }

  static String _caption(int shown, int total) {
    if (total == 0) return 'No entries yet';
    return total <= shown
        ? (total == 1 ? 'The 1 entry' : 'All $total entries')
        : 'The last $shown of $total entries';
  }

  Widget _cell(String text, {bool numeric = false, bool bold = false}) =>
      Padding(
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.sm,
          vertical: AppSpacing.sm,
        ),
        child: Text(
          text,
          textAlign: numeric ? TextAlign.right : TextAlign.left,
          overflow: TextOverflow.ellipsis,
          maxLines: 2,
          style: bold ? const TextStyle(fontWeight: FontWeight.w600) : null,
        ),
      );

  Widget _table(Json account, List<dynamic> lines, int total, ThemeData theme) {
    final Border line = Border(
      bottom: BorderSide(color: theme.dividerColor),
    );
    TableRow row(List<Widget> cells, {Decoration? decoration}) =>
        TableRow(decoration: decoration ?? BoxDecoration(border: line), children: cells);
    return Table(
      defaultVerticalAlignment: TableCellVerticalAlignment.middle,
      columnWidths: const {
        0: FlexColumnWidth(1.2),
        1: FlexColumnWidth(2.2),
        2: FlexColumnWidth(1.4),
        3: FlexColumnWidth(1.4),
        4: FlexColumnWidth(1.1),
        5: FlexColumnWidth(1.1),
        6: FlexColumnWidth(1.1),
      },
      children: [
        row([
          _cell('Date', bold: true),
          _cell('Type', bold: true),
          _cell('Reference', bold: true),
          _cell('Remarks', bold: true),
          _cell('Debit', numeric: true, bold: true),
          _cell('Credit', numeric: true, bold: true),
          _cell('Balance', numeric: true, bold: true),
        ]),
        // Entries older than the ones shown are folded into this.
        if (total > lines.length)
          row([
            _cell(''),
            _cell('Opening balance'),
            _cell(''),
            _cell(''),
            _cell(''),
            _cell(''),
            _cell(_plain(account['opening_balance']), numeric: true),
          ]),
        for (final dynamic entry in lines)
          row([
            _cell(stringValue((entry as Map)['transaction_date'])),
            _cell(statusInWords(stringValue(entry['transaction_type']))),
            _cell(stringValue(entry['reference_number'])),
            _cell(stringValue(entry['remarks'])),
            _cell(_plain(entry['debit']), numeric: true),
            _cell(_plain(entry['credit']), numeric: true),
            _cell(_plain(entry['balance']), numeric: true),
          ]),
        if (_mayReceive) _entryRow(theme),
      ],
    );
  }

  /// The row that is not an entry yet. Its amount sits under Credit, because
  /// a receipt is a credit to the customer's account.
  TableRow _entryRow(ThemeData theme) {
    const InputDecoration dense = InputDecoration(
      isDense: true,
      border: OutlineInputBorder(),
    );
    Widget padded(Widget child) => Padding(
          padding: const EdgeInsets.all(AppSpacing.xs),
          child: child,
        );
    return TableRow(
      decoration: BoxDecoration(color: theme.colorScheme.surfaceContainerLow),
      children: [
        padded(TextField(
          key: const ValueKey('account-row-date'),
          controller: _date,
          decoration: dense.copyWith(labelText: 'Date'),
        )),
        padded(DropdownButtonFormField<String>(
          key: const ValueKey('account-row-against'),
          initialValue: _against,
          isExpanded: true,
          decoration: dense.copyWith(labelText: 'Against'),
          items: [
            const DropdownMenuItem<String>(
              value: '',
              child: Text('On account'),
            ),
            for (final OutstandingInvoice bill in _bills)
              DropdownMenuItem<String>(
                value: bill.invoiceId,
                child: Text(
                  '${bill.invoiceNumber} · owes ${_full(bill.outstanding)}',
                  overflow: TextOverflow.ellipsis,
                ),
              ),
          ],
          onChanged: (value) => setState(() {
            _against = value ?? '';
            final OutstandingInvoice? bill = _chosenBill;
            // Only into an empty box: what somebody typed is theirs.
            if (bill != null && _amount.text.trim().isEmpty) {
              _amount.text = bill.outstandingAmount;
            }
          }),
        )),
        padded(TextField(
          key: const ValueKey('account-row-reference'),
          controller: _reference,
          decoration: dense.copyWith(labelText: 'Reference'),
        )),
        padded(DropdownButtonFormField<String>(
          key: const ValueKey('account-row-mode'),
          initialValue: _mode,
          isExpanded: true,
          decoration: dense.copyWith(labelText: 'Mode'),
          items: [
            for (final MapEntry<String, String> mode
                in paymentModeLabels.entries)
              DropdownMenuItem<String>(
                value: mode.key,
                child: Text(mode.value, overflow: TextOverflow.ellipsis),
              ),
          ],
          onChanged: (value) =>
              setState(() => _mode = value ?? 'BANK_TRANSFER'),
        )),
        const SizedBox.shrink(),
        padded(TextField(
          key: const ValueKey('account-row-amount'),
          controller: _amount,
          textAlign: TextAlign.right,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          decoration: dense.copyWith(labelText: 'Amount'),
        )),
        padded(FilledButton(
          key: const ValueKey('account-row-add'),
          onPressed: _posting ? null : () => unawaited(_add()),
          child: const Text('Add'),
        )),
      ],
    );
  }
}
