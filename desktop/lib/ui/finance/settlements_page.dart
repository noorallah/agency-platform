import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/customer.dart';
import '../../models/entities.dart';
import '../../models/settlement.dart';
import '../../models/settlement_direction.dart';
import '../../models/vendor.dart';
import '../workspace/desktop_framework.dart';
import 'record_settlement_dialog.dart';

/// Money in and money out.
///
/// One page serves both. A receipt from a customer and a payment to a vendor
/// are the same document with the signs reversed, and the words on screen are
/// the only thing that differs -- so they are the only thing parameterised.
class SettlementsPage extends StatefulWidget {
  const SettlementsPage({
    super.key,
    required this.api,
    required this.permissions,
    required this.hasActiveFirm,
    required this.direction,
  });

  final ApiClient api;
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
      );
      if (!mounted) return;
      setState(() {
        _rows = result.items;
        _total = result.total;
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
      if (widget.direction.isCustomer) {
        final PagedResult<Customer> result =
            await widget.api.customers(page: 1, search: '');
        parties = [
          for (final Customer customer in result.items)
            PartyOption(id: customer.id, code: customer.code, name: customer.name),
        ];
      } else {
        final PagedResult<Vendor> result =
            await widget.api.vendors(page: 1, search: '');
        parties = [
          for (final Vendor vendor in result.items)
            PartyOption(id: vendor.id, code: vendor.code, name: vendor.name),
        ];
      }
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
    NotificationService.show(
      context,
      '${saved.settlementNumber} recorded and posted to the ledger.',
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
                  message: switch (widget.direction) {
                    SettlementDirection.receipt =>
                      'Recording a receipt puts the money in the ledger and '
                          'reduces what the customer owes.',
                    SettlementDirection.payment =>
                      'Recording a payment puts the money in the ledger and '
                          'reduces what the firm owes the vendor.',
                    SettlementDirection.refund =>
                      'Recording a refund puts the money in the ledger and '
                          'reduces what the customer is holding in advance.',
                  },
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
    final List<OutstandingInvoice> invoices =
        await widget.api.outstandingInvoices(
      direction: SettlementDirection.receipt,
      partyId: row.partyId,
    );
    if (!mounted) return;
    if (invoices.isEmpty) {
      NotificationService.show(
        context,
        '${row.partyName} has no unpaid invoices to apply this to.',
        kind: AppNotificationKind.information,
      );
      return;
    }
    final _Application? chosen = await showDialog<_Application>(
      context: context,
      builder: (context) => _ApplyDialog(
        settlement: row,
        invoices: invoices,
      ),
    );
    if (chosen == null || !mounted) return;
    try {
      await widget.api.allocateReceipt(
        id: row.id,
        invoiceId: chosen.invoiceId,
        amount: chosen.amount,
      );
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

  Widget _tile(BuildContext context, Settlement row) {
    // A reversed settlement still names what it had cleared: that is the
    // first thing anybody asks when a correction is queried.
    final String cleared = row.allocations.isEmpty
        ? 'Not applied to any invoice'
        : '${row.isReversed ? 'Had cleared' : 'Cleared'} '
            '${row.allocations.map((a) => a.invoiceNumber).join(', ')}';
    return ListTile(
      title: Text(
        '${row.settlementNumber}  ·  ${row.settlementDate}  ·  '
        '${row.partyCode} ${row.partyName}',
      ),
      subtitle: Text(
        '$cleared  ·  ${row.method} into ${row.ledgerAccountName}'
        // The order the money came in against, where it came in against one.
        // Without it a deposit is indistinguishable from a payment somebody
        // made for no stated reason.
        '${row.salesOrderNumber.isEmpty ? '' : ' · against ${row.salesOrderNumber}'}'
        '${row.instrumentReference.isEmpty ? '' : ' · ${row.instrumentReference}'}',
      ),
      trailing: Row(mainAxisSize: MainAxisSize.min, children: [
        Text(row.amount, style: Theme.of(context).textTheme.titleSmall),
        const SizedBox(width: AppSpacing.md),
        // On-account money can now be applied. It used to say "somebody has
        // to apply it eventually" and there was no way to: `ADVANCE_APPLY`
        // was a declared transaction type nothing could reach.
        if (_canCreate && row.isOnAccount && row.direction == 'RECEIPT')
          IconButton(
            tooltip: 'Apply to an invoice',
            icon: const Icon(Icons.playlist_add_check),
            onPressed: () => unawaited(_apply(row)),
          ),
        if (_canCreate && !row.isReversed)
          IconButton(
            tooltip: 'Reverse',
            icon: const Icon(Icons.undo),
            onPressed: () => unawaited(_reverse(row)),
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
  const _ApplyDialog({required this.settlement, required this.invoices});

  final Settlement settlement;
  final List<OutstandingInvoice> invoices;

  @override
  State<_ApplyDialog> createState() => _ApplyDialogState();
}

class _ApplyDialogState extends State<_ApplyDialog> {
  late final TextEditingController _amount =
      TextEditingController(text: widget.settlement.unallocatedAmount);
  late String _invoiceId = widget.invoices.first.invoiceId;

  @override
  void dispose() {
    // Owned by the dialog, not the caller: disposing it after `showDialog`
    // returns disposes it mid-animation, with the field still rebuilding.
    _amount.dispose();
    super.dispose();
  }

  OutstandingInvoice get _chosen => widget.invoices
      .firstWhere((invoice) => invoice.invoiceId == _invoiceId);

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: Text('Apply ${widget.settlement.settlementNumber}'),
        content: SizedBox(
          width: 460,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                'Nothing moves in the ledger. The money arrived when the '
                'receipt was recorded; this says which invoice it clears.',
                style: Theme.of(context).textTheme.bodySmall,
              ),
              const SizedBox(height: AppSpacing.md),
              DropdownButtonFormField<String>(
                initialValue: _invoiceId,
                decoration: const InputDecoration(labelText: 'Invoice'),
                items: [
                  for (final OutstandingInvoice invoice in widget.invoices)
                    DropdownMenuItem<String>(
                      value: invoice.invoiceId,
                      child: Text(
                        '${invoice.invoiceNumber} — owes '
                        '${invoice.outstandingAmount}',
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
                  helperText: '${widget.settlement.unallocatedAmount} on '
                      'account, ${_chosen.outstandingAmount} still owed',
                ),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () {
              final String amount = _amount.text.trim();
              if (amount.isEmpty) return;
              Navigator.of(context).pop(_Application(
                invoiceId: _invoiceId,
                invoiceNumber: _chosen.invoiceNumber,
                amount: amount,
              ));
            },
            child: const Text('Apply'),
          ),
        ],
      );
}
