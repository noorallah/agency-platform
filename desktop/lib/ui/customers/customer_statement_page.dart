// What a customer's account did over a period, and what of it is overdue.
//
// Two questions with different shapes, so two views rather than one screen
// trying to be both. A **statement** is a movement — what the account stood at,
// everything that happened to it in date order, what it stands at now. An
// **ageing** is a position — which bills are still unpaid, and for how long.

import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/customer.dart';
import '../../models/entities.dart';
import '../../phase2/indian_format.dart';
import '../workspace/balance_confirmation.dart';
import '../workspace/desktop_framework.dart';
import '../settings/send_message_dialog.dart';
import '../workspace/remind_dialog.dart';
import '../workspace/whatsapp_share.dart';

/// Which of the two questions is on screen.
enum _View { statement, ageing, combined }

/// Show one customer's account, and the firm's receivables ageing.
class CustomerStatementPage extends StatefulWidget {
  const CustomerStatementPage({
    super.key,
    required this.api,
    required this.permissions,
    required this.hasActiveFirm,
    this.letters = const BalanceConfirmationActions(),
    this.whatsApp = const WhatsAppSharer(),
  });

  final ApiClient api;
  final PermissionService permissions;
  final bool hasActiveFirm;

  /// How letters are shown and saved; tests replace it.
  final BalanceConfirmationActions letters;

  /// How a reminder on WhatsApp reaches the machine; tests replace it.
  final WhatsAppSharer whatsApp;

  @override
  State<CustomerStatementPage> createState() => _CustomerStatementPageState();
}

class _CustomerStatementPageState extends State<CustomerStatementPage> {
  late final TextEditingController _from =
      TextEditingController(text: _isoMonthsAgo(3));
  late final TextEditingController _to = TextEditingController(text: _isoToday());

  _View _view = _View.ageing;
  List<Json> _ageing = const [];
  Json? _statement;
  Json? _combined;

  /// Whether the customer on show is also a supplier (ACC-11): the combined
  /// statement is offered only then.
  bool _hasLinkedSupplier = false;
  String? _selectedCustomerId;
  String? _error;
  bool _loading = false;

  bool get _mayView => widget.permissions.hasPermission('CUSTOMER_VIEW');

  static String _isoToday() => _iso(DateTime.now());

  static String _isoMonthsAgo(int months) {
    final DateTime now = DateTime.now();
    return _iso(DateTime(now.year, now.month - months, now.day));
  }

  static String _iso(DateTime value) =>
      '${value.year.toString().padLeft(4, '0')}-'
      '${value.month.toString().padLeft(2, '0')}-'
      '${value.day.toString().padLeft(2, '0')}';

  @override
  void initState() {
    super.initState();
    if (widget.hasActiveFirm && _mayView) _loadAgeing();
  }

  @override
  void dispose() {
    _from.dispose();
    _to.dispose();
    super.dispose();
  }

  Future<void> _loadAgeing() async {
    setState(() {
      _loading = true;
      _error = null;
      _ageing = const [];
    });
    try {
      final List<Json> rows = await widget.api.customerAgeing();
      if (!mounted) return;
      setState(() {
        _ageing = rows;
        _loading = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.message;
        _loading = false;
      });
    }
  }

