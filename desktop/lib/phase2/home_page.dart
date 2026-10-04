import 'package:flutter/material.dart';

import '../core/api/api_client.dart' show ApiException;
import '../core/design/design_tokens.dart';

import '../ui/workspace/save_in_dialog.dart';
import 'favourites.dart';
import 'indian_format.dart';
import 'menu_layout.dart';

export 'indian_format.dart' show indianAmount;

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

  /// Money received from customers on [day], reversed receipts left out --
  /// the wireframe's fourth key figure (backlog 49 item 4).
  Future<double> receiptsOn(DateTime day);

  /// Batches that expire within 30 days.
  Future<int> batchesExpiringIn30Days();

  /// Trade licences -- the firm's own, and its customers' and vendors' --
  /// that have run out or run out within the server's warning window.
  Future<int> expiringLicences();

  /// What needs doing in stock (STK-14): counts of products out of stock,
  /// below reorder level, over maximum, batches near expiry, goods in
  /// transit and count sheets open (`GET /inventory/alerts`).
  Future<Map<String, dynamic>> stockAlerts();

  /// The tax calendar: returns and deposits due, latest month first
  /// (backlog 63 item 4).
  Future<List<Map<String, dynamic>>> taxCalendar();

  /// Record a month's GSTR-1 or GSTR-3B as filed: `return_type`,
  /// `return_period`, `filed_on` and optionally `arn`.
  Future<void> markGstReturnFiled(Map<String, dynamic> body);

  /// Withdraw a filing recorded in error.
  Future<void> withdrawGstReturnFiling(String id);

  /// A document list's summary, by its screen's path.
  Future<Map<String, dynamic>> summary(String path);
}

/// One to-do line: a count from a list's summary, and the list it opens.
class HomeTodo {
  const HomeTodo(
    this.label,
    this.path,
    this.key, {
    this.alert = false,
    this.openPath,
    this.view,
  });

  final String label;

  /// The list whose summary holds the count.
  final String path;

  /// The summary field that holds the count.
  final String key;

  /// A non-zero count somebody should act on today.
  final bool alert;

  /// Where a click lands, when not on [path] itself -- a report that lists
  /// exactly what was counted.
  final String? openPath;

  /// What the landing screen shows: a view of the list, a report's id.
  final String? view;
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
    this.onOpenView,
    this.favourites,
    this.onFinishSetup,
  });

  /// "Finish setting up" (backlog 71, U5): when set, a calm card under the
  /// greeting asks for the agency's name and logo and calls this to open the
  /// form. Null -- everybody who may not give it, and everyone once it is
  /// given -- draws nothing.
  final VoidCallback? onFinishSetup;

  final String? firmName;
  final String? userName;

  /// The firm's day, UTC like everything the server stores.
  final DateTime today;
  final bool Function(String path) allowed;
  final HomeSource source;
  final ValueChanged<MenuItemSpec> onOpen;

  /// Open a screen showing one view of it ([HomeTodo.view]); null opens the
  /// screen as the menu would.
  final void Function(MenuItemSpec item, String view)? onOpenView;

  /// The parts this user has chosen not to see ([sections] ids).
  final Set<String> hidden;

  /// The user's starred screens (D-UI-3), which the FAVOURITES box shows and
  /// lets them remove and reorder; null shows [screens] and offers neither.
  final Favourites? favourites;

  /// Keep a new choice of hidden parts; null offers no Customise.
  final ValueChanged<Set<String>>? onCustomise;

  /// Home's parts, by id, as Customise lists them.
  static const Map<String, String> sections = {
    'figures': 'Key figures',
    'chart': 'Sales, last 14 days',
    'recent': 'Recent invoices',
    'tax': 'Tax calendar',
    'todo': 'To do',
    'screens': 'Favourites',
  };

  static const String salesInvoices = 'salesInvoices/sales-invoices';
  static const String stock = 'inventory/inventory';
  static const String expiry = 'inventory/expiry-monitor';
  static const String physicalCounts = 'inventory/physical-counts';
  static const String tradeLicences = 'masters/trade-licences';
  static const String receipts = 'accounting/receipts';
  static const String gstPayment = 'sales/gst-payment';
  static const String gstDeposits = 'sales/gst-deposits';
  static const String gstReturns = 'sales/gst-returns';

  /// The to-do list, in the order of a trading day.
  ///
  /// Each lands on exactly what it counts (the owner, 2026-09-26): the drafts
  /// of Sales Orders; for the rest a report, because "overdue" and "not yet
  /// delivered" are derived from what has been paid and dispatched, which no
  /// list filter can say.
  static const List<HomeTodo> todos = [
    HomeTodo('Orders to approve', 'salesOrders', 'draft', view: 'draft'),
    HomeTodo(
      'Orders to deliver',
      'deliveryNotes/delivery-notes',
      'pending_orders',
      openPath: 'reports/operational',
      view: 'sales-order-pending',
    ),
    HomeTodo(
      'Invoices overdue',
      salesInvoices,
      'overdue_invoices',
      alert: true,
      openPath: 'reports/financial',
      view: 'sales-invoice-overdue',
    ),
    HomeTodo(
      'POs to receive',
      'goodsReceipts/receipts',
      'pending_purchase_orders',
      openPath: 'reports/operational',
      view: 'purchase-order-pending',
    ),
    HomeTodo(
      'Purchase invoices overdue',
      'purchaseInvoices',
      'overdue_invoices',
      alert: true,
      openPath: 'reports/financial',
      view: 'purchase-invoice-overdue',
    ),
  ];

  /// The daily screens of 4.6: the favourites of somebody who has never
  /// starred one (the wireframe's "they start with the common screens their
  /// role may open").
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

