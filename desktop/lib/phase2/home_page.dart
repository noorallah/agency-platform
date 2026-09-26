import 'package:flutter/material.dart';

import 'menu_layout.dart';

/// Where Home's figures come from -- the endpoints each list's own screens and
/// reports already call. An interface so Home can be tested without a server.
abstract class HomeSource {
  /// Sales invoices dated [from] to [to] inclusive, every page of them.
  Future<List<Map<String, dynamic>>> invoiceRegister(
      DateTime from, DateTime to);

  /// Each customer's running balance.
  Future<List<Map<String, dynamic>>> customerOutstanding();

  /// Stock lines below their reorder level.
  Future<int> itemsBelowReorder();

  /// Batches that expire within 30 days.
  Future<int> batchesExpiringIn30Days();

  /// A document list's summary, by its screen's path.
  Future<Map<String, dynamic>> summary(String path);
}

/// One to-do line: a count from a list's summary, and the list it opens.
class HomeTodo {
  const HomeTodo(this.label, this.path, this.key, {this.alert = false});

  final String label;
  final String path;

  /// The summary field that holds the count.
  final String key;

  /// A non-zero count somebody should act on today.
  final bool alert;
}

/// Home in the phase 2 app (UI_PHASE_2_DESIGN.md 4.9), as the owner approved
/// it in the wireframe: a greeting line; the day's key figures; sales over the
/// last 14 days; recent invoices; a to-do list; the user's screens.
///
/// Every part is drawn only for a user whose role may open the list behind it
/// ([allowed], the menu's own answer, 4.12), so an owner, an accountant and a
/// storeman each get a different Home from the same page -- a storeman sees
/// stock and batches, and no receivables.
class Phase2HomePage extends StatefulWidget {
  const Phase2HomePage({
    super.key,
    required this.firmName,
    required this.userName,
    required this.today,
    required this.allowed,
    required this.source,
    required this.onOpen,
    this.hidden = const {},
    this.onCustomise,
  });

  final String? firmName;
  final String? userName;

  /// The firm's day, UTC like everything the server stores.
  final DateTime today;
  final bool Function(String path) allowed;
  final HomeSource source;
  final ValueChanged<MenuItemSpec> onOpen;

  /// The parts this user has chosen not to see ([sections] ids).
  final Set<String> hidden;

  /// Keep a new choice of hidden parts; null offers no Customise.
  final ValueChanged<Set<String>>? onCustomise;

  /// Home's parts, by id, as Customise lists them.
  static const Map<String, String> sections = {
    'figures': 'Key figures',
    'chart': 'Sales, last 14 days',
    'recent': 'Recent invoices',
    'todo': 'To do',
    'screens': 'Your screens',
  };

  static const String salesInvoices = 'salesInvoices/sales-invoices';
  static const String stock = 'inventory/inventory';
  static const String expiry = 'inventory/expiry-monitor';

  /// The to-do list, in the order of a trading day.
  static const List<HomeTodo> todos = [
    HomeTodo('Orders to approve', 'salesOrders', 'draft'),
    HomeTodo(
        'Orders to deliver', 'deliveryNotes/delivery-notes', 'pending_orders'),
    HomeTodo('Invoices overdue', salesInvoices, 'overdue_invoices',
        alert: true),
    HomeTodo(
        'POs to receive', 'goodsReceipts/receipts', 'pending_purchase_orders'),
    HomeTodo('Purchase bills overdue', 'purchaseInvoices', 'overdue_invoices',
        alert: true),
  ];

  /// The daily screens of 4.6. Favourites (4.3's star) will replace these
  /// with the user's own choice.
  static const List<String> screens = [
    salesInvoices,
    'accounting/receipts',
    'salesOrders',
    'quotations',
    'deliveryNotes/delivery-notes',
    'goodsReceipts/receipts',
    'purchaseInvoices',
    'accounting/payments',
    stock,
    'masters/customer-statements',
    'masters/customers',
    'masters/products',
    'dashboard',
  ];

