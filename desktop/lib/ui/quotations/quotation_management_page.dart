import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/api/concurrency.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/preferences/desktop_preferences_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/branch_warehouse.dart';
import '../../models/customer.dart';
import '../../models/entities.dart';
import '../../models/product.dart';
import '../../models/quotation.dart';
import '../workspace/desktop_framework.dart';
import '../workspace/printed_document.dart';
import '../settings/send_message_dialog.dart';
import 'quotation_editor_dialog.dart';

/// Prices offered to customers before anything is sold.
///
/// A quotation commits nothing — no stock is reserved, no balance moves, no
/// journal is written — so the screen never implies it has. What it does say,
/// prominently, is how long each offer stands: an expired quotation is the one
/// thing here that quietly stops being worth anything, and a list that showed
/// only its status would look identical the day before and the day after.
/// " less 10.00%" where a rate was resolved, nothing where none was: the
/// card printed `qty × price` and the totals, so the only way to read the
/// rate a line got was Revise (BL-31.14).
String _lessRate(String percent) {
  final double rate = double.tryParse(percent) ?? 0;
  return rate == 0 ? '' : ' less $percent%';
}

class QuotationManagementPage extends StatefulWidget {
  const QuotationManagementPage({
    super.key,
    required this.api,
    required this.preferences,
    required this.permissions,
    required this.hasActiveFirm,
    this.today,
  });

  final ApiClient api;

  /// Where the grid's chosen columns are remembered.
  final DesktopPreferencesService preferences;
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

