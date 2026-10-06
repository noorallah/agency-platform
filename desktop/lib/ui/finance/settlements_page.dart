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
import '../workspace/cheque_print_dialog.dart';
import '../workspace/desktop_framework.dart';
import '../settings/send_message_dialog.dart';
import '../workspace/printed_document.dart';
import 'ledger_files_dialog.dart';
import 'record_settlement_dialog.dart';
import 'supplier_credit_refunds.dart';

/// Money in and money out.
///
/// One page serves both. A receipt from a customer and a payment to a vendor
/// are the same document with the signs reversed, and the words on screen are
/// the only thing that differs -- so they are the only thing parameterised.
class SettlementsPage extends StatefulWidget {
  const SettlementsPage({
    super.key,
    required this.api,
    required this.preferences,
    required this.permissions,
    required this.hasActiveFirm,
    required this.direction,
  });

  final ApiClient api;

  /// Where the grid's chosen columns are remembered.
  final DesktopPreferencesService preferences;
  final PermissionService permissions;
  final bool hasActiveFirm;
  final SettlementDirection direction;

  @override
  State<SettlementsPage> createState() => _SettlementsPageState();
}

class _SettlementsPageState extends State<SettlementsPage> {
  static const int _rowsPerPage = 20;
  final TextEditingController _search = TextEditingController();
  List<Settlement> _rows = const [];
  Settlement? _selected;

  /// The settlement dates the list is narrowed to (owner, 2026-09-27).
  DatePeriod _period = const DatePeriod.all();
  int _page = 1;
  int _total = 0;
  bool _loading = false;
  String? _error;

  String get _noun => widget.direction.noun;
  String get _title => widget.direction.title;
  bool get _canView =>
      widget.permissions.hasPermission(widget.direction.viewPermission);
  bool get _canCreate =>
      widget.permissions.hasPermission(widget.direction.createPermission);

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  Future<void> _load({int? requestedPage}) async {
    if (!widget.hasActiveFirm || !_canView) return;
    setState(() {
      _loading = true;
      _error = null;
      if (requestedPage != null) _page = requestedPage;
    });
    try {
      final PagedResult<Settlement> result = await widget.api.settlements(
        direction: widget.direction,
        page: _page,
        pageSize: _rowsPerPage,
        search: _search.text.trim(),
        settlementFrom:
            _period.from == null ? null : DatePeriod.iso(_period.from!),
        settlementTo: _period.to == null ? null : DatePeriod.iso(_period.to!),
      );
      if (!mounted) return;
      setState(() {
        _rows = result.items;
        _total = result.total;
        // Keep the picked one across a reload, unless it fell off the page.
        final String? selectedId = _selected?.id;
        _selected = selectedId == null
            ? null
            : result.items.where((item) => item.id == selectedId).firstOrNull;
      });
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() {
        _error = exception.message;
        _rows = const [];
        _total = 0;
      });
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _record() async {
    setState(() => _loading = true);
    List<PartyOption> parties = const [];
    try {
      // The money screens' own party list, not the customer or vendor master.
      //
      // This read `api.customers(...)` and `api.vendors(...)`, which are gated
      // on `CUSTOMER_VIEW` and `VENDOR_VIEW`. `CASHIER` holds the four receipt
      // and payment codes and neither of those, so recording a receipt was
      // refused **here**, at the party lookup, before the receipt the cashier
      // was authorised for was ever attempted — a role blocked one step
      // before the thing it exists to do. Found at plan step 22.4.
      parties = await widget.api.settlementParties(direction: widget.direction);
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() => _error = exception.message);
      return;
    } finally {
      if (mounted) setState(() => _loading = false);
    }
    if (!mounted) return;
    if (parties.isEmpty) {
      setState(() => _error = widget.direction.isCustomer
          ? 'There are no customers to receive money from yet.'
          : 'There are no vendors to pay yet.');
      return;
    }
    final Settlement? saved = await showDialog<Settlement>(
      context: context,
      barrierDismissible: false,
      builder: (_) => RecordSettlementDialog(
        api: widget.api,
        direction: widget.direction,
        parties: parties,
      ),
    );
    if (saved == null || !mounted) return;
    await _load(requestedPage: 1);
    if (!mounted) return;
    // PG-12: a payment in another currency says what the rate cost or saved.
    final double difference = saved.exchangeDifferenceValue;
    final String exchange = !saved.isForeign
        ? ''
        : difference == 0
            ? ' No exchange difference.'
            : difference > 0
                ? ' Exchange loss ₹${difference.toStringAsFixed(2)}.'
                : ' Exchange gain ₹${(-difference).toStringAsFixed(2)}.';
    NotificationService.show(
      context,
      '${saved.settlementNumber} recorded and posted to the ledger.$exchange',
      kind: AppNotificationKind.success,
    );
  }

