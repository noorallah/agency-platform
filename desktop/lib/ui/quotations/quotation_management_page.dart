import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/api/concurrency.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/branch_warehouse.dart';
import '../../models/customer.dart';
import '../../models/entities.dart';
import '../../models/product.dart';
import '../../models/quotation.dart';
import '../workspace/desktop_framework.dart';
import 'quotation_editor_dialog.dart';

/// Prices offered to customers before anything is sold.
///
/// A quotation commits nothing — no stock is reserved, no balance moves, no
/// journal is written — so the screen never implies it has. What it does say,
/// prominently, is how long each offer stands: an expired quotation is the one
/// thing here that quietly stops being worth anything, and a list that showed
/// only its status would look identical the day before and the day after.
class QuotationManagementPage extends StatefulWidget {
  const QuotationManagementPage({
    super.key,
    required this.api,
    required this.permissions,
    required this.hasActiveFirm,
    this.today,
  });

  final ApiClient api;
  final PermissionService permissions;
  final bool hasActiveFirm;

  /// Overridable so a test can pin the date a new quotation carries.
  final DateTime? today;

  @override
  State<QuotationManagementPage> createState() =>
      _QuotationManagementPageState();
}

class _QuotationManagementPageState extends State<QuotationManagementPage> {
  static const int _rowsPerPage = 20;
  final TextEditingController _search = TextEditingController();
  List<Quotation> _quotations = const [];
  Quotation? _selected;
  int _page = 1;
  int _total = 0;
  bool _loading = false;
  String? _error;

  bool get _canView => widget.permissions.hasPermission('SALES_VIEW');

