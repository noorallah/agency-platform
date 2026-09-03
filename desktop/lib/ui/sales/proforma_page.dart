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
import '../../models/proforma.dart';
import '../workspace/desktop_framework.dart';

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

  Future<void> _cancel(ProformaRecord row) async {
    final TextEditingController reason = TextEditingController();
    final bool? confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('Withdraw ${row.proformaNumber}'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text(
              'Nothing is reversed, because a proforma posts nothing. The '
              'document stays on the record: the customer holds a copy, and '
              'one that vanished would leave them with a number nobody here '
              'can explain.',
            ),
            const SizedBox(height: AppSpacing.md),
            TextField(
              controller: reason,
              decoration: const InputDecoration(labelText: 'Reason'),
              autofocus: true,
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Keep it'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Withdraw'),
          ),
        ],
      ),
    );
    final String text = reason.text.trim();
    reason.dispose();
    if (confirmed != true || text.isEmpty) return;
    await _act(
      () => widget.api.cancelProformaInvoice(row.id, reason: text),
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