  @override
  State<Phase2HomePage> createState() => _Phase2HomePageState();
}

/// A figure being fetched: null while loading, [failed] if it could not be.
class _Figure<T> {
  T? value;
  bool failed = false;
  bool get loading => value == null && !failed;
}

class _Phase2HomePageState extends State<Phase2HomePage> {
  final _Figure<List<Map<String, dynamic>>> _register = _Figure();
  final _Figure<List<Map<String, dynamic>>> _outstanding = _Figure();
  final _Figure<int> _belowReorder = _Figure();
  final _Figure<int> _expiring = _Figure();
  final Map<String, _Figure<Map<String, dynamic>>> _summaries = {};

  bool get _sales => widget.allowed(Phase2HomePage.salesInvoices);
  bool get _stock => widget.allowed(Phase2HomePage.stock);
  bool get _batches => widget.allowed(Phase2HomePage.expiry);

  DateTime get _day =>
      DateTime(widget.today.year, widget.today.month, widget.today.day);

  List<DateTime> get _fortnight => [
        for (int back = 13; back >= 0; back--)
          _day.subtract(Duration(days: back)),
      ];

  @override
  void initState() {
    super.initState();
    if (_sales) {
      _load(_register, widget.source.invoiceRegister(_fortnight.first, _day));
      _load(_outstanding, widget.source.customerOutstanding());
    }
    if (_stock) _load(_belowReorder, widget.source.itemsBelowReorder());
    if (_batches) _load(_expiring, widget.source.batchesExpiringIn30Days());
    for (final HomeTodo todo in Phase2HomePage.todos) {
      if (!widget.allowed(todo.path) || _summaries.containsKey(todo.path)) {
        continue;
      }
      final _Figure<Map<String, dynamic>> figure = _Figure();
      _summaries[todo.path] = figure;
      _load(figure, widget.source.summary(todo.path));
    }
  }

  void _load<T>(_Figure<T> figure, Future<T> future) {
    future.then((value) {
      if (mounted) setState(() => figure.value = value);
    }, onError: (Object _) {
      if (mounted) setState(() => figure.failed = true);
    });
  }

  void _open(String path) {
    final MenuItemSpec? item = MenuLayout.itemFor(path);
    if (item != null && widget.allowed(path)) widget.onOpen(item);
  }

  // -- figures -------------------------------------------------------------

  /// What was sold on [day]: approved and closed bills, as a sale is booked;
  /// a draft has not been sold and a cancelled bill was not.
  double _salesOn(DateTime day) {
    double total = 0;
    for (final Map<String, dynamic> row in _register.value ?? const []) {
      final String status = '${row['status'] ?? ''}'.toUpperCase();
      if (status != 'APPROVED' && status != 'CLOSED') continue;
      final DateTime? date = DateTime.tryParse('${row['invoice_date'] ?? ''}');
      if (date == null ||
          date.year != day.year ||
          date.month != day.month ||
          date.day != day.day) {
        continue;
      }
      total += double.tryParse('${row['grand_total'] ?? 0}') ?? 0;
    }
    return total;
  }

  double get _receivable => (_outstanding.value ?? const [])
      .map((row) => double.tryParse('${row['outstanding_amount'] ?? 0}') ?? 0)
      .where((amount) => amount > 0)
      .fold(0, (sum, amount) => sum + amount);

  int? _count(HomeTodo todo) {
    final Object? value = _summaries[todo.path]?.value?[todo.key];
    return value is num ? value.toInt() : null;
  }

