// A statement of what an order will be charged, issued before the bill.
//
// The one thing every view here must make impossible to miss: **this is not a
// tax invoice.** No input credit can be claimed against it and no tax is
// payable on it. Somebody eventually prints one and hands it to an accounts
// clerk, so the words travel with the document rather than living in a manual.

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/preferences/desktop_preferences_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/entities.dart';
import '../../models/product.dart';
import '../../models/proforma.dart';
import '../settings/send_message_dialog.dart';
import '../workspace/desktop_framework.dart';
import '../workspace/printed_document.dart';
import '../workspace/reason_prompt.dart';
import '../../phase2/document_page.dart';
import '../../phase2/indian_format.dart';

part 'proforma_raise_phase2.dart';

/// List the firm's proformas, raise one from an order, issue or withdraw it.
class ProformaPage extends StatefulWidget {
  const ProformaPage({
    super.key,
    required this.api,
    required this.preferences,
    required this.permissions,
    required this.hasActiveFirm,
  });

  final ApiClient api;

  /// Where the grid's chosen columns are remembered.
  final DesktopPreferencesService preferences;
  final PermissionService permissions;
  final bool hasActiveFirm;

  @override
  State<ProformaPage> createState() => _ProformaPageState();
}

class _ProformaPageState extends State<ProformaPage> {
  List<ProformaRecord> _rows = const [];
  String? _selectedId;
  String? _error;
  bool _loading = true;

  /// Search (number or customer) and the Period, on phase 2's page line
  /// (owner, 2026-09-27), as the other sales lists.
  final TextEditingController _search = TextEditingController();
  DatePeriod _period = const DatePeriod.all();

  String? get _from => _period.from == null ? null : DatePeriod.iso(_period.from!);
  String? get _to => _period.to == null ? null : DatePeriod.iso(_period.to!);

  Widget _periodFilter() => DateRangeFilter(
        value: _period,
        onChanged: (period) {
          setState(() => _period = period);
          unawaited(_load());
        },
      );

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  bool get _mayView => widget.permissions.hasPermission('PROFORMA_VIEW');
  bool get _mayManage => widget.permissions.hasPermission('PROFORMA_MANAGE');

  ProformaRecord? get _selected {
    final String? id = _selectedId;
    if (id == null) return null;
    for (final ProformaRecord row in _rows) {
      if (row.id == id) return row;
    }
    return null;
  }