  /// The quotation dates the list is narrowed to (owner, 2026-09-27).
  DatePeriod _period = const DatePeriod.all();
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
        quotationFrom:
            _period.from == null ? null : DatePeriod.iso(_period.from!),
        quotationTo: _period.to == null ? null : DatePeriod.iso(_period.to!),
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
      // Every customer and product, not the newest 20 and 100: an older
      // customer could not be quoted from here at all (D-SELL-18).
      final List<dynamic> results = await Future.wait<dynamic>([
        fetchAllPages<Customer>(
          (int page) => widget.api.customers(
            page: page,
            pageSize: maxApiPageSize,
            sortBy: 'name',
            descending: false,
          ),
        ),
        fetchAllPages<Product>(
          (int page) => widget.api.products(
            page: page,
            pageSize: maxApiPageSize,
            sortBy: 'name',
            descending: false,
          ),
        ),
        widget.api.branches(page: 1, pageSize: 100),
        widget.api.warehouses(page: 1, pageSize: 100),
      ]);
      customers = results[0] as List<Customer>;
      products = results[1] as List<Product>;
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
    // The firm's default for a new offer's "Rate includes GST" switch;
    // unreadable settings leave it off, as every offer was before.
    bool rateIncludesTax = false;
    if (existing == null && Phase2Scope.of(context)) {
      try {
        rateIncludesTax =
            (await widget.api.salesWorkflowSettings()).rateIncludesTax;
      } on ApiException {
        rateIncludesTax = false;
      }
      if (!mounted) return;
    }
    final Json? payload = await showDocument<Json>(
      context,
      title: existing == null ? 'New quotation' : 'Edit quotation',
      builder: (_) => QuotationEditorDialog(
        customers: customers,
        products: products,
        branches: branches,
        warehouses: warehouses,
        today: widget.today ?? DateTime.now(),
        existing: existing,
        rateIncludesTax: rateIncludesTax,
        // The firm's own fields on a quotation (MST-6).
        loadAttributes: () =>
            widget.api.applicableAttributeDefinitions('QUOTATION'),
        // Phase 2's screen prices the offer as it is typed.
        preview: Phase2Scope.of(context) ? widget.api.previewQuotation : null,
        // ...and shows what this customer is charged, and why.
        loadUnitPrices: Phase2Scope.of(context)
            ? ({
                required List<String> productIds,
                required String on,
                required String customerId,
              }) =>
                widget.api.unitPrices(
                  productIds: productIds,
                  on: on,
                  customerId: customerId,
                )
            : null,
      ),
    );
    if (payload == null) return;
    final bool printAfter =
        payload.remove(QuotationEditorDialog.printAfterSave) == true;
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
      if (printAfter) await _printQuotation(saved);
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
                decoration: const InputDecoration(
                  labelText: 'Search by quotation number or customer',
                  prefixIcon: Icon(Icons.search),
                  hintText: 'QT-…, shop name, code or phone',
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

  /// Phase 2 (owner, 2026-09-27): a full-width grid, as Sales Orders,
  /// Invoices and Delivery Notes -- the Period after the search, Columns,
  /// option C's bar naming the picked offer with its steps, and a
  /// double-click to read it. The side pane went: it took more width than
  /// the list to show an offer somebody had only pointed at.
  Widget _grid(BuildContext context) {
    final Quotation? selected = _selected;
    final bool open = selected != null && (selected.isDraft || selected.isSent);
    final bool decidable =
        selected != null && open && !selected.isExpired && _canDecide;
    return LoadingOverlay(
      loading: _loading,
      child: ManagementWorkspaceLayout(
        toolbar: WorkspaceToolbar(
          actions: const [
            ToolbarAction.newItem,
            ToolbarAction.view,
            ToolbarAction.refresh,
          ],
          isVisible: (action) => action != ToolbarAction.newItem || _canQuote,
          isEnabled: (action) =>
              !_loading &&
              switch (action) {
                ToolbarAction.newItem => _canQuote,
                ToolbarAction.view => selected != null,
                ToolbarAction.refresh => true,
                _ => false,
              },
          onAction: (action) {
            switch (action) {
              case ToolbarAction.newItem:
                unawaited(_writeQuotation());
              case ToolbarAction.view:
                if (selected != null) unawaited(_openQuotation(selected));
              case ToolbarAction.refresh:
                unawaited(_load());
              default:
                break;
            }
          },
          // Period right after the search, then Columns (owner).
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
          ],
          commands: [
            // On every offer whatever its state: a declined quotation is
            // still a document somebody may need to produce.
            ToolbarCommand(
              id: 'print',
              label: 'Print',
              icon: Icons.print_outlined,
              onPressed: selected == null
                  ? null
                  : () => unawaited(_printQuotation(selected)),
            ),
            // Emails the offer to the customer (MSG-4); "Mark as sent" only
            // moves the status.
            if (widget.permissions.hasPermission('DOCUMENT_SEND'))
              ToolbarCommand(
                id: 'email',
                label: 'Send',
                icon: Icons.forward_to_inbox_outlined,
                onPressed:
                    selected == null ? null : () => unawaited(_email(selected)),
              ),
            ToolbarCommand(
              id: 'send',
              label: 'Mark as sent',
              icon: Icons.send_outlined,
              onPressed: selected != null && selected.isDraft && _canQuote
                  ? () => unawaited(_act(selected, 'send'))
                  : null,
            ),
            ToolbarCommand(
              id: 'revise',
              label: 'Revise',
              icon: Icons.edit_outlined,
              onPressed: open && _canQuote
                  ? () => unawaited(_writeQuotation(existing: selected))
                  : null,
            ),
            ToolbarCommand(
              id: 'accept',
              label: 'Customer accepted',
              icon: Icons.thumb_up_outlined,
              onPressed: selected != null && decidable
                  ? () => unawaited(_decide(selected, 'accept', 'Accept'))
                  : null,
            ),
            ToolbarCommand(
              id: 'decline',
              label: 'Customer declined',
              icon: Icons.thumb_down_outlined,
              onPressed: selected != null && decidable
                  ? () => unawaited(_decide(selected, 'decline', 'Decline'))
                  : null,
            ),
            // An accepted offer whose prices lapsed is not offered: the
            // server refuses it, and the dialog says why.
            ToolbarCommand(
              id: 'convert',
              label: 'Convert to order',
              icon: Icons.arrow_forward,
              onPressed: selected != null && selected.canConvert && _canDecide
                  ? () => unawaited(_convert(selected))
                  : null,
            ),
            ToolbarCommand(
              id: 'withdraw',
              label: 'Withdraw',
              icon: Icons.block_outlined,
              onPressed: selected != null &&
                      !selected.isConverted &&
                      !selected.isCancelled &&
                      _canCancel
                  ? () => unawaited(_decide(selected, 'cancel', 'Withdraw'))
                  : null,
            ),
          ],
        ),
        selectionBar: true,
        selection: selected == null
            ? null
            : SelectionSummary.document(
                number: selected.quotationNumber,
                party: selected.customerName,
                status: selected.status,
                total: selected.grandTotal,
                onClear: () => setState(() => _selected = null),
              ),
        searchPanel: SearchFilterPanel(
          controller: _search,
          hintText: 'Search number or customer',
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
            child: _loading && _quotations.isEmpty
                ? const SizedBox.shrink()
                : _quotations.isEmpty
                ? (_search.text.trim().isEmpty && _period.from == null
                    ? const StandardEmptyState(
                        type: EmptyStateType.noRecords,
                        title: 'Nothing has been quoted',
                        message: 'A quotation is a price offered to a '
                            'customer. It reserves no stock and puts nothing '
                            'on their account until it becomes an order.',
                      )
                    : const StandardEmptyState(
                        type: EmptyStateType.noSearchResults,
                      ))
                : EnterpriseDataGrid<Quotation>(
                    columns: _columns.gridColumns,
                    items: _quotations,
                    id: (item) => item.id,
                    selectedId: selected?.id,
                    cells: _columns.cells,
                    onSelect: (item) => setState(() => _selected = item),
                    onOpen: (item) => unawaited(_openQuotation(item)),
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

  /// Every column the grid can show; Columns picks among them, remembered
  /// per screen on this PC (owner, 2026-09-27).
  late final ColumnChoice<Quotation> _columns = ColumnChoice(
    preferences: widget.preferences,
    stateKey: 'quotations.grid',
    columns: [
      ChoosableColumn(
        column: const GridColumn(key: 'number', label: 'Quotation Number'),
        cell: (item) => item.quotationNumber,
        required: true,
      ),
      // Whose offer it is; kept at any width.
      ChoosableColumn(
        column:
            const GridColumn(key: 'customer', label: 'Customer', priority: 1),
        cell: (item) => item.customerName,
        shownByDefault: true,
      ),
      // One date: the quotation's, with the minute it was entered.
      ChoosableColumn(
        column: const GridColumn(key: 'date', label: 'Quotation Date'),
        cell: (item) => documentDateStamp(item.quotationDate, item.createdAt),
        shownByDefault: true,
      ),
      // How long the offer stands is what a status word cannot carry: SENT
      // reads the same the day before and the day after the prices lapse.
      ChoosableColumn(
        column: const GridColumn(key: 'valid', label: 'Valid Until'),
        cell: (item) =>
            _lapsed(item) ? '${item.validUntil} · lapsed' : item.validUntil,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'status', label: 'Status'),
        cell: (item) => item.status,
        shownByDefault: true,
      ),
      // What came of it: the order it became, or why it was declined.
      ChoosableColumn(
        column: const GridColumn(key: 'outcome', label: 'Outcome'),
        cell: _standing,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'reference', label: 'Their Reference'),
        cell: (item) => item.customerReference,
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
        column: const GridColumn(
            key: 'subtotal', label: 'Taxable Value', numeric: true),
        cell: (item) => item.subtotal,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'tax', label: 'Tax', numeric: true),
        cell: (item) => item.taxTotal,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'total', label: 'Grand Total'),
        cell: (item) => item.grandTotal,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'remarks', label: 'Remarks'),
        cell: (item) => item.remarks,
      ),
    ],
  );