  Future<void> _loadStatement(String customerId) async {
    setState(() {
      _loading = true;
      _error = null;
      // Dropped on the way in. A refusal is reported in place of the
      // account below, so this is belt and braces rather than the thing that
      // stops one customer's figures appearing under another's name.
      _statement = null;
      if (_selectedCustomerId != customerId) _hasLinkedSupplier = false;
      _selectedCustomerId = customerId;
      _view = _View.statement;
    });
    try {
      final Json answer = await widget.api.customerStatement(
        customerId,
        fromDate: _from.text.trim(),
        toDate: _to.text.trim(),
      );
      if (!mounted) return;
      setState(() {
        _statement = answer;
        _loading = false;
      });
      unawaited(_checkLinkedSupplier(customerId));
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.message;
        _loading = false;
      });
    }
  }

  /// Reads whether the customer has a linked supplier (ACC-11). Advisory:
  /// anything unreadable leaves the combined statement off.
  Future<void> _checkLinkedSupplier(String customerId) async {
    // Never answers inside the caller's own setState.
    await Future<void>.value();
    bool linked = false;
    if (widget.permissions.hasPermission('VENDOR_VIEW')) {
      try {
        final Customer customer = await widget.api.customer(customerId);
        linked = customer.linkedVendorId.isNotEmpty;
      } on Object {
        linked = false;
      }
    }
    if (!mounted || _selectedCustomerId != customerId) return;
    setState(() => _hasLinkedSupplier = linked);
  }

  /// The customer's account and their supplier's, net of each other.
  Future<void> _loadCombined() async {
    final String? customerId = _selectedCustomerId;
    if (customerId == null) return;
    setState(() {
      _loading = true;
      _error = null;
      _combined = null;
      _view = _View.combined;
    });
    try {
      final Json answer = await widget.api.customerCombinedStatement(
        customerId,
        fromDate: _from.text.trim(),
        toDate: _to.text.trim(),
      );
      if (!mounted) return;
      setState(() {
        _combined = answer;
        _loading = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.message;
        _loading = false;
      });
    }
  }

  /// The day the letters are drawn for: the statement's end date.
  String get _asOf =>
      DateTime.tryParse(_to.text.trim()) == null ? _isoToday() : _to.text.trim();

  Future<void> _confirmation() async {
    final String? id = _selectedCustomerId;
    if (id == null) return;
    await widget.letters.letter(
      context,
      fetch: () => widget.api.customerBalanceConfirmation(id, asOf: _asOf),
      documentName: 'Balance confirmation $id',
    );
  }

  /// The name of the customer on show, from the statement or the ageing row.
  String get _selectedCustomerName {
    final Json? statement = _statement;
    if (statement != null &&
        stringValue(statement['customer_id']) == _selectedCustomerId) {
      return stringValue(statement['customer_name']);
    }
    for (final Json row in _ageing) {
      if (stringValue(row['customer_id']) == _selectedCustomerId) {
        return stringValue(row['customer_name']);
      }
    }
    return 'customer';
  }

  /// Remind the customer on show to pay: their statement, by email or by
  /// hand on WhatsApp (MSG-3).
  Future<void> _remind() async {
    final String? id = _selectedCustomerId;
    if (id == null) return;
    await showDialog<bool>(
      context: context,
      builder: (_) => RemindDialog(
        api: widget.api,
        customerId: id,
        customerName: _selectedCustomerName,
        whatsApp: widget.whatsApp,
      ),
    );
  }

  /// Email the customer on show their statement, by hand (MSG-4).
  Future<void> _sendStatement() async {
    final String? id = _selectedCustomerId;
    if (id == null) return;
    await showDialog<bool>(
      context: context,
      builder: (_) => SendMessageDialog(
        api: widget.api,
        invoiceId: id,
        invoiceNumber: 'statement for $_selectedCustomerName',
        documentType: 'CUSTOMER_STATEMENT',
      ),
    );
  }

  Future<void> _everyone() => widget.letters.everyone(
        context,
        fetch: () => widget.api.customerBalanceConfirmations(asOf: _asOf),
        suggestedName: 'customer-balance-confirmations-$_asOf.zip',
      );

  /// Read again whichever view is on show.
  void _refresh() {
    if (_view == _View.ageing) {
      _loadAgeing();
      return;
    }
    if (_view == _View.combined) {
      unawaited(_loadCombined());
      return;
    }
    final String? id = _selectedCustomerId;
    if (id != null) _loadStatement(id);
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.hasActiveFirm) {
      return const WorkspaceEmptyState(
        title: 'Choose a firm',
        message: 'An account belongs to one firm’s books.',
      );
    }
    if (!_mayView) {
      return const WorkspaceEmptyState(
        icon: Icons.lock_outline,
        title: 'You cannot see this',
        message: 'Reading what customers owe needs the view customers '
            'permission.',
      );
    }
    final bool phase2 = Phase2Scope.of(context);
    return ManagementWorkspaceLayout(
      // Phase 2 (review, 2026-09-27): the statement's period is the Period
      // control on the line, not two free-text boxes in the search slot.
      toolbar: phase2
          ? WorkspaceToolbar(
              actions: const [ToolbarAction.refresh],
              isEnabled: (_) => !_loading,
              onAction: (_) => _refresh(),
              trailing: [
                DateRangeFilter(
                  value: _statementPeriod,
                  onChanged: (period) {
                    setState(() {
                      _from.text =
                          period.from == null ? '' : _iso(period.from!);
                      _to.text = period.to == null ? '' : _iso(period.to!);
                    });
                    if (_view != _View.ageing) _refresh();
                  },
                ),
              ],
              commands: [
                // Sends the statement as a payment reminder (MSG-3).
                if (widget.permissions.hasPermission('DOCUMENT_SEND'))
                  ToolbarCommand(
                    id: 'remind',
                    label: 'Remind',
                    icon: Icons.notifications_active_outlined,
                    tooltip: 'Send the customer their statement and unpaid '
                        'bills, by email or WhatsApp',
                    onPressed: _selectedCustomerId == null
                        ? null
                        : () => unawaited(_remind()),
                  ),
                if (widget.permissions.hasPermission('DOCUMENT_SEND'))
                  ToolbarCommand(
                    id: 'send-statement',
                    label: 'Send',
                    icon: Icons.send_outlined,
                    tooltip: 'Email the customer their statement',
                    onPressed: _selectedCustomerId == null
                        ? null
                        : () => unawaited(_sendStatement()),
                  ),
                // Offered when the customer is also a supplier (ACC-11).
                ToolbarCommand(
                  id: 'combined-statement',
                  label: 'Combined statement',
                  icon: Icons.compare_arrows,
                  menuOnly: true,
                  tooltip: _hasLinkedSupplier
                      ? 'The customer and their supplier account on one page, '
                          'net of each other'
                      : 'Only for a customer who is also a supplier',
                  onPressed: _selectedCustomerId == null || !_hasLinkedSupplier
                      ? null
                      : () => unawaited(_loadCombined()),
                ),
                ToolbarCommand(
                  id: 'balance-confirmation',
                  label: 'Balance confirmation',
                  icon: Icons.mark_email_read_outlined,
                  menuOnly: true,
                  tooltip: 'A letter asking the customer to confirm the '
                      'balance on the period’s end date',
                  onPressed: _selectedCustomerId == null
                      ? null
                      : () => unawaited(_confirmation()),
                ),
                // Not about the customer on show.
                ToolbarCommand(
                  id: 'letters-everyone',
                  label: 'Letters for everyone with a balance',
                  icon: Icons.folder_zip_outlined,
                  menuOnly: true,
                  tooltip: 'One letter per customer with a balance, as of '
                      'the period’s end date, saved as a zip',
                  onPressed: () => unawaited(_everyone()),
                ),
              ],
            )
          : Wrap(
              spacing: AppSpacing.sm,
              runSpacing: AppSpacing.sm,
              children: [
                Phase2Refresh(
                  onPressed: _refresh,
                  child: OutlinedButton.icon(
                    onPressed: _refresh,
                    icon: const Icon(Icons.refresh),
                    label: const Text('Refresh'),
                  ),
                ),
              ],
            ),
      searchPanel: phase2 ? const SizedBox.shrink() : _periodPanel(),
      notice: _view == _View.ageing
          ? 'What each bill still owes, off the receipts against it. '
              'Double-click a customer to read their account.'
          : 'Balances recomputed in date order.',
      viewBar: SegmentedButton<_View>(
        segments: const [
          ButtonSegment(value: _View.ageing, label: Text('Ageing')),
          ButtonSegment(value: _View.statement, label: Text('Statement')),
        ],
        selected: {_view == _View.combined ? _View.statement : _view},
        showSelectedIcon: false,
        onSelectionChanged: (selection) {
          setState(() => _view = selection.first);
          if (_view == _View.ageing && _ageing.isEmpty) _loadAgeing();
        },
      ),
      primaryContent: _content(),
      statusBar: WorkspaceStatusBar(
        total: _view == _View.ageing
            ? _ageing.length
            : _view == _View.combined
                ? _combinedLines().length
                : _lines().length,
        selected: false,
        message: _view == _View.ageing
            ? 'What each bill still owes, off the receipts against it.'
            : 'Balances recomputed in date order.',
      ),
    );
  }

  /// The statement's dates as the Period control holds them.
  DatePeriod get _statementPeriod {
    final DateTime? from = DateTime.tryParse(_from.text.trim());
    final DateTime? to = DateTime.tryParse(_to.text.trim());
    return from == null || to == null
        ? const DatePeriod.all()
        : DatePeriod.custom(from, to);
  }

  /// Phase 2's ageing: a grid, a column per band, double-click to read the
  /// customer's account.
  Widget _ageingGrid() {
    final List<dynamic> bands =
        _ageing.first['buckets'] as List<dynamic>? ?? const [];
    String band(Object? cell) {
      final Map c = cell as Map;
      final Object? upper = c['to_days'];
      return upper == null ? '${c['from_days']}+ days' : '${c['from_days']}-$upper days';
    }
    return EnterpriseDataGrid<Json>(
      items: _ageing,
      total: _ageing.length,
      pageOffset: 0,
      rowsPerPage: _ageing.length,
      availableRowsPerPage: [_ageing.length],
      selectedId: _selectedCustomerId,
      columns: [
        const GridColumn(key: 'customer', label: 'Customer', priority: 1),
        const GridColumn(key: 'code', label: 'Code'),
        for (int i = 0; i < bands.length; i++)
          GridColumn(key: 'band$i', label: band(bands[i]), numeric: true),
        const GridColumn(key: 'total', label: 'Outstanding', numeric: true),
        const GridColumn(key: 'gap', label: 'Account'),
      ],
      id: (row) => stringValue(row['customer_id']),
      cells: (row) {
        final List<dynamic> buckets =
            row['buckets'] as List<dynamic>? ?? const [];
        return [
          stringValue(row['customer_name']),
          stringValue(row['customer_code']),
          for (int i = 0; i < bands.length; i++)
            i < buckets.length ? _money((buckets[i] as Map)['amount']) : '0.00',
          _money(row['total_outstanding']),
          _gap(row),
        ];
      },
      onSelect: (row) => setState(() {
        if (_selectedCustomerId != stringValue(row['customer_id'])) {
          _hasLinkedSupplier = false;
        }
        _selectedCustomerId = stringValue(row['customer_id']);
        unawaited(_checkLinkedSupplier(_selectedCustomerId!));
      }),
      onOpen: (row) => _loadStatement(stringValue(row['customer_id'])),
      onPageChanged: (_) {},
    );
  }

  /// Phase 2's statement: the balances as counters on the line, the lines
  /// a grid.
  Widget _statementGrid(Json statement, List<dynamic> lines) {
    double amount(Object? value) => double.tryParse('${value ?? 0}') ?? 0;
    final double advance = amount(statement['unapplied_advance']);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        SummaryCards(children: [
          SummaryCount(
            label: stringValue(statement['customer_name']),
            value: '',
          ),
          SummaryCount(
            label: 'Opening',
            value: indianAmount(amount(statement['opening_balance']),
                full: true),
          ),
          SummaryCount(
            label: 'Closing',
            value: indianAmount(amount(statement['closing_balance']),
                full: true),
          ),
          if (advance > 0)
            SummaryCount(
              label: 'On account',
              value: indianAmount(advance, full: true),
            ),
        ]),
        Expanded(
          child: lines.isEmpty
              ? const WorkspaceEmptyState(
                  title: 'Nothing moved',
                  message: 'The account had no activity in this period.',
                )
              : EnterpriseDataGrid<Map>(
                  items: [for (final dynamic line in lines) line as Map],
                  total: lines.length,
                  pageOffset: 0,
                  rowsPerPage: lines.length,
                  availableRowsPerPage: [lines.length],
                  columns: const [
                    GridColumn(key: 'date', label: 'Date'),
                    GridColumn(key: 'type', label: 'Type'),
                    GridColumn(key: 'reference', label: 'Reference', priority: 1),
                    GridColumn(key: 'debit', label: 'Debit', numeric: true),
                    GridColumn(key: 'credit', label: 'Credit', numeric: true),
                    GridColumn(key: 'balance', label: 'Balance', numeric: true),
                  ],
                  id: (line) => '${line['reference_number']}|'
                      '${line['transaction_date']}|${line.hashCode}',
                  cells: (line) => [
                    stringValue(line['transaction_date']),
                    statusInWords(stringValue(line['transaction_type'])),
                    stringValue(line['reference_number']),
                    _money(line['debit']),
                    _money(line['credit']),
                    _money(line['balance']),
                  ],
                  onSelect: (_) {},
                  onPageChanged: (_) {},
                ),
        ),
      ],
    );
  }

  Widget _periodPanel() => Padding(
        padding: const EdgeInsets.all(AppSpacing.md),
        child: Row(
          children: [
            Expanded(
              child: TextField(
                controller: _from,
                decoration: const InputDecoration(labelText: 'From'),
              ),
            ),
            const SizedBox(width: AppSpacing.lg),
            Expanded(
              child: TextField(
                controller: _to,
                decoration: const InputDecoration(labelText: 'To'),
              ),
            ),
          ],
        ),
      );

  List<dynamic> _lines() =>
      _statement?['lines'] as List<dynamic>? ?? const <dynamic>[];

  Widget _content() {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_error != null) {
      return WorkspaceEmptyState(
        icon: Icons.error_outline,
        title: 'Nothing could be read',
        message: _error!,
      );
    }
    if (_view == _View.combined) return _combinedView();
    return _view == _View.ageing ? _ageingView() : _statementView();
  }

  List<dynamic> _combinedLines() =>
      _combined?['lines'] as List<dynamic>? ?? const <dynamic>[];

  /// The customer and supplier accounts as one run of lines, with the net
  /// balance after each. Positive is what they owe the firm.
  Widget _combinedView() {
    final Json? combined = _combined;
    if (combined == null) {
      return const WorkspaceEmptyState(
        title: 'Nothing to show',
        message: 'Choose a customer who is also a supplier.',
      );
    }
    double amount(Object? value) => double.tryParse('${value ?? 0}') ?? 0;
    String full(Object? value) => indianAmount(amount(value), full: true);
    final List<dynamic> lines = _combinedLines();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        SummaryCards(children: [
          SummaryCount(
            label: 'Opening net',
            value: full(combined['net_opening']),
          ),
          SummaryCount(
            label: 'They owe us',
            value: full(combined['receivable_closing']),
          ),
          SummaryCount(
            label: 'We owe them',
            value: full(combined['payable_closing']),
          ),
          SummaryCount(
            label: 'Closing net',
            value: full(combined['net_closing']),
          ),
        ]),
        Expanded(
          child: lines.isEmpty
              ? const WorkspaceEmptyState(
                  title: 'Nothing moved',
                  message: 'Neither account had activity in this period.',
                )
              : EnterpriseDataGrid<Map>(
                  items: [for (final dynamic line in lines) line as Map],
                  total: lines.length,
                  pageOffset: 0,
                  rowsPerPage: lines.length,
                  availableRowsPerPage: [lines.length],
                  columns: const [
                    GridColumn(key: 'date', label: 'Date'),
                    GridColumn(key: 'account', label: 'Account'),
                    GridColumn(key: 'type', label: 'Type'),
                    GridColumn(
                        key: 'reference', label: 'Reference', priority: 1),
                    GridColumn(key: 'debit', label: 'Debit', numeric: true),
                    GridColumn(key: 'credit', label: 'Credit', numeric: true),
                    GridColumn(
                        key: 'net', label: 'Net balance', numeric: true),
                  ],
                  id: (line) => '${line['reference_number']}|'
                      '${line['transaction_date']}|${line.hashCode}',
                  cells: (line) => [
                    stringValue(line['transaction_date']),
                    stringValue(line['account']) == 'PAYABLE'
                        ? 'Purchases'
                        : 'Sales',
                    statusInWords(stringValue(line['transaction_type'])),
                    stringValue(line['reference_number']),
                    _money(line['debit']),
                    _money(line['credit']),
                    _money(line['net_balance']),
                  ],
                  onSelect: (_) {},
                  onPageChanged: (_) {},
                ),
        ),
      ],
    );
  }

  Widget _ageingView() {
    if (_ageing.isEmpty) {
      return const WorkspaceEmptyState(
        title: 'Nothing outstanding',
        message: 'Every approved bill has been settled in full.',
      );
    }
    if (Phase2Scope.of(context)) return _ageingGrid();
    return ListView.builder(
      itemCount: _ageing.length,
      itemBuilder: (context, index) {
        final Json row = _ageing[index];
        final List<dynamic> buckets =
            row['buckets'] as List<dynamic>? ?? const [];
        return Card(
          margin: const EdgeInsets.symmetric(
            horizontal: AppSpacing.md,
            vertical: AppSpacing.xs,
          ),
          child: ListTile(
            title: Text(
              '${stringValue(row['customer_name'])}  '
              '(${stringValue(row['customer_code'])})',
            ),
            subtitle: Text(
              // Every band, including the empty ones, so the row reads the
              // same shape every time and the eye can compare down a column.
              buckets.map((bucket) {
                final Map cell = bucket as Map;
                final Object? upper = cell['to_days'];
                final String band = upper == null
                    ? '${cell['from_days']}+'
                    : '${cell['from_days']}-$upper';
                return '$band: ${_money(cell['amount'])}';
              }).join('   •   '),
            ),
            trailing: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Text(
                  _money(row['total_outstanding']),
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                // The bills and the account are not the same number, and a
                // row that showed only the first would disagree with the
                // customer's own balance with nothing to explain the gap.
                if (_gap(row).isNotEmpty)
                  Text(
                    _gap(row),
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
              ],
            ),
            onTap: () => _loadStatement(stringValue(row['customer_id'])),
          ),
        );
      },
    );
  }

  Widget _statementView() {
    final Json? statement = _statement;
    if (statement == null) {
      return const WorkspaceEmptyState(
        title: 'Choose a customer',
        message: 'Pick one from the ageing to read their account.',
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Expanded(child: _statementBody(statement)),
        _interestSection(statement),
      ],
    );
  }

  /// Interest the customer's overdue bills have accrued as of the statement's
  /// end date (SEL-14), with a debit note per bill for whoever may raise one.
  Widget _interestSection(Json statement) {
    final dynamic raw = statement['overdue_interest'];
    final List<Json> rows = raw is List
        ? raw.whereType<Map>().map(Map<String, dynamic>.from).toList()
        : const <Json>[];
    if (rows.isEmpty) return const SizedBox.shrink();
    final ThemeData theme = Theme.of(context);
    final bool mayRaise =
        widget.permissions.hasPermission('CUSTOMER_DEBIT_NOTE_MANAGE');
    return Container(
      key: const ValueKey('statement-overdue-interest'),
      constraints: const BoxConstraints(maxHeight: 190),
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        border: Border(top: BorderSide(color: theme.dividerColor)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            'Interest on overdue bills: ${_money(statement['interest_accrued'])}',
            style: theme.textTheme.titleSmall,
          ),
          const SizedBox(height: AppSpacing.sm),
          Flexible(
            child: ListView(
              shrinkWrap: true,
              children: [
                for (final Json row in rows)
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 2),
                    child: Row(
                      children: [
                        Expanded(
                          child: Text(
                            '${stringValue(row['invoice_number'])}  due '
                            '${stringValue(row['due_date'])}  '
                            '${_money(row['outstanding'])} owing  '
                            '${stringValue(row['days'])} days at '
                            '${stringValue(row['rate'])}%  =  '
                            '${_money(row['interest'])}',
                            overflow: TextOverflow.ellipsis,
                            maxLines: 2,
                          ),
                        ),
                        if (mayRaise)
                          TextButton(
                            key: ValueKey(
                                'raise-interest-${stringValue(row['invoice_id'])}'),
                            onPressed: () => unawaited(_raiseInterest(row)),
                            child: const Text('Raise interest debit note'),
                          ),
                      ],
                    ),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _raiseInterest(Json row) async {
    final String? customerId = _selectedCustomerId;
    if (customerId == null) return;
    try {
      final Json made = await widget.api.raiseOverdueInterestDebitNote(
        customerId,
        invoiceId: stringValue(row['invoice_id']),
        asOf: _to.text.trim(),
      );
      if (!mounted) return;
      NotificationService.show(
        context,
        'Debit note ${stringValue(made['debit_note_number'])} raised as a '
        'draft.',
        kind: AppNotificationKind.success,
      );
    } on ApiException catch (error) {
      if (!mounted) return;
      NotificationService.show(
        context,
        error.message,
        kind: AppNotificationKind.error,
      );
    }
  }

  Widget _statementBody(Json statement) {
    final List<dynamic> lines = _lines();
    if (Phase2Scope.of(context)) return _statementGrid(statement, lines);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Padding(
          padding: const EdgeInsets.all(AppSpacing.md),
          child: Text(
            '${stringValue(statement['customer_name'])}  •  opened at '
            '${_money(statement['opening_balance'])}, closed at '
            '${_money(statement['closing_balance'])}'
            // Beside the balance rather than folded into it: netting them
            // hides an advance the customer can have applied.
            '${_advanceNote(statement)}',
            style: Theme.of(context).textTheme.titleSmall,
          ),
        ),
        Expanded(
          child: lines.isEmpty
              ? const WorkspaceEmptyState(
                  title: 'Nothing moved',
                  message: 'The account had no activity in this period.',
                )
              : SingleChildScrollView(
                  scrollDirection: Axis.horizontal,
                  child: SingleChildScrollView(
                    child: DataTable(
                      columns: const [
                        DataColumn(label: Text('Date')),
                        DataColumn(label: Text('Type')),
                        DataColumn(label: Text('Reference')),
                        DataColumn(label: Text('Debit')),
                        DataColumn(label: Text('Credit')),
                        DataColumn(label: Text('Balance')),
                      ],
                      rows: [
                        for (final dynamic line in lines)
                          DataRow(cells: [
                            DataCell(Text(stringValue((line as Map)['transaction_date']))),
                            DataCell(Text(stringValue(line['transaction_type']))),
                            DataCell(Text(stringValue(line['reference_number']))),
                            DataCell(Text(_money(line['debit']))),
                            DataCell(Text(_money(line['credit']))),
                            DataCell(Text(_money(line['balance']))),
                          ]),
                      ],
                    ),
                  ),
                ),
        ),
      ],
    );
  }

  /// Say how the unpaid bills differ from the account, when they do.
  ///
  /// A credit note or a sales return reduces the account and sits on no
  /// invoice; tax collected at source raises it without being billed. Left
  /// unsaid, the two reports simply disagree.
  static String _gap(Json row) {
    final double credits =
        double.tryParse('${row['unapplied_credits'] ?? 0}') ?? 0;
    final double charges =
        double.tryParse('${row['charges_not_billed'] ?? 0}') ?? 0;
    final double balance =
        double.tryParse('${row['account_balance'] ?? 0}') ?? 0;
    if (credits > 0) {
      return 'less ${credits.toStringAsFixed(2)} credit '
          '= ${balance.toStringAsFixed(2)}';
    }
    if (charges > 0) {
      return 'plus ${charges.toStringAsFixed(2)} unbilled '
          '= ${balance.toStringAsFixed(2)}';
    }
    return '';
  }

  static String _advanceNote(Json statement) {
    final double advance =
        double.tryParse('${statement['unapplied_advance'] ?? 0}') ?? 0;
    return advance <= 0
        ? ''
        : '  •  ${advance.toStringAsFixed(2)} held on account';
  }

  static String _money(Object? value) {
    final double? parsed = double.tryParse('${value ?? 0}');
    return parsed == null ? '${value ?? ''}' : parsed.toStringAsFixed(2);
  }
}
