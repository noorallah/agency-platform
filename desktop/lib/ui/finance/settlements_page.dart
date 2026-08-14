import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/customer.dart';
import '../../models/entities.dart';
import '../../models/settlement.dart';
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
    required this.isReceipt,
  });

  final ApiClient api;
  final PermissionService permissions;
  final bool hasActiveFirm;
  final bool isReceipt;

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

  String get _noun => widget.isReceipt ? 'receipt' : 'payment';
  String get _title => widget.isReceipt ? 'Receipts' : 'Payments';
  bool get _canView => widget.permissions
      .hasPermission(widget.isReceipt ? 'RECEIPT_VIEW' : 'PAYMENT_VIEW');
  bool get _canCreate => widget.permissions
      .hasPermission(widget.isReceipt ? 'RECEIPT_CREATE' : 'PAYMENT_CREATE');

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
        isReceipt: widget.isReceipt,
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
      if (widget.isReceipt) {
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
      setState(() => _error = widget.isReceipt
          ? 'There are no customers to receive money from yet.'
          : 'There are no vendors to pay yet.');
      return;
    }
    final Settlement? saved = await showDialog<Settlement>(
      context: context,
      barrierDismissible: false,
      builder: (_) => RecordSettlementDialog(
        api: widget.api,
        isReceipt: widget.isReceipt,
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
                  hintText: widget.isReceipt ? 'RC-…' : 'PY-…',
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
                  widget.isReceipt ? 'Record Receipt' : 'Record Payment',
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
                  message: widget.isReceipt
                      ? 'Recording a receipt puts the money in the ledger and '
                          'reduces what the customer owes.'
                      : 'Recording a payment puts the money in the ledger and '
                          'reduces what the firm owes the vendor.',
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

  Widget _tile(BuildContext context, Settlement row) {
    final String cleared = row.allocations.isEmpty
        ? 'Not applied to any invoice'
        : 'Cleared ${row.allocations.map((a) => a.invoiceNumber).join(', ')}';
    return ListTile(
      title: Text(
        '${row.settlementNumber}  ·  ${row.settlementDate}  ·  '
        '${row.partyCode} ${row.partyName}',
      ),
      subtitle: Text(
        '$cleared  ·  ${row.method} into ${row.ledgerAccountName}'
        '${row.instrumentReference.isEmpty ? '' : ' · ${row.instrumentReference}'}',
      ),
      trailing: Row(mainAxisSize: MainAxisSize.min, children: [
        Text(row.amount, style: Theme.of(context).textTheme.titleSmall),
        const SizedBox(width: AppSpacing.md),
        // On-account money is worth flagging: it reached the ledger and
        // reduced the balance, but no document says what it was for, and
        // somebody has to apply it eventually.
        if (row.isOnAccount)
          StatusBadge(label: 'On account ${row.unallocatedAmount}')
        else
          const StatusBadge(label: 'Applied'),
      ]),
    );
  }
}
