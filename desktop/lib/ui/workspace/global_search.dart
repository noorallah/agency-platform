import 'package:flutter/material.dart';

import '../workspace/workspace_interactions.dart';

enum GlobalSearchCategory {
  all,
  masters,
  inventory,
  tax,
  organization,
  products,
  warehouses,
  branches,
}

extension GlobalSearchCategoryDetails on GlobalSearchCategory {
  String get label => switch (this) {
        GlobalSearchCategory.all => 'All',
        GlobalSearchCategory.masters => 'Masters',
        GlobalSearchCategory.inventory => 'Inventory',
        GlobalSearchCategory.tax => 'Tax',
        GlobalSearchCategory.organization => 'Organization',
        GlobalSearchCategory.products => 'Products',
        GlobalSearchCategory.warehouses => 'Warehouses',
        GlobalSearchCategory.branches => 'Branches',
      };

  IconData get icon => switch (this) {
        GlobalSearchCategory.all => Icons.apps_outlined,
        GlobalSearchCategory.masters => Icons.folder_copy_outlined,
        GlobalSearchCategory.inventory => Icons.inventory_2_outlined,
        GlobalSearchCategory.tax => Icons.receipt_long_outlined,
        GlobalSearchCategory.organization => Icons.apartment_outlined,
        GlobalSearchCategory.products => Icons.inventory_outlined,
        GlobalSearchCategory.warehouses => Icons.warehouse_outlined,
        GlobalSearchCategory.branches => Icons.account_tree_outlined,
      };
}

enum GlobalSearchAction {
  openInventory,
  viewLedger,
  viewTransactions,
  copyProductCode,
  copyInventoryId,
}

extension GlobalSearchActionDetails on GlobalSearchAction {
  String get label => switch (this) {
        GlobalSearchAction.openInventory => 'Open Inventory',
        GlobalSearchAction.viewLedger => 'View Ledger',
        GlobalSearchAction.viewTransactions => 'View Transactions',
        GlobalSearchAction.copyProductCode => 'Copy Product Code',
        GlobalSearchAction.copyInventoryId => 'Copy Inventory ID',
      };

  IconData get icon => switch (this) {
        GlobalSearchAction.openInventory => Icons.open_in_new,
        GlobalSearchAction.viewLedger => Icons.receipt_long_outlined,
        GlobalSearchAction.viewTransactions => Icons.swap_horiz_outlined,
        GlobalSearchAction.copyProductCode => Icons.copy_outlined,
        GlobalSearchAction.copyInventoryId => Icons.copy_all_outlined,
      };
}

class GlobalSearchRequest {
  const GlobalSearchRequest({
    required this.query,
    required this.category,
    this.page = 1,
    this.pageSize = 20,
    this.entityTypes = const [],
  });

  final String query;
  final GlobalSearchCategory category;
  final int page;
  final int pageSize;
  final List<String> entityTypes;
}

class GlobalSearchResultItem {
  const GlobalSearchResultItem({
    required this.id,
    required this.title,
    this.subtitle = '',
    this.currentStock = '',
    this.availableStock = '',
    this.branch = '',
    this.warehouse = '',
    this.status = '',
    this.productCode = '',
    this.inventoryId = '',
    this.entityType = '',
    this.module = '',
    this.tab,
    this.badges = const [],
    this.matchedFields = const [],
    this.navigationPath,
    this.icon = Icons.inventory_2_outlined,
    this.onOpen,
    this.onAction,
  });

  final String id;
  final String title;
  final String subtitle;
  final String currentStock;
  final String availableStock;
  final String branch;
  final String warehouse;
  final String status;
  final String productCode;
  final String inventoryId;
  final String entityType;
  final String module;
  final String? tab;
  final List<String> badges;
  final List<String> matchedFields;
  final String? navigationPath;
  final IconData icon;
  final Future<void> Function()? onOpen;
  final Future<void> Function(GlobalSearchAction action)? onAction;
}

class GlobalSearchResponse {
  const GlobalSearchResponse({
    required this.results,
    this.message,
    this.page = 1,
    this.pageSize = 20,
    this.total = 0,
  });

  final List<GlobalSearchResultItem> results;
  final String? message;
  final int page;
  final int pageSize;
  final int total;
}

typedef GlobalSearchExecutor = Future<GlobalSearchResponse> Function(
  GlobalSearchRequest request,
);