  @override
  void initState() {
    super.initState();
    if (widget.hasActiveFirm && _mayView) _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final List<ProformaRecord> rows = await fetchAllPages<ProformaRecord>(
        (page) => widget.api.proformaInvoices(
          page: page,
          search: _search.text.trim(),
          proformaFrom: _from,
          proformaTo: _to,
        ),
      );
      if (!mounted) return;
      setState(() {
        _rows = rows;
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

  Future<void> _act(Future<ProformaRecord> Function() action, String done) async {
    try {
      await action();
      if (!mounted) return;
      NotificationService.show(context, done,
          kind: AppNotificationKind.success);
      await _load();
    } on ApiException catch (error) {
      if (!mounted) return;
      NotificationService.show(context, error.message,
          kind: AppNotificationKind.error);
    }
  }

  /// Raise a proforma against an approved order.
  ///
  /// The order is the only thing asked for. Its lines are snapshotted server
  /// side, because a caller that could name its own would be stating a price
  /// the order never agreed.
  /// Render the proforma and hand it to whatever prints on this machine.
  Future<void> _print(ProformaRecord row) async {
    try {
      final List<int> pdf = await widget.api.proformaPdf(row.id);
      if (!mounted) return;
      await printDocument(
        context,
        bytes: pdf,
        documentName: row.proformaNumber,
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

  /// Email the proforma to its customer.
  Future<void> _email(ProformaRecord row) async {
    await showDialog<bool>(
      context: context,
      builder: (_) => SendMessageDialog(
        api: widget.api,
        invoiceId: row.id,
        invoiceNumber: row.proformaNumber,
        documentType: 'PROFORMA_INVOICE',
      ),
    );
  }

  Future<void> _raise() async {
    final List<Json> orders = await _statableOrders();
    if (!mounted) return;
    if (orders.isEmpty) {
      NotificationService.show(
        context,
        'No approved order to state. A proforma restates a deal that exists.',
        kind: AppNotificationKind.information,
      );
      return;
    }
    // Phase 2 raises on its own screen, the order's lines on show; phase 1
    // keeps its dialog.
    final bool phase2 = Phase2Scope.of(context);
    final Map<String, String> names =
        phase2 ? await _productNames() : const {};
    if (!mounted) return;
    Future<ProformaRecord> create(Json values) =>
        widget.api.createProformaInvoice(values);
    final ProformaRecord? row = phase2
        ? await showDocument<ProformaRecord>(
            context,
            title: 'New proforma',
            builder: (_) => _Phase2RaiseProforma(
              orders: orders,
              productNames: names,
              today: DateTime.now(),
              onSave: create,
            ),
          )
        : await showDialog<ProformaRecord>(
            context: context,
            builder: (context) =>
                _RaiseProformaDialog(orders: orders, onSave: create),
          );
    if (row == null || !mounted) return;
    NotificationService.show(
      context,
      '${row.proformaNumber} raised. Issue it when the customer needs it.',
      kind: AppNotificationKind.success,
    );
    await _load();
  }

  /// The orders a proforma may state.
  ///
  /// A draft is not a deal and a cancelled one has been called off, so the
  /// picker offers neither -- the server refuses them anyway, and a list that
  /// offers what will be refused wastes the user's time twice.
  ///
  /// Every page of them: this read the newest hundred orders of any status,
  /// so an older approved order could not be stated at all (D-SELL-18).
  /// Product names by id, for the lines of the order being stated; an
  /// empty map where they cannot be read, and the lines fall back to their
  /// own text.
  Future<Map<String, String>> _productNames() async {
    try {
      final List<Product> products = await fetchAllPages<Product>(
        (page) => widget.api.products(page: page, pageSize: 100),
      );
      return {for (final Product item in products) item.id: item.name};
    } on ApiException {
      return const {};
    }
  }

  Future<List<Json>> _statableOrders() async {
    try {
      final List<Json> orders = await fetchAllPages<Json>((int page) async {
        final Json response = await widget.api.documentPage(
          'sales-orders',
          page: page,
          pageSize: maxApiPageSize,
        );
        final dynamic data = response['data'];
        final dynamic pagination = response['pagination'];
        final List<Json> rows = data is List
            ? data.whereType<Map>().map(Map<String, dynamic>.from).toList()
            : <Json>[];
        return PagedResult<Json>(
          items: rows,
          total: pagination is Map
              ? (pagination['total_records'] as num?)?.toInt() ?? rows.length
              : rows.length,
        );
      });
      return orders
          .where((order) => const <String>{
                'APPROVED',
                'PARTIALLY_DELIVERED',
                'DELIVERED',
                'CLOSED',
              }.contains('${order['status']}'))
          .toList();
    } on ApiException {
      return const <Json>[];
    }
  }

  Future<void> _cancel(ProformaRecord row) async {
    final String? reason = await askForReason(
      context,
      title: 'Withdraw ${row.proformaNumber}',
      explanation: 'Nothing is reversed, because a proforma posts nothing. '
          'The document stays on the record: the customer holds a copy, and '
          'one that vanished would leave them with a number nobody here can '
          'explain.',
      cancelLabel: 'Keep it',
      confirmLabel: 'Withdraw',
    );
    if (reason == null || !mounted) return;
    await _act(
      () => widget.api.cancelProformaInvoice(row.id, reason: reason),
      '${row.proformaNumber} withdrawn.',
    );
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.hasActiveFirm) {
      return const WorkspaceEmptyState(
        title: 'Choose a firm',
        message: 'A proforma states one firm’s order.',
      );
    }
    if (!_mayView) {
      return const WorkspaceEmptyState(
        icon: Icons.lock_outline,
        title: 'You cannot see this',
        message: 'Reading proformas needs the view proforma permission.',
      );
    }
    final ProformaRecord? selected = _selected;
    final bool phase2 = Phase2Scope.of(context);
    return ManagementWorkspaceLayout(
      // Phase 2: Refresh as the line's icon, Issue and Withdraw as its
      // commands, "+ New" last -- as every list.
      toolbar: phase2
          ? WorkspaceToolbar(
              // Period right after the search, then Columns (owner).
              trailing: [
                _periodFilter(),
                ColumnsButton(
                  onPressed: () async {
                    if (await _columns.choose(context) && mounted) {
                      setState(() {});
                    }
                  },
                ),
              ],
              actions: const [
                ToolbarAction.view,
                ToolbarAction.refresh,
                ToolbarAction.newItem,
              ],
              isEnabled: (action) => switch (action) {
                ToolbarAction.view => selected != null,
                ToolbarAction.refresh => true,
                _ => _mayManage,
              },
              onAction: (action) {
                switch (action) {
                  case ToolbarAction.newItem:
                    unawaited(_raise());
                  case ToolbarAction.view:
                    if (selected != null) unawaited(_openProforma(selected));
                  default:
                    unawaited(_load());
                }
              },
              commands: [
                // On every proforma whatever its state (D-UI-71): the copy
                // itself says when it is a draft or was withdrawn.
                ToolbarCommand(
                  id: 'print',
                  label: 'Print',
                  icon: Icons.print_outlined,
                  onPressed: selected == null
                      ? null
                      : () => unawaited(_print(selected)),
                ),
                // Emails it to the customer; a withdrawn one is not sent.
                if (widget.permissions.hasPermission('DOCUMENT_SEND'))
                  ToolbarCommand(
                    id: 'email',
                    label: 'Send',
                    icon: Icons.forward_to_inbox_outlined,
                    onPressed: selected == null || selected.isCancelled
                        ? null
                        : () => unawaited(_email(selected)),
                  ),
                ToolbarCommand(
                  id: 'issue',
                  label: 'Issue',
                  icon: Icons.outbox_outlined,
                  onPressed:
                      _mayManage && selected != null && selected.isDraft
                          ? () => _act(
                                () => widget.api
                                    .issueProformaInvoice(selected.id),
                                '${selected.proformaNumber} issued.',
                              )
                          : null,
                ),
                ToolbarCommand(
                  id: 'withdraw',
                  label: 'Withdraw',
                  icon: Icons.block_outlined,
                  onPressed:
                      _mayManage && selected != null && !selected.isCancelled
                          ? () => _cancel(selected)
                          : null,
                ),
              ],
            )
          : Wrap(
        spacing: AppSpacing.sm,
        runSpacing: AppSpacing.sm,
        children: [
          Phase2Refresh(
            onPressed: _load,
            child: OutlinedButton.icon(
              onPressed: _load,
              icon: const Icon(Icons.refresh),
              label: const Text('Refresh'),
            ),
          ),
          FilledButton.icon(
            onPressed: _mayManage ? _raise : null,
            icon: const Icon(Icons.add),
            label: const Text('New'),
          ),
          FilledButton.icon(
            onPressed: _mayManage && selected != null && selected.isDraft
                ? () => _act(
                      () => widget.api.issueProformaInvoice(selected.id),
                      '${selected.proformaNumber} issued.',
                    )
                : null,
            icon: const Icon(Icons.outbox_outlined),
            label: const Text('Issue'),
          ),
          OutlinedButton.icon(
            onPressed: _mayManage && selected != null && !selected.isCancelled
                ? () => _cancel(selected)
                : null,
            icon: const Icon(Icons.block_outlined),
            label: const Text('Withdraw'),
          ),
        ],
      ),
      // Option C (owner, 2026-09-27): the proforma's actions on a bar that
      // names it, above the grid.
      selectionBar: true,
      selection: selected == null
          ? null
          : SelectionSummary.document(
              number: selected.proformaNumber,
              party: selected.customerName,
              status: selected.status,
              total: selected.grandTotal,
              onClear: () => setState(() => _selectedId = null),
            ),
      // Phase 2: the note is on the detail pane, where it is said again; on
      // the one line it wrapped into three.
      searchPanel: phase2
          ? SearchFilterPanel(
              controller: _search,
              hintText: 'Search number or customer',
              onSearch: (_) => unawaited(_load()),
            )
          : Padding(
        padding: const EdgeInsets.all(AppSpacing.md),
        child: Text(
          // Said once at the top of the workspace and again on the detail
          // pane, because this is the property the document is defined by.
          'A proforma is not a tax invoice: it raises no revenue, no output '
          'tax and nothing the customer owes yet.',
          style: Theme.of(context).textTheme.bodySmall,
        ),
      ),
      // Phase 2: a full-width grid, the proforma read on a double-click
      // (owner, 2026-09-27); phase 1 keeps its list and side pane.
      primaryContent: phase2 ? _grid() : _list(),
      detailsPanel: phase2 || selected == null ? null : _details(selected),
      detailsWidth: 340,
      statusBar: WorkspaceStatusBar(
        total: _rows.length,
        selected: selected != null,
        message: 'Lines snapshotted from the order they state.',
      ),
    );
  }

  Widget _list() {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_error != null) {
      return WorkspaceEmptyState(
        icon: Icons.error_outline,
        title: 'Nothing could be read',
        message: _error!,
      );
    }
    if (_rows.isEmpty) {
      return const WorkspaceEmptyState(
        title: 'No proformas yet',
        message: 'Raise one against an approved sales order when a customer '
            'needs the figure before the goods move.',
      );
    }
    return ListView.builder(
      itemCount: _rows.length,
      itemBuilder: (context, index) {
        final ProformaRecord row = _rows[index];
        return ListTile(
          selected: row.id == _selectedId,
          onTap: () => setState(() => _selectedId = row.id),
          title: Text('${row.proformaNumber}  •  ${row.customerName}'),
          subtitle: Text(
            'against ${row.salesOrderNumber} • ${row.proformaDate}'
            '${row.supersedesId.isEmpty ? '' : ' • replaces an earlier one'}',
          ),
          trailing: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(row.grandTotal.toStringAsFixed(2)),
              const SizedBox(width: AppSpacing.md),
              StatusBadge.fromStatus(row.status),
            ],
          ),
        );
      },
    );
  }

  /// Phase 2's list: the chosen columns over every proforma.
  Widget _grid() {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_error != null || _rows.isEmpty) return _list();
    return EnterpriseDataGrid<ProformaRecord>(
      items: _rows,
      total: _rows.length,
      pageOffset: 0,
      rowsPerPage: _rows.length,
      availableRowsPerPage: [_rows.length],
      selectedId: _selectedId,
      columns: _columns.gridColumns,
      id: (row) => row.id,
      cells: _columns.cells,
      onSelect: (row) => setState(() => _selectedId = row.id),
      onOpen: (row) => unawaited(_openProforma(row)),
      onPageChanged: (_) {},
    );
  }

  static String _amount(double value) => value.toStringAsFixed(2);

  /// Every column the grid can show; Columns picks among them, remembered
  /// per screen on this PC (owner, 2026-09-27).
  late final ColumnChoice<ProformaRecord> _columns = ColumnChoice(
    preferences: widget.preferences,
    stateKey: 'proforma-invoices.grid',
    columns: [
      ChoosableColumn(
        column: const GridColumn(key: 'number', label: 'Number'),
        cell: (item) => item.proformaNumber,
        required: true,
      ),
      // Whose it is; kept at any width.
      ChoosableColumn(
        column:
            const GridColumn(key: 'customer', label: 'Customer', priority: 1),
        cell: (item) => item.customerName,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'date', label: 'Date'),
        cell: (item) => item.proformaDate,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'order', label: 'Sales Order'),
        cell: (item) => item.salesOrderNumber,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'valid', label: 'Valid Until'),
        cell: (item) => item.validUntil,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'status', label: 'Status'),
        cell: (item) => item.status,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(
            key: 'subtotal', label: 'Taxable Value', numeric: true),
        cell: (item) => _amount(item.subtotal),
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'tax', label: 'Tax', numeric: true),
        cell: (item) => _amount(item.taxTotal),
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'total', label: 'Grand Total'),
        cell: (item) => _amount(item.grandTotal),
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'payment', label: 'Payment Terms'),
        cell: (item) => item.paymentTerms,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'delivery', label: 'Delivery Terms'),
        cell: (item) => item.deliveryTerms,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'remarks', label: 'Remarks'),
        cell: (item) => item.remarks,
      ),
    ],
  );

  /// Read one proforma: what the side pane held, in a window. Issue and
  /// Withdraw stay on the bar above the grid, so this only reads.
  Future<void> _openProforma(ProformaRecord row) async {
    setState(() => _selectedId = row.id);
    await showDialog<void>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        content: SizedBox(width: 520, child: _details(row)),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(),
            child: const Text('Close'),
          ),
        ],
      ),
    );
  }

  Widget _details(ProformaRecord row) => SingleChildScrollView(
        padding: const EdgeInsets.all(AppSpacing.md),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(row.proformaNumber,
                style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: AppSpacing.xs),
            // The line that has to be on any printout. A customer's accounts
            // clerk holding this has no other way to tell it apart from a bill.
            if (!row.isTaxInvoice)
              Text(
                'Not a tax invoice — no input tax credit is available against '
                'this document.',
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      color: Theme.of(context).colorScheme.error,
                    ),
              ),
            const SizedBox(height: AppSpacing.md),
            _fact('Customer', row.customerName),
            _fact('Against order', row.salesOrderNumber),
            _fact('Dated', row.proformaDate),
            if (row.validUntil.isNotEmpty) _fact('Valid until', row.validUntil),
            if (row.paymentTerms.isNotEmpty)
              _fact('Payment terms', row.paymentTerms),
            if (row.deliveryTerms.isNotEmpty)
              _fact('Delivery terms', row.deliveryTerms),
            const Divider(height: AppSpacing.xl),
            for (final ProformaLine line in row.lines)
              Padding(
                padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                child: Text(
                  '${line.quantity.toStringAsFixed(2)} × ${line.productName}'
                  // Free goods are stated: a document that dropped them would
                  // understate what is being shipped.
                  '${line.freeQuantity > 0 ? ' (+${line.freeQuantity.toStringAsFixed(2)} free)' : ''}'
                  '  =  ${line.netAmount.toStringAsFixed(2)}',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ),
            const Divider(height: AppSpacing.xl),
            _fact('Taxable value', row.subtotal.toStringAsFixed(2)),
            _fact('Tax', row.taxTotal.toStringAsFixed(2)),
            // Said when there are any, so the total reads as the sum of what
            // is above it (D-SELL-16).
            if (row.otherCharges != 0)
              _fact('Other charges', row.otherCharges.toStringAsFixed(2)),
            _fact('Total', row.grandTotal.toStringAsFixed(2)),
            if (row.isCancelled) ...[
              const SizedBox(height: AppSpacing.md),
              Text(
                'Withdrawn. It stays on the record because the customer holds '
                'a copy.',
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ],
          ],
        ),
      );

  Widget _fact(String label, String value) => Padding(
        padding: const EdgeInsets.only(bottom: AppSpacing.xs),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SizedBox(
              width: 110,
              child: Text(label, style: Theme.of(context).textTheme.bodySmall),
            ),
            Expanded(child: Text(value)),
          ],
        ),
      );
}


