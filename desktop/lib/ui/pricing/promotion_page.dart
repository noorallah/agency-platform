import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/entities.dart';
import '../../models/pricing.dart';
import '../workspace/desktop_framework.dart';
import 'promotion_dialog.dart';

/// The offers a firm is running, in the order they apply.
///
/// A price list is a standing arrangement; a promotion is an offer, and unlike
/// a price list **several apply at once**. They run in priority order, lowest
/// number first, and each says whether it lets the ones behind it apply too.
///
/// Two things this screen has to say plainly, because both surprise people.
/// Percentages **compound on what is left**, so two ten percent offers take
/// nineteen percent rather than twenty. And a discount somebody types on a
/// line beats every promotion on it — a person deciding beats a rule.
class PromotionPage extends StatefulWidget {
  const PromotionPage({
    super.key,
    required this.api,
    required this.permissions,
    required this.hasActiveFirm,
  });

  final ApiClient api;
  final PermissionService permissions;
  final bool hasActiveFirm;

  @override
  State<PromotionPage> createState() => _PromotionPageState();
}

class _PromotionPageState extends State<PromotionPage> {
  final TextEditingController _search = TextEditingController();

  /// Which half of the screen is showing. Offers and the codes that reach
  /// them are two lists about one thing, so they share a screen rather than
  /// competing for a place in the sales module's tab bar.
  bool _showingCoupons = false;

  List<PromotionRecord> _rows = const [];
  List<PromotionCouponRecord> _coupons = const [];
  PromotionRecord? _selected;
  PromotionCouponRecord? _selectedCoupon;
  int _total = 0;
  int _page = 1;
  bool _loading = true;
  String? _error;