  @override
  Widget build(BuildContext context) {
    if (!_canView) {
      return StandardEmptyState(
        type: EmptyStateType.noPermissions,
        title: _title,
        message: 'You do not have permission to view ${_noun}s.',
      );
    }
    if (!widget.hasActiveFirm) {
      return StandardEmptyState(
        type: EmptyStateType.noFirmSelected,
        title: _title,
        message: 'Choose a firm to see its ${_noun}s.',
      );
    }
    if (Phase2Scope.of(context)) return _grid(context);
    return LoadingOverlay(
      loading: _loading,
      child: Column(children: [
        Padding(
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: Row(children: [
            Expanded(
              child: TextField(
                controller: _search,
                decoration: InputDecoration(
                  labelText: 'Search by number or reference',
                  prefixIcon: const Icon(Icons.search),
                  hintText: switch (widget.direction) {
                    SettlementDirection.receipt => 'RC-…',
                    SettlementDirection.payment => 'PY-…',
                    SettlementDirection.refund => 'RF-…',
                  },
                ),
                onSubmitted: (_) => _load(requestedPage: 1),
              ),
            ),
            const SizedBox(width: AppSpacing.md),
            // Goods sent back against a receipt leave a credit on the
            // supplier's account; this is where it is set against a bill
            // (D-FIN-19). Not about any row in the list, so it sits beside
            // Record Payment rather than on a row.
            if (_canCreate &&
                widget.direction == SettlementDirection.payment) ...[
              OutlinedButton.icon(
                onPressed: () => unawaited(_supplierCredits()),
                icon: const Icon(Icons.assignment_return_outlined),
                label: const Text('Supplier credits'),
              ),
              const SizedBox(width: AppSpacing.sm),
              OutlinedButton.icon(
                onPressed: () => unawaited(_supplierRefunds()),
                icon: const Icon(Icons.currency_exchange),
                label: const Text('Supplier refunds'),
              ),
              const SizedBox(width: AppSpacing.sm),
            ],
            if (_canCreate)
              FilledButton.icon(
                onPressed: () => unawaited(_record()),
                icon: const Icon(Icons.add),
                label: Text(
                  switch (widget.direction) {
                    SettlementDirection.receipt => 'Record Receipt',
                    SettlementDirection.payment => 'Record Payment',
                    SettlementDirection.refund => 'Record Refund',
                  },
                ),
              ),
          ]),
        ),
        if (_error != null)
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg),
            child: MaterialBanner(
              content: Text(_error!),
              actions: [
                TextButton(
                  onPressed: () => setState(() => _error = null),
                  child: const Text('Dismiss'),
                ),
              ],
            ),
          ),
        Expanded(
          child: _rows.isEmpty
              ? StandardEmptyState(
                  type: EmptyStateType.noRecords,
                  title: 'No ${_noun}s yet',
                  message: _emptyMessage,
                )
              : ListView.separated(
                  itemCount: _rows.length,
                  separatorBuilder: (_, __) => const Divider(height: 1),
                  itemBuilder: (context, index) => _tile(context, _rows[index]),
                ),
        ),
        WorkspacePager(
          page: _page,
          pageSize: _rowsPerPage,
          total: _total,
          onPageChanged: (next) => unawaited(_load(requestedPage: next)),
        ),
      ]),
    );
  }

  String get _emptyMessage => switch (widget.direction) {
        SettlementDirection.receipt =>
          'Recording a receipt puts the money in the ledger and '
              'reduces what the customer owes.',
        SettlementDirection.payment =>
          'Recording a payment puts the money in the ledger and '
              'reduces what the firm owes the vendor.',
        SettlementDirection.refund =>
          'Recording a refund puts the money in the ledger and '
              'reduces what the customer is holding in advance.',
      };

  /// Phase 2 (owner, 2026-09-27): a full-width grid, as every other list --
  /// the Period after the search, Columns, option C's bar naming the picked
  /// receipt with Apply and Reverse, and a double-click to read it.
  Widget _grid(BuildContext context) {
    final Settlement? selected = _selected;
    return LoadingOverlay(
      loading: _loading,
      child: ManagementWorkspaceLayout(
        toolbar: WorkspaceToolbar(
          actions: const [
            ToolbarAction.newItem,
            ToolbarAction.view,
            ToolbarAction.refresh,
          ],
          isVisible: (action) => action != ToolbarAction.newItem || _canCreate,
          isEnabled: (action) =>
              !_loading &&
              switch (action) {
                ToolbarAction.newItem => _canCreate,
                ToolbarAction.view => selected != null,
                ToolbarAction.refresh => true,
                _ => false,
              },
          onAction: (action) {
            switch (action) {
              case ToolbarAction.newItem:
                unawaited(_record());
              case ToolbarAction.view:
                if (selected != null) unawaited(_openSettlement(selected));
              case ToolbarAction.refresh:
                unawaited(_load());
              default:
                break;
            }
          },
          // Period right after the search, then Columns (owner). Supplier
          // credits is about no row in the list, so it stays on the line.
          trailing: [
            DateRangeFilter(
              value: _period,
              onChanged: (period) {
                setState(() => _period = period);
                unawaited(_load(requestedPage: 1));
              },
            ),
            ColumnsButton(
              onPressed: () async {
                if (await _columns.choose(context) && mounted) {
                  setState(() {});
                }
              },
            ),
            if (_canCreate && widget.direction == SettlementDirection.payment)
              OutlinedButton.icon(
                onPressed: () => unawaited(_supplierCredits()),
                icon: const Icon(Icons.assignment_return_outlined, size: 16),
                label: const Text('Supplier credits'),
              ),
            if (_canCreate && widget.direction == SettlementDirection.payment)
              OutlinedButton.icon(
                onPressed: () => unawaited(_supplierRefunds()),
                icon: const Icon(Icons.currency_exchange, size: 16),
                label: const Text('Supplier refunds'),
              ),
            // What a return or credit note left on a bill already paid: set
            // against another of the customer's bills here (D-PRC-75). About
            // no row in the list, as Supplier credits is.
            if (_canCreate && widget.direction == SettlementDirection.receipt)
              OutlinedButton.icon(
                key: const ValueKey('customer-credits'),
                onPressed: () => unawaited(_customerCredits()),
                icon: const Icon(Icons.assignment_return_outlined, size: 16),
                label: const Text('Customer credits'),
              ),
          ],
          commands: [
            ToolbarCommand(
              id: 'apply',
              label: widget.direction == SettlementDirection.receipt
                  ? 'Apply to an invoice'
                  : 'Apply to a bill',
              icon: Icons.playlist_add_check,
              onPressed: selected != null &&
                      _canCreate &&
                      selected.isOnAccount &&
                      selected.direction != 'REFUND'
                  ? () => unawaited(_apply(selected))
                  : null,
            ),
            ToolbarCommand(
              id: 'reverse',
              label: 'Reverse',
              icon: Icons.undo,
              onPressed: selected != null && _canCreate && !selected.isReversed
                  ? () => unawaited(_reverse(selected))
                  : null,
            ),
            // A receipt as a PDF, or emailed to the customer (MSG-4).
            if (widget.direction == SettlementDirection.receipt) ...[
              ToolbarCommand(
                id: 'print',
                label: 'Print',
                icon: Icons.print_outlined,
                onPressed: selected != null
                    ? () => unawaited(_printReceipt(selected))
                    : null,
              ),
              if (widget.permissions.hasPermission('DOCUMENT_SEND'))
                ToolbarCommand(
                  id: 'send',
                  label: 'Send',
                  icon: Icons.send_outlined,
                  onPressed: selected != null && !selected.isReversed
                      ? () => unawaited(_sendReceipt(selected))
                      : null,
                ),
            ],
            // Papers kept with a receipt or payment (ACC-10); a refund has
            // no files endpoint.
            if (widget.direction.allocates)
              ToolbarCommand(
                id: 'files',
                label: 'Files',
                icon: Icons.attach_file,
                onPressed: selected != null
                    ? () => unawaited(_openFiles(selected))
                    : null,
              ),
            // A bank payment written as a cheque (ACC-12); the layout is set
            // up now and then and is about no row, so it sits behind "...".
            if (widget.direction == SettlementDirection.payment) ...[
              ToolbarCommand(
                id: 'print-cheque',
                label: 'Print cheque',
                icon: Icons.local_atm_outlined,
                onPressed:
                    selected != null && _canCreate && canPrintCheque(selected)
                        ? () => unawaited(_printCheque(selected))
                        : null,
              ),
              if (_canCreate)
                ToolbarCommand(
                  id: 'cheque-layout',
                  label: 'Cheque layout',
                  icon: Icons.straighten,
                  menuOnly: true,
                  onPressed: () => unawaited(_chequeLayout()),
                ),
            ],
          ],
        ),
        selectionBar: true,
        selection: selected == null
            ? null
            : SelectionSummary.document(
                number: selected.settlementNumber,
                party: selected.partyName,
                status: _state(selected),
                total: selected.amount,
                onClear: () => setState(() => _selected = null),
              ),
        searchPanel: SearchFilterPanel(
          controller: _search,
          hintText: widget.direction.isCustomer
              ? 'Search number, reference or customer'
              : 'Search number, reference or supplier',
          onSearch: (_) => unawaited(_load(requestedPage: 1)),
        ),
        primaryContent: Column(children: [
          if (_error != null)
            MaterialBanner(
              content: Text(_error!),
              actions: [
                TextButton(
                  onPressed: () => setState(() => _error = null),
                  child: const Text('Dismiss'),
                ),
              ],
            ),
          Expanded(
            // Nothing yet while the first read is out: the thin bar says it is
            // loading, and "nothing here" would be a claim not yet known.
            child: _loading && _rows.isEmpty
                ? const SizedBox.shrink()
                : _rows.isEmpty
                ? (_search.text.trim().isEmpty && _period.from == null
                    ? StandardEmptyState(
                        type: EmptyStateType.noRecords,
                        title: 'No ${_noun}s yet',
                        message: _emptyMessage,
                      )
                    : const StandardEmptyState(
                        type: EmptyStateType.noSearchResults,
                      ))
                : EnterpriseDataGrid<Settlement>(
                    columns: _columns.gridColumns,
                    items: _rows,
                    id: (item) => item.id,
                    selectedId: selected?.id,
                    cells: _columns.cells,
                    onSelect: (item) => setState(() => _selected = item),
                    onOpen: (item) => unawaited(_openSettlement(item)),
                    total: _total,
                    pageOffset: (_page - 1) * _rowsPerPage,
                    rowsPerPage: _rowsPerPage,
                    onPageChanged: (offset) {
                      final int next = offset ~/ _rowsPerPage + 1;
                      if (next != _page) unawaited(_load(requestedPage: next));
                    },
                  ),
          ),
        ]),
        statusBar: WorkspaceStatusBar(
          total: _total,
          selected: selected != null,
          message: _loading ? 'Loading...' : null,
        ),
      ),
    );
  }

  Future<void> _openFiles(Settlement row) => showDialog<void>(
        context: context,
        builder: (_) => LedgerFilesDialog(
          api: widget.api,
          recordId: row.id,
          direction: widget.direction,
          subtitle: row.settlementNumber,
          canView: _canView,
          canEdit: _canCreate,
        ),
      );

  Future<void> _printReceipt(Settlement row) async {
    try {
      final List<int> pdf = await widget.api.receiptPdf(row.id);
      if (!mounted) return;
      await printDocument(
        context,
        bytes: pdf,
        documentName: row.settlementNumber,
      );
    } on ApiException catch (exception) {
      if (!mounted) return;
      NotificationService.show(
        context,
        exception.message,
        kind: AppNotificationKind.error,
      );
    }
  }

  Future<void> _sendReceipt(Settlement row) async {
    await showDialog<bool>(
      context: context,
      builder: (_) => SendMessageDialog(
        api: widget.api,
        invoiceId: row.id,
        invoiceNumber: row.settlementNumber,
        documentType: 'RECEIPT',
      ),
    );
  }

  Future<void> _printCheque(Settlement row) async {
    await showDialog<Object>(
      context: context,
      builder: (_) => ChequePrintDialog(
        api: widget.api,
        paymentId: row.id,
        number: row.settlementNumber,
        partyName: row.partyName,
        amount: row.cashAmount,
      ),
    );
  }

  Future<void> _chequeLayout() async {
    await showDialog<Object>(
      context: context,
      builder: (_) => ChequeLayoutDialog(api: widget.api),
    );
  }

  /// Where the money stands, in the words the status column uses.
  static String _state(Settlement row) => row.isReversed
      ? 'REVERSED'
      : row.isOnAccount
          ? 'ON_ACCOUNT'
          : 'APPLIED';

  /// What it cleared, or had cleared before it was reversed.
  static String _cleared(Settlement row) =>
      row.allocations.map(_allocationLabel).join(', ');

  /// Every column the grid can show; Columns picks among them, remembered
  /// per screen on this PC (owner, 2026-09-27).
  late final ColumnChoice<Settlement> _columns = ColumnChoice(
    preferences: widget.preferences,
    stateKey: '${widget.direction.path}.grid',
    columns: [
      ChoosableColumn(
        column: const GridColumn(key: 'number', label: 'Number'),
        cell: (item) => item.settlementNumber,
        required: true,
      ),
      // Whose money it is; kept at any width.
      ChoosableColumn(
        column: GridColumn(
          key: 'party',
          label: widget.direction.isCustomer ? 'Customer' : 'Supplier',
          priority: 1,
        ),
        cell: (item) => item.partyName,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'date', label: 'Date'),
        cell: (item) => item.settlementDate,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'method', label: 'Method'),
        cell: (item) => item.method,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'account', label: 'Account'),
        cell: (item) => item.ledgerAccountName,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'reference', label: 'Reference'),
        cell: (item) => item.instrumentReference,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'cleared', label: 'Cleared'),
        cell: _cleared,
        shownByDefault: true,
      ),
      // The order a deposit came in against, where it came in against one.
      ChoosableColumn(
        column: const GridColumn(key: 'order', label: 'Against Order'),
        cell: (item) => item.salesOrderNumber,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'status', label: 'Status'),
        cell: _state,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(
            key: 'unallocated', label: 'On Account', numeric: true),
        cell: (item) => item.unallocatedAmount,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'amount', label: 'Amount'),
        cell: (item) => item.amount,
        shownByDefault: true,
      ),
      // Tax deducted at source (53.1): off by default, since most firms
      // deduct on few settlements; Columns turns them on.
      if (widget.direction.allocates) ...[
        ChoosableColumn(
          column: const GridColumn(key: 'tds', label: 'TDS', numeric: true),
          cell: (item) => item.tdsValue > 0 ? item.tdsAmount : '',
        ),
        ChoosableColumn(
          column: const GridColumn(key: 'tds_section', label: 'TDS Section'),
          cell: (item) => item.tdsSection,
        ),
        ChoosableColumn(
          column: const GridColumn(
              key: 'deductions', label: 'Other Deductions', numeric: true),
          cell: (item) => item.hasDeductions
              ? (item.roundingValue +
                      item.bankChargesValue +
                      item.discountValue)
                  .toStringAsFixed(2)
              : '',
        ),
        ChoosableColumn(
          column: const GridColumn(
              key: 'cash', label: 'Cash or Bank', numeric: true),
          cell: (item) => item.cashAmount,
        ),
      ],
      ChoosableColumn(
        column: const GridColumn(key: 'narration', label: 'Narration'),
        cell: (item) => item.narration,
      ),
    ],
  );

  /// Read one: who, how, into which account, and what it cleared. Apply and
  /// Reverse stay on the bar above the grid, so this only reads.
  Future<void> _openSettlement(Settlement row) async {
    setState(() => _selected = row);
    await showDialog<void>(
      context: context,
      builder: (dialogContext) {
        final TextStyle? small = Theme.of(dialogContext).textTheme.bodySmall;
        Widget fact(String label, String value) => value.isEmpty
            ? const SizedBox.shrink()
            : Padding(
                padding: const EdgeInsets.symmetric(vertical: 2),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    SizedBox(width: 120, child: Text(label, style: small)),
                    Expanded(child: Text(value)),
                  ],
                ),
              );
        return AlertDialog(
          title: Row(children: [
            Expanded(child: Text(row.settlementNumber)),
            StatusBadge.fromStatus(_state(row)),
          ]),
          content: SizedBox(
            width: 520,
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  fact(
                    widget.direction.isCustomer ? 'Customer' : 'Supplier',
                    '${row.partyCode} ${row.partyName}'.trim(),
                  ),
                  fact('Date', row.settlementDate),
                  fact('Amount', row.amount),
                  if (row.tdsValue > 0 || row.hasDeductions) ...[
                    if (row.tdsValue > 0)
                      fact('TDS deducted',
                          '${row.tdsAmount} under ${row.tdsSection}'),
                    if (row.roundingValue > 0)
                      fact('Rounding / short paid', row.roundingAmount),
                    if (row.bankChargesValue > 0)
                      fact('Bank charges', row.bankChargesAmount),
                    if (row.discountValue > 0)
                      fact(
                          row.direction == 'RECEIPT'
                              ? 'Discount allowed'
                              : 'Discount received',
                          row.discountAmount),
                    fact(
                        row.direction == 'RECEIPT'
                            ? 'Received in cash or bank'
                            : 'Paid from cash or bank',
                        row.cashAmount),
                  ],
                  fact('Method', row.method),
                  fact('Account', row.ledgerAccountName),
                  fact('Reference', row.instrumentReference),
                  fact('Against order', row.salesOrderNumber),
                  fact(
                    row.isReversed ? 'Had cleared' : 'Cleared',
                    row.allocations.isEmpty
                        ? 'Not applied to any invoice'
                        : _cleared(row),
                  ),
                  if (row.isOnAccount && !row.isReversed)
                    fact('On account', row.unallocatedAmount),
                  fact('Narration', row.narration),
                  fact('Reversed because', row.reversalReason),
                ],
              ),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(dialogContext).pop(),
              child: const Text('Close'),
            ),
          ],
        );
      },
    );
  }

  /// Take one back, after saying why.
  ///
  /// The reason is asked for rather than optional in spirit: a reversed
  /// receipt is a question somebody will ask about later, and "why" is the
  /// answer they want. The document is not deleted -- both it and the mirror
  /// journal stay.
  Future<void> _reverse(Settlement row) async {
    // No TextEditingController: the dialog rebuilds while it animates out, so
    // one disposed the moment `showDialog` returns is used after disposal.
    // The reason is a plain string the field writes into.
    String why = '';
    final bool? confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text('Reverse ${row.settlementNumber}'),
        // Bounded, because an AlertDialog gives its content unbounded height
        // and a Column inside one overflows by whatever it feels like.
        content: SizedBox(
          width: 460,
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            Text(
              widget.direction.isCustomer
                  ? 'This writes an opposite journal, puts the invoices back and '
                      'restores what the customer owed. Nothing is deleted: both '
                      'the receipt and its reversal stay on the record.'
                  : 'This writes an opposite journal and puts the bills back. '
                      'Nothing is deleted: both the payment and its reversal stay '
                      'on the record.',
              style: Theme.of(dialogContext).textTheme.bodyMedium,
            ),
            const SizedBox(height: AppSpacing.lg),
            TextField(
              onChanged: (value) => why = value,
              decoration: const InputDecoration(
                labelText: 'Why is it being reversed?',
              ),
            ),
          ]),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(dialogContext, true),
            child: const Text('Reverse'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    setState(() => _loading = true);
    try {
      await widget.api.reverseSettlement(
        direction: widget.direction,
        id: row.id,
        reason: why.trim(),
      );
      await _load();
      if (!mounted) return;
      NotificationService.show(
        context,
        '${row.settlementNumber} reversed.',
        kind: AppNotificationKind.success,
      );
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() => _error = exception.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  /// Set money already received against an invoice raised since.
  ///
  /// Nothing is posted to the ledger: the money moved when the receipt was
  /// recorded, and this decides which invoice it clears. The screen says so,
  /// because "applying" money sounds like moving it.
  Future<void> _apply(Settlement row) async {
    // A supplier advance is the same fact the other way round, and the same
    // dialog: a payment recorded before the bill arrived, set against the
    // bill afterwards (D-BUY-8). The words differ -- a bill, not an invoice;
    // money that left, not money that arrived.
    final bool isReceipt = widget.direction == SettlementDirection.receipt;
    final String document = isReceipt ? 'invoice' : 'bill';
    final List<OutstandingInvoice> invoices =
        await widget.api.outstandingInvoices(
      direction: widget.direction,
      partyId: row.partyId,
    );
    if (!mounted) return;
    if (invoices.isEmpty) {
      NotificationService.show(
        context,
        '${row.partyName} has no unpaid ${document}s to apply this to.',
        kind: AppNotificationKind.information,
      );
      return;
    }
    final _Application? chosen = await showDialog<_Application>(
      context: context,
      builder: (context) => _ApplyDialog(
        title: 'Apply ${row.settlementNumber}',
        note: 'Nothing moves in the ledger. The money '
            '${isReceipt ? 'arrived when the receipt' : 'left when the payment'}'
            ' was recorded; this says which $document it clears.',
        available: row.unallocatedAmount,
        availableLabel: 'on account',
        invoiceLabel: isReceipt ? 'Invoice' : 'Bill',
        invoices: invoices,
      ),
    );
    if (chosen == null || !mounted) return;
    try {
      if (isReceipt) {
        await widget.api.allocateReceipt(
          id: row.id,
          invoiceId: chosen.invoiceId,
          amount: chosen.amount,
        );
      } else {
        await widget.api.allocatePayment(
          id: row.id,
          invoiceId: chosen.invoiceId,
          amount: chosen.amount,
        );
      }
      if (!mounted) return;
      NotificationService.show(
        context,
        '${row.settlementNumber} applied to ${chosen.invoiceNumber}.',
        kind: AppNotificationKind.success,
      );
      await _load();
    } on ApiException catch (error) {
      if (!mounted) return;
      NotificationService.show(context, error.message,
          kind: AppNotificationKind.error);
    }
  }

  /// Ask whose credit, from the money screens' own supplier list.
  Future<PartyOption?> _pickVendor() async {
    setState(() => _loading = true);
    List<PartyOption> parties = const [];
    try {
      parties = await widget.api.settlementParties(direction: widget.direction);
    } on ApiException catch (exception) {
      if (!mounted) return null;
      setState(() => _error = exception.message);
      return null;
    } finally {
      if (mounted) setState(() => _loading = false);
    }
    if (!mounted || parties.isEmpty) return null;
    return showDialog<PartyOption>(
      context: context,
      builder: (dialogContext) => SimpleDialog(
        title: const Text('Whose credit?'),
        children: [
          for (final PartyOption party in parties)
            SimpleDialogOption(
              onPressed: () => Navigator.pop(dialogContext, party),
              child: Text('${party.code}  ${party.name}'),
            ),
        ],
      ),
    );
  }

  /// What a supplier's returns left on their account, how each came back, and
  /// the refunds recorded against the ones that came back as money.
  Future<void> _supplierRefunds() async {
    final PartyOption? vendor = await _pickVendor();
    if (vendor == null || !mounted) return;
    await showDialog<void>(
      context: context,
      builder: (_) => SupplierCreditsDialog(
        api: widget.api,
        vendorId: vendor.id,
        vendorName: vendor.name,
        canManage: _canCreate,
      ),
    );
  }

  /// Set a supplier's credit from returns against one of their bills.
  ///
  /// Nothing is posted: the return debited payables when it completed and the
  /// bill credited them when it was approved. The screen says so.
  Future<void> _supplierCredits() async {
    final PartyOption? vendor = await _pickVendor();
    if (vendor == null || !mounted) return;
    final List<SupplierCredit> credits;
    final List<OutstandingInvoice> bills;
    try {
      credits = await widget.api.supplierCredits(vendor.id);
      bills = await widget.api.outstandingInvoices(
        direction: SettlementDirection.payment,
        partyId: vendor.id,
      );
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() => _error = exception.message);
      return;
    }
    if (!mounted) return;
    if (credits.isEmpty || bills.isEmpty) {
      NotificationService.show(
        context,
        credits.isEmpty
            ? '${vendor.name} holds no credit from returns.'
            : '${vendor.name} has no unpaid bills to set the credit against.',
        kind: AppNotificationKind.information,
      );
      return;
    }
    final SupplierCredit? credit = credits.length == 1
        ? credits.single
        : await showDialog<SupplierCredit>(
            context: context,
            builder: (dialogContext) => SimpleDialog(
              title: const Text('Which credit?'),
              children: [
                for (final SupplierCredit row in credits)
                  SimpleDialogOption(
                    onPressed: () => Navigator.pop(dialogContext, row),
                    child: Text(
                      '${row.label} -- ${row.availableAmount} left',
                    ),
                  ),
              ],
            ),
          );
    if (credit == null || !mounted) return;
    final _Application? chosen = await showDialog<_Application>(
      context: context,
      builder: (context) => _ApplyDialog(
        title: 'Set ${credit.label} against a bill',
        note: 'Nothing moves in the ledger. The '
            '${credit.isDebitNote ? 'debit note' : 'return'} debited the '
            'supplier when it was raised; this says which bill that credit '
            'settles.',
        available: credit.availableAmount,
        availableLabel: 'of credit',
        invoiceLabel: 'Bill',
        invoices: bills,
      ),
    );
    if (chosen == null || !mounted) return;
    try {
      await widget.api.applySupplierCredit(
        sourceId: credit.sourceId,
        invoiceId: chosen.invoiceId,
        amount: chosen.amount,
      );
      if (!mounted) return;
      NotificationService.show(
        context,
        '${credit.label} set against ${chosen.invoiceNumber}.',
        kind: AppNotificationKind.success,
      );
    } on ApiException catch (error) {
      if (!mounted) return;
      NotificationService.show(context, error.message,
          kind: AppNotificationKind.error);
    }
  }

  /// Set what a customer's return or credit note left on a paid bill
  /// against another of their bills (D-PRC-75).
  ///
  /// Nothing is posted: the return credited the customer when it completed
  /// and the bill debited them when it was approved. The dialog runs the
  /// save itself, so a refusal is read with the amount still typed.
  Future<void> _customerCredits() async {
    final PartyOption? customer = await _pickVendor();
    if (customer == null || !mounted) return;
    final List<CustomerCredit> credits;
    final List<OutstandingInvoice> bills;
    try {
      credits = await widget.api.customerCredits(customer.id);
      bills = await widget.api.outstandingInvoices(
        direction: SettlementDirection.receipt,
        partyId: customer.id,
      );
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() => _error = exception.message);
      return;
    }
    if (!mounted) return;
    if (credits.isEmpty || bills.isEmpty) {
      NotificationService.show(
        context,
        credits.isEmpty
            ? '${customer.name} holds no credit from returns or credit notes.'
            : '${customer.name} has no unpaid bills to set the credit '
                'against.',
        kind: AppNotificationKind.information,
      );
      return;
    }
    final CustomerCredit? credit = credits.length == 1
        ? credits.single
        : await showDialog<CustomerCredit>(
            context: context,
            builder: (dialogContext) => SimpleDialog(
              title: const Text('Which credit?'),
              children: [
                for (final CustomerCredit row in credits)
                  SimpleDialogOption(
                    onPressed: () => Navigator.pop(dialogContext, row),
                    child: Text(
                      '${row.label} -- ${row.availableAmount} left',
                    ),
                  ),
              ],
            ),
          );
    if (credit == null || !mounted) return;
    final _Application? chosen = await showDialog<_Application>(
      context: context,
      builder: (context) => _ApplyDialog(
        title: 'Set ${credit.label} against a bill',
        note: 'Nothing moves in the ledger. The '
            '${credit.isCreditNote ? 'credit note' : 'return'} credited the '
            'customer when it was raised; this says which bill that credit '
            'settles.',
        available: credit.availableAmount,
        availableLabel: 'of credit',
        invoiceLabel: 'Bill',
        invoices: bills,
        onSave: (application) => widget.api.applyCustomerCredit(
          sourceId: credit.sourceId,
          invoiceId: application.invoiceId,
          amount: application.amount,
        ),
      ),
    );
    if (chosen == null || !mounted) return;
    NotificationService.show(
      context,
      '${credit.label} set against ${chosen.invoiceNumber}.',
      kind: AppNotificationKind.success,
    );
    await _load();
  }

  /// "SI-… on 2026-05-19": the bill, and the day the money met it, which
  /// is what a statement's running balance is dated by (D-TER-19).
  static String _allocationLabel(SettlementAllocation a) =>
      a.allocatedOn.isEmpty
          ? a.invoiceNumber
          : '${a.invoiceNumber} on ${a.allocatedOn}';

  Widget _tile(BuildContext context, Settlement row) {
    // A reversed settlement still names what it had cleared: that is the
    // first thing anybody asks when a correction is queried.
    final String cleared = row.allocations.isEmpty
        ? 'Not applied to any invoice'
        : '${row.isReversed ? 'Had cleared' : 'Cleared'} '
            '${row.allocations.map(_allocationLabel).join(', ')}';
    return ListTile(
      title: Text(
        '${row.settlementNumber}  ·  ${row.settlementDate}  ·  '
        '${row.partyCode} ${row.partyName}',
      ),
      subtitle: Text(
        '$cleared  ·  ${row.modeLabel} into ${row.ledgerAccountName}'
        // The order the money came in against, where it came in against one.
        // Without it a deposit is indistinguishable from a payment somebody
        // made for no stated reason.
        '${row.salesOrderNumber.isEmpty ? '' : ' · against ${row.salesOrderNumber}'}'
        '${row.instrumentReference.isEmpty ? '' : ' · ${row.instrumentReference}'}'
        '${row.instrumentDate.isEmpty ? '' : ' dated ${row.instrumentDate}'}',
      ),
      trailing: Row(mainAxisSize: MainAxisSize.min, children: [
        Text(row.amount, style: Theme.of(context).textTheme.titleSmall),
        const SizedBox(width: AppSpacing.md),
        // On-account money can now be applied. It used to say "somebody has
        // to apply it eventually" and there was no way to: `ADVANCE_APPLY`
        // was a declared transaction type nothing could reach.
        // A supplier advance too, since D-BUY-8; a refund holds nothing to
        // apply, it is money handed back.
        // Labelled, not bare icons: what a checklist icon and an undo arrow
        // do to money is not obvious at a glance (BL-31.14). The tooltip
        // stays as the address a test and a hover both use.
        if (_canCreate && row.isOnAccount && row.direction != 'REFUND')
          Tooltip(
            message: row.direction == 'RECEIPT'
                ? 'Apply to an invoice'
                : 'Apply to a bill',
            child: TextButton.icon(
              icon: const Icon(Icons.playlist_add_check),
              label: const Text('Apply'),
              onPressed: () => unawaited(_apply(row)),
            ),
          ),
        if (_canCreate && !row.isReversed)
          Tooltip(
            message: 'Reverse',
            child: TextButton.icon(
              icon: const Icon(Icons.undo),
              label: const Text('Reverse'),
              onPressed: () => unawaited(_reverse(row)),
            ),
          ),
        if (row.isReversed)
          const StatusBadge(label: 'Reversed')
        else if (row.isOnAccount)
          StatusBadge(label: 'On account ${row.unallocatedAmount}')
        else
          const StatusBadge(label: 'Applied'),
      ]),
    );
  }
}

