import 'package:flutter/material.dart';

enum GlobalSearchCategory {
  users,
  customers,
  products,
  invoices,
  reports,
}

extension GlobalSearchCategoryDetails on GlobalSearchCategory {
  String get label => switch (this) {
        GlobalSearchCategory.users => 'Users',
        GlobalSearchCategory.customers => 'Customers',
        GlobalSearchCategory.products => 'Products',
        GlobalSearchCategory.invoices => 'Invoices',
        GlobalSearchCategory.reports => 'Reports',
      };

  IconData get icon => switch (this) {
        GlobalSearchCategory.users => Icons.people_outline,
        GlobalSearchCategory.customers => Icons.storefront_outlined,
        GlobalSearchCategory.products => Icons.inventory_2_outlined,
        GlobalSearchCategory.invoices => Icons.receipt_long_outlined,
        GlobalSearchCategory.reports => Icons.assessment_outlined,
      };
}

class GlobalSearchRequest {
  const GlobalSearchRequest({required this.query, required this.category});

  final String query;
  final GlobalSearchCategory? category;
}

typedef GlobalSearchCallback = Future<void> Function(
  GlobalSearchRequest request,
);

Future<void> showGlobalSearch(
  BuildContext context, {
  GlobalSearchCallback? onSearch,
}) =>
    showDialog<void>(
      context: context,
      builder: (context) => _GlobalSearchDialog(onSearch: onSearch),
    );

class _GlobalSearchDialog extends StatefulWidget {
  const _GlobalSearchDialog({this.onSearch});

  final GlobalSearchCallback? onSearch;

  @override
  State<_GlobalSearchDialog> createState() => _GlobalSearchDialogState();
}

class _GlobalSearchDialogState extends State<_GlobalSearchDialog> {
  final TextEditingController _controller = TextEditingController();
  GlobalSearchCategory? _category;
  bool _searching = false;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _submit(String value) async {
    if (value.trim().isEmpty || widget.onSearch == null || _searching) return;
    setState(() => _searching = true);
    try {
      await widget.onSearch!(
        GlobalSearchRequest(query: value.trim(), category: _category),
      );
    } finally {
      if (mounted) setState(() => _searching = false);
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
          width: 640,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              TextField(
                controller: _controller,
                autofocus: true,
                enabled: !_searching,
                onSubmitted: _submit,
                decoration: const InputDecoration(
                  hintText:
                      'Search users, customers, products, invoices, reports',
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
                          : (selected) => setState(
                                () => _category = selected ? category : null,
                              ),
                    ),
                ],
              ),
              const SizedBox(height: 16),
              Text(
                widget.onSearch == null
                    ? 'Search integration will be enabled when module APIs are available.'
                    : 'Press Enter to search.',
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: _searching ? null : () => Navigator.pop(context),
            child: const Text('Close'),
          ),
          FilledButton.icon(
            onPressed: widget.onSearch == null || _searching
                ? null
                : () => _submit(_controller.text),
            icon: _searching
                ? const SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.search),
            label: const Text('Search'),
          ),
        ],
      );
}