  bool get _mayManage => widget.permissions.hasPermission('PROMOTION_MANAGE');

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
    final int page = requestedPage ?? _page;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      if (_showingCoupons) {
        final PagedResult<PromotionCouponRecord> coupons =
            await widget.api.promotionCoupons(page: page, search: _search.text);
        if (!mounted) return;
        setState(() {
          _coupons = coupons.items;
          _total = coupons.total;
          _page = page;
          _loading = false;
          _selectedCoupon = _coupons
              .where((row) => row.id == _selectedCoupon?.id)
              .firstOrNull;
        });
        return;
      }
      final PagedResult<PromotionRecord> result = await widget.api.promotions(
        page: page,
        search: _search.text,
      );
      if (!mounted) return;
      setState(() {
        _rows = result.items;
        _total = result.total;
        _page = page;
        _loading = false;
        _selected = _rows.where((row) => row.id == _selected?.id).firstOrNull;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.message;
        _loading = false;
      });
    }
  }

  Future<void> _edit({PromotionRecord? existing}) async {
    final bool? saved = await showDialog<bool>(
      context: context,
      builder: (_) => PromotionDialog(api: widget.api, existing: existing),
    );
    if (saved ?? false) unawaited(_load());
  }

  Future<void> _delete(PromotionRecord row) async {
    try {
      await widget.api.deletePromotion(row.id);
      if (!mounted) return;
      NotificationService.show(
        context,
        'Promotion ${row.code} retired.',
        kind: AppNotificationKind.success,
      );
      unawaited(_load());
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
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          SegmentedButton<bool>(
            segments: const [
              ButtonSegment(value: false, label: Text('Offers')),
              ButtonSegment(value: true, label: Text('Coupons')),
            ],
            selected: {_showingCoupons},
            onSelectionChanged: (choice) {
              setState(() {
                _showingCoupons = choice.first;
                _page = 1;
              });
              unawaited(_load(requestedPage: 1));
            },
          ),
          if (_mayManage && !_showingCoupons)
            FilledButton.icon(
              onPressed: () => unawaited(_edit()),
              icon: const Icon(Icons.add),
              label: const Text('New promotion'),
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
        hintText: 'Search by name...',
        onSearch: (_) => unawaited(_load(requestedPage: 1)),
      ),
      primaryContent: _showingCoupons ? _couponContent() : _content(),
      detailsPanel: _showingCoupons
          ? null
          : (_selected == null ? null : _details(_selected!)),
      statusBar: WorkspaceStatusBar(
        total: _total,
        selected: _showingCoupons ? _selectedCoupon != null : _selected != null,
        message: _loading ? 'Loading...' : null,
      ),
    );
  }

  Widget _content() {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_error != null) {
      return WorkspaceEmptyState(
        title: 'Promotions unavailable',
        message: _error!,
      );
    }
    if (_rows.isEmpty) {
      return WorkspaceEmptyState(
        title: _search.text.trim().isEmpty
            ? 'No promotions yet'
            : 'Nothing matches that search',
        message: 'A promotion is an offer that applies while a document is '
            'priced — a rate off a line, off the whole bill, or goods given '
            'away. Several can apply to one order.',
      );
    }
    return EnterpriseDataGrid<PromotionRecord>(
      items: _rows,
      total: _total,
      pageOffset: (_page - 1) * 20,
      rowsPerPage: 20,
      selectedId: _selected?.id,
      columns: const [
        GridColumn(key: 'priority', label: 'Order'),
        GridColumn(key: 'code', label: 'Code'),
        GridColumn(key: 'name', label: 'Name'),
        GridColumn(key: 'gives', label: 'Gives'),
        GridColumn(key: 'stacks', label: 'Stacks'),
        GridColumn(key: 'window', label: 'In force'),
        GridColumn(key: 'status', label: 'Status'),
      ],
      id: (row) => row.id,
      cells: (row) => [
        '${row.priority}',
        row.code,
        row.name,
        _benefitLabel(row),
        row.allowStacking ? 'Yes' : 'Ends here',
        _windowLabel(row),
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
        if (action == WorkspaceContextAction.edit) {
          unawaited(_edit(existing: row));
        }
        if (action == WorkspaceContextAction.delete) unawaited(_delete(row));
      },
    );
  }

  Widget _couponContent() {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_error != null) {
      return WorkspaceEmptyState(title: 'Coupons unavailable', message: _error!);
    }
    if (_coupons.isEmpty) {
      return const WorkspaceEmptyState(
        title: 'No coupons yet',
        message: 'A coupon is a code a customer presents to claim an offer. '
            'The benefit lives on the offer; the coupon decides who reaches '
            'it, and how often.',
      );
    }
    return EnterpriseDataGrid<PromotionCouponRecord>(
      items: _coupons,
      total: _total,
      pageOffset: (_page - 1) * 20,
      rowsPerPage: 20,
      selectedId: _selectedCoupon?.id,
      columns: const [
        GridColumn(key: 'code', label: 'Code'),
        GridColumn(key: 'promotion', label: 'Offer'),
        GridColumn(key: 'used', label: 'Claimed'),
        GridColumn(key: 'per', label: 'Per customer'),
        GridColumn(key: 'status', label: 'Status'),
      ],
      id: (row) => row.id,
      cells: (row) => [
        row.code,
        row.promotionCode,
        row.usageLabel,
        row.maxRedemptionsPerCustomer == null
            ? 'No limit'
            : '${row.maxRedemptionsPerCustomer}',
        row.status,
      ],
      onSelect: (row) => setState(() => _selectedCoupon = row),
      onPageChanged: (page) => unawaited(_load(requestedPage: page)),
    );
  }

  static String _benefitLabel(PromotionRecord row) {
    if (row.actions.isEmpty) return '—';
    return row.actions.map(_actionLabel).join(', ');
  }

  static String _actionLabel(PromotionActionRecord action) =>
      switch (action.actionType) {
        'LINE_DISCOUNT_PERCENT' => '${action.percent}% off the line',
        'LINE_DISCOUNT_AMOUNT' => '${action.amount} off the line',
        'BILL_DISCOUNT_PERCENT' => '${action.percent}% off the bill',
        'BILL_DISCOUNT_AMOUNT' => '${action.amount} off the bill',
        'FREE_QUANTITY' =>
          'buy ${action.buyQuantity}, get ${action.freeQuantity} free',
        _ => action.actionType,
      };

  static String _windowLabel(PromotionRecord row) {
    if (row.effectiveFrom.isEmpty && row.effectiveTo.isEmpty) return 'Always';
    if (row.effectiveTo.isEmpty) return 'From ${row.effectiveFrom}';
    if (row.effectiveFrom.isEmpty) return 'Until ${row.effectiveTo}';
    return '${row.effectiveFrom} to ${row.effectiveTo}';
  }

  Widget _details(PromotionRecord row) {
    final ThemeData theme = Theme.of(context);
    return SingleChildScrollView(
      padding: const EdgeInsets.all(AppSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(row.name, style: theme.textTheme.titleMedium),
          Text(
            '${row.code} · revision ${row.versionNumber} · applies '
            '${row.priority == 1 ? 'first' : 'at ${row.priority}'}',
            style: theme.textTheme.bodySmall,
          ),
          const SizedBox(height: AppSpacing.sm),
          Text('In force ${_windowLabel(row)}',
              style: theme.textTheme.bodySmall),
          if (row.description.isNotEmpty) ...[
            const SizedBox(height: AppSpacing.sm),
            Text(row.description, style: theme.textTheme.bodyMedium),
          ],
          const SizedBox(height: AppSpacing.md),
          Text('Gives', style: theme.textTheme.titleSmall),
          const SizedBox(height: AppSpacing.xs),
          for (final PromotionActionRecord action in row.actions)
            Padding(
              padding: const EdgeInsets.only(bottom: AppSpacing.xs),
              child: Text(_actionLabel(action)),
            ),
          const SizedBox(height: AppSpacing.md),
          Text('Applies when', style: theme.textTheme.titleSmall),
          const SizedBox(height: AppSpacing.xs),
          if (row.conditions.isEmpty)
            Text(
              'Always — no conditions, so every line qualifies.',
              style: theme.textTheme.bodySmall,
            ),
          for (final PromotionConditionRecord condition in row.conditions)
            Padding(
              padding: const EdgeInsets.only(bottom: AppSpacing.xs),
              child: Text(
                '${condition.fieldKey} ${condition.operator} '
                '${condition.valueText.isNotEmpty ? condition.valueText : condition.valueNumber}',
                style: theme.textTheme.bodySmall,
              ),
            ),
          const SizedBox(height: AppSpacing.md),
          Text(
            row.allowStacking
                ? 'Other promotions may still apply after this one. '
                    'Percentages compound on what is left, so two ten percent '
                    'offers take nineteen percent, not twenty.'
                : 'This promotion ends the stack: nothing after it applies.',
            style: theme.textTheme.bodySmall,
          ),
        ],
      ),
    );
  }
}