/// Choose the order a proforma will state, and the terms it carries.
/// How an order reads in the Raise dialog: number, customer, total.
///
/// The list holds every customer's approved and delivered orders, and with a
/// number and a total alone the wrong customer's order is easy to pick -- a
/// sales return was raised against another customer's note for exactly that
/// reason (plan items 9.22 and 9.25, 2026-09-13).
String proformaOrderLabel(Json order) {
  final String name = '${order['customer_name'] ?? ''}'.trim();
  return name.isEmpty
      ? '${order['order_number']} — ${order['grand_total']}'
      : '${order['order_number']} — $name — ${order['grand_total']}';
}

class _RaiseProformaDialog extends StatefulWidget {
  const _RaiseProformaDialog({required this.orders, required this.onSave});

  final List<Json> orders;

  /// Raises the proforma; throws [ApiException] on a refusal, which the dialog
  /// shows without closing.
  final Future<ProformaRecord> Function(Json values) onSave;

  @override
  State<_RaiseProformaDialog> createState() => _RaiseProformaDialogState();
}

class _RaiseProformaDialogState extends State<_RaiseProformaDialog>
    with SaveInDialog<_RaiseProformaDialog> {
  /// Null until an order is chosen: the first of the list is nobody's
  /// choice (D-UI-66).
  String? _orderId;
  final TextEditingController _paymentTerms = TextEditingController();
  final TextEditingController _deliveryTerms = TextEditingController();
  final TextEditingController _validUntil = TextEditingController();

  @override
  void dispose() {
    // Owned by the dialog, not the caller: disposing after `showDialog`
    // returns disposes mid-animation, with the fields still rebuilding.
    _paymentTerms.dispose();
    _deliveryTerms.dispose();
    _validUntil.dispose();
    super.dispose();
  }

  static String _today() {
    final DateTime now = DateTime.now();
    return '${now.year.toString().padLeft(4, '0')}-'
        '${now.month.toString().padLeft(2, '0')}-'
        '${now.day.toString().padLeft(2, '0')}';
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: const Text('Raise a proforma'),
        content: SizedBox(
          width: 460,
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                saveErrorBanner(),
                Text(
                  'The order’s lines are copied as they stand. Editing the '
                  'order afterwards will not change the document the customer '
                  'is holding.',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
                const SizedBox(height: AppSpacing.md),
                DropdownButtonFormField<String>(
                  isExpanded: true,
                  initialValue: _orderId,
                  decoration: const InputDecoration(labelText: 'Sales order'),
                  items: [
                    for (final Json order in widget.orders)
                      DropdownMenuItem<String>(
                        value: '${order['id']}',
                        child: Text(
                          proformaOrderLabel(order),
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                  ],
                  onChanged: (value) =>
                      setState(() => _orderId = value ?? _orderId),
                ),
                const SizedBox(height: AppSpacing.sm),
                TextField(
                  controller: _validUntil,
                  decoration: const InputDecoration(
                    labelText: 'Valid until',
                    helperText: 'How long the stated prices stand. Blank for '
                        'no deadline.',
                    helperMaxLines: 2,
                  ),
                ),
                const SizedBox(height: AppSpacing.sm),
                TextField(
                  controller: _paymentTerms,
                  decoration: const InputDecoration(labelText: 'Payment terms'),
                ),
                const SizedBox(height: AppSpacing.sm),
                TextField(
                  controller: _deliveryTerms,
                  decoration:
                      const InputDecoration(labelText: 'Delivery terms'),
                ),
              ],
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: cancelHandler,
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: saving ? null : _orderId == null ? () => setState(() => saveError = 'Choose the sales order this proforma states.') : () => saveAndClose<ProformaRecord>(() => widget.onSave(<String, dynamic>{
              'sales_order_id': _orderId,
              'proforma_date': _today(),
              // Blank means no deadline, which is a real choice -- so an
              // empty box is left out rather than sent as an empty string.
              if (_validUntil.text.trim().isNotEmpty)
                'valid_until': _validUntil.text.trim(),
              if (_paymentTerms.text.trim().isNotEmpty)
                'payment_terms': _paymentTerms.text.trim(),
              if (_deliveryTerms.text.trim().isNotEmpty)
                'delivery_terms': _deliveryTerms.text.trim(),
            })),
            child: const Text('Raise'),
          ),
        ],
      );
}