/// One stock line of the to-do list (STK-14).
class _StockAlert {
  const _StockAlert(this.key, this.label, this.count, this.path, this.alert);

  final String key;
  final String label;
  final int count;
  final String path;
  final bool alert;
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
  final _Figure<double> _receiptsToday = _Figure();
  final _Figure<int> _expiring = _Figure();
  final _Figure<int> _licencesExpiring = _Figure();
  final _Figure<Map<String, dynamic>> _stockAlerts = _Figure();
  final _Figure<List<Map<String, dynamic>>> _calendar = _Figure();
  final Map<String, _Figure<Map<String, dynamic>>> _summaries = {};

  bool get _sales => widget.allowed(Phase2HomePage.salesInvoices);
  bool get _stock => widget.allowed(Phase2HomePage.stock);
  bool get _receipts => widget.allowed(Phase2HomePage.receipts);
  bool get _batches => widget.allowed(Phase2HomePage.expiry);
  bool get _licences => widget.allowed(Phase2HomePage.tradeLicences);
  bool get _tax => widget.allowed(Phase2HomePage.gstPayment);

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
    if (_stock) _load(_stockAlerts, widget.source.stockAlerts());
    if (_receipts) _load(_receiptsToday, widget.source.receiptsOn(_day));
    if (_batches) _load(_expiring, widget.source.batchesExpiringIn30Days());
    if (_tax) _loadCalendar();
    if (_licences) {
      _load(_licencesExpiring, widget.source.expiringLicences());
    }
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

  void _loadCalendar() {
    _calendar.value = null;
    _calendar.failed = false;
    _load(_calendar, widget.source.taxCalendar());
  }

  void _open(String path) {
    final MenuItemSpec? item = MenuLayout.itemFor(path);
    if (item != null && widget.allowed(path)) widget.onOpen(item);
  }

