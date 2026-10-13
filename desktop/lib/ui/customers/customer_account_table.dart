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
// **All** shows the whole account from its first entry (backlog 141, F10),
// read a page at a time as the rows are scrolled, and the row that adds a
// receipt comes after the last of them. Download writes every row of the
// choice on show to an Excel sheet, reading the pages not yet on the screen
// first. How many entries to show is remembered on this machine, per user.
//
// Calls: opening it reads the account and, for someone who may record a
// receipt, the unpaid bills. Changing how many entries show reads the account
// again. Under All, scrolling near the end reads one more page, and Download
// reads what is left in pages of 200. Adding posts once and reads both again.
// Nothing else is requested.

import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/preferences/desktop_preferences_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/entities.dart';
import '../../models/settlement.dart';
import '../../models/settlement_direction.dart';
import '../../phase2/indian_format.dart';
import '../workspace/desktop_framework.dart';
import '../workspace/report_workbook.dart';

/// How many entries the chooser offers; the first is the default.
const List<int> accountEntryChoices = <int>[20, 50, 100];

/// The choice that shows the whole account, as the chooser keeps it.
const int accountAllEntries = 0;

/// How many entries one read of the whole account asks for as it is
/// scrolled, and how many when the rest is read for a download.
const int accountPageSize = 100;
const int accountDownloadPageSize = 200;

/// How the page's Download reaches the rows this table holds: the table
/// names its sheet here while it is on show.
class CustomerAccountSheet {
  Future<WorkbookSheet> Function()? build;
}

/// One customer's account. Keyed by the customer on the page that holds it,
/// so a different customer is a new state and never shows the last one's rows.
class CustomerAccountTable extends StatefulWidget {
  const CustomerAccountTable({
    super.key,
    required this.api,
    required this.permissions,
    required this.customerId,
    this.preferences,
    this.sheet,
  });

  final ApiClient api;
  final PermissionService permissions;
  final String customerId;

  /// Where the number of entries chosen is kept; without it the table opens
  /// on the first choice every time.
  final DesktopPreferencesService? preferences;

  /// Where the page's Download finds this table's sheet.
  final CustomerAccountSheet? sheet;

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

  /// This screen's own state on this machine: the choice of each user.
  static const String _stateKey = 'customer_account';

  Json? _account;

  /// The entries read so far, oldest first, and how many the account holds.
  List<dynamic> _lines = <dynamic>[];
  int _total = 0;

  /// Under All: a further page is being read, or the last one failed.
  bool _reading = false;
  String? _moreError;

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

  bool get _all => _last == accountAllEntries;

  /// Whether rows of the whole account are still to be read.
  bool get _moreToRead => _all && _lines.length < _total;

  String get _user => widget.permissions.userId ?? '';

  /// What this user chose last time, or the first choice.
  int _remembered() {
    final Object? shown =
        widget.preferences?.workspaceState(_stateKey)['show'];
    final Object? mine = shown is Map ? shown[_user] : null;
    return mine is int &&
            (mine == accountAllEntries || accountEntryChoices.contains(mine))
        ? mine
        : accountEntryChoices.first;
  }

  void _remember() {
    final DesktopPreferencesService? preferences = widget.preferences;
    if (preferences == null) return;
    final Map<String, dynamic> state = preferences.workspaceState(_stateKey);
    final Object? shown = state['show'];
    unawaited(preferences.saveWorkspaceState(_stateKey, <String, dynamic>{
      ...state,
      'show': <String, dynamic>{
        if (shown is Map) ...Map<String, dynamic>.from(shown),
        _user: _last,
      },
    }));
  }

  static String _iso(DateTime value) =>
      '${value.year.toString().padLeft(4, '0')}-'
      '${value.month.toString().padLeft(2, '0')}-'
      '${value.day.toString().padLeft(2, '0')}';

  @override
  void initState() {
    super.initState();
    _last = _remembered();
    widget.sheet?.build = _sheet;
    _scroll.addListener(_nearTheEnd);
    unawaited(_load(withBills: true));
  }