  /// Lapsed and still open: converted or withdrawn offers have no deadline
  /// left to miss.
  bool _lapsed(Quotation row) =>
      row.isExpired && !row.isConverted && !row.isCancelled;

  /// Read one offer: what was offered and what came of it. Its steps stay on
  /// the bar above the grid, so this only reads.
  Future<void> _openQuotation(Quotation row) async {
    setState(() => _selected = row);
    await showDialog<void>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Row(children: [
          Expanded(child: Text(row.quotationNumber)),
          if (_lapsed(row))
            const Padding(
              padding: EdgeInsets.only(right: AppSpacing.sm),
              child: StatusBadge(label: 'EXPIRED'),
            ),
          StatusBadge.fromStatus(row.status),
        ]),
        content: SizedBox(
          width: 560,
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                if (_customer(row).isNotEmpty) Text(_customer(row)),
                ..._facts(dialogContext, row),
                // The server refuses to convert lapsed prices; say so here,
                // since the bar does not offer the step at all.
                if (row.isAccepted && row.isExpired) ...[
                  const SizedBox(height: AppSpacing.sm),
                  Text(
                    'These prices have lapsed. Revise the quotation and have '
                    'it accepted again before converting it.',
                    style: Theme.of(dialogContext).textTheme.bodySmall,
                  ),
                ],
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
      ),
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
            // Whose it is first: the owner asked the list to say so (and
            // search finds a quotation by its customer too).
            subtitle: Text(
              [
                if (_customer(row).isNotEmpty) _customer(row),
                // The minute it was made tells today's quotations apart.
                _withStamp(_standing(row), row.createdAt),
              ].join('\n'),
            ),
            isThreeLine: _customer(row).isNotEmpty,
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

  /// The customer as the list shows them: name, then code.
  String _customer(Quotation row) => [
        if (row.customerName.isNotEmpty) row.customerName,
        if (row.customerCode.isNotEmpty) row.customerCode,
      ].join('  ·  ');

  /// What has become of an offer, in one line.
  String _withStamp(String text, String createdAt) {
    final String stamp = createdStamp(createdAt);
    return stamp.isEmpty ? text : '$text  ·  made $stamp';
  }

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
          ..._facts(context, row),
          const SizedBox(height: AppSpacing.md),
          _actions(row),
        ],
      ),
    );
  }

  /// What was offered and what came of it -- the side pane's body, and the
  /// whole of phase 2's dialog.
  List<Widget> _facts(BuildContext context, Quotation row) => [
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
                      '${line.quantity} × ${line.unitPrice}'
                      '${_lessRate(line.discountPercent)} — '
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
      ];

  /// Email the offer to its customer (MSG-4).
  Future<void> _email(Quotation row) async {
    await showDialog<bool>(
      context: context,
      builder: (_) => SendMessageDialog(
        api: widget.api,
        invoiceId: row.id,
        invoiceNumber: row.quotationNumber,
        documentType: 'SALES_QUOTATION',
      ),
    );
  }

  /// Render the offer and hand it to whatever prints on this machine.
  Future<void> _printQuotation(Quotation row) async {
    try {
      final List<int> pdf = await widget.api.quotationPdf(row.id);
      if (!mounted) return;
      await printDocument(
        context,
        bytes: pdf,
        documentName: row.quotationNumber,
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

  Widget _actions(Quotation row) => Wrap(
        spacing: AppSpacing.sm,
        runSpacing: AppSpacing.sm,
        children: [
          // On every offer whatever its state: a declined quotation is still
          // a document somebody may need to produce.
          OutlinedButton.icon(
            onPressed: () => unawaited(_printQuotation(row)),
            icon: const Icon(Icons.print_outlined, size: 18),
            label: const Text('Print'),
          ),
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
              child:
                  TextButton(onPressed: null, child: Text('Convert to order')),
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