  /// A to-do line lands on what it counted: its report or view when the user
  /// may open it, the list itself otherwise.
  void _openTodo(HomeTodo todo) {
    final bool toReport =
        todo.openPath != null && widget.allowed(todo.openPath!);
    final String target = toReport ? todo.openPath! : todo.path;
    final MenuItemSpec? item = MenuLayout.itemFor(target);
    if (item == null || !widget.allowed(target)) return;
    final String? view = toReport || todo.openPath == null ? todo.view : null;
    if (view != null && widget.onOpenView != null) {
      widget.onOpenView!(item, view);
    } else {
      widget.onOpen(item);
    }
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
      if (shown('tax')) _taxCalendar(context),
      if (shown('screens')) _yourScreens(context),
    ]);
    return Material(
      color: theme.colorScheme.surface,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _greeting(context),
          if (widget.onFinishSetup != null) _finishSetup(context),
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

  Widget _finishSetup(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.fromLTRB(14, 10, 14, 0),
      child: Container(
        key: const ValueKey('home-finish-setup'),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        decoration: BoxDecoration(
          color: theme.colorScheme.surfaceContainerLow,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: theme.colorScheme.outlineVariant),
        ),
        child: Row(children: [
          Icon(Icons.flag_outlined,
              size: 20, color: theme.colorScheme.primary),
          const SizedBox(width: 12),
          Expanded(
            child: Text.rich(
              TextSpan(children: [
                TextSpan(
                  text: 'Finish setting up  ',
                  style: theme.textTheme.bodyMedium
                      ?.copyWith(fontWeight: FontWeight.w600),
                ),
                TextSpan(
                  text: "Give your agency's name and logo, so every PC "
                      'shows them.',
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
              ]),
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
          ),
          const SizedBox(width: 12),
          FilledButton.tonal(
            key: const ValueKey('home-finish-setup-open'),
            onPressed: widget.onFinishSetup,
            child: const Text('Set up your agency'),
          ),
        ]),
      ),
    );
  }

  /// The parts this user's role gives them at all; Customise offers only
  /// these, and hides among them.
  Set<String> get _available => {
        if (_sales || _stock) 'figures',
        if (_sales) ...{'chart', 'recent'},
        if (_tax) 'tax',
        if (_todoRows().isNotEmpty ||
            _stockAlertRows().isNotEmpty ||
            _batches ||
            _licences)
          'todo',
        if (widget.favourites != null || _screens().isNotEmpty) 'screens',
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
    // The wireframe's page bar: its own white band with a line beneath,
    // the title bold, the firm and date as plain grey text beside it, and
    // Customise at the far right.
    return Container(
      height: 44,
      padding: const EdgeInsets.symmetric(horizontal: 12),
      decoration: BoxDecoration(
        color: theme.colorScheme.surfaceContainerLowest,
        border: Border(
          bottom: BorderSide(color: theme.colorScheme.outlineVariant),
        ),
      ),
      child: Row(children: [
        Text(
          // As the wireframe: the greeting alone. A user's name is often the
          // firm's own ("MarketBridge ... Admin") and the text beside it
          // already names the firm, so it read twice.
          greeting,
          style: theme.textTheme.titleMedium
              ?.copyWith(fontWeight: FontWeight.w700),
        ),
        const SizedBox(width: 16),
        Expanded(
          child: Text(
            [if (widget.firmName != null) widget.firmName!, date].join(' · '),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: theme.textTheme.bodyMedium
                ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
          ),
        ),
        if (widget.onCustomise != null && _available.isNotEmpty)
          OutlinedButton(
            key: const ValueKey('home-customise'),
            onPressed: _customise,
            // The wireframe's page-bar button: small, square-cornered, a grey
            // edge and dark text -- not a rounded pill in the accent colour.
            style: OutlinedButton.styleFrom(
              foregroundColor: theme.colorScheme.onSurface,
              backgroundColor: theme.colorScheme.surfaceContainerLowest,
              side: BorderSide(color: theme.colorScheme.outlineVariant),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(5),
              ),
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
              minimumSize: const Size(0, 30),
              visualDensity: VisualDensity.compact,
              tapTargetSize: MaterialTapTargetSize.shrinkWrap,
            ),
            child: const Text('Customise'),
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
      if (_receipts)
        _kpi(context,
            key: 'receipts-today',
            label: 'Receipts today',
            value: _receiptsToday.value == null
                ? null
                : indianAmount(_receiptsToday.value!),
            failed: _receiptsToday.failed,
            path: Phase2HomePage.receipts),
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
                                          color:
                                              context.semanticColors.chartBar,
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

  // -- tax calendar ----------------------------------------------------------

  static const List<String> _monthNames = [
    'Jan',
    'Feb',
    'Mar',
    'Apr',
    'May',
    'Jun',
    'Jul',
    'Aug',
    'Sep',
    'Oct',
    'Nov',
    'Dec',
  ];

  static String _kindName(String kind) => switch (kind) {
        'GSTR1' => 'GSTR-1',
        'GSTR3B' => 'GSTR-3B',
        'IFF' => 'IFF (optional)',
        'PMT06' => 'PMT-06 deposit',
        _ => 'TCS deposit',
      };

  /// The period a row covers: the month, or the quarter ("Jul-Sep 2026")
  /// when a quarterly filer's return starts earlier than its own month.
  static String _periodLabel(Map<String, dynamic> row) {
    final String period = '${row['return_period']}';
    final String from = '${row['period_from'] ?? ''}';
    final String kind = '${row['kind']}';
    if ((kind == 'GSTR1' || kind == 'GSTR3B') &&
        from.length >= 7 &&
        period.length >= 7 &&
        from.substring(0, 7) != period.substring(0, 7)) {
      final int? a = int.tryParse(from.substring(5, 7));
      final int? b = int.tryParse(period.substring(5, 7));
      if (a != null && b != null && a >= 1 && a <= 12 && b >= 1 && b <= 12) {
        return '${_monthNames[a - 1]}-${_monthNames[b - 1]} '
            '${period.substring(0, 4)}';
      }
    }
    return _month(period);
  }

  /// "2026-08" as "Aug 2026".
  static String _month(String period) {
    final List<String> parts = period.split('-');
    final int? month = parts.length == 2 ? int.tryParse(parts[1]) : null;
    if (month == null || month < 1 || month > 12) return period;
    return '${_monthNames[month - 1]} ${parts[0]}';
  }

  /// "2026-09-20" as "20 Sep".
  static String _dayMonth(Object? iso) {
    final DateTime? d = DateTime.tryParse('${iso ?? ''}');
    return d == null ? '' : '${d.day} ${_monthNames[d.month - 1]}';
  }

  /// What a row says about its state, and whether it is a warning.
  (String, bool) _calendarStatus(Map<String, dynamic> row) {
    final String status = '${row['status'] ?? ''}';
    if (status == 'DONE') {
      final bool paid = row['kind'] == 'GSTR3B' && row['reference'] != null;
      return ('${paid ? 'Paid' : 'Filed'} ${_dayMonth(row['done_on'])}', false);
    }
    if (status == 'OPTIONAL') {
      return ('optional · by ${_dayMonth(row['due_date'])}', false);
    }
    if (status == 'LATE') {
      final int days = (row['days_late'] as num?)?.toInt() ?? 0;
      return ('$days ${days == 1 ? 'day' : 'days'} late', true);
    }
    final DateTime? due = DateTime.tryParse('${row['due_date'] ?? ''}');
    if (due == null) return ('due', false);
    final int left = DateTime.utc(due.year, due.month, due.day)
        .difference(DateTime.utc(_day.year, _day.month, _day.day))
        .inDays;
    return (
      left <= 0
          ? 'due today'
          : left == 1
              ? 'due in 1 day'
              : 'due in $left days',
      false,
    );
  }

  Widget _taxCalendar(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final List<Map<String, dynamic>> rows = _calendar.value ?? const [];
    return _Section(
      title: 'TAX CALENDAR',
      child: _calendar.failed
          ? Text('The tax calendar could not be read.',
              style: theme.textTheme.bodySmall)
          : _calendar.loading
              ? const LinearProgressIndicator(minHeight: 2)
              : rows.isEmpty
                  ? Text('Nothing due.', style: theme.textTheme.bodySmall)
                  : Column(children: [
                      for (final Map<String, dynamic> row in rows)
                        _taxRow(context, row),
                    ]),
    );
  }

  Widget _taxRow(BuildContext context, Map<String, dynamic> row) {
    final ThemeData theme = Theme.of(context);
    final String kind = '${row['kind']}';
    final String period = '${row['return_period']}';
    final bool done = row['status'] == 'DONE';
    final (String status, bool late) = _calendarStatus(row);
    final String? filingId = row['filing_id'] as String?;
    final bool canRecord =
        kind != 'TCS' &&
        kind != 'PMT06' &&
        widget.allowed(Phase2HomePage.gstReturns);
    final double amount = double.tryParse('${row['amount'] ?? 0}') ?? 0;
    final Color statusColour =
        late ? theme.colorScheme.error : theme.colorScheme.onSurfaceVariant;
    return InkWell(
      key: ValueKey('home-tax-$kind-$period'),
      onTap: () => _open(kind == 'GSTR1' || kind == 'IFF'
          ? Phase2HomePage.gstReturns
          : kind == 'PMT06'
              ? Phase2HomePage.gstDeposits
              : Phase2HomePage.gstPayment),
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 6, horizontal: 2),
        decoration: BoxDecoration(
          border: Border(
            bottom: BorderSide(color: theme.colorScheme.outlineVariant),
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(children: [
              Expanded(
                child: Text(
                  '${_kindName(kind)} · ${_periodLabel(row)}',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: theme.textTheme.bodyMedium
                      ?.copyWith(fontWeight: FontWeight.w600),
                ),
              ),
              const SizedBox(width: 8),
              Text(
                indianAmount(amount),
                style: theme.textTheme.bodyMedium?.copyWith(
                  fontFeatures: const [FontFeature.tabularFigures()],
                ),
              ),
            ]),
            const SizedBox(height: 2),
            Row(children: [
              if (done)
                Padding(
                  padding: const EdgeInsets.only(right: 4),
                  child: Icon(Icons.check_circle,
                      size: 14, color: theme.colorScheme.primary),
                ),
              Expanded(
                child: Text(
                  done
                      ? status
                      : '$status · due ${_dayMonth(row['due_date'])}',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: theme.textTheme.bodySmall
                      ?.copyWith(color: statusColour),
                ),
              ),
              if (!done && canRecord)
                _linkButton(
                  key: 'home-tax-mark-$kind-$period',
                  label: 'Mark filed',
                  onPressed: () => _markFiled(kind, period),
                ),
              if (done && canRecord && filingId != null)
                _linkButton(
                  key: 'home-tax-undo-$kind-$period',
                  label: 'Undo',
                  onPressed: () => _withdraw(filingId),
                ),
            ]),
          ],
        ),
      ),
    );
  }

  Widget _linkButton({
    required String key,
    required String label,
    required VoidCallback onPressed,
  }) =>
      TextButton(
        key: ValueKey(key),
        onPressed: onPressed,
        style: TextButton.styleFrom(
          padding: const EdgeInsets.symmetric(horizontal: 6),
          minimumSize: const Size(0, 24),
          visualDensity: VisualDensity.compact,
          tapTargetSize: MaterialTapTargetSize.shrinkWrap,
        ),
        child: Text(label),
      );

  Future<void> _markFiled(String kind, String period) async {
    final bool? saved = await showDialog<bool>(
      context: context,
      builder: (context) => _MarkFiledDialog(
        title: '${_kindName(kind)} · ${_month(period)}',
        today: widget.today,
        onSave: (String filedOn, String arn) =>
            widget.source.markGstReturnFiled({
          'return_type': kind,
          'return_period': period,
          'filed_on': filedOn,
          if (arn.isNotEmpty) 'arn': arn,
        }),
      ),
    );
    if (saved == true && mounted) setState(_loadCalendar);
  }

  Future<void> _withdraw(String filingId) async {
    try {
      await widget.source.withdrawGstReturnFiling(filingId);
    } on ApiException catch (exception) {
      if (!mounted) return;
      ScaffoldMessenger.maybeOf(context)?.showSnackBar(
        SnackBar(content: Text(exception.message)),
      );
      return;
    }
    if (mounted) setState(_loadCalendar);
  }

  List<HomeTodo> _todoRows() => [
        for (final HomeTodo todo in Phase2HomePage.todos)
          if (widget.allowed(todo.path)) todo,
      ];

  /// One line per non-zero stock count; a failed or unanswered read draws
  /// none, as the other to-do sources do not nag about what they could not
  /// read.
  List<_StockAlert> _stockAlertRows() {
    final Map<String, dynamic>? data = _stockAlerts.value;
    if (!_stock || data == null) return const [];
    int count(String key) {
      final Object? value = data[key];
      return value is num ? value.toInt() : 0;
    }

    String plural(int n, String one, String many) => n == 1 ? one : many;
    final int out = count('out');
    final int low = count('low');
    final int near = count('near_expiry');
    final int over = count('over_maximum');
    final int transit = count('in_transit');
    final int counts = count('open_counts');
    const String stock = Phase2HomePage.stock;
    final String countsPath =
        widget.allowed(Phase2HomePage.physicalCounts)
            ? Phase2HomePage.physicalCounts
            : stock;
    final String expiryPath =
        widget.allowed(Phase2HomePage.expiry) ? Phase2HomePage.expiry : stock;
    return [
      if (out > 0)
        _StockAlert('out', '$out ${plural(out, 'product', 'products')} out of '
            'stock', out, stock, true),
      if (low > 0)
        _StockAlert('low', '$low below reorder level', low, stock, true),
      if (near > 0)
        _StockAlert(
            'near-expiry',
            '$near ${plural(near, 'batch', 'batches')} near expiry',
            near,
            expiryPath,
            true),
      if (over > 0) _StockAlert('over', '$over over maximum', over, stock, false),
      if (transit > 0)
        _StockAlert('transit', '$transit in transit', transit, stock, false),
      if (counts > 0)
        _StockAlert(
            'counts',
            '$counts ${plural(counts, 'count sheet', 'count sheets')} open',
            counts,
            countsPath,
            false),
    ];
  }

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
            onTap: () => _openTodo(todo),
          ),
        for (final _StockAlert alert in _stockAlertRows())
          _row(
            context,
            key: 'todo-stock-${alert.key}',
            left: alert.label,
            right: '${alert.count}',
            strong: true,
            alert: alert.alert,
            onTap: () => _open(alert.path),
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
        if (_licences)
          _row(
            context,
            key: 'todo-licences-expiring',
            left: 'Licences expiring',
            right: _licencesExpiring.failed
                ? '-'
                : _licencesExpiring.value?.toString() ?? '…',
            strong: true,
            alert: (_licencesExpiring.value ?? 0) > 0,
            onTap: () => _open(Phase2HomePage.tradeLicences),
          ),
      ]),
    );
  }

  /// The favourites this user may open, in their order. A starred screen
  /// their role has since lost stays starred and is simply not drawn.
  List<MenuItemSpec> _screens() => [
        for (final String path
            in widget.favourites?.paths ?? Phase2HomePage.screens)
          if (widget.allowed(path))
            if (MenuLayout.itemFor(path) case final MenuItemSpec item) item,
      ];

  /// The wireframe's FAVOURITES: plain boxes of dark text in two columns,
  /// each with an x while pointed at, and dragged onto another to reorder.
  Widget _yourScreens(BuildContext context) {
    final Favourites? favourites = widget.favourites;
    if (favourites == null) return _favouriteBoxes(context);
    return ListenableBuilder(
      listenable: favourites,
      builder: (context, _) => _favouriteBoxes(context),
    );
  }

  Widget _favouriteBoxes(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final List<MenuItemSpec> items = _screens();
    return _Section(
      title: 'FAVOURITES',
      child: items.isEmpty
          ? Text(
              'Point at a screen in any menu and click its star to keep it '
              'here.',
              key: const ValueKey('home-favourites-empty'),
              style: theme.textTheme.bodySmall
                  ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
            )
          : LayoutBuilder(builder: (context, constraints) {
              final double width = (constraints.maxWidth - 6) / 2;
              return Wrap(spacing: 6, runSpacing: 6, children: [
                for (final MenuItemSpec item in items)
                  SizedBox(
                    width: width,
                    child: _FavouriteBox(
                      item: item,
                      favourites: widget.favourites,
                      onOpen: () => widget.onOpen(item),
                    ),
                  ),
              ]);
            }),
    );
  }

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

