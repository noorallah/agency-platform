import 'package:flutter/material.dart';

import 'menu_layout.dart';

/// One tile on Home: a document list, the figures from its summary that
/// somebody acts on, and the screen it opens.
class HomeTile {
  const HomeTile(this.path, this.figures);

  /// The screen, as the menu addresses it.
  final String path;

  /// (label, summary key, whether a non-zero value needs acting on).
  final List<(String, String, bool)> figures;
}

/// Home in the phase 2 app (UI_PHASE_2_DESIGN.md 4.9).
///
/// Phase 1's Dashboard counts firms, users and roles across the platform and
/// is offered only to a platform administrator, so everybody else had no
/// Home at all -- the owner's first report on phase 2. This one is for
/// everybody: today's figures from the lists the user may open, and their
/// daily screens a click away. Cards live here and only here (4.5): Home is
/// where somebody goes to look at numbers, a list is where they work.
class Phase2HomePage extends StatefulWidget {
  const Phase2HomePage({
    super.key,
    required this.firmName,
    required this.userName,
    required this.allowed,
    required this.loadSummary,
    required this.onOpen,
  });

  final String? firmName;
  final String? userName;

  /// Whether the user may open a screen -- the menu's own answer (4.12).
  final bool Function(String path) allowed;

  /// The summary behind a tile, by its screen's path.
  final Future<Map<String, dynamic>> Function(String path) loadSummary;
  final ValueChanged<MenuItemSpec> onOpen;

  /// The document lists Home reports on, in the order of a trading day.
  static const List<HomeTile> tiles = [
    HomeTile('salesInvoices/sales-invoices', [
      ('Overdue', 'overdue_invoices', true),
      ('Pending', 'pending_invoices', false),
      ('Draft', 'draft', false),
    ]),
    HomeTile('salesOrders', [
      ('Draft', 'draft', false),
      ('Approved', 'approved', false),
    ]),
    HomeTile('deliveryNotes/delivery-notes', [
      ('Orders to deliver', 'pending_orders', true),
      ('Draft', 'draft', false),
    ]),
    HomeTile('goodsReceipts/receipts', [
      ('POs to receive', 'pending_purchase_orders', true),
      ('Draft', 'draft', false),
    ]),
    HomeTile('purchaseInvoices', [
      ('Overdue', 'overdue_invoices', true),
      ('Pending', 'pending_invoices', false),
    ]),
    HomeTile('purchaseReturns', [
      ('Draft', 'draft', false),
      ('Approved', 'approved', false),
    ]),
  ];

  /// The daily screens of 4.6, offered as one-click buttons.
  static const List<String> daily = [
    'salesInvoices/sales-invoices',
    'accounting/receipts',
    'salesOrders',
    'quotations',
    'deliveryNotes/delivery-notes',
    'goodsReceipts/receipts',
    'purchaseInvoices',
    'accounting/payments',
    'inventory/inventory',
    'masters/customer-statements',
    'masters/customers',
    'masters/products',
    // A platform administrator's own overview.
    'dashboard',
  ];

  @override
  State<Phase2HomePage> createState() => _Phase2HomePageState();
}

class _Phase2HomePageState extends State<Phase2HomePage> {
  /// Each tile's summary, or null while loading; an empty map is a summary
  /// that could not be read, shown as dashes rather than as zeros.
  final Map<String, Map<String, dynamic>?> _summaries = {};

  List<HomeTile> get _tiles =>
      Phase2HomePage.tiles.where((tile) => widget.allowed(tile.path)).toList();

  @override
  void initState() {
    super.initState();
    for (final HomeTile tile in _tiles) {
      _summaries[tile.path] = null;
      widget.loadSummary(tile.path).then((summary) {
        if (mounted) setState(() => _summaries[tile.path] = summary);
      }, onError: (Object _) {
        if (mounted) setState(() => _summaries[tile.path] = const {});
      });
    }
  }

  void _open(String path) {
    final MenuItemSpec? item = MenuLayout.itemFor(path);
    if (item != null) widget.onOpen(item);
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final List<HomeTile> tiles = _tiles;
    final List<MenuItemSpec> daily = [
      for (final String path in Phase2HomePage.daily)
        if (widget.allowed(path))
          if (MenuLayout.itemFor(path) case final MenuItemSpec item) item,
    ];
    return Material(
      color: theme.colorScheme.surface,
      child: ListView(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
        children: [
          Text(
            widget.userName == null ? 'Home' : 'Welcome, ${widget.userName}',
            style: theme.textTheme.titleLarge
                ?.copyWith(fontWeight: FontWeight.w600),
          ),
          if (widget.firmName != null)
            Text(
              widget.firmName!,
              style: theme.textTheme.bodyMedium
                  ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
            ),
          if (tiles.isNotEmpty) ...[
            const SizedBox(height: 16),
            _heading(context, 'TODAY'),
            const SizedBox(height: 8),
            Wrap(
              spacing: 12,
              runSpacing: 12,
              children: [for (final HomeTile tile in tiles) _tile(tile)],
            ),
          ],
          if (daily.isNotEmpty) ...[
            const SizedBox(height: 20),
            _heading(context, 'YOUR SCREENS'),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                for (final MenuItemSpec item in daily)
                  OutlinedButton(
                    key: ValueKey('home-open-${item.path}'),
                    onPressed: () => widget.onOpen(item),
                    child: Text(item.label),
                  ),
              ],
            ),
          ],
          if (tiles.isEmpty && daily.isEmpty) ...[
            const SizedBox(height: 16),
            Text(
              'Choose a screen from the menu above, or press Ctrl+K and type '
              'its name.',
              style: theme.textTheme.bodyMedium,
            ),
          ],
        ],
      ),
    );
  }

  Widget _heading(BuildContext context, String label) => Text(
        label,
        style: Theme.of(context).textTheme.labelSmall?.copyWith(
              color: Theme.of(context).colorScheme.onSurfaceVariant,
              letterSpacing: .6,
              fontWeight: FontWeight.w600,
            ),
      );

  Widget _tile(HomeTile tile) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
    final Map<String, dynamic>? summary = _summaries[tile.path];
    final String title = MenuLayout.itemFor(tile.path)?.label ?? tile.path;
    return SizedBox(
      width: 260,
      child: Card(
        key: ValueKey('home-tile-${tile.path}'),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: () => _open(tile.path),
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(children: [
                  Expanded(
                    child: Text(title,
                        style: theme.textTheme.titleSmall
                            ?.copyWith(fontWeight: FontWeight.w600)),
                  ),
                  Icon(Icons.chevron_right,
                      size: 18, color: scheme.onSurfaceVariant),
                ]),
                const SizedBox(height: 10),
                if (summary == null)
                  const LinearProgressIndicator(minHeight: 2)
                else
                  Wrap(spacing: 18, runSpacing: 6, children: [
                    for (final (String label, String key, bool alert)
                        in tile.figures)
                      _figure(label, summary[key], alert),
                  ]),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _figure(String label, Object? value, bool alert) {
    final ThemeData theme = Theme.of(context);
    final String shown = value == null ? '-' : '$value';
    final bool alarming = alert && value is num && value > 0;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          shown,
          style: theme.textTheme.headlineSmall?.copyWith(
            fontWeight: FontWeight.w600,
            color: alarming ? theme.colorScheme.error : null,
          ),
        ),
        Text(
          label,
          style: theme.textTheme.bodySmall
              ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
        ),
      ],
    );
  }
}
