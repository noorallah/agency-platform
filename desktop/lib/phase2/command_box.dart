import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'menu_layout.dart';

/// The words people use for a screen that are not its name.
///
/// "Bill" finds Sales Invoices (UI_PHASE_2_DESIGN.md 4.4): somebody coming
/// from Tally or Busy types what they call the thing, not what this
/// application's catalogue calls it. Keyed by router path.
const Map<String, List<String>> _synonyms = {
  'salesInvoices/sales-invoices': ['bill', 'billing', 'invoice', 'tax invoice'],
  'salesOrders': ['so', 'order', 'booking'],
  'quotations': ['quote', 'estimate'],
  'deliveryNotes/delivery-notes': ['dn', 'dispatch', 'challan'],
  'salesReturns': ['return', 'sales return'],
  'purchases/purchase-orders': ['po', 'purchase order', 'indent'],
  'goodsReceipts/receipts': ['grn', 'inward', 'receiving'],
  'purchaseInvoices': ['purchase bill', 'supplier bill', 'purchase entry'],
  'accounting/receipts': ['collection', 'money in'],
  'accounting/payments': ['money out', 'pay supplier'],
  'accounting/journal-entries': ['journal', 'jv'],
  'accounting/ledgers': ['ledger', 'account book'],
  'masters/customers': ['party', 'debtor', 'buyer', 'retailer'],
  'masters/vendors': ['supplier', 'creditor', 'party'],
  'masters/products': ['item', 'sku', 'stock item'],
  'inventory/inventory': ['stock', 'stock enquiry'],
  'masters/customer-statements': ['statement', 'outstanding'],
  'sales/gst-returns': ['gstr', 'gstr-1', 'gstr-3b', 'gst'],
  'administration/uoms': ['unit', 'uom'],
  'masters/financial-years': ['financial year', 'fy', 'books'],
  'dashboard': ['home', 'dashboard'],
};

/// A screen the command box can offer, with what it is matched on.
class CommandScreen {
  const CommandScreen({
    required this.item,
    required this.area,
    required this.group,
  });

  final MenuItemSpec item;
  final String area;
  final String group;

  /// Where it lives, as the menu shows it.
  String get place => group == area ? area : '$area > $group';
}

/// The screens in [areas], in menu order -- already filtered to what the user
/// may open, so the box can never offer a screen the menu would not (4.12).
List<CommandScreen> commandScreens(Iterable<MenuAreaSpec> areas) => [
      for (final MenuAreaSpec area in areas)
        for (final MenuGroupSpec group in area.groups)
          for (final MenuItemSpec item in group.items)
            CommandScreen(item: item, area: area.label, group: group.label),
    ];

/// [screens] matching [query], best first: a name that starts with it, then
/// a word of the name that does, then a synonym, then anywhere in the name or
/// its place; the shorter name first among equals. Every word of a query of
/// several must match somewhere.
List<CommandScreen> matchScreens(List<CommandScreen> screens, String query) {
  final String q = query.trim().toLowerCase();
  if (q.isEmpty) return screens;
  final List<String> words = q.split(RegExp(r'\s+'));
  int? rank(CommandScreen screen) {
    final String name = screen.item.label.toLowerCase();
    final List<String> also = _synonyms[screen.item.path] ?? const [];
    final String haystack =
        '$name ${screen.place.toLowerCase()} ${also.join(' ')}';
    if (!words.every(haystack.contains)) return null;
    if (name.startsWith(q)) return 0;
    if (name.split(RegExp(r'[\s&-]+')).any((word) => word.startsWith(q))) {
      return 1;
    }
    if (also.any((word) => word == q || word.startsWith(q))) return 2;
    return 3;
  }

  final List<(int, int, CommandScreen)> ranked = [
    for (int i = 0; i < screens.length; i++)
      if (rank(screens[i]) case final int r) (r, i, screens[i]),
  ]..sort((a, b) {
      if (a.$1 != b.$1) return a.$1 - b.$1;
      // Equally good matches: the shorter name is the closer one ("cust"
      // means Customers before Customer Statements), then menu order.
      final int length = a.$3.item.label.length - b.$3.item.label.length;
      return length != 0 ? length : a.$2 - b.$2;
    });
  return [for (final (_, _, CommandScreen screen) in ranked) screen];
}

/// What the command box was asked to do.
sealed class CommandChoice {
  const CommandChoice();
}

class OpenScreenChoice extends CommandChoice {
  const OpenScreenChoice(this.item);
  final MenuItemSpec item;
}

class SearchRecordsChoice extends CommandChoice {
  const SearchRecordsChoice(this.query);
  final String query;
}

/// Ctrl+K or Alt+G (4.4): type, and the matching screens are there; the last
/// line searches records -- customers, products, documents -- for the same
/// words. Arrow keys move, Enter opens, Escape closes.
Future<CommandChoice?> showCommandBox(
  BuildContext context, {
  required List<CommandScreen> screens,
}) =>
    showDialog<CommandChoice>(
      context: context,
      barrierColor: Colors.black26,
      builder: (context) => _CommandBox(screens: screens),
    );

class _CommandBox extends StatefulWidget {
  const _CommandBox({required this.screens});

  final List<CommandScreen> screens;

  @override
  State<_CommandBox> createState() => _CommandBoxState();
}

class _CommandBoxState extends State<_CommandBox> {
  final TextEditingController _query = TextEditingController();
  final ScrollController _scroll = ScrollController();
  int _selected = 0;