Future<void> showGlobalSearch(
  BuildContext context, {
  GlobalSearchExecutor? executor,
  List<String> initialRecentQueries = const [],
  List<String> initialSavedQueries = const [],
  Future<void> Function(List<String> values)? onRecentQueriesChanged,
  Future<void> Function(List<String> values)? onSavedQueriesChanged,
}) =>
    showDialog<void>(
      context: context,
      builder: (context) => _GlobalSearchDialog(
        executor: executor,
        initialRecentQueries: initialRecentQueries,
        initialSavedQueries: initialSavedQueries,
        onRecentQueriesChanged: onRecentQueriesChanged,
        onSavedQueriesChanged: onSavedQueriesChanged,
      ),
    );

class _GlobalSearchDialog extends StatefulWidget {
  const _GlobalSearchDialog({
    this.executor,
    this.initialRecentQueries = const [],
    this.initialSavedQueries = const [],
    this.onRecentQueriesChanged,
    this.onSavedQueriesChanged,
  });

  final GlobalSearchExecutor? executor;
  final List<String> initialRecentQueries;
  final List<String> initialSavedQueries;
  final Future<void> Function(List<String> values)? onRecentQueriesChanged;
  final Future<void> Function(List<String> values)? onSavedQueriesChanged;

  @override
  State<_GlobalSearchDialog> createState() => _GlobalSearchDialogState();
}

class _GlobalSearchDialogState extends State<_GlobalSearchDialog> {
  final TextEditingController _controller = TextEditingController();
  final FocusNode _searchFocus = FocusNode();
  final TextEditingController _advancedTypesController = TextEditingController();
  GlobalSearchCategory _category = GlobalSearchCategory.all;
  bool _searching = false;
  bool _showAdvanced = false;
  String? _message;
  List<GlobalSearchResultItem> _results = const [];
  int _selectedIndex = -1;
  int _page = 1;
  int _pageSize = 20;
  int _total = 0;
  String _lastQuery = '';
  late List<String> _recentQueries;
  late List<String> _savedQueries;

  @override
  void initState() {
    super.initState();
    _recentQueries = [...widget.initialRecentQueries];
    _savedQueries = [...widget.initialSavedQueries];
  }

  @override
  void dispose() {
    _controller.dispose();
    _searchFocus.dispose();
    _advancedTypesController.dispose();
    super.dispose();
  }

  Future<void> _submit({String? value, int? page}) async {
    final String query = (value ?? _controller.text).trim();
    if (query.isEmpty || widget.executor == null || _searching) return;
    final int nextPage = page ?? _page;
    setState(() {
      _searching = true;
      _message = null;
      _selectedIndex = -1;
      _page = nextPage;
      _lastQuery = query;
    });
    try {
      final List<String> entityTypes = _advancedTypesController.text
          .split(',')
          .map((value) => value.trim())
          .where((value) => value.isNotEmpty)
          .toList();
      final GlobalSearchResponse response = await widget.executor!(
        GlobalSearchRequest(
          query: query,
          category: _category,
          page: nextPage,
          pageSize: _pageSize,
          entityTypes: entityTypes,
        ),
      );
      if (!mounted) return;
      setState(() {
        _results = response.results;
        _message = response.message;
        _total = response.total;
        _page = response.page;
        _pageSize = response.pageSize;
        _selectedIndex = _results.isEmpty ? -1 : 0;
      });
      await _rememberRecentQuery(query);
    } finally {
      if (mounted) setState(() => _searching = false);
    }
  }

  Future<void> _rememberRecentQuery(String query) async {
    final List<String> values = [
      query,
      ..._recentQueries.where((item) => item != query),
    ].take(8).toList();
    _recentQueries = values;
    await widget.onRecentQueriesChanged?.call(values);
  }

  Future<void> _saveCurrentQuery() async {
    final String query = _controller.text.trim();
    if (query.isEmpty) return;
    final List<String> values = [
      query,
      ..._savedQueries.where((item) => item != query),
    ].take(16).toList();
    setState(() => _savedQueries = values);
    await widget.onSavedQueriesChanged?.call(values);
  }

  Future<void> _runAction(
    GlobalSearchResultItem item,
    GlobalSearchAction action,
  ) async {
    switch (action) {
      case GlobalSearchAction.copyProductCode:
        await copyTextToClipboard(item.productCode);
        break;
      case GlobalSearchAction.copyInventoryId:
        await copyTextToClipboard(item.inventoryId.isEmpty ? item.id : item.inventoryId);
        break;
      default:
        if (item.onAction != null) {
          await item.onAction!(action);
        }
        break;
    }
  }