/// Records a filing. Saves itself and stays open with the server's message on
/// a refusal (D-DLG-1).
class _MarkFiledDialog extends StatefulWidget {
  const _MarkFiledDialog({
    required this.title,
    required this.today,
    required this.onSave,
  });

  final String title;
  final DateTime today;
  final Future<void> Function(String filedOn, String arn) onSave;

  @override
  State<_MarkFiledDialog> createState() => _MarkFiledDialogState();
}

class _MarkFiledDialogState extends State<_MarkFiledDialog>
    with SaveInDialog<_MarkFiledDialog> {
  late final TextEditingController _date;
  final TextEditingController _arn = TextEditingController();

  @override
  void initState() {
    super.initState();
    final DateTime t = widget.today;
    _date = TextEditingController(
      text: '${t.year.toString().padLeft(4, '0')}-'
          '${t.month.toString().padLeft(2, '0')}-'
          '${t.day.toString().padLeft(2, '0')}',
    );
  }

  @override
  void dispose() {
    _date.dispose();
    _arn.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text('Mark filed: ${widget.title}'),
      content: SizedBox(
        width: 340,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            saveErrorBanner(),
            TextField(
              key: const ValueKey('home-tax-filed-on'),
              controller: _date,
              decoration: const InputDecoration(
                labelText: 'Filed on',
                helperText: 'YYYY-MM-DD',
              ),
            ),
            const SizedBox(height: 8),
            TextField(
              key: const ValueKey('home-tax-arn'),
              controller: _arn,
              maxLength: 30,
              decoration: const InputDecoration(labelText: 'ARN (optional)'),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: saving ? null : () => Navigator.of(context).pop(false),
          child: const Text('Cancel'),
        ),
        FilledButton(
          key: const ValueKey('home-tax-save'),
          onPressed: saving
              ? null
              : () => saveAndClose<bool>(() async {
                    await widget.onSave(_date.text.trim(), _arn.text.trim());
                    return true;
                  }),
          child: const Text('Save'),
        ),
      ],
    );
  }
}

