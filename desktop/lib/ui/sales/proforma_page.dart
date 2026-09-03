// A statement of what an order will be charged, issued before the bill.
//
// The one thing every view here must make impossible to miss: **this is not a
// tax invoice.** No input credit can be claimed against it and no tax is
// payable on it. Somebody eventually prints one and hands it to an accounts
// clerk, so the words travel with the document rather than living in a manual.

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/entities.dart';
import '../../models/proforma.dart';
import '../workspace/desktop_framework.dart';
import '../workspace/reason_prompt.dart';

/// List the firm's proformas, raise one from an order, issue or withdraw it.
class ProformaPage extends StatefulWidget {
  const ProformaPage({
    super.key,
    required this.api,
    required this.permissions,
    required this.hasActiveFirm,
  });

  final ApiClient api;
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
        (page) => widget.api.proformaInvoices(page: page),
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
    final Json? chosen = await showDialog<Json>(
      context: context,
      builder: (context) => _RaiseProformaDialog(orders: orders),
    );
    if (chosen == null || !mounted) return;
    try {
      final ProformaRecord row = await widget.api.createProformaInvoice(chosen);
      if (!mounted) return;
      NotificationService.show(
        context,
        '${row.proformaNumber} raised. Issue it when the customer needs it.',
        kind: AppNotificationKind.success,
      );
      await _load();
    } on ApiException catch (error) {
      if (!mounted) return;
      NotificationService.show(context, error.message,
          kind: AppNotificationKind.error);
    }
  }

  /// The orders a proforma may state.
  ///
  /// A draft is not a deal and a cancelled one has been called off, so the
  /// picker offers neither -- the server refuses them anyway, and a list that
  /// offers what will be refused wastes the user's time twice.
  Future<List<Json>> _statableOrders() async {
    try {
      final Json response = await widget.api.documentPage(
        'sales-orders',
        pageSize: 100,
      );
      final dynamic data = response['data'];
      if (data is! List) return const <Json>[];
      return data
          .whereType<Map>()
          .map(Map<String, dynamic>.from)
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
    return ManagementWorkspaceLayout(
      toolbar: Wrap(
        spacing: AppSpacing.sm,
        runSpacing: AppSpacing.sm,
        children: [
          OutlinedButton.icon(
            onPressed: _load,
            icon: const Icon(Icons.refresh),
            label: const Text('Refresh'),
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
      searchPanel: Padding(
        padding: const EdgeInsets.all(AppSpacing.md),
        child: Text(
          // Said once at the top of the workspace and again on the detail
          // pane, because this is the property the document is defined by.
          'A proforma is not a tax invoice: it raises no revenue, no output '
          'tax and nothing the customer owes yet.',
          style: Theme.of(context).textTheme.bodySmall,
        ),
      ),
      primaryContent: _list(),
      detailsPanel: selected == null ? null : _details(selected),
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
class _RaiseProformaDialog extends StatefulWidget {
  const _RaiseProformaDialog({required this.orders});

  final List<Json> orders;

  @override
  State<_RaiseProformaDialog> createState() => _RaiseProformaDialogState();
}

class _RaiseProformaDialogState extends State<_RaiseProformaDialog> {
  late String _orderId = '${widget.orders.first['id']}';
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
                Text(
                  'The order’s lines are copied as they stand. Editing the '
                  'order afterwards will not change the document the customer '
                  'is holding.',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
                const SizedBox(height: AppSpacing.md),
                DropdownButtonFormField<String>(
                  initialValue: _orderId,
                  decoration: const InputDecoration(labelText: 'Sales order'),
                  items: [
                    for (final Json order in widget.orders)
                      DropdownMenuItem<String>(
                        value: '${order['id']}',
                        child: Text(
                          '${order['order_number']} — '
                          '${order['grand_total']}',
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
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(<String, dynamic>{
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
            }),
            child: const Text('Raise'),
          ),
        ],
      );
}