  @override
  void dispose() {
    _date.dispose();
    _amount.dispose();
    _reference.dispose();
    _scroll.dispose();
    // A table for another customer may already have named its own.
    if (widget.sheet?.build == _sheet) widget.sheet?.build = null;
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
      _lines = <dynamic>[];
      _total = 0;
      _reading = false;
      _moreError = null;
    });
    try {
      final Json account = await widget.api.customerAccount(
        widget.customerId,
        last: _all ? accountPageSize : _last,
        fromStart: _all,
      );
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
        _lines = List<dynamic>.of(_linesOf(account));
        _total = _totalOf(account, _lines.length);
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

  static List<dynamic> _linesOf(Json page) =>
      page['lines'] as List<dynamic>? ?? const <dynamic>[];

  static int _totalOf(Json page, int otherwise) =>
      int.tryParse('${page['total_entries'] ?? ''}') ?? otherwise;

  void _nearTheEnd() {
    if (!mounted) return;
    if (_scroll.hasClients && _scroll.position.extentAfter < 300) {
      unawaited(_readMore());
    }
  }

  /// Under All, read the page after the rows held. A read that failed is
  /// not tried again until somebody asks, or scrolling would ask for ever.
  Future<void> _readMore({bool again = false}) async {
    if (!_moreToRead || _reading || _loading) return;
    if (_moreError != null && !again) return;
    final int ask = _ask;
    setState(() {
      _reading = true;
      _moreError = null;
    });
    try {
      final Json page = await widget.api.customerAccount(
        widget.customerId,
        last: accountPageSize,
        skip: _lines.length,
        fromStart: true,
      );
      // A fresh read of the account since then owns the rows now.
      if (!mounted || ask != _ask) return;
      final List<dynamic> more = _linesOf(page);
      setState(() {
        _lines.addAll(more);
        // An empty page is the end, whatever the count said.
        _total = more.isEmpty ? _lines.length : _totalOf(page, _total);
        _reading = false;
      });
    } on ApiException catch (exception) {
      if (!mounted || ask != _ask) return;
      setState(() {
        _moreError = exception.message;
        _reading = false;
      });
    }
  }

  /// Every row of the choice on show as a sheet (backlog 141). Under All the
  /// pages not yet scrolled to are read first, so the sheet is the account.
  Future<WorkbookSheet> _sheet() async {
    final Json? account = _account;
    if (account == null) {
      throw const ApiException('The account has not been read yet.');
    }
    final List<dynamic> lines = List<dynamic>.of(_lines);
    int total = _total;
    if (_all) {
      while (lines.length < total) {
        final Json page = await widget.api.customerAccount(
          widget.customerId,
          last: accountDownloadPageSize,
          skip: lines.length,
          fromStart: true,
        );
        final List<dynamic> more = _linesOf(page);
        if (more.isEmpty) break;
        lines.addAll(more);
        total = _totalOf(page, total);
      }
      if (lines.length != total) total = lines.length;
    }
    return WorkbookSheet(
      title: 'Customer account: ${stringValue(account['customer_name'])}',
      notes: [_caption(lines.length, total)],
      headers: const [
        'Date',
        'Type',
        'Reference',
        'Remarks',
        'Debit',
        'Credit',
        'Balance',
      ],
      numeric: const {4, 5, 6},
      rows: [
        // Entries older than the ones chosen are folded into this.
        if (total > lines.length)
          [
            null,
            'Opening balance',
            null,
            null,
            null,
            null,
            account['opening_balance'],
          ],
        for (final dynamic entry in lines)
          [
            stringValue((entry as Map)['transaction_date']),
            statusInWords(stringValue(entry['transaction_type'])),
            stringValue(entry['reference_number']),
            stringValue(entry['remarks']),
            entry['debit'],
            entry['credit'],
            entry['balance'],
          ],
      ],
    );
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
    final List<dynamic> lines = _lines;
    final int total = _total;
    final ThemeData theme = Theme.of(context);
    if (_toEnd) {
      _toEnd = false;
      // The whole account opens on its first entry; the last few open on
      // the row that adds a receipt.
      final bool top = _all;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (_scroll.hasClients) {
          _scroll.jumpTo(top ? 0 : _scroll.position.maxScrollExtent);
        }
      });
    }
    if (_moreToRead) {
      // A page that does not fill the window cannot be scrolled to its end.
      WidgetsBinding.instance.addPostFrameCallback((_) => _nearTheEnd());
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
                  const DropdownMenuItem<int>(
                    value: accountAllEntries,
                    child: Text('Show all'),
                  ),
                ],
                onChanged: (value) {
                  if (value == null || value == _last) return;
                  _last = value;
                  _remember();
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
                      if (_moreToRead) _more(theme),
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

  String _caption(int shown, int total) {
    if (total == 0) return 'No entries yet';
    if (total <= shown) return total == 1 ? 'The 1 entry' : 'All $total entries';
    return _all
        ? 'The first $shown of $total entries'
        : 'The last $shown of $total entries';
  }

  /// Under the rows while the whole account is still being read.
  Widget _more(ThemeData theme) => Padding(
        key: const ValueKey('account-more'),
        padding: const EdgeInsets.all(AppSpacing.md),
        child: _moreError == null
            ? Text('Reading more entries…', style: theme.textTheme.bodySmall)
            : Row(
                children: [
                  Flexible(
                    child: Text(
                      'The rest could not be read: $_moreError',
                      style: theme.textTheme.bodyMedium
                          ?.copyWith(color: theme.colorScheme.error),
                    ),
                  ),
                  TextButton(
                    key: const ValueKey('account-more-again'),
                    onPressed: () => unawaited(_readMore(again: true)),
                    child: const Text('Try again'),
                  ),
                ],
              ),
      );

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
        // Entries older than the ones shown are folded into this. The whole
        // account opens at nothing, so it has no such row.
        if (!_all && total > lines.length)
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
        // Under All the row comes after the last entry, once it is read.
        if (_mayReceive && !_moreToRead) _entryRow(theme),
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