  // -- layout --------------------------------------------------------------

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    bool shown(String section) =>
        _available.contains(section) && !widget.hidden.contains(section);
    final List<Widget> main = _spaced([
      if (shown('figures')) _kpis(context),
      if (shown('chart')) _chart(context),
      if (shown('recent')) _recent(context),
    ]);
    final List<Widget> side = _spaced([
      if (shown('todo')) _todo(context),
      if (shown('screens')) _yourScreens(context),
    ]);
    return Material(
      color: theme.colorScheme.surface,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _greeting(context),
          Expanded(
            child: LayoutBuilder(builder: (context, constraints) {
              if (main.isEmpty && side.isEmpty) {
                return Padding(
                  padding: const EdgeInsets.all(16),
                  child: Text(
                    'Choose a screen from the menu above, or press Ctrl+K and '
                    'type its name.',
                    style: theme.textTheme.bodyMedium,
                  ),
                );
              }
              // The wireframe's two columns, 2 : 1; one column when narrow.
              if (constraints.maxWidth < 860 || main.isEmpty || side.isEmpty) {
                return ListView(
                  padding: const EdgeInsets.all(14),
                  children: [
                    ...main,
                    if (main.isNotEmpty && side.isNotEmpty)
                      const SizedBox(height: 12),
                    ...side,
                  ],
                );
              }
              return SingleChildScrollView(
                padding: const EdgeInsets.all(14),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(flex: 2, child: Column(children: main)),
                    const SizedBox(width: 14),
                    Expanded(child: Column(children: side)),
                  ],
                ),
              );
            }),
          ),
        ],
      ),
    );
  }

  /// The parts this user's role gives them at all; Customise offers only
  /// these, and hides among them.
  Set<String> get _available => {
        if (_sales || _stock) 'figures',
        if (_sales) ...{'chart', 'recent'},
        if (_todoRows().isNotEmpty || _batches) 'todo',
        if (_screens().isNotEmpty) 'screens',
      };

  static List<Widget> _spaced(List<Widget> parts) => [
        for (int i = 0; i < parts.length; i++) ...[
          if (i > 0) const SizedBox(height: 12),
          parts[i],
        ],
      ];

  /// Customise (the wireframe's button): which of Home's parts to show.
  Future<void> _customise() async {
    final Set<String> available = _available;
    final Set<String> hidden = {...widget.hidden};
    final Set<String>? chosen = await showDialog<Set<String>>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setState) => AlertDialog(
          title: const Text('Customise Home'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              for (final MapEntry<String, String> section
                  in Phase2HomePage.sections.entries)
                if (available.contains(section.key))
                  CheckboxListTile(
                    key: ValueKey('home-show-${section.key}'),
                    title: Text(section.value),
                    value: !hidden.contains(section.key),
                    onChanged: (show) => setState(() => show == true
                        ? hidden.remove(section.key)
                        : hidden.add(section.key)),
                  ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () => Navigator.of(context).pop(hidden),
              child: const Text('Save'),
            ),
          ],
        ),
      ),
    );
    if (chosen != null) widget.onCustomise?.call(chosen);
  }

  /// "Good evening", the firm and the date -- the page's one line (4.5).
  Widget _greeting(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final int hour = DateTime.now().hour;
    final String greeting = hour < 12
        ? 'Good morning'
        : hour < 17
            ? 'Good afternoon'
            : 'Good evening';
    const List<String> days = [
      'Monday',
      'Tuesday',
      'Wednesday',
      'Thursday',
      'Friday',
      'Saturday',
      'Sunday',
    ];
    final DateTime d = _day;
    final String date = '${days[d.weekday - 1]} '
        '${d.day.toString().padLeft(2, '0')}-'
        '${d.month.toString().padLeft(2, '0')}-${d.year}';
    return Padding(
      padding: const EdgeInsets.fromLTRB(14, 10, 14, 6),
      child: Row(children: [
        Text(
          widget.userName == null ? greeting : '$greeting, ${widget.userName}',
          style: theme.textTheme.titleMedium
              ?.copyWith(fontWeight: FontWeight.w600),
        ),
        const SizedBox(width: 12),
        Flexible(
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
            decoration: BoxDecoration(
              color: theme.colorScheme.surfaceContainerLow,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: theme.colorScheme.outlineVariant),
            ),
            child: Text(
              [if (widget.firmName != null) widget.firmName!, date]
                  .join('  ·  '),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: theme.textTheme.bodySmall
                  ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
            ),
          ),
        ),
        const Spacer(),
        if (widget.onCustomise != null && _available.isNotEmpty)
          OutlinedButton.icon(
            key: const ValueKey('home-customise'),
            onPressed: _customise,
            icon: const Icon(Icons.tune, size: 18),
            label: const Text('Customise'),
          ),
      ]),
    );
  }

  Widget _kpis(BuildContext context) {
    final int? overdue = _count(Phase2HomePage.todos[2]);
    final List<Widget> tiles = [
      if (_sales) ...[
        _kpi(context,
            key: 'sales-today',
            label: 'Sales today',
            value: _register.loading || _register.failed
                ? null
                : indianAmount(_salesOn(_day)),
            failed: _register.failed,
            path: Phase2HomePage.salesInvoices),
        _kpi(context,
            key: 'sales-fortnight',
            label: 'Sales, last 14 days',
            value: _register.loading || _register.failed
                ? null
                : indianAmount(
                    _fortnight.fold(0.0, (sum, day) => sum + _salesOn(day))),
            failed: _register.failed,
            path: Phase2HomePage.salesInvoices),
        _kpi(context,
            key: 'receivable',
            label:
                overdue == null ? 'Receivable' : 'Receivable, $overdue overdue',
            alert: (overdue ?? 0) > 0,
            value: _outstanding.loading || _outstanding.failed
                ? null
                : indianAmount(_receivable),
            failed: _outstanding.failed,
            path: 'masters/customer-statements'),
      ],
      if (_stock)
        _kpi(context,
            key: 'below-reorder',
            label: 'Items below reorder',
            value: _belowReorder.value?.toString(),
            failed: _belowReorder.failed,
            path: Phase2HomePage.stock),
    ];
    return LayoutBuilder(builder: (context, constraints) {
      final int perRow = (constraints.maxWidth / 170).floor().clamp(1, 4);
      final double width = (constraints.maxWidth - (perRow - 1) * 10) / perRow;
      return Wrap(
        spacing: 10,
        runSpacing: 10,
        children: [
          for (final Widget tile in tiles) SizedBox(width: width, child: tile),
        ],
      );
    });
  }

  Widget _kpi(
    BuildContext context, {
    required String key,
    required String label,
    required String? value,
    required bool failed,
    required String path,
    bool alert = false,
  }) {
    final ThemeData theme = Theme.of(context);
    return _Card(
      key: ValueKey('home-kpi-$key'),
      onTap: () => _open(path),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            height: 30,
            child: value == null && !failed
                ? const Align(
                    alignment: Alignment.centerLeft,
                    child: SizedBox(
                      width: 60,
                      child: LinearProgressIndicator(minHeight: 2),
                    ),
                  )
                : Text(
                    failed ? '-' : value!,
                    style: theme.textTheme.headlineSmall
                        ?.copyWith(fontWeight: FontWeight.w700),
                  ),
          ),
          Text(
            label,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: theme.textTheme.bodySmall?.copyWith(
              color: alert
                  ? theme.colorScheme.error
                  : theme.colorScheme.onSurfaceVariant,
            ),
          ),
        ],
      ),
    );
  }

  /// Sales per day over the last 14 days: one series, so one colour and no
  /// legend -- the title names it; each bar says its day and amount on hover.
  Widget _chart(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final List<DateTime> days = _fortnight;
    final List<double> values = [for (final DateTime d in days) _salesOn(d)];
    final double top = values.fold(0.0, (a, b) => a > b ? a : b);
    return _Section(
      title: 'SALES, LAST 14 DAYS',
      child: SizedBox(
        height: 130,
        child: _register.loading
            ? const Center(child: LinearProgressIndicator(minHeight: 2))
            : _register.failed
                ? Center(
                    child: Text('Sales could not be read.',
                        style: theme.textTheme.bodySmall))
                : Column(children: [
                    Expanded(
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.end,
                        children: [
                          for (int i = 0; i < days.length; i++)
                            Expanded(
                              child: Tooltip(
                                // The exact figure on hover; the bar
                                // gives the size at a glance.
                                message: '${_short(days[i])}: '
                                    '${indianAmount(values[i], full: true)}',
                                child: Padding(
                                  // A 2 px gap each side between bars.
                                  padding:
                                      const EdgeInsets.symmetric(horizontal: 2),
                                  child: Align(
                                    alignment: Alignment.bottomCenter,
                                    child: FractionallySizedBox(
                                      heightFactor: top <= 0
                                          ? 0.02
                                          : (values[i] / top).clamp(0.02, 1.0),
                                      child: Container(
                                        key: ValueKey('home-bar-$i'),
                                        decoration: BoxDecoration(
                                          color: theme.colorScheme.primary,
                                          borderRadius:
                                              const BorderRadius.vertical(
                                                  top: Radius.circular(4)),
                                        ),
                                      ),
                                    ),
                                  ),
                                ),
                              ),
                            ),
                        ],
                      ),
                    ),
                    Divider(height: 1, color: theme.colorScheme.outlineVariant),
                    const SizedBox(height: 4),
                    Row(children: [
                      Text(_short(days.first),
                          style: theme.textTheme.bodySmall?.copyWith(
                              color: theme.colorScheme.onSurfaceVariant)),
                      const Spacer(),
                      Text('Today',
                          style: theme.textTheme.bodySmall?.copyWith(
                              color: theme.colorScheme.onSurfaceVariant)),
                    ]),
                  ]),
      ),
    );
  }

  Widget _recent(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final List<Map<String, dynamic>> rows = [...?_register.value]..sort(
        (a, b) => '${b['invoice_date']}${b['invoice_number']}'
            .compareTo('${a['invoice_date']}${a['invoice_number']}'));
    return _Section(
      title: 'RECENT INVOICES',
      child: _register.loading
          ? const LinearProgressIndicator(minHeight: 2)
          : rows.isEmpty
              ? Text(
                  _register.failed
                      ? 'Invoices could not be read.'
                      : 'No invoices in the last 14 days.',
                  style: theme.textTheme.bodySmall)
              : Column(children: [
                  for (final Map<String, dynamic> row in rows.take(6))
                    _row(
                      context,
                      key: 'recent-${row['invoice_number']}',
                      left: '${row['invoice_number'] ?? '-'}  ·  '
                          '${row['customer_name'] ?? ''}',
                      right: indianAmount(
                          double.tryParse('${row['grand_total'] ?? 0}') ?? 0,
                          full: true),
                      onTap: () => _open(Phase2HomePage.salesInvoices),
                    ),
                ]),
    );
  }

  List<HomeTodo> _todoRows() => [
        for (final HomeTodo todo in Phase2HomePage.todos)
          if (widget.allowed(todo.path)) todo,
      ];

  Widget _todo(BuildContext context) {
    return _Section(
      title: 'TO DO',
      child: Column(children: [
        for (final HomeTodo todo in _todoRows())
          _row(
            context,
            key: 'todo-${todo.label}',
            left: todo.label,
            right: _summaries[todo.path]?.failed ?? false
                ? '-'
                : _count(todo)?.toString() ?? '…',
            strong: true,
            alert: todo.alert && (_count(todo) ?? 0) > 0,
            onTap: () => _open(todo.path),
          ),
        if (_batches)
          _row(
            context,
            key: 'todo-expiring',
            left: 'Batches expiring in 30 days',
            right: _expiring.failed ? '-' : _expiring.value?.toString() ?? '…',
            strong: true,
            alert: (_expiring.value ?? 0) > 0,
            onTap: () => _open(Phase2HomePage.expiry),
          ),
      ]),
    );
  }

  List<MenuItemSpec> _screens() => [
        for (final String path in Phase2HomePage.screens)
          if (widget.allowed(path))
            if (MenuLayout.itemFor(path) case final MenuItemSpec item) item,
      ];

  Widget _yourScreens(BuildContext context) => _Section(
        title: 'YOUR SCREENS',
        child: LayoutBuilder(builder: (context, constraints) {
          final double width = (constraints.maxWidth - 6) / 2;
          return Wrap(spacing: 6, runSpacing: 6, children: [
            for (final MenuItemSpec item in _screens())
              SizedBox(
                width: width,
                child: OutlinedButton(
                  key: ValueKey('home-open-${item.path}'),
                  style: OutlinedButton.styleFrom(
                    alignment: Alignment.centerLeft,
                    padding: const EdgeInsets.symmetric(
                        horizontal: 10, vertical: 12),
                    shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(6)),
                  ),
                  onPressed: () => widget.onOpen(item),
                  child: Text(item.label,
                      maxLines: 1, overflow: TextOverflow.ellipsis),
                ),
              ),
          ]);
        }),
      );

  Widget _row(
    BuildContext context, {
    required String key,
    required String left,
    required String right,
    required VoidCallback onTap,
    bool strong = false,
    bool alert = false,
  }) {
    final ThemeData theme = Theme.of(context);
    return InkWell(
      key: ValueKey('home-$key'),
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 7, horizontal: 2),
        decoration: BoxDecoration(
          border: Border(
            bottom: BorderSide(color: theme.colorScheme.outlineVariant),
          ),
        ),
        child: Row(children: [
          Expanded(
            child: Text(left, maxLines: 1, overflow: TextOverflow.ellipsis),
          ),
          const SizedBox(width: 8),
          Text(
            right,
            style: theme.textTheme.bodyMedium?.copyWith(
              fontWeight: strong ? FontWeight.w700 : null,
              color: alert ? theme.colorScheme.error : null,
              fontFeatures: const [FontFeature.tabularFigures()],
            ),
          ),
        ]),
      ),
    );
  }

  static String _short(DateTime d) =>
      '${d.day.toString().padLeft(2, '0')}-${d.month.toString().padLeft(2, '0')}';
}

