// Credit a customer earns on what they buy, and spends on what they buy next.
//
// A register rather than a till: it shows the firm's scheme and every movement
// of credit under it. Spending credit happens where the bill is, not here.
//
// The one thing it must not misstate is what spending does. Redeeming
// **settles** a bill; it does not discount one. The difference is what GST the
// firm collects, so the screen says it rather than leaving a reader to assume
// the familiar thing.

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/entities.dart';
import '../../phase2/indian_format.dart';
import '../workspace/desktop_framework.dart';
import 'loyalty_adjust_dialog.dart';
import 'loyalty_settings_dialog.dart';

/// Show a firm's scheme and every movement of credit under it.
class LoyaltyPage extends StatefulWidget {
  const LoyaltyPage({
    super.key,
    required this.api,
    required this.permissions,
    required this.hasActiveFirm,
  });

  final ApiClient api;
  final PermissionService permissions;
  final bool hasActiveFirm;

  @override
  State<LoyaltyPage> createState() => _LoyaltyPageState();
}

class _LoyaltyPageState extends State<LoyaltyPage> {
  Json? _settings;
  List<Json> _entries = const [];

  /// Every customer the unfiltered ledger names, once each, for the picker.
  List<MapEntry<String, String>> _customers = const [];
  String? _customerId;
  Json? _balance;
  String? _error;
  bool _loading = true;

  bool get _mayView => widget.permissions.hasPermission('LOYALTY_VIEW');

  /// Spending or writing off a customer's credit is money, so it is its
  /// own authority rather than part of reading the register.
  bool get _mayManage => widget.permissions.hasPermission('LOYALTY_MANAGE');

  /// Granting points by hand is writing off a receivable once they are spent,
  /// so the route asks the scheme's own code rather than [_mayManage]'s.
  bool get _mayAdjust =>
      widget.permissions.hasPermission('LOYALTY_MANAGE_SETTINGS');