  Future<void> _openSelected() async {
    if (_selectedIndex < 0 || _selectedIndex >= _results.length) return;
    final Future<void> Function()? onOpen = _results[_selectedIndex].onOpen;
    if (onOpen != null) {
      await onOpen();
    }
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: const Row(children: [
          Icon(Icons.manage_search),
          SizedBox(width: 12),
          Text('Global search'),
        ]),
        content: SizedBox(
          width: 980,
          height: 700,
          child: WorkspaceShortcuts(
            bindings: WorkspaceShortcutBindings(
              focusSearch: _searchFocus.requestFocus,
              globalSearch: _searchFocus.requestFocus,
              advancedSearch: () => setState(() => _showAdvanced = !_showAdvanced),
              copy: _selectedIndex < 0 || _selectedIndex >= _results.length
                  ? null
                  : () => copyTextToClipboard(_results[_selectedIndex].title),
              save: _saveCurrentQuery,
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                TextField(
                  controller: _controller,
                  focusNode: _searchFocus,
                  autofocus: true,
                  enabled: !_searching,
                  onSubmitted: (value) => _submit(value: value, page: 1),
                  decoration: const InputDecoration(
                    hintText:
                        'Search across users, firms, profiles, products, inventory, tax, UOM, batches, geo masters, and settings',
                    prefixIcon: Icon(Icons.search),
                  ),
                ),
                const SizedBox(height: 12),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    for (final GlobalSearchCategory category
                        in GlobalSearchCategory.values)
                      ChoiceChip(
                        avatar: Icon(category.icon, size: 18),
                        label: Text(category.label),
                        selected: _category == category,
                        onSelected: _searching
                            ? null
                            : (selected) {
                                if (!selected) return;
                                setState(() => _category = category);
                              },
                      ),
                  ],
                ),
                if (_showAdvanced) ...[
                  const SizedBox(height: 10),
                  TextField(
                    controller: _advancedTypesController,
                    enabled: !_searching,
                    decoration: const InputDecoration(
                      prefixIcon: Icon(Icons.tune),
                      hintText:
                          'Advanced entity filter (comma-separated): users,products,tax_rules,batch,...',
                    ),
                  ),
                ],
                const SizedBox(height: 8),
                if (_savedQueries.isNotEmpty)
                  _queryChipRow(
                    context,
                    'Saved',
                    _savedQueries,
                  ),
                if (_recentQueries.isNotEmpty)
                  _queryChipRow(
                    context,
                    'Recent',
                    _recentQueries,
                  ),
                const SizedBox(height: 8),
                if (_message?.isNotEmpty == true)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 8),
                    child: Text(
                      _message!,
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ),
                Expanded(
                  child: _results.isEmpty
                      ? Center(
                          child: Text(
                            widget.executor == null
                                ? 'Search integration will be enabled when module APIs are available.'
                                : 'Press Enter to search.',
                            style: Theme.of(context).textTheme.bodySmall,
                          ),
                        )
                      : ListView.separated(
                          itemCount: _results.length,
                          separatorBuilder: (_, __) => const SizedBox(height: 8),
                          itemBuilder: (context, index) {
                            final GlobalSearchResultItem item = _results[index];
                            final bool selected = index == _selectedIndex;
                            return InkWell(
                              onTap: () => setState(() => _selectedIndex = index),
                              onDoubleTap: item.onOpen == null
                                  ? null
                                  : () async => item.onOpen!(),
                              child: Card(
                                color: selected
                                    ? Theme.of(context)
                                        .colorScheme
                                        .primaryContainer
                                        .withValues(alpha: .45)
                                    : null,
                                child: Padding(
                                  padding: const EdgeInsets.all(14),
                                  child: Row(
                                    crossAxisAlignment: CrossAxisAlignment.start,
                                    children: [
                                      CircleAvatar(
                                        child: Icon(item.icon),
                                      ),
                                      const SizedBox(width: 12),
                                      Expanded(
                                        child: Column(
                                          crossAxisAlignment: CrossAxisAlignment.start,
                                          children: [
                                            _highlightedText(
                                              context,
                                              item.title,
                                              _lastQuery,
                                              Theme.of(context).textTheme.titleMedium,
                                            ),
                                            if (item.subtitle.isNotEmpty) ...[
                                              const SizedBox(height: 4),
                                              _highlightedText(
                                                context,
                                                item.subtitle,
                                                _lastQuery,
                                                null,
                                              ),
                                            ],
                                            const SizedBox(height: 8),
                                            Wrap(
                                              spacing: 8,
                                              runSpacing: 8,
                                              children: [
                                                if (item.entityType.isNotEmpty)
                                                  _metaChip('Type', item.entityType),
                                                if (item.status.isNotEmpty)
                                                  _metaChip('Status', item.status),
                                                if (item.branch.isNotEmpty)
                                                  _metaChip('Branch', item.branch),
                                                if (item.warehouse.isNotEmpty)
                                                  _metaChip('Warehouse', item.warehouse),
                                                if (item.currentStock.isNotEmpty)
                                                  _metaChip('Current', item.currentStock),
                                                if (item.availableStock.isNotEmpty)
                                                  _metaChip('Available', item.availableStock),
                                                for (final String badge in item.badges)
                                                  _metaChip('Badge', badge),
                                                if (item.matchedFields.isNotEmpty)
                                                  _metaChip(
                                                    'Match',
                                                    item.matchedFields.join(', '),
                                                  ),
                                              ],
                                            ),
                                          ],
                                        ),
                                      ),
                                      const SizedBox(width: 12),
                                      PopupMenuButton<GlobalSearchAction>(
                                        tooltip: 'Search actions',
                                        onSelected: (action) => _runAction(item, action),
                                        itemBuilder: (context) => [
                                          for (final GlobalSearchAction action
                                              in GlobalSearchAction.values)
                                            PopupMenuItem<GlobalSearchAction>(
                                              value: action,
                                              child: Row(
                                                children: [
                                                  Icon(action.icon, size: 18),
                                                  const SizedBox(width: 8),
                                                  Text(action.label),
                                                ],
                                              ),
                                            ),
                                        ],
                                      ),
                                    ],
                                  ),
                                ),
                              ),
                            );
                          },
                        ),
                ),
              ],
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: _searching ? null : () => Navigator.pop(context),
            child: const Text('Close'),
          ),
          TextButton.icon(
            onPressed: _searching ? null : _saveCurrentQuery,
            icon: const Icon(Icons.bookmark_add_outlined),
            label: const Text('Save Search'),
          ),
          if (_results.isNotEmpty)
            TextButton.icon(
              onPressed: _selectedIndex < 0 || _selectedIndex >= _results.length
                  ? null
                  : () => _runAction(
                        _results[_selectedIndex],
                        GlobalSearchAction.copyInventoryId,
                      ),
              icon: const Icon(Icons.copy_all_outlined),
              label: const Text('Copy ID'),
            ),
          FilledButton.icon(
            onPressed: widget.executor == null || _searching
                ? null
                : () => _submit(value: _controller.text, page: 1),
            icon: _searching
                ? const SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.search),
            label: const Text('Search'),
          ),
          if (_results.isNotEmpty)
            FilledButton.tonalIcon(
              onPressed: _openSelected,
              icon: const Icon(Icons.visibility_outlined),
              label: const Text('Open Details'),
            ),
          if (_results.isNotEmpty)
            FilledButton.tonalIcon(
              onPressed: _page > 1 ? () => _submit(page: _page - 1) : null,
              icon: const Icon(Icons.chevron_left),
              label: const Text('Prev'),
            ),
          if (_results.isNotEmpty)
            FilledButton.tonalIcon(
              onPressed: _page * _pageSize < _total ? () => _submit(page: _page + 1) : null,
              icon: const Icon(Icons.chevron_right),
              label: const Text('Next'),
            ),
        ],
      );

  Widget _metaChip(String label, String value) => Chip(
        label: Text('$label: $value'),
      );

  Widget _queryChipRow(BuildContext context, String label, List<String> values) => Padding(
        padding: const EdgeInsets.only(top: 6),
        child: Wrap(
          spacing: 6,
          runSpacing: 6,
          children: [
            Text(
              '$label:',
              style: Theme.of(context).textTheme.bodySmall,
            ),
            for (final String value in values)
              ActionChip(
                avatar: const Icon(Icons.history, size: 14),
                label: Text(value),
                onPressed: _searching
                    ? null
                    : () {
                        _controller.text = value;
                        _submit(value: value, page: 1);
                      },
              ),
          ],
        ),
      );

  Widget _highlightedText(
    BuildContext context,
    String value,
    String query,
    TextStyle? style,
  ) {
    if (query.isEmpty) {
      return Text(value, style: style);
    }
    final String lowerValue = value.toLowerCase();
    final String lowerQuery = query.toLowerCase();
    final int index = lowerValue.indexOf(lowerQuery);
    if (index < 0) {
      return Text(value, style: style);
    }
    final TextStyle base = style ?? Theme.of(context).textTheme.bodyMedium!;
    final TextStyle highlighted = base.copyWith(
      backgroundColor: Theme.of(context).colorScheme.secondaryContainer,
      fontWeight: FontWeight.w600,
    );
    return Text.rich(
      TextSpan(
        children: [
          TextSpan(text: value.substring(0, index), style: base),
          TextSpan(
            text: value.substring(index, index + query.length),
            style: highlighted,
          ),
          TextSpan(text: value.substring(index + query.length), style: base),
        ],
      ),
    );
  }
}

