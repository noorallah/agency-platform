import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/customer.dart';
import '../../models/entities.dart';
import '../../models/pricing.dart';
import '../../models/product.dart';
import '../workspace/desktop_framework.dart';
import 'price_list_dialog.dart';

/// What a firm has agreed to charge, and to whom.
///
/// A product carries one selling price and a customer can be put on one
/// blanket rate. A price list is the arrangement between those two: this
/// customer, or everyone on this round, on these products, from this date.
///
/// The list holds **rates off the product's price** rather than prices of its
/// own, which is why every figure on this screen is a percentage. Saying so on
/// screen matters: somebody expecting to type a price will otherwise enter one
/// into a discount column.
class PriceListPage extends StatefulWidget {
  const PriceListPage({
    super.key,
    required this.api,
    required this.permissions,
    required this.hasActiveFirm,
  });

  final ApiClient api;
  final PermissionService permissions;
  final bool hasActiveFirm;

  @override
  State<PriceListPage> createState() => _PriceListPageState();
}

class _PriceListPageState extends State<PriceListPage> {
  final TextEditingController _search = TextEditingController();

  List<PriceListRecord> _rows = const [];
  List<Customer> _customers = const [];
  List<Product> _products = const [];
  PriceListRecord? _selected;
  int _total = 0;
  int _page = 1;
  bool _loading = true;
  String? _error;

  bool get _mayManage => widget.permissions.hasPermission('PRICE_LIST_MANAGE');

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
    if (!widget.hasActiveFirm) {
      setState(() => _loading = false);
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
      if (requestedPage != null) _page = requestedPage;
    });
    try {
      final PagedResult<PriceListRecord> page = await widget.api.priceLists(
        page: _page,
        search: _search.text,
      );
      // The pickers need every customer and product, so they are paged
      // through rather than asked for in one over-cap page.
      final List<Customer> customers = _customers.isNotEmpty
          ? _customers
          : await fetchAllPages<Customer>((p) => widget.api.customers(page: p));
      final List<Product> products = _products.isNotEmpty
          ? _products
          : await fetchAllPages<Product>((p) => widget.api.products(page: p));
      if (!mounted) return;
      setState(() {
        _rows = page.items;
        _total = page.total;
        _customers = customers;
        _products = products;
        _loading = false;
        // Keep the selection only if it survived the reload.
        _selected = _rows
            .where((row) => row.id == _selected?.id)
            .cast<PriceListRecord?>()
            .firstWhere((row) => true, orElse: () => null);
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.message;
        _loading = false;
      });
    }
  }

  Future<void> _edit({PriceListRecord? existing}) async {
    final bool? saved = await showDialog<bool>(
      context: context,
      builder: (_) => PriceListDialog(
        api: widget.api,
        customers: _customers,
        products: _products,
        existing: existing,
      ),
    );
    if (saved != true) return;
    if (!mounted) return;
    NotificationService.show(
      context,
      existing == null ? 'Price list created.' : 'Price list saved.',
      kind: AppNotificationKind.success,
    );
    await _load();
  }

  Future<void> _delete(PriceListRecord row) async {
    try {
      await widget.api.deletePriceList(row.id);
      if (!mounted) return;
      NotificationService.show(
        context,
        '${row.code} withdrawn. Documents already priced under it are '
        'unchanged — the rate is stored on the line.',
        kind: AppNotificationKind.success,
      );
      await _load();
    } on ApiException catch (error) {
      if (!mounted) return;
      NotificationService.show(
        context,
        error.message,
        kind: AppNotificationKind.error,
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.hasActiveFirm) {
      return const StandardEmptyState(type: EmptyStateType.noFirmSelected);
    }
    return ManagementWorkspaceLayout(
      toolbar: Wrap(
        spacing: 8,
        children: [
          if (_mayManage)
            FilledButton.icon(
              onPressed: () => unawaited(_edit()),
              icon: const Icon(Icons.add),
              label: const Text('New price list'),
            ),
          OutlinedButton.icon(
            onPressed: () => unawaited(_load()),
            icon: const Icon(Icons.refresh),
            label: const Text('Refresh'),
          ),
        ],
      ),
      searchPanel: SearchFilterPanel(
        controller: _search,
        hintText: 'Search by code or name...',
        onSearch: (_) => unawaited(_load(requestedPage: 1)),
      ),
      primaryContent: _content(),
      detailsPanel: _selected == null ? null : _details(_selected!),
      statusBar: WorkspaceStatusBar(
        total: _total,
        selected: _selected != null,
        message: _loading ? 'Loading...' : null,
      ),
    );
  }

  Widget _content() {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_error != null) {
      return WorkspaceEmptyState(
        title: 'Price lists unavailable',
        message: _error!,
      );
    }
    if (_rows.isEmpty) {
      return WorkspaceEmptyState(
        title: _search.text.trim().isEmpty
            ? 'No price lists yet'
            : 'Nothing matches that search',
        message: 'A price list is a rate off the product price, for one '
            'customer, one territory, or everybody — from a date.',
      );
    }
    return EnterpriseDataGrid<PriceListRecord>(
      items: _rows,
      total: _total,
      pageOffset: (_page - 1) * 20,
      rowsPerPage: 20,
      selectedId: _selected?.id,
      columns: const [
        GridColumn(key: 'code', label: 'Code'),
        GridColumn(key: 'name', label: 'Name'),
        GridColumn(key: 'scope', label: 'Applies to'),
        GridColumn(key: 'window', label: 'In force'),
        GridColumn(key: 'items', label: 'Products'),
        GridColumn(key: 'status', label: 'Status'),
      ],
      id: (row) => row.id,
      cells: (row) => [
        row.code,
        row.name,
        row.scopeLabel,
        row.windowLabel,
        '${row.items.length}',
        row.status,
      ],
      onSelect: (row) => setState(() => _selected = row),
      onPageChanged: (page) => unawaited(_load(requestedPage: page)),
      contextActions: const [
        WorkspaceContextAction.edit,
        WorkspaceContextAction.delete,
      ],
      onContextAction: (action, row) {
        if (!_mayManage) return;
        if (action == WorkspaceContextAction.edit) unawaited(_edit(existing: row));
        if (action == WorkspaceContextAction.delete) unawaited(_delete(row));
      },
    );
  }

  Widget _details(PriceListRecord row) {
    final ThemeData theme = Theme.of(context);
    return SingleChildScrollView(
      padding: const EdgeInsets.all(AppSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(row.name, style: theme.textTheme.titleMedium),
          Text('${row.code} · applies to ${row.scopeLabel}',
              style: theme.textTheme.bodySmall),
          const SizedBox(height: AppSpacing.sm),
          Text('In force ${row.windowLabel}', style: theme.textTheme.bodySmall),
          if (row.description.isNotEmpty) ...[
            const SizedBox(height: AppSpacing.sm),
            Text(row.description, style: theme.textTheme.bodyMedium),
          ],
          const SizedBox(height: AppSpacing.md),
          Text('Rates', style: theme.textTheme.titleSmall),
          const SizedBox(height: AppSpacing.xs),
          if (row.items.isEmpty)
            Text(
              'No products yet. A list with no rates changes nothing.',
              style: theme.textTheme.bodySmall,
            ),
          for (final PriceListItemRecord item in row.items)
            Padding(
              padding: const EdgeInsets.only(bottom: AppSpacing.xs),
              child: Row(
                children: [
                  Expanded(child: Text(item.label)),
                  Text('${item.discountPercent}%'),
                ],
              ),
            ),
        ],
      ),
    );
  }
}