  @override
  void initState() {
    super.initState();
    if (widget.hasActiveFirm && _mayView) _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final Json settings = await widget.api.loyaltySettings();
      final List<Json> entries =
          await widget.api.loyaltyEntries(customerId: _customerId);
      final Json? balance = _customerId == null
          ? null
          : await widget.api.loyaltyBalance(_customerId!);
      if (!mounted) return;
      setState(() {
        _settings = settings;
        _entries = entries;
        _balance = balance;
        if (_customerId == null) _customers = _customersIn(entries);
        _loading = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.message;
        _loading = false;
      });
    }
  }

  /// Write off points that have run out of time.
  ///
  /// Safe to run twice -- each expiry names the entry it takes -- so the
  /// button says what it did rather than asking first.
  Future<void> _expire() async {
    try {
      final Json answer = await widget.api.expireLoyalty();
      if (!mounted) return;
      final int lapsed = (answer['expired'] as num?)?.toInt() ?? 0;
      NotificationService.show(
        context,
        lapsed == 0
            ? 'Nothing had lapsed.'
            : '$lapsed batch${lapsed == 1 ? '' : 'es'} of points lapsed.',
        kind: AppNotificationKind.success,
      );
      await _load();
    } on ApiException catch (error) {
      if (!mounted) return;
      NotificationService.show(context, error.message,
          kind: AppNotificationKind.error);
    }
  }

  /// Correct a balance by hand, starting from the customer on screen.
  Future<void> _adjust() async {
    final String? name = _customers
        .where((customer) => customer.key == _customerId)
        .map((customer) => customer.value)
        .firstOrNull;
    final bool? saved = await showDialog<bool>(
      context: context,
      builder: (_) => LoyaltyAdjustDialog(
        api: widget.api,
        customerId: _customerId,
        customerName: name,
      ),
    );
    if (saved != true || !mounted) return;
    NotificationService.show(context, 'Balance adjusted.',
        kind: AppNotificationKind.success);
    await _load();
  }

  /// Open the scheme, and re-read the banner if it changed.
  ///
  /// The banner beside the ledger states the rate, so leaving it stale after a
  /// save would show one rule while another was in force.
  Future<void> _openSettings() async {
    final bool? saved = await showDialog<bool>(
      context: context,
      builder: (_) => LoyaltySettingsDialog(
        api: widget.api,
        permissions: widget.permissions,
      ),
    );
    if (saved == true && mounted) await _load();
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.hasActiveFirm) {
      return const WorkspaceEmptyState(
        title: 'Choose a firm',
        message: 'A scheme belongs to one firm and its customers.',
      );
    }
    if (!_mayView) {
      return const WorkspaceEmptyState(
        icon: Icons.lock_outline,
        title: 'You cannot see this',
        message: 'Reading what customers have earned needs the view loyalty '
            'permission.',
      );
    }
    if (Phase2Scope.of(context)) return _phase2(context);
    return ManagementWorkspaceLayout(
      toolbar: Wrap(
        spacing: AppSpacing.sm,
        runSpacing: AppSpacing.sm,
        children: [
          Phase2Refresh(
            onPressed: _load,
            child: OutlinedButton.icon(
              onPressed: _load,
              icon: const Icon(Icons.refresh),
              label: const Text('Refresh'),
            ),
          ),
          OutlinedButton.icon(
            onPressed: _mayManage ? _expire : null,
            icon: const Icon(Icons.timer_off_outlined),
            label: const Text('Expire lapsed'),
          ),
          OutlinedButton.icon(
            onPressed: _mayAdjust ? _adjust : null,
            icon: const Icon(Icons.exposure_outlined),
            label: const Text('Adjust points'),
          ),
          // Offered to anyone who can read the scheme, not only to whoever may
          // change it: the banner beside this states the rate, and somebody
          // asking why a balance is what it is should be able to open the rule
          // behind it. The dialog itself is read-only without
          // `LOYALTY_MANAGE_SETTINGS`, and says so.
          OutlinedButton.icon(
            onPressed: _openSettings,
            icon: const Icon(Icons.tune_outlined),
            label: const Text('Scheme settings'),
          ),
        ],
      ),
      searchPanel: Column(
        mainAxisSize: MainAxisSize.min,
        children: [_schemeBanner(), _customerRow()],
      ),
      primaryContent: _ledger(),
      statusBar: WorkspaceStatusBar(
        total: _entries.length,
        selected: false,
        // Said plainly, because "redeem" sounds like a discount and it is not.
        message: 'Spending credit settles a bill; it does not discount it.',
      ),
    );
  }

  /// The scheme in one sentence, for phase 2's (i).
  String? get _schemeSentence {
    final Json? settings = _settings;
    if (settings == null) return null;
    if (settings['is_enabled'] != true) {
      return 'No scheme is running: nobody is earning anything.';
    }
    final String expiry = settings['expiry_months'] == null
        ? 'and never expire'
        : 'and expire after ${settings['expiry_months']} months';
    return '${trimDiscountRate('${settings['points_per_amount']}')} points per '
        '100, worth ${trimDiscountRate('${settings['amount_per_point']}')} '
        'each $expiry. At least ${settings['minimum_redemption_points']} '
        'before any can be spent. Spending credit settles a bill; it does '
        'not discount it.';
  }

  /// Phase 2 (review, 2026-09-27): the customer is a chip on the page line,
  /// their balance counters there too, the scheme behind the (i), Adjust on
  /// the line and the rarer steps under "..."; the ledger is a grid. Before,
  /// all of it was crammed into the search slot above a raw table.
  Widget _phase2(BuildContext context) {
    final Json? balance = _balance;
    String customerName = 'Everyone';
    for (final MapEntry<String, String> customer in _customers) {
      if (customer.key == _customerId) customerName = customer.value;
    }
    return ManagementWorkspaceLayout(
      toolbar: WorkspaceToolbar(
        actions: const [ToolbarAction.refresh],
        isEnabled: (_) => !_loading,
        onAction: (_) => _load(),
        trailing: [
          Phase2MenuChip<String>(
            key: const ValueKey('loyalty-customer'),
            label: 'Customer: $customerName',
            onSelected: (id) {
              setState(() => _customerId = id.isEmpty ? null : id);
              _load();
            },
            itemBuilder: (_) => [
              const PopupMenuItem<String>(value: '', child: Text('Everyone')),
              for (final MapEntry<String, String> customer in _customers)
                PopupMenuItem<String>(
                  value: customer.key,
                  child: Text(customer.value),
                ),
            ],
          ),
        ],
        commands: [
          ToolbarCommand(
            id: 'adjust-points',
            label: 'Adjust points',
            icon: Icons.exposure_outlined,
            onPressed: _mayAdjust ? _adjust : null,
          ),
          ToolbarCommand(
            id: 'expire-lapsed',
            label: 'Expire lapsed',
            icon: Icons.timer_off_outlined,
            menuOnly: true,
            onPressed: _mayManage ? _expire : null,
          ),
          // Anyone who can read the scheme may open its rule; the dialog is
          // read-only without the settings permission.
          ToolbarCommand(
            id: 'scheme-settings',
            label: 'Scheme settings',
            icon: Icons.tune_outlined,
            menuOnly: true,
            onPressed: _openSettings,
          ),
        ],
      ),
      searchPanel: const SizedBox.shrink(),
      notice: _schemeSentence,
      primaryContent: Column(children: [
        if (balance != null)
          SummaryCards(children: [
            SummaryCount(label: 'Points', value: _money(balance['points'])),
            SummaryCount(
              label: balance['redeemable'] == false
                  ? 'Worth (below the floor)'
                  : 'Worth',
              value: indianAmount(
                double.tryParse('${balance['amount'] ?? 0}') ?? 0,
                full: true,
              ),
            ),
          ]),
        Expanded(child: _ledgerGrid()),
      ]),
      statusBar: WorkspaceStatusBar(
        total: _entries.length,
        selected: false,
        message: 'Spending credit settles a bill; it does not discount it.',
      ),
    );
  }

  Widget _ledgerGrid() {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_error != null) {
      return WorkspaceEmptyState(
        icon: Icons.error_outline,
        title: 'Nothing could be read',
        message: _error!,
      );
    }
    if (_entries.isEmpty) {
      return const WorkspaceEmptyState(
        title: 'Nothing earned yet',
        message: 'Points are credited when a bill is approved.',
      );
    }
    return EnterpriseDataGrid<Json>(
      items: _entries,
      total: _entries.length,
      pageOffset: 0,
      rowsPerPage: _entries.length,
      availableRowsPerPage: [_entries.length],
      columns: const [
        GridColumn(key: 'on', label: 'On'),
        GridColumn(key: 'customer', label: 'Customer', priority: 1),
        GridColumn(key: 'why', label: 'Why'),
        GridColumn(key: 'against', label: 'Against'),
        GridColumn(key: 'points', label: 'Points', numeric: true),
        GridColumn(key: 'worth', label: 'Worth', numeric: true),
        GridColumn(key: 'expires', label: 'Expires'),
      ],
      id: (row) => '${row['id'] ?? row.hashCode}',
      cells: (row) => [
        stringValue(row['earned_on']),
        stringValue(row['customer_name']),
        statusInWords(stringValue(row['kind'])),
        stringValue(row['sales_invoice_number']),
        _points(row['points']),
        _money(row['amount']),
        row['expires_on'] == null ? 'never' : stringValue(row['expires_on']),
      ],
      onSelect: (_) {},
      onPageChanged: (_) {},
    );
  }

  Widget _schemeBanner() {
    final Json? settings = _settings;
    if (settings == null) return const SizedBox.shrink();
    final bool on = settings['is_enabled'] == true;
    final String expiry = settings['expiry_months'] == null
        // Null is a real choice, not a missing value, so it is spelled out.
        ? 'and never expire'
        : 'and expire after ${settings['expiry_months']} months';
    return Padding(
      padding: const EdgeInsets.all(AppSpacing.md),
      child: Row(
        children: [
          Icon(on ? Icons.card_giftcard : Icons.pause_circle_outline, size: 18),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Text(
              on
                  // Trimmed: the server's four decimals read as
                  // "2.0000 points per 100, worth 1.0000 each" (plan 10.8).
                  ? '${trimDiscountRate('${settings['points_per_amount']}')} '
                      'points per 100, worth '
                      '${trimDiscountRate('${settings['amount_per_point']}')} '
                      'each $expiry. '
                      'At least ${settings['minimum_redemption_points']} before '
                      'any can be spent.'
                  : 'No scheme is running: nobody is earning anything.',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ),
        ],
      ),
    );
  }

  /// One customer's ledger and balance, which the page could not answer:
  /// it had no customer filter and no balance, though the API had both
  /// (BL-31.15). The picker offers whoever the ledger has named -- a
  /// customer with no entry has no balance to show.
  Widget _customerRow() {
    final Json? balance = _balance;
    return Padding(
      padding: const EdgeInsets.fromLTRB(
          AppSpacing.md, 0, AppSpacing.md, AppSpacing.md),
      child: Row(children: [
        // Up to 320, but it gives way: the search strip narrows as the
        // toolbar beside it grows, and a fixed width overflowed it.
        Flexible(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 320),
            child: DropdownButton<String?>(
              value: _customerId,
              isExpanded: true,
              items: [
                const DropdownMenuItem<String?>(
                    value: null, child: Text('Everyone')),
                for (final MapEntry<String, String> customer in _customers)
                  DropdownMenuItem<String?>(
                      value: customer.key, child: Text(customer.value)),
              ],
              onChanged: (value) {
                setState(() => _customerId = value);
                _load();
              },
            ),
          ),
        ),
        const SizedBox(width: AppSpacing.md),
        if (balance != null)
          Expanded(
            child: Text(
              '${stringValue(balance['customer_name'])}: '
              '${_money(balance['points'])} points, worth '
              '${_money(balance['amount'])}'
              // The server's own floor, so the screen says "not yet"
              // rather than offering a redemption the service refuses.
              '${balance['redeemable'] == false ? ' — below the floor to spend' : ''}',
            ),
          ),
      ]),
    );
  }

  /// The customers the ledger names, once each, by name.
  static List<MapEntry<String, String>> _customersIn(List<Json> entries) {
    final Map<String, String> seen = <String, String>{};
    for (final Json row in entries) {
      final String id = stringValue(row['customer_id']);
      if (id.isNotEmpty) {
        seen.putIfAbsent(id, () => stringValue(row['customer_name']));
      }
    }
    return seen.entries.toList()..sort((a, b) => a.value.compareTo(b.value));
  }

  Widget _ledger() {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_error != null) {
      return WorkspaceEmptyState(
        icon: Icons.error_outline,
        title: 'Nothing could be read',
        message: _error!,
      );
    }
    if (_entries.isEmpty) {
      return const WorkspaceEmptyState(
        title: 'Nothing earned yet',
        message: 'Points are credited when a bill is approved.',
      );
    }
    final DataTable table = DataTable(
          columns: const [
            DataColumn(label: Text('On')),
            DataColumn(label: Text('Customer')),
            DataColumn(label: Text('Why')),
            DataColumn(label: Text('Against')),
            DataColumn(label: Text('Points')),
            DataColumn(label: Text('Worth')),
            DataColumn(label: Text('Expires')),
          ],
          rows: [
            for (final Json row in _entries)
              DataRow(cells: [
                DataCell(Text(stringValue(row['earned_on']))),
                DataCell(Text(stringValue(row['customer_name']))),
                DataCell(Text(stringValue(row['kind']))),
                DataCell(Text(stringValue(row['sales_invoice_number']))),
                // Signed, so a reader can see at a glance which way it went
                // without decoding the kind first.
                DataCell(Text(_points(row['points']))),
                DataCell(Text(_money(row['amount']))),
                DataCell(Text(
                  row['expires_on'] == null
                      ? 'never'
                      : stringValue(row['expires_on']),
                )),
              ]),
          ],
        );
    // Phase 2: the full width, in the lists' grid style.
    if (Phase2Scope.of(context)) {
      return SingleChildScrollView(child: Phase2WideTable(table: table));
    }
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: SingleChildScrollView(child: table),
    );
  }

  static String _points(Object? value) {
    final double parsed = double.tryParse('${value ?? 0}') ?? 0;
    final String shown = parsed.toStringAsFixed(2);
    return parsed > 0 ? '+$shown' : shown;
  }

  static String _money(Object? value) =>
      (double.tryParse('${value ?? 0}') ?? 0).toStringAsFixed(2);
}