/// What somebody chose to apply, and to which bill.
class _Application {
  const _Application({
    required this.invoiceId,
    required this.invoiceNumber,
    required this.amount,
  });

  final String invoiceId;
  final String invoiceNumber;
  final String amount;
}

/// Pick an invoice and an amount for money already on account.
class _ApplyDialog extends StatefulWidget {
  const _ApplyDialog({
    required this.title,
    required this.note,
    required this.available,
    required this.availableLabel,
    required this.invoiceLabel,
    required this.invoices,
    this.onSave,
  });

  final String title;
  final String note;

  /// The save, run by the dialog itself so a refusal is shown with the
  /// amount still typed (D-DLG-1). Null closes with the choice and leaves
  /// the call to the caller, as the two older uses do.
  final Future<void> Function(_Application application)? onSave;

  /// What there is to apply, and what to call it: money on account, or a
  /// supplier's credit from returns.
  final String available;
  final String availableLabel;
  final String invoiceLabel;
  final List<OutstandingInvoice> invoices;

  @override
  State<_ApplyDialog> createState() => _ApplyDialogState();
}

class _ApplyDialogState extends State<_ApplyDialog>
    with SaveInDialog<_ApplyDialog> {
  late final TextEditingController _amount =
      TextEditingController(text: widget.available);
  late String _invoiceId = widget.invoices.first.invoiceId;

  @override
  void dispose() {
    // Owned by the dialog, not the caller: disposing it after `showDialog`
    // returns disposes it mid-animation, with the field still rebuilding.
    _amount.dispose();
    super.dispose();
  }

  OutstandingInvoice get _chosen =>
      widget.invoices.firstWhere((invoice) => invoice.invoiceId == _invoiceId);

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: Text(widget.title),
        content: SizedBox(
          width: 460,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              saveErrorBanner(),
              Text(
                widget.note,
                style: Theme.of(context).textTheme.bodySmall,
              ),
              const SizedBox(height: AppSpacing.md),
              DropdownButtonFormField<String>(
                isExpanded: true,
                initialValue: _invoiceId,
                decoration: InputDecoration(labelText: widget.invoiceLabel),
                items: [
                  for (final OutstandingInvoice invoice in widget.invoices)
                    DropdownMenuItem<String>(
                      value: invoice.invoiceId,
                      child: Text(
                        '${invoice.invoiceNumber}'
                        '${invoice.isOpeningBill ? ' (opening)' : ''} — owes '
                        '${invoice.outstandingAmount}',
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                ],
                onChanged: (value) =>
                    setState(() => _invoiceId = value ?? _invoiceId),
              ),
              const SizedBox(height: AppSpacing.sm),
              TextField(
                controller: _amount,
                decoration: InputDecoration(
                  labelText: 'Amount',
                  helperText: '${widget.available} ${widget.availableLabel}, '
                      '${_chosen.outstandingAmount} still owed',
                ),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: cancelHandler,
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: saving
                ? null
                : () {
                    final String amount = _amount.text.trim();
                    if (amount.isEmpty) return;
                    unawaited(submit<_Application>(
                      _Application(
                        invoiceId: _invoiceId,
                        invoiceNumber: _chosen.invoiceNumber,
                        amount: amount,
                      ),
                      widget.onSave,
                    ));
                  },
            child: const Text('Apply'),
          ),
        ],
      );
}