/// One box of Home's FAVOURITES. With [favourites] it shows an x while it is
/// pointed at, and can be dragged onto another box to take its place.
class _FavouriteBox extends StatefulWidget {
  const _FavouriteBox({
    required this.item,
    required this.favourites,
    required this.onOpen,
  });

  final MenuItemSpec item;
  final Favourites? favourites;
  final VoidCallback onOpen;

  @override
  State<_FavouriteBox> createState() => _FavouriteBoxState();
}

class _FavouriteBoxState extends State<_FavouriteBox> {
  bool _hovered = false;

  Widget _box(BuildContext context, {bool target = false}) {
    final ColorScheme scheme = Theme.of(context).colorScheme;
    final Favourites? favourites = widget.favourites;
    return Material(
      color: scheme.surfaceContainerLowest,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(6),
        side: BorderSide(
          color: target ? scheme.primary : scheme.outlineVariant,
          width: target ? 1.5 : 1,
        ),
      ),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        key: ValueKey('home-open-${widget.item.path}'),
        onTap: widget.onOpen,
        child: Row(children: [
          Expanded(
            child: Padding(
              padding: const EdgeInsets.all(8),
              child: Text(
                widget.item.label,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: Theme.of(context)
                    .textTheme
                    .bodyMedium
                    ?.copyWith(color: scheme.onSurface),
              ),
            ),
          ),
          if (favourites != null && _hovered)
            IconButton(
              key: ValueKey('home-unstar-${widget.item.path}'),
              tooltip: 'Remove from favourites',
              iconSize: 14,
              padding: EdgeInsets.zero,
              visualDensity: VisualDensity.compact,
              constraints: const BoxConstraints.tightFor(width: 28, height: 28),
              onPressed: () => favourites.remove(widget.item.path),
              icon: Icon(Icons.close, color: scheme.onSurfaceVariant),
            ),
        ]),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final Favourites? favourites = widget.favourites;
    final Widget box = MouseRegion(
      onEnter: (_) => setState(() => _hovered = true),
      onExit: (_) => setState(() => _hovered = false),
      child: _box(context),
    );
    if (favourites == null) return box;
    final String path = widget.item.path;
    return DragTarget<String>(
      onWillAcceptWithDetails: (details) => details.data != path,
      onAcceptWithDetails: (details) => favourites.move(details.data, path),
      builder: (context, candidates, _) => Draggable<String>(
        key: ValueKey('home-drag-$path'),
        data: path,
        feedback: Material(
          elevation: 4,
          borderRadius: BorderRadius.circular(6),
          child: Padding(
            padding: const EdgeInsets.all(8),
            child: Text(widget.item.label),
          ),
        ),
        childWhenDragging: Opacity(opacity: .4, child: _box(context)),
        child: candidates.isEmpty ? box : _box(context, target: true),
      ),
    );
  }
}