  /// `SALES_QUOTATION_CREATE` is the code the server gates writing one on. It
  /// has been seeded and enforced nowhere since the identity seed was written.
  bool get _canQuote =>
      widget.permissions.hasPermission('SALES_QUOTATION_CREATE');
  bool get _canDecide => widget.permissions.hasPermission('SALES_APPROVE');
  bool get _canCancel => widget.permissions.hasPermission('SALES_CANCEL');

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
      final PagedResult<Quotation> result = await widget.api.quotations(
        page: _page,
        pageSize: _rowsPerPage,
        search: _search.text.trim(),
      );
      if (!mounted) return;
      setState(() {
        _quotations = result.items;
        _total = result.total;
        final String? selectedId = _selected?.id;
        _selected = selectedId == null
            ? null
            : result.items.where((item) => item.id == selectedId).firstOrNull;
      });
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() {
        _error = exception.message;
        _quotations = const [];
        _total = 0;
      });
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _writeQuotation({Quotation? existing}) async {
    setState(() => _loading = true);
    List<Customer> customers = const [];
    List<Product> products = const [];
    List<BranchRecord> branches = const [];
    List<WarehouseRecord> warehouses = const [];
    try {
      final List<dynamic> results = await Future.wait<dynamic>([
        widget.api.customers(page: 1),
        widget.api.products(page: 1, pageSize: 100),
        widget.api.branches(page: 1, pageSize: 100),
        widget.api.warehouses(page: 1, pageSize: 100),
      ]);
      customers = (results[0] as PagedResult<Customer>).items;
      products = (results[1] as PagedResult<Product>).items;
      branches = (results[2] as PagedResult<BranchRecord>).items;
      warehouses = (results[3] as PagedResult<WarehouseRecord>).items;
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() => _error = exception.message);
      return;
    } finally {
      if (mounted) setState(() => _loading = false);
    }
    if (!mounted) return;
    final Json? payload = await showDialog<Json>(
      context: context,
      barrierDismissible: false,
      builder: (_) => QuotationEditorDialog(
        customers: customers,
        products: products,
        branches: branches,
        warehouses: warehouses,
        today: widget.today ?? DateTime.now(),
        existing: existing,
      ),
    );
    if (payload == null) return;
    try {
      final Quotation saved = existing == null
          ? await widget.api.createQuotation(payload)
          : await widget.api.updateQuotation(
              existing.id,
              payload,
              expectedVersion: preconditionFor(existing.version),
            );
      if (!mounted) return;
      NotificationService.show(
        context,
        existing == null
            ? '${saved.quotationNumber} drafted, good until ${saved.validUntil}. '
                'Nothing is reserved by it.'
            : '${saved.quotationNumber} revised.',
        kind: AppNotificationKind.success,
      );
      await _load(requestedPage: existing == null ? 1 : _page);
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() => _error =
          saveFailureMessage(exception, 'quotation', changesKept: false));
    }
  }

  Future<void> _act(Quotation row, String action, {String? reason}) async {
    setState(() => _loading = true);
    try {
      final Quotation updated =
          await widget.api.quotationAction(row.id, action, reason: reason);
      if (!mounted) return;
      setState(() => _selected = updated);
      NotificationService.show(
        context,
        switch (action) {
          'send' => '${updated.quotationNumber} marked as sent. It stands '
              'until ${updated.validUntil}.',
          'accept' => '${updated.quotationNumber} accepted. Converting it is '
              'what creates the order.',
          'decline' => '${updated.quotationNumber} declined.',
          'cancel' => '${updated.quotationNumber} withdrawn.',
          _ => '${updated.quotationNumber} updated.',
        },
        kind: AppNotificationKind.success,
      );
      await _load();
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() => _error = exception.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _convert(Quotation row) async {
    setState(() => _loading = true);
    try {
      final QuotationConversion result =
          await widget.api.convertQuotation(row.id);
      if (!mounted) return;
      NotificationService.show(
        context,
        '${row.quotationNumber} became ${result.orderNumber}. The order '
        'reserves the stock when it is approved.',
        kind: AppNotificationKind.success,
      );
      setState(() => _selected = result.quotation);
      await _load();
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() => _error = exception.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _decide(Quotation row, String action, String title) async {
    final String? reason = await showDialog<String>(
      context: context,
      builder: (_) => _ReasonDialog(title: title, quotation: row),
    );
    if (reason == null) return;
    await _act(row, action, reason: reason);
  }

  @override
  Widget build(BuildContext context) {
    if (!_canView) {
      return const StandardEmptyState(
        type: EmptyStateType.noPermissions,
        title: 'Quotations',
        message: 'You do not have permission to view sales documents.',
      );
    }
    if (!widget.hasActiveFirm) {
      return const StandardEmptyState(
        type: EmptyStateType.noFirmSelected,
        title: 'Quotations',
        message: 'Choose a firm to see what it has offered.',
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
                decoration: const InputDecoration(
                  labelText: 'Search by quotation number',
                  prefixIcon: Icon(Icons.search),
                  hintText: 'QT-…',
                ),
                onSubmitted: (_) => unawaited(_load(requestedPage: 1)),
              ),
            ),
            const SizedBox(width: AppSpacing.md),
            if (_canQuote)
              FilledButton.icon(
                onPressed: () => unawaited(_writeQuotation()),
                icon: const Icon(Icons.request_quote_outlined),
                label: const Text('New Quotation'),
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
          child: _quotations.isEmpty
              ? const StandardEmptyState(
                  type: EmptyStateType.noRecords,
                  title: 'Nothing has been quoted',
                  message: 'A quotation is a price offered to a customer. It '
                      'reserves no stock and puts nothing on their account '
                      'until it becomes an order.',
                )
              : Row(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                  Expanded(flex: 3, child: _list()),
                  const VerticalDivider(width: 1),
                  Expanded(flex: 4, child: _detail(context)),
                ]),
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

  Widget _list() => ListView.separated(
        itemCount: _quotations.length,
        separatorBuilder: (_, __) => const Divider(height: 1),
        itemBuilder: (context, index) {
          final Quotation row = _quotations[index];
          return ListTile(
            selected: row.id == _selected?.id,
            title: Text('${row.quotationNumber}  ·  ${row.grandTotal}'),
            subtitle: Text(_standing(row)),
            trailing: Row(mainAxisSize: MainAxisSize.min, children: [
              // Expiry is the fact a status word cannot carry: SENT reads the
              // same the day before and the day after the prices lapse.
              if (row.isExpired && !row.isConverted && !row.isCancelled)
                const Padding(
                  padding: EdgeInsets.only(right: AppSpacing.sm),
                  child: StatusBadge(label: 'EXPIRED'),
                ),
              StatusBadge(label: row.status),
            ]),
            onTap: () => setState(() => _selected = row),
          );
        },
      );

  /// What has become of an offer, in one line.
  String _standing(Quotation row) {
    if (row.isConverted) return 'became ${row.convertedSalesOrderNumber}';
    if (row.isDeclined) {
      return row.declineReason.isEmpty
          ? 'declined'
          : 'declined — ${row.declineReason}';
    }
    if (row.isCancelled) return 'withdrawn';
    if (row.isExpired) return 'lapsed on ${row.validUntil}';
    return 'stands until ${row.validUntil}';
  }

  Widget _detail(BuildContext context) {
    final Quotation? row = _selected;
    if (row == null) {
      return const StandardEmptyState(
        type: EmptyStateType.noRecords,
        title: 'No quotation selected',
        message: 'Choose one to see what was offered and what came of it.',
      );
    }
    return SingleChildScrollView(
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(children: [
            Expanded(
              child: Text(row.quotationNumber,
                  style: Theme.of(context).textTheme.titleMedium),
            ),
            StatusBadge(label: row.status),
          ]),
          Text(_standing(row), style: Theme.of(context).textTheme.bodySmall),
          const SizedBox(height: AppSpacing.md),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(AppSpacing.md),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Offered', style: Theme.of(context).textTheme.labelLarge),
                  const SizedBox(height: AppSpacing.sm),
                  for (final QuotationLine line in row.lines)
                    Padding(
                      padding: const EdgeInsets.symmetric(vertical: 2),
                      child: Text(
                        '${line.quantity} × ${line.unitPrice} — '
                        '${line.description.isEmpty ? "line ${line.lineNumber}" : line.description}',
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                    ),
                  const Divider(),
                  Text('${row.subtotal} + ${row.taxTotal} tax = '
                      '${row.grandTotal}'),
                  if (row.paymentTerms.isNotEmpty)
                    Text('Payment: ${row.paymentTerms}',
                        style: Theme.of(context).textTheme.bodySmall),
                  if (row.deliveryTerms.isNotEmpty)
                    Text('Delivery: ${row.deliveryTerms}',
                        style: Theme.of(context).textTheme.bodySmall),
                ],
              ),
            ),
          ),
          const SizedBox(height: AppSpacing.md),
          // Said plainly, because a document that looks like an order is one
          // somebody will assume has reserved the goods.
          Text(
            row.isConverted
                ? 'The order ${row.convertedSalesOrderNumber} carries this '
                    'now; stock is reserved when that order is approved.'
                : 'Nothing is reserved and nothing is owed. Converting this '
                    'to an order is what commits the firm.',
            style: Theme.of(context).textTheme.bodySmall,
          ),
          const SizedBox(height: AppSpacing.md),
          _actions(row),
        ],
      ),
    );
  }

  Widget _actions(Quotation row) => Wrap(
        spacing: AppSpacing.sm,
        runSpacing: AppSpacing.sm,
        children: [
          if (row.isDraft && _canQuote)
            FilledButton(
              onPressed: () => unawaited(_act(row, 'send')),
              child: const Text('Mark as sent'),
            ),
          if ((row.isDraft || row.isSent) && _canQuote)
            OutlinedButton(
              onPressed: () => unawaited(_writeQuotation(existing: row)),
              child: const Text('Revise'),
            ),
          if ((row.isDraft || row.isSent) && !row.isExpired && _canDecide) ...[
            FilledButton(
              onPressed: () => unawaited(_decide(row, 'accept', 'Accept')),
              child: const Text('Customer accepted'),
            ),
            OutlinedButton(
              onPressed: () => unawaited(_decide(row, 'decline', 'Decline')),
              child: const Text('Customer declined'),
            ),
          ],
          if (row.canConvert && _canDecide)
            FilledButton.icon(
              onPressed: () => unawaited(_convert(row)),
              icon: const Icon(Icons.arrow_forward),
              label: const Text('Convert to order'),
            ),
          // An accepted quotation whose prices lapsed before anybody converted
          // it: the server refuses, so the button says why instead of failing.
          if (row.isAccepted && row.isExpired)
            const Tooltip(
              message: 'These prices have lapsed. Revise the quotation and '
                  'have it accepted again.',
              child: TextButton(onPressed: null, child: Text('Convert to order')),
            ),
          if (!row.isConverted && !row.isCancelled && _canCancel)
            TextButton(
              onPressed: () => unawaited(_decide(row, 'cancel', 'Withdraw')),
              child: const Text('Withdraw'),
            ),
        ],
      );
}

/// Why an offer was accepted, declined or withdrawn.
class _ReasonDialog extends StatefulWidget {
  const _ReasonDialog({required this.title, required this.quotation});

  final String title;
  final Quotation quotation;

  @override
  State<_ReasonDialog> createState() => _ReasonDialogState();
}

class _ReasonDialogState extends State<_ReasonDialog> {
  final TextEditingController _reason = TextEditingController();

  @override
  void dispose() {
    _reason.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: Text('${widget.title} ${widget.quotation.quotationNumber}'),
        content: Column(mainAxisSize: MainAxisSize.min, children: [
          Text(
            widget.title == 'Decline'
                // The one thing a quotation module knows that nothing else
                // does: why the firm is losing work.
                ? 'Why did they say no? It is the only place this is recorded.'
                : 'Anything worth noting alongside the decision.',
          ),
          const SizedBox(height: AppSpacing.md),
          TextField(
            controller: _reason,
            autofocus: true,
            decoration: const InputDecoration(labelText: 'Reason'),
          ),
        ]),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Back'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(_reason.text.trim()),
            child: Text(widget.title),
          ),
        ],
      );
}