/// A card on Home: a light border, as the wireframe draws them.
class _Card extends StatelessWidget {
  const _Card({super.key, required this.child, this.onTap});

  final Widget child;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final ColorScheme scheme = Theme.of(context).colorScheme;
    return Material(
      color: scheme.surfaceContainerLowest,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(8),
        side: BorderSide(color: scheme.outlineVariant),
      ),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
          child: child,
        ),
      ),
    );
  }
}

/// A titled card: "TO DO", "RECENT INVOICES".
class _Section extends StatelessWidget {
  const _Section({required this.title, required this.child});

  final String title;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return _Card(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            title,
            style: theme.textTheme.labelSmall?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
              letterSpacing: .6,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 8),
          child,
        ],
      ),
    );
  }
}

/// An amount the Indian way: lakh and crore for the large figures a glance
/// reads ("1.84 L", "2.10 Cr"), Indian digit grouping otherwise
/// ("62,400", "1,12,050.00" when [full]).
String indianAmount(double value, {bool full = false}) {
  final double magnitude = value.abs();
  final String sign = value < 0 ? '-' : '';
  if (!full && magnitude >= 10000000) {
    return '$sign${(magnitude / 10000000).toStringAsFixed(2)} Cr';
  }
  if (!full && magnitude >= 100000) {
    return '$sign${(magnitude / 100000).toStringAsFixed(2)} L';
  }
  final String fixed = magnitude.toStringAsFixed(full ? 2 : 0);
  final List<String> parts = fixed.split('.');
  final String digits = parts.first;
  String grouped;
  if (digits.length <= 3) {
    grouped = digits;
  } else {
    final String last3 = digits.substring(digits.length - 3);
    String rest = digits.substring(0, digits.length - 3);
    final List<String> pairs = [];
    while (rest.length > 2) {
      pairs.insert(0, rest.substring(rest.length - 2));
      rest = rest.substring(0, rest.length - 2);
    }
    if (rest.isNotEmpty) pairs.insert(0, rest);
    grouped = '${pairs.join(',')},$last3';
  }
  return '$sign$grouped${parts.length > 1 ? '.${parts[1]}' : ''}';
}