  static const double _rowHeight = 40;

  @override
  void dispose() {
    _query.dispose();
    _scroll.dispose();
    super.dispose();
  }

  List<CommandScreen> get _matches =>
      matchScreens(widget.screens, _query.text).take(12).toList();

  bool get _offersRecords => _query.text.trim().isNotEmpty;

  int get _rowCount => _matches.length + (_offersRecords ? 1 : 0);

  void _move(int step) {
    if (_rowCount == 0) return;
    setState(() => _selected = (_selected + step + _rowCount) % _rowCount);
    final double target = _selected * _rowHeight;
    if (_scroll.hasClients) {
      _scroll.jumpTo(target.clamp(0, _scroll.position.maxScrollExtent));
    }
  }

  void _choose(int index) {
    final List<CommandScreen> matches = _matches;
    if (index < matches.length) {
      Navigator.of(context).pop(OpenScreenChoice(matches[index].item));
    } else if (_offersRecords) {
      Navigator.of(context).pop(SearchRecordsChoice(_query.text.trim()));
    }
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
    final List<CommandScreen> matches = _matches;
    return Align(
      alignment: const Alignment(0, -0.6),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 640, maxHeight: 520),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16),
          child: Material(
            color: scheme.surfaceContainerLowest,
            elevation: 8,
            borderRadius: BorderRadius.circular(10),
            clipBehavior: Clip.antiAlias,
            child: CallbackShortcuts(
              bindings: {
                const SingleActivator(LogicalKeyboardKey.arrowDown): () =>
                    _move(1),
                const SingleActivator(LogicalKeyboardKey.arrowUp): () =>
                    _move(-1),
              },
              child: Column(mainAxisSize: MainAxisSize.min, children: [
                TextField(
                  key: const ValueKey('command-box-input'),
                  controller: _query,
                  autofocus: true,
                  onChanged: (_) => setState(() => _selected = 0),
                  onSubmitted: (_) => _choose(_selected),
                  decoration: const InputDecoration(
                    hintText: 'Go to a screen, or search records',
                    prefixIcon: Icon(Icons.search),
                    border: InputBorder.none,
                    enabledBorder: InputBorder.none,
                    focusedBorder: InputBorder.none,
                    filled: false,
                    contentPadding: EdgeInsets.symmetric(vertical: 16),
                  ),
                ),
                const Divider(height: 1),
                Flexible(
                  child: _rowCount == 0
                      ? Padding(
                          padding: const EdgeInsets.all(20),
                          child: Text('No screen by that name.',
                              style: theme.textTheme.bodyMedium
                                  ?.copyWith(color: scheme.onSurfaceVariant)),
                        )
                      : ListView(
                          controller: _scroll,
                          shrinkWrap: true,
                          padding: const EdgeInsets.symmetric(vertical: 6),
                          children: [
                            if (matches.isNotEmpty)
                              _heading(context, 'SCREENS'),
                            for (int i = 0; i < matches.length; i++)
                              _row(
                                context,
                                index: i,
                                icon: Icons.open_in_browser_outlined,
                                title: matches[i].item.label,
                                trailing: matches[i].place,
                              ),
                            if (_offersRecords) ...[
                              _heading(context, 'RECORDS'),
                              _row(
                                context,
                                index: matches.length,
                                icon: Icons.manage_search,
                                title:
                                    'Search records for "${_query.text.trim()}"',
                                trailing: 'customers, products, documents',
                              ),
                            ],
                          ],
                        ),
                ),
                const Divider(height: 1),
                Padding(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                  child: Text(
                    'Up/Down to move  -  Enter to open  -  Esc to close',
                    style: theme.textTheme.bodySmall
                        ?.copyWith(color: scheme.onSurfaceVariant),
                  ),
                ),
              ]),
            ),
          ),
        ),
      ),
    );
  }

  Widget _heading(BuildContext context, String label) => Padding(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 4),
        child: Text(
          label,
          style: Theme.of(context).textTheme.labelSmall?.copyWith(
                color: Theme.of(context).colorScheme.onSurfaceVariant,
                letterSpacing: .6,
                fontWeight: FontWeight.w600,
              ),
        ),
      );

  Widget _row(
    BuildContext context, {
    required int index,
    required IconData icon,
    required String title,
    required String trailing,
  }) {
    final ColorScheme scheme = Theme.of(context).colorScheme;
    final bool selected = index == _selected;
    return InkWell(
      key: ValueKey('command-row-$index'),
      onTap: () => _choose(index),
      child: Container(
        height: _rowHeight,
        padding: const EdgeInsets.symmetric(horizontal: 16),
        // 4.14: the chosen row is tinted *and* marked by a solid bar.
        decoration: BoxDecoration(
          color: selected ? scheme.primary.withValues(alpha: .12) : null,
          border: Border(
            left: BorderSide(
              color: selected ? scheme.primary : Colors.transparent,
              width: 3,
            ),
          ),
        ),
        child: Row(children: [
          Icon(icon, size: 18, color: scheme.onSurfaceVariant),
          const SizedBox(width: 12),
          Expanded(
            child: Text(title, maxLines: 1, overflow: TextOverflow.ellipsis),
          ),
          const SizedBox(width: 12),
          Text(
            trailing,
            style: Theme.of(context)
                .textTheme
                .bodySmall
                ?.copyWith(color: scheme.onSurfaceVariant),
          ),
        ]),
      ),
    );
  }
}
